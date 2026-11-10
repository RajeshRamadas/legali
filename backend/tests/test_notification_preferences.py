"""Preference tests use mocked provider boundaries and never send messages."""
import concurrent.futures
import threading
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, notification_preferences as preferences, notify, whatsapp
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, Customer, CustomerNotificationPreference, Notification, ServiceRequest, User, utcnow
from conftest import authenticate_customer
from test_notifications import configured, queue, row, run  # noqa: F401

BASE = "/api/v1/account/notification-preferences"


def save(client, revision=0, **values):
    return client.put(BASE, json={"email": False, "sms": False, "whatsapp": False, "revision": revision, **values})


def scope(client, raise_ticket):
    number = raise_ticket()
    with SessionLocal() as db:
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        customer_id = ticket.customer_id
        # Isolate worker tests from alerts created with the synthetic case.
        for n in db.scalars(select(Notification)):
            n.delivery_status = "cancelled"
        db.commit()
    return customer_id


def test_defaults_preserve_existing_behavior_without_writing_or_exposing_account_data(client):
    authenticate_customer(client)
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"email": True, "sms": True, "whatsapp": True, "revision": 0, "updated_at": None}
    assert "no-store" in response.headers["cache-control"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CustomerNotificationPreference)) == 0


def test_saved_choices_are_private_and_noop_save_does_not_duplicate_history(client, admin_headers):
    assert client.get(BASE).status_code == 401
    assert save(client).status_code == 401
    assert client.get(BASE, headers=admin_headers).status_code == 401
    authenticate_customer(client)
    saved = save(client, sms=True)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1 and saved.json()["updated_at"]
    assert "no-store" in saved.headers["cache-control"]
    assert save(client, 1, sms=True).json() == saved.json()
    assert client.get(BASE).json() == saved.json()
    authenticate_customer(client, "9999900002")
    assert client.get(BASE).json()["revision"] == 0
    with SessionLocal() as db:
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "notification.preferences_changed")))
        assert len(audits) == 1
        assert audits[0].metadata_ == {"source": "customer", "channels": {"email": False, "sms": True, "whatsapp": False}, "revision": 1}
        assert "98765" not in str(audits[0].metadata_)


@pytest.mark.parametrize("change", [{"email": "false"}, {"sms": 0}, {"whatsapp": None}, {"revision": True}, {"revision": -1}, {"account_id": "other"}])
def test_choices_are_strict_and_cannot_select_another_account(client, change):
    authenticate_customer(client)
    assert save(client, **change).status_code == 422
    assert client.get(BASE).json()["revision"] == 0


def test_all_fields_are_required_and_stale_changes_do_not_override_another_device(client):
    authenticate_customer(client)
    assert client.put(BASE, json={"email": False, "revision": 0}).status_code == 422
    assert save(client).status_code == 200
    stale = save(client, email=True)
    assert stale.status_code == 409
    assert client.get(BASE).json()["email"] is False
    assert save(client, 1, email=True).json()["revision"] == 2


def test_save_cancels_only_owned_customer_channels_including_future_and_claimed_rows(client, raise_ticket, agent):
    owner = scope(client, raise_ticket)
    with SessionLocal() as db:
        alias = Customer(full_name="Same verified phone", phone_normalized="9876543210")
        other = Customer(full_name="Other customer", phone_normalized="9999900002")
        db.add_all([alias, other]); db.commit()
        alias_id, other_id = alias.id, other.id
    future = queue(customer_id=owner, send_after=utcnow()+timedelta(days=2))
    claimed = queue("sms", customer_id=alias_id, claim_token=uuid.uuid4(), processing_until=utcnow()+timedelta(minutes=5))
    accepted = queue(customer_id=owner, delivery_status="sent", provider_reference="accepted")
    unrelated = queue(customer_id=other_id)
    staff = queue(customer_id=owner, user_id=uuid.UUID(agent["id"]))
    in_app = queue("in_app", customer_id=owner)
    assert save(client).status_code == 200
    for identifier in (future, claimed):
        assert row(identifier).delivery_status == "cancelled" and row(identifier).error_code == "preference_disabled"
        assert row(identifier).claim_token is None and row(identifier).processing_until is None
    assert row(accepted).delivery_status == "sent" and row(accepted).provider_reference == "accepted"
    assert all(row(identifier).delivery_status == "queued" for identifier in (unrelated, staff, in_app))
    assert save(client, 1, email=True, sms=True, whatsapp=True).status_code == 200
    assert row(future).delivery_status == "cancelled"  # No replay after opt-in.


