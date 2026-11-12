# Customer account-summary download

Verified customers can open **Download my summary** at `/account/data` to keep a
JSON copy of their current profile, preferences and request activity. The page
shows coverage counts before the customer explicitly starts the download. It
does not fetch the full summary automatically or publish a download link.

This is a current activity summary. It does not complete a formal access request,
provide a full case evidence copy, or certify a payment/refund or legal opinion.
Customers can use the existing Privacy requests workflow for a fuller reviewed
copy, corrections and deletion enquiries.

## Scope

The `homexo-account-summary-v1` JSON includes only these selected fields:

- Profile: current name, email, verified phone digits and account/profile times.
- Notification preferences: current channel choices, revision and change time,
  including the existing defaults when no preference row exists.
- Requests: ticket number, title, service/package, status/label, creation/update
  times, count of case documents, generic file-preservation state and effective
  external-document-AI permission state/change time.
- Meetings: owning ticket, scheduled start/end times, status and creation time.
- Payments: owning ticket, amount/currency, status, creation/paid times and known
  refunded/pending amounts. Monetary amounts are integer **paise**, not rupees.
  These are payment-attempt records, not an invoice or a sum of money collected.

File contents, filenames/storage paths, download links, report text, messages,
chat, original intake answers, internal notes and private preservation/consent
snapshots are excluded. So are staff account identifiers/contact details, meeting agendas/join links,
gateway identifiers/payment URLs/failure notes, authentication records, tokens,
login codes and raw audit history. A field allowlist is used instead of dumping
database objects or reusing staff views.

Case ownership follows the same verified-phone rule as the account/request APIs,
including requests raised before sign-up. Staff tokens cannot impersonate an
account for this endpoint. No customer ID or phone selector is accepted. All
related meeting/payment records are restricted to the selected owned cases, and
case ownership is rechecked before the file is prepared.

## Limits and consistency

The self-service download supports at most **1,000 requests**, **2,000 meetings**,
**2,000 payment records** and **5 MiB** of encoded JSON. The backend checks one
extra record per collection before serialization. It refuses oversized summaries
instead of silently truncating them; customers are directed to Privacy requests.
The older account overview's 100-request display cap does not limit this download.

Preview counts can change before download. The file records its own counts and
generation time and uses records observed during preparation. It is not a
transactionally frozen historical snapshot across all account tables. If ownership
changes during preparation, the request refuses the file and asks for refresh.
Times are ISO 8601 with a UTC offset; the page labels its checked time in IST.

## Preparation and privacy controls

The file is constructed in memory and returned as a private/no-store JSON
attachment named `homexo-account-summary.json`, with `nosniff`. No case files are
opened and no external processor is contacted. The server creates no stored
archive, temporary export file, public URL or delivery notification.

Successful server preparation appends `privacy.account_summary_prepared` to the
protected audit log. Metadata contains only format version and record counts;
the customer account is the entity reference. No exported personal text is copied
into audit metadata. This event proves preparation, not successful browser
delivery. If the audit write fails, the file is not returned. Preview reads create
no such event, and downloading does not resolve a formal privacy request.

The browser starts a file only after the explicit download action and only if the
same customer session is still active when preparation returns. It releases its
temporary object URL after the browser claims the file. Counts are retained and
labelled stale after a failed request; refresh is required before retrying.
Retry-After delays are respected. Customers should store their downloaded copy
privately; the application does not control copies once downloaded.

## API and rollout

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/v1/account/data-summary` | Authenticated coverage counts, limits, scope and readiness |
| GET | `/api/v1/account/data-summary/download` | Authenticated owner JSON attachment; no selectors |

Both require the current verified customer session and return private/no-store,
including access failures. Coverage reads use the shared lookup budget. Download
attempts use a separate `API_ACCOUNT_SUMMARIES_PER_HOUR` budget, default **5** per
hour, enforced for both verified session identity and client address. Failed
preparations also consume this budget. Compose forwards the setting to the API.

No migration is required; schema remains at `0044_document_preservation`.
Restart API and deploy the web/shared-client changes together. There is no new
scheduled worker, provider credential or storage service to configure. The local
preview was checked anonymously only; no real customer's summary was downloaded.

Tests use synthetic records and disposable databases. They cover ownership and
staff denial, private-field exclusions, exact paise amounts, more than 100 owned
requests, collection/payload refusal, session revocation, budget separation,
ownership rechecks, no provider/file access and failed-audit rollback. Browser
checks inspect the downloaded JSON and cover session changes, retry behavior,
signed-out access, mobile widths and accessibility.
