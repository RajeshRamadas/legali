# AI case-to-blog desk: implementation

**Related:** [requirements.md](requirements.md), [design.md](design.md).

**Status:** the files below are in PR #21, which is not merged to `main` yet.

## Files

| File | What it does |
| --- | --- |
| `backend/app/blog_agent.py` | Scan (web search) → leads; draft (web fetch) → AI post; schedule loop; CLI; admin API under `/api/v1/admin/blog-agent` and `POST /api/v1/admin/posts/{id}/recheck`. |
| `backend/app/blog_checks.py` | Code checks: quote matching, dates/amounts/sections/case numbers vs sources, copying score, warnings. |
| `backend/app/posts.py` | Admin post responses include `origin`, `ai_review` (without stored source text), `reviewed_by`, `reviewed_at`; publish gate (`review_confirmed`). |
| `backend/app/models.py`, `migrations/versions/0014_blog_agent.py` | `case_scan_runs`, `case_leads`, new post columns. |
| `backend/app/config.py` | `BLOG_AGENT_*` settings (below). |
| `backend/app/main.py` | Registers the router; starts the schedule loop when `BLOG_AGENT_ENABLED=true`. |
| `backend/tests/test_blog_agent.py` | Faked Claude client: scan filtering and de-duplication, pause/resume, drafting and checks, publish gate, recheck, failures, scheduled run. |
| `frontend/app/admin/blog/cases/page.tsx` | Case finder: "Find new cases", leads with relevance, "Write draft", "Dismiss", "Review draft". |
| `frontend/app/admin/blog/[id]/page.tsx` | AI review panel (claims ✓/✗, unverified figures, copying %, sources, "Re-run checks") and the review checkbox that unlocks Publish. |
| `frontend/app/admin/blog/blog-agent.css` | Styles for those two admin screens only. Public blog pages are unchanged, so this does not touch the site redesign. |
| `packages/shared/src/index.ts` | `AdminPost`, `AiReview`, `CaseLead`, `CaseScanRun`, `BlogAgentStatus`; `origin` on posts. |

## API (admin only)

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/admin/blog-agent` | Whether the desk is available, schedule, models, domains, last 10 runs. |
| `GET /api/v1/admin/blog-agent/leads?status=` | Leads, newest first. |
| `POST /api/v1/admin/blog-agent/scan` | Start a scan in the background (202). 409 if one is running; 503 without a key. |
| `POST /api/v1/admin/blog-agent/leads/{id}/draft` | Draft a lead in the background (202). |
| `POST /api/v1/admin/blog-agent/leads/{id}/dismiss` | `{"reason": "…"}` |
| `POST /api/v1/admin/posts/{id}/recheck` | Re-run the checks on the saved body. |
| `PATCH /api/v1/admin/posts/{id}` | Publishing an unreviewed AI draft needs `"review_confirmed": true` (else 409). |

## Settings

| Variable | Default | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | (none) | Required; without it the desk is off. Shared with the chat assistant. |
| `BLOG_AGENT_ENABLED` | `false` | In-process schedule. Use on one API instance only; otherwise use cron. |
| `BLOG_AGENT_INTERVAL_HOURS` | `24` | Measured from the last scheduled/cron run, so restarts don't reset it. |
| `BLOG_AGENT_AUTO_DRAFTS` | `2` | Drafts written after a scheduled run (relevance 4+). Drafts only. |
| `BLOG_AGENT_SEARCH_MODEL` | `claude-sonnet-5-5` | Scan. |
| `BLOG_AGENT_WRITE_MODEL` | `claude-opus-5-5` | Draft. |
| `BLOG_AGENT_LOOKBACK_DAYS` | `14` | |
| `BLOG_AGENT_MAX_LEADS` | `8` | Per scan. |
| `BLOG_AGENT_MAX_SEARCHES` / `BLOG_AGENT_MAX_FETCHES` | `8` / `4` | Per-request caps. |
| `BLOG_AGENT_DOMAINS` | see design.md §3 | Comma-separated; subdomains included. |
| `BLOG_AGENT_FALLBACKS` | `default` | Server-side refusal fallback; set `off` on Bedrock, Vertex AI or Foundry. |

Cron alternative: `cd backend && python -m app.blog_agent run` (also `scan`, `draft <lead id>`).

## Cost estimate (Claude API list prices, Nov 2026)

| Step | Rough tokens | Cost |
| --- | --- | --- |
| Scan (Sonnet 5.5, up to 8 searches) | 40k in / 3k out + searches ($10 per 1,000) | about $0.20 |
| Draft (Opus 5.5, 1-2 pages fetched) | 60k in / 6k out | about $0.40 |
| Daily: 1 scan + 2 drafts | | about $1 (₹85) |

Fetched pages count as input tokens. Each run stores its tokens and searches, and each AI post stores its draft's usage in `ai_review.usage`.

## Testing

- `cd backend && pytest tests/test_blog_agent.py tests/test_posts.py` passes on SQLite and on Postgres 16 (`TEST_DATABASE_URL`).
- On Postgres 16: `alembic upgrade head`, `downgrade 0013_more_property_types`, `upgrade head`, and `alembic check` reports no drift.
- `npx tsc --noEmit` in `frontend/` passes.
- **Not yet run against the live Claude API** (no key in the build container). Before turning the schedule on, run one manual scan and one draft from `/admin/blog/cases` and read the result.

## Next steps

FC-6 second-model review, HR-5 advocate sign-off, OP-5 notify admins of new drafts, RSS feeds as an extra lead source.
