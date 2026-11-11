import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, notify, operations, support_alerts
from app.db import SessionLocal, engine
from app.main import app
from app.models import AuditLog, Notification, SupportDeadlineAlert, SupportRequest, User, utcnow
from app.tickets import aware
from conftest import authenticate_customer
from test_support import ADMIN, BASE, create, reply, review
from test_support_ownership import assign, another_admin

ALERTS = ADMIN+"/deadline-alerts"


def overdue(client, hours=1):
    authenticate_customer(client)
    item = create(client)
    due = utcnow()-timedelta(hours=hours)
    with SessionLocal() as db:
        db.get(SupportRequest, uuid.UUID(item["id"])).reply_due_at = due
        db.commit()
    return item, due


def reconcile(now=None):
    with SessionLocal() as db:
        return support_alerts.reconcile(db, now)


def listing(client, headers, **params):
    response = client.get(ALERTS, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ack(client, headers, alert, **changes):
    return client.post(f"{ALERTS}/{alert['id']}/acknowledge", headers=headers, json={"revision": alert["revision"], **changes})


def test_monitoring_is_deduplicated_private_and_does_not_mutate_support_work(client, admin_headers):
    item, due = overdue(client)
    # Future/equal targets, resolved work and requests waiting without a target are excluded.
    with SessionLocal() as db:
        account = db.get(SupportRequest, uuid.UUID(item["id"])).account_id
        for target, status in ((utcnow()+timedelta(days=1), "open"), (None, "waiting_for_customer"), (due, "resolved")):
            db.add(SupportRequest(account_id=account, submission_key=uuid.uuid4(), kind="other", subject="Synthetic second request", details="Private details should never reach alerts", status=status, reply_due_at=target))
        db.commit()
    assert reconcile(due) == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SupportDeadlineAlert)) == 0
    before = client.get(f"{BASE}/{item['id']}").json()
    assert reconcile() == 1 and reconcile() == 0
    alerts = listing(client, admin_headers)
    assert alerts["total"] == alerts["unacknowledged"] == 1 and alerts["escalated"] == 0
    assert "subject" not in alerts["items"][0] and "details" not in alerts["items"][0]
    after = client.get(f"{BASE}/{item['id']}").json()
    assert after == before and "alert" not in str(after)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action.like("support.deadline_%"))))
        assert len(audits) == 1 and audits[0].action == "support.deadline_alerted"
        assert "subject" not in str(audits[0].metadata_) and "body" not in str(audits[0].metadata_)


def test_alert_authorization_strict_commands_and_idempotent_acknowledgement(client, admin_headers, agent, monkeypatch):
    item, _ = overdue(client); reconcile()
    alert = listing(client, admin_headers)["items"][0]
    assert client.get(ALERTS).status_code == 401
    assert client.get(ALERTS, headers=agent["headers"]).status_code == 403
    assert ack(client, dict(client.headers), alert).status_code == 401
    assert ack(client, agent["headers"], alert).status_code == 403
    assert client.get(ALERTS, headers=admin_headers).headers["cache-control"] == "private, no-store"
    path = f"{ALERTS}/{alert['id']}/acknowledge"
    for body in ({}, {"revision": True}, {"revision": "1"}, {"revision": 0}, {"revision": 1, "extra": "ignored?"}):
        assert client.post(path, headers=admin_headers, json=body).status_code == 422
    assert ack(client, admin_headers, {**alert, "id": str(uuid.uuid4())}).status_code == 404
    assert listing(client, admin_headers, page=2, page_size=1)["items"] == []
    for _ in range(2):
        result = ack(client, admin_headers, alert)
        assert result.status_code == 200 and result.json()["acknowledged_by"]["name"] == "Meera Admin"
    assert listing(client, admin_headers)["total"] == listing(client, admin_headers)["unacknowledged"] == 0
    assert listing(client, admin_headers, include_acknowledged=True)["items"][0]["id"] == alert["id"]
    assert client.get(f"{BASE}/{item['id']}").json()["revision"] == item["revision"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "support.deadline_acknowledged")) == 1
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(ALERTS, headers=admin_headers).status_code == 429


