"""Run all dependency audits and fail closed on findings above policy or incomplete reports."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def evaluate_npm(report):
    if not isinstance(report, dict) or not isinstance(report.get("metadata"), dict):
        raise ValueError("npm audit did not produce a complete report")
    counts = report["metadata"].get("vulnerabilities")
    if report.get("error") or not isinstance(counts, dict) or not isinstance(report.get("vulnerabilities"), dict):
        raise ValueError("npm audit did not produce a complete report")
    if any(type(counts.get(key)) is not int or counts[key] < 0 for key in ("low", "moderate", "high", "critical")):
        raise ValueError("npm audit severity counts are missing or invalid")
    blocked = counts["high"] + counts["critical"]
    return not blocked, {key: counts[key] for key in ("low", "moderate", "high", "critical")}


def evaluate_python(report):
    if not isinstance(report, dict):
        raise ValueError("Python audit did not produce a complete report")
    dependencies = report.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("Python audit did not cover any dependencies")
    total = 0
    for item in dependencies:
        if not isinstance(item, dict) or item.get("skip_reason") or not item.get("name") or not item.get("version") or not isinstance(item.get("vulns"), list):
            raise ValueError("Python audit has skipped or incomplete dependency coverage")
        total += len(item["vulns"])
    return total == 0, {"packages": len(dependencies), "findings": total}


def audit(report_dir):
    report_dir.mkdir(parents=True, exist_ok=True)
    results = []
    jobs = [("python-runtime", [sys.executable, "-m", "pip_audit", "-r", "backend/requirements.txt"], evaluate_python),
        ("python-test", [sys.executable, "-m", "pip_audit", "-r", "backend/requirements-dev.txt"], evaluate_python),
        ("python-tools", [sys.executable, "-m", "pip_audit", "-r", "ci/security-requirements.txt"], evaluate_python),
        ("npm", ["npm", "audit", "--package-lock-only", "--json", "--audit-level=high", "--fetch-retries=1", "--fetch-timeout=30000"], evaluate_npm)]
    for name, command, evaluate in jobs:
        destination = report_dir / f"{name}.json"
        destination.unlink(missing_ok=True)  # Never mistake a stale report for this run's result.
        try:
            if name.startswith("python"):
                command += ["--no-deps", "--disable-pip", "--require-hashes", "--vulnerability-service", "pypi", "--format", "json", "--output", str(destination)]
                result = subprocess.run(command, cwd=ROOT, timeout=300, check=False)
            else:
                with destination.open("w") as output:
                    result = subprocess.run(command, cwd=ROOT, stdout=output, timeout=300, check=False)
            passed, summary = evaluate(json.loads(destination.read_text()))
            results.append({"audit": name, "passed": passed and result.returncode == 0, **summary})
        except (OSError, ValueError, subprocess.TimeoutExpired):
            results.append({"audit": name, "passed": False, "error": "Audit failed or its report was incomplete; inspect the tool output."})
    (report_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    for item in results:
        print(json.dumps(item))
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as output:
            output.write("## Dependency audit results\n\n| Audit | Result | Findings |\n| --- | --- | --- |\n")
            for item in results:
                count = str(item.get("findings", "incomplete")) if item["audit"] != "npm" else f"{item.get('high', '?')} high / {item.get('critical', '?')} critical; {item.get('moderate', '?')} moderate"
                output.write(f"| {item['audit']} | {'PASS' if item['passed'] else 'FAIL'} | {count} |\n")
            output.write("\nPython findings of any severity fail. npm high/critical findings fail; lower severities remain visible. Tool/network failures also fail.\n")
    return 0 if all(item["passed"] for item in results) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "security-reports")
    args = parser.parse_args()
    sys.exit(audit(args.report_dir.resolve()))


if __name__ == "__main__":
    main()
