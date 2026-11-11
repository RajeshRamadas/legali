"""Deterministic, owner-only guided intake. No model sees answers or creates a ticket."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import document_requirements, tickets, service_intake_forms, submitted_intake
from .customer_auth import current_customer
from .db import get_db
from .models import Consent, Conversation, ConversationMessage, CustomerAccount, IntakeDraft, ServiceRequest, ServiceType, utcnow

router = APIRouter(prefix="/api/v1/intake")
NOTICE_VERSION = "guided-request-v2"
RETENTION_DAYS = 30
NOTICE = {
    "version": NOTICE_VERSION,
    "retention_days": RETENTION_DAYS,
    "saving": "Save my completed answers privately for up to 30 days so I can resume this request on my signed-in devices. I can discard an unfinished draft at any time.",
    "submission": "I ask Homexo to review these details and contact me about this service request. The case team will confirm scope, availability, required documents and fees.",
    "details": [
        "We collect your verified phone number, name, optional email, service goal, property details, available document names, service-specific answers requested by the team and preferred way to follow up.",
        "Completed answers are saved to your signed-in account when you select Continue. Unsaved text in the current question is not retained. Do not enter identity numbers, financial information or document contents here.",
        "This guided flow uses configured questions, including up to five service-specific questions. It does not send your answers to an AI provider or make legal decisions. Staff see the submitted summary and question history after you create a request.",
        "Unfinished drafts expire 30 days after creation. Discard removes their answers immediately. Submitted details and consent become part of the case record and follow Homexo's case-retention requirements.",
        "Submitting this request does not give marketing consent. Ask your case team through your account for help with access, corrections or deletion, subject to applicable retention requirements.",
    ],
}
LAND = {"residential_plot", "agricultural_land", "farmhouse", "plantation_estate", "industrial_land"}
PROPERTY_LABELS = {"apartment": "Apartment", "villa": "Villa or row house", "independent_house": "Independent house",
    "residential_plot": "Residential plot", "agricultural_land": "Agricultural land", "farmhouse": "Farmhouse or managed farmland",
    "plantation_estate": "Plantation estate", "industrial_land": "Industrial land", "commercial": "Commercial property", "other": "Other"}


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: bool = Field(strict=True)
    notice_version: str = Field(max_length=80)
    service_slug: str | None = Field(default=None, max_length=100)

class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    key: str = Field(min_length=1, max_length=60)
    value: str = Field(max_length=4000)

class Submit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    consent: bool = Field(strict=True)
    notice_version: str = Field(max_length=80)


def _select(key, prompt, choices, help=""):
    return {"key": key, "prompt": prompt, "kind": "select", "required": True, "help": help,
            "options": [{"value": value, "label": label} for value, label in choices]}

def _text(key, prompt, *, required=False, maximum=100, minimum=0, kind="text", help=""):
    return {"key": key, "prompt": prompt, "kind": kind, "required": required, "max_length": maximum, "min_length": minimum,
            "help": help, "options": []}

def questions(db, answers, form_snapshot=None):
    # Keep the selected service in a saved draft so a pause never discards its
    # answers. Only available services can be selected for a new draft.
    services = list(db.scalars(select(ServiceType).where(ServiceType.is_active.is_(True),
        (ServiceType.intake_paused.is_(False)) | (ServiceType.slug == answers.get("service_slug", ""))).order_by(ServiceType.name)))
    service = next((s for s in services if s.slug == answers.get("service_slug")), None)
    rows = [_select("service_slug", "What would you like help with?", [(s.slug, s.name) for s in services]),
        _text("goal", "Tell us what you want to achieve.", required=True, minimum=10, maximum=2000, kind="textarea", help="A short description is enough. An advocate will assess the legal questions."),
        _select("property_type", "What kind of property is this?", [(p, PROPERTY_LABELS[p]) for p in (service.supported_property_types if service else []) if p in PROPERTY_LABELS]),
        _text("location", "Which area and city is the property in?", required=True, minimum=2, maximum=180),
        _select("state", "Which state is the property in?", [("Karnataka", "Karnataka"), ("Other", "Another state"), ("Unknown", "I'm not sure")])]
    if answers.get("state") == "Other":
        rows.append(_text("state_name", "What is the state's name?", required=True, minimum=2, maximum=60))
    rows.append(_select("role", "What is your role in this request?", [(v, l) for v, l in (
        ("buyer", "Buyer"), ("owner", "Owner"), ("seller", "Seller"), ("tenant", "Tenant"),
        ("representative", "Authorised representative"), ("developer", "Developer"), ("other", "Other"))]))
    if answers.get("service_slug") in document_requirements.SERVICES:
        rows += [_select("transaction", "What kind of transaction are you considering?", [(v, l) for v, l in (
            ("purchase", "Purchase"), ("inheritance", "Inheritance"), ("gift", "Gift"), ("partition", "Partition"), ("other", "Other"), ("unknown", "I'm not sure"))]),
            _select("seller_capacity", "Who owns or is offering the property?", [(v, l) for v, l in (
                ("owner", "The owner"), ("power_of_attorney", "A power-of-attorney holder"), ("legal_heir", "A legal heir"), ("company", "A company"), ("unknown", "I'm not sure"))])]
        if answers.get("property_type") not in LAND:
            rows.append(_select("development", "Is this a new development or a resale?", [("new", "New development"), ("resale", "Resale"), ("unknown", "I'm not sure")]))
        else:
            rows.append(_select("granted_land", "Was this land originally granted by the government?", [("yes", "Yes"), ("no", "No"), ("unknown", "I'm not sure")], "Choose not sure if you do not have a reliable record. The advocate will check applicability."))
    if answers.get("property_type") in LAND:
        rows += [_text("survey_number", "Do you know the survey number?", maximum=60, help="Optional. You can skip this if you don't know it."),
                 _text("village", "Which village is the property in?", help="Optional; skip if unknown."),
                 _text("taluk", "Do you know the taluk?", help="Optional; skip if unknown.")]
    else:
        rows.append(_text("property_id_or_pid", "Do you know the property ID or PID?", maximum=60, help="Optional. You can share this later if you don't know it."))
    rows += [_text("district", "Do you know the district?", help="Optional; skip if unknown."),
        _text("available_documents", "Which property documents do you already have?", maximum=500, kind="textarea", help="Names only, such as sale deed or EC. You can skip this. Upload files securely after your request is created."),
        _text("customer_name", "What name should the team use?", required=True, minimum=2, maximum=120),
        _text("email", "Would you like to add an email address?", maximum=254, kind="email", help="Optional. Your verified phone remains the way you sign in.")]
    contacts = [("phone", "Phone call"), ("whatsapp", "WhatsApp")]
    if answers.get("email"):
        contacts.append(("email", "Email"))
    rows.append(_select("contact_preference", "How would you prefer the case team to follow up?", contacts,
                        "This is your preference for this request. It does not subscribe you to marketing."))
    return rows + service_intake_forms.selected_questions(form_snapshot, answers)


def validate(question, value):
    import re
    value = value.strip()
    if "\x00" in value:
        raise HTTPException(422, "Remove unsupported control characters from this answer.")
    if question["kind"] == "select":
        if not value and not question["required"]: return value
        if value not in {o["value"] for o in question["options"]}:
            raise HTTPException(422, "Choose one of the available answers.")
    else:
        if len(value) > question["max_length"] or (question["required"] and len(value) < max(1, question["min_length"])):
            raise HTTPException(422, f"Enter between {question['min_length']} and {question['max_length']} characters for this answer.")
        if question["kind"] == "email" and value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise HTTPException(422, "Enter a valid email address or skip this question.")
    return value


def clean(db, answers, form_snapshot=None):
    answers = dict(answers)
    # Changing service/property/state removes irrelevant answers and invalid dependent choices.
    for _ in range(3):
        allowed = {q["key"]: q for q in questions(db, answers, form_snapshot)}
        valid = {}
        for key, value in answers.items():
            if key in allowed and isinstance(value, str):
                try: valid[key] = validate(allowed[key], value)
                except HTTPException: pass
        if valid == answers:
            return valid
        answers = valid
    return answers


def _owned(db, id, account, *, lock=False):
    query = select(IntakeDraft).where(IntakeDraft.id == id, IntakeDraft.account_id == account.id, IntakeDraft.status != "discarded")
    draft = db.scalar(query.with_for_update() if lock else query)
    if draft is None:
        raise HTTPException(404, "Saved request not found.")
    if tickets.aware(draft.created_at) <= utcnow() - timedelta(days=RETENTION_DAYS):
        raise HTTPException(410, "This draft has expired. Start a new request.")
    return draft

def _created(db, draft):
    ticket = db.get(ServiceRequest, draft.submitted_request_id)
    if ticket is None:
        raise HTTPException(409, "This draft was already submitted. Open your account to find the request.")
    return {"ticket_number": ticket.ticket_number, "status": ticket.status,
            "message": "Request received. A specialist will confirm scope, availability, required documents and fees."}

def view(db, draft):
    answers = clean(db, draft.answers, draft.service_form_snapshot) if draft.status == "draft" else draft.answers
    rows = questions(db, answers, draft.service_form_snapshot)
    from .service_availability import accepts_requests
    return {"id": str(draft.id), "status": draft.status, "revision": draft.revision, "answers": answers, "questions": rows,
            "service_available": accepts_requests(db, answers["service_slug"]) if answers.get("service_slug") else True,
            "next_question": next((q["key"] for q in rows if q["key"] not in answers), None),
            "completed": sum(q["key"] in answers for q in rows), "total": len(rows),
            "service_form_revision": draft.service_form_snapshot.get("revision"),
            "updated_at": tickets.aware(draft.updated_at).isoformat(),
            "expires_at": (tickets.aware(draft.created_at) + timedelta(days=RETENTION_DAYS)).isoformat(),
            "ticket": _created(db, draft) if draft.status == "submitted" else None, "notice": NOTICE}

def consent(payload):
    if not payload.consent:
        raise HTTPException(422, "Confirm the notice before continuing.")
    if payload.notice_version != NOTICE_VERSION:
        raise HTTPException(409, "The privacy notice changed. Reload and review it before continuing.")

def editable(draft, revision):
    if draft.status != "draft":
        raise HTTPException(409, "This request is already submitted and cannot be edited here.")
    if draft.revision != revision:
        raise HTTPException(409, "This draft changed on another tab or device. Reload the saved answers before continuing.")


@router.get("/notice")
def notice():
    return NOTICE

@router.get("/drafts")
def list_drafts(account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    rows = db.scalars(select(IntakeDraft).where(IntakeDraft.account_id == account.id, IntakeDraft.status == "draft",
        IntakeDraft.created_at > utcnow() - timedelta(days=RETENTION_DAYS)).order_by(IntakeDraft.updated_at.desc())).all()
    return {"items": [view(db, draft) for draft in rows], "notice": NOTICE}

@router.post("/drafts", status_code=201)
def start(payload: Start, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    consent(payload)
    # Serialize starts for one account so active/daily limits also hold across workers.
    db.scalar(select(CustomerAccount).where(CustomerAccount.id == account.id).with_for_update())
    now = utcnow()
    count = db.scalar(select(func.count()).select_from(IntakeDraft).where(IntakeDraft.account_id == account.id, IntakeDraft.created_at >= now - timedelta(days=1)))
    active = db.scalar(select(func.count()).select_from(IntakeDraft).where(IntakeDraft.account_id == account.id, IntakeDraft.status == "draft", IntakeDraft.created_at > now - timedelta(days=RETENTION_DAYS)))
    if count >= 20 or active >= 5:
        raise HTTPException(429, "Resume or discard an existing draft. You can start up to five active drafts and twenty drafts in 24 hours.")
    answers = {k: v for k, v in {"customer_name": account.full_name, "email": account.email}.items() if v}
    if payload.service_slug:
        from .service_availability import accepts_requests, PAUSED
        selected = db.scalar(select(ServiceType).where(ServiceType.slug == payload.service_slug))
        if selected is not None and selected.is_active and not accepts_requests(db, payload.service_slug):
            raise HTTPException(409, PAUSED)
        validate(questions(db, {})[0], payload.service_slug)
        answers["service_slug"] = payload.service_slug
    form_snapshot = service_intake_forms.snapshot(db, payload.service_slug) if payload.service_slug else {}
    draft = IntakeDraft(account_id=account.id, answers=clean(db, answers, form_snapshot), service_form_snapshot=form_snapshot,
        saving_notice_version=NOTICE_VERSION, saving_consented_at=now)
    db.add(draft); db.commit()
    return view(db, draft)

@router.get("/drafts/{id}")
def get_draft(id: uuid.UUID, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    return view(db, _owned(db, id, account))

@router.patch("/drafts/{id}")
def answer(id: uuid.UUID, payload: Answer, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    draft = _owned(db, id, account, lock=True)
    editable(draft, payload.revision)
    answers = clean(db, draft.answers, draft.service_form_snapshot)
    rows = questions(db, answers, draft.service_form_snapshot)
    index = next((i for i, q in enumerate(rows) if q["key"] == payload.key), None)
    first = next((i for i, q in enumerate(rows) if q["key"] not in answers), len(rows))
    if index is None or (index > first and payload.key not in answers):
        raise HTTPException(422, "Answer the current question before continuing.")
    answers[payload.key] = validate(rows[index], payload.value)
    if payload.key == "service_slug" and answers[payload.key] != draft.answers.get("service_slug"):
        draft.service_form_snapshot = service_intake_forms.snapshot(db, answers[payload.key]) if draft.saving_notice_version == NOTICE_VERSION else {}
        # Even identical identifiers on different services must not carry answers over.
        answers = {key: value for key, value in answers.items() if not key.startswith("extra_")}
    draft.answers = clean(db, answers, draft.service_form_snapshot)
    draft.revision += 1
    draft.updated_at = utcnow()
    db.commit()
    return view(db, draft)

@router.delete("/drafts/{id}")
def discard(id: uuid.UUID, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    draft = _owned(db, id, account, lock=True)
    editable(draft, draft.revision)
    draft.answers, draft.status, draft.service_form_snapshot = {}, "discarded", {}
    draft.revision += 1
    db.commit()
    return {"message": "Draft answers removed."}

@router.post("/drafts/{id}/submit")
def submit(id: uuid.UUID, payload: Submit, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    draft = _owned(db, id, account, lock=True)
    if draft.status == "submitted":
        return _created(db, draft)
    editable(draft, payload.revision)
    consent(payload)
    answers = clean(db, draft.answers, draft.service_form_snapshot)
    if answers != draft.answers:
        raise HTTPException(409, "Available questions changed. Reload the saved answers and review them before submitting.")
    rows = questions(db, answers, draft.service_form_snapshot)
    if any(q["key"] not in answers for q in rows):
        raise HTTPException(422, "Finish the questions and review your answers before submitting.")
    service = db.scalar(select(ServiceType).where(ServiceType.slug == answers["service_slug"], ServiceType.is_active.is_(True)))
    if service is None:
        raise HTTPException(422, "Choose an available service.")
    property_intake = document_requirements.PropertyIntake.model_validate({k: v for k, v in answers.items() if k in document_requirements.PropertyIntake.model_fields}).model_dump()
    if answers["property_type"] in LAND:
        property_intake["development"] = "land"
    description = answers["goal"] + "\n\nAvailable documents: " + (answers.get("available_documents") or "Not specified")
    description += f"\nCustomer role: {answers['role']}\nPreferred follow-up: {answers['contact_preference']}"
    ticket = tickets.create_ticket(db, customer_name=answers["customer_name"], phone=account.phone_normalized,
        email=answers.get("email") or None, property_type=answers["property_type"], service=service, package=None,
        location=answers["location"], description=description, source="chat", property_intake=property_intake)
    ticket.prop.state = answers.get("state_name") if answers["state"] == "Other" else "Karnataka" if answers["state"] == "Karnataka" else None
    now = utcnow()
    guided = {"draft_id": str(draft.id), "answers": answers, "notice_version": NOTICE_VERSION, "consented_at": now.isoformat(),
              "submitted_answers": submitted_intake.capture(rows, answers),
              "service_form": draft.service_form_snapshot,
              "saving_notice_version": draft.saving_notice_version, "saving_consented_at": tickets.aware(draft.saving_consented_at).isoformat()}
    ticket.structured_answers = {**ticket.structured_answers, "guided_intake": guided}
    conversation = Conversation(customer_id=ticket.customer_id, property_id=ticket.property_id, service_type_id=service.id,
        state="submitted", intake_data=guided, consent_notice_version=NOTICE_VERSION, consented_at=now)
    db.add(conversation); db.flush()
    ticket.conversation_id = conversation.id
    for question in rows:
        value = answers[question["key"]]
        label = next((o["label"] for o in question["options"] if o["value"] == value), value) or "Skipped"
        db.add_all([ConversationMessage(conversation_id=conversation.id, sender_type="assistant", body=question["prompt"]),
                    ConversationMessage(conversation_id=conversation.id, sender_type="customer", body=label)])
    db.add(Consent(customer_id=ticket.customer_id, conversation_id=conversation.id, purpose="guided_service_request",
        notice_version=NOTICE_VERSION, consented=True, source="website", created_at=now))
    draft.answers, draft.status, draft.submitted_request_id = answers, "submitted", ticket.id
    draft.revision += 1
    tickets.audit(db, None, "intake.submitted", ticket.id, draft_id=str(draft.id), notice_version=NOTICE_VERSION)
    db.commit()
    return _created(db, draft)


def cleanup():
    from .db import SessionLocal
    with SessionLocal() as db:
        db.execute(delete(IntakeDraft).where(IntakeDraft.created_at <= utcnow() - timedelta(days=RETENTION_DAYS)))
        db.commit()


if __name__ == "__main__":
    cleanup()
