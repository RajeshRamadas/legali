from datetime import timedelta
import uuid

import pytest
from sqlalchemy import event,func,select

from app import account_summary as summary,config,storage,verification
from app.db import SessionLocal
from app.models import ApiRateBucket,AuditLog,CaseAIConsent,CaseDocumentHold,CustomerAccount,CustomerNotificationPreference,Document,Meeting,Payment,ServiceRequest,utcnow
from test_documents import _upload,local_storage

BASE="/api/v1/account/data-summary"


@pytest.fixture
def case(client,raise_ticket,local_storage,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","");monkeypatch.setattr(config,"ANTHROPIC_API_KEY","")
    return raise_ticket()


def request_row(number):
    with SessionLocal() as db:return db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==number))


def test_owner_only_private_attachment_without_public_download_tokens(client,admin_headers,case,raise_ticket):
    other=raise_ticket(customer_name="OTHER PRIVATE PERSON",contact="9999900001")
    assert client.get(BASE,headers={"Authorization":""}).status_code==401
    denied=client.get(BASE+"/download",headers=admin_headers)
    assert denied.status_code==401 and denied.headers["cache-control"]=="private, no-store"
    result=client.get(BASE+"/download?account_id=another-account&ticket="+other)
    assert result.status_code==200 and [row["ticket_number"] for row in result.json()["requests"]]==[case]
    assert result.headers["cache-control"]=="private, no-store" and result.headers["x-content-type-options"]=="nosniff"
    assert result.headers["content-disposition"]=="attachment; filename=homexo-account-summary.json"
    assert "OTHER PRIVATE PERSON" not in result.text and other not in result.text
    assert set(result.json())=={"format_version","generated_at","scope","counts","sections","excluded","profile","notification_preferences","requests","meetings","payments"}


def test_explicit_fields_exclude_private_content_and_keep_exact_financial_records(client,admin_headers,case):
    now=utcnow();_upload(client,case)
    actor=uuid.UUID(client.get("/api/v1/auth/me",headers=admin_headers).json()["id"])
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==case));account=db.scalar(select(CustomerAccount))
        account.full_name="Synthetic Customer";account.email="customer@example.test"
        ticket.description="PRIVATE case description";ticket.structured_answers={"private_secret":"PRIVATE structured data"}
        db.add(CaseDocumentHold(service_request_id=ticket.id,held=True,revision=1,reason="privacy_review",note="PRIVATE preservation legal review note"))
        db.add(CaseAIConsent(service_request_id=ticket.id,allowed=True,revision=1,processing_revision="old-processor",notice_version="old",notice_snapshot={"PRIVATE":"original processor snapshot"}))
        db.add(CustomerNotificationPreference(account_id=account.id,email=False,sms=True,whatsapp=False,revision=1,updated_at=now))
        db.add(Meeting(service_request_id=ticket.id,lawyer_user_id=actor,title="PRIVATE meeting title",agenda="PRIVATE agenda",meet_link="https://PRIVATE.example.test/join",calendar_event_id="PRIVATE calendar event",starts_at=now,ends_at=now+timedelta(minutes=30)))
        db.add(Payment(service_request_id=ticket.id,provider="test",kind="checkout",amount_paise=10501,currency="INR",status="paid",provider_order_id="PRIVATE order",provider_payment_id="PRIVATE payment",pay_url="https://PRIVATE.example.test/pay",failure_reason="PRIVATE failure",refund_review_reason="PRIVATE review",paid_at=now,refunded_paise=101,refund_pending_paise=20))
        db.add(Document(service_request_id=ticket.id,original_filename="PRIVATE report.pdf",content_type="application/pdf",byte_size=20,storage_key="PRIVATE-report-object",document_category="final_report",scan_status="clean"))
        db.commit()
    preview=client.get(BASE).json()
    assert preview["ready"] and preview["counts"]=={"requests":1,"meetings":1,"payments":1}
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="privacy.account_summary_prepared"))==0
    result=client.get(BASE+"/download");data=result.json()
    assert "PRIVATE" not in result.text and "token_version" not in result.text and "download_url" not in result.text
    assert data["profile"]["name"]=="Synthetic Customer" and data["profile"]["verified_phone"]=="9876543210"
    assert set(data["profile"])=={"name","email","verified_phone","account_created_at","profile_updated_at"}
    assert data["notification_preferences"]["email"] is False
    request=data["requests"][0]
    assert request["document_count"]==1 and request["document_preservation_active"]
    assert request["external_document_ai"]["status"]=="review_required"
    assert set(request)=={"ticket_number","title","service_name","package","status","status_label","created_at","updated_at","document_count","document_preservation_active","external_document_ai"}
    payment=data["payments"][0]
    assert payment["amount_paise"]==10501 and payment["refunded_paise"]==101 and payment["refund_pending_paise"]==20
    assert set(payment)=={"ticket_number","amount_paise","currency","status","created_at","paid_at","refunded_paise","refund_pending_paise"}
    assert set(data["meetings"][0])=={"ticket_number","starts_at","ends_at","status","created_at"}
    with SessionLocal() as db:
        audit=db.scalar(select(AuditLog).where(AuditLog.action=="privacy.account_summary_prepared"))
        assert audit.metadata_=={"format_version":summary.FORMAT_VERSION,"counts":data["counts"]} and audit.actor_user_id is None


