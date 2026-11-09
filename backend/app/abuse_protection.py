"""Pre-body API budgets and bounded request streams. Never trust forwarded identity headers."""
import hashlib
import hmac
import ipaddress
import logging
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from . import config
from .db import SessionLocal
from .models import ApiRateBucket, utcnow

log = logging.getLogger("homexo.abuse_protection")
JSON_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Policy:
    group: str
    limit: int
    seconds: int = 60
    max_bytes: int = JSON_MAX_BYTES


def policy_for(method, path):
    path = path.rstrip("/")
    if method == "POST":
        if path == "/api/v1/tickets" or re.fullmatch(r"/api/v1/lawyers/[^/]+/bookings", path) or re.fullmatch(r"/api/v1/intake/drafts/[^/]+/submit", path):
            return Policy("submissions", config.API_SUBMISSIONS_PER_HOUR, 3600)
        if path == "/api/v1/tickets/documents" or re.fullmatch(r"/api/v1/admin/tickets/[^/]+/(documents|report/signed)", path):
            return Policy("uploads", config.API_UPLOADS_PER_MINUTE, max_bytes=(config.UPLOAD_MAX_MB + 1) * 1024 * 1024)
        if re.fullmatch(r"/api/v1/admin/tickets/[^/]+/(verification|documents/[^/]+/(check|scan))", path):
            return Policy("expensive_checks", config.API_AI_ACTIONS_PER_MINUTE)
        if path == "/api/v1/chat":
            return Policy("chat", max(1, config.CHAT_RATE_LIMIT_PER_MINUTE))
        if path in ("/api/v1/tickets/lookup", "/api/v1/bookings/lookup"):
            return Policy("lookups", config.API_LOOKUPS_PER_MINUTE)
        if path.startswith("/api/v1/auth/") or path in ("/api/v1/account/login/start", "/api/v1/account/login/verify"):
            return Policy("authentication", config.API_AUTH_PER_MINUTE)
    if method == "GET":
        if path.startswith("/api/v1/files/"):
            return Policy("downloads", config.API_DOWNLOADS_PER_MINUTE)
        if path == "/api/v1/account" or path.startswith(("/api/v1/account/requests/", "/api/v1/account/privacy-requests", "/api/v1/intake/drafts")):
            return Policy("lookups", config.API_LOOKUPS_PER_MINUTE)
    if method in ("POST", "PATCH", "DELETE") and (
        path in ("/api/v1/tickets/messages", "/api/v1/tickets/property-intake", "/api/v1/tickets/documents/tag", "/api/v1/tickets/documents/delete", "/api/v1/account", "/api/v1/account/logout-all")
        or path.startswith("/api/v1/intake/drafts") or path.startswith("/api/v1/bookings/") or path.startswith("/api/v1/account/privacy-requests") or path.startswith("/api/v1/admin/privacy-requests")):
        return Policy("customer_writes", config.API_WRITES_PER_MINUTE)
    return None


def _key(group, identity):
    return hmac.new(config.JWT_SECRET.encode(), f"api-budget:{group}:{identity}".encode(), hashlib.sha256).hexdigest()


def session_identity(header):
    if len(header) > 4096:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        claims = jwt.decode(parts[1], config.JWT_SECRET, algorithms=["HS256"], audience=["homexo-customer", "homexo-staff"],
            options={"require": ["sub", "aud", "exp", "iat", "ver"]})
        if claims["aud"] not in ("homexo-customer", "homexo-staff"):
            return None
        return f"session:{claims['aud']}:{uuid.UUID(claims['sub'])}"
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError):
        return None


def client_identity(scope):
    host = (scope.get("client") or ("unknown", 0))[0]
    try:
        address = ipaddress.ip_address(host)
        host = str(address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address)
    except ValueError:
        host = host.lower()
    return "client:" + host


