import base64
import json
from datetime import timedelta

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app import config, notification_providers as providers, staff_auth
from app.db import SessionLocal
from app.models import AuditLog, StaffAuthBucket, StaffAuthToken, User
from app.security import create_access_token
from conftest import PASSWORD, authenticate_customer

LOGIN = {"email": "admin@homexo.test", "password": PASSWORD}


@pytest.fixture
def reset_mail(monkeypatch):
    messages = []
    monkeypatch.setattr(providers, "enabled", lambda channel: channel == "email")
    monkeypatch.setattr(providers, "send_staff_reset", lambda email, token, reference: messages.append((email, token, reference)))
    return messages


def _headers(session):
    return {"Authorization": "Bearer " + session["access_token"]}


def _enroll(client, headers):
    setup = client.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=headers)
    assert setup.status_code == 200, setup.text
    code = staff_auth.totp(setup.json()["secret"], int(staff_auth.utcnow().timestamp()) // 30)
    response = client.post("/api/v1/auth/mfa/enable", json={"password": PASSWORD, "code": code}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json(), setup.json()


def _request_reset(client, messages):
    response = client.post("/api/v1/auth/password-reset/request", json={"email": LOGIN["email"]})
    assert response.status_code == 200, response.text
    return messages[-1][1]


def test_totp_matches_rfc6238_sha1_vector():
    assert staff_auth.totp(base64.b32encode(b"12345678901234567890").decode(), 59 // 30) == "287082"


def test_enrollment_encrypts_seed_and_revokes_old_sessions(client, admin_headers):
    session, setup = _enroll(client, admin_headers)
    assert len(session["recovery_codes"]) == 8 and len(set(session["recovery_codes"])) == 8
    assert setup["qr_image"].startswith("data:image/svg+xml;base64,") and "otpauth://totp/" in setup["uri"]
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    response = client.get("/api/v1/auth/security", headers=_headers(session))
    assert response.json() == {"mfa_enabled": True, "mfa_required": False, "recovery_codes_remaining": 8}
    assert response.headers["cache-control"] == "private, no-store"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == LOGIN["email"]))
        assert setup["secret"] not in user.mfa_secret and staff_auth._decrypt(user.mfa_secret) == setup["secret"]
        assert user.mfa_pending_secret is None and user.mfa_pending_until is None
        saved = json.dumps(user.mfa_recovery_hashes)
        assert all(code.replace("-", "") not in saved for code in session["recovery_codes"])
        assert setup["secret"] not in str(db.scalars(select(AuditLog)).all())


def test_mfa_login_has_no_access_until_code_and_challenge_is_single_use(client, admin_headers):
    session, _ = _enroll(client, admin_headers)
    response = client.post("/api/v1/auth/login", json=LOGIN)
    challenge = response.json()["challenge_token"]
    assert "access_token" not in response.json()
    assert client.get("/api/v1/admin/staff", headers={"Authorization": "Bearer " + challenge}).status_code == 401
    assert client.post("/api/v1/auth/login/mfa", json={"token": challenge, "code": "bad"}).status_code == 401
    payload = {"token": challenge, "code": session["recovery_codes"][0]}
    signed = client.post("/api/v1/auth/login/mfa", json=payload)
    assert signed.status_code == 200 and signed.json()["user"]["mfa_enabled"]
    assert client.get("/api/v1/auth/me", headers=_headers(signed.json())).status_code == 200
    assert client.post("/api/v1/auth/login/mfa", json=payload).status_code == 401
    new_challenge = client.post("/api/v1/auth/login", json=LOGIN).json()["challenge_token"]
    assert client.post("/api/v1/auth/login/mfa", json={**payload, "token": new_challenge}).status_code == 401


def test_totp_replay_and_challenge_attempt_limit(client, admin_headers, monkeypatch):
    session, setup = _enroll(client, admin_headers)
    now = staff_auth.utcnow()
    monkeypatch.setattr(staff_auth, "utcnow", lambda: now + timedelta(seconds=30))
    code = staff_auth.totp(setup["secret"], int(staff_auth.utcnow().timestamp()) // 30)
    token = client.post("/api/v1/auth/login", json=LOGIN).json()["challenge_token"]
    assert client.post("/api/v1/auth/login/mfa", json={"token": token, "code": code}).status_code == 200
    token = client.post("/api/v1/auth/login", json=LOGIN).json()["challenge_token"]
    assert client.post("/api/v1/auth/login/mfa", json={"token": token, "code": code}).status_code == 401
    for _ in range(4):
        assert client.post("/api/v1/auth/login/mfa", json={"token": token, "code": "bad"}).status_code == 401
    assert client.post("/api/v1/auth/login/mfa", json={"token": token, "code": session["recovery_codes"][0]}).status_code == 401


def test_required_admin_enrollment_token_cannot_open_workspace(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config, "STAFF_REQUIRE_ADMIN_MFA", True)
    assert client.get("/api/v1/admin/staff", headers=admin_headers).status_code == 401
    result = client.post("/api/v1/auth/login", json=LOGIN).json()
    assert result["mfa_setup_required"] and "access_token" not in result
    headers = {"Authorization": "Bearer " + result["setup_token"]}
    for url in ("/api/v1/auth/me", "/api/v1/admin/staff", "/api/v1/admin/tickets", "/api/v1/auth/security"):
        assert client.get(url, headers=headers).status_code == 401
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 401
    session, _ = _enroll(client, headers)
    assert client.get("/api/v1/admin/staff", headers=_headers(session)).status_code == 200
    assert client.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": session["recovery_codes"][0]}, headers=_headers(session)).status_code == 409
    assert client.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=headers).status_code == 401


def test_pending_setup_requires_password_valid_code_and_expiration(client, admin_headers, monkeypatch):
    assert client.post("/api/v1/auth/mfa/setup", json={"password": "wrong"}, headers=admin_headers).status_code == 400
    setup = client.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=admin_headers).json()
    assert client.post("/api/v1/auth/mfa/enable", json={"password": PASSWORD, "code": "wrong"}, headers=admin_headers).status_code == 400
    now = staff_auth.utcnow()
    monkeypatch.setattr(staff_auth, "utcnow", lambda: now + timedelta(minutes=11))
    code = staff_auth.totp(setup["secret"], int(staff_auth.utcnow().timestamp()) // 30)
    assert client.post("/api/v1/auth/mfa/enable", json={"password": PASSWORD, "code": code}, headers=admin_headers).status_code == 409


def test_production_mfa_requires_separate_encryption_key(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "STAFF_MFA_ENCRYPTION_KEY", "")
    assert client.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=admin_headers).status_code == 503
    monkeypatch.setattr(config, "STAFF_MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert client.post("/api/v1/auth/mfa/setup", json={"password": PASSWORD}, headers=admin_headers).status_code == 200


def test_reset_request_is_generic_and_never_exposes_raw_token(client, admin_headers, reset_mail):
    known = client.post("/api/v1/auth/password-reset/request", json={"email": LOGIN["email"]})
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@example.test"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    assert len(reset_mail) == 1
    token = reset_mail[0][1]
    assert token not in known.text
    with SessionLocal() as db:
        row = db.scalar(select(StaffAuthToken))
        assert row.token_hash != token and row.purpose == "reset"
        assert token not in json.dumps([a.metadata_ for a in db.scalars(select(AuditLog))])


def test_reset_revokes_sessions_invalidates_old_links_and_changes_password(client, admin_headers, reset_mail):
    old = _request_reset(client, reset_mail)
    token = _request_reset(client, reset_mail)
    payload = {"token": old, "password": "a-new-long-password"}
    assert client.post("/api/v1/auth/password-reset/confirm", json=payload).status_code == 401
    payload["token"] = token
    response = client.post("/api/v1/auth/password-reset/confirm", json=payload)
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    assert client.post("/api/v1/auth/password-reset/confirm", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=LOGIN).status_code == 401
    assert client.post("/api/v1/auth/login", json={**LOGIN, "password": payload["password"]}).status_code == 200


def test_reset_cannot_bypass_mfa(client, admin_headers, reset_mail):
    session, _ = _enroll(client, admin_headers)
    token = _request_reset(client, reset_mail)
    payload = {"token": token, "password": "a-new-long-password"}
    assert client.post("/api/v1/auth/password-reset/confirm", json=payload).status_code == 401
    payload["code"] = session["recovery_codes"][0]
    assert client.post("/api/v1/auth/password-reset/confirm", json=payload).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_headers(session)).status_code == 401
    response = client.post("/api/v1/auth/login", json={**LOGIN, "password": payload["password"]})
    assert response.json()["mfa_required"] and "access_token" not in response.json()


