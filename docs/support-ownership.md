# Support-request ownership

Administrators can assign a responsible person from **Support queue** at
`/admin/support`. Open a request, choose an active administrator under **Support
owner**, and choose **Save support owner**. **Assign to me** claims it for the
signed-in administrator. Select **Unassigned** to clear ownership.

Ownership helps route operational work; every administrator retains the existing
support access. It does not grant agents access to private complaints. Support
ownership is separate from case assignment and the lawyer handling a consultation.
Customers do not receive the owner's identity or assignment history.

## Queue and handoff

The **Owner** filter offers All owners, Assigned to me, Unassigned, Owner
unavailable and named active administrators. Status/category/search filters and
pagination combine with it. The response-target count shown in the queue applies
to the current view; the API also retains its existing global overdue count.
An open conversation stays selected when its assignment moves it outside the
current filter, so an unsent draft is not silently discarded.

Only active administrators can receive a new assignment. A saved owner who is
suspended or loses administrator access stays visible as unavailable until
reassigned. Review **Owner unavailable** and **Unassigned** regularly. Removing a
staff row clears its current ownership through the foreign key; explicit
assignment history remains in the private audit log.

Ownership is retained through customer follow-up, resolution and reopening.
Resolved requests may also be assigned for accountability without reopening them.
Saving an owner does not change support status, response target, unread/read
counters, customer-visible messages, payments or case assignments.
The owner must monitor the queue; assignment itself sends no provider messages.
When optional [staff deadline email](support-deadline-email.md) is enabled,
ownership changes cancel obsolete pending recipient routes; monitoring can queue
the newly eligible owner without changing the incident or customer conversation.

## Drafts and conflicts

Saving ownership keeps unsent response and internal-note drafts. The saved editing
revision advances for that assignment, so the administrator can continue their
review. Reply submission and ownership changes cannot run simultaneously from
the editor.

Another administrator's assignment, a customer reply or a support review can make
an ownership draft stale. Such a save returns 409 without overwriting the newer
state. The owner choice, reply and private note stay on screen.
**Reload latest request** explicitly replaces those drafts with the current
conversation. A lost-response retry can also return 409; review the saved state
before trying again. Saving the current owner with the current revision is a
no-op and does not add another history event.

**Private assignment history** records actor, time and previous/new owner, with
20 changes per page. Names reflect current staff records; removed staff appear as
Former administrator. History contains no customer reply or private-note text.

## API and concurrency

- `GET /api/v1/admin/support-requests/owners` lists eligible administrator IDs and
  names without email addresses or phone numbers.
- The queue accepts `assignee=all|me|unassigned|inactive|<UUID>` and returns
  `filtered_overdue` in addition to its existing global `overdue`.
- Staff summary/detail responses include `assignee` with ID, name and eligibility.
  Customer responses omit ownership fields.
- `PATCH /api/v1/admin/support-requests/{id}/assignment` requires strict integer
  `revision` and explicit `assignee_user_id` (UUID or null). Unknown, agent or
  inactive targets receive 422; stale revisions receive 409.
- `GET /api/v1/admin/support-requests/{id}/assignments?page=1` returns private
  paginated history.

All routes require administrator authentication and use shared lookup/write
budgets and private/no-store responses. Assignment follows the existing support
account/request lock order. PostgreSQL serializes simultaneous changes so one
editing revision can produce only one ownership change. Private audit action
`support.assigned` stores owner references and revision without message contents.
Queue owner metadata is fetched in batches rather than once per request.

## Deployment and rollback

Back up the database, stop old API writers and apply `0033_support_ownership`
with `alembic upgrade head` from `backend`, then start the updated API and website.
Existing requests start unassigned. Messages, deadlines and unread counters are
retained. No assignment or notification is created by migration or startup.

Downgrade refuses while any request remains assigned, including resolved work.
PostgreSQL holds an exclusive support-table lock for that guard. Do not clear real
ownership simply to force rollback; use a reviewed recovery or forward-fix
procedure. A permitted downgrade removes the owner column/index while retaining
conversations, read counters and private audit history. Include ownership and its
history in support-record backup, privacy/access and retention procedures.

## Verification

Run from `backend` with isolated data:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_support_ownership.py tests/test_support_ownership_migration.py tests/test_support.py tests/test_support_unread.py
```

Use a **disposable** PostgreSQL `TEST_DATABASE_URL` for the simultaneous-writer
test. Fixtures drop and recreate application tables; never use a live database.
The real migration canary verifies rollback refusal and preservation of support
messages and unread state across a permitted down/up cycle. Browser fixtures
cover draft preservation, review revision updates, conflict recovery, owner
filters, agent boundaries, history, axe and overflow at desktop/mobile/narrow
widths. They use synthetic requests and never assign live customer work.

Validated on 10 November 2026: the full SQLite suite passed 610 tests (31
skipped). After the final unavailable-owner filter and resolved-case
checks, the focused SQLite suite passed five tests (one PostgreSQL-only skip).
PostgreSQL support/customer regressions passed 60 tests, with all six final
ownership/migration checks passing, including simultaneous assignment conflicts.
The real PostgreSQL migration canary refused removal of assigned ownership and
retained messages and unread counters across an allowed downgrade/upgrade.

The production browser suite passed 167 checks with one existing
desktop-inapplicable skip. Workspace type checks, isolated and local production
builds, Bandit and actionlint passed. Frontend lint had no errors and seven
existing warnings. A verified private database backup preceded the local preview
migration to `0033`; API health/readiness and the website returned 200, while an
unauthenticated owner-list request returned 401 with private/no-store caching.
The disposable PostgreSQL test database was removed after verification. No live
support request was assigned and no provider message was sent.
