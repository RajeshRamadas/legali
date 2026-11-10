import concurrent.futures
import json

import pytest
from sqlalchemy import func, select

from app import config, payments
from app.db import SessionLocal, engine
from app.models import AuditLog, Payment, Refund
from conftest import authenticate_customer
from test_lawyers import CUSTOMER, _book, lawyer  # noqa: F401
from test_payments import REF, _sign, razorpay  # noqa: F401


def paid_booking(client, lawyer, payment_id="pay_refund_fixture"):
    booking = _book(client, lawyer["slug"]).json()
    checkout = client.post("/api/v1/bookings/pay", json=REF(booking)).json()["checkout"]
    result = client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": checkout["order_id"],
        "payment_id": payment_id, "signature": _sign(f"{checkout['order_id']}|{payment_id}".encode(), "key-secret")})
    assert result.status_code == 200
    return booking


def refund_event(client, name="refund.processed", *, identifier="rfnd_fixture", payment_id="pay_refund_fixture", amount=50000, currency="INR"):
    body = json.dumps({"event": name, "payload": {"refund": {"entity": {"id": identifier, "payment_id": payment_id, "amount": amount, "currency": currency}}}}).encode()
    return client.post("/api/v1/payments/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": _sign(body, "hook-secret")})


def payment_view(client, booking):
    return client.post("/api/v1/bookings/lookup", json=REF(booking)).json()["payment"]


def test_partial_refunds_preserve_paise_and_only_full_total_marks_refunded(client, lawyer, razorpay):
    booking = paid_booking(client, lawyer)
    client.post("/api/v1/bookings/cancel", json=REF(booking))
    assert refund_event(client, amount=10050).status_code == 200
    partial = payment_view(client, booking)
    assert partial["status"] == "refund_due" and partial["refunded_paise"] == 10050 and not partial["refund_review_required"]
    for _ in range(2): assert refund_event(client, amount=10050).status_code == 200
    assert payment_view(client, booking)["refunded_paise"] == 10050
    assert refund_event(client, identifier="rfnd_rest", amount=139950).status_code == 200
    complete = payment_view(client, booking)
    assert complete["status"] == "refunded" and complete["refunded_paise"] == 150000
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Refund)) == 2


def test_pending_failed_and_late_events_never_count_twice_or_downgrade_processed(client, lawyer, razorpay):
    booking = paid_booking(client, lawyer)
    assert refund_event(client, "refund.created").status_code == 200
    assert payment_view(client, booking)["refund_pending_paise"] == 50000
    assert payment_view(client, booking)["refunded_paise"] == 0
    refund_event(client, "refund.failed")
    assert payment_view(client, booking)["refund_pending_paise"] == 0
    refund_event(client, "refund.created")
    with SessionLocal() as db: assert db.scalar(select(Refund)).status == "failed"
    refund_event(client)
    refund_event(client, "refund.failed"); refund_event(client, "refund.created")
    view = payment_view(client, booking)
    assert view["status"] == "paid" and view["refunded_paise"] == 50000 and view["refund_pending_paise"] == 0
    with SessionLocal() as db: assert db.scalar(select(Refund)).status == "processed"


def test_refund_before_payment_capture_is_retained_then_attached(client, lawyer, razorpay, admin_headers):
    assert refund_event(client, amount=150000).status_code == 200
    unmatched = client.get("/api/v1/admin/refunds/unmatched", headers=admin_headers).json()
    assert unmatched["total"] == 1
    booking = paid_booking(client, lawyer)
    view = payment_view(client, booking)
    assert view["status"] == "refunded" and view["refunded_paise"] == 150000
    assert client.get("/api/v1/admin/refunds/unmatched", headers=admin_headers).json()["total"] == 0


@pytest.mark.parametrize("changes", [{"amount": 0}, {"amount": -1}, {"amount": True}, {"amount": "50000"},
    {"amount": 2147483648}, {"identifier": "bad/id"}, {"currency": "invalid"}])
def test_invalid_refund_fields_fail_without_financial_writes(client, razorpay, changes):
    assert refund_event(client, **changes).status_code == 422
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(Refund)) == 0


def test_signature_and_malformed_body_guards(client, razorpay):
    assert client.post("/api/v1/payments/razorpay/webhook", content=b"{}", headers={"X-Razorpay-Signature": "forged"}).status_code == 400
    for value in ([], {"payload": []}, {"event": "refund.processed", "payload": {"refund": "invalid"}}):
        body = json.dumps(value).encode()
        assert client.post("/api/v1/payments/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": _sign(body, "hook-secret")}).status_code in (400, 422)
    body = b"x" * (128 * 1024 + 1)
    assert client.post("/api/v1/payments/razorpay/webhook", content=body).status_code == 413


