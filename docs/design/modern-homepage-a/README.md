# Modern professional homepage — Concept A

Archived visual direction. The newer [legal-tech homepage](../legal-tech-homepage/README.md) replaces this design.

Implements the approved white-and-blue visual concept for the public homepage.
The homepage has a simpler navigation, a property-document review hero, a
three-step workflow, service cards, RERA search, package comparison, advocate
cards, intake, tracking, insights and FAQs.

## Behavior

- **Start property review** selects the existing title-verification service,
  scrolls to the intake form and focuses the name field.
- **See a sample report** opens an illustrative report in a native dialog. Escape
  closes it, Tab/Shift+Tab stay within the dialog, and focus returns to the trigger.
  Its CTA opens the actual intake form. The fictional example is clearly labelled.
- Package buttons retain the service/package selection and existing callback flow.
- RERA search, document uploads, request tracking, assistant and advocate links
  use the existing routes and APIs. Live data and its sample-data notice remain
  connected, with useful links when the API is unavailable.
- The new palette is scoped to `.hx-home-public` on `/`; other public routes and
  customer/staff workspaces retain their existing design. Light and dark modes work.
- The architectural image is AI-generated decorative imagery, hosted locally as
  a 116 KB WebP. The review interface, text and paper illustrations are HTML/CSS,
  not a screenshot used as a page background.

## Review screenshots

- [Desktop, light](home-light-1440.png)
- [Desktop, dark](home-dark-1440.png)
- [Mobile, light](home-light-390.png)
- [Mobile, dark](home-dark-390.png)
- [Sample report](sample-report.png)
- [Full homepage](home-light-1440-full.png)

## Validation

- Production Next.js build and all workspace TypeScript checks pass.
- Frontend lint passes with eight pre-existing warnings; no new lint errors.
- Chromium checks at 1440, 1024, 768, 390 and 360 pixels: no horizontal overflow.
- Browser checks cover the sample dialog's keyboard behavior and focus return,
  title-verification/Pro intake selection, light/dark theme switching, mobile menu
  opening/Escape, RERA search, and route-scoped theme cleanup. No client exceptions.
- Backend code and database schemas are unchanged. Native mobile UI, Safari and
  Firefox were not part of this homepage validation.

Run locally from the repository root with `npm ci` and `npm run web`, then open
http://localhost:3000. Use the backend/Docker instructions in the main README
for live account, request and document workflows.
