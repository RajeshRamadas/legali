"""Online payment of consultation fees through Razorpay.

The website opens Razorpay Checkout on an order we create; the app opens a Razorpay payment link in the browser.
A payment counts once its signature checks out (Checkout), Razorpay's webhook says so, or a status check with
Razorpay finds it paid. Card, UPI and bank details never reach us; we keep Razorpay's ids and the outcome.

Without Razorpay keys, test mode (development only by default) takes a pretend payment so the flow can be tried
end to end. With neither, online bookings work as before and the team arranges payment.

A booking made while online payment was on holds its slot for PAYMENT_HOLD_MINUTES; the notification worker
releases it after that if the fee is still unpaid. Money that arrives for a cancelled booking, or twice, is
marked for refund, which staff make from the Razorpay dashboard (the refund webhook then marks it refunded).
"""
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, meetings, tickets
from .db import get_db
from .models import Meeting, Payment, ServiceRequest, utcnow

log = logging.getLogger("homexo.payments")
router = APIRouter()

class PaymentError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code

def mode() -> str:
    """"razorpay" with keys, "test" for pretend payments, or "off" (the team arranges payment)."""
    if config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET:
        return "razorpay"
    return "test" if config.PAYMENTS_TEST_MODE else "off"

def online(fee: int | None) -> bool:
    return mode() != "off" and bool(fee) and fee > 0

def _sign(message: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

def _valid(message: bytes, signature: str | None, secret: str) -> bool:
    return bool(signature and secret) and hmac.compare_digest(_sign(message, secret), signature)

def _api(method: str, path: str, body: dict | None = None) -> dict:
    try:
        response = httpx.request(method, f"{config.RAZORPAY_API_BASE}{path}", auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET), json=body, timeout=15)
    except httpx.HTTPError as exc:
        log.warning("Razorpay %s %s failed: %s", method, path, exc)
        raise PaymentError("We couldn't reach the payment service. Please try again in a minute.") from exc
    if response.status_code >= 400:
        log.warning("Razorpay %s %s returned %s: %s", method, path, response.status_code, response.text[:500])
        raise PaymentError("The payment service couldn't start this payment. Please try again, or call us.")
    return response.json()

def _iso(value: datetime | None) -> str | None:
    return tickets.aware(value).isoformat() if value else None

def _rows(db: Session, ticket: ServiceRequest) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.service_request_id == ticket.id).order_by(Payment.created_at)).all())

def _booking(ticket: ServiceRequest) -> Meeting | None:
    return max(ticket.meetings, key=lambda m: m.created_at) if ticket.meetings else None

def amount_due(ticket: ServiceRequest) -> int | None:
    """The fee in paise when this booking is paid online, else None."""
    answers = ticket.structured_answers or {}
    return int(answers["fee"]) * 100 if answers.get("pay_online") and answers.get("fee") else None

def pay_by(meeting: Meeting) -> datetime | None:
    return tickets.aware(meeting.created_at) + timedelta(minutes=config.PAYMENT_HOLD_MINUTES) if config.PAYMENT_HOLD_MINUTES > 0 else None

def payment_view(db: Session, ticket: ServiceRequest, meeting: Meeting) -> dict | None:
    if amount_due(ticket) is None:
        return None
    rows = _rows(db, ticket)
    settled = next((p for p in rows if p.status != "created"), None)
    status = settled.status if settled else "due"
    open_booking = meeting.status == "scheduled"
    return {
        "status": status,
        "amount": (ticket.structured_answers or {})["fee"],
        "paid_at": _iso(settled.paid_at) if settled else None,
        "method": settled.method if settled else None,
        "reference": settled.provider_payment_id if settled else None,
        "pay_by": _iso(pay_by(meeting)) if status == "due" and open_booking else None,
        "mode": mode(),
        "can_pay": status == "due" and open_booking and mode() != "off",
        "last_error": rows[-1].failure_reason if rows and status == "due" else None,
    }

