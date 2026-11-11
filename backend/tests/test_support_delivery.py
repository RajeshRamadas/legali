"""Read-only support delivery metadata must never expose recipient/provider/message data."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select

from app import config
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, AuditLog, CustomerAccount, Notification, SupportDeadlineAlert, SupportRequest, User, utcnow
from conftest import authenticate_customer
from test_support import BASE, ADMIN, create


def setup(client):
    authenticate_customer(client)
    item = create(client, subject="PRIVATE support subject", details="PRIVATE customer concern in the portal")
    with SessionLocal() as db:
        account = db.get(SupportRequest, uuid.UUID(item["id"])).account_id
    return item, account


def notice(db, item, account, **changes):
    row = Notification(account_id=account, support_request_id=uuid.UUID(item["id"]), support_update_revision=1,
        template_key="support_reply", channel="email", recipient="PRIVATE-recipient@example.invalid", body="PRIVATE notification body",
        params=["PRIVATE params"], provider_reference="PRIVATE provider reference", claim_token=uuid.uuid4(),
        dedupe_key="PRIVATE-dedupe-"+uuid.uuid4().hex, **changes)
    db.add(row)
    return row


def history(client, headers, item, **params):
    result = client.get(f"{ADMIN}/{item['id']}/deliveries", headers=headers, params=params)
    assert result.status_code == 200, result.text
    return result


def test_authorization_unknown_request_validation_and_private_cache(client, admin_headers, agent):
    item, _ = setup(client); path=f"{ADMIN}/{item['id']}/deliveries"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=agent["headers"]).status_code == 403
    result = history(client, admin_headers, item)
    assert result.json()["items"] == [] and result.headers["cache-control"] == "private, no-store"
    assert client.get(f"{BASE}/{item['id']}/deliveries").status_code in (404,405)
    assert client.get(f"{ADMIN}/{uuid.uuid4()}/deliveries", headers=admin_headers).status_code == 404
    for params in ({"page":0},{"page_size":101},{"recipient":"agent"},{"channel":"in_app"},{"status":"unknown"}):
        assert client.get(path, headers=admin_headers, params=params).status_code == 422


def test_only_exact_conversation_and_owner_scope_is_returned_with_a_safe_field_allowlist(client, admin_headers):
    item, account = setup(client)
    with SessionLocal() as db:
        outsider=CustomerAccount(phone_normalized="9999900002"); db.add(outsider); db.flush()
        other=SupportRequest(account_id=outsider.id, submission_key=uuid.uuid4(), kind="other", subject="PRIVATE other", details="PRIVATE other account")
        db.add(other); db.flush()
        alert=SupportDeadlineAlert(support_request_id=uuid.UUID(item["id"]), target_at=utcnow()-timedelta(hours=1), revision=2)
        other_alert=SupportDeadlineAlert(support_request_id=other.id, target_at=utcnow()-timedelta(hours=1))
        db.add_all([alert,other_alert]); db.flush()
        own=notice(db,item,account,error_code="PRIVATE legacy provider error",delivery_status="failed")
        notice(db,item,outsider.id)  # Corrupt account/request linkage must fail closed on read.
        notice(db,{"id":str(other.id)},outsider.id)
        user=db.scalar(select(User).where(User.email=="admin@homexo.test"))
        staff=Notification(user_id=user.id,support_alert_id=alert.id,support_alert_revision=2,template_key="support_deadline_email",channel="email",recipient="PRIVATE staff email",params=["escalated"],body="PRIVATE staff details")
        db.add_all([staff, Notification(support_alert_id=other_alert.id,support_alert_revision=1,template_key="support_deadline_email",channel="email"),
            Notification(template_key="staff_message",channel="email",body="PRIVATE case history")])
        db.commit(); expected={str(own.id),str(staff.id)}
    result=history(client,admin_headers,item).json()
    assert {row["id"] for row in result["items"]}==expected and result["total"]==2
    for row in result["items"]:
        assert set(row)=={"id","event","recipient_kind","recipient_name","channel","status","attempts","created_at","last_attempt_at","scheduled_for","delivered_at","reason"}
    assert "PRIVATE" not in str(result) and "recipient@" not in str(result)
    assert next(row for row in result["items"] if row["event"]=="customer_reply")["reason"]=="Delivery issue; review provider records"
    assert next(row for row in result["items"] if row["event"]=="support_escalation")["recipient_name"]=="Meera Admin"


def test_filters_paging_and_tied_dates_are_stable_without_mutating_records(client, admin_headers):
    item, account=setup(client); now=utcnow()
    with SessionLocal() as db:
        rows=[notice(db,item,account,delivery_status=status,created_at=now,attempts=i) for i,status in enumerate(("queued","sent","delivered","failed","cancelled"))]
        db.commit(); expected=sorted((str(row.id) for row in rows),reverse=True)
        before=db.get(SupportRequest,uuid.UUID(item["id"]))
        saved=(before.revision,before.customer_read_revision,before.customer_update_revision,before.updated_at)
        audits=db.scalar(select(func.count()).select_from(AuditLog))
    combined=[]
    for page in (1,2,3):
        result=history(client,admin_headers,item,page=page,page_size=2).json()
        assert result["total"]==5 and result["page"]==page and result["page_size"]==2
        combined.extend(row["id"] for row in result["items"])
    assert combined==expected
    assert history(client,admin_headers,item,status="failed").json()["total"]==1
    assert history(client,admin_headers,item,recipient="administrator").json()["total"]==0
    assert history(client,admin_headers,item,channel="sms").json()["total"]==0
    assert history(client,admin_headers,item,page=10).json()["items"]==[]
    with SessionLocal() as db:
        current=db.get(SupportRequest,uuid.UUID(item["id"]))
        assert (current.revision,current.customer_read_revision,current.customer_update_revision,current.updated_at)==saved
        assert db.scalar(select(func.count()).select_from(AuditLog))==audits
        assert all(row.claim_token and row.provider_reference=="PRIVATE provider reference" for row in db.scalars(select(Notification)))


def test_cancellation_reasons_and_configuration_are_safe_current_metadata(client, admin_headers, monkeypatch):
    item, account=setup(client)
    with SessionLocal() as db:
        notice(db,item,account,delivery_status="cancelled",error_code="support_reply_read")
        notice(db,item,account,delivery_status="failed",error_code="provider_outcome_unknown")
        db.commit()
    monkeypatch.setattr(config,"SUPPORT_REPLY_NOTIFICATIONS_ENABLED",False)
    monkeypatch.setattr(config,"SUPPORT_DEADLINE_EMAIL_ENABLED",False)
    result=history(client,admin_headers,item).json()
    assert {row["reason"] for row in result["items"]}=={"Reply already read","Provider outcome uncertain; review before retrying"}
    assert not result["configuration"]["customer_replies_enabled"] and result["configuration"]["staff_email"]=="disabled"
    assert set(result["configuration"]["channels"])=={"email","sms","whatsapp"}
    assert all(type(value) is bool for value in result["configuration"]["channels"].values())


def test_history_reads_use_shared_lookup_budget_and_cannot_retry_deliveries(client, admin_headers, monkeypatch):
    item,_=setup(client); path=f"{ADMIN}/{item['id']}/deliveries"
    assert client.post(path,headers=admin_headers).status_code==405
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(path,headers=admin_headers).status_code==200
    limited=client.get(path,headers=admin_headers)
    assert limited.status_code==429 and limited.headers["retry-after"]


def test_staff_name_join_does_not_add_queries_per_delivery_row(client, admin_headers):
    item,_=setup(client)
    alert_id=uuid.uuid4()
    with SessionLocal() as db:
        db.add(SupportDeadlineAlert(id=alert_id,support_request_id=uuid.UUID(item["id"]),target_at=utcnow()-timedelta(hours=1))); db.commit()
    def add_staff(count):
        with SessionLocal() as db:
            for _ in range(count):
                user_id=uuid.uuid4()
                db.add(User(id=user_id,display_name="Historical administrator",password_hash="unused-fixture"))
                db.flush()  # Persist each parent before the FK-only notification object.
                db.add(Notification(user_id=user_id,support_alert_id=alert_id,support_alert_revision=1,template_key="support_deadline_email",channel="email"))
            db.commit()
    add_staff(1)
    queries=[]
    def count(*args): queries.append(1)
    event.listen(engine,"before_cursor_execute",count)
    try:
        history(client,admin_headers,item); small=len(queries)
        add_staff(30)
        queries.clear();history(client,admin_headers,item,page_size=100); large=len(queries)
        assert large <= small+2
    finally: event.remove(engine,"before_cursor_execute",count)
