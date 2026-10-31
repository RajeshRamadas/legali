"""Customer accounts: sign in with a one-time code sent to the phone, then see every request, booking, payment and
document raised with that number in one place.

An account is keyed by the phone number it proved, so tickets and bookings made before signing up (and from the app or
the website) show up as soon as the customer signs in. Signed-in clients keep using the existing ticket and booking
endpoints with the verified phone as the contact.
"""
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import case_files, config, payments, tickets, whatsapp, document_requirements
from .chat import client_key
from .db import get_db
from .lawyers import booking_view
from .models import CLOSED_STATUSES, Customer, CustomerAccount, LoginCode, ServiceRequest, utcnow

log = logging.getLogger("homexo.accounts")

router = APIRouter(prefix="/api/v1/account")

_AUDIENCE = "homexo-customer"
_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
WRONG_CODE = "That code is wrong or has expired. Check the latest message, or ask for a new code."
# Requests listed on the account page, newest first.
MAX_REQUESTS = 100

class CodeRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=20)

class CodeCheck(CodeRequest):
    code: str = Field(min_length=4, max_length=8)

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _phone(value: str) -> str:
    digits = tickets.normalize_phone(value)
    if len(digits) < 10:
        raise HTTPException(status_code=422, detail="phone: Enter your 10-digit mobile number.")
    return digits

def _hash(phone: str, code: str) -> str:
    return hmac.new(config.JWT_SECRET.encode(), f"login:{phone}:{code}".encode(), hashlib.sha256).hexdigest()

def delivery_channel() -> str | None:
    """How codes go out: "whatsapp", "dev" (shown on screen, development only) or None when sign-in is unavailable."""
    if whatsapp.enabled():
        return "whatsapp"
    return "dev" if config.LOGIN_CODE_DEV_MODE else None

def _count_since(db: Session, column, value: str, since: datetime) -> int:
    return db.scalar(select(func.count()).select_from(LoginCode).where(column == value, LoginCode.created_at >= since)) or 0

def display_phone(phone: str) -> str:
    return f"+{config.WHATSAPP_DEFAULT_COUNTRY_CODE} {phone[:5]} {phone[5:]}" if len(phone) == 10 else phone

@router.post("/login/start")
def start_login(payload: CodeRequest, request: Request, db: Session = Depends(get_db)):
    phone = _phone(payload.phone)
    channel = delivery_channel()
    if channel is None:
        raise HTTPException(status_code=503, detail="Signing in by phone isn't available right now. You can still track a request with its ticket number.")
    now = utcnow()
    key = client_key(request)
    hour_ago = now - timedelta(hours=1)
    if (_count_since(db, LoginCode.phone_normalized, phone, hour_ago) >= config.LOGIN_CODES_PER_PHONE_PER_HOUR
            or _count_since(db, LoginCode.client_key, key, hour_ago) >= config.LOGIN_CODES_PER_CLIENT_PER_HOUR):
        raise HTTPException(status_code=429, detail="Too many codes asked for. Please wait an hour and try again, or call us.")
    latest = db.scalars(select(LoginCode).where(LoginCode.phone_normalized == phone).order_by(LoginCode.created_at.desc())).first()
    if latest and tickets.aware(latest.created_at) > now - timedelta(seconds=config.LOGIN_CODE_RESEND_SECONDS):
        raise HTTPException(status_code=429, detail="We just sent a code. Please wait a few seconds before asking for another.")

    code = f"{secrets.randbelow(10**6):06d}"
    if channel == "whatsapp":
        try:
            whatsapp.send_template(phone, config.LOGIN_CODE_TEMPLATE, [code], button_param=code)
        except whatsapp.WhatsAppError as exc:
            log.warning("Login code to %s failed: %s", phone[-4:], exc)
            raise HTTPException(status_code=502, detail="We couldn't send the code on WhatsApp. Check the number has WhatsApp, or try again shortly.")
    else:
        log.warning("Dev mode login code for %s: %s", display_phone(phone), code)
    # Only the newest code works.
    for old in db.scalars(select(LoginCode).where(LoginCode.phone_normalized == phone, LoginCode.used_at.is_(None))).all():
        old.used_at = now
    db.add(LoginCode(phone_normalized=phone, code_hash=_hash(phone, code), channel=channel, client_key=key,
                     expires_at=now + timedelta(minutes=config.LOGIN_CODE_MINUTES)))
    db.commit()
    result = {"phone": display_phone(phone), "channel": channel, "expires_in": config.LOGIN_CODE_MINUTES * 60, "resend_after": config.LOGIN_CODE_RESEND_SECONDS}
    if channel == "dev":
        result["dev_code"] = code
    return result

def create_session_token(account: CustomerAccount) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(account.id), "ver": account.token_version, "aud": _AUDIENCE, "iat": now, "exp": now + timedelta(days=config.CUSTOMER_SESSION_DAYS)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

def _latest_customer(db: Session, phone: str) -> Customer | None:
    return db.scalars(select(Customer).where(Customer.phone_normalized == phone).order_by(Customer.created_at.desc())).first()

