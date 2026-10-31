import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app import config, whatsapp
from app.db import SessionLocal
from app.models import LoginCode

from test_lawyers import CUSTOMER, _book, lawyer  # noqa: F401  (fixture)

PHONE = "+91 98765 43210"  # the raise_ticket fixture's number

def _sign_in(client, phone: str = PHONE) -> dict:
    code = client.post("/api/v1/account/login/start", json={"phone": phone}).json()["dev_code"]
    response = client.post("/api/v1/account/login/verify", json={"phone": phone, "code": code})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def _age_codes(seconds: int = 120) -> None:
    """Moves earlier codes back in time, past the resend wait."""
    with SessionLocal() as db:
        for row in db.scalars(select(LoginCode)).all():
            row.created_at -= timedelta(seconds=seconds)
        db.commit()

def test_sign_in_lists_requests_raised_with_the_same_phone_before_signing_up(client, raise_ticket):
    first = raise_ticket()
    second = raise_ticket(contact="098765-43210", service_slug="title-verification")
    raise_ticket(contact="+91 91234 56789")  # someone else

    started = client.post("/api/v1/account/login/start", json={"phone": "9876543210"})
    assert started.status_code == 200, started.text
    assert started.json()["channel"] == "dev" and started.json()["phone"] == "+91 98765 43210"
    response = client.post("/api/v1/account/login/verify", json={"phone": "98765 43210", "code": started.json()["dev_code"]})
    account = response.json()["account"]
    assert account["name"] == "Sample Customer" and account["email"] == "sample@example.com" and account["contact"] == "9876543210"

    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    overview = client.get("/api/v1/account", headers=headers).json()
    assert [r["ticket_number"] for r in overview["requests"]] == [second, first]
    assert overview["requests"][0]["kind"] == "request" and overview["requests"][0]["status_label"] == "Request received"
    assert overview["bookings"] == [] and overview["payments"] == []

    # The full ticket opens for the account; other people's tickets don't.
    assert client.get(f"/api/v1/account/requests/{first.lower()}", headers=headers).json()["ticket_number"] == first
    other = raise_ticket(contact="+91 91234 56789")
    assert client.get(f"/api/v1/account/requests/{other}", headers=headers).status_code == 404
    # The verified phone works as the contact on the existing ticket endpoints.
    assert client.post("/api/v1/tickets/lookup", json={"ticket_number": first, "contact": account["contact"]}).status_code == 200

def test_bookings_and_payments_show_on_the_account(client, lawyer):
    booking = _book(client, lawyer["slug"]).json()
    headers = _sign_in(client, CUSTOMER["phone"])
    overview = client.get("/api/v1/account", headers=headers).json()
    assert overview["requests"][0]["kind"] == "consultation" and overview["requests"][0]["next_meeting"]["status"] == "scheduled"
    assert [b["ticket_number"] for b in overview["bookings"]] == [booking["ticket_number"]]
    assert overview["payments"][0]["status"] == "due" and overview["payments"][0]["amount"] == 1500
    assert overview["payments"][0]["description"] == "Consultation with Kiran Agent"

def test_wrong_codes_are_limited_and_only_the_newest_code_works(client):
    first = client.post("/api/v1/account/login/start", json={"phone": PHONE}).json()["dev_code"]
    # A second request straight away has to wait.
    assert client.post("/api/v1/account/login/start", json={"phone": PHONE}).status_code == 429
    _age_codes()
    second = client.post("/api/v1/account/login/start", json={"phone": PHONE}).json()["dev_code"]
    if first != second:
        assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": first}).status_code == 400
    wrong = "000000" if second != "000000" else "111111"
    for _ in range(config.LOGIN_CODE_MAX_ATTEMPTS - (1 if first != second else 0)):
        assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": wrong}).status_code == 400
    # Out of attempts: even the right code is refused now.
    assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": second}).status_code == 400

def test_codes_expire_and_cannot_be_reused(client):
    code = client.post("/api/v1/account/login/start", json={"phone": PHONE}).json()["dev_code"]
    assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": code}).status_code == 200
    assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": code}).status_code == 400
    _age_codes()
    code = client.post("/api/v1/account/login/start", json={"phone": PHONE}).json()["dev_code"]
    with SessionLocal() as db:
        db.scalars(select(LoginCode).where(LoginCode.used_at.is_(None))).one().expires_at -= timedelta(minutes=config.LOGIN_CODE_MINUTES + 1)
        db.commit()
    assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": code}).status_code == 400

def test_codes_per_phone_per_hour_are_capped(client):
    for _ in range(config.LOGIN_CODES_PER_PHONE_PER_HOUR):
        assert client.post("/api/v1/account/login/start", json={"phone": PHONE}).status_code == 200
        _age_codes(40)
    response = client.post("/api/v1/account/login/start", json={"phone": PHONE})
    assert response.status_code == 429 and "an hour" in response.json()["detail"]

def test_profile_update_and_sign_out_everywhere(client):
    headers = _sign_in(client)
    assert client.get("/api/v1/account", headers=headers).json()["profile"]["name"] is None
    profile = client.patch("/api/v1/account", json={"full_name": "Asha Rao", "email": "Asha@Example.com"}, headers=headers).json()
    assert profile["name"] == "Asha Rao" and profile["email"] == "asha@example.com"
    assert client.patch("/api/v1/account", json={"email": "not-an-email"}, headers=headers).status_code == 422
    assert client.post("/api/v1/account/logout-all", headers=headers).status_code == 200
    assert client.get("/api/v1/account", headers=headers).status_code == 401

def test_customer_and_staff_tokens_are_not_interchangeable(client, admin_headers):
    customer = _sign_in(client)
    assert client.get("/api/v1/auth/me", headers=customer).status_code == 401
    assert client.get("/api/v1/admin/tickets", headers=customer).status_code == 401
    assert client.get("/api/v1/account", headers=admin_headers).status_code == 401
    assert client.get("/api/v1/account").status_code == 401

def test_short_numbers_are_rejected(client):
    response = client.post("/api/v1/account/login/start", json={"phone": "12345-6789"})
    assert response.status_code == 422 and "10-digit" in response.json()["detail"]

def test_no_dev_mode_and_no_whatsapp_means_no_sign_in(client, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_CODE_DEV_MODE", False)
    assert client.post("/api/v1/account/login/start", json={"phone": PHONE}).status_code == 503

def test_code_goes_out_on_whatsapp_with_the_copy_code_button(client, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "wa-token")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "1234")
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})
    monkeypatch.setattr(whatsapp, "http", httpx.Client(transport=httpx.MockTransport(handler)))

    started = client.post("/api/v1/account/login/start", json={"phone": PHONE}).json()
    assert started["channel"] == "whatsapp" and "dev_code" not in started
    message = sent[0]
    assert message["to"] == "919876543210" and message["template"]["name"] == "login_code"
    body, button = message["template"]["components"]
    code = body["parameters"][0]["text"]
    assert button["sub_type"] == "url" and button["parameters"][0]["text"] == code
    assert client.post("/api/v1/account/login/verify", json={"phone": PHONE, "code": code}).status_code == 200

def test_whatsapp_failure_saves_no_code(client, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "wa-token")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "1234")
    monkeypatch.setattr(whatsapp, "http", httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(400, json={"error": {"message": "Recipient not on WhatsApp", "code": 131026}}))))
    assert client.post("/api/v1/account/login/start", json={"phone": PHONE}).status_code == 502
    with SessionLocal() as db:
        assert db.scalars(select(LoginCode)).first() is None
