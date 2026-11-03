"""Provider requests are mocked; these tests never deliver email or SMS."""
import json
import uuid
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app import config, notification_providers as providers, notify
from app.db import SessionLocal
from app.models import Notification, utcnow


@pytest.fixture
def configured(monkeypatch):
    for key, value in {"RESEND_API_KEY": "test-email-key", "EMAIL_FROM": "Homexo <notices@example.test>",
                       "TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "test-sms-key", "TWILIO_FROM_NUMBER": "+15005550006",
                       "TWILIO_MESSAGING_SERVICE_SID": "", "WHATSAPP_ACCESS_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": "",
                       "NOTIFY_MAX_ATTEMPTS": 3, "NOTIFY_RETRY_SECONDS": 60, "NOTIFY_MAX_AGE_HOURS": 24}.items():
        monkeypatch.setattr(config, key, value)


def queue(channel="email", **values):
    with SessionLocal() as db:
        n = Notification(channel=channel, recipient="buyer@example.test" if channel == "email" else "+91 98765 43210",
                         template_key="staff_message", body="PRIVATE legal issue: confidential records", **values)
        db.add(n)
        db.commit()
        return n.id


def row(id):
    with SessionLocal() as db:
        return db.get(Notification, id)


def run(now=None, limit=100):
    with SessionLocal() as db:
        return notify.deliver_due(db, now=now, limit=limit)


def transport(monkeypatch, handler):
    monkeypatch.setattr(providers, "http", httpx.Client(transport=httpx.MockTransport(handler)))


def test_both_channels_send_once_and_do_not_include_private_message(configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "email-123"} if request.url.host == "api.resend.com" else {"sid": "SM123", "status": "queued"})
    transport(monkeypatch, handler)
    email, sms = queue(), queue("sms")
    assert run() == 2
    assert run() == 0
    assert len(calls) == 2
    mail = next(r for r in calls if r.url.host == "api.resend.com")
    assert mail.headers["idempotency-key"] == f"homexo-notification/{email}"
    assert mail.headers["authorization"] == "Bearer test-email-key"
    data = json.loads(mail.content)
    assert data["to"] == ["buyer@example.test"] and data["from"] == config.EMAIL_FROM
    assert "PRIVATE" not in data["text"] and "/account" in data["text"]
    text = parse_qs(next(r for r in calls if r.url.host == "api.twilio.com").content.decode())
    assert text["To"] == ["+919876543210"] and text["From"] == [config.TWILIO_FROM_NUMBER]
    assert "PRIVATE" not in text["Body"][0]
    assert row(email).provider_reference == "email-123" and row(sms).provider_reference == "SM123"
    assert row(email).attempts == 1 and row(sms).delivery_status == "sent"
    assert row(email).delivered_at is None  # Provider acceptance is not delivery confirmation.


def test_unconfigured_channels_do_not_consume_attempts(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "")
    email, sms = queue(), queue("sms")
    assert run() == 0
    assert row(email).delivery_status == row(sms).delivery_status == "queued"
    assert row(email).attempts == row(sms).attempts == 0


def test_email_transient_failure_backs_off_and_reuses_idempotency_key(configured, monkeypatch):
    now = utcnow()
    calls = []
    def handler(request):
        calls.append(request.headers["idempotency-key"])
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"id": "email-123"})
    transport(monkeypatch, handler)
    id = queue()
    assert run(now) == 0
    assert row(id).delivery_status == "queued" and row(id).error_code == "email_http_503"
    assert run(now + timedelta(seconds=59)) == 0
    assert run(now + timedelta(seconds=60)) == 1
    assert len(calls) == 2 and calls[0] == calls[1]
    assert row(id).attempts == 2 and row(id).error_code is None


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_email_errors_stop_without_recording_provider_text(configured, monkeypatch, status):
    transport(monkeypatch, lambda r: httpx.Response(status, text="secret value and recipient"))
    id = queue()
    assert run() == 0 and run(utcnow() + timedelta(hours=1)) == 0
    assert row(id).delivery_status == "failed" and row(id).error_code == f"email_http_{status}"
    assert row(id).attempts == 1


