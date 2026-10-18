from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
from uuid import uuid4
from datetime import datetime, timezone
import os
import re

app = FastAPI(
    title="Homexo Property Services API",
    version="0.1.0",
    description="Starter API for Homexo service discovery and ticket intake."
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

ALL_PROPERTY_TYPES = ["apartment", "independent_house", "residential_plot", "agricultural_land", "commercial", "other"]
BUILT_PROPERTY_TYPES = ["apartment", "independent_house", "commercial", "other"]
LAND_PROPERTY_TYPES = ["residential_plot", "agricultural_land", "commercial", "other"]

# Mirrors the "Service needed" options on the website callback form.
SERVICES = [
    {
        "slug": "title-verification",
        "name": "Title Verification",
        "category": "Buyers",
        "description": "Title deed chain, Mother Deed, Encumbrance Certificate, RERA and basic litigation checks with a Go / No-Go verdict.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "legal-due-diligence",
        "name": "Full Legal Due Diligence",
        "category": "Buyers",
        "description": "30-year title history, BBMP / BDA / BMRDA approvals, acquisition notices and SRO field verification.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "sale-agreement-deed",
        "name": "Sale Agreement / Sale Deed",
        "category": "Buyers",
        "description": "Buyer-protective sale agreement and sale deed drafting or vetting with the responsible advocate.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "property-registration",
        "name": "Property Registration",
        "category": "Buyers",
        "description": "Readiness checklist, deed and SRO appointment coordination and registration-day support.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "khata-tax-bescom-transfer",
        "name": "Khata / Tax / BESCOM Transfer",
        "category": "Post-purchase",
        "description": "Khata transfer, property-tax name change and BESCOM name transfer after registration.",
        "property_types": BUILT_PROPERTY_TYPES + ["residential_plot"],
    },
    {
        "slug": "developer-land-screening",
        "name": "Developer Land Screening",
        "category": "Developers",
        "description": "Initial title, encumbrance, land-classification and survey checks before committing to a parcel.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "acquisition-due-diligence",
        "name": "Acquisition Due Diligence",
        "category": "Developers",
        "description": "Title-chain reconstruction, revenue and EC reconciliation, litigation and development-rights review.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "bulk-registration-operations",
        "name": "Bulk Registration Operations",
        "category": "Developers",
        "description": "Unit-level readiness, buyer document coordination, SRO appointments and registration tracking for projects.",
        "property_types": ["apartment", "independent_house", "residential_plot", "commercial"],
    },
    {
        "slug": "mutation-records-management",
        "name": "Mutation & Records Management",
        "category": "Developers",
        "description": "Mutation follow-up, Khata and property-tax updates and utility transfers after sale.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "document-retrieval-courier",
        "name": "Government Document Retrieval & Courier",
        "category": "Documents",
        "description": "We confirm the issuing authority and requirements, coordinate the request and courier physical documents.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "certified-copy-ec",
        "name": "Certified Copy / Encumbrance Certificate",
        "category": "Documents",
        "description": "Encumbrance Certificate, registered deed copies and eligible certified-copy requests.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "rtc-mutation-survey-records",
        "name": "RTC / Mutation / Survey Records",
        "category": "Documents",
        "description": "RTC / Pahani, Mutation Register extracts, mutation orders and eligible survey records.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "khata-property-tax-documents",
        "name": "Khata / Property Tax Documents",
        "category": "Documents",
        "description": "Khata / e-Khata guidance, property-tax records and application follow-up.",
        "property_types": BUILT_PROPERTY_TYPES + ["residential_plot"],
    },
    {
        "slug": "deed-drafting-registration",
        "name": "Deed Drafting / Registration Support",
        "category": "Documents",
        "description": "POA, Gift Deed, Will and other property-deed drafting, vetting and registration support.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "advocate-consultation",
        "name": "Advocate Consultation",
        "category": "Consultation",
        "description": "A 30-minute video consultation with a senior property advocate, with a written summary.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "general-guidance",
        "name": "Not sure — need guidance",
        "category": "Consultation",
        "description": "Tell us about the property and a specialist will suggest the right service.",
        "property_types": ALL_PROPERTY_TYPES,
    },
]
SERVICES_BY_SLUG = {service["slug"]: service for service in SERVICES}

class TicketCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=254)
    email: str | None = Field(default=None, max_length=254)
    property_type: str = Field(min_length=2, max_length=40)
    service_slug: str = Field(min_length=2, max_length=100)
    package: str | None = Field(default=None, max_length=60)
    location: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=4000)
    source: Literal["website", "chat", "mobile"] = "website"

