# Operational monitoring

Administrators can open **System health** at `/admin/operations`. Agents and customers cannot access its API. It shows a fresh database/schema check, shared worker observations, notification due/scheduled/delayed counts, failed deliveries over 24 hours, scan/quarantine counts, missed-case alerts and failed research scans. No recipients, document names, case/customer identifiers, provider errors or secrets appear in the snapshot. The page refreshes every 30 seconds while visible; a failed refresh prominently marks retained data as an old snapshot. It never retries deliveries, scans documents or contacts providers.

Apply migration `0022_operations_monitoring` (`cd backend && alembic upgrade head`) and restart API/external workers. This adds the small `worker_pulses` table without changing customer or case data. All processes in a deployment must share the database and application revision. The admin API refuses a mismatched migration revision.

## Liveness and readiness

- `GET /health` remains a cheap process-liveness check; database failure does not make it fail.
- `GET /ready` returns **200** `{ "status": "ready" }` only when PostgreSQL is reachable and its Alembic revisions match the running application. Otherwise it returns **503** `{ "status": "not_ready" }`, without disclosing database details. Probe responses are not cached. Readiness is exempt from application rate budgets.

PostgreSQL readiness uses a separate unpooled connection with a 3-second connection timeout and 2-second statement timeout, so it does not wait for a saturated application pool. DNS/network behavior can add latency outside database query execution. Readiness tests database/schema availability, not every table's integrity, external providers, workers or backups. Monitor both endpoints from outside the application; use readiness for routing traffic and liveness for process restarts. Do not restart a healthy API repeatedly just because its database is unavailable.

## Worker observations and queue warnings

`python -m app.notify` and `python -m app.notify --loop` report the notifications/deadlines group, as does the API's in-process worker. It covers booking expiry, daily agendas, case deadline reconciliation and due delivery. The research scheduler and `python -m app.blog_agent run` report the case-research group. Manual research scans/drafts keep their existing history under the research desk; they are not scheduler heartbeats.

Each group stores its latest start/completion, last success/failure, duration and a fixed error category. Updates are atomic across processes and older completion timestamps cannot overwrite newer observations. The latest successful completion means **at least one worker in the group** succeeded; it does not prove every process is healthy. Only two named group rows exist, with bounded failure counters and no unbounded event table. Clock synchronization matters. A lack of recent completions is highlighted after `max(3 × poll interval, 5 minutes)`; research polls every 15 minutes. A long-running job can become stale while still working. A disabled in-process notification worker can be healthy when an external worker is observed. Research disabled without a recent observation is neutral.

Observation-write failure produces a fixed log event and does not prevent the underlying work from running. Actual task failures retain their existing failure behavior; loops continue, while single-shot worker CLI commands exit nonzero. Fixed categories are `database_error`, `worker_not_configured` and `task_failed`; investigate logs and the relevant case/research/delivery history. Research scan failures are also counted separately because a scheduler check may finish successfully after a scan records its failure.

`OPS_QUEUE_WARN_MINUTES` (default **15**) determines delayed notification and pending-document counts. Due times use `send_after` or creation time. Future reminders are scheduled work, not a stalled backlog. Failed deliveries use the most recent attempt time, falling back to creation time, within the last 24 hours. In-app notifications are excluded from provider delivery counts. A configured channel means its required credentials/settings are present; it is **not** a live provider availability check. Unconfigured channels with due work, stale/failed expected workers, delayed/failed delivery or scan work, threats, and outstanding alerts cause an attention summary. The dashboard has no automatic resend control because ambiguous provider outcomes require review.

## Request references and logs

Every application HTTP response carries a server-generated **`X-Request-ID`**. Client-supplied IDs are not trusted. Allowed CORS origins can read it, and administrator errors include it for support. Preflight responses handled directly by CORS do not have an application reference. Unexpected errors before response headers become a generic private/no-store **500** with the same `request_id` in JSON. Stream/background failures after headers cannot change the response status; logs retain that status plus `response_failed`/`background_failed`. Their rethrown server error suppresses original exception text. Client cancellation is recorded separately.

The `homexo.operations` logger emits one-line JSON to stderr:

```json
{"event":"http_request","timestamp":"2026-11-09T10:00:00+00:00","method":"POST","route":"/api/v1/tickets","status":201,"duration_ms":24,"policy":"submissions","request_id":"0123456789abcdef0123456789abcdef"}
```

Routes are declared templates (for example `/api/v1/files/{token}`), or `unmatched` when routing has not occurred. Method, status, duration, known budget group and request ID are bounded metadata. Request bodies, query strings, raw paths, IPs, authorization headers, token values and exception messages are never fields in these events. Successful health probes are omitted to reduce noise; failed probes are logged. HTTP duration ends at the final response body where available, before background work. Worker events are `worker_completed`, `worker_failed` and `worker_observation_unavailable` with a fixed group/category and duration. Worker history beyond the latest observations belongs in the log collector.

The app disables Uvicorn's raw access logger at import/startup, and the Docker command uses `--no-access-log`. For native deployment use `uvicorn app.main:app --no-access-log`. Configure proxy/Gunicorn and third-party loggers separately so they do not reintroduce raw URLs, request data or provider payloads. These events do not sanitize unrelated existing library logs or replace a review of provider logging settings. Keep logs access-controlled and set an organization-approved retention period.

## Alert and incident setup

Use the [incident-response runbook](incident-response.md) for triage, containment,
customer communication and recovery verification. The [isolated API performance
checks](performance-checks.md) provide repeatable baselines without loading the
live service.

Connect stderr JSON events and endpoint checks to your hosting provider's log/monitoring system. No external telemetry service or alert recipient is configured by this feature. Recommended alerts are repeated `/ready` failures, sustained HTTP 5xx/latency increases, `worker_failed`/observation failures and stale worker observations or growing delayed queues. Restrict automated access to `/api/v1/admin/operations` to an appropriate staff-admin session; it is not a public metrics endpoint. For expired sessions, use external readiness/log alerts instead of bypassing staff MFA or ownership checks.

Use the request reference to find the corresponding event, then inspect the relevant worker, provider or case history. Verify database availability/migrations before restarting workers. Inspect provider outcomes before resending messages. For backup freshness and actual recoverability, follow [the backup runbook](backups.md); application health does not claim that backups or off-host copies are safe. Document alert routing and test incident response before production.

Validation: run `pytest tests/test_operations.py` from `backend/`. A disposable PostgreSQL `TEST_DATABASE_URL` enables the concurrent-worker test; never point the pytest runner at a live database, because its fixtures drop tables.
