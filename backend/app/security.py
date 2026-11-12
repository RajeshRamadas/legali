"""Staff authentication: password hashing, access tokens and role checks."""
import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal, get_db
from .models import StaffSession, User, utcnow
from .session_metadata import aware
from .staff_session_records import issue

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()

def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, salt_b64, digest_b64 = (stored or "").split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))

def create_access_token(user: User, *, mfa: bool = False, setup: bool = False, db: Session | None = None, user_agent: str = "") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "ver": user.token_version, "mfa": mfa,
               "aud": "homexo-staff-setup" if setup else "homexo-staff",
               "iat": now, "exp": now + timedelta(minutes=10 if setup else config.ACCESS_TOKEN_MINUTES)}
    if not setup:
        if db is None:
            # Standalone trusted callers require an already committed user.
            with SessionLocal() as session:
                key, version, now, expires = issue(session, user.id, user_agent)
                session.commit()
        else:
            key, version, now, expires = issue(db, user.id, user_agent)
        payload.update(jti=str(key), ver=version, iat=now, exp=expires)
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})

def _staff(credentials, db, *, allow_setup=False) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=["HS256"],
                             audience=["homexo-staff", "homexo-staff-setup"] if allow_setup else "homexo-staff",
                             options={"require": ["sub", "ver", "aud", "exp", "iat", "mfa"]})
        if not isinstance(payload.get("sub"), str) or type(payload.get("ver")) is not int or type(payload.get("mfa")) is not bool or payload.get("aud") not in ("homexo-staff", "homexo-staff-setup"):
            raise ValueError()
        user_id = uuid.UUID(payload["sub"])
        session_id = None
        if payload["aud"] == "homexo-staff":
            if not isinstance(payload.get("jti"), str):
                raise ValueError()
            session_id = uuid.UUID(payload["jti"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _UNAUTHORIZED
    user = db.get(User, user_id)
    # Staff are users holding an agent or admin role; anything else (or a disabled account) is rejected.
    if user is None or user.account_status != "active" or not (user.role_names & {"agent", "admin", "super_admin"}) or payload["ver"] != user.token_version:
        raise _UNAUTHORIZED
    if payload["aud"] == "homexo-staff-setup":
        if user.mfa_secret or not allow_setup:
            raise _UNAUTHORIZED
    elif (user.mfa_secret and payload["mfa"] is not True) or (config.STAFF_REQUIRE_ADMIN_MFA and user.is_admin and not user.mfa_secret):
        raise _UNAUTHORIZED
    if session_id is not None:
        row = db.execute(select(StaffSession.token_version, StaffSession.expires_at, StaffSession.last_seen_at, StaffSession.revoked_at)
            .where(StaffSession.id == session_id, StaffSession.user_id == user.id)).first()
        now = utcnow()
        if not row or row.revoked_at is not None or row.token_version != user.token_version or aware(row.expires_at) <= now:
            raise _UNAUTHORIZED
        user._authenticated_session_id = session_id
        if aware(row.last_seen_at) < now - timedelta(minutes=5):
            with SessionLocal() as activity:
                activity.execute(update(StaffSession).where(StaffSession.id == session_id, StaffSession.revoked_at.is_(None),
                    StaffSession.last_seen_at < now - timedelta(minutes=5)).values(last_seen_at=now))
                activity.commit()
    return user

def current_staff(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    return _staff(credentials, db)

def current_security_staff(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    """An enrollment token can only access the enrollment endpoints using this dependency."""
    return _staff(credentials, db, allow_setup=True)

def require_admin(user: User = Depends(current_staff)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can do this.")
    return user
