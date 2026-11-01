# Case management: step-by-step build guide

This guide is for a developer or an LLM coding agent building case management into this repository from
scratch. Follow the steps in order. Each step names the files to touch, says what to write, and ends with a
check you can run before going on. The *what* and *why* are in [README.md](README.md); this file is the *how*.

The reference build of phase 1 is pull request #20 (branch `claude/project-thread-j5nyde`). If you can read
that branch, use it as an answer key, but do not copy it blindly: follow the steps so that each part is tested
as you go.

## Before you start

**Know the codebase.** These are the files that case management touches. Read them first.

| File | What is in it today |
| --- | --- |
| `backend/app/models.py` | SQLAlchemy models. `ServiceRequest` is the ticket (the case). `Assignment` holds the case owner. `TicketEvent` is the activity log. `LegalReport` and `ReportItem` hold the document checklist and report. `Meeting` holds video consultations. |
| `backend/app/tickets.py` | Ticket lifecycle: `create_ticket`, `add_event`, `change_status`, `add_message`, `queue_notifications`, and the views `customer_view`, `staff_summary`, `staff_detail`. |
| `backend/app/admin.py` | Staff API: login, queue, `GET/PATCH /admin/tickets/{n}`, assignment, messages. `_visible_tickets(user)` decides which tickets an agent can see. `_get_ticket` and `_detail` are reused by other routers. |
| `backend/app/documents.py` | Report and checklist endpoints (issue, review item, final PDF, signed upload). |
| `backend/app/case_files.py` | `checklist_complete(report)` and report views. |
| `backend/app/document_requirements.py` | `SERVICES` (services that run a document checklist) and `view(ticket)` (the customer's document request). |
| `backend/app/accounts.py` | Customer account API; `_request_summary` and `_needs_you` build each request row. |
| `backend/app/config.py` | Settings from environment variables. |
| `backend/migrations/versions/` | Alembic migrations, numbered `0001` to `0013` on main. |
| `backend/tests/conftest.py` | Fixtures: `client`, `admin_headers`, `agent`, `raise_ticket`. Tests run on SQLite by default. |
| `packages/shared/src/index.ts` | API types shared by the website and the app (`TicketStatus`, `AccountRequest`). |
| `frontend/app/admin/` | Staff workspace: `AdminShell.tsx` (navigation), `api.ts` (types and `adminFetch`), `tickets/[ticketNumber]/page.tsx` (ticket page). |
| `frontend/app/TrackRequest.tsx`, `frontend/app/account/page.tsx` | Customer tracking card and account page. |
| `frontend/app/ui/tokens.css` | Homexo UI colour tokens (`--primary`, `--surface`, `--surface-2`, `--ink`, `--ink-2`, `--ink-3`, `--line`, `--red-50`, `--red-ink`, `--amber-50`, `--amber-ink`, `--green-50`, `--green-ink`). Light and dark themes. |

**Set up and run the existing tests.**

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q
cd .. && npm install && npm run typecheck --workspace frontend
```

Two OCR tests in `tests/test_verification.py` need `tesseract`. If it is not installed they fail on main too;
deselect them with `--deselect tests/test_verification.py::test_scanned_image_ocr --deselect tests/test_verification.py::test_scanned_page_image_is_collected_but_not_saved`.
Every other test must pass before you start and after every step.

**Rules that apply to every step.**

- The case *is* the ticket. Do not add a `cases` table.
- Do not change the 13 ticket statuses. Other code (queue, app, chat assistant) depends on them.
- Add fields to existing API responses; never remove or rename one.
- Customers must never see tasks, team members, staff phone numbers, override reasons or fee notes.
- Write every case action to the activity log (`tickets.add_event`) and the audit log (`tickets.audit`).
- New CSS uses only the tokens in `frontend/app/ui/tokens.css`, never hard-coded colours, so dark mode works.

---

## Phase 1

### Step 1. Add the models

**File:** `backend/app/models.py`

1. Add constants next to the other status tuples:

   ```python
   CASE_TASK_STATUSES = ("open", "done", "cancelled")
   CASE_TASK_SOURCES = ("manual", "playbook")
   CASE_MEMBER_ROLES = ("associate", "paralegal", "reviewer")
   CLOSURE_OUTCOMES = ("delivered", "withdrawn", "not_viable", "duplicate", "other")
   FEE_STATUSES = ("none", "quoted", "paid", "waived")
   ```

2. Add 11 columns to `ServiceRequest`, after `completed_at`:

   | Column | Type | Notes |
   | --- | --- | --- |
   | `first_response_due_at` | `DateTime(timezone=True)`, nullable | |
   | `first_response_at` | `DateTime(timezone=True)`, nullable | |
   | `closure_outcome` | `Text`, nullable | One of `CLOSURE_OUTCOMES` |
   | `closure_summary` | `Text`, nullable | Staff only |
   | `closed_at` | `DateTime(timezone=True)`, nullable | |
   | `fee_status` | `Text`, not null, default `"none"`, `server_default=text("'none'")` | One of `FEE_STATUSES` |
   | `fee_quote_paise` | `Integer`, nullable | Store money in paise |
   | `fee_paid_paise` | `Integer`, nullable | |
   | `fee_reference` | `Text`, nullable | UPI, UTR or receipt number |
   | `fee_paid_at` | `DateTime(timezone=True)`, nullable | |
   | `fee_note` | `Text`, nullable | Staff only |

   `due_at` already exists; it becomes the case due date.

3. Add to `ServiceRequest.__table_args__`:
   `Index("idx_requests_status_due", "status", "due_at")` and
   `CheckConstraint(_check_in("fee_status", FEE_STATUSES), name="ck_service_requests_fee_status")`.

4. Add two models before `TicketEvent`:

   - `CaseMember` (`case_members`): `id`, `service_request_id` (FK, cascade delete), `user_id` (FK users),
     `role`, `added_by_user_id` (FK, set null), `added_at`, `removed_at`. Check constraint on `role`.
     Partial index `idx_case_members_user_active` on `user_id` where `removed_at IS NULL`
     (pass both `postgresql_where` and `sqlite_where`). Relationship `user` (joined).
   - `CaseTask` (`case_tasks`): `id`, `service_request_id` (FK, cascade delete), `title`, `notes`,
     `assignee_user_id` (FK, set null), `due_at`, `status` (default `open`), `source` (default `manual`),
     `playbook_key`, `created_by_user_id`, `created_at`, `completed_by_user_id`, `completed_at`.
     Check constraints on `status` and `source`. Indexes `idx_case_tasks_request` and partial
     `idx_case_tasks_assignee_open` on `(assignee_user_id, due_at)` where `status = 'open'`.
     Relationships `assignee` (joined) and `service_request` (back_populates `tasks`, joined).

5. Add relationships on `ServiceRequest`:

   ```python
   tasks = relationship(back_populates="service_request", order_by="CaseTask.created_at", lazy="selectin", cascade="all, delete-orphan")
   members = relationship(order_by="CaseMember.added_at", lazy="selectin", cascade="all, delete-orphan")
   ```

**Check:** `python -m pytest -q` still passes (the test fixture builds tables from the models).

### Step 2. Write the migration

**File:** `backend/migrations/versions/0014_case_management.py`, with `revision = "0014_case_management"` and
`down_revision` set to the current head on main (`0013_more_property_types` when this guide was written;
run `alembic heads` to confirm).

- `upgrade()`: in `op.batch_alter_table("service_requests")`, add the 11 columns (with `server_default` on
  `fee_status`) and the check constraint; create the status/due index; create `case_members` and
  `case_tasks` with their constraints and indexes.
- `downgrade()`: drop in reverse order.

**Check against PostgreSQL**, not only SQLite:

```bash
export DATABASE_URL=postgresql+psycopg://USER@localhost:5432/scratch
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

Then compare the database with the models. This must print nothing:

```python
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine
from app.models import Base
import os
with create_engine(os.environ["DATABASE_URL"]).connect() as c:
    for d in compare_metadata(MigrationContext.configure(c), Base.metadata): print(d)
```

### Step 3. Add settings

**File:** `backend/app/config.py`

```python
CASE_FIRST_RESPONSE_HOURS = int(os.getenv("CASE_FIRST_RESPONSE_HOURS", "4"))
CASE_DEFAULT_TURNAROUND_DAYS = int(os.getenv("CASE_DEFAULT_TURNAROUND_DAYS", "7"))
```

### Step 4. Build the case logic module

**New file:** `backend/app/case_management.py`. It must not import `tickets` at module level (tickets imports
it); import `tickets` helpers inside functions where needed.

Write these parts, in this order.

**4a. Labels.** `OUTCOME_LABELS`, `MEMBER_ROLE_LABELS`, `FEE_LABELS`, and:

```python
MILESTONES = (
    ("received", "Request received"),
    ("scoped", "Scope and fee agreed"),
    ("assigned", "Lawyer assigned"),
    ("documents", "Documents verified"),
    ("signed", "Report signed"),
    ("closed", "Case closed"),
)
BOARD_COLUMNS = (  # the milestone each open case is working towards
    ("scoped", "Confirm scope and fee"),
    ("assigned", "Assign a lawyer"),
    ("documents", "Collect and verify documents"),
    ("signed", "Sign the report"),
    ("closed", "Ready to close"),
)
OPEN_STATUSES = tuple(s for s in TICKET_STATUSES if s not in CLOSED_STATUSES and s != "draft")
```

**4b. Milestones from facts.**

- `needs_documents(ticket)`: `ticket.report is not None or ticket.service_type.slug in document_requirements.SERVICES`.
- `milestone_state(ticket) -> dict[str, bool]`:
  - `received`: always `True`.
  - `scoped`: fee status is quoted, paid or waived; or status is one of `approved_for_processing`, `assigned`,
    `in_progress`, `quality_review`, `completed`; or any past `status_changed` event moved into one of those.
  - `assigned`: `ticket.active_assignment is not None`.
  - `documents`: report exists, is not `draft`, and `case_files.checklist_complete(report)`.
  - `signed`: report status is `signed`.
  - `closed`: status is `completed`.
- `milestones(ticket)`: the `MILESTONES` rows with `done`, dropping `documents` and `signed` when
  `needs_documents` is false; mark `current` on the first row that is not done.
- `current_milestone(ticket)`: key of the current row, or `"closed"` if all are done.

**4c. Allowed status moves.** `allowed_statuses(ticket) -> list[str]`:

| Current status | Returns |
| --- | --- |
| Closed (`completed`, `cancelled`, `rejected`) | `["reopened"]` |
| `on_hold` | every open status except `on_hold` and `reopened`, plus `cancelled` |
| Any other open status | every open status except itself and `reopened`, plus all three closed statuses |

**4d. Closure checks.** `closure_check(ticket) -> {"can_close", "blockers", "warnings"}`:

- Blocker if `fee_status == "quoted"`: "The fee of ₹X is not paid or waived."
- Blocker if a report exists and is not `signed`.
- Blocker if any meeting has status `scheduled`.
- Warning if any task is open: "N open tasks will be cancelled."
- `can_close` is true when there are no blockers.

**4e. Deadlines.**

- `set_deadlines(ticket)`: if `first_response_due_at` and `first_response_at` are both empty, set
  `first_response_due_at = submitted_at + CASE_FIRST_RESPONSE_HOURS`. If `due_at` is empty, set it to
  `submitted_at + service_type.estimated_turnaround_hours`, or `+ CASE_DEFAULT_TURNAROUND_DAYS` days.
- `deadlines(ticket, now)`: returns `due_at`, `overdue` (past due, not closed, not on hold),
  `first_response_due_at`, `first_response_at`, and `first_response_missed` (met late, or not met and past due
  while open). SQLite returns naive datetimes; treat them as UTC (`tickets.aware`).

**4f. Playbook.** A dict from key to `(title, reached(ticket, state), due_after, finished(ticket, state))`:

| Key | Title | Reached when | Due | Finished when |
| --- | --- | --- | --- | --- |
| `confirm-scope` | Call the customer to confirm scope and fee | always | the first-response deadline | `state["scoped"]` |
| `issue-report` | Issue the preliminary report and document checklist | `assigned` and `needs_documents` | 2 days | report exists and is not `draft` |
| `chase-documents` | Chase pending documents and government records | report exists and is not `draft` | 5 days | `state["documents"]` |
| `sign-report` | Print, sign and upload the final report | report is `final_generated` or `signed` | 2 days | `state["signed"]` |

`sync(ticket)`: return at once if the case is closed. For each key: if no task exists with that
`playbook_key`, create one only when it is reached and not already finished, assigned to the case owner. If an
open one exists and is finished, mark it `done`. If an open one exists and the owner changed, move it to the
new owner. Never re-create a playbook task that was done or cancelled.

**4g. The event hook.**

```python
FIRST_RESPONSE_EVENTS = ("status_changed", "message_sent", "assigned", "meeting_scheduled", "report_issued")

def note_event(ticket, event_type, actor):
    if actor is not None and ticket.first_response_at is None and event_type in FIRST_RESPONSE_EVENTS:
        ticket.first_response_at = utcnow()
    set_deadlines(ticket)
    sync(ticket)
```

**4h. Close and reopen.**

- `close_out(ticket, outcome, summary)`: set `closed_at`, `closure_outcome` (default: `delivered` for completed,
  `withdrawn` for cancelled, `not_viable` for rejected), `closure_summary`; cancel every open task; return the
  cancelled titles.
- `reopen(ticket)`: clear `closed_at`, `closure_outcome` and `closure_summary`.
- `active_members(ticket)`: members with no `removed_at`.

**4i. Views.**

- `task_view(task, now, with_case=False)`: id, title, notes, status, source, playbook_key, assignee
  `{id, name}`, due_at, `overdue`, created_at, completed_at; with `with_case`, add the ticket number, service,
  customer name, status and priority.
- `fee_view(ticket, staff)`: status, label, quote and paid in rupees, paid_at; staff also get reference and note.
- `staff_case_view(ticket)`: milestones, current_milestone, deadlines, owner, team (user, role, role_label),
  tasks (open first, by due date), open_tasks, overdue_tasks, fee, closure (only while open), closed
  (outcome, label, summary, at; only when closed), allowed_statuses, outcomes.
- `customer_progress(ticket)`: milestones, `next_step` (see below), due_at (while open), fee (if not `none`,
  without reference or note), closed (outcome label, summary, at).
  - `next_step`: none when closed. When `waiting_for_customer`: the document prompt if customer uploads are
    missing, else "Please reply to the case team's latest message." When the fee is quoted: "Pay the fee of ₹X
    to the case team." When the report is signed: "Your signed report is ready to download."
- `board_card(ticket, now)`: `tickets.staff_summary(ticket)` plus milestone, deadlines, open_tasks,
  overdue_tasks, fee_status and team names.

**Check:** `python -c "import app.case_management"` from `backend/` works.

### Step 5. Wire the hook and the views into tickets

**File:** `backend/app/tickets.py`

1. Import `case_management` with the other module imports.
2. At the end of `add_event`, after `ticket.events.append(event)`, call
   `case_management.note_event(ticket, event_type, actor)`. Every existing flow (create, assign, issue report,
   sign report, message) already calls `add_event` *after* it updates the ticket, so deadlines and playbook
   tasks follow without touching those flows.
3. In `customer_view`, add `"progress": case_management.customer_progress(ticket)`.
4. In `staff_detail`, add `"case": case_management.staff_case_view(ticket)`.

**File:** `backend/app/accounts.py`

1. In `_request_summary`, add `"progress": case_management.customer_progress(ticket)`.
2. In `_needs_you`, after the `waiting_for_customer` line, return `"Fee of ₹X to pay"` when the fee is quoted.

**Check:** run the full test suite. It must still pass: nothing so far blocks any existing flow. A new
ticket should now have a due date, a first-response deadline and one open `confirm-scope` task.

### Step 6. Enforce moves, closure and reopen on the staff API

**File:** `backend/app/admin.py`

1. Add to `TicketUpdate`: `outcome` (one of `CLOSURE_OUTCOMES`), `closure_summary` (≤2000),
   `override_reason` (≤500), `due_at` (datetime), `due_reason` (≤300).
2. Extend `_visible_tickets`: agents also see tickets where they are an active `CaseMember`.
3. Write `_move(db, ticket, payload, user)` and call it from `update_ticket` when the status changes:
   - Not in `allowed_statuses` → 409 ("A closed case can only be reopened." or "From X you can't move to Y.").
   - `reopened` without a note → 422.
   - `completed` with blockers: without `override_reason` → 409 listing the blockers; with one but the user is not
     an admin → 403.
   - Call `tickets.change_status`. If the new status is closed, call `close_out` and add a `case_closed` event
     with `{outcome, cancelled_tasks, override}` and the override reason or summary as the note. If the old
     status was closed, call `reopen` and `sync`.
   - Audit `ticket.status_changed`, including the override reason when used.
4. In `update_ticket`, handle `due_at`: require `due_reason` (422), store it as UTC, add a `due_date_changed`
   event with old and new dates, audit `case.due_changed`.

Internal callers of `tickets.change_status` (bookings, customer replies, unpaid holds) are not limited; only the
staff `PATCH` goes through `_move`.

**Check:** the existing test that closes a new ticket straight to Completed still passes, because a new ticket
with no report, fee or meeting has no blockers.

### Step 7. Add the case endpoints

**New file:** `backend/app/cases.py`, router prefix `/api/v1`, reusing `_detail`, `_get_ticket` and
`_visible_tickets` from `admin.py`. Register it in `main.py` right after `admin.router`. Every write endpoint
returns `_detail(db, ticket)` so the page re-renders from the server's answer.

| Endpoint | Rules |
| --- | --- |
| `POST /admin/tickets/{n}/tasks` | Case must be open (409). Assignee defaults to the case owner, else the caller. Assignee must be active staff (422). Event `task_added`. |
| `PATCH /admin/tickets/{n}/tasks/{id}` | Edit title, notes, due date, assignee; set status `done`, `cancelled` or `open` (sets or clears `completed_at`/`completed_by`). Events `task_done`, `task_cancelled`, `task_reopened`. |
| `GET /admin/tasks` | Open tasks on open cases. `assignee=me` (default), or `all` or a staff id for admins. Order by due date; overdue first. Uses `task_view(with_case=True)`. A task assignee can see their task here even if they cannot open the case. |
| `POST /admin/tickets/{n}/members` | Admin or case owner only (403). Can't add the owner (409). Re-adding with a new role ends the old row. Event `member_added`, audit `case.member_added`. |
| `DELETE /admin/tickets/{n}/members/{user_id}` | Admin or owner. Sets `removed_at`. Event `member_removed`. |
| `PUT /admin/tickets/{n}/fee` | `action`: `quote` (amount required; not if already paid; notify customer), `paid` (reference required; amount defaults to the quote; notify customer), `waive` (note required), `clear` (not if paid). Events `fee_quoted`, `fee_paid`, `fee_waived`, `fee_cleared`; audit `case.fee_<action>`. Amounts in rupees in, paise stored. |
| `GET /admin/cases/board` | Open visible cases, optional `assignee=me|unassigned|<id>`, cut at 500. Columns from `BOARD_COLUMNS` by `current_milestone`. Sort urgent first, then overdue, then due date. Counts: `open`, `overdue`, `due_this_week`, `first_response_missed` (not yet answered), `overdue_tasks`, `closed_30_days`. |

### Step 8. Write the backend tests

**New file:** `backend/tests/test_cases.py`. Cover at least:

1. A new case has six milestones, current `scoped`, a due date, a first-response deadline and one open
   `confirm-scope` task due at that deadline; the customer lookup has the same milestones and no tasks.
2. An `advocate-consultation` case has only four milestones.
3. Playbook: assigning ticks off `confirm-scope`, sets `first_response_at` and opens `issue-report` for the owner;
   issuing a report ticks off `issue-report` and opens `chase-documents`; Completed is then blocked (409) with a
   warning about open tasks.
4. Moves: cancel with an outcome and summary closes out and cancels tasks; only `reopened` is then allowed;
   reopening without a note is 422; with one it clears the close-out and the customer can reply again.
5. Fee: quote needs an amount; the customer sees the quote and a next step but no reference; Completed is
   blocked; an agent owner can't override (403); paying needs a reference; after paying, Completed works with
   outcome `delivered`.
6. An admin override close is logged on the `case_closed` event.
7. Tasks: an overdue task appears in the assignee's My tasks; finishing it removes it.
8. Team: a member can open the case; a member who is not the owner can't change the team (403); removing
   them takes access away again.
9. Moving the due date needs a reason; the board puts the overdue case first and counts it.
10. A missed first response shows on the board until a staff reply meets it (late).

**Check:** run the full suite on SQLite, then on PostgreSQL with `TEST_DATABASE_URL`. Both must pass.

### Step 9. Add the shared types

**File:** `packages/shared/src/index.ts`

```ts
export type CaseMilestone = { key: "received" | "scoped" | "assigned" | "documents" | "signed" | "closed"; label: string; done: boolean; current: boolean };
export type CaseProgress = {
  milestones: CaseMilestone[];
  next_step: string | null;
  due_at: string | null;
  fee: { status: "quoted" | "paid" | "waived"; status_label: string; quote: number | null; paid: number | null; paid_at: string | null } | null;
  closed: { outcome_label: string | null; summary: string | null; at: string | null } | null;
};
```

Add `progress?: CaseProgress` to `TicketStatus` and to `AccountRequest`. Optional, so the mobile app keeps
compiling.

**File:** `frontend/app/admin/api.ts`: add `CaseTask`, `CaseDeadlines`, `CaseFee`, `CaseView`, `BoardCard` and
`Board` types mirroring step 4i, add `case: CaseView` to `TicketDetail`, and add helpers `formatDay(iso)` and
`dueIn(iso)` ("in 3d", "2h late").

**Check:** `npm run typecheck --workspace frontend` and `--workspace packages/shared`.

### Step 10. Build the staff ticket page panels

**New file:** `frontend/app/admin/CasePanel.tsx`, exporting four components. Each takes the ticket and an
`act(path, method, body, doneMessage)` function from the page that calls the API and replaces the ticket with the
response.

- `CaseOverview`: milestone bar (done, current, to do), four fact tiles (case due with a Move form that asks for a
  reason; first response; fee; tasks), the closed note, and the closure blockers and warnings.
- `TasksCard`: open tasks with a tick box, assignee, due date and "routine" for playbook tasks; Cancel; an Add task
  form (title, assignee from owner, team and staff, due, notes); a toggle for finished tasks with Reopen.
- `TeamCard`: owner and members with role; for admins and the owner, Remove and an add form (person and role).
- `FeeCard`: status, quote, paid, reference, note; Quote, Record payment (amount and reference), Waive (reason).

**File:** `frontend/app/admin/tickets/[ticketNumber]/page.tsx`

1. Let `act` take `PUT` and `DELETE` and a `null` body.
2. Put `CaseOverview` and `TasksCard` at the top of the main column; put `TeamCard` and `FeeCard` in the side
   column under Assignment.
3. Rewrite the Status card: the stage list is the current status plus `case.allowed_statuses` (label closed ones
   "Close as …" and `reopened` "Reopen case"). When closing, ask for an outcome and a staff-only summary. When
   Completed is blocked, list the blockers and, for admins, an override reason field; the button reads "Close
   anyway". Reopening requires a note.
4. Add activity-log text for the new events: `case_closed`, `due_date_changed`, `task_*`, `member_*`, `fee_*`.

**New file:** `frontend/app/admin/cases.css`, imported in `frontend/app/admin/layout.tsx` after the admin view
CSS. Use only UI tokens. Don't reuse class names already used elsewhere (for example `.team-list` belongs to the
Team calls page; use `.case-team`).

