import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import func, select

from app import config, verification, verification_jobs as jobs
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, AuditLog, Document, Notification, ServiceRequest, VerificationJob, VerificationRun, utcnow
from test_verification import local, upload


def base(number):return f"/api/v1/admin/tickets/{number}/verification/jobs"


def payload(**values):return {"state":"Karnataka","use_llm":False,"consent_to_external_processing":False,"submission_key":str(uuid.uuid4()),**values}


@pytest.fixture
def case(client,raise_ticket,admin_headers):
    number=raise_ticket();upload(client,number);return number


def queued(client,headers,number,**values):
    result=client.post(base(number),headers=headers,json=payload(**values))
    assert result.status_code==202,result.text
    return result.json()


def stored(key):
    with SessionLocal() as db:return db.get(VerificationJob,uuid.UUID(key))


def test_queue_is_fast_idempotent_private_and_does_no_analysis(client,admin_headers,case,monkeypatch):
    monkeypatch.setattr(verification,"run_prepared",lambda *args:pytest.fail("HTTP submission must not run analysis"))
    body=payload();first=client.post(base(case),headers=admin_headers,json=body)
    assert first.status_code==202 and first.json()["status"]=="queued" and first.headers["cache-control"]=="private, no-store"
    assert client.post(base(case),headers=admin_headers,json=body).json()["id"]==first.json()["id"]
    assert client.post(base(case),headers=admin_headers,json={**body,"state":"Tamil Nadu"}).status_code==409
    assert client.post(base(case),headers=admin_headers,json=payload()).status_code==409
    assert client.post(base(case).removesuffix("/jobs"),headers=admin_headers,json={"state":"Karnataka"}).status_code==409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VerificationJob))==1
        assert db.scalar(select(func.count()).select_from(VerificationRun))==0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="verification.job_queued"))==1
    assert set(first.json())=={"id","status","phase","created_at","started_at","finished_at","state","use_llm","run_id","message","can_cancel"}


def test_access_scope_and_cancellation_permissions(client,admin_headers,agent,case,raise_ticket):
    job=queued(client,admin_headers,case)
    assert client.get(base(case)).status_code==401
    assert client.get(base(case),headers=agent["headers"]).status_code==404
    assert client.post(f"/api/v1/admin/tickets/{case}/members",headers=admin_headers,json={"user_id":agent["id"],"role":"reviewer"}).status_code==201
    assert client.get(base(case),headers=agent["headers"]).json()["items"][0]["can_cancel"] is False
    assert client.post(base(case)+"/"+job["id"]+"/cancel",headers=agent["headers"]).status_code==403
    other=raise_ticket()
    assert client.post(base(other)+"/"+job["id"]+"/cancel",headers=admin_headers).status_code==404
    assert client.delete(f"/api/v1/admin/tickets/{case}/members/{agent['id']}",headers=admin_headers).status_code==200
    assert client.get(base(case),headers=agent["headers"]).status_code==404


def test_local_worker_saves_grounded_result_without_notifications_or_automatic_approval(client,admin_headers,case):
    job=queued(client,admin_headers,case)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(Notification))
    assert jobs.process_one() is True and jobs.process_one() is False
    row=stored(job["id"]);assert row.status=="completed" and row.run_id and row.claim_token is None
    result=client.get(base(case).removesuffix("/jobs"),headers=admin_headers).json()["items"][0]
    assert result["id"]==str(row.run_id) and not result["stale"] and result["verdict"]=="insufficient_evidence"
    assert "Survey number 42" in result["documents"][0]["pages"][0]["text"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Notification))==before
        assert db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==case)).report is None


@pytest.mark.parametrize("change",["evidence","closed","configuration","access"])
def test_changed_inputs_or_access_stop_before_processing(client,admin_headers,agent,case,monkeypatch,change):
    if change=="access":
        client.post(f"/api/v1/admin/tickets/{case}/members",headers=admin_headers,json={"user_id":agent["id"],"role":"reviewer"})
    job=queued(client,agent["headers"] if change=="access" else admin_headers,case)
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==case))
        if change=="evidence":ticket.documents[0].tag="changed-tag"
        if change=="closed":ticket.status="cancelled"
        db.commit()
    if change=="configuration":monkeypatch.setattr(config,"VERIFICATION_OCR_LANGUAGES","eng+kan")
    if change=="access":client.delete(f"/api/v1/admin/tickets/{case}/members/{agent['id']}",headers=admin_headers)
    monkeypatch.setattr(verification,"run_prepared",lambda *args:pytest.fail("Changed inputs must not reach analysis"))
    jobs.process_one();row=stored(job["id"])
    assert row.status==("stale" if change in ("evidence","closed") else "cancelled" if change=="access" else "failed")
    assert row.run_id is None


def test_running_cancellation_rejects_late_results(client,admin_headers,case,monkeypatch):
    job=queued(client,admin_headers,case);real=verification.run_prepared
    def run(prepared,request,progress):
        assert client.post(base(case)+"/"+job["id"]+"/cancel",headers=admin_headers).status_code==200
        return real(prepared,request,progress)
    monkeypatch.setattr(verification,"run_prepared",run);jobs.process_one()
    assert stored(job["id"]).status=="cancelled"
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(VerificationRun))==0
    assert client.post(base(case)+"/"+job["id"]+"/cancel",headers=admin_headers).status_code==200
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="verification.job_cancelled"))==1


