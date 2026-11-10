# Unread support replies

Customers can see new team responses without opening every support conversation.
The account's **Support & complaints** link, request list and notification bell
show unread reply counts. The bell links back to the private support area.
Counts refresh on navigation, window focus, read actions and every 30 seconds
while the page is visible. A failed refresh retains the last known badge count.

Only committed, customer-visible administrator responses create unread replies.
Internal notes, customer messages and status-only edits do not. Counts include
resolved requests, whose saved responses remain available. Email/SMS/WhatsApp
preferences do not hide saved conversations or their in-app badges; this feature
does not send messages through any delivery provider.

## Reading a conversation

Opening or refreshing a conversation does not mark it read. On its newest message
page, choose **Mark request as read** to acknowledge replies received before
that conversation was loaded. Older messages remain accessible.

The action keeps an unsent reply draft. If a newer team response arrives during
the action, it remains unread and the page asks you to reload before acknowledging
it. **Reload conversation** explicitly replaces the unsent draft, as explained
beside the button. Failed read actions keep the draft, badge and retry target.
Repeated or older read receipts cannot make a previously read reply unread.

Read receipts do not change the support status, team response target, work-queue
ordering, customer message history or administrator editing revision. Staff
cannot use a customer receipt endpoint to acknowledge a reply for the customer.

## API and concurrency

- `GET /api/v1/account/support-requests/unread` returns aggregate `requests` and
  `unread_replies` for the verified account only.
- Existing list/detail responses add `unread_replies`,
  `customer_update_revision` and `customer_read_revision`. Customer thread pages
  also return the update revision captured for that load.
- `POST /api/v1/account/support-requests/{id}/read` accepts only
  `{"through_revision": <nonnegative integer>}`. A future revision returns 409;
  a previously acknowledged revision is an idempotent read.

Responses are private/no-store. Customer lookup/write budgets also protect these
routes. Staff or missing customer credentials receive 401; another account's or
unknown request receives 404. Revision strings, floats, booleans, negatives and
extra fields fail validation. No message body or internal-note metadata is
included in the aggregate response.

Visible response text and its update counter commit in the same transaction.
Receipts use the same PostgreSQL account/request lock order as support reviews.
The explicit loaded revision prevents a delayed read from clearing a newer
response. Read-counter updates preserve `updated_at` and the support editing
revision. Frontend metadata merges also preserve a newer loaded counter and the
draft's original editing state.

## Deployment and rollback

Back up the database and stop old API writers before applying
`0032_support_unread_replies` with `alembic upgrade head` from `backend`.
Start the updated API and website together. Older writers do not increment the
new counters and must not keep accepting support reviews during rollout.

The migration initializes both counters to zero: existing historical messages
are retained and do not generate a backlog of unread alerts. New visible team
responses start counting after upgrade. No support response, read receipt or
provider notification is created by migration/startup.

Downgrade refuses while any unread reply remains, including on resolved requests.
PostgreSQL takes an exclusive support-table lock for that guard. Do not mark a
customer's responses read solely to force rollback; use a reviewed recovery or
forward-fix procedure. A permitted downgrade removes the counters while retaining
the support conversations. A subsequent upgrade establishes a new zero baseline.
Receipt counters are part of the support business record and database backup;
include them in reviewed privacy/access/retention procedures.

## Verification

Run from `backend` with isolated test data:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support.py tests/test_support_unread.py tests/test_support_unread_migration.py
```

Use a **disposable** PostgreSQL `TEST_DATABASE_URL` for the concurrent receipt
check. Fixtures drop and recreate application tables; never use a live database.
Migration checks preserve existing support/message rows and reject removal with
unread replies. Browser fixtures in `support-unread.spec.ts` exercise badges,
explicit acknowledgement, newer-response handling, failed retries, draft/focus
preservation, axe and overflow at desktop/mobile/narrow widths. They use synthetic
accounts and do not change real conversations.

Validated on 10 November 2026: the complete SQLite suite passed 605 tests (30
environment-specific skips). PostgreSQL support, ownership, receipt and migration
checks passed 55 tests, including concurrent reply/read serialization. The real
PostgreSQL guard/down/up canary retained support/message rows and rejected unsafe
rollback. The complete browser suite passed 155 checks (one inapplicable desktop
skip), including all nine unread-reply scenarios. Workspace type checks, both
production builds, Bandit and workflow validation passed; lint reported no errors
and seven existing warnings. A verified private local backup preceded preview
migration 0032. Validation created no real support response or customer read
receipt and sent no provider messages.
