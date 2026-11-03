# Case deadline pauses and escalation alerts

Staff can place a case **On hold** with a customer-visible reason. The case target and any outstanding first-response target pause until the case leaves On hold. The staff case overview and case board show **Paused** rather than an overdue countdown; customer tracking hides the old target date and explains that the target is paused.

On resume, elapsed hold time is added once to the target dates, and the pause duration is recorded. If the case was already late before the hold, it remains equally late when resumed. Repeated updates to the same status do not add time again. Closing a held case ends the pause and preserves clock history; closed cases generate no active alerts. Reopening retains the recorded target, which staff can move with a reason if needed.

First-response policy is unchanged: customer-visible staff messages, status changes, assignments, meeting bookings and report issue count as a response. A staff hold with its required note therefore counts as a response. If a system puts a case on hold before any response, a staff response during that hold receives only the pause elapsed up to that response. Internal notes and alert acknowledgements do not count. A recorded late response remains historically late.

Targets use elapsed UTC time, not a business-hours or holiday calendar. Open task due dates are managed separately and are not shifted by the case-target pause. Resume/reopen a case before manually moving its target. Status, first-response and deadline changes use case-row locks to prevent duplicate extensions or overwritten response clocks across workers.

## Staff alerts

**Deadline alerts** in the staff navigation (`/admin/alerts`) lists active missed case targets and first responses, with the case owner and target time. The staff notification indicator includes unacknowledged alerts and links to this page. The page supports refresh, pagination and inclusion of acknowledged alerts.

- At the first missed target, an incident is recorded and a staff email is queued for the active owner. Unassigned cases, or cases whose owner no longer has active staff access, go to active administrators.
- After `CASE_ESCALATION_HOURS` (24 by default) beyond the target, the incident is escalated to the owner and active admins/super admins. This clears any earlier acknowledgement so the escalation needs review. If the first scan is already beyond escalation time, only escalation emails are queued.
- An acknowledgement records who saw the alert and cancels unclaimed queued emails for it. It does not fulfill a first response, change a due date, resolve the overdue case, or suppress a later escalation.
- One incident exists per case, target type and target timestamp. Worker restarts and concurrent scans reuse it. At most one email is queued per incident, recipient and phase (initial/escalated). Reusing exactly the same target reuses its incident/history; a changed target can produce a new incident.
- Staff only see and acknowledge alerts on cases they can currently open. Admins see all; agents see their owned/shared/meeting cases under the existing permissions. Customer tokens cannot access the alert APIs, and internal escalation details are not added to customer views.
- Held/closed cases, completed first responses and changed target dates are excluded from active lists immediately. The monitor records resolution and cancels unclaimed emails at its next check. Both before claiming and just before provider delivery, the worker verifies that the incident, target, phase, staff account, recipient email and case ownership still apply. An email already being sent can still arrive after a case changes; its delivery result remains recorded.

Email contains the target type, a case reference and a staff sign-in link, without customer names, locations, document contents or legal details. It uses the existing Resend provider, retry handling and idempotency keys. Missing credentials leave email queued; in-app alerts work without email credentials. Existing maximum age/attempt rules also apply to alert emails. SMS/WhatsApp deadline alerts are not implemented in this release.

## Deployment

1. Run `alembic upgrade head` in `backend/`. Migration `0020_case_deadline_alerts` adds clock metadata, the incident table and a notification link/index. Existing holds begin pausing at migration time; historical hold durations are not guessed. Existing accounts, tickets and notification history are preserved.
2. Keep the existing notification worker running: the API starts it when `NOTIFY_WORKER_ENABLED=true`, or run `python -m app.notify --loop` as a separate worker with that API setting disabled. Every run scans case targets before delivering due notifications. The default interval is `NOTIFY_INTERVAL_SECONDS=60`; staff screens refresh counts every 30 seconds. For a monitor-only run, use `python -m app.sla_alerts` (records incidents and queues email, without delivering it).
3. Configure `CASE_FIRST_RESPONSE_HOURS` (4), `CASE_DEFAULT_TURNAROUND_DAYS` (7, when the service has no specific turnaround), and `CASE_ESCALATION_HOURS` (24, minimum 1). Compose forwards these settings. Existing first-response/target values are preserved when defaults change; explicit target edits require a reason.
4. Configure the existing Resend credentials and verified sender to enable staff email, and set `PUBLIC_SITE_URL` to the trusted HTTPS website address. No new provider, application dependency or secret is required. Test only with synthetic cases and a mocked email transport until live delivery is intended.

## API and verification

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/admin/case-alerts` | Active visible incidents; `include_acknowledged`, `page`, `page_size` (max 100); includes pending/escalated counts |
| POST | `/api/v1/admin/case-alerts/{id}/acknowledge` | Acknowledge an active authorized incident; idempotent while active |
| PATCH | `/api/v1/admin/tickets/{ticket}` | Existing status/due endpoint; On hold needs a note; target edits are rejected on held/closed cases |

Paused metadata is returned in staff `case.deadlines`; customers receive only `progress.deadline_paused` and a hidden target while held. Incidents, escalation, acknowledgement and resolution are audited without case contents. Pause transitions also appear in case history.

Run the backend suite, workspace type checks, production build/lint and desktop/mobile browser checks. `tests/test_deadline_alerts.py` covers pause arithmetic, lateness preservation, first responses during holds, incident/phase deduplication, escalation, authorization, acknowledgement, stale delivery and safe email content. PostgreSQL tests verify concurrent monitor runs and concurrent resumes. Provider calls are mocked; these checks never send live email.
