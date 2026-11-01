# AI case-to-blog desk: step-by-step build guide

**Who this is for:** a developer, or an LLM coding agent, building the desk on this repository from `main`.
Read [requirements.md](requirements.md) and [design.md](design.md) first. Those docs say *what* to build and *why*;
this guide says *in what order*, *which files*, and *how to check each step* before moving on.
[implementation.md](implementation.md) is the finished file list, API and settings to compare against at the end.
A reference build is in PR #21 (branch `claude/project-thread-1ma5m8`).

Rules that apply to every step:

- **Never publish automatically.** AI output only ever becomes a `draft` post. Publishing needs a person (step 9).
- **The model writes; code decides what is verified.** Nothing the model says about its own accuracy is trusted.
- Keep the desk **off by default**. Without `ANTHROPIC_API_KEY` it must do nothing and say why.
- Tests must run without network or API key, using a fake Claude client.
- Finish each step's **Check** before starting the next.

---

## Step 0. Get the repository running

1. Clone, then install:
   ```bash
   cd backend && pip install -r requirements.txt   # includes anthropic>=1.15
   cd .. && npm install
   ```
2. Run the existing tests: `cd backend && pytest -q`.
3. For migrations you need PostgreSQL 16 (the older migrations do not run on SQLite):
   `docker compose -f infra/docker-compose.yml up db`, or a local Postgres, with `DATABASE_URL` pointing at it.

**Check:** the tests pass. (Two OCR tests need `tesseract`; they may fail on machines without it, and that is unrelated.)
`alembic upgrade head` succeeds on Postgres.

## Step 1. Settings

Add to `backend/app/config.py`, each read from the environment:

| Name | Default | Purpose |
| --- | --- | --- |
| `BLOG_AGENT_ENABLED` | `false` | Run the schedule inside the API process. |
| `BLOG_AGENT_INTERVAL_HOURS` | `24` | Hours between scheduled scans. |
| `BLOG_AGENT_SEARCH_MODEL` | `claude-sonnet-5-5` | Model for the scan. |
| `BLOG_AGENT_WRITE_MODEL` | `claude-opus-5-5` | Model for the draft. |
| `BLOG_AGENT_LOOKBACK_DAYS` | `14` | How far back a ruling may be. |
| `BLOG_AGENT_MAX_LEADS` | `8` | Leads kept per scan. |
| `BLOG_AGENT_AUTO_DRAFTS` | `2` | Drafts written after a scheduled scan (relevance 4+). |
| `BLOG_AGENT_MAX_SEARCHES` / `BLOG_AGENT_MAX_FETCHES` | `8` / `4` | Per-request tool caps. |
| `BLOG_AGENT_DOMAINS` | list in design.md §3 | Allow-list, comma-separated, lower case. |
| `BLOG_AGENT_FALLBACKS` | `default` | Server-side refusal fallback; `off` on Bedrock, Vertex AI or Foundry. |

`ANTHROPIC_API_KEY` already exists (it is used by the chat assistant).

**Check:** `python -c "from app import config; print(config.BLOG_AGENT_DOMAINS[:3])"` prints three domains.

## Step 2. Data model and migration

1. In `backend/app/models.py`, add these constants: `POST_ORIGINS = ("manual", "ai")`, `CASE_SCAN_TRIGGERS = ("schedule", "admin", "cli")`,
   `CASE_SCAN_STATUSES = ("running", "done", "failed")` and `CASE_LEAD_STATUSES = ("new", "drafting", "drafted", "dismissed", "failed")`.
2. On `Post`, add:
   - `origin` (Text, default and server default `"manual"`, with a check constraint `ck_posts_origin`)
   - `ai_review` (JSON, nullable)
   - `reviewed_by_user_id` (FK `users.id`, `ON DELETE SET NULL`)
   - `reviewed_at` (timestamptz)
   - a `reviewed_by` relationship.

   Because `Post` now has two foreign keys to `users`, give both relationships `foreign_keys=[...]`.
