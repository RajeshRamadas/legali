# AI case-to-blog desk: requirements

**Status:** agreed requirements, 2026-11-01. The code is in PR #21 (not merged yet), so "Built" below means built and tested in that PR.
**Related:** [design.md](design.md) (how it works), [implementation.md](implementation.md) (file by file, setup, cost).

Each requirement has an ID and a status: **Built** (in this branch, covered by tests), **Partial** (built with a stated
gap) or **Planned** (agreed direction, not built).

## 1. Purpose

Homexo Legal's blog (articles and case studies, `/blog`, admin editor at `/admin/blog`) brings in buyers who search for
property-law questions. Writing about a fresh court ruling the week it comes out is the content that ranks and gets
shared, but someone has to watch the legal news, read the judgment and write a plain-English post.

The desk does that first pass: it **finds** recent court rulings and news that matter to Bengaluru/Karnataka home buyers,
**drafts** a blog post from the primary source, **checks** every fact in the draft against the source text in code, and
puts it in front of an admin as a **draft**. A person always reviews and publishes. Nothing is published automatically.

## 2. Users

| User | Needs |
| --- | --- |
| Admin (editor) | A short list of new, relevant cases each day; one click to get a draft; a clear view of which statements are backed by a quote and which are not; publish only after checking. |
| Advocate (optional reviewer) | Drafts that quote the judgment accurately, name the court, case number and date, and do not give legal advice. |
| Reader (public) | Accurate, readable posts with links to the original judgment or report. |
| Operator | Control over schedule, sources, models, cost, and an off switch. |

## 3. Scope

In scope: discovering rulings and news on an allow-list of legal news and court sites; summarising and drafting posts in
the existing blog format; automated fact and citation checks; an admin review queue; scheduling and manual runs.

Out of scope (for now): automatic publishing, social media posting, cover-image generation, Kannada posts, paid
databases (SCC Online, Manupatra), and reading e-Courts case status pages that need a captcha.

## 4. Functional requirements

### 4.1 Sourcing (finding cases)

| ID | Requirement | Status |
| --- | --- | --- |
| SR-1 | Search the web for court rulings, orders and regulator decisions from the last `BLOG_AGENT_LOOKBACK_DAYS` (default 14) days that matter to property buyers in Bengaluru/Karnataka: title disputes, RERA, builder delays and refunds, khata/BBMP/BDA, land conversion, registration and stamp duty, consumer forum orders against builders, and Supreme Court rulings with national effect. | Built |
| SR-2 | Search only an allow-list of domains (legal news, court and regulator sites, major newspapers), configurable with `BLOG_AGENT_DOMAINS`. | Built |
| SR-3 | Record each result as a **case lead** with title, court, decision date, source URL and site, a one-paragraph summary, why it matters to buyers, topics and a relevance score 1-5. | Built |
| SR-4 | Drop any lead whose URL did not actually come back from the search (the model may not invent URLs) or is off the allow-list. | Built |
| SR-5 | Never store the same case twice: de-duplicate by normalised URL and by court + case number. | Built |
| SR-6 | Keep a run log: when, trigger (schedule or admin), status, leads found and new, model, token and search usage, error. | Built |

### 4.2 Drafting (LLM summarising and writing)

| ID | Requirement | Status |
| --- | --- | --- |
| DR-1 | From a lead, read the primary source (the judgment where it can be found, else the news report) with the web fetch tool and write a post in the existing format: type (case study or article), title, summary, Markdown body, tags, "case at a glance" highlights. | Built |
| DR-2 | Write in plain English for home buyers, in original words. Quotes from the source are short (25 words or fewer) and marked as quotes. Include "What this means for buyers" and avoid telling a reader what to do in their own case. | Built |
| DR-3 | Return a list of **claims**: every factual statement about the case (parties, court, bench, dates, amounts, sections, outcome), each with a verbatim quote from a fetched source and that source's URL. | Built |
| DR-4 | Add a "Sources" section with links and a standard disclaimer in code, not by the model. | Built |
| DR-5 | Name private individuals only as they appear in the case title; never include personal details beyond the source; never identify parties the law protects (minors, sexual offence victims). | Built (prompt) |
| DR-6 | Fail the lead (no post) if no source page could be read. | Built |

### 4.3 Fact and citation checks (in code, after the model)

| ID | Requirement | Status |
| --- | --- | --- |
| FC-1 | Each claim's quote must be found in the text of the source it cites (normalised whitespace, quotes, case). Claims are marked supported or unsupported. | Built |
| FC-2 | Every date, rupee amount, section/Act number and case number in the body must appear in at least one source; anything else is listed as an unverified figure. | Built |
| FC-3 | Measure copying: the share of 8-word sequences in the body that also appear in the sources. Above 15% is flagged. | Built |
| FC-4 | Flag drafts with fewer than 3 claims or no claim naming the court. | Built |
| FC-5 | An admin can re-run the checks after editing the body, against the stored source text. | Built |
| FC-6 | A second-model review ("does the body say anything the sources do not support?") as an extra check. | Planned |

### 4.4 Human review and publishing

| ID | Requirement | Status |
| --- | --- | --- |
| HR-1 | AI drafts land in the blog list as normal drafts, marked "AI draft". | Built |
| HR-2 | The editor shows the review panel: sources, each claim with supported/unsupported, unverified figures, copying score. | Built |
| HR-3 | Publishing an AI draft needs the admin to tick "I checked this against the sources". The API refuses to publish without it and records who confirmed and when (audit log). | Built |
| HR-4 | Leads can be dismissed with a reason, so they are not offered again. | Built |
| HR-5 | Optional advocate sign-off step before publishing. | Planned |

### 4.5 Scheduling and operations

| ID | Requirement | Status |
| --- | --- | --- |
| OP-1 | Run a scan on a schedule inside the API process (`BLOG_AGENT_ENABLED`, `BLOG_AGENT_INTERVAL_HOURS`, default 24), or from cron with `python -m app.blog_agent run`. Off by default. | Built |
| OP-2 | After a scheduled scan, draft the top `BLOG_AGENT_AUTO_DRAFTS` (default 2) leads with relevance 4 or more. Drafts only; never publishes. | Built |
| OP-3 | Admins can start a scan and draft any lead from `/admin/blog/cases`. Only one scan at a time. | Built |
| OP-4 | Without `ANTHROPIC_API_KEY` the desk is off: the page explains why and nothing calls out. | Built |
| OP-5 | Email/WhatsApp the admin when new drafts are waiting. | Planned |

## 5. Non-functional requirements

| ID | Requirement | Status |
| --- | --- | --- |
| NF-1 | Cost: a daily scan plus two drafts should stay around ₹100 a day (see implementation.md). Searches and fetches are capped per call. | Built |
| NF-2 | Fetched pages are untrusted. Their text is treated as data in prompts, output goes only to drafts, and the Markdown renderer allows only http(s) links. | Built |
| NF-3 | Legal and copyright: original summaries, short quotes, always link the source, disclaimer on every post, no legal advice. | Built |
| NF-4 | Every AI action is logged (run log, lead status, audit log on publish). | Built |
| NF-5 | Tests run without network or API key (the Claude client is faked). | Built |

## 6. Open questions for Rajesh

1. Domain allow-list: is the default list (design.md section 3) right? Any site you do not want quoted?
2. Should an advocate sign off before publishing (HR-5), or is an admin's check enough?
3. Schedule: daily at 07:00 IST with 2 auto drafts, or manual only to start?
4. Should posts show "Written with AI assistance, reviewed by <name>" publicly?
