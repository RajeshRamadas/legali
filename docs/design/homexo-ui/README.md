# Homexo UI: requirements and design specification

**Status:** approved direction (Rajesh, 2026-11-01). This document is the single source of truth for rebuilding the Homexo web front end in one uniform look and feel.
**Audience:** any engineer or LLM coding agent. It is written so the work can be done without extra context: read it top to bottom, then build in the order given in section 11.

Companion files in this folder:

| Path | What it is |
|---|---|
| `mockups/*.html` | Static HTML mockups of the five reference screens. Open them in a browser. They are the visual target. |
| `mockups/homexo-ui.css` | The mockups' stylesheet. Token values and component CSS here are normative: copy them, don't reinvent them. |
| `mockups/build.py` | Generates the mockups. It shows the icon set (`ICONS`) and the exact markup of every component. |
| `screenshots/` | Desktop (1440 px) and mobile (390 px) captures of each mockup, plus `overview-desktop.png`. |

---

## 1. Context

Homexo Legal is a Bangalore property legal-services platform. It offers:
- a free RERA project check
- booking verified advocates for video consultations
- fixed-fee property verification packages (Shield Starter ₹4,999, Shield Pro ₹9,999, Shield Complete ₹18,999)
- documents (EC, RTC, certified copies, deeds, affidavits)
- services for developers
- a request number for every case, with tracking
- an AI legal assistant

**Stack:** Next.js 14 App Router + React 18 + TypeScript in `frontend/`, with plain global CSS files (no Tailwind, no CSS-in-JS). The API client and types live in `packages/shared` (`@homexo/shared`). The backend is FastAPI in `backend/`. An Expo mobile app lives in `mobile/`.

**Problem:** the site looks dated. It uses Georgia serif headings, a forest-green, gold and cream palette, 9 to 12 px text and flat cards. The three areas also look like three different products:
- the public site
- the customer pages (`/account`, `/documents`, `/bookings`)
- the staff workspace (`/admin`)

**Decision:** adopt **Homexo UI**, a single design system based on modern legal-tech dashboards (references in Appendix A). It has a violet primary colour, Plus Jakarta Sans, a sidebar app shell, tinted stat tiles, case cards, an AI assistant panel, and light and dark themes.

## 2. Goals and non-goals

**Goals**
- G1. One visual language across the public site, customer portal, staff workspace and AI assistant.
- G2. Customers see "what needs me now" on one screen after sign-in.
- G3. Staff see their queue, today's calls and documents to review on one screen.
- G4. Mobile-first quality: every customer-facing page works at 360 px, and the customer portal uses bottom tabs.
- G5. Light and dark themes.
- G6. No change to API contracts, business logic, routes or URLs that already exist.

**Non-goals**
- Changing backend behaviour or the database. The only exception is the optional endpoint in R-STF-5.
- New product features beyond the dashboards and the full-page assistant described here.
- Redesigning the Expo app's screens. Only its colour tokens are shared (phase 6).
- Adding a CSS framework (Tailwind, MUI and so on) or an icon package. Use the inline SVG icon set from `mockups/build.py`.

## 3. Surfaces and routes

| Surface | Routes (all exist today unless marked NEW) | Shell |
|---|---|---|
| Public site | `/`, `/rera`, `/rera/projects/[slug]`, `/rera/localities/[slug]`, `/rera/developers/[slug]`, `/lawyers`, `/lawyers/[slug]`, `/services`, `/developers`, `/blog`, `/blog/[slug]` | `PublicShell` (top nav + footer) |
| Customer portal | `/account` (becomes the dashboard), `/documents`, `/bookings`, `/bookings/paid`, **NEW** `/assistant` | `AppShell` with the customer nav (signed in). Signed-out visitors see the existing sign-in / track forms inside `PublicShell`. |
| Staff workspace | `/admin` (becomes the dashboard + queue), `/admin/tickets/[ticketNumber]`, `/admin/calendar`, `/admin/fetches`, `/admin/team`, `/admin/profile`, `/admin/blog`, `/admin/blog/[id]`, `/admin/staff` | `AppShell` with the staff nav (replaces `admin/AdminShell.tsx` visuals; keep its auth logic) |

The floating `ChatWidget` stays on public pages. Inside the customer portal, the assistant is the `/assistant` page and the dashboard panel, so the floating button is hidden there.

