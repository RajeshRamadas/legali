"""Run Bandit and reject incomplete source coverage as well as reported findings."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def covered_and_clean(report):
    if not isinstance(report, dict) or not isinstance(report.get("metrics"), dict) or not isinstance(report["metrics"].get("_totals"), dict):
        raise ValueError("Source scan did not produce a complete report")
    errors, findings = report.get("errors"), report.get("results")
    lines = report.get("metrics", {}).get("_totals", {}).get("loc")
    if not isinstance(errors, list) or errors or not isinstance(findings, list) or type(lines) is not int or lines <= 0:
        raise ValueError("Source scan did not cover the requested Python files completely")
    return not findings


def scan(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        result = subprocess.run([sys.executable, "-m", "bandit", "-r", "backend/app", "infra/backup/backup.py", "scripts",
            "-ll", "-ii", "-f", "json", "-o", str(destination)], cwd=ROOT, check=False, timeout=180)
        clean = covered_and_clean(json.loads(destination.read_text()))
        return 0 if result.returncode == 0 and clean else 1
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("Source scan failed or its report was incomplete.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "security-reports/bandit.json")
    args = parser.parse_args()
    sys.exit(scan(args.output.resolve()))
