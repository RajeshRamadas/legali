# Staff account security

Staff sign-in supports passwords, RFC 6238 authenticator codes and single-use recovery codes. **Security** in the staff navigation offers authenticator enrollment, recovery-code rotation, password changes and sign-out on every device. Customer phone sign-in remains separate.

[Staff session management](staff-sessions.md) now adds active sign-in review,
individual/other-session revocation and server-confirmed ordinary sign-out.
Migration `0046_staff_sessions` requires existing staff to sign in again;
passwords, enrolled authenticators and recovery codes are preserved.

## Deployment

1. Install backend requirements and run `alembic upgrade head`. Migration `0018_staff_account_security` adds encrypted enrollment data, session versions, hashed one-time tokens and persistent rate-limit buckets. Existing staff tokens are invalid after this change: everyone must sign in again. Accounts and passwords are preserved.
2. Keep a long, random `JWT_SECRET`. Set a separate `STAFF_MFA_ENCRYPTION_KEY` in the secret manager before enrolling staff outside development. Generate a Fernet key with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Never commit it or expose it through `NEXT_PUBLIC_` variables. Preserve it with the protected backup/recovery process: losing it prevents authenticator verification. Rotate it by securely rewrapping stored seeds or conducting verified re-enrollment; changing the value alone does not re-encrypt existing seeds.
3. Blank/unset `STAFF_REQUIRE_ADMIN_MFA` requires administrators to enroll when `APP_ENV` is anything other than `development`. In development, MFA is optional and a separate development-only encryption key is derived from the signing secret. Set `STAFF_REQUIRE_ADMIN_MFA=true` to exercise mandatory enrollment locally. Explicit `false` opts out of the admin requirement; enrolled accounts still always need a second factor.
4. Configure `RESEND_API_KEY`, a verified `EMAIL_FROM`, and `PUBLIC_SITE_URL` with the trusted HTTPS website address to enable recovery email. Reset URLs use this configured address, never the request Host header. Missing email configuration returns the same unavailable response for every address. Live delivery requires provider setup; tests use synthetic accounts and a mocked transport.
5. Use HTTPS and a synchronized server clock. TOTP accepts the current 30-second interval plus one interval on either side, and refuses already-used counters. After using a code, wait for the next code before using another protected action, or use a recovery code.
6. Run `python -m app.staff_auth` daily to remove expired authentication tokens and old throttle buckets after one day. Behind a proxy, configure uvicorn `--proxy-headers --forwarded-allow-ips=<trusted proxy address>` so limits count actual clients. Arbitrary `X-Forwarded-For` headers are not trusted by the application.

## Sign-in and enrollment

A correct password returns a five-minute challenge when an authenticator is enabled. The challenge cannot access staff or customer APIs; completing it with an authenticator/recovery code returns the staff session. Challenges allow at most five code attempts and work once. Login limits allow 10 password attempts per account and 60 per client in a fixed 15-minute window; MFA confirmation has its own 60-per-client limit. Limits use atomic database counters and apply across workers. `429` includes `Retry-After`.

An administrator who must enroll receives a ten-minute token scoped only to authenticator setup and confirmation. It cannot open the workspace, download files, change passwords or disable MFA. Enrollment requires the current password, a locally generated QR/manual setup key, and a valid code within ten minutes. Completing enrollment revokes older staff sessions and shows eight recovery codes once. Save them before continuing. Seeds are Fernet-encrypted; only keyed hashes of recovery codes are stored.

All enrolled staff must use a second factor. Administrator MFA cannot be disabled when policy requires it. Disabling optional MFA or generating replacement recovery codes requires the current password and a second factor. Replacement codes invalidate every previous code. There is no remotely callable administrator override of someone else's MFA. If both authenticator and recovery codes are lost, use the organization's verified, audited account recovery process; email recovery alone cannot remove MFA.

## Password recovery and sessions

**Forgot password?** returns the same response for eligible and unknown addresses. Only active staff accounts with passwords receive mail. Requests are limited to three per address and ten per client per hour, including unknown addresses. Reset links last 20 minutes, are single-use, and requesting a newer link invalidates the previous one. Tokens are saved only as keyed hashes. The raw token exists only in the email and process memory, never a ticket/notification record or audit metadata.

Recovery email is sent directly after the request transaction in a background task. If delivery fails, the link is invalidated and only a safe error code is logged. A process shutdown before sending can lose the email; ask for a new link. Reset links are deliberately excluded from the general notification retry queue, which persists message content.

The link carries its token in a URL fragment, removed from the address bar when opened. It is never sent in a page request, query string or referrer. Admin pages set a no-referrer policy; authentication API responses use `private, no-store`. Tokens stay in component memory while entering the new password. Reloading the reset page requires reopening the email link or requesting a new one. Do not add analytics or email click tracking to recovery links.

New/reset passwords need at least 12 characters. Enrolled accounts also need an authenticator or unused recovery code to reset a password; recovery never disables MFA. Reset confirmation permits five attempts per token and 30 per client per 15 minutes. Reset success signs out every staff device and requires a fresh sign-in.

Changing a password, enabling/disabling MFA, rotating recovery codes, changing staff roles/status, and **Sign out all devices** increment the account's session version. Old access, enrollment and challenge/reset tokens are rejected immediately. Password changes and MFA management return a replacement session for the current tab. Account-security actions have a shared 20-attempt limit per user per 15 minutes, and are audited without passwords, seeds, raw codes or reset tokens. Rotating `JWT_SECRET` invalidates signed sessions and outstanding token/recovery-code hashes; plan replacement recovery codes as part of that operation.

## Checks

Run `python -m pytest -q` in `backend/`, then workspace type checks, frontend build and lint. `tests/test_staff_security.py` covers the RFC TOTP vector, encryption, recovery and code replay, expiry, enrollment scope, mandatory admin MFA, wrong/legacy/customer tokens, session revocation, generic reset responses, delivery failures, throttling and safe email links. Also exercise pairing, recovery-code download, MFA login, password reset and small-screen layout in the browser using synthetic accounts.
