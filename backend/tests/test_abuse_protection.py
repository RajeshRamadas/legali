import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app import abuse_protection as abuse, config, documents
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, Notification, ServiceRequest, utcnow
from conftest import authenticate_customer


def test_invalid_submissions_share_booking_and_intake_budget(client, monkeypatch):
    monkeypatch.setattr(config, "API_SUBMISSIONS_PER_HOUR", 2)
    assert client.post("/api/v1/tickets", json={}).status_code == 422
    # Bad input and anonymous requests still consume a budget before validation/auth.
    assert client.post("/api/v1/lawyers/missing/bookings", json={}).status_code != 429
    blocked = client.post("/api/v1/intake/drafts/missing/submit", content="not json")
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 3600
    assert blocked.json()["retry_after"] == int(blocked.headers["retry-after"])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 0


def test_lookups_are_limited_and_forwarded_headers_cannot_reset_budget(client, monkeypatch):
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.post("/api/v1/tickets/lookup", json={}).status_code != 429
    response = client.post("/api/v1/bookings/lookup", json={}, headers={
        "X-Forwarded-For": "203.0.113.77", "X-Real-IP": "198.51.100.7", "Origin": config.CORS_ORIGINS[0],
    })
    assert response.status_code == 429
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["access-control-allow-origin"] == config.CORS_ORIGINS[0]
    assert "retry-after" in response.headers["access-control-expose-headers"].lower()
    with SessionLocal() as db:
        bucket = db.scalar(select(ApiRateBucket))
        assert bucket.key == abuse._key("lookups", "client:testclient")
        assert bucket.attempts == 2 and "testclient" not in bucket.key


def test_signed_customer_budget_follows_account_across_clients(client, monkeypatch):
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    headers = authenticate_customer(client)
    with TestClient(app, client=("198.51.100.1", 1)) as first, TestClient(app, client=("198.51.100.2", 2)) as second:
        assert first.get("/api/v1/account", headers=headers).status_code == 200
        assert second.get("/api/v1/account", headers=headers).status_code == 429
    # Throttling does not revoke the customer session.
    with SessionLocal() as db:
        db.query(ApiRateBucket).delete()
        db.commit()
    assert client.get("/api/v1/account").status_code == 200


@pytest.mark.parametrize("audience", ["homexo-customer", "homexo-staff"])
def test_session_identity_requires_verified_signature_and_session_claims(audience):
    now = utcnow()
    claims = {"sub": str(uuid.uuid4()), "aud": audience, "ver": 1, "iat": now, "exp": now + timedelta(minutes=5)}
    signed = lambda payload, secret=config.JWT_SECRET: "Bearer " + jwt.encode(payload, secret, algorithm="HS256")
    assert abuse.session_identity(signed(claims)) == f"session:{audience}:{claims['sub']}"
    assert abuse.session_identity(signed(claims, "attacker-key-that-is-not-the-server-key")) is None
    for overrides in ({"aud": "homexo-staff-setup"}, {"exp": now - timedelta(seconds=1)}, {"sub": "bad"}, {"aud": [audience]}):
        assert abuse.session_identity(signed({**claims, **overrides})) is None
    for missing in ("exp", "aud", "ver", "sub", "iat"):
        assert abuse.session_identity(signed({k: v for k, v in claims.items() if k != missing})) is None
    assert abuse.session_identity("Bearer malformed") is None


def test_forged_token_cannot_charge_another_account(client, monkeypatch):
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    headers = authenticate_customer(client)
    claims = jwt.decode(headers["Authorization"].split()[1], config.JWT_SECRET, algorithms=["HS256"], audience="homexo-customer")
    forged = jwt.encode(claims, "attacker-key-that-is-not-the-server-key", algorithm="HS256")
    with TestClient(app, client=("198.51.100.9", 9)) as attacker:
        assert attacker.get("/api/v1/account", headers={"Authorization": "Bearer " + forged}).status_code == 401
    assert client.get("/api/v1/account").status_code == 200


def test_atomic_counter_resets_saturates_and_does_not_move_backwards():
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
    policy = abuse.Policy("test", 2)
    assert abuse.consume(policy, ["client:one"], now) is None
    assert abuse.consume(policy, ["client:one"], now) is None
    assert abuse.consume(policy, ["client:one"], now) == 50
    assert abuse.consume(policy, ["client:one"], now) == 50
    with SessionLocal() as db:
        assert db.scalar(select(ApiRateBucket.attempts)) == 3
    assert abuse.consume(policy, ["client:one"], now + timedelta(minutes=1)) is None
    assert abuse.consume(policy, ["client:one"], now) is None
    assert abuse.consume(policy, ["client:one"], now) == 110
    with SessionLocal() as db:
        assert db.scalar(select(ApiRateBucket.window_start)).replace(tzinfo=timezone.utc).minute == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent independent workers require PostgreSQL")