@router.post("/login/verify")
def verify_login(payload: CodeCheck, db: Session = Depends(get_db)):
    phone = _phone(payload.phone)
    now = utcnow()
    login = db.scalars(
        select(LoginCode).where(LoginCode.phone_normalized == phone, LoginCode.used_at.is_(None)).order_by(LoginCode.created_at.desc()).with_for_update()
    ).first()
    if login is None or tickets.aware(login.expires_at) <= now or login.attempts >= config.LOGIN_CODE_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail=WRONG_CODE)
    if not hmac.compare_digest(login.code_hash, _hash(phone, payload.code.strip())):
        login.attempts += 1
        db.commit()
        raise HTTPException(status_code=400, detail=WRONG_CODE)
    login.used_at = now

    account = db.scalars(select(CustomerAccount).where(CustomerAccount.phone_normalized == phone)).first()
    if account is None:
        # Start from what they told us on their latest request, if they have one.
        known = _latest_customer(db, phone)
        account = CustomerAccount(phone_normalized=phone, full_name=known.full_name if known else None, email=known.email if known else None)
        db.add(account)
    account.last_login_at = now
    db.commit()
    return {"access_token": create_session_token(account), "token_type": "bearer", "account": _profile(account)}

def current_customer(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> CustomerAccount:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=["HS256"], audience=_AUDIENCE)
        account_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED
    account = db.get(CustomerAccount, account_id)
    if account is None or payload.get("ver") != account.token_version:
        raise _UNAUTHORIZED
    return account

def _profile(account: CustomerAccount) -> dict:
    return {
        "name": account.full_name,
        "phone": display_phone(account.phone_normalized),
        "email": account.email,
        # What the ticket, document and booking endpoints take as `contact` for this customer's requests.
        "contact": account.phone_normalized,
    }

def _needs_you(ticket: ServiceRequest) -> str | None:
    """A short line when the customer has something to do on this request."""
    if ticket.status in CLOSED_STATUSES:
        return None
    if ticket.status == "waiting_for_customer":
        return "Waiting for your reply"
    report = ticket.report
    if report is not None and report.status == "issued":
        if any(i.status == "rejected" for i in report.items):
            return "A document needs uploading again"
        if any(i.status == "pending" and i.fetch_by == "customer" for i in report.items):
            return "Documents to upload"
    if document_requirements.view(ticket)["missing_count"]:
        return "Documents to upload"
    return None

def _request_summary(ticket: ServiceRequest) -> dict:
    report = case_files.customer_report_view(ticket)
    upcoming = [m for m in ticket.meetings if m.status == "scheduled" and tickets.aware(m.ends_at) > utcnow()]
    return {
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "service_name": ticket.service_type.name,
        "package": ticket.package,
        "kind": "consultation" if (ticket.structured_answers or {}).get("booked_online") else "request",
        "status": ticket.status,
        "status_label": tickets.status_label(ticket.status),
        "created_at": tickets.aware(ticket.created_at).isoformat(),
        "updated_at": tickets.aware(ticket.updated_at).isoformat(),
        "documents": len(case_files.case_documents(ticket)),
        "report": {"status_label": report["status_label"], "progress": report["progress"], "signed": report["status"] == "signed"} if report else None,
        "next_meeting": tickets.meeting_view(upcoming[0]) if upcoming else None,
        "needs_you": _needs_you(ticket),
    }

def _payment_row(booking: dict) -> dict:
    payment = booking["payment"]
    return {
        "ticket_number": booking["ticket_number"],
        "description": f"Consultation with {booking['lawyer']['name']}",
        "when": booking["meeting"]["when"],
        **{key: payment[key] for key in ("status", "amount", "paid_at", "method", "reference", "can_pay")},
    }

def _customer_tickets(db: Session, account: CustomerAccount) -> list[ServiceRequest]:
    return list(db.scalars(
        select(ServiceRequest).join(Customer, ServiceRequest.customer_id == Customer.id)
        .where(Customer.phone_normalized == account.phone_normalized)
        .order_by(ServiceRequest.created_at.desc()).limit(MAX_REQUESTS)
    ).unique().all())

@router.get("")
def account_overview(account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    """Everything raised with the account's phone: requests, consultation bookings and their payments."""
    owned = _customer_tickets(db, account)
    bookings = [
        booking_view(db, t, max(t.meetings, key=lambda m: m.created_at))
        for t in owned if (t.structured_answers or {}).get("booked_online") and t.meetings
    ]
    return {
        "profile": _profile(account),
        "requests": [_request_summary(t) for t in owned],
        "bookings": bookings,
        "payments": [_payment_row(b) for b in bookings if b["payment"]],
        "payments_mode": payments.mode(),
    }

@router.get("/requests/{ticket_number}")
def account_request(ticket_number: str, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    ticket = db.scalars(
        select(ServiceRequest).join(Customer, ServiceRequest.customer_id == Customer.id)
        .where(ServiceRequest.ticket_number == ticket_number.strip().upper(), Customer.phone_normalized == account.phone_normalized)
    ).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="We couldn't find that request on your account.")
    return tickets.customer_view(ticket)

@router.patch("")
def update_profile(payload: ProfileUpdate, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    if payload.full_name is not None:
        account.full_name = payload.full_name.strip()
    if payload.email is not None:
        account.email = payload.email.strip().lower() or None
    db.commit()
    return _profile(account)

@router.post("/logout-all")
def logout_everywhere(account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    """Ends every session of this account, including the one making the call."""
    account.token_version += 1
    db.commit()
    return {"ok": True}
