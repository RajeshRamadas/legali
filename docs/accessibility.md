# Keyboard access and mobile browser checks

The shared public, customer and staff interface supports a **Skip to main
content** link as the first keyboard stop. Each page has one focusable main
landmark, including loading and staff sign-in screens. Pages rendered inside a
workspace use the shell's main landmark rather than nesting another one.

## Navigation and dialogs

- Public mobile navigation focuses its first link when opened. Escape returns
  to the menu button; selecting a link, moving focus away or clicking outside
  closes the disclosure. It remains a navigation region, not an ARIA menu.
- Customer and staff mobile drawers and search use native modal dialogs.
  Background controls are inert, Tab/Shift+Tab remain inside, Escape closes,
  background scrolling pauses, and focus returns to the opener. Resizing to
  desktop dismisses mobile overlays and releases the scroll lock.
- The callback confirmation uses the same dialog behavior and explicitly
  remembers its submit button across the asynchronous disabled/loading state.
- Ctrl+K / Cmd+K focuses workspace search. Notifications expose their expanded
  state, focus their contents on opening and return to the bell on Escape.
- The floating assistant stays nonmodal: it focuses the message input on open,
  offers a close button and returns to its opener on Escape. It does not trap
  focus or disable the rest of the page.
- Reduced-motion preferences disable CSS scrolling/animations and animated
  callback/document jumps. Mobile icon and dialog close controls have at least
  44-pixel touch targets. The lime document-services panel uses dark text for
  readable contrast while retaining the navy/lime visual design.

## Automated browser regression suite

`frontend/tests/browser/accessibility.spec.ts` runs Chromium at 1440, 390 and
320 CSS pixels wide. It checks public home/services and signed-out account,
documents, bookings, guided requests and staff sign-in pages, plus signed-in customer and staff workspace
fixtures. Checks cover main landmarks, skip-link focus, horizontal overflow,
public navigation, callback and sample-report dialogs, assistant dismissal,
drawer/search/notification keyboard behavior, responsive resizing and reduced
motion.

Axe checks the selected WCAG 2 A/AA, 2.1 A/AA and 2.2 AA rules on those pages
and open modal states. Any reported violation fails the test; no rules or page
elements are excluded. Full axe JSON results are attached to the browser report.
The fixtures intercept browser API requests and use synthetic accounts, so these
tests do not send messages, take payments or modify a running database. They
exercise UI behavior; backend authentication/authorization remains covered by
the separate API regression suite.

The existing **Web and shared-client validation** CI job now installs Chromium
and runs the browser suite after the production build. HTML reports, JUnit
results and failure screenshots/traces are retained for seven days. Its check
name is unchanged, so existing branch protection references remain valid.

## Run locally

Use Node 24 and run from the repository root:

```bash
npm ci --ignore-scripts
npm run typecheck
npm run lint --workspace frontend
npm run build --workspace frontend
npm exec --workspace frontend -- playwright install --with-deps chromium
npm run test:browser --workspace frontend
```

The test runner starts the production site on `127.0.0.1:3100` and stops it
afterward. Keep that port free; build before running tests. In a managed cloud
environment with system Chromium already installed, use
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium` for the test command
instead of downloading another browser. Test reports and browser artifacts are
ignored by Git. Reports/traces from fixture runs contain synthetic data; review
them before attaching recordings from any live-data investigation.

## Validation

Local validation on 2026-11-10: 41 browser tests passed, with one mobile-only
case skipped in the desktop project. Workspace type checks, frontend lint
(seven existing warnings), both API-free and normal production builds, and
workflow syntax validation passed. The npm lock audit reports no high/critical
findings; 15 moderate findings remain tracked in `dependency-security.md`.

## Remaining manual checks

Automated checks cover the listed routes and states, not every workflow or all
WCAG success criteria. Before launch, test with screen readers, browser text
zoom, high-contrast settings, real touch devices and Safari/Firefox. Review
document upload/report flows and error/recovery states with representative users.
Native mobile builds remain outside this browser suite.
