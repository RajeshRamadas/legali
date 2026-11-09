# Security and privacy checklist

- [ ] Never commit API keys, `.env`, database dumps or customer documents.
- [ ] Use managed secrets and rotate credentials.
- [ ] Implement authentication, MFA for admins, RBAC and least privilege.
  Staff password recovery and MFA are implemented; configure and verify the deployment policy in [staff security](staff-security.md).
- [ ] Verify identity/ownership before exposing ticket data or files.
- [ ] Use TLS everywhere outside local development.
- [ ] Keep CORS restricted to known frontend origins.
- [ ] Rate-limit public intake, login, uploads and AI endpoints.
  Shared API budgets, request-size caps and callback-form honeypots are implemented; tune limits, verify trusted-proxy settings and schedule cleanup for deployment ([API abuse protection](api-abuse-protection.md)). Existing staff sign-in and customer OTP account limits remain in place.
- [ ] Validate file type by content, size, extension and malware scan.
- [ ] Store documents in private object storage; use expiring signed URLs.
- [ ] Do not place personal data or document contents in application logs.
- [ ] Encrypt backups and test restores.
  Encrypted database/document backup and empty-target recovery tooling is implemented; configure scheduling, separate off-host copies/key escrow and periodic recovery drills before checking this off ([backup runbook](backups.md)).
- [ ] Define retention, deletion, access request and incident response procedures.
  Verified privacy requests, administrator decisions and guarded anonymous chat cleanup are implemented; review business-record retention/fulfillment, legacy holds and scheduling before enabling deletion ([privacy and retention](privacy-and-retention.md)).
- [ ] Record consent notice version, purpose and timestamp.
- [ ] Separate internal notes from customer-visible messages.
- [ ] Audit status changes, assignments, exports and permission changes.
- [ ] Review privacy, consumer protection, professional-service and government-record access requirements with qualified counsel.
- [ ] Test authorization failures, IDOR, prompt injection, upload abuse and data leakage.
  Automated dependency/source checks and full SQLite/PostgreSQL API regressions are implemented. Require the workflow checks before merging, review retained reports and track the open moderate npm findings; broader manual security testing remains necessary ([dependency security](dependency-security.md)).
