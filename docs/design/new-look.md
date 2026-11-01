# Homexo UI: one look and feel for the whole web app

Status: **draft for Rajesh's approval.** Nothing merges to `main` until he approves.

## What changed in the brief

1. The first sample only re-coloured the old layout. Rajesh wanted new templates, not just new colours.
2. Three separate home page directions were tried next. They are now superseded.
3. Rajesh shared seven reference designs (LegalEase, CaseIQ, LegalSphere, FlowFunds, Upcounsel, Vertex Legal in light and dark). He asked for **one uniform GUI** across the web that takes the best of them.

This doc defines that system. It is called **Homexo UI**, and it covers four screen types that today all look different:

| Screen | Today | Homexo UI | Mockup |
|---|---|---|---|
| Public site (home, RERA, lawyers, packages) | Long serif marketing page | Upcounsel-style hero: big sans headline with an underline accent, floating lawyer, price and status cards, ask box, trust strip, service cards | `1-public-home.html` |
| Customer portal (`/account`, `/documents`, `/bookings`) | Separate pages, top links only | Left sidebar app shell, "Good afternoon, Asha", stat tiles, "Needs your attention", request cards with progress, AI assistant panel, upcoming calls | `2-customer-dashboard.html` |
| Staff workspace (`/admin`) | Dark green sidebar, plain table | Same shell, greeting, segmented tabs, stat tiles, case cards (priority badge, fee, stage, Documents/Update), calendar with call dots, today's timeline | `3-staff-workspace.html` |
| AI assistant | Floating chat bubble only | Full page chat with sources, lawyer hand-off card, quick actions and tips rail | `5-ai-assistant.html` |

The whole system also comes in **dark mode** (`4-staff-workspace-dark.html`), switched by the sun icon in the top bar, as in the Vertex reference.

Screenshots: `screenshots/homexo-ui/` in the project files (`overview-desktop.png`, `overview-mobile.png`, plus full pages for each screen). Mockups: `mockups/homexo-ui/`. They open in any browser.

## What we took from each reference

| Reference | Idea used |
|---|---|
| LegalEase (injury cases) | Segmented tabs; tinted stat tiles with icons; case cards with name, priority badge, amount, date, Documents and Update actions |
| CaseIQ | Clean white sidebar with grouped sections and a count badge; light, airy cards; violet primary colour |
| LegalSphere (AI assistant) | Top bar with ⌘K search; full page assistant with export/clear, a quick-actions rail and tips |
| FlowFunds | "Needs attention" cards, with the most urgent one in a solid colour; today's timeline; AI risk summary inside a card |
| Upcounsel | Public hero: large headline with a hand-drawn underline, photo collage with floating info cards, two pill buttons, trust strip |
| Vertex Legal | "Good afternoon, Jane" greeting with the date; calendar with dots on busy days; dark mode |

## Design system

- **Font:** Plus Jakarta Sans everywhere (self-hosted). Headings 700-800 with tight tracking. No serif.
- **Colours:** violet primary `#6d4aff`; ink `#0f1222`; page `#f5f6fa`; white cards. Status colours are reserved for meaning: green done/ready, amber waiting/medium, red urgent/high risk, blue scheduled/info, pink documents. The public site uses a warm off-white `#f7f5f0` background so it feels friendlier than the app.
- **Dark mode:** the same tokens re-defined under `[data-theme="dark"]` (page `#0c0e17`, cards `#151826`).
- **Shape:** cards 22 px radius, inner items 16 px, buttons 12 px (pill on the public site). Soft two-layer shadows.
- **Components** (one set, used on every screen): App shell (sidebar + top bar), Page header (greeting, date, actions), Tabs, Stat tile, Card with header, Case card, Attention card, Timeline, Calendar, AI panel (chat, chips, input), List row, Badge, Chip, Button, Icon button, Mobile bottom tabs.
- **Mobile:** the sidebar collapses. The customer portal gets a bottom tab bar (Home, Requests, Ask, Docs, Account), matching the Expo app.
- **Accessibility:** text meets WCAG AA contrast in both themes, focus rings are visible, and every icon button has a label.

## Implementation plan (after approval)

The presentation layer is rebuilt. APIs, data loading and behaviour stay as they are.

1. **Tokens and base**: `frontend/app/ui/tokens.css` (light and dark), the font via `@fontsource-variable/plus-jakarta-sans`, and a theme toggle that is saved per browser. Retire the forest/gold tokens, the Georgia `serif` class and the restyle layer from the first sample.
2. **Component library** in `frontend/app/ui/` (React + CSS modules): `AppShell`, `Sidebar`, `TopBar` (⌘K search), `PageHeader`, `Tabs`, `StatTile`, `Card`, `CaseCard`, `AttentionCard`, `Timeline`, `MiniCalendar`, `AssistantPanel`, `Badge`, `Button`, `BottomTabs`. Each one replaces the hand-written markup currently repeated across pages.
3. **Public site** (PR 1): new `SiteHeader`, hero, trust strip, service cards, footer; then `/rera`, `/lawyers`, `/services`, `/developers` and `/blog` on the same components.
4. **Customer portal** (PR 2): a new `/account` dashboard ("Good afternoon"), with `/documents`, `/bookings` and the document journey inside the app shell, and a full page `/assistant` built from the existing chat API.
5. **Staff workspace** (PR 3): `AdminShell` becomes the shared shell, plus a dashboard home, tabbed ticket queue with case cards, calendar and timeline; then the ticket page, verification, team, profile, blog editor and fetches.
6. **Mobile app**: export the tokens through `packages/shared` so the Expo app uses the same colours and type.
7. **Checks for every PR**: `npm run typecheck`, `next build` with the API running, screenshots at 1440 px and 390 px in light and dark, contrast checks, keyboard navigation.

Rough effort: tokens and components 2 days; public site 2 days; customer portal 2-3 days; staff workspace 3 days.

## Questions for Rajesh

1. Approve this system (violet, Plus Jakarta Sans, sidebar app shell, light and dark)?
2. For the public hero, should we use real photos of your advocates (with their consent), or keep the illustrated cards?
3. Should dark mode follow the device setting by default, or start light?
