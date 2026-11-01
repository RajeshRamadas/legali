# Legal-tech homepage adaptation

Requested reference: https://www.spotdraft.com/. Direct inspection returned HTTP
403 under this environment's network policy, so the reference site's current
layout, colours and interactions could not be verified. This implementation is
an original legal-tech interpretation for Homexo's property-review workflows.

## Design

- Warm ivory, ink, lavender and citron accents, with large editorial headings.
- A central interactive workspace replaces the architectural-photo hero.
- Five real, keyboard-accessible preview tabs: documents, ownership chain,
  cross-document comparison, legal context and advocate review.
- Each tab changes the evidence panel and review insight. The persistent sample
  label and disclaimer distinguish fictional examples from a customer's case.
- Supporting workflow, services, RERA search, packages, advocates, intake,
  tracking, insights and FAQ sections share the new palette.
- Styles remain scoped to the homepage. Other routes and customer/staff
  workspaces retain their existing layout and theme.

## Behavior

The existing title-verification intake action, package selection, sample-report
dialog, assistant and public routes remain connected. The preview uses local
state and sends no uploaded documents or API requests. The legal examples name
illustrative statutes and explicitly leave applicability/current-law review to
the advocate; they do not issue a legal opinion.

No backend, schema, dependencies, secret configuration or environment publication
changes are included. No external images, tracking scripts, fonts or reference-site
assets were added.

## Validation

- All workspace TypeScript checks and production Next.js build pass.
- Frontend ESLint passes, with eight existing warnings and no errors.
- Chromium checks at 1440, 1024, 768, 701, 700, 390 and 360 pixels exercise all five
  panels without page-level horizontal overflow.
- Arrow/Home/End navigation, report-dialog focus, intake/package selection,
  light/dark theme, mobile navigation/Escape and RERA search are checked.
- Route navigation removes the homepage palette; no client exceptions were seen.
- Safari and Firefox have not been checked.

## Screenshots

- [Desktop, light](home-light-1440.png)
- [Desktop, dark](home-dark-1440.png)
- [Mobile, light](home-light-390.png)
- [Mobile, dark](home-dark-390.png)
- [Cross-document example](cross-checks.png)
- [Legal-context example](legal-context.png)
- [Full homepage](home-light-1440-full.png)

For local preview, use Node.js 24.3+ (the mobile workspace's Metro dependency
requires a newer version than the frontend alone), then run `npm ci` and
`npm run web`. Open http://localhost:3000. See the root README for the database
and API startup instructions needed for actual customer requests.
