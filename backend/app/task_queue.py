"""Staff task triage scoped to current case access, before filtering or pagination."""
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .admin import _visible_tickets
from .db import get_db
from .models import CLOSED_STATUSES, CaseTask, Customer, ServiceRequest, ServiceType, User, utcnow
from .security import current_staff
from .tickets import aware, staff_status_label

router = APIRouter(prefix="/api/v1/admin/task-queue")


def visible_case_ids(user):
    return _visible_tickets(user).with_only_columns(ServiceRequest.id)


@router.get("")
def queue(assignee: str = Query("me", max_length=36),
    status: Literal["open", "done", "cancelled", "all"] = "open",
    due: Literal["all", "overdue", "today", "week", "unscheduled"] = "all",
    priority: Literal["all", "urgent", "high", "normal", "low"] = "all",
    q: str = Query("", max_length=100, pattern=r"^[^\x00-\x1f\x7f]*$"),
    page: int = Query(1, ge=1, le=10000), page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(current_staff), db: Session = Depends(get_db)):
    if not user.is_admin and assignee != "me":
        raise HTTPException(403, "Agents can review only their own task queue.")
    now = utcnow()
    india = ZoneInfo("Asia/Kolkata")
    today = datetime.combine(now.astimezone(india).date(), time.min, india).astimezone(timezone.utc)
    tomorrow = today + timedelta(days=1)
    conditions = [ServiceRequest.id.in_(visible_case_ids(user)), ServiceRequest.status.not_in(CLOSED_STATUSES)]
    if assignee == "me": conditions.append(CaseTask.assignee_user_id == user.id)
    elif assignee == "unassigned": conditions.append(CaseTask.assignee_user_id.is_(None))
    elif assignee != "all":
        try: selected = uuid.UUID(assignee)
        except ValueError: raise HTTPException(422, "Choose me, all, unassigned or a staff UUID.")
        conditions.append(CaseTask.assignee_user_id == selected)
    if status != "all": conditions.append(CaseTask.status == status)
    overdue = (CaseTask.status == "open") & (CaseTask.due_at < now)
    due_today = (CaseTask.due_at >= today) & (CaseTask.due_at < tomorrow)
    if due == "overdue": conditions.append(overdue)
    elif due == "today": conditions.append(due_today)
    elif due == "week": conditions.extend((CaseTask.due_at >= now, CaseTask.due_at < now+timedelta(days=7)))
    elif due == "unscheduled": conditions.append(CaseTask.due_at.is_(None))
    if priority != "all": conditions.append(ServiceRequest.priority == priority)
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(or_(CaseTask.title.ilike(f"%{escaped}%", escape="\\"), ServiceRequest.ticket_number.ilike(f"%{escaped}%", escape="\\")))
    # Aggregate the same access scope and filters as the page. Counts never
    # include an inaccessible case, even if its task is still assigned to you.
    counts = db.execute(select(func.count().label("total"),
        func.sum(case((CaseTask.status == "open", 1), else_=0)).label("open"),
        func.sum(case((overdue, 1), else_=0)).label("overdue"),
        func.sum(case(((CaseTask.status == "open") & due_today, 1), else_=0)).label("today"),
        func.sum(case(((CaseTask.status == "open") & CaseTask.due_at.is_(None), 1), else_=0)).label("unscheduled"))
        .select_from(CaseTask).join(ServiceRequest, CaseTask.service_request_id == ServiceRequest.id).where(*conditions)).one()
    # Queue rows omit notes, messages, contacts and the case's structured answers.
    query = select(CaseTask.id, CaseTask.title, CaseTask.status, CaseTask.source, CaseTask.due_at,
        CaseTask.assignee_user_id, User.display_name, ServiceRequest.ticket_number,
        ServiceRequest.status.label("case_status"), ServiceRequest.priority, ServiceType.name.label("service_name"),
        Customer.full_name.label("customer_name")).join(ServiceRequest, CaseTask.service_request_id == ServiceRequest.id)
    query = query.join(Customer, ServiceRequest.customer_id == Customer.id).join(ServiceType, ServiceRequest.service_type_id == ServiceType.id)
    query = query.outerjoin(User, CaseTask.assignee_user_id == User.id).where(*conditions)
    urgency = case({"urgent": 0, "high": 1, "normal": 2, "low": 3}, value=ServiceRequest.priority, else_=4)
    rows = db.execute(query.order_by(case((CaseTask.status == "open", 0), else_=1),
        CaseTask.due_at.is_(None), CaseTask.due_at, urgency, CaseTask.id).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [{"id": str(row.id), "title": row.title, "status": row.status, "source": row.source,
        "due_at": aware(row.due_at).isoformat() if row.due_at else None,
        "overdue": bool(row.status == "open" and row.due_at and aware(row.due_at) < now),
        "assignee": {"id": str(row.assignee_user_id), "name": row.display_name} if row.assignee_user_id and row.display_name else None,
        "case": {"ticket_number": row.ticket_number, "status": row.case_status, "status_label": staff_status_label(row.case_status), "priority": row.priority,
            "service_name": row.service_name, "customer_name": row.customer_name}} for row in rows],
        "total": counts.total, "page": page, "page_size": page_size, "checked_at": now.isoformat(),
        "summary": {"open": int(counts.open or 0), "overdue": int(counts.overdue or 0),
            "due_today": int(counts.today or 0), "unscheduled": int(counts.unscheduled or 0)}}
