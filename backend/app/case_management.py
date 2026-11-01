"""Case management: the ticket seen as a case from request to close.

A case is a ServiceRequest. This module adds what ties its parts together: milestones computed from facts on the case,
the status moves staff may make, closure checks, playbook tasks, deadlines, the case team and the case fee.
See docs/case-management.md.
"""
from datetime import datetime, timedelta

from . import config, document_requirements
from .models import CLOSED_STATUSES, TICKET_STATUSES, CaseMember, CaseTask, ServiceRequest, User, utcnow

OPEN_STATUSES = tuple(s for s in TICKET_STATUSES if s not in CLOSED_STATUSES and s != "draft")
OUTCOME_LABELS = {
    "delivered": "Work delivered",
    "withdrawn": "Withdrawn by the customer",
    "not_viable": "Not viable",
    "duplicate": "Duplicate request",
    "other": "Other",
}
MEMBER_ROLE_LABELS = {"associate": "Associate", "paralegal": "Paralegal", "reviewer": "Reviewer"}
FEE_LABELS = {"none": "No fee quoted", "quoted": "Fee quoted, not paid", "paid": "Fee paid", "waived": "Fee waived"}
# (key, label). Customer wording is the same; it describes the case, not the team.
MILESTONES = (
    ("received", "Request received"),
    ("scoped", "Scope and fee agreed"),
    ("assigned", "Lawyer assigned"),
    ("documents", "Documents verified"),
    ("signed", "Report signed"),
    ("closed", "Case closed"),
)
# The case board's columns: the milestone each open case is working towards ("received" is always done).
BOARD_COLUMNS = (
    ("scoped", "Confirm scope and fee"),
    ("assigned", "Assign a lawyer"),
    ("documents", "Collect and verify documents"),
    ("signed", "Sign the report"),
    ("closed", "Ready to close"),
)
_PAST_SCOPE = ("approved_for_processing", "assigned", "in_progress", "quality_review", "completed")

def _aware(value: datetime | None) -> datetime | None:
    from .tickets import aware
    return aware(value) if value else None

def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None

def needs_documents(ticket: ServiceRequest) -> bool:
    """Whether the case runs through a document checklist and report (a plain consultation booking does not)."""
    return ticket.report is not None or ticket.service_type.slug in document_requirements.SERVICES

def _reached_scope(ticket: ServiceRequest) -> bool:
    if ticket.fee_status in ("quoted", "paid", "waived") or ticket.status in _PAST_SCOPE:
        return True
    return any(e.event_type == "status_changed" and (e.new_value or {}).get("status") in _PAST_SCOPE for e in ticket.events)

def milestone_state(ticket: ServiceRequest) -> dict[str, bool]:
    report = ticket.report
    from .case_files import checklist_complete
    return {
        "received": True,
        "scoped": _reached_scope(ticket),
        "assigned": ticket.active_assignment is not None,
        "documents": bool(report and report.status != "draft" and checklist_complete(report)),
        "signed": bool(report and report.status == "signed"),
        "closed": ticket.status == "completed",
    }

def milestones(ticket: ServiceRequest) -> list[dict]:
    done = milestone_state(ticket)
    skip = set() if needs_documents(ticket) else {"documents", "signed"}
    rows = [{"key": k, "label": label, "done": done[k]} for k, label in MILESTONES if k not in skip]
    current = next((r["key"] for r in rows if not r["done"]), None)
    for r in rows:
        r["current"] = r["key"] == current
    return rows

def current_milestone(ticket: ServiceRequest) -> str:
    return next((m["key"] for m in milestones(ticket) if m["current"]), "closed")

# ---- Status moves ----

def allowed_statuses(ticket: ServiceRequest) -> list[str]:
    """Where staff may move the case next. System moves (bookings, customer replies) are not limited."""
    status = ticket.status
    if status in CLOSED_STATUSES:
        return ["reopened"]
    if status == "on_hold":
        return [s for s in OPEN_STATUSES if s not in ("on_hold", "reopened")] + ["cancelled"]
    return [s for s in OPEN_STATUSES if s not in (status, "reopened")] + list(CLOSED_STATUSES)

def closure_check(ticket: ServiceRequest) -> dict:
    """What stops the case closing as Completed (blockers) and what will happen anyway (warnings)."""
    blockers, warnings = [], []
    if ticket.fee_status == "quoted":
        blockers.append(f"The fee of ₹{(ticket.fee_quote_paise or 0) // 100:,} is not paid or waived.")
    report = ticket.report
    if report is not None and report.status != "signed":
        blockers.append("The report is started but the signed final report is not uploaded.")
    upcoming = [m for m in ticket.meetings if m.status == "scheduled"]
    if upcoming:
        blockers.append(f"{len(upcoming)} meeting{'s are' if len(upcoming) > 1 else ' is'} still scheduled. Mark {'them' if len(upcoming) > 1 else 'it'} done or cancel first.")
    open_tasks = [t for t in ticket.tasks if t.status == "open"]
    if open_tasks:
        warnings.append(f"{len(open_tasks)} open task{'s' if len(open_tasks) > 1 else ''} will be cancelled.")
    return {"can_close": not blockers, "blockers": blockers, "warnings": warnings}

