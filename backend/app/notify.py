"""Notification delivery: sends due WhatsApp messages (invites, reminders, agendas) and queues each lawyer's daily agenda.

Runs every NOTIFY_INTERVAL_SECONDS inside the API process, or on its own with `python -m app.notify [--loop]`.
Without WhatsApp credentials nothing is sent and messages stay queued. SMS and email have no provider yet and stay queued.
"""
import argparse
import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import config, whatsapp
from .db import SessionLocal
from .meetings import render
from .models import Meeting, Notification, User, utcnow
from .tickets import aware

log = logging.getLogger("homexo.notify")

def _expired(notification: Notification, meeting: Meeting | None, now: datetime) -> bool:
    """A reminder after the start, or an invite after the end (say, after the worker was down), would only confuse."""
    if meeting is None or notification.template_key == "meeting_cancelled":
        return False
    if meeting.status != "scheduled":
        return True
    return aware(meeting.starts_at if notification.template_key == "meeting_reminder" else meeting.ends_at) <= now

def deliver_due(db: Session, now: datetime | None = None, limit: int = 100) -> int:
    """Send queued WhatsApp messages whose time has come. Returns how many were sent."""
    if not whatsapp.enabled():
        return 0
    now = now or utcnow()
    due = db.scalars(
        select(Notification)
        .where(Notification.channel == "whatsapp", Notification.delivery_status == "queued", or_(Notification.send_after.is_(None), Notification.send_after <= now))
        .order_by(Notification.send_after).limit(limit)
        # Several API processes can run this loop; each row goes to one of them.
        .with_for_update(skip_locked=True)
    ).all()
    sent = 0
    for notification in due:
        meeting = db.get(Meeting, notification.meeting_id) if notification.meeting_id else None
        if _expired(notification, meeting, now):
            notification.delivery_status, notification.error_code = "cancelled", "expired"
        else:
            try:
                notification.provider_reference = whatsapp.send_template(notification.recipient or "", notification.template_key, notification.params or [])
                notification.delivery_status = "sent"
                sent += 1
            except whatsapp.WhatsAppError as exc:
                log.warning("WhatsApp %s to notification %s failed: %s", notification.template_key, notification.id, exc)
                notification.delivery_status, notification.error_code = "failed", exc.code
        db.commit()
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

def run_once() -> None:
    with SessionLocal() as db:
        queue_daily_agendas(db)
        deliver_due(db)

async def worker_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("Notification run failed")
        await asyncio.sleep(config.NOTIFY_INTERVAL_SECONDS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help=f"Keep running every {config.NOTIFY_INTERVAL_SECONDS}s instead of once.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        run_once()
        if not args.loop:
            break
        time.sleep(config.NOTIFY_INTERVAL_SECONDS)