### Step 11. Build the case board

**New file:** `frontend/app/admin/cases/page.tsx`

- Header with a whose-cases toggle: admins choose Everyone, Mine or Unassigned; agents choose "I own" or "I'm on".
- Six stat tiles from `counts`; overdue, late first reply and overdue tasks turn red when non-zero.
- A My tasks card from `GET /admin/tasks`, each with a tick box that marks it done and reloads.
- Five columns from `columns`. Each card links to the ticket and shows the customer, service, location, status,
  due flag, "No reply yet", task count with late count, "Fee due", "Customer replied", ticket number, owner and
  team size. Late cases get a red left border; urgent ones a red outline.

**File:** `frontend/app/admin/AdminShell.tsx`: add `{ href: "/admin/cases", label: "Case board" }` after Ticket
queue, with an existing icon name from `ui/Icon.tsx`.

On phones the columns scroll sideways inside their container. The page itself must not scroll sideways.

### Step 12. Show progress to customers

**New file:** `frontend/app/CaseProgress.tsx` with `case-progress.css`: a step bar from `progress.milestones`,
the next step in a highlighted line, and chips for target date and fee. A `compact` mode shows only small dots
and "Now: …". On narrow screens show only the current step's label.

- `frontend/app/TrackRequest.tsx`: render `<CaseProgress progress={ticket.progress} />` under the service line.
- `frontend/app/account/page.tsx`: use `progress` for each request's stage text ("status · step 3 of 6: Lawyer
  assigned") and its progress bar.