class TicketLookup(BaseModel):
    ticket_number: str = Field(min_length=5, max_length=40)
    contact: str = Field(min_length=5, max_length=254)

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=1000)

STATUS_LABELS = {
    "submitted": "Request received",
    "under_review": "Specialist reviewing scope",
    "awaiting_documents": "Waiting for documents",
    "in_progress": "Work in progress",
    "lawyer_review": "In advocate review",
    "completed": "Completed",
    "closed": "Closed",
}

# DEMO ONLY: in-memory storage is cleared whenever the API restarts.
# Replace with PostgreSQL repositories, authentication, verification and audit logging.
TICKETS: list[dict] = []

def _normalize_contact(value: str) -> str:
    value = value.strip().lower()
    if "@" in value:
        return value
    digits = re.sub(r"\D", "", value)
    return digits[-10:]

def _public_ticket(ticket: dict) -> dict:
    return {
        "ticket_number": ticket["ticket_number"],
        "service_name": SERVICES_BY_SLUG[ticket["service_slug"]]["name"],
        "package": ticket.get("package"),
        "status": ticket["status"],
        "status_label": STATUS_LABELS.get(ticket["status"], ticket["status"]),
        "created_at": ticket["created_at"],
        "history": [
            {**event, "label": STATUS_LABELS.get(event["status"], event["status"])}
            for event in ticket["history"]
        ],
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "homexo-api"}

@app.get("/api/v1/services")
def list_services():
    return {"items": SERVICES}

@app.get("/api/v1/services/{slug}")
def get_service(slug: str):
    service = SERVICES_BY_SLUG.get(slug)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@app.post("/api/v1/tickets", status_code=201)
def create_ticket(payload: TicketCreate):
    if payload.service_slug not in SERVICES_BY_SLUG:
        raise HTTPException(status_code=422, detail="Unknown service_slug")
    now = datetime.now(timezone.utc)
    ticket = {
        "id": str(uuid4()),
        "ticket_number": f"HX-{now:%y%m%d}-{uuid4().hex[:6].upper()}",
        **payload.model_dump(),
        "status": "submitted",
        "created_at": now.isoformat(),
        "history": [{"status": "submitted", "note": "We have your request and will call you to confirm scope.", "at": now.isoformat()}],
    }
    TICKETS.append(ticket)
    return {
        "ticket_number": ticket["ticket_number"],
        "status": ticket["status"],
        "message": "Request received. A specialist will call you to confirm the scope, documents needed and any fees.",
    }

@app.post("/api/v1/tickets/lookup")
def lookup_ticket(payload: TicketLookup):
    """Return a ticket's status when the caller knows both its number and the contact used to raise it."""
    number = payload.ticket_number.strip().upper()
    contact = _normalize_contact(payload.contact)
    ticket = next(
        (
            item for item in TICKETS
            if item["ticket_number"] == number
            and contact in {_normalize_contact(item["contact"]), _normalize_contact(item.get("email") or "")}
        ),
        None,
    )
    if ticket is None or not contact:
        # Same answer for "no such ticket" and "wrong contact" so ticket numbers can't be probed.
        raise HTTPException(status_code=404, detail="We couldn't find a request with that ticket number and phone or email.")
    return _public_ticket(ticket)

