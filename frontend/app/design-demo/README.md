# Homexo UI design review demo

Open `/design-demo` in the running Next.js app. This is a demo-only route, excluded from indexing, with four switchable reference screens: public home, customer portal, staff workspace and full-page assistant. Use the theme toggle to review the dark staff design, and Phone view to constrain the viewport to 390 px.

The approved reference HTML/CSS and bundled font from `docs/design/homexo-ui/mockups/` are copied into `frontend/public/demo-ui/`. An iframe keeps these styles separate from the existing application. The small `demo.js` layer adds local interactions: navigation, case tabs/search, notifications, a sample document selector, enquiry confirmation, calendar/consultation previews, scripted chat, transcript export and clear. Fictional case/person data comes from the reference mockups. Files are not uploaded; no backend/API or LLM is called.

The demo uses its own `hx-demo-theme` preference and does not change the live site's theme or screens. Other than that preference, an optional pending demo chat question is stored in sessionStorage and removed when consumed. Chat, selected file and form state are in memory.

This route is for design approval before a production redesign. It does not implement the complete website migration, new authentication, legal verification, bookings or payments. The production phases in section 11 of the design specification remain separate work after approval.

Run from the repository root:

```bash
npm run dev --workspace frontend -- --hostname 0.0.0.0
```

Validation: frontend type check and production build; browser checks of each screen at desktop/phone widths, theme persistence, filters, document picker and scripted assistant interactions.

A standalone HTML gallery is also available at `/demo-ui/index.html`. The same assets can be zipped for review without installing Node or application dependencies. If local file access is restricted by the browser, serve that folder with a static HTTP server and open its `index.html`.