# ---- Deadlines ----

def set_deadlines(ticket: ServiceRequest) -> None:
    """Fill the first-response and case due dates if they are not set yet."""
    start = _aware(ticket.submitted_at) or utcnow()
    if ticket.first_response_due_at is None and ticket.first_response_at is None:
        ticket.first_response_due_at = start + timedelta(hours=config.CASE_FIRST_RESPONSE_HOURS)
    if ticket.due_at is None:
        hours = ticket.service_type.estimated_turnaround_hours if ticket.service_type else None
        ticket.due_at = start + (timedelta(hours=hours) if hours else timedelta(days=config.CASE_DEFAULT_TURNAROUND_DAYS))

def deadlines(ticket: ServiceRequest, now: datetime | None = None) -> dict:
    now = now or utcnow()
    closed = ticket.status in CLOSED_STATUSES
    due, first_due, first_at = _aware(ticket.due_at), _aware(ticket.first_response_due_at), _aware(ticket.first_response_at)
    return {
        "due_at": _iso(due),
        "overdue": bool(due and not closed and ticket.status != "on_hold" and now > due),
        "first_response_due_at": _iso(first_due),
        "first_response_at": _iso(first_at),
        "first_response_missed": bool(first_due and ((first_at and first_at > first_due) or (not first_at and not closed and now > first_due))),
    }

# Staff actions the customer sees, and so count as the first response.
FIRST_RESPONSE_EVENTS = ("status_changed", "message_sent", "assigned", "meeting_scheduled", "report_issued")

def note_event(ticket: ServiceRequest, event_type: str, actor: User | None) -> None:
    """Called for every ticket event (tickets.add_event): first response, deadlines and playbook tasks."""
    if actor is not None and ticket.first_response_at is None and event_type in FIRST_RESPONSE_EVENTS:
        ticket.first_response_at = utcnow()
    set_deadlines(ticket)
    sync(ticket)

# ---- Playbook ----

# key: (title, created when, due after, done when)
PLAYBOOK = {
    "confirm-scope": ("Call the customer to confirm scope and fee", lambda t, m: True, None, lambda t, m: m["scoped"]),
    "issue-report": ("Issue the preliminary report and document checklist", lambda t, m: m["assigned"] and needs_documents(t), timedelta(days=2),
                     lambda t, m: bool(t.report and t.report.status != "draft")),
    "chase-documents": ("Chase pending documents and government records", lambda t, m: bool(t.report and t.report.status != "draft"), timedelta(days=5),
                        lambda t, m: m["documents"]),
    "sign-report": ("Print, sign and upload the final report", lambda t, m: bool(t.report and t.report.status in ("final_generated", "signed")), timedelta(days=2),
                    lambda t, m: m["signed"]),
}

def sync(ticket: ServiceRequest) -> None:
    """Add playbook tasks the case has reached, tick off those whose work is done, and keep open ones with the owner."""
    if ticket.status in CLOSED_STATUSES:
        return
    state = milestone_state(ticket)
    owner = ticket.active_assignment.agent_user_id if ticket.active_assignment else None
    have = {t.playbook_key: t for t in ticket.tasks if t.source == "playbook"}
    now = utcnow()
    for key, (title, reached, due_after, finished) in PLAYBOOK.items():
        task = have.get(key)
        if task is None:
            if not reached(ticket, state) or finished(ticket, state):
                continue
            due = ticket.first_response_due_at if key == "confirm-scope" else now + due_after
            task = CaseTask(service_request_id=ticket.id, title=title, source="playbook", playbook_key=key, due_at=due, assignee_user_id=owner, status="open")
            ticket.tasks.append(task)
            continue
        if task.status == "open":
            if finished(ticket, state):
                task.status, task.completed_at = "done", now
            elif owner and task.assignee_user_id != owner:
                task.assignee_user_id = owner

def close_out(ticket: ServiceRequest, outcome: str | None, summary: str | None) -> list[str]:
    """Record how the case ended and cancel open tasks. Returns the cancelled task titles."""
    now = utcnow()
    ticket.closed_at = now
    ticket.closure_outcome = outcome or ("delivered" if ticket.status == "completed" else "withdrawn" if ticket.status == "cancelled" else "not_viable")
    ticket.closure_summary = summary
    cancelled = []
    for task in ticket.tasks:
        if task.status == "open":
            task.status, task.completed_at = "cancelled", now
            cancelled.append(task.title)
    return cancelled

def reopen(ticket: ServiceRequest) -> None:
    ticket.closed_at = None
    ticket.closure_outcome = None
    ticket.closure_summary = None

# ---- Team ----

def active_members(ticket: ServiceRequest) -> list[CaseMember]:
    return [m for m in ticket.members if m.removed_at is None]

# ---- Views ----

