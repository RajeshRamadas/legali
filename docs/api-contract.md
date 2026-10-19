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

`email`, `package` and `description` are optional; `source` is `website`, `chat` or `mobile`. `conversation_id` (optional) is the chat the request was raised from; staff then see that chat on the ticket.

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
Assistant behind the website chat widget and the app's assistant screen. With `ANTHROPIC_API_KEY` set it answers with Claude, grounded in the knowledge base (`backend/app/knowledge/*.md`, retrieved per question) and, when the request carries a ticket that verifies, that ticket's customer view (never internal notes). Without a key, or if the AI call fails or declines, it answers from rule-based topics. Every message and reply is saved in `conversations` / `conversation_messages`. Rate limited per client address (`CHAT_RATE_LIMIT_PER_MINUTE`, default 20; 429 when exceeded), counted from saved messages so the limit holds across API workers. Only a salted hash of the address is stored.

Request: `{"message": "What do you need from me?", "conversation_id": "..." | null, "ticket": {"ticket_number": "HX-261018-ABC123", "contact": "9876543210"} | null}`

Send the `conversation_id` from the previous reply to continue a chat; its saved transcript (last 12 turns) is the history. `history` (`[{"role": "user" | "assistant", "content": "..."}]`) is only read when starting a conversation. `ticket` is re-verified on every message, exactly like lookup; a verified ticket with no linked chat gets this one linked.

Response: `{"reply": "...", "action": "request" | "track" | "status" | null, "ticket_number": null, "service": {...} | null, "suggestions": ["..."], "sources": [{"title": "Buyer packages", "section": "Shield Pro (₹9,999)"}], "mode": "ai" | "rules", "ticket": {...customer view...} | null, "ticket_verified": true, "conversation_id": "..."}`

`action` tells the widget what to render: `request` a callback form for `service`, `track` a ticket-verification form, `status` the status card for `ticket` (with the reply box).

## Staff API

Staff sign in with `POST /api/v1/auth/login` (`{"email", "password"}`) and send the returned `access_token` as `Authorization: Bearer <token>`. Admins see and act on every ticket; agents only on tickets currently assigned to them (others return 404).

| Method | Path | Who | What |
| --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | staff | Current user and role |
| GET | `/api/v1/admin/tickets` | staff | Queue. Filters: `status` (a status, comma list, `open` or `closed`), `service`, `assignee` (`me`, `unassigned` or an id), `needs_reply`, `q` (ticket, name, phone, area), `page`, `page_size` |
| GET | `/api/v1/admin/tickets/{ticket_number}` | staff | Full ticket: customer, property, events, messages and notes, notifications, `chat_transcript` (the linked chat with the assistant) |
| PATCH | `/api/v1/admin/tickets/{ticket_number}` | staff | `{"status", "priority", "note"}`; `note` is shown to the customer with the new status |
| POST | `/api/v1/admin/tickets/{ticket_number}/assignment` | admin | `{"agent_id": "..." or null, "note"}` |
| POST | `/api/v1/admin/tickets/{ticket_number}/messages` | staff | `{"message", "visibility": "customer" or "internal"}` |
| GET | `/api/v1/admin/reports/summary` | staff | Open, new today, unassigned, waiting on us, counts by status |
| GET | `/api/v1/admin/meta` | staff | Status and priority options |
| GET / POST | `/api/v1/admin/staff` | admin | List staff / add `{"display_name", "email", "password", "role"}` |
| PATCH | `/api/v1/admin/staff/{id}` | admin | `{"account_status": "active" or "suspended", "role"}` |
| GET | `/api/v1/posts` | public | Published blog posts, newest first. Filters: `type` (`article` or `case_study`), `tag`, `q`, `page`, `page_size` |
| GET | `/api/v1/posts/{slug}` | public | One published post with its Markdown `body`, `highlights` and up to 3 `related` posts of the same type |
| GET / POST | `/api/v1/admin/posts` | admin | List all posts (filters `type`, `status`, `q`) / create `{"post_type", "title", "slug"?, "status", "excerpt", "body", "cover_image_url", "tags", "highlights"}` |
| GET / PATCH / DELETE | `/api/v1/admin/posts/{id}` | admin | Read, edit, publish (`{"status": "published"}`), unpublish (`"draft"`) or delete a post |

Status changes, assignments, sign-ins and staff changes are written to `audit_logs`; every ticket change is also a `ticket_events` row.

## Production endpoint rules
- Validate payloads and cap lengths.
- Authenticate/verify the customer before showing ticket details.
- Never use a ticket number as the only authorization mechanism.
- Apply RBAC to admin/agent endpoints.
- Use pagination for list endpoints.
- Return consistent error bodies and request IDs.
- Log status transitions and assignments to append-only event history.
