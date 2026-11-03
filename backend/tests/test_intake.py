import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import config, intake, tickets
from app.db import SessionLocal
from app.models import Consent, Conversation, IntakeDraft, Notification, ServiceRequest, ServiceType
from conftest import authenticate_customer

BASE = "/api/v1/intake/drafts"
DEFAULTS = {"service_slug": "title-verification", "goal": "Please check title before I buy this property.", "property_type": "apartment",
    "location": "Whitefield, Bengaluru", "state": "Karnataka", "state_name": "Tamil Nadu", "role": "buyer",
    "transaction": "purchase", "seller_capacity": "owner", "development": "resale", "granted_land": "unknown",
    "survey_number": "45/2", "village": "Example village", "taluk": "Example taluk", "property_id_or_pid": "PID-123",
    "district": "Bengaluru", "available_documents": "Sale deed and EC", "customer_name": "Example Customer", "email": "", "contact_preference": "phone"}


def start(client, **overrides):
    response = client.post(BASE, json={"consent": True, "notice_version": intake.NOTICE_VERSION, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def answer(client, draft, key, value):
    response = client.patch(BASE + "/" + draft["id"], json={"revision": draft["revision"], "key": key, "value": value})
    assert response.status_code == 200, response.text
    return response.json()


def fill(client, draft, **overrides):
    for _ in range(30):
        if not draft["next_question"]:
            return draft
        key = draft["next_question"]
        draft = answer(client, draft, key, {**DEFAULTS, **overrides}[key])
    pytest.fail("Intake did not finish")


def submit(client, draft, **overrides):
    return client.post(BASE + "/" + draft["id"] + "/submit", json={"revision": draft["revision"], "consent": True, "notice_version": intake.NOTICE_VERSION, **overrides})


def test_drafts_require_verified_customer_and_saving_consent(client, admin_headers):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=admin_headers).status_code == 401
    authenticate_customer(client)
    assert client.post(BASE, json={"consent": False, "notice_version": intake.NOTICE_VERSION}).status_code == 422
    assert client.post(BASE, json={"consent": "true", "notice_version": intake.NOTICE_VERSION}).status_code == 422
    assert client.post(BASE, json={"consent": True, "notice_version": "old"}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IntakeDraft)) == 0
    draft = start(client)
    assert draft["next_question"] == "service_slug" and draft["answers"] == {}
    with SessionLocal() as db:
        stored = db.get(IntakeDraft, uuid.UUID(draft["id"]))
        assert stored.saving_consented_at and stored.saving_notice_version == intake.NOTICE_VERSION


def test_answers_resume_from_another_session_without_exposing_other_accounts(client):
    headers = authenticate_customer(client)
    draft = start(client, service_slug="title-verification")
    draft = answer(client, draft, "goal", DEFAULTS["goal"])
    authenticate_customer(client, "9123456789")
    assert client.get(BASE).json()["items"] == []
    path = BASE + "/" + draft["id"]
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"revision": draft["revision"], "key": "goal", "value": "A different goal"}).status_code == 404
    assert submit(client, draft).status_code == 404
    assert client.delete(path).status_code == 404
    response = client.get(path, headers=headers)
    assert response.json()["answers"]["goal"] == DEFAULTS["goal"]
    assert response.json()["next_question"] == "property_type"
    assert response.headers["cache-control"] == "private, no-store"


def test_current_question_validation_and_stale_edit_protection(client):
    authenticate_customer(client)
    draft = start(client)
    path = BASE + "/" + draft["id"]
    def patch(key, value, revision=None):
        return client.patch(path, json={"revision": revision or draft["revision"], "key": key, "value": value})
    assert patch("goal", DEFAULTS["goal"]).status_code == 422  # No skipping service.
    assert patch("contact", "9123456789").status_code == 422  # Owner phone cannot be changed.
    assert patch("service_slug", "not-a-service").status_code == 422
    draft = answer(client, draft, "service_slug", "title-verification")
    assert patch("goal", "short").status_code == 422
    assert patch("goal", " " * 12).status_code == 422
    assert patch("goal", DEFAULTS["goal"], revision=1).status_code == 409
    draft = answer(client, draft, "goal", DEFAULTS["goal"])
    assert draft["revision"] == 3


def test_service_property_changes_remove_stale_conditional_answers(client):
    authenticate_customer(client)
    draft = fill(client, start(client), property_type="agricultural_land", granted_land="yes")
    assert "survey_number" in draft["answers"] and "granted_land" in draft["answers"]
    assert "development" not in {q["key"] for q in draft["questions"]}
    draft = answer(client, draft, "property_type", "apartment")
    assert "survey_number" not in draft["answers"] and "granted_land" not in draft["answers"]
    assert draft["next_question"] == "development"
    draft = answer(client, draft, "service_slug", "rtc-mutation-survey-records")
    assert "property_type" not in draft["answers"] and "transaction" not in draft["answers"]
    assert draft["next_question"] == "property_type"
    response = client.patch(BASE + "/" + draft["id"], json={"revision": draft["revision"], "key": "property_type", "value": "apartment"})
    assert response.status_code == 422


def test_state_change_and_optional_email_validate_dependents(client):
    authenticate_customer(client)
    draft = fill(client, start(client), state="Other", email="customer@example.test", contact_preference="email")
    assert draft["answers"]["state_name"] == "Tamil Nadu"
    draft = answer(client, draft, "state", "Karnataka")
    assert "state_name" not in draft["answers"]
    assert client.patch(BASE + "/" + draft["id"], json={"revision": draft["revision"], "key": "email", "value": "bad-email"}).status_code == 422
    draft = answer(client, draft, "email", "")
    assert "contact_preference" not in draft["answers"] and draft["next_question"] == "contact_preference"


