import concurrent.futures
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app import config, lawyers, meetings
from app.db import SessionLocal, engine
from app.models import AuditLog, Customer, LawyerTimeOff, Meeting, Notification, ServiceRequest, User
from test_lawyers import lawyer, _first_slot, _book, CUSTOMER

BASE = "/api/v1/admin/time-off"


def payload(start=None, **changes):
    start = start or (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    return {"submission_key": str(uuid.uuid4()), "starts_at": start.isoformat(),
        "ends_at": (start+timedelta(hours=2)).isoformat(), "reason": "Private planned absence", "confirmed": True, **changes}


def test_scope_private_history_strict_validation_and_rate_budgets(client, lawyer, admin_headers, monkeypatch):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE).headers["cache-control"] == "private, no-store"
    own = client.get(BASE, headers=lawyer["headers"])
    assert own.status_code == 200 and own.json()["total"] == 0
    admin_id = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    assert client.get(BASE, params={"user_id": admin_id}, headers=lawyer["headers"]).status_code == 403
    for changed in ({"confirmed": "true"}, {"confirmed": False}, {"reason": "          "}, {"extra": 1}, {"ends_at": datetime.now(timezone.utc).isoformat()}, {"starts_at": "2030-01-01T09:00:00"}):
        assert client.post(BASE, headers=lawyer["headers"], json=payload(**changed)).status_code == 422
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(BASE, headers=lawyer["headers"]).status_code == 429


def test_idempotent_creation_cancellation_and_no_public_reason(client, lawyer, admin_headers):
    body = payload()
    first = client.post(BASE, headers=lawyer["headers"], json=body)
    assert first.status_code == 201, first.text
    row = first.json()
    assert client.post(BASE, headers=lawyer["headers"], json=body).json()["id"] == row["id"]
    assert client.post(BASE, headers=lawyer["headers"], json={**body, "reason": "Different private operational reason"}).status_code == 409
    assert client.post(BASE, headers=lawyer["headers"], json=payload(datetime.fromisoformat(body["starts_at"]))).status_code == 409
    assert client.post(f"{BASE}/{row['id']}/cancel", headers=admin_headers, json={"confirmed": True}).status_code == 404
    url = f"{BASE}/{row['id']}/cancel?user_id={lawyer['id']}"
    assert client.post(url, headers=admin_headers, json={"confirmed": False}).status_code == 422
    assert client.post(url, headers=admin_headers, json={"confirmed": True}).json()["cancelled_at"]
    assert client.post(url, headers=admin_headers, json={"confirmed": True}).status_code == 200
    assert client.post(BASE, headers=lawyer["headers"], json=body).json()["cancelled_at"]
    assert body["reason"] not in client.get(f"/api/v1/lawyers/{lawyer['slug']}").text
    with SessionLocal() as db:
        events = list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "lawyer_time_off")))
        assert len(events) == 2 and body["reason"] not in str([event.metadata_ for event in events])


def test_offset_normalization_boundary_slots_and_cancel_restores_availability(client, lawyer, monkeypatch):
    now = datetime(2030, 1, 1, 19, tzinfo=timezone.utc)  # 00:30 India, following calendar day.
    monkeypatch.setattr(lawyers, "utcnow", lambda: now)
    monkeypatch.setattr(meetings, "utcnow", lambda: now)
    from app import time_off
    monkeypatch.setattr(time_off, "utcnow", lambda: now)
    first = _first_slot(client, lawyer["slug"])
    assert client.get(f"/api/v1/lawyers/{lawyer['slug']}/slots").headers["cache-control"] == "no-store"
    start = datetime.fromisoformat(first)
    offset = timezone(timedelta(hours=5, minutes=30))
    body = payload(start, starts_at=start.astimezone(offset).isoformat(), ends_at=(start+timedelta(minutes=30)).astimezone(offset).isoformat())
    row = client.post(BASE, headers=lawyer["headers"], json=body)
    assert row.status_code == 201, row.text
    assert datetime.fromisoformat(row.json()["starts_at"]) == start
    assert _first_slot(client, lawyer["slug"]) == (start+timedelta(minutes=30)).isoformat()
    cards = client.get("/api/v1/lawyers").json()["items"]
    assert cards[0]["next_available"]["starts_at"] != first
    with SessionLocal() as db:
        assert db.scalar(select(LawyerTimeOff.starts_at)).replace(tzinfo=timezone.utc) == start
    client.post(f"{BASE}/{row.json()['id']}/cancel", headers=lawyer["headers"], json={"confirmed": True})
    assert _first_slot(client, lawyer["slug"]) == first


