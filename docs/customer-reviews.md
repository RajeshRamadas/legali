# Customer review withdrawal

Verified customers can open **My reviews** at `/account/reviews` to see feedback
from their consultations, including older bookings and unpublished reviews.
Results are paginated, 20 reviews per page, and use the same verified-phone
ownership rule as the customer's account and bookings. Staff credentials and a
case number alone do not grant access to this customer endpoint.

## Customer workflow

Each review shows the advocate, booking reference, original stars/comment,
submission date and publication status. Choose **Withdraw review**, read the
confirmation, then choose **Confirm withdrawal** or **Keep review**. The first
step sends no withdrawal request. Keyboard focus moves to the confirmation,
returns to the opener after cancellation, and moves to the review heading after
success. A failed request keeps the confirmation available for an explicit retry.

Withdrawal is final through the application. It removes the review from public
profile responses, rating averages/counts and rating-based search ordering.
The original review and moderation history remain private with the booking
record. Customers cannot submit another rating for that meeting, and staff
cannot republish withdrawn feedback. Requests to erase retained information
continue through the existing privacy-request process; withdrawal is not a
database erasure operation. Previously downloaded pages and cached homepage
rating cards can remain until refreshed; the homepage retains its normal
five-minute revalidation interval.

## Administrator behavior and concurrency

The moderation queue includes **Withdrawn by customer** separately from
moderator-hidden feedback. Staff can inspect the review and prior private
decisions, but publication controls are unavailable. Current API calls reject
attempts to moderate withdrawn feedback. The withdrawal timestamp and a database
constraint also prevent the previous moderation implementation from changing a
withdrawn row back to published.

The owner endpoint locks the review row. Repeated or simultaneous withdrawals
return the existing result without changing the timestamp or adding duplicate
audit events. A simultaneous moderator action cannot cancel the owner's intent:
the completed withdrawal remains private regardless of which request starts
first. Audit metadata records the customer-account reference, transition and
revision, excluding review text and private moderator notes.

## Deployment and rollback

Migration `0028_review_withdrawal` adds a nullable withdrawal timestamp and the
publication guard. It leaves existing stars, comments, publication decisions and
private decision history unchanged. Back up the database, stop old API instances,
apply `alembic upgrade head` from `backend/`, then start the updated API and
website. The local preview was backed up before migration; no customer withdrawal
is created by this migration or by startup.

**Downgrade refuses to remove the guard while withdrawn reviews exist.** Do not
clear withdrawal timestamps or delete reviews to bypass that protection. Keep the
schema and follow a reviewed rollback/recovery procedure that preserves customer
choices. On PostgreSQL, the downgrade check holds an exclusive table lock to
prevent a concurrent withdrawal from slipping between the check and schema change.
Older API versions from before review moderation ignore publication status and
must not serve public review access. The existing deployment/backup and
review-moderation rollout guidance still applies.

## API and verification

- `GET /api/v1/account/reviews?page=1`: the verified customer's review records.
- `POST /api/v1/account/reviews/{id}/withdraw` with `{"confirmed": true}`:
  withdraw the owned review or return its existing withdrawn state.

Private responses use `Cache-Control: private, no-store`. Endpoints consume the
existing shared read/write budgets. Missing or non-customer sessions receive
401; unknown/non-owned reviews use the same 404; missing, false, non-boolean or
extra confirmation fields receive 422. A customer withdrawal never waits for
staff approval and sends no messages or provider requests.

Run `pytest tests/test_customer_reviews.py tests/test_review_moderation.py
tests/test_review_withdrawal_migration.py` from `backend/`. Use a disposable
PostgreSQL `TEST_DATABASE_URL` for both withdrawal concurrency cases; application
test fixtures drop/recreate their tables. Migration checks cover preservation,
legacy publication blocking and refusal of unsafe rollback. Browser fixtures in
`frontend/tests/browser/customer-reviews.spec.ts` exercise confirmation,
cancellation, retries, persistence, role boundaries, focus and axe checks at
desktop, mobile and narrow widths, without modifying live customer records.

Verified on 10 November 2026: the full SQLite API suite passed (554 tests, 23
environment-specific skips); 42 PostgreSQL checks passed, including concurrent
withdrawal/moderation and the migration preservation/rollback canary. The full
browser suite passed (101 tests, one existing desktop-only skip), including all
12 customer-withdrawal checks. Workspace type checks, production builds, Bandit
and workflow validation passed. ESLint reported no errors and seven existing
warnings. The backed-up local preview was upgraded to migration 0028; liveness,
readiness and the new page returned 200. Desktop and mobile visual checks used
synthetic, read-only review data.
