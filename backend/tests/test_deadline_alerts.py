import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import admin, case_management, config, notification_providers as providers, notify, sla_alerts, tickets
from app.db import SessionLocal
from app.models import AuditLog, CaseDeadlineAlert, Notification, ServiceRequest, User, utcnow

ALERTS = "/api/v1/admin/case-alerts"


def clock(monkeypatch, now):
    for module in (admin, case_management, sla_alerts, tickets):
        monkeypatch.setattr(module, "utcnow", lambda: now)


def edit(number, **values):
    with SessionLocal() as db:
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        for key, value in values.items(): setattr(ticket, key, value)
        db.commit()


def scan(now):
    with SessionLocal() as db: return sla_alerts.reconcile(db, now)


def rows(model, **filters):
    with SessionLocal() as db: return list(db.scalars(select(model).filter_by(**filters)))


def patch(client, headers, number, **values):
    return client.patch(f"/api/v1/admin/tickets/{number}", headers=headers, json=values)


def late(raise_ticket, now, *, first=False):
    number = raise_ticket(email=None)
    edit(number, due_at=now + timedelta(days=1) if first else now - timedelta(hours=1),
         first_response_due_at=now - timedelta(hours=1) if first else now + timedelta(hours=4), first_response_at=None)
    return number


def test_hold_requires_reason_freezes_targets_and_resumes_once(client, admin_headers, raise_ticket, monkeypatch):
    now = utcnow(); clock(monkeypatch, now)
    number = raise_ticket(email=None)
    assert patch(client, admin_headers, number, status="on_hold").status_code == 422
    held = patch(client, admin_headers, number, status="on_hold", note="Waiting for access to the property.").json()
    d = held["case"]["deadlines"]; original = tickets.aware(datetime.fromisoformat(d["due_at"]))
    assert d["paused"] and not d["overdue"] and d["paused_at"]
    assert patch(client, admin_headers, number, due_at=(now + timedelta(days=5)).isoformat(), due_reason="New estimate").status_code == 409
    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).json()
    assert public["progress"]["deadline_paused"] and public["progress"]["due_at"] is None
    clock(monkeypatch, now + timedelta(hours=5))
    resumed = patch(client, admin_headers, number, status="in_progress").json()["case"]["deadlines"]
    assert datetime.fromisoformat(resumed["due_at"]) == original + timedelta(hours=5)
    assert resumed["paused_seconds"] == 18000 and resumed["paused_at"] is None and not resumed["paused"]
    repeated = patch(client, admin_headers, number, status="in_progress").json()["case"]["deadlines"]
    assert repeated == resumed


def test_lateness_before_a_hold_is_not_erased(client, admin_headers, raise_ticket, monkeypatch):
    now = utcnow(); clock(monkeypatch, now)
    number = late(raise_ticket, now)
    patch(client, admin_headers, number, status="on_hold", note="Waiting for an inspection.")
    clock(monkeypatch, now + timedelta(hours=7))
    resumed = patch(client, admin_headers, number, status="in_progress").json()["case"]["deadlines"]
    assert resumed["overdue"] and datetime.fromisoformat(resumed["due_at"]) == now + timedelta(hours=6)


def test_response_during_system_hold_accounts_for_only_elapsed_pause(client, admin_headers, raise_ticket, monkeypatch):
    now = utcnow(); clock(monkeypatch, now)
    number = raise_ticket(email=None)
    edit(number, first_response_due_at=now + timedelta(hours=4))
    with SessionLocal() as db:
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        tickets.change_status(db, ticket, "on_hold", None, "System hold"); db.commit()
    clock(monkeypatch, now + timedelta(hours=6))
    reply = client.post(f"/api/v1/admin/tickets/{number}/messages", headers=admin_headers, json={"visibility": "customer", "message": "We will contact you when work resumes."}).json()
    first = reply["case"]["deadlines"]
    assert not first["first_response_missed"] and datetime.fromisoformat(first["first_response_due_at"]) == now + timedelta(hours=10)
    clock(monkeypatch, now + timedelta(hours=8))
    resumed = patch(client, admin_headers, number, status="in_progress").json()["case"]["deadlines"]
    assert resumed["first_response_due_at"] == first["first_response_due_at"] and resumed["paused_seconds"] == 28800


def test_two_breaches_are_deduplicated_and_monitor_is_not_first_response(client, admin_headers, raise_ticket):
    now = utcnow(); number = late(raise_ticket, now, first=True)
    edit(number, due_at=now - timedelta(hours=2))
    assert scan(now) == 2 and scan(now) == 0
    alerts = rows(CaseDeadlineAlert)
    assert {a.kind for a in alerts} == {"case_due", "first_response"}
    outgoing = rows(Notification, template_key="case_deadline_alert")
    assert len(outgoing) == 2 and all(n.user_id and not n.customer_id and n.channel == "email" for n in outgoing)
    assert all(t.first_response_at is None for t in rows(ServiceRequest))


