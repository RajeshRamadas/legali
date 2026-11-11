"""Staff deadline delivery tests use synthetic incidents and mocked email transports."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, notify, support_deadline_email, support_alerts
from app.db import SessionLocal, engine
from app.main import app
from app.models import Notification, Role, SupportDeadlineAlert, SupportRequest, User, utcnow
from test_notifications import configured, run, transport  # noqa: F401
from test_support import BASE, ADMIN, review
from test_support_alerts import ALERTS, ack, listing, overdue, reconcile
from test_support_ownership import assign, another_admin


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(config, "SUPPORT_DEADLINE_EMAIL_ENABLED", True)


def notices():
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.template_key == "support_deadline_email").order_by(Notification.created_at, Notification.id)))


def owner_id(client, headers):
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]


def test_owner_gets_one_initial_email_and_escalation_reaches_all_active_administrators(client, admin_headers, agent):
    item, due = overdue(client)
    owner = owner_id(client, admin_headers); second = another_admin()
    assert assign(client, admin_headers, item, owner).status_code == 200
    before = client.get(f"{BASE}/{item['id']}").json()
    assert reconcile() == 1 and reconcile() == 0
    rows = notices()
    assert len(rows) == 1 and str(rows[0].user_id) == owner and rows[0].params == ["initial"]
    assert rows[0].account_id is rows[0].customer_id is rows[0].support_request_id is rows[0].service_request_id is None
    incident = listing(client, admin_headers)["items"][0]
    assert ack(client, admin_headers, incident).status_code == 200
    assert notices()[0].delivery_status == "cancelled"
    reconcile(due + timedelta(hours=config.SUPPORT_ESCALATION_HOURS + 1))
    rows = notices()
    escalated = [n for n in rows if n.params == ["escalated"]]
    assert len(escalated) == 2 and {str(n.user_id) for n in escalated} == {owner, second}
    assert all(n.support_alert_revision == 2 and n.delivery_status == "queued" for n in escalated)
    assert client.get(f"{BASE}/{item['id']}").json() == before
    assert reconcile(due + timedelta(hours=config.SUPPORT_ESCALATION_HOURS + 2)) == 0 and len(notices()) == 3


@pytest.mark.parametrize("owner_state", ["unassigned", "no_email", "invalid_email", "inactive", "agent"])
def test_unavailable_owner_falls_back_to_eligible_admins_only(client, admin_headers, agent, owner_state):
    item, _ = overdue(client)
    second = another_admin()
    if owner_state != "unassigned":
        assert assign(client, admin_headers, item, second).status_code == 200
        with SessionLocal() as db:
            user = db.get(User, uuid.UUID(second))
            if owner_state == "no_email": user.email = None
            elif owner_state == "invalid_email": user.email = "not an email"
            elif owner_state == "inactive": user.account_status = "suspended"
            elif owner_state == "agent": user.roles = [db.scalar(select(Role).where(Role.name == "agent"))]
            db.commit()
    reconcile()
    expected = {owner_id(client, admin_headers), second} if owner_state == "unassigned" else {owner_id(client, admin_headers)}
    assert {str(n.user_id) for n in notices()} == expected
    assert all(n.channel == "email" for n in notices())


def test_handoff_cancels_former_owner_without_replaying_old_route(client, admin_headers):
    item, _ = overdue(client); first = owner_id(client, admin_headers); second = another_admin()
    item = assign(client, admin_headers, item, first).json(); reconcile()
    item = assign(client, admin_headers, item, second).json()
    assert notices()[0].delivery_status == "cancelled"
    reconcile()
    pending = [n for n in notices() if n.delivery_status == "queued"]
    assert len(pending) == 1 and str(pending[0].user_id) == second
    item = assign(client, admin_headers, item, first).json(); reconcile()
    assert len(notices()) == 2 and all(n.delivery_status == "cancelled" for n in notices())


def test_new_contact_queues_fresh_notice_without_retargeting_old_record(client, admin_headers):
    item, _ = overdue(client); owner = owner_id(client, admin_headers)
    assert assign(client, admin_headers, item, owner).status_code == 200
    reconcile(); original = notices()[0]
    with SessionLocal() as db:
        db.get(User, uuid.UUID(owner)).email = "new-admin@example.invalid"; db.commit()
    reconcile()
    rows = notices()
    assert len(rows) == 2
    old = next(n for n in rows if n.id == original.id)
    new = next(n for n in rows if n.id != original.id)
    assert old.recipient == original.recipient and old.delivery_status == "cancelled"
    assert new.recipient == "new-admin@example.invalid" and new.delivery_status == "queued"


def test_acknowledgement_and_customer_response_stop_pending_notices_without_worker(client, admin_headers):
    item, _ = overdue(client); reconcile()
    incident = listing(client, admin_headers)["items"][0]
    assert ack(client, admin_headers, incident).status_code == 200
    assert all(n.delivery_status == "cancelled" for n in notices())
    # A new request demonstrates immediate reply cancellation independently of acknowledgement.
    second, _ = overdue(client); reconcile()
    assert any(n.delivery_status == "queued" for n in notices())
    result = review(client, admin_headers, second, customer_response="PRIVATE customer-visible resolution", internal_note="PRIVATE internal discussion")
    assert result.status_code == 200
    assert all(n.delivery_status == "cancelled" for n in notices())


def test_enabled_metadata_and_customer_preferences_do_not_disable_private_staff_email(client, admin_headers, configured):
    item, _ = overdue(client)
    assert client.put("/api/v1/account/notification-preferences", json={"email": False,"sms":False,"whatsapp":False,"revision":0}).status_code == 200
    assert client.get(ALERTS, headers=admin_headers).json()["email_delivery"] == "enabled"
    reconcile()
    assert all(n.delivery_status == "queued" for n in notices())
    assert client.get(ALERTS).status_code == 401


def test_generic_provider_text_and_idempotency_never_include_private_record_or_params(client, admin_headers, configured, monkeypatch):
    item, _ = overdue(client); reconcile(); calls=[]
    with SessionLocal() as db:
        n = db.scalar(select(Notification)); n.body="PRIVATE support concern"; db.commit()
    def handler(request):
        calls.append(request); return httpx.Response(200,json={"id":"synthetic-staff-email"})
    transport(monkeypatch, handler)
    assert run() == 1 and run() == 0
    payload=json.loads(calls[0].content)
    assert payload["subject"] == "Homexo staff: Support response target missed"
    assert "/admin/support/alerts" in payload["text"]
    assert all(value not in str(payload) for value in ("PRIVATE", item["subject"], item["id"], "9876543210"))
    notice=notices()[0]
    assert calls[0].headers["idempotency-key"] == f"homexo-notification/{notice.id}"
    assert notice.delivery_status == "sent" and notice.provider_reference == "synthetic-staff-email"


@pytest.mark.parametrize("change", ["ack", "reply", "handoff", "role", "email", "disabled"])
def test_worker_revalidates_after_claim_without_using_stale_models(client, admin_headers, configured, monkeypatch, change):
    item, _ = overdue(client); owner=owner_id(client,admin_headers); second=another_admin()
    item=assign(client,admin_headers,item,owner).json(); reconcile()
    alert=listing(client,admin_headers)["items"][0]
    original,calls=support_deadline_email.cancellation_reason,[]
    def check(db, notification, now):
        calls.append(notification.id)
        if len(calls)==2:
            if change=="ack": assert ack(client,admin_headers,alert).status_code==200
            elif change=="reply": assert review(client,admin_headers,item,customer_response="Reply after the worker's claim").status_code==200
            elif change=="handoff": assert assign(client,admin_headers,item,second).status_code==200
            elif change=="disabled": monkeypatch.setattr(config,"SUPPORT_DEADLINE_EMAIL_ENABLED",False)
            else:
                with SessionLocal() as other:
                    user=other.get(User,uuid.UUID(owner))
                    if change=="email": user.email="changed@example.invalid"
                    else: user.roles=[other.scalar(select(Role).where(Role.name=="agent"))]
                    other.commit()
        return original(db,notification,now)
    monkeypatch.setattr(support_deadline_email,"cancellation_reason",check)
    monkeypatch.setattr(notify.providers,"send_email",lambda *args:pytest.fail("Obsolete staff alert reached a provider"))
    assert run()==0 and len(calls)==2
    assert notices()[0].delivery_status=="cancelled"


def test_disabling_unconfigured_delivery_cancels_unsent_notices_and_preserves_in_app_alert(client, admin_headers, monkeypatch):
    item,_=overdue(client); reconcile()
    monkeypatch.setattr(config,"SUPPORT_DEADLINE_EMAIL_ENABLED",False)
    monkeypatch.setattr(notify.providers,"enabled",lambda channel:False)
    monkeypatch.setattr(notify.whatsapp,"enabled",lambda:False)
    assert run()==0 and notices()[0].delivery_status=="cancelled"
    assert listing(client,admin_headers)["total"]==1
    assert client.get(ALERTS,headers=admin_headers).json()["email_delivery"]=="disabled"
    monkeypatch.setattr(config,"SUPPORT_DEADLINE_EMAIL_ENABLED",True)
    assert client.get(ALERTS,headers=admin_headers).json()["email_delivery"]=="unconfigured"
    reconcile(); assert len(notices())==1  # No replay of cancelled recipient/revision.


def test_provider_already_in_flight_retains_truthful_acceptance_after_ack(client, admin_headers, configured, monkeypatch):
    item,_=overdue(client); reconcile(); incident=listing(client,admin_headers)["items"][0]
    def send(*args):
        assert ack(client,admin_headers,incident).status_code==200
        return "provider-already-accepted"
    monkeypatch.setattr(notify.providers,"send_email",send)
    assert run()==1
    assert notices()[0].delivery_status=="sent" and notices()[0].provider_reference=="provider-already-accepted"


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Independent monitoring locks require PostgreSQL")
def test_concurrent_reconciliation_deduplicates_staff_delivery(client,admin_headers):
    item,_=overdue(client); barrier=Barrier(2)
    def check(_): barrier.wait(timeout=10); return reconcile()
    with ThreadPoolExecutor(max_workers=2) as pool: assert sum(pool.map(check,range(2)))==1
    assert len(notices())==1
