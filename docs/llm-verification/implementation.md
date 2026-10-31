# LLM document verification: implementation

**Status:** what is built on `main` as of 2026-10-31. Built in commits 15db9a5 and e4fa84d (agent and Karnataka
workflow), then PR #14 (bf4f6e9: Claude per step, page images, partial acceptance, factual inconsistencies),
PR #15 (557bb3d: upload checks) and PR #16 (5fc91d2: document journey UI).
See [requirements.md](requirements.md) for what it must do and [design.md](design.md) for why it works this way.

## 1. Files

| File | What it contains |
| --- | --- |
| `backend/app/verification.py` | `DEFAULT_MODELS`, `model_for(step)`, `provider_status()`, `model_call()` (Anthropic and OpenAI-compatible transport), schemas `Evidence`/`Fact`/`Facts`/`Finding`/`Findings`/`RunRequest`, `SYSTEM` prompt, `normalise()`/`valid_evidence()`, `snapshot()`/`fingerprint()`, `run_agent()`, `applicable_laws()`, `title_chain()`, run history and run endpoints. |
| `backend/app/document_reader.py` | `extract(data, filename, images=None, max_pages=15)`, `model_image()` (JPEG, long edge 1568 px, quality 85), limits `MAX_PAGES=15`, `MAX_CHARS=45000`. |
| `backend/app/upload_check.py` | `UploadCheck` schema, `SYSTEM`/`TASK` prompts, `enabled()`, `assess()`, `run()` (background task), `view()`; constants `CHECK_PAGES=3`, `EC_YEARS=30`, `EC_MAX_AGE_DAYS=45`. |
| `backend/app/property_law.py` | `LAW_VERSION = "2026-10-31.1"`, `LAWS` (ids `tpa-sale`, `registration`, `stamp`, `litigation`, `rera`, `karnataka-land`, `karnataka-grant`), `BY_ID`. |
| `backend/app/verification_workflow.py` | `POST .../verification/report-draft`, `POST .../verification/approve`, `evidence_fingerprint()`, `require_current_draft()`, `validate_final_approval()` (final PDF gate). |
| `backend/app/document_requirements.py` | Intake questions and the provisional document request a run checks against. |
| `backend/app/document_journey.py` | `GROUPS`, `LINKS`, `journey()` returning `{stages, groups, links, checks, next_upload}`. |
| `backend/app/documents.py` | Schedules `upload_check.run` after customer and staff uploads; staff re-check endpoint. |
| `backend/app/case_files.py` | Adds `check` (from `upload_check.view`) to each document in ticket views. |
| `backend/app/config.py` | `VERIFICATION_*` settings (section 4). |
| `frontend/app/admin/VerificationPanel.tsx` | Staff run form (state, LLM toggle, consent), saved runs, verdict, findings with quotes, discarded counts, title chain, export, report draft and advocate approval. |
| `frontend/app/admin/VerificationOverview.tsx` | Staff at-a-glance journey with upload-check notes per file. |
| `frontend/app/documents/page.tsx`, `Journey.tsx`, `journey.css` | Customer Documents page: stepper, document map, checklist, one-at-a-time upload card, upload-check line per file, polling while checks are pending. |
| `packages/shared/src/index.ts` | `UploadCheck`, `describeUploadCheck()`, `DocumentJourney` and related types shared by web and app. |

## 2. Database

| Migration | Change |
| --- | --- |
| `0011_verification` | Table `verification_runs` (`id`, `service_request_id` → `service_requests` cascade, `created_by_user_id` → `users` set null, `created_at`, `result` JSON/JSONB), index on `service_request_id`. |
| `0012_document_checks` | Column `documents.ai_check` (JSON/JSONB, nullable). |

Intake answers, the agent report marker and advocate approval live in the ticket's existing `structured_answers` JSON;
no other migration is needed.

### 2.1 `verification_runs.result`

