# Customer documents and legal reports

Every ticket has a document repository and, once the lawyer starts it, a legal report.

## Flow

1. **Customer shares documents.** On `/documents` (or from the tracking card, "Open"), with the ticket number and the phone or email they used, the customer uploads files and tags each one, e.g. `#sale-deed`. Tags are lowercase words joined by hyphens.
2. **Lawyer writes the preliminary report** on the ticket in `/admin` ("Documents and legal report"). It has fixed sections (property details, scope, preliminary observations, what we need from you) and a checklist of documents. The checklist starts from a standard list for the property type (`backend/app/report_templates.py`); the lawyer edits, reorders, removes or adds items. Each item gets a tag (`sale-deed`, `ec`, or one made from the label, e.g. `gift-deed-from-father`) that never changes once saved.
3. **Issue to customer.** The customer is notified and the ticket moves to "Waiting for your reply". They see the checklist with each tag, upload against an item, or retag earlier uploads to link them. An item moves to "Received" as soon as a file is filed under its tag. The preliminary report is also a printable PDF.
4. **Public records are fetched by Homexo.** Items like the EC, khata, tax receipts, RTC, mutation, survey sketch and RERA certificate are marked "Homexo fetches" by default, so the buyer needn't chase them. They appear in `/admin/fetches`, grouped by portal (Kaveri, Bhoomi, Bhoomojini, BBMP e-Khata, Karnataka RERA) with the property identifiers to search by (survey number, PID, village... edited on the ticket under "Property identifiers"). Staff download the copy from the portal and upload it, which files it under the item's tag. These portals have no open API (captcha, OTP or paid logins), so this is a staff task; a fetcher that returns the file can be added in `backend/app/gov_sources.py` when a portal or licensed aggregator offers one.
5. **Lawyer reviews each item**: Verify, Reject with a note (the customer is asked to upload again), Waive (not needed; the note is printed), or Reopen. Customers can't remove or retag files under a verified item.
6. **Final report.** When every item is verified or waived and the opinion is written, "Generate final report PDF" makes the report: header, property and scope, a table of every document examined with its tag and files, the final sections (flow of title, encumbrances, revenue records, approvals, opinion, conditions), a disclaimer, and two signature blocks (advocate and reviewing advocate, with name, enrolment number, signature, date, place and seal) plus an initials line on every page. Changing the report afterwards sends it back to collecting documents until the PDF is generated again.
7. **Print, sign, upload.** Staff print the PDF, the advocates sign it, and staff upload the scan ("Upload signed scan"). The customer is notified and can download the signed report; the report is then locked.

## Storage

| Setting | Default | |
| --- | --- | --- |
| `S3_BUCKET` | empty | Private bucket. Empty keeps files in `LOCAL_STORAGE_DIR`. |
| `S3_ENDPOINT_URL` | empty | For Cloudflare R2: `https://<account id>.r2.cloudflarestorage.com`. |
| `S3_REGION` | empty | `auto` for R2, the bucket's region for S3. |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | empty | Without them boto3 uses its usual chain (environment, instance role). |
| `S3_KEY_PREFIX` | `homexo/` | Objects are `<prefix>tickets/<ticket>/<id>.<ext>`. |
| `LOCAL_STORAGE_DIR` | `backend/storage` | Development only. |
| `UPLOAD_MAX_MB` | 25 | Per file. |
| `MAX_DOCUMENTS_PER_TICKET` | 200 | |
| `DOWNLOAD_LINK_MINUTES` | 15 | Lifetime of download links in ticket views. |
| `FIRM_NAME`, `FIRM_ADDRESS` | Homexo Legal, Bengaluru | Printed on the reports. |

Accepted files are PDF, JPG, PNG, WEBP, HEIC, DOC and DOCX; the first bytes must match the extension. Files are never public: views carry signed links (`/api/v1/files/<token>`) that redirect to a 60-second presigned URL for a bucket, or stream from disk. Turn on default encryption for the bucket (S3 does by default; R2 always encrypts). The SHA-256 of every file is recorded, and uploads, deletions and report steps are in the ticket activity and the audit log.

Not done yet: virus scanning (`scan_status` stays `pending`), customer OTP before showing documents (today the ticket number plus phone or email is enough, as for tracking), document upload in the mobile app, and automatic portal fetchers.
