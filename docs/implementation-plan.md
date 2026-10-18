# Implementation plan

## Phase 0 — Repository and foundation
- [x] Create responsive public homepage starter
- [x] Add FastAPI starter and health endpoint
- [x] Add PostgreSQL schema draft
- [x] Add Docker Compose and GitHub CI
- [ ] Configure development/staging/production environments
- [ ] Add Alembic migrations and DB-backed repositories

## Phase 1 — Service catalogue and intake
- [ ] Store services and dynamic intake forms in PostgreSQL
- [ ] Build guided chat state machine per service
- [ ] Add save/resume and request summary review
- [ ] Add consent capture and privacy notice version
- [ ] Create tickets transactionally with unique numbers
- [ ] Add verified customer contact flow

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
- [ ] Privacy notice, terms and grievance/contact details
- [ ] Backup/restore test and monitoring
- [ ] Accessibility and mobile QA
- [ ] Load tests, incident runbook and support process
- [ ] Pilot with limited service types and locations
