from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Event
import uuid

import jwt
import pytest
from sqlalchemy import event, func, select, update

from app import config, security, staff_session_records
from app.db import SessionLocal, engine
from app.models import AuditLog, StaffSession, User, utcnow
from conftest import PASSWORD, authenticate_customer
from test_documents import _upload, local_storage

BASE = "/api/v1/auth/sessions"
LOGIN = {"email": "admin@homexo.test", "password": PASSWORD}


def login(client):
    response = client.post("/api/v1/auth/login", json=LOGIN, headers={"user-agent": "PRIVATE raw marker Chrome/121 Windows"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def claims(headers):
    return jwt.decode(headers["Authorization"].split()[1], config.JWT_SECRET, algorithms=["HS256"], audience="homexo-staff")


def key(headers):
    return uuid.UUID(claims(headers)["jti"])


def test_unique_staff_sessions_safe_hints_and_no_customer_or_agent_crossover(client, admin_headers, agent):
    second = login(client)
    assert key(second) != key(admin_headers)
    response = client.get(BASE, headers=second)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    item = next(row for row in response.json()["items"] if row["is_current"])
    assert item["browser"] == "Chrome" and item["device"] == "Windows"
    assert set(item) == {"id", "browser", "device", "created_at", "last_seen_at", "expires_at", "is_current"}
    assert "PRIVATE" not in response.text and second["Authorization"].split()[1] not in response.text
    assert len(client.get(BASE, headers=agent["headers"]).json()["items"]) == 1
    assert client.post(f"{BASE}/{key(second)}/revoke", headers=agent["headers"]).status_code == 404
    assert client.post(f"{BASE}/{key(agent['headers'])}/revoke", headers=second).status_code == 404
    customer = authenticate_customer(client)
    assert client.get(BASE, headers=customer).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=customer).status_code == 401


def test_individual_revocation_is_idempotent_and_blocks_private_file_access(client, admin_headers, raise_ticket, local_storage):
    number = raise_ticket()
    document = _upload(client, number).json()["documents"][0]
    second = login(client)
    assert client.get(document["download_url"], headers=admin_headers).status_code == 200
    assert client.post(f"{BASE}/{key(admin_headers)}/revoke", headers=second).json() == {"revoked": True, "current": False}
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    assert client.get(document["download_url"], headers=admin_headers).status_code == 401
    assert client.get(document["download_url"], headers=second).status_code == 200
    assert client.post(f"{BASE}/{key(admin_headers)}/revoke", headers=second).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "staff.session_revoked")) == 1


def test_other_current_and_global_sign_out(client, admin_headers):
    second = login(client)
    third = login(client)
    assert client.post(BASE + "/revoke-others", headers=second).json() == {"revoked": 2}
    assert client.get(BASE, headers=admin_headers).status_code == 401
    assert client.get(BASE, headers=third).status_code == 401
    assert len(client.get(BASE, headers=second).json()["items"]) == 1
    assert client.post(BASE + "/revoke-others", headers=second).json() == {"revoked": 0}
    assert client.post("/api/v1/auth/logout", headers=second).json() == {"revoked": True, "current": True}
    assert client.get(BASE, headers=second).status_code == 401
    fourth = login(client)
    assert client.post("/api/v1/auth/logout-all", headers=fourth).status_code == 200
    assert client.get(BASE, headers=fourth).status_code == 401
    with SessionLocal() as db:
        assert all(row.revoked_at is not None for row in db.scalars(select(StaffSession)))


