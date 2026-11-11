from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app import ai_processing as ai, config, document_reader, upload_check, verification, verification_jobs as jobs
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, AuditLog, CaseAIConsent, ServiceRequest, VerificationJob, VerificationRun, VerificationUsage
from conftest import authenticate_customer
from test_upload_check import ec_result
from test_verification import approve, local, upload
from test_verification_jobs import base, queued


def endpoint(number):return f"/api/v1/account/requests/{number}/ai-processing"


def withdraw(client,number):
    current=client.get(endpoint(number)).json()
    return client.put(endpoint(number),json={"allowed":False,"revision":current["revision"]})


@pytest.fixture
def case(client,raise_ticket):
    number=raise_ticket();upload(client,number);return number


def test_default_denies_external_processing_without_affecting_local_analysis(client,admin_headers,case,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    monkeypatch.setattr(verification,"model_call",lambda *args,**kwargs:pytest.fail("No case AI grant"))
    value=client.get(endpoint(case))
    assert value.status_code==200 and value.headers["cache-control"]=="private, no-store"
    assert value.json()["status"]=="not_allowed" and value.json()["revision"]==0
    assert client.post(f"/api/v1/admin/tickets/{case}/verification",headers=admin_headers,json={"state":"Karnataka","use_llm":True,"consent_to_external_processing":True}).status_code==409
    assert client.post(f"/api/v1/admin/tickets/{case}/verification",headers=admin_headers,json={"state":"Karnataka"}).status_code==201
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CaseAIConsent))==0


def test_choices_are_case_scoped_owned_private_and_customer_controlled(client,admin_headers,agent,case,raise_ticket):
    value=approve(client,case)
    assert value["allowed"] and value["revision"]==1
    other=raise_ticket()
    assert client.get(endpoint(other)).json()["allowed"] is False
    assert client.get(endpoint(case),headers={"Authorization":""}).status_code==401
    assert client.put(endpoint(case),headers=admin_headers,json={"allowed":False,"revision":1}).status_code==401
    staff=f"/api/v1/admin/tickets/{case}/ai-processing"
    assert client.get(staff,headers={"Authorization":""}).headers["cache-control"]=="private, no-store"
    assert client.get(staff,headers=agent["headers"]).status_code==404
    assert client.get(staff,headers=admin_headers).json()["allowed"]
    original=dict(client.headers);authenticate_customer(client,"9999900001")
    assert client.get(endpoint(case)).status_code==404
    assert client.put(endpoint(case),json={"allowed":False,"revision":1}).status_code==404
    client.headers.clear();client.headers.update(original)


def test_explicit_notice_binding_optimistic_revision_and_retained_audit(client,case):
    current=client.get(endpoint(case)).json();notice=current["disclosure"]
    payload={"allowed":True,"revision":0,"notice_version":notice["notice_version"],"processing_revision":notice["processing_revision"]}
    assert client.put(endpoint(case),json={**payload,"notice_version":"old"}).status_code==409
    assert client.put(endpoint(case),json=payload).status_code==200
    assert client.put(endpoint(case),json=payload).status_code==409
    assert withdraw(client,case).json()["status"]=="withdrawn"
    assert client.put(endpoint(case),json={**payload,"revision":1}).status_code==409
    with SessionLocal() as db:
        events=db.scalars(select(AuditLog).where(AuditLog.action.in_(("case.ai_processing_allowed","case.ai_processing_withdrawn"))).order_by(AuditLog.created_at)).all()
        assert len(events)==2 and events[0].metadata_["notice"]["paragraphs"]==ai.NOTICE
        row=db.scalar(select(CaseAIConsent))
        assert not row.allowed and row.revision==2 and row.notice_snapshot["processor"]=="Synthetic AI processor"


@pytest.mark.parametrize("change",["processor","privacy","endpoint","invalid"])
def test_processor_changes_require_fresh_customer_review_but_never_block_withdrawal(client,case,monkeypatch,change):
    approve(client,case)
    if change=="processor":monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_NAME","Another synthetic processor")
    if change=="privacy":monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_PRIVACY_URL","https://privacy.example.test/new-policy")
    if change=="endpoint":monkeypatch.setattr(config,"VERIFICATION_LLM_PROVIDER","openai")
    if change=="invalid":monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_NAME","")
    current=client.get(endpoint(case)).json()
    assert current["status"]=="review_required" and not current["allowed"] and current["can_withdraw"]
    with SessionLocal() as db:
        row=db.scalar(select(CaseAIConsent))
        with pytest.raises(ai.ApprovalRequired):ai.approved(db,row.service_request_id)
    assert withdraw(client,case).json()["status"]=="withdrawn"


def test_key_rotation_models_and_rates_do_not_change_the_processor_notice(client,case,monkeypatch):
    current=approve(client,case)
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","PRIVATE rotated key")
    monkeypatch.setattr(config,"VERIFICATION_EXTRACT_MODEL","another-model")
    monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES","not-configured")
    after=client.get(endpoint(case))
    assert after.json()["allowed"] and after.json()["disclosure"]["processing_revision"]==current["disclosure"]["processing_revision"]
    assert "PRIVATE" not in after.text


