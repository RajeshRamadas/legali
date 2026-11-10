# Incident response runbook

Assign an incident coordinator, technical on-call, customer-support owner and
backup approver in the deployment team's private directory before launch. Record
the approved paging channel and escalation contacts there; this repository does
not invent contacts or configure an external alert service. Test alert delivery
and run a staged recovery drill before relying on this process.

## Open and classify

Start a restricted incident record with the time (include timezone), environment,
release/commit, affected service, user impact and a coordinator. Use broad counts
and sanitized request references; never paste tokens, credentials, customer
messages/documents or raw provider payloads into the record.

| Priority | Trigger | Immediate coordination |
| --- | --- | --- |
| Critical | Suspected unauthorized data access, widespread outage, incorrect/duplicate financial actions | Page the technical owner and incident coordinator immediately; involve security/legal/payment owners as applicable |
| High | Sustained readiness/5xx failures, blocked private workflows, major delivery/scan backlog | Engage on-call and support owner; agree an update cadence |
| Normal | Limited degradation with a working alternative | Track scope, owner and next update; escalate if impact grows |

These are operational categories, not statutory deadlines. Follow approved legal
and contractual reporting procedures with qualified counsel where applicable.

## Triage with bounded evidence

1. Check `GET /health` and `GET /ready` from outside the deployment. Liveness
   means the process is running; readiness checks database/schema availability.
   Do not restart a healthy process repeatedly because its database is unavailable.
2. Compare the running release/migration revision and recent deployment changes.
   Inspect platform CPU, memory, database connections/locks and disk limits.
   Application readiness does not establish provider, backup or worker health.
3. With an authorized administrator session, review `/admin/operations`, the
   affected case/support queue and delivery/scan history. Keep MFA and ownership
   checks enabled. Use `X-Request-ID` to correlate sanitized operational logs.
4. Bound the time window and affected workflows. Distinguish a slow application,
   saturated database, rate-budget rejection and an unavailable provider. Use
   existing aggregate performance reports as baselines; do not load-test the
   incident's live environment to diagnose it.

See [monitoring](operations-monitoring.md) for event fields, worker observations
and their limitations, and [performance checks](performance-checks.md) for the
isolated workload. Preserve relevant logs with approved access/retention controls.

## Contain and recover

| Symptom | Actions |
| --- | --- |
| Readiness/schema failure | Check database reachability and migration state; remove unready instances from routing. Apply the reviewed release procedure or restore to an empty target; never stamp a migration as applied to suppress a mismatch. |
| Suspected access/data leakage | Restrict affected routes/accounts/integrations, preserve evidence and involve the security owner. Rotate exposed credentials and revoke affected sessions through approved controls. Do not delete business/audit records to hide an incident. |
| Delayed or failed notifications | Review worker observations, provider status and claim/delivery history. Pause affected delivery if needed. Confirm provider outcomes before replaying ambiguous sends. |
| Payment/refund discrepancy | Preserve provider references and reconcile with the payment owner/provider dashboard. Do not blindly repeat charges/refunds or mark an outcome without verification. |
| Document threat or scanner outage | Keep files quarantined and downloads blocked; restore signatures/scanner availability and use the reviewed retry flow. Do not disable scanning to clear a queue. |
| Capacity/latency increase | Check resource saturation and query plans, compare the previous release, then use a reviewed rollback/scale adjustment. Reproduce the workload in the isolated fixture or approved staging environment. |
| Data loss/corruption | Stop affected writes where appropriate, identify the recovery point and follow the encrypted backup/empty-target restore procedure with an approver. Preserve keys and source backups. |

Use [the backup runbook](backups.md) for recovery and actual restore validation.
A code rollback does not reverse database migrations automatically; a destructive
schema downgrade can remove support/privacy records. Review compatibility and
data preservation before changing schema. Keep a record of who authorized each
material action and how it was verified.

## Communicate, verify and close

The support owner links related customer complaints in `/admin/support`, records
customer-safe replies and keeps investigative details in internal notes. Use an
approved status/update channel for broader incidents; no automatic external
message is sent by this runbook. Do not promise a recovery time or refund before
it has been established. Track the next update time even when the cause is unknown.

Before closure, confirm sustained health/readiness, the previously failing
workflow with synthetic/authorized data, stable error/latency/resource trends and
appropriate worker/provider backlog recovery. Confirm financial/document outcomes
separately. Do not treat an HTTP 200 or one healthy worker pulse as full recovery.

Record the impact window, root cause, contributing conditions, recovery actions,
privacy/financial review as needed and evidence links with restricted access.
Assign owners/dates to follow-up fixes and update tests, thresholds, alert routing
and this runbook. Run a staged incident/recovery exercise and document its outcome.