def test_retries_stop_at_attempt_limit(configured, monkeypatch):
    transport(monkeypatch, lambda r: httpx.Response(429))
    id = queue()
    now = utcnow()
    for minutes in (0, 1, 3, 10):
        assert run(now + timedelta(minutes=minutes)) == 0
    assert row(id).delivery_status == "failed" and row(id).attempts == 3


def test_sms_explicit_rate_limit_is_retried(configured, monkeypatch):
    count = []
    def handler(request):
        count.append(request)
        return httpx.Response(429) if len(count) == 1 else httpx.Response(201, json={"sid": "SM123"})
    transport(monkeypatch, handler)
    id = queue("sms")
    now = utcnow()
    assert run(now) == 0
    assert run(now + timedelta(seconds=60)) == 1
    assert row(id).attempts == 2


@pytest.mark.parametrize("failure", ["timeout", "server_error", "invalid_json"])
def test_uncertain_sms_outcomes_are_not_resent(configured, monkeypatch, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive provider details", request=request)
        return httpx.Response(503) if failure == "server_error" else httpx.Response(201, text="not json")
    transport(monkeypatch, handler)
    id = queue("sms")
    assert run() == 0 and run(utcnow() + timedelta(hours=1)) == 0
    assert row(id).delivery_status == "failed" and row(id).error_code == "sms_outcome_unknown"
    assert row(id).attempts == 1


def test_stale_sms_lease_is_not_replayed_after_worker_crash(configured, monkeypatch):
    transport(monkeypatch, lambda r: pytest.fail("A possibly accepted SMS must not be replayed"))
    id = queue("sms", attempts=1, processing_until=utcnow()-timedelta(seconds=1), claim_token=uuid.uuid4())
    assert run() == 0
    assert row(id).error_code == "provider_outcome_unknown" and row(id).attempts == 1


def test_active_lease_is_skipped_and_email_crash_recovery_is_idempotent(configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.headers["idempotency-key"])
        return httpx.Response(200, json={"id": "email-123"})
    transport(monkeypatch, handler)
    now = utcnow()
    id = queue(attempts=1, processing_until=now+timedelta(minutes=5), claim_token=uuid.uuid4(), first_attempt_at=now)
    assert run(now) == 0
    assert run(now+timedelta(minutes=6)) == 1
    assert calls == [f"homexo-notification/{id}"] and row(id).attempts == 2


def test_email_idempotency_window_is_not_exceeded(configured, monkeypatch):
    transport(monkeypatch, lambda r: pytest.fail("Email deduplication window expired"))
    id = queue(attempts=1, first_attempt_at=utcnow()-timedelta(hours=24))
    assert run() == 0 and row(id).error_code == "email_retry_window_expired"


def test_old_backlog_is_cancelled_and_future_notifications_wait(configured, monkeypatch):
    transport(monkeypatch, lambda r: pytest.fail("Not due or too old"))
    old = queue(created_at=utcnow()-timedelta(days=7))
    future = queue(send_after=utcnow()+timedelta(days=2))
    assert run() == 0
    assert row(old).delivery_status == "cancelled" and row(old).error_code == "expired"
    assert row(future).delivery_status == "queued" and row(future).attempts == 0


def test_sending_lease_is_persisted_before_provider_call(configured, monkeypatch):
    id = queue()
    def handler(request):
        claimed = row(id)
        assert claimed.attempts == 1 and claimed.claim_token and claimed.processing_until
        return httpx.Response(200, json={"id": "email-123"})
    transport(monkeypatch, handler)
    assert run() == 1
    assert row(id).claim_token is None and row(id).processing_until is None


def test_sms_messaging_service_and_validation(configured, monkeypatch):
    monkeypatch.setattr(config, "TWILIO_MESSAGING_SERVICE_SID", "MGtest")
    def handler(request):
        form = parse_qs(request.content.decode())
        assert form["MessagingServiceSid"] == ["MGtest"] and "From" not in form
        return httpx.Response(201, json={"sid": "SM123"})
    transport(monkeypatch, handler)
    assert run() == 0
    id = queue("sms")
    assert run() == 1 and row(id).provider_reference == "SM123"
    for value in ["", "123", "buyer@example.test"]:
        with pytest.raises(providers.DeliveryError):
            providers.sms_number(value)


def test_staff_notification_history_includes_delivery_metadata(client, raise_ticket, admin_headers, configured, monkeypatch):
    transport(monkeypatch, lambda r: httpx.Response(200, json={"id": "email-123", "sid": "SM123"}))
    ticket = raise_ticket()
    assert run() >= 2
    detail = client.get(f"/api/v1/admin/tickets/{ticket}", headers=admin_headers).json()
    assert all(n["status"] == "sent" and n["attempts"] == 1 and n["provider_reference"] for n in detail["notifications"])


def test_scheduled_reminders_and_changes_cover_email_and_sms(client, raise_ticket, admin_headers):
    ticket = raise_ticket()
    start = (utcnow()+timedelta(hours=48)).isoformat()
    response = client.post(f"/api/v1/admin/tickets/{ticket}/meetings", json={"starts_at": start, "meet_link": "https://meet.google.com/abc-defg-hij"}, headers=admin_headers)
    assert response.status_code == 201, response.text
    meeting = response.json()["meetings"][0]
    updated = client.patch(f"/api/v1/admin/meetings/{meeting['id']}", json={"meet_link": "https://meet.google.com/new-link"}, headers=admin_headers)
    assert updated.status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification).where(Notification.meeting_id == uuid.UUID(meeting["id"]))).all()
        assert {n.channel for n in rows if n.template_key == "meeting_scheduled"} == {"email", "sms", "whatsapp"}
        assert {n.channel for n in rows if n.template_key == "meeting_reminder"} == {"email", "sms", "whatsapp"}
        keys = [n.dedupe_key for n in rows if n.dedupe_key]
        assert len(keys) == len(set(keys))
    changed = client.patch(f"/api/v1/admin/meetings/{meeting['id']}", json={"status": "cancelled"}, headers=admin_headers)
    assert changed.status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification).where(Notification.meeting_id == uuid.UUID(meeting["id"]))).all()
        assert all(n.delivery_status == "cancelled" for n in rows if n.template_key == "meeting_reminder")
        assert {n.channel for n in rows if n.template_key == "meeting_cancelled"} == {"email", "sms", "whatsapp"}


