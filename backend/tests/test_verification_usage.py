import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier

import httpx
import pytest
from sqlalchemy import select, text

from app import config, verification, verification_jobs as jobs, verification_usage as usage
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, ServiceRequest, VerificationUsage
from test_verification import local, upload, approve
from test_verification_jobs import base, queued

HTTP_CLIENT = httpx.Client


def prices(model="fixture-model", **changes):
    return json.dumps({"version":"reviewed-fixture", "models":{f"anthropic/{model}":{"input_per_million":"2.00", "output_per_million":"6.00", **changes}}})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_PROVIDER","anthropic")
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    monkeypatch.setattr(config,"VERIFICATION_LLM_MODEL","fixture-model")
    monkeypatch.setattr(config,"VERIFICATION_EXTRACT_MODEL","")
    monkeypatch.setattr(config,"VERIFICATION_COMPARE_MODEL","")
    monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES",prices())


def transport(monkeypatch, handler):
    monkeypatch.setattr(verification.httpx,"Client",lambda **kwargs:HTTP_CLIENT(transport=httpx.MockTransport(handler),**kwargs))


def response(request, counters=None, valid=True):
    return httpx.Response(200,request=request,json={"stop_reason":"tool_use", "usage":counters,
        "content":[{"type":"tool_use","name":"submit","input":{"facts":[]} if valid else {"PRIVATE":"sensitive document"}}]})


def rows():
    with SessionLocal() as db:return db.scalars(select(VerificationUsage).order_by(VerificationUsage.started_at)).all()


@pytest.mark.parametrize("provider,value,expected",[
    ("anthropic",{"input_tokens":10,"output_tokens":2},(10,2,0)),
    ("anthropic",{"input_tokens":10,"output_tokens":2,"cache_read_input_tokens":4,"cache_creation_input_tokens":3},(17,2,7)),
    ("openai",{"prompt_tokens":10,"completion_tokens":2,"prompt_tokens_details":{"cached_tokens":4}},(10,2,4)),
    ("anthropic",{"input_tokens":0,"output_tokens":0},(0,0,0)),
    ("anthropic",{"input_tokens":True,"output_tokens":1},None),
    ("anthropic",{"input_tokens":-1,"output_tokens":1},None),
    ("anthropic",{"input_tokens":1.0,"output_tokens":1},None),
    ("anthropic",{"input_tokens":1},None),
    ("anthropic",{"input_tokens":1_000_000_000,"cache_read_input_tokens":1,"output_tokens":1},None),
    ("openai",{"prompt_tokens":10,"completion_tokens":1,"prompt_tokens_details":None},None),
    ("openai",{"prompt_tokens":1,"completion_tokens":2,"prompt_tokens_details":{"cached_tokens":2}},None),
    ("openai",None,None),
])
def test_strict_provider_counters(provider,value,expected):
    assert usage.tokens(provider,value)==expected


@pytest.mark.parametrize("value",["bad", "[]", '{"version":"ok","models":{}}',
    '{"version":"ok","version":"again","models":{}}', prices(input_per_million=True),
    prices(input_per_million="NaN"),prices(input_per_million="-1"),prices(input_per_million="0.0000001"),
    prices(input_per_million="1000001"),prices(extra="private"),prices(model="bad\nmodel")])
def test_invalid_prices_disable_estimates_without_details(monkeypatch,value):
    monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES",value)
    assert usage.rates()=={"status":"invalid","version":None,"models":{}}


def test_attempt_persists_before_send_snapshots_rates_and_resets_scope(monkeypatch,configured):
    case,job=uuid.uuid4(),uuid.uuid4()
    def handler(request):
        assert rows()[0].status=="started" and rows()[0].estimated_usd is None
        monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES",prices(input_per_million="999"))
        return response(request,{"input_tokens":100,"output_tokens":20})
    transport(monkeypatch,handler)
    with usage.scope(case,job):verification.model_call("PRIVATE prompt",{"PRIVATE":"document"},verification.Facts,step="extract")
    row=rows()[0]
    assert row.status=="succeeded" and row.job_id==job and row.service_request_id==case
    assert row.estimated_usd==Decimal("0.000320000000") and row.input_rate==2 and row.rate_version=="reviewed-fixture"
    assert row.duration_ms>=0 and row.usage_complete and row.estimate_reason=="priced"
    transport(monkeypatch,lambda request:response(request,{"input_tokens":100,"output_tokens":20}))
    verification.model_call("legacy untracked",{},verification.Facts)
    assert len(rows())==1 and usage._scope.get() is None


