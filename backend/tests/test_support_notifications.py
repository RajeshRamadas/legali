"""Transactional support notices use synthetic accounts and mocked provider boundaries only."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, notify, support, support_notifications, whatsapp
from app.db import SessionLocal, engine
from app.main import app
from app.models import Customer, CustomerAccount, Notification, SupportMessage, SupportRequest
from conftest import authenticate_customer
from test_notifications import configured, row, run, transport  # noqa: F401
from test_support import BASE, ADMIN, create, review


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", True)


def setup(client):
    headers = authenticate_customer(client)
    with SessionLocal() as db:
        account = db.scalar(select(CustomerAccount))
        account.email = "support-owner@example.test"
        db.commit()
    return create(client, subject="PRIVATE subject", details="PRIVATE complaint and sensitive case details"), headers


def answer(client, headers, item, **changes):
    result = review(client, headers, item, customer_response="PRIVATE visible response to the complaint", internal_note="PRIVATE team deliberation", **changes)
    assert result.status_code == 200, result.text
    return result.json()


def notices():
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.template_key == "support_reply").order_by(Notification.support_update_revision, Notification.channel)))


def test_reply_and_generic_notices_commit_together_for_account_without_case(client, admin_headers):
    item, _ = setup(client)
    after = answer(client, admin_headers, item)
    rows = notices()
    assert len(rows) == 3 and {n.channel for n in rows} == {"email", "sms", "whatsapp"}
    assert after["customer_update_revision"] == 1 and after["unread_replies"] == 1
    for n in rows:
        assert n.account_id and str(n.support_request_id) == item["id"] and n.support_update_revision == 1
        assert n.customer_id is n.user_id is n.service_request_id is None
        assert n.delivery_status == "queued" and n.params == [config.PUBLIC_SITE_URL.rstrip("/")+"/account/support"]
        assert all(value not in str((n.body, n.params)) for value in ("PRIVATE", "complaint", "support-owner", "9876543210", "Meera"))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Customer)) == 0
        assert db.scalar(select(func.count()).select_from(SupportMessage)) == 2


def test_only_visible_new_replies_queue_not_status_notes_assignment_or_history(client, admin_headers, monkeypatch):
    item, _ = setup(client)
    item = review(client, admin_headers, item, status="in_progress", internal_note="Private status reasoning").json()
    assert notices() == []
    monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", False)
    item = answer(client, admin_headers, item)
    assert notices() == []
    monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", True)
    assert run() == 0 and notices() == []  # No retrospective queue on enable.
    item = answer(client, admin_headers, item)
    assert len(notices()) == 3 and all(n.support_update_revision == 2 for n in notices())
    stale = review(client, admin_headers, {**item, "revision": 1}, customer_response="This stale retry must not create another reply")
    assert stale.status_code == 409 and len(notices()) == 3


def test_failed_review_rolls_back_reply_and_superseding_queue_changes(client, admin_headers, monkeypatch):
    item, _ = setup(client)
    item = answer(client, admin_headers, item)
    def fail(*args, **kwargs): raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(support, "audit", fail)
    result = review(client, admin_headers, item, customer_response="A response that must roll back", internal_note="Private rolled-back note")
    assert result.status_code == 500 and "synthetic audit failure" not in result.text
    assert len(notices()) == 3 and all(n.delivery_status == "queued" for n in notices())
    with SessionLocal() as db:
        assert db.get(SupportRequest, uuid.UUID(item["id"])).customer_update_revision == 1
        assert db.scalar(select(func.count()).select_from(SupportMessage)) == 2


def test_unlinked_account_preferences_cancel_queued_claims_and_do_not_replay(client, admin_headers):
    item, _ = setup(client)
    item = answer(client, admin_headers, item)
    with SessionLocal() as db:
        for n in db.scalars(select(Notification)):
            n.claim_token = uuid.uuid4()
        db.commit()
    url = "/api/v1/account/notification-preferences"
    assert client.put(url, json={"email": False, "sms": False, "whatsapp": False, "revision": 0}).status_code == 200
    assert all(n.delivery_status == "cancelled" and n.error_code == "preference_disabled" and n.claim_token is None for n in notices())
    assert client.put(url, json={"email": True, "sms": True, "whatsapp": True, "revision": 1}).status_code == 200
    assert all(n.delivery_status == "cancelled" for n in notices())
    item = answer(client, admin_headers, item)
    assert len([n for n in notices() if n.delivery_status == "queued"]) == 3


def test_new_reply_coalesces_unsent_notices_and_only_current_read_receipt_cancels_them(client, admin_headers):
    item, _ = setup(client)
    item = answer(client, admin_headers, item)
    item = answer(client, admin_headers, item)
    rows = notices()
    assert len(rows) == 6
    assert all(n.error_code == "support_reply_superseded" for n in rows if n.support_update_revision == 1)
    url = f"{BASE}/{item['id']}/read"
    assert client.post(url, json={"through_revision": 1}).status_code == 200
    assert all(n.delivery_status == "queued" for n in notices() if n.support_update_revision == 2)
    assert client.post(url, json={"through_revision": 2}).status_code == 200
    assert all(n.error_code == "support_reply_read" for n in notices() if n.support_update_revision == 2)
    after = client.get(f"{BASE}/{item['id']}").json()
    assert after["revision"] == item["revision"] and after["reply_due_at"] == item["reply_due_at"]


def test_opted_out_new_notices_are_cancelled_and_missing_email_is_not_invented(client, admin_headers):
    item, _ = setup(client)
    with SessionLocal() as db:
        db.scalar(select(CustomerAccount)).email = None
        db.commit()
    assert client.put("/api/v1/account/notification-preferences", json={"email": False, "sms": False, "whatsapp": False, "revision": 0}).status_code == 200
    answer(client, admin_headers, item)
    assert {n.channel for n in notices()} == {"sms", "whatsapp"}
    assert all(n.delivery_status == "cancelled" and n.error_code == "preference_disabled" for n in notices())


def test_disabling_feature_cancels_unconfigured_pending_channels_without_replay(client, admin_headers, monkeypatch):
    item, _ = setup(client); answer(client, admin_headers, item)
    monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", False)
    monkeypatch.setattr(notify.providers, "enabled", lambda channel: False)
    monkeypatch.setattr(whatsapp, "enabled", lambda: False)
    assert run() == 0
    assert all(n.error_code == "support_notifications_disabled" and n.delivery_status == "cancelled" for n in notices())
    monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", True)
    assert run() == 0 and all(n.delivery_status == "cancelled" for n in notices())


def test_actual_provider_requests_use_generic_text_and_stable_delivery_ids(client, admin_headers, configured, monkeypatch):
    item, _ = setup(client); answer(client, admin_headers, item)
    calls, wa = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "mail-synthetic"} if request.url.host == "api.resend.com" else {"sid": "SMsynthetic", "status": "queued"})
    transport(monkeypatch, handler)
    monkeypatch.setattr(whatsapp, "enabled", lambda: True)
    monkeypatch.setattr(whatsapp, "send_template", lambda *args: wa.append(args) or "wa-synthetic")
    # Defend even if an old producer stored unsafe body/params for the generic notice.
    with SessionLocal() as db:
        for n in db.scalars(select(Notification)): n.body, n.params = "PRIVATE unsafe body", ["PRIVATE unsafe params"]
        db.commit()
    assert run() == 3 and run() == 0
    serialized = str([(str(r.url), r.content.decode()) for r in calls]) + str(wa)
    assert "PRIVATE" not in serialized and item["id"] not in serialized and item["subject"] not in serialized
    mail = next(r for r in calls if r.url.host == "api.resend.com")
    assert json.loads(mail.content)["subject"] == "Homexo Legal: New support reply"
    assert "/account/support" in json.loads(mail.content)["text"]
    sms = next(r for r in calls if r.url.host == "api.twilio.com")
    assert parse_qs(sms.content.decode())["To"] == ["+919876543210"]
    assert wa[0][1:] == ("support_reply", [config.PUBLIC_SITE_URL.rstrip("/")+"/account/support"])
    email = next(n for n in notices() if n.channel == "email")
    assert mail.headers["idempotency-key"] == f"homexo-notification/{email.id}"
    assert all(n.delivery_status == "sent" for n in notices())


@pytest.mark.parametrize("change,reason", [("read", "support_reply_read"), ("disabled", "support_notifications_disabled"), ("contact", "support_recipient_changed"), ("owner", "support_reply_unavailable")])
def test_worker_rechecks_current_support_and_recipient_after_claim(client, admin_headers, configured, monkeypatch, change, reason):
    item, _ = setup(client); answer(client, admin_headers, item)
    with SessionLocal() as db:
        for n in db.scalars(select(Notification).where(Notification.channel != "email")): n.delivery_status = "cancelled"
        db.commit()
    original, calls = support_notifications.cancellation_reason, []
    def check(db, notification):
        calls.append(notification.id)
        if len(calls) == 2:
            if change == "read":
                assert client.post(f"{BASE}/{item['id']}/read", json={"through_revision": 1}).status_code == 200
            elif change == "disabled": monkeypatch.setattr(config, "SUPPORT_REPLY_NOTIFICATIONS_ENABLED", False)
            else:
                with SessionLocal() as other:
                    account = other.scalar(select(CustomerAccount))
                    if change == "contact": account.email = "new-owner@example.test"
                    else:
                        stranger = CustomerAccount(phone_normalized="9999900002"); other.add(stranger); other.flush()
                        other.get(Notification, notification.id).account_id = stranger.id
                    other.commit()
                db.refresh(notification)
        return original(db, notification)
    monkeypatch.setattr(support_notifications, "cancellation_reason", check)
    monkeypatch.setattr(notify.providers, "send_email", lambda *args: pytest.fail("Obsolete support notice reached the provider"))
    assert run() == 0 and len(calls) == 2
    email = next(n for n in notices() if n.channel == "email")
    assert email.delivery_status == "cancelled" and email.error_code == reason


def test_other_accounts_and_staff_cannot_clear_notifications_by_reading(client, admin_headers, agent):
    item, _ = setup(client); answer(client, admin_headers, item)
    url = f"{BASE}/{item['id']}/read"
    assert client.post(url, headers=admin_headers, json={"through_revision": 1}).status_code == 401
    assert client.post(url, headers=agent["headers"], json={"through_revision": 1}).status_code == 401
    authenticate_customer(client, "9999900002")
    assert client.post(url, json={"through_revision": 1}).status_code == 404
    assert client.put("/api/v1/account/notification-preferences", json={"email": False, "sms": False, "whatsapp": False, "revision": 0}).status_code == 200
    assert all(n.delivery_status == "queued" for n in notices())


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent account/request serialization requires PostgreSQL")
def test_simultaneous_review_retries_queue_one_revision_only(client, admin_headers):
    item, _ = setup(client)
    barrier = Barrier(2)
    def send(_):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            return review(second, admin_headers, item, customer_response="One verified response after concurrency").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, range(2))) == [200, 409]
    assert len(notices()) == 3 and all(n.support_update_revision == 1 for n in notices())
