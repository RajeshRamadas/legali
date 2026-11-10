# Isolated API performance checks

The `API performance checks` workflow runs a bounded HTTP workload against a
temporary API and dedicated PostgreSQL 16 service. It runs on pull requests,
main pushes, manual dispatch and Tuesdays at **08:47 IST** (03:17 UTC). No live
application URL, provider credentials or customer sessions are needed.

## Workload and limits

`ci/performance.json` defines nine GET scenarios: liveness, database readiness,
service catalogue, lawyer and RERA searches, customer account/support reads,
and administrator ticket/support queues. The default fixture contains 20
synthetic customers, 200 cases, 200 support requests with private notes, eight
lawyer profiles and 40 explicitly synthetic RERA projects.

Each scenario has two warm-up requests followed by 32 measured requests, paced
at 20 requests/second with at most four concurrent requests. The report includes
p50/p95/p99 client latency, completed throughput, status/error counts and dispatch
lag. Latency measures the request/body read, not time waiting to be dispatched.
Dispatch lag helps identify a saturated driver or service. These are controlled
baseline checks, not proof of an open-loop arrival rate or production capacity.

The initial CI gate requires **p95 <= 1500 ms and zero measured errors** for every
scenario. Warm-up errors also fail. HTTP 429, redirects, authorization failures,
invalid/oversized JSON and response-contract failures count as errors. Requiring
nonempty seeded results prevents a fast empty database or sign-in page from
passing. A missing identity, invalid profile, setup/driver failure or incomplete
global deadline fails the command. Reports from an earlier run are removed first.

Profiles have hard limits: 32 concurrent requests, 200 requests/second, 1000
measured requests per scenario, 12 scenarios, 5000 total requests including
warm-ups, ten-second request timeouts and a 300-second measurement deadline.
The checked-in deadline is 120 seconds. Review profile changes as test-budget
changes; do not raise limits merely to hide a regression. Agree deployment
capacity/SLO targets separately.

## Isolation and data handling

The launcher requires `APP_ENV=performance` and a PostgreSQL database named
`legali_perf_*`. It checks for business data **before migrations** and again
inside the seed transaction; populated databases are refused. It never deletes
or resets existing records. Seeding is bounded, serialized and transactional.
Only roles/service catalogue and Alembic metadata can already exist.

The launcher creates temporary signing/encryption keys and verified synthetic
customer/admin sessions. The administrator fixture has a valid encrypted MFA
seed and a token with MFA confirmation; normal endpoint authentication, account
and role checks remain enabled. Login, OTP/MFA challenges and provider delivery
are not load-tested. Workers, retention and all configured providers/bootstrap
accounts are disabled or cleared in the child environment. Lookup/write budgets
are raised **only in that isolated API**, and recorded in the report, so 429
responses do not hide actual query performance. The application defaults are
unchanged. Normal request logs/budget counters still update inside the fixture.

The workload driver accepts loopback HTTP origins and GET requests only, does
not follow redirects, and bounds response bodies. Aggregate JSON/Markdown
reports include scenario labels and counts, not URLs, response bodies, query
strings, tokens, database credentials or exception messages. Private identity
files are mode 0600 inside a temporary directory. The API process/private files
are cleaned up on normal completion/failure; the database is deliberately left
for inspection and is destroyed with the CI service. After an interrupted local
run, check that port 8766 is free before trying again.

## Run locally

Use the hash-verified backend environment and a **new empty PostgreSQL database**
with the reserved prefix. Set `DATABASE_URL` through your local environment or
secret tooling; never point it at the normal `homexo` database.

```bash
# From the repository root, after setting DATABASE_URL for legali_perf_<run>:
export APP_ENV=performance
python -m scripts.performance.check
```

The command applies migrations, seeds fixtures, starts a local API on port 8766,
waits for readiness, runs the workload and writes `performance-reports/results.json`
and `results.md`. Use `--port` for another unprivileged free port and `--profile`
for a reviewed profile. A repeated run needs a fresh database; the command will
not clear the previous run's data. Remove only the disposable database you created
when finished. No Docker execution is required by the launcher itself.

The lower-level `python -m scripts.performance.run` can check an already-running
loopback fixture using `PERF_CUSTOMER_TOKEN`/`PERF_ADMIN_TOKEN` environment variables.
Prefer the isolated launcher; never put session tokens in command arguments or
upload private fixture/process logs. Git ignores generated reports. CI retains
only aggregate results for seven days. After the first trusted GitHub run, a
repository administrator can make **Isolated API performance** required in branch
protection; the workflow does not change repository rules.

## Validation and measured improvement (2026-11-10)

The first local run found per-row case/account metadata reads in the support
queue. Page serialization now fetches ticket numbers and customer summaries in
batches. A query-count regression test checks that fetching 20 rows does not
add a query per row, while ownership and internal-note isolation remain tested.

| Scenario | Before p95 | After p95 |
| --- | ---: | ---: |
| Administrator support queue | 1808 ms | 75 ms |
| Customer support list | 921 ms | 43 ms |

Both runs used the same profile/cardinalities on fresh synthetic databases.
The improved run completed all nine scenarios, 288 measured requests and 18
warm-ups with zero errors; every p95 was below 220 ms locally. Hardware/load and
query/data distributions affect these numbers; they are not deployment promises.
The full SQLite API suite passed 437 tests (15 skips). Separate PostgreSQL
support regressions and negative isolation checks cover the optimized paths.
Benchmark tests exercise throttling, invalid/oversized responses, warm-up errors,
latency/deadline failures, identity guards, redaction and dirty-database refusal.

Before launch, run representative staging capacity/soak tests with realistic data
volumes and deployment workers. Write-heavy flows, uploads/OCR, bookings/payments,
external services, worker throughput, real login traffic and browser rendering
remain outside this smoke workload. Use the [incident runbook](incident-response.md)
when a deployment check fails.
