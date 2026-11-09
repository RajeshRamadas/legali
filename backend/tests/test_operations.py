import asyncio
import json
import logging
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app import config, operations, telemetry
from app.db import SessionLocal, engine
from app.models import Document, Notification, WorkerPulse, utcnow
from conftest import authenticate_customer


@pytest.fixture
def events(caplog):
    caplog.set_level(logging.INFO, logger="homexo.operations")
    telemetry.log.addHandler(caplog.handler)
    yield lambda: [json.loads(record.getMessage()) for record in caplog.records if record.name == "homexo.operations"]
    telemetry.log.removeHandler(caplog.handler)


def set_revision(revision=None):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("DELETE FROM alembic_version"))
        for value in ([revision] if revision else operations.expected_revisions()):
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"), {"revision": value})


def test_liveness_and_readiness_have_separate_database_and_schema_checks(client, monkeypatch):
    set_revision("0021_api_abuse_protection")
    assert client.get("/health").status_code == 200
    failed = client.get("/ready")
    assert failed.status_code == 503 and failed.json() == {"status": "not_ready"}
    set_revision()
    assert client.get("/ready").json() == {"status": "ready"}
    def unavailable():
        raise OperationalError("secret SQL", {}, Exception("secret connection details"))
    monkeypatch.setattr(operations, "probe_engine", unavailable)
    response = client.get("/ready")
    assert response.status_code == 503 and "secret" not in response.text
    assert client.get("/health").status_code == 200


def test_operations_requires_current_admin_and_migrations(client, agent, admin_headers):
    assert client.get("/api/v1/admin/operations").status_code == 401
    assert client.get("/api/v1/admin/operations", headers=agent["headers"]).status_code == 403
    authenticate_customer(client)
    assert client.get("/api/v1/admin/operations").status_code == 401
    set_revision("old_revision")
    assert client.get("/api/v1/admin/operations", headers=admin_headers).status_code == 503
    set_revision()
    response = client.get("/api/v1/admin/operations", headers=admin_headers)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"


def test_snapshot_separates_due_scheduled_failed_and_unconfigured_delivery(client, admin_headers, raise_ticket, monkeypatch):
    set_revision()
    now = utcnow()
    monkeypatch.setattr(operations, "utcnow", lambda: now)
    monkeypatch.setattr(operations.notification_providers, "enabled", lambda channel: False)
    monkeypatch.setattr(operations.whatsapp, "enabled", lambda: False)
    number = raise_ticket()
    with SessionLocal() as db:
        # Ignore notifications created by the fixture; exercise each queue boundary explicitly.
        db.query(Notification).delete()
        db.add_all([
            Notification(channel="email", template_key="test", delivery_status="queued", send_after=now - timedelta(minutes=30), recipient="private@example.test", body="PRIVATE BODY"),
            Notification(channel="email", template_key="test", delivery_status="queued", send_after=now + timedelta(days=1)),
            Notification(channel="sms", template_key="test", delivery_status="failed", last_attempt_at=now, created_at=now - timedelta(days=10), recipient="9999999999", error_code="PRIVATE PROVIDER ERROR"),
            Notification(channel="sms", template_key="test", delivery_status="failed", created_at=now - timedelta(days=2)),
            Notification(channel="in_app", template_key="test", delivery_status="queued", created_at=now - timedelta(days=1)),
        ])
        from app.models import ServiceRequest
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        db.add(Document(service_request_id=ticket.id, original_filename="PRIVATE FILE.pdf", content_type="application/pdf", byte_size=1, storage_key="private/key", scan_status="pending", created_at=now - timedelta(hours=1)))
        db.commit()
    response = client.get("/api/v1/admin/operations", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    channels = {row["name"]: row for row in body["channels"]}
    assert channels["email"]["due"] == 1 and channels["email"]["delayed"] == 1 and channels["email"]["scheduled"] == 1
    assert channels["sms"]["failed_24h"] == 1 and channels["sms"]["due"] == 0
    assert body["documents"]["pending"] == body["documents"]["delayed"] == 1
    assert body["status"] == "attention"
    assert all(secret not in response.text for secret in ("private@example.test", "9999999999", "PRIVATE", "private/key", number))


def test_worker_observations_preserve_results_and_survive_failed_endpoint_transactions(events):
    @telemetry.observe_worker("notifications")
    def succeeds():
        return 42
    assert succeeds() == 42
    with SessionLocal() as db:
        pulse = db.get(WorkerPulse, "notifications")
        assert pulse.last_success_at and pulse.consecutive_failures == 0 and pulse.error_code is None
    @telemetry.observe_worker("notifications")
    def fails():
        raise ValueError("PRIVATE PROVIDER SECRET")
    with pytest.raises(ValueError):
        fails()
    with SessionLocal() as db:
        pulse = db.get(WorkerPulse, "notifications")
        assert pulse.last_success_at and pulse.last_failure_at and pulse.consecutive_failures == 1 and pulse.error_code == "task_failed"
    assert "PRIVATE PROVIDER SECRET" not in json.dumps(events())
    assert succeeds() == 42
    with SessionLocal() as db:
        pulse = db.get(WorkerPulse, "notifications")
        assert pulse.consecutive_failures == 0 and pulse.last_failure_at and pulse.error_code is None


def test_observation_storage_failure_does_not_block_work(monkeypatch, events):
    def unavailable():
        raise OperationalError("PRIVATE SQL", {}, Exception("PRIVATE DETAILS"))
    monkeypatch.setattr(telemetry, "SessionLocal", unavailable)
    called = []
    @telemetry.observe_worker("notifications")
    def work():
        called.append(True)
        return "done"
    assert work() == "done" and called == [True]
    assert sum(event["event"] == "worker_observation_unavailable" for event in events()) == 2
    assert "PRIVATE" not in json.dumps(events())


def test_old_completions_cannot_overwrite_new_worker_results():
    now = utcnow()
    telemetry.record_worker("notifications", now, finished=now, duration_ms=3)
    telemetry.record_worker("notifications", now - timedelta(minutes=1), finished=now - timedelta(seconds=10), duration_ms=5, error_code="task_failed")
    with SessionLocal() as db:
        pulse = db.get(WorkerPulse, "notifications")
        assert pulse.error_code is None and pulse.duration_ms == 3


@pytest.mark.parametrize("state,age,error", [("healthy", 10, None), ("failed", 10, "task_failed"), ("stale", 1000, None)])
def test_worker_health_tracks_success_failure_and_staleness(state, age, error):
    now = utcnow()
    row = WorkerPulse(name="notifications", started_at=now - timedelta(seconds=age + 1), finished_at=now - timedelta(seconds=age), error_code=error, consecutive_failures=1 if error else 0)
    assert operations.worker_view(row, "notifications", False, 60, now)["state"] == state


def test_external_worker_is_observed_when_in_process_worker_is_disabled(client, admin_headers):
    set_revision()
    now = utcnow()
    assert not config.NOTIFY_WORKER_ENABLED
    telemetry.record_worker("notifications", now, finished=now, duration_ms=1)
    body = client.get("/api/v1/admin/operations", headers=admin_headers).json()
    assert body["workers"][0]["state"] == "healthy" and body["workers"][0]["enabled_in_api"] is False
    assert body["workers"][1]["state"] == "disabled"
    assert body["status"] == "healthy"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Atomic multi-worker writes require PostgreSQL")
def test_concurrent_worker_failures_are_counted_atomically():
    now = utcnow()
    def fail(_):
        telemetry.record_worker("notifications", now, finished=now, duration_ms=1, error_code="task_failed")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fail, range(16)))
    with SessionLocal() as db:
        assert db.get(WorkerPulse, "notifications").consecutive_failures == 16


