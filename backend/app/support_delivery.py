"""Read-only administrator delivery metadata; no message bodies, contacts or provider payloads."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import config, notification_providers, support_deadline_email, whatsapp
from .db import get_db
from .models import Notification, SupportDeadlineAlert, User
from .security import require_admin
from .support import find
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/support-requests")

REASONS = {
    "preference_disabled": "Channel disabled by customer",
    "support_reply_read": "Reply already read",
    "support_reply_superseded": "Newer reply available",
    "support_reply_unavailable": "Reply no longer available",
    "support_recipient_changed": "Customer contact changed",
    "support_notifications_disabled": "Customer reply notices are off",
    "support_alert_no_longer_pending": "Alert changed or was acknowledged",
    "support_alert_recipient_changed": "Administrator routing changed",
    "support_deadline_email_disabled": "Staff email notices are off",
    "expired": "Delivery window expired",
    "provider_outcome_unknown": "Provider outcome uncertain; review before retrying",
    "sms_outcome_unknown": "Provider outcome uncertain; review before retrying",
    "email_retry_window_expired": "Email retry window expired",
    "attempts_exhausted": "Delivery attempt limit reached",
    "invalid_email": "Email address could not be used",
    "invalid_phone": "Phone number could not be used",
    "email_unreachable": "Email provider unavailable",
    "email_invalid_response": "Email provider response incomplete",
    "sms_rate_limited": "SMS provider rate limit reached",
    "sms_connect_failed": "SMS provider unavailable",
    "sms_rejected": "SMS provider rejected delivery",
}


def timestamp(value):
    return aware(value).isoformat() if value else None


def view(notice, staff_name):
    customer = notice.template_key == "support_reply"
    return {"id": str(notice.id), "event": "customer_reply" if customer else (
            "support_escalation" if notice.params == ["escalated"] else "support_deadline"),
        "recipient_kind": "customer" if customer else "administrator",
        "recipient_name": "Customer" if customer else staff_name or "Former administrator",
        "channel": notice.channel, "status": notice.delivery_status, "attempts": notice.attempts,
        "created_at": timestamp(notice.created_at), "last_attempt_at": timestamp(notice.last_attempt_at),
        "scheduled_for": timestamp(notice.send_after), "delivered_at": timestamp(notice.delivered_at),
        "reason": REASONS.get(notice.error_code, "Delivery issue; review provider records") if notice.error_code else None}


@router.get("/{request_id}/deliveries")
def history(request_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    recipient: Literal["all", "customer", "administrator"] = "all",
    status: Literal["all", "queued", "sent", "delivered", "failed", "cancelled"] = "all",
    channel: Literal["all", "email", "sms", "whatsapp"] = "all",
    _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = find(db, request_id)
    incidents = select(SupportDeadlineAlert.id).where(SupportDeadlineAlert.support_request_id == item.id)
    customer = (Notification.template_key == "support_reply") & (Notification.support_request_id == item.id) & (Notification.account_id == item.account_id)
    staff = (Notification.template_key == "support_deadline_email") & (Notification.support_alert_id.in_(incidents)) & (Notification.channel == "email")
    query = select(Notification).where(Notification.channel.in_(("email", "sms", "whatsapp")),
        customer if recipient == "customer" else staff if recipient == "administrator" else or_(customer, staff))
    if status != "all": query = query.where(Notification.delivery_status == status)
    if channel != "all": query = query.where(Notification.channel == channel)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.add_columns(User.display_name).outerjoin(User, User.id == Notification.user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [view(notice, name) for notice, name in rows], "total": total, "page": page, "page_size": page_size,
        "configuration": {"customer_replies_enabled": config.SUPPORT_REPLY_NOTIFICATIONS_ENABLED,
            "staff_email": support_deadline_email.delivery_status(),
            "channels": {"email": notification_providers.enabled("email"), "sms": notification_providers.enabled("sms"), "whatsapp": whatsapp.enabled()}}}
