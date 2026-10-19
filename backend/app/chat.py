"""Website and app chat assistant. Answers with Claude grounded in the knowledge base (assistant.py) when an API key
is configured, and from the rule-based topics below otherwise or whenever the AI call fails. Every chat is saved as a
conversation so staff can read it on the ticket it leads to."""
import hashlib
import re
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import assistant, config, tickets
from .catalogue import SERVICES_BY_SLUG
from .db import get_db
from .models import Conversation, ConversationMessage, utcnow
from .public import _find_for_customer

router = APIRouter()

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

class ChatTicket(BaseModel):
    ticket_number: str = Field(min_length=5, max_length=40)
    contact: str = Field(min_length=5, max_length=254)

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    # Returned by the first reply; send it back to continue the same saved conversation.
    conversation_id: uuid.UUID | None = None
    # Only used when there is no saved conversation yet; otherwise the saved transcript is the history.
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    # A ticket the customer verified earlier in this chat. Re-checked on every message.
    ticket: ChatTicket | None = None

HISTORY_TURNS = 12

# Rule-based topics: each maps keywords to an answer and, optionally, a service the visitor can raise a ticket for.
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
        "keywords": ["affidavit", "name change affidavit", "notary", "notarise", "notarize", "notarisation", "notarization", "self declaration"],
        "reply": "An advocate can draft your affidavit, such as name change, address proof, gap or loss of documents, on stamp paper and arrange notarisation. Stamp paper and notary charges are quoted separately.",
        "service_slug": "affidavit-drafting",
        "suggestions": ["Courier delivery", "Talk to a specialist"],
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

RATE_LIMITED = "You're sending messages quickly. Please wait a moment and try again."

def client_key(request: Request) -> str:
    """Salted hash of the caller's address, so the database never holds raw IPs. Behind a proxy, run uvicorn with
    --proxy-headers and --forwarded-allow-ips so this is the visitor's address, not the proxy's."""
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{config.JWT_SECRET}:{host}".encode()).hexdigest()[:32]

def _rate_limit(db: Session, key: str) -> None:
    """One-minute window over saved customer messages, so the limit holds across every API worker."""
    recent = db.scalar(
        select(func.count()).select_from(ConversationMessage).join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(Conversation.client_key == key, ConversationMessage.sender_type == "customer", ConversationMessage.created_at >= utcnow() - timedelta(minutes=1))
    )
    if recent >= config.CHAT_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=RATE_LIMITED)

def _history(conversation: Conversation) -> list[dict]:
    turns = [m for m in conversation.messages if m.sender_type in ("customer", "assistant")][-HISTORY_TURNS:]
    return [{"role": "user" if m.sender_type == "customer" else "assistant", "content": m.body} for m in turns]

@router.post("/api/v1/chat")
def chat(payload: ChatMessage, request: Request, db: Session = Depends(get_db)):
    key = client_key(request)
    _rate_limit(db, key)
    conversation = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
    if conversation is None:
        conversation = Conversation(client_key=key)
        db.add(conversation)
        db.flush()
        history = [turn.model_dump() for turn in payload.history[-HISTORY_TURNS:]]
    else:
        history = _history(conversation)

    ticket = None
    if payload.ticket:
        try:
            ticket = _find_for_customer(db, payload.ticket.ticket_number, payload.ticket.contact)
        except HTTPException:
            ticket = None
    ticket_view = tickets.customer_view(ticket) if ticket else None
    if ticket:
        conversation.customer_id = ticket.customer_id
        # Staff see the chat on the ticket it was about, unless the ticket was raised from another chat.
        if ticket.conversation_id is None:
            ticket.conversation_id = conversation.id

    message = payload.message.strip()
    reply = assistant.answer(message, history, ticket_view) or rule_based_reply(message, ticket_view)
    reply = {"sources": [], "mode": "rules", **reply}
    db.add(ConversationMessage(conversation_id=conversation.id, sender_type="customer", body=message))
    db.add(ConversationMessage(
        conversation_id=conversation.id, sender_type="assistant", body=reply["reply"],
        structured_payload={
            "action": reply["action"], "mode": reply["mode"], "ticket_number": reply["ticket_number"],
            "service_slug": reply["service"]["slug"] if reply["service"] else None, "sources": reply["sources"],
        },
    ))
    conversation.updated_at = utcnow()
    db.commit()
    return {
        **reply,
        "conversation_id": str(conversation.id),
        "ticket": ticket_view if reply["action"] == "status" else None,
        "ticket_verified": ticket_view is not None,
    }

def rule_based_reply(message: str, ticket_view: dict | None) -> dict:
    text = message.strip().lower()
    ticket_match = TICKET_NUMBER_RE.search(message)
    if ticket_match or any(re.search(rf"\b{word}\b", text) for word in ["track", "status", "my request", "my ticket"]):
        if ticket_view and (not ticket_match or ticket_match.group(0).upper() == ticket_view["ticket_number"]):
            return {
                "reply": f"{ticket_view['ticket_number']} is at '{ticket_view['status_label']}'. Here are the details.",
                "action": "status",
                "ticket_number": ticket_view["ticket_number"],
                "service": None,
                "suggestions": ["Package prices", "Talk to a specialist"],
            }
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
