import concurrent.futures
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import func, select

from app import config, service_availability as availability, tickets
from app.bootstrap import sync_reference_data
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, Customer, ServiceRequest, ServiceType, Notification, IntakeDraft
from conftest import authenticate_customer
from test_intake import start, fill, submit
from test_lawyers import lawyer, _book, _first_slot, CUSTOMER  # noqa: F401

BASE = "/api/v1/admin/services"
SLUG = "title-verification"
PRIVATE_REASON = "Pilot capacity requires a smaller service scope."


def change(client, headers, slug=SLUG, revision=1, paused=True, **extra):
    return client.patch(f"{BASE}/{slug}", headers=headers,
        json={"revision": revision, "paused": paused, "confirmed": True, "reason": PRIVATE_REASON, **extra})


def totals():
    with SessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(model)) for model in (Customer, ServiceRequest, Notification))


def test_only_admin_can_read_or_change_availability_and_private_history(client, admin_headers, agent):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=agent["headers"]).status_code == 403
    authenticate_customer(client)
    assert client.get(BASE).status_code == 401
    assert change(client, agent["headers"]).status_code == 403
    response = change(client, admin_headers)
    assert response.status_code == 200 and response.json()["revision"] == 2
    assert "no-store" in response.headers["cache-control"]
    history = client.get(f"{BASE}/{SLUG}/history", headers=admin_headers).json()
    assert history["items"][0]["reason"] == PRIVATE_REASON and history["items"][0]["actor"] == "Meera Admin"
    assert client.get(f"{BASE}/{SLUG}/history").status_code == 401
    public = client.get("/api/v1/services")
    assert PRIVATE_REASON not in public.text
    assert SLUG not in {item["slug"] for item in public.json()["items"]}
    assert client.get(f"/api/v1/services/{SLUG}").status_code == 404


@pytest.mark.parametrize("extra", [{"paused": 1}, {"revision": True}, {"confirmed": False}, {"confirmed": "true"}, {"reason": "          "}, {"unknown": True}])
def test_changes_require_strict_reviewed_payload(client, admin_headers, extra):
    assert change(client, admin_headers, **extra).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(ServiceType).where(ServiceType.slug == SLUG)).availability_revision == 1


def test_pause_and_resume_are_revision_checked_and_survive_reference_sync(client, admin_headers):
    before = client.get(f"/api/v1/services/{SLUG}").json()
    assert change(client, admin_headers).status_code == 200
    assert change(client, admin_headers).status_code == 409
    assert change(client, admin_headers, paused=False).status_code == 409
    with SessionLocal() as db:
        sync_reference_data(db)
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG))
        assert service.is_active and service.intake_paused and service.availability_revision == 2
    assert change(client, admin_headers, revision=2, paused=False).json()["revision"] == 3
    assert client.get(f"/api/v1/services/{SLUG}").json() == before
    assert client.get("/api/v1/services").headers["cache-control"] == "no-store"
    history = client.get(f"{BASE}/{SLUG}/history", headers=admin_headers).json()
    assert history["total"] == 2 and [item["paused"] for item in history["items"]] == [False, True]
    assert client.get(f"{BASE}/{SLUG}/history?page=2", headers=admin_headers).json()["items"] == []
    assert client.get(f"{BASE}/{SLUG}/history?page=10001", headers=admin_headers).status_code == 422


def test_retired_and_unknown_services_cannot_be_reactivated(client, admin_headers):
    with SessionLocal() as db:
        db.add(ServiceType(slug="retired-fixture", name="Retired", category="Fixture", description="Historical service", is_active=False))
        db.commit()
    assert change(client, admin_headers, slug="retired-fixture").status_code == 409
    assert change(client, admin_headers, slug="unknown").status_code == 404
    assert client.get(f"{BASE}/unknown/history", headers=admin_headers).status_code == 404


@pytest.mark.parametrize("source", ["website", "mobile", "chat"])
def test_paused_new_requests_have_no_customer_case_or_notification_side_effects(client, admin_headers, source):
    assert change(client, admin_headers).status_code == 200
    before = totals()
    response = client.post("/api/v1/tickets", json={"customer_name": "Synthetic Customer", "contact": "+919999900001",
        "property_type": "apartment", "service_slug": SLUG, "location": "Synthetic city", "source": source})
    assert response.status_code == 409 and "temporarily" in response.json()["detail"]
    assert totals() == before


