# Deployment configuration preflight

Staging and production now refuse unsafe API configuration before database
bootstrap or background workers start. Use the canonical `APP_ENV` values
`staging` and `production`. `development`, `test` and the reserved `performance`
fixture mode remain supported; other environment names are refused.

This is an **offline configuration check**, not a launch approval or a service
health probe. It does not connect to a database, scanner, storage bucket or
provider, run migrations, create an administrator, send a code or take payment.
Reports contain check identifiers and fixed guidance, never supplied values,
connection strings or credentials. Signing-key length/placeholder checks cannot
prove randomness, uniqueness across deployments or safe secret storage.

## Profiles and secrets

The existing `.env.example` is for local development. Start from
`infra/environments/staging.env.example` or `production.env.example` for deployed
configuration. Copy it to a private `staging.env`/`production.env` file (Git ignores
these files), restrict file permissions and replace the blank/invalid settings
through your deployment's secret tooling. Examples intentionally fail until real
settings are supplied. No deployment or provider credentials are included.

Use different signing/Fernet keys, databases, storage and provider credentials
for staging and production. Generate JWT signing material with a cryptographic
random generator (at least 32 characters) and a separate Fernet key with
`cryptography.fernet.Fernet.generate_key()`. Keep generated values in the secret
manager, not shell history, Git, reports or support records.

| Check | Deployed policy |
| --- | --- |
| Environment and JWT | Target matches `APP_ENV`; signing secret is long and avoids known development/placeholder/repeated values |
| Staff MFA | Dedicated valid Fernet key, distinct from JWT; administrator MFA required |
| Development shortcuts | `LOGIN_CODE_DEV_MODE=false`, `PAYMENTS_TEST_MODE=false`, `RERA_SAMPLE_WHEN_EMPTY=false`; misspelled boolean values fail |
| Database | Explicit PostgreSQL URL; default/placeholder or explicitly empty passwords are refused; external authentication can omit the URL password |
| Public address/CORS | HTTPS origins with no user information, paths beyond `/`, queries, fragments, wildcards, literal loopback or example addresses; CORS includes the public site |
| Bootstrap | Email/password absent together, or a real email and a strong one-time password; remove both after bootstrap |
| Razorpay | Off with no provider credentials, or a complete key/secret/webhook set; staging uses `rzp_test_`, production uses `rzp_live_` |
| Storage/WhatsApp | Supplied credential pairs must be complete; S3 custom endpoints use HTTPS; IAM credential chains remain supported |

Allowed CORS origins are normalized in the deployed API to the browser's origin
format, including IDNA host names and omitted default ports. A trailing `/` or
explicit `:443` cannot produce a passing check with broken CORS.

Warnings remain visible for checks requiring an operator: database TLS and
least privilege, bucket privacy/encryption or durable local volumes, actual
WhatsApp template/code delivery, migrations, ClamAV signatures, worker scheduling,
alert routing, backup/recovery and legal/support ownership. Missing WhatsApp
credentials mean customer phone sign-in is unavailable, even if configuration
passes. A zero exit code does not establish those capabilities.

## Native API / deployment platform

Inject the selected environment into the process with your platform or secret
tool, then run from `backend` using the hash-verified Python environment:

```bash
python -m app.deployment_check --target staging
python -m app.deployment_check --target production --json
```

Select the command matching the intended target. Exit **0** means configuration
policy passed, with manual checks still reported; exit **1** means settings failed.
The CLI works even when importing `app.config` would refuse to start. JSON includes
`configuration_passed`, failure/warning counts and check results. Review reports
before attaching them to deployment records.

Regular API and Alembic imports enforce the same policy automatically. Changing
environment values after import does not reconfigure a running process; restart
with the reviewed settings. Do not use a development/test/performance label to
bypass deployment guards.

Configure the website separately: build Next.js with the environment's public
HTTPS `NEXT_PUBLIC_API_BASE_URL`; use an appropriate `API_INTERNAL_BASE_URL` for
server access if needed. Public Next.js settings are compiled into the bundle.
Keep API/payment/signing secrets out of `NEXT_PUBLIC_` variables. This backend
command does not inspect the built website or its environment.

## Compose wiring and CI

The local Compose stack now forwards development flags and notification worker
selection. Explicitly empty bootstrap fields stay empty instead of falling back
to development credentials. Compose keeps its internal ClamAV service; native
deployments supply their own scanner host/port. The persistent document volume
remains mounted at `/data/storage`.

With the API image built through the approved build process, check a private
profile from the repository root without starting dependencies or running the
default API/migration command:

```bash
docker compose -f infra/docker-compose.yml --env-file infra/environments/staging.env \
  run --rm --no-deps api python -m app.deployment_check --target staging --json
```

Base Compose publishes database/API host ports and is a local stack; these profiles
do not provision production TLS, network boundaries, secret management, external
services or a production orchestrator. Use the deployment team's reviewed topology
and release procedure for actual staging/production.

`python scripts/check_deployment_profiles.py` renders both examples with temporary
generated fixture values and validates the **rendered API environment**. It checks
that bootstrap stays off and development flags stay disabled, ignores operator
`.env` files/inherited application values, deletes its private fixture file and
never starts containers or contacts a daemon. It requires Docker Compose and the
backend Python dependencies. Only fixed summaries are printed. The SQLite API CI
job runs this check; existing check names are unchanged.

## Validation (2026-11-10)

- Full SQLite API suite: **490 passed, 15 skipped**, including 53 deployment-policy
  regressions for invalid/partial settings, URL handling, output redaction,
  template refusal, CLI exit codes and startup before database import.
- Both profiles pass actual Compose rendering with temporary settings. Unfilled
  templates are deliberately rejected.
- Staging and production API processes passed migrations, liveness/readiness,
  allowed canonical CORS and rejected local CORS against a disposable PostgreSQL
  database owned by a limited temporary role. Providers/workers were disabled;
  the database and role were removed afterward. No deployment was performed.

Complete external checks and use [operations monitoring](operations-monitoring.md),
the [backup runbook](backups.md), [performance checks](performance-checks.md) and
the [incident runbook](incident-response.md) during release verification.
