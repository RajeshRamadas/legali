# Service availability and pilot controls

Administrators open **Service availability** at `/admin/services` to pause or
resume new requests for an existing service. Use this during a limited pilot,
capacity shortage or operational review. Select a service, enter a private
operational reason, acknowledge the effect on new requests and choose **Pause new
requests** or **Resume new requests**. Retired services are read-only and cannot
be reactivated through this screen. Availability does not change service copy,
prices, legal scope, geography, staffing or government-provider configuration.

Pauses are stored separately from the seeded catalogue. Restarting the API or
synchronizing reference data preserves the pause and its revision. Availability
history records the administrator, timestamp, revision and private reason; those
reasons never appear in the public catalogue or customer error messages. Agents
and customers cannot access the administration endpoints or history. Conflicting
updates return 409 and retain the editor's reason and confirmation until the
administrator explicitly reloads the catalogue. History is paginated separately.

The same page provides [reviewed public descriptions](service-descriptions.md),
with independent revisions and private publication history. Saving availability
preserves an unsaved description draft; publishing copy preserves the operational
reason and confirmation. Only an explicit catalogue reload replaces both drafts.

## Customer behavior

The public catalogue reads PostgreSQL and lists only active services accepting
new requests. A paused service's public detail returns 404 without caching.
The homepage callback form refreshes those choices on mount. If a linked or
previously selected service is unavailable, the customer can choose another
service without losing entered contact/property details. If availability cannot
be fetched, the existing catalogue copy remains a fallback and the server checks
availability at submission. Empty availability blocks submission and provides a
refresh control. Static marketing descriptions may still describe paused services;
they are not a reservation or guarantee of availability.

All actual case creation passes through the same server admission check,
including website/mobile callbacks, chat requests, guided intake and online
advocate bookings. Paused requests return a clear 409 without creating a customer,
case, payment, assignment or notification. Chat does not offer a paused service.
The lawyer profile explains a consultation pause and hides its new-booking form;
public search no longer advertises an earliest new slot while consultations are
paused. Clients with older cached information are still checked by the server.

Existing cases, documents, payments and bookings remain accessible. Customers can
reply to existing cases, move/cancel existing bookings under the usual rules and
rate completed consultations. Pausing sends no messages, initiates no refunds and
cancels no existing appointment. Slot lookup remains available for rescheduling
an existing booking; a listed slot does not bypass admission for a new booking.

Saved guided-intake answers are preserved while a service is paused. Customers see
the pause notice and can choose another service or return later. Fresh drafts
cannot select a paused service. An already submitted draft still returns its
original case on retry. Resuming restores admission without replaying any failed
request or automatically submitting a saved draft.

## Concurrency and API

Creation holds a shared service-row lock until its transaction commits. An
administrator change takes an exclusive lock and checks the editing revision.
If creation was already admitted, pause waits for it to finish; once pause
commits, subsequent creation attempts are rejected. SQLite is useful for normal
regressions; PostgreSQL is required for this locking guarantee.
Online booking acquires service admission before locking the lawyer's staff row,
so a pause audit referencing that staff member cannot invert the lock order.

- `GET /api/v1/admin/services`: current catalogue including paused/retired rows.
- `PATCH /api/v1/admin/services/{slug}`: strict `revision`, `paused`,
  `confirmed: true` and a trimmed private `reason` of 10–1000 characters.
- `GET /api/v1/admin/services/{slug}/history?page=1`: 20 private changes per page.

Private responses are no-store and consume shared lookup/write budgets. Missing
staff credentials receive 401; agents receive 403. Unknown services receive 404.
Invalid/coercible/extra payload fields receive 422. A stale revision, unchanged
state or retired service receives 409 without another audit event. Audit action
`service.availability_changed` retains the reason with the service reference,
state and revision, without customer data.

## Deployment and rollback

Back up the database and stop old API instances before running `alembic upgrade
head` from `backend/`. Migration `0030_service_availability` adds pause/revision
fields and preserves existing service activation, content and linked cases. No
service is paused by migration or startup. Start the updated API and website;
older API versions do not enforce admission restrictions and must not handle new
requests during a rollout or rollback.

Downgrade refuses to remove these controls while any service is paused. PostgreSQL
holds an exclusive service-table lock for that guard. Preserve restrictions and
use a reviewed recovery procedure; do not resume real services solely to force a
rollback. When no service is paused, the permitted rollback preserves existing
service and case records. Private audit history remains in the audit table.

## Verification

From `backend/`, run `TEST_DATABASE_URL=sqlite:// python -m pytest -q
tests/test_service_availability.py tests/test_service_availability_migration.py
tests/test_public.py tests/test_intake.py tests/test_lawyers.py tests/test_chat.py`.
Use a disposable PostgreSQL `TEST_DATABASE_URL` for shared/exclusive admission
locking: fixtures drop/recreate application tables. Migration checks preserve
active/retired services and historical case links, and verify rollback refusal.

Browser fixtures in `frontend/tests/browser/service-availability.spec.ts` check
administrator confirmation, pause/resume history, conflicting edits, agent access,
callback selection and retained details, focus, axe and overflow at desktop,
mobile and narrow widths. Tests use synthetic data and send no provider messages.

Validated on 10 November 2026: the final complete SQLite suite passed 594 tests
(26 environment-specific skips). PostgreSQL intake/public/chat/booking regressions
passed 66 checks; after the booking lock-order correction, the final admission
and lawyer checks passed 27, plus a deterministic one-test lock-order rerun. The
actual PostgreSQL migration canary preserved services and historical case links
and refused unsafe rollback. The full browser suite passed 137 checks (one
existing desktop skip), including 18 availability checks. Workspace type checks,
both production builds, Bandit and workflow validation passed. Lint reported no
errors and seven existing warnings. The local database backup was verified before
migration 0030; final liveness/readiness/page checks returned 200 and the private
administrator API returned 401 without a staff session. Desktop/mobile visual
checks used synthetic read-only data and showed no horizontal overflow. No real
service was paused or provider message sent during validation.
