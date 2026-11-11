# Reviewed intake-form restoration

Administrators can republish an earlier service-specific form at
`/admin/intake-forms`. Open **Private form publication history**, inspect the
published questions or expand **Previous questions**, then choose **Review
restoration of version N**. The restoration preview shows the exact retained
question definitions. Enter a new **Private restoration reason** (10–1000
characters), then choose **Publish restored version**.

Opening history, selecting a version and cancelling do not publish anything.
The original empty version can be restored when its definition survives in the
first publication's preceding snapshot. Retired services have readable history
but cannot publish. Current/future versions and definitions already matching the
published form cannot be restored.

## Versions, drafts and history

Restoration creates the next version; it never rewinds a revision or overwrites
an earlier publication. Newly selected services use the restored form. Saved
customer drafts and submitted cases keep their original questions, answer labels,
answers and consent records. Clearing supplemental questions by restoring an
empty form does not remove standard guided questions.

Preview and cancellation keep unpublished editor questions and the existing
publication reason. A successful restoration also keeps those local edits when
present and requires a fresh ordinary review before publishing them. An untouched
editor adopts the restored questions. The success notice explains which happened.
**Reload published form (replaces draft)** explicitly replaces local edits;
selecting another service also leaves the current editor. These local drafts
exist only in component state.

Preview, success and restoration errors receive keyboard focus. Cancellation
returns focus to the source action. A conflict retains both the editor draft and
restoration reason for review; cancel and explicitly reload before trying again.

The publication audit retains actor, timestamp, new revision, previous/new
questions and the private reason. Restoration adds the source revision, retained
event ID and whether the source was its published or preceding snapshot. History
shows **Restored from version N**. Private event IDs used for source provenance
are not added to customer responses or the history response allowlist.

## API and consistency

`POST /api/v1/admin/intake-forms/{slug}/restore` accepts:

```json
{
  "revision": 3,
  "source_revision": 1,
  "preview_questions": [],
  "reason": "Restore the original empty form after review.",
  "confirmed": true
}
```

Revisions must be strict positive integers, and confirmation must be the boolean
`true`. Question definitions follow the existing bounded publication schema;
unknown fields, duplicate question identifiers and invalid definitions fail
validation. The API locks the service row and checks its current revision before
writing. A competing publication or restoration yields one successful write and
one stale conflict.

The source lookup is scoped to the same service and publication action. It uses
the source publication's questions, or, if that event is absent, the immediately
following publication's preceding questions. Missing retained history returns
404. Ambiguous, invalid or unreviewable snapshots return 409. Historical revision
metadata must be an integer, and unrelated malformed values cannot break the
lookup. The server validates retained definitions again and compares them with
the submitted preview before publication. A changed preview, stale current
revision, retired service or unchanged question set returns 409 without a new
publication or audit record. Invalid request payloads return 422.

Administrator authentication is required: absent/customer credentials receive
401 and agents receive 403. Responses use private/no-store caching, and POST
uses the existing shared write budget. Restoration changes only the service form
and its audit history; it does not send notifications or alter service availability.

## Deployment and verification

Deploy API and website together. There are no new dependencies, secrets or
migrations; schema remains `0038_service_intake_forms`. Its existing downgrade
guard also protects restoration publications and advanced revisions. Do not
delete history or reset revisions to bypass it.

Run tests from `backend` against disposable data only; fixtures drop and recreate
application tables:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_intake_form_restoration.py tests/test_service_intake_forms.py
```

Use a dedicated disposable PostgreSQL database for the publication/restoration
race test. Browser fixtures in `intake-restoration.spec.ts` cover reviewed
publication, no-write cancellation, focus, draft preservation, subsequent fresh
publication, stale and changed-source conflicts, empty baseline restoration,
access boundaries, axe and desktop/phone/narrow layouts. All browser publications
use synthetic intercepted API responses.

Local verification on 11 November 2026 passed the full SQLite suite (748 tests,
40 skips), PostgreSQL regressions (85 tests, including the competing-write race)
and 45 browser checks across desktop, phone and narrow layouts. Browser checks
also cover access to retained history when every service is retired. Workspace
type checks and the production build passed. Lint had no errors and seven
existing warnings; Bandit reported no medium/high severity findings. Desktop and
phone restoration screenshots were inspected.

The disposable PostgreSQL test database was removed. The local API and website
previews were refreshed without a migration; health, readiness, homepage and
editor returned 200. Anonymous restoration returned 401 with private/no-store
caching. No forms were published to the normal preview, and delivery and
background workers remain disabled.
