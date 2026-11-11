# Submitted request review for the case team

Open a guided-intake case from the staff ticket queue. **Submitted request**,
below Case progress, shows the customer's recorded questions and answers.
Administrators and staff who already have access to that case can use it.

Use **Answer group** to choose General request or Service-specific questions,
and **Find in submitted answers** to search question/answer text. Skipped answers
are explicitly labelled. Filtering is local: it makes no additional API requests
and preserves the unsent customer reply or internal note. Recorded notices can be
expanded independently to inspect saving/submission versions and timestamps.
The service-form version appears when it was retained.

The panel is read-only. Use the existing case workflow for follow-up and working
property information. Reading, searching and expanding notices do not change
submission data, draft revisions, consent, case status, messages or notifications.
Ordinary callback cases have no guided review panel.

## Historical wording and older records

New guided submissions retain an ordered `submitted_answers` snapshot inside
`structured_answers.guided_intake` and the linked conversation's intake data.
Each entry records question key, original prompt, raw saved value, original
display answer and skip state. Core choice labels and service-specific choice
labels are captured in the same submission transaction as the case and consent.
Later changes to catalogue names, question definitions, option ordering or the
conversation do not rewrite the submitted view.

Older guided requests have no complete display snapshot. Their general fields
are labelled and displayed as saved values, with a visible older-record note.
Service-specific answers use the retained service-form definition when available,
including its original choice labels. The server never rebuilds historical
wording from the live catalogue or guesses question/answer pairs from later chat.
The existing transcript is labelled **Submitted question history** for guided
requests; other conversations retain their original assistant heading.

Missing, malformed, oversized or inconsistent entries are omitted with a
missing-data message. Unknown field keys and unrelated metadata are excluded.
A display snapshot whose raw value no longer matches the saved answer is not
shown as current evidence. Missing notice IDs/timestamps display **Not retained**;
the panel does not infer consent that was not recorded. Retained case records and
question history remain available through their existing authorized views.

## API, access and retention

The existing staff case-detail response gains optional `guided_request`:

- `format`: `snapshot` or `legacy`.
- `answers`: allowlisted question/answer rows, skip state and general/service group.
- `incomplete`: some retained data could not be displayed safely.
- `service_form_revision`, `submitted_at`, `saving_consented_at`,
  `submission_notice` and `saving_notice` when valid and retained.

No new route or write action is added. The existing case authorization continues
to apply to detail reads and updated-ticket responses: administrators, current
assignees, active case-team members and permitted meeting staff use the existing
visibility rules. Staff without a current case-access grant receive 404 on reads;
customer credentials cannot call staff routes. Private/no-store caching continues
to apply. The new summary is excluded from customer tracking/account responses.
Search terms stay in component state, without URLs or browser storage.

The answer snapshot belongs to the existing case and conversation business
records. Include it in existing retention, correction, access and deletion review,
alongside saved answers and the transcript. Expiring the temporary intake draft
does not remove submitted case records. No answer is sent to a provider by this
feature, and no publication audit or notification is created by opening the view.

## Deployment and verification

Deploy the updated API and website together. The schema remains
`0038_service_intake_forms`; no new migration, dependencies, worker or provider
configuration is needed. Older application versions ignore the additional JSON
snapshot fields while retaining them. Existing submissions are read without
backfilling or rewriting records.

From `backend`, use disposable test data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_submitted_intake.py tests/test_intake.py tests/test_cases.py
```

PostgreSQL regressions cover real JSON storage, submitted snapshots and case
access/revocation. Test fixtures drop/recreate application tables. Browser fixtures
cover filtering, skipped values, notice metadata, draft preservation, legacy and
missing-data states, ordinary callbacks, authorized agents and denied cases.
They check the new review component with axe and whole-page overflow at desktop,
phone and narrow widths using synthetic records.

Local verification on 11 November 2026 passed the full SQLite suite (732 tests,
39 skips), PostgreSQL regressions (89 tests), 18 new browser checks and 21 related
intake checks. Tests covered original labels after publication/catalogue changes,
legacy values, malformed-data omission, case access and revocation, read-only
behavior, draft preservation, component axe and whole-page overflow. Workspace
type checks, production builds and Bandit passed. Lint had no errors and seven
existing warnings. The refreshed API health/readiness, homepage and staff
workspace returned 200. Schema remains at `0038`; no migration or backfill was
applied. Preview delivery features and background workers remain disabled, and
no provider messages were sent.
