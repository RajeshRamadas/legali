"""Report deployment configuration without importing app.config or contacting services."""
import argparse
import json
import os

from .deployment import inspect_environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("staging", "production"), required=True)
    parser.add_argument("--json", action="store_true", help="Write a sanitized machine-readable report to stdout.")
    args = parser.parse_args(argv)
    report = inspect_environment(os.environ, args.target)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Deployment configuration: {args.target}; {report['failures']} failures, {report['warnings']} manual checks")
        for item in report["checks"]:
            print(f"{item['status'].upper():7} {item['id']}: {item['message']}")
        print("Configuration checks do not establish service availability or production readiness.")
    return 0 if report["configuration_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
