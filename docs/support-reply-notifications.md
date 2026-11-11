# Support reply notifications

Customers can receive a generic email, SMS or WhatsApp notice when an
administrator posts a customer-visible support response. The notice says only
that a reply is available and links to `/account/support`. Reading the response
still requires the verified customer session. Subjects, message excerpts,
private notes, case references, account names and authentication tokens are never
included in the notice or template parameters.

This feature is **off by default**. Set
`SUPPORT_REPLY_NOTIFICATIONS_ENABLED=true` consistently on API writers and
notification workers only after reviewing the configured channels. The local
preview keeps it off, along with background delivery/retention workers.

## Which events and recipients qualify

A new customer-visible administrator response queues its notices in the same
transaction as the response and unread counter. A failed review rolls back all
three. Internal notes, status-only changes, assignments, customer messages and
read receipts do not queue external notices. Stale administrator revisions are
rejected before another response or notification is created. Enabling delivery
does not scan or replay historical conversations.

The verified account is the recipient, even when its support request has no
linked case or legacy customer row. Email uses the current account email if one
is present; SMS and WhatsApp use its verified normalized phone. These are not
the contact details on an optionally linked case. The worker checks the account
and current address again before delivery. A contact change cancels the old
notice rather than retargeting it; a future reply uses the new contact.

Existing **Notification preferences** apply to all three channels. Opted-out
channels are recorded as cancelled at queue time. Saving an opt-out also cancels
pending support alerts, including worker claims and unconfigured channels,
without cancelling another account's alerts. Re-enabling a channel never
replays cancelled rows. Requested sign-in codes and private team workflows
remain separate from these automated alerts.

## Coalescing, reading and delivery

Only the newest still-unread response on a support request needs an unsent
notice per channel. A newer response cancels older pending notices with
`support_reply_superseded`. The customer's existing explicit read acknowledgement
cancels pending notices through the acknowledged reply revision. Reading an
older loaded response cannot cancel a newer unseen reply. Accepting a provider
message does not mark the conversation read, change case/support status, move a
response target or clear an administrator's deadline acknowledgement.

The existing notification worker claims, retries and expires these notices.
It rechecks feature enablement, ownership, current reply/read revisions, contact
details and channel preferences before claiming and after committing its claim.
Disabling the feature cancels all pending support notices on the next worker
pass, including unconfigured channels. It preserves sent/failed/cancelled history.
Unconfigured channels otherwise wait without consuming attempts until the reply
is read, superseded, expired or a provider becomes available.

Provider acceptance and reading, opting out or disabling delivery cannot be one
atomic transaction. A notice already in flight or accepted may still arrive.
Email retries retain the existing notification-ID idempotency key and retry
window. Ambiguous SMS/WhatsApp outcomes are stopped for review rather than
blindly replayed. **Sent** records provider acceptance, not confirmed delivery
or customer reading. Generic provider text is generated independently of stored
message/body parameters so private content cannot be copied by an old producer.

## Channel setup and rollout

Email/SMS reuse the Resend/Twilio configuration in [notifications](notifications.md).
If WhatsApp is configured, approve a utility template named **support_reply** in
WhatsApp Manager, using the configured template language and one body parameter:

> Homexo Legal: You have a new support reply. Sign in to read it securely: {{1}}

Parameter 1 is the canonical public-site URL followed by `/account/support`.
Do not place a support subject, private response, phone, case reference or token
in this template. Keep `PUBLIC_SITE_URL` set to the deployed HTTPS website.
The support owner must still monitor the administrator queue: this feature sends
customer reply notices, not external staff escalation notifications.

Back up the database, stop old API/worker processes and apply
`0035_support_reply_notifications` with `python -m alembic upgrade head` from
`backend`. Restart the updated API and workers with the same flag and channel
configuration. Old workers do not understand account-scoped preference checks;
do not leave them running during the rollout. No provider is called by the
migration, preference save, administrator reply transaction or read receipt.
Actual delivery occurs only in the separately configured notification worker.

The migration adds nullable account/request references, the reply revision,
scope checks and lookup indexes to the existing notification outbox. Existing
notification, support, unread and preference data is preserved. The new records
are included in database backups and privacy/retention review. Removed references
fail closed at delivery. Downgrade refuses while any support notification history
remains, including cancelled records. PostgreSQL locks the notification table
during that guard. Preserve business history and use reviewed recovery or a
forward fix instead of deleting rows to force rollback.

## Verification

Run from `backend` with disposable data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_notifications.py tests/test_support_notifications_migration.py tests/test_notification_preferences.py tests/test_notifications.py
```

Use a dedicated disposable PostgreSQL `TEST_DATABASE_URL` for concurrent review
and worker regressions. The fixture drops/recreates application tables. Tests
use synthetic accounts and mocked provider transports; none sends a real
message. The real migration canary checks down/up preservation and refusal to
discard retained support delivery history. Browser preferences/unread-support
fixtures check opt-out, conflict/retry, read-receipt controls, axe and mobile
overflow without contacting the running account database.

Validated locally on 11 November 2026: the complete SQLite suite passed 636
tests (34 PostgreSQL/environment-specific skips); PostgreSQL support,
preference and delivery regressions passed 97, including concurrent reviews and
worker claims. The real PostgreSQL upgrade/down/up canary preserved legacy
delivery rows, conversations and unread counters, and refused removal of
retained support notice history. Its disposable database was removed.

All 27 targeted preferences/unread-support browser cases passed at desktop,
phone and narrow widths. Workspace type checks, isolated and normal production
builds, Bandit, actionlint and Python lock validation passed. Frontend lint
reported no errors and seven existing warnings. Desktop/mobile synthetic
screenshots were reviewed. A verified private backup preceded the preview's
upgrade to `0035`; API health/readiness and the settings page returned 200, and
the unauthenticated settings API returned 401 with private/no-store caching.
No real support response, read receipt, preference change or provider message
was created by validation; support delivery and background workers remain off
in the preview.
