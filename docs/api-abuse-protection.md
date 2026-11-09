# API abuse protection

Apply `alembic upgrade head` from `backend/` before starting the updated API. Migration `0021_api_abuse_protection` adds `api_rate_buckets`; it does not change case or customer records.

The API checks these budgets before parsing request bodies or running endpoint work. Failed validation, unauthorized requests and rejected uploads also consume attempts. All workers share atomic PostgreSQL counters. Each request consumes a client-IP budget and, when a cryptographically valid customer/staff session token is present, a budget for that account. Both must have capacity. Endpoint authorization, session revocation, MFA and case ownership checks still apply downstream; a token used for counting grants no access. Invalid tokens only consume the IP budget.

| Setting | Default | Shared across |
| --- | --- | --- |
| `API_SUBMISSIONS_PER_HOUR` | 20/hour | Ticket creation, consultation booking, guided-intake submission |
| `API_LOOKUPS_PER_MINUTE` | 60/minute | Ticket/booking lookup, customer profile/request reads, saved-intake reads |
| `API_UPLOADS_PER_MINUTE` | 20/minute | Customer uploads, staff uploads, signed-report uploads |
| `API_AI_ACTIONS_PER_MINUTE` | 10/minute | Staff verification runs, document checks and malware rescans |
| `API_WRITES_PER_MINUTE` | 60/minute | Customer replies, profile edits, document tagging/deletion, intake saves/edits/deletion, booking changes/payment actions |
| `API_DOWNLOADS_PER_MINUTE` | 120/minute | Private file downloads |
| `API_AUTH_PER_MINUTE` | 60/minute | Staff authentication/security POSTs and customer sign-in requests |
| `CHAT_RATE_LIMIT_PER_MINUTE` | 20/minute | Assistant messages |

These are fixed UTC minute/hour windows, so traffic can burst around a boundary. Limits are positive integers (values below 1 become 1). Restart all API workers after changing settings; workers must share the same limits, clock and `JWT_SECRET`. Existing staff sign-in/recovery, customer OTP and rolling chat limits provide additional checks. Health checks, CORS preflight, public catalogues and the Razorpay webhook do not consume these budgets. The webhook continues to require its provider signature.

The API returns HTTP **429**, a numeric `Retry-After` header and `{ "detail": "…", "retry_after": 42 }`. The response is private/no-store, and allowed CORS origins can read `Retry-After`. The shared web/mobile client exposes the delay as `ApiError.retryAfterSeconds`. Public callback and chat-request forms preserve input, display the error and disable submission until their countdown ends. Other forms display the server error through existing error handling. Writes are never automatically retried. If budget storage is unavailable, covered requests fail with **503** and a short retry delay; unprotected health checks stay available.

JSON bodies on covered routes are limited to **1 MiB**. Multipart upload requests are limited to `UPLOAD_MAX_MB + 1` MiB (one extra MiB for form fields and multipart overhead); the existing individual file-size, content-type and malware checks remain. Declared oversized requests are rejected before reading the stream. Undeclared or misleading lengths are checked as the body is read and return **413** when the cap is exceeded. A client disconnect can interrupt the response. GET downloads only check declared request-body size because their endpoints do not parse request bodies.

The callback and chat-request forms include an invisible `website_url` honeypot. Leave it absent or empty in API/mobile integrations. A non-empty value receives **400** and creates no request or notification. It adds friction for simple form bots and complements the rate limits.

## Deployment and maintenance

Identities are stored as HMAC hashes, with the budget group in the hashed input; raw IPs, phone numbers and JWTs are not stored in the counter table. Counters saturate at the limit plus one. One row per identity/group is reused across windows.

The middleware uses ASGI's client address and ignores `X-Forwarded-For` and `X-Real-IP`. When a trusted reverse proxy sits in front of uvicorn, configure `--proxy-headers --forwarded-allow-ips=<trusted proxy addresses>` and ensure the proxy replaces incoming forwarding headers. Never trust all source addresses. Otherwise callers can spoof the address or all visitors can share the proxy's budget. Restrict direct API access to the proxy in production.

Schedule this command daily with the same database/settings as the API:

```bash
cd backend
python -m app.abuse_protection
```

It deletes counter rows whose window is more than 24 hours old; active windows remain protected. This does not remove staff-auth or customer-OTP counters, chat transcripts or any business records. Monitor 429/503 rates and table growth, and tune shared-IP limits for expected traffic. Use proxy connection/body/time limits and upstream bot/DDoS controls as well: application budgets do not prevent a saturated connection pool or slow incoming streams.

## Validation

Run `pytest tests/test_abuse_protection.py` from `backend/`. Tests cover pre-parser rejection, JSON/multipart stream caps, error/CORS headers, signed versus forged identities, shared endpoint budgets, window reset, counter saturation, cleanup, honeypots and webhook signature preservation. Set `TEST_DATABASE_URL` to a **disposable** PostgreSQL database to run the concurrent-worker tests; the fixture drops and recreates all application tables. Never use a live database for tests.
