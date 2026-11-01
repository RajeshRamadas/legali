"""Staff endpoints: sign-in, ticket queue, ticket work (status, assignment, messages, notes), staff and reports.

Admins see every ticket. Agents see only tickets currently assigned to them.
"""
import uuid
from datetime import datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from . import case_management, config, google_calendar, tickets, whatsapp
from .db import get_db
from .models import (
    CLOSED_STATUSES, CLOSURE_OUTCOMES, PRIORITIES, STAFF_ROLES, TICKET_STATUSES, Assignment, CaseMember, Customer, LawyerProfile, Meeting, Notification, Property, Role, ServiceRequest, ServiceType, TicketMessage, User, utcnow,
)
from .security import create_access_token, current_staff, hash_password, require_admin, verify_password

router = APIRouter(prefix="/api/v1")

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

class TicketUpdate(BaseModel):
    status: Literal[TICKET_STATUSES] | None = None  # type: ignore[valid-type]
    priority: Literal[PRIORITIES] | None = None  # type: ignore[valid-type]
    note: str | None = Field(default=None, max_length=1000, description="Shown to the customer with the status change.")
    priority_note: str | None = Field(default=None, max_length=300, description="Staff only: why it's urgent. Sent to the assignee with the urgent alert.")
    outcome: Literal[CLOSURE_OUTCOMES] | None = Field(default=None, description="How the case ended, when closing it.")  # type: ignore[valid-type]
    closure_summary: str | None = Field(default=None, max_length=2000, description="Staff only: what was done, when closing.")
    override_reason: str | None = Field(default=None, max_length=500, description="Admins only: close as Completed despite closure check blockers.")
    due_at: datetime | None = Field(default=None, description="New case due date.")
    due_reason: str | None = Field(default=None, max_length=300, description="Why the due date moved. Required with due_at.")

class AssignmentRequest(BaseModel):
    agent_id: uuid.UUID | None = Field(description="Agent to assign, or null to unassign.")
    note: str | None = Field(default=None, max_length=1000)

class StaffMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    visibility: Literal["customer", "internal"]

class StaffCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    role: Literal[STAFF_ROLES]  # type: ignore[valid-type]
    phone: str | None = Field(default=None, max_length=20, description="WhatsApp number for meeting invites, reminders and the daily agenda.")

class AvailabilityUpdate(BaseModel):
    available: bool
    note: str | None = Field(default=None, max_length=120, description="e.g. 'Till 6 pm' or 'Only urgent matters'.")
    phone: str | None = Field(default=None, max_length=20, description="Set or change your own number. Seen by the team only.")

class StaffUpdate(BaseModel):
    account_status: Literal["active", "suspended"] | None = None
    role: Literal[STAFF_ROLES] | None = None  # type: ignore[valid-type]
    phone: str | None = Field(default=None, max_length=20, description="Empty string removes the number.")

def _me(user: User) -> dict:
    # Staff workspace only. Phone numbers of staff are never part of a customer-facing response or message.
    return {
        "id": str(user.id), "name": user.display_name, "email": user.email, "phone": user.phone, "role": "admin" if user.is_admin else "agent",
        "available_for_calls": user.available_for_calls, "availability_note": user.availability_note,
        "availability_updated_at": user.availability_updated_at.isoformat() if user.availability_updated_at else None,
    }

def _flag_urgent(db: Session, ticket: ServiceRequest, agent: User | None, actor: User, note: str | None) -> None:
    """Tell the assignee on WhatsApp that a ticket of theirs is urgent (they also see it under Urgent in the workspace)."""
    if agent is None or agent.id == actor.id or not agent.phone:
        return
    from .meetings import render  # meetings imports this module
    params = [agent.display_name, f"{ticket.title or ticket.service_type.name} ({ticket.ticket_number})", note or f"Flagged by {actor.display_name}.",
              f"{config.PUBLIC_SITE_URL}/admin/tickets/{ticket.ticket_number}"]
    db.add(Notification(service_request_id=ticket.id, user_id=agent.id, channel="whatsapp", template_key="urgent_task", recipient=agent.phone,
                        params=params, body=render("urgent_task", params), send_after=utcnow()))