@pytest.mark.parametrize("change", ["legacy", "unknown", "other_staff", "malformed", "wrong_version_type", "wrong_factor_type", "expired_record"])
def test_invalid_session_cannot_authorize(client, admin_headers, agent, change):
    payload = claims(admin_headers)
    if change == "legacy": payload.pop("jti")
    if change == "unknown": payload["jti"] = str(uuid.uuid4())
    if change == "other_staff": payload["jti"] = str(key(agent["headers"]))
    if change == "malformed": payload["jti"] = "not-a-session"
    if change == "wrong_version_type": payload["ver"] = True
    if change == "wrong_factor_type": payload["mfa"] = 1
    if change == "expired_record":
        with SessionLocal() as db:
            row = db.get(StaffSession, key(admin_headers))
            row.created_at = utcnow() - timedelta(days=2)
            row.expires_at = utcnow() - timedelta(days=1)
            db.commit()
    headers = {"Authorization": "Bearer " + jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")}
    assert client.get(BASE, headers=headers).status_code == 401


def test_last_seen_is_throttled_and_does_not_extend_expiry(client, admin_headers):
    with SessionLocal() as db:
        row = db.get(StaffSession, key(admin_headers))
        expires = row.expires_at
        row.last_seen_at = utcnow() - timedelta(minutes=10)
        db.commit()
    assert client.get(BASE, headers=admin_headers).status_code == 200
    with SessionLocal() as db:
        row = db.get(StaffSession, key(admin_headers))
        seen = row.last_seen_at
        assert security.aware(seen) > utcnow() - timedelta(minutes=1) and row.expires_at == expires
    assert client.get(BASE, headers=admin_headers).status_code == 200
    with SessionLocal() as db:
        assert db.get(StaffSession, key(admin_headers)).last_seen_at == seen


def test_active_session_limit_does_not_touch_another_staff_member(client, admin_headers, agent, monkeypatch):
    monkeypatch.setattr(staff_session_records, "MAX_ACTIVE_SESSIONS", 2)
    with SessionLocal() as db:
        db.get(StaffSession, key(admin_headers)).created_at = utcnow() - timedelta(minutes=10)
        db.commit()
    second, third = login(client), login(client)
    assert client.get(BASE, headers=admin_headers).status_code == 401
    assert all(client.get(BASE, headers=value).status_code == 200 for value in (second, third, agent["headers"]))
    with SessionLocal() as db:
        assert db.get(StaffSession, key(admin_headers)).revoke_reason == "session_limit"


def test_mfa_challenge_and_setup_tokens_never_get_active_session_access(client, admin_headers, monkeypatch):
    from test_staff_security import _enroll, _headers
    session, _ = _enroll(client, admin_headers)
    with SessionLocal() as db: before = db.scalar(select(func.count()).select_from(StaffSession))
    challenge = client.post("/api/v1/auth/login", json=LOGIN).json()["challenge_token"]
    assert client.get(BASE, headers={"Authorization": "Bearer " + challenge}).status_code == 401
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(StaffSession)) == before
    assert len(client.get(BASE, headers=_headers(session)).json()["items"]) == 1
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == LOGIN["email"]))
        user.mfa_secret = None
        db.commit()
    monkeypatch.setattr(config, "STAFF_REQUIRE_ADMIN_MFA", True)
    setup = client.post("/api/v1/auth/login", json=LOGIN).json()["setup_token"]
    assert client.get(BASE, headers={"Authorization": "Bearer " + setup}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer " + setup}).status_code == 401
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(StaffSession)) == before


def test_security_change_and_session_issuance_roll_back_on_audit_failure(client, admin_headers):
    from sqlalchemy.orm import Session
    def reject(session, context, instances):
        if any(isinstance(row, AuditLog) and row.action == "staff.password_changed" for row in session.new):
            raise RuntimeError("Synthetic audit failure")
    event.listen(Session, "before_flush", reject)
    try:
        assert client.post("/api/v1/auth/password/change", headers=admin_headers,
            json={"password": PASSWORD, "new_password": "another-synthetic-password"}).status_code == 500
    finally: event.remove(Session, "before_flush", reject)
    assert client.get(BASE, headers=admin_headers).status_code == 200
    assert client.get(BASE, headers=login(client)).status_code == 200
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(StaffSession)) == 2


def test_revocation_audit_failure_preserves_session(client, admin_headers):
    from sqlalchemy.orm import Session
    second = login(client)
    def reject(session, context, instances):
        if any(isinstance(row, AuditLog) and row.action == "staff.session_revoked" for row in session.new):
            raise RuntimeError("Synthetic audit failure")
    event.listen(Session, "before_flush", reject)
    try: assert client.post(f"{BASE}/{key(second)}/revoke", headers=admin_headers).status_code == 500
    finally: event.remove(Session, "before_flush", reject)
    assert client.get(BASE, headers=second).status_code == 200


def test_session_revocations_share_the_existing_security_throttle(client, admin_headers):
    from app.staff_auth import _hash
    from app.models import StaffAuthBucket
    payload = claims(admin_headers)
    now = utcnow()
    with SessionLocal() as db:
        db.add(StaffAuthBucket(key=_hash("rate", f"security:{payload['sub']}"), window_start=now, attempts=20))
        db.commit()
    response = client.post("/api/v1/auth/logout", headers=admin_headers)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert client.get(BASE, headers=admin_headers).status_code == 200


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Real PostgreSQL user locks")
def test_sign_in_waits_for_global_revocation_and_uses_new_version(client, admin_headers):
    user_id = uuid.UUID(claims(admin_headers)["sub"])
    waiting = Event()
    def attempting(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "users" in statement: waiting.set()
    with SessionLocal() as locked, ThreadPoolExecutor(max_workers=1) as pool:
        user = locked.scalar(select(User).where(User.id == user_id).with_for_update())
        user.token_version += 1
        staff_session_records.invalidate_sessions(locked, user, "all_sessions")
        locked.flush()
        event.listen(engine, "before_cursor_execute", attempting)
        try:
            future = pool.submit(login, client)
            assert waiting.wait(5)
            with pytest.raises(TimeoutError): future.result(timeout=0.2)
        finally:
            event.remove(engine, "before_cursor_execute", attempting)
            locked.commit()
        fresh = future.result(timeout=10)
    assert claims(fresh)["ver"] == claims(admin_headers)["ver"] + 1
    assert client.get(BASE, headers=admin_headers).status_code == 401
    assert client.get(BASE, headers=fresh).status_code == 200
