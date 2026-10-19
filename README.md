# Homexo Property Services Platform

A GitHub-ready starter repository for a unified Homexo platform covering **homes, apartments, plots, land records, property legal assistance, maintenance, customer requests, agent assignments, and ticket tracking**.

> Status: starter scaffold, not production-ready. Review the security checklist and complete the TODOs before handling real customer data or payments.

## Included

- Responsive Next.js homepage for Homexo Legal (buyer packages, developer services, document desk) with a callback form that raises tickets, ticket tracking and a chat assistant.
- Expo (React Native) app for Android and iPhone with the service list and request form.
- Shared TypeScript package (`packages/shared`) with API types and client, used by both the website and the app.
- FastAPI backend with the service catalogue, ticket intake and tracking, customer replies, and a staff API (sign-in, queue, status, assignment, messages, internal notes, staff management, reports).
- Staff workspace at `/admin` for admins and agents.
- PostgreSQL schema (SQLAlchemy models + Alembic migrations in `backend/migrations`) for customers, properties, service requests/tickets, assignments, ticket events, messages, documents, notifications and audit logs.
- Docker Compose for local PostgreSQL + API.
- GitHub Actions backend checks.
- Requirements, architecture, API outline, implementation plan and security checklist.

## Architecture

```text
Customer browser
  └── Next.js frontend (frontend/)
        ├── Homepage / service catalogue
        ├── AI chat assistant (answers from the knowledge base and the verified ticket; raises, tracks and replies to tickets)
        ├── Ticket tracking and replies (ticket number + phone/email)
        └── Staff workspace /admin (admins and agents)
  Android / iPhone app
  └── Expo app (mobile/)
        ├── Service list
        └── Request form
  Both use packages/shared (API types + client)
                 │ HTTPS / JSON
                 ▼
           FastAPI backend (backend/)
                 ├── Service catalogue
                 ├── Customer intake / conversations (next phase)
                 ├── Ticket lifecycle
                 ├── Staff APIs (admins see all tickets, agents see assigned)
                 └── Claude API for the chat assistant (optional; rule-based without a key)
                 │
                 ▼
           PostgreSQL database
                 └── Private object storage for uploaded documents (future)

Admin dashboard and agent workspace should be added as authenticated role-based routes/apps.
```

## Prerequisites

- Git
- Docker + Docker Compose
- Node.js 20+ and npm
- Python 3.11+ if running the API outside Docker

## Run locally

1. Copy environment settings:

   ```bash
   cp .env.example infra/.env
   ```

2. Start the API and PostgreSQL:

   ```bash
   docker compose -f infra/docker-compose.yml up --build
   ```

3. In another terminal, install JavaScript dependencies once from the repo root (npm workspaces cover `frontend/`, `mobile/` and `packages/`), then run the website:

   ```bash
   npm install
   npm run web
   ```

4. Open:
   - Homepage: http://localhost:3000
   - Staff workspace: http://localhost:3000/admin (sign in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`, by default `admin@homexo.local` / `change-this-admin-password`)
   - API health: http://localhost:8000/health
   - API docs: http://localhost:8000/docs

The API container runs `alembic upgrade head` before starting, so the database schema is always current. The first admin is created only when no admin exists; change its password and add agents from **Staff** in the workspace.

The frontend is configured to use `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` by default.

### AI chat assistant

Set `ANTHROPIC_API_KEY` in `infra/.env` to turn on AI answers in the chat. The assistant retrieves the most relevant sections of the knowledge base in `backend/app/knowledge/*.md` for each question and, once a customer verifies their ticket in the chat, reads that ticket's status, history and case-team messages (never internal notes). It uses `claude-opus-5-5` by default (`CHAT_MODEL`, `CHAT_EFFORT`) with Anthropic's server-side refusal fallback; set `CHAT_FALLBACKS=off` when calling Claude through Bedrock, Vertex AI or Foundry. Without a key, or if a call fails, the chat answers from its built-in rule-based topics.

To teach the assistant something new, edit the markdown files: every `## ` heading is one section it can retrieve, so keep each section about one topic.

### Run the API without Docker

With PostgreSQL running locally:

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://homexo_app:PASSWORD@localhost:5432/homexo
export BOOTSTRAP_ADMIN_EMAIL=admin@homexo.local BOOTSTRAP_ADMIN_PASSWORD=choose-a-password
alembic upgrade head
uvicorn app.main:app --reload
```

Tests use in-memory SQLite by default (`pytest`). To run them against PostgreSQL, point `TEST_DATABASE_URL` at an empty test database; the tests drop and recreate its tables.

After changing `backend/app/models.py`, create a migration with `alembic revision --autogenerate -m "describe the change"` and review it before committing.

### Run the mobile app (Android / iPhone)

1. Install [Expo Go](https://expo.dev/go) on your phone, or use an Android emulator / iOS simulator.
2. Point the app at the API. `localhost` on a phone means the phone itself, so use your computer's LAN address (or `http://10.0.2.2:8000` on the Android emulator):

   ```bash
   EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:8000 npm run mobile
   ```

3. Scan the QR code with Expo Go (Android) or the Camera app (iPhone).

Publishing to the stores needs an Apple Developer account and a Google Play developer account; builds are made with EAS Build (`npx eas build`). Add mobile packages with `npx expo install <package>` from `mobile/` so versions match the Expo SDK.

Run `npm run typecheck` from the repo root to type-check the website, app and shared package together.

## Publish to GitHub

Create an empty repository on GitHub, for example `homexo-property-services`. Do not initialize it with a README if you will push this folder.

```bash
cd homexo-platform
git init
git add .
git commit -m "Initial Homexo platform scaffold"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/homexo-property-services.git
git push -u origin main
```

Never commit `.env`, API keys, database passwords, customer documents, or production data. `.gitignore` excludes common secret files.

## Important implementation gaps

Before production, implement:
1. Password reset, MFA for admins, and OTP verification for customers before showing ticket details (today a ticket number plus the phone or email used is enough).
2. SLA targets and due dates on tickets.
3. Conversational intake with validation, consent and resumable sessions. The chat assistant answers questions but still raises tickets through the form.
4. Secure document upload/download using private object storage, file scanning and expiring URLs.
5. A delivery worker and provider for notifications (email/SMS/WhatsApp); notifications are recorded as queued but not sent yet.
6. Payment integration only after selecting a compliant provider; never store card data.
7. Rate limiting (login, ticket intake and lookup; chat has a per-process limit only), abuse protection, backups, observability, privacy retention and security testing.
8. Legal review of service descriptions and authorization requirements for accessing government records.

See `docs/requirements.md`, `docs/architecture.md`, `docs/api-contract.md`, `docs/implementation-plan.md` and `docs/security-checklist.md`.
