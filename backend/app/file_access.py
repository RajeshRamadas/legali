"""Append-only authorization records for private file responses and safe admin review."""
import uuid
from datetime import date, datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select

from .activity import cursor_for, cursor_value
from .db import get_db
from .models import AuditLog, CustomerAccount, ServiceRequest, User, utcnow
from .security import require_admin
from .session_metadata import aware

router = APIRouter(prefix="/api/v1/admin/file-access")
ACTIONS = {
    "file.customer_document_authorized": ("customer", "document"),
    "file.staff_document_authorized": ("staff", "document"),
    "file.customer_preliminary_authorized": ("customer", "preliminary_report"),
    "file.staff_preliminary_authorized": ("staff", "preliminary_report"),
}


def record_authorized(db, reader, ticket, file_id, *, preliminary=False):
    customer = isinstance(reader, CustomerAccount)
    kind = "preliminary" if preliminary else "document"
    metadata = {"file_id": str(file_id)}
    if customer:
        metadata["customer_account_id"] = str(reader.id)
    db.add(AuditLog(actor_user_id=None if customer else reader.id,
        action=f"file.{'customer' if customer else 'staff'}_{kind}_authorized",
        entity_type="service_request", entity_id=ticket.id, metadata_=metadata))
    # Fail closed before opening a bucket stream or generating/serving private bytes.
    db.commit()


def safe_reference(value):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


@router.get("")
def history(reader: Literal["all", "customer", "staff"] = "all",
    kind: Literal["all", "document", "preliminary_report"] = "all",
    ticket_number: str = Query("", max_length=60, pattern=r"^[A-Za-z0-9 -]*$"),
    from_date: date | None = None, to_date: date | None = None,
    cursor: str | None = Query(None, max_length=180), page_size: int = Query(25, ge=1, le=50),
    _: User = Depends(require_admin), db=Depends(get_db)):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "From date must be on or before To date.")
    actions = [action for action, labels in ACTIONS.items()
        if (reader == "all" or labels[0] == reader) and (kind == "all" or labels[1] == kind)]
    # Select one allowlisted reference from JSON, never the full private payload.
    query = select(AuditLog.id, AuditLog.created_at, AuditLog.action, AuditLog.entity_id,
        AuditLog.metadata_["file_id"].as_string().label("file_id"), User.display_name, ServiceRequest.ticket_number)
    query = query.outerjoin(User, User.id == AuditLog.actor_user_id).outerjoin(ServiceRequest, ServiceRequest.id == AuditLog.entity_id)
    query = query.where(AuditLog.entity_type == "service_request", AuditLog.action.in_(actions))
    if ticket_number.strip():
        query = query.where(ServiceRequest.ticket_number == ticket_number.strip().upper())
    india = ZoneInfo("Asia/Kolkata")
    try:
        if from_date:
            query = query.where(AuditLog.created_at >= datetime.combine(from_date, time.min, india).astimezone(timezone.utc))
        if to_date:
            query = query.where(AuditLog.created_at <= datetime.combine(to_date, time.max, india).astimezone(timezone.utc))
    except (ValueError, OverflowError):
        raise HTTPException(422, "Choose dates within the supported calendar range.")
    if cursor is not None:
        stamp, key = cursor_value(cursor)
        query = query.where(or_(AuditLog.created_at < stamp, and_(AuditLog.created_at == stamp, AuditLog.id < key)))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(page_size + 1)).all()
    more = len(rows) > page_size
    rows = rows[:page_size]
    return {"items": [{"id": str(row.id), "at": aware(row.created_at).isoformat(),
        "reader": ACTIONS[row.action][0], "actor": "Verified customer" if ACTIONS[row.action][0] == "customer" else row.display_name or "Former staff",
        "kind": ACTIONS[row.action][1], "case_reference": str(row.entity_id) if row.entity_id else None,
        "ticket_number": row.ticket_number, "file_reference": safe_reference(row.file_id)} for row in rows],
        "next_cursor": cursor_for(rows[-1]) if more else None, "checked_at": utcnow().isoformat()}
