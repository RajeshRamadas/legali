"""Queue deadlines use one clock, compose with existing filters, and never mutate work."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import config, support
from app.db import SessionLocal
from app.models import AuditLog, Notification, SupportRequest
from conftest import authenticate_customer
from test_support import ADMIN, BASE, create

NOW = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def requests(client, admin_headers, monkeypatch):
    monkeypatch.setattr(support, "utcnow", lambda: NOW)
    authenticate_customer(client)
    initial = create(client)
    owner = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    specs = [
        ("old", "open", -48, 0), ("recent", "in_progress", -1, -120),
        ("now", "open", 0, -96), ("soon", "open", 1, -72),
        ("edge", "open", 24, -48), ("later", "open", 25, -24),
        ("waiting", "waiting_for_customer", None, 1), ("resolved", "resolved", -240, 2),
    ]
    ids = {}
    with SessionLocal() as db:
        account_id = db.get(SupportRequest, uuid.UUID(initial["id"])).account_id
        db.delete(db.get(SupportRequest, uuid.UUID(initial["id"]))); db.flush()
        for number, (name, status, hours, updated) in enumerate(specs, 1):
            item = SupportRequest(id=uuid.UUID(int=number), account_id=account_id, submission_key=uuid.uuid4(),
                subject=f"Priority fixture {name}", details="PRIVATE initial description", kind="documents" if name == "old" else "other",
                status=status, reply_due_at=NOW+timedelta(hours=hours) if hours is not None else None,
                created_at=NOW-timedelta(days=20), updated_at=NOW+timedelta(hours=updated),
                assignee_user_id=uuid.UUID(owner) if name == "old" else None)
            if name == "later": item.reply_due_at = NOW+timedelta(hours=24, microseconds=1)
            db.add(item); ids[name] = str(item.id)
        db.commit()
    return ids


def queue(client, headers, **params):
    response = client.get(ADMIN, headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def test_target_boundaries_include_now_and_24_hours_but_exclude_resolved(client, admin_headers, requests):
    for target, names in (("overdue", ["old", "recent"]), ("due_soon", ["now", "soon", "edge"]),
                          ("none", ["resolved", "waiting"]), ("all", ["old", "recent", "now", "soon", "edge", "later", "resolved", "waiting"])):
        result = queue(client, admin_headers, status="all", response_target=target, sort="response_target")
        assert [row["id"] for row in result["items"]] == [requests[name] for name in names]
        assert result["total"] == len(names)
        assert result["overdue"] == 2
        assert result["filtered_overdue"] == (2 if target in ("overdue", "all") else 0)
        assert result["response_target_as_of"] == NOW.isoformat()
        assert all(row["overdue"] == (row["id"] in (requests["old"], requests["recent"])) for row in result["items"])
        assert "PRIVATE" not in str(result) and all("details" not in row for row in result["items"])
    # A resolved record with a legacy target has no pending target.
    assert queue(client, admin_headers, status="resolved", response_target="overdue")["total"] == 0
    assert queue(client, admin_headers, status="resolved", response_target="none")["total"] == 1


def test_filters_intersect_and_reading_keeps_revisions_targets_and_audits(client, admin_headers, requests):
    with SessionLocal() as db:
        before = [(str(row.id), row.revision, row.reply_due_at, row.updated_at) for row in db.scalars(select(SupportRequest).order_by(SupportRequest.id))]
        audit_count = db.scalar(select(func.count()).select_from(AuditLog))
    result = queue(client, admin_headers, response_target="overdue", assignee="me", kind="documents", q="fixture old")
    assert result["total"] == result["filtered_overdue"] == 1 and result["items"][0]["id"] == requests["old"]
    assert queue(client, admin_headers, response_target="overdue", assignee="unassigned")["items"][0]["id"] == requests["recent"]
    assert queue(client, admin_headers, response_target="due_soon", q="missing")["total"] == 0
    assert queue(client, admin_headers, response_target="overdue", q="SR-"+requests["old"].replace("-", ""))["total"] == 1
    with SessionLocal() as db:
        assert before == [(str(row.id), row.revision, row.reply_due_at, row.updated_at) for row in db.scalars(select(SupportRequest).order_by(SupportRequest.id))]
        assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_count
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_stable_paging_ties_and_legacy_recent_update_order(client, admin_headers, requests):
    with SessionLocal() as db:
        old, recent = (db.get(SupportRequest, uuid.UUID(requests[name])) for name in ("old", "recent"))
        recent.reply_due_at, recent.updated_at = old.reply_due_at, old.updated_at
        db.commit()
    first = queue(client, admin_headers, sort="response_target", page_size=1)
    second = queue(client, admin_headers, sort="response_target", page_size=1, page=2)
    assert first["items"][0]["id"] == requests["old"]
    assert second["items"][0]["id"] == requests["recent"]
    assert first["total"] == second["total"] == 7
    assert queue(client, admin_headers, sort="response_target", page=99)["items"] == []
    default = queue(client, admin_headers, status="all")
    updated = queue(client, admin_headers, status="all", sort="updated")
    assert default["items"] == updated["items"]
    assert updated["items"][0]["id"] == requests["resolved"]
    assert queue(client, admin_headers, status="all", response_target="none", sort="response_target")["items"][0]["id"] == requests["resolved"]


def test_authorization_validation_and_lookup_budget(client, admin_headers, agent, requests, monkeypatch):
    assert client.get(ADMIN, headers=agent["headers"], params={"response_target": "overdue"}).status_code == 403
    assert client.get(ADMIN).status_code == 401  # Customer session is not a staff session.
    client.headers.pop("authorization", None)
    assert client.get(ADMIN).status_code == 401
    for params in ({"response_target": "invalid"}, {"sort": "sql"}, {"response_target": "Overdue"}, {"page": 0}):
        assert client.get(ADMIN, headers=admin_headers, params=params).status_code == 422
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(ADMIN, headers=admin_headers, params={"response_target": "overdue"}).status_code == 429


def test_customer_queue_keeps_its_order_and_excludes_staff_metadata(client, admin_headers, requests):
    result = client.get(BASE, params={"response_target": "overdue", "sort": "response_target"}).json()
    assert len(result["items"]) == 8
    assert result["items"][0]["id"] == requests["resolved"]
    assert "response_target_as_of" not in result
    assert all("assignee" not in row and "customer" not in row for row in result["items"])
