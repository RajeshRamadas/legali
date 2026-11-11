# Implementation plan

## Phase 0 — Repository and foundation
- [x] Create responsive public homepage starter
- [x] Add FastAPI starter and health endpoint
- [x] Add PostgreSQL schema draft
- [x] Add Docker Compose and GitHub CI
- [ ] Configure development/staging/production environments
  Separate deployed environment templates, offline preflight/startup guards and rendered Compose profile checks are implemented (`deployment-readiness.md`). Provision real secrets, HTTPS/network boundaries and external services; verify delivery, recovery and deployment ownership before launch.
- [ ] Add Alembic migrations and DB-backed repositories

## Phase 1 — Service catalogue and intake
- [x] Restore reviewed intake-form versions without rewriting saved requests
  Retained publication/preceding snapshots can be reviewed and republished as a new version with administrator reasons and source provenance (`intake-form-restoration.md`). Stale edits and mismatched previews are rejected; existing customer snapshots and unpublished administrator drafts are preserved.
- [ ] Store services and dynamic intake forms in PostgreSQL
  Public choices, admission controls, description overrides and supplemental guided-question definitions now persist in PostgreSQL (`service-availability.md`, `service-descriptions.md`, `service-intake-forms.md`). Core conditional questions, catalogue identities and default copy remain code-managed.
- [x] Configure reviewed service-specific guided questions with pinned draft versions
  A bounded form editor, strict answer validation, private publication history and legacy-consent preservation are implemented (`service-intake-forms.md`). New service selections capture current questions; saved and submitted requests retain the original definitions and labels.
- [x] Publish reviewed service descriptions to a live customer catalogue
  Administrator preview/publication, independent editing revisions, private history and guarded standard restoration are implemented (`service-descriptions.md`). The public services page supports search/category filters and current availability; editorial marketing sections remain separate.
- [x] Build guided chat state machine per service
- [x] Add save/resume and request summary review
- [x] Add consent capture and privacy notice version
- [x] Create tickets transactionally with unique numbers
- [x] Add verified customer contact flow

## Phase 2 — Admin and agent workspaces
- [x] Review retained platform activity with administrator-only filters
  A private read-only activity index supports group, current staff-name, India-day and record-reference filters with cursor paging and draft-safe refresh (`activity-history.md`). It excludes audit payloads and unknown action text. Database guards and task-change coverage are implemented separately (`append-only-audit.md`); broader event coverage remains future work.
- [x] Review submitted customer intake with original wording and case-scoped access
  Searchable read-only question/answer snapshots, retained service labels, notice metadata and explicit legacy/missing-data handling are implemented (`submitted-intake-review.md`). Existing case permissions apply; current intake changes do not rewrite original submissions.
- [ ] Authentication and role-based access control
- [ ] Ticket queue, search, filters and pagination
- [ ] Ticket details, assignment, status workflow and SLA
- [ ] Internal notes vs customer-visible messages
- [x] Agent's assigned work queue and checklist
  A dedicated task queue adds explicit search/filters, due-date ordering, matching counts and paging, with links to existing case checklists (`staff-task-queue.md`). Both task lists enforce current case permissions; task assignment alone does not grant access.
- [x] Append-only audit history
  PostgreSQL/SQLite guards preserve `audit_logs` against data rewrites and deletion, including PostgreSQL truncation and SQLite replacement (`append-only-audit.md`). Readiness and administrator health inspect actual guard configuration. Manual task writes append safe audit events atomically; schema owners and broader timeline/event coverage remain outside this protection boundary.

## Phase 3 — Documents and communications
- [ ] Private object storage and presigned uploads
- [ ] MIME sniffing, size limits and malware scanning
- [ ] Secure download links and retention policy
- [ ] Email/SMS/WhatsApp provider adapters
- [ ] Notification templates, consent and retry handling

## Phase 4 — AI assistance
- [x] Give customers control over external document AI per case
  Verified customer grants/withdrawals, processor-bound notices, strict revision checks, retained audit and guarded upload/full-case processing are implemented (`case-ai-consent.md`). Existing cases receive no inferred grant. Review public processor identity/policy settings and deploy API/workers together before use; historical data is not replayed automatically.
- [x] Process full-case verification through durable background jobs
  Case-scoped submission/status/cancellation, detached processing, leased PostgreSQL claims, stale/access/configuration checks, explicit retries and worker health are implemented (`background-verification.md`). Start the optional worker with shared configuration after reviewing queued work. Upload classification/rechecks retain their existing flow; broader evaluation and retention controls remain further work.
- [x] Monitor background verification provider usage, latency and estimated cost
  Private administrator filters, grouped case-job summaries, durable attempt outcomes and configurable USD rate snapshots are implemented (`verification-usage.md`). Estimates distinguish missing/cached usage and unfinished outcomes; they are not invoices. Review actual prices before configuring rates. Other AI workflows, spending caps, billing reconciliation and quality evaluation remain separate work.
- [ ] Add provider abstraction and secrets management
- [ ] Define service-specific prompts and structured output schemas
- [ ] Keep server-side validation as the authority
- [ ] Add safety filters, prompt-injection protections and human handoff
- [ ] Measure answer quality and monitor cost/latency
  Background verification usage/latency and optional estimates are implemented as above. A versioned synthetic text benchmark adds shared screening, offline CI gating and explicitly requested provider evaluation (`verification-evaluation.md`). No live benchmark was run during implementation; reviewed historical outcomes, broader workflow/language/OCR coverage and production quality measurement remain pending.