def _staff_phone(db: Session, value: str, user_id: uuid.UUID | None = None) -> str | None:
    value = value.strip()
    if not value:
        return None
    if len(tickets.normalize_phone(value)) < 10:
        raise HTTPException(status_code=422, detail="Enter a full mobile number for WhatsApp.")
    taken = db.scalars(select(User).where(User.phone == value, *([User.id != user_id] if user_id else []))).first()
    if taken:
        raise HTTPException(status_code=409, detail=f"{taken.display_name} already uses this number.")
    return value

def _visible_tickets(user: User):
    query = select(ServiceRequest)
    if not user.is_admin:
        # An agent works tickets assigned to them, and opens those where they take a meeting.
        query = query.where(or_(
            exists().where(Assignment.service_request_id == ServiceRequest.id, Assignment.agent_user_id == user.id, Assignment.unassigned_at.is_(None)),
            exists().where(Meeting.service_request_id == ServiceRequest.id, Meeting.lawyer_user_id == user.id, Meeting.status != "cancelled"),
            # Case team members (associates, paralegals, reviewers) open the cases they help on.
            exists().where(CaseMember.service_request_id == ServiceRequest.id, CaseMember.user_id == user.id, CaseMember.removed_at.is_(None)),
        ))
    return query

def _needs_reply_clause():
    """Open tickets whose latest customer-visible message came from the customer."""
    later = aliased(TicketMessage)
    customer_msg = aliased(TicketMessage)
    return ServiceRequest.status.not_in(CLOSED_STATUSES) & exists().where(
        customer_msg.service_request_id == ServiceRequest.id,
        customer_msg.visibility == "customer",
        customer_msg.author_type == "customer",
        ~exists().where(
            later.service_request_id == ServiceRequest.id, later.visibility == "customer",
            later.author_type != "customer", later.created_at > customer_msg.created_at,
        ),
    )

def _get_ticket(db: Session, user: User, ticket_number: str) -> ServiceRequest:
    ticket = db.scalars(_visible_tickets(user).where(ServiceRequest.ticket_number == ticket_number.upper())).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

def _detail(db: Session, ticket: ServiceRequest) -> dict:
    notifications = db.scalars(select(Notification).where(Notification.service_request_id == ticket.id).order_by(Notification.created_at)).all()
    return tickets.staff_detail(ticket, list(notifications))

@router.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(func.lower(User.email) == payload.email.strip().lower())).first()
    if user is None or not verify_password(payload.password, user.password_hash) or user.account_status != "active" or not (user.role_names & {"agent", "admin", "super_admin"}):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    tickets.audit(db, user, "staff.login", None)
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": _me(user)}

@router.get("/auth/me")
def me(user: User = Depends(current_staff)):
    return _me(user)

