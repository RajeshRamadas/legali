from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
import uuid

import jwt
import pytest
from sqlalchemy import event,func,select,update

from app import config,customer_auth as auth
from app.db import SessionLocal,engine
from app.models import ApiRateBucket,AuditLog,CustomerAccount,CustomerSession,utcnow
from conftest import authenticate_customer
from test_documents import _upload,local_storage

BASE="/api/v1/account/sessions"


def claims(headers):return jwt.decode((headers.get("Authorization") or headers["authorization"]).split()[1],config.JWT_SECRET,algorithms=["HS256"],audience="homexo-customer")


def key(headers):return uuid.UUID(claims(headers)["jti"])


def test_login_creates_unique_revocable_sessions_and_safe_device_hints(client,monkeypatch):
    monkeypatch.setattr(config,"LOGIN_CODE_DEV_MODE",True)
    result=client.post("/api/v1/account/login/start",json={"phone":"9876543210"}).json()
    login=client.post("/api/v1/account/login/verify",headers={"user-agent":"PRIVATE raw browser marker Chrome/121 Linux"},json={"phone":"9876543210","code":result["dev_code"]})
    assert login.status_code==200
    first={"Authorization":"Bearer "+login.json()["access_token"]}
    second=authenticate_customer(client)
    assert key(first)!=key(second)
    response=client.get(BASE,headers=first)
    assert response.status_code==200 and response.headers["cache-control"]=="private, no-store"
    item=next(item for item in response.json()["items"] if item["is_current"])
    assert item["browser"]=="Chrome" and item["device"]=="Linux"
    assert set(item)=={"id","browser","device","created_at","last_seen_at","expires_at","is_current"}
    assert "PRIVATE" not in response.text and login.json()["access_token"] not in response.text


def test_revoke_one_session_leaves_other_session_active_and_denies_file_access(client,raise_ticket,local_storage):
    number=raise_ticket();first=dict(client.headers)
    document=_upload(client,number).json()["documents"][0]
    second=authenticate_customer(client)
    result=client.post(f"{BASE}/{key(first)}/revoke",headers=second)
    assert result.json()=={"revoked":True,"current":False}
    assert client.get("/api/v1/account",headers=first).status_code==401
    assert client.get(document["download_url"],headers=first).status_code==401
    assert client.get(document["download_url"],headers=second).status_code==200
    assert client.get("/api/v1/account/data-summary/download",headers=first).status_code==401
    assert client.post(f"{BASE}/{key(first)}/revoke",headers=second).json()["revoked"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="customer.session_revoked"))==1


def test_revoke_others_keeps_caller_and_global_logout_revokes_every_token(client):
    first=authenticate_customer(client);second=authenticate_customer(client);third=authenticate_customer(client)
    result=client.post(BASE+"/revoke-others",headers=second)
    assert result.json()=={"revoked":2}
    assert client.get(BASE,headers=first).status_code==401 and client.get(BASE,headers=third).status_code==401
    assert len(client.get(BASE,headers=second).json()["items"])==1
    assert client.post(BASE+"/revoke-others",headers=second).json()=={"revoked":0}
    assert client.post("/api/v1/account/logout-all",headers=second).status_code==200
    assert client.get(BASE,headers=second).status_code==401
    with SessionLocal() as db:assert all(row.revoked_at is not None for row in db.scalars(select(CustomerSession)))


def test_current_logout_is_server_side_and_owner_scoped(client,admin_headers):
    first=authenticate_customer(client);second=authenticate_customer(client,"9999900001")
    assert client.post(f"{BASE}/{key(first)}/revoke",headers=second).status_code==404
    assert client.get(BASE,headers=admin_headers).status_code==401
    assert client.post("/api/v1/account/logout",headers=first).json()=={"revoked":True,"current":True}
    assert client.get(BASE,headers=first).status_code==401
    assert client.get(BASE,headers=second).status_code==200


