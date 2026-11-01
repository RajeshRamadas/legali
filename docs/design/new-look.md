# New look and feel: design and implementation plan

Status: **draft. Choosing a direction.** Nothing merges to `main` until Rajesh approves.

The first sample (PR #19, first commit) only re-coloured the existing layout. Rajesh wants a **completely different template**: new page structure, new components and a new feel, not just new colours. This doc offers three distinct directions. Rajesh picks one, then the chosen direction gets built into the real site.

Mockups (static HTML, open in a browser): `mockups/new-look/` in the project files. Screenshots: `screenshots/new-look-directions/` (`compare-desktop.png`, `compare-mobile.png`, plus full pages).

## Why the current site feels old

- Long single-column marketing page with ten stacked sections that all look the same (eyebrow, serif heading, paragraph, cards).
- Georgia serif headings, forest green and gold, cream background: reads like a traditional law office.
- Small text (9-12 px), thin borders and flat cards, so nothing looks tappable.
- A crowded header with eight items that wrap at laptop widths.

## The three directions

### A. Super-app (like Practo, Urban Company, Swiggy)
*"Property legal help, one tap away."*
- **Structure:** top bar with city picker and a global search; a hero card with a grid of 8 colourful service icons (RERA check, lawyer, verify, affidavit, EC, RTC/khata, deeds, Ask AI) next to two big promo banners ("Free RERA check", "Consult from ₹800"); "Lawyers free today" cards with time-slot chips and Book buttons; package cards with the popular one in black; a phone mockup showing the case tracker; slim footer.
- **Mobile:** a fixed **bottom tab bar** (Home, Lawyers, RERA, Track, Account), so the site feels like an app and matches the Expo mobile app.
- **Feel:** bright white, royal blue `#1b4dff` and sunshine yellow `#ffd23f`, DM Sans, big rounded tiles.
- **Best for:** first-time buyers on phones who want to tap a service immediately. Easiest for mass audiences.

### B. Dark bento (like Linear, Apple, modern fintech)
*"Buy property without the legal maze."*
- **Structure:** huge headline with outlined and neon words, search on the right; a **bento grid** of mixed-size live tiles: a large RERA risk tile with a real project card and risk bar, lawyers (avatar stack and "from ₹800"), an AI chat preview, a live case tracker, a neon "Shield Pro ₹9,999" tile, then documents, affidavits and developers; a scrolling strip of localities; outlined 01/02/03 steps; a neon closing banner.
- **Feel:** near-black `#07080c`, neon lime `#c6ff3d` and violet accents, Space Grotesk. Premium and techy.
- **Best for:** standing out from every other legal site and signalling "tech-first". Riskier for older visitors, since dark sites can feel less familiar.

### C. Ask-first (like Perplexity or ChatGPT, with an editorial style)
*"What do you want to know about this property?"*
- **Structure:** a centred hero that is one big **ask box** with mode chips (Ask, Check RERA, Find a lawyer, Verify, Get a document) and suggested questions; an example answer with sources and a "Book an advocate" hand-off; services as a large numbered editorial list (01-05 with prices); advocate cards with large monogram photos; a dark olive "One number. Every step." band; a giant wordmark footer.
- **Feel:** warm paper `#f4f1ea`, ink black, signal orange `#ff5b29`, Instrument Serif headlines with Inter body. Calm and confident.
- **Best for:** putting the AI assistant and RERA data front and centre. It makes the product feel smart rather than like a directory.

| | A Super-app | B Dark bento | C Ask-first |
|---|---|---|---|
| First thing users do | Tap a service icon | Scan live tiles | Type a question |
| Mood | Friendly, mass-market | Premium, techy | Calm, intelligent |
| Mobile | App-like bottom tabs | Stacked tiles | Big ask box |
| Matches mobile app | Closely | Partly | Partly |
| Build effort | Medium | Medium-high | Medium |

**Recommendation: A (Super-app).** Most buyers arrive on phones and want to tap a service, not read. It matches the Practo-style lawyer booking already built, and the bottom tab bar lines up with the Expo app. Parts of C can still be used: the ask box can become the "Ask AI" icon's full-screen view.

## Implementation plan (once a direction is chosen)

This is a new template, so it is a rebuild of the presentation layer, not a re-skin. Data loading, APIs and behaviour stay the same.

1. **Design tokens and font**: one `tokens.css` (colour, type scale, radius, shadow, spacing), with the font self-hosted via `@fontsource`. Remove the old forest/gold tokens and the Georgia `serif` class.
2. **Shared components** in `frontend/app/ui/`: `TopBar` (search, city, account), `BottomTabs` (mobile, for direction A), `ServiceGrid`, `PromoCard`, `LawyerCard` (with slot chips), `PackageCard`, `CaseTracker`, `Section`, `Button`, `Chip`, `Footer`. These replace `SiteHeader`, `SiteFooter` and the per-page card markup.
3. **Home page**: rewrite `page.tsx` around the new structure, reusing today's data loaders (RERA summary, lawyers, posts) and the existing client islands (`HomeHero` tabs become the service grid or ask box, `CallbackSection`, `ChatWidget`).
4. **Inner pages**, one PR each, in this order: `/lawyers` and lawyer profile, `/rera` (search, project, locality, developer), `/documents` and the journey, `/bookings` and `/account`, `/services` and `/developers`, `/blog`. Then the admin screens get the new tokens only (layout unchanged).
5. **Mobile app**: share the tokens through `packages/shared` so the Expo app uses the same colours and type.
6. **Checks for each PR**: `npm run typecheck`, `next build` with the API running, desktop (1440) and mobile (390) screenshots of every changed page, WCAG AA contrast on text, keyboard focus states, and no layout shift from fonts.

Estimated effort: home page and shared components about 2-3 days; inner pages about 4-6 days; mobile token sharing about 1 day.

## Questions for Rajesh

1. Which direction: A, B or C (or A with C's ask box)?
2. Keep the name and "H" mark, or design a new logo too?
3. Staff/admin screens: new layout this round, or tokens only?
