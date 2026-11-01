# Homexo UI website adaptation

The approved demo is adapted to the real Next.js application on `feature/homexo-ui`. Existing API endpoints, roles, ticket/document workflows, payments, scheduling and legal-report approval remain in use. There are no backend source or schema changes in this redesign.

## What changed

- Shared design tokens, self-hosted Plus Jakarta Sans, SVG icons, buttons, badges, cards, accessible tabs, stat/attention/case cards, calendar, loading states, page headers and theme controls live in `frontend/app/ui/`.
- The root frame selects the public shell, signed-in customer shell or existing staff authentication boundary. Theme selection is saved as `hx-theme`; an early script applies saved/system preference before hydration. The design demo keeps its separate preference.
- Public pages share navigation/footer. The homepage uses the approved headline/collage, working assistant ask box, service grid, live RERA/lawyer data, three package cards and preserved section anchors. API failures retain useful public content and fallback links. Sample RERA data is labelled.
- `/account` is a real dashboard: attention cards, active/completed requests, signed-report count, consultations, payments, profile editing and the assistant. The shell includes masked phone, search, notifications and mobile bottom navigation. Documents, bookings and payment return routes retain their workflows inside the shell.
- `/assistant` works with or without a customer session. The floating widget, dashboard panel and full page share an in-memory conversation through `useAssistant`. The page supports safe Markdown, knowledge sources, real callback/ticket verification forms, transcript export and Clear. Model-generated image links are not automatically loaded.
- The staff auth/provider remains responsible for access control. The new shell, real summary tiles, case-card queue, status tabs/URL selection, urgent filter, CSV export, calendar and meeting timeline use existing staff APIs. Role-specific links and the existing availability control remain.
- The customer case Message action opens a real message/history section on Documents. Upload, intake, verification, advocate approval, final PDF and signature controls remain in their existing components. Mutations refresh shell notifications.
- The superseded per-area CSS files and navigation components are retired. Behaviour-specific view rules now live under `ui/views/`; shared tokens and theme-aware colour treatments replace the old palette and typography. Layout-specific rules remain with their views to avoid changing legal/booking behaviours.
- `/ui` is a noindex component showcase. `/design-demo` and its standalone static reference remain available.

## Validation

- Workspace TypeScript checks and production Next.js build.
- Existing backend regression suite: 131 passed.
- Chromium with real local API/PostgreSQL fixtures at 1440×900, 390×844 and 360×844, light and dark: homepage, account, documents, assistant, staff dashboard, inner public pages and the staff case/verification page.
- Real assistant request, transcript export and Clear; customer signed-report tile and meeting data; no horizontal overflow or page exceptions in the checked views.
- Additional interaction checks cover search, queue tabs/export, mobile navigation/Escape, theme persistence/system default and real customer document messaging/upload. A delayed chat response is discarded after sign-out, so one customer’s conversation cannot reappear across that session boundary.
- Lawyer profile/detail grids were checked and corrected to shrink at 360 px. No references to the old palette tokens or Georgia remain in `frontend/app`.

The fixture cases, account and report used for browser checks are explicitly synthetic and exist only in the local development database. They are not hardcoded into the website. Production records are never manufactured to fill dashboards.

Screenshots are captured during browser checks for review. Chromium was exercised; Safari/Firefox and a comparative Lighthouse run are not claimed here. Optional Expo colour-token changes are outside this web adaptation. Publishing the environment or merging to the production branch is separate from these code changes.

## Running the working site

This is now the Next.js website, not just the standalone HTML mockup. After checking out the feature branch, run `npm ci` from the repository root, start the existing API/PostgreSQL workflow, then run `npm run dev --workspace frontend -- --port 8085`. Open `http://localhost:8085`.

For API calls from that port, set `CORS_ORIGINS=http://localhost:8085` (or include both `http://localhost:3000,http://localhost:8085`) in the backend process environment or `infra/.env` before starting/recreating the API. Using the normal `npm run web` port 3000 works with the existing default CORS setting. A plain Python file server cannot run the working Next.js site; it is only suitable for the preserved `frontend/public/demo-ui/` static demo.
