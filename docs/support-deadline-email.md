# Administrator email for missed support targets

The existing support incident monitor can queue generic email notices for
eligible administrators. Initial notices go to the current active administrator
owner when that person has a usable email address; otherwise they go to active
administrators with usable addresses. Escalated incidents notify all eligible
administrators, including super administrators. Agents, customers and inactive
staff are excluded.

Emails contain only a fixed missed/escalated target label and a link to
`/admin/support/alerts`. Support subjects, message excerpts, customer names or
contacts, private notes, request/case references and sign-in tokens stay inside
the authenticated application. Changing stored message bodies cannot copy
conversation content into provider text.

## Enablement and delivery status

`SUPPORT_DEADLINE_EMAIL_ENABLED` defaults to **false**. Before enabling it,
review the current overdue backlog and staff recipients, configure the existing
`RESEND_API_KEY` and `EMAIL_FROM`, and run the existing notification monitor and
delivery worker. Keep this setting consistent across API and worker processes.
The feature creates queue records; only the worker calls the email provider.
No real provider calls occur during the incident reconciliation, acknowledgement,
support review, ownership change or migration.

The administrator alert page reports whether email notices are off, enabled,
or missing provider configuration. Enabled means configured, not verified
delivery or provider health. The in-app list, bell, acknowledgement and overdue
targets remain available in every state. Continue monitoring the queue.
Customer notification preferences do not disable these private staff notices.
The separate [customer reply notices](support-reply-notifications.md) continue
to honor the customer's channel choices.

Compose forwards both support-delivery opt-ins, response/escalation targets and
support abuse limits to the API. Staging/production examples explicitly keep
both delivery flags off and provide empty email-provider settings. Native and
external workers need the same environment values. The rendered profile check
verifies defaults and explicit opt-ins without starting containers or sending
messages.

## Incidents, routing and cancellation

Monitoring queues at most one notice per incident revision, eligible staff
account and delivery address. Repeated passes do not resend an accepted, failed
or cancelled record. If the first pass finds an already-escalated target, only
its current escalation is queued. Enabling delivery can queue existing current,
unacknowledged incidents; it does not replay resolved or acknowledged history.

Acknowledging an incident immediately cancels its unclaimed notices. A visible
customer response clears the target and cancels those pending notices too.
Escalation requires acknowledgement again and queues a new incident revision.
Reopened incidents similarly use their new revision. Acknowledgement and email
delivery do not change support editing revisions, response targets, ownership,
customer messages, unread counters or case/payment state.

Ownership changes cancel unclaimed notices whose old recipient is no longer
eligible. The next monitor pass can queue the current owner. An already-notified
recipient/incident/address is not replayed if ownership moves away and back.
Address changes never retarget historical records: old pending addresses are
cancelled, and a later monitor pass can queue a fresh record for the current
usable address. Initial fallback and escalation routing are recalculated from
current active administrator roles, not cached user objects. Missing/invalid
owner email uses administrator fallback. With no eligible addresses, the in-app
incident remains the source of operational follow-up.

Before claiming and immediately before provider delivery, the worker rechecks
the feature flag, target, incident revision, acknowledgement, owner/routing,
current role and email. Disabled delivery cancels unclaimed notices even when
the email provider is unconfigured. Claimed notices recheck before sending.
Unconfigured channels otherwise remain queued and use existing expiry rules.

A provider call already in flight may still be accepted after acknowledgement,
reassignment or disablement. Its accepted result is retained truthfully as sent;
cancellation cannot recall accepted mail. Sent means provider acceptance, not
confirmed delivery or reading. Existing notification-ID idempotency keys,
bounded email retries, leases and maximum-age rules apply. No acknowledgement
or routing action resets failed/cancelled history for blind retry.

## Migration and rollback

Back up the database and stop old API/worker processes before applying
`0036_support_deadline_email` with `python -m alembic upgrade head` from
`backend`. Restart the updated application and workers with delivery disabled
until deployment configuration is reviewed. The preview keeps support customer
and staff delivery, background delivery and retention workers disabled.

The migration adds a nullable incident reference, incident revision, scope check
and lookup index to the notification outbox. Existing customer notification,
support and incident records are preserved; migration itself queues nothing.
Staff notices are constrained to email and cannot carry customer/case/meeting
recipient scopes. Removed incident or user references fail closed at delivery.
These records belong in database backups and business-record retention review.

Downgrade refuses while any staff support-email history remains, including
cancelled rows or orphaned references. PostgreSQL locks the notification table
during the guard. Preserve history and use reviewed recovery or a forward fix
instead of deleting records to force rollback. A permitted downgrade preserves
the preceding customer support delivery and incident features.

## Validation

From `backend`, using only disposable data:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_deadline_email.py tests/test_support_deadline_email_migration.py tests/test_support_alerts.py tests/test_notifications.py
```

A dedicated disposable PostgreSQL `TEST_DATABASE_URL` enables simultaneous
monitor and claim/revalidation tests. Fixtures drop/recreate application tables;
never point them at a live database. Providers are mocked. Browser fixtures
exercise the alert page, three delivery states, acknowledgement, conflicts,
pagination, access boundaries, axe and desktop/phone/narrow layout without
mutating real support records.

Validated locally on 11 November 2026: the complete SQLite suite passed 658
tests (35 PostgreSQL/environment-specific skips), and PostgreSQL staff/customer
delivery, incident, ownership and deadline regressions passed 112. The real
PostgreSQL canary preserved customer-notification scope, unread counters and
incident revisions through an allowed down/up cycle, then refused removal of
retained staff email history. Its dedicated test database was removed.

All 21 support-alert browser cases passed, covering enabled, disabled and
unconfigured delivery at desktop, phone and narrow widths. Workspace type
checks, isolated and normal builds, Bandit, actionlint and Python lock checks
passed. Lint had no errors and seven existing warnings. Rendered staging and
production profiles preserved disabled defaults and explicit delivery opt-ins.
Desktop/mobile synthetic screenshots were reviewed.

A verified private database backup preceded the preview upgrade to `0036`.
Liveness/readiness and the support-alert website route returned 200; the
unauthenticated administrator API returned 401 with private/no-store caching.
No real alert was acknowledged or emailed, and no real support response,
ownership or preference was changed during validation. Customer/staff support
delivery, background delivery and retention workers remain disabled locally.