## 4. Functional requirements

IDs are referenced by the acceptance criteria in section 12.

### 4.1 Global

- **R-GLB-1 Theme.** Light and dark themes come from the same tokens (section 6.1). The `<html>` element carries `data-theme="light|dark"`. A toggle button (sun/moon icon) in the top bar and the public nav switches theme and saves it in `localStorage` under `hx-theme`. With no saved value, follow `prefers-color-scheme`. An inline script in `layout.tsx` sets the attribute before first paint, so there is no flash.
- **R-GLB-2 Font.** Plus Jakarta Sans variable, self-hosted via `@fontsource-variable/plus-jakarta-sans`, imported once in `frontend/app/layout.tsx`. No Google Fonts request.
- **R-GLB-3 Formatting.** Money uses the existing `formatFee` (₹ with en-IN grouping), with lakhs shown as `₹1.86L` in stat tiles. Dates and times use en-IN in the Asia/Kolkata zone, for example "Saturday, 1 November 2026" and "4:00 pm".
- **R-GLB-4 Greeting.** Show "Good morning" before 12:00, "Good afternoon" before 17:00 and "Good evening" after, followed by the first name, in IST.
- **R-GLB-5 States.** Every data block has three states: loading (a skeleton the size of the content), empty (one line plus a primary action) and error (one line plus Retry). No block may crash the page. The home page already renders without the API, and must keep doing so.
- **R-GLB-6 Copy.** Plain English, sentence case, no exclamation marks. Keep existing copy wherever a page keeps its purpose.

### 4.2 Public site (mockup `1-public-home.html`)

- **R-PUB-1 Nav.** Logo (violet "H" mark + "homexo legal"), links (RERA check, Find a lawyer, Verify a property, Documents, For developers), theme toggle, "Sign in" (outline pill, goes to `/account`) and "Get started" (dark pill, goes to `/#callback`). Below 1000 px, the links collapse into a menu button that opens a sheet, which also lists Track request and Sign in.
- **R-PUB-2 Hero.** Two columns:
  - **Left:** a badge ("Bangalore · property law online"), the H1 "Property lawyers, on *demand*." with the hand-drawn underline under the accent word, a lead paragraph, two pill buttons ("Book a lawyer" goes to `/lawyers`, "Check a RERA project" goes to `/rera`) and the ask box.
  - **Right:** the collage. Two tinted portrait panels plus floating cards fed by live data when available:
    - the first lawyer from `searchLawyers({sort:"soonest"})`, with name, headline and next free slot
    - the most popular package from `PACKAGES` in `content.ts`, with price and delivery
    - a static "Title review done · Stage 3 of 4" example card
    - the first red-risk RERA project from `searchReraProjects({risk:"red", sort:"risk", page_size:1})`
  
  Fall back to the static text in the mockup when the API is down.
- **R-PUB-3 Ask box.** Typing and submitting opens the chat assistant with the question, through the existing `askAssistant()` in `homeEvents.ts`.
- **R-PUB-4 Trust strip.** Six items with icons: Verified advocates, Fixed fees, Google Meet calls, WhatsApp updates, UPI & cards, Karnataka RERA data. Use text and icons only, no third-party logos.
- **R-PUB-5 Below the hero**, in this order, rebuilt with the new components:
  - service cards (the existing nine `TILES` in `page.tsx`, shown as 4 columns on desktop, 2 on tablet and 1 on phone)
  - the RERA block (search, sample notice, flagged project card, market stats)
  - "How it works" (3 steps)
  - lawyers available today (3 `LawyerCard`s)
  - packages (the 3 packages, with the popular one highlighted)
  - developer band
  - the callback form (`CallbackSection`, behaviour unchanged)
  - track request (unchanged behaviour)
  - insights (3 posts)
  - FAQ
  - final call to action
  - footer
  
  Keep every existing `id` anchor (`#rera`, `#services`, `#lawyers`, `#packages`, `#developers`, `#callback`, `#track`, `#insights`, `#faq`), because other pages link to them.
- **R-PUB-6 Inner public pages** (`/rera*`, `/lawyers*`, `/services`, `/developers`, `/blog*`) use `PublicShell` and the same components:
  - `Card` for panels
  - `Badge` for risk and status
  - `Button`, `Chip` for filters
  - `StatTile` for market numbers
  - `LawyerCard` for lawyer lists
  
  Layout and content stay the same. Only the components and styles change.