def test_expired_reset_and_suspended_account_are_rejected(client, admin_headers, reset_mail):
    token = _request_reset(client, reset_mail)
    with SessionLocal() as db:
        row = db.scalar(select(StaffAuthToken)); row.expires_at = staff_auth.utcnow() - timedelta(seconds=1); db.commit()
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "a-new-long-password"}).status_code == 401
    token = _request_reset(client, reset_mail)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == LOGIN["email"])); user.account_status = "suspended"; db.commit()
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "a-new-long-password"}).status_code == 401


def test_recovery_code_rotation_and_disable_require_both_factors(client, admin_headers):
    session, _ = _enroll(client, admin_headers)
    headers = _headers(session)
    assert client.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD}, headers=headers).status_code == 400
    rotated = client.post("/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD, "code": session["recovery_codes"][0]}, headers=headers)
    assert rotated.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    headers = _headers(rotated.json())
    assert client.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": session["recovery_codes"][1]}, headers=headers).status_code == 400
    result = client.post("/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": rotated.json()["recovery_codes"][0]}, headers=headers)
    assert result.status_code == 200 and not result.json()["user"]["mfa_enabled"]
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert "access_token" in client.post("/api/v1/auth/login", json=LOGIN).json()


def test_change_password_and_logout_all_revoke_tokens(client, admin_headers):
    response = client.post("/api/v1/auth/password/change", json={"password": "wrong", "new_password": "another-long-password"}, headers=admin_headers)
    assert response.status_code == 400
    response = client.post("/api/v1/auth/password/change", json={"password": PASSWORD, "new_password": "another-long-password"}, headers=admin_headers)
    assert response.status_code == 200
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 401
    headers = _headers(response.json())
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_token_audiences_legacy_tokens_and_mfa_claim_cannot_bypass(client, admin_headers):
    authenticate_customer(client)
    assert client.get("/api/v1/auth/me").status_code == 401
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == LOGIN["email"]))
        legacy = jwt.encode({"sub": str(user.id), "exp": staff_auth.utcnow() + timedelta(minutes=1)}, config.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + legacy}).status_code == 401
    session, _ = _enroll(client, admin_headers)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == LOGIN["email"]))
        password_only = create_access_token(user)
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + password_only}).status_code == 401


