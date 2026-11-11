# Staff task queue

Open **Task queue** from the staff navigation (`/admin/tasks`) or the case board's
**Open full task queue** link. The default view shows your open tasks on cases you
can currently open. Administrators can also choose **Everyone** or **Unassigned**.
Search task titles or case numbers, choose task status, due-date group and case
priority, then **Apply task filters**. Editing filters makes no request until you
apply them. **Clear task filters** returns to your open tasks.

Rows show the task title, status/overdue marker, current customer/service names,
assignee, due time, case priority, routine/manual source and case status. **Open
case** leads to the existing checklist, where staff can review notes and complete,
cancel or reopen tasks under current case permissions. The queue itself is read
only and does not perform task changes or send messages.

## Priorities, dates and paging

Open tasks come before finished tasks. Within each group, tasks with a due date
come first, ordered by earliest due time. Tied due times use urgent/high/normal/low
case priority, then task UUID for deterministic ordering. Undated tasks follow
dated tasks. This order places overdue open tasks before upcoming ones.

- **Overdue** means an open task whose due time is strictly earlier than the
  server's check time. A task due exactly at that time is not yet overdue.
- **Due today** uses the inclusive start and exclusive end of the current
  `Asia/Kolkata` calendar day. It can include tasks already overdue today.
- **Next 7 days** includes times from now through, but excluding, now plus seven
  days. It excludes earlier times today.
- **No due date** matches tasks with no recorded due time.

All displayed times explicitly use IST. Completed and cancelled task filters can
be combined with date filters; **Overdue** always requires an open task. Closed
cases are excluded even when task status is **All**. Case holds pause case targets
but do not change task due dates, and held cases are labelled in queue rows.

The summary counts open, overdue, open due-today and open undated tasks within
the applied filters, across all matching pages. Selecting only finished tasks
therefore yields zero open-task counts. Total matching tasks includes the selected
statuses. Each response includes its server check time.

**Previous tasks**, **Next tasks** and **Refresh tasks** use the applied filters,
keeping unapplied filter edits. Refresh checks the current page again. Applying
or clearing starts at page one. Failed lookups keep the last successful page and
its scope, label it potentially out of date, preserve edits and focus the error.
Successful manual loads focus feedback. If a shrinking queue leaves the page
empty, use Previous or clear/apply filters to return to page one. Rows and counts
reflect queries at the check time; concurrent work can move tasks between pages.

There is no automatic polling, cached previous-page snapshot or browser-storage
copy of queue data. Leaving the page discards local filters and results.

## Access and privacy

Both the new queue and the existing `GET /api/v1/admin/tasks` enforce current case
visibility in SQL before filtering, counting or limiting. Administrators keep
their existing case access. Agents need an active case assignment, a current case
team membership or an existing non-cancelled lawyer meeting, as defined by the
case workspace's existing rules. An agent's queue additionally contains only
tasks assigned to that agent.

Assigning a task alone does not grant case access. Case owners/administrators
must add staff to the case team when needed. Removing the last case-access path
hides its tasks from subsequent reads, even if they remain assigned. Tasks are
neither deleted nor reassigned. Re-granting access makes eligible tasks visible
again. The task-creation form explains this requirement.

The new queue selects only its response fields and omits task notes, customer
contacts, case structured answers, messages and documents. These remain in the
existing case workspace. Search matches only task titles and case numbers; `%`,
`_` and backslash are literal characters. Staff-supplied text renders literally.
An agent's filtered counts never include tasks from inaccessible cases.

Staff authentication is required: absent/customer credentials receive 401. Agents
requesting another ownership scope receive 403 on the new route. The legacy
route retains its existing behavior of coercing agent requests to their own
tasks, with the added case-access restriction. Both routes use private/no-store
caching, vary on authorization and share the private lookup budget (429 with
Retry-After). Already displayed data is a snapshot; a successful refresh replaces
it using current permissions. Existing session expiry handling still signs out.

## API and rollout

`GET /api/v1/admin/task-queue` accepts:

- `assignee`: `me` (default), `all`, `unassigned`, or an exact staff UUID. Only
  administrators may use scopes other than `me`; the UI offers the first three.
- `status`: `open` (default), `done`, `cancelled`, `all`.
- `due`: `all` (default), `overdue`, `today`, `week`, `unscheduled`.
- `priority`: `all` (default), `urgent`, `high`, `normal`, `low`.
- `q`: task-title/case-number substring, at most 100 characters; trimmed, with
  control characters rejected.
- `page`: 1–10000, default 1. `page_size`: 1–100, default 25.

The response includes `items`, `total`, `page`, `page_size`, `checked_at` and
`summary` (`open`, `overdue`, `due_today`, `unscheduled`). Rows allowlist `id`,
`title`, `status`, `source`, `due_at`, `overdue`, nullable assignee ID/name and case
number/status/label/priority/service/customer name. Invalid filters return 422.

Deploy API and website together. There are no new migrations, dependencies,
credentials or workers; schema remains `0039_activity_history_index`. Before
rollout, review task assignees who lack case access and add the appropriate case
team memberships. Do not rely on task assignment as a permission grant.

## Verification

Run tests from `backend` using disposable data only; fixtures drop/recreate
application tables:

```bash
TEST_DATABASE_URL=sqlite:// python -m pytest -q tests/test_task_queue.py tests/test_cases.py
```

Backend tests cover staff boundaries, task-only assignments, current owner/team/
meeting access and revocation, duplicate access paths, closed/held cases,
ownership/status/search/priority combinations, literal wildcards, IST midnight
and rolling-week boundaries, deterministic paging and counts, private SQL/response
fields, read-only behavior and shared lookup budgets. Browser fixtures cover
explicit filtering, paging, current-page refresh, preserved edits, focused error
recovery, empty/shrinking queues, agent options, access changes, case links, axe
and desktop/phone/narrow layouts. Intercepted fixtures do not create or change
normal-preview tasks.

Local verification on 11 November 2026 passed the full SQLite suite (786 tests,
40 skips), PostgreSQL regressions (87 tests) and 54 browser checks across desktop,
phone and narrow layouts. Type checks and production builds passed. Lint had no
errors and seven existing warnings; Bandit passed with complete coverage and no
findings at its medium/high severity gate. Desktop and phone queue screenshots
were inspected, with axe and horizontal-overflow checks passing.

The disposable PostgreSQL test database was removed. API and website previews
were refreshed without a migration. Health/readiness, homepage, task queue and
case board returned 200. Both task-list routes returned 401 for anonymous access,
with private/no-store caching and authorization variance. No tasks were created
or changed for normal-preview fixtures. Delivery/background flags remain off,
and no provider messages were sent.
