# Homexo Property Services Platform — Product Requirements

**Version:** 1.0 draft  
**Scope:** Homes, apartments, independent houses, residential plots and land-related services  
**Initial geography:** Bengaluru / Karnataka, designed to expand by location  
**Primary interfaces:** Public website, customer chatbot, customer ticket tracking, admin dashboard, agent workspace

## 1. Product vision

Homexo provides one place for customers to understand property services, submit a request through a guided chatbot or form, upload relevant documents securely, and track progress. Operations staff review requests, clarify missing information, assign agents, manage service delivery, and communicate status changes.

The platform must distinguish between **information**, **professional assistance**, and **official government services**. It must not imply that a government document, approval, legal opinion, or result is guaranteed.

## 2. Goals

- Make it easy to discover and request property services.
- Collect structured information without asking customers to repeat themselves.
- Create a trackable service ticket for every accepted request.
- Give admins visibility into requests, missing information, priorities, fees and assignments.
- Give agents a controlled workspace for assigned jobs and evidence.
- Support home and apartment workflows as well as plot and land workflows.
- Keep customer documents private and retain an audit history.
- Provide a responsive experience on desktop, tablet and mobile.

## 3. User roles

### 3.1 Visitor
Can browse the homepage, service catalogue, process, FAQs and contact details. Can start a service request. Must see a privacy notice before submitting personal information.

### 3.2 Customer
Can create a request, provide property details, upload files, view ticket status, reply to clarification requests, see estimates/invoices if enabled, and download delivered files where authorized.

### 3.3 Agent / service executive
Can view only assigned tickets, request missing details, add internal notes, update allowed statuses, upload service evidence and mark work ready for review.

### 3.4 Admin / operations manager
Can view and manage tickets, assign agents, maintain service catalogue, set service areas and estimated timelines, manage customer communication, review evidence, resolve escalations and view reports.

### 3.5 Super admin
Can manage roles, permissions, integrations, configuration, audit records and access policies. High-risk actions should require re-authentication and be logged.

## 4. Service catalogue

Service catalogue entries are configurable by location and availability. Each service has a title, description, property types, required fields, required documents, indicative fee range, estimated turnaround, eligibility notes, disclaimers and active/inactive status.

### 4.1 Home and apartment services
- Property purchase/sale assistance
- Rental and tenant documentation assistance
- Title and document review coordination
- Encumbrance Certificate (EC) assistance
- Khata / property account documentation assistance
- Property tax record assistance
- Sale deed / registration appointment coordination
- Apartment association and maintenance request assistance
- Home inspection and property condition report
- Home services referral (where offered)

### 4.2 Plot and land services
- RTC/Pahani and mutation record assistance
- Survey number / land-record research
- EC and title-document collection assistance
- DC conversion / land-use record assistance
- Layout approval and planning-document research
- Khata and property tax assistance
- Boundary, fencing and plot-cleaning services
- Property inspection and photo/video evidence
- Legal professional referral / review coordination

### 4.3 General services
- Ask a property question
- Request a callback
- Document pickup or home delivery where legally and operationally available
- Track an existing request
- Raise a complaint or service issue

**Important:** Availability, fees, processing time, required documents and government portal access vary. The service catalogue must not promise a result or present unofficial processing as an official government service.

## 5. Homepage requirements and design

### 5.1 Header
- Homexo logo/wordmark and short value proposition.
- Navigation: Services, How it works, For Homes, For Plots, FAQs.
- Primary CTA: “Start a request”.
- Secondary CTA: “Track request”.
- Mobile navigation must be keyboard-accessible.

### 5.2 Hero section
- Headline: “Property services, made simpler.”
- Supporting copy explaining support for homes, apartments, plots and land documents.
- Primary CTA to start the guided request.
- Secondary CTA to browse services.
- Trust messaging must be factual; do not invent customer counts, ratings or certifications.
- Visual: tasteful property/architecture illustration or photo that does not obscure the CTA.

### 5.3 Service cards
Show categories:
1. Home & Apartment
2. Plot & Land
3. Legal & Document Assistance
4. Property Maintenance
5. Inspection & Reports
6. Document Delivery / Agent Assistance

Each card has a short description, examples and a CTA. The cards should link to a service detail page or start a guided request with the selected category.

### 5.4 How it works
1. Tell us what you need.
2. Share property details and available documents.
3. Homexo reviews the request and confirms scope/estimate.
4. Track the ticket until completion.