### Step 13. Verify end to end and document

1. Run the API on PostgreSQL after `alembic upgrade head`, run the website, and seed cases through the API:
   a new one, a quoted fee, one assigned with a report issued, team members and an overdue task, an overdue
   in-progress one, an urgent consultation, a waived-fee consultation, and a closed one.
2. Check in a browser at 1440 px and 390 px, light and dark: the board, a case page, closing a blocked case,
   closing a ready one, a closed case, the customer tracking card and the account page. On phones the page must
   not scroll sideways (`document.documentElement.scrollWidth` equals the viewport width).
3. Add `docs/case-management.md` (developer summary: parts, API, screens, what is not built) and a line in the
   README feature list.
4. Open one pull request for phase 1. Don't merge until the product owner has reviewed it.

---

## Phase 2

Build each item as its own pull request, with tests, after phase 1 is merged.

### 2a. Online payment of case fees

1. Reuse `backend/app/payments.py`. Today it collects booking fees from `structured_answers["fee"]`; add a
   `purpose` to `Payment` (`booking` or `case_fee`) in a new migration, defaulting existing rows to `booking`.
2. Add `POST /api/v1/tickets/fee/pay` (customer, by ticket number and contact, or account token) that creates a
   Razorpay order or link for `fee_quote_paise`, and the matching verify step.