def test_request_events_use_templates_and_never_include_sensitive_input(client, events):
    response = client.get("/api/v1/files/PRIVATE-DOWNLOAD-TOKEN?contact=PRIVATE-PHONE", headers={"Authorization": "Bearer PRIVATE-AUTH", "X-Request-ID": "PRIVATE-ID"})
    assert re.fullmatch(r"[a-f0-9]{32}", response.headers["x-request-id"])
    records = [item for item in events() if item["event"] == "http_request"]
    assert records[-1]["route"] == "/api/v1/files/{token}"
    assert records[-1]["request_id"] == response.headers["x-request-id"]
    assert records[-1]["duration_ms"] >= 0
    client.get("/PRIVATE-UNMATCHED-PATH?email=PRIVATE-EMAIL")
    assert "PRIVATE" not in json.dumps(events())
    assert logging.getLogger("uvicorn.access").disabled


def test_throttled_requests_are_traced_without_reading_or_logging_body(client, monkeypatch, events):
    monkeypatch.setattr(config, "API_SUBMISSIONS_PER_HOUR", 1)
    client.post("/api/v1/tickets", json={})
    blocked = client.post("/api/v1/tickets", content=b"PRIVATE BODY")
    assert blocked.status_code == 429 and blocked.headers.get("x-request-id")
    assert events()[-1]["policy"] == "submissions" and events()[-1]["status"] == 429
    assert "PRIVATE BODY" not in json.dumps(events())


def test_unexpected_errors_are_safe_correlated_and_readable_through_cors(client, monkeypatch, events):
    def explode(*args):
        raise RuntimeError("PRIVATE SQL AND CUSTOMER BODY")
    monkeypatch.setattr(operations, "schema_matches", explode)
    response = client.get("/ready", headers={"Origin": config.CORS_ORIGINS[0]})
    assert response.status_code == 500 and "PRIVATE" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"] == events()[-1]["request_id"]
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
    assert response.headers["cache-control"] == "private, no-store"
    assert "PRIVATE" not in json.dumps(events())


@pytest.mark.parametrize("complete,code", [(False, "response_failed"), (True, "background_failed")])
def test_streaming_or_background_failures_never_expose_exception_text(events, complete, code):
    async def run():
        sent = []
        async def failing(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": not complete})
            raise ValueError("PRIVATE STREAM ERROR")
        async def receive():
            return {"type": "http.disconnect"}
        async def send(message):
            sent.append(message)
        with pytest.raises(RuntimeError) as error:
            await telemetry.RequestTelemetry(failing)({"type": "http", "method": "GET", "path": "/stream"}, receive, send)
        assert "PRIVATE" not in "".join(traceback.format_exception(error.value))
        assert telemetry.request_id.get() is None
    asyncio.run(run())
    assert events()[-1]["error_code"] == code and events()[-1]["status"] == 200


def test_successful_probe_requests_do_not_flood_access_logs(client, events):
    set_revision()
    assert client.get("/health").status_code == client.get("/ready").status_code == 200
    assert not [item for item in events() if item["event"] == "http_request"]
