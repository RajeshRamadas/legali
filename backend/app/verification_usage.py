"""Content-free metadata for provider attempts in detached background jobs only."""
import json
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, time as midnight, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select

from . import config
from .db import SessionLocal, get_db
from .models import User, VerificationUsage as Usage, utcnow
from .security import require_admin
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/verification-usage")
_scope = ContextVar("verification_usage_scope", default=None)
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
VERSION = re.compile(r"[A-Za-z0-9._-]{1,40}\Z")
MAX_TOKENS = 1_000_000_000


class UsageRecordingError(Exception):
    """Never expose database/provider details or silently repeat a provider call."""


@contextmanager
def scope(case_id, job_id):
    token = _scope.set((uuid.UUID(str(case_id)), uuid.UUID(str(job_id))))
    try:
        yield
    finally:
        _scope.reset(token)


def rates():
    """Validate operator-reviewed prices; malformed configuration disables estimates."""
    raw = config.VERIFICATION_TOKEN_RATES
    if not raw.strip(): return {"status": "not_configured", "version": None, "models": {}}
    try:
        if len(raw) > 20000: raise ValueError()
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError()
                result[key] = value
            return result
        value = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {"version", "models"}: raise ValueError()
        if not isinstance(value["version"], str) or not VERSION.fullmatch(value["version"]): raise ValueError()
        if not isinstance(value["models"], dict) or not 1 <= len(value["models"]) <= 40: raise ValueError()
        parsed = {}
        for key, item in value["models"].items():
            provider, model = key.split("/", 1)
            if provider not in ("anthropic", "openai") or not MODEL.fullmatch(model): raise ValueError()
            if not isinstance(item, dict) or set(item) != {"input_per_million", "output_per_million"}: raise ValueError()
            prices = []
            for price in (item["input_per_million"], item["output_per_million"]):
                if isinstance(price, bool) or not isinstance(price, (str, int, Decimal)): raise ValueError()
                if len(str(price)) > 40: raise ValueError()
                number = Decimal(price)
                if not number.is_finite() or not 0 <= number <= 1_000_000 or number.as_tuple().exponent < -6: raise ValueError()
                prices.append(number)
            parsed[key] = tuple(prices)
        return {"status": "configured", "version": value["version"], "models": parsed}
    except (ValueError, TypeError, InvalidOperation, OverflowError, RecursionError):
        return {"status": "invalid", "version": None, "models": {}}


def tokens(provider, value):
    """Missing/malformed counters are unknown; explicit zero is valid usage."""
    def count(number):
        if type(number) is not int or not 0 <= number <= MAX_TOKENS: raise ValueError()
        return number
    try:
        if not isinstance(value, dict): raise ValueError()
        if provider == "anthropic":
            cached = count(value.get("cache_creation_input_tokens", 0)) + count(value.get("cache_read_input_tokens", 0))
            incoming = count(count(value["input_tokens"]) + cached)
            outgoing = count(value["output_tokens"])
        else:
            incoming, outgoing = count(value["prompt_tokens"]), count(value["completion_tokens"])
            details = value.get("prompt_tokens_details", {})
            if not isinstance(details, dict): raise ValueError()
            cached = count(details.get("cached_tokens", 0))
        if cached > incoming: raise ValueError()
        return incoming, outgoing, cached
    except (KeyError, ValueError, TypeError):
        return None


class Attempt:
    def __init__(self, provider, model, step):
        self.provider, self.model, self.step = provider, model, step
        self.key = None
        self.reported = None

    def capture(self, body):
        if self.key is not None:
            self.reported = tokens(self.provider, body.get("usage") if isinstance(body, dict) else None)

    def __enter__(self):
        context = _scope.get()
        if context is None: return self  # Legacy synchronous analysis/upload checks are outside this feature.
        if self.provider not in ("anthropic", "openai") or self.step not in ("extract", "compare") or not MODEL.fullmatch(self.model):
            raise UsageRecordingError("Provider attempt metadata is unavailable.")
        pricing = rates()
        self.price = pricing["models"].get(f"{self.provider}/{self.model}")
        self.reason = {"not_configured": "rates_not_configured", "invalid": "invalid_rate_configuration"}.get(pricing["status"], "model_not_priced")
        self.key = uuid.uuid4()
        try:
            with SessionLocal() as db:
                db.add(Usage(id=self.key, service_request_id=context[0], job_id=context[1], provider=self.provider,
                    model=self.model, step=self.step, input_rate=self.price[0] if self.price else None,
                    output_rate=self.price[1] if self.price else None, rate_version=pricing["version"]))
                db.commit()
        except Exception:
            raise UsageRecordingError("Provider attempt could not be recorded; no request was sent.") from None
        self.clock = time.monotonic()
        return self

    def __exit__(self, kind, error, traceback):
        if self.key is None: return False
        # Process termination leaves the durable 'started' record with unknown billing.
        if kind and not issubclass(kind, Exception): return False
        category = None
        if error is not None:
            category = "provider_http_error" if isinstance(error, httpx.HTTPStatusError) else "transport_error" if isinstance(error, httpx.RequestError) else "invalid_response" if isinstance(error, (ValueError, KeyError, TypeError, IndexError)) else "operation_failed"
        incoming, outgoing, cached = self.reported or (None, None, None)
        estimate, reason = None, self.reason
        if self.price:
            if self.reported is None: reason = "usage_unavailable"
            elif cached: reason = "cache_usage_unpriced"
            else:
                estimate = ((incoming*self.price[0] + outgoing*self.price[1])/Decimal(1_000_000)).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
                reason = "priced"
        try:
            with SessionLocal() as db:
                row = db.get(Usage, self.key)
                if row is None: raise UsageRecordingError()
                row.status = "failed" if error is not None else "succeeded"
                row.finished_at = utcnow()
                row.duration_ms = min(2_147_483_647, max(0, int((time.monotonic()-self.clock)*1000)))
                row.input_tokens, row.output_tokens, row.cache_tokens = incoming, outgoing, cached
                row.usage_complete = self.reported is not None
                row.estimated_usd, row.estimate_reason, row.error_category = estimate, reason, category
                db.commit()
        except Exception:
            raise UsageRecordingError("Provider outcome could not be recorded; review the unfinished attempt before retrying.") from None
        return False


