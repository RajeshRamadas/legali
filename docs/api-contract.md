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
  "contact": "customer@example.com",
  "property_type": "apartment",
  "service_slug": "ec-assistance",
  "location": "Bengaluru",
  "description": "Need assistance obtaining an EC."
}
```

Response:
```json
{
  "ticket_number": "HX-EXAMPLE",
  "status": "submitted",
  "message": "Request received. An operations team member must review the request."
}
```

## Production endpoint rules
- Validate payloads and cap lengths.
- Authenticate/verify the customer before showing ticket details.
- Never use a ticket number as the only authorization mechanism.
- Apply RBAC to admin/agent endpoints.
- Use pagination for list endpoints.
- Return consistent error bodies and request IDs.
- Log status transitions and assignments to append-only event history.
