# Consultation review moderation

Customers can still rate a consultation once after it ends, using the verified
account that owns the booking. New feedback starts **Waiting for review** and
remains private to that customer and authorized administrators until published.
Only published feedback contributes to public review lists, rating averages,
review counts and rating-based search ordering. Consultation counts are unchanged.

## Administrator workflow

Open **Review moderation** at `/admin/reviews`. The pending queue starts with
the oldest feedback. Filter by publication status or search by lawyer/case
number. Queue results and decision history are paginated, 20 records per page.

Select feedback, read it in full and choose **Publish feedback** or **Do not
publish / hide feedback**. A decision requires confirmation that the content
was reviewed, a reason and a private note. Apply the same publication policy to
positive and negative ratings. A low star rating alone is not a reason to hide
feedback. Check for personal/contact details, confidential case information,
abuse, relevance and authenticity; agree the publication policy with the
responsible legal/privacy team before launch.

Administrators can publish pending/hidden feedback or hide pending/published
feedback. They cannot edit the customer's rating, words or displayed author name,
and cannot moderate reviews about their own lawyer profile. Another
administrator must decide those cases. Agents cannot read or change this queue.
Customer-facing booking information shows publication status without the
moderator's identity, reason or note. A hidden review still exists privately;
it does not grant another rating submission for the same consultation.

Every change appends a private decision record with its actor, time, reason,
note and revision. General audit metadata records the transition/revision/code,
excluding free-text feedback and notes. History follows the review's database
retention/backup rules; it is not a separate tamper-proof archive.

Conflicting decisions return **409**. The editor keeps its original revision
and note until the administrator explicitly selects **Reload review (replaces
draft)**. Concurrent customer submissions create at most one review, and
concurrent moderator decisions create at most one decision for the same revision.
Read/write endpoints use the existing shared API budgets and private no-store
responses. Feedback is displayed as text rather than interpreted HTML.

## Migration and rollout

Migration `0027_review_moderation` adds publication state, revisions, update
timestamps and decision history. **All existing reviews enter the pending
queue**, preserving their original wording, stars, author and submission date.
Public ratings/counts may decrease until those reviews are reviewed and published.
No customer messages or automatic publication jobs are sent/run by this feature.

Back up the database, stop old API instances, run `alembic upgrade head` from
`backend/`, then start the updated API before reopening public access. Do not
serve a mix of old and new API versions: the old implementation ignores the
publication state and can expose pending/hidden feedback. Public search/profile
responses now request no caching, but existing browser views or cached homepage
rating cards may remain until refreshed; the homepage retains its normal
five-minute revalidation interval.

Downgrade removes moderation state and decision history while retaining the
original feedback. Preserve that history separately and disable public review
access before rollback; serving the old API can republish previously withheld
content. Review the deployment and backup runbooks before a production cutover.
Review moderation does not replace consent/retention procedures or guarantee
removal of copies published before rollout.

## API and validation

- `GET /api/v1/admin/reviews?status=pending&q=&page=1`: private queue/counts.
- `GET /api/v1/admin/reviews/{id}?page=1`: feedback and private decision history.
- `PATCH /api/v1/admin/reviews/{id}`: strict `revision`, `status`, `reason`,
  `note` and `reviewed` fields; only `published`/`hidden` targets are accepted.

From `backend/`, run `pytest tests/test_review_moderation.py tests/test_lawyers.py`.
Use a disposable PostgreSQL `TEST_DATABASE_URL` for both concurrency tests;
test fixtures drop/recreate application tables. The complete suite defaults to
in-memory SQLite. Browser checks in `frontend/tests/browser/reviews.spec.ts`
use synthetic API responses at desktop, mobile and narrow widths, including axe,
draft preservation, role restrictions and customer publication status. No real
customer feedback or live provider action is needed for validation.

Local validation on 2026-11-10: the full SQLite suite passed 539 tests (21
database-specific skips). PostgreSQL passed 52 booking/payment/moderation
regressions, with both concurrency scenarios also checked separately. Migration
up/down/up checks preserved original feedback on PostgreSQL and a prepared
SQLite baseline; older historical migrations remain PostgreSQL-oriented. The
full browser suite passed 89 tests (one inapplicable desktop case skipped),
including all 15 moderation checks. Type checks, lint, production build and the
configured Python source-security scan passed.
