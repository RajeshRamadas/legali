"""Administrator activity index. Select safe columns only, never audit payloads."""
import base64
import binascii
import uuid
from datetime import date, datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, User, utcnow
from .security import require_admin
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/activity")
Category = Literal["all", "services", "cases", "staff", "support", "privacy", "policies", "reviews", "scheduling", "refunds", "notifications", "publishing", "other"]

# An explicit vocabulary keeps future or malformed action strings private.
GROUPS = {
    "services": ("Services", {
        "service.availability_changed": "Service availability changed",
        "service.description_changed": "Service description changed",
        "service.intake_form_published": "Intake form published",
    }),
    "cases": ("Case work", {
        "case.task_created": "Case task created", "case.task_updated": "Case task updated",
        "ticket.status_changed": "Case status changed", "ticket.assigned": "Case assignment changed",
        "case.due_changed": "Case due date changed", "case.member_added": "Case team member added",
        "case.member_removed": "Case team member removed", "case.fee_quote": "Case fee quoted",
        "case.fee_paid": "Case fee payment recorded", "case.fee_waive": "Case fee waived",
        "case.fee_clear": "Case fee cleared", "case.deadline_alerted": "Case deadline alert recorded",
        "case.deadline_acknowledged": "Case deadline alert acknowledged",
        "case.deadline_escalated": "Case deadline alert escalated", "case.deadline_resolved": "Case deadline alert resolved",
    }),
    "staff": ("Staff & security", {
        "staff.created": "Staff account created", "staff.updated": "Staff account updated",
        "staff.availability": "Staff call availability changed", "staff.login": "Staff signed in",
        "staff.login_mfa": "Staff signed in with MFA", "staff.mfa_setup_started": "MFA setup started",
        "staff.mfa_enabled": "MFA enabled", "staff.mfa_disabled": "MFA disabled",
        "staff.password_changed": "Staff password changed", "staff.password_reset": "Staff password reset",
        "staff.password_reset_requested": "Staff password reset requested",
        "staff.recovery_codes_regenerated": "Recovery codes regenerated", "staff.sessions_revoked": "Staff sessions revoked",
    }),
    "support": ("Customer support", {
        "support.created": "Support request created", "support.customer_replied": "Customer support reply recorded",
        "support.reviewed": "Support request reviewed", "support.assigned": "Support owner changed",
        "support.deadline_alerted": "Support deadline alert recorded",
        "support.deadline_acknowledged": "Support deadline alert acknowledged",
        "support.deadline_escalated": "Support deadline alert escalated",
        "support.deadline_reopened": "Support deadline alert reopened", "support.deadline_resolved": "Support deadline alert resolved",
    }),
    "privacy": ("Privacy & retention", {
        "privacy.requested": "Privacy request created", "privacy.reviewed": "Privacy request reviewed",
        "privacy.withdrawn": "Privacy request withdrawn", "retention.chats_cleaned": "Chat retention cleanup recorded",
        "retention.hold_set": "Retention hold set", "retention.hold_released": "Retention hold released",
    }),
    "policies": ("Public policies", {
        "site_policy_draft_saved": "Policy draft saved", "site_policy_published": "Policy published",
        "site_policy_withdrawn": "Policy withdrawn",
    }),
    "reviews": ("Consultation reviews", {"review.moderated": "Consultation review moderated", "review.withdrawn": "Consultation review withdrawn"}),
    "scheduling": ("Scheduling", {"lawyer.time_off_created": "Lawyer time off recorded", "lawyer.time_off_cancelled": "Lawyer time off cancelled"}),
    "refunds": ("Refunds", {"refund.created": "Provider refund created", "refund.failed": "Provider refund failed",
        "refund.processed": "Provider refund processed", "refund.recorded": "Refund recorded",
        "refund.updated": "Refund updated", "refund.note_saved": "Refund follow-up note saved"}),
    "notifications": ("Notification preferences", {"notification.preferences_changed": "Customer notification preferences changed"}),
    "publishing": ("Publishing & research", {"post.created": "Post created", "post.updated": "Post updated",
        "post.published": "Post published", "post.unpublished": "Post unpublished", "post.deleted": "Post deleted",
        "post.review_confirmed": "Post review confirmed", "post.ai_drafted": "Post draft generated",
        "post.rechecked": "Post checks repeated", "blog_agent.scan_started": "Research scan started",
        "blog_agent.draft_started": "Research draft started", "blog_agent.lead_dismissed": "Research lead dismissed"}),
}
ACTIONS = {action: (category, label) for category, (_, actions) in GROUPS.items() for action, label in actions.items()}
RECORDS = {"service_type": "Service", "service_request": "Case", "staff_security": "Staff security",
    "support_request": "Support request", "privacy_request": "Privacy request", "site_policy": "Public policy",
    "lawyer_review": "Consultation review", "lawyer_time_off": "Time off", "refund": "Refund",
    "customer_account": "Customer account", "post": "Post", "case_scan_run": "Research scan",
    "case_lead": "Research lead", "retention_run": "Retention run", "conversation": "Conversation"}


def cursor_for(row):
    return base64.urlsafe_b64encode(f"{aware(row.created_at).isoformat()}|{row.id}".encode()).decode().rstrip("=")


def cursor_value(value):
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True).decode()
        stamp, key = raw.split("|")
        stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is None: raise ValueError()
        return stamp.astimezone(timezone.utc), uuid.UUID(key)
    except (ValueError, OverflowError, UnicodeError, binascii.Error):
        raise HTTPException(422, "Invalid activity page cursor. Refresh activity to start again.")


@router.get("")
def history(category: Category = "all", actor: str = Query("", max_length=100, pattern=r"^[^\x00-\x1f\x7f]*$"),
    from_date: date | None = None, to_date: date | None = None, record_id: uuid.UUID | None = None,
    cursor: str | None = Query(None, max_length=180), page_size: int = Query(25, ge=1, le=50),
    _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "From date must be on or before To date.")
    # No metadata, IP hashes, request IDs, contacts or authentication fields are loaded.
    query = select(AuditLog.id, AuditLog.created_at, AuditLog.action, AuditLog.entity_type, AuditLog.entity_id,
        User.display_name).outerjoin(User, User.id == AuditLog.actor_user_id)
    if category == "other": query = query.where(AuditLog.action.not_in(ACTIONS))
    elif category != "all": query = query.where(AuditLog.action.in_(GROUPS[category][1]))
    if actor.strip():
        escaped = actor.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(User.display_name.ilike(f"%{escaped}%", escape="\\"))
    if record_id: query = query.where(AuditLog.entity_id == record_id)
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
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(page_size+1)).all()
    more = len(rows) > page_size
    rows = rows[:page_size]
    return {"items": [{"id": str(row.id), "at": aware(row.created_at).isoformat(),
        "actor": row.display_name or "Unattributed · customer, system or former staff",
        "category": ACTIONS.get(row.action, ("other", "Other recorded activity"))[0],
        "activity": ACTIONS.get(row.action, ("other", "Other recorded activity"))[1],
        "record_type": RECORDS.get(row.entity_type, "Other record"),
        "record_id": str(row.entity_id) if row.entity_id and row.entity_type in RECORDS else None} for row in rows],
        "next_cursor": cursor_for(rows[-1]) if more else None, "checked_at": utcnow().isoformat(),
        "categories": [{"value": key, "label": label} for key, (label, _) in GROUPS.items()] + [{"value": "other", "label": "Other recorded activity"}]}