```jsonc
{
  "version": 1, "state": "Karnataka", "law_version": "2026-10-31.1",
  "input_fingerprint": "<sha256 of snapshot()>",
  "verdict": "high_risk | insufficient_evidence | conditional_review", "reason": "...",
  "llm_status": "not_requested | completed | failed",
  "provider": "anthropic", "model": "claude-sonnet-5-5 (extract) · claude-opus-5-5 (compare)",
  "models": {"extract": "...", "compare": "..."},
  "page_images_sent": 4,
  "rejected": {"facts": 0, "findings": 0},
  "documents": [{"id", "filename", "tag", "sha256", "pages": [{"page", "text", "method": "embedded_text|ocr|docx_text"}], "warnings": [], "page_count"}],
  "facts": [{"field": "seller|buyer|property_identifier|area|registration|execution_date|encumbrance|document_type", "value", "evidence": {"document_id", "page", "quote"}}],
  "findings": [{"title", "severity": "critical|high|caution", "category": "legal|factual_inconsistency", "reason", "action", "law_ids": [], "evidence": [...]}],
  "open_checks": [{"title", "law_ids", "action"}],
  "document_request": {...}, "title_chain": {"transfers", "status", "chronology", "undated", "links", "note"},
  "checklist": [{"tag", "label", "status", "files"}], "laws": [...], "trace": [{"step", "detail"}], "limitations": [...]
}
```

The API view adds `id`, `created_at` and `stale` (fingerprint recomputed on read). Page images are never stored.

### 2.2 `documents.ai_check`

```jsonc
{
  "status": "done | failed | skipped", "model": "claude-haiku-5-5", "checked_at": "...", "checksum_sha256": "...",
  "document_type": "Encumbrance certificate (Form 15)", "suggested_tag": "ec",
  "legible": "yes|partly|no", "complete": "yes|no|unclear",
  "issue_date": "YYYY-MM-DD|", "period_from": "YYYY-MM-DD|", "period_to": "YYYY-MM-DD|",
  "summary": "...", "problems": ["customer-facing sentence", "..."]
}
```

The `check` field on each document in ticket views is `upload_check.view()`: the fields above plus `tag_mismatch`
(computed on read), or `{"status": "pending"}` while a check is due, or `null` when checks are off.

## 3. API

| Method and path | Who | Purpose |
| --- | --- | --- |
| `GET /api/v1/admin/verification/config` | staff | Provider, models per step, page-image setting, `configured`, limits, law version. |
| `GET /api/v1/admin/tickets/{ticket}/verification` | staff with case access | Latest 10 runs with `stale`. |
| `POST /api/v1/admin/tickets/{ticket}/verification` | staff with case access | Body `{state, use_llm, consent_to_external_processing}`. 201 with the run; 422 no documents, more than 10 files, no consent, or state conflicts with intake; 409 LLM not configured; 429 within 60 s of the last run. |
| `POST /api/v1/admin/tickets/{ticket}/verification/report-draft` | staff | Body `{run_id}`; needs a current, completed, Karnataka run and no final/signed report. |
| `POST /api/v1/admin/tickets/{ticket}/verification/approve` | staff advocate | Body `{sources, notes, current_law_and_applicability_confirmed, official_checks_reviewed}`. |
| `POST /api/v1/tickets/documents`, `POST /api/v1/admin/tickets/{ticket}/documents` | customer / staff | Upload; schedules the upload check when enabled. |
| `POST /api/v1/admin/tickets/{ticket}/documents/{id}/check` | staff | Re-runs the upload check synchronously; 409 when checks are off or unconfigured. |

Ticket views (customer lookup and staff detail) include `document_request.journey` and each document's `check`.