def test_escalation_is_once_per_target_resets_ack_and_rejects_stale_phase(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config, "SUPPORT_ESCALATION_HOURS", 24)
    _, due = overdue(client)
    reconcile(due+timedelta(seconds=1))
    initial = listing(client, admin_headers)["items"][0]
    assert ack(client, admin_headers, initial).status_code == 200
    reconcile(due+timedelta(hours=24))
    escalated = listing(client, admin_headers)["items"][0]
    assert escalated["id"] == initial["id"] and escalated["revision"] > initial["revision"] and escalated["escalated_at"]
    assert escalated["acknowledged_at"] is None
    assert ack(client, admin_headers, initial).status_code == 409
    assert ack(client, admin_headers, escalated).status_code == 200
    reconcile(due+timedelta(hours=48))
    assert listing(client, admin_headers)["unacknowledged"] == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "support.deadline_escalated")) == 1


def test_visible_reply_hides_alert_immediately_and_later_followup_starts_new_cycle(client, admin_headers):
    item, due = overdue(client); reconcile()
    initial = listing(client, admin_headers)["items"][0]
    # Private work and customer follow-ups leave the existing target untouched.
    item = review(client, admin_headers, item, internal_note="Private investigation without a response").json()
    item = reply(client, item).json()
    assert aware(datetime.fromisoformat(item["reply_due_at"])) == aware(due)
    reconcile(); assert listing(client, admin_headers)["items"][0]["id"] == initial["id"]
    item = review(client, admin_headers, item, status="waiting_for_customer", customer_response="Please supply a legible replacement document.").json()
    assert listing(client, admin_headers)["items"] == []
    assert ack(client, admin_headers, initial).status_code == 409
    reconcile()
    item = reply(client, item).json()
    later = datetime.fromisoformat(item["reply_due_at"])
    reconcile(later+timedelta(seconds=1))
    # The new target is still in the future for real-time API reads.
    assert listing(client, admin_headers)["items"] == []
    with SessionLocal() as db:
        rows = list(db.scalars(select(SupportDeadlineAlert).order_by(SupportDeadlineAlert.target_at)))
        assert len(rows) == 2 and rows[0].resolved_at and rows[1].resolved_at is None
        assert rows[0].id != rows[1].id
        assert db.get(SupportRequest, uuid.UUID(item["id"])).customer_update_revision == 1


def test_owner_changes_and_read_receipts_preserve_acknowledgement_and_drafts(client, admin_headers):
    item, due = overdue(client); reconcile()
    alert = listing(client, admin_headers)["items"][0]
    ack(client, admin_headers, alert)
    owner = another_admin()
    assigned = assign(client, admin_headers, item, owner).json()
    client.post(f"{BASE}/{item['id']}/read", json={"through_revision": 0})
    reconcile()
    current = listing(client, admin_headers, include_acknowledged=True)["items"][0]
    assert current["owner"]["id"] == owner and current["acknowledged_at"]
    assert current["revision"] == alert["revision"] and current["id"] == alert["id"]
    with SessionLocal() as db:
        db.get(User, uuid.UUID(owner)).account_status = "suspended"; db.commit()
    assert listing(client, admin_headers, include_acknowledged=True)["items"][0]["owner"]["active"] is False
    assert review(client, admin_headers, assigned, customer_response="A current saved reply still uses the same editing revision.").status_code == 200


def test_restored_target_reuses_incident_but_invalidates_old_acknowledgement(client, admin_headers):
    item, due = overdue(client); reconcile()
    initial = listing(client, admin_headers)["items"][0]
    ack(client, admin_headers, initial)
    with SessionLocal() as db:
        db.get(SupportRequest, uuid.UUID(item["id"])).reply_due_at = None; db.commit()
    reconcile()
    with SessionLocal() as db:
        db.get(SupportRequest, uuid.UUID(item["id"])).reply_due_at = due; db.commit()
    reconcile()
    revived = listing(client, admin_headers)["items"][0]
    assert revived["id"] == initial["id"] and revived["revision"] > initial["revision"] and revived["acknowledged_at"] is None
    assert ack(client, admin_headers, initial).status_code == 409