def test_concurrent_postgres_workers_claim_each_message_once(configured, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.db import engine
    if engine.dialect.name != "postgresql":
        pytest.skip("Worker locking is verified against PostgreSQL separately.")
    entered, release = Event(), Event()
    calls = []
    def handler(request):
        calls.append(request)
        entered.set()
        assert release.wait(10)
        return httpx.Response(200, json={"id": "email-123"})
    transport(monkeypatch, handler)
    id = queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        try:
            assert entered.wait(10)
            assert pool.submit(run).result(timeout=10) == 0
        finally:
            release.set()
        assert first.result(timeout=10) == 1
    assert len(calls) == 1 and row(id).attempts == 1


def test_each_claim_gets_a_fresh_lease_in_a_slow_batch(configured, monkeypatch):
    from app.tickets import aware
    now = utcnow()
    clock = [now]
    monkeypatch.setattr(notify, "utcnow", lambda: clock[0])
    calls = []
    def handler(request):
        id = uuid.UUID(request.headers["idempotency-key"].split("/")[1])
        assert aware(row(id).processing_until) == clock[0]+timedelta(minutes=5)
        calls.append(id)
        clock[0] += timedelta(minutes=10)
        return httpx.Response(200, json={"id": "email-123"})
    transport(monkeypatch, handler)
    queue()
    queue()
    assert run(limit=2) == 2 and len(calls) == 2