def test_blocks_customer_booking_and_staff_schedule_without_side_effects(client, lawyer, admin_headers, raise_ticket):
    slot = datetime.fromisoformat(_first_slot(client, lawyer["slug"]))
    assert client.post(BASE, headers=lawyer["headers"], json=payload(slot)).status_code == 201
    with SessionLocal() as db:
        counts = [db.scalar(select(func.count()).select_from(model)) for model in (ServiceRequest, Customer, Notification)]
    assert _book(client, lawyer["slug"], starts_at=slot.isoformat()).status_code == 409
    with SessionLocal() as db:
        assert counts == [db.scalar(select(func.count()).select_from(model)) for model in (ServiceRequest, Customer, Notification)]
    ticket = raise_ticket()
    response = client.post(f"/api/v1/admin/tickets/{ticket}/meetings", headers=admin_headers,
        json={"starts_at": slot.isoformat(), "lawyer_id": lawyer["id"], "meet_link": "https://meet.example.test/mock"})
    assert response.status_code == 409 and "unavailable" in response.text


def test_existing_meetings_block_time_off_and_moves_respect_blocks(client, lawyer, admin_headers):
    booking = _book(client, lawyer["slug"]).json()
    old = datetime.fromisoformat(booking["meeting"]["starts_at"])
    assert client.post(BASE, headers=lawyer["headers"], json=payload(old)).status_code == 409
    target = datetime.fromisoformat(_first_slot(client, lawyer["slug"], skip=4))
    assert client.post(BASE, headers=lawyer["headers"], json=payload(target)).status_code == 201
    response = client.post("/api/v1/bookings/reschedule", json={"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"], "starts_at": target.isoformat()})
    assert response.status_code == 409
    response = client.patch(f"/api/v1/admin/meetings/{booking['meeting']['id']}", headers=admin_headers, json={"starts_at": target.isoformat()})
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Meeting.starts_at)).replace(tzinfo=timezone.utc) == old


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Independent PostgreSQL row locks")
def test_committing_time_off_serializes_booking_admission(client, lawyer):
    slot = datetime.fromisoformat(_first_slot(client, lawyer["slug"]))
    started = threading.Event()
    def create_booking():
        with SessionLocal() as db:
            started.set()
            profile = db.scalar(select(lawyers.LawyerProfile).where(lawyers.LawyerProfile.user_id == uuid.UUID(lawyer["id"])))
            meetings.lock_lawyer(db, profile.user_id)
            try:
                lawyers._slot_open(db, profile, slot)
                return "admitted"
            except Exception as exc:
                return getattr(exc, "status_code", None)
    with SessionLocal() as db, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        db.scalar(select(User).where(User.id == uuid.UUID(lawyer["id"])).with_for_update(key_share=True))
        db.add(LawyerTimeOff(lawyer_user_id=uuid.UUID(lawyer["id"]), submission_key=uuid.uuid4(), starts_at=slot, ends_at=slot+timedelta(hours=2), reason="Private race test absence"))
        db.flush()
        future = pool.submit(create_booking)
        try:
            assert started.wait(5)
            with pytest.raises(concurrent.futures.TimeoutError): future.result(timeout=0.2)
        finally:
            db.commit()
        assert future.result(timeout=5) == 409


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Independent PostgreSQL FK and row locks")
def test_cross_staff_creator_references_do_not_invert_lawyer_locks(client, lawyer, admin_headers):
    admin_id = uuid.UUID(client.get("/api/v1/auth/me", headers=admin_headers).json()["id"])
    agent_id = uuid.UUID(lawyer["id"])
    barrier = threading.Barrier(2)
    start = datetime.now(timezone.utc) + timedelta(days=2)
    def create(target, creator):
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            meetings.lock_lawyer(db, target)
            barrier.wait(timeout=5)
            db.add(LawyerTimeOff(lawyer_user_id=target, created_by_user_id=creator,
                submission_key=uuid.uuid4(), starts_at=start, ends_at=start+timedelta(hours=1), reason="Synthetic concurrent creator"))
            db.commit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, agent_id, admin_id), pool.submit(create, admin_id, agent_id)]
        for future in futures: future.result(timeout=10)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL meeting admission lock")
def test_time_off_waits_for_admitted_meeting_then_rejects_overlap(client, lawyer):
    start = datetime.fromisoformat(_first_slot(client, lawyer["slug"]))
    body = payload(start)
    entered = threading.Event()
    def block():
        with SessionLocal() as db:
            actor = db.get(User, uuid.UUID(lawyer["id"]))
            entered.set()
            from app.time_off import CreateTimeOff, create_time_off
            try: create_time_off(CreateTimeOff(**body), None, actor, db)
            except Exception as error: return getattr(error, "status_code", None)
    # Use a real booked meeting, then hold its admission owner lock while the time-off writer waits.
    booking = _book(client, lawyer["slug"]).json()
    with SessionLocal() as db, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        meetings.lock_lawyer(db, uuid.UUID(lawyer["id"]))
        future = pool.submit(block)
        try:
            assert entered.wait(5)
            with pytest.raises(concurrent.futures.TimeoutError): future.result(timeout=0.2)
        finally: db.commit()
        assert future.result(timeout=5) == 409
