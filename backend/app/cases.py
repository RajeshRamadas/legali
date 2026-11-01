"""Staff case endpoints: tasks, case team, case fee, the case board and My tasks. See case_management.py."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import case_management, tickets
from .admin import _detail, _get_ticket, _visible_tickets
from .db import get_db
from .models import CASE_MEMBER_ROLES, CLOSED_STATUSES, CaseMember, CaseTask, ServiceRequest, User, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1")

class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    assignee_id: uuid.UUID | None = Field(default=None, description="Defaults to the case owner, else you.")
    due_at: datetime | None = None

class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: Literal["open", "done", "cancelled"] | None = None

class MemberAdd(BaseModel):
    user_id: uuid.UUID
    role: Literal[CASE_MEMBER_ROLES]  # type: ignore[valid-type]

class FeeUpdate(BaseModel):
    action: Literal["quote", "paid", "waive", "clear"]
    amount: int | None = Field(default=None, ge=1, le=10_000_000, description="Rupees. Required to quote; the amount received when marking paid.")
    reference: str | None = Field(default=None, max_length=200, description="UPI, bank or receipt reference for a payment.")
    note: str | None = Field(default=None, max_length=500, description="Required to waive.")

def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def _staff(db: Session, user_id: uuid.UUID) -> User:
    member = db.get(User, user_id)
    if member is None or member.account_status != "active" or not (member.role_names & {"agent", "admin", "super_admin"}):
        raise HTTPException(status_code=422, detail="Choose an active staff member.")
    return member

def _open_case(ticket: ServiceRequest) -> None:
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="This case is closed. Reopen it first.")

def _can_manage_team(user: User, ticket: ServiceRequest) -> bool:
    owner = ticket.active_assignment
    return user.is_admin or bool(owner and owner.agent_user_id == user.id)

# ---- Tasks ----

@router.post("/admin/tickets/{ticket_number}/tasks", status_code=201)
def add_task(ticket_number: str, payload: TaskCreate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    _open_case(ticket)
    owner = ticket.active_assignment
    assignee = _staff(db, payload.assignee_id) if payload.assignee_id else (owner.agent if owner else user)
    task = CaseTask(service_request_id=ticket.id, title=payload.title.strip(), notes=(payload.notes or "").strip() or None, assignee_user_id=assignee.id,
                    due_at=_aware(payload.due_at), created_by_user_id=user.id, source="manual", status="open")
    ticket.tasks.append(task)
    tickets.add_event(db, ticket, "task_added", user, new={"title": task.title, "assignee": assignee.display_name})
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.patch("/admin/tickets/{ticket_number}/tasks/{task_id}")
def update_task(ticket_number: str, task_id: uuid.UUID, payload: TaskUpdate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    task = next((t for t in ticket.tasks if t.id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _open_case(ticket)
    fields = payload.model_fields_set
    if "title" in fields and payload.title:
        task.title = payload.title.strip()
    if "notes" in fields:
        task.notes = (payload.notes or "").strip() or None
    if "due_at" in fields:
        task.due_at = _aware(payload.due_at)
    if "assignee_id" in fields:
        task.assignee_user_id = _staff(db, payload.assignee_id).id if payload.assignee_id else None
    if payload.status and payload.status != task.status:
        old = task.status
        task.status = payload.status
        task.completed_at = utcnow() if payload.status != "open" else None
        task.completed_by_user_id = user.id if payload.status != "open" else None
        kind = {"done": "task_done", "cancelled": "task_cancelled", "open": "task_reopened"}[payload.status]
        tickets.add_event(db, ticket, kind, user, old={"status": old}, new={"title": task.title})
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.get("/admin/tasks")
def my_tasks(
    assignee: str = Query("me", description="'me', 'all' (admins) or a staff id (admins)."),
    include_done: bool = False,
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    """Open tasks across cases, overdue first, then by due date."""
    query = select(CaseTask).join(ServiceRequest, CaseTask.service_request_id == ServiceRequest.id).where(ServiceRequest.status.not_in(CLOSED_STATUSES))
    if not include_done:
        query = query.where(CaseTask.status == "open")
    if assignee == "me" or not user.is_admin:
        query = query.where(CaseTask.assignee_user_id == user.id)
    elif assignee != "all":
        try:
            query = query.where(CaseTask.assignee_user_id == uuid.UUID(assignee))
        except ValueError:
            raise HTTPException(status_code=422, detail="assignee must be 'me', 'all' or a staff id")
    rows = db.scalars(query.order_by(CaseTask.due_at.is_(None), CaseTask.due_at, CaseTask.created_at).limit(200)).unique().all()
    now = utcnow()
    items = [case_management.task_view(t, now, with_case=True) for t in rows]
    items.sort(key=lambda t: not t["overdue"])
    return {"items": items}

# ---- Case team ----

@router.post("/admin/tickets/{ticket_number}/members", status_code=201)
def add_member(ticket_number: str, payload: MemberAdd, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    if not _can_manage_team(user, ticket):
        raise HTTPException(status_code=403, detail="Only an admin or the case owner can change the case team.")
    member = _staff(db, payload.user_id)
    owner = ticket.active_assignment
    if owner and owner.agent_user_id == member.id:
        raise HTTPException(status_code=409, detail=f"{member.display_name} already owns this case.")
    current = next((m for m in case_management.active_members(ticket) if m.user_id == member.id), None)
    if current:
        if current.role == payload.role:
            return _detail(db, ticket)
        current.removed_at = utcnow()
    row = CaseMember(service_request_id=ticket.id, user_id=member.id, role=payload.role, added_by_user_id=user.id)
    db.add(row)
    ticket.members.append(row)
    db.flush()
    db.refresh(row)
    tickets.add_event(db, ticket, "member_added", user, new={"name": member.display_name, "role": payload.role})
    tickets.audit(db, user, "case.member_added", ticket.id, user_id=str(member.id), role=payload.role)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.delete("/admin/tickets/{ticket_number}/members/{user_id}")
def remove_member(ticket_number: str, user_id: uuid.UUID, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    if not _can_manage_team(user, ticket):
        raise HTTPException(status_code=403, detail="Only an admin or the case owner can change the case team.")
    current = next((m for m in case_management.active_members(ticket) if m.user_id == user_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Not on the case team")
    current.removed_at = utcnow()
    tickets.add_event(db, ticket, "member_removed", user, old={"name": current.user.display_name, "role": current.role})
    tickets.audit(db, user, "case.member_removed", ticket.id, user_id=str(user_id))
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

# ---- Fee ----

@router.put("/admin/tickets/{ticket_number}/fee")
def set_fee(ticket_number: str, payload: FeeUpdate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Quote the case fee, record it paid (offline: UPI, bank, cash), waive it, or clear a quote."""
    ticket = _get_ticket(db, user, ticket_number)
    _open_case(ticket)
    note = (payload.note or "").strip() or None
    old = ticket.fee_status
    if payload.action == "quote":
        if not payload.amount:
            raise HTTPException(status_code=422, detail="amount: Enter the fee in rupees.")
        if old == "paid":
            raise HTTPException(status_code=409, detail="The fee is already paid.")
        ticket.fee_status, ticket.fee_quote_paise, ticket.fee_note = "quoted", payload.amount * 100, note
        tickets.add_event(db, ticket, "fee_quoted", user, new={"amount": payload.amount}, reason=note)
        tickets.queue_notifications(db, ticket, "fee_quoted", f"Homexo Legal: the fee for {ticket.ticket_number} is ₹{payload.amount:,}. Your case team will share how to pay.")
    elif payload.action == "paid":
        amount = payload.amount or ((ticket.fee_quote_paise or 0) // 100)
        if not amount:
            raise HTTPException(status_code=422, detail="amount: Enter the amount received.")
        if not (payload.reference or "").strip():
            raise HTTPException(status_code=422, detail="reference: Add the UPI, bank or receipt reference.")
        ticket.fee_status, ticket.fee_paid_paise, ticket.fee_paid_at = "paid", amount * 100, utcnow()
        ticket.fee_quote_paise = ticket.fee_quote_paise or amount * 100
        ticket.fee_reference = payload.reference.strip()
        if note:
            ticket.fee_note = note
        tickets.add_event(db, ticket, "fee_paid", user, new={"amount": amount, "reference": ticket.fee_reference})
        tickets.queue_notifications(db, ticket, "fee_paid", f"Homexo Legal: we received ₹{amount:,} for {ticket.ticket_number}. Thank you.")
    elif payload.action == "waive":
        if not note:
            raise HTTPException(status_code=422, detail="note: Say why the fee is waived.")
        ticket.fee_status, ticket.fee_note = "waived", note
        tickets.add_event(db, ticket, "fee_waived", user, reason=note)
    else:
        if old == "paid":
            raise HTTPException(status_code=409, detail="A paid fee can't be cleared.")
        ticket.fee_status, ticket.fee_quote_paise, ticket.fee_note = "none", None, None
        tickets.add_event(db, ticket, "fee_cleared", user)
    tickets.audit(db, user, f"case.fee_{payload.action}", ticket.id, amount=payload.amount, old=old)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

# ---- Board ----

@router.get("/admin/cases/board")
def board(
    assignee: str | None = Query(None, description="'me', 'unassigned' or a staff id."),
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    """Open cases grouped by their current milestone, with deadline and task markers and headline counts."""
    query = _visible_tickets(user).where(ServiceRequest.status.not_in(CLOSED_STATUSES))
    rows = db.scalars(query.order_by(ServiceRequest.due_at.is_(None), ServiceRequest.due_at).limit(500)).unique().all()
    if assignee == "me":
        rows = [t for t in rows if t.active_assignment and t.active_assignment.agent_user_id == user.id]
    elif assignee == "unassigned":
        rows = [t for t in rows if t.active_assignment is None]
    elif assignee:
        rows = [t for t in rows if t.active_assignment and str(t.active_assignment.agent_user_id) == assignee]
    now = utcnow()
    cards = [case_management.board_card(t, now) for t in rows]
    # Urgent first, then late, then by due date (already ordered by the query).
    cards.sort(key=lambda c: (c["priority"] != "urgent", not c["deadlines"]["overdue"]))
    columns = [{"key": key, "label": label, "cards": [c for c in cards if c["milestone"] == key]} for key, label in case_management.BOARD_COLUMNS]
    week = now + timedelta(days=7)
    closed_30 = db.scalar(select(func.count()).select_from(
        _visible_tickets(user).where(ServiceRequest.status == "completed", or_(ServiceRequest.closed_at >= now - timedelta(days=30), ServiceRequest.completed_at >= now - timedelta(days=30))).subquery()
    ))
    return {
        "columns": columns,
        "counts": {
            "open": len(cards),
            "overdue": sum(1 for c in cards if c["deadlines"]["overdue"]),
            "due_this_week": sum(1 for c in cards if c["deadlines"]["due_at"] and not c["deadlines"]["overdue"] and datetime.fromisoformat(c["deadlines"]["due_at"]) <= week),
            "first_response_missed": sum(1 for c in cards if c["deadlines"]["first_response_missed"] and not c["deadlines"]["first_response_at"]),
            "overdue_tasks": sum(c["overdue_tasks"] for c in cards),
            "closed_30_days": closed_30,
        },
    }
