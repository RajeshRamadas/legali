# Property verification agent

The staff case page (`/admin/tickets/<ticket number>`) includes a document analysis agent. Customers continue to upload through the existing document repository. Assigned agents and admins can run the agent; it uses the same case access restrictions as the rest of the staff workspace.

## Workflow

1. Upload the case documents in the case file. Select the state/union territory and keep property identifiers and the lawyer's checklist current.
2. Run local extraction to inspect coverage, OCR and the remaining legal checks without sending documents to an LLM.
3. For semantic analysis, enable the configured LLM and confirm authorisation to send extracted case text externally. This transmits the extracted document contents, case property details and law reference pack to the configured provider. Uploaded originals are not sent by this implementation. Choose a provider and retention policy appropriate for your documents.
4. The agent inventories/checks file hashes, extracts evidence, asks the model to extract quoted facts, asks it to compare documents and identify legal issues, and validates every quoted page/document reference and law ID. The server computes the screening verdict from evidence completeness and finding severity.
5. Review findings, source quotes, OCR coverage, missing items and independent checks. Export the JSON evidence report for the case record. History stores the ten most recent runs in the UI (older runs remain in the database). Any file, tag, property or checklist-status change marks a previous run as stale.
6. Complete official searches and advocate review through the existing checklist, report, final PDF and signed-report workflow. The agent cannot mark a checklist item verified or sign a report.

Verdicts:

- **High risk:** a model finding with high/critical severity has source quotes and a permitted legal reference. Investigate and resolve the issue before proceeding. A matching quote validates provenance, not the model's interpretation.
- **Insufficient evidence:** unreadable/partial/unsupported documents, unresolved checklist items, no checklist, or LLM analysis not completed. No clear-title decision is available.
- **Conditional review:** the model completed, extraction has no warnings, checklist items are verified/waived, and no high-severity findings were returned. Independent searches and a signed advocate opinion are still required. This is never automatic title clearance.

## LLM configuration

For Docker, place values securely in `infra/.env` and recreate the API service. For a native API process, export these variables before starting uvicorn. No key is stored in the database or exposed to the browser. No client-supplied API URL/key is accepted by the analysis endpoint.

```dotenv
VERIFICATION_LLM_PROVIDER=openai
VERIFICATION_LLM_MODEL=gpt-4.1-mini
VERIFICATION_LLM_API_KEY=<supply securely on the server>
VERIFICATION_LLM_BASE_URL=https://api.openai.com/v1
VERIFICATION_OCR_LANGUAGES=eng
```

For Anthropic, use `VERIFICATION_LLM_PROVIDER=anthropic`, select a model available to your account, and supply `VERIFICATION_LLM_API_KEY` (or the existing `ANTHROPIC_API_KEY`). Anthropic uses its fixed HTTPS messages endpoint; the base URL setting only affects OpenAI-compatible providers. For a trusted compatible gateway, use provider `openai` and its HTTPS API base URL. It must support chat completions, JSON object responses, and `max_tokens`. Configure network access for the actual destination (e.g. `api.openai.com` or `api.anthropic.com`) through environment settings. Keys cannot overcome a network deny.

Models must return complete JSON with exact source quotes. Provider timeouts, non-2xx responses, truncated output, unsupported quotes/laws and invalid schemas produce `llm_status=failed`, no accepted model findings and an insufficient-evidence verdict. The saved run explains the failure without logging credential values or provider response bodies. No live credentialed LLM call is part of the automated test suite.

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
