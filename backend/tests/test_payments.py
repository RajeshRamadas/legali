import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import config, payments
from app.db import SessionLocal
from app.models import Meeting, Payment, ServiceRequest, utcnow

from test_lawyers import CUSTOMER, PROFILE, _book, _first_slot, lawyer  # noqa: F401  (fixture)

REF = lambda booking: {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"]}

def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def _events(ticket_number: str) -> list[str]:
    with SessionLocal() as db:
        ticket = db.scalars(select(ServiceRequest).where(ServiceRequest.ticket_number == ticket_number)).one()
        return [e.event_type for e in ticket.events]

@pytest.fixture
def razorpay(monkeypatch):
    """Razorpay keys set, with the API faked: orders and links get fixed ids, and status checks answer from `state`."""
    monkeypatch.setattr(config, "RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setattr(config, "RAZORPAY_KEY_SECRET", "key-secret")
    monkeypatch.setattr(config, "RAZORPAY_WEBHOOK_SECRET", "hook-secret")
    state = {"calls": [], "link_status": "created"}

    def fake_api(method, path, body=None):
        state["calls"].append((method, path, body))
        if path == "/orders":
            return {"id": f"order_{len(state['calls'])}"}
        if path == "/payment_links":
            return {"id": "plink_1", "short_url": "https://rzp.io/i/abc"}
        if path.startswith("/payment_links/"):
            return {"status": state["link_status"], "payments": [{"payment_id": "pay_link1", "status": "captured", "method": "upi"}]}
        raise AssertionError(path)
    monkeypatch.setattr(payments, "_api", fake_api)
    return state

def test_search_cards_show_courts_and_profile_says_fee_is_paid_online(client, lawyer):
    card = client.get("/api/v1/lawyers").json()["items"][0]
    assert card["courts"] == ["Karnataka High Court"] and card["experience_years"] == 12 and card["specialisations"][0] == "Property & real estate"
    assert [c["name"] for c in client.get("/api/v1/lawyers", params={"q": "high court"}).json()["items"]] == ["Kiran Agent"]
    assert client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()["pay_online"] is True

def test_test_mode_payment_and_refund_on_cancel(client, lawyer):
    booking = _book(client, lawyer["slug"]).json()
    payment = booking["payment"]
    assert payment["status"] == "due" and payment["amount"] == 1500 and payment["mode"] == "test" and payment["can_pay"] and payment["pay_by"]

    started = client.post("/api/v1/bookings/pay", json=REF(booking)).json()["checkout"]
    assert started["provider"] == "test" and started["order_id"].startswith("order_test_") and started["amount_paise"] == 150000 and started["key_id"] is None
    # The same unpaid order is reused rather than piling up new ones.
    assert client.post("/api/v1/bookings/pay", json=REF(booking)).json()["checkout"]["order_id"] == started["order_id"]

    assert client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": started["order_id"], "payment_id": "pay_real", "signature": ""}).status_code == 422
    paid = client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": started["order_id"], "payment_id": "pay_test_1", "signature": ""}).json()
    assert paid["payment"]["status"] == "paid" and not paid["payment"]["can_pay"] and paid["payment"]["pay_by"] is None
    assert client.post("/api/v1/bookings/pay", json=REF(booking)).status_code == 422  # nothing left to pay

    cancelled = client.post("/api/v1/bookings/cancel", json=REF(booking)).json()
    assert cancelled["payment"]["status"] == "refund_due"
    assert {"payment_received", "payment_refund_due"} <= set(_events(booking["ticket_number"]))

def test_checkout_signature_is_checked(client, lawyer, razorpay):
    booking = _book(client, lawyer["slug"]).json()
    started = client.post("/api/v1/bookings/pay", json=REF(booking)).json()["checkout"]
    assert started["provider"] == "razorpay" and started["key_id"] == "rzp_test_key" and started["order_id"] == "order_1"
    assert razorpay["calls"][0][2]["amount"] == 150000 and razorpay["calls"][0][2]["receipt"] == booking["ticket_number"]

    forged = client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": "order_1", "payment_id": "pay_9", "signature": "0" * 64})
    assert forged.status_code == 422
    good = _sign(b"order_1|pay_9", "key-secret")
    other = client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "contact": "someone@else.com", "order_id": "order_1", "payment_id": "pay_9", "signature": good})
    assert other.status_code == 404
    paid = client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": "order_1", "payment_id": "pay_9", "signature": good}).json()
    assert paid["payment"]["status"] == "paid" and paid["payment"]["reference"] == "pay_9"

