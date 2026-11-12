"""Persistent staff sign-ins; callers commit issuance with the security action."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from . import config
from .models import AuditLog, StaffSession, User, utcnow
from .session_metadata import device_labels

MAX_ACTIVE_SESSIONS = 20


def invalidate_sessions(db, user, reason="security_change"):
    db.execute(update(StaffSession).where(StaffSession.user_id == user.id, StaffSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoke_reason=reason).execution_options(synchronize_session=False))


def issue(db, user_id, user_agent):
    # All sign-in/security paths take the user lock before session records.
    db.flush()
    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None or user.account_status != "active" or not user.role_names & {"agent", "admin", "super_admin"}:
        raise ValueError("An active staff account is required.")
    now = utcnow().replace(microsecond=0)
    expires = now + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)
    if expires <= now:
        raise RuntimeError("Staff session lifetime must be positive.")
    rows = db.scalars(select(StaffSession).where(StaffSession.user_id == user.id, StaffSession.token_version == user.token_version,
        StaffSession.revoked_at.is_(None), StaffSession.expires_at > now).order_by(StaffSession.created_at, StaffSession.id)).all()
    ended = rows[:max(0, len(rows) - MAX_ACTIVE_SESSIONS + 1)]
    for row in ended:
        row.revoked_at = now
        row.revoke_reason = "session_limit"
    if ended:
        db.add(AuditLog(actor_user_id=user.id, action="staff.sessions_limited", entity_type="staff_security", entity_id=user.id, metadata_={"count": len(ended)}))
    key = uuid.uuid4()
    browser, device = device_labels(user_agent)
    db.add(StaffSession(id=key, user_id=user.id, token_version=user.token_version, browser=browser, device=device,
        created_at=now, last_seen_at=now, expires_at=expires))
    db.flush()
    return key, user.token_version, now, expires
