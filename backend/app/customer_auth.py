"""Verified customer sessions and ownership checks shared by every customer API."""
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import config
from .db import get_db
from .models import Customer, CustomerAccount, ServiceRequest

_AUDIENCE = "homexo-customer"
_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(status_code=401, detail="Sign in with your phone to access your requests, documents and bookings.", headers={"WWW-Authenticate": "Bearer"})

def create_session_token(account: CustomerAccount) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(account.id), "ver": account.token_version, "aud": _AUDIENCE, "iat": now, "exp": now + timedelta(days=config.CUSTOMER_SESSION_DAYS)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

def current_customer(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> CustomerAccount:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=["HS256"], audience=_AUDIENCE, options={"require": ["sub", "aud", "exp", "iat", "ver"]})
        account_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED
    account = db.get(CustomerAccount, account_id)
    if account is None or payload.get("ver") != account.token_version:
        raise _UNAUTHORIZED
    return account

def optional_customer(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> CustomerAccount | None:
    return current_customer(credentials, db) if credentials is not None else None


def owned_ticket(db: Session, ticket_number: str, account: CustomerAccount) -> ServiceRequest:
    ticket = db.scalars(select(ServiceRequest).join(Customer, ServiceRequest.customer_id == Customer.id).where(
        ServiceRequest.ticket_number == ticket_number.strip().upper(),
        Customer.phone_normalized == account.phone_normalized,
    )).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="We couldn't find that request on your account.")
    return ticket
