"""Optional administrator email for current support incidents; no private conversation data."""
import hashlib
import re

from sqlalchemy import select, update

from . import config, notification_providers
from .models import Notification, Role, SupportDeadlineAlert, SupportRequest, User
from .tickets import aware


def active(alert, item, now):
    return bool(item and item.status != "resolved" and item.reply_due_at and not alert.resolved_at
        and aware(item.reply_due_at) == aware(alert.target_at) and aware(alert.target_at) < now)


def recipients(db, item, escalated):
    rows = db.execute(select(User.id, User.email).where(User.account_status == "active",
        User.roles.any(Role.name.in_(("admin", "super_admin"))))).all()
    eligible = {id: email.strip() for id, email in rows if email and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip())}
    if not escalated and item.assignee_user_id in eligible:
        return {item.assignee_user_id: eligible[item.assignee_user_id]}
    return eligible


def delivery_status():
    if not config.SUPPORT_DEADLINE_EMAIL_ENABLED:
        return "disabled"
    return "enabled" if notification_providers.enabled("email") else "unconfigured"


def cancel_pending(db, alert_id, reason="support_alert_no_longer_pending"):
    # Leased notices recheck before sending; accepted in-flight results must stay truthful.
    db.execute(update(Notification).where(Notification.support_alert_id == alert_id,
        Notification.delivery_status == "queued", Notification.claim_token.is_(None))
        .values(delivery_status="cancelled", error_code=reason))


def sync_alert(db, alert, item, now, *, enqueue=True):
    eligible = recipients(db, item, bool(alert.escalated_at)) if (
        config.SUPPORT_DEADLINE_EMAIL_ENABLED and active(alert, item, now) and alert.acknowledged_at is None) else {}
    phase = "escalated" if alert.escalated_at else "initial"
    pending = list(db.scalars(select(Notification).where(Notification.support_alert_id == alert.id,
        Notification.delivery_status == "queued", Notification.claim_token.is_(None))))
    for notice in pending:
        if notice.support_alert_revision != alert.revision or eligible.get(notice.user_id) != notice.recipient or notice.params != [phase]:
            notice.delivery_status, notice.error_code = "cancelled", "support_alert_no_longer_pending"
    if not enqueue:
        return
    for user_id, email in eligible.items():
        address = hashlib.sha256(email.encode()).hexdigest()[:24]
        key = f"support-deadline:{alert.id}:{alert.revision}:{user_id}:{address}"
        if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)) is None:
            db.add(Notification(user_id=user_id, support_alert_id=alert.id, support_alert_revision=alert.revision,
                channel="email", template_key="support_deadline_email", recipient=email, params=[phase],
                body="A support response target needs attention. Sign in to the staff support alerts.",
                dedupe_key=key, send_after=now))


def invalidate_request(db, item, now):
    for alert in db.scalars(select(SupportDeadlineAlert).where(SupportDeadlineAlert.support_request_id == item.id)):
        sync_alert(db, alert, item, now, enqueue=False)


def cancellation_reason(db, notification, now):
    if notification.template_key != "support_deadline_email":
        return None
    if not config.SUPPORT_DEADLINE_EMAIL_ENABLED:
        return "support_deadline_email_disabled"
    if not notification.support_alert_id or not notification.user_id or notification.channel != "email":
        return "support_alert_no_longer_pending"
    # Refresh incident/request state and query current role/email scalars after each claim.
    alert = db.get(SupportDeadlineAlert, notification.support_alert_id, populate_existing=True)
    item = db.get(SupportRequest, alert.support_request_id, populate_existing=True) if alert else None
    if not alert or not active(alert, item, now) or alert.acknowledged_at is not None or alert.revision != notification.support_alert_revision:
        return "support_alert_no_longer_pending"
    phase = "escalated" if alert.escalated_at else "initial"
    if notification.params != [phase] or recipients(db, item, bool(alert.escalated_at)).get(notification.user_id) != notification.recipient:
        return "support_alert_recipient_changed"
    return None
