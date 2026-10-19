# Architecture

## Components

- **Frontend:** Next.js App Router + TypeScript. Public homepage with the callback form, ticket tracking and chat assistant; staff workspace under `/admin`.
- **Backend:** FastAPI REST API (`backend/app`). Pydantic schemas validate input; SQLAlchemy models in `models.py`; ticket lifecycle in `tickets.py`; staff endpoints in `admin.py` with bearer-token sign-in and admin/agent roles.
- **Database:** PostgreSQL. The schema is defined by the models and applied with Alembic migrations (`backend/migrations`).
- **Chat assistant:** `chat.py` + `assistant.py`. Retrieval-augmented: each question is matched with BM25 (`knowledge.py`) against the markdown knowledge base in `backend/app/knowledge/`, and the top sections plus the customer's verified ticket (customer view only) go to Claude (`claude-haiku-5-5` by default, low effort, JSON-schema output; configurable with `CHAT_MODEL`). The model only answers and suggests a UI action; tickets are raised, verified and replied to through the normal endpoints. Falls back to rule-based topics without an API key or on any AI error. To add knowledge, edit or add a markdown file: each `## ` section is one retrievable chunk. Chats are saved as `conversations` and linked to the ticket raised from them (or the ticket checked in them), and staff read them on the ticket page. The chat rate limit counts saved messages per hashed client address, so it is shared by every API worker.
- **AI intake (future):** service-specific intake state machine. The model may propose questions or summaries, but server-side rules determine required fields, permissions and status transitions.
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
