# LLM document verification: requirements

**Status:** describes what is on `main` as of 2026-10-31 (PRs #14, #15, #16) plus the planned accuracy work.
**Related:** [design.md](design.md) (how it works), [implementation.md](implementation.md) (what is built, file by file),
[../property-verification.md](../property-verification.md) (operator guide), [../document-journey.md](../document-journey.md).

Each requirement has an ID and a status: **Built** (on `main` and covered by tests), **Partial** (built with a stated gap)
or **Planned** (agreed direction, not built).

## 1. Purpose

Homexo Legal verifies property title for buyers in Bengaluru/Karnataka. A case collects 10 to 30 documents (sale deeds,
encumbrance certificates, khata, RTC, mutation, approvals) of mixed quality: digital PDFs, phone photos and Kannada
scans. Before an advocate signs a title opinion, someone has to read every document, pull out the facts that matter
(survey number, extent, owners, dates, charges) and notice where documents disagree or a legal requirement is unmet.

The LLM feature does that first reading so the advocate starts from a quoted, checkable summary instead of a pile of
files. It is a **screening assistant**. It never decides title, approves a checklist item or signs a report.

## 2. Users

| User | What they need from the feature |
| --- | --- |
| Customer (buyer) | Know straight away if an upload is the wrong document, unreadable, incomplete or out of date, and what to send next. |
| Case agent | A reading of every document with quotes, a list of contradictions and gaps, and what is still missing, before the advocate's time is spent. |
| Advocate | Findings tied to exact page quotes and named law principles, a candidate title chain, and a draft report they can edit, review and sign. |
| Admin / operator | Control over which provider and models are used, whether documents leave the server at all, and cost. |

## 3. Scope

In scope: reading uploaded case documents, per-upload checks, cross-document comparison, screening against a curated
law pack, a computed screening verdict, a draft report for Karnataka cases, and showing check status to customers and staff.

Out of scope: live searches of government portals (Kaveri, Bhoomi, e-courts, RERA), signature/seal/forgery
detection, legal research beyond the curated pack, and any automatic legal conclusion.

## 4. Functional requirements

### 4.1 Upload check (on arrival)

| ID | Requirement | Status |
| --- | --- | --- |
| UC-1 | Every customer or staff upload is checked automatically in the background within seconds; the upload itself never waits for or fails because of the check. | Built |
| UC-2 | The check identifies the document type and suggests which requested checklist item it belongs to, limited to known tags. | Built |
| UC-3 | The check reports legibility (yes / partly / no) and completeness (yes / no / unclear) from the first pages. | Built |
| UC-4 | The check reads the issue date and, for an encumbrance certificate (EC), the search period, as ISO dates only when written unambiguously. | Built |
| UC-5 | Date rules are applied in code, not by the model: an EC must run to within the last 45 days and cover 30 years. | Built |
| UC-6 | The customer sees one plain-language line under each file, and the page refreshes while checks are pending. | Built |
| UC-7 | Staff see the same result in the case file and can run the check again. | Built |
| UC-8 | A file filed under the wrong item is flagged; re-filing clears the flag without a new model call. | Built |
| UC-9 | The check is advice only. It never changes a checklist item's status. | Built |
| UC-10 | An operator can turn the check off (`VERIFICATION_UPLOAD_CHECKS=false`) so documents are not sent to the provider at upload. | Built |
| UC-11 | A provider failure is recorded on the document as `failed` and does not affect the upload. | Built |

### 4.2 Case verification run (staff)

| ID | Requirement | Status |
| --- | --- | --- |
| VR-1 | An assigned agent or admin can run verification from the case page. Customers cannot. | Built |
| VR-2 | A run without the LLM still inventories files, extracts text (embedded text or OCR) and lists open checks, without sending anything externally. | Built |
| VR-3 | An LLM run requires the server to be configured and the staff member to confirm authority to send extracted text and scanned page images to the provider, on every run. | Built |
| VR-4 | Each document is read separately, with images of its scanned pages, extracting facts of 8 types: seller, buyer, property identifier, area, registration, execution date, encumbrance, document type. | Built |
| VR-5 | One comparison call across the whole case returns findings of two kinds: `factual_inconsistency` (documents disagree on survey/hissa number, extent, boundaries, names or dates) and `legal` (an issue under a supplied law principle). | Built |
| VR-6 | Every fact and finding carries a literal quote with document and page. A quote that cannot be found in that page's text (after normalising spacing, hyphenation, case and invisible characters) is discarded. | Built |
| VR-7 | A legal finding must cite at least one law ID from the supplied pack; an unknown ID discards the finding. A factual inconsistency needs no law ID. | Built |
| VR-8 | One bad quote discards only that fact or finding. The count of discarded items is shown, and any discard blocks a `conditional_review` verdict. | Built |
| VR-9 | A provider error, timeout, truncated or invalid response fails the LLM step as a whole: no model output is kept and the verdict is `insufficient_evidence`. | Built |
| VR-10 | The verdict is computed in code from finding severity and evidence completeness: `high_risk`, `insufficient_evidence` or `conditional_review`. It is never "clear title". | Built |
| VR-11 | A candidate title chain is built from quoted facts: ordered only when each document has exactly one ISO execution date, and linked only when the previous buyer and next seller names match exactly (shown as "name match only"). | Built |
| VR-12 | Each run is saved with its inputs' fingerprint; any change to files, tags, property, intake or checklist marks the run stale. | Built |
| VR-13 | The JSON evidence report of a run can be exported. | Built |
| VR-14 | Runs on one case are serialised and limited to one per minute. | Built |
| VR-15 | Code cross-checks between documents (survey number, extent with unit conversion, owner names, EC coverage across the chain) that do not depend on the model noticing. | Planned |
| VR-16 | Match the project against imported Karnataka RERA records. | Planned |
| VR-17 | Per-document-type extraction schemas (sale deed, EC, RTC, khata) instead of 8 generic fact types. | Planned |
| VR-18 | A confidence signal on findings, and a gold evaluation set of 30 to 50 past cases with known outcomes to measure accuracy. | Planned |

### 4.3 Advocate workflow

| ID | Requirement | Status |
| --- | --- | --- |
| AW-1 | For a current, completed Karnataka run, staff can prepare an editable report draft from the findings, quotes, title chain, law references and open checks. | Built |
| AW-2 | The draft never overwrites an advocate-written final section or a final/signed report. | Built |
| AW-3 | Recording advocate approval needs a bar-enrolled advocate profile, every checklist item verified or waived with reasons, HTTPS source references, notes and two explicit attestations (current law; official checks). | Built |
| AW-4 | A final PDF of an agent-drafted report is blocked until approval is recorded; any later change to evidence, intake, report or checklist invalidates the approval. | Built |

### 4.4 Showing progress (document journey)

| ID | Requirement | Status |
| --- | --- | --- |
| DJ-1 | Customers and staff see the same stages: property details, your documents, official records, documents read, advocate review, signed report. | Built |
| DJ-2 | "Documents read" reflects the latest verification run and says when new files arrived since. | Built |
| DJ-3 | Requested documents are grouped by the question they answer (who is selling, how they came to own it, loans, records, approvals, searches) with a relationship map. | Built |
| DJ-4 | Each group's check status comes only from checklist statuses set by the team; upload-check problems appear as flags and never change a status. | Built |
| DJ-5 | The customer is asked for one document at a time, rejected uploads first. | Built |
| DJ-6 | Cross-check results (VR-15) appear as flags on the relevant check. | Planned |
| DJ-7 | The mobile app shows the journey. | Planned |

## 5. Non-functional requirements

| ID | Requirement | Status |
| --- | --- | --- |
| NF-1 | **Grounding:** no model statement is shown without a quote that exists in the extracted text. | Built |
| NF-2 | **Human control:** no model output can verify, reject or waive a checklist item, issue a report or sign. | Built |
| NF-3 | **Prompt injection:** document text is treated as untrusted evidence; the system prompt says so and the output is schema-forced. | Built |
| NF-4 | **Privacy:** documents leave the server only when the LLM is configured; case runs need per-run consent; upload checks can be turned off; images are not stored in runs; API keys never reach the browser or saved reports; provider bodies are not logged. | Built |
| NF-5 | **Bounded cost and size:** at most 10 files per run, 15 pages per PDF, 10,000 characters per page, 45,000 per file and 90,000 per case; upload checks read 3 pages. Anything cut is flagged. | Built |
| NF-6 | **Model choice per step:** a vision model for per-document reading, the strongest model for the case-wide comparison, a low-cost model for upload checks; each overridable by environment variable. | Built |
| NF-7 | **Provider portability:** Anthropic (default) or an OpenAI-compatible HTTPS endpoint. | Built |
| NF-8 | **Languages:** OCR in English, Hindi and Kannada in the Docker image; page images let the model read scans OCR gets wrong. | Built |
| NF-9 | **Audit:** each run records who ran it, the models, the law pack version, the trace of steps and the verdict. | Built |
| NF-10 | **Latency:** runs are synchronous and can take minutes on scans; a durable worker queue is needed for production. | Partial |
| NF-11 | **Measured accuracy:** extraction and finding accuracy measured on a gold set before relying on the feature in production. | Planned |

## 6. Acceptance criteria (current build)

- A fact whose quote is not on the cited page is discarded and counted; the other facts in the same response are kept.
- A `legal` finding with no law ID fails validation; a `factual_inconsistency` finding with none is accepted.
- A high/critical finding gives `high_risk`; any warning, open checklist item, open intake question, discard or failed LLM step gives `insufficient_evidence`.
- Anthropic calls use a forced `submit` tool and send page images before the prompt.
- An EC ending more than 45 days ago, or covering under 30 years, produces a customer-facing problem.
- Retagging a file clears its mismatch flag without another model call.
- With the upload check off or unconfigured, nothing is sent at upload and no check is shown.

These are exercised by `backend/tests/test_verification.py`, `test_upload_check.py`, `test_document_journey.py` and
`test_document_requests.py`. No test makes a live provider call.

## 7. Open questions

- Which 30 to 50 past cases (with the advocate's actual outcome) can seed the gold evaluation set?
- Is sending every upload's first pages to the provider acceptable for all customers, or should it need explicit customer consent?
- Should the case run move to a background worker before launch, given scans can take several minutes?
