# Customer support and complaints

Customers open **Support & complaints** from their account or the public footer
(`/account/support`). A verified phone session is required. They can ask for a
case update, report a document issue, ask about a payment, raise a service
complaint or request other help. A case ticket number is optional; the server
only accepts a case owned by that verified account.

Each request has an `SR-…` reference, status and private conversation. Customers
can reply and read older messages. Replying to a resolved request reopens it;
replying while the team is waiting for the customer returns it to Open. Existing
case status, payments, refunds and case documents are not changed by this flow.
Use the case document area for files. Do not enter passwords, card details or
sign-in codes in support messages.

## Administrator review

Administrators open **Support queue** under Administration (`/admin/support`).
The queue supports status/category filters, subject/reference search, pagination
and a count of overdue team-response targets. Open a request to view the
customer's initial description, optional case link and conversation.

- **Open:** received or reopened for the team.
- **Being reviewed:** an administrator is handling it.
- **Waiting for customer:** the team has asked for more information.
- **Resolved:** the team has explained the outcome.

Moving to Waiting for customer or Resolved requires a customer-visible response
of at least ten characters. Record a completed action or a clear next step;
changing the status does not perform a refund, government-record lookup or case
operation. These actions still use their existing workflows.

Customer replies and administrator updates are serialized per account/request.
The administrator's revision must match the current record. A conflicting save
returns 409 and keeps the draft on screen; **Reload latest request** replaces
that draft with the saved conversation. This prevents an old review from closing
over a newer customer follow-up. Internal notes have a separate field, are
labelled in the administrator thread and are filtered out before customer thread
counts and pagination. Agents cannot access this queue or its API.

Replies are available in the account. This version does not send email,
WhatsApp or SMS alerts; the support owner must monitor the queue. Set an
operational owner and review schedule before relying on it for live support.

## Targets and limits

| Setting | Default | Purpose |
| --- | --- | --- |
| `SUPPORT_RESPONSE_HOURS` | 72 | Elapsed hours for the next team response; configurable from 1 to 720 |
| `SUPPORT_OPEN_LIMIT` | 5 | Maximum unresolved requests per account, including reopened requests |
| `SUPPORT_REQUESTS_PER_DAY` | 10 | New requests per account in a rolling 24 hours |
| `SUPPORT_MESSAGES_PER_DAY` | 50 | Customer follow-ups across all requests in a rolling 24 hours |

Targets are operational, not statutory grievance deadlines or guaranteed
resolution times. The first unanswered submission starts the target; subsequent
customer messages do not postpone it. Internal notes and a status change to
Being reviewed do not clear it. A visible team response clears it, and a later
customer reply starts a new target. The queue shows targets that have passed.

Create and customer-reply commands use UUID submission keys. Retrying the same
key/content returns the existing result; changing content with an already-used
key returns 409. These retries do not consume the business quotas again.
Administrator updates use revisions to prevent duplicate/conflicting writes.
Shared API write/lookup budgets also apply; 429 responses include `Retry-After`.

## API and data

Customer routes under `/api/v1/account/support-requests` provide create/list,
`/{id}` detail and paged `/{id}/messages` reads/replies. Administrator routes
under `/api/v1/admin/support-requests` provide the filtered queue, detail,
messages and a revision-checked `PATCH /{id}` review operation.

Migration `0024_customer_support` adds request and message tables. Apply
`python -m alembic upgrade head` from `backend` when deploying. Upgrading does
not alter existing case records. Downgrading removes support records, so preserve
any required data before a rollback.

Support records are business records included in database backups. Anonymous
chat retention does not delete them. Privacy/access/deletion fulfillment must
include these records and follow a reviewed retention policy. Audit entries
record actions, state and revision without copying subject/message/note text into
audit metadata. HTTP logs retain route templates rather than request content.

Use the [public policy centre](public-policies.md) to publish reviewed grievance
information and accountable contact details. It starts unpublished and does not
automatically turn the support queue into a statutory grievance mechanism.

This is an operational support workflow. Publish a legally reviewed grievance
policy, accountable contact details, applicable deadlines and escalation process
before presenting it as a statutory grievance mechanism. Customers who cannot
verify their phone can use the existing public callback form to request help;
that form does not grant access to private records.

## Validation

Validated locally on 2026-11-10: the full SQLite suite passed 400 tests (14
skips), PostgreSQL support/privacy/access regressions passed 59, and final
support/API-budget checks passed 40 on SQLite (5 PostgreSQL-only skips).
The browser suite passed 50 checks with one inapplicable desktop case skipped.
Workspace TypeScript, frontend lint (seven existing warnings), production build
and the configured Python source scan passed. Migration up/down/up preserved
nonempty synthetic account and case rows.

Run API tests from `backend`:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support.py tests/test_abuse_protection.py
```

A disposable PostgreSQL `TEST_DATABASE_URL` enables concurrent creation and
reply/resolution tests. Never point the suite at a live database: its fixtures
drop and recreate application tables. Validate migrations up/down/up on an empty
test database. From the repository root, run workspace type checks, frontend
lint/build and `npm run test:browser --workspace frontend`. Browser fixtures cover
customer submission/reply, administrator conflict recovery, internal-note display,
axe checks and mobile overflow at 1440, 390 and 320 CSS pixels.
