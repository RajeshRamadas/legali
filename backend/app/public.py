"""Customer-facing endpoints: service catalogue, raising tickets, tracking and replying."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tickets, document_requirements
from .catalogue import SERVICES, SERVICES_BY_SLUG
from .db import get_db
from .models import CLOSED_STATUSES, PROPERTY_TYPES, ServiceRequest, ServiceType

router = APIRouter()

class TicketCreate(BaseModel):
    property_intake: document_requirements.PropertyIntake | None = None
    customer_name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=254, description="Phone number (or email for older clients).")
    email: str | None = Field(default=None, max_length=254)
    property_type: Literal[PROPERTY_TYPES]  # type: ignore[valid-type]
    service_slug: str = Field(min_length=2, max_length=100)
    package: str | None = Field(default=None, max_length=60)
    location: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=4000)
    source: Literal["website", "chat", "mobile"] = "website"
    # The chat this request was raised from, if any; staff see its transcript on the ticket.
    conversation_id: uuid.UUID | None = None

class TicketLookup(BaseModel):
    ticket_number: str = Field(min_length=5, max_length=40)
    contact: str = Field(min_length=5, max_length=254)

class CustomerReply(TicketLookup):
    message: str = Field(min_length=1, max_length=4000)

NOT_FOUND = "We couldn't find a request with that ticket number and phone or email."

def _find_for_customer(db: Session, ticket_number: str, contact: str) -> ServiceRequest:
    ticket = db.scalars(select(ServiceRequest).where(ServiceRequest.ticket_number == ticket_number.strip().upper())).first()
    # Same answer for "no such ticket" and "wrong contact" so ticket numbers can't be probed.
    if ticket is None or not tickets.contact_matches(ticket.customer, contact):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return ticket

@router.get("/health")
def health():
    return {"status": "ok", "service": "homexo-api"}

@router.get("/api/v1/services")
def list_services():
    return {"items": SERVICES}

@router.get("/api/v1/services/{slug}")
def get_service(slug: str):
    service = SERVICES_BY_SLUG.get(slug)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.post("/api/v1/tickets", status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    service = db.scalars(select(ServiceType).where(ServiceType.slug == payload.service_slug, ServiceType.is_active.is_(True))).first()
    if service is None:
        raise HTTPException(status_code=422, detail="Unknown service_slug")
    # The mobile app still sends email or phone in one "contact" field.
    contact = payload.contact.strip()
    phone, email = (None, contact) if "@" in contact else (contact, payload.email)
    if phone and len(tickets.normalize_phone(phone)) < 8:
        raise HTTPException(status_code=422, detail="contact: Enter a valid phone number.")
    ticket = tickets.create_ticket(
        db, customer_name=payload.customer_name.strip(), phone=phone, email=(email or "").strip() or None,
        property_type=payload.property_type, service=service, package=payload.package, location=payload.location.strip(),
        description=payload.description.strip(), source=payload.source,
        property_intake=payload.property_intake.model_dump() if payload.property_intake else None,
    )
    if payload.conversation_id:
        tickets.link_conversation(db, ticket, payload.conversation_id)
    db.commit()
    return {
        "ticket_number": ticket.ticket_number,
        "status": ticket.status,
        "message": "Request received. A specialist will call you to confirm the scope, documents needed and any fees.",
        "document_request": document_requirements.view(ticket),
    }

@router.post("/api/v1/tickets/lookup")
def lookup_ticket(payload: TicketLookup, db: Session = Depends(get_db)):
    """Return a ticket's status when the caller knows both its number and the contact used to raise it."""
    return tickets.customer_view(_find_for_customer(db, payload.ticket_number, payload.contact))

@router.post("/api/v1/tickets/messages", status_code=201)
def customer_reply(payload: CustomerReply, db: Session = Depends(get_db)):
    ticket = _find_for_customer(db, payload.ticket_number, payload.contact)
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="This request is closed. Please raise a new request.")
    tickets.add_message(db, ticket, payload.message.strip(), author_type="customer", visibility="customer")
    # A reply to "waiting for your reply" hands the ticket back to the team.
    if ticket.status == "waiting_for_customer":
        tickets.change_status(db, ticket, "under_review", None, "Thanks, we have your reply.")
    db.commit()
    return tickets.customer_view(ticket)