def test_owner_alert_escalates_to_admins_and_reopens_acknowledgement(client, admin_headers, agent, raise_ticket, monkeypatch):
    now = utcnow(); clock(monkeypatch, now)
    number = raise_ticket(email=None)
    client.post(f"/api/v1/admin/tickets/{number}/assignment", headers=admin_headers, json={"agent_id": agent["id"]})
    edit(number, due_at=now - timedelta(hours=1))
    assert scan(now) == 1
    mail = rows(Notification, template_key="case_deadline_alert")
    assert len(mail) == 1 and str(mail[0].user_id) == agent["id"]
    alert = client.get(ALERTS, headers=agent["headers"]).json()["items"][0]
    assert client.post(f"{ALERTS}/{alert['id']}/acknowledge", headers=agent["headers"]).status_code == 200
    assert client.get(ALERTS, headers=admin_headers).json()["unacknowledged"] == 0
    later = now + timedelta(hours=config.CASE_ESCALATION_HOURS)
    clock(monkeypatch, later); assert scan(later) == 0
    result = client.get(ALERTS, headers=admin_headers).json()
    assert result["unacknowledged"] == result["escalated"] == 1
    assert result["items"][0]["acknowledged_at"] is None
    assert len(rows(Notification, template_key="case_deadline_alert")) == 3
    scan(later)
    assert len(rows(Notification, template_key="case_deadline_alert")) == 3


def test_already_escalated_first_scan_does_not_queue_both_stages(client, admin_headers, raise_ticket):
    now = utcnow(); number = late(raise_ticket, now)
    edit(number, due_at=now - timedelta(hours=config.CASE_ESCALATION_HOURS + 1))
    assert scan(now) == 1
    mail = rows(Notification, template_key="case_deadline_alert")
    assert len(mail) == 1 and mail[0].params == ["case_due", "escalated"]


