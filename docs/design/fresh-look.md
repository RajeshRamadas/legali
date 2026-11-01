# Fresh look: design and implementation plan

Status: **draft for review**. The home page sample is on branch `claude/project-thread-3b540n`. Nothing merges to `main` until Rajesh approves.

## 1. Why

The current site reads as old-fashioned:

- **Georgia serif headings** with forest green, gold and cream feel like a traditional law office, not an app people use from their phone.
- **Tiny text**: much of the copy is 9 to 12 px (footer links, labels, form notes), which looks dated and is hard to read on mobile.
- **Flat, boxy surfaces**: thin borders, small radii and few shadows, so nothing feels tappable.
- **Cramped header**: menu labels wrap onto two lines at laptop widths ("RERA / check", "Find a / lawyer").
- **Heavy dark-green bands** (stats, footer, call to action) break the page into slabs.

The goal is a look that feels like a modern consumer app (think UPI and fintech apps people already trust), so first-time visitors stay, while keeping the content, flows and structure that already work.

## 2. Design direction: "bright, confident, trustworthy"

| | Before | After |
|---|---|---|
| Type | Georgia serif headings, Inter body | **Plus Jakarta Sans** (self-hosted variable font) for everything; headings 800 weight with tight tracking |
| Primary colour | Forest green `#123b35` | **Indigo `#4f46e5` → violet `#7c3aed`** gradient |
| Accents | Gold `#d6ad66` | Cyan `#06b6d4` (highlights), saffron `#ff8a3d` ("most chosen", attention), green `#12a87a` (success only) |
| Background | Cream `#f7f5ef` | Cool off-white `#f6f7fb` and white, alternating per section |
| Dark surfaces | Forest green | Midnight `#0b1026` with soft violet/cyan glows |
| Buttons | 9 px radius, flat | Pill-shaped, gradient fill, soft coloured shadow, lift on hover |
| Cards | 13-18 px radius, thin border | 16-28 px radius, light border, layered shadow, lift on hover |
| Text size | 9-13 px common | 12 px minimum, 14-16 px body, 18 px hero copy |

### Key moves on the home page

1. **Hero**: white canvas with a soft "aurora" (blurred indigo, violet, cyan and saffron glows) and a faint grid; the headline's key phrase *easy steps* in gradient text; the eyebrow becomes a pill badge; the task launcher becomes a frosted card with segmented tabs.
2. **Journey card**: frosted glass with a glow behind it; the live step ("Call with your advocate") highlighted with a gradient ring; the tilted gold sticky note becomes a clean floating chip.
3. **Stats**: the dark band becomes four floating white cards overlapping the hero, numbers in gradient text.
4. **Steps**: gradient number badges; cards lift on hover.
5. **Service tiles**: each tile gets its own colourful gradient icon, so the grid scans quickly.
6. **Lawyers, packages, blog**: rounder cards, gradient avatars, the popular package highlighted with an indigo edge.
7. **Developer band and final call to action**: midnight band with glows, and a full gradient card for the last call to action.
8. **Header and footer**: frosted sticky header with pill hover states and no wrapping; midnight footer with readable 14 px links.
9. **Chat assistant**: midnight button with a gradient icon; user messages in the brand gradient.

Accessibility is kept: text colours meet WCAG AA contrast on their backgrounds (gradient ends were darkened so white button text and large gradient headings still pass), focus rings are visible (2 px indigo), and green stays reserved for "done / safe" states so it still means something.

Screenshots: `screenshots/fresh-look/` in the project files (before/after, desktop and mobile).

## 3. How it is built

The change is mostly CSS, so it is low risk and easy to roll back.

- `frontend/app/theme.css` (new, loaded in `layout.tsx` after `globals.css`): the design tokens plus shared components (buttons, header, forms, FAQ, call to action, footer, chat).
  - New semantic tokens: `--brand`, `--brand-2`, `--brand-3`, `--accent`, `--success`, `--night`, `--surface*`, `--text*`, `--border`, `--radius*`, `--shadow-*`, `--gradient`, `--font`.
  - The **old token names** (`--forest`, `--gold`, `--mint`, `--cream`, …) are re-pointed at the new palette, so every page changes colour immediately without touching its CSS.
  - The `.serif` class now means "bold display sans", which converts all 28 serif headings in one line.
- `frontend/app/home-fresh.css` (new, imported by `page.tsx` after `home.css`): the home page styles above.
- `@fontsource-variable/plus-jakarta-sans`: font files bundled with the site (no Google Fonts call, works offline, no privacy concern).
- No changes to page markup, data loading or behaviour in the sample.

## 4. Rollout plan (after approval)

**Phase 1: home page and shared chrome** (the sample, about 1 day to finish)
- Polish anything Rajesh asks for in review.
- Check every breakpoint (1440, 1180, 980, 740, 390 px) and the chat panel, modals and toasts.

**Phase 2: every other page** (about 2-3 days)
Token remapping already recolours them, but the page CSS still has around 200 hard-coded greens, some Georgia headings and small font sizes (see the `/lawyers` screenshot). For each file, replace hard-coded colours with tokens, drop Georgia, raise minimum text size to 12 px and round the cards:
`lawyers.css`, `rera/rera.css`, `documents/*.css`, `blog/blog.css`, `account/account.css`, the `/services`, `/developers` and `/bookings` pages, then `admin/admin.css` and `admin/verification.css` (staff screens, lower priority).

**Phase 3: tidy up**
- Fold `theme.css` into `globals.css` and remove the old token aliases once nothing uses them.
- Remove the ~60 inline `style={{…}}` colours in components.
- Bring the mobile app (`mobile/`) onto the same palette and font so web and app match.

**Checks for each phase**: `npm run typecheck`, `next build`, screenshots of each page at desktop and mobile widths with live API data, and a contrast check on any new colour pair.

## 5. Open questions for review

1. Colour: is the **indigo/violet** direction right, or would you prefer a variant (for example teal/blue, or keeping a touch of green to stay close to the current brand)?
2. Logo: the "H" mark now uses the gradient. Do you want a new logo as part of this, or keep the text mark?
3. Should staff/admin screens get the new look in this round, or only customer-facing pages?
