# Customer notification preferences

Verified customers open **Notifications** in their account sidebar
(`/account/notifications`) to choose email, SMS and WhatsApp automated alerts.
The choices cover case/document/report updates, payment updates and consultation
invites, changes, cancellations and reminders for requests associated with their
verified phone. Historical customer rows with that same normalized phone are
included. The choices do not replace contact details on those requests.

When enabled for the deployment, generic [support reply notices](support-reply-notifications.md)
also honor these choices, including support accounts with no linked case or
legacy customer row. They use the account's current contact details and keep
support content inside the verified portal.

Existing delivery behavior is preserved until a customer saves different choices.
No marketing subscription or marketing consent is created. Personal contact by
the case team remains outside these automated-channel settings. Customers can
disable all channels and continue checking updates and meeting links in their
account. Phone sign-in codes are sent only when requested and remain available
when WhatsApp alerts are off. Staff invites, agendas and deadline alerts are
separate from customer choices.

## Saving and delivery

Each channel is an explicitly labelled checkbox. Save applies all three choices
together; a failed save retains the draft. A conflicting revision from another
device disables further saving until **Reload saved choices** replaces the draft
with the server's current version. Reload is explicit; background refresh does
not overwrite unsaved choices. The confirmation or conflict receives keyboard
focus. Shared lookup/write budgets apply, including the save retry countdown.

Disabling a channel cancels its queued customer notifications, including future
reminders, retries, unconfigured channels and rows claimed by a worker. Sent and
failed history, in-app records and staff notifications are retained. The worker
checks current choices before claiming and again immediately before calling a
provider; it reads scalar database values rather than cached preference models.
New case and meeting alerts on disabled channels are recorded as cancelled with
`preference_disabled`, displayed as **channel disabled by customer** in staff
notification history. The worker also protects alerts inserted by an older queue
producer during a rollout.

An alert already in a provider call or already accepted cannot be recalled and
may still arrive. Provider acceptance and saving preferences cannot be one atomic
transaction. Enabling a channel again applies only to future events: no cancelled
notification is reset or replayed, and no provider message is sent by saving.

## API and data

- `GET /api/v1/account/notification-preferences` returns `email`, `sms`,
  `whatsapp`, `revision` and `updated_at`. An account without saved choices gets
  all channels enabled, revision 0 and no saved timestamp; reading creates no row.
- `PUT /api/v1/account/notification-preferences` accepts exactly the three strict
  booleans and current nonnegative integer `revision`. It returns the saved
  choices. Missing fields, coercible values and extra fields receive 422; a stale
  revision receives 409 without writing. An unchanged save with a current revision
  returns the existing result without another audit entry.

Both endpoints require the verified customer session and use private/no-store
responses. A staff session or caller-supplied account identifier cannot select
another account. Account row locking serializes first saves as well as later
updates. Preferences are stored in `customer_notification_preferences`; the
audit action `notification.preferences_changed` records the account reference,
channel booleans and revision without recipient details or message content.
Preferences are included in database backups and the existing privacy workflow.

## Deployment and rollback

Back up the database, stop old API and notification-worker processes, run
`alembic upgrade head` from `backend/`, and start the updated API and workers.
Migration `0029_notification_preferences` creates an empty table and preserves
all existing accounts, alerts, delivery states and withdrawal protections.
Do not leave old delivery workers running: versions without preference checks
can send alerts inserted after a customer opts out.

Downgrade refuses to remove the preference table while any customer has disabled
a channel. PostgreSQL holds an exclusive table lock during that check. Preserve
these choices and use a reviewed recovery procedure; do not change real choices
just to force a rollback. When every channel is enabled, the permitted downgrade
preserves account and notification rows. Cancelled alerts remain cancelled.

## Verification

From `backend/`, run `TEST_DATABASE_URL=sqlite:// python -m pytest -q
tests/test_notification_preferences.py tests/test_notification_preferences_migration.py
tests/test_notifications.py tests/test_meetings.py tests/test_accounts.py`.
Use a disposable PostgreSQL `TEST_DATABASE_URL` for concurrent first-save and
worker-locking tests: fixtures drop/recreate their application tables. Migration
tests verify existing data preservation and rollback refusal for each disabled
channel. Provider boundaries are mocked; tests never send real messages.

Browser fixtures in `frontend/tests/browser/notification-preferences.spec.ts`
cover saved choices, all-channel opt-out, conflict recovery, deliberate retry,
rate-limit countdown, initial-load failure, signed-out access, focus, axe checks
and overflow at desktop, mobile and narrow widths. Workspace type checks,
frontend lint/build and configured source scans apply as normal.

Validated on 10 November 2026: the complete SQLite API suite passed 575 tests
(24 environment-specific skips). PostgreSQL preference/notification/meeting
regressions passed 49 tests (one skip), including concurrent first saves and
worker locking; the actual migration canary preserved accounts/alerts and refused
to discard an opt-out during rollback. All 18 new browser checks passed, and the
full website suite passed 119 checks with one existing desktop skip. Workspace
type checks, both production builds, Bandit and workflow validation passed.
Frontend lint reported no errors and seven existing warnings. The local preview
database was backed up before migration 0029; liveness, readiness and the new page
returned 200, and the private settings API returned 401 without authentication.
Desktop/mobile visual checks used synthetic read-only data and showed no
horizontal overflow. No provider messages were sent by this validation.