def test_alert_access_pagination_and_ack_audit_do_not_satisfy_response(client, admin_headers, agent, raise_ticket):
    now = utcnow(); late(raise_ticket, now, first=True); late(raise_ticket, now)
    scan(now)
    assert client.get(ALERTS).status_code == 401  # Customer token from raise_ticket.
    assert client.get(ALERTS, headers=agent["headers"]).json()["items"] == []
    page = client.get(ALERTS + "?page_size=1", headers=admin_headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    id = page["items"][0]["id"]
    assert client.post(f"{ALERTS}/{id}/acknowledge", headers=agent["headers"]).status_code == 404
    assert client.post(f"{ALERTS}/{id}/acknowledge", headers=admin_headers).status_code == 200
    assert client.post(f"{ALERTS}/{id}/acknowledge", headers=admin_headers).status_code == 200
    assert client.get(ALERTS, headers=admin_headers).json()["unacknowledged"] == 1
    assert client.get(ALERTS + "?include_acknowledged=true", headers=admin_headers).json()["total"] == 2
    assert all(t.first_response_at is None for t in rows(ServiceRequest))
    assert len(rows(AuditLog, action="case.deadline_acknowledged")) == 1


@pytest.mark.parametrize("action", ["hold", "close", "move", "suspend", "unassign", "acknowledge"])
def test_queued_email_is_rechecked_before_delivery(client, admin_headers, agent, raise_ticket, monkeypatch, action):
    now = utcnow(); number = raise_ticket(email=None)
    client.post(f"/api/v1/admin/tickets/{number}/assignment", headers=admin_headers, json={"agent_id": agent["id"]})
    edit(number, due_at=now - timedelta(hours=1)); scan(now)
    alert = rows(CaseDeadlineAlert)[0]
    if action == "hold": patch(client, admin_headers, number, status="on_hold", note="Waiting for access.")
    elif action == "close": patch(client, admin_headers, number, status="cancelled")
    elif action == "move": patch(client, admin_headers, number, due_at=(now + timedelta(days=1)).isoformat(), due_reason="New agreed date")
    elif action == "suspend":
        with SessionLocal() as db:
            db.get(User, uuid.UUID(agent["id"])).account_status = "suspended"; db.commit()
    elif action == "unassign": client.post(f"/api/v1/admin/tickets/{number}/assignment", headers=admin_headers, json={"agent_id": None})
    else: client.post(f"{ALERTS}/{alert.id}/acknowledge", headers=admin_headers)
    monkeypatch.setattr(providers, "enabled", lambda channel: channel == "email")
    monkeypatch.setattr(providers, "send_email", lambda *args: pytest.fail("Stale staff alert was delivered"))
    with SessionLocal() as db: assert notify.deliver_due(db, now + timedelta(seconds=1)) == 0
    assert all(n.delivery_status == "cancelled" for n in rows(Notification, template_key="case_deadline_alert"))


def test_reply_resolves_first_response_alert_before_next_scan(client, admin_headers, raise_ticket, monkeypatch):
    now = utcnow(); number = late(raise_ticket, now, first=True); scan(now)
    client.post(f"/api/v1/admin/tickets/{number}/messages", headers=admin_headers, json={"visibility": "customer", "message": "We are reviewing your request."})
    assert client.get(ALERTS, headers=admin_headers).json()["total"] == 0
    monkeypatch.setattr(providers, "enabled", lambda channel: channel == "email")
    monkeypatch.setattr(providers, "send_email", lambda *args: pytest.fail("Resolved response alert was delivered"))
    with SessionLocal() as db: assert notify.deliver_due(db, now + timedelta(seconds=1)) == 0
    scan(now + timedelta(seconds=1))
    assert rows(CaseDeadlineAlert)[0].resolved_at


def test_changing_target_resolves_old_incident_and_creates_one_new_alert(client, admin_headers, raise_ticket):
    now = utcnow(); number = late(raise_ticket, now); scan(now)
    patch(client, admin_headers, number, due_at=(now - timedelta(hours=2)).isoformat(), due_reason="Correct target entered")
    assert scan(now) == 1 and scan(now) == 0
    alerts = rows(CaseDeadlineAlert)
    assert len(alerts) == 2 and sum(a.resolved_at is None for a in alerts) == 1
    assert client.get(ALERTS, headers=admin_headers).json()["total"] == 1


def test_staff_email_uses_staff_portal_and_contains_no_case_details(client, admin_headers, raise_ticket):
    now = utcnow(); late(raise_ticket, now); scan(now)
    notification = rows(Notification, template_key="case_deadline_alert")[0]
    subject, body = providers.customer_message(notification, "HX-SYNTHETIC")
    assert "Homexo staff" in subject and "/admin/alerts" in body and "/account" not in body
    assert "Sample Customer" not in body and "Whitefield" not in body and "HX-SYNTHETIC" in body


def test_active_staff_alert_delivers_once_with_a_mock_provider(client, admin_headers, raise_ticket, monkeypatch):
    now = utcnow(); late(raise_ticket, now); scan(now)
    delivered = []
    monkeypatch.setattr(providers, "enabled", lambda channel: channel == "email")
    def send(notification, ticket_number):
        delivered.append((notification.id, ticket_number))
        return "synthetic-alert-reference"
    monkeypatch.setattr(providers, "send_email", send)
    with SessionLocal() as db:
        assert notify.deliver_due(db, now + timedelta(seconds=1)) == 1
        assert notify.deliver_due(db, now + timedelta(seconds=2)) == 0
    assert len(delivered) == 1
    notification = rows(Notification, template_key="case_deadline_alert")[0]
    assert notification.delivery_status == "sent" and notification.attempts == 1 and notification.provider_reference == "synthetic-alert-reference"


@pytest.mark.skipif(not config.DATABASE_URL.startswith("postgresql"), reason="Requires PostgreSQL case row locks")
def test_concurrent_monitors_do_not_duplicate_alerts(client, admin_headers, raise_ticket):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    now = utcnow(); late(raise_ticket, now)
    ready = Barrier(2)
    def run(_): ready.wait(timeout=10); return scan(now)
    with ThreadPoolExecutor(max_workers=2) as pool: assert sum(pool.map(run, range(2))) == 1
    assert len(rows(CaseDeadlineAlert)) == len(rows(Notification, template_key="case_deadline_alert")) == 1


@pytest.mark.skipif(not config.DATABASE_URL.startswith("postgresql"), reason="Requires PostgreSQL case row locks")
def test_concurrent_resumes_add_hold_time_once(client, admin_headers, raise_ticket, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    now = utcnow(); clock(monkeypatch, now); number = raise_ticket(email=None)
    held = patch(client, admin_headers, number, status="on_hold", note="Waiting for access.").json()
    original = datetime.fromisoformat(held["case"]["deadlines"]["due_at"])
    clock(monkeypatch, now + timedelta(hours=5)); ready = Barrier(2)
    def resume(_):
        ready.wait(timeout=10)
        response = patch(client, admin_headers, number, status="in_progress")
        assert response.status_code == 200
        return response.json()["case"]["deadlines"]
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(resume, range(2)))
    assert all(datetime.fromisoformat(r["due_at"]) == original + timedelta(hours=5) and r["paused_seconds"] == 18000 for r in results)
