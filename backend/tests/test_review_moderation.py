import concurrent.futures
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, LawyerReview, LawyerReviewDecision, Meeting, Role, User
from conftest import authenticate_customer
from test_lawyers import CUSTOMER, _book, lawyer  # noqa: F401


def finished_booking(client, lawyer):
    booking = _book(client, lawyer["slug"]).json()
    with SessionLocal() as db:
        meeting = db.get(Meeting, uuid.UUID(booking["meeting"]["id"]))
        meeting.starts_at = datetime.now(timezone.utc) - timedelta(hours=2)
        meeting.ends_at = meeting.starts_at + timedelta(minutes=30)
        meeting.status = "completed"; db.commit()
    ref = {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"]}
    return ref, uuid.UUID(booking["meeting"]["id"])


def submitted(client, lawyer, rating=1, comment="A detailed but critical account of the consultation."):
    ref, meeting_id = finished_booking(client, lawyer)
    response = client.post("/api/v1/bookings/review", json={**ref, "rating": rating, "comment": comment})
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        identifier = db.scalar(select(LawyerReview.id).where(LawyerReview.meeting_id == meeting_id))
    return str(identifier), ref


def decision(revision=1, status="published", **overrides):
    return {"revision": revision, "status": status, "reason": "approved" if status == "published" else "privacy", "note": "Private operational decision note.", "reviewed": True, **overrides}


def test_new_feedback_is_private_and_only_published_reviews_affect_ratings(client, lawyer, admin_headers):
    identifier, ref = submitted(client, lawyer)
    owner = client.post("/api/v1/bookings/lookup", json=ref).json()["review"]
    assert owner["moderation_status"] == "pending" and owner["rating"] == 1
    profile = client.get(f"/api/v1/lawyers/{lawyer['slug']}")
    assert "no-store" in profile.headers["cache-control"] and profile.json()["reviews"] == []
    card = client.get("/api/v1/lawyers", params={"sort": "rating"}).json()["items"][0]
    assert card["rating"] is None and card["review_count"] == 0
    assert client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision()).status_code == 200
    card = client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()
    assert card["rating"] == 1 and card["review_count"] == 1
    assert card["reviews"][0]["comment"] == owner["comment"]
    assert "Private operational" not in str(card) and "moderation_status" not in card["reviews"][0]


def test_hiding_and_republishing_preserve_customer_words_and_private_history(client, lawyer, admin_headers):
    identifier, ref = submitted(client, lawyer, rating=5)
    path = f"/api/v1/admin/reviews/{identifier}"
    for revision, state in ((1, "published"), (2, "hidden"), (3, "published")):
        response = client.patch(path, headers=admin_headers, json=decision(revision, state))
        assert response.status_code == 200, response.text
        card = client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()
        assert card["review_count"] == (0 if state == "hidden" else 1)
        owner = client.post("/api/v1/bookings/lookup", json=ref).json()["review"]
        assert owner["moderation_status"] == state and owner["rating"] == 5
        assert owner["comment"] == "A detailed but critical account of the consultation."
        assert "note" not in owner and "reason" not in owner
    detail = client.get(path, headers=admin_headers)
    assert "no-store" in detail.headers["cache-control"]
    assert [item["revision"] for item in detail.json()["history"]] == [4, 3, 2]
    with SessionLocal() as db:
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "review.moderated")))
        assert len(audits) == 3 and all("Private operational" not in str(item.metadata_) for item in audits)


def test_only_administrators_can_read_and_decide_and_owners_do_not_get_private_notes(client, lawyer, admin_headers):
    identifier, ref = submitted(client, lawyer)
    for path in ("/api/v1/admin/reviews", f"/api/v1/admin/reviews/{identifier}"):
        assert client.get(path).status_code == 401  # Customer session is not a staff session.
        assert client.get(path, headers=lawyer["headers"]).status_code == 403
    assert client.patch(f"/api/v1/admin/reviews/{identifier}", headers=lawyer["headers"], json=decision()).status_code == 403
    authenticate_customer(client, "+919999900002")
    assert client.post("/api/v1/bookings/lookup", json=ref).status_code == 404
    assert client.patch(f"/api/v1/admin/reviews/{identifier}", json=decision()).status_code == 401
    assert client.get("/api/v1/admin/reviews", headers=admin_headers).status_code == 200


