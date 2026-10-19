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
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

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

def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})

def current_staff(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED
    user = db.get(User, user_id)
    # Staff are users holding an agent or admin role; anything else (or a disabled account) is rejected.
    if user is None or user.account_status != "active" or not (user.role_names & {"agent", "admin", "super_admin"}):
        raise _UNAUTHORIZED
    return user

def require_admin(user: User = Depends(current_staff)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can do this.")
    return user