# Rule-based assistant for the website chat widget. Each topic maps keywords to an answer
# and, optionally, a service the visitor can raise a ticket for. Swap for an AI provider later.
CHAT_TOPICS = [
    {
        "keywords": ["developer", "builder", "project", "bulk", "units", "acquisition", "parcel", "land screening"],
        "reply": "For developers we cover the whole lifecycle: land screening, acquisition due diligence, bulk registration operations and mutation follow-up. Scope and capacity are confirmed for each engagement.",
        "service_slug": "developer-land-screening",
        "suggestions": ["Bulk registrations", "Acquisition due diligence", "Talk to a specialist"],
    },
    {
        "keywords": ["bulk registration", "bulk registrations"],
        "reply": "Registration Operations gives each unit a readiness checklist, buyer document coordination, deed and SRO appointment coordination and progress tracking.",
        "service_slug": "bulk-registration-operations",
        "suggestions": ["Mutation follow-up", "Talk to a specialist"],
    },
    {
        "keywords": ["acquisition due diligence"],
        "reply": "Acquisition Due Diligence reconstructs the title chain, reconciles revenue, survey and EC records, checks litigation and restrictions and ends with a lawyer report.",
        "service_slug": "acquisition-due-diligence",
        "suggestions": ["Land screening", "Talk to a specialist"],
    },
    {
        "keywords": ["price", "cost", "fee", "charges", "package", "how much", "starter", "pro", "complete"],
        "reply": "We have three fixed-fee packages: Shield Starter ₹4,999 (48–72 hours), Shield Pro ₹9,999 (5–7 working days, most popular) and Shield Complete ₹18,999 (7–10 days plus post-purchase support). Stamp duty, registration fees and government charges are separate at actuals.",
        "service_slug": "legal-due-diligence",
        "suggestions": ["What does Pro include?", "Talk to an advocate", "Stamp duty"],
    },
    {
        "keywords": ["include", "includes", "what does"],
        "reply": "Shield Pro includes everything in Starter plus a 30-year title history, Mother Deed chain, BBMP / BDA / BMRDA audit, acquisition notice check, SRO field verification, a buyer-protective sale agreement and Khata and tax records.",
        "service_slug": "legal-due-diligence",
        "suggestions": ["Package prices", "Talk to a specialist"],
    },
    {
        "keywords": ["stamp duty", "registration fee", "government fee"],
        "reply": "Stamp duty, registration fees and other government charges are not part of our packages. They are billed separately at actuals.",
        "service_slug": None,
        "suggestions": ["Package prices", "Registration support"],
    },
    {
        "keywords": ["safe to buy", "safe", "risk", "verdict", "title", "mother deed", "verify", "verification", "rera"],
        "reply": "Our advocate reviews the title chain, EC, RERA and approvals and gives you a plain-English Go / Investigate / Do Not Proceed verdict. No service can guarantee every risk is found, but you'll know what's verified and what still needs attention.",
        "service_slug": "title-verification",
        "suggestions": ["Package prices", "What documents do I need?", "Talk to a specialist"],
    },
    {
        "keywords": ["documents do i need", "which documents", "seller", "checklist"],
        "reply": "It depends on the property, but usually title deeds, EC, revenue records, approvals, Khata and tax records, and survey documents. A specialist will send you a checklist for your property.",
        "service_slug": "general-guidance",
        "suggestions": ["Talk to a specialist", "Package prices"],
    },
    {
        "keywords": ["encumbrance", "ec", "certified copy", "deed copy"],
        "reply": "We can help request an Encumbrance Certificate, registered deed copies and other eligible certified copies, and courier the physical documents to you.",
        "service_slug": "certified-copy-ec",
        "suggestions": ["Courier delivery", "Talk to a specialist"],
    },
    {
        "keywords": ["rtc", "pahani", "mutation", "survey"],
        "reply": "We help with RTC / Pahani, Mutation Register extracts, mutation orders and eligible survey records, and follow up on mutation after registration.",
        "service_slug": "rtc-mutation-survey-records",
        "suggestions": ["Courier delivery", "Talk to a specialist"],
    },
    {
        "keywords": ["khata", "e-khata", "property tax", "bescom", "electricity", "name change", "transfer"],
        "reply": "After registration we can handle Khata transfer, property-tax name change and BESCOM name transfer where applicable.",
        "service_slug": "khata-tax-bescom-transfer",
        "suggestions": ["Shield Complete", "Talk to a specialist"],
    },
    {
        "keywords": ["sale agreement", "sale deed", "agreement", "draft", "poa", "gift deed", "will"],
        "reply": "We coordinate sale agreements, sale deeds, POA, Gift Deed and Will drafting or vetting with the responsible advocate.",
        "service_slug": "deed-drafting-registration",
        "suggestions": ["Registration support", "Talk to a specialist"],
    },
    {
        "keywords": ["registration", "register", "registered", "sro"],
        "reply": "We prepare a readiness checklist, coordinate the deed and the SRO appointment and support you on registration day. Government fees are separate.",
        "service_slug": "property-registration",
        "suggestions": ["Stamp duty", "Talk to a specialist"],
    },
    {
        "keywords": ["courier", "deliver", "delivery", "home", "doorstep"],
        "reply": "Tell us the document and the property location. We confirm the issuing authority, eligibility, authorisation, timeline and charges, then coordinate and courier physical documents to you.",
        "service_slug": "document-retrieval-courier",
        "suggestions": ["Encumbrance Certificate", "RTC / Pahani"],
    },
    {
        "keywords": ["advocate", "lawyer", "consult", "video call"],
        "reply": "A 30-minute video consultation with a senior property advocate costs ₹999, includes a written summary, and is credited toward a Shield package ordered within 7 days.",
        "service_slug": "advocate-consultation",
        "suggestions": ["Package prices", "Track my request"],
    },
    {
        "keywords": ["callback", "call me", "specialist", "human", "agent", "talk", "contact", "help"],
        "reply": "Sure. Share a few details and a specialist will call you back to discuss the property and the right next step.",
        "service_slug": "general-guidance",
        "suggestions": ["Package prices", "Track my request"],
    },
]
TICKET_NUMBER_RE = re.compile(r"\bHX-\d{6}-[0-9A-F]{6}\b", re.IGNORECASE)

