# Support delivery history

Administrators open a conversation in **Support queue** (`/admin/support`) and
expand **Delivery history** below the reply form. It shows customer reply notices
and administrator deadline emails for that exact request, including retained
records for resolved or acknowledged incidents.

Filter by recipient group, delivery state and channel, move through pages, or
choose **Refresh delivery history**. These actions keep the unsent reply,
internal note and request-status selection intact. History is fetched only after
expansion. Changing conversations discards the old view; late responses cannot
replace another request's history. Load errors offer an explicit retry without
reloading the conversation. Normal session expiry still requires sign-in again.

## Interpreting records

- **Queued** can include a scheduled retry, missing channel configuration or an
  in-flight provider attempt. It is not a promise of eventual delivery.
- **Accepted by provider** represents the worker's `sent` state. It confirms
  neither arrival nor that a customer read the reply.
- **Delivery confirmed** shows an existing confirmed record when present. This
  view does not add a provider receipt integration or infer customer reading.
- **Failed** and **Cancelled** retain their history. Safe reason labels explain
  opt-out, reading, supersession, changed contacts/routing, acknowledgement,
  disabled features, expiry and uncertain provider outcomes. Unknown legacy
  errors produce a generic review instruction instead of their stored text.

Records include their event, channel, recipient group, attempts, timestamps and
internal delivery reference. Staff recipients use their current display name,
or **Former administrator** after removal; customers are labelled **Customer**.
Email addresses, phone numbers, message/note bodies, raw provider errors,
provider references, template parameters, claim tokens and deduplication keys
are not returned.

Current feature/channel configuration appears separately from past records.
Configured means settings are present, not provider health. An off feature can
have older sent or queued records. Reading history does not change delivery
state, acknowledge incidents, mark replies read or enable a channel. There is
no resend action: investigate uncertain outcomes before arranging another
message through the normal workflow.

## Privacy, access and API

`GET /api/v1/admin/support-requests/{id}/deliveries` requires an administrator
session. Customers and agents cannot read it, including the customer who owns
the request. It uses private/no-store responses and the shared lookup budget.
It creates no provider calls or support/audit mutations; ordinary request-budget
counters still apply.

Parameters are `page` (at least 1), `page_size` (1–100, default 20), `recipient`
(`all`, `customer`, `administrator`), `status` (`all`, `queued`, `sent`,
`delivered`, `failed`, `cancelled`) and `channel` (`all`, `email`, `sms`,
`whatsapp`). Invalid values return 422. Missing requests return 404 after
authorization. Order is newest creation time first, then delivery ID to break
ties. Concurrent delivery updates can change filtered counts between loads;
refresh or return to a previous page when needed.

Customer rows must match both the selected request and its account. Staff rows
must link to an incident belonging to the selected request. Other accounts,
unrelated support requests, case notices and staff agendas are excluded. Staff
names are joined in one query rather than loaded per row. Field and reason
allowlists prevent arbitrary stored provider text from reaching the response.
Records whose incident linkage was removed cannot be associated with this view;
the preceding delivery features retain their history/rollback protections.

## Deployment and verification

No new schema or migration is required. This reads references from migrations
`0035_support_reply_notifications` and `0036_support_deadline_email`. Deploy
the updated API and website together on the current schema. Existing delivery
flags/provider configuration remain unchanged; the view does not enable them.
History remains covered by database backup and business-record retention review.

From `backend`, using disposable data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_delivery.py tests/test_support.py tests/test_support_ownership.py
```

Use a dedicated disposable PostgreSQL `TEST_DATABASE_URL` for joins, timestamp/
UUID paging, scope and related support workflows. Fixtures drop/recreate tables.
Browser fixtures in `frontend/tests/browser/support-delivery.spec.ts` verify
filters, paging, empty states, retry, draft preservation, late-response isolation,
agent boundaries, axe and desktop/phone/narrow overflow without real provider
delivery or support mutations.

Local verification on 11 November 2026: the full SQLite suite passed (664 tests,
35 skips), the PostgreSQL support regression suite passed (98 tests), and browser
checks passed (24 tests across desktop, phone and narrow widths). Workspace type
checks, production build, Bandit, actionlint and dependency-lock checks passed.
Lint had no errors and seven existing warnings. The refreshed development website,
API health and API readiness returned 200; anonymous history access returned 401
with private/no-store caching. Delivery workers and both support delivery features
remain disabled in the preview. No provider messages were sent and no schema
change was applied.
