"""Ticket lifecycle: creation, events, messages, notifications and the views customers and staff see."""
import re
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import case_files, config
from .models import (
    CLOSED_STATUSES, AuditLog, Conversation, ConversationMessage, Customer, Meeting, Notification, Property, ServiceRequest, ServiceType, TicketEvent, TicketMessage, User, utcnow,
)

STATUS_LABELS = {
    "draft": "Draft",
    "submitted": "Request received",
    "under_review": "Specialist reviewing scope",
    "waiting_for_customer": "Waiting for your reply",
    "approved_for_processing": "Scope confirmed",
    "assigned": "Case team assigned",
    "in_progress": "Work in progress",
    "quality_review": "In advocate review",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "rejected": "Not taken up",
    "on_hold": "On hold",
    "reopened": "Reopened",
}
# Staff see the same stages worded from the team's side.
STAFF_STATUS_LABELS = {**STATUS_LABELS, "submitted": "New", "under_review": "Reviewing scope", "waiting_for_customer": "Waiting for customer", "rejected": "Rejected"}
CREATED_NOTE = "We have your request and will call you to confirm scope."

def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").capitalize())

def staff_status_label(status: str) -> str:
    return STAFF_STATUS_LABELS.get(status, status_label(status))

def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-10:]

def contact_matches(customer: Customer, contact: str) -> bool:
    contact = contact.strip().lower()
    if "@" in contact:
        return bool(customer.email) and customer.email.strip().lower() == contact
    digits = normalize_phone(contact)
    return len(digits) >= 8 and digits == customer.phone_normalized

def _new_ticket_number(now: datetime) -> str:
    return f"HX-{now:%y%m%d}-{uuid.uuid4().hex[:6].upper()}"

def audit(db: Session, actor: User | None, action: str, entity_id: uuid.UUID | None, **metadata) -> None:
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity_type="service_request", entity_id=entity_id, metadata_=metadata))

def add_event(db: Session, ticket: ServiceRequest, event_type: str, actor: User | None = None, old=None, new=None, reason: str | None = None) -> None:
    event = TicketEvent(service_request_id=ticket.id, actor_user_id=actor.id if actor else None, event_type=event_type, old_value=old, new_value=new, reason=reason)
    db.add(event)
    ticket.events.append(event)

def queue_notifications(db: Session, ticket: ServiceRequest, template_key: str, body: str) -> None:
    """Record outgoing customer notifications. A delivery worker or provider integration sends queued rows."""
    customer = ticket.customer
    targets = []
    if customer.phone:
        targets.append(("sms", customer.phone))
    if customer.email:
        targets.append(("email", customer.email))
    for channel, recipient in targets:
        db.add(Notification(service_request_id=ticket.id, customer_id=customer.id, channel=channel, template_key=template_key, recipient=recipient, body=body))

def create_ticket(db: Session, *, customer_name: str, phone: str, email: str | None, property_type: str, service: ServiceType,
                  package: str | None, location: str, description: str, source: str) -> ServiceRequest:
    phone_normalized = normalize_phone(phone)
    # Returning customers are matched on phone so their tickets stay together.
    customer = db.scalars(select(Customer).where(Customer.phone_normalized == phone_normalized).order_by(Customer.created_at)).first() if phone_normalized else None
    if customer is None:
        customer = Customer(full_name=customer_name, phone=phone, phone_normalized=phone_normalized, email=email or None)
        db.add(customer)
    elif email and not customer.email:
        customer.email = email
    db.flush()
    prop = Property(customer_id=customer.id, property_type=property_type, locality=location)
    db.add(prop)
    db.flush()
    now = utcnow()
    ticket = ServiceRequest(
        ticket_number=_new_ticket_number(now), customer_id=customer.id, property_id=prop.id, service_type_id=service.id,
        title=f"{service.name} · {location}", description=description, package=package, source=source, submitted_at=now,
        # Captured as typed on this request, since the customer record may be shared across requests.
        structured_answers={"customer_name": customer_name, "contact": phone, "email": email},
    )
    db.add(ticket)
    db.flush()
    db.refresh(ticket)
    add_event(db, ticket, "created", new={"status": "submitted"}, reason=CREATED_NOTE)
    queue_notifications(db, ticket, "ticket_created", f"Homexo Legal: we received your request {ticket.ticket_number} for {service.name}. A specialist will call you to confirm scope, documents and fees.")
    return ticket

