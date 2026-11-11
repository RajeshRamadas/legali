# Append-only audit records

Migration `0040_append_only_audit` protects retained `audit_logs` with database
triggers. Normal writers continue to insert new events. Existing records cannot
be edited or deleted through ORM operations, direct SQL, bulk deletion or upsert
updates. Corrections must be appended as new events; there is no bypass switch or
audit-edit API. The migration preserves all existing rows, identifiers, actor
references, timestamps and private payloads without rewriting them.

## Database behavior

PostgreSQL uses a statement-level BEFORE UPDATE/DELETE/TRUNCATE trigger. Even an
update assigning the same value is rejected. `INSERT ... ON CONFLICT DO UPDATE`
is rejected, while ordinary inserts and conflict-ignore operations remain
possible. The trigger is enabled ALWAYS, including replica session mode. Cascaded
truncation of a referenced table cannot truncate the audit table either.

SQLite uses BEFORE UPDATE/DELETE triggers and a BEFORE INSERT guard against an
already retained primary key. This prevents `INSERT OR REPLACE` from silently
deleting an existing event when recursive triggers are off. Duplicate-ID inserts,
including conflict-ignore attempts, are rejected on SQLite; normal application
writers use fresh UUIDs. SQLite has no TRUNCATE operation.

The fixed rejection message is **Audit history is append-only. Append a new event
instead.** It does not include the event payload. Failed writes roll back with
their transaction; callers must roll back a failed session before reusing it.

PostgreSQL physical deletion of a referenced staff user is also rejected: its
existing ON DELETE SET NULL foreign key would rewrite the audit actor field.
Use the existing suspension/role-change workflows. They revoke access as before
and append new events without modifying earlier records. Current staff display
names can still change; the activity index shows current names and does not claim
historical identity snapshots. SQLite foreign-key enforcement depends on the
connection's foreign-key configuration; the audit-row guards do not enable it
globally or rewrite existing dangling references.

Customer privacy review and chat-retention operations continue through their
existing workflows; those flows append audit events rather than deleting them.
This feature does not add an audit-erasure workflow or determine a legal retention
period. Review retained legacy payloads, business-record obligations and access
before production use. Any exceptional schema-admin recovery or erasure procedure
must preserve required evidence and follow the organization's reviewed policy.

## Protection boundary

These guards protect data operations on `audit_logs`. A database owner, superuser
or someone able to change schema can remove/replace guards or drop tables. Use
separate migration/owner credentials and a runtime role with only the data
privileges it needs; do not grant runtime schema ownership or trigger-management
powers. SQLite file owners can likewise replace the file or schema.

This is not cryptographic tamper evidence, immutable external storage, a complete
security log or a guarantee that every platform action is recorded. Other tables,
including case timelines and specialist decision records, retain their existing
rules. Historical damage or missing events are not repaired or backfilled.

## Health and readiness

**System health → Audit history protection** reports installed guards, missing or
changed guards, or an unsupported database. The check reads database catalogues;
it never attempts a destructive test. PostgreSQL inspection checks trigger event
flags, ALWAYS mode, unconditional execution, function binding/schema and the v1
function body. SQLite inspection checks all three guard definitions. A trigger
name alone is insufficient. Missing configuration makes overall health show
attention; older API responses without this field also show attention in the UI.

`GET /ready` requires both the current schema revision and configured audit
guards. Missing/changed guards return 503 with the existing generic response.
The administrator operations response adds `audit_history.state` as `configured`,
`missing` or `unsupported`. Existing authentication and private caching apply.
Refresh failures retain a clearly labelled last-successful health snapshot.

The check diagnoses configuration; it cannot prevent a schema owner changing the
database immediately afterwards. Review database ownership and external
monitoring separately. Fix missing guards through reviewed migration/database
administration, then verify readiness and health; the application does not
silently reinstall guards at startup.

## Task audit coverage

Manual task creation appends `case.task_created` with task/assignee references,
source and due time. Effective task edits append `case.task_updated` with task
reference, changed-field names and previous/current status. Task titles, notes
and customer content are excluded from these audit payloads. Unchanged requests
do not create another task-update audit event.

Task changes, case events and audit inserts commit in one transaction. An audit
insert failure rolls back the task write and its case event. Existing case access,
closed-case restrictions, checklist logic and task notifications are unchanged.
The activity index labels these events as **Case task created** and **Case task
updated**. Automatically generated playbook transitions retain their existing
timeline behavior; this change does not backfill individual historical tasks.

## Deployment and recovery

1. Back up and verify the database. Stop old API/worker instances.
2. From `backend`, run `python -m alembic upgrade head` with migration credentials.
   The new head is `0040_append_only_audit`; existing audit data is preserved.
3. Deploy API and website together, restart services with their established
   configuration, and verify `/ready` plus the administrator protection card.
4. Check runtime database privileges and monitor readiness outside the process.

No new dependency, secret or external provider is needed. The PostgreSQL trigger
function/DDL and SQLite definitions are versioned in `app/audit_guard_v1.py`, shared
by migration 0040 and newly metadata-created test databases. Preserve these v1
definitions for migration reproducibility; use a new version for future schema
changes. Metadata creation/drop hooks are for explicit schema administration,
including disposable tests, and do not run on normal API startup.

Downgrading to `0039_activity_history_index` removes only the guards/function and
preserves all rows; it also removes the protection, so it is an explicit schema
administration decision. Prefer a forward fix. New code fails readiness without
the required guards. Restore backups into empty destinations using the existing
[backup runbook](backups.md); verify guard configuration after restore. Do not
disable guards merely to replay a write against existing audit IDs.

## Verification

Run tests from `backend` against disposable data only; fixtures drop/recreate
application tables:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_append_only_audit.py tests/test_append_only_audit_migration.py
```

Use a dedicated PostgreSQL test database for truncation, upsert, actor foreign-key,
restricted-role and replica-mode tests. Tests cover every audit column, ORM/bulk
changes, replacement writes, preservation across upgrade/downgrade/upgrade,
missing/modified guard detection, staff suspension, task privacy/idempotence and
transaction rollback. Restoration regression fixtures represent missing/corrupt
legacy history through initial inserts, without rewriting retained audit rows.
Browser fixtures cover configured/missing/unsupported/older-API states, health
refresh failures, agent boundaries, axe and desktop/phone/narrow layouts.

Local verification on 11 November 2026 passed the full SQLite suite (804 tests,
42 skips), PostgreSQL regressions (120 tests, one SQLite-specific skip), and 42
browser checks. The final PostgreSQL catalog checks were revalidated in 33 tests
(one SQLite-specific skip), including a correctly named ALWAYS trigger with a
false condition. Restricted-role and replica-mode tests ran successfully.
Migration up/down/up preserved a legacy private audit payload. Type checks and
production builds passed; lint had no errors and seven existing warnings. Bandit
passed its medium/high severity gate. Mobile protection-card screenshots were
inspected, and axe/overflow checks passed across all three viewport sizes.

A private local backup was verified before migrating the development preview to
`0040`. Health/readiness, homepage, operations and activity pages returned 200;
anonymous operations access returned 401. Actual schema and unconditional ALWAYS
guard configuration were checked read-only. No destructive probes ran against
the normal preview. Delivery/background flags stayed false, no provider messages
were sent, and the dedicated PostgreSQL test database was removed.
