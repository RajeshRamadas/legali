# Transactional email, SMS and WhatsApp

Ticket confirmations, status changes, document requests and case-team messages queue email/SMS alerts. Consultation bookings, changes, cancellations and future reminders also queue customer email/SMS alongside the existing WhatsApp messages. Payment processing queues a payment update once, including when a payment webhook is repeated. Private case text, legal findings, attachments and meeting links stay in the authenticated portal; email/SMS give a short alert and an account link.

Verified customers can control automated email, SMS and WhatsApp from
**Notifications** in their account. Disabled channels cancel queued alerts and
remain blocked by the worker; sign-in codes and staff alerts are separate.
See [customer notification preferences](notification-preferences.md), including
rollout and rollback requirements for migration 0029.

## Configure delivery

Set values securely in the deployment environment or ignored `infra/.env` for Docker Compose; never commit credentials. Provider activation requires network access to `api.resend.com` and `api.twilio.com`. Missing provider credentials keep that channel queued without consuming attempts. Staff see “channel not configured” in the ticket's notification history.

| Channel | Required settings |
| --- | --- |
| Email (Resend) | `RESEND_API_KEY`, `EMAIL_FROM` on a verified sender domain |
| SMS (Twilio) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and either `TWILIO_MESSAGING_SERVICE_SID` or `TWILIO_FROM_NUMBER` |
| WhatsApp | Existing `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` and approved templates from `meetings.md` |

Use a production HTTPS `PUBLIC_SITE_URL` for portal links. Bare 10-digit SMS numbers use `SMS_DEFAULT_COUNTRY_CODE` (91 by default). Provision the Twilio sender/service for the destination countries, including India's required sender/template registration where applicable. Messages are transactional; no marketing subscription is added. SMS length may span multiple segments.

Run `alembic upgrade head` in `backend/` before starting this version of the API or the delivery worker. Migration `0016_notification_delivery` adds attempt and worker-claim fields without changing existing messages. Restart the API after configuration changes. Docker Compose passes the new settings through to the API.

## Worker behavior

The existing API worker sends notifications when `NOTIFY_WORKER_ENABLED=true`. Alternatively disable it and run `python -m app.notify --loop` in `backend/`. Use PostgreSQL for concurrent workers: each claims one due row with `FOR UPDATE SKIP LOCKED`, commits a five-minute lease before contacting the provider, then conditionally records its outcome using a claim token. Only configured channels are selected.

- Successfully accepted messages become `sent` with a provider reference and are not selected again. `sent` means provider acceptance, not inbox/handset delivery. Delivery-receipt webhooks are not part of this implementation.
- Retryable email failures (network errors, 429, 5xx and invalid success responses) reuse the notification UUID as Resend's idempotency key. Attempts stop before its 24-hour retention boundary; the worker uses a conservative 23-hour limit.
- SMS retries cover connection failures before submission and explicit 429 responses. Read/write timeouts, 5xx and malformed success responses have an uncertain outcome and stop as `failed`. Check the provider console before arranging a replacement; automatic resend could duplicate a message.
- A crashed email worker can recover its expired lease with the same idempotency key. An expired SMS/WhatsApp lease stops for review because the provider may already have accepted the message.
- Authentication/validation errors are terminal. Only safe error codes are saved; provider response bodies and credentials are not logged. Failed rows are not automatically reset when credentials change.
- Future sends wait until `send_after`. Cancelled/rescheduled meetings supersede queued alerts across all three channels. Stale notifications are cancelled rather than sending an old backlog; age is measured from the scheduled send time when present.

Defaults: `NOTIFY_MAX_ATTEMPTS=5`, `NOTIFY_RETRY_SECONDS=60` (exponential backoff capped at one hour), `NOTIFY_MAX_AGE_HOURS=24`. Configure these for operational needs. Do not change email payload settings while retries are outstanding: Resend requires the same payload with an idempotency key. External acceptance and database updates cannot be one transaction; conditional updates preserve cancellation, but an alert already accepted by a provider cannot be recalled.

Staff notification history includes status, attempts, retry time, provider reference and uncertain-outcome guidance. Missing credentials, retryable failures, terminal failures and accepted messages remain distinct.

## Validation

From `backend/`, run `python -m pytest -q -rs`. Provider calls in tests use `httpx.MockTransport` and never send real messages. Run notification tests against an **empty disposable** PostgreSQL database using `TEST_DATABASE_URL` to exercise concurrent worker locking; the test fixture drops/recreates tables. SQLite runs skip that PostgreSQL-specific check. The migration should also be checked up/down/up on a disposable database with a queued message retained. From the repository root run workspace type checks, the frontend build and frontend lint.