def test_new_case_and_consultation_alerts_respect_preferences_without_suppressing_staff(client, raise_ticket, admin_headers, agent):
    scope(client, raise_ticket)
    with SessionLocal() as db:
        db.get(User, uuid.UUID(agent["id"])).phone = "+919999900003"
        db.commit()
    assert save(client).status_code == 200
    number = raise_ticket()
    start = (utcnow()+timedelta(hours=48)).isoformat()
    response = client.post(f"/api/v1/admin/tickets/{number}/meetings", headers=admin_headers,
        json={"lawyer_id": agent["id"], "starts_at": start, "meet_link": "https://meet.google.com/fixture-link"})
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        alerts = list(db.scalars(select(Notification).where(Notification.service_request_id == ticket.id)))
        customer_alerts = [n for n in alerts if n.customer_id and not n.user_id]
        assert {n.channel for n in customer_alerts} == {"email", "sms", "whatsapp"}
        assert all(n.delivery_status == "cancelled" and n.error_code == "preference_disabled" for n in customer_alerts)
        assert any(n.user_id and n.delivery_status == "queued" for n in alerts)


@pytest.mark.parametrize("channel", ["email", "sms", "whatsapp"])
def test_worker_blocks_notifications_inserted_after_save_even_if_queue_producer_is_old(client, raise_ticket, configured, monkeypatch, channel):
    owner = scope(client, raise_ticket)
    assert save(client).status_code == 200
    monkeypatch.setattr(notify.providers, "enabled", lambda channel: True)
    monkeypatch.setattr(whatsapp, "enabled", lambda: True)
    monkeypatch.setattr(notify.providers, "send_email", lambda *args: pytest.fail("Opted-out customer must not receive email"))
    monkeypatch.setattr(notify.providers, "send_sms", lambda *args: pytest.fail("Opted-out customer must not receive SMS"))
    monkeypatch.setattr(whatsapp, "send_template", lambda *args: pytest.fail("Opted-out customer must not receive WhatsApp"))
    identifier = queue(channel, customer_id=owner)
    assert run() == 0
    assert row(identifier).error_code == "preference_disabled" and row(identifier).attempts == 0


def test_worker_rechecks_choices_after_claim_and_ignores_stale_identity_map(client, raise_ticket, configured, monkeypatch):
    owner = scope(client, raise_ticket)
    assert save(client, email=True, sms=True, whatsapp=True).status_code == 200
    identifier = queue(customer_id=owner)
    original, calls = notify.delivery_allowed, []
    def check(db, notification):
        calls.append(notification.id)
        if len(calls) == 2:
            assert save(client, 1).status_code == 200
        return original(db, notification)
    monkeypatch.setattr(notify, "delivery_allowed", check)
    monkeypatch.setattr(notify.providers, "send_email", lambda *args: pytest.fail("Opt-out after claim must be respected"))
    assert run() == 0 and len(calls) == 2
    assert row(identifier).delivery_status == "cancelled"
    with SessionLocal() as db:
        pref = db.scalar(select(CustomerNotificationPreference))
        assert save(client, 2, email=True).status_code == 200
        assert pref.email is False  # Deliberately stale model instance.
        assert preferences.delivery_allowed(db, db.get(Notification, identifier)) is True


def test_sign_in_codes_are_available_when_whatsapp_alerts_are_off(client, monkeypatch):
    authenticate_customer(client)
    assert save(client).status_code == 200
    calls = []
    monkeypatch.setattr(whatsapp, "enabled", lambda: True)
    monkeypatch.setattr(whatsapp, "send_template", lambda *args, **kwargs: calls.append((args, kwargs)))
    response = client.post("/api/v1/account/login/start", json={"phone": "9876543210"})
    assert response.status_code == 200 and response.json()["channel"] == "whatsapp"
    assert len(calls) == 1 and calls[0][0][1] == config.LOGIN_CODE_TEMPLATE


def test_preferences_use_shared_read_and_write_budgets(client, monkeypatch):
    authenticate_customer(client)
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(BASE).status_code == 200 and client.get(BASE).status_code == 429
    monkeypatch.setattr(config, "API_WRITES_PER_MINUTE", 1)
    assert save(client).status_code == 200 and save(client, 1, email=True).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Independent row locking requires PostgreSQL")
def test_concurrent_first_saves_serialize_and_one_stale_device_is_rejected(client):
    headers = authenticate_customer(client)
    barrier = threading.Barrier(2)
    def send(enabled):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            return second.put(BASE, headers=headers, json={"email": enabled, "sms": False, "whatsapp": False, "revision": 0}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(send, (True, False)))
    assert sorted(statuses) == [200, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CustomerNotificationPreference)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "notification.preferences_changed")) == 1
