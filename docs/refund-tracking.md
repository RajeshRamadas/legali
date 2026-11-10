# Refund tracking

Administrators can open **Refund tracking** at `/admin/refunds` to review payments needing action, pending refunds, completed refunds and records requiring investigation. Search accepts a case number, provider order or payment reference. Each view and history is paginated. Internal follow-up notes use revision checks; a conflict keeps the editor text until the administrator explicitly reloads. Agents and customers cannot read or edit this queue or its notes.

## Provider configuration and workflow

Keep refund initiation in the Razorpay dashboard. This feature does not call the provider refund API or move money. Configure the existing signed webhook endpoint `/api/v1/payments/razorpay/webhook` for `refund.created`, `refund.processed` and `refund.failed`, in addition to payment events. Configure `RAZORPAY_WEBHOOK_SECRET` and verify delivery in the provider dashboard. The handler caps request bodies at 128 KiB and retains the existing exemption from shared client request budgets.

Amounts use integer paise. Pending and failed refunds do not count as returned money. Distinct processed refund IDs accumulate; only a processed total equal to the payment amount marks it fully refunded. Duplicate deliveries do not add money twice. Late pending or failed events cannot downgrade a processed refund. Customer booking and account payment summaries show partial amounts, processing amounts or a review message; they do not promise a settlement date.

Refunds arriving before a matching payment are retained in **Unmatched provider refunds**. Recording or re-verifying the captured payment attaches matching events. PostgreSQL transaction advisory locks and row locks serialize capture and refund deliveries; a unique provider refund ID prevents duplicate ledger entries. Contradictory identity, currency, amounts, excessive totals or ambiguous payment references require investigation. The previously confirmed amount is retained while the summary is under review. A failed refund may be followed by a processed event; confirm the provider outcome before initiating any replacement refund.

## Migration and historical records

Run `alembic upgrade head` from `backend/` before starting the updated API. Migration `0026_refund_tracking` adds refund totals and the ledger. Earlier code marked partial refunds fully refunded, so every existing payment with status `refunded` receives `legacy_unverified`; its historical refund amount is deliberately left unknown. Replayed events do not automatically clear that warning. Compare provider records and establish a reviewed operational reconciliation before relying on historical totals. This release provides no administrator override or bulk provider reconciliation command. Notes do not clear review flags or establish settlement.

Back up the database before migration. Downgrading removes the ledger and its notes; preserve those records separately before rollback. Payment and case records remain. Ledger and note retention follows database backup and privacy procedures; audit events record status, revision and amount, excluding note contents and raw provider payloads. Limit note contents to necessary operational information.

The queue tracks every payment attempt separately. The existing customer booking summary selects one settled attempt; it is not an all-attempt financial statement. GST invoices, in-app refund initiation and automated reconciliation against the provider dashboard remain separate work.

## Validation

Run `pytest tests/test_refunds.py tests/test_payments.py tests/test_abuse_protection.py` from `backend/`. SQLite covers signatures, malformed events, exact partial totals, duplicate and out-of-order delivery, review conditions, unmatched attachment, authorization and private revision-protected notes. Use a disposable `TEST_DATABASE_URL` for PostgreSQL concurrency checks; test fixtures drop all application tables. Browser regressions in `frontend/tests/browser/refunds.spec.ts` use synthetic API responses across desktop, mobile and narrow screens, including accessibility and preservation of conflicting edits. No live refund is needed for these checks.