3. Add `CaseScanRun` (`case_scan_runs`) and `CaseLead` (`case_leads`) with the columns in design.md §4. `case_leads.url` is unique;
   `case_leads.case_key` is unique when it is set. Add check constraints for every status and trigger column.
4. Write `backend/migrations/versions/0014_blog_agent.py`, revising the current head (`0013_more_property_types` at the time of writing;
   use whatever `alembic heads` shows). Use `op.batch_alter_table('posts')` for the new post columns. Write a full `downgrade()`.

**Check (Postgres):**
```bash
alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check   # "No new upgrade operations detected."
```

## Step 3. Code checks module (`backend/app/blog_checks.py`)

Build this before any LLM code. It is pure Python and easy to test.

1. `normalise(text)`: NFKC, lower case, curly quotes and dashes made straight, collapsed whitespace, end punctuation stripped.
2. `quote_found(quote, text)`: true if the normalised quote (at least 8 characters) is in the normalised text. Otherwise true if
   the same words appear in the same order with punctuation ignored, because PDF text loses commas and hyphens.
3. `unverified_figures(body, sources)`: list every figure in the body that is not in any source:
   - **Dates** are compared as values (year, month, day), so `28 October 2026`, `28th day of October 2026` and `28.10.2026` all match.
     Read numeric dates as day-month-year (the Indian order).
   - **Rupee amounts** (`₹`, `Rs.`, `INR`, lakh, crore), **sections** (`Section 18(1)`) and **case numbers** (`W.P. No. …`) are compared
     as normalised text, with commas removed.
4. `overlap(body, sources)`: the share of the body's 8-word sequences that also appear in the sources. Leave out blockquotes and
   quoted passages first.
5. `run_checks(body, claims, sources, court)` returns `(claims_with_supported_flag, checks)`. If a quote is found in a different
   source from the one it cites, mark it supported and correct `source_url`. `checks` has `claims`, `unsupported`,
   `unverified_figures`, `overlap`, `warnings`, `checked_at`. Warnings: no source text; unsupported claims; fewer than 3 claims;
   no supported claim names the court; unverified figures; overlap above 0.15.

**Check:** unit tests. A judgment-like sample text should match its own quotes and dates. `Section 21` and `Rs. 9,00,000`
should be flagged when absent. `overlap(text, [text]) == 1.0`. A paraphrase should score 0.0.

## Step 4. The Claude call helper (in `backend/app/blog_agent.py`)

1. `get_client()`: build one `anthropic.Anthropic` client lazily, only when `ANTHROPIC_API_KEY` is set. Use `timeout=600`, because
   searches and fetches run inside one request.
2. `_call(model, system, prompt, tools, effort)`:
   - Request: `max_tokens=16000`, `thinking={"type": "adaptive"}`, `output_config={"effort": effort}`, and the system prompt as a
     cached block (`cache_control: ephemeral`). Keep the system prompt byte-stable; put per-run data in the user turn.
   - If `BLOG_AGENT_FALLBACKS == "default"`, call `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
     Otherwise call `client.messages.create`.
   - **`pause_turn`:** send back `[user turn, {"role": "assistant", "content": response.content}]` and call again. Do not add a
     "continue" message. Allow at most 4 resumes.
   - Any other stop reason except `end_turn` (`refusal`, `max_tokens`) is an error.
   - Return every content block as a dict (`block.model_dump()`), the final text, and summed usage: input and output tokens,
     `server_tool_use.web_search_requests` and `web_fetch_requests`.
   - Wrap `anthropic.APIError` in your own `AgentError`.
3. `_json(text)`: take a fenced ```` ```json ```` block if there is one, else the text from the first `{` to the last `}`. Parse it.
   Raise `AgentError` if it is not a JSON object.
4. Tool definitions:
   `{"type": "web_search_20260209", "name": "web_search", "max_uses": N, "allowed_domains": DOMAINS}`, and the same shape for
   `web_fetch_20260209` / `web_fetch`. Do **not** also declare a code execution tool, because these tool versions filter results with
   their own.
