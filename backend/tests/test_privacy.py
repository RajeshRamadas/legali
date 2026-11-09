import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, privacy
from app.db import SessionLocal, engine
from app.main import app
from app.models import AuditLog, PrivacyRequest, ServiceRequest
from conftest import authenticate_customer

BASE = "/api/v1/account/privacy-requests"
ADMIN = "/api/v1/admin/privacy-requests"


def payload(**changes):
    return {"kind": "deletion", "details": "Please review which personal information can be deleted.", "notice_version": privacy.NOTICE_VERSION, "submission_key": str(uuid.uuid4()), **changes}


def send(client, **changes):
    response = client.post(BASE, json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_notice_and_verified_account_boundaries(client, admin_headers, agent):
    assert client.get("/api/v1/privacy/notice").status_code == 200
    assert client.get(BASE).status_code == client.post(BASE, json=payload()).status_code == 401
    assert client.get(BASE, headers=admin_headers).status_code == 401
    for path in (ADMIN, "/api/v1/admin/privacy-retention"):
        assert client.get(path, headers=agent["headers"]).status_code == 403
        assert client.get(path).status_code == 401
    authenticate_customer(client)
    assert client.get(ADMIN).status_code == 401
    created = send(client)
    assert created["status"] == "submitted" and created["revision"] == 1
    assert created["reference"].startswith("PR-")
    assert "internal_note" not in created and "submission_key" not in created
    assert client.get(BASE).headers["cache-control"] == "private, no-store"


def test_owner_isolation_and_owned_case_scope(client, raise_ticket, admin_headers):
    ticket = raise_ticket()
    owner = dict(client.headers)
    created = send(client, ticket_number=ticket.lower())
    authenticate_customer(client, "9123456789")
    assert client.get(BASE).json()["items"] == []
    assert client.post(f"{BASE}/{created['id']}/withdraw", json={"revision": 1}).status_code == 404
    assert client.post(BASE, json=payload(ticket_number=ticket)).status_code == 404
    assert client.get(BASE, headers=owner).json()["items"][0]["ticket_number"] == ticket
    assert client.get(f"{ADMIN}/{created['id']}", headers=admin_headers).status_code == 200


def test_retries_are_idempotent_and_open_duplicates_are_rejected(client):
    authenticate_customer(client)
    data = payload()
    first = client.post(BASE, json=data)
    retry = client.post(BASE, json=data)
    assert first.status_code == 201 and retry.status_code == 200
    assert first.json()["id"] == retry.json()["id"]
    assert client.post(BASE, json={**data, "details": "A different request with an already used submission key."}).status_code == 409
    assert client.post(BASE, json=payload()).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PrivacyRequest)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "privacy.requested")) == 1


def test_notice_validation_and_whitespace_details(client):
    authenticate_customer(client)
    assert client.post(BASE, json=payload(notice_version="old")).status_code == 409
    assert client.post(BASE, json=payload(details=" " * 20)).status_code == 422
    assert client.post(BASE, json=payload(details="Unsupported\x00 details")).status_code == 422
    assert client.post(BASE, json=payload(kind="delete_everything")).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PrivacyRequest)) == 0


def test_daily_limit_survives_withdrawal_and_replays_do_not_create_rows(client, monkeypatch):
    monkeypatch.setattr(config, "PRIVACY_REQUESTS_PER_DAY", 1)
    authenticate_customer(client)
    data = payload()
    created = client.post(BASE, json=data).json()
    assert client.post(f"{BASE}/{created['id']}/withdraw", json={"revision": 1}).status_code == 200
    blocked = client.post(BASE, json=payload())
    assert blocked.status_code == 429 and 1 <= int(blocked.headers["retry-after"]) <= 86400
    assert client.post(BASE, json=data).json()["status"] == "withdrawn"