def test_login_limits_are_persisted_and_return_retry_after(client, admin_headers):
    for _ in range(9):
        assert client.post("/api/v1/auth/login", json={**LOGIN, "password": "wrong"}).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=LOGIN)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    with SessionLocal() as db:
        buckets = db.scalars(select(StaffAuthBucket)).all()
        assert buckets and all(LOGIN["email"] not in b.key and "testclient" not in b.key for b in buckets)


def test_failed_reset_delivery_invalidates_link(client, admin_headers, monkeypatch):
    monkeypatch.setattr(providers, "enabled", lambda channel: True)
    def fail(*args): raise providers.DeliveryError("synthetic_failure")
    monkeypatch.setattr(providers, "send_staff_reset", fail)
    assert client.post("/api/v1/auth/password-reset/request", json={"email": LOGIN["email"]}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(StaffAuthToken)).used_at is not None


def test_staff_status_changes_revoke_tokens_even_after_reactivation(client, admin_headers, agent):
    path = f"/api/v1/admin/staff/{agent['id']}"
    assert client.patch(path, json={"account_status": "suspended"}, headers=admin_headers).status_code == 200
    assert client.patch(path, json={"account_status": "active"}, headers=admin_headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=agent["headers"]).status_code == 401


def test_reset_email_uses_fragment_and_no_notification_storage(monkeypatch):
    messages = []
    def send(url, **kwargs):
        messages.append((url, kwargs)); return httpx.Response(200, json={"id": "synthetic-reference"})
    monkeypatch.setattr(providers.http, "post", send)
    providers.send_staff_reset("staff@example.test", "synthetic-secret-token", "synthetic-id")
    body = messages[0][1]["json"]["text"]
    assert "/admin/reset-password#token=synthetic-secret-token" in body
    assert "?token=" not in body and messages[0][1]["headers"]["Idempotency-Key"].endswith("synthetic-id")


@pytest.mark.skipif(not config.DATABASE_URL.startswith("postgresql"), reason="Requires PostgreSQL row locks")
def test_concurrent_challenges_cannot_reuse_a_recovery_code(client, admin_headers):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    session, _ = _enroll(client, admin_headers)
    tokens = [client.post("/api/v1/auth/login", json=LOGIN).json()["challenge_token"] for _ in range(2)]
    ready = Barrier(2)
    def confirm(token):
        ready.wait(timeout=10)
        return client.post("/api/v1/auth/login/mfa", json={"token": token, "code": session["recovery_codes"][0]}).status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(confirm, tokens)) == [200, 401]


@pytest.mark.skipif(not config.DATABASE_URL.startswith("postgresql"), reason="Requires independent PostgreSQL transactions")
def test_rate_limit_is_atomic_across_workers(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    now = staff_auth.utcnow()
    monkeypatch.setattr(staff_auth, "utcnow", lambda: now)
    ready = Barrier(6)
    def attempt(_):
        ready.wait(timeout=10)
        with SessionLocal() as db:
            try:
                staff_auth.throttle(db, "concurrent-test", "synthetic-client", 2)
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=6) as workers:
        assert sorted(workers.map(attempt, range(6))) == [200, 200, 429, 429, 429, 429]
