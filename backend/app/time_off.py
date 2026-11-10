"""Private staff unavailability; lawyer-row locking serializes it with meeting admission."""
import uuid
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, tickets
from .db import get_db
from .models import AuditLog, LawyerTimeOff, Meeting, User, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1/admin/time-off")


class CreateTimeOff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_key: uuid.UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str = Field(min_length=10, max_length=500)
    confirmed: bool = Field(strict=True)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 10 or any(ord(c) < 32 and c not in "\n\t\r" for c in value):
            raise ValueError("Enter a private reason of 10–500 characters without control characters.")
        return value


class CancelTimeOff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(strict=True)


def owner(db, user, user_id, *, lock=False):
    target = user_id or user.id
    if target != user.id and not user.is_admin:
        raise HTTPException(403, "You can manage only your own time off.")
    query = select(User).where(User.id == target)
    if lock:
        # NO KEY UPDATE preserves serialization while allowing audit/creator FK checks.
        query = query.with_for_update(key_share=True)
    row = db.scalars(query.execution_options(populate_existing=True)).first()
    if row is None or not row.role_names & {"agent", "admin", "super_admin"}:
        raise HTTPException(404, "Staff member not found.")
    return row


def view(row):
    return {"id": str(row.id), "lawyer_id": str(row.lawyer_user_id),
        "starts_at": tickets.aware(row.starts_at).isoformat(), "ends_at": tickets.aware(row.ends_at).isoformat(),
        "reason": row.reason, "created_at": tickets.aware(row.created_at).isoformat(),
        "cancelled_at": tickets.aware(row.cancelled_at).isoformat() if row.cancelled_at else None}


def ensure_available(db, lawyer_id, start, end):
    if db.scalar(select(LawyerTimeOff.id).where(LawyerTimeOff.lawyer_user_id == lawyer_id,
        LawyerTimeOff.cancelled_at.is_(None), LawyerTimeOff.starts_at < end, LawyerTimeOff.ends_at > start).limit(1)):
        raise HTTPException(409, "This staff member is unavailable at that time. Choose another time.")


@router.get("")
def list_time_off(user_id: uuid.UUID | None = None, page: int = Query(1, ge=1),
                  user: User = Depends(current_staff), db: Session = Depends(get_db)):
    target = owner(db, user, user_id)
    query = select(LawyerTimeOff).where(LawyerTimeOff.lawyer_user_id == target.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(LawyerTimeOff.starts_at.desc(), LawyerTimeOff.id).offset((page-1)*20).limit(20)).all()
    return {"items": [view(row) for row in rows], "total": total, "page": page, "page_size": 20,
        "lawyer_id": str(target.id), "name": target.display_name, "timezone": config.MEETING_TIMEZONE}


@router.post("", status_code=201)
def create_time_off(payload: CreateTimeOff, user_id: uuid.UUID | None = None,
                    user: User = Depends(current_staff), db: Session = Depends(get_db)):
    target = owner(db, user, user_id, lock=True)
    if not payload.confirmed:
        raise HTTPException(422, "Confirm that existing meetings must be moved or cancelled first.")
    start, end = payload.starts_at.astimezone(timezone.utc), payload.ends_at.astimezone(timezone.utc)
    existing = db.scalar(select(LawyerTimeOff).where(LawyerTimeOff.lawyer_user_id == target.id, LawyerTimeOff.submission_key == payload.submission_key))
    if existing:
        if (tickets.aware(existing.starts_at), tickets.aware(existing.ends_at), existing.reason) != (start, end, payload.reason):
            raise HTTPException(409, "This submission key was already used for different time off.")
        return view(existing)  # A retry never recreates a cancelled period.
    now = utcnow()
    if end <= now or end <= start or end-start > timedelta(days=90) or start < now-timedelta(days=1) or start > now+timedelta(days=366):
        raise HTTPException(422, "Choose an upcoming period of at most 90 days, starting within the next year or past 24 hours.")
    if target.account_status != "active":
        raise HTTPException(409, "Choose an active staff member.")
    ensure_available(db, target.id, start, end)
    if db.scalar(select(Meeting.id).where(Meeting.lawyer_user_id == target.id, Meeting.status == "scheduled", Meeting.starts_at < end, Meeting.ends_at > start).limit(1)):
        raise HTTPException(409, "A scheduled meeting overlaps this period. Move or cancel it before adding time off.")
    row = LawyerTimeOff(lawyer_user_id=target.id, submission_key=payload.submission_key,
        starts_at=start, ends_at=end, reason=payload.reason, created_by_user_id=user.id)
    db.add(row); db.flush()
    db.add(AuditLog(actor_user_id=user.id, action="lawyer.time_off_created", entity_type="lawyer_time_off", entity_id=row.id,
        metadata_={"lawyer_id": str(target.id), "starts_at": start.isoformat(), "ends_at": end.isoformat()}))
    db.commit()
    return view(row)


@router.post("/{period_id}/cancel")
def cancel_time_off(period_id: uuid.UUID, payload: CancelTimeOff, user_id: uuid.UUID | None = None,
                    user: User = Depends(current_staff), db: Session = Depends(get_db)):
    target = owner(db, user, user_id, lock=True)
    row = db.get(LawyerTimeOff, period_id, populate_existing=True)
    if row is None or row.lawyer_user_id != target.id:
        raise HTTPException(404, "Time off not found.")
    if not payload.confirmed:
        raise HTTPException(422, "Confirm cancellation to reopen these times for booking.")
    if row.cancelled_at is None:
        row.cancelled_at, row.cancelled_by_user_id = utcnow(), user.id
        db.add(AuditLog(actor_user_id=user.id, action="lawyer.time_off_cancelled", entity_type="lawyer_time_off", entity_id=row.id,
            metadata_={"lawyer_id": str(target.id)}))
        db.commit()
    return view(row)