def aggregate_columns():
    return (func.count(Usage.id).label("attempts"),
        func.sum(case((Usage.status == "succeeded", 1), else_=0)).label("succeeded"),
        func.sum(case((Usage.status == "failed", 1), else_=0)).label("failed"),
        func.sum(case((Usage.status == "started", 1), else_=0)).label("unfinished"),
        func.sum(case((Usage.usage_complete, 1), else_=0)).label("usage_reported"),
        func.sum(Usage.input_tokens).label("input_tokens"), func.sum(Usage.output_tokens).label("output_tokens"),
        func.count(Usage.estimated_usd).label("priced"), func.sum(Usage.estimated_usd).label("known_estimated_usd"),
        func.avg(Usage.duration_ms).label("average_duration_ms"))


def summary(row=None):
    values = dict(row._mapping) if row is not None else {}
    result = {key: int(values.get(key) or 0) for key in ("attempts", "succeeded", "failed", "unfinished", "usage_reported")}
    result.update({key: int(values[key]) if values.get(key) is not None else None for key in ("input_tokens", "output_tokens", "average_duration_ms")})
    result["known_estimated_usd"] = format(values["known_estimated_usd"], ".12f") if values.get("known_estimated_usd") is not None else None
    result["unpriced_attempts"] = result["attempts"] - int(values.get("priced") or 0)
    return result


def summaries(db, job_ids):
    if not job_ids: return {}
    rows = db.execute(select(Usage.job_id, *aggregate_columns()).where(Usage.job_id.in_(job_ids)).group_by(Usage.job_id))
    return {row.job_id: summary(row) for row in rows}


def view(row):
    fields = ("provider", "model", "step", "status", "duration_ms", "input_tokens", "output_tokens", "cache_tokens", "usage_complete", "estimate_reason", "rate_version", "error_category")
    value = {key: getattr(row, key) for key in fields}
    value.update({key: str(getattr(row, key)) for key in ("id", "job_id", "service_request_id")})
    value.update({key: aware(getattr(row, key)).isoformat() if getattr(row, key) else None for key in ("started_at", "finished_at")})
    value["estimated_usd"] = format(row.estimated_usd, ".12f") if row.estimated_usd is not None else None
    return value


@router.get("")
def history(provider: Literal["all", "anthropic", "openai"] = "all", step: Literal["all", "extract", "compare"] = "all",
    status: Literal["all", "started", "succeeded", "failed"] = "all", days: int = Query(30, ge=1, le=90),
    job_id: uuid.UUID | None = None, page: int = Query(1, ge=1, le=10000), page_size: int = Query(25, ge=1, le=100),
    _: User = Depends(require_admin), db=Depends(get_db)):
    now = utcnow()
    india = ZoneInfo("Asia/Kolkata")
    start = datetime.combine(now.astimezone(india).date()-timedelta(days=days-1), midnight.min, india).astimezone(timezone.utc)
    filters = [Usage.started_at >= start, Usage.started_at <= now]
    for field, value in ((Usage.provider, provider), (Usage.step, step), (Usage.status, status)):
        if value != "all": filters.append(field == value)
    if job_id: filters.append(Usage.job_id == job_id)
    totals = summary(db.execute(select(*aggregate_columns()).where(*filters)).one())
    rows = db.scalars(select(Usage).where(*filters).order_by(Usage.started_at.desc(), Usage.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    pricing = rates()
    return {"items": [view(row) for row in rows], "summary": totals, "page": page, "page_size": page_size,
        "checked_at": now.isoformat(), "from_at": start.isoformat(), "scope": "background_verification",
        "pricing": {"status": pricing["status"], "version": pricing["version"], "models": len(pricing["models"])}}