@router.get("/admin/tickets")
def list_tickets(
    status: str | None = Query(None, description="A status, a comma-separated list, or 'open' / 'closed'."),
    service: str | None = None,
    assignee: str | None = Query(None, description="'me', 'unassigned' or an agent id."),
    q: str | None = Query(None, max_length=100),
    needs_reply: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    query = _visible_tickets(user)
    if status == "open":
        query = query.where(ServiceRequest.status.not_in(CLOSED_STATUSES))
    elif status == "closed":
        query = query.where(ServiceRequest.status.in_(CLOSED_STATUSES))
    elif status:
        query = query.where(ServiceRequest.status.in_(status.split(",")))
    if service:
        query = query.where(ServiceRequest.service_type.has(ServiceType.slug == service))
    active = (Assignment.service_request_id == ServiceRequest.id) & Assignment.unassigned_at.is_(None)
    if assignee == "unassigned":
        query = query.where(~exists().where(active))
    elif assignee:
        try:
            agent_id = user.id if assignee == "me" else uuid.UUID(assignee)
        except ValueError:
            raise HTTPException(status_code=422, detail="assignee must be 'me', 'unassigned' or an agent id")
        query = query.where(exists().where(active, Assignment.agent_user_id == agent_id))
    if needs_reply:
        query = query.where(_needs_reply_clause())
    if q:
        term = f"%{q.strip().lower()}%"
        digits = tickets.normalize_phone(q)
        conditions = [
            func.lower(ServiceRequest.ticket_number).like(term),
            ServiceRequest.customer.has(func.lower(Customer.full_name).like(term)),
            ServiceRequest.prop.has(func.lower(Property.locality).like(term)),
        ]
        if len(digits) >= 4:
            conditions.append(ServiceRequest.customer.has(Customer.phone_normalized.like(f"%{digits}%")))
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ServiceRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": [tickets.staff_summary(t) for t in rows], "total": total, "page": page, "page_size": page_size}

@router.get("/admin/tickets/{ticket_number}")
def get_ticket(ticket_number: str, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    return _detail(db, _get_ticket(db, user, ticket_number))

@router.patch("/admin/tickets/{ticket_number}")
def update_ticket(ticket_number: str, payload: TicketUpdate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    if payload.status and payload.status != ticket.status:
        _move(db, ticket, payload, user)
    if payload.due_at is not None:
        reason = (payload.due_reason or "").strip()
        if not reason:
            raise HTTPException(status_code=422, detail="due_reason: Say why the due date is moving.")
        due = payload.due_at if payload.due_at.tzinfo else payload.due_at.replace(tzinfo=timezone.utc)
        old_due = tickets.aware(ticket.due_at).isoformat() if ticket.due_at else None
        ticket.due_at = due
        tickets.add_event(db, ticket, "due_date_changed", user, old={"due_at": old_due}, new={"due_at": due.isoformat()}, reason=reason)
        tickets.audit(db, user, "case.due_changed", ticket.id, due_at=due.isoformat())
    if payload.priority and payload.priority != ticket.priority:
        note = (payload.priority_note or "").strip() or None
        tickets.add_event(db, ticket, "priority_changed", user, old={"priority": ticket.priority}, new={"priority": payload.priority}, reason=note)
        ticket.priority = payload.priority
        if payload.priority == "urgent":
            assignment = ticket.active_assignment
            _flag_urgent(db, ticket, assignment.agent if assignment else None, user, note)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

def _move(db: Session, ticket: ServiceRequest, payload: TicketUpdate, user: User) -> None:
    """A staff status change: only allowed moves, closure checks before Completed, a reason to reopen."""
    old, new = ticket.status, payload.status
    note = (payload.note or "").strip() or None
    if new not in case_management.allowed_statuses(ticket):
        hint = "A closed case can only be reopened." if old in CLOSED_STATUSES else f"From {tickets.staff_status_label(old)} you can't move to {tickets.staff_status_label(new)}."
        raise HTTPException(status_code=409, detail=hint)
    if new == "reopened" and not note:
        raise HTTPException(status_code=422, detail="note: Say why the case is being reopened.")
    override = (payload.override_reason or "").strip() or None
    if new == "completed":
        check = case_management.closure_check(ticket)
        if not check["can_close"]:
            if not override:
                raise HTTPException(status_code=409, detail="Can't close yet: " + " ".join(check["blockers"]))
            if not user.is_admin:
                raise HTTPException(status_code=403, detail="Only an admin can close a case despite the closure checks.")
    tickets.change_status(db, ticket, new, user, note)
    if new in CLOSED_STATUSES:
        cancelled = case_management.close_out(ticket, payload.outcome, (payload.closure_summary or "").strip() or None)
        tickets.add_event(db, ticket, "case_closed", user, new={"outcome": ticket.closure_outcome, "cancelled_tasks": len(cancelled), "override": bool(override and new == "completed")},
                          reason=override if new == "completed" and override else ticket.closure_summary)
    elif old in CLOSED_STATUSES:
        case_management.reopen(ticket)
        case_management.sync(ticket)
    tickets.audit(db, user, "ticket.status_changed", ticket.id, old=old, new=new, **({"override": override} if override and new == "completed" else {}))

@router.post("/admin/tickets/{ticket_number}/assignment")
def assign_ticket(ticket_number: str, payload: AssignmentRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, admin, ticket_number)
    current = ticket.active_assignment
    if payload.agent_id is not None:
        agent = db.get(User, payload.agent_id)
        if agent is None or agent.account_status != "active" or not (agent.role_names & {"agent", "admin"}):
            raise HTTPException(status_code=422, detail="Choose an active staff member.")
        if current and current.agent_user_id == agent.id:
            return _detail(db, ticket)
    if current:
        current.unassigned_at = utcnow()
    if payload.agent_id is None:
        tickets.add_event(db, ticket, "unassigned", admin, old={"agent": current.agent.display_name} if current else None, reason=payload.note)
    else:
        assignment = Assignment(service_request_id=ticket.id, agent_user_id=agent.id, assigned_by_user_id=admin.id, assignment_note=payload.note)
        db.add(assignment)
        ticket.assignments.append(assignment)
        tickets.add_event(db, ticket, "assigned", admin, old={"agent": current.agent.display_name} if current else None, new={"agent": agent.display_name}, reason=payload.note)
        if ticket.priority == "urgent":
            _flag_urgent(db, ticket, agent, admin, _urgent_flag(ticket)["urgent_note"])
        # New requests move along once someone owns them.
        if ticket.status in ("submitted", "under_review", "approved_for_processing"):
            tickets.change_status(db, ticket, "assigned", admin, None)
    tickets.audit(db, admin, "ticket.assigned", ticket.id, agent_id=str(payload.agent_id) if payload.agent_id else None)
    ticket.updated_at = utcnow()
    db.commit()
    db.refresh(ticket)
    return _detail(db, ticket)

@router.post("/admin/tickets/{ticket_number}/messages", status_code=201)
def post_message(ticket_number: str, payload: StaffMessage, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    tickets.add_message(db, ticket, payload.message.strip(), author_type="staff", visibility=payload.visibility, author=user)
    db.commit()
    return _detail(db, ticket)

def _urgent_flag(ticket: ServiceRequest) -> dict:
    """Who marked the ticket urgent, when and why (the latest time), for the Urgent list and the WhatsApp alert."""
    flagged = [e for e in ticket.events if e.event_type == "priority_changed" and (e.new_value or {}).get("priority") == "urgent"]
    last = flagged[-1] if flagged else None
    return {
        "urgent_note": last.reason if last else None,
        "flagged_by": last.actor.display_name if last and last.actor else None,
        "flagged_at": tickets.aware(last.created_at).isoformat() if last else tickets.aware(ticket.created_at).isoformat(),
    }

@router.get("/admin/urgent")
def urgent_tickets(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Open urgent tickets: an agent's own, or every one for admins. Shown at the top of the queue."""
    rows = db.scalars(
        _visible_tickets(user).where(ServiceRequest.priority == "urgent", ServiceRequest.status.not_in(CLOSED_STATUSES)).order_by(ServiceRequest.updated_at.desc()).limit(50)
    ).unique().all()
    return {"items": [tickets.staff_summary(t) | _urgent_flag(t) for t in rows]}

@router.put("/admin/me/availability")
def set_availability(payload: AvailabilityUpdate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """A staff member says whether the team can call them now. Only the team sees this and the number."""
    if payload.phone is not None:
        user.phone = _staff_phone(db, payload.phone, user.id)
    if payload.available and not user.phone:
        raise HTTPException(status_code=422, detail="phone: Add your mobile number so the team can call you.")
    user.available_for_calls = payload.available
    user.availability_note = (payload.note or "").strip() or None
    user.availability_updated_at = utcnow()
    tickets.audit(db, user, "staff.availability", None, available=payload.available)
    db.commit()
    return _me(user)

@router.get("/admin/team")
def team(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Who on the team can take a call now, with their numbers. Staff only."""
    staff = db.scalars(select(User).where(User.account_status == "active", User.roles.any(Role.name.in_(("agent", "admin", "super_admin"))))).all()
    listed = set(db.scalars(select(LawyerProfile.user_id).where(LawyerProfile.is_listed.is_(True))).all())
    items = [_me(u) | {"lawyer": u.id in listed} for u in staff]
    items.sort(key=lambda m: (not m["available_for_calls"], m["name"]))
    return {"items": items}

@router.get("/admin/reports/summary")
def summary(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    visible = _visible_tickets(user).subquery()
    by_status = dict(db.execute(select(visible.c.status, func.count()).group_by(visible.c.status)).all())
    open_count = sum(n for s, n in by_status.items() if s not in CLOSED_STATUSES)
    today = datetime.combine(utcnow().date(), time.min, tzinfo=timezone.utc)
    new_today = db.scalar(select(func.count()).select_from(visible).where(visible.c.created_at >= today))
    active = (Assignment.service_request_id == visible.c.id) & Assignment.unassigned_at.is_(None)
    unassigned = db.scalar(select(func.count()).select_from(visible).where(visible.c.status.not_in(CLOSED_STATUSES), ~exists().where(active)))
    needs_reply = db.scalar(select(func.count()).select_from(_visible_tickets(user).where(_needs_reply_clause()).subquery()))
    urgent = db.scalar(select(func.count()).select_from(visible).where(visible.c.priority == "urgent", visible.c.status.not_in(CLOSED_STATUSES)))
    return {
        "open": open_count,
        "new_today": new_today,
        "unassigned": unassigned,
        "needs_reply": needs_reply,
        "urgent": urgent,
        "by_status": [{"status": s, "label": tickets.staff_status_label(s), "count": by_status.get(s, 0)} for s in TICKET_STATUSES if by_status.get(s)],
    }

@router.get("/admin/meta")
def meta(user: User = Depends(current_staff)):
    """Status and priority options for the staff workspace."""
    return {
        "statuses": [{"value": s, "label": tickets.staff_status_label(s)} for s in TICKET_STATUSES if s != "draft"],
        "priorities": list(PRIORITIES),
        "meetings": {
            "google_calendar": google_calendar.enabled(), "whatsapp": whatsapp.enabled(),
            "timezone": config.MEETING_TIMEZONE, "reminder_minutes": config.MEETING_REMINDER_MINUTES,
        },
    }

@router.get("/admin/staff")
def list_staff(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    if not user.is_admin:
        return {"items": [_me(user) | {"account_status": user.account_status}]}
    staff = db.scalars(select(User).where(User.roles.any(Role.name.in_(("agent", "admin", "super_admin")))).order_by(User.display_name)).all()
    return {"items": [_me(u) | {"account_status": u.account_status} for u in staff]}

def _role(db: Session, name: str) -> Role:
    role = db.scalars(select(Role).where(Role.name == name)).first()
    if role is None:
        role = Role(name=name)
        db.add(role)
    return role

@router.post("/admin/staff", status_code=201)
def create_staff(payload: StaffCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalars(select(User).where(func.lower(User.email) == email)).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    phone = _staff_phone(db, payload.phone) if payload.phone else None
    user = User(display_name=payload.display_name.strip(), email=email, phone=phone, password_hash=hash_password(payload.password), roles=[_role(db, payload.role)])
    db.add(user)
    db.flush()
    tickets.audit(db, admin, "staff.created", None, user_id=str(user.id), role=payload.role)
    db.commit()
    return _me(user) | {"account_status": user.account_status}

@router.patch("/admin/staff/{user_id}")
def update_staff(user_id: uuid.UUID, payload: StaffUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if user.id == admin.id and (payload.account_status == "suspended" or payload.role == "agent"):
        raise HTTPException(status_code=422, detail="You can't remove your own admin access.")
    if payload.account_status:
        user.account_status = payload.account_status
    if payload.role:
        user.roles = [r for r in user.roles if r.name not in STAFF_ROLES] + [_role(db, payload.role)]
    if payload.phone is not None:
        user.phone = _staff_phone(db, payload.phone, user.id)
    tickets.audit(db, admin, "staff.updated", None, user_id=str(user.id), **payload.model_dump(exclude_none=True))
    db.commit()
    return _me(user) | {"account_status": user.account_status}
