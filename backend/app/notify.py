"""Notification delivery: transactional email, SMS and WhatsApp with persisted attempts and worker leases.
Each run also releases online bookings left unpaid past PAYMENT_HOLD_MINUTES (see payments.py).

Runs every NOTIFY_INTERVAL_SECONDS inside the API process, or on its own with `python -m app.notify [--loop]`.
Unconfigured channels remain queued. Email uses provider idempotency; ambiguous SMS outcomes stop for review.
"""
import argparse
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from . import config, payments, whatsapp, notification_providers as providers, sla_alerts, support_alerts, support_notifications
from .db import SessionLocal
from .meetings import render
from .models import Meeting, Notification, ServiceRequest, User, utcnow
from .tickets import aware
from .telemetry import observe_worker
from .notification_preferences import delivery_allowed

log = logging.getLogger("homexo.notify")

def _expired(notification: Notification, meeting: Meeting | None, now: datetime) -> bool:
    """A reminder after the start, or an invite after the end (say, after the worker was down), would only confuse."""
    if meeting is None or notification.template_key == "meeting_cancelled":
        return False
    if meeting.status != "scheduled":
        return True
    return aware(meeting.starts_at if notification.template_key == "meeting_reminder" else meeting.ends_at) <= now

def _due(now, channels):
    return (
        Notification.channel.in_(channels), Notification.delivery_status == "queued",
        or_(Notification.send_after.is_(None), Notification.send_after <= now),
        or_(Notification.processing_until.is_(None), Notification.processing_until <= now),
    )


def deliver_due(db: Session, now: datetime | None = None, limit: int = 100) -> int:
    """Claim one row at a time, persist its lease, and send only configured channels.

    Email uses the row ID as a provider idempotency key. A lost SMS/WhatsApp claim
    is stopped for review because those APIs cannot guarantee idempotent resends.
    """
    fixed_now = now
    now = now or utcnow()
    if not config.SUPPORT_REPLY_NOTIFICATIONS_ENABLED:
        db.execute(update(Notification).where(Notification.template_key == "support_reply", Notification.delivery_status == "queued")
            .values(delivery_status="cancelled", error_code="support_notifications_disabled", claim_token=None, processing_until=None))
        db.commit()
    channels = [c for c in ("email", "sms") if providers.enabled(c)]
    if whatsapp.enabled():
        channels.append("whatsapp")
    if not channels:
        return 0
    sent = 0
    for _ in range(limit):
        now = fixed_now or utcnow()
        notification = db.scalars(select(Notification).where(*_due(now, channels))
            .order_by(Notification.send_after, Notification.created_at, Notification.id)
            .with_for_update(skip_locked=True).limit(1)).first()
        if notification is None:
            break
        reason = support_notifications.cancellation_reason(db, notification)
        if reason:
            notification.delivery_status, notification.error_code = "cancelled", reason
            notification.processing_until = notification.claim_token = None
            db.commit()
            continue
        if not delivery_allowed(db, notification):
            notification.delivery_status, notification.error_code = "cancelled", "preference_disabled"
            notification.processing_until = notification.claim_token = None
            db.commit()
            continue
        meeting = db.get(Meeting, notification.meeting_id) if notification.meeting_id else None
        due_at = aware(notification.send_after or notification.created_at)
        allowed = sla_alerts.delivery_allowed(db, notification, now)
        if not allowed or _expired(notification, meeting, now) or due_at < now - timedelta(hours=config.NOTIFY_MAX_AGE_HOURS):
            notification.delivery_status, notification.error_code = "cancelled", "expired" if allowed else "alert_no_longer_pending"
            notification.processing_until = notification.claim_token = None
            db.commit()
            continue
        if notification.processing_until is not None and notification.channel != "email":
            notification.delivery_status, notification.error_code = "failed", "provider_outcome_unknown"
            notification.processing_until = notification.claim_token = None
            db.commit()
            continue
        # Resend retains idempotency keys for 24h; never replay outside that window.
        if notification.channel == "email" and notification.first_attempt_at and aware(notification.first_attempt_at) < now - timedelta(hours=23):
            notification.delivery_status, notification.error_code = "failed", "email_retry_window_expired"
            notification.processing_until = notification.claim_token = None
            db.commit()
            continue
        if notification.attempts >= config.NOTIFY_MAX_ATTEMPTS:
            notification.delivery_status, notification.error_code = "failed", "attempts_exhausted"
            db.commit()
            continue
        claim = uuid.uuid4()
        notification.claim_token = claim
        notification.processing_until = now + timedelta(minutes=5)
        notification.attempts += 1
        notification.first_attempt_at = notification.first_attempt_at or now
        notification.last_attempt_at = now
        notification.error_code = None
        db.commit()  # A crash after provider acceptance cannot leave an unclaimed queued row.
        notification_id = notification.id
        values = {"claim_token": None, "processing_until": None}
        try:
            # Refresh after claim commit, so cancellation before sending is respected.
            db.refresh(notification)
            if notification.delivery_status != "queued" or notification.claim_token != claim:
                continue
            reason = support_notifications.cancellation_reason(db, notification)
            if reason:
                db.execute(update(Notification).where(Notification.id == notification_id, Notification.claim_token == claim)
                    .values(delivery_status="cancelled", error_code=reason, claim_token=None, processing_until=None))
                db.commit()
                continue
            if not delivery_allowed(db, notification):
                db.execute(update(Notification).where(Notification.id == notification_id, Notification.claim_token == claim)
                    .values(delivery_status="cancelled", error_code="preference_disabled", claim_token=None, processing_until=None))
                db.commit()
                continue
            if not sla_alerts.delivery_allowed(db, notification, fixed_now or utcnow()):
                db.execute(update(Notification).where(Notification.id == notification_id, Notification.claim_token == claim)
                    .values(delivery_status="cancelled", error_code="alert_no_longer_pending", claim_token=None, processing_until=None))
                db.commit()
                continue
            if notification.channel == "whatsapp":
                params = [config.PUBLIC_SITE_URL.rstrip("/") + "/account/support"] if notification.template_key == "support_reply" else notification.params or []
                reference = whatsapp.send_template(notification.recipient or "", notification.template_key, params)
            else:
                ticket = db.get(ServiceRequest, notification.service_request_id) if notification.service_request_id else None
                sender = providers.send_email if notification.channel == "email" else providers.send_sms
                reference = sender(notification, ticket.ticket_number if ticket else None)
            values.update(provider_reference=reference, delivery_status="sent", error_code=None)
        except providers.DeliveryError as exc:
            retry = exc.retryable and notification.attempts < config.NOTIFY_MAX_ATTEMPTS
            values.update(delivery_status="queued" if retry else "failed", error_code=exc.code)
            if retry:
                values["send_after"] = now + timedelta(seconds=min(3600, config.NOTIFY_RETRY_SECONDS * 2 ** (notification.attempts - 1)))
        except whatsapp.WhatsAppError as exc:
            # Keep historical WhatsApp errors terminal; unknown outcomes must not be blindly replayed.
            values.update(delivery_status="failed", error_code=exc.code)
        result = db.execute(update(Notification).where(Notification.id == notification_id,
            Notification.claim_token == claim, Notification.delivery_status == "queued").values(**values))
        db.commit()
        if values["delivery_status"] == "sent" and result.rowcount:
            sent += 1
    return sent