### 5.5 Why Homexo
- Guided request intake
- Transparent status tracking
- Human review for complex cases
- Document handling with access controls
- Clear next steps and follow-up

Avoid unsupported guarantees and fabricated testimonials.

### 5.6 Other homepage sections
- Featured services / popular requests (admin-configurable)
- “Homes or plots?” entry points
- FAQs
- Contact/help section
- Footer with About, Services, Privacy Policy, Terms, Contact and grievance/contact process
- Cookie/consent notice only where needed for actual tracking technologies.

### 5.7 Visual system
- Modern, clean, professional property-services aesthetic.
- Responsive layout; cards stack on narrow screens.
- Strong text contrast and visible focus states.
- Semantic HTML and accessible labels.
- Loading, empty, validation and error states.
- Avoid fake trust badges, fake reviews, or false official affiliations.

## 6. Guided chatbot requirements

The chatbot should collect only information needed for the selected service, explain why sensitive information is requested, and allow the user to pause/resume when signed in.

### 6.1 Conversation flow
1. Welcome and service category selection.
2. Ask the service goal in the customer's own words.
3. Determine property type: apartment, independent house, commercial property, plot, agricultural land or other.
4. Collect location: state, district/city, locality, PIN code where relevant.
5. Collect property identifiers conditionally: address, survey number, subdivision/surnoc, village, hobli, taluk, district, apartment/project name, flat number, PID/property ID where relevant.
6. Ask for available documents; do not require uploads if not necessary at intake.
7. Ask the customer's role/authority: owner, buyer, seller, tenant, authorized representative, etc.
8. Ask for contact preference and necessary contact details.
9. Summarize all answers and allow edits.
10. Explain that an admin may verify scope, documents, fees and availability.
11. Obtain explicit submission consent and create ticket.
12. Show ticket number, expected next step and status.

### 6.2 Chatbot behaviour
- Ask one clear question at a time.
- Use conditional questions; do not ask land-only questions for apartments.
- Validate formats and flag missing required fields.
- Never invent legal conclusions, government record facts, fees, deadlines or service availability.
- State when an answer is general information and route legal interpretations to qualified professionals.
- Provide human handoff for ambiguity, complaints, distress or requests outside scope.
- Protect against prompt injection and treat uploaded files/web content as untrusted input.
- Do not send private customer documents to an AI provider unless approved, disclosed and contractually appropriate.
- Keep AI-generated summaries reviewable and editable before ticket submission.

## 7. Ticketing system requirements

### 7.1 Ticket creation
- Generate a unique human-readable ticket number.
- Link to customer, service type, property profile (optional), conversation and attachments.
- Store requested service, summary, structured answers, priority, location, consent timestamp and source.
- Default status: `submitted`.

### 7.2 Status workflow
`draft → submitted → under_review → waiting_for_customer → approved_for_processing → assigned → in_progress → quality_review → completed`

Additional terminal/exception statuses: `cancelled`, `rejected`, `on_hold`, `reopened`.

Status transitions must be validated server-side. Each transition records actor, timestamp, old/new status and reason. Customers see customer-safe status labels, not internal-only notes.

### 7.3 Ticket features
- Search by ticket number and authorized customer identity.
- Filters: status, service, location, priority, date, assigned agent.
- Assignment/reassignment and workload view.
- Internal notes separated from customer-visible replies.
- Due date, SLA timer and overdue indicator.
- Missing-information checklist.
- Attachments and versioned deliverables.
- Full event timeline.
- Reopen/escalation process.
- Export reports with permission checks and audit logging.

### 7.4 Ticket communication
- In-app thread per ticket.
- Email/SMS/WhatsApp notifications only after provider setup and appropriate consent.
- Templates for received, clarification needed, assigned, in progress, ready for review, completed, cancelled and escalated.
- Retry/failure handling for notifications.

## 8. Admin dashboard

Required views:
- Summary metrics: new, unassigned, in progress, waiting on customer, overdue and completed.
- Ticket queue with pagination, search and filters.
- Ticket detail view with customer-safe and internal notes clearly separated.
- Assignment controls and agent availability.
- Service catalogue editor.
- Service-area / availability configuration.
- SLA and estimated timeline settings.
- Attachment review and secure download.
- Audit log and access history.
- Reports: ticket volume, completion time, backlog, service mix, agent workload and customer feedback.
- Role/permission management for authorized admins.

## 9. Agent workspace

