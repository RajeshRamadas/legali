# Reviewed service descriptions and live catalogue

Administrators open **Service availability** (`/admin/services`), choose a
service and use **Public service description**. Enter 10–800 characters of
plain public text and a private publication reason of 10–1000 characters.
Choose **Review description**, inspect the preview, then **Publish reviewed
description**. Editing and previewing do not write to the API. Publishing changes
the description used by subsequent public catalogue loads immediately.

The public `/services` page has a live **Services accepting requests** catalogue,
with category and text filters, current descriptions and guided-request links.
The homepage callback form also shows the selected service's current description.
The public API continues to serve the same allowlisted fields to existing clients.
Description text renders literally, without HTML or Markdown processing. The
private reason and administrator history are never included in public responses.

Only active, unpaused services appear in the live catalogue. Refresh loads current
availability/copy while preserving the search text; an unavailable category resets
to All categories. Load errors provide retry and hide previous results. Empty
availability and empty filtered results have separate messages. Request admission
is still checked by the API when a customer submits; viewing a card reserves
nothing. Static marketing sections, packages and document-desk descriptions remain
separate editorial content and may describe currently paused services.

## Editing and history

Custom descriptions are stored separately from standard code-managed descriptions.
Startup reference-data sync preserves the custom text and its revision. Standard
descriptions can evolve through normal code releases; custom descriptions retain
their published wording until an administrator changes or restores them.

**Use standard description** prepares a reset draft. Review and publish it with a
private reason; the button alone makes no change. Reset publication includes the
exact standard text that was previewed. If that standard changes before saving,
the API returns 409 instead of publishing unseen wording. Subsequent code releases
can update a restored standard description normally.

Publication and availability use independent revisions and the same service-row
lock. Changing copy never pauses/resumes admission, creates a case or sends a
notice. Saving either editor preserves the other editor's unsaved text. Responses
update only the editor's own fields, so an unrelated save cannot silently advance
the editing revision after a concurrent administrator change. Conflicting saves
retain the draft and reason. **Reload catalogue (replaces draft)** explicitly
discards local edits; selecting another service also replaces that service's draft.
Drafts are local component state, not saved to browser storage or the database.

Expand **Private description history** to read paginated publication records:
administrator, timestamp, revision, previous/published text, standard/custom choice
and private reason. History loads lazily and retries/pages independently without
replacing the editor. Retired services keep readable history but cannot publish.
Use history and reload to investigate an uncertain save before attempting another.

Names, slugs, categories, property support, pricing, scope, question definitions,
consent and service admission policies remain controlled by their existing flows.
Publishing a description does not change them. Review public wording before
publication and keep private customer details out of the public description.

## API

- `GET /api/v1/admin/services` adds `description_revision`,
  `description_customized` and `default_description` per service.
- `PATCH /api/v1/admin/services/{slug}/description` requires strict integer
  `revision`, `description` (trimmed text, or null to restore standard), private
  `reason` and `confirmed: true`. Resets must also provide `standard_description`
  equal to the current standard text. Custom publications may omit that field.
- `GET /api/v1/admin/services/{slug}/description/history?page=1` returns 20
  events per page, newest first, with a request page limit of 10000.

All administration operations require an administrator session, private/no-store
caching and shared lookup/write budgets. Agents get 403; absent/customer staff
credentials get 401. Unknown services get 404. Invalid, coercible, extra or
control-character payloads get 422. Stale revisions, retired publications or a
changed standard preview get 409 without another publication. A current request
whose override already matches returns its current state without adding history;
a stale retry still requires reload. Public lists/details keep their existing
allowlist, unpaused/active filtering and no-store behavior.

## Deployment and rollback

Back up the database and stop old API instances before applying
`python -m alembic upgrade head` from `backend`. Migration
`0037_service_descriptions` adds an optional override, a positive description
revision and length constraints. Existing services retain their standard text,
admission settings and case links. Deploy API and website together, then check
readiness, administrator access and the public catalogue. No new dependencies,
provider configuration or background worker is needed.

Downgrade refuses while any custom override, advanced description revision or
`service.description_changed` audit history remains, including after restoring
standard text or retiring a service. Use a forward fix or reviewed recovery;
do not clear history/revisions just to bypass this protection. Standard database
backup, business-record retention and access review cover publication history.

## Verification

From `backend`, run against disposable data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_service_descriptions.py tests/test_service_descriptions_migration.py tests/test_service_availability.py
```

Use a dedicated disposable PostgreSQL `TEST_DATABASE_URL` for concurrent
publication/admission locks and migration roundtrips. Fixtures drop and recreate
application tables. Browser fixtures in `service-descriptions.spec.ts` cover
reviewed publication, standard restoration, private history, retained drafts,
conflicts, unchanged editing revisions, literal markup, public filters, retry,
empty states, agent boundaries, axe and desktop/phone/narrow overflow.

Local validation on 11 November 2026 passed the full SQLite suite (691 tests,
38 skips), PostgreSQL regressions (158 tests), 21 new browser checks and 18
related availability checks. PostgreSQL migration up/down/up preserved standard
catalogue copy, a synthetic customer and linked case; custom and reset history
blocked downgrade as intended. Long unbroken descriptions and literal markup
passed callback/catalogue/preview overflow and accessibility checks. Workspace
type checks, production builds and Bandit passed. Lint had no errors and seven
existing warnings. A private local backup was verified before migrating the
development preview to `0037`; API health/readiness and homepage/services returned
200. The public API returned 17 allowlisted services, and anonymous publication
history returned 401 with private/no-store caching. No custom descriptions were
published to the normal preview. Delivery features and background workers remain
disabled; no provider messages were sent.
