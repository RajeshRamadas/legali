# Case document preservation holds

Administrators can use **Documents and legal report → Document preservation** on
a case to place or release a file hold. **Document holds** at
`/admin/document-holds` lists current active/released decisions, with explicit
status/reason/ticket filters and case links. No files are removed by these controls.

A hold blocks deletion of the case's stored document records and files through
the customer/staff application. It also blocks replacing a stored final-report
PDF, before rendering/writing a replacement object. It covers existing and newly
added case files until an administrator records a reviewed release.

## Decisions and visibility

Each transition requires a reason (`privacy_review`, `legal_obligation` or
`manual_review`), a private review note of 20–2000 plain-text characters, the
current decision revision and an explicit UI confirmation. A stale revision or
duplicate state returns 409. Releasing a hold does not bypass ordinary file
ownership, closed-case, accepted-item or signed-report restrictions.

The current state lives in `case_document_holds`; each transition appends an
audit event containing the decision revision, reason and original note. Existing
audit guards protect those events. Administrators can review the latest ten
decisions in the case. Prior decisions remain in audit history. The activity
index uses safe labels and never exposes note payloads.

Other staff need existing case access to read the active status. They cannot
manage holds or load private reasons, notes or decision history. Customers see a
generic preservation message and no remove controls for held files. They do not
receive private review details, administrator identity or hold reasons. Server
checks remain authoritative if an old browser still shows a remove button.

The case controls and queue have explicit refresh. A failed request preserves
the last labelled snapshot and unsaved review/filter text. Refreshing a decision
keeps the review note but clears confirmation, so the administrator must review
the current state again. Preservation changes do not reload the case's unsent
customer reply, internal note or report draft. Queue pages use applied filters;
unapplied edits remain separate.

## Enforcement and concurrency

Hold changes and file removal serialize on the same service-request row lock.
The common removal helper checks current persisted hold state before changing a
document record or deleting its object. The lock lasts through commit/rollback.
A removal waiting for a hold transaction rechecks the committed hold and refuses
deletion. A removal already admitted before a hold may complete first; the hold
applies once its own transaction is accepted. No API recalls a completed removal.

Final-report generation locks the case before checking for an older stored PDF.
If replacement would remove a held file, it stops before rendering or storing a
new one, avoiding an orphan replacement object. Creating the first final PDF and
adding a signed scan do not remove existing stored files and remain possible
under their usual workflow rules.

Uploads, authorized downloads, retagging, security scans and advocate work can
continue. Malware rules still deny unsafe downloads. A clean rescan may relocate
an identical, checksum-verified file from quarantine before removing the old key;
the document's bytes remain preserved at the new key. File preservation does not
block customer withdrawal of external-AI permission.

## Boundaries and rollout

This is an **application file-deletion/replacement hold**. It does not freeze all
case metadata, report text, AI results, chats or every rendered preliminary PDF.
It is not an object-storage WORM lock, a database-owner restriction, a retention
period or a complete legal-hold policy. Direct storage/SQL administration,
backups and any future case-purge tool need their own reviewed retention controls;
a future deletion tool must check holds under the same case lock. One current
case state is recorded, not multiple independent holds with separate owners.
Review all preservation obligations before releasing it.

Apply migration `0044_document_preservation` before restarting the API. It creates
an empty hold table and changes no existing files, AI choices or case outcomes.
No historical holds are inferred and no cleanup schedule is enabled. Empty
downgrade works; downgrade refuses any retained preservation decisions, including
released ones. Preserve records and use a forward fix or reviewed recovery.

The local preview has no real holds created by this implementation. Tests use
synthetic temporary storage and disposable databases. Operators still need a
reviewed preservation/retention policy, accountable reviewers and a procedure for
responding to related privacy requests. Recording a privacy request as fulfilled
does not itself remove evidence or release a hold.

## API

| Method | Path | Access |
| --- | --- | --- |
| GET | `/api/v1/admin/tickets/{ticket}/document-hold` | Staff with current case access; private fields only for administrators |
| PUT | Same path | Administrator, `{held,revision,reason,note}` |
| GET | `/api/v1/admin/document-holds` | Administrator; `status=active\|released\|all`, `reason`, ticket substring `q`, `page` |

The queue defaults to active holds, newest decision first, 25 rows per page.
`active_count` covers all active holds; `total` covers the applied filters.
Queue rows omit private notes, customer identity and storage paths. Responses
and access errors are private/no-store. Lookups and writes use existing shared
budgets. There is no delete decision, bulk release, export or cleanup API.

Tests cover ownership and role boundaries, blocked customer/staff/direct-helper
removal, retained bytes/downloads, allowed uploads, stale decisions, audit
history, final-report replacement without orphan writes, queue filters and
PostgreSQL case-lock concurrency. Browser checks cover draft preservation,
read-only staff, responsive layouts and accessibility.
