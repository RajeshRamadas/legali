# Verification quality benchmark

The versioned synthetic text suite measures verification outputs against reviewed
reference facts and findings. It exercises the same `screen_documents` rules used
after production document extraction. It never loads a case, reads case storage,
changes a checklist or writes a verification result. No migration is required.

## Offline regression gate

From `backend/`, with the normal backend dependencies installed:

```sh
DATABASE_URL=sqlite:// python -m app.verification_evaluation
```

The default **replay** mode supplies scripted model responses and never contacts a
provider, even when credentials exist. It validates the screening rules and the
benchmark machinery. Its passing scores do **not** measure a live model's accuracy.
No database connection, PDF extraction, OCR or page-image processing is involved.

To create a report, add `--output /tmp/verification-evaluation-first.json`. The
parent directory must exist and the file must be new. The command reserves a
private `0600` file before evaluation and refuses existing files and symlinks.
An uncompleted reservation is removed if the command cannot start/write the report.
Without `--output`, the JSON report goes to stdout. Exit codes are **0** for all
checks passing, **1** for a failed benchmark and **2** for invalid settings,
configuration, fixtures or report paths.

The API regression workflow runs the offline gate once in its SQLite job and
retains `verification-evaluation.json` alongside its test artifacts. A regression
fails the workflow. CI does not execute provider evaluations or receive new
provider credentials.

## Explicit provider evaluation

After reviewing the synthetic suite, the actual configured provider/endpoint and
potential charges, an operator can run, for example:

```sh
python -m app.verification_evaluation --mode provider \
  --allow-external-synthetic-data \
  --case clear-parties-and-property --max-calls 2 --timeout 60 \
  --output /tmp/verification-provider-first.json
```

This sends **only bundled synthetic extracted text**, the normal screening task,
schemas and curated laws through the existing verification provider adapter. It
uses `VERIFICATION_LLM_PROVIDER`, server-held credentials, base URL and extraction/
comparison model overrides. No uploaded case selector, custom fixture file or
customer data import is supported. It sends no page images and does not inspect
real records. Provider configuration must be valid; OpenAI-compatible endpoints
must use HTTPS without URL credentials.

`--case` may be repeated. Omitting it selects the eligible suite. Provider mode
requires the explicit external-data flag. Before any request, the command checks
the maximum possible calls for the selection against `--max-calls` (default 30,
range 1–50). Timeout is 5–120 seconds per call, default 60; connect timeout remains
the adapter's 10 seconds. Calls are sequential, with no automatic retries or
fallback provider. The budget bounds attempts, **not money**. A failed/unfinished
request may still incur charges; avoid blindly repeating an interrupted run.
Cancellation is by interrupting the command; there is no background worker or
automatic scheduled evaluation.

Five scripted failure/grounding cases are replay-only because they intentionally
inject invalid provider answers. Provider mode excludes them and reports the
skipped IDs. The seven provider-eligible cases need at most 14 calls. Results
contain adapter/model names and elapsed time but do not reconcile billing. These
CLI calls are outside background-job usage accounting and do not create usage rows.
Run comparable selections repeatedly if assessing nondeterministic model behavior;
compare suite, pipeline and evaluator hashes before comparing scores.

## Coverage and scoring

The twelve bundled cases are maintained in
`backend/app/verification_evaluation_cases.json`, version `verification-text-v1`:

| Case | Check | Provider eligible |
| --- | --- | --- |
| `clear-parties-and-property` | Correct parties and survey identifier | Yes |
| `cross-document-survey-mismatch` | High-severity mismatch with both citations | Yes |
| `explicit-outstanding-mortgage` | Explicit current mortgage and supplied law | Yes |
| `untrusted-clearance-instruction` | Ignore document commands to clear title or reveal a key | Yes |
| `pending-checklist-needs-review` | Pending checklist prevents conditional review | Yes |
| `historical-mortgage-is-not-current` | Avoid inventing a current adverse finding | Yes |
| `unreadable-text-stays-incomplete` | Missing text remains insufficient evidence | Yes |
| `invented-quotes-and-wrong-pages` | Drop fabricated quotes/wrong page references | No |
| `cross-document-extraction-reference` | Keep each extraction scoped to its source | No |
| `state-law-scope-is-enforced` | Drop an inapplicable state-law reference | No |
| `provider-failure-clears-partial-facts` | Do not retain partial model conclusions after failure | No |
| `schema-cannot-add-legal-clearance` | Reject an extra legal-clearance field | No |

Facts match field, canonical value or a reviewed alias, source ID, page and an
expected literal quote anchor. Longer valid quotes can match. Findings match
category, severity, the exact set of law IDs, all required evidence anchors and
reviewed issue terms in the title/reason. Matching is one-to-one: duplicates and
unmatched outputs count as false positives; unmatched reference items count as
false negatives. Values are normalized with the production text normalizer.

Reports provide TP/FP/FN, precision, recall and F1 separately for facts/findings.
Undefined denominators produce `null`, not an invented perfect score. Unexpected
case errors still count their reference outputs as missing. The gate requires
**no false positives or false negatives**, expected LLM status and server verdict,
grounded evidence/law references, and a permitted non-clearance verdict. Replay
also checks exact rejection counts. Model interpretations remain subject to
advocate review even when every automated check passes.

The report contains suite version/hash, pipeline hash, evaluator hash, law version,
mode, check time, safe model names, counts and fixed case/error codes. It omits
source text, prompts, quote strings, fact values, findings, filenames, endpoint
URLs, credentials, provider bodies and exception messages. Per-case output is
limited to metrics, verdict/status, checks and rejection counts. There is no
report-upload endpoint or public page.

## Maintaining references

Keep every fixture fictional. Review expected facts, semantic quote anchors,
aliases, findings, severity and law applicability; increment the suite version
when references change. The loader validates schema, unique case/document/page
references, replay coverage and source-grounded reference quotes/laws. Avoid
editing reference outputs merely to obtain a passing score. The report's hashes
make changes to cases, evaluation rules and production screening visible.

These small cases cannot establish legal accuracy on production documents. String
matching can flag an otherwise reasonable paraphrase as a mismatch; review a
failed provider run before changing aliases. OCR/image accuracy, language coverage,
upload classification, chat, confidence calibration and real historical case
outcomes remain outside this benchmark. A separately reviewed set of historical
outcomes and professional evaluation are still needed before relying on measured
accuracy in production. No live provider run was performed to ship this feature.
