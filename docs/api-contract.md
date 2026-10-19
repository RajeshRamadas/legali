# API contract (starter)

Base URL in development: `http://localhost:8000`

## GET `/health`
Returns service health.

Example:
```json
{"status":"ok"}
```

## GET `/api/v1/services`
Returns the initial public service catalogue.

## POST `/api/v1/tickets`
Creates a customer (matched on phone if they've raised one before), a property and a ticket, and queues SMS/email notifications. Not yet rate-limited.

Request:
```json
{
  "customer_name": "Sample Customer",
  "contact": "+91 98765 43210",
  "email": "customer@example.com",
  "property_type": "apartment",
  "service_slug": "legal-due-diligence",
  "package": "Shield Pro",
  "location": "Whitefield, Bengaluru",
  "description": "Optional note.",
  "source": "website"
}
```

Response:
```json
{
  "ticket_number": "HX-EXAMPLE",
  "status": "submitted",
  "message": "Request received. A specialist will call you to confirm the scope, documents needed and any fees."
}
```

`email`, `package` and `description` are optional; `source` is `website`, `chat` or `mobile`.

## POST `/api/v1/tickets/lookup`
Returns a ticket's status and history when the caller supplies both the ticket number and the phone or email used to raise it. A wrong contact and an unknown ticket return the same 404. Starter-level verification only; replace with OTP or signed-in access before production.

Request: `{"ticket_number": "HX-261018-ABC123", "contact": "9876543210"}`

Response:
```json
{
  "ticket_number": "HX-261018-ABC123",
  "service_name": "Full Legal Due Diligence",
  "package": "Shield Pro",
  "status": "submitted",
  "status_label": "Request received",
  "created_at": "2026-10-18T20:06:00+00:00",
  "history": [{"status": "submitted", "label": "Request received", "note": "...", "at": "..."}],
  "messages": [{"from": "homexo", "message": "...", "at": "..."}],
  "can_reply": true
}
```

Internal notes and staff names are never included.

## POST `/api/v1/tickets/messages`
A customer reply to the case team. Same verification as lookup; returns the updated customer view. A reply to a ticket waiting on the customer moves it back to `under_review`. Closed tickets return 409.

Request: `{"ticket_number": "HX-261018-ABC123", "contact": "9876543210", "message": "I've emailed the EC."}`

## POST `/api/v1/chat`
Rule-based assistant behind the website chat widget. Matches keywords to an answer and, where relevant, a service the visitor can raise a request for, or asks for ticket details to track a request.

Request: `{"message": "Is this property safe to buy?"}`

Response: `{"reply": "...", "action": "request" | "track" | null, "ticket_number": null, "service": {...} | null, "suggestions": ["Package prices", "..."]}`

## Staff API

Staff sign in with `POST /api/v1/auth/login` (`{"email", "password"}`) and send the returned `access_token` as `Authorization: Bearer <token>`. Admins see and act on every ticket; agents only on tickets currently assigned to them (others return 404).

| Method | Path | Who | What |
| --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | staff | Current user and role |
| GET | `/api/v1/admin/tickets` | staff | Queue. Filters: `status` (a status, comma list, `open` or `closed`), `service`, `assignee` (`me`, `unassigned` or an id), `needs_reply`, `q` (ticket, name, phone, area), `page`, `page_size` |
| GET | `/api/v1/admin/tickets/{ticket_number}` | staff | Full ticket: customer, property, events, messages and notes, notifications |
| PATCH | `/api/v1/admin/tickets/{ticket_number}` | staff | `{"status", "priority", "note"}`; `note` is shown to the customer with the new status |
| POST | `/api/v1/admin/tickets/{ticket_number}/assignment` | admin | `{"agent_id": "..." or null, "note"}` |
| POST | `/api/v1/admin/tickets/{ticket_number}/messages` | staff | `{"message", "visibility": "customer" or "internal"}` |
| GET | `/api/v1/admin/reports/summary` | staff | Open, new today, unassigned, waiting on us, counts by status |
| GET | `/api/v1/admin/meta` | staff | Status and priority options |
| GET / POST | `/api/v1/admin/staff` | admin | List staff / add `{"display_name", "email", "password", "role"}` |
| PATCH | `/api/v1/admin/staff/{id}` | admin | `{"account_status": "active" or "suspended", "role"}` |

Status changes, assignments, sign-ins and staff changes are written to `audit_logs`; every ticket change is also a `ticket_events` row.

## Production endpoint rules
- Validate payloads and cap lengths.
- Authenticate/verify the customer before showing ticket details.
- Never use a ticket number as the only authorization mechanism.
- Apply RBAC to admin/agent endpoints.
- Use pagination for list endpoints.
- Return consistent error bodies and request IDs.
- Log status transitions and assignments to append-only event history.
