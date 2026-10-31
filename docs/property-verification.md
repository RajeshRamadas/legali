# Property verification agent

Requirements, design and implementation notes for the LLM parts of this feature are in [llm-verification/](llm-verification/README.md).

The staff case page (`/admin/tickets/<ticket number>`) includes a document analysis agent. Customers continue to upload through the existing document repository. Assigned agents and admins can run the agent; it uses the same case access restrictions as the rest of the staff workspace.

## Workflow

1. Upload the case documents in the case file. Select the state/union territory and keep property identifiers and the lawyer's checklist current.
2. Run local extraction to inspect coverage, OCR and the remaining legal checks without sending documents to an LLM.
3. For semantic analysis, enable the configured LLM and confirm authorisation to send extracted case text externally. This transmits the extracted document contents, JPEG images of scanned (OCR'd) pages, case property details and law reference pack to the configured provider. Digital PDFs and DOCX files are sent as text only. Set `VERIFICATION_SEND_PAGE_IMAGES=false` to send text only. Choose a provider and retention policy appropriate for your documents.
4. The agent inventories/checks file hashes and extracts text, then makes one extraction call per document (with that document's scanned page images) and one comparison call across all documents. Findings are either `legal` (must cite a supplied law ID) or `factual_inconsistency` (documents disagree on survey number, extent, boundaries, names or dates; no law ID needed). Every quote is checked against the page text after normalising whitespace, line-break hyphenation, case and invisible characters. A fact or finding whose quote or law ID does not match is discarded on its own and counted in `rejected`; the rest of the run is kept. Any discarded item prevents a conditional verdict. The server computes the screening verdict from evidence completeness and finding severity.
5. Review findings, source quotes, OCR coverage, missing items and independent checks. Export the JSON evidence report for the case record. History stores the ten most recent runs in the UI (older runs remain in the database). Any file, tag, property or checklist-status change marks a previous run as stale.
6. Complete official searches and advocate review through the existing checklist, report, final PDF and signed-report workflow. The agent cannot mark a checklist item verified or sign a report.

Verdicts:

- **High risk:** a model finding with high/critical severity has source quotes and a permitted legal reference. Investigate and resolve the issue before proceeding. A matching quote validates provenance, not the model's interpretation.
- **Insufficient evidence:** unreadable/partial/unsupported documents, unresolved checklist items, no checklist, or LLM analysis not completed. No clear-title decision is available.
- **Conditional review:** the model completed, extraction has no warnings, checklist items are verified/waived, and no high-severity findings were returned. Independent searches and a signed advocate opinion are still required. This is never automatic title clearance.

## LLM configuration

For Docker, place values securely in `infra/.env` and recreate the API service. For a native API process, export these variables before starting uvicorn. No key is stored in the database or exposed to the browser. No client-supplied API URL/key is accepted by the analysis endpoint.

```dotenv
VERIFICATION_LLM_PROVIDER=anthropic
VERIFICATION_LLM_API_KEY=<supply securely on the server, or set ANTHROPIC_API_KEY>
# Optional overrides; these are the defaults for anthropic:
VERIFICATION_EXTRACT_MODEL=claude-sonnet-5-5
VERIFICATION_COMPARE_MODEL=claude-opus-5-5
VERIFICATION_SEND_PAGE_IMAGES=true
VERIFICATION_OCR_LANGUAGES=eng+hin+kan
```

Why two models: extraction runs once per document and reads scanned page images, so it uses Claude Sonnet 5.5 (vision, lower cost). The comparison and legal screen runs once per case and is where a missed defect is costly, so it uses Claude Opus 5.5. Anthropic calls use a forced `submit` tool whose input schema is the Pydantic schema, so the provider enforces the JSON shape. Output is capped at 16,000 tokens per call and the request timeout is 300 seconds.

`VERIFICATION_LLM_MODEL` sets one model for both steps when no per-step value is given. For OpenAI or a trusted OpenAI-compatible gateway, use provider `openai`, its HTTPS API base URL and a vision-capable model (default `gpt-4.1-mini`). It must support chat completions, JSON object responses, image inputs and `max_tokens`. Anthropic uses its fixed HTTPS messages endpoint; the base URL setting only affects OpenAI-compatible providers. Configure network access for the actual destination (e.g. `api.anthropic.com`) through environment settings. Keys cannot overcome a network deny.

Models must return complete structured output with source quotes. Provider timeouts, non-2xx responses, truncated output and invalid schemas produce `llm_status=failed`, no accepted model findings and an insufficient-evidence verdict. Individual unsupported quotes or law IDs are discarded and counted instead of failing the run. The saved run explains the failure without logging credential values or provider response bodies. No live credentialed LLM call is part of the automated test suite.

## Installation

Python dependencies use the existing backend requirements. Local extraction requires `poppler-utils` (`pdfinfo`, `pdftotext`, `pdftoppm`) and `tesseract-ocr`. Install language packs for the documents you process. The backend Docker image installs English, Hindi and Kannada packs; set `VERIFICATION_OCR_LANGUAGES=eng+hin+kan` for mixed scans. Native development needs those packs installed separately. Missing OCR/language support is reported as an extraction failure, not a successful analysis.

Apply the new migration from `backend/`:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

From the repository root, `docker compose -f infra/docker-compose.yml up --build` installs tools and applies migrations through the existing entrypoint. Rebuild the API image after this change.

Validation:

```bash
cd backend
python -m pytest -q
# From the repository root:
npm run typecheck
npm run build --workspace frontend
```

## Scope and limits

- Up to 10 case files per run, first 15 pages per PDF, 10,000 characters per PDF/image page, 45,000 per file and 90,000 per case. Any omitted content is flagged and prevents a conditional verdict. DOCX uses logical part references rather than printed page numbers. Legacy DOC and HEIC uploads remain supported by the repository but must be converted to a supported analysis format. Encrypted, corrupt or unreadable documents are flagged.
- PDF embedded text and OCR are evidence extraction, not signature, seal, forgery or authenticity verification. Scanned OCR depends on legibility and installed languages. Original pages must be compared against the extracted quotes.
- The law pack covers selected national principles (Transfer of Property Act, Registration Act, stamp-law checks and RERA) and Karnataka conversion/granted-land checks. Other states receive national screening and an explicit state-law review requirement. It is not comprehensive Indian land law, personal/inheritance law or current legal research. Official India Code links are Act search links, not proof of live text verification. Confirm current statutes, amendments, exemptions, state rules and judgments with an advocate.
- No automated EC, sub-registrar, court, lender, revenue, acquisition or live RERA verification is claimed. Existing sample RERA records do not establish verification.
- Runs retain extracted text and evidence in the case database. Apply the same access, backup and retention controls as original case documents. Legal verdicts are internal staff work product until the advocate completes the existing signed-report process.
- Runs are synchronous and may take several minutes for scans. A PostgreSQL row lock serializes runs on a case, and a one-minute interval limits repeated analysis. Deploy with suitable request timeouts; a durable worker queue and broader abuse/retention policies are follow-up production work.

## Automatic upload check

Every customer or staff upload is checked a few seconds after it arrives, in a background task, with a low-cost model (`VERIFICATION_CLASSIFY_MODEL`, default `claude-haiku-5-5` on Anthropic). It reads the first 3 pages (text plus images of scanned pages) and records on the document (`documents.ai_check`, migration `0012_document_checks`):

- document type and the checklist tag it most likely belongs to (`suggested_tag`, limited to known tags); `tag_mismatch` is computed at view time, so retagging clears it without another call;
- legibility (`yes` / `partly` / `no`) and completeness (`yes` / `no` / `unclear`);
- issue date and, for encumbrance certificates, the search period;
- customer-facing `problems`. The code adds two deterministic EC rules: the period must end within the last 45 days and cover 30 years.

The customer sees one line under each file on the Documents page (the page refreshes while checks are pending) and the case team sees it in the case file, with **Check again** (`POST /api/v1/admin/tickets/{ticket}/documents/{id}/check`). The check is advice only: it never marks an item verified or rejected. It runs whenever the LLM is configured and `VERIFICATION_UPLOAD_CHECKS` is not `false`; turning it off stops documents from being sent to the provider at upload. A provider failure records `status: failed` and never affects the upload.

## Intake-driven Karnataka workflow

Verification services (`title-verification`, `legal-due-diligence`, `developer-land-screening`, `acquisition-due-diligence`) now create a provisional document request as soon as a ticket is raised. No LLM key and no issued lawyer report is needed for this request. The response, customer Documents page and tracking card include the current request. A customer-visible system message and queued SMS/email notifications announce it; delivery still depends on the repository's notification-provider integrations.

Customers answer structured questions about state, transaction type, seller authority, development stage and granted-land history, and can provide survey/PID/village/taluk/district details. Unknown answers remain explicit questions. Inheritance adds death and succession records; a POA holder adds authority documents; a company adds signatory authority; gifts/partitions and new developments add their corresponding instruments. These are provisional requirements, not determinations of legal applicability. Unrelated services such as affidavit drafting do not receive a full title-verification checklist.

The request distinguishes customer uploads from case-team official-record tasks. Uploading under a tag changes that item to received and removes it from the current missing-upload prompt; deleting the file restores the request. Received never means verified. The government fetch queue now includes intake tasks before a preliminary report exists, including litigation/acquisition search records. Karnataka portal links are supplied only when Karnataka is explicitly selected. Captchas, official searches, court coverage and legal conclusions remain work for the team. Customers cannot rewrite an advocate-issued checklist; staff can correct intake, add newly applicable requirements and preserve existing review decisions. Those changes invalidate affected agent outputs.

The agent produces a candidate title-chain view grouped by quoted document facts. Where one valid ISO execution date is available per document, it shows a candidate chronological order and exact-name continuity checks. Ambiguous parties, dates and missing intervening transfers remain unresolved. Matching names do not verify identity or ownership.

After a successful Karnataka LLM run, staff can use **Prepare advocate report draft**. It copies the evidence-backed findings, legal references, chain facts, limitations and open checks into the existing editable legal report. It does not issue, approve or sign it. Existing advocate-written final sections are protected from silent overwrite. Review the report, issue its checklist and resolve each item through the case file.

**Record advocate approval** requires a staff advocate profile with a recorded bar enrolment, every checklist item verified/waived, explanations for waivers, official HTTPS source references and review notes. The advocate explicitly attests to checking current law/amendments/applicability/judgments and the independent record checks. The app records the reviewer, timestamp, sources and notes; it does not claim the LLM independently researched current legislation or verified the advocate's enrolment. Final PDF generation for an agent-drafted report is blocked until this review is recorded. Evidence, intake, report or checklist changes invalidate the relevant approval. The existing final PDF and signed-upload workflow completes the case.

API additions:

- `POST /api/v1/tickets`: optional `property_intake`; returns `document_request`.
- `POST /api/v1/tickets/property-intake`: ticket/contact plus `intake`; returns the updated customer ticket.
- `PATCH /api/v1/admin/tickets/{ticket}/property-intake`: staff correction and checklist reconciliation.
- `POST /api/v1/admin/tickets/{ticket}/verification/report-draft`: `run_id` of a current successful Karnataka analysis.
- `POST /api/v1/admin/tickets/{ticket}/verification/approve`: `sources`, `notes`, `current_law_and_applicability_confirmed`, `official_checks_reviewed`.

Intake and approval metadata use the existing ticket JSON storage; no additional database migration is required beyond `0011_verification`.

Before approval, the advocate must replace the `AUTOMATED DRAFT` opinion with their own reasoned opinion and resolve all outstanding intake questions. Waivers need substantive reasons; a verified item needs an attached record or substantive verification notes. The draft's conditions include the applicable curated Act/section principles and official reference links, even when the model returns no adverse findings. This supports a documented review; it does not automate legal research or guarantee title.
