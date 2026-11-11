# Administrator activity history

Open **Activity history** in the administrator navigation (`/admin/activity`) to
review retained platform audit entries. Activity groups include services, case
work, staff/security, support, privacy/retention, policies, consultation reviews,
scheduling, refunds, notification preferences and publishing/research.

Choose a group, enter part of a current staff display name, set optional From/To
dates, or expand **Find a record by reference** and paste a record UUID from an
entry. Choose **Apply activity filters**. Date boundaries are inclusive calendar
days in `Asia/Kolkata`; displayed timestamps explicitly use IST. Staff-name
matching is literal, case-insensitive substring matching for supported database
characters, with `%`, `_` and backslash escaped. Names are current user display
names, not historical identity snapshots. Entries without a resolved actor are
labelled unattributed; they may represent customers, automated work or former
staff, and the view does not infer which.

Each entry shows a safe activity label, group, recorded time and actor label.
Expand **Entry references** for the entry UUID, record type and, where supported,
the record UUID. Use the service, case, support or other relevant workspace for
decision details. This general index does not display private reasons or
customer content.

## Paging and refresh

**Older activity** loads the next page by recorded time and UUID, newest first.
Tied timestamps have a deterministic UUID order. Newer inserts do not displace
the older cursor sequence. **Newer activity** uses cached pages from the current
view. **Refresh activity** returns to the first page of the applied scope and
keeps unapplied filter edits. Applying or clearing filters starts a new view.

Typed filters do not trigger background lookups. Applied filters are shown above
the results, separately from edited inputs. A failed lookup keeps the last
successful page and its applied scope, labels it potentially out of date, and
keeps typed filter edits. Errors and successful manual navigation/refresh receive
keyboard focus. The page does not automatically refresh or store audit records
or filter drafts in browser storage. Leaving the page discards local state.

## API, privacy and scope

`GET /api/v1/admin/activity` accepts:

- `category`: `all` or one of the categories returned in `categories`.
- `actor`: optional current staff display-name substring, at most 100 characters;
  control characters are rejected.
- `from_date`, `to_date`: optional ISO calendar dates; From must not follow To.
- `record_id`: optional exact UUID identifying the affected record.
- `page_size`: 1–50, default 25.
- `cursor`: the opaque `next_cursor` returned by the preceding page.

The response contains `items`, `categories`, `checked_at` and `next_cursor`.
Each item is limited to `id`, `at`, `actor`, `category`, `activity`, `record_type`
and nullable `record_id`. A cursor controls only the page boundary; it grants no
access and never replaces the requested filters. Malformed, oversized or
timezone-free cursors return 422. Invalid filters also return 422.

Administrator authentication is required: absent/customer credentials receive
401, agents receive 403. Responses, including authentication failures, use
private/no-store caching and vary on authorization. Reads share the existing
private lookup budget and return 429/Retry-After when exhausted. There are no
create, edit, delete, export or replay operations on this route.

SQL selects only the columns needed for the response. It does not load audit
metadata, request IDs, IP hashes, staff contacts, secrets, message bodies,
publication text or question definitions. Action and record-type labels use an
explicit vocabulary. Unknown action text becomes **Other recorded activity**;
unknown record-type text becomes **Other record**, with its target UUID omitted.
The unknown raw strings are never returned. Actor names and IDs render as text.

This is an index of retained `AuditLog` records, not a complete security log or
proof that every platform action was recorded. It does not backfill historical
events or add missing event producers. [Database audit guards](append-only-audit.md)
now protect `audit_logs` from data rewrites and deletion; manual task writes also
produce safe activity entries. Existing case timelines, form/policy publication histories and other
specialist decision histories keep their current permissions and data. Review
access and database ownership operationally before production use.

## Deployment and validation

Deploy API and website together. Back up the database, stop old API instances
and run `python -m alembic upgrade head` from `backend`. Migration
`0039_activity_history_index` adds only a `(created_at, id)` index to `audit_logs`;
it does not rewrite or remove records. Downgrade to `0038_service_intake_forms`
removes only this index and preserves audit data. Index creation can briefly
block writes on a large audit table; plan the maintenance window accordingly.
No new dependencies, credentials, providers or background workers are required.

Run tests from `backend` against disposable data only; fixtures drop and recreate
application tables:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_activity.py tests/test_activity_migration.py
```

Use a dedicated disposable PostgreSQL database to verify filtering, cursor ties
and migration up/down/up. Backend tests check role boundaries, no audit mutations
or notifications on reads, safe response/SQL fields, unknown action redaction,
combined filters, literal wildcard handling, IST midnight boundaries, tied
timestamps, insertion during pagination, invalid cursors/dates and shared lookup
budgets. Browser fixtures cover filters, cached paging, unapplied edits,
refresh/apply/initial failures, empty results, agent boundaries, axe and
desktop/phone/narrow layouts. Fixtures intercept APIs and do not write real
history records.

Local verification on 11 November 2026 passed the full SQLite suite (767 tests,
40 skips), PostgreSQL regressions (100 tests) and 48 browser checks. PostgreSQL
index up/down/up preserved a retained private audit payload; the disposable test
database was removed afterwards. Type checks and production builds passed. Lint
had no errors and seven existing warnings; Bandit passed its medium/high severity
gate. Desktop and phone screenshots were inspected, with axe and overflow checks
passing on desktop, phone and narrow layouts.

A private local database backup was verified before updating the development
preview to `0039`. API health/readiness, homepage and activity route returned 200;
anonymous activity access returned 401 with private/no-store caching and
authorization variance. The deployed index and schema were checked directly.
No activity records were created or changed for preview fixtures. Delivery and
background workers remain disabled, and no provider messages were sent.
