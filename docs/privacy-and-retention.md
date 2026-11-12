# Privacy requests and anonymous chat retention

Administrators can now place [case document preservation holds](document-preservation.md)
to prevent application deletion/replacement of stored files during a records
review. These controls are separate from anonymous-chat cleanup and from approval
of a privacy-request outcome. A hold does not freeze every kind of case data.

Verified customers can use **Privacy requests** at `/account/privacy` to ask for access to information, a correction or deletion. They can scope a request to an owned ticket or their account generally, view the team's response and withdraw an open request. Administrators review requests at `/admin/privacy`; agents cannot read this desk. The existing phone sign-in, session revocation, staff MFA and administrator authorization rules apply. No new provider integration or live message delivery is added; customers follow progress in the authenticated center.

Apply migration **`0023_privacy_requests`** and restart API/workers. It adds privacy requests, explicit conversation account ownership and a retention-hold flag/index. It preserves existing case, account, payment, document, consent and chat records. Because old general chats did not record whether the caller was signed in, migration places existing conversations without a customer link on retention hold. Review those legacy holds before releasing any; ownership cannot be reconstructed safely from a shared client-IP hash. Migration rollback drops the new request/hold/ownership fields, so preserve a backup before any rollback involving real requests.

## Customer and administrator workflow

- Request types are access, correction and deletion. The server derives the owner from the verified account. Optional ticket scope is checked against that account's ownership; knowing another ticket/request ID does not grant access.
- Every creation uses a client submission UUID. Retrying the same submission returns the original record, including after it closes/withdraws. Reusing its key with different details is rejected. Only one open request per type/account is allowed, backed by a database unique index and account row lock. `PRIVACY_REQUESTS_PER_DAY` defaults to **5** per rolling 24 hours, including withdrawn and closed requests. Writes also consume the shared API abuse budget.
- `PRIVACY_REVIEW_DAYS` defaults to **30**. It sets a persisted operational review target at submission, not a statutory response deadline. The desk highlights overdue open requests. Changing the setting affects future requests only.
- Administrators move a submitted request into review before closing it. A close requires an outcome (fulfilled, partial or declined) and a customer-facing explanation of at least 20 characters. Partial/declined outcomes also require a reason. Internal review notes are separated from customer-visible responses; customer endpoints never return them or reviewer identity.
- Updates and withdrawal require the current revision. Account/request locks serialize customer/admin changes; stale saves return **409** and keep the user's draft in the UI until they explicitly reload. Closed/withdrawn records are immutable. Customer withdrawal is idempotent; a new request needs a new submission key.
- Queue summaries omit request details and show only the customer's name and phone's last four digits. Full request detail is fetched separately by an authenticated administrator. Authenticated responses are private/no-store. Logs use route templates and do not contain request details or note text. Audit rows record actor, request ID, kind, revision and status transition without duplicating personal text.

Review and perform the approved privacy action through the appropriate account/case/records procedure **before** marking it fulfilled. The review workflow does not automatically erase an account, case evidence, signed reports, payments or consent records. Access exports, correction of evidence, identity/scope clarification, redaction and any deletion involving those records need the reviewed procedure and applicable retention assessment. Explain retained records and their reason in the customer response. Protect third-party information and staff-only material when providing an access copy. Closed privacy requests and their audit records also need a legally reviewed retention policy; they are not swept by the anonymous chat tool.

The customer notice is versioned as `privacy-requests-v1`, recorded on each request and available at `/api/v1/privacy/notice`. Review its wording, operational targets, jurisdiction-specific obligations and grievance/contact process before production. This workflow does not itself establish legal compliance.

## Conversation ownership

New general chats made while signed in are tied to that customer account. Only the verified owner can resume them, including from another network. Anonymous continuations require both the conversation ID and the original trusted client-address hash. On sign-in, a valid anonymous continuation can become account-bound. A case-linked conversation continues to require case ownership. Callback creation checks the same account/client ownership before linking a transcript. Invalid or another account's identifiers return **404**.

Chat append and case-link paths lock the conversation row before accessing/updating it. Cleanup and hold changes lock the same row. With PostgreSQL, cleanup skips currently locked rows instead of deleting a chat being resumed or linked. A genuinely expired anonymous conversation already removed by policy can start a new chat when the client next sends a message; it does not resurrect old content.

## Retention policy and preview

`CHAT_RETENTION_DAYS` defaults to **90** inactive days. Cleanup only considers conversations that:

- Have no account, customer or property association, no ticket reference, and are not submitted.
- Have no recorded consent or consent metadata, and no intake JSON other than an empty object.
- Are not on an explicit hold, and have creation/update timestamps older than the cutoff.
- Have no message at or after the cutoff, even if a legacy parent's activity timestamp is old.

Case-linked transcripts, signed-in chats, consent records, documents, case history, payments, draft records and privacy requests are excluded. Backup and log retention are separate policies. The administrator retention card shows only policy/eligible/held counts and cannot execute cleanup.

From `backend/`, with the intended database environment:

```bash
python -m app.retention cleanup
# Equivalent count-only default:
python -m app.retention
```

The default is a dry run even if the policy is enabled. Output contains counts and settings, never conversation IDs, message bodies, client hashes or customer information. Review candidate counts, legacy holds, record requirements and backup retention before enabling deletion. `CHAT_RETENTION_ENABLED` defaults to **false**. No task in this implementation enables or executes cleanup against production data.

After your retention policy is approved, set `CHAT_RETENTION_ENABLED=true` and schedule an explicit bounded apply:

```bash
python -m app.retention cleanup --apply --batch-size 100
```

Both the enabled policy **and** `--apply` are required. Each invocation removes at most 100 conversations by default, with a hard batch limit of 500. `more_eligible` indicates that additional eligible rows may remain, including ones skipped because they were locked. Schedule repeat runs for the desired throughput. Each batch deletes parent/messages atomically with a count-only audit event; failure rolls everything back. Runs are idempotent and never cascade into cases or consent. PostgreSQL is required for concurrent production cleanup; SQLite regressions run single-threaded.

## Holds and releases

An authorized operator can use:

```bash
python -m app.retention hold <conversation-uuid> --reason privacy_review
python -m app.retention release <conversation-uuid> --reason manual_review
```

Other supported reasons are `legal_obligation` and `manual_review`. Commands require the deployment's database credentials; they are not public HTTP actions. Holds block cleanup regardless of age. Release does not bypass account/case/consent protection or change the conversation's last activity time. Changes are audited with a fixed reason code and no free-text personal data. For a privacy request involving a known unlinked conversation, place a hold before investigating; the customer's account-wide request cannot identify an anonymous chat automatically. A hold cannot recover records already deleted under an approved policy.

Recovery from an older backup may bring back removed anonymous chats. Reapply the current retention/hold decisions before exposing restored data, and follow backup expiry/off-host copy policies. Keep legal holds and request decisions available to the recovery operator. Do not run broad business-record deletion SQL from this runbook.

## Validation

Run `pytest tests/test_privacy.py tests/test_retention.py` from `backend/`. Tests cover account/admin boundaries, case ownership, idempotency, open/daily limits, private-note separation, revision/terminal-state checks, authenticated/anonymous conversation ownership, every retention exclusion, disabled/dry-run protection, batching, hold audit/activity preservation and rollback. A **disposable** PostgreSQL `TEST_DATABASE_URL` enables concurrent creation/decision tests and skip-locked cleanup; fixtures drop tables, so never point them at a live database.
