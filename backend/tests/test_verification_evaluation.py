from copy import deepcopy
import json
from pathlib import Path
import stat

import httpx
import pytest

from app import config, document_reader, storage, verification, verification_evaluation as evaluation
from app.db import engine
from test_verification import local


def suite():return evaluation.load_suite()[0]


def one(key):return next(case for case in suite().cases if case.id==key)


def result(case):
    return verification.screen_documents(evaluation.prepared_for(case),verification.RunRequest(state=case.state,use_llm=True),
        evaluation.documents_for(case),model_runner=evaluation.replay_runner(case))


def test_default_replay_is_database_storage_and_network_independent(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail("Replay must not access network, case storage, OCR or database")
    monkeypatch.setattr(verification,"model_call",forbidden)
    monkeypatch.setattr(httpx,"Client",forbidden)
    monkeypatch.setattr(storage,"get",forbidden)
    monkeypatch.setattr(document_reader,"extract",forbidden)
    monkeypatch.setattr(engine,"connect",forbidden)
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","PRIVATE configured key never used")
    data,digest=evaluation.load_suite();report=evaluation.evaluate(data,digest)
    assert report["passed"] and report["mode"]=="replay" and report["provider"] is None
    assert report["summary"]["cases"]==12 and report["summary"]["passed"]==12
    assert report["summary"]["facts"]["true_positive"]==9 and report["summary"]["findings"]["true_positive"]==2
    assert report["summary"]["calls"]==25
    assert len(report["suite_sha256"])==64 and len(report["pipeline_revision"])==64 and len(report["evaluator_revision"])==64
    encoded=json.dumps(report)
    for private in ("PRIVATE","Ravi","Meera","Example Bank","Ignore all previous","Seller:","deed-a","Synthetic evaluation text"):
        assert private not in encoded


@pytest.mark.parametrize("mutation",["missed_fact","invented_value","wrong_citation","duplicate_fact","unsafe_verdict","failed_status"])
def test_reference_metrics_fail_on_regressions(mutation):
    case=one("clear-parties-and-property");value=result(case)
    if mutation=="missed_fact":value["facts"].pop()
    if mutation=="invented_value":value["facts"][0]["value"]="Invented Person"
    if mutation=="wrong_citation":value["facts"][0]["evidence"]["quote"]="Buyer: Meera."
    if mutation=="duplicate_fact":value["facts"].append(deepcopy(value["facts"][0]))
    if mutation=="unsafe_verdict":value["verdict"]="legally_safe"
    if mutation=="failed_status":value["llm_status"]="failed"
    scored=evaluation.score(case,value,"replay")
    assert not scored["passed"]
    if mutation=="invented_value":assert scored["facts"]["false_positive"]==1 and scored["facts"]["false_negative"]==1
    if mutation=="duplicate_fact":assert scored["facts"]["false_positive"]==1 and scored["facts"]["recall"]==1
    if mutation=="unsafe_verdict":assert not scored["checks"]["no_automatic_clearance"]


@pytest.mark.parametrize("mutation",["missed_finding","wrong_severity","missing_document","wrong_issue","unknown_law"])
def test_mismatch_requires_both_sources_and_the_expected_issue(mutation):
    case=one("cross-document-survey-mismatch");value=result(case)
    if mutation=="missed_finding":value["findings"]=[]
    if mutation=="wrong_severity":value["findings"][0]["severity"]="caution"
    if mutation=="missing_document":value["findings"][0]["evidence"].pop()
    if mutation=="wrong_issue":value["findings"][0].update(title="Unrelated issue",reason="Unrelated issue using real evidence.")
    if mutation=="unknown_law":value["findings"][0]["law_ids"]=["invented-law"]
    scored=evaluation.score(case,value,"replay")
    assert not scored["passed"] and scored["findings"]["false_negative"]==1


def test_no_expected_findings_does_not_get_an_invented_perfect_score():
    assert evaluation.metrics({"true_positive":0,"false_positive":0,"false_negative":0})=={
        "true_positive":0,"false_positive":0,"false_negative":0,"precision":None,"recall":None,"f1":None}
    case=one("historical-mortgage-is-not-current");value=result(case)
    value["findings"]=[one("explicit-outstanding-mortgage").findings[0].finding.model_dump()]
    score=evaluation.score(case,value,"replay")
    assert not score["passed"] and score["findings"]["false_positive"]==1 and score["findings"]["precision"]==0


def test_reviewed_aliases_and_longer_grounded_quotes_match_without_keyword_only_values():
    case=one("clear-parties-and-property");value=result(case)
    value["facts"][2]["value"]="Survey No. 42/1"
    value["facts"][2]["evidence"]["quote"]="Buyer: Meera. Survey No. 42/1."
    assert evaluation.score(case,value,"replay")["passed"]
    value["facts"][2]["value"]="Survey No. 42/1 legally safe"
    assert not evaluation.score(case,value,"replay")["passed"]


@pytest.mark.parametrize("mutation",["duplicate_case","duplicate_document","bad_reference","unknown_law","duplicate_page","missing_replay","not_synthetic","extra_field"])
def test_invalid_reference_suites_are_rejected(mutation):
    raw=suite().model_dump()
    if mutation=="duplicate_case":raw["cases"].append(deepcopy(raw["cases"][0]))
    if mutation=="duplicate_document":raw["cases"][0]["documents"].append(deepcopy(raw["cases"][0]["documents"][0]))
    if mutation=="bad_reference":raw["cases"][0]["facts"][0]["evidence"]["quote"]="An invented reference quote"
    if mutation=="unknown_law":raw["cases"][2]["findings"][0]["finding"]["law_ids"]=["invented-law"]
    if mutation=="duplicate_page":raw["cases"][0]["documents"][0]["pages"].append(deepcopy(raw["cases"][0]["documents"][0]["pages"][0]))
    if mutation=="missing_replay":raw["cases"][0]["replay"]["extractions"]={}
    if mutation=="not_synthetic":raw["synthetic_only"]=False
    if mutation=="extra_field":raw["unexpected"]="PRIVATE fixture field"
    with pytest.raises(ValueError):evaluation.Suite.model_validate(raw)


@pytest.mark.parametrize("settings",[
    {"mode":"provider"}, {"mode":"provider","allow_external":True,"max_calls":1},
    {"mode":"provider","allow_external":True}, {"case_ids":["unknown-case"]},
    {"mode":"provider","allow_external":True,"case_ids":["invented-quotes-and-wrong-pages"]},
    {"timeout":4},{"timeout":121},{"max_calls":0},{"max_calls":51},{"mode":"unknown"},
])
def test_preflight_failures_never_send(settings,monkeypatch):
    monkeypatch.setattr(verification,"model_call",lambda *args,**kwargs:pytest.fail("Invalid settings must not send"))
    with pytest.raises(evaluation.SettingsError):evaluation.evaluate(suite(),"fixture-digest",**settings)


def test_provider_mode_uses_real_adapter_with_mocked_transport_and_bounded_calls(monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    monkeypatch.setattr(config,"VERIFICATION_LLM_MODEL","fixture-model")
    selected=one("clear-parties-and-property");calls=[];real=httpx.Client
    def handler(request):
        body=json.loads(request.content);calls.append(body)
        content={"facts":[fact.model_dump(exclude={"aliases"}) for fact in selected.facts]} if len(calls)==1 else {"findings":[]}
        return httpx.Response(200,request=request,json={"stop_reason":"tool_use","content":[{"type":"tool_use","name":"submit","input":content}]})
    monkeypatch.setattr(httpx,"Client",lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    report=evaluation.evaluate(suite(),"fixture-digest",mode="provider",allow_external=True,case_ids=[selected.id],max_calls=2,timeout=5)
    assert report["passed"] and report["summary"]["calls"]==2 and len(calls)==2
    assert report["provider"]=={"provider":"anthropic","models":{"extract":"fixture-model","compare":"fixture-model"}}
    assert "expected_rejections" not in report["cases"][0]["checks"]
    assert "synthetic-never-sent" not in json.dumps(report)


def test_provider_mode_skips_scripted_guard_cases_and_reports_coverage(monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    def empty(*args,**kwargs):return verification.Facts(facts=[]) if kwargs.get("step")=="extract" else verification.Findings(findings=[])
    monkeypatch.setattr(verification,"model_call",empty)
    report=evaluation.evaluate(suite(),"fixture-digest",mode="provider",allow_external=True)
    assert report["summary"]["cases"]==7 and len(report["summary"]["skipped_replay_only"])==5 and report["summary"]["calls"]==14
    assert not report["passed"] and report["summary"]["facts"]["false_negative"]==9


def test_failed_provider_attempt_is_counted_once_without_retry_or_private_details(monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    calls=[]
    def failed(*args,**kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("PRIVATE endpoint, credentials and response body")
    monkeypatch.setattr(verification,"model_call",failed)
    report=evaluation.evaluate(suite(),"fixture-digest",mode="provider",allow_external=True,
        case_ids=["clear-parties-and-property"],max_calls=2)
    assert not report["passed"] and len(calls)==1 and report["summary"]["calls"]==1
    assert report["summary"]["facts"]["false_negative"]==3 and report["cases"][0]["llm_status"]=="failed"
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("base",["http://untrusted.example.test","https://private-user:PRIVATE@example.test/v1"])
def test_provider_endpoint_preflight_rejects_before_call_without_exposing_url(base,monkeypatch):
    monkeypatch.setattr(config,"VERIFICATION_LLM_PROVIDER","openai")
    monkeypatch.setattr(config,"VERIFICATION_LLM_API_KEY","synthetic-never-sent")
    monkeypatch.setattr(config,"VERIFICATION_LLM_BASE_URL",base)
    monkeypatch.setattr(verification,"model_call",lambda *args,**kwargs:pytest.fail("Invalid endpoint must not send"))
    with pytest.raises(evaluation.SettingsError,match="trusted HTTPS") as failure:
        evaluation.evaluate(suite(),"fixture-digest",mode="provider",allow_external=True)
    assert "PRIVATE" not in str(failure.value) and base not in str(failure.value)


def test_unexpected_evaluation_failure_is_private_and_preserves_missing_counts(monkeypatch):
    def failed(*args,**kwargs):raise RuntimeError("PRIVATE provider body, path and key")
    monkeypatch.setattr(evaluation,"replay_runner",lambda case:failed)
    report=evaluation.evaluate(suite(),"fixture-digest",case_ids=["clear-parties-and-property"])
    assert not report["passed"] and report["cases"][0]["error"]=="evaluation_failed"
    assert report["summary"]["facts"]["false_negative"]==3 and "PRIVATE" not in json.dumps(report)


def test_cli_report_is_private_exclusive_and_reports_failures(tmp_path,capsys,monkeypatch):
    output=tmp_path/"report.json"
    assert evaluation.main(["--output",str(output)])==0
    assert stat.S_IMODE(output.stat().st_mode)==0o600 and json.loads(output.read_text())["passed"]
    retained=output.read_bytes()
    assert evaluation.main(["--output",str(output)])==2 and output.read_bytes()==retained
    link=tmp_path/"link.json";link.symlink_to(output)
    assert evaluation.main(["--output",str(link)])==2 and output.read_bytes()==retained
    unstarted=tmp_path/"unstarted.json"
    assert evaluation.main(["--mode","provider","--output",str(unstarted)])==2 and not unstarted.exists()
    assert "--allow-external-synthetic-data" in capsys.readouterr().err
    monkeypatch.setattr(evaluation,"replay_runner",lambda case:lambda *args,**kwargs:verification.Facts(facts=[]))
    assert evaluation.main(["--case","clear-parties-and-property"])==1
    assert json.loads(capsys.readouterr().out)["passed"] is False


def test_pipeline_revision_changes_with_curated_laws(monkeypatch):
    original=evaluation.pipeline_revision()
    monkeypatch.setattr(evaluation.property_law,"LAW_VERSION","reviewed-next-version")
    assert evaluation.pipeline_revision()!=original


def test_ci_keeps_offline_gate_and_report_artifact():
    workflow=(Path(__file__).resolve().parents[2]/".github/workflows/security.yml").read_text()
    assert 'python -m app.verification_evaluation --output ../security-reports/verification-evaluation.json' in workflow
    assert 'security-reports/verification-evaluation.json' in workflow
    assert '--mode provider' not in workflow
