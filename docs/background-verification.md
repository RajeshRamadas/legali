# Durable background verification

The case's **Property verification agent** now uses **Queue verification** for
full-case local extraction or LLM evidence analysis. Requests save quickly to
PostgreSQL and return a job status rather than holding the browser request while
reading files or contacting a provider. Staff can leave the case and return;
**Recent analysis jobs** reloads the latest 20 requests. Earlier saved evidence
runs and advocate report/approval rules keep their existing behavior.

The page polls active jobs every five seconds while visible. **Refresh analysis
jobs** checks manually. Completion refreshes saved evidence runs without replacing
unsent case replies or review settings. Lookup failures label the last loaded
status as potentially out of date and preserve settings. Job data and submission
references are not saved in browser storage.

## Worker deployment

Deploy the API, website and dedicated worker from the same revision. Back up and
verify the database, stop old instances, and run `python -m alembic upgrade head`
from `backend`. Head `0041_verification_jobs` creates an empty job table, its
indexes and constraints; it does not process or replay historical evidence.
Migration up/down/up on an empty job table preserves existing runs/audit records.
Downgrade refuses if any job history is retained, including cancelled or finished
jobs. Use a forward fix or reviewed recovery.

The worker requires PostgreSQL and the API's database, storage credentials/volume,
OCR language packs, provider/models, page-image policy and curated law revision:

```bash
cd backend
python -m app.verification_jobs          # process at most one job
python -m app.verification_jobs --loop   # poll every ten seconds
```

The optional Compose profile shares the API environment and storage volume:

```bash
docker compose -f infra/docker-compose.yml --profile verification up -d --build verification-worker
```

Apply migrations before starting the worker. Use the deployment's reviewed env
files/settings with the command. The API does not start this worker automatically.
Each worker tick checks the current schema and audit guards before claiming work;
misconfigured workers stop with a safe configuration failure instead of processing.
Until a worker is running, accepted requests remain **Queued · waiting for a
worker**. Review the backlog and processing authorization before enabling it.
The normal development preview keeps provider/delivery workers disabled; no live
provider calls are needed to validate this feature.

System health shows queued/running counts, interrupted jobs, failures over 24
hours and the external verification worker's observations. A queued job without
an observed worker needs attention. Worker observations describe completed worker
checks, not legal correctness or guaranteed provider availability. No case text,
file names or provider response bodies appear in the operator snapshot.

## Claims, progress and interruption

Workers claim queued rows with `FOR UPDATE SKIP LOCKED`, commit a unique claim
token and a 15-minute lease, then release their database session. Analysis uses a
detached value snapshot; no database connection or case-row lock spans OCR or
provider calls. Short checkpoints before files/provider calls renew the lease
and save Reading/Analysing/Checking-and-saving progress.

An expired or missing lease is **interrupted**. A worker sweep or a new submission
retires that attempt as failed; it never automatically requeues provider work.
Late workers cannot renew an expired claim or publish after its token is revoked.
A crashed worker may already have contacted a provider, so blind automatic retry
could duplicate processing or cost. A database failure at publication rolls back
the result and leaves the lease to be recovered, rather than replaying analysis.

One active queued/running job is permitted per case, enforced by a partial unique
index and short case-row submission locks. New requests share the existing
one-minute case cooldown with saved analyses. Submission references make an
unchanged HTTP retry idempotent, while reuse with different settings is rejected.
The browser reuses its reference after an uncertain submission failure and loads
saved jobs on return, instead of automatically submitting again.

## Access, evidence and consent

Every API read/write requires current staff case access. Workers check that the
requester is still active staff with case access before processing, at checkpoints
and before accepting a result. A request can survive session expiry, but loss of
the underlying staff/case authorization stops it. Only the requester or an
administrator with case access may cancel a job.

Submission validates clean scans, bounded file count, state/intake agreement and
existing provider/consent rules without reading file bytes or contacting a model.
The job retains a fingerprint of evidence metadata, property/intake/checklist,
case/report status and processing settings. File bytes are read only during
processing and checked against their recorded hashes. Changed evidence, case
status, access, law/OCR settings or provider/model/endpoint/image settings stops
the old request. A configuration revision binds LLM submission to the settings
shown for consent; stale settings must be reloaded and reviewed.

