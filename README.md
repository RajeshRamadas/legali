# Homexo Property Services Platform

A GitHub-ready starter repository for a unified Homexo platform covering **homes, apartments, plots, land records, property legal assistance, maintenance, customer requests, agent assignments, and ticket tracking**.

> Status: starter scaffold, not production-ready. Review the security checklist and complete the TODOs before handling real customer data or payments.

## Included

- Responsive Next.js homepage for Homexo Legal (buyer packages, developer services, document desk) with a callback form that raises tickets, ticket tracking and a chat assistant.
- Expo (React Native) app for Android and iPhone with the service list and request form.
- Shared TypeScript package (`packages/shared`) with API types and client, used by both the website and the app.
- FastAPI backend with the service catalogue, ticket intake and tracking, customer replies, and a staff API (sign-in, queue, status, assignment, messages, internal notes, staff management, reports).
- Find a lawyer (Practo style) on the website (`/lawyers`, `/bookings`) and in the app: search advocates by specialisation, language, fee, experience and availability, book an open slot for a video consultation, then move, cancel or rate it. Lawyers keep their profile and weekly hours under Lawyer profile in `/admin` (see `docs/lawyer-booking.md`).
- Customer document repository and legal reports (`/documents`, and on each ticket in `/admin`): customers upload and tag documents; the lawyer issues a preliminary report with a checklist of documents, each with a tag the customer files uploads under; public records (EC, khata, RTC, tax receipts) go to a government fetch queue for the team instead of the buyer; once every item is verified or waived, a final report PDF is generated to print, sign and upload back for the customer to download. Files go to S3 or Cloudflare R2, or local disk in development (see `docs/documents.md`).
- Staff workspace at `/admin` for admins and agents, with a calendar of each lawyer's video meetings.
- Video consultations on tickets: Google Calendar events with Google Meet links, WhatsApp invites and reminders for the customer and the lawyer, and a Join button on the customer's tracking card (see `docs/meetings.md`).
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
        ├── Request form
        └── Assistant (same AI chat: answers, tracking, replies to the case team)
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

Set `ANTHROPIC_API_KEY` in `infra/.env` to turn on AI answers in the chat. The assistant retrieves the most relevant sections of the knowledge base in `backend/app/knowledge/*.md` for each question and, once a customer verifies their ticket in the chat, reads that ticket's status, history and case-team messages (never internal notes). It uses the low-cost `claude-haiku-5-5` at low effort by default (`CHAT_MODEL`, `CHAT_EFFORT`). Retrieval keeps each request small (the instructions plus about five short sections), and the instructions are prompt-cached. To use a larger model such as `claude-sonnet-5-5`, set `CHAT_MODEL`; non-Haiku models also turn on Anthropic's server-side refusal fallback (`CHAT_FALLBACKS`, set it to `off` on Bedrock, Vertex AI or Foundry). Without a key, or if a call fails, the chat answers from its built-in rule-based topics.

Chats are saved. When a customer raises a request from the chat, or checks a ticket in it, staff see the conversation under **Chat with the assistant** on the ticket page. The chat is limited to `CHAT_RATE_LIMIT_PER_MINUTE` messages per visitor (default 20), counted in the database so the limit holds however many API workers run. Behind a load balancer, start uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy address>` so each visitor is counted separately.

To teach the assistant something new, edit the markdown files: every `## ` heading is one section it can retrieve, so keep each section about one topic.

### Video meetings (Google Meet and WhatsApp)

From a ticket, staff can book a call with the customer. With Google Calendar connected (`GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CALENDAR_USER`) the API creates the event with a Meet link; without it, staff paste a link. With WhatsApp Business connected (`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`) the customer and lawyer get the link, reminders and changes on WhatsApp; without it, the messages wait in the queue. Setup steps and the WhatsApp templates to create are in `docs/meetings.md`.

### Find a lawyer

Each staff member can publish a lawyer profile with weekly hours from Lawyer profile in `/admin`. For sample lawyers in development, run `python -m app.demo_lawyers` in `backend/` (accounts without passwords; not for production). Booking rules and settings are in `docs/lawyer-booking.md`.

### Documents and legal reports

Set `S3_BUCKET` (plus `S3_ENDPOINT_URL` and `S3_REGION=auto` for Cloudflare R2, and keys) to keep files in a private bucket; without it they go to `backend/storage/`. The flow, settings and the government portals are in `docs/documents.md`.

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
4. Virus scanning of uploads (files are type-checked and stored privately with expiring links, but `scan_status` stays `pending`), and automatic fetching from government portals, which today is a task queue for staff because the portals have no open API.
5. Email and SMS providers for notifications; they are recorded as queued but not sent yet. WhatsApp meeting messages send once WhatsApp Business is connected (`docs/meetings.md`), but ticket status updates still go only to the SMS and email queue.
6. Payment integration only after selecting a compliant provider; never store card data. Lawyer bookings show the fee but don't collect it yet.
7. Rate limiting for login, ticket intake and lookup (chat is limited already), abuse protection, backups, observability, privacy retention (including a clean-up of old chat transcripts) and security testing.
8. Legal review of service descriptions and authorization requirements for accessing government records.

See `docs/requirements.md`, `docs/architecture.md`, `docs/api-contract.md`, `docs/implementation-plan.md` and `docs/security-checklist.md`.
