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
- [ ] Store services and dynamic intake forms in PostgreSQL
- [x] Build guided chat state machine per service
- [x] Add save/resume and request summary review
- [x] Add consent capture and privacy notice version
- [x] Create tickets transactionally with unique numbers
- [x] Add verified customer contact flow

## Phase 2 — Admin and agent workspaces
- [ ] Authentication and role-based access control
- [ ] Ticket queue, search, filters and pagination
- [ ] Ticket details, assignment, status workflow and SLA
- [ ] Internal notes vs customer-visible messages
- [ ] Agent's assigned work queue and checklist
- [ ] Append-only audit history

## Phase 3 — Documents and communications
- [ ] Private object storage and presigned uploads
- [ ] MIME sniffing, size limits and malware scanning
- [ ] Secure download links and retention policy
- [ ] Email/SMS/WhatsApp provider adapters
- [ ] Notification templates, consent and retry handling

## Phase 4 — AI assistance
- [ ] Add provider abstraction and secrets management
- [ ] Define service-specific prompts and structured output schemas
- [ ] Keep server-side validation as the authority
- [ ] Add safety filters, prompt-injection protections and human handoff
- [ ] Measure answer quality and monitor cost/latency
- [ ] Never let the model autonomously declare a property legally safe

## Phase 5 — Launch readiness
- [ ] Security review and dependency scanning
  Automated dependency audits, Python source scans, hashed dependency locks and API/web regressions are implemented (`dependency-security.md`). Configure required GitHub checks, resolve remaining moderate npm findings and complete broader manual security review.
- [ ] Privacy notice, terms and grievance/contact details
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