def consume(policy, identities, now=None):
    """Consume both budgets in an independent transaction; failed endpoint work cannot roll them back."""
    now = now or utcnow()
    window = datetime.fromtimestamp(int(now.timestamp()) // policy.seconds * policy.seconds, timezone.utc)
    with SessionLocal() as db:
        insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
        retry = 0
        for key in sorted({_key(policy.group, identity) for identity in identities}):
            statement = insert(ApiRateBucket).values(key=key, window_start=window, attempts=1)
            statement = statement.on_conflict_do_update(index_elements=[ApiRateBucket.key], set_={
                "window_start": case((ApiRateBucket.window_start < window, window), else_=ApiRateBucket.window_start),
                "attempts": case((ApiRateBucket.window_start < window, 1),
                    (ApiRateBucket.attempts <= policy.limit, ApiRateBucket.attempts + 1), else_=ApiRateBucket.attempts),
            }).returning(ApiRateBucket.attempts, ApiRateBucket.window_start)
            attempts, stored_window = db.execute(statement).one()
            if attempts > policy.limit:
                # SQLite drops timezone information; PostgreSQL preserves it.
                stored_window = stored_window.replace(tzinfo=timezone.utc)
                retry = max(retry, math.ceil((stored_window + timedelta(seconds=policy.seconds) - now).total_seconds()), 1)
        db.commit()
    return retry or None


async def reject(scope, receive, send, status, detail, retry=None):
    headers = {"Cache-Control": "private, no-store"}
    if retry:
        headers["Retry-After"] = str(retry)
    await JSONResponse({"detail": detail, **({"retry_after": retry} if retry else {})}, status_code=status, headers=headers)(scope, receive, send)


class AbuseProtection:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or (policy := policy_for(scope["method"], scope["path"])) is None:
            await self.app(scope, receive, send)
            return
        headers = scope.get("headers", [])
        scope["homexo.policy"] = policy.group
        authorizations = [value for name, value in headers if name.lower() == b"authorization"]
        if len(authorizations) > 1:
            await reject(scope, receive, send, 400, "Use one Authorization header.")
            return
        identities = [client_identity(scope)]
        identity = session_identity(authorizations[0].decode("latin-1")) if authorizations else None
        if identity:
            identities.append(identity)
        try:
            retry = await run_in_threadpool(consume, policy, identities)
        except SQLAlchemyError:
            log.warning("api_rate_limit_unavailable")
            await reject(scope, receive, send, 503, "We cannot accept this request right now. Please try again shortly.", 10)
            return
        if retry:
            await reject(scope, receive, send, 429, f"Too many requests. Please try again in {retry} seconds.", retry)
            return
        lengths = [value for name, value in headers if name.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or (lengths and int(lengths[0]) < 0):
                raise ValueError
            if lengths and int(lengths[0]) > policy.max_bytes:
                await reject(scope, receive, send, 413, "This request is too large. Reduce its size and try again.")
                return
        except ValueError:
            await reject(scope, receive, send, 400, "Invalid request size.")
            return
        size, started = 0, False

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > policy.max_bytes:
                    raise HTTPException(413, "This request is too large. Reduce its size and try again.")
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if message["status"] >= 400:
                    message["headers"] = [(name, value) for name, value in message.get("headers", []) if name.lower() != b"cache-control"]
                    message["headers"].append((b"cache-control", b"private, no-store"))
            await send(message)

        try:
            # GET downloads may listen for disconnects after sending their headers.
            # They never parse a request body, so only enforce their declared size.
            await self.app(scope, receive if scope["method"] == "GET" else bounded_receive, tracked_send)
        except HTTPException as exc:
            if exc.status_code != 413 or started:
                raise
            await reject(scope, receive, send, 413, exc.detail)


def cleanup():
    with SessionLocal() as db:
        db.execute(delete(ApiRateBucket).where(ApiRateBucket.window_start < utcnow() - timedelta(days=1)))
        db.commit()


if __name__ == "__main__":
    cleanup()