@pytest.mark.parametrize("counters,valid,reason,estimate",[
    ({"input_tokens":0,"output_tokens":0},True,"priced",Decimal(0)),
    (None,True,"usage_unavailable",None),
    ({"input_tokens":10,"output_tokens":2,"cache_read_input_tokens":3},True,"cache_usage_unpriced",None),
    ({"input_tokens":10,"output_tokens":2},False,"priced",Decimal("0.000032")),
])
def test_unknown_zero_cache_and_billed_invalid_output(monkeypatch,configured,counters,valid,reason,estimate):
    transport(monkeypatch,lambda request:response(request,counters,valid))
    with usage.scope(uuid.uuid4(),uuid.uuid4()):
        if valid:verification.model_call("fixture",{},verification.Facts)
        else:
            with pytest.raises(ValueError):verification.model_call("fixture",{},verification.Facts)
    row=rows()[0]
    assert row.estimate_reason==reason and row.estimated_usd==estimate
    assert row.status==("succeeded" if valid else "failed")
    assert row.error_category==(None if valid else "invalid_response")


@pytest.mark.parametrize("failure,category",[("http","provider_http_error"),("transport","transport_error"),("json","invalid_response")])
def test_failed_request_has_unknown_billing_and_safe_category(monkeypatch,configured,failure,category):
    def handler(request):
        if failure=="transport":raise httpx.ReadTimeout("PRIVATE key and response",request=request)
        if failure=="json":return httpx.Response(200,request=request,text="PRIVATE malformed body")
        return httpx.Response(503,request=request,text="PRIVATE provider response")
    transport(monkeypatch,handler)
    with usage.scope(uuid.uuid4(),uuid.uuid4()),pytest.raises(Exception):verification.model_call("fixture",{},verification.Facts)
    row=rows()[0]
    assert row.status=="failed" and row.estimated_usd is None and row.input_tokens is None and row.error_category==category
    assert "PRIVATE" not in json.dumps(usage.view(row))


def test_recording_failure_prevents_send_and_finish_failure_leaves_unfinished(monkeypatch,configured):
    real=usage.SessionLocal
    def broken():raise RuntimeError("PRIVATE database credentials")
    transport(monkeypatch,lambda request:pytest.fail("Unrecorded attempt must not be sent"))
    monkeypatch.setattr(usage,"SessionLocal",broken)
    with usage.scope(uuid.uuid4(),uuid.uuid4()),pytest.raises(usage.UsageRecordingError,match="no request was sent"):
        verification.model_call("fixture",{},verification.Facts)
    monkeypatch.setattr(usage,"SessionLocal",real)
    def handler(request):
        monkeypatch.setattr(usage,"SessionLocal",broken)
        return response(request,{"input_tokens":10,"output_tokens":2})
    transport(monkeypatch,handler)
    with usage.scope(uuid.uuid4(),uuid.uuid4()),pytest.raises(usage.UsageRecordingError,match="unfinished attempt"):
        verification.model_call("fixture",{},verification.Facts)
    assert rows()[0].status=="started" and rows()[0].estimate_reason=="attempt_unfinished"
    assert usage._scope.get() is None


@pytest.mark.parametrize("raw,reason",[("","rates_not_configured"),("bad","invalid_rate_configuration"),(prices(model="another-model"),"model_not_priced")])
def test_unpriced_configuration_does_not_stop_provider_work(monkeypatch,configured,raw,reason):
    monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES",raw)
    transport(monkeypatch,lambda request:response(request,{"input_tokens":1,"output_tokens":2}))
    with usage.scope(uuid.uuid4(),uuid.uuid4()):verification.model_call("fixture",{},verification.Facts)
    row=rows()[0]
    assert row.status=="succeeded" and row.usage_complete and row.estimated_usd is None and row.estimate_reason==reason


def test_openai_adapter_records_actual_usage_and_rejects_invalid_endpoint_before_attempt(monkeypatch,configured):
    monkeypatch.setattr(config,"VERIFICATION_LLM_PROVIDER","openai")
    monkeypatch.setattr(config,"VERIFICATION_LLM_BASE_URL","https://adapter.example.test/v1")
    monkeypatch.setattr(config,"VERIFICATION_TOKEN_RATES",prices().replace("anthropic/","openai/"))
    transport(monkeypatch,lambda request:httpx.Response(200,request=request,json={"usage":{"prompt_tokens":100,"completion_tokens":20},"choices":[{"finish_reason":"stop","message":{"content":"{\"facts\":[]}"}}]}))
    with usage.scope(uuid.uuid4(),uuid.uuid4()):verification.model_call("fixture",{},verification.Facts)
    row=rows()[0]
    assert row.provider=="openai" and row.estimated_usd==Decimal("0.00032")
    monkeypatch.setattr(config,"VERIFICATION_LLM_BASE_URL","http://untrusted.example.test")
    with usage.scope(uuid.uuid4(),uuid.uuid4()),pytest.raises(ValueError,match="HTTPS"):
        verification.model_call("fixture",{},verification.Facts)
    assert len(rows())==1