@pytest.mark.parametrize("missing_lease",[False,True])
def test_expired_work_is_not_replayed_and_old_token_cannot_publish(client,admin_headers,case,missing_lease):
    job=queued(client,admin_headers,case);key,token=jobs.claim()
    with SessionLocal() as db:
        row=db.get(VerificationJob,key);row.lease_until=None if missing_lease else utcnow()-timedelta(seconds=1);row.created_at=utcnow()-timedelta(minutes=20);db.commit()
    assert client.get(base(case),headers=admin_headers).json()["items"][0]["status"]=="interrupted"
    assert jobs.process_one() is False and stored(job["id"]).reason_code=="interrupted"
    with pytest.raises(jobs.StopWork):jobs.checkpoint(key,token,"finalizing")
    fresh=queued(client,admin_headers,case)
    assert fresh["id"]!=job["id"] and stored(job["id"]).status=="failed"


def test_queued_cancellation_never_processes_and_retry_requires_fresh_request(client,admin_headers,case):
    job=queued(client,admin_headers,case)
    client.post(base(case)+"/"+job["id"]+"/cancel",headers=admin_headers)
    assert jobs.process_one() is False
    assert client.post(base(case),headers=admin_headers,json=payload()).status_code==429


def test_llm_consent_settings_binding_and_sanitized_failure(client,admin_headers,case,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    assert client.post(base(case),headers=admin_headers,json=payload(use_llm=True)).status_code==422
    assert client.post(base(case),headers=admin_headers,json=payload(use_llm=True,consent_to_external_processing=True,configuration_revision="old")).status_code==409
    job=queued(client,admin_headers,case,use_llm=True,consent_to_external_processing=True,configuration_revision=jobs.configuration(True))
    def failed(*args,**kwargs):raise ValueError("PRIVATE provider response and API key")
    monkeypatch.setattr(verification,"model_call",failed)
    jobs.process_one();row=stored(job["id"])
    assert row.status=="failed" and row.reason_code=="analysis_failed" and row.run_id is None
    assert "PRIVATE" not in client.get(base(case),headers=admin_headers).text
    assert jobs.process_one() is False


@pytest.mark.parametrize("extra",[{"use_llm":"true"},{"consent_to_external_processing":1},{"submission_key":"bad"},{"unexpected":True},{"state":"bad\x00state"},{"state":"  "}])
def test_strict_job_submission(client,admin_headers,case,extra):
    assert client.post(base(case),headers=admin_headers,json=payload(**extra)).status_code==422


def test_submission_and_lookup_budgets_apply(client,admin_headers,case,monkeypatch):
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_AI_ACTIONS_PER_MINUTE",1)
    queued(client,admin_headers,case)
    assert client.post(base(case),headers=admin_headers,json=payload()).status_code==429
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(base(case),headers=admin_headers).status_code==200
    assert client.get(base(case),headers=admin_headers).status_code==429


def test_operations_surface_waiting_jobs_and_external_worker_health(client,admin_headers,case):
    from test_operations import set_revision
    set_revision();queued(client,admin_headers,case)
    result=client.get("/api/v1/admin/operations",headers=admin_headers).json()
    assert result["verification_jobs"]["queued"]==1 and result["status"]=="attention"
    worker=next(row for row in result["workers"] if row["name"]=="verification")
    assert worker["state"]=="not_observed" and not worker["enabled_in_api"]
    jobs.tick()
    result=client.get("/api/v1/admin/operations",headers=admin_headers).json()
    assert result["verification_jobs"]["queued"]==0
    assert next(row for row in result["workers"] if row["name"]=="verification")["state"]=="healthy"


def test_worker_refuses_processing_without_current_schema(client,admin_headers,case):
    from test_operations import set_revision
    from app.telemetry import WorkerConfigurationError
    queued(client,admin_headers,case);set_revision("0040_append_only_audit")
    with pytest.raises(WorkerConfigurationError):jobs.tick()
    assert client.get(base(case),headers=admin_headers).json()["items"][0]["status"]=="queued"


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Concurrent job claims require PostgreSQL")
def test_concurrent_workers_claim_one_job_once(client,admin_headers,case):
    queued(client,admin_headers,case);barrier=Barrier(2)
    def claim():barrier.wait(timeout=5);return jobs.claim()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
    assert sum(value is not None for value in results)==1


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real PostgreSQL case-lock concurrency")
def test_case_updates_are_not_locked_by_analysis_and_changed_results_are_discarded(client,admin_headers,case,monkeypatch):
    job=queued(client,admin_headers,case);started=Event();release=Event();real=verification.run_prepared
    def paused(prepared,request,progress):started.set();assert release.wait(timeout=15);return real(prepared,request,progress)
    monkeypatch.setattr(verification,"run_prepared",paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(jobs.process_one)
        try:
            assert started.wait(timeout=10)
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                from sqlalchemy import text
                connection.execute(text("SET statement_timeout=2000"))
                connection.execute(text("UPDATE service_requests SET status='on_hold' WHERE ticket_number=:number"),{"number":case})
        finally:release.set()
        assert future.result(timeout=15)
    assert stored(job["id"]).status=="stale" and stored(job["id"]).run_id is None