def test_review_and_explicit_current_consent_required_before_ticket_creation(client):
    authenticate_customer(client)
    draft = start(client)
    assert submit(client, draft).status_code == 422
    draft = fill(client, draft)
    assert submit(client, draft, consent=False).status_code == 422
    assert submit(client, draft, notice_version="old").status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 0
        assert db.scalar(select(func.count()).select_from(Consent)) == 0


def test_submit_is_idempotent_and_preserves_verified_phone_consent_and_transcript(client, admin_headers):
    authenticate_customer(client)
    draft = fill(client, start(client), transaction="inheritance", seller_capacity="legal_heir")
    first, second = submit(client, draft), submit(client, draft)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    number = first.json()["ticket_number"]
    path = BASE + "/" + draft["id"]
    assert client.get(path).json()["ticket"]["ticket_number"] == number
    assert client.get(BASE).json()["items"] == []
    assert client.patch(path, json={"revision": draft["revision"], "key": "goal", "value": "A changed goal"}).status_code == 409
    assert client.delete(path).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 1
        assert db.scalar(select(func.count()).select_from(Consent)) == 1
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1
        ticket = db.scalar(select(ServiceRequest))
        assert ticket.customer.phone_normalized == "9876543210" and ticket.source == "chat"
        assert ticket.prop.state == "Karnataka" and ticket.prop.property_id_or_pid == "PID-123"
        assert ticket.structured_answers["property_intake"]["transaction"] == "inheritance"
        assert ticket.structured_answers["guided_intake"]["answers"]["role"] == "buyer"
        consent = db.scalar(select(Consent))
        assert consent.consented and consent.notice_version == intake.NOTICE_VERSION and consent.conversation_id == ticket.conversation_id
        assert db.scalar(select(func.count()).select_from(Notification)) == 2  # SMS: received + documents requested, no email.
    detail = client.get(f"/api/v1/admin/tickets/{number}", headers=admin_headers).json()
    assert len(detail["chat_transcript"]) == draft["total"] * 2
    assert any(row["message"] == DEFAULTS["goal"] for row in detail["chat_transcript"])
    tags = {item["tag"] for item in detail["document_request"]["items"]}
    assert {"death-certificate", "succession-records"} <= tags
    assert client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).status_code == 200


def test_other_state_and_land_intake_use_correct_scope(client):
    authenticate_customer(client)
    draft = fill(client, start(client), property_type="agricultural_land", state="Other", granted_land="yes")
    number = submit(client, draft).json()["ticket_number"]
    view = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).json()
    assert view["document_request"]["intake"]["development"] == "land"
    assert view["document_request"]["intake"]["survey_number"] == "45/2"
    assert all(i["source"] is None for i in view["document_request"]["items"])
    with SessionLocal() as db:
        assert db.scalar(select(ServiceRequest)).prop.state == "Tamil Nadu"


def test_discard_clears_answers_and_daily_start_limit_cannot_be_bypassed(client):
    authenticate_customer(client)
    draft = answer(client, start(client), "service_slug", "title-verification")
    assert client.delete(BASE + "/" + draft["id"]).status_code == 200
    assert client.get(BASE + "/" + draft["id"]).status_code == 404
    with SessionLocal() as db:
        row = db.get(IntakeDraft, uuid.UUID(draft["id"]))
        assert row.answers == {} and row.status == "discarded"
        for _ in range(19):
            db.add(IntakeDraft(account_id=row.account_id, answers={}, status="discarded", saving_notice_version=intake.NOTICE_VERSION, saving_consented_at=intake.utcnow()))
        db.commit()
    assert client.post(BASE, json={"consent": True, "notice_version": intake.NOTICE_VERSION}).status_code == 429


def test_active_limit_expiry_and_cleanup(client):
    authenticate_customer(client)
    drafts = [start(client) for _ in range(5)]
    assert client.post(BASE, json={"consent": True, "notice_version": intake.NOTICE_VERSION}).status_code == 429
    with SessionLocal() as db:
        row = db.get(IntakeDraft, uuid.UUID(drafts[0]["id"]))
        row.created_at = intake.utcnow() - timedelta(days=31); db.commit()
    assert client.get(BASE + "/" + drafts[0]["id"]).status_code == 410
    assert len(client.get(BASE).json()["items"]) == 4
    intake.cleanup()
    with SessionLocal() as db:
        assert db.get(IntakeDraft, uuid.UUID(drafts[0]["id"])) is None
    assert start(client)["status"] == "draft"


def test_retired_service_requires_reselection_and_submit_is_transactional(client, monkeypatch):
    authenticate_customer(client)
    draft = fill(client, start(client))
    original = tickets.create_ticket
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic failure before consent commit")
    monkeypatch.setattr(tickets, "create_ticket", fail)
    with pytest.raises(RuntimeError):
        submit(client, draft)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 0
        assert db.get(IntakeDraft, uuid.UUID(draft["id"])).status == "draft"
        service = db.scalar(select(ServiceType).where(ServiceType.slug == "title-verification")); service.is_active = False; db.commit()
    assert client.get(BASE + "/" + draft["id"]).json()["next_question"] == "service_slug"
    assert submit(client, draft).status_code == 409


@pytest.mark.skipif(not config.DATABASE_URL.startswith("postgresql"), reason="Requires PostgreSQL row locks")
def test_concurrent_submit_creates_one_ticket_and_one_consent(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    authenticate_customer(client)
    draft = fill(client, start(client))
    ready = Barrier(2)
    def send(_):
        ready.wait(timeout=10)
        response = submit(client, draft)
        assert response.status_code == 200
        return response.json()["ticket_number"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(send, range(2)))
    assert values[0] == values[1]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 1
        assert db.scalar(select(func.count()).select_from(Consent)) == 1