Normal result staleness and advocate approval checks also remain in force after
completion. Changes after publication can make a saved analysis stale. There is
no automated checklist approval, signed opinion or title clearance.

**Cancel analysis** revokes the claim and prevents result publication and later
checkpoints. A provider request already in progress cannot be recalled. Failed,
stale, cancelled or interrupted requests offer **Review a new analysis**. This
does not submit anything: it clears external-processing consent and asks staff to
review current settings before explicitly queueing a new request. The one-minute
cooldown still applies. Provider errors are sanitized, incomplete LLM work is not
accepted as a new run, and old saved analyses remain available.

## API and storage

- `POST /api/v1/admin/tickets/{number}/verification/jobs` → 202. Send existing
  `state`, strict boolean `use_llm`/`consent_to_external_processing`, UUID
  `submission_key`, and the config endpoint's `configuration_revision` for LLM
  processing. State is trimmed and rejects control characters. Extra fields and
  malformed payloads return 422; active/stale-setting conflicts return 409.
- `GET .../verification/jobs?page=1` → up to 20 jobs, newest first; pages 1–10000.
- `POST .../verification/jobs/{id}/cancel` → current status; cancellation is
  idempotent. Other-case jobs return 404; unauthorized cancellation returns 403.

Responses allowlist job ID, status/phase, times, state/mode, optional saved run ID,
safe message and cancellation permission. They omit claim tokens, leases,
fingerprints, submission references and internal requests. Authentication failures
are private/no-store; reads share lookup budgets, new jobs use expensive-action
budgets and cancellation uses the write budget. Legacy synchronous analysis
remains available for compatible clients but cannot run beside an active job.

Jobs store request settings, timestamps, fingerprints and references, not document
text, storage paths, provider keys or response bodies. Accepted results use the
existing protected verification-run storage/retention controls. Minimal lifecycle
audit entries are appended transactionally and appear in Activity history. This
feature adds no notification sends and does not replace retention/evaluation/cost
policies. Upload classification and staff per-file rechecks remain separate.

## Verification

Run tests from `backend` using disposable data only; fixtures drop/recreate tables:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_verification_jobs.py tests/test_verification_jobs_migration.py tests/test_verification.py
```

Dedicated PostgreSQL checks exercise exclusive claims and case updates during
paused analysis. Tests cover local completion, idempotent submission, authorization
changes, cancellation, expired/missing leases, stale evidence/configuration,
consent binding, sanitized failures, budgets, worker health and guarded rollback.
Browser fixtures cover queuing, navigation/resume, completion, preserved reply
drafts, cancellation, consent, uncertain HTTP retry, status failures and denied
cases across desktop/phone/narrow layouts. Provider calls use stubs only.

Local verification on 11 November 2026 passed the full SQLite suite (821 tests,
44 skips), PostgreSQL regressions (101 tests, one SQLite-specific skip), and 60
browser checks. Final worker/validation/recovery additions passed another focused
run of 37 SQLite tests (three PostgreSQL-only skips) and 40 PostgreSQL tests. The
documented standalone worker command also completed on the disposable PostgreSQL
database. Exclusive claims and nonblocking case updates were exercised on real
PostgreSQL. Empty-table migration up/down/up preserved existing guarded audit data.

Type checks, production builds and the Bandit gate passed; lint had no errors and
seven existing warnings. Default staging/production Compose rendering and the
optional verification profile's shared database/storage/provider settings passed.
Browser axe/overflow checks passed; queue screenshots were reviewed, with fixed
navigation recaptured after resetting scroll and focus.

A private database backup was verified before updating the local preview to
`0041`. API health/readiness, homepage and operations returned 200. Anonymous job
GET/POST returned 401 with private/no-store caching. Existing audit guards and an
empty normal-preview job queue were verified read-only. No real verification jobs
were submitted or processed in the normal preview; no provider calls or messages
were sent. The optional worker remains off there, existing delivery/background
flags remain false, and the disposable PostgreSQL database was removed.