@pytest.mark.parametrize("shared", ["client:shared", "session:homexo-customer:shared"])
def test_concurrent_workers_cannot_overspend_either_identity_budget(shared):
    policy = abuse.Policy("concurrent", 4)
    now = utcnow()
    def attempt(i):
        return abuse.consume(policy, [shared, f"other:{i}"], now)
    with ThreadPoolExecutor(max_workers=12) as workers:
        results = list(workers.map(attempt, range(24)))
    assert results.count(None) == 4
    assert all(1 <= result <= 60 for result in results if result is not None)
    with SessionLocal() as db:
        assert db.get(ApiRateBucket, abuse._key(policy.group, shared)).attempts == 5


def test_budget_storage_failure_fails_closed_without_running_handler(client, monkeypatch):
    def unavailable(*args):
        raise OperationalError("not logged", {}, Exception("not logged"))
    monkeypatch.setattr(abuse, "consume", unavailable)
    response = client.post("/api/v1/tickets", json={})
    assert response.status_code == 503 and response.headers["retry-after"] == "10"
    assert "not logged" not in response.text
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/health", "/api/v1/services", "/api/v1/intake/notice"])
def test_public_reads_do_not_consume_budget(client, monkeypatch, path):
    def unexpected(*args):
        raise AssertionError("Public read consumed a budget")
    monkeypatch.setattr(abuse, "consume", unexpected)
    assert client.get(path).status_code == 200
    assert client.options("/api/v1/tickets", headers={"Origin": config.CORS_ORIGINS[0], "Access-Control-Request-Method": "POST"}).status_code == 200


def test_payment_webhook_keeps_signature_validation_and_is_not_throttled(client, monkeypatch):
    monkeypatch.setattr(config, "RAZORPAY_WEBHOOK_SECRET", "test-webhook-secret")
    def unexpected(*args):
        raise AssertionError("Webhook must use provider signature validation")
    monkeypatch.setattr(abuse, "consume", unexpected)
    response = client.post("/api/v1/payments/razorpay/webhook", content=b"{}", headers={"X-Razorpay-Signature": "wrong"})
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/api/v1/tickets/documents", "/api/v1/admin/tickets/HX-1/documents", "/api/v1/admin/tickets/HX-1/report/signed"])
def test_upload_limit_runs_before_multipart_parser(client, monkeypatch, path):
    monkeypatch.setattr(config, "API_UPLOADS_PER_MINUTE", 1)
    abuse.consume(abuse.policy_for("POST", path), ["client:testclient"])
    def unexpected(*args, **kwargs):
        raise AssertionError("Throttled upload reached processing")
    monkeypatch.setattr(documents, "_read_upload", unexpected)
    response = client.post(path, content=b"invalid multipart", headers={"Content-Type": "multipart/form-data; boundary=none", "Content-Length": str(10**9)})
    assert response.status_code == 429


@pytest.mark.parametrize("path", ["/api/v1/tickets", "/api/v1/tickets/documents"])
@pytest.mark.parametrize("declared_length", [True, False])
def test_json_and_multipart_streams_are_bounded(client, monkeypatch, path, declared_length):
    monkeypatch.setattr(config, "UPLOAD_MAX_MB", 0)  # 1 MiB multipart allowance in this test.
    body = b"x" * (abuse.JSON_MAX_BYTES + 1)
    if path.endswith("documents"):
        body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.pdf"\r\nContent-Type: application/pdf\r\n\r\n' + body + b'\r\n--test--\r\n'
    headers = {"Content-Type": "multipart/form-data; boundary=test" if path.endswith("documents") else "application/json"}
    content = body if declared_length else iter([body[:200], body[200:]])
    response = client.post(path, content=content, headers=headers)
    assert response.status_code == 413, response.text
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("headers", [[(b"content-length", b"-1")], [(b"content-length", b"invalid")], [(b"content-length", b"0"), (b"content-length", b"0")], [(b"authorization", b"Bearer a"), (b"authorization", b"Bearer b")]])
def test_invalid_headers_are_rejected_without_reading_body(headers):
    async def run():
        sent = []
        async def unexpected(*args):
            raise AssertionError("Invalid headers reached handler or body stream")
        async def send(message):
            sent.append(message)
        scope = {"type": "http", "method": "POST", "path": "/api/v1/tickets", "headers": headers, "client": ("127.0.0.1", 1)}
        await abuse.AbuseProtection(unexpected)(scope, unexpected, send)
        assert sent[0]["status"] == 400
    asyncio.run(run())


def test_form_trap_creates_no_request_or_notification(client):
    response = client.post("/api/v1/tickets", json={"customer_name": "Example Customer", "contact": "9876543210", "property_type": "apartment", "service_slug": "title-verification", "location": "Bengaluru", "website_url": "https://spam.invalid"})
    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_cleanup_removes_only_expired_budgets():
    now = utcnow()
    with SessionLocal() as db:
        db.add_all([ApiRateBucket(key="old", attempts=2, window_start=now - timedelta(days=2)), ApiRateBucket(key="active", attempts=1, window_start=now)])
        db.commit()
    abuse.cleanup()
    with SessionLocal() as db:
        assert list(db.scalars(select(ApiRateBucket.key))) == ["active"]
