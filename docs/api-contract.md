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
Starter-only in-memory endpoint for smoke testing. **Not suitable for production** until backed by PostgreSQL, authenticated, rate-limited and audited.

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
  "history": [{"status": "submitted", "label": "Request received", "note": "...", "at": "..."}]
}
```

## POST `/api/v1/chat`
Rule-based assistant behind the website chat widget. Matches keywords to an answer and, where relevant, a service the visitor can raise a request for, or asks for ticket details to track a request.

Request: `{"message": "Is this property safe to buy?"}`

Response: `{"reply": "...", "action": "request" | "track" | null, "ticket_number": null, "service": {...} | null, "suggestions": ["Package prices", "..."]}`

## Production endpoint rules
- Validate payloads and cap lengths.
- Authenticate/verify the customer before showing ticket details.
- Never use a ticket number as the only authorization mechanism.
- Apply RBAC to admin/agent endpoints.
- Use pagination for list endpoints.
- Return consistent error bodies and request IDs.
- Log status transitions and assignments to append-only event history.
