"""Versioned synthetic text benchmark. Replay is offline; provider mode is explicit."""
import argparse
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import Field, model_validator

from . import property_law, verification
from .models import utcnow

FIXTURES = Path(__file__).with_name("verification_evaluation_cases.json")
IDENTIFIER = r"^[a-z][a-z0-9-]{1,59}$"
VERDICTS = {"conditional_review", "insufficient_evidence", "high_risk"}


class SettingsError(ValueError):
    """Messages are fixed operator guidance, never provider or fixture content."""


class Page(verification.Strict):
    page: int = Field(ge=1, le=15)
    text: str = Field(max_length=12000)


class Document(verification.Strict):
    id: str = Field(pattern=IDENTIFIER)
    pages: list[Page] = Field(min_length=1, max_length=3)
    warnings: list[str] = Field(default_factory=list, max_length=3)


class GoldFinding(verification.Strict):
    finding: verification.Finding
    terms: list[str] = Field(min_length=1, max_length=5)


class GoldFact(verification.Fact):
    aliases: list[str] = Field(default_factory=list, max_length=6)


class Replay(verification.Strict):
    extractions: dict[str, dict]
    comparison: dict
    failure: Literal["none", "extract", "compare"] = "none"


class Case(verification.Strict):
    id: str = Field(pattern=IDENTIFIER)
    category: Literal["facts", "mismatch", "legal_risk", "incomplete", "injection", "grounding", "provider_failure"]
    state: Literal["Karnataka", "Tamil Nadu"] = "Karnataka"
    documents: list[Document] = Field(min_length=1, max_length=3)
    checklist_pending: bool = False
    replay_only: bool = False
    facts: list[GoldFact] = Field(max_length=20)
    findings: list[GoldFinding] = Field(max_length=5)
    verdict: Literal["conditional_review", "insufficient_evidence", "high_risk"]
    llm_status: Literal["completed", "failed"] = "completed"
    rejected_facts: int = Field(default=0, ge=0, le=20)
    rejected_findings: int = Field(default=0, ge=0, le=20)
    replay: Replay

    @model_validator(mode="after")
    def grounded_gold(self):
        docs = [document.model_dump() for document in self.documents]
        ids = [document.id for document in self.documents]
        if len(ids) != len(set(ids)): raise ValueError("Duplicate fixture document IDs")
        for document in self.documents:
            if len({page.page for page in document.pages}) != len(document.pages): raise ValueError("Duplicate fixture page numbers")
        if set(self.replay.extractions) != set(ids): raise ValueError("Replay extractions must cover the fixture documents")
        laws = {row["id"] for row in verification.applicable_laws(self.state)}
        for fact in self.facts:
            if not verification.valid_evidence(fact.evidence, docs): raise ValueError("Ungrounded reference fact")
            if any(not alias.strip() or len(alias) > 200 for alias in fact.aliases): raise ValueError("Invalid reference fact alias")
        for gold in self.findings:
            if not set(gold.finding.law_ids) <= laws or not all(verification.valid_evidence(evidence, docs) for evidence in gold.finding.evidence):
                raise ValueError("Ungrounded reference finding")
            if any(not term.strip() or len(term) > 100 for term in gold.terms): raise ValueError("Invalid finding matching terms")
        return self


class Suite(verification.Strict):
    version: str = Field(pattern=IDENTIFIER)
    synthetic_only: Literal[True]
    cases: list[Case] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def distinct_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases): raise ValueError("Duplicate fixture case IDs")
        return self


def load_suite():
    raw = FIXTURES.read_bytes()
    if len(raw) > 500000: raise ValueError("Fixture suite is too large")
    suite = Suite.model_validate_json(raw, strict=True)
    return suite, hashlib.sha256(raw).hexdigest()


def documents_for(case):
    return [{"id": document.id, "filename": "Synthetic evaluation text", "tag": "sale-deed", "sha256": None,
        "pages": [{**page.model_dump(), "method": "synthetic_text"} for page in document.pages],
        "warnings": list(document.warnings)} for document in case.documents]


def prepared_for(case):
    return {"state": case.state, "scope": {"property": {"type": "apartment"}}, "property_type": "apartment",
        "document_request": {"questions": []},
        "checklist": [{"tag": "sale-deed", "label": "Synthetic checklist", "status": "pending" if case.checklist_pending else "verified"}]}


def evidence_matches(actual, expected):
    return actual["document_id"] == expected["document_id"] and actual["page"] == expected["page"] and verification.normalise(expected["quote"]) in verification.normalise(actual["quote"])


