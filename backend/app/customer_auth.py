"""Verified customer sessions and ownership checks shared by every customer API."""
import uuid
from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from . import config
from .session_metadata import aware, device_labels
from .db import SessionLocal, get_db
from .models import AuditLog, Customer, CustomerAccount, CustomerSession, ServiceRequest, utcnow

_AUDIENCE = "homexo-customer"
_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(status_code=401, detail="Sign in with your phone to access your requests, documents and bookings.", headers={"WWW-Authenticate": "Bearer"})

MAX_ACTIVE_SESSIONS=20


def _issue(db,account_id,user_agent):
    account=db.scalar(select(CustomerAccount).where(CustomerAccount.id==account_id).with_for_update().execution_options(populate_existing=True))
    if account is None:raise _UNAUTHORIZED
    now=utcnow().replace(microsecond=0);expires=now+timedelta(days=config.CUSTOMER_SESSION_DAYS)
    if expires<=now:raise RuntimeError("Customer session lifetime must be positive.")
    active=db.scalars(select(CustomerSession).where(CustomerSession.account_id==account.id,CustomerSession.token_version==account.token_version,
        CustomerSession.revoked_at.is_(None),CustomerSession.expires_at>now).order_by(CustomerSession.created_at,CustomerSession.id)).all()
    expired=active[:max(0,len(active)-MAX_ACTIVE_SESSIONS+1)]
    for row in expired:row.revoked_at=now;row.revoke_reason="session_limit"
    if expired:db.add(AuditLog(action="customer.sessions_limited",entity_type="customer_account",entity_id=account.id,metadata_={"count":len(expired)}))
    browser,device=device_labels(user_agent)
    key=uuid.uuid4()
    db.add(CustomerSession(id=key,account_id=account.id,token_version=account.token_version,browser=browser,device=device,
        created_at=now,expires_at=expires,last_seen_at=now));db.flush()
    return jwt.encode({"sub":str(account.id),"jti":str(key),"ver":account.token_version,"aud":_AUDIENCE,"iat":now,"exp":expires},config.JWT_SECRET,algorithm="HS256")


def create_session_token(account:CustomerAccount,*,db:Session|None=None,user_agent:str="") -> str:
    if db is not None:return _issue(db,account.id,user_agent)
    # Standalone trusted callers must refer to an already committed account.
    with SessionLocal() as session:
        token=_issue(session,account.id,user_agent);session.commit();return token

def current_customer(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> CustomerAccount:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=["HS256"], audience=_AUDIENCE, options={"require": ["sub", "aud", "exp", "iat", "ver", "jti"]})
        if payload.get("aud")!=_AUDIENCE or type(payload.get("ver")) is not int or not isinstance(payload.get("sub"),str) or not isinstance(payload.get("jti"),str):raise ValueError()
        account_id = uuid.UUID(payload["sub"])
        session_id=uuid.UUID(payload["jti"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _UNAUTHORIZED
    account = db.get(CustomerAccount, account_id)
    if account is None or payload.get("ver") != account.token_version:
        raise _UNAUTHORIZED
    session=db.execute(select(CustomerSession.id,CustomerSession.token_version,CustomerSession.expires_at,CustomerSession.last_seen_at,CustomerSession.revoked_at)
        .where(CustomerSession.id==session_id,CustomerSession.account_id==account.id)).first()
    now=utcnow()
    if not session or session.revoked_at is not None or session.token_version!=account.token_version or aware(session.expires_at)<=now:
        raise _UNAUTHORIZED
    account._authenticated_session_id=session_id
    if aware(session.last_seen_at)<now-timedelta(minutes=5):
        with SessionLocal() as activity:
            activity.execute(update(CustomerSession).where(CustomerSession.id==session_id,CustomerSession.revoked_at.is_(None),
                CustomerSession.last_seen_at<now-timedelta(minutes=5)).values(last_seen_at=now));activity.commit()
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