def test_empty_account_and_missing_choices_do_not_create_business_records(client,case):
    from conftest import authenticate_customer
    authenticate_customer(client,"9999900002")
    result=client.get(BASE+"/download").json()
    assert result["counts"]=={"requests":0,"meetings":0,"payments":0} and result["requests"]==[]
    assert result["notification_preferences"]["revision"]==0 and result["notification_preferences"]["email"] is True
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CustomerNotificationPreference))==0
        assert db.scalar(select(func.count()).select_from(CaseAIConsent))==0


def test_all_owned_requests_are_included_beyond_legacy_account_page_limit(client,case):
    with SessionLocal() as db:
        original=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==case))
        db.add_all([ServiceRequest(customer_id=original.customer_id,service_type_id=original.service_type_id,ticket_number=f"HX-SUMMARY-{index:04d}",title=f"Synthetic request {index}",description="PRIVATE original submission") for index in range(105)])
        db.commit()
    result=client.get(BASE+"/download")
    assert result.status_code==200 and len(result.json()["requests"])==106 and result.json()["counts"]["requests"]==106


def test_excessive_collection_or_payload_refuses_instead_of_truncating(client,case,monkeypatch):
    monkeypatch.setattr(summary,"LIMITS",{"requests":0,"meetings":2000,"payments":2000})
    assert not client.get(BASE).json()["ready"]
    assert client.get(BASE+"/download").status_code==409
    monkeypatch.setattr(summary,"LIMITS",{"requests":1000,"meetings":2000,"payments":2000})
    monkeypatch.setattr(summary,"MAX_BYTES",10)
    response=client.get(BASE+"/download")
    assert response.status_code==409 and "Privacy requests" in response.json()["detail"]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="privacy.account_summary_prepared"))==0


@pytest.mark.parametrize("table",["meetings","payments"])
def test_child_collection_limit_is_checked_at_download(client,admin_headers,case,monkeypatch,table):
    actor=uuid.UUID(client.get("/api/v1/auth/me",headers=admin_headers).json()["id"])
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==case));now=utcnow()
        if table=="meetings":db.add(Meeting(service_request_id=ticket.id,lawyer_user_id=actor,title="Synthetic meeting",starts_at=now,ends_at=now+timedelta(minutes=30)))
        else:db.add(Payment(service_request_id=ticket.id,provider="test",kind="checkout",amount_paise=100,currency="INR",provider_order_id="synthetic-order"))
        db.commit()
    monkeypatch.setattr(summary,"LIMITS",{**summary.LIMITS,table:0})
    assert client.get(BASE+"/download").status_code==409 and not client.get(BASE).json()["ready"]


def test_download_has_separate_hourly_budget_and_lookup_preview_budget(client,case,monkeypatch):
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_ACCOUNT_SUMMARIES_PER_HOUR",1);monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE).status_code==200 and client.get(BASE).status_code==429
    assert client.get(BASE+"/download").status_code==200
    denied=client.get(BASE+"/download")
    assert denied.status_code==429 and denied.headers["retry-after"] and denied.headers["cache-control"]=="private, no-store"


def test_summary_does_not_open_storage_or_contact_a_provider(client,case,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail("Account summaries do not process source files or contact providers")
    monkeypatch.setattr(storage,"get",forbidden);monkeypatch.setattr(storage,"put",forbidden);monkeypatch.setattr(verification,"model_call",forbidden)
    assert client.get(BASE+"/download").status_code==200


def test_revoked_session_cannot_prepare_download(client,case):
    old=dict(client.headers)
    assert client.post("/api/v1/account/logout-all").status_code==200
    assert client.get(BASE+"/download",headers=old).status_code==401


def test_ownership_is_rechecked_before_serialization(client,case,monkeypatch):
    real=summary.owned;calls=[]
    def changing(account):
        calls.append(True)
        return real(account) if len(calls)==1 else real(account).where(ServiceRequest.ticket_number=="missing")
    monkeypatch.setattr(summary,"owned",changing)
    assert client.get(BASE+"/download").status_code==409


def test_audit_failure_does_not_return_an_unaudited_download(client,case):
    from sqlalchemy.orm import Session
    def reject(session,context,instances):
        if any(isinstance(item,AuditLog) and item.action=="privacy.account_summary_prepared" for item in session.new):raise RuntimeError("Synthetic audit failure")
    event.listen(Session,"before_flush",reject)
    try:
        result=client.get(BASE+"/download")
        assert result.status_code==500 and "content-disposition" not in result.headers
        assert "Synthetic audit failure" not in result.text and "format_version" not in result.text
    finally:event.remove(Session,"before_flush",reject)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="privacy.account_summary_prepared"))==0