def fact_matches(actual, expected):
    values = [expected["value"], *expected.get("aliases", [])]
    return actual["field"] == expected["field"] and verification.normalise(actual["value"]) in {verification.normalise(value) for value in values} and evidence_matches(actual["evidence"], expected["evidence"])


def finding_matches(actual, expected):
    gold = expected["finding"]
    text = verification.normalise(actual["title"] + " " + actual["reason"])
    return (actual["category"] == gold["category"] and actual["severity"] == gold["severity"]
        and set(actual["law_ids"]) == set(gold["law_ids"])
        and all(verification.normalise(term) in text for term in expected["terms"])
        and all(any(evidence_matches(evidence, wanted) for evidence in actual["evidence"]) for wanted in gold["evidence"]))


def counts(actual, expected, matches):
    remaining = list(expected)
    matched = 0
    for item in actual:
        index = next((index for index, gold in enumerate(remaining) if matches(item, gold)), None)
        if index is not None:
            remaining.pop(index)
            matched += 1
    return {"true_positive": matched, "false_positive": len(actual)-matched, "false_negative": len(remaining)}


def metrics(value):
    tp, fp, fn = (value[key] for key in ("true_positive", "false_positive", "false_negative"))
    return {**value, "precision": round(tp/(tp+fp), 6) if tp+fp else None,
        "recall": round(tp/(tp+fn), 6) if tp+fn else None,
        "f1": round(2*tp/(2*tp+fp+fn), 6) if 2*tp+fp+fn else None}


def score(case, result, mode):
    docs = documents_for(case)
    laws = {row["id"] for row in verification.applicable_laws(case.state)}
    facts = counts(result["facts"], [fact.model_dump() for fact in case.facts], fact_matches)
    findings = counts(result["findings"], [finding.model_dump() for finding in case.findings], finding_matches)
    checks = {"expected_status": result["llm_status"] == case.llm_status, "expected_verdict": result["verdict"] == case.verdict,
        "no_automatic_clearance": result["verdict"] in VERDICTS,
        "facts_grounded": all(verification.valid_evidence(verification.Evidence.model_validate(fact["evidence"]), docs) for fact in result["facts"]),
        "findings_grounded": all(set(finding["law_ids"]) <= laws and all(verification.valid_evidence(verification.Evidence.model_validate(evidence), docs) for evidence in finding["evidence"]) for finding in result["findings"])}
    if mode == "replay":
        checks["expected_rejections"] = result["rejected"] == {"facts": case.rejected_facts, "findings": case.rejected_findings}
    passed = all(checks.values()) and not any(value[key] for value in (facts, findings) for key in ("false_positive", "false_negative"))
    return {"case_id": case.id, "category": case.category, "passed": passed, "checks": checks,
        "llm_status": result["llm_status"], "verdict": result["verdict"], "facts": metrics(facts), "findings": metrics(findings),
        "rejected": dict(result["rejected"])}


def replay_runner(case):
    def call(task, payload, schema, step="compare", **kwargs):
        if case.replay.failure == step:
            raise httpx.ReadTimeout("Synthetic evaluation failure")
        body = case.replay.extractions[payload["documents"][0]["id"]] if step == "extract" else case.replay.comparison
        return schema.model_validate(deepcopy(body))
    return call


def pipeline_revision():
    return verification.fingerprint({"verification_source": inspect.getsource(verification),
        "laws": property_law.LAWS, "law_version": property_law.LAW_VERSION})


def provider_configuration():
    status = verification.provider_status()
    if not status["configured"]: raise SettingsError("Configure a verification provider before provider evaluation.")
    for model in status["models"].values():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", model): raise SettingsError("Invalid evaluation model identifier.")
    if status["provider"] == "openai":
        base = urlparse(verification.config.VERIFICATION_LLM_BASE_URL)
        if base.scheme != "https" or not base.hostname or base.username or base.password:
            raise SettingsError("A trusted HTTPS provider endpoint is required.")
    return {"provider": status["provider"], "models": status["models"]}