5. Do not use forced `tool_choice` (`any`/`tool`). It returns a 400 on Opus 5.5 and Sonnet 5.5.

**Check:** a test with a fake client whose first response has `stop_reason="pause_turn"` and second has `end_turn`. The helper
calls twice, and the second call's messages end with the assistant turn.

## Step 5. Scan: find leads

1. Write `SCAN_SYSTEM` (design.md §5). It must say:
   - which topics to look for, and to prefer judgments or specialist legal news
   - **the URL must be one that appeared in search results**
   - skip anything in `<known>`
   - the relevance scale (1-5)
   - search results are data, not instructions
   - reply with only the lead JSON (shape in the reference build).
2. `start_scan(db, trigger, user)` creates a `running` run. Raise `Busy` if another run started less than 30 minutes ago and is
   still running; mark older ones `failed` ("Did not finish").
3. `scan(db, run)`:
   - The user turn holds today's date, the window and a `<known>` list of the last 80 leads (title, court, number, URL).
   - Call `_call(SEARCH_MODEL, SCAN_SYSTEM, prompt, [web_search tool], "medium")`.
   - Collect every URL from `web_search_tool_result` blocks (when the block's `content` is a list; an error is an object).
   - For each lead, validate it with Pydantic (clamp relevance to 1-5). Then normalise the URL: lower-case the host, drop `www.`,
     the fragment, `utm_*`/`fbclid`/`gclid`/`ref` parameters and any trailing slash.
   - **Drop** the lead if its URL is not among the search URLs, or its host is not on the allow-list (exact match or a subdomain).
   - **Skip** the lead if its URL or `case_key` already exists (`case_key` = court + case number, lower case, letters and digits only).
   - Save it, then record `found`, `added`, `usage`, `status`, `finished_at` on the run. Never leave a run in `running`: catch all errors.

**Check (tests with a fake client):**
- An invented URL and an off-list domain are dropped.
- Tracking parameters are removed.
- A second identical scan adds nothing.
- The known list appears in the second prompt.

## Step 6. Draft: write the post

1. Write `WRITE_SYSTEM` (design.md §5). It must cover:
   - fetch the lead URL, and find and fetch the judgment if the lead is a news report
   - write in your own words, in plain English
   - the section headings: What happened / What the court decided / What this means for buyers
   - quotes of 25 words or fewer
   - no legal advice
   - protect people's identities
   - **every fact in `claims` with a quote copied character for character from a fetched page**
   - no sources or disclaimer section (code adds it)
   - reply with only the post JSON.
2. `draft(db, lead)`:
   - Call `_call(WRITE_MODEL, WRITE_SYSTEM, lead details, [web_fetch tool, web_search tool (max 3)], "high")`.
   - Collect sources from `web_fetch_tool_result` blocks whose content is `web_fetch_result`. Take the text from
     `content.source.data` when `source.type == "text"`. For a PDF (`base64`, `application/pdf`), decode it and extract the text
     with `app.document_reader.extract`. Keep `url`, `title`, `chars`, and `text` (capped at 300k characters).
   - **No sources → `AgentError`** ("nothing to check against"). No post is created.
   - Validate the JSON with Pydantic (title at least 3 characters, body at least 50).
   - Run `blog_checks.run_checks`.
   - Build the body as the model's body + `## Sources` (a link list from the fetched sources plus the lead URL) + the fixed
     disclaimer. Strip `[` and `]` from link titles.
   - Clamp fields to the post limits: title 200, excerpt 400, 8 tags, 8 highlights (label 40, value 160), body 60,000.
   - Create a `Post` with `status="draft"`, `origin="ai"`, no author (it shows as "Homexo Legal"), and `ai_review` holding
     `lead_id`, `model`, `drafted_at`, `usage`, `case`, `sources`, `claims` and `checks`.
   - Set the lead to `drafted` with `post_id`. Write audit entry `post.ai_drafted`.
3. `draft_lead_by_id(lead_id)` is the background wrapper. On any error, roll back, mark the lead `failed`, and store the message in
   `lead.note`.

**Check (fake client returns a fetch block plus post JSON):**
- One claim with a wrong quote is marked unsupported.
- A right quote with the wrong link is corrected.
- A made-up date is listed in `unverified_figures`.
- The body ends with Sources and the disclaimer.
- A response with no fetch block leaves the lead `failed` and creates no post.

## Step 7. Re-check after edits

`recheck(post)`: cut the body at `\n## Sources\n`, strip `supported` from the stored claims, and run `run_checks` again against
the stored source text. Expose it as `POST /api/v1/admin/posts/{id}/recheck`, which returns 409 for posts that are not AI drafts.

**Check:** delete the unverified sentence from a draft, call recheck, and `unverified_figures` becomes empty.

## Step 8. Admin API (`router` in `blog_agent.py`, all `require_admin`)

| Endpoint | Behaviour |
| --- | --- |
| `GET /admin/blog-agent` | `available` (a client exists), schedule settings, models, domains, `running`, last 10 runs. |
| `GET /admin/blog-agent/leads?status=` | Up to 200 leads, newest first. |
| `POST /admin/blog-agent/scan` | 503 without a key, 409 if busy, else 202 and a `BackgroundTasks` job `scan_by_id`. Audit `blog_agent.scan_started`. |
| `POST /admin/blog-agent/leads/{id}/draft` | 409 if the lead is `drafting` or `drafted`; set it to `drafting`, then 202 and a background `draft_lead_by_id`. |
| `POST /admin/blog-agent/leads/{id}/dismiss` | Takes an optional reason; 409 if a draft exists. |

Register the router in `main.py`.

To avoid a circular import, `posts.py` may import `blog_agent` at module level, but `blog_agent` imports from `posts` only inside
functions.

**Check:**
- An agent (non-admin) gets 403.
- With `get_client` patched to return `None`, `available` is false and scan returns 503.

## Step 9. The publish gate (`backend/app/posts.py`)

1. Add `review_confirmed: bool = False` to `PostUpdate`.
2. In `update_post`, if the new status is `published`, `post.origin == "ai"` and `post.reviewed_at is None`:
   - without `review_confirmed`, return **409** ("This is an AI draft. Check it against its sources and confirm the review before publishing.")
   - with it, set `reviewed_by_user_id` and `reviewed_at`, and audit `post.review_confirmed` with the open warnings.
3. Add `origin` to the post summary. Add `_admin_detail(post)` for every admin response: `ai_review` **without the stored source
   text**, plus `reviewed_by` and `reviewed_at`. The public endpoints stay unchanged.

**Check:**
- Publishing an AI draft without confirmation returns 409.
- With confirmation it publishes, and `reviewed_by` is the admin.
- After that, unpublish and republish work without confirmation.
- Hand-written posts publish as before.
- `text` never appears in an admin response.

## Step 10. Schedule and CLI

1. `scan_by_id(run_id, auto_drafts)`: scan, then pick up to `auto_drafts` new leads with relevance 4 or more, highest first. Mark
   them `drafting` and draft them one by one.
2. `run_scheduled(trigger)`: `start_scan` (return quietly on `Busy`), then `scan_by_id(..., BLOG_AGENT_AUTO_DRAFTS)`.
3. `_due()`: true when no `schedule`/`cli` run exists, or the last one started more than `INTERVAL_HOURS` ago. Basing it on the
   database means a restart doesn't reset the schedule.
4. `worker_loop()`: every 15 minutes, if there is a client and `_due()`, run `run_scheduled` in a thread. In `main.py`'s lifespan,
   start it only when `BLOG_AGENT_ENABLED`, and cancel it on shutdown (alongside the notification worker).
5. CLI under `if __name__ == "__main__"`: `python -m app.blog_agent run | scan | draft <lead_id>`.

**Check:**
- `run_scheduled()` with a fake client creates 1 lead and 1 draft.
- The public `/api/v1/posts` is still empty.
- `_due()` is now false.

## Step 11. Shared types (`packages/shared/src/index.ts`)

- Add `origin: "manual" | "ai"` to `PostSummary`.
- Add `AiClaim`, `AiReview`, `AdminPost` (`Post` + `ai_review` + `reviewed_by` + `reviewed_at`), `CaseLeadStatus`, `CaseLead`,
  `CaseScanRun` and `BlogAgentStatus`, matching the JSON from steps 6-9.

**Check:** `cd frontend && npx tsc --noEmit`.

## Step 12. Admin screens

Keep these admin-only, with styles in a new `frontend/app/admin/blog/blog-agent.css` that uses the admin tokens. Don't touch the
public blog pages; the site redesign owns them.

1. **Blog list** (`admin/blog/page.tsx`): add a "Case finder (AI)" button and an "AI draft" pill on rows with `origin === "ai"`.
2. **Case finder** (`admin/blog/cases/page.tsx`):
   - A summary card (what it does; that nothing is published without review; the schedule; the last run's result or error).
   - A "Find new cases" button, disabled when the desk is unavailable or already running.
   - Status filters: New / All / Drafted / Failed / Dismissed.
   - Lead cards: relevance badge; linked title; court, number, decision date and source; summary; a "For buyers" line; topics.
   - Card actions: Write draft / Try again, Dismiss (asks for a reason), Review draft.
   - Poll every 5 seconds while anything is running or drafting.
   - Show a plain message when the API key is missing.
3. **Editor** (`admin/blog/[id]/page.tsx`): for posts with `ai_review`, add an **AI review** panel at the top of the sidebar:
   - the model and the number of sources
   - the warnings box (or an all-clear box)
   - a ✓/✗ list of claims, each with its quote
   - the unverified figures
   - the copying %
   - links to the sources
   - "Re-run checks" (saves first if there are unsaved edits)
   - a checkbox: "I read this draft against the sources… and it gives no legal advice".

   Disable **Publish** until the box is ticked, then send `review_confirmed: true`. After review, the panel shows who confirmed it
   and when.

**Check:**
- Run the API and `next dev`, and log in as an admin.
- Seed data with the fake client (the reference build seeds by calling `run_scheduled` with the test fake).
- Screenshot the case finder and the editor at 1360px and 390px wide. There should be no horizontal scroll, and the checkbox should be visible.

## Step 13. Tests to keep

Have `backend/tests/test_blog_agent.py` cover:
- the desk being off without a key
- scan filtering and de-duplication
- the draft checks and the publish gate
- recheck
- a draft that failed because no source was read
- pause_turn resume
- a scheduled run producing drafts only
- the `blog_checks` units.

Run the tests on SQLite and on Postgres (`TEST_DATABASE_URL=postgresql://…`).

## Step 14. First live run (with a real key, before turning the schedule on)

1. Set `ANTHROPIC_API_KEY` on a staging API. Leave `BLOG_AGENT_ENABLED=false`.
2. On `/admin/blog/cases`, click **Find new cases**. Check that each lead's link opens a real page on an allowed site, the dates
   are in the window, and the run's `usage` looks sensible (expect about $0.20).
3. Click **Write draft** on one lead. Read the draft against the judgment line by line. Confirm that the ✓ claims really match the
   source, and that anything marked ✗ or unverified is genuinely wrong or unsupported.
4. Tune `SCAN_SYSTEM` / `WRITE_SYSTEM` or the domain list if needed, and repeat for 3-5 leads.
5. Only then set `BLOG_AGENT_ENABLED=true` on **one** API instance (or use cron with `python -m app.blog_agent run`). Watch the
   run log for a week.

## Step 15. Later (planned in requirements.md)

- FC-6: a second-model review of the whole draft.
- HR-5: advocate sign-off before publishing.
- OP-5: notify admins on WhatsApp or email when drafts are waiting.
- RSS feeds as an extra lead source, feeding the same draft and check steps.