## 4. Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `VERIFICATION_LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` (any OpenAI-compatible HTTPS endpoint). |
| `VERIFICATION_LLM_API_KEY` | empty | Provider key. For Anthropic, `ANTHROPIC_API_KEY` is used when this is empty. Without a key the LLM is "not configured". |
| `VERIFICATION_LLM_MODEL` | empty | One model for all steps without a per-step value. |
| `VERIFICATION_EXTRACT_MODEL` | `claude-sonnet-5-5` | Per-document extraction (vision). |
| `VERIFICATION_COMPARE_MODEL` | `claude-opus-5-5` | Case-wide comparison and legal screen. |
| `VERIFICATION_CLASSIFY_MODEL` | `claude-haiku-5-5` | Upload check. |
| `VERIFICATION_SEND_PAGE_IMAGES` | `true` | Send JPEGs of OCR'd pages to the extraction model. |
| `VERIFICATION_UPLOAD_CHECKS` | `true` | Check uploads on arrival when the LLM is configured. |
| `VERIFICATION_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible only; must be HTTPS without credentials. |
| `VERIFICATION_OCR_LANGUAGES` | `eng` (`eng+hin+kan` in Docker Compose) | Tesseract languages. |

For provider `openai`, all three steps default to `gpt-4.1-mini`. All values are passed through
`infra/docker-compose.yml`. The backend image installs `poppler-utils` and Tesseract with English, Hindi and Kannada.

## 5. Limits in code

| Limit | Value | Where |
| --- | --- | --- |
| Files per run | 10 | `verification.MAX_DOCUMENTS` |
| Pages per PDF | 15 (3 for upload checks) | `document_reader.MAX_PAGES`, `upload_check.CHECK_PAGES` |
| Characters per page / file / case | 10,000 / 45,000 / 90,000 | `document_reader`, `run_agent` |
| Characters per page sent in upload check | 4,000 | `upload_check.assess` |
| OCR trigger | page with under 50 characters of embedded text | `document_reader.extract` |
| Output tokens per call | 16,000 | `verification.MAX_OUTPUT_TOKENS` |
| Timeout | 300 s per call (60 s upload check); 45 s per local tool | `model_call`, `document_reader.command` |
| Facts / findings per response | 100 / 25; 8 quotes per finding, 5 law IDs | schemas |
| Runs per case | 1 per 60 s, serialised by a row lock | `analyse` |
| History shown | 10 runs | `history` |

## 6. Tests

| File | Covers |
| --- | --- |
| `backend/tests/test_verification.py` (13 tests) | Extraction and invalid files, OCR of scanned images, page limit warning, history/staleness/access, consent and configuration errors, grounding and no automatic approval, quote normalisation, partial acceptance, legal vs factual findings, OpenAI and Anthropic transports (forced tool, images first), model selection, images not saved. |
| `backend/tests/test_upload_check.py` (4) | Off without configuration, wrong tag and short/old EC flagged, unknown tags dropped, failure recorded and staff re-check. |
| `backend/tests/test_document_journey.py` (3) | Stages, groups, check statuses, flags, next upload. |
| `backend/tests/test_document_requests.py` (7) | Intake-driven request, Karnataka workflow, draft and approval gates. |

Provider calls are mocked with `httpx.MockTransport` or monkeypatching; no test calls a live model. Run with
`cd backend && python -m pytest -q`. The two OCR tests need `tesseract` installed; in a container without it they fail
(27 of 29 pass in such an environment).

## 7. Known gaps

- **Not tested live.** No credentialed call to Anthropic has run in development; the first real run should be on a
  known case with a reviewer watching quotes, discards and cost.
- **Synchronous runs.** A case run holds the HTTP request (and a row lock) for the whole pipeline; scanned cases can take
  minutes. Needs a worker queue before production. The staff re-check also runs inline.
- **No cross-checks, RERA match, typed schemas, confidence or gold set yet** (VR-15 to VR-18); being built in the
  accuracy work.
- **Upload checks send data without customer consent.** Every upload's first pages go to the provider when configured;
  the Documents page footer says so. Decide whether explicit consent is needed.
- **No retention policy** for `verification_runs` (extracted text is kept indefinitely) and no cost tracking per run.
- **Mobile app** does not show upload checks or the journey yet.
- **Native OCR default.** Outside Docker, `VERIFICATION_OCR_LANGUAGES` defaults to `eng`; Kannada scans need
  `eng+hin+kan` and the language packs installed.
