# Homexo Property Services Platform

A GitHub-ready starter repository for a unified Homexo platform covering **homes, apartments, plots, land records, property legal assistance, maintenance, customer requests, agent assignments, and ticket tracking**.

> Status: starter scaffold, not production-ready. Review the security checklist and complete the TODOs before handling real customer data or payments.

## Included

- Responsive Next.js homepage with service catalogue, navigation, process steps, CTA and chatbot entry point.
- Expo (React Native) app for Android and iPhone with the service list and request form.
- Shared TypeScript package (`packages/shared`) with API types and client, used by both the website and the app.
- FastAPI backend starter with health, service catalogue and ticket creation/listing endpoints.
- PostgreSQL schema for customers, property profiles, conversations, service requests/tickets, assignments, messages, files, notifications and audit events.
- Docker Compose for local PostgreSQL + API.
- GitHub Actions backend checks.
- Requirements, architecture, API outline, implementation plan and security checklist.

## Architecture

```text
Customer browser
  └── Next.js frontend (frontend/)
        ├── Homepage / service catalogue
        ├── Chatbot UI (starter entry point)
        └── Future customer account / ticket tracking
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
                 ├── Admin and agent APIs (next phase)
                 └── AI provider integration (next phase)
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
   cp .env.example .env
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
   - API health: http://localhost:8000/health
   - API docs: http://localhost:8000/docs

The frontend is configured to use `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` by default.

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
1. Authentication, password reset, MFA for admins, session management and RBAC.
2. Database-backed repositories and migrations (the sample ticket API currently uses in-memory data).
3. Conversational intake with validation, consent, resumable sessions and AI provider abstraction.
4. Admin dashboard: ticket queue, filters, assignment, status transitions, notes, SLA and audit trail.
5. Agent workspace and customer ticket tracking.
6. Secure document upload/download using private object storage, file scanning and expiring URLs.
7. Notifications (email/SMS/WhatsApp) with templates and opt-in/opt-out.
8. Payment integration only after selecting a compliant provider; never store card data.
9. Rate limiting, abuse protection, backups, observability, privacy retention and security testing.
10. Legal review of service descriptions and authorization requirements for accessing government records.

See `docs/requirements.md`, `docs/architecture.md`, `docs/api-contract.md`, `docs/implementation-plan.md` and `docs/security-checklist.md`.
