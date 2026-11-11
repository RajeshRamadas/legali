# Reviewed service intake questions

Administrators open **Intake forms** (`/admin/intake-forms`), choose a service
and add up to five supplemental questions. Choose Short answer, Paragraph or
Choose one; enter a prompt and optional help; set whether the answer is required.
Text answers can be limited to 1–1000 characters. Choice questions have two to
eight distinct choices, each at most 80 characters. Move questions up or remove
them to set the order. Names, core questions, document requirements, account
ownership, consent and admission controls keep their existing behavior.

Enter a private publication reason, choose **Review intake form**, inspect the
customer-facing preview, then **Publish reviewed form**. Editing and reviewing do
not write to the API. Publication applies immediately to new service selections.
Publishing an empty question list removes supplemental questions from future
selections without deleting saved answers or changing existing cases.

These questions apply only to the guided request flow and to every property type
using the selected service. Callbacks, assistant requests and bookings continue
through their existing flows. Supplemental questions are not a new universal
admission requirement. Ask only for information needed to scope the service;
identity numbers, credentials, payment data and document contents do not belong
in this form. Files use the existing secure case document area.

## Saved customer requests

A new draft with a preselected service captures its current form in one row read.
A draft without a service captures the form when the customer first selects one.
The snapshot contains service, revision and question definitions. Later form
publications, reordering or changed choice labels never replace that snapshot.
Even an initially empty form stays pinned. Saving the same service again does
not refresh the snapshot. Choosing a different service captures its current form
and clears all previous supplemental answers, even if an identifier is reused.
Choosing the original service again then uses its current published form.

Supplemental questions appear after the standard guided questions. Continue and
Save and exit use the existing owner-scoped, revision-checked answer flow.
Optional text and choice questions can be saved empty; required questions must
be answered. The server validates current-step reachability, allowed choices and
lengths before saving or submitting. Unknown answer keys cannot modify core
fields. The draft displays its selected service-form version.

Submission retains the full selected form with its revision and answers inside
`guided_intake.service_form` in the case and conversation data. The staff question/
answer transcript uses the original prompts and choice labels. A submitted retry
returns the same case. Existing service admission checks still run at creation.
No answers are sent to an AI provider by this flow, and no legal outcome is inferred.

## Privacy, edits and history

The guided request notice is now `guided-request-v2` and explicitly includes
service-specific answers. New starts must review that version. Drafts created
under the old saving notice retain their existing core questions; changing their
service does not add supplemental collection under the old consent. Existing
draft answers and original saving consent/version are preserved. Submission uses
the current submission notice, with the saving consent retained separately.

Customer drafts remain account-private, expire after 30 days and use existing
cleanup and business-record retention rules. Discard clears both answers and the
form snapshot. Submitted case/conversation records retain their snapshots after
draft cleanup. Answers are not copied into administrator publication audits or
browser storage. The administrator's private reason is never returned with the
customer questions or public catalogue.

Publication uses a service-row lock and its own positive revision, independently
of service description and admission revisions. Conflicting saves return 409 and
keep the administrator's draft/reason. **Reload published form (replaces draft)**
or selecting another service replaces local edits. Pending administrator drafts
exist only in component state. Retired services have readable history but cannot
publish. Reference-data sync preserves published questions and their revision.

**Private form publication history** loads on expansion, with independent retry
and pagination. Each entry retains author, time, version, private reason and
previous/published question definitions. Reviewing history preserves unsaved
edits. Clearing a form or retiring a service does not remove retained history.

## API and deployment

- `GET /api/v1/admin/intake-forms`: current forms, service names and active state.
- `PATCH /api/v1/admin/intake-forms/{slug}`: strict `revision`, `confirmed: true`,
  10–1000 character private `reason` and `questions` (0–5 definitions).
- `GET /api/v1/admin/intake-forms/{slug}/history?page=1`: 20 publications per
  page; pages are bounded to 1–10000.

Definitions use a UUID `id`, 5–160 character `prompt`, optional 0–400 character
`help`, `kind` (`text`, `textarea`, `select`), strict boolean `required`, strict
integer `max_length` and string `options`. Question IDs must be distinct within
a form. Options are trimmed, distinct ignoring case and forbidden on text kinds.
Text and identifiers render literally; no executable markup or scripts are supported.

Administration requires administrator authentication, private/no-store caching
and shared lookup/write budgets. Customers/absent credentials receive 401,
agents 403, missing services 404, invalid/unreviewed payloads 422 and stale/retired
publications 409. A current no-op returns the current form without another audit;
stale retries still require review. Customer endpoints keep their existing access
checks and add the optional `service_form_revision` response field.

Back up the database and stop old API instances before `python -m alembic upgrade
head` from `backend`. Migration `0038_service_intake_forms` adds service question
JSON/revision and a draft snapshot. Existing drafts get empty snapshots, preserving
their previous question collection and consent. Deploy API and website together.
No new dependency, provider secret or delivery worker is needed.

Downgrade refuses while published definitions, advanced form revisions, meaningful
draft snapshots or publication history remain, including after a form is cleared.
Use a forward fix or reviewed recovery. Do not reset versions or delete history to
bypass the guard. Pristine up/down/up preserves service descriptions and legacy
draft answers/consent; linked case records are unchanged.

## Verification

From `backend`, run tests on disposable data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_service_intake_forms.py tests/test_service_intake_forms_migration.py tests/test_intake.py
```

Use a dedicated disposable PostgreSQL `TEST_DATABASE_URL` for publication races
and migration roundtrips. Fixtures drop/recreate application tables. Browser
fixtures cover the editor, preview/publication, private history retry/paging,
conflicts, pinned customer choices, optional skips, resume, current submission
consent, agent boundaries, long text, axe and desktop/phone/narrow layouts.

Local verification on 11 November 2026 passed the full SQLite suite (721 tests,
39 skips), PostgreSQL regressions (140 tests), and browser checks (39 tests).
Migration up/down/up preserved legacy saving consent/answers and a linked case;
configured/cleared forms and pinned history blocked rollback. Browser review
also corrected the existing answer-summary definition-list structure and verified
long question/help text without horizontal overflow. Workspace type checks,
production builds and Bandit passed. Lint had no errors and seven existing
warnings. A private local database backup was verified before updating the
development preview to `0038`. API health/readiness, homepage, editor and guided
request routes returned 200; anonymous administration/history returned 401 with
private/no-store caching. The v2 notice and unchanged public catalogue allowlist
were verified. No forms were published to the normal preview. Delivery features
and background workers remain disabled; no provider messages were sent.