@pytest.mark.parametrize("changes", [{"amount": 60000}, {"payment_id": "pay_other"}, {"currency": "USD"}])
def test_conflicting_identity_or_amount_requires_review_and_preserves_confirmed_balance(client, lawyer, razorpay, changes):
    booking = paid_booking(client, lawyer)
    refund_event(client)
    assert refund_event(client, **changes).status_code == 200
    result = payment_view(client, booking)
    assert result["refund_review_required"] and result["refunded_paise"] == 50000
    with SessionLocal() as db:
        record = db.scalar(select(Refund))
        assert record.amount_paise == 50000 and record.provider_payment_id == "pay_refund_fixture"


def test_over_refund_is_reviewed_not_claimed_complete(client, lawyer, razorpay):
    booking = paid_booking(client, lawyer)
    refund_event(client, amount=100000)
    refund_event(client, identifier="rfnd_excess", amount=100000)
    result = payment_view(client, booking)
    assert result["refund_review_required"] and result["status"] == "paid" and result["refunded_paise"] == 100000


def test_legacy_refunds_remain_under_review_even_after_replayed_event(client, lawyer, razorpay):
    booking = paid_booking(client, lawyer)
    with SessionLocal() as db:
        payment = db.scalar(select(Payment)); payment.status = "refunded"; payment.refund_review_reason = "legacy_unverified"; db.commit()
    refund_event(client)
    assert payment_view(client, booking)["refund_review_required"]


def test_admin_queue_auth_filters_internal_notes_and_conflict_protection(client, lawyer, razorpay, admin_headers, agent):
    booking = paid_booking(client, lawyer)
    client.post("/api/v1/bookings/cancel", json=REF(booking))
    queue = client.get("/api/v1/admin/refunds", headers=admin_headers).json()
    assert queue["total"] == 1 and queue["counts"]["needs_action"] == 1
    refund_event(client, "refund.created", amount=10050)
    queue = client.get("/api/v1/admin/refunds?state=pending", headers=admin_headers).json()
    assert queue["total"] == 1 and queue["items"][0]["pending_paise"] == 10050
    pid = queue["items"][0]["id"]
    records = client.get(f"/api/v1/admin/refunds/payments/{pid}", headers=admin_headers).json()
    item = records["items"][0]
    saved = client.patch(f"/api/v1/admin/refunds/{item['id']}/note", headers=admin_headers,
        json={"revision": item["revision"], "internal_note": "PRIVATE_REFUND_NOTE"})
    assert saved.status_code == 200
    assert client.patch(f"/api/v1/admin/refunds/{item['id']}/note", headers=admin_headers,
        json={"revision": item["revision"], "internal_note": "stale"}).status_code == 409
    assert client.patch(f"/api/v1/admin/refunds/{item['id']}/note", headers=admin_headers,
        json={"revision": saved.json()["revision"], "internal_note": "override", "status": "processed"}).status_code == 422
    customer = authenticate_customer(client)
    assert "PRIVATE_REFUND_NOTE" not in client.get("/api/v1/account", headers=customer).text
    for headers in (customer, agent["headers"], {"Authorization": "Bearer invalid"}):
        assert client.get("/api/v1/admin/refunds", headers=headers).status_code in (401, 403)
        assert client.get("/api/v1/admin/refunds/unmatched", headers=headers).status_code in (401, 403)
        assert client.get(f"/api/v1/admin/refunds/payments/{pid}", headers=headers).status_code in (401, 403)
        assert client.patch(f"/api/v1/admin/refunds/{item['id']}/note", headers=headers,
            json={"revision": saved.json()["revision"], "internal_note": "unauthorized"}).status_code in (401, 403)
    with SessionLocal() as db:
        assert all("PRIVATE_REFUND_NOTE" not in str(row.metadata_) for row in db.scalars(select(AuditLog).where(AuditLog.entity_type == "refund")))


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent refund accounting requires PostgreSQL advisory/row locks")
def test_concurrent_refund_events_do_not_lose_or_double_count_money(client, lawyer, razorpay):
    booking = paid_booking(client, lawyer)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda identifier: refund_event(client, identifier=identifier, amount=50000).status_code, ("rfnd_a", "rfnd_b", "rfnd_a")))
    assert results == [200, 200, 200]
    assert payment_view(client, booking)["refunded_paise"] == 100000


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent capture requires PostgreSQL advisory/row locks")
def test_refund_racing_capture_is_attached_and_counted(client, lawyer, razorpay):
    booking = _book(client, lawyer["slug"]).json()
    checkout = client.post("/api/v1/bookings/pay", json=REF(booking)).json()["checkout"]
    def capture():
        return client.post("/api/v1/bookings/pay/verify", json={**REF(booking), "order_id": checkout["order_id"],
            "payment_id": "pay_refund_fixture", "signature": _sign(f"{checkout['order_id']}|pay_refund_fixture".encode(), "key-secret")}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        captured = pool.submit(capture)
        refunded = pool.submit(refund_event, client, amount=150000)
        assert captured.result() == 200 and refunded.result().status_code == 200
    result = payment_view(client, booking)
    assert result["status"] == "refunded" and result["refunded_paise"] == 150000
    with SessionLocal() as db: assert db.scalar(select(Refund)).payment_id is not None
