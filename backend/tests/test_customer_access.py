"""Regression tests for the verified-customer authorization boundary."""
import io
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app import config
from app.customer_auth import create_session_token
from app.db import SessionLocal
from app.models import CustomerAccount

OWNER = "9876543210"
OTHER = "9123456789"


def identity(phone):
    with SessionLocal() as db:
        account = db.scalars(select(CustomerAccount).where(CustomerAccount.phone_normalized == phone)).first()
        if account is None:
            account = CustomerAccount(phone_normalized=phone)
            db.add(account)
            db.commit()
        return {"Authorization": f"Bearer {create_session_token(account)}"}


def operation(endpoint, ticket):
    body = {"ticket_number": ticket, "contact": OWNER}
    if endpoint.endswith("/messages"):
        body["message"] = "Private customer message"
    elif endpoint.endswith("/property-intake"):
        body["intake"] = {"state": "Karnataka"}
    elif endpoint.endswith("/tag") or endpoint.endswith("/delete"):
        body["document_id"] = "00000000-0000-0000-0000-000000000001"
        body["tag"] = "sale-deed"
    elif endpoint.endswith("/reschedule"):
        body["starts_at"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    elif endpoint.endswith("/review"):
        body.update(rating=5, comment="Review")
    elif endpoint.endswith("/verify"):
        body.update(order_id="order_example", payment_id="pay_example", signature="invalid")
    elif endpoint == "/api/v1/chat":
        body = {"message": "Show my private request", "ticket": body}
    return body


PROTECTED = [
    "/api/v1/tickets/lookup", "/api/v1/tickets/messages", "/api/v1/tickets/property-intake",
    "/api/v1/tickets/documents/tag", "/api/v1/tickets/documents/delete",
    "/api/v1/bookings/lookup", "/api/v1/bookings/cancel", "/api/v1/bookings/reschedule",
    "/api/v1/bookings/pay", "/api/v1/bookings/pay/verify", "/api/v1/bookings/pay/refresh",
    "/api/v1/bookings/review", "/api/v1/chat",
]


@pytest.mark.parametrize("endpoint", PROTECTED)
def test_known_contact_is_not_authentication(client, raise_ticket, endpoint):
    number = raise_ticket()
    client.headers.clear()
    response = client.post(endpoint, json=operation(endpoint, number))
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("endpoint", PROTECTED)
def test_other_verified_customer_cannot_use_known_contact(client, raise_ticket, endpoint):
    number = raise_ticket()
    response = client.post(endpoint, json=operation(endpoint, number), headers=identity(OTHER))
    assert response.status_code == 404, response.text


def test_upload_and_download_require_session_and_current_ownership(client, raise_ticket, admin_headers, agent, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    number = raise_ticket()
    owner = identity(OWNER)
    other = identity(OTHER)
    data = {"ticket_number": number, "contact": OWNER}
    pdf = b"%PDF-1.4\nsynthetic test document"
    def upload(headers):
        return client.post("/api/v1/tickets/documents", data=data, files={"file": ("proof.pdf", io.BytesIO(pdf), "application/pdf")}, headers=headers)
    client.headers.clear()
    assert upload({}).status_code == 401
    assert upload(other).status_code == 404
    response = upload(owner)
    assert response.status_code == 201, response.text
    url = response.json()["documents"][0]["download_url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=other).status_code == 404
    assert client.get(url, headers=agent["headers"]).status_code == 404
    assert client.get(url, headers=admin_headers).content == pdf
    assert client.get(url, headers=owner).content == pdf
    assert client.get(url, headers=owner).headers["cache-control"] == "private, no-store"
    assert client.post("/api/v1/account/logout-all", headers=owner).status_code == 200
    assert client.get(url, headers=owner).status_code == 401
    assert client.post("/api/v1/tickets/lookup", json=data, headers=owner).status_code == 401


def test_invalid_expired_and_staff_tokens_are_not_customer_sessions(client, raise_ticket, admin_headers):
    number = raise_ticket()
    with SessionLocal() as db:
        account = db.scalars(select(CustomerAccount).where(CustomerAccount.phone_normalized == OWNER)).one()
        claims = {"sub": str(account.id), "ver": account.token_version, "aud": "homexo-customer",
                  "iat": datetime.now(timezone.utc)-timedelta(hours=2), "exp": datetime.now(timezone.utc)-timedelta(hours=1)}
    expired = jwt.encode(claims, config.JWT_SECRET, algorithm="HS256")
    for token in ["not.a.token", expired, admin_headers["Authorization"].split()[1]]:
        response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": OWNER}, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_linked_conversation_cannot_be_read_or_reattached_by_someone_else(client, raise_ticket):
    number = raise_ticket()
    response = client.post("/api/v1/chat", json={"message": "Review my documents", "ticket": {"ticket_number": number, "contact": OWNER}})
    assert response.status_code == 200
    conversation = response.json()["conversation_id"]
    client.headers.clear()
    assert client.post("/api/v1/chat", json={"message": "Continue", "conversation_id": conversation}).status_code == 404
    assert client.post("/api/v1/chat", json={"message": "Continue", "conversation_id": conversation}, headers=identity(OTHER)).status_code == 404
    forged = client.post("/api/v1/tickets", json={"customer_name": "Other customer", "contact": OTHER, "property_type": "apartment", "service_slug": "title-verification", "location": "Bengaluru", "conversation_id": conversation})
    assert forged.status_code == 404
    assert client.post("/api/v1/chat", json={"message": "What is title verification?"}).status_code == 200


def test_development_codes_cannot_be_enabled_in_production(client, monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "LOGIN_CODE_DEV_MODE", True)
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "")
    assert client.post("/api/v1/account/login/start", json={"phone": OWNER}).status_code == 503