def start(db: Session, ticket: ServiceRequest, kind: str) -> dict:
    """An order (kind "checkout") or payment link (kind "link") for the fee, reusing an unpaid one."""
    amount = amount_due(ticket)
    provider = mode()
    if amount is None or provider == "off":
        raise PaymentError("This booking isn't paid online.", 422)
    customer = ticket.customer
    name = (ticket.structured_answers or {}).get("customer_name") or customer.full_name
    payment = next((p for p in reversed(_rows(db, ticket)) if p.status == "created" and p.provider == provider and p.kind == kind and p.amount_paise == amount), None)
    if payment is None:
        pay_url = None
        if provider == "test":
            order_id = f"{'plink' if kind == 'link' else 'order'}_test_{secrets.token_hex(8)}"
        elif kind == "checkout":
            order_id = _api("POST", "/orders", {
                "amount": amount, "currency": "INR", "receipt": ticket.ticket_number, "notes": {"ticket_number": ticket.ticket_number},
            })["id"]
        else:
            link = _api("POST", "/payment_links", {
                "amount": amount, "currency": "INR", "description": ticket.title or "Consultation fee",
                "reference_id": f"{ticket.ticket_number}-{secrets.token_hex(3)}",
                "customer": {"name": name, "contact": customer.phone or "", **({"email": customer.email} if customer.email else {})},
                "notify": {"sms": False, "email": False}, "reminder_enable": False,
                "notes": {"ticket_number": ticket.ticket_number},
                "callback_url": f"{config.PUBLIC_SITE_URL}/bookings/paid", "callback_method": "get",
            })
            order_id, pay_url = link["id"], link["short_url"]
        payment = Payment(service_request_id=ticket.id, provider=provider, kind=kind, amount_paise=amount, provider_order_id=order_id, pay_url=pay_url)
        db.add(payment)
        db.flush()
    return {
        "provider": provider,
        "kind": kind,
        "order_id": payment.provider_order_id,
        "pay_url": payment.pay_url,
        "key_id": config.RAZORPAY_KEY_ID if provider == "razorpay" else None,
        "amount_paise": payment.amount_paise,
        "currency": payment.currency,
        "description": ticket.title or "Consultation fee",
        "prefill": {"name": name, "contact": customer.phone or "", "email": customer.email or ""},
    }

def _find(db: Session, ticket: ServiceRequest, order_id: str) -> Payment:
    payment = db.scalars(select(Payment).where(Payment.service_request_id == ticket.id, Payment.provider_order_id == order_id)).first()
    if payment is None:
        raise PaymentError("We couldn't match this payment to your booking. If money left your account, call us with your booking number.", 404)
    return payment

def verify(db: Session, ticket: ServiceRequest, order_id: str, payment_id: str, signature: str) -> None:
    """Checkout's success handler: count the payment if Razorpay's signature over order|payment checks out."""
    payment = _find(db, ticket, order_id)
    if payment.provider == "test":
        ok = mode() == "test" and payment_id.startswith("pay_test_")
    else:
        ok = _valid(f"{order_id}|{payment_id}".encode(), signature, config.RAZORPAY_KEY_SECRET)
    if not ok:
        raise PaymentError("We couldn't confirm this payment. If money left your account, call us with your booking number.", 422)
    mark_paid(db, payment, payment_id)

def refresh(db: Session, ticket: ServiceRequest) -> None:
    """Ask Razorpay about unpaid orders and links, for when the customer is back from paying before the webhook lands."""
    for payment in _rows(db, ticket):
        if payment.status != "created" or payment.provider != "razorpay":
            continue
        if payment.kind == "link":
            link = _api("GET", f"/payment_links/{payment.provider_order_id}")
            if link.get("status") == "paid":
                paid = [p for p in link.get("payments") or [] if p.get("status") == "captured"]
                mark_paid(db, payment, paid[-1]["payment_id"] if paid else None, paid[-1].get("method") if paid else None)
        elif _api("GET", f"/orders/{payment.provider_order_id}").get("status") == "paid":
            captured = [p for p in _api("GET", f"/orders/{payment.provider_order_id}/payments").get("items", []) if p.get("status") == "captured"]
            mark_paid(db, payment, captured[-1]["id"] if captured else None, captured[-1].get("method") if captured else None)

def mark_paid(db: Session, payment: Payment, payment_id: str | None, method: str | None = None) -> None:
    if payment.status != "created":
        return
    ticket = payment.service_request
    already = any(p.status != "created" for p in _rows(db, ticket) if p.id != payment.id)
    payment.status, payment.provider_payment_id, payment.method, payment.paid_at, payment.failure_reason = "paid", payment_id, method, utcnow(), None
    rupees = payment.amount_paise // 100
    tickets.add_event(db, ticket, "payment_received", None, new={"amount": rupees, "reference": payment_id, "method": method})
    meeting = _booking(ticket)
    if already or meeting is None or meeting.status == "cancelled":
        _refund_due(db, payment, "Paid twice for one booking." if already else "Paid after the booking was cancelled.")
    tickets.audit(db, None, "payment.received", ticket.id, payment_id=str(payment.id), amount=rupees)

