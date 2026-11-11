# Customer permission for external document AI

Verified customers can open **Documents → External AI processing** for a case to
review the named processor and privacy policy, allow document processing, or
withdraw permission. The choice is optional and case scoped. Uploads, local
extraction and advocate review remain available without it. Staff can see the
choice in the verification panel and refresh it; they cannot grant or withdraw
permission on the customer's behalf. Full-case AI requests still require the
existing explicit staff authorization as well.

## Rollout

1. Back up the database, stop old API/verification worker processes, and apply
   `alembic upgrade head` from `backend/` (migration `0043_case_ai_consent`).
2. Review the disclosure in `app/ai_processing.py` and your actual processor's
   contract, privacy terms, retention and data-sharing arrangements. Configure
   `VERIFICATION_PROCESSOR_NAME` (plain public name, 2–120 characters) and
   `VERIFICATION_PROCESSOR_PRIVACY_URL` (valid HTTPS URL without credentials).
   These are public customer-facing fields; never put credentials in them.
3. Configure the actual verification provider separately. For an OpenAI-compatible
   gateway, name the actual processor and use its policy; the adapter name does
   not establish who handles the data. HTTPS endpoints must be valid and have no
   embedded URL credentials. Compose forwards the public fields to API and worker.
4. Restart API and optional verification workers with the same processing and
   disclosure settings. Confirm the customer notice, default-denied state and
   existing case access before admitting external work. There is no deployment
   switch that grants customer permission automatically.

Blank/malformed public processor settings prevent new grants and external case
document processing. Existing choices can still be withdrawn. The migration
creates an empty consent table: historical uploads, staff confirmations, general
intake consent and earlier AI activity are **not** interpreted as permission.
Legacy queued AI jobs have no consent revision and are rejected when processed.
No historical documents are transmitted by the migration, a grant or a refresh.

The preview remains unconfigured for these public processor fields; no real
customer permissions or provider calls were created during implementation.

## Data and scope

The notice covers document text, filenames, scanned-page images, property details
and curated legal references sent for automatic upload checks and staff-requested
full-case analysis. The saved choice is bound to a hash of the notice text/version,
processor adapter and endpoint, public processor name and privacy URL. Changing
that identity/notice requires customer review for the new configuration. Credential
rotation, model overrides and price-rate changes do not rewrite this permission.

Chat and research are separate services outside this case-document choice. AI
advice remains subject to source checks and advocate review; it cannot approve a
checklist item, verify official records or replace a signed opinion. This feature
does not establish legally sufficient notice wording or the processor's retention
terms; the deployment owner must review those before use.

New uploads can be checked automatically only when the provider/upload-check
feature is enabled **and** current case permission exists. Older uploads are not
replayed when permission is granted. Staff can deliberately use **Check again**
under the existing case permissions. No automatic provider retry is added.
Files without a check display `awaiting_consent` instead of polling indefinitely.
Previously saved results remain part of the case record after withdrawal.

## Withdrawal and concurrency

Updates use a strict boolean, optimistic choice revision and an explicit current
notice/revision for grants. A stale update returns 409 and cannot overwrite a
newer withdrawal. The UI keeps failed confirmations, disables resubmission until
refresh, and requires the user to confirm again after refreshed information.

The API stores a choice in `case_ai_consents`, independently of the case row lock.
Withdrawal updates that choice row without waiting for provider work holding a
legacy synchronous case lock. Authorization is rechecked before external calls
and before publishing results. Short choice-row share locks serialize publication
against a change; no choice lock spans the provider request. A request already
admitted or in progress cannot be recalled, and sent data follows the processor's
contract. A late response after withdrawal is discarded.

Background jobs bind the grant revision at submission and check it at worker
checkpoints and publication. Withdrawal or regrant does not revive an old job;
the worker marks it cancelled with `consent_changed` when it observes the change.
Status may remain queued/running until checked; external work still requires the
current permission. A fresh analysis requires a fresh reviewed submission.
Provider attempts already incurred stay in usage accounting even when no result
is accepted. Local-only jobs remain independent of this choice.

The current row keeps the choice, revision, customer-account reference, change
time and last accepted disclosure snapshot. Each change appends an audit event
with the original notice and decision provenance. Activity history exposes safe
labels; raw snapshots and customer identifiers stay out of its index. Existing
audit guards protect the history. Case deletion cascades the current choice under
existing case-retention procedures; audit retention remains governed separately.

## API and verification

| Method | Endpoint | Access |
| --- | --- | --- |
| GET | `/api/v1/account/requests/{ticket}/ai-processing` | Verified owning customer |
| PUT | Same path | Verified owning customer; `{allowed, revision, notice_version, processing_revision}` |
| GET | `/api/v1/admin/tickets/{ticket}/ai-processing` | Staff with current case access |

For withdrawal, only `allowed:false` and the current `revision` are needed. New
grants require the current notice and processing revision. Responses include the
current safe disclosure, effective status, revision, change time and ability to
withdraw. They omit endpoint URLs, keys and customer-account identifiers. Customer
and staff lookups share existing lookup budgets; writes use the customer-write
budget. Responses, including anonymous access failures, are private/no-store.

Migration 0043 also adds nullable `verification_jobs.consent_revision`, without
backfilling permission. Empty rollback is supported; downgrade refuses retained
choices or jobs with consent revisions. Use a forward fix or reviewed recovery
instead of discarding decisions. Deploy API/worker changes together: old software
does not enforce the new permission and must not keep processing work.

Tests cover default denial, ownership, strict/stale requests, processor changes,
key rotation, withdrawal/regrant, late result rejection, retained usage and real
PostgreSQL withdrawal concurrency. Browser checks cover accessibility, mobile
widths and preservation of unsent customer/staff messages. Providers are mocked;
no live credentials or document transmissions are needed for verification.
