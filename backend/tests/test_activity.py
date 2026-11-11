import base64
import copy
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import event, func, select

from app import config
from app.activity import ACTIONS, GROUPS
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, AuditLog, Notification, User
from conftest import authenticate_customer

BASE = "/api/v1/admin/activity"
WHEN = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)
SECRET = "PRIVATE-payload-credential@example.test"
RECORD = uuid.UUID("af1251c4-0979-4c1a-86aa-601d77e75601")


def add(action="service.intake_form_published", *, actor=None, at=WHEN, entity_type="service_type", entity_id=RECORD, key=None):
    with SessionLocal() as db:
        row = AuditLog(id=key or uuid.uuid4(), actor_user_id=actor, action=action, entity_type=entity_type, entity_id=entity_id,
            created_at=at, metadata_={"body": SECRET, "token": SECRET, "questions": [{"prompt": SECRET}], "reason": SECRET}, request_id=SECRET, ip_hash=SECRET)
        db.add(row); db.commit(); return str(row.id)


def test_activity_is_admin_only_private_and_read_only(client, admin_headers, agent):
    assert client.get(BASE).status_code == 401
    authenticate_customer(client)
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=agent["headers"]).status_code == 403
    for method in ("post", "patch", "delete"):
        assert getattr(client, method)(BASE, headers=admin_headers).status_code == 405
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@homexo.test"))
        actor = admin.id
    key = add(actor=actor)
    with SessionLocal() as db:
        before = {str(row.id): copy.deepcopy(row.metadata_) for row in db.scalars(select(AuditLog))}
        notices = db.scalar(select(func.count()).select_from(Notification))
    selected = []
    def inspect_query(connection, cursor, statement, parameters, context, many):
        if "audit_logs" in statement: selected.append(statement)
    event.listen(engine, "before_cursor_execute", inspect_query)
    try:
        for _ in range(2):
            response = client.get(BASE, headers=admin_headers)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store" and "authorization" in response.headers["vary"].lower()
            assert SECRET not in response.text and "admin@homexo.test" not in response.text
        row = next(row for row in response.json()["items"] if row["id"] == key)
        assert row["actor"] == "Meera Admin" and row["category"] == "services" and row["record_id"] == str(RECORD)
        assert set(row) == {"id", "at", "actor", "category", "activity", "record_type", "record_id"}
    finally:
        event.remove(engine, "before_cursor_execute", inspect_query)
    assert selected and all("metadata" not in statement and "ip_hash" not in statement and "request_id" not in statement for statement in selected)
    with SessionLocal() as db:
        assert before == {str(row.id): row.metadata_ for row in db.scalars(select(AuditLog))}
        assert db.scalar(select(func.count()).select_from(Notification)) == notices


def test_categories_are_explicit_and_unknown_action_and_record_text_are_never_exposed(client, admin_headers):
    ids = {category: add(next(iter(actions))) for category, (_, actions) in GROUPS.items()}
    unknown = add(SECRET, entity_type=SECRET)
    for category, key in ids.items():
        result = client.get(BASE, headers=admin_headers, params={"category": category}).json()
        assert key in [row["id"] for row in result["items"]]
        assert all(row["category"] == category for row in result["items"])
    other = client.get(BASE, headers=admin_headers, params={"category": "other"}).json()
    assert other["items"] == [{"id": unknown, "at": WHEN.isoformat(), "actor": "Unattributed · customer, system or former staff",
        "activity": "Other recorded activity", "category": "other", "record_type": "Other record", "record_id": None}]
    assert SECRET not in str(other) and len(ACTIONS) == sum(len(actions) for _, actions in GROUPS.values())


def test_combined_actor_category_record_and_india_calendar_day_filters(client, admin_headers):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@homexo.test")); actor = admin.id
    first = datetime(2026, 11, 10, 18, 30, tzinfo=timezone.utc)
    last = datetime(2026, 11, 11, 18, 29, 59, 999999, tzinfo=timezone.utc)
    kept = {add(actor=actor, at=first), add(actor=actor, at=last)}
    add(actor=actor, at=first-timedelta(microseconds=1)); add(actor=actor, at=last+timedelta(microseconds=1))
    add(actor=actor, entity_id=uuid.uuid4()); add(actor=actor, action="support.reviewed"); add()
    result = client.get(BASE, headers=admin_headers, params={"category": "services", "actor": "  meERA  ", "record_id": str(RECORD), "from_date": "2026-11-11", "to_date": "2026-11-11"}).json()
    assert {row["id"] for row in result["items"]} == kept


def test_name_wildcards_are_literal_and_current_names_do_not_guess_missing_actors(client, admin_headers):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@homexo.test")); admin.display_name = "Literal %_\\ Name"; actor = admin.id; db.commit()
    key = add(actor=actor); add()
    result = client.get(BASE, headers=admin_headers, params={"actor": "%_\\"}).json()
    assert key in [row["id"] for row in result["items"]]
    assert all(row["actor"] == "Literal %_\\ Name" for row in result["items"])
    assert client.get(BASE, headers=admin_headers, params={"actor": "Missing staff"}).json()["items"] == []


def test_cursor_ties_and_new_inserts_do_not_skip_or_duplicate_older_history(client, admin_headers):
    keys = [add(key=uuid.UUID(int=n)) for n in range(1, 8)]
    params = {"page_size": 2, "category": "services"}
    first = client.get(BASE, headers=admin_headers, params=params).json()
    assert [row["id"] for row in first["items"]] == list(reversed(keys))[:2]
    newer = add(at=WHEN+timedelta(seconds=1))
    seen = [row["id"] for row in first["items"]]; cursor = first["next_cursor"]
    while cursor:
        result = client.get(BASE, headers=admin_headers, params={**params, "cursor": cursor}).json()
        seen += [row["id"] for row in result["items"]]; cursor = result["next_cursor"]
    assert seen == list(reversed(keys)) and newer not in seen
    assert client.get(BASE, headers=admin_headers, params=params).json()["items"][0]["id"] == newer
    # A cursor never changes the category or record scope of a later lookup.
    assert client.get(BASE, headers=admin_headers, params={"cursor": first["next_cursor"], "category": "refunds"}).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"category": "credentials"}, {"actor": "x"*101}, {"actor": "bad\x00name"}, {"record_id": "not-a-uuid"},
    {"from_date": "2026-11-12", "to_date": "2026-11-11"}, {"from_date": "0001-01-01"},
    {"to_date": "not-a-date"}, {"page_size": 0}, {"page_size": 51}, {"cursor": "bad cursor"},
    {"cursor": "x"*181}, {"cursor": base64.urlsafe_b64encode(f"2026-11-11T00:00:00|{RECORD}".encode()).decode()},
])
def test_invalid_filters_and_cursors_fail_cleanly(client, admin_headers, params):
    result = client.get(BASE, headers=admin_headers, params=params)
    assert result.status_code == 422 and result.headers["cache-control"] == "private, no-store"


def test_activity_reads_share_private_lookup_budget(client, admin_headers, monkeypatch):
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(BASE, headers=admin_headers).status_code == 200
    limited = client.get(BASE, headers=admin_headers)
    assert limited.status_code == 429 and limited.headers["cache-control"] == "private, no-store"
    assert limited.headers["retry-after"]