- [x] Gate verification screening with a synthetic quality benchmark
  Twelve curated cases cover correct facts, mismatches, current/historical mortgages, incomplete evidence, prompt injection, quote/state-law grounding and provider/schema failures. Reports retain hashes and metrics without source content; replay scores validate regression behavior, not live model accuracy (`verification-evaluation.md`).
- [ ] Never let the model autonomously declare a property legally safe

## Phase 5 — Launch readiness
- [x] Prioritize pending support responses before targets are missed
  Administrator response-target filters, earliest-target ordering, checked-at timestamps and draft-safe queue refresh are implemented (`support-queue-priority.md`). Monitor both overdue and upcoming work; targets are operational and require an accountable team.
- [x] Inspect support notification delivery without exposing private payloads
  Administrator-only filtered history, safe reason labels, current configuration and draft-safe refresh are implemented (`support-delivery-history.md`). Review uncertain outcomes before arranging another message; the view does not resend or enable delivery.
- [x] Email eligible administrators about current missed support targets
  Owner/fallback routing, escalation, current-role/address checks and pending-notice cancellation are implemented (`support-deadline-email.md`). Review recipients/backlog, configure email and enable consistently; verify delivery and keep in-app monitoring active.
- [x] Notify customers of unread support replies without copying private content
  Account-scoped transactional notices, preference/recipient checks, coalescing, read cancellation and guarded rollout are implemented (`support-reply-notifications.md`). Configure providers/templates and enable consistently after reviewing delivery policy; external staff routing remains operational work.
- [x] Surface missed support response targets with private acknowledgement and escalation
  Persistent incidents, administrator bell/navigation counts, direct conversation links, current-state checks and operations health are implemented (`support-deadline-alerts.md`). Keep monitoring running and complete external alert routing and operational review before launch.
- [x] Assign accountable support owners and surface unassigned work
  Private administrator ownership, filtered queues, assignment history and conflict-safe draft preservation are implemented (`support-ownership.md`). Operators must monitor unassigned and unavailable-owner work; assignment does not send external alerts.
- [x] Surface unread support replies without exposing private team notes
  Account/list/bell badges, explicit read acknowledgements, draft preservation and loaded-reply concurrency protection are implemented (`support-unread-replies.md`). External support delivery alerts remain outside this in-app feature.
- [x] Respect lawyer time off across online bookings and staff scheduling
  Private confirmed periods, cancellation history, shared admission locks and rollback protection are implemented (`lawyer-time-off.md`). Staff must resolve conflicting existing meetings and review their calendar before adding time off.
- [x] Add administrator service admission controls for a limited pilot
  Confirmed pause/resume decisions, private history, shared request-admission locks and customer availability messaging are implemented (`service-availability.md`). Existing cases/bookings continue; deployment capacity and pilot scope still require operational review.
- [x] Give verified customers control over automated notification channels
  Email/SMS/WhatsApp choices, queued-alert cancellation, worker checks, private audit and rollback protection are implemented (`notification-preferences.md`). Requested sign-in codes remain available; cancelled alerts are never replayed.
- [x] Give verified customers control over withdrawal of consultation reviews
  The private My reviews centre, confirmed/idempotent withdrawal, moderator restrictions and rollback protection are implemented (`customer-reviews.md`). Retained-record deletion continues through the privacy workflow.
- [x] Moderate consultation feedback before public display and rating aggregation
  Administrator publication decisions, private history, conflict protection and customer publication status are implemented (`review-moderation.md`). Review the publication policy and existing pending feedback before launch.
- [x] Track partial, pending and processed booking refunds with an administrator queue
  Signed provider events, exact paise totals, unmatched-event retention and private follow-up notes are implemented (`refund-tracking.md`). Refund initiation remains in the provider dashboard; reconcile historical review flags before relying on past totals.
- [ ] Security review and dependency scanning
  Automated dependency audits, Python source scans, hashed dependency locks and API/web regressions are implemented (`dependency-security.md`). Configure required GitHub checks, resolve remaining moderate npm findings and complete broader manual security review.
- [ ] Privacy notice, terms and grievance/contact details
  A public policy centre with private administrator drafts, reviewed publication, immutable version snapshots and withdrawal is implemented (`public-policies.md`). Supply legally reviewed wording and accountable organization contacts, publish them and assign maintenance ownership before launch.
- [ ] Backup/restore test and monitoring
  Encrypted database/document backup, verification, empty-target recovery and freshness/retention commands are implemented (`backups.md`). Deployment scheduling, off-host copies, recovery drills and broader monitoring still need configuration.
  Administrator system health, database readiness and request/worker logs are implemented (`operations-monitoring.md`); connect an external collector and configure/test alert routing.
- [ ] Accessibility and mobile QA
  Shared skip links, main landmarks, modal focus handling and keyboard/mobile browser regressions with axe are implemented (`accessibility.md`). Complete manual screen-reader, real-device and cross-browser review before launch.
- [x] Add bounded API load smoke checks and incident/support runbooks
  Isolated PostgreSQL workloads, latency/error gates and CI reports are implemented (`performance-checks.md`), alongside the incident runbook (`incident-response.md`) and verified support workflow (`customer-support.md`).
- [ ] Run deployment capacity/soak tests and an incident-response drill
  Assign operational/support owners, configure and test external alert routing, agree deployment SLOs and exercise recovery before launch.
- [ ] Pilot with limited service types and locations
