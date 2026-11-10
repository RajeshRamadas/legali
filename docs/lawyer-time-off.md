# Lawyer time off

Staff open **Time off** at `/admin/time-off` to block unavailable periods without
editing weekly consultation hours. Agents manage their own periods.
Administrators can select another staff member. Private reasons and history are
available only to the staff member and administrators, never customers or other
agents. Do not put medical or other unnecessary sensitive information in reasons.

Enter a start and end using the device timezone shown above the form, add a
private reason of 10–500 characters and confirm the effect before saving. The
browser sends an explicit UTC timestamp; the server normalizes offsets before
storage. History displays dates in `MEETING_TIMEZONE`. Periods may begin in the
past 24 hours or next year, must end in the future and may span at most 90 days.
The end is exclusive: a meeting may start exactly when the period ends.

## Booking behavior

Active periods are included in public slot calculations, search availability and
the next-available time. Slot responses are no-store. New online bookings,
customer rescheduling and staff scheduling/moves recheck availability inside the
lawyer's admission transaction. Cached marketing cards can still show an older
suggestion; the server never relies on that suggestion to admit a booking.
Customers receive a generic unavailable-time message, without the private reason.

A period cannot overlap another active period or a scheduled meeting. Staff must
use the existing rescheduling or cancellation workflow for conflicting meetings
first. Time off does not cancel meetings, change payments/refunds, send messages,
alter a profile's weekly hours or pause a service. Service admission rules still
apply independently.

Cancelling a period requires a separate confirmation. The record remains in
private history and otherwise available slots reopen. Cancellation is idempotent.
Create retries reuse the submission key for the same details, including after a
lost response. A reused key with different details returns 409; retrying a period
that was already cancelled returns its retained cancelled state and never
recreates it. Errors preserve entered dates, reason and confirmation.

## API and concurrency

- `GET /api/v1/admin/time-off?page=1` lists 20 private periods per page.
- `POST /api/v1/admin/time-off` accepts `submission_key`, offset-aware
  `starts_at`/`ends_at`, `reason` and strict `confirmed: true`.
- `POST /api/v1/admin/time-off/{id}/cancel` accepts strict `confirmed: true`.
- Administrators may add `?user_id=<staff UUID>` to any of those requests.

Unknown or another member's period is not exposed. Extra fields and invalid
confirmation values fail validation. Private responses use no-store and shared
lookup/write budgets apply. Audit actions record creation/cancellation, actor and
period reference; audit metadata does not copy private reasons.

Creation/cancellation take the same PostgreSQL lawyer-row lock used for meeting
admission. `FOR NO KEY UPDATE` preserves mutual exclusion while permitting
foreign-key checks for staff creators and audit actors. If a booking commits
first, a conflicting time-off request fails; if time off commits first, the
booking fails. SQLite covers ordinary behavior, not independent-worker locking.

## Deployment and rollback

Back up the database, stop old API writers, and run `alembic upgrade head` from
`backend` before starting the updated API and website. Migration
`0031_lawyer_time_off` creates a new table and changes no existing staff, profile,
meeting or customer rows. No period is created by migration or startup.

Downgrade refuses while an uncancelled future/ongoing period exists and takes an
exclusive table lock for the PostgreSQL guard. Older APIs do not enforce time off
and must not handle scheduling while such restrictions need to remain in force.
Do not cancel real time off simply to bypass rollback protection. A permitted
downgrade removes the time-off table, including past/cancelled reasons; preserve
required records before any reviewed rollback. Audit records remain separate.
These are staff business records included in database backups, not anonymous chat
retention data; handle any privacy request under the reviewed retention policy.

## Verification

Run from `backend` against isolated data:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_time_off.py tests/test_time_off_migration.py tests/test_lawyers.py tests/test_meetings.py
```

A **disposable** PostgreSQL `TEST_DATABASE_URL` enables both admission-order tests
and the cross-staff foreign-key locking check. Test fixtures drop and recreate
application tables; never point them at a live database. The real PostgreSQL
migration canary verifies the active-period rollback guard and retained staff
across a permitted down/up cycle.

Browser fixtures in `frontend/tests/browser/time-off.spec.ts` exercise private
creation/cancellation, device-zone conversion, overlap recovery, own-account
controls, axe and overflow at 1440, 390 and 320 CSS pixels. They use synthetic
data and do not create real leave, meetings or provider messages. Manual calendar
planning still requires staff to review their saved periods; this feature does
not synchronize leave to external calendars or employment/HR systems.

Validated on 10 November 2026: the complete SQLite run passed 599 tests (27
environment-specific skips). Final time-off/migration/lawyer checks passed 14
on SQLite (three PostgreSQL-only skips); PostgreSQL booking, meeting and service
regressions passed 44, with all nine final time-off/migration cases passing after
the migration-fixture correction. The real PostgreSQL guard/down/up canary
preserved staff and refused unsafe rollback. The existing 137 browser checks
passed (one inapplicable desktop skip), and all nine time-off browser cases
passed in the final targeted run. Workspace type checks,
both production builds, Bandit and workflow syntax validation passed. Frontend
lint reported no errors and seven existing warnings. A verified private local
backup preceded preview migration 0031. No real time off, meeting or provider
notification was created during validation.
