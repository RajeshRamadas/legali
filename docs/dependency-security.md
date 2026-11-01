# JavaScript dependency security update

The previous Next.js 14 lockfile was flagged by npm audit. The website now uses
Next.js 16.4.3 and React/React DOM 19.3.1. Node.js 20.9 or newer is required;
Node.js 22 or 24 LTS is recommended.

Server pages await route and search parameters; client detail pages use
`useParams`. The removed `next lint` command is replaced by ESLint flat config.
New React Compiler refactoring rules are disabled for existing code; normal
Next.js and Hooks checks remain enabled.

Compatible transitive security patches were applied with `npm audit fix`.
Expo stays on SDK 58; its status bar and React Native versions were aligned
with the installed SDK's bundled compatibility data. Expo's online compatibility
service was blocked by the cloud network policy, so the SDK check ran offline.
Native iOS/Android builds have not been run.

## Remaining audit findings

The audit still reports moderate findings in the `glob` / `minimatch` dependency
chains used by Expo and ESLint. As checked on 2026-11-01, the full workspace audit reports 26 moderate
findings and no low, high or critical findings; these counts include dependent
packages in the same affected chains. The frontend production-only audit
reports one moderate `minimatch` finding in the shared workspace lockfile.
Neither result is a zero-vulnerability claim. Do not run `npm audit fix --force`: npm
proposes downgrading Expo to SDK 51 and ESLint to version 4. Forcing new major
versions of transitive glob libraries also needs compatibility testing.

These findings remain open; an audit result is not proof that every reported
attack is reachable in this application. Recheck upstream compatible releases
and run `npm audit` regularly.

## Local update

```bash
npm ci
npm run typecheck
npm run lint --workspace frontend
npm run build --workspace frontend
npm run web
```

The startup process for Docker database/API services is unchanged. API keys
stay in the backend environment, never in `NEXT_PUBLIC_` variables.

## Validation

- All workspace TypeScript checks and Next.js production build pass.
- Frontend ESLint passes with eight existing warnings (images, Hooks dependencies,
  and unused disable comments); new React Compiler refactor checks are disabled.
- Chromium smoke checks cover public, customer, staff, assistant, blog/RERA query
  pages, payment query handling, lawyer detail routing, and mobile overflow.
- Expo SDK dependency check passes offline; native builds remain untested.