3. When Razorpay confirms (signature, webhook or status check), set `fee_status = "paid"`, `fee_paid_paise`,
   `fee_paid_at`, `fee_reference` = the Razorpay payment id, and add a `fee_paid` event. This clears the
   closure blocker and the customer's next step.
4. Show a Pay button on the customer tracking card and account when the fee is quoted and payments are on.
5. Tests: pay in test mode; a second payment is marked for refund; staff can still record offline payments.

### 2b. WhatsApp alerts for tasks and late cases

1. Queue a staff `Notification` (channel `whatsapp`, `user_id` set) when a task is assigned to someone other than
   its creator, using the existing WhatsApp template flow in `whatsapp.py` and `notify.py`.
2. Add a daily job in the notification worker that sends each staff member their overdue tasks and late cases,
   with a `dedupe_key` per person per day.
3. Register the new WhatsApp templates and document them in `docs/meetings.md` next to the existing ones.

### 2c. Case screens in the mobile app

1. Show `progress` on the app's request screen with a native step bar (`mobile/`), using the shared types.
2. Verify with `npx expo export --platform android`.

---

## Phase 3

### 3a. Deadlines that pause

Add `paused_at` and `paused_seconds` to `service_requests`. When a case moves into `on_hold` or
`waiting_for_customer`, set `paused_at`; when it leaves, add the paused time to `paused_seconds` and push `due_at`
out by the same amount. `deadlines()` treats a paused case as not overdue.

### 3b. Working-hours calendar

Add `CASE_WORKING_HOURS` (for example `Mon-Sat 09:00-19:00`) and `CASE_HOLIDAYS` settings. Write
`add_working_hours(start, hours)` and use it for the first-response deadline and playbook due dates. Test across a
weekend and a holiday.

### 3c. Workload balancing

On the Assignment card, show each lawyer's open cases and overdue tasks next to their name, and suggest the
least-loaded lawyer who handles the service. Use the board query, grouped by owner.

### 3d. Time-to-close reports

Add `GET /admin/reports/cases`: median and 90th-percentile days from `submitted_at` to `closed_at`, by service and
by month, with counts by outcome. Add a reports page with a chart per service.

---

## Done when

- Every step's check passes, on SQLite and PostgreSQL.
- Customer responses contain no task, team, override or fee-note fields.
- The board, case page and customer views work at 390 px and 1440 px, in light and dark.
- `docs/case-management.md` and the README describe what was built.
