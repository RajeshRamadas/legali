# Security and privacy checklist

- [ ] Never commit API keys, `.env`, database dumps or customer documents.
- [ ] Use managed secrets and rotate credentials.
- [ ] Implement authentication, MFA for admins, RBAC and least privilege.
- [ ] Verify identity/ownership before exposing ticket data or files.
- [ ] Use TLS everywhere outside local development.
- [ ] Keep CORS restricted to known frontend origins.
- [ ] Rate-limit public intake, login, uploads and AI endpoints.
- [ ] Validate file type by content, size, extension and malware scan.
- [ ] Store documents in private object storage; use expiring signed URLs.
- [ ] Do not place personal data or document contents in application logs.
- [ ] Encrypt backups and test restores.
- [ ] Define retention, deletion, access request and incident response procedures.
- [ ] Record consent notice version, purpose and timestamp.
- [ ] Separate internal notes from customer-visible messages.
- [ ] Audit status changes, assignments, exports and permission changes.
- [ ] Review privacy, consumer protection, professional-service and government-record access requirements with qualified counsel.
- [ ] Test authorization failures, IDOR, prompt injection, upload abuse and data leakage.