@pytest.mark.parametrize("cancel",[False,True])
def test_background_context_and_job_history_summaries(client,admin_headers,raise_ticket,monkeypatch,configured,cancel):
    number=raise_ticket();upload(client,number);approve(client,number)
    job=queued(client,admin_headers,number,use_llm=True,consent_to_external_processing=True,configuration_revision=jobs.configuration(True))
    real=verification.run_prepared
    def run(prepared,request,progress):
        verification.model_call("fixture",{},verification.Facts,step="extract")
        result=real(prepared,verification.RunRequest(state="Karnataka"),progress)
        result["llm_status"]="completed"
        return result
    monkeypatch.setattr(verification,"run_prepared",run)
    def handler(request):
        if cancel:assert client.post(base(number)+f"/{job['id']}/cancel",headers=admin_headers).status_code==200
        return response(request,{"input_tokens":100,"output_tokens":20})
    transport(monkeypatch,handler)
    assert jobs.process_one() and usage._scope.get() is None
    result=client.get(base(number),headers=admin_headers).json()["items"][0]
    assert result["status"]==("cancelled" if cancel else "completed") and result["usage"]["attempts"]==1 and result["usage"]["known_estimated_usd"]=="0.000320000000"
    if cancel:assert result["run_id"] is None
    assert rows()[0].job_id==uuid.UUID(job["id"])
    assert client.post(base(number)+f"/{job['id']}/cancel",headers=admin_headers).json()["usage"]==result["usage"]


def test_admin_scope_paging_window_and_unknown_subtotals(client,admin_headers,agent,monkeypatch,configured):
    now=datetime(2026,11,11,19,0,tzinfo=timezone.utc)  # 12 November IST
    monkeypatch.setattr(usage,"utcnow",lambda:now)
    job=uuid.uuid4()
    with SessionLocal() as db:
        for hour,status,cost in [(17,"succeeded",Decimal(0)),(18,"failed",Decimal("0.000000000001")),(19,"started",None)]:
            db.add(VerificationUsage(service_request_id=uuid.uuid4(),job_id=job,provider="anthropic",model="fixture-model",step="extract",status=status,
                started_at=now.replace(hour=hour),estimated_usd=cost))
        db.commit()
    endpoint="/api/v1/admin/verification-usage"
    assert client.get(endpoint).status_code==401
    assert client.get(endpoint,headers=agent["headers"]).status_code==403
    result=client.get(endpoint+"?days=1",headers=admin_headers)
    assert result.status_code==200 and result.headers["cache-control"]=="private, no-store"
    assert result.json()["from_at"]=="2026-11-11T18:30:00+00:00" and result.json()["summary"]["attempts"]==1
    result=client.get(endpoint+"?page_size=1&days=2",headers=admin_headers).json()
    assert len(result["items"])==1 and result["summary"]["attempts"]==3 and result["summary"]["unpriced_attempts"]==1
    assert result["summary"]["known_estimated_usd"]=="0.000000000001"
    assert result["pricing"]=={"status":"configured","version":"reviewed-fixture","models":1}
    assert set(result["items"][0])=={"id","service_request_id","job_id","provider","model","step","status","started_at","finished_at","duration_ms","input_tokens","output_tokens","cache_tokens","usage_complete","estimated_usd","estimate_reason","rate_version","error_category"}
    assert client.get(endpoint+"?provider=openai",headers=admin_headers).json()["summary"]["known_estimated_usd"] is None
    for query in ("days=91","days=0","page=0","page_size=101","status=bad","provider=bad","step=classify","job_id=bad"):
        assert client.get(endpoint+"?"+query,headers=admin_headers).status_code==422
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(endpoint,headers=admin_headers).status_code==200
    assert client.get(endpoint,headers=admin_headers).status_code==429


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real concurrent PostgreSQL transactions")
def test_metadata_does_not_lock_cases_and_parallel_scopes_stay_separate(client,admin_headers,raise_ticket,configured):
    number=raise_ticket()
    with SessionLocal() as db:case=db.scalar(select(ServiceRequest.id).where(ServiceRequest.ticket_number==number))
    barrier=Barrier(2)
    ids=[uuid.uuid4(),uuid.uuid4()]
    def run(job):
        with usage.scope(case,job),usage.Attempt("anthropic","fixture-model","extract") as attempt:
            barrier.wait(timeout=5)
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text("SET statement_timeout=2000"))
                connection.execute(text("UPDATE service_requests SET priority='high' WHERE id=:key"),{"key":case})
            attempt.capture({"usage":{"input_tokens":1,"output_tokens":2}})
        assert usage._scope.get() is None
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,ids))
    assert {row.job_id for row in rows()}==set(ids) and all(row.status=="succeeded" for row in rows())