def test_app_payment_link_paid_by_webhook_or_status_check(client, lawyer, razorpay):
    booking = _book(client, lawyer["slug"], source="mobile").json()
    started = client.post("/api/v1/bookings/pay", json={**REF(booking), "kind": "link"}).json()["checkout"]
    assert started["pay_url"] == "https://rzp.io/i/abc" and started["order_id"] == "plink_1"
    link_body = razorpay["calls"][0][2]
    assert link_body["customer"]["contact"] and link_body["callback_url"].endswith("/bookings/paid") and link_body["notify"] == {"sms": False, "email": False}

    # Still unpaid at Razorpay: refresh changes nothing.
    assert client.post("/api/v1/bookings/pay/refresh", json=REF(booking)).json()["payment"]["status"] == "due"

    event = json.dumps({"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_1", "status": "paid"}},
        "payment": {"entity": {"id": "pay_hook", "method": "upi", "status": "captured"}},
    }}).encode()
    assert client.post("/api/v1/payments/razorpay/webhook", content=event, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    assert client.post("/api/v1/payments/razorpay/webhook", content=event, headers={"X-Razorpay-Signature": _sign(event, "hook-secret")}).status_code == 200
    # A repeat delivery is harmless.
    client.post("/api/v1/payments/razorpay/webhook", content=event, headers={"X-Razorpay-Signature": _sign(event, "hook-secret")})
    view = client.post("/api/v1/bookings/lookup", json=REF(booking)).json()
    assert view["payment"]["status"] == "paid" and view["payment"]["method"] == "upi"
    assert _events(booking["ticket_number"]).count("payment_received") == 1

    client.post("/api/v1/bookings/cancel", json=REF(booking))
    refund = json.dumps({"event": "refund.processed", "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_hook", "amount": 150000}}}}).encode()
    client.post("/api/v1/payments/razorpay/webhook", content=refund, headers={"X-Razorpay-Signature": _sign(refund, "hook-secret")})
    assert client.post("/api/v1/bookings/lookup", json=REF(booking)).json()["payment"]["status"] == "refunded"

def test_status_check_catches_a_link_paid_before_the_webhook(client, lawyer, razorpay):
    booking = _book(client, lawyer["slug"]).json()
    client.post("/api/v1/bookings/pay", json={**REF(booking), "kind": "link"})
    razorpay["link_status"] = "paid"
    view = client.post("/api/v1/bookings/pay/refresh", json=REF(booking)).json()
    assert view["payment"]["status"] == "paid" and view["payment"]["reference"] == "pay_link1"

def test_unpaid_bookings_are_released_after_the_hold(client, lawyer, monkeypatch):
    monkeypatch.setattr(config, "PAYMENT_HOLD_MINUTES", 30)
    unpaid = _book(client, lawyer["slug"]).json()
    paid = _book(client, lawyer["slug"], starts_at=_first_slot(client, lawyer["slug"], skip=1)).json()
    order = client.post("/api/v1/bookings/pay", json=REF(paid)).json()["checkout"]["order_id"]
    client.post("/api/v1/bookings/pay/verify", json={**REF(paid), "order_id": order, "payment_id": "pay_test_2"})

    with SessionLocal() as db:
        assert payments.release_unpaid(db) == 0  # still inside the hold
        for meeting in db.scalars(select(Meeting)).all():
            meeting.created_at = utcnow() - timedelta(minutes=31)
        db.commit()
        assert payments.release_unpaid(db) == 1

    released = client.post("/api/v1/bookings/lookup", json=REF(unpaid)).json()
    assert released["meeting"]["status"] == "cancelled" and released["status"] == "cancelled" and not released["payment"]["can_pay"]
    assert client.post("/api/v1/bookings/lookup", json=REF(paid)).json()["meeting"]["status"] == "scheduled"
    # The released time can be booked again.
    assert _first_slot(client, lawyer["slug"]) == unpaid["meeting"]["starts_at"]

def test_without_keys_or_test_mode_the_team_arranges_payment(client, lawyer, monkeypatch):
    monkeypatch.setattr(config, "PAYMENTS_TEST_MODE", False)
    assert client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()["pay_online"] is False
    booking = _book(client, lawyer["slug"]).json()
    assert booking["payment"] is None and booking["fee"] == 1500
    assert client.post("/api/v1/bookings/pay", json=REF(booking)).status_code == 422
    with SessionLocal() as db:
        assert db.scalars(select(Payment)).first() is None
