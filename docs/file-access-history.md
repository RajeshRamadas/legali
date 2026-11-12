# Private file access history

Administrators open **File access history** at `/admin/file-access` to review
authorized private file requests. The read-only view combines reader (customer
or staff), stored-file/preliminary-report type, exact case ticket and inclusive
India-calendar-date filters. Cursor paging and explicit refresh preserve
unapplied filter edits; failed reads keep the previous page with a stale-result
message. A current case links to its existing restricted workspace.

## What an entry means

`GET /api/v1/files/{token}` already requires a current customer/staff session,
a valid expiring file link and current case permission. After those checks and
the applicable clean-scan/customer-visibility checks succeed, the API commits an
append-only **access authorized** event before opening the storage stream or
generating a preliminary PDF. Failure to commit that record fails the request;
private bytes are not released without the authorization record.

An event records a permitted request, **not** completed delivery, file reading or
proof that a person saw the contents. Storage lookup, PDF generation, streaming,
client disconnects or invalid ranges can fail after authorization. Authorized
requests for a database file whose stored object is missing are retained too.
Repeated opens, previews and HTTP range requests create separate records. These
records are not unique-person or completed-download counts.

Missing/rejected sessions, expired/invalid links, another customer's case,
unassigned staff, unavailable file records, quarantined files and hidden customer
reports do not create successful-authorization events. This feature does not
provide a denial log or change file access permissions. Existing malware,
ownership, staff-role and session-revocation checks remain authoritative.

## Retained and displayed data

Four fixed actions distinguish customer/staff and stored-file/preliminary-PDF
authorization. Each record uses the existing `audit_logs` table and its database
update/delete/truncation guards. It retains the case UUID, file/report UUID,
timestamp and staff actor UUID or verified customer-account UUID. It does not
copy file names, file contents, storage keys, signed links, bearer tokens,
addresses, IPs, raw user-agent headers or customer contact details.

The administrator response selects the known action, references and current
staff display name, plus one allowlisted file-reference field from JSON. It
never returns the complete audit payload, customer-account UUID, request IDs,
IP hashes or arbitrary action text. Malformed historical file references are
masked rather than displayed. Customers are labelled **Verified customer**;
staff names are their current display names, with a former-staff fallback.

The case and file references are retained even after a file is deleted. If a
case is no longer available, the view keeps the event without inventing a case
link. These events also appear with fixed labels in the existing administrator
Activity history. Neither view opens/downloads a file or records another file
authorization just by listing or refreshing history.

## Deployment and retention

Apply migration `0047_file_access_history_index` and restart the API, then deploy
the frontend. The migration adds action/time and case/action/time indexes only;
it does not rewrite audit history, remove guards, create customer sessions or
require a new sign-in. Empty and populated index downgrade/upgrade preserve
existing records and guards. Review index-build locking and expected audit
volume before applying to a large production audit table.

Capture starts with the new API code. No historical access is inferred from old
links, uploads or other audit events. Deploy API instances together for consistent
capture; old instances do not append the new access events. Rolling back capture
does not erase records but creates an unrecorded interval. Audit/security-record
retention, log storage capacity, backups and authorized evidence-copy procedures
remain separate operational decisions. No automatic purge or export is added.

## API and validation

`GET /api/v1/admin/file-access` accepts `reader=all|customer|staff`,
`kind=all|document|preliminary_report`, `ticket_number`, `from_date`, `to_date`,
`cursor` and `page_size` (default 25, maximum 50). Only administrators may read
it; agents/customer sessions are denied. Unknown action types are omitted.
Dates use Asia/Kolkata boundaries. Ordering is timestamp then UUID, newest first;
newer arrivals do not disturb an existing traversal of older records. An exact
ticket filter requires a currently retained case record.

Responses and access failures are `private, no-store` with authorization-aware
cache variation. Shared lookup budgets cover review reads; existing download
budgets still cover file requests. The feature sends no provider messages and
has no mutation, retry-download, bulk-download or customer-impersonation endpoint.

Backend tests cover owner/role boundaries, safe record content, preliminary and
stored files, rejected/quarantined links, range requests, missing storage,
post-deletion preservation, fail-closed audit failures, filters, cursor ties,
malformed references, API budgets and index/guard preservation. PostgreSQL checks
exercise JSON field selection and actual append-only guards. Browser checks use
synthetic fixtures for responsive accessibility, explicit filters, paging,
stale results, retries and restricted navigation. No real customer file was
opened to verify this feature.