@pytest.mark.parametrize("change",["legacy","unknown","other_account","malformed","wrong_version_type","expired_record"])
def test_legacy_or_invalid_session_records_never_become_authorized(client,change):
    first=authenticate_customer(client);data=claims(first)
    if change=="legacy":data.pop("jti")
    if change=="unknown":data["jti"]=str(uuid.uuid4())
    if change=="other_account":data["jti"]=str(key(authenticate_customer(client,"9999900001")))
    if change=="malformed":data["jti"]="bad-reference"
    if change=="wrong_version_type":data["ver"]=True
    if change=="expired_record":
        with SessionLocal() as db:
            row=db.get(CustomerSession,key(first));row.created_at=utcnow()-timedelta(days=2);row.expires_at=utcnow()-timedelta(days=1);db.commit()
    invalid={"Authorization":"Bearer "+jwt.encode(data,config.JWT_SECRET,algorithm="HS256")}
    assert client.get(BASE,headers=invalid).status_code==401


def test_last_activity_is_throttled_without_extending_expiration(client):
    headers=authenticate_customer(client)
    with SessionLocal() as db:
        row=db.get(CustomerSession,key(headers));expires=row.expires_at;row.last_seen_at=utcnow()-timedelta(minutes=10);db.commit()
    assert client.get(BASE,headers=headers).status_code==200
    with SessionLocal() as db:
        row=db.get(CustomerSession,key(headers));seen=row.last_seen_at
        assert auth.aware(seen)>utcnow()-timedelta(minutes=1) and row.expires_at==expires
    assert client.get(BASE,headers=headers).status_code==200
    with SessionLocal() as db:assert db.get(CustomerSession,key(headers)).last_seen_at==seen


def test_session_limit_ends_the_oldest_record_without_touching_another_account(client,monkeypatch):
    monkeypatch.setattr(auth,"MAX_ACTIVE_SESSIONS",2)
    first=authenticate_customer(client)
    with SessionLocal() as db:
        db.get(CustomerSession,key(first)).created_at=utcnow()-timedelta(minutes=10);db.commit()
    other=authenticate_customer(client,"9999900001")
    second=authenticate_customer(client);third=authenticate_customer(client)
    assert client.get(BASE,headers=first).status_code==401
    assert all(client.get(BASE,headers=value).status_code==200 for value in (second,third,other))
    with SessionLocal() as db:assert db.get(CustomerSession,key(first)).revoke_reason=="session_limit"


def test_reads_and_revocations_use_shared_budgets(client,monkeypatch):
    first=authenticate_customer(client);second=authenticate_customer(client)
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE,headers=first).status_code==200
    assert client.get(BASE,headers=first).status_code==429
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    assert client.post(f"{BASE}/{key(second)}/revoke",headers=first).status_code==200
    assert client.post(BASE+"/revoke-others",headers=first).status_code==429


def test_revocation_audit_failure_rolls_back_the_security_change(client):
    from sqlalchemy.orm import Session
    first=authenticate_customer(client);second=authenticate_customer(client)
    def reject(session,context,instances):
        if any(isinstance(row,AuditLog) and row.action=="customer.session_revoked" for row in session.new):raise RuntimeError("Synthetic audit failure")
    event.listen(Session,"before_flush",reject)
    try:assert client.post(f"{BASE}/{key(second)}/revoke",headers=first).status_code==500
    finally:event.remove(Session,"before_flush",reject)
    assert client.get(BASE,headers=second).status_code==200


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real PostgreSQL account-lock concurrency")
def test_new_sign_in_waits_for_global_revocation_and_uses_the_new_version(client):
    first=authenticate_customer(client);account_id=uuid.UUID(claims(first)["sub"]);locked=Event();release=Event()
    with SessionLocal() as db:account=db.get(CustomerAccount,account_id)
    def revoke():
        with SessionLocal() as db:
            row=db.scalar(select(CustomerAccount).where(CustomerAccount.id==account_id).with_for_update())
            row.token_version+=1;db.execute(update(CustomerSession).where(CustomerSession.account_id==account_id).values(revoked_at=utcnow(),revoke_reason="all_sessions"));db.flush()
            locked.set();assert release.wait(10);db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        old=pool.submit(revoke)
        try:
            assert locked.wait(5);new=pool.submit(auth.create_session_token,account)
        finally:release.set()
        old.result(timeout=10);token=new.result(timeout=10)
    assert client.get(BASE,headers=first).status_code==401
    assert client.get(BASE,headers={"Authorization":"Bearer "+token}).status_code==200