### 4.3 Customer portal (mockup `2-customer-dashboard.html`)

The data comes from `api.getAccount(token)`, which returns `AccountOverview { profile, requests[], bookings[], payments[] }`. The session token comes from `frontend/app/account/session.ts`.

- **R-CUS-1 Shell.**
  - **Sidebar** "Overview": Home (`/account`), My requests (`/account#requests`, with a count badge of open requests), Documents (`/documents`), Consultations (`/bookings`), Payments (`/account#payments`).
  - **Sidebar** "Get help": AI assistant (`/assistant`), Find a lawyer (`/lawyers`), RERA check (`/rera`).
  - **Footer:** avatar initials, name (or "Your account"), masked phone, and a menu with Sign out.
  - **Top bar:** search (filters requests by title or ticket number and jumps to the match; ⌘K/Ctrl+K focuses it), theme toggle, and a notifications bell. The bell shows a dot when any request has `needs_you`, and opens a list of those requests.
  - **Below 1000 px:** the sidebar is hidden, the top bar shows the logo, and bottom tabs appear: Home, Requests, Ask (`/assistant`), Docs (`/documents`), Account (`/account#profile`).
- **R-CUS-2 Page header.** "Good afternoon, {first name}" (R-GLB-4), with the date line underneath. Actions: "Book a consultation" (outline, goes to `/lawyers`) and "New request" (primary, goes to `/#callback`).
- **R-CUS-3 Stat tiles (4).** Open requests: requests whose status is not completed or cancelled. Documents needed: requests with a non-null `needs_you`. Consultation today / next: the earliest scheduled `next_meeting` across requests and bookings, shown as a time; the label is "Consultation today" when it is today, otherwise "Next consultation" with the date. Reports ready: requests with `report.signed === true`. Tile colours are violet, amber, blue and green, in that order.
- **R-CUS-4 Needs your attention.** Up to 4 cards in a 2-column grid, taken from `needs_you` items first, then today's meetings, then signed reports.
  - The first card uses the solid violet gradient. The rest are neutral with a status badge.
  - Badge colours: "Due"/"Waiting on you" amber, "Today" blue, "Ready" green.
  - Each card links to its request: `/documents?ticket=…` through the existing `openDocuments()`, or a meeting's `meet_link` when it can be joined.
  - Empty state: "You're all caught up."