def test_queue_is_paged_escalated_first_and_operations_keeps_overdue_visible(client, admin_headers, monkeypatch):
    item, due = overdue(client)
    with SessionLocal() as db:
        account = db.get(SupportRequest, uuid.UUID(item["id"])).account_id
        for number in range(27):
            db.add(SupportRequest(account_id=account, submission_key=uuid.uuid4(), kind="other", subject=f"Synthetic {number}", details="Private body", reply_due_at=due-timedelta(days=2) if number == 0 else due))
        db.commit()
    reconcile()
    result = listing(client, admin_headers, page_size=25)
    assert result["total"] == result["unacknowledged"] == 28 and len(result["items"]) == 25
    assert result["escalated"] == 1 and result["items"][0]["escalated_at"]
    assert len(listing(client, admin_headers, page=2, page_size=25)["items"]) == 3
    monkeypatch.setattr(operations, "schema_matches", lambda _: True)
    snapshot = client.get("/api/v1/admin/operations", headers=admin_headers).json()
    assert snapshot["support"] == {"overdue_requests": 28, "unacknowledged": 28, "escalated": 1}
    for alert in listing(client, admin_headers, page_size=100)["items"]:
        assert ack(client, admin_headers, alert).status_code == 200
    assert client.get("/api/v1/admin/operations", headers=admin_headers).json()["support"]["overdue_requests"] == 28


def test_worker_integration_records_alerts_without_provider_notifications(client, monkeypatch):
    overdue(client)
    monkeypatch.setattr(notify.payments, "release_unpaid", lambda _: None)
    monkeypatch.setattr(notify, "queue_daily_agendas", lambda _: None)
    monkeypatch.setattr(notify.sla_alerts, "reconcile", lambda _: None)
    monkeypatch.setattr(notify, "deliver_due", lambda _: 0)
    notify.run_once()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SupportDeadlineAlert)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Independent support-monitor row locks")
def test_parallel_workers_create_one_incident_and_one_audit(client):
    overdue(client); barrier = Barrier(2)
    def run():
        barrier.wait(timeout=5)
        return reconcile()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sum(f.result(timeout=15) for f in futures) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SupportDeadlineAlert)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "support.deadline_alerted")) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Acknowledgement/escalation row-lock ordering")
def test_escalation_cannot_be_silenced_by_an_old_concurrent_ack(client, admin_headers):
    _, due = overdue(client); reconcile()
    initial = listing(client, admin_headers)["items"][0]; barrier = Barrier(2)
    def escalate():
        barrier.wait(timeout=5); reconcile(due+timedelta(hours=config.SUPPORT_ESCALATION_HOURS+1))
    def acknowledge():
        with TestClient(app) as peer:
            barrier.wait(timeout=5); return ack(peer, admin_headers, initial).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(escalate), pool.submit(acknowledge)
        first.result(timeout=15); assert second.result(timeout=15) in (200,409)
    result = listing(client, admin_headers)
    assert result["unacknowledged"] == result["escalated"] == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent reply and monitor lock ordering")
def test_visible_reply_wins_over_concurrent_monitor_without_stale_alerts(client, admin_headers):
    item, _ = overdue(client); barrier = Barrier(2)
    def monitor():
        barrier.wait(timeout=5); reconcile()
    def respond():
        with TestClient(app) as peer:
            barrier.wait(timeout=5)
            return review(peer, admin_headers, item, customer_response="A current response clears the missed team-response target.").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(monitor), pool.submit(respond)
        first.result(timeout=15); assert second.result(timeout=15) == 200
    assert listing(client, admin_headers)["items"] == []
    reconcile()
    with SessionLocal() as db:
        assert not list(db.scalars(select(SupportDeadlineAlert).where(SupportDeadlineAlert.resolved_at.is_(None))))
