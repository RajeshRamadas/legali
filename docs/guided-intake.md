# Guided customer request intake

`/request` asks one question at a time, saves completed answers to the verified customer's account, and shows an editable summary before submission. It is available from **New request** on the account page, **Start / resume request** in customer navigation, the assistant and the homepage callback section. The quick callback form remains available.

## Flow

1. Sign in with the verified customer phone. Read the guided-request privacy notice and explicitly choose to save answers before starting a draft.
2. Select a service, describe the goal and choose a supported property type. Location/state and the customer's role are collected next. Known name/email can be prefilled from the signed-in profile and remain editable in the summary.
3. Verification services ask about the transaction and seller's capacity. Built properties ask about new development/resale and optional PID; land asks about grant history and optional survey/village/taluk identifiers. Other states collect their name and do not receive Karnataka portal assignments. Optional questions can be skipped with an empty answer. The verified account supplies the phone number; a draft cannot change request ownership.
4. Each **Continue** saves one validated answer. **Save and exit** saves the current valid answer before returning to saved drafts. Leaving without either action does not save text still being typed. Resume from the same account on another device or reload the draft URL.
5. Review every answer, edit as needed, and explicitly consent to Homexo reviewing/contacting the customer about this request. That consent is separate from saving a draft and does not give marketing consent. The notice and version come from the API; a stale notice must be reviewed again.
6. Submission creates the ticket, property intake, provisional document checklist, staff question/answer transcript, consent record and notification records in one transaction. The confirmation links to documents and account tracking. No legal outcome, fee or availability is promised.

This flow is deterministic. No answers are sent to an LLM and the model cannot change validation, consent or submission. An intake transcript is created at submission; unrelated anonymous assistant chat is not attached automatically. Submitted cases use the existing `source=chat` classification and keep a `guided_intake` snapshot in structured answers.

Administrators can publish up to five [service-specific questions](service-intake-forms.md)
after the standard questions. New service selections pin the current form; later
publications leave saved questions/answers intact. Switching service clears
previous supplemental answers and selects the new form. The `guided-request-v2`
notice includes this collection. Older saving-consent drafts keep core questions
without supplemental collection. Submission retains original form definitions,
version and choice labels in the case snapshot/transcript. Migration
`0038_service_intake_forms` preserves legacy drafts with empty form snapshots.

## Privacy and consistency

- Drafts require customer JWTs and are selected by account ID on every route. Staff/customer token audiences remain distinct; knowing the draft UUID is insufficient. Private responses use `private, no-store`. Draft answers are not written to browser storage, and neither answers nor session tokens are placed in URLs. Draft URLs contain only an opaque owner-checked UUID; the optional `service` query contains a public service slug.
- Saving consent, notice version and timestamp are persisted on each draft. Submission consent is written to the existing `consents` table linked to the submitted conversation/customer. The case snapshot also preserves the original saving consent/version/timestamp. Staff see the submitted goal, identifiers, role, follow-up preference and complete question history through existing ticket details.
- A draft expires 30 days after creation. Discard clears its answer JSON immediately. A minimal discarded record remains until expiry to enforce the daily creation limit. Submitted consent/transcripts remain with the case after draft cleanup under the existing case-retention process.
- Run `python -m app.intake` daily from `backend/` with the deployment database configured. It removes expired draft records, including submitted/discarded drafts, without deleting cases, consent or submitted transcripts. Expired drafts are inaccessible even before cleanup runs. Schedule this command alongside the existing account-security cleanup; no new provider or secrets are required.
- At most five active drafts and twenty starts in a rolling 24-hour period per account are allowed. Starts lock the account row so simultaneous workers cannot bypass limits. Discarding cannot reset the daily count.
- Answer updates require the draft's current `revision`; stale updates return `409` and the interface offers **Reload saved answers**. Service/property/state changes prune incompatible answers. The server checks available services, supported property types, required answers, lengths and email formats. Unknown keys and skipped required steps are rejected.
- Submission locks the draft and records its ticket ID. Retrying a successfully submitted draft returns the original ticket, without another consent, notification batch or case. Submitted drafts cannot be edited/discarded as a way of modifying an existing case; use the normal case workflow.

## Setup and API

Apply migration `0019_guided_intake` with `alembic upgrade head`. It adds only the `intake_drafts` table; existing tickets, accounts and conversations are preserved. There are no new dependencies. The website, shared client and backend must be deployed together. Continue to configure customer phone verification and notification providers using their existing setup documentation.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/intake/notice` | Public current saving/submission notice, version and details |
| GET | `/api/v1/intake/drafts` | The signed-in customer's unexpired drafts |
| POST | `/api/v1/intake/drafts` | Start with `{consent: true, notice_version, service_slug?}` |
| GET | `/api/v1/intake/drafts/{id}` | Resume the owner's draft; includes questions, answers, revision and progress |
| PATCH | `/api/v1/intake/drafts/{id}` | Save `{revision, key, value}` for a reachable question |
| DELETE | `/api/v1/intake/drafts/{id}` | Discard an unfinished draft and clear its answers |
| POST | `/api/v1/intake/drafts/{id}/submit` | Submit reviewed `{revision, consent: true, notice_version}` |

`401` means sign in, `404` means unavailable to this owner, `410` means expired, `409` means revision/state/notice conflict, `422` means invalid/missing input, and `429` means the account's draft cap was reached. Submitted retry responses may show the case's current status but always reference the same ticket.

Validate with the backend suite, workspace type checks, frontend build/lint and browser checks at desktop/mobile widths. `tests/test_intake.py` covers private resume, consent, conditional pruning, validation, stale updates, discard/expiry/limits, atomic rollback and duplicate submission. Its PostgreSQL concurrency test verifies that simultaneous submits produce exactly one case and consent.
