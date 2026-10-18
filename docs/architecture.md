# Architecture

## Components

- **Frontend:** Next.js App Router + TypeScript. Public homepage and service discovery are in the starter; chatbot and customer/admin workspaces are planned modules.
- **Backend:** FastAPI REST API. Pydantic schemas validate input. Current starter endpoints are intentionally small.
- **Database:** PostgreSQL. `database/schema.sql` is an initial relational model; use Alembic migrations before production.
- **AI orchestration (future):** provider adapter + service-specific intake state machine. The model may propose questions or summaries, but server-side rules determine required fields, permissions and status transitions.
- **File storage (future):** private S3-compatible object storage with malware scanning and short-lived signed URLs.
- **Notifications (future):** provider adapter for email/SMS/WhatsApp, with consent and delivery logs.
- **Deployment:** GitHub for source and CI; frontend and API deployed separately; managed PostgreSQL and object storage.

## Core design principles

1. Service configuration controls required questions and documents.
2. AI is not the source of truth for prices, status transitions, permissions or legal outcomes.
3. Keep internal notes separate from customer-visible messages.
4. Every sensitive admin action is authorized and audited.
5. Customer documents are private by default.
6. Use database transactions for ticket creation and status changes.
7. Use idempotency keys for retryable create/payment/notification operations.
