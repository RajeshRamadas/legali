# Support response deadline alerts

Administrators open **Support alerts** at `/admin/support/alerts`. The list shows
missed team-response targets, the current support owner and any escalation.
The staff navigation and notification bell show the unacknowledged count.
Agents and customers cannot read or acknowledge these private alerts.

Choose **Open support request** to open that exact conversation in the support
queue. Its current reply and ownership workflow remains available, including
revision conflict handling. Refreshing the queue list preserves an unsent reply;
following a link loads the saved conversation rather than restoring a draft from
another page.

## Targets, acknowledgement and escalation

The existing `SUPPORT_RESPONSE_HOURS` target starts with an unanswered submission
or customer follow-up. Further customer messages, internal notes, ownership
changes and read receipts do not postpone it. A customer-visible team response
clears it. Replying after resolution starts a new response cycle.

Monitoring records one incident per request/target, and repeated passes do not
duplicate it. **Acknowledge support alert** records that an administrator has
seen it. It leaves the owner, support status, response target, editing revision,
customer messages and unread counters unchanged. Include acknowledged alerts to
review targets that remain active after acknowledgement.

After `SUPPORT_ESCALATION_HOURS` (24 by default) beyond the target, the incident
escalates once and needs acknowledgement again. An older alert revision cannot
acknowledge a newer escalation: the API returns 409 and the page asks for a
refresh. A retry of the same successful acknowledgement is a no-op, with one
private audit event. All administrators see the alert queue; ownership is shown
for follow-up rather than restricting existing administrator access.

Current request state is rechecked on list and acknowledgement calls. An alert
for a replied-to, resolved or changed response target disappears immediately,
even before the monitoring worker next runs. The worker retains the resolved
incident for history. Restoring the exact same overdue target reuses its incident
with a new revision and fresh acknowledgement; a new target creates a new incident.

Targets use elapsed hours, not business hours. They are operational response
targets, not statutory grievance deadlines or guarantees of resolution.

## Monitoring and operations

The existing notification worker now also reconciles support deadlines each
pass, using `NOTIFY_INTERVAL_SECONDS` (60 seconds by default). Run it through
the existing API worker setting or the external `python -m app.notify --loop`
process; use only one configured scheduling arrangement for the deployment.
Independent workers follow the support account/request lock order and deduplicate
incidents. Candidates are processed in pages of 100 with locked accounts skipped
until a later pass.

For a support-only reconciliation with no provider delivery, run from `backend`:

```bash
python -m app.support_alerts
```

This feature records **in-app** alerts. It does not create email, SMS or WhatsApp
notifications. The ordinary notification worker continues its existing delivery
work. Administrators must monitor the application; external alert routing remains
an operational launch task.

**System health** includes current overdue support requests, unacknowledged
alerts and escalations, with a link to the alert page. Overdue requests keep
health in Attention even after acknowledgement or before the worker has recorded
alerts. Consequently, overdue request and recorded alert counts can differ while
monitoring catches up. The support queue always retains its direct overdue count.

## Deployment, privacy and rollback

Back up the database, stop old API writers and apply `0034_support_deadline_alerts`
with `python -m alembic upgrade head` from `backend`, then start the updated API
and website. Upgrading adds an empty alert table and does not alter conversations,
ownership, deadlines or read receipts. The first monitoring pass can record
already-overdue requests; review the existing backlog and operational ownership
before enabling monitoring. Local validation keeps background delivery and
retention workers disabled.

Alerts and their private audit events are support business records included in
database backups and privacy/retention review. Responses use private/no-store
caching and shared API lookup/write budgets. Alert responses omit customer
message text, support subjects, phone numbers and private-note bodies; current
administrator names identify owners and acknowledgers.

Downgrade refuses while **any** incident history remains, including resolved
incidents. PostgreSQL holds an exclusive alert-table lock during that guard.
Do not delete business history to force rollback; use reviewed recovery or a
forward fix. An empty-table downgrade leaves support requests, messages,
ownership and unread counters intact.

## API

- `GET /api/v1/admin/support-requests/deadline-alerts` returns active incidents,
  global unacknowledged/escalated counts and pagination. `include_acknowledged`
  defaults to false; `page_size` accepts 1–100.
  The escalated count is the subset of unacknowledged incidents that escalated.
- `POST /api/v1/admin/support-requests/deadline-alerts/{id}/acknowledge` requires
  an explicit strict integer `revision`. Stale or inactive alerts return 409;
  an unknown alert returns 404. Agent/customer access remains denied.

## Validation

Run from `backend`, using only disposable data:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_alerts.py tests/test_support_alerts_migration.py
```

A disposable PostgreSQL `TEST_DATABASE_URL` enables simultaneous-worker,
reply/monitor and escalation/acknowledgement regressions. Fixtures drop and
recreate application tables: never point the runner at a live database.
The real migration canary preserves conversations and unread state across an
allowed down/up cycle and verifies refusal once incident history is present.
Browser fixtures cover acknowledgement/bell updates, stale escalation recovery,
deep links, paging, administrator boundaries, axe and mobile overflow with
synthetic support records and no provider delivery.

Validated locally on 11 November 2026: the full SQLite suite passed 620 tests
(33 skipped), and PostgreSQL support/worker regressions passed 99, including
parallel monitoring, reply/monitor ordering and escalation/acknowledgement races.
The final exact-target and migration checks passed nine SQLite tests (three
PostgreSQL-only skips). The real PostgreSQL canary preserved support messages,
editing revisions and unread counters across an allowed down/up cycle and
refused removal of retained incidents. Its disposable database was removed.

The complete browser run passed 180 cases with one existing desktop-inapplicable
skip; two existing time-off cases timed out during a slow run and both passed
when rerun with one worker. All 15 new support-alert browser cases passed, and
all 182 applicable browser cases were validated across those runs. Desktop and
mobile screenshots were reviewed. Workspace type checks, isolated and normal
production builds, Bandit, actionlint and Python lock validation passed. Lint
had no errors and seven existing warnings.

A verified private database backup preceded the local preview migration to
`0034`. API health/readiness and the support-alert website route returned 200;
an unauthenticated alert-list request returned 401 with private/no-store caching.
No live support request was assigned, acknowledged or replied to, and no provider
message was sent. Preview delivery/retention workers remain disabled.