@pytest.mark.parametrize("url",["http://privacy.example.test","https://person:PRIVATE@privacy.example.test","https://privacy.example.test:bad/policy","https://[invalid/policy"])
def test_invalid_processor_policy_is_not_exposed_or_accepted(client,case,monkeypatch,url):
    monkeypatch.setattr(config,"VERIFICATION_PROCESSOR_PRIVACY_URL",url)
    value=client.get(endpoint(case)).json()
    assert not value["disclosure"]["configured"] and value["disclosure"]["processor"] is None and value["disclosure"]["privacy_url"] is None
    assert client.put(endpoint(case),json={"allowed":True,"revision":0}).status_code==409


def test_malformed_gateway_cannot_reuse_a_valid_processor_label(client,case,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_PROVIDER","openai")
    monkeypatch.setattr(config,"VERIFICATION_LLM_BASE_URL","https://[PRIVATE malformed endpoint")
    value=client.get(endpoint(case))
    assert not value.json()["disclosure"]["configured"] and "PRIVATE" not in value.text


@pytest.mark.parametrize("changes",[{"allowed":"true"},{"revision":True},{"revision":-1},{"unexpected":True},{"allowed":1}])
def test_choice_payload_is_strict(client,case,changes):
    assert client.put(endpoint(case),json={"allowed":False,"revision":0,**changes}).status_code==422


def test_reads_and_writes_share_budgets(client,case,monkeypatch):
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(endpoint(case)).status_code==200
    assert client.get(endpoint(case)).status_code==429
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    assert client.put(endpoint(case),json={"allowed":False,"revision":0}).status_code==200
    assert client.put(endpoint(case),json={"allowed":False,"revision":1}).status_code==429


def test_upload_check_waits_for_permission_and_grant_does_not_replay_old_files(client,admin_headers,case,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    calls=[]
    monkeypatch.setattr(verification,"model_call",lambda *args,**kwargs:calls.append(kwargs) or ec_result())
    upload(client,case)
    documents=client.get(f"/api/v1/account/requests/{case}").json()["documents"]
    assert all(doc["check"]["status"]=="awaiting_consent" for doc in documents) and not calls
    approve(client,case);assert not calls
    document=documents[0]["id"]
    assert client.post(f"/api/v1/admin/tickets/{case}/documents/{document}/check",headers=admin_headers).status_code==200 and len(calls)==1
    withdraw(client,case)
    assert client.post(f"/api/v1/admin/tickets/{case}/documents/{document}/check",headers=admin_headers).status_code==409 and len(calls)==1


def test_withdrawal_during_upload_check_discards_late_result(client,case,monkeypatch):
    approve(client,case);monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    def call(*args,**kwargs):
        assert withdraw(client,case).status_code==200
        return ec_result()
    monkeypatch.setattr(verification,"model_call",call)
    upload(client,case)
    assert all(doc["check"]["status"]=="awaiting_consent" for doc in client.get(f"/api/v1/account/requests/{case}").json()["documents"])


def test_regrant_does_not_resurrect_a_queued_job_under_old_permission(client,admin_headers,case,monkeypatch):
    approve(client,case);monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    value=queued(client,admin_headers,case,use_llm=True,consent_to_external_processing=True,configuration_revision=jobs.configuration(True))
    withdraw(client,case);approve(client,case)
    monkeypatch.setattr(verification,"model_call",lambda *args,**kwargs:pytest.fail("Old job permission must not be reused"))
    jobs.process_one()
    with SessionLocal() as db:
        row=db.get(VerificationJob,uuid.UUID(value["id"]))
        assert row.status=="cancelled" and row.reason_code=="consent_changed" and row.run_id is None


def test_background_withdrawal_keeps_incurred_usage_but_publishes_no_result(client,admin_headers,case,monkeypatch):
    approve(client,case);monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    value=queued(client,admin_headers,case,use_llm=True,consent_to_external_processing=True,configuration_revision=jobs.configuration(True))
    real=httpx.Client;calls=[]
    def handler(request):
        calls.append(request)
        assert withdraw(client,case).status_code==200
        return httpx.Response(200,request=request,json={"stop_reason":"tool_use","usage":{"input_tokens":10,"output_tokens":2},"content":[{"type":"tool_use","name":"submit","input":{"facts":[]}}]})
    monkeypatch.setattr(httpx,"Client",lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    jobs.process_one()
    with SessionLocal() as db:
        row=db.get(VerificationJob,uuid.UUID(value["id"]))
        assert row.status=="cancelled" and row.reason_code=="consent_changed" and row.run_id is None
        assert db.scalar(select(func.count()).select_from(VerificationRun))==0
        meter=db.scalar(select(VerificationUsage))
        assert meter.status=="succeeded" and meter.input_tokens==10 and len(calls)==1


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Concurrent PostgreSQL row-lock behavior")
def test_withdrawal_does_not_wait_for_legacy_analysis_case_lock(client,admin_headers,case,monkeypatch):
    approve(client,case);monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    started=Event();release=Event();calls=[]
    def paused(*args,**kwargs):
        calls.append(kwargs);started.set();assert release.wait(10)
        return verification.Facts(facts=[])
    monkeypatch.setattr(verification,"model_call",paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=pool.submit(lambda:client.post(f"/api/v1/admin/tickets/{case}/verification",headers=admin_headers,json={"state":"Karnataka","use_llm":True,"consent_to_external_processing":True}))
        try:
            assert started.wait(5)
            withdrawn=pool.submit(withdraw,client,case)
            assert withdrawn.result(timeout=3).status_code==200
        finally:release.set()
        assert pending.result(timeout=10).status_code==409 and len(calls)==1