def test_saved_draft_answers_survive_pause_and_can_submit_after_resume(client, admin_headers):
    authenticate_customer(client)
    draft = fill(client, start(client, service_slug=SLUG))
    assert change(client, admin_headers).status_code == 200
    loaded = client.get(f"/api/v1/intake/drafts/{draft['id']}").json()
    assert loaded["answers"] == draft["answers"] and loaded["service_available"] is False
    before = totals()
    assert submit(client, draft).status_code == 409
    assert totals() == before
    with SessionLocal() as db:
        assert db.get(IntakeDraft, uuid.UUID(draft["id"])).answers == draft["answers"]
    assert client.post("/api/v1/intake/drafts", json={"service_slug": SLUG,"notice_version": draft["notice"]["version"],"consent":True}).status_code == 409
    fresh = start(client)
    assert SLUG not in {option["value"] for option in fresh["questions"][0]["options"]}
    assert change(client, admin_headers, revision=2, paused=False).status_code == 200
    created = submit(client, draft)
    assert created.status_code == 200
    assert change(client, admin_headers, revision=3).status_code == 200
    assert submit(client, draft).json() == created.json()  # Existing submissions remain idempotent.


def test_existing_case_tracking_and_replies_work_while_service_is_paused(client, raise_ticket, admin_headers):
    number = raise_ticket(service_slug=SLUG)
    assert change(client, admin_headers).status_code == 200
    assert client.get(f"/api/v1/account/requests/{number}").status_code == 200
    assert client.post("/api/v1/tickets/messages", json={"ticket_number":number,"contact":"9876543210","message":"Please keep working on my existing case."}).status_code == 201


def test_consultation_pause_blocks_new_bookings_but_preserves_existing_booking_changes(client, lawyer, admin_headers):
    booking = _book(client, lawyer["slug"]).json()
    assert change(client, admin_headers, slug="advocate-consultation").status_code == 200
    before = totals()
    response = _book(client, lawyer["slug"])
    assert response.status_code == 409 and totals() == before
    assert client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()["booking_paused"] is True
    assert client.get("/api/v1/lawyers").json()["items"][0]["next_available"] is None
    ref = {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"]}
    moved = client.post("/api/v1/bookings/reschedule", json={**ref,"starts_at":_first_slot(client,lawyer["slug"],skip=2)})
    assert moved.status_code == 200, moved.text
    assert client.post("/api/v1/bookings/cancel",json=ref).status_code == 200


def test_assistant_does_not_offer_a_paused_service(client, admin_headers):
    assert change(client, admin_headers).status_code == 200
    response = client.post("/api/v1/chat", json={"message":"title verification"})
    assert response.status_code == 200
    assert response.json()["service"] is None and response.json()["action"] is None
    assert "temporarily" in response.json()["reply"]


def test_shared_budgets_apply(client, admin_headers, monkeypatch):
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE,headers=admin_headers).status_code == 200
    assert client.get(BASE,headers=admin_headers).status_code == 429
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    assert change(client,admin_headers).status_code == 200
    assert change(client,admin_headers,revision=2,paused=False).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql",reason="Shared admission locks require PostgreSQL")
def test_pause_waits_for_an_already_admitted_transaction_then_rejects_later_work(client,admin_headers):
    with SessionLocal() as db:
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG))
        availability.admit_new_request(db,service)
        entered = threading.Event()
        def pause():
            with TestClient(app) as second:
                entered.set()
                return change(second,admin_headers).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pause)
            try:
                assert entered.wait(10)
                with pytest.raises(concurrent.futures.TimeoutError): future.result(timeout=0.3)
            finally: db.commit()
            assert future.result(timeout=10) == 200
        with pytest.raises(HTTPException) as error: availability.admit_new_request(db,service)
        assert error.value.status_code == 409


@pytest.mark.skipif(engine.dialect.name != "postgresql",reason="Lock ordering requires PostgreSQL")
def test_booking_admission_precedes_the_lawyer_lock_to_avoid_audit_foreign_key_deadlocks(client,lawyer,monkeypatch):
    from app import meetings, lawyers
    entered, admission_entered = threading.Event(), threading.Event()
    original = meetings.lock_lawyer
    admit = lawyers.admit_new_request
    def admission(db,service):
        admission_entered.set()
        return admit(db,service)
    monkeypatch.setattr(lawyers,"admit_new_request",admission)
    def lock(db,identifier):
        entered.set()
        return original(db,identifier)
    monkeypatch.setattr(meetings,"lock_lawyer",lock)
    slot = _first_slot(client,lawyer["slug"])
    with SessionLocal() as db:
        db.scalar(select(ServiceType).where(ServiceType.slug == "advocate-consultation").with_for_update())
        def book():
            with TestClient(app) as second:
                return second.post(f"/api/v1/lawyers/{lawyer['slug']}/bookings",json={"starts_at":slot,**CUSTOMER}).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(book)
            try:
                assert admission_entered.wait(10)
                with pytest.raises(concurrent.futures.TimeoutError): future.result(timeout=0.3)
                assert not entered.is_set()
            finally: db.commit()
            assert future.result(timeout=10) == 201
            assert entered.is_set()