@app.post("/api/v1/chat")
def chat(payload: ChatMessage):
    text = payload.message.strip().lower()
    ticket_match = TICKET_NUMBER_RE.search(payload.message)
    if ticket_match or any(re.search(rf"\b{word}\b", text) for word in ["track", "status", "my request", "my ticket"]):
        return {
            "reply": "I can check that. Enter your ticket number and the phone number or email you used.",
            "action": "track",
            "ticket_number": ticket_match.group(0).upper() if ticket_match else None,
            "service": None,
            "suggestions": [],
        }
    # Longest matching keyword wins, so "bulk registration" beats "registration".
    best, best_len = None, 0
    for topic in CHAT_TOPICS:
        for keyword in topic["keywords"]:
            if len(keyword) > best_len and re.search(rf"\b{re.escape(keyword)}\b", text):
                best, best_len = topic, len(keyword)
    if best is None and re.search(r"\b(hi|hello|hey|namaste|namaskara)\b", text):
        return {
            "reply": "Hello! I'm the Homexo Legal assistant. I can explain our packages, help you pick a service, raise a request or track one.",
            "action": None,
            "ticket_number": None,
            "service": None,
            "suggestions": ["Is this property safe to buy?", "Package prices", "Track my request"],
        }
    if best is None:
        return {
            "reply": "I'm not sure I understood. I can help with title verification, registration, Khata transfers, document retrieval and developer services, or a specialist can call you back.",
            "action": "request",
            "ticket_number": None,
            "service": SERVICES_BY_SLUG["general-guidance"],
            "suggestions": ["Package prices", "Developer services", "Track my request"],
        }
    service = SERVICES_BY_SLUG.get(best["service_slug"]) if best["service_slug"] else None
    return {
        "reply": best["reply"],
        "action": "request" if service else None,
        "ticket_number": None,
        "service": service,
        "suggestions": best["suggestions"],
    }

@app.get("/api/v1/demo/tickets")
def list_demo_tickets():
    """Development-only demo endpoint. Remove or protect before any deployment."""
    return {"items": TICKETS}