def link_conversation(db: Session, ticket: ServiceRequest, conversation_id: uuid.UUID) -> None:
    """Attach the chat a ticket was raised from, so staff can read what the customer asked first."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        return
    ticket.conversation_id = conversation.id
    conversation.customer_id = ticket.customer_id
    conversation.state = "submitted"
    db.add(ConversationMessage(conversation_id=conversation.id, sender_type="system", body=f"Raised ticket {ticket.ticket_number} for {ticket.service_type.name}."))

def change_status(db: Session, ticket: ServiceRequest, new_status: str, actor: User | None, note: str | None) -> None:
    old_status = ticket.status
    if new_status == old_status:
        return
    ticket.status = new_status
    ticket.completed_at = utcnow() if new_status == "completed" else None
    add_event(db, ticket, "status_changed", actor, old={"status": old_status}, new={"status": new_status}, reason=note)
    message = f"Homexo Legal: your request {ticket.ticket_number} is now '{status_label(new_status)}'."
    if note:
        message += f" {note}"
    queue_notifications(db, ticket, "status_changed", message)

def add_message(db: Session, ticket: ServiceRequest, text: str, *, author_type: str, visibility: str, author: User | None = None) -> TicketMessage:
    message = TicketMessage(service_request_id=ticket.id, author_user_id=author.id if author else None, author_type=author_type, visibility=visibility, message=text)
    db.add(message)
    ticket.messages.append(message)
    ticket.updated_at = utcnow()
    add_event(db, ticket, "customer_replied" if author_type == "customer" else ("note_added" if visibility == "internal" else "message_sent"), author)
    if author_type == "staff" and visibility == "customer":
        queue_notifications(db, ticket, "staff_message", f"Homexo Legal: new message on {ticket.ticket_number}: {text[:140]}")
    return message

def needs_reply(ticket: ServiceRequest) -> bool:
    visible = [m for m in ticket.messages if m.visibility == "customer"]
    return bool(visible) and visible[-1].author_type == "customer" and ticket.status not in CLOSED_STATUSES

def aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; every stored time is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def _iso(value: datetime | None) -> str | None:
    return aware(value).isoformat() if value else None

def format_when(value: datetime) -> str:
    """'Tue 21 Oct, 4:30 pm IST' in the meeting time zone, for messages."""
    local = aware(value).astimezone(ZoneInfo(config.MEETING_TIMEZONE))
    return f"{local:%a} {local.day} {local:%b}, {local.strftime('%I:%M %p').lstrip('0').lower()} {local.tzname()}"

MEETING_STATUS_LABELS = {"scheduled": "Scheduled", "completed": "Completed", "cancelled": "Cancelled"}

def meeting_view(meeting: Meeting, *, staff: bool = False) -> dict:
    view = {
        "id": str(meeting.id),
        "title": meeting.title,
        "agenda": meeting.agenda,
        "starts_at": _iso(meeting.starts_at),
        "ends_at": _iso(meeting.ends_at),
        "when": format_when(meeting.starts_at),
        "status": meeting.status,
        "status_label": MEETING_STATUS_LABELS[meeting.status],
        "lawyer_name": meeting.lawyer.display_name,
        # The link only matters (and is only shared) while the meeting is on.
        "meet_link": meeting.meet_link if meeting.status == "scheduled" else None,
    }
    if staff:
        ticket = meeting.service_request
        view |= {
            "lawyer": _staff_ref(meeting.lawyer),
            "ticket_number": ticket.ticket_number,
            "service_name": ticket.service_type.name,
            "customer_name": (ticket.structured_answers or {}).get("customer_name") or ticket.customer.full_name,
            "customer_phone": ticket.customer.phone,
            "calendar": "google" if meeting.calendar_event_id else "manual",
        }
    return view

def customer_view(ticket: ServiceRequest) -> dict:
    """What a customer may see: status history, customer-visible messages and meetings, never internal notes or staff contact details."""
    history = [
        {"status": e.new_value["status"], "label": status_label(e.new_value["status"]), "note": e.reason or "", "at": _iso(e.created_at)}
        for e in ticket.events if e.event_type in ("created", "status_changed") and e.new_value
    ]
    messages = [
        {"from": "you" if m.author_type == "customer" else "homexo", "message": m.message, "at": _iso(m.created_at)}
        for m in ticket.messages if m.visibility == "customer"
    ]
    return {
        "ticket_number": ticket.ticket_number,
        "service_name": ticket.service_type.name,
        "package": ticket.package,
        "status": ticket.status,
        "status_label": status_label(ticket.status),
        "created_at": _iso(ticket.created_at),
        "history": history,
        "messages": messages,
        "meetings": [meeting_view(m) for m in ticket.meetings],
        "can_reply": ticket.status not in CLOSED_STATUSES,
        "documents": case_files.customer_documents_view(ticket),
        "report": case_files.customer_report_view(ticket),
        "can_upload": ticket.status not in CLOSED_STATUSES,
    }

def _staff_ref(user: User | None) -> dict | None:
    return {"id": str(user.id), "name": user.display_name} if user else None

def staff_summary(ticket: ServiceRequest) -> dict:
    assignment = ticket.active_assignment
    answers = ticket.structured_answers or {}
    return {
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "customer_name": answers.get("customer_name") or ticket.customer.full_name,
        "phone": ticket.customer.phone,
        "service_slug": ticket.service_type.slug,
        "service_name": ticket.service_type.name,
        "package": ticket.package,
        "location": ticket.prop.locality if ticket.prop else None,
        "status": ticket.status,
        "status_label": staff_status_label(ticket.status),
        "priority": ticket.priority,
        "source": ticket.source,
        "assignee": _staff_ref(assignment.agent) if assignment else None,
        "needs_reply": needs_reply(ticket),
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }

def staff_detail(ticket: ServiceRequest, notifications: list[Notification]) -> dict:
    customer = ticket.customer
    return {
        **staff_summary(ticket),
        "description": ticket.description,
        "customer": {"id": str(customer.id), "name": customer.full_name, "phone": customer.phone, "email": customer.email},
        "property": {"type": ticket.prop.property_type, "location": ticket.prop.locality} if ticket.prop else None,
        "events": [
            {"type": e.event_type, "old": e.old_value, "new": e.new_value, "note": e.reason, "actor": _staff_ref(e.actor), "at": _iso(e.created_at)}
            for e in ticket.events
        ],
        "messages": [
            {"id": str(m.id), "author_type": m.author_type, "author": _staff_ref(m.author), "visibility": m.visibility, "message": m.message, "at": _iso(m.created_at)}
            for m in ticket.messages
        ],
        "meetings": [meeting_view(m, staff=True) for m in ticket.meetings],
        "documents": case_files.staff_documents_view(ticket),
        "report": case_files.staff_report_view(ticket),
        "chat_transcript": [
            {"from": m.sender_type, "message": m.body, "at": _iso(m.created_at)}
            for m in ticket.conversation.messages
        ] if ticket.conversation else [],
        "notifications": [
            {
                "channel": n.channel, "template": n.template_key, "recipient": n.recipient, "to": "staff" if n.user_id else "customer",
                "status": n.delivery_status, "error": n.error_code, "at": _iso(n.created_at), "send_after": _iso(n.send_after),
            }
            for n in notifications
        ],
    }