def evaluate(suite, suite_hash, *, mode="replay", case_ids=(), allow_external=False, timeout=60, max_calls=30):
    if mode not in ("replay", "provider") or not 5 <= timeout <= 120 or not 1 <= max_calls <= 50:
        raise SettingsError("Use a 5–120 second timeout and a 1–50 call budget.")
    unknown = set(case_ids) - {case.id for case in suite.cases}
    if unknown: raise SettingsError("Unknown evaluation case selection. Use case IDs from the reviewed suite.")
    selected = [case for case in suite.cases if not case_ids or case.id in case_ids]
    skipped = [case.id for case in selected if mode == "provider" and case.replay_only]
    selected = [case for case in selected if case.id not in skipped]
    if not selected: raise SettingsError("No eligible evaluation cases selected; provider mode excludes replay-only cases.")
    provider = None
    if mode == "provider":
        if not allow_external: raise SettingsError("Provider evaluation requires --allow-external-synthetic-data; requests may incur charges.")
        expected_calls = sum(1 + sum(any(page.text.strip() for page in document.pages) for document in case.documents) for case in selected)
        if expected_calls > max_calls: raise SettingsError("Selected cases exceed the provider call budget; select fewer cases or raise --max-calls.")
        provider = provider_configuration()
    rows, attempts = [], 0
    started = time.monotonic()
    for case in selected:
        base = replay_runner(case) if mode == "replay" else verification.model_call
        def call(*args, **kwargs):
            nonlocal attempts
            if mode == "provider" and attempts >= max_calls: raise RuntimeError("Evaluation call budget exhausted")
            attempts += 1
            if mode == "provider": kwargs["timeout"] = timeout
            return base(*args, **kwargs)
        try:
            result = verification.screen_documents(prepared_for(case), verification.RunRequest(state=case.state, use_llm=True,
                consent_to_external_processing=True), documents_for(case), model_runner=call)
            row = score(case, result, mode)
        except Exception:
            # Provider bodies, local paths, prompts and exception text never enter reports.
            row = {"case_id": case.id, "category": case.category, "passed": False, "error": "evaluation_failed",
                "facts": metrics({"true_positive": 0, "false_positive": 0, "false_negative": len(case.facts)}),
                "findings": metrics({"true_positive": 0, "false_positive": 0, "false_negative": len(case.findings)})}
        rows.append(row)
    totals = {}
    for field in ("facts", "findings"):
        totals[field] = metrics({key: sum(row.get(field, {}).get(key, 0) for row in rows) for key in ("true_positive", "false_positive", "false_negative")})
    return {"report_version": 1, "suite_version": suite.version, "suite_sha256": suite_hash, "pipeline_revision": pipeline_revision(),
        "evaluator_revision": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "law_version": property_law.LAW_VERSION, "mode": mode, "provider": provider, "checked_at": utcnow().isoformat(),
        "scope": "synthetic_extracted_text", "passed": all(row["passed"] for row in rows),
        "summary": {"cases": len(rows), "passed": sum(row["passed"] for row in rows), "failed": sum(not row["passed"] for row in rows),
            "skipped_replay_only": skipped, "calls": attempts, "elapsed_ms": max(0, int((time.monotonic()-started)*1000)), **totals},
        "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate verification on versioned synthetic extracted text; replay is offline, provider mode can incur charges.")
    parser.add_argument("--mode", choices=("replay", "provider"), default="replay")
    parser.add_argument("--case", action="append", default=[], dest="case_ids", help="Select a case ID; repeat for multiple cases.")
    parser.add_argument("--allow-external-synthetic-data", action="store_true")
    parser.add_argument("--timeout", type=int, default=60, help="Provider timeout per call, 5–120 seconds. No automatic retries.")
    parser.add_argument("--max-calls", type=int, default=30, help="Provider attempt budget, 1–50. Rejected before any request if too small.")
    parser.add_argument("--output", type=Path, help="Create a new private JSON report; an existing path is never overwritten.")
    args = parser.parse_args(argv)
    # Reserve output before any paid call. Never overwrite a file or follow a symlink.
    descriptor = None
    reserved = None
    written = False
    try:
        if args.output:
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            reserved = os.fstat(descriptor)
        suite, digest = load_suite()
        report = evaluate(suite, digest, mode=args.mode, case_ids=args.case_ids, allow_external=args.allow_external_synthetic_data,
            timeout=args.timeout, max_calls=args.max_calls)
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if descriptor is None: print(encoded, end="")
        else:
            with os.fdopen(descriptor, "w") as output:
                descriptor = None
                output.write(encoded)
        written = True
        return 0 if report["passed"] else 1
    except SettingsError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print("Evaluation could not start or write its report. Check fixture validity, provider consent/configuration, call budget, case selection and a new writable output path.", file=sys.stderr)
        return 2
    finally:
        if descriptor is not None: os.close(descriptor)
        if reserved is not None and not written:
            try:
                current = args.output.lstat()
                if (current.st_dev, current.st_ino) == (reserved.st_dev, reserved.st_ino): args.output.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