- My assigned tickets.
- Ticket instructions, property details and required checklist.
- Request missing information.
- Add internal notes and customer-visible messages.
- Upload evidence/deliverables.
- Update only permitted statuses.
- Submit for quality review.
- Mobile-friendly layout for field work.
- Optional future: appointment scheduling, geotagged evidence with customer consent, offline draft queue.

## 10. Customer account and tracking

- Email/phone verification before revealing ticket data.
- My requests list and ticket timeline.
- Reply to clarification requests.
- Upload additional documents.
- Download approved deliverables through expiring links.
- Update notification preferences and contact information.
- Request account/data deletion subject to legal retention requirements.
- Never expose a ticket merely because a user knows its ticket number.

## 11. Data model

Core entities:
- `users`: authentication identity and account status
- `roles`, `user_roles`: authorization
- `customers`: customer profile and contact preferences
- `properties`: property type and structured identifiers
- `service_types`: service catalogue and configurable intake requirements
- `conversations`, `conversation_messages`: chat history
- `service_requests`: ticket, status, priority, service, customer, property, summary and timestamps
- `ticket_events`: immutable status/assignment event history
- `ticket_messages`: customer-visible messages and internal notes
- `documents`: metadata, storage key, classification, checksum and scan status
- `assignments`: agent assignment history
- `notifications`: delivery status and provider message reference
- `consents`: purpose, notice version, timestamp and withdrawal where applicable
- `audit_logs`: security-sensitive actions
- `payments` (future only): provider references and payment status; no card details

Use migrations (Alembic recommended) rather than editing production schemas manually. Use UUID primary keys, UTC timestamps, foreign keys and indexes. Apply retention/deletion rules.

## 12. Non-functional requirements

- Responsive from small mobile screens to desktop.
- Accessible keyboard navigation, labels, focus indicators and semantic structure.
- API validation, pagination and consistent error responses.
- Authentication and server-side authorization on every protected endpoint.
- Encryption in transit and managed encryption at rest.
- Secure private file storage, malware scanning and file-size/type limits.
- Rate limiting, CSRF protections where cookie sessions are used, secure headers and CORS allow-list.
- Structured logs with request IDs; never log passwords, tokens or document contents.
- Database backups, restore testing, monitoring and incident response.
- Configurable retention and deletion.
- Target availability and performance SLAs to be agreed before launch.
- Support English first; prepare localization for Kannada and other languages.
- Keep service rules configurable rather than hard-coded.

## 13. API requirements (initial contract)

Public:
- `GET /health`
- `GET /api/v1/services`
- `GET /api/v1/services/{slug}`

Customer (authenticated or verified intake session):
- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{id}/messages`
- `POST /api/v1/tickets`
- `GET /api/v1/tickets/{ticket_number}` (verified authorization required)
- `POST /api/v1/tickets/{ticket_number}/messages`
- `POST /api/v1/tickets/{ticket_number}/documents` (presigned upload flow recommended)

Admin/agent (authenticated with RBAC):
- `GET /api/v1/admin/tickets`
- `GET /api/v1/admin/tickets/{id}`
- `PATCH /api/v1/admin/tickets/{id}/status`
- `POST /api/v1/admin/tickets/{id}/assignments`
- `POST /api/v1/admin/tickets/{id}/internal-notes`
- `GET /api/v1/admin/reports/summary`

All protected routes require server-side identity and permission checks, audit events and rate limits as appropriate.

## 14. Acceptance criteria

- A visitor can browse the homepage and service categories on mobile and desktop.
- A visitor can start a service request from a service card or hero CTA.
- The intake flow asks only relevant questions for the selected property/service.
- A request summary can be reviewed before submission.
- Submission creates a unique ticket and confirms the next step.
- Customer can view a ticket only after verification/authorization.
- Admin can search/filter tickets, assign an agent and transition status.
- Agent can work assigned tickets and submit deliverables for review.
- Every status change and assignment is audit logged.
- Internal notes are never shown to customers.
- Uploaded documents are private and authorized downloads expire.
- Empty, loading, invalid input and API failure states are designed.
- Secrets are stored in deployment secret managers, not source control.

## 15. Out of scope for initial scaffold

- Live access to government portals or automated scraping
- Legal advice or automated title-clearance decisions
- Payment collection
- Production-grade authentication
- WhatsApp/SMS/email provider integration
- OCR / document intelligence
- Native mobile apps
- Real-time agent tracking

These should be planned as later phases with legal, security and operational review.
