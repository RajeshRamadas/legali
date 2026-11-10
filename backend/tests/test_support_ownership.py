import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.db import SessionLocal, engine
from app.main import app
from app.models import AuditLog, Notification, Role, SupportRequest, User, utcnow
from conftest import authenticate_customer
from test_support import BASE, ADMIN, create, review, reply


def assign(client, headers, item, owner):
    return client.patch(f"{ADMIN}/{item['id']}/assignment", headers=headers,
        json={"revision": item["revision"], "assignee_user_id": owner})


def another_admin():
    with SessionLocal() as db:
        person = User(display_name="Second support administrator", email="second-support@example.invalid", password_hash="unused-synthetic-password", roles=[db.scalar(select(Role).where(Role.name == "admin"))])
        db.add(person); db.commit(); return str(person.id)


def test_authorization_candidates_customer_privacy_and_strict_payloads(client, admin_headers, agent):
    authenticate_customer(client); item = create(client)
    urls = [ADMIN+"/owners", f"{ADMIN}/{item['id']}/assignments"]
    for url in urls:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=agent["headers"]).status_code == 403
    assert client.get(ADMIN+"/owners", headers={"Authorization": "Bearer invalid"}).headers["cache-control"] == "private, no-store"
    owner = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    candidates = client.get(ADMIN+"/owners", headers=admin_headers).json()["items"]
    assert candidates == [{"id": owner, "name": "Meera Admin"}]
    assert assign(client, agent["headers"], item, owner).status_code == 403
    assert assign(client, dict(client.headers), item, owner).status_code == 401
    for body in ({"revision": "1", "assignee_user_id": owner}, {"revision": 1}, {"revision": True, "assignee_user_id": None}, {"revision": 1, "assignee_user_id": None, "extra": 1}):
        assert client.patch(f"{ADMIN}/{item['id']}/assignment", headers=admin_headers, json=body).status_code == 422
    assert assign(client, admin_headers, item, agent["id"]).status_code == 422
    assert assign(client, admin_headers, item, str(uuid.uuid4())).status_code == 422
    assigned = assign(client, admin_headers, item, owner)
    assert assigned.status_code == 200 and assigned.json()["assignee"]["name"] == "Meera Admin"
    for data in (client.get(BASE).json()["items"][0], client.get(f"{BASE}/{item['id']}").json()):
        assert "assignee" not in data and "Meera Admin" not in str(data) and owner not in str(data)


def test_assignment_preserves_due_status_unread_and_conversation_and_audits_changes(client, admin_headers):
    authenticate_customer(client); item = create(client); owner = another_admin()
    item = review(client, admin_headers, item, status="resolved", customer_response="A saved response that must remain unread.").json()
    before = client.get(f"{BASE}/{item['id']}").json()
    changed = assign(client, admin_headers, item, owner).json()
    assert changed["revision"] == item["revision"]+1
    for key in ("reply_due_at", "status", "unread_replies", "customer_update_revision", "customer_read_revision", "resolved_at"):
        assert changed[key] == before[key]
    unchanged = assign(client, admin_headers, changed, owner).json()
    assert unchanged["revision"] == changed["revision"]
    history = client.get(f"{ADMIN}/{item['id']}/assignments", headers=admin_headers).json()
    assert history["total"] == 1 and history["items"][0]["owner"]["id"] == owner
    assert history["items"][0]["actor"] == "Meera Admin"
    # A follow-up keeps the owner; unassignment changes only private ownership.
    followed = reply(client, item).json()
    staff = client.get(f"{ADMIN}/{item['id']}", headers=admin_headers).json()
    assert staff["assignee"]["id"] == owner
    cleared = assign(client, admin_headers, staff, None).json()
    assert cleared["assignee"] is None
    assert client.get(f"{ADMIN}/{item['id']}/assignments", headers=admin_headers).json()["total"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
        events = list(db.scalars(select(AuditLog).where(AuditLog.action == "support.assigned")))
        assert len(events) == 2 and all("response" not in str(event.metadata_) for event in events)


def test_stale_ownership_and_reply_drafts_conflict_and_disabled_owners_cannot_receive_work(client, admin_headers):
    authenticate_customer(client); item = create(client); owner = another_admin()
    changed = assign(client, admin_headers, item, owner).json()
    assert assign(client, admin_headers, item, None).status_code == 409
    assert review(client, admin_headers, item, customer_response="A stale reply draft must not close over assignment.").status_code == 409
    assert review(client, admin_headers, changed, customer_response="A current reply is accepted after ownership reload.").status_code == 200
    with SessionLocal() as db:
        person = db.get(User, uuid.UUID(owner)); person.account_status = "suspended"; db.commit()
    assert owner not in str(client.get(ADMIN+"/owners", headers=admin_headers).json())
    current = client.get(f"{ADMIN}/{item['id']}", headers=admin_headers).json()
    assert current["assignee"]["active"] is False
    assert client.get(ADMIN, headers=admin_headers, params={"assignee": "inactive"}).json()["total"] == 1
    assert assign(client, admin_headers, current, owner).status_code == 422
    assert assign(client, admin_headers, current, None).status_code == 200


def test_owner_filters_and_filtered_overdue_counts(client, admin_headers, monkeypatch):
    authenticate_customer(client); first, second = create(client), create(client)
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    assign(client, admin_headers, first, me)
    with SessionLocal() as db:
        for row in db.scalars(select(SupportRequest)):
            row.reply_due_at = utcnow()-timedelta(hours=1)
        db.commit()
    mine = client.get(ADMIN, headers=admin_headers, params={"assignee": "me"}).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == first["id"] and mine["filtered_overdue"] == 1 and mine["overdue"] == 2
    unassigned = client.get(ADMIN, headers=admin_headers, params={"assignee": "unassigned"}).json()
    assert unassigned["total"] == 1 and unassigned["items"][0]["id"] == second["id"]
    assert client.get(ADMIN, headers=admin_headers, params={"assignee": me}).json()["total"] == 1
    assert client.get(ADMIN, headers=admin_headers, params={"assignee": "invalid-owner"}).status_code == 422
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(ADMIN+"/owners", headers=admin_headers).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Concurrent support assignment row locks")
def test_concurrent_assignments_have_one_winner_and_preserve_the_other_draft(client, admin_headers):
    authenticate_customer(client); item = create(client)
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    other = another_admin(); barrier = Barrier(2)
    def change(target):
        with TestClient(app) as second:
            barrier.wait(timeout=5)
            return assign(second, admin_headers, item, target).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(change, me), pool.submit(change, other)]
        assert sorted(future.result(timeout=10) for future in futures) == [200,409]
    assert client.get(f"{ADMIN}/{item['id']}/assignments", headers=admin_headers).json()["total"] == 1