def test_admin_review_decision_and_private_notes_never_leak_to_customer(client, admin_headers, raise_ticket):
    ticket = raise_ticket()
    created = send(client, ticket_number=ticket)
    path = f"{ADMIN}/{created['id']}"
    assert client.patch(path, headers=admin_headers, json={"revision": 1, "status": "closed"}).status_code == 409
    review = client.patch(path, headers=admin_headers, json={"revision": 1, "status": "in_review", "internal_note": "STAFF ONLY REVIEW", "customer_response": "Your request is under review."})
    assert review.status_code == 200 and review.json()["revision"] == 2
    assert client.patch(path, headers=admin_headers, json={"revision": 1, "status": "in_review"}).status_code == 409
    close = {"revision": 2, "status": "closed", "resolution": "partial", "customer_response": "Some records are retained for the case's applicable retention obligations.", "internal_note": "STAFF ONLY FINAL NOTE"}
    assert client.patch(path, headers=admin_headers, json=close).status_code == 422
    result = client.patch(path, headers=admin_headers, json={**close, "retention_reason": "legal_retention"})
    assert result.status_code == 200 and result.json()["status"] == "closed"
    customer = client.get(BASE)
    assert "STAFF ONLY" not in customer.text and customer.json()["items"][0]["resolution"] == "partial"
    assert client.post(f"{BASE}/{created['id']}/withdraw", json={"revision": 3}).status_code == 409
    assert client.patch(path, headers=admin_headers, json={"revision": 3, "status": "in_review"}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 1
        records = db.scalars(select(AuditLog).where(AuditLog.entity_type == "privacy_request")).all()
        assert len(records) == 3
        assert all("STAFF ONLY" not in str(row.metadata_) and created["details"] not in str(row.metadata_) for row in records)


def test_withdrawal_is_owner_only_terminal_and_versioned(client, admin_headers):
    authenticate_customer(client)
    item = send(client)
    assert client.post(f"{BASE}/{item['id']}/withdraw", json={"revision": 99}).status_code == 409
    withdrawn = client.post(f"{BASE}/{item['id']}/withdraw", json={"revision": 1})
    assert withdrawn.json()["revision"] == 2 and withdrawn.json()["status"] == "withdrawn"
    assert client.post(f"{BASE}/{item['id']}/withdraw", json={"revision": 1}).status_code == 200
    assert client.patch(f"{ADMIN}/{item['id']}", headers=admin_headers, json={"revision": 2, "status": "in_review"}).status_code == 409


def test_admin_queue_masks_phone_omits_details_and_counts_overdue_open_requests(client, admin_headers):
    authenticate_customer(client)
    created = send(client)
    with SessionLocal() as db:
        item = db.get(PrivacyRequest, uuid.UUID(created["id"]))
        item.due_at = privacy.utcnow() - timedelta(days=1)
        db.commit()
    response = client.get(ADMIN, headers=admin_headers)
    assert response.status_code == 200 and response.json()["overdue"] == 1
    assert "9876543210" not in response.text and created["details"] not in response.text
    assert response.json()["items"][0]["customer"]["phone_last4"] == "3210"
    assert "details" not in response.json()["items"][0]
    assert client.get(ADMIN + "?status=closed", headers=admin_headers).json()["total"] == 0
    assert client.get(ADMIN + "?page_size=51", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/admin/privacy-retention", headers=admin_headers).json()["eligible_anonymous_chats"] == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Account/row serialization requires PostgreSQL")
def test_concurrent_replays_create_one_request_and_one_audit(client):
    authenticate_customer(client)
    data = payload()
    barrier = Barrier(2)
    def create(_):
        barrier.wait(timeout=10)
        return client.post(BASE, json=data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(create, range(2)))
    assert sorted(reply.status_code for reply in replies) == [200, 201]
    assert replies[0].json()["id"] == replies[1].json()["id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PrivacyRequest)) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent admin/customer updates require PostgreSQL")
def test_concurrent_decision_and_withdrawal_preserve_one_terminal_outcome(client, admin_headers):
    authenticate_customer(client)
    item = send(client)
    path = f"{ADMIN}/{item['id']}"
    assert client.patch(path, headers=admin_headers, json={"status": "in_review", "revision": 1}).status_code == 200
    barrier = Barrier(2)
    def finish(which):
        barrier.wait(timeout=10)
        if which:
            return client.patch(path, headers=admin_headers, json={"status": "closed", "revision": 2, "resolution": "fulfilled", "customer_response": "The agreed action has been completed and recorded."})
        return client.post(f"{BASE}/{item['id']}/withdraw", json={"revision": 2})
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(finish, [False, True]))
    assert sorted(reply.status_code for reply in replies) == [200, 409]
    with SessionLocal() as db:
        item = db.get(PrivacyRequest, uuid.UUID(item["id"]))
        assert item.status in ("closed", "withdrawn") and item.revision == 3


def test_authenticated_general_chats_are_owned_across_networks(client, monkeypatch):
    from app import chat
    monkeypatch.setattr(chat.assistant, "answer", lambda *args: None)
    headers = authenticate_customer(client)
    conversation = client.post("/api/v1/chat", json={"message": "hello"}).json()["conversation_id"]
    with TestClient(app, client=("198.51.100.10", 10)) as another_network:
        assert another_network.post("/api/v1/chat", headers=headers, json={"message": "hello again", "conversation_id": conversation}).status_code == 200
    authenticate_customer(client, "9123456789")
    assert client.post("/api/v1/chat", json={"message": "hello", "conversation_id": conversation}).status_code == 404


def test_anonymous_chat_id_alone_does_not_allow_access_from_another_client(client, monkeypatch):
    from app import chat
    monkeypatch.setattr(chat.assistant, "answer", lambda *args: None)
    conversation = client.post("/api/v1/chat", json={"message": "hello"}).json()["conversation_id"]
    with TestClient(app, client=("198.51.100.10", 10)) as other:
        assert other.post("/api/v1/chat", json={"message": "hello", "conversation_id": conversation}).status_code == 404
