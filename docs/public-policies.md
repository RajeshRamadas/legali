# Public policies and accountable contact details

The website has a policy centre at `/policies`, with public pages for privacy,
terms and grievance/contact information. The footer links to all three. An
administrator manages their private drafts and publication history under
**Public policies** (`/admin/policies`). Agents and customer accounts cannot
access drafts, history or publication commands.

There are no seeded legal policies or invented contact details. Empty or
withdrawn policies show an unpublished state and existing support/privacy/callback
routes. An API outage shows an availability error and retry control, rather than
claiming a policy is unpublished or showing a draft. Publication requires the
organization's reviewed wording and real contacts; this feature does not provide
legal advice or establish statutory compliance.

## Prepare and publish

1. Choose Privacy notice, Terms of service or Contact & grievance.
2. Enter the title, summary, Markdown text, organization and public contact email.
   Phone and postal/contact fields are also available. Contact & grievance needs
   an accountable contact name and postal address before publication.
3. **Save private draft**, then preview the text and contact details. Drafts may
   be incomplete; saving never changes the public version.
4. Confirm that the saved version and contact details have been reviewed and
   approved for public publication, then **Publish reviewed version**. Unsaved
   changes disable publication. The server also enforces the review confirmation
   and required content/contact checks.

Publication needs a title of at least five characters, summary of at least 20,
body of at least 100 and organization name of at least three. Placeholder email
domains, malformed email/phone fields and control characters are refused. These
are format checks, not verification of a contact's identity or deliverability.
The responsible owner must review scope, applicable deadlines, escalation paths,
data processing and retention statements before publishing.

Each publication creates a numbered snapshot with its publication timestamp and
administrator identity in the database. Existing snapshot text is never edited
by these APIs. Later edits require a new draft and publication. Old public
versions have stable links such as `/policies/privacy?version=1`; current pages
link to their exact version. Published timestamps describe publication, not a
legal effective-date conclusion. State any applicable effective dates in the
reviewed policy text.

## Conflicts, history and withdrawal

Draft saves, publication and withdrawal use a revision and database row lock.
Concurrent/stale commands return 409 rather than overwriting another review or
creating a duplicate publication. The editor keeps unsaved text after an error.
**Reload latest (replaces editor text)** explicitly replaces it with saved data.
If a network outcome is uncertain, reload and check the current version/history
before starting another publication.

Administrator history is paginated ten versions at a time. An earlier snapshot
can be copied into the editor, saved as a new draft and reviewed for a new
publication. It does not directly republish or overwrite the original snapshot.

**Withdraw public policy** requires a private reason and explicit confirmation.
It removes the current policy and all its previously public versions from new
public API/page requests. Snapshots remain in administrator history. Publishing
a later version does not reactivate withdrawn versions; numbering continues.
Readers' downloaded, copied or already displayed information cannot be recalled.

Policy read responses use `Cache-Control: no-store`, and server-rendered policy
pages fetch without caching. The browser refreshes the policy after hydration and
removes it if it is no longer available. Public responses include only publication
number/time and approved content, not draft text, reviewer identities, revisions
or withdrawal reasons. Markdown renders React elements rather than raw HTML;
policy images are omitted so reading a policy does not load image beacons.

## Relationship to other workflows

This centre publishes information; it does not record customer acceptance, change
existing guided-intake/privacy notice versions, alter saved consent records, send
policy-update messages, grant private-record access, resolve complaints or perform
deletion/refunds. Review whether a policy change needs a separate customer notice
or consent process. Existing operational targets are not statutory deadlines.

The [support desk](customer-support.md) and [privacy request workflow](privacy-and-retention.md)
retain their verified-account checks. Customer case/support records and internal
notes are never inserted into a policy automatically. Published contacts should
be intentionally public organization contacts, not customer/private case data.
Policy drafts, snapshots and audit records are included in database backups;
anonymous-chat cleanup does not delete them. Audit metadata stores actions,
kind, revision and version counters without copying policy text or contact fields.

## API and migration

| Method | Route | Access / behavior |
| --- | --- | --- |
| GET | `/api/v1/policies` | Public; three fixed kinds with availability and current published content |
| GET | `/api/v1/policies/{kind}` | Public; current version or generic 404 |
| GET | `/api/v1/policies/{kind}/versions/{number}` | Public; visible historical snapshot or generic 404 |
| GET | `/api/v1/admin/site-policies` | Administrator; current heads, private drafts and revision values |
| PUT | `/api/v1/admin/site-policies/{kind}/draft` | Administrator; `{revision, content}` |
| POST | `/api/v1/admin/site-policies/{kind}/publish` | Administrator; `{revision, reviewed: true}` |
| POST | `/api/v1/admin/site-policies/{kind}/withdraw` | Administrator; `{revision, reviewed: true, reason}` |
| GET | `/api/v1/admin/site-policies/{kind}/versions?page=1` | Administrator; paged history, including withdrawn snapshots |

Kinds are `privacy`, `terms` and `grievance`. Content fields are `title`, `summary`,
`body`, `organization`, `contact_email`, `contact_phone`, `postal_address` and
`grievance_officer`; unknown fields are rejected. Existing shared API lookup/write
budgets protect administrator commands.

Apply migration `0025_site_policies` with `python -m alembic upgrade head` from
`backend` before running the updated API. It adds two tables without publishing
or seeding policies. A downgrade removes policy drafts/history; preserve required
records before rollback. No new dependencies or provider credentials are needed.

## Validation (2026-11-10)

- Full SQLite API suite: **506 passed, 16 skipped**. PostgreSQL policy regressions:
  **17 passed**, including two concurrent publications producing one snapshot.
- PostgreSQL migration up/down/up preserved a nonempty existing account. The
  dedicated test database and limited role were removed afterward.
- Full browser suite at 1440, 390 and 320 pixels: **62 passed, one inapplicable
  desktop case skipped**. New checks cover private drafts, safe public rendering,
  publication/review, withdrawal, version links and conflict recovery with axe.
- Workspace type checks, frontend lint and production builds pass. Lint retains
  seven existing warnings. Browser fixtures are synthetic; no real policy was
  published by the implementation/validation work.

Publish reviewed information and assign its maintenance owner before launch.
The deployment configuration preflight does not review or publish site policies.
