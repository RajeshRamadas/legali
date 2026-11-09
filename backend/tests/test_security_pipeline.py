"""The security gate must not mistake unavailable tools or incomplete scans for success."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


checks = module("audit_dependencies")
locks = module("check_python_locks")
source = module("scan_python")


def npm_report(**updates):
    return {"metadata": {"vulnerabilities": {"low": 0, "moderate": 15, "high": 0, "critical": 0, **updates}}, "vulnerabilities": {}}


def test_npm_policy_reports_moderates_but_rejects_high_or_critical():
    assert checks.evaluate_npm(npm_report()) == (True, {"low": 0, "moderate": 15, "high": 0, "critical": 0})
    assert not checks.evaluate_npm(npm_report(high=1))[0]
    assert not checks.evaluate_npm(npm_report(critical=1))[0]


@pytest.mark.parametrize("report", [[], {"metadata": []}, {}, {"error": {"code": "ENETUNREACH"}}, {"metadata": {"vulnerabilities": {}}}, npm_report(high=-1), npm_report(high="0")])
def test_incomplete_or_invalid_npm_report_cannot_pass(report):
    with pytest.raises(ValueError): checks.evaluate_npm(report)


def test_python_policy_rejects_vulnerabilities_and_skipped_coverage():
    clean = {"dependencies": [{"name": "sample", "version": "1.0", "vulns": []}]}
    assert checks.evaluate_python(clean)[0]
    assert not checks.evaluate_python({"dependencies": [{"name": "sample", "version": "1.0", "vulns": [{"id": "GHSA-synthetic"}]}]})[0]
    for report in ([], {}, {"dependencies": []}, {"dependencies": [{"name": "sample", "skip_reason": "lookup unavailable"}]}, {"dependencies": [{"name": "sample", "version": "1.0"}]}):
        with pytest.raises(ValueError): checks.evaluate_python(report)


def test_all_audits_run_after_one_fails_and_stale_reports_are_removed(tmp_path, monkeypatch):
    (tmp_path / "python-runtime.json").write_text(json.dumps({"dependencies": [{"name": "old", "version": "1.0", "vulns": []}]}))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "npm":
            json.dump(npm_report(), kwargs["stdout"])
            return SimpleNamespace(returncode=0)
        target = Path(command[command.index("--output") + 1])
        if target.name == "python-runtime.json":
            return SimpleNamespace(returncode=1)  # No replacement report: the old file must not count.
        target.write_text(json.dumps({"dependencies": [{"name": "sample", "version": "1.0", "vulns": []}]}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(checks.subprocess, "run", run)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert checks.audit(tmp_path) == 1 and len(calls) == 4
    result = json.loads((tmp_path / "summary.json").read_text())
    assert not result[0]["passed"] and all(row["passed"] for row in result[1:])


def test_nonzero_tool_exit_cannot_be_overridden_by_clean_json(tmp_path, monkeypatch):
    def run(command, **kwargs):
        if command[0] == "npm": json.dump(npm_report(), kwargs["stdout"])
        else: Path(command[command.index("--output") + 1]).write_text(json.dumps({"dependencies": [{"name": "sample", "version": "1.0", "vulns": []}]}))
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(checks.subprocess, "run", run)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert checks.audit(tmp_path) == 1
    assert all(not row["passed"] for row in json.loads((tmp_path / "summary.json").read_text()))


@pytest.mark.parametrize("line", ["sample>=1.0", "sample==1.0", "sample==1.* --hash=sha256:" + "a" * 64, "sample @ https://example.invalid/package.whl"])
def test_unpinned_unhashed_and_direct_url_locks_fail(tmp_path, line):
    path = tmp_path / "requirements.txt"
    path.write_text(line + "\n")
    with pytest.raises(ValueError): locks.locked(path)


def test_lock_inputs_check_current_versions_and_duplicate_pins(tmp_path):
    path = tmp_path / "requirements.txt"
    line = "sample==1.0 --hash=sha256:" + "a" * 64 + "\n"
    path.write_text(line)
    assert locks.locked(path) == {"sample": "1.0"}
    source = tmp_path / "requirements.in"
    source.write_text("sample>=2.0\n")
    with pytest.raises(ValueError): locks.check_inputs(source, locks.locked(path))
    path.write_text(line + line)
    with pytest.raises(ValueError): locks.locked(path)


def test_source_scan_rejects_parse_errors_and_empty_coverage():
    clean = {"errors": [], "results": [], "metrics": {"_totals": {"loc": 100}}}
    assert source.covered_and_clean(clean)
    assert not source.covered_and_clean({**clean, "results": [{"test_id": "B314"}]})
    for report in ([], {"metrics": []}, {"metrics": {"_totals": []}}, {}, {**clean, "errors": [{"filename": "unreadable.py"}]}, {**clean, "metrics": {"_totals": {"loc": 0}}}):
        with pytest.raises(ValueError): source.covered_and_clean(report)
