# Architecture

## Components

- **Frontend:** Next.js App Router + TypeScript. Public homepage with the callback form, ticket tracking and chat assistant; staff workspace under `/admin`.
- **Backend:** FastAPI REST API (`backend/app`). Pydantic schemas validate input; SQLAlchemy models in `models.py`; ticket lifecycle in `tickets.py`; staff endpoints in `admin.py` with bearer-token sign-in and admin/agent roles.
- **Database:** PostgreSQL. The schema is defined by the models and applied with Alembic migrations (`backend/migrations`).
- **AI orchestration (future):** provider adapter + service-specific intake state machine. The model may propose questions or summaries, but server-side rules determine required fields, permissions and status transitions.
- **File storage (future):** private S3-compatible object storage with malware scanning and short-lived signed URLs.
- **Notifications:** ticket events queue rows in `notifications` (SMS and email). A provider adapter and delivery worker are still to be added.
- **Deployment:** GitHub for source and CI; frontend and API deployed separately; managed PostgreSQL and object storage.

## Core design principles

1. Service configuration controls required questions and documents.
2. AI is not the source of truth for prices, status transitions, permissions or legal outcomes.
3. Keep internal notes separate from customer-visible messages.
4. Every sensitive admin action is authorized and audited.
5. Customer documents are private by default.
6. Use database transactions for ticket creation and status changes.
7. Use idempotency keys for retryable create/payment/notification operations.
