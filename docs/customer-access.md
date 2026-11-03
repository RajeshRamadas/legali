# Verified customer access

A ticket number and a known phone/email no longer grant access to private records. Customers sign in using the existing phone OTP flow. Every protected operation checks the customer JWT audience, expiry, account existence, token version, and ownership by normalized phone. Another account receives 404, whether or not it knows the ticket's contact details. Staff tokens cannot act as customer tokens.

Protected operations include ticket lookup/replies, property intake, document upload/tag/delete, booking lookup/cancel/reschedule/reviews, payment start/verify/refresh, and ticket-aware chat. General chat, public catalogues/search, callback enquiries and new consultation booking remain public. Authenticated responses and chat responses are private and not cached.

File links require both a valid short-lived link and a current owner or authorized staff session. Customer sessions cannot open draft preliminary reports or unsigned final report PDFs. The API streams S3 files after authorization instead of redirecting the browser to an unauthenticated presigned URL. Logging out everywhere invalidates earlier sessions, including file access. Staff access still follows case-assignment permissions.

## Clients

`createApiClient(baseUrl, { getToken, onUnauthorized })` resolves authentication for each request. The website and mobile client supply the current account session. Expired sessions are cleared; delayed failures from an older session do not clear a newer session. Website tracking, document and booking pages show the OTP form before fetching private data. Guest payment actions also prompt for verification. Website downloads use `FileLink`, which sends a bearer header without putting session tokens in URLs.

Existing API consumers must send customer bearer tokens on the protected endpoints. Keeping the old `contact` parameter is supported, but it is checked only after account ownership. Email-only historical requests cannot be accessed by proving knowledge of the email; the case team must verify the customer and link the request to a phone through its authorized data-correction process. No automatic email-to-phone claiming is provided.

## Operation and validation

Production sign-in requires the existing WhatsApp authentication template and credentials. Development OTP codes appear only in development API responses, never in application logs; setting the development flag in production does not enable them. No database migration or new dependencies are required.

Run `python -m pytest -q -rs` in `backend/`, then `npm run typecheck`, `npm run build --workspace frontend`, and `npm run lint --workspace frontend` from the repository root. Authorization regressions cover missing/invalid/expired/staff tokens, another verified customer with the correct contact, uploads/downloads, unassigned staff, logout revocation, linked conversation isolation, and production OTP fail-closed behavior.
