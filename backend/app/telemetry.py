"""Bounded operational metadata and privacy-safe request/worker events."""
import asyncio
import contextvars
import functools
import json
import logging
import time
import uuid

from sqlalchemy import case, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from .db import SessionLocal
from .models import WorkerPulse, utcnow

request_id = contextvars.ContextVar("request_id", default=None)
log = logging.getLogger("homexo.operations")
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
log.setLevel(logging.INFO)
log.propagate = False
WORKERS = {"notifications", "blog_scan", "verification"}
POLICIES = {"submissions", "uploads", "expensive_checks", "chat", "lookups", "authentication", "downloads", "customer_writes"}


def event(name, **fields):
    # Callers pass fixed-schema fields only. Never pass exception text, request data or URLs.
    record = {"event": name, "timestamp": utcnow().isoformat(), **fields}
    if request_id.get():
        record["request_id"] = request_id.get()
    log.info(json.dumps(record, separators=(",", ":")))


def disable_raw_access_logs():
    # Uvicorn's default access logger includes query strings and private download tokens.
    logging.getLogger("uvicorn.access").disabled = True


class WorkerConfigurationError(Exception):
    pass


def error_category(error):
    if isinstance(error, SQLAlchemyError):
        return "database_error"
    if isinstance(error, WorkerConfigurationError):
        return "worker_not_configured"
    return "task_failed"


def record_worker(name, started, *, finished=None, duration_ms=None, error_code=None):
    if name not in WORKERS:
        raise ValueError("Unknown worker group")
    if error_code not in (None, "database_error", "worker_not_configured", "task_failed"):
        raise ValueError("Unknown worker error category")
    try:
        with SessionLocal() as db:
            insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
            values = {"name": name, "started_at": started, "consecutive_failures": 0}
            if finished is None:
                changes = {"started_at": case((or_(WorkerPulse.started_at.is_(None), WorkerPulse.started_at < started), started), else_=WorkerPulse.started_at)}
                condition = None
            else:
                values.update(finished_at=finished, duration_ms=duration_ms, error_code=error_code,
                    consecutive_failures=1 if error_code else 0,
                    **({"last_failure_at": finished} if error_code else {"last_success_at": finished}))
                changes = {key: value for key, value in values.items() if key not in ("name", "started_at", "consecutive_failures")}
                changes["consecutive_failures"] = case((WorkerPulse.consecutive_failures < 1_000_000, WorkerPulse.consecutive_failures + 1), else_=WorkerPulse.consecutive_failures) if error_code else 0
                condition = or_(WorkerPulse.finished_at.is_(None), WorkerPulse.finished_at <= finished)
            statement = insert(WorkerPulse).values(**values).on_conflict_do_update(index_elements=[WorkerPulse.name], set_=changes, where=condition)
            db.execute(statement)
            db.commit()
    except SQLAlchemyError:
        event("worker_observation_unavailable", worker=name)


def observe_worker(name):
    def decorate(function):
        @functools.wraps(function)
        def observed(*args, **kwargs):
            started, clock = utcnow(), time.perf_counter()
            record_worker(name, started)
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                duration = min(2_147_483_647, max(0, round((time.perf_counter() - clock) * 1000)))
                code = error_category(error)
                record_worker(name, started, finished=utcnow(), duration_ms=duration, error_code=code)
                event("worker_failed", worker=name, duration_ms=duration, error_code=code)
                raise
            else:
                duration = min(2_147_483_647, max(0, round((time.perf_counter() - clock) * 1000)))
                record_worker(name, started, finished=utcnow(), duration_ms=duration)
                event("worker_completed", worker=name, duration_ms=duration)
                return result
        return observed
    return decorate


class RequestTelemetry:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        reference = uuid.uuid4().hex
        token = request_id.set(reference)
        started, completed, status, response_started, failure = time.perf_counter(), None, 499, False, None

        async def tracked_send(message):
            nonlocal response_started, status, completed
            if message["type"] == "http.response.start":
                response_started, status = True, message["status"]
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-request-id"]
                headers.append((b"x-request-id", reference.encode()))
                if status >= 500:
                    headers = [(key, value) for key, value in headers if key.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"private, no-store"))
                message["headers"] = headers
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = time.perf_counter()
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except asyncio.CancelledError:
            failure = "request_cancelled"
            raise
        except Exception:
            failure = "background_failed" if completed else "response_failed"
            if response_started:
                # Suppress the original exception/trace in ASGI server logs (it may contain PII).
                raise RuntimeError(f"Response failed; request_id={reference}") from None
            await JSONResponse({"detail": "We couldn't complete this request. Please try again.", "request_id": reference}, status_code=500)(scope, receive, tracked_send)
        finally:
            try:
                if scope["path"] not in ("/health", "/ready") or status >= 400 or failure:
                    route = getattr(scope.get("route"), "path", None) or "unmatched"
                    method = scope["method"] if scope["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} else "OTHER"
                    policy = scope.get("homexo.policy")
                    event("http_request", method=method, route=route, status=status,
                        duration_ms=max(0, round(((completed or time.perf_counter()) - started) * 1000)),
                        **({"policy": policy} if policy in POLICIES else {}), **({"error_code": failure} if failure else {}))
            finally:
                request_id.reset(token)
