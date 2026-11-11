# Prioritizing support responses

Administrators open **Support queue** (`/admin/support`). **Queue order** defaults
to **Earliest response target**: unresolved requests with a pending team-response
target appear first, ordered by that target. Overdue requests precede future
targets. Requests without a pending target follow, most recently updated first.
Choose **Recently updated** to use the previous queue ordering.

**Response target** works together with status, category, owner and
subject/reference search:

| Choice | Included requests |
| --- | --- |
| All response targets | Every request matching the other filters |
| Overdue targets | Unresolved requests whose pending target is before the check time |
| Due within 24 hours | Unresolved requests with a target from the check time through 24 elapsed hours later, including both boundaries |
| No pending target | Requests with no target, plus resolved requests even if a legacy target remains |

The 24-hour view excludes overdue requests. These are elapsed hours, with no
business-hours, holiday or statutory-deadline calculation. Resolving a request
or sending a customer-visible response uses the existing support workflow;
filtering never changes a target or acknowledges an alert.

The queue shows when targets were checked and each listed request's pending
target in India time. Choose **Refresh list** to update the view as time passes
or colleagues work. Counts and pagination can change between requests. Filters
and order changes return to page one. Requests with the same target sort by
latest update, then request ID for stable ties; untargeted requests use the
same update/ID tie breakers.

Queue refresh, pagination, search and filters preserve the open conversation,
unsent reply, private note and selected request status, including when the open
request no longer matches the list. Loading hides the previous list so it is
not presented under new filters. Load errors offer an explicit list refresh;
the conversation stays available. Late responses for previous filters cannot
replace the latest view. Selecting another conversation or explicitly reloading
it retains the existing draft-replacement behavior. Save conflicts still require
reviewing the latest request before retrying.

## API and access

`GET /api/v1/admin/support-requests` accepts two additional query parameters:

- `response_target`: `all` (default), `overdue`, `due_soon`, or `none`.
- `sort`: `updated` (default for existing API consumers) or `response_target`.

Unknown values return 422. Filtering and sorting happen in the database before
counting/pagination. `filtered_overdue` follows all selected filters;
`overdue` continues to count overdue requests across the queue. The new
`response_target_as_of` ISO timestamp records the single server clock used for
filter boundaries, overdue counts and returned item overdue flags. Concurrent
updates can still affect rows/counts during a request; this is a live queue,
not a historical snapshot.

Administrator authentication, private/no-store caching and shared lookup budgets
continue to apply. Agents and customers cannot access the administrator queue.
Customer lists retain their existing order and account scope. The feature adds
no contact fields, message bodies, writes, provider calls, alerts or migrations.
It reads the existing support response-target and ownership fields.

## Verification

From `backend`, run against disposable data only:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_queue_priority.py tests/test_support.py tests/test_support_ownership.py
```

Use a dedicated disposable PostgreSQL `TEST_DATABASE_URL` to verify ordering and
timestamp boundaries. Test fixtures drop and recreate application tables.
Browser fixtures in `frontend/tests/browser/support-priority.spec.ts` cover
filter composition, page reset, draft preservation, queue-error retry, late
responses, accessibility and desktop/phone/narrow widths using synthetic records.

Local validation on 11 November 2026 passed the full SQLite suite (669 tests,
35 skips), PostgreSQL support regressions (85 tests), and the final precise
24-hour boundary checks on both databases (five tests each). Nine new browser
checks and 33 related delivery/ownership/unread checks passed across desktop,
phone and narrow widths, including axe and overflow checks. Workspace type
checks, production builds and Bandit passed. Frontend lint had no errors and
seven existing warnings. The refreshed website, API health and readiness returned
200; anonymous queue access returned 401 with private/no-store caching. Schema
remains at `0036_support_deadline_email`, with no migration needed. Preview
delivery features and background workers remain disabled; no provider messages
were sent.