- **R-CUS-5 My requests.** Tabs: Active / Completed. Each request is a `CaseCard`:
  - service icon in a tint
  - title, plus a package badge when there is one
  - lawyer or service line, plus the started date
  - amount and payment state (from the matching booking or payment, if any)
  - stage label from `status_label`
  - progress bar from `report.progress.done / total`, or the stage index when there is no report
  - actions: Documents (`openDocuments`) and Message (opens the request's message thread on `/documents`)
- **R-CUS-6 Assistant panel.** A compact `AssistantPanel`: an "Online" badge, the last exchange (or a greeting when empty), 3 suggestion chips (from the last reply's `suggestions`, or the defaults "RERA check", "Which package?", "Talk to a lawyer") and an input. Sending calls `api.chat()` with the stored `conversationId`, the same as `ChatWidget`. "Open full chat" goes to `/assistant`.
- **R-CUS-7 Upcoming.** A list of the next 3 scheduled meetings (lawyer initials avatar, lawyer name, title, time and date). The primary button reads "Join today's call" and is enabled only when the meeting can be joined: reuse the logic of `joinable()` from `admin/api.ts`, moving it to a shared util. Otherwise the button reads "See all consultations" and goes to `/bookings`.
- **R-CUS-8 Existing pages inside the shell.** `/documents` (journey, uploads, checklist) and `/bookings` keep their behaviour but render inside `AppShell` with the new components. The document checklist uses `Card` + `Badge`. Upload rows use list rows.
- **R-CUS-9 Assistant page `/assistant`** (mockup `5-ai-assistant.html`), NEW:
  - **Main card:** a header (icon, "Legal assistant", subtitle, Export and Clear buttons), the message list, and an input pinned at the bottom.
  - **Assistant messages:** render the reply with the existing safe Markdown renderer `frontend/app/Markdown.tsx`, then source badges from `sources[].title`.
  - **Lawyer hand-off:** when a reply has `service` or `action === "request"`, show a card with a lawyer avatar, a one-line offer and a Start button that calls `requestService()` / goes to `/?service=<slug>#callback`.
  - **Export** downloads the transcript as a `.txt` file. **Clear** resets the conversation id and history.
  - **Right rail:** Quick actions (Check a RERA project goes to `/rera`, Explain a document goes to `/documents`, Draft an affidavit goes to `/?service=affidavit-drafting#callback`, Talk to a lawyer goes to `/lawyers`), then Tips.
  - The page works signed out as well. Use `PublicShell` with the same main card when there is no session.

### 4.4 Staff workspace (mockups `3-staff-workspace.html`, `4-staff-workspace-dark.html`)

Data uses `adminFetch` from `frontend/app/admin/api.ts`. Keep the existing auth and sign-in from `AdminShell.tsx`.

- **R-STF-1 Shell.**
  - **Sidebar** "Workspace": Dashboard (`/admin`), Ticket queue (`/admin?view=queue`, with a count badge of `summary.open`), Calendar (`/admin/calendar`), Government fetches (`/admin/fetches`).
  - **Sidebar** "Clients & team": Team calls (`/admin/team`), Lawyer profile (`/admin/profile`).
  - **Sidebar** "Content", admins only: Blog (`/admin/blog`), Staff (`/admin/staff`).
  - **Footer:** the user's name, role and Sign out.
  - **Top bar:** ticket search (submits `q` to the queue), theme toggle, and a bell that shows the count from `/admin/urgent`.
- **R-STF-2 Header.** The badge "Property legal", "Good afternoon, {first name}", and the date line. Actions: Export (downloads the current queue page as CSV on the client), Filter (opens the existing filters) and "New ticket" (opens `/#callback` in a new tab, as today).
- **R-STF-3 Tabs.**
  - Active cases: `status=open`.
  - New requests: `status=submitted`.
  - Waiting on customer: the "waiting on the customer" statuses that exist in `/admin/meta`. If none exists, hide this tab.
  - Customer replied: `needs_reply=true`.
  - Completed: `status=closed`.
  
  The selected tab is saved in the URL (`?tab=`).
- **R-STF-4 Stat tiles (4)**, from `GET /admin/reports/summary`:
  - Open tickets: `open`, violet
  - New today: `new_today`, blue
  - Urgent: `urgent`, amber
  - Customer replied: `needs_reply`, pink
  
  Admins also see Unassigned (`unassigned`) as a fifth tile. Clicking a tile applies the same filter the current stat buttons apply.
- **R-STF-5 Case list.** `GET /admin/tickets?…` items shown as `CaseCard`s:
  - icon tinted by priority
  - `customer_name` with a priority `Badge` (urgent red "Urgent", high amber "High", normal blue "Normal", low gray "Low")
  - service name plus package
  - right column: `ticket_number` · `location`, plus the fee when it is known (otherwise hide the amount)
  - bottom row: `status_label`, a progress bar from the status order in `/admin/meta`, and actions Documents (goes to `/admin/tickets/{n}#documents`) and Update (goes to `/admin/tickets/{n}`)
  
  Below the list, pagination and the existing filters (service, assignee, search). *Optional backend addition:* include `fee` in `staff_summary` if it is cheap, otherwise omit it.
- **R-STF-6 Calendar card.** A month grid. Days with meetings from `GET /admin/meetings?start=<ISO>&end=<ISO>&lawyer=me` (admins may omit `lawyer`) show a dot, and today is filled violet. Clicking a day goes to `/admin/calendar?day=YYYY-MM-DD`. The footer shows "This month · N calls".
- **R-STF-7 Today's timeline.** Today's meetings in time order: a time badge, title, ticket or customer, and a Join button when `joinable()` is true.
- **R-STF-8 Inner staff pages** (ticket page, calendar, fetches, team, profile, blog editor, staff) render inside `AppShell` with `Card`, `Badge`, `Button`, `Tabs` and list rows. Their behaviour is unchanged.

## 5. Non-functional requirements

- **NFR-1 Accessibility (WCAG 2.2 AA).**
  - Text contrast of at least 4.5:1 (3:1 for 24 px+ bold) in both themes.
  - Visible 2 px focus rings on every interactive element.
  - Every icon-only button has an `aria-label`.
  - The sidebar is a `<nav aria-label>`, and the current item has `aria-current="page"`.
  - Tabs use `role="tablist"`/`tab`/`tabpanel` with arrow-key support.
  - Hit targets are at least 40×40 px (44 on touch).
  - Motion is limited to transitions of 200 ms or less and is disabled under `prefers-reduced-motion`.
- **NFR-2 Performance.** No new runtime dependencies other than the font package. Keep server components where pages are server components today (the home page uses `revalidate = 300`). The font loads with `font-display: swap`. Lighthouse mobile performance must not get worse than the current home page.
- **NFR-3 Responsiveness.** Breakpoints are 1240, 1000, 740 and 520 px. No horizontal scroll at 360 px on any customer-facing page. Staff pages must be usable at 1000 px and readable on phones.
- **NFR-4 Browsers.** The latest two versions of Chrome, Edge, Safari and Firefox, plus Android Chrome and iOS Safari. CSS `color-mix()` is allowed.
- **NFR-5 Security and privacy.** No third-party requests (fonts, icons or analytics). Mask phone numbers in the shell footer (`+91 98•••• 4410`). No customer data in `localStorage` beyond what the app stores today.
- **NFR-6 Code quality.** TypeScript strict passes (`npm run typecheck -w frontend`). Components are small and typed. No inline `style={{}}` for colours: use tokens and classes.

## 6. Design system

### 6.1 Tokens (copy into `frontend/app/ui/tokens.css`)

```css
:root {
  --primary:#6d4aff; --primary-600:#5b37f5; --primary-50:#f1edff; --primary-100:#e4dcff;
  --ink:#0f1222; --ink-2:#4a5068; --ink-3:#8a90a6;
  --bg:#f5f6fa; --surface:#ffffff; --surface-2:#f8f9fc; --line:#e8eaf1;
  --green:#16a34a; --green-50:#e9f8ef; --amber:#f59e0b; --amber-50:#fff6e5;
  --red:#ef4444;  --red-50:#fdecec;  --blue:#2563eb;  --blue-50:#eaf1ff;
  --pink:#ec4899; --pink-50:#fdeef6; --teal:#0d9488; --teal-50:#e6f6f4;
  --public-bg:#f7f5f0;               /* warm off-white for public pages */
  --radius-sm:10px; --radius:16px; --radius-lg:22px; --radius-pill:999px;
  --shadow:0 1px 2px rgba(15,18,34,.04),0 6px 20px rgba(15,18,34,.05);
  --shadow-lg:0 24px 60px rgba(15,18,34,.12);
  --shadow-primary:0 6px 16px rgba(109,74,255,.28);
  --side:#ffffff; --side-ink:#4a5068; --side-active:var(--primary-50); --side-active-ink:var(--primary);
  --font:"Plus Jakarta Sans Variable",system-ui,-apple-system,"Segoe UI",sans-serif;
}
[data-theme="dark"] {
  --ink:#f2f3f8; --ink-2:#b4b8cc; --ink-3:#7c8199;
  --bg:#0c0e17; --surface:#151826; --surface-2:#1b1f30; --line:#262a3d;
  --primary-50:#231c4d; --primary-100:#2e2566;
  --green-50:#0f2a1c; --amber-50:#2d2312; --red-50:#2f1518; --blue-50:#132143; --pink-50:#2e1426; --teal-50:#0d2826;
  --public-bg:#0c0e17;
  --shadow:0 1px 2px rgba(0,0,0,.3); --shadow-lg:0 24px 60px rgba(0,0,0,.5);
  --side:#11131f; --side-ink:#b4b8cc; --side-active:#231c4d; --side-active-ink:#c9bcff;
}
```

**Colour meaning is fixed:**
- violet: primary action, selection, brand
- green: done, ready, safe, online
- amber: waiting, medium priority, "check before you buy"
- red: urgent, high risk, errors
- blue: scheduled or informational
- pink: documents

Never use a status colour for decoration.

### 6.2 Typography

Use one family (Plus Jakarta Sans) at weights 400, 500, 600, 700 and 800.

| Role | Size / line-height / weight / tracking |
|---|---|
| Display (public H1) | clamp(44px, 6vw, 76px) / 1.02 / 700 / -0.045em |
| Page title (app H1) | 28px / 1.2 / 800 / -0.025em (24px under 1000px) |
| Section title (public H2) | 40px / 1.1 / 700 / -0.04em (30px on phone) |
| Card title | 16px / 1.3 / 700 |
| Case name | 16px / 1.3 / 700 |
| Body | 14px / 1.55 / 400-500 (public lead 18px) |
| Small / meta | 12.5-13px / 1.45 / 500-600, colour `--ink-3` |
| Group label | 10.5px / 700 / uppercase / 0.1em, colour `--ink-3` |
| Stat value | 26px / 800 / -0.03em (21px under 1000px) |

The minimum text size is 11.5px (badges only). Everything else is 12px or larger.

### 6.3 Spacing and layout

- Base unit 4px. Card padding 20px. Gaps between cards 20px, between tiles 16px, inside cards 12px.
- App shell: sidebar 252px plus fluid content. Top bar 66px high and sticky. Content padding 26px 28px (18px 16px under 1000px, with 90px bottom padding for the tabs).
- Dashboard grid: `minmax(0,1.6fr) minmax(0,1fr)` on the customer dashboard, `1.55fr / 1fr` on staff, and one column under 1000px.
- Public container: `min(1200px, 100% - 40px)`.

### 6.4 Icons

Use inline SVGs at 24×24 with stroke 1.8, round caps and joins, and `currentColor`. Build `frontend/app/ui/Icon.tsx` from the `ICONS` map in `mockups/build.py` (home, case, file, cal, law, rera, spark, card, users, inbox, video, bell, search, plus, check, clock, alert, upload, send, chev, settings, chat, shield, pen, download, filter, sun, rupee). Add a `moon` icon for the dark-mode toggle. Usage: `<Icon name="case" size={18} />`. Icons are `aria-hidden` unless they stand alone, in which case the parent button carries the label.

## 7. Components

Put every component in `frontend/app/ui/`, with one `.tsx` per component and a shared `ui.css` that holds the component classes from `mockups/homexo-ui.css`. Export them from `frontend/app/ui/index.ts`. Use the class names in the mockup CSS so the mockups stay a valid reference.

| Component | Props (TypeScript) | Notes |
|---|---|---|
| `Icon` | `{ name: IconName; size?: number; className?: string }` | See section 6.4 |
| `Button` | `{ variant?: "default"\|"primary"\|"dark"; size?: "sm"\|"md"\|"pill"; icon?: IconName; href?: string; …button props }` | Renders a `Link` when `href` is set. Classes `.btn`, `.primary`, `.dark`, `.sm`, `.pill`. |
| `IconButton` | `{ icon: IconName; label: string; dot?: boolean; onClick? }` | `.icon-btn`, with `.dot` for unread |
| `Badge` | `{ tone: "green"\|"amber"\|"red"\|"blue"\|"violet"\|"gray"; children }` | `.badge` |
| `Chip` | `{ selected?: boolean; onClick?; children }` | `.chip`, `.chip.on` |
| `Tabs` | `{ items: {id,label,count?}[]; value; onChange }` | `.tabs`, accessible tablist |
| `Card` | `{ title?: string; icon?: IconName; action?: ReactNode; children; className? }` | `.card` plus `.card-h` header with an icon chip |
| `StatTile` | `{ tone: "violet"\|"green"\|"amber"\|"blue"\|"pink"; icon; label; value: ReactNode; delta?: string; onClick? }` | `.stat.t-{tone}`. It is a button when clickable. |
| `CaseCard` | `{ icon; tone; title; badge?: {tone,label}; subtitle; amount?: string; amountNote?: string; stage: string; progress?: number /*0-1*/; actions: ReactNode }` | `.case` |
| `AttentionCard` | `{ featured?: boolean; badge: {tone,label}; title; meta; href }` | The featured card uses the violet gradient (`linear-gradient(135deg,#6d4aff,#9b7bff)`). |
| `ListRow` | `{ leading?: ReactNode; title; meta?; trailing?: ReactNode }` | `.rowi` |
| `MiniCalendar` | `{ month: Date; marked: Set<string /*YYYY-MM-DD*/>; today: Date; onSelect(day) }` | `.cal`, starts on Sunday |
| `Timeline` | `{ items: {time,title,meta,tone,action?}[] }` | List rows with a time badge |
| `AssistantPanel` | `{ compact?: boolean }` | Wraps the chat state from `ChatWidget` (extract it into a `useAssistant()` hook in `ui/useAssistant.ts` and share it with `ChatWidget` and `/assistant`) |
| `Avatar` | `{ initials; tone?: string }` | Colour picked deterministically from the initials |
| `Skeleton` | `{ height; width? }` | Shimmer that respects reduced motion |
| `AppShell` | `{ nav: NavGroup[]; user: {name, sub, initials}; searchPlaceholder; onSearch; bell?: {count, items}; mobileTabs?: NavItem[]; children }` | `.shell`, `.side`, `.topbar`, `.content`, `.mtabs` |
| `PublicShell` | `{ children }` | Public nav (R-PUB-1) and the new footer |
| `ThemeToggle` | none | R-GLB-1 |
| `PageHeader` | `{ eyebrow?: ReactNode; title; subtitle?; actions? }` | `.page-head` |

The footer (in `PublicShell`) has 4 columns (brand + blurb, Get it done, Services, Important), the same links as today's `SiteFooter.tsx` and the same legal disclaimer text. It sits on `--ink` in light theme and `--surface` in dark, with 14px links.

## 8. Screen layouts

Match the mockups. Where this section and a mockup disagree, this section wins.

1. **Public home**: see R-PUB-1 to R-PUB-5 and `1-public-home.html`. Sections alternate `--public-bg` and `--surface` backgrounds, and section padding is 60-96px. Packages show as three cards, with the popular one in an `--ink` (dark) card and a "Most chosen" amber badge. The final call to action is a violet gradient card with white text.
2. **Customer dashboard**: in order, page header, 4 stat tiles, then a 2-column grid (left: Needs your attention, My requests; right: assistant panel, Upcoming). See `2-customer-dashboard.html`.
3. **Staff dashboard**: in order, page header with badge, tabs, stat tiles, then a 2-column grid (left: case list; right: calendar, today's timeline). See `3-staff-workspace.html`.
4. **Assistant page**: a 2-column grid of the main chat card and a 320px rail. See `5-ai-assistant.html`.
5. **Dark theme**: identical layouts with dark tokens. See `4-staff-workspace-dark.html`.

## 9. Responsive behaviour

| Width | Behaviour |
|---|---|
| ≥ 1240 | As in the mockups |
| 1000-1239 | Public nav links tighten. The public brand tagline is hidden. |
| < 1000 | Sidebar hidden. The top bar shows the logo, theme toggle and bell, and search moves into a full-screen sheet opened by a search icon. The customer portal shows bottom tabs. Stat tiles drop to 2 columns, and dashboard grids drop to 1 column. Public hero becomes 1 column with the collage below. Staff pages get a menu button that opens the sidebar as a drawer. |
| < 740 | Case card progress bars are hidden (the stage text stays). Attention cards drop to 1 column. Tabs scroll horizontally. |
| < 520 | Service cards drop to 1 column. The public collage scales down to 0.8. |

## 10. Removing the old design

- Delete the forest/gold tokens and the `.serif` class from `globals.css`. Keep only the resets that are still needed, and move the reusable parts into `ui/`.
- Retire `home.css`, `account/account.css`, `documents/documents.css`, `documents/journey.css`, `lawyers/lawyers.css`, `rera/rera.css`, `blog/blog.css`, `admin/admin.css` and `admin/verification.css`. Do this file by file as each page moves to the new components: when a page is migrated, delete the CSS it no longer uses. At the end, no file may reference `--forest`, `--gold`, `--mint`, `--cream` or `Georgia`. `grep -rE "forest|--gold|--mint|--cream|Georgia" frontend/app` must return nothing.
- Replace `SiteHeader.tsx`/`SiteFooter.tsx` with `PublicShell`, and `CustomerNav.tsx` and the visuals of `AdminShell.tsx` with `AppShell`.

## 11. Implementation plan (order of work)

Build on a feature branch. Each phase is one pull request and must pass section 12 before merging.

1. **Foundation**
   - `ui/tokens.css`, `ui/ui.css`, the `ui/*` components from section 7
   - the font package, `ThemeToggle` and the no-flash script in `layout.tsx`
   - `useAssistant()` extracted from `ChatWidget`
   - a hidden `/ui` page that renders every component in both themes, for review (exclude it from the sitemap, and add `robots: noindex`)
2. **Public site**: `PublicShell`, the home page (R-PUB-*), then `/rera*`, `/lawyers*`, `/services`, `/developers` and `/blog*`.
3. **Customer portal**: the `/account` dashboard (R-CUS-1 to 7), `/documents` and `/bookings` in the shell (R-CUS-8), and `/assistant` (R-CUS-9).
4. **Staff workspace**: `AppShell` for `/admin` (R-STF-1), the dashboard (R-STF-2 to 7), then the inner pages (R-STF-8).
5. **Clean-up**: section 10, dead code removal, and the final grep checks.
6. **Mobile tokens (optional)**: export `tokens` as a TS object from `packages/shared` (`theme.ts`: `colors.light`, `colors.dark`, `radius`, `font`), and use it in `mobile/` for colours only.

## 12. Acceptance criteria and verification

**For every PR:**
- `npm install`, `npm run typecheck -w frontend` and `npx next build` (in `frontend/`, with the API running) all pass. Backend tests (`cd backend && pytest`) still pass. They must, since the backend doesn't change.
- Screenshots at 1440×900 and 390×844, in light and dark, of every page the PR touches, attached to the PR. Run the API locally with demo data. The recipe:
  1. `Base.metadata.create_all` + `sync_reference_data`
  2. `python -m app.demo_lawyers`
  3. RERA sample data loads automatically at startup
  4. build Next.js while the API is up
- No horizontal scrolling at 360px on customer-facing pages.
- Keyboard: you can tab through the nav, tabs, buttons and inputs with visible focus. Esc closes menus and sheets.
- Contrast is spot-checked for any new colour pair.

**Feature checks:**
- R-GLB-1: the toggle survives a reload, there is no flash on load, and with no saved value the theme follows the OS setting.
- R-PUB-2: with the API stopped, the home page still renders, using static cards.
- R-CUS-3/4: with a customer who has a request with `needs_you`, a signed report and a meeting today, the tiles show 1/1/time/1. The attention list shows all three, and the bell shows a dot.
- R-CUS-9: the assistant page sends and receives, shows sources, Export downloads a `.txt`, and Clear resets.
- R-STF-4/5: tile numbers match `/admin/reports/summary`, clicking a tile filters the list, and priority badges match each ticket's priority.
- R-STF-6/7: meeting dots match `/admin/meetings`, and Join appears only when `joinable()`.
- Section 10's grep returns nothing (final PR).

## 13. Open decisions (defaults to use until told otherwise)

1. Public hero portraits: use the illustrated tinted panels with silhouettes for now. Switch to real advocate photos only with written consent. The component should accept an image URL so it's a data change.
2. Default theme: follow the OS (`prefers-color-scheme`) when no choice is saved.
3. Staff fee on case cards: hide it until `staff_summary` exposes a fee.

---

## Appendix A: reference designs and what was taken from each

| Reference | Idea used |
|---|---|
| LegalEase, "Injury case management" | Segmented tabs, tinted stat tiles with an icon, case cards with priority badge, amount, date, and Documents/Update actions |
| CaseIQ dashboard | Clean white grouped sidebar with a count badge, airy cards, violet primary |
| LegalSphere, "AI legal assistant" | Top bar with ⌘K search, full-page assistant with Export/Clear, quick actions and tips rail |
| FlowFunds, "Today's priorities" | "Needs attention" cards with the urgent one solid, today's timeline, AI risk summary inside a card |
| Upcounsel, "Expert attorneys, on demand" | Public hero with a big headline and hand-drawn underline, portrait collage with floating info cards, pill buttons, trust strip |
| Vertex Legal | "Good afternoon, Jane" greeting with the date, calendar with event dots, dark mode |

## Appendix B: history

- 2026-11-01: palette-only restyle proposed and rejected ("not colour only, completely different templates").
- 2026-11-01: three home page directions (super-app, dark bento, ask-first) proposed, then superseded by Rajesh's reference images.
- 2026-11-01: Homexo UI defined from the references. Rajesh asked for a complete requirements and design document that any LLM can build from, merged to `main`.
