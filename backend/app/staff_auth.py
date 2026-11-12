"""Staff recovery and RFC 6238 MFA. Tokens/codes are single-use; secrets stay out of logs."""
import base64
import hashlib
import hmac
import io
import logging
import secrets
import struct
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import qrcode
from qrcode.image.svg import SvgPathImage
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import config, notification_providers as providers
from .db import get_db
from .staff_session_records import invalidate_sessions
from .models import AuditLog, StaffAuthBucket, StaffAuthToken, User, utcnow
from .security import (_UNAUTHORIZED, create_access_token, current_security_staff, current_staff,
                       hash_password, verify_password)

router = APIRouter(prefix="/api/v1/auth")
log = logging.getLogger("homexo.staff_auth")
_DUMMY_PASSWORD = hash_password(secrets.token_urlsafe(24))


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class TokenCode(BaseModel):
    token: str = Field(min_length=30, max_length=128)
    code: str = Field(min_length=1, max_length=64)

class ResetRequest(BaseModel):
    token: str = Field(min_length=30, max_length=128)
    password: str = Field(min_length=12, max_length=200)
    code: str = Field(default="", max_length=64)

class PasswordProof(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(default="", max_length=64)

class PasswordChange(PasswordProof):
    new_password: str = Field(min_length=12, max_length=200)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def _hash(purpose, value):
    return hmac.new(config.JWT_SECRET.encode(), f"staff:{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

def _eligible(user):
    return user and user.account_status == "active" and user.role_names & {"admin", "agent", "super_admin"}

def audit(db, user, action):
    db.add(AuditLog(actor_user_id=user.id, action=action, entity_type="staff_security", entity_id=user.id, metadata_={}))

def throttle(db, scope, identity, limit, seconds=900):
    """Atomic upsert holds across API workers. Only salted identity hashes are persisted."""
    now = utcnow()
    window = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, timezone.utc)
    key = _hash("rate", f"{scope}:{identity}")
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert(StaffAuthBucket).values(key=key, window_start=window, attempts=1)
    statement = statement.on_conflict_do_update(index_elements=[StaffAuthBucket.key], set_={
        "window_start": window,
        "attempts": case((StaffAuthBucket.window_start < window, 1), else_=StaffAuthBucket.attempts + 1),
    }).returning(StaffAuthBucket.attempts)
    attempts = db.scalar(statement)
    db.commit()
    if attempts > limit:
        retry = max(1, int((window + timedelta(seconds=seconds) - now).total_seconds()))
        raise HTTPException(429, "Too many attempts. Please wait and try again.", headers={"Retry-After": str(retry)})

def _client(request):
    # Proxy headers are handled by uvicorn's explicit forwarded-allow-ips, never trusted here.
    return request.client.host if request.client else "unknown"

def _cipher():
    key = config.STAFF_MFA_ENCRYPTION_KEY
    if not key and config.APP_ENV == "development":
        key = base64.urlsafe_b64encode(hashlib.sha256((config.JWT_SECRET + ":staff-mfa-development").encode()).digest())
    try:
        if not key:
            raise ValueError
        return Fernet(key)
    except (ValueError, TypeError):
        raise HTTPException(503, "Authenticator protection is unavailable. Contact the administrator.")

def _decrypt(ciphertext):
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise HTTPException(503, "Authenticator protection is unavailable. Contact the administrator.")

def totp(secret, counter):
    digest = hmac.new(base64.b32decode(secret), struct.pack("!Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('!I', digest[offset:offset+4])[0] & 0x7fffffff) % 1000000:06d}"

def _counter(secret, code, last=None):
    code = code.strip()
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    current = int(utcnow().timestamp()) // 30
    for counter in (current, current - 1, current + 1):
        if (last is None or counter > last) and hmac.compare_digest(totp(secret, counter), code):
            return counter
    return None

def _factor(user, code):
    if not user.mfa_secret:
        return True
    normalized = code.strip().replace("-", "").upper()
    digest = _hash("recovery", f"{user.id}:{normalized}")
    for stored in user.mfa_recovery_hashes or []:
        if hmac.compare_digest(stored, digest):
            user.mfa_recovery_hashes = [h for h in user.mfa_recovery_hashes if h != stored]
            return True
    counter = _counter(_decrypt(user.mfa_secret), code, user.mfa_last_counter)
    if counter is None:
        return False
    user.mfa_last_counter = counter
    return True

def _recovery_codes(user):
    raw = [secrets.token_hex(8).upper() for _ in range(8)]
    user.mfa_recovery_hashes = [_hash("recovery", f"{user.id}:{code}") for code in raw]
    return ["-".join(code[i:i+4] for i in range(0, 16, 4)) for code in raw]

def _new_token(db, user, purpose, minutes):
    now = utcnow()
    # Reset requests supersede previous reset links; multiple login challenges may coexist.
    if purpose == "reset":
        db.execute(update(StaffAuthToken).where(StaffAuthToken.user_id == user.id, StaffAuthToken.purpose == purpose,
                   StaffAuthToken.used_at.is_(None)).values(used_at=now))
    raw = secrets.token_urlsafe(32)
    row = StaffAuthToken(user_id=user.id, token_hash=_hash(purpose, raw), purpose=purpose,
                         token_version=user.token_version, expires_at=now + timedelta(minutes=minutes))
    db.add(row)
    return raw, row

def _token_user(db, raw, purpose):
    row = db.scalar(select(StaffAuthToken).where(StaffAuthToken.token_hash == _hash(purpose, raw), StaffAuthToken.purpose == purpose))
    if row is None:
        raise HTTPException(401, "This request is invalid or has expired. Start again.")
    # Always lock the user before a token to avoid races with reset/enrollment/recovery changes.
    user = db.scalar(select(User).where(User.id == row.user_id).with_for_update().execution_options(populate_existing=True))
    db.refresh(row, with_for_update=True)
    if not _eligible(user) or row.used_at or _aware(row.expires_at) <= utcnow() or row.token_version != user.token_version or row.attempts >= 5:
        raise HTTPException(401, "This request is invalid or has expired. Start again.")
    return user, row

def _locked(db, user):
    version = user.token_version
    user = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not _eligible(user) or user.token_version != version:
        raise _UNAUTHORIZED
    return user

def _proof(user, payload):
    if not verify_password(payload.password, user.password_hash) or not _factor(user, payload.code):
        raise HTTPException(400, "Check your password and authenticator or recovery code.")

def _session(db, user, request, *, mfa=False):
    from .admin import _me
    return {"access_token": create_access_token(user, mfa=mfa, db=db, user_agent=request.headers.get("user-agent", "")), "token_type": "bearer", "user": _me(user)}


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    throttle(db, "login-ip", _client(request), 60)
    throttle(db, "login-account", email, 10)
    user = db.scalar(select(User).where(func.lower(User.email) == email).with_for_update())
    valid = verify_password(payload.password, user.password_hash if user and user.password_hash else _DUMMY_PASSWORD)
    if not _eligible(user) or not valid:
        raise HTTPException(401, "Email or password is incorrect.")
    if user.mfa_secret:
        raw, _ = _new_token(db, user, "mfa", 5)
        db.commit()
        return {"mfa_required": True, "challenge_token": raw}
    if config.STAFF_REQUIRE_ADMIN_MFA and user.is_admin:
        return {"mfa_setup_required": True, "setup_token": create_access_token(user, setup=True)}
    audit(db, user, "staff.login")
    result = _session(db, user, request)
    db.commit()
    return result


@router.post("/login/mfa")
def login_mfa(payload: TokenCode, request: Request, db: Session = Depends(get_db)):
    throttle(db, "mfa-ip", _client(request), 60)
    user, row = _token_user(db, payload.token, "mfa")
    row.attempts += 1
    if not user.mfa_secret or not _factor(user, payload.code):
        db.commit()
        raise HTTPException(401, "That code is incorrect, expired or already used.")
    row.used_at = utcnow()
    audit(db, user, "staff.login_mfa")
    result = _session(db, user, request, mfa=True)
    db.commit()
    return result


def _send_reset(token_id, email, raw):
    from .db import SessionLocal
    try:
        providers.send_staff_reset(email, raw, str(token_id))
    except providers.DeliveryError as exc:
        log.warning("Staff password reset delivery failed: %s", exc.code)
        with SessionLocal() as db:
            db.execute(update(StaffAuthToken).where(StaffAuthToken.id == token_id).values(used_at=utcnow()))
            db.commit()


@router.post("/password-reset/request")
def request_reset(payload: EmailRequest, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    throttle(db, "reset-ip", _client(request), 10, 3600)
    throttle(db, "reset-account", email, 3, 3600)
    if not providers.enabled("email"):
        raise HTTPException(503, "Password recovery email is unavailable. Contact the administrator.")
    user = db.scalar(select(User).where(func.lower(User.email) == email).with_for_update())
    if _eligible(user) and user.password_hash:
        raw, row = _new_token(db, user, "reset", 20)
        audit(db, user, "staff.password_reset_requested")
        db.commit()
        background.add_task(_send_reset, row.id, user.email, raw)
    return {"message": "If this email belongs to an active staff account, a reset link will arrive shortly. Check spam too."}


@router.post("/password-reset/confirm")
def reset_password(payload: ResetRequest, request: Request, db: Session = Depends(get_db)):
    throttle(db, "reset-confirm-ip", _client(request), 30)
    user, row = _token_user(db, payload.token, "reset")
    row.attempts += 1
    if not _factor(user, payload.code):
        db.commit()
        raise HTTPException(401, "Enter a current authenticator code or an unused recovery code.")
    user.password_hash = hash_password(payload.password)
    user.token_version += 1
    invalidate_sessions(db, user)
    row.used_at = utcnow()
    user.mfa_pending_secret = user.mfa_pending_until = None
    audit(db, user, "staff.password_reset")
    db.commit()
    return {"message": "Password updated. Sign in again on all devices."}


@router.get("/security")
def security_status(user: User = Depends(current_staff)):
    return {"mfa_enabled": bool(user.mfa_secret), "mfa_required": bool(user.is_admin and config.STAFF_REQUIRE_ADMIN_MFA),
            "recovery_codes_remaining": len(user.mfa_recovery_hashes or [])}


@router.post("/mfa/setup")
def setup_mfa(payload: PasswordProof, request: Request, user: User = Depends(current_security_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(400, "Check your password.")
    if user.mfa_secret:
        raise HTTPException(409, "Two-factor sign-in is already enabled.")
    cipher = _cipher()
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    user.mfa_pending_secret = cipher.encrypt(secret.encode()).decode()
    user.mfa_pending_until = utcnow() + timedelta(minutes=10)
    uri = "otpauth://totp/" + quote("Homexo Legal:" + user.email, safe="") + "?" + urlencode({"secret": secret, "issuer": "Homexo Legal", "algorithm": "SHA1", "digits": 6, "period": 30})
    image = qrcode.make(uri, image_factory=SvgPathImage)
    output = io.BytesIO(); image.save(output)
    audit(db, user, "staff.mfa_setup_started")
    db.commit()
    return {"secret": secret, "uri": uri, "qr_image": "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode(), "expires_in": 600}


@router.post("/mfa/enable")
def enable_mfa(payload: PasswordProof, request: Request, user: User = Depends(current_security_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(400, "Check your password.")
    if user.mfa_secret or not user.mfa_pending_secret or not user.mfa_pending_until or _aware(user.mfa_pending_until) <= utcnow():
        raise HTTPException(409, "Start authenticator setup again.")
    counter = _counter(_decrypt(user.mfa_pending_secret), payload.code)
    if counter is None:
        raise HTTPException(400, "Enter the current six-digit code from your authenticator.")
    user.mfa_secret, user.mfa_last_counter = user.mfa_pending_secret, counter
    user.mfa_pending_secret = user.mfa_pending_until = None
    codes = _recovery_codes(user)
    user.token_version += 1
    invalidate_sessions(db, user)
    audit(db, user, "staff.mfa_enabled")
    result = _session(db, user, request, mfa=True) | {"recovery_codes": codes}
    db.commit()
    return result


@router.post("/mfa/recovery-codes")
def regenerate_codes(payload: PasswordProof, request: Request, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    if not user.mfa_secret:
        raise HTTPException(409, "Enable two-factor sign-in first.")
    _proof(user, payload)
    codes = _recovery_codes(user)
    user.token_version += 1
    invalidate_sessions(db, user)
    audit(db, user, "staff.recovery_codes_regenerated")
    result = _session(db, user, request, mfa=True) | {"recovery_codes": codes}
    db.commit()
    return result


@router.post("/mfa/disable")
def disable_mfa(payload: PasswordProof, request: Request, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    if user.is_admin and config.STAFF_REQUIRE_ADMIN_MFA:
        raise HTTPException(409, "Two-factor sign-in is required for administrators.")
    _proof(user, payload)
    user.mfa_secret = user.mfa_pending_secret = user.mfa_pending_until = user.mfa_last_counter = user.mfa_recovery_hashes = None
    user.token_version += 1
    invalidate_sessions(db, user)
    audit(db, user, "staff.mfa_disabled")
    result = _session(db, user, request)
    db.commit()
    return result


@router.post("/password/change")
def change_password(payload: PasswordChange, request: Request, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    _proof(user, payload)
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    invalidate_sessions(db, user)
    user.mfa_pending_secret = user.mfa_pending_until = None
    audit(db, user, "staff.password_changed")
    result = _session(db, user, request, mfa=bool(user.mfa_secret))
    db.commit()
    return result


@router.post("/logout-all")
def logout_all(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    throttle(db, "security", str(user.id), 20)
    user = _locked(db, user)
    user.token_version += 1
    invalidate_sessions(db, user, "all_sessions")
    audit(db, user, "staff.sessions_revoked")
    db.commit()
    return {"message": "Signed out on all devices."}


def cleanup():
    """Run daily to bound expired tokens and throttle records without retaining client identifiers."""
    from .db import SessionLocal
    with SessionLocal() as db:
        cutoff = utcnow() - timedelta(days=1)
        db.execute(delete(StaffAuthToken).where(StaffAuthToken.expires_at < cutoff))
        db.execute(delete(StaffAuthBucket).where(StaffAuthBucket.window_start < cutoff))
        db.commit()


if __name__ == "__main__":
    cleanup()
