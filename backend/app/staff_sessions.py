"""Staff may review and revoke their own authenticated sessions only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from .db import get_db
from .models import AuditLog, StaffSession, User, utcnow
from .security import current_staff
from .session_metadata import aware
from .staff_auth import _locked, throttle
from .staff_session_records import MAX_ACTIVE_SESSIONS

router = APIRouter(prefix="/api/v1/auth")


@router.get("/sessions")
def sessions(user: User = Depends(current_staff), db=Depends(get_db)):
    now = utcnow()
    current = user._authenticated_session_id
    rows = db.scalars(select(StaffSession).where(StaffSession.user_id == user.id, StaffSession.token_version == user.token_version,
        StaffSession.revoked_at.is_(None), StaffSession.expires_at > now).order_by(StaffSession.created_at.desc(), StaffSession.id.desc()).limit(MAX_ACTIVE_SESSIONS)).all()
    return {"items": [{"id": str(row.id), "browser": row.browser, "device": row.device, "created_at": aware(row.created_at).isoformat(),
        "last_seen_at": aware(row.last_seen_at).isoformat(), "expires_at": aware(row.expires_at).isoformat(), "is_current": row.id == current} for row in rows],
        "checked_at": now.isoformat(), "max_active": MAX_ACTIVE_SESSIONS, "activity_interval_seconds": 300}


def end_session(db, user, key):
    current = user._authenticated_session_id
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    row = db.scalar(select(StaffSession).where(StaffSession.id == key, StaffSession.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Sign-in session not found.")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoke_reason = "staff"
        db.add(AuditLog(actor_user_id=user.id, action="staff.session_revoked", entity_type="staff_security", entity_id=user.id,
            metadata_={"session_id": str(key), "current": key == current}))
        db.commit()
    return {"revoked": True, "current": key == current}


@router.post("/sessions/{session_id}/revoke")
def revoke(session_id: uuid.UUID, user: User = Depends(current_staff), db=Depends(get_db)):
    return end_session(db, user, session_id)


@router.post("/logout")
def logout(user: User = Depends(current_staff), db=Depends(get_db)):
    return end_session(db, user, user._authenticated_session_id)


@router.post("/sessions/revoke-others")
def revoke_others(user: User = Depends(current_staff), db=Depends(get_db)):
    current = user._authenticated_session_id
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    result = db.execute(update(StaffSession).where(StaffSession.user_id == user.id, StaffSession.id != current,
        StaffSession.token_version == user.token_version, StaffSession.revoked_at.is_(None), StaffSession.expires_at > utcnow())
        .values(revoked_at=utcnow(), revoke_reason="other_sessions").execution_options(synchronize_session=False))
    if result.rowcount:
        db.add(AuditLog(actor_user_id=user.id, action="staff.other_sessions_revoked", entity_type="staff_security", entity_id=user.id, metadata_={"count": result.rowcount}))
    db.commit()
    return {"revoked": result.rowcount}
