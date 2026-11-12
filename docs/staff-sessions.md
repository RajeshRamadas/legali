# Staff sign-in session management

Staff can review their own active sign-ins in **Security** at `/admin/security`,
end an individual session or sign out other sessions while keeping the current
one. Ending the current session and signing out all devices are confirmed before
clearing browser storage. The workspace's ordinary sign-out button also waits
for server confirmation. A network/server failure leaves the browser signed in
and displays a retry message; rejected/expired authentication clears it locally.

## Rollout

Apply `0046_staff_sessions` before deploying the API, then deploy the frontend.
The migration creates an empty table, preserves users, passwords, authenticator
seeds, recovery codes and customer sessions, and does not infer old device records.
**Existing staff access tokens without a session identifier are rejected. Staff
must sign in again, including their usual second factor when enrolled.**
Enrollment-only tokens retain their existing scope and expiry; they cannot list
or revoke sessions. MFA challenges and password-reset tokens remain separate
single-use records and never appear in the active-session list.

Deploy API instances together: old stateless instances do not enforce individual
revocation. Returning to old authentication code could make individually revoked
tokens valid again. Prefer a forward fix; any reviewed recovery using old code
must globally invalidate outstanding staff token versions before admitting
traffic. Migration downgrade succeeds only while the table is empty, and refuses
to discard retained records, including revoked or expired sessions.

## Enforcement and privacy

Each successful staff sign-in has a unique JWT `jti` and matching database record.
Every staff-authenticated request checks the current user status/roles, token
version, MFA policy, session ownership, database expiry and revocation state.
Customers and enrollment tokens cannot access these controls. Administrators
cannot use them to inspect or revoke a different staff member's individual
sessions; existing role/status management remains a separate authorized action.
Revoked credentials also lose private file access on the next request.

Session issuance and security mutations serialize on the user row. Login/MFA
completion, code consumption, session creation and safe audit events commit
together. Password changes, MFA changes, recovery-code replacement, role/status
changes, password recovery and global sign-out revoke existing session records
while advancing the existing account version. Actions returning a replacement
token create its session atomically; the security page reloads the list for that
replacement token. Global sign-out also invalidates outstanding setup/challenge/
reset tokens through the existing account version checks.

Individual revocation is idempotent from another valid own session and records
one audit event. Revoke-others ends active own sessions except the caller; a later
fresh sign-in is allowed. At most 20 sign-ins remain active. A new sign-in beyond
the cap ends the oldest active session, ordered by creation time then ID.
The existing positive `ACCESS_TOKEN_MINUTES` lifetime remains in use; activity
never extends expiration.

Browser/device names are fixed vocabulary hints derived from the first 512 user-
agent characters at sign-in. They are not verified hardware identities. No raw
user-agent, IP address, location, fingerprint or bearer token is stored in this
table, returned by the session endpoints or added to their audit payloads.
Last activity updates at most about every five minutes through a short conditional
transaction. Sign-in/activity/expiry times are shown in IST. Reads and refreshes
never revoke sessions; errors label the previous results as stale and require
refresh before another mutation.

Ending a session blocks subsequent authenticated requests. Requests already
admitted may finish, downloaded files cannot be recalled and queued case work is
not cancelled by signing out. No provider calls or messages are sent by these
controls. This feature does not add an automatic session-record cleanup job:
expired/revoked metadata stays retained pending a reviewed security-record
retention policy. User deletion cascades session rows; audit retention is separate.

## API and verification

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/v1/auth/sessions` | Up to 20 own active sign-ins with current marker and checked time |
| POST | `/api/v1/auth/sessions/{id}/revoke` | End own session; another user's ID returns 404 |
| POST | `/api/v1/auth/sessions/revoke-others` | End other active own sessions, retaining caller |
| POST | `/api/v1/auth/logout` | End caller session |
| POST | `/api/v1/auth/logout-all` | Existing global sign-out plus retained session revocation |

Responses, including access failures, use `private, no-store`. Reads use the
shared lookup budget. Mutations retain shared authentication API budgets and
the existing per-user 20-attempt/15-minute security-action limit. Session IDs
are operation references, not standalone credentials.

Trusted server/test callers may use `create_access_token(user)` for a committed
user. Callers already creating/updating a user in a transaction pass `db=...`
and commit the surrounding transaction; staff login, security actions and
isolated performance fixtures use this form. Never expose this helper as an
endpoint or treat its `mfa=True` argument as a substitute for factor verification.

Tests cover ownership/role/audience boundaries, malformed and legacy tokens,
MFA/setup isolation, file denial, individual/other/global revocation, activity
throttling, expiry/caps, audit rollback, shared security limits, migration
preservation and real PostgreSQL sign-in/global-revocation concurrency. Browser
checks cover responsive accessibility, explicit confirmations, failed lookup/
mutation behavior, server-confirmed ordinary sign-out, replacement tokens and
signed-out access. All authentication tests use isolated synthetic records;
no real staff session is created or revoked to verify the feature.