def _refund_due(db: Session, payment: Payment, reason: str) -> None:
    payment.status = "refund_due"
    tickets.add_event(db, payment.service_request, "payment_refund_due", None, new={"amount": payment.amount_paise // 100, "reference": payment.provider_payment_id}, reason=reason)

def booking_cancelled(db: Session, ticket: ServiceRequest) -> None:
    """A cancelled booking with nothing else scheduled on its ticket gets its fee back."""
    if any(m.status == "scheduled" for m in ticket.meetings):
        return
    for payment in _rows(db, ticket):
        if payment.status == "paid":
            _refund_due(db, payment, "The consultation was cancelled.")

def release_unpaid(db: Session, now: datetime | None = None) -> int:
    """Cancel online bookings whose fee is still unpaid PAYMENT_HOLD_MINUTES after booking, freeing the slot."""
    if config.PAYMENT_HOLD_MINUTES <= 0 or mode() == "off":
        return 0
    now = now or utcnow()
    stale = db.scalars(
        select(Meeting).where(
            Meeting.status == "scheduled", Meeting.created_by_user_id.is_(None),
            Meeting.created_at < now - timedelta(minutes=config.PAYMENT_HOLD_MINUTES),
        ).with_for_update(skip_locked=True, of=Meeting)
    ).unique().all()
    released = 0
    for meeting in stale:
        ticket = meeting.service_request
        if amount_due(ticket) is None or meeting is not _booking(ticket):
            continue
        try:
            refresh(db, ticket)
        except PaymentError:
            continue  # Razorpay can't tell us; try again next round rather than drop a booking that may be paid.
        if any(p.status != "created" for p in _rows(db, ticket)):
            continue
        meetings.cancel_meeting(db, meeting, None, f"The fee wasn't paid within {config.PAYMENT_HOLD_MINUTES} minutes of booking, so the time was released. You're welcome to book again.")
        if ticket.status not in ("completed", "cancelled", "rejected"):
            tickets.change_status(db, ticket, "cancelled", None, "Booking released because the fee wasn't paid.")
        tickets.audit(db, None, "booking.released", ticket.id, meeting_id=str(meeting.id))
        released += 1
    db.commit()
    return released

@router.post("/api/v1/payments/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay events: order.paid, payment_link.paid, payment.failed and refund.processed. Others are ignored."""
    if not config.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")
    body = await request.body()
    if not _valid(body, request.headers.get("X-Razorpay-Signature"), config.RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Bad signature.")
    event = json.loads(body)
    name, payload = event.get("event"), event.get("payload") or {}
    entity = lambda key: (payload.get(key) or {}).get("entity") or {}
    paid = entity("payment")
    by_order = lambda order_id: db.scalars(select(Payment).where(Payment.provider_order_id == order_id)).first() if order_id else None

    if name in ("order.paid", "payment_link.paid"):
        payment = by_order(entity("order" if name == "order.paid" else "payment_link").get("id"))
        if payment:
            mark_paid(db, payment, paid.get("id"), paid.get("method"))
    elif name == "payment.failed":
        payment = by_order(paid.get("order_id"))
        if payment and payment.status == "created":
            payment.failure_reason = (paid.get("error_description") or "The payment didn't go through.")[:300]
            tickets.add_event(db, payment.service_request, "payment_failed", None, new={"amount": payment.amount_paise // 100, "method": paid.get("method")}, reason=payment.failure_reason)
    elif name == "refund.processed":
        refund = entity("refund")
        payment = db.scalars(select(Payment).where(Payment.provider_payment_id == refund.get("payment_id"))).first() if refund.get("payment_id") else None
        if payment and payment.status in ("paid", "refund_due"):
            payment.status = "refunded"
            tickets.add_event(db, payment.service_request, "payment_refunded", None, new={"amount": int(refund.get("amount") or payment.amount_paise) // 100, "reference": refund.get("id")})
    db.commit()
    return {"ok": True}