@pytest.mark.parametrize("overrides", [
    {"reviewed": False}, {"reviewed": 1}, {"revision": True}, {"revision": 0},
    {"status": "pending"}, {"reason": "privacy"}, {"note": "   "}, {"note": "null\x00character"},
    {"comment": "Administrator rewritten feedback"}, {"rating": 5},
])
def test_decision_requires_explicit_review_reason_and_does_not_allow_text_edits(client, lawyer, admin_headers, overrides):
    identifier, _ = submitted(client, lawyer)
    response = client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision(**overrides))
    assert response.status_code == 422, response.text
    with SessionLocal() as db:
        assert db.get(LawyerReview, uuid.UUID(identifier)).moderation_status == "pending"
        assert db.scalar(select(func.count()).select_from(LawyerReviewDecision)) == 0


def test_stale_and_duplicate_decisions_cannot_overwrite_a_decision(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    path = f"/api/v1/admin/reviews/{identifier}"
    assert client.patch(path, headers=admin_headers, json=decision()).status_code == 200
    assert client.patch(path, headers=admin_headers, json=decision(1, "hidden")).status_code == 409
    assert client.patch(path, headers=admin_headers, json=decision(2)).status_code == 409
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(LawyerReviewDecision)) == 1


def test_a_lawyer_with_administrator_access_cannot_moderate_their_own_profile(client, lawyer):
    identifier, _ = submitted(client, lawyer)
    with SessionLocal() as db:
        person = db.get(User, uuid.UUID(lawyer["id"]))
        person.roles.append(db.scalar(select(Role).where(Role.name == "admin"))); db.commit()
    response = client.patch(f"/api/v1/admin/reviews/{identifier}", headers=lawyer["headers"], json=decision())
    assert response.status_code == 403
    assert "Another administrator" in response.json()["detail"]


def test_queue_search_filters_and_unknown_records_are_bounded(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    path = "/api/v1/admin/reviews"
    queue = client.get(path, headers=admin_headers).json()
    assert queue["counts"] == {"pending": 1, "published": 0, "hidden": 0} and queue["total"] == 1
    assert client.get(path, params={"q": "%"}, headers=admin_headers).json()["total"] == 0
    assert client.get(path, params={"page": 2}, headers=admin_headers).json()["items"] == []
    assert client.get(path, params={"page": 10001}, headers=admin_headers).status_code == 422
    assert client.get(path, params={"status": "invalid"}, headers=admin_headers).status_code == 422
    assert client.get(f"{path}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.patch(f"{path}/{uuid.uuid4()}", headers=admin_headers, json=decision()).status_code == 404
    assert client.patch(f"{path}/{identifier}", headers=admin_headers, json=decision()).status_code == 200
    assert client.get(path, headers=admin_headers).json()["items"] == []
    assert client.get(path, params={"status": "all"}, headers=admin_headers).json()["total"] == 1


def test_moderation_reads_and_writes_consume_shared_budgets(client, lawyer, admin_headers, monkeypatch):
    identifier, _ = submitted(client, lawyer)
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get("/api/v1/admin/reviews", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers).status_code == 429
    with SessionLocal() as db:
        db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config, "API_WRITES_PER_MINUTE", 1)
    assert client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision()).status_code == 200
    assert client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision(2, "hidden")).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent moderation requires independent PostgreSQL sessions")
def test_concurrent_decisions_record_one_revision_and_one_history_entry(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    barrier = threading.Barrier(2)
    def send(state):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            return second.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision(1, state)).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, ("published", "hidden")))
    assert sorted(results) == [200, 409]
    with SessionLocal() as db:
        assert db.get(LawyerReview, uuid.UUID(identifier)).revision == 2
        assert db.scalar(select(func.count()).select_from(LawyerReviewDecision)) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent submissions require PostgreSQL row locks")
def test_concurrent_customer_submissions_create_one_pending_review(client, lawyer):
    ref, _ = finished_booking(client, lawyer)
    headers = {"Authorization": client.headers["Authorization"]}
    barrier = threading.Barrier(2)
    def send(rating):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            return second.post("/api/v1/bookings/review", headers=headers, json={**ref, "rating": rating, "comment": "Concurrent synthetic feedback."}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, (1, 5)))
    assert sorted(results) == [201, 422]
    with SessionLocal() as db:
        rows = list(db.scalars(select(LawyerReview)))
        assert len(rows) == 1 and rows[0].moderation_status == "pending"
