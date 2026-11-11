"""Generic support-reply notices. Message contents remain inside the verified portal."""
from sqlalchemy import select, update

from . import config
from .models import CustomerAccount, Notification, SupportRequest
from .notification_preferences import queue_customer_notification


def cancel_queued(db, request_id, *, through_revision=None, reason):
    query = update(Notification).where(Notification.template_key == "support_reply",
        Notification.support_request_id == request_id, Notification.delivery_status == "queued")
    if through_revision is not None:
        query = query.where(Notification.support_update_revision <= through_revision)
    db.execute(query.values(delivery_status="cancelled", error_code=reason, claim_token=None, processing_until=None))


def queue_reply(db, item):
    # Caller owns the account/request locks. Queue changes commit with the visible reply.
    cancel_queued(db, item.id, reason="support_reply_superseded")
    if not config.SUPPORT_REPLY_NOTIFICATIONS_ENABLED:
        return
    account = db.get(CustomerAccount, item.account_id, populate_existing=True)
    link = config.PUBLIC_SITE_URL.rstrip("/") + "/account/support"
    body = f"Homexo Legal: You have a new support reply. Sign in to read it securely: {link}"
    for channel, recipient in (("email", account.email), ("sms", account.phone_normalized), ("whatsapp", account.phone_normalized)):
        if not recipient:
            continue
        queue_customer_notification(db, account_id=account.id, support_request_id=item.id,
            support_update_revision=item.customer_update_revision, channel=channel, recipient=recipient,
            template_key="support_reply", body=body, params=[link],
            dedupe_key=f"support-reply:{item.id}:{item.customer_update_revision}:{channel}")


def cancellation_reason(db, notification):
    if notification.template_key != "support_reply":
        return None
    if not config.SUPPORT_REPLY_NOTIFICATIONS_ENABLED:
        return "support_notifications_disabled"
    # Scalar reads bypass the session cache, including after the worker's claim commit.
    row = db.execute(select(SupportRequest.account_id, SupportRequest.customer_update_revision,
        SupportRequest.customer_read_revision, CustomerAccount.email, CustomerAccount.phone_normalized)
        .join(CustomerAccount, CustomerAccount.id == SupportRequest.account_id)
        .where(SupportRequest.id == notification.support_request_id)).first()
    if row is None or row.account_id != notification.account_id or not notification.support_update_revision:
        return "support_reply_unavailable"
    if row.customer_update_revision != notification.support_update_revision:
        return "support_reply_superseded"
    if row.customer_read_revision >= notification.support_update_revision:
        return "support_reply_read"
    recipient = row.email if notification.channel == "email" else row.phone_normalized
    if not recipient or recipient != notification.recipient:
        return "support_recipient_changed"
    return None
