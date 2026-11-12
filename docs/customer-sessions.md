# Customer sign-in sessions

Verified customers can open **Signed-in sessions** at `/account/security` to see
their active sign-ins, identify the current session, end an individual session or
sign out all other sessions. Each action has an explicit confirmation. The account
page retains its sign-out-everywhere control; ordinary sign-out now revokes the
current server session before clearing browser storage.

## Rollout and compatibility

Apply migration `0045_customer_sessions` before restarting the API, then deploy
the web/shared-client changes. It creates an empty session table and does not
change customer records, case access, consent choices, document holds or staff
authentication. **Existing customer tokens without a session identifier are no
longer accepted. Customers must verify their phone again after rollout.** No
legacy session is invented from an old token, user agent or IP address.

Do not mix stateless old API instances with the new authentication code: they do
not enforce individual session revocation. Rollback to stateless authentication
could make individually revoked tokens usable again. Use a forward fix or a
reviewed recovery procedure that globally invalidates old customer token versions
before allowing old authentication code. Empty downgrade works; retained session
records block migration downgrade. Preserve security history before recovery.

`CUSTOMER_SESSION_DAYS` remains the lifetime setting (default 30 days; positive
values required). Activity never extends the original expiration time. Phone-code
verification remains the way to sign in again; no refresh-token or external
identity-provider integration is added.

## Authentication and revocation

Each new JWT has a unique `jti` session reference. The server stores its account,
token version, expiration and lifecycle metadata, never the raw bearer token.
Every customer-authenticated API checks the signature/audience, current account
version and matching active session record. Expired, revoked, absent, malformed,
legacy and another account's session references are denied. Existing case ownership
and staff/customer audience separation still apply, including file downloads,
account-summary downloads, chat and document operations.

Sign-in issuance and revocation serialize on the customer-account row. A new
sign-in after a global logout uses the new version; an earlier token does not
regain access. Signing out all other sessions preserves only the authenticated
caller. Global logout increments the existing account token version and records
session revocation. Repeating an individual revocation from a different active
session is idempotent and does not duplicate its audit event.

Revocation blocks subsequent authenticated requests. Requests already admitted
may finish and downloaded information cannot be recalled. Ending a session does
not withdraw external-document-AI permission, close cases or cancel background
case work; those remain separate choices and workflows.

Ordinary browser/profile sign-out now waits for server confirmation. On an
unconfirmed server/network failure, the customer stays signed in and sees a retry
message instead of a false success. The existing local clear operation remains
available internally for expired/rejected authentication. Responses for a stale
token cannot sign out a different newly active browser session.

## Privacy, activity and limits

Only fixed browser/device labels are retained, such as Chrome/Windows or
Safari/iPhone or iPad, derived from a bounded portion of the sign-in user agent.
Raw user-agent strings, IP addresses, location, fingerprints and bearer tokens are
not stored in `customer_sessions` or returned by its API. Labels are hints from
the original sign-in, not verified hardware identities or a detector of copied
tokens. Unknown clients receive generic labels.

Authenticated use updates `last_seen_at` at most about every five minutes through
a short conditional update. It does not hold case locks or change expiration.
The UI displays sign-in, last-activity and expiry times in IST. It lists active
sessions only, with explicit refresh and labelled stale results after errors.
It never automatically revokes a session when the page loads or refreshes.

At most 20 sign-ins remain active per account. A successful new sign-in beyond
that cap revokes the oldest recorded active session (creation time, then ID).
Issuance, row revocation and their audit records are committed atomically. Specific
session, other-session, global logout and cap actions append safe account audit
events, without raw device headers or token contents. The activity index exposes
fixed action labels rather than private payloads.

Expired/revoked metadata remains retained; this feature adds no automatic cleanup.
Account deletion cascades its session rows through the existing database relation,
while audit retention is governed separately. Review security-record retention
alongside the broader account/privacy policy. Session records stay excluded from
the self-service account-activity summary.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/v1/account/sessions` | Up to 20 active own sessions, current marker and checked time |
| POST | `/api/v1/account/sessions/{session_id}/revoke` | End an own session; another account's ID returns 404 |
| POST | `/api/v1/account/sessions/revoke-others` | End other active sessions; keep caller |
| POST | `/api/v1/account/logout` | End caller session |
| POST | `/api/v1/account/logout-all` | Existing global sign-out, now with session metadata and audit |

All require a verified customer session. Staff tokens cannot enumerate or revoke
customer sessions. Responses and access failures are private/no-store. Lookups
and revocations use existing shared API budgets. The session ID is an operation
reference, not a standalone credential. No password, token export, administrator
impersonation or session-renewal API is exposed.

Trusted server/test callers can issue a token for a committed account with
`create_session_token(account)`. Callers already creating an account inside a
transaction must flush it and pass `db=...`, then commit the surrounding
transaction; OTP login and isolated performance fixtures use that atomic form.

Tests cover session uniqueness, device-label privacy, individual/other/global
revocation, file/export denial, owner boundaries, invalid/legacy tokens, throttled
activity, expiry/cap behavior, audit rollback, migration preservation and real
PostgreSQL sign-in/revocation concurrency. Browser checks cover confirmations,
server-confirmed sign-out, failures, signed-out access and responsive accessibility.
No real customer session was created or revoked for implementation testing.
