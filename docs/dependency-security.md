# Dependency security and automated checks

The `Security and regression checks` GitHub Actions workflow runs on pull
requests, pushes to `main`, and manual dispatch. A Monday 05:37 UTC schedule
runs dependency and Python source scans so newly published advisories can be
found without a code change. Scheduled runs omit the API and web regressions.

## Merge checks and reports

- **Dependency and source security** validates Python lock consistency, audits
  the full runtime, test and security-tool graphs with `pip-audit`, audits the
  full npm workspace lockfile, and scans production Python with Bandit.
  Python advisories of any severity fail. npm high/critical findings fail;
  lower severities remain visible in the summary and JSON reports. Bandit
  medium-or-higher severity findings with medium-or-higher confidence fail.
  Tool failures, missing/invalid reports and skipped Python audit coverage fail.
- **API regression (sqlite)** and **API regression (postgres)** install the
  hash-verified test graph and run the complete backend suite. PostgreSQL uses
  a disposable service and applies Alembic migrations first. Native PDF/OCR
  tools are installed; external providers and workers remain disabled.
- **Web and shared-client validation** performs a clean npm install, checks
  web/mobile/shared TypeScript, lints the frontend and builds Next.js. The build
  uses a local unavailable API address to exercise build-time fallbacks; it is
  a validation build, not a deployment artifact.
  It also runs Chromium keyboard/mobile regressions and axe accessibility checks
  at desktop and phone widths ([accessibility runbook](accessibility.md)).

JSON security reports and API JUnit results are retained for seven days, even
when a check fails. Actions use immutable commit references, repository access
is read-only, and no deployment/provider credentials are needed. Dependency
checks require PyPI and npm advisory services; outages fail the check.

After this workflow first runs on GitHub, a repository administrator must make
all four check names above required in the `main` branch ruleset/protection
settings to block merges. Adding a workflow does not configure branch rules.
No GitHub Actions run is claimed by the local validation recorded below.

## Python installs and reviewed updates

Locks target Python 3.12 on Linux. Edit `backend/requirements.in` for runtime
dependencies, `backend/requirements-dev.in` for test-only dependencies, and
`ci/security-requirements.in` for scanner tooling. Every resolved dependency is
pinned with distribution SHA-256 hashes. The test lock constrains all runtime
versions to the production lock; pytest and moto are excluded from the runtime
install. Docker installs `backend/requirements.txt` with `--require-hashes`.

From the repository root:

```bash
python3.12 -m venv .venv-security
source .venv-security/bin/activate
python -m pip install --require-hashes -r ci/security-requirements.txt
bash scripts/lock-python.sh
# To request a reviewed upgrade, pass --upgrade-package NAME to that script.
python scripts/check_python_locks.py
python scripts/audit_dependencies.py
python scripts/scan_python.py
```

Review the resulting lock diff, reinstall into a fresh environment and run the
regressions before committing an update. Regenerate all three locks together;
do not hand-edit hashes or add audit suppressions to make an update pass.
Use a separate application/test environment:

```bash
python3.12 -m venv .venv-api
source .venv-api/bin/activate
python -m pip install --require-hashes -r backend/requirements-dev.txt
python -m pip check
cd backend
python -m pytest -q
```

Tests use in-memory SQLite unless `TEST_DATABASE_URL` is set. PostgreSQL tests
drop and recreate application tables: only point them at a disposable test
database. Run pytest from `backend`, as the suite expects that working directory.

## Findings and validation (2026-11-09)

The Python audits found advisories affecting Pillow 12.3.0 and pytest 8.4.2.
The reviewed locks now use Pillow 13.0.0 and pytest 9.2.0; runtime, test and tool
audits report no known vulnerabilities. Static analysis identified unsafe XML
parsing of uploaded DOCX documents. Parsing now rejects DTDs and entity payloads
with `defusedxml`. The reader also rejects uploaded images with oversized pixel
dimensions before OCR or vision conversion. Regression tests cover those boundaries and
the audit failure policies.

The full npm workspace audit reports **15 moderate findings and no low, high
or critical findings**. These include dependent packages in the `glob` and
`minimatch` chains used by Expo/ESLint (GHSA-3g3m-2fjr-6pw4 and
GHSA-g3hv-75wg-m249). They remain open. Recheck compatible upstream updates;
do not use `npm audit fix --force` or override transitive major versions without
compatibility testing. Counts can change as registries publish advisories.

The earlier JavaScript security update moved the site to Next.js 16.4.3 and
React/React DOM 19.3.1, adopted asynchronous route parameters and ESLint flat
config, and aligned the Expo SDK 58 dependency versions. CI now uses Node 24.
Clean npm installation, all-workspace typechecking, frontend lint and production
build pass locally. Lint retains existing warnings. Native mobile builds remain
untested. Source/dependency checks do not replace container/OS patching,
authorization review, penetration testing or legal/privacy review.

Local API validation passed on the locked test environment: 384 tests passed on
SQLite (13 database-specific skips), and 396 passed on PostgreSQL 16 (one
time-dependent meeting-test skip). The final document-reader and audit-policy
tests passed separately: 25 tests, including malformed-report failure cases.
The workflow also passes `actionlint`, all Python locks validate, and Bandit
reports no findings at the configured threshold.