def _ref(user: User | None) -> dict | None:
    return {"id": str(user.id), "name": user.display_name} if user else None

def task_view(task: CaseTask, now: datetime | None = None, *, with_case: bool = False) -> dict:
    now = now or utcnow()
    due = _aware(task.due_at)
    view = {
        "id": str(task.id), "title": task.title, "notes": task.notes, "status": task.status, "source": task.source,
        "playbook_key": task.playbook_key, "assignee": _ref(task.assignee), "due_at": _iso(due),
        "overdue": bool(due and task.status == "open" and now > due), "created_at": _iso(task.created_at), "completed_at": _iso(task.completed_at),
    }
    if with_case:
        t = task.service_request
        view["case"] = {"ticket_number": t.ticket_number, "service_name": t.service_type.name, "customer_name": (t.structured_answers or {}).get("customer_name") or t.customer.full_name,
                        "status": t.status, "priority": t.priority}
    return view

def fee_view(ticket: ServiceRequest, *, staff: bool) -> dict:
    view = {
        "status": ticket.fee_status,
        "status_label": FEE_LABELS[ticket.fee_status],
        "quote": (ticket.fee_quote_paise or 0) // 100 if ticket.fee_quote_paise else None,
        "paid": (ticket.fee_paid_paise or 0) // 100 if ticket.fee_paid_paise else None,
        "paid_at": _iso(ticket.fee_paid_at),
    }
    if staff:
        view |= {"reference": ticket.fee_reference, "note": ticket.fee_note}
    return view

def staff_case_view(ticket: ServiceRequest) -> dict:
    now = utcnow()
    owner = ticket.active_assignment
    open_tasks = [t for t in ticket.tasks if t.status == "open"]
    return {
        "milestones": milestones(ticket),
        "current_milestone": current_milestone(ticket),
        "deadlines": deadlines(ticket, now),
        "owner": _ref(owner.agent) if owner else None,
        "team": [{"user": _ref(m.user), "role": m.role, "role_label": MEMBER_ROLE_LABELS[m.role], "added_at": _iso(m.added_at)} for m in active_members(ticket)],
        "tasks": [task_view(t, now) for t in sorted(ticket.tasks, key=lambda t: (t.status != "open", _aware(t.due_at) or now + timedelta(days=3650)))],
        "open_tasks": len(open_tasks),
        "overdue_tasks": sum(1 for t in open_tasks if t.due_at and _aware(t.due_at) < now),
        "fee": fee_view(ticket, staff=True),
        "closure": closure_check(ticket) if ticket.status not in CLOSED_STATUSES else None,
        "closed": {
            "outcome": ticket.closure_outcome, "outcome_label": OUTCOME_LABELS.get(ticket.closure_outcome or "", None),
            "summary": ticket.closure_summary, "at": _iso(ticket.closed_at),
        } if ticket.status in CLOSED_STATUSES else None,
        "allowed_statuses": allowed_statuses(ticket),
        "outcomes": [{"value": k, "label": v} for k, v in OUTCOME_LABELS.items()],
    }

def _customer_next_step(ticket: ServiceRequest) -> str | None:
    if ticket.status in CLOSED_STATUSES:
        return None
    if ticket.status == "waiting_for_customer":
        request = document_requirements.view(ticket)
        missing = [i for i in request["items"] if i["fetch_by"] == "customer" and i["status"] in ("pending", "rejected")]
        return request["prompt"] if missing else "Please reply to the case team's latest message."
    if ticket.fee_status == "quoted":
        return f"Pay the fee of ₹{(ticket.fee_quote_paise or 0) // 100:,} to the case team. They will share payment details."
    report = ticket.report
    if report and report.status == "signed":
        return "Your signed report is ready to download."
    return None

def customer_progress(ticket: ServiceRequest) -> dict:
    """The six steps, the next thing the customer must do, the due date and the fee. No internal tasks or team details."""
    closed = ticket.status in CLOSED_STATUSES
    return {
        "milestones": milestones(ticket),
        "next_step": _customer_next_step(ticket),
        "due_at": _iso(ticket.due_at) if not closed else None,
        "fee": fee_view(ticket, staff=False) if ticket.fee_status != "none" else None,
        "closed": {"outcome_label": OUTCOME_LABELS.get(ticket.closure_outcome or "", None), "summary": ticket.closure_summary, "at": _iso(ticket.closed_at)} if closed else None,
    }

def board_card(ticket: ServiceRequest, now: datetime) -> dict:
    from .tickets import staff_summary
    open_tasks = [t for t in ticket.tasks if t.status == "open"]
    return {
        **staff_summary(ticket),
        "milestone": current_milestone(ticket),
        "deadlines": deadlines(ticket, now),
        "open_tasks": len(open_tasks),
        "overdue_tasks": sum(1 for t in open_tasks if t.due_at and _aware(t.due_at) < now),
        "fee_status": ticket.fee_status,
        "team": [m.user.display_name for m in active_members(ticket)],
    }