def queue_daily_agendas(db: Session, now: datetime | None = None) -> int:
    """Once a day, from LAWYER_AGENDA_HOUR, give each lawyer with meetings still ahead today the day's list."""
    if config.LAWYER_AGENDA_HOUR < 0:
        return 0
    now = now or utcnow()
    zone = ZoneInfo(config.MEETING_TIMEZONE)
    local_now = now.astimezone(zone)
    if local_now.hour < config.LAWYER_AGENDA_HOUR:
        return 0
    day_end = datetime.combine(local_now.date() + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    meetings = db.scalars(
        select(Meeting).where(Meeting.status == "scheduled", Meeting.starts_at >= now, Meeting.starts_at < day_end).order_by(Meeting.starts_at)
    ).unique().all()
    by_lawyer: dict = {}
    for meeting in meetings:
        by_lawyer.setdefault(meeting.lawyer_user_id, []).append(meeting)
    queued = 0
    for lawyer_id, todays in by_lawyer.items():
        lawyer = db.get(User, lawyer_id)
        key = f"agenda:{lawyer_id}:{local_now.date().isoformat()}"
        if not lawyer.phone or db.scalars(select(Notification.id).where(Notification.dedupe_key == key)).first():
            continue
        items = "; ".join(
            f"{aware(m.starts_at).astimezone(zone).strftime('%I:%M %p').lstrip('0').lower()} {m.service_request.customer.full_name} ({m.service_request.ticket_number})"
            for m in todays
        )
        params = [lawyer.display_name, str(len(todays)), items, f"{config.PUBLIC_SITE_URL}/admin/calendar"]
        db.add(Notification(user_id=lawyer.id, channel="whatsapp", template_key="lawyer_daily_agenda", recipient=lawyer.phone,
                            params=params, body=render("lawyer_daily_agenda", params), send_after=now, dedupe_key=key))
        queued += 1
    db.commit()
    return queued

@observe_worker("notifications")
def run_once() -> None:
    with SessionLocal() as db:
        payments.release_unpaid(db)
        queue_daily_agendas(db)
        sla_alerts.reconcile(db)
        support_alerts.reconcile(db)
        deliver_due(db)

async def worker_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            pass  # observe_worker recorded a fixed error category without provider/SQL details.
        await asyncio.sleep(config.NOTIFY_INTERVAL_SECONDS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help=f"Keep running every {config.NOTIFY_INTERVAL_SECONDS}s instead of once.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            run_once()
        except Exception:
            if not args.loop:
                raise SystemExit(1) from None  # The observation wrapper already emitted a safe event.
        if not args.loop:
            break
        time.sleep(config.NOTIFY_INTERVAL_SECONDS)
