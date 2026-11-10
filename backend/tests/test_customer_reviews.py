import concurrent.futures
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app import config
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, LawyerReview, LawyerReviewDecision
from conftest import authenticate_customer
from test_lawyers import lawyer  # noqa: F401
from test_review_moderation import decision, submitted

BASE = "/api/v1/account/reviews"


def withdraw(client, identifier):
    return client.post(f"{BASE}/{identifier}/withdraw", json={"confirmed": True})


@pytest.mark.parametrize("initial", ["pending", "published", "hidden"])
def test_owner_withdraws_from_each_state_without_losing_feedback_or_history(client, lawyer, admin_headers, initial):
    identifier, ref = submitted(client, lawyer)
    if initial != "pending":
        assert client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision(status=initial)).status_code == 200
    response = withdraw(client, identifier)
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["status"] == "withdrawn" and row["withdrawn_at"]
    assert row["rating"] == 1 and row["comment"] == "A detailed but critical account of the consultation."
    assert "no-store" in response.headers["cache-control"]
    public = client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()
    assert public["reviews"] == [] and public["review_count"] == 0 and public["rating"] is None
    booking = client.post("/api/v1/bookings/lookup", json=ref).json()
    assert booking["review"]["moderation_status"] == "withdrawn" and not booking["can_review"]
    detail = client.get(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers).json()
    assert detail["review"]["status"] == "withdrawn"
    assert len(detail["history"]) == (0 if initial == "pending" else 1)
    with SessionLocal() as db:
        record = db.get(LawyerReview, uuid.UUID(identifier))
        assert record.moderation_status == "hidden" and record.withdrawn_at is not None
        assert record.publication_status == "withdrawn"


def test_withdrawal_is_idempotent_and_logs_no_review_text(client, lawyer):
    identifier, _ = submitted(client, lawyer)
    first = withdraw(client, identifier).json()
    assert withdraw(client, identifier).json() == first
    with SessionLocal() as db:
        row = db.get(LawyerReview, uuid.UUID(identifier))
        assert row.revision == 2
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "review.withdrawn")))
        assert len(audits) == 1
        assert audits[0].metadata_["source"] == "customer"
        assert "A detailed" not in str(audits[0].metadata_) and "comment" not in audits[0].metadata_


def test_customer_session_and_ownership_are_required_even_for_already_withdrawn_rows(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    assert len(client.get(BASE).json()["items"]) == 1
    assert client.get(BASE, headers=lawyer["headers"]).status_code == 401
    assert client.post(f"{BASE}/{identifier}/withdraw", headers=admin_headers, json={"confirmed": True}).status_code == 401
    withdraw(client, identifier)
    authenticate_customer(client, "+919999900002")
    assert client.get(BASE).json()["items"] == []
    unknown = withdraw(client, str(uuid.uuid4()))
    other = withdraw(client, identifier)
    assert unknown.status_code == other.status_code == 404 and unknown.json() == other.json()


@pytest.mark.parametrize("payload", [{}, {"confirmed": False}, {"confirmed": 1}, {"confirmed": "true"}, {"confirmed": True, "account_id": "another-account"}])
def test_withdrawal_requires_explicit_strict_confirmation(client, lawyer, payload):
    identifier, _ = submitted(client, lawyer)
    response = client.post(f"{BASE}/{identifier}/withdraw", json=payload)
    assert response.status_code == 422
    with SessionLocal() as db: assert db.get(LawyerReview, uuid.UUID(identifier)).withdrawn_at is None


def test_withdrawn_feedback_cannot_be_republished_by_current_or_legacy_updates(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    withdraw(client, identifier)
    response = client.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision(2))
    assert response.status_code == 409 and "withdrew" in response.json()["detail"]
    # The database guard also protects an older application that lacks the new API guard.
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(update(LawyerReview).where(LawyerReview.id == uuid.UUID(identifier)).values(moderation_status="published"))
            db.commit()
        db.rollback()
        assert db.get(LawyerReview, uuid.UUID(identifier)).publication_status == "withdrawn"


def test_owner_listing_and_administrator_filters_keep_withdrawal_distinct(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    response = client.get(BASE)
    assert "no-store" in response.headers["cache-control"]
    row = response.json()["items"][0]
    assert set(row) == {"id", "lawyer_name", "ticket_number", "rating", "comment", "created_at", "status", "withdrawn_at"}
    assert client.get(BASE, params={"page": 2}).json()["items"] == []
    assert client.get(BASE, params={"page": 10001}).status_code == 422
    withdraw(client, identifier)
    withdrawn = client.get("/api/v1/admin/reviews", headers=admin_headers, params={"status": "withdrawn"}).json()
    assert withdrawn["total"] == 1 and withdrawn["counts"]["withdrawn"] == 1
    hidden = client.get("/api/v1/admin/reviews", headers=admin_headers, params={"status": "hidden"}).json()
    assert hidden["total"] == 0 and hidden["counts"]["hidden"] == 0


def test_reads_and_withdrawals_use_shared_api_budgets(client, lawyer, monkeypatch):
    identifier, _ = submitted(client, lawyer)
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(BASE).status_code == 200
    assert client.get(BASE).status_code == 429
    monkeypatch.setattr(config, "API_WRITES_PER_MINUTE", 1)
    assert withdraw(client, identifier).status_code == 200
    assert withdraw(client, identifier).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Independent row locking requires PostgreSQL")
def test_simultaneous_withdrawals_record_one_withdrawal(client, lawyer):
    identifier, _ = submitted(client, lawyer)
    headers = {"Authorization": client.headers["Authorization"]}
    barrier = threading.Barrier(2)
    def send(_):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            return second.post(f"{BASE}/{identifier}/withdraw", headers=headers, json={"confirmed": True})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: responses = list(pool.map(send, (1, 2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "review.withdrawn")) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent moderation requires PostgreSQL")
def test_withdrawal_wins_over_a_simultaneous_moderator_publication(client, lawyer, admin_headers):
    identifier, _ = submitted(client, lawyer)
    owner = {"Authorization": client.headers["Authorization"]}
    barrier = threading.Barrier(2)
    def send(kind):
        with TestClient(app) as second:
            barrier.wait(timeout=10)
            if kind == "owner": return second.post(f"{BASE}/{identifier}/withdraw", headers=owner, json={"confirmed": True}).status_code
            return second.patch(f"/api/v1/admin/reviews/{identifier}", headers=admin_headers, json=decision()).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(send, ("owner", "moderator")))
    assert results[0] == 200 and results[1] in (200, 409)
    with SessionLocal() as db: assert db.get(LawyerReview, uuid.UUID(identifier)).publication_status == "withdrawn"
    assert client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()["review_count"] == 0
