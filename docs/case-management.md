# Case management

Every ticket (`service_requests`) is managed as a case from request to close. The full requirements and design
are in the project's "Case management: requirements and design" doc; this page is the developer summary.

## What a case has

| Part | Where |
| --- | --- |
| Six milestones (Request received, Scope and fee agreed, Lawyer assigned, Documents verified, Report signed, Case closed), computed from facts on the case | `case_management.milestones` |
| Allowed status moves; a closed case can only be reopened, with a reason | `case_management.allowed_statuses`, `admin._move` |
| Closure checks before Completed: unpaid quoted fee, unsigned report, scheduled meeting (blockers); open tasks (warning, cancelled on close). Admins can override with a logged reason | `case_management.closure_check` |
| Close-out: outcome (delivered, withdrawn, not viable, duplicate, other), summary, closed time | `service_requests.closure_*`, `closed_at` |
| Tasks, manual and playbook (confirm scope, issue report, chase documents, sign report) that are added and ticked off as the case moves | `case_tasks`, `case_management.PLAYBOOK`, `sync` |
| Case team: owner (the assignment) plus associates, paralegals and reviewers, who can open the case | `case_members`, `admin._visible_tickets` |
| Deadlines: first response (`CASE_FIRST_RESPONSE_HOURS`, default 4) and case due date (service turnaround, else `CASE_DEFAULT_TURNAROUND_DAYS`, default 7) | `service_requests.first_response_*`, `due_at` |
| Case fee: quote, record an offline payment with a reference, or waive | `service_requests.fee_*`, `PUT /admin/tickets/{n}/fee` |

`tickets.add_event` calls `case_management.note_event` for every event, so first response, deadlines and playbook
tasks stay current without each endpoint having to remember.

## API

| Endpoint | Does |
| --- | --- |
| `GET /api/v1/admin/tickets/{n}` | Adds `case`: milestones, deadlines, owner, team, tasks, fee, closure check, allowed statuses |
| `PATCH /api/v1/admin/tickets/{n}` | Enforces moves; takes `outcome`, `closure_summary`, `override_reason`, `due_at` + `due_reason` |
| `POST /api/v1/admin/tickets/{n}/tasks`, `PATCH .../tasks/{id}` | Add, edit, finish, cancel or reopen tasks |
| `POST /api/v1/admin/tickets/{n}/members`, `DELETE .../members/{user_id}` | Case team (admin or owner) |
| `PUT /api/v1/admin/tickets/{n}/fee` | `action`: quote, paid, waive, clear |
| `GET /api/v1/admin/cases/board` | Open cases by milestone column, with counts |
| `GET /api/v1/admin/tasks` | Open tasks for me (admins: `assignee=all` or a staff id) |
| Customer lookup and account | `progress`: milestones, next step, due date, fee (no tasks or team) |

## Screens

- `/admin/cases`: case board with counts, My tasks and milestone columns.
- Ticket page: Case progress panel, Tasks, Case team, Case fee, and close or reopen in the Status card.
- Customer tracking card and account requests: step bar, next step, target date and fee.

## Not yet

Online payment of case fees, WhatsApp alerts for tasks and overdue cases, case screens in the mobile app, and
deadlines that pause while on hold.
