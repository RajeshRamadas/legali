"""Customer document repository and legal reports on a ticket.

Customers upload documents to their ticket and tag them. The lawyer writes a preliminary report with a checklist of the
documents needed, each with a tag; customers file uploads under those tags (or retag earlier ones), and public records go
to the case team to fetch from government portals. The lawyer verifies each item, and once all are verified or waived
generates the final report as a PDF, prints it, signs it and uploads the signed scan, which the customer can download.
"""
import hashlib
import os
import re
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import case_files, config, gov_sources, report_pdf, report_templates, storage, tickets, document_requirements, upload_check
from .admin import _detail, _get_ticket, _visible_tickets
from .db import get_db
from .models import (
    CLOSED_STATUSES, Document, LawyerProfile, LegalReport, ReportItem, ServiceRequest, User, utcnow,
)
from .public import _find_for_customer
from .security import current_staff

router = APIRouter(prefix="/api/v1")

# Extension -> stored content type, and the leading bytes the file must start with (None: not checked).
ALLOWED_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".webp": ("image/webp", (b"RIFF",)),
    ".heic": ("image/heic", None),
    ".doc": ("application/msword", (b"\xd0\xcf\x11\xe0",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
}
SIGNED_TYPES = (".pdf", ".jpg", ".jpeg", ".png")
ALLOWED_LABEL = "PDF, JPG, PNG, WEBP, HEIC, DOC or DOCX"

class CustomerRef(BaseModel):
    ticket_number: str = Field(min_length=5, max_length=40)
    contact: str = Field(min_length=5, max_length=254)

class CustomerTag(CustomerRef):
    document_id: uuid.UUID
    tag: str = Field(default="", max_length=60, description="Empty string removes the tag.")

class CustomerDelete(CustomerRef):
    document_id: uuid.UUID

class IntakeUpdate(CustomerRef):
    intake: document_requirements.PropertyIntake

@router.post("/tickets/property-intake")
def customer_intake(payload: IntakeUpdate, db: Session = Depends(get_db)):
    ticket = _customer_ticket(db, payload.ticket_number, payload.contact)
    if ticket.report and ticket.report.status in ("issued", "final_generated", "signed"):
        raise HTTPException(409, "The advocate has issued your checklist. Send corrections to the case team so they can review it.")
    values = payload.intake.model_dump()
    if document_requirements.intake(ticket) != values:
        ticket.structured_answers = {**(ticket.structured_answers or {}), "property_intake": values}
        if ticket.prop:
            for field in ("survey_number", "property_id_or_pid", "village", "taluk", "district"):
                if values[field].strip():
                    setattr(ticket.prop, field, values[field].strip())
        request = document_requirements.view(ticket)
        tickets.add_event(db, ticket, "intake_updated", new={"state": values["state"]})
        from .models import TicketMessage
        ticket.messages.append(TicketMessage(service_request_id=ticket.id, author_type="system", visibility="customer", message=request["prompt"]))
        tickets.queue_notifications(db, ticket, "documents_requested", f"{ticket.ticket_number}: {request['prompt']}")
        ticket.updated_at = utcnow()
        db.commit()
    return tickets.customer_view(ticket)

class StaffTag(BaseModel):
    tag: str = Field(default="", max_length=60)

class ItemIn(BaseModel):
    id: uuid.UUID | None = None
    label: str = Field(min_length=2, max_length=160)
    guidance: str = Field(default="", max_length=500)
    # Only used for new items; empty makes one from the label.
    tag: str = Field(default="", max_length=60)
    fetch_by: Literal["customer", "homexo"] = "customer"
    source: str | None = Field(default=None, max_length=40)

class ReportSave(BaseModel):
    preliminary: dict[str, str] | None = None
    final: dict[str, str] | None = None
    items: list[ItemIn] | None = Field(default=None, max_length=60)
    lawyer_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = Field(default=None, description="Second signature on the final report. Null clears it.")

class ItemReview(BaseModel):
    status: Literal["pending", "verified", "rejected", "waived"]
    note: str | None = Field(default=None, max_length=1000, description="Shown to the customer, required when rejecting.")
    fetch_by: Literal["customer", "homexo"] | None = None

class PropertyDetails(BaseModel):
    address_line: str | None = Field(default=None, max_length=300)
    survey_number: str | None = Field(default=None, max_length=60)
    subdivision_or_surnoc: str | None = Field(default=None, max_length=60)
    property_id_or_pid: str | None = Field(default=None, max_length=60)
    village: str | None = Field(default=None, max_length=100)
    hobli: str | None = Field(default=None, max_length=100)
    taluk: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)

# ---- Storing files ----

def _clean_filename(name: str | None) -> str:
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip() or "document"
    stem, ext = os.path.splitext(name)
    return stem[:120] + ext[:10]

def _read_upload(upload: UploadFile, allowed: tuple[str, ...] = tuple(ALLOWED_TYPES)) -> tuple[str, str, bytes]:
    filename = _clean_filename(upload.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=422, detail=f"Upload a {ALLOWED_LABEL if allowed == tuple(ALLOWED_TYPES) else ', '.join(e[1:].upper() for e in allowed)} file.")
    limit = config.UPLOAD_MAX_MB * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Files can be up to {config.UPLOAD_MAX_MB} MB.")
    if not data:
        raise HTTPException(status_code=422, detail="That file is empty.")
    content_type, magic = ALLOWED_TYPES[ext]
    # Trust the bytes, not the name: a renamed executable must not pass as a PDF.
    if magic and not any(data.startswith(m) for m in magic):
        raise HTTPException(status_code=422, detail=f"That file doesn't look like a {ext[1:].upper()}.")
    return filename, content_type, data

def store_document(db: Session, ticket: ServiceRequest, filename: str, content_type: str, data: bytes, *, uploader_type: str,
                   user: User | None = None, tag: str | None = None, note: str | None = None, category: str | None = None) -> Document:
    if category is None and len(case_files.case_documents(ticket)) >= config.MAX_DOCUMENTS_PER_TICKET:
        raise HTTPException(status_code=409, detail="This request already has the most files it can hold. Ask the case team for help.")
    document_id = uuid.uuid4()
    key = f"tickets/{ticket.ticket_number}/{document_id.hex}{os.path.splitext(filename)[1].lower()}"
    storage.put(key, data, content_type)
    document = Document(
        id=document_id, service_request_id=ticket.id, uploaded_by_user_id=user.id if user else None, uploader_type=uploader_type,
        original_filename=filename, content_type=content_type, byte_size=len(data), storage_key=key,
        checksum_sha256=hashlib.sha256(data).hexdigest(), tag=tag or None, note=(note or "").strip() or None, document_category=category,
        created_at=utcnow(),
    )
    db.add(document)
    ticket.documents.append(document)
    return document

def _remove_document(db: Session, ticket: ServiceRequest, document: Document) -> None:
    ticket.documents.remove(document)
    db.delete(document)
    db.flush()
    storage.delete(document.storage_key)

def _ticket_document(ticket: ServiceRequest, document_id: uuid.UUID) -> Document:
    document = next((d for d in case_files.case_documents(ticket) if d.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

def _all_items_received(ticket: ServiceRequest) -> bool:
    report = ticket.report
    return bool(report and report.items) and all(i.status != "pending" and i.status != "rejected" for i in report.items if i.fetch_by == "customer")

def _after_customer_files(db: Session, ticket: ServiceRequest) -> None:
    case_files.sync_items(ticket)
    # The last document asked for hands the ticket back to the team.
    if ticket.status == "waiting_for_customer" and ticket.report and ticket.report.status == "issued" and _all_items_received(ticket):
        tickets.change_status(db, ticket, "under_review", None, "Thanks, we have every document we asked you for.")

# ---- Customers ----

def _customer_ticket(db: Session, ticket_number: str, contact: str) -> ServiceRequest:
    ticket = _find_for_customer(db, ticket_number, contact)
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="This request is closed, so its documents can't be changed.")
    return ticket

def _check_customer_tag(ticket: ServiceRequest, tag: str) -> None:
    if tag and tag in case_files.locked_tags(ticket):
        raise HTTPException(status_code=409, detail="The lawyer has already accepted the documents under this tag.")

@router.post("/tickets/documents", status_code=201)
def customer_upload(
    background: BackgroundTasks, ticket_number: str = Form(min_length=5, max_length=40), contact: str = Form(min_length=5, max_length=254),
    tag: str = Form(default="", max_length=60), note: str = Form(default="", max_length=500), file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ticket = _customer_ticket(db, ticket_number, contact)
    tag = report_templates.normalize_tag(tag)
    _check_customer_tag(ticket, tag)
    filename, content_type, data = _read_upload(file)
    document = store_document(db, ticket, filename, content_type, data, uploader_type="customer", tag=tag, note=note)
    tickets.add_event(db, ticket, "document_uploaded", new={"filename": filename, "tag": tag or None, "by": "customer"})
    _after_customer_files(db, ticket)
    ticket.updated_at = utcnow()
    db.commit()
    if upload_check.enabled():
        background.add_task(upload_check.run, document.id)
    return tickets.customer_view(ticket)

@router.post("/tickets/documents/tag")
def customer_tag(payload: CustomerTag, db: Session = Depends(get_db)):
    """File an earlier upload under another tag, e.g. one the preliminary report asks for."""
    ticket = _customer_ticket(db, payload.ticket_number, payload.contact)
    document = _ticket_document(ticket, payload.document_id)
    if document.uploader_type != "customer":
        raise HTTPException(status_code=403, detail="Only the case team can retag files they added.")
    tag = report_templates.normalize_tag(payload.tag)
    _check_customer_tag(ticket, document.tag or "")
    _check_customer_tag(ticket, tag)
    document.tag = tag or None
    _after_customer_files(db, ticket)
    db.commit()
    return tickets.customer_view(ticket)

@router.post("/tickets/documents/delete")
def customer_delete(payload: CustomerDelete, db: Session = Depends(get_db)):
    ticket = _customer_ticket(db, payload.ticket_number, payload.contact)
    document = _ticket_document(ticket, payload.document_id)
    if document.uploader_type != "customer":
        raise HTTPException(status_code=403, detail="Only the case team can remove files they added.")
    _check_customer_tag(ticket, document.tag or "")
    tickets.add_event(db, ticket, "document_removed", old={"filename": document.original_filename, "tag": document.tag, "by": "customer"})
    _remove_document(db, ticket, document)
    case_files.sync_items(ticket)
    db.commit()
    return tickets.customer_view(ticket)

# ---- Downloads ----

@router.get("/files/{token}")
def download(token: str, db: Session = Depends(get_db)):
    """Signed, short-lived links handed out in ticket views, so the browser can open files without a header."""
    claims = case_files.read_download_token(token)
    if claims is None:
        raise HTTPException(status_code=404, detail="This link has expired. Open the request again for a fresh one.")
    if "doc" in claims:
        document = db.get(Document, uuid.UUID(claims["doc"]))
        if document is None:
            raise HTTPException(status_code=404, detail="File not found")
        inline = document.content_type == "application/pdf" or document.content_type.startswith("image/")
        return storage.download_response(document.storage_key, document.original_filename, document.content_type, inline=inline)
    report = db.get(LegalReport, uuid.UUID(claims["report"])) if claims.get("kind") == "preliminary" else None
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    ticket = db.get(ServiceRequest, report.service_request_id)
    pdf = report_pdf.preliminary_pdf(ticket, report)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{ticket.ticket_number}-preliminary-report.pdf"', "Cache-Control": "private, no-store",
    })

# ---- Staff: documents ----

@router.post("/admin/tickets/{ticket_number}/documents", status_code=201)
def staff_upload(
    background: BackgroundTasks, ticket_number: str, tag: str = Form(default="", max_length=60), note: str = Form(default="", max_length=500),
    file: UploadFile = File(...), user: User = Depends(current_staff), db: Session = Depends(get_db),
):
    """Files the team adds, e.g. an EC fetched from Kaveri, filed under the checklist item's tag."""
    ticket = _get_ticket(db, user, ticket_number)
    filename, content_type, data = _read_upload(file)
    tag = report_templates.normalize_tag(tag)
    document = store_document(db, ticket, filename, content_type, data, uploader_type="staff", user=user, tag=tag, note=note)
    tickets.add_event(db, ticket, "document_uploaded", user, new={"filename": filename, "tag": tag or None, "by": "staff"})
    case_files.sync_items(ticket)
    tickets.audit(db, user, "document.uploaded", ticket.id, filename=filename, tag=tag)
    ticket.updated_at = utcnow()
    db.commit()
    if upload_check.enabled():
        background.add_task(upload_check.run, document.id)
    return _detail(db, ticket)

@router.patch("/admin/tickets/{ticket_number}/documents/{document_id}")
def staff_tag(ticket_number: str, document_id: uuid.UUID, payload: StaffTag, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    document = _ticket_document(ticket, document_id)
    document.tag = report_templates.normalize_tag(payload.tag) or None
    case_files.sync_items(ticket)
    db.commit()
    return _detail(db, ticket)

@router.post("/admin/tickets/{ticket_number}/documents/{document_id}/check")
def staff_recheck(ticket_number: str, document_id: uuid.UUID, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Run the automatic upload check again, e.g. after it failed or the provider was configured later."""
    ticket = _get_ticket(db, user, ticket_number)
    document = _ticket_document(ticket, document_id)
    if not upload_check.enabled():
        raise HTTPException(status_code=409, detail="Automatic upload checks are off or the LLM is not configured on the server.")
    upload_check.run(document.id)
    db.expire_all()
    return _detail(db, _get_ticket(db, user, ticket_number))

@router.delete("/admin/tickets/{ticket_number}/documents/{document_id}")
def staff_delete(ticket_number: str, document_id: uuid.UUID, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    document = _ticket_document(ticket, document_id)
    if ticket.report and ticket.report.status in ("final_generated", "signed"):
        raise HTTPException(status_code=409, detail="The final report lists these files, so they are kept.")
    tickets.add_event(db, ticket, "document_removed", user, old={"filename": document.original_filename, "tag": document.tag, "by": "staff"})
    tickets.audit(db, user, "document.deleted", ticket.id, filename=document.original_filename, checksum=document.checksum_sha256)
    _remove_document(db, ticket, document)
    case_files.sync_items(ticket)
    db.commit()
    return _detail(db, ticket)

@router.patch("/admin/tickets/{ticket_number}/property")
def update_property(ticket_number: str, payload: PropertyDetails, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Identifiers the government portals search by (survey number, PID, village ...)."""
    ticket = _get_ticket(db, user, ticket_number)
    if ticket.prop is None:
        raise HTTPException(status_code=409, detail="This ticket has no property record.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ticket.prop, field, (value or "").strip() or None)
    db.commit()
    return _detail(db, ticket)

# ---- Staff: report ----

@router.get("/admin/report-template")
def report_template(ticket: str | None = None, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Starting text for each section and a checklist for the ticket's property type, plus the government portals."""
    property_type = None
    if ticket:
        found = _get_ticket(db, user, ticket)
        property_type = found.prop.property_type if found.prop else None
    return {
        "preliminary": [{"key": k, "heading": h, "hint": hint, "text": t} for k, h, hint, t in report_templates.PRELIMINARY_SECTIONS],
        "final": [{"key": k, "heading": h, "hint": hint, "text": t} for k, h, hint, t in report_templates.FINAL_SECTIONS],
        "items": document_requirements.checklist(found) if ticket else report_templates.checklist_for(property_type),
        "sources": [gov_sources.source_view(key) for key in gov_sources.SOURCES],
    }

def _editable_report(ticket: ServiceRequest) -> LegalReport:
    report = ticket.report
    if report is None:
        raise HTTPException(status_code=404, detail="Write the preliminary report first.")
    if report.status == "signed":
        raise HTTPException(status_code=409, detail="The signed final report is on file, so the report can't change.")
    return report

def _staff_user(db: Session, user_id: uuid.UUID) -> User:
    staff = db.get(User, user_id)
    if staff is None or staff.account_status != "active" or not (staff.role_names & {"agent", "admin", "super_admin"}):
        raise HTTPException(status_code=422, detail="Choose an active staff member.")
    return staff

def _clean_sections(values: dict[str, str], sections: tuple) -> dict:
    keys = {k for k, *_ in sections}
    return {k: v.strip()[:8000] for k, v in values.items() if k in keys}

def _save_items(db: Session, report: LegalReport, items: list[ItemIn]) -> None:
    existing = {i.id: i for i in report.items}
    kept: list[ReportItem] = []
    taken: set[str] = set()
    for position, item_in in enumerate(items):
        source = item_in.source if item_in.source in gov_sources.SOURCES else None
        item = existing.get(item_in.id) if item_in.id else None
        if item is None:
            wanted = report_templates.normalize_tag(item_in.tag)
            tag = wanted if wanted and wanted not in taken else report_templates.make_tag(item_in.tag or item_in.label, taken)
            item = ReportItem(tag=tag, label="", fetch_by="customer")
            if source is None:
                source = gov_sources.source_for(tag)
        item.label, item.guidance, item.position = item_in.label.strip(), item_in.guidance.strip(), position
        item.fetch_by, item.source = item_in.fetch_by, source
        if item.tag in taken:
            raise HTTPException(status_code=422, detail=f"Two checklist items use the tag #{item.tag}.")
        taken.add(item.tag)
        kept.append(item)
    for item in report.items:
        if item not in kept and item.status == "verified":
            raise HTTPException(status_code=409, detail=f"#{item.tag} is already verified. Set it back to waiting before removing it.")
    report.items = kept

@router.put("/admin/tickets/{ticket_number}/report")
def save_report(ticket_number: str, payload: ReportSave, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Create or edit the report: section text, checklist items and signatories. Editing after the final PDF was made
    takes the report back to collecting documents, so the PDF has to be generated again."""
    ticket = _get_ticket(db, user, ticket_number)
    report = ticket.report
    if report is None:
        report = LegalReport(
            service_request_id=ticket.id, lawyer_user_id=user.id, items=[],
            preliminary=report_templates.blank_sections(report_templates.PRELIMINARY_SECTIONS), final=report_templates.blank_sections(report_templates.FINAL_SECTIONS),
        )
        db.add(report)
        ticket.report = report
        tickets.add_event(db, ticket, "report_started", user)
    report = _editable_report(ticket)
    if payload.preliminary is not None:
        report.preliminary = {**report.preliminary, **_clean_sections(payload.preliminary, report_templates.PRELIMINARY_SECTIONS)}
    if payload.final is not None:
        report.final = {**report.final, **_clean_sections(payload.final, report_templates.FINAL_SECTIONS)}
    if payload.items is not None:
        _save_items(db, report, payload.items)
    if payload.lawyer_id:
        report.lawyer_user_id = _staff_user(db, payload.lawyer_id).id
    if "reviewer_id" in payload.model_fields_set:
        report.reviewer_user_id = _staff_user(db, payload.reviewer_id).id if payload.reviewer_id else None
    if report.status == "final_generated":
        report.status = "issued"
    db.flush()
    db.expire(report, ["lawyer", "reviewer"])
    case_files.sync_items(ticket)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.post("/admin/tickets/{ticket_number}/report/issue")
def issue_report(ticket_number: str, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Send the preliminary report to the customer, who then sees the checklist and files uploads under its tags."""
    ticket = _get_ticket(db, user, ticket_number)
    report = _editable_report(ticket)
    if not report.items:
        raise HTTPException(status_code=422, detail="Add at least one document to the checklist.")
    first = report.status == "draft"
    if first:
        report.status = "issued"
        report.issued_at = utcnow()
    case_files.sync_items(ticket)
    mine = [i for i in report.items if i.fetch_by == "customer" and i.status in ("pending", "rejected")]
    ours = [i for i in report.items if i.fetch_by == "homexo"]
    tickets.add_event(db, ticket, "report_issued" if first else "report_updated", user, new={"items": len(report.items)})
    note = f"Your preliminary report is ready. Please upload {len(mine)} document{'s' if len(mine) != 1 else ''} under the tags shown." if mine else "Your preliminary report is ready."
    if ours:
        note += f" We will get {len(ours)} public record{'s' if len(ours) != 1 else ''} from the government portals for you."
    if mine and ticket.status not in CLOSED_STATUSES and ticket.status != "waiting_for_customer":
        tickets.change_status(db, ticket, "waiting_for_customer", user, note)
    else:
        tickets.queue_notifications(db, ticket, "report_issued", f"Homexo Legal: {note} Ticket {ticket.ticket_number}.")
    tickets.audit(db, user, "report.issued", ticket.id)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.patch("/admin/tickets/{ticket_number}/report/items/{item_id}")
def review_item(ticket_number: str, item_id: uuid.UUID, payload: ItemReview, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    report = _editable_report(ticket)
    item = next((i for i in report.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    note = (payload.note or "").strip() or None
    if payload.status == "rejected" and not note:
        raise HTTPException(status_code=422, detail="Tell the customer what is wrong with the document.")
    if payload.fetch_by:
        item.fetch_by = payload.fetch_by
    old = item.status
    item.status, item.review_note = payload.status, note
    item.reviewed_by_user_id, item.reviewed_at = user.id, utcnow()
    if payload.status == "pending":
        item.review_note = None
        case_files.sync_items(ticket)
    if report.status == "final_generated":
        report.status = "issued"
    tickets.add_event(db, ticket, "report_item_reviewed", user, old={"tag": item.tag, "status": old}, new={"tag": item.tag, "status": item.status}, reason=item.review_note)
    if payload.status == "rejected" and item.fetch_by == "customer" and report.status != "draft":
        tickets.queue_notifications(db, ticket, "document_rejected", f"Homexo Legal: please upload {item.label} again under #{item.tag} for {ticket.ticket_number}. {note}")
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

@router.post("/admin/tickets/{ticket_number}/report/final")
def generate_final(ticket_number: str, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Make the final report PDF to print and sign. Needs every checklist item verified or waived."""
    ticket = _get_ticket(db, user, ticket_number)
    report = _editable_report(ticket)
    from .verification_workflow import validate_final_approval
    validate_final_approval(ticket)
    if report.status == "draft":
        raise HTTPException(status_code=409, detail="Issue the preliminary report first.")
    if not case_files.checklist_complete(report):
        left = [f"#{i.tag}" for i in report.items if i.status not in case_files.DONE_ITEM_STATUSES]
        raise HTTPException(status_code=409, detail=f"Verify or waive every checklist item first. Still open: {', '.join(left)}.")
    if not (report.final or {}).get("opinion", "").strip():
        raise HTTPException(status_code=422, detail="Write the opinion before generating the final report.")
    now = utcnow()
    signers = [i for i in (report.lawyer_user_id, report.reviewer_user_id) if i]
    enrolments = dict(db.execute(select(LawyerProfile.user_id, LawyerProfile.bar_enrolment).where(LawyerProfile.user_id.in_(signers))).all()) if signers else {}
    pdf = report_pdf.final_pdf(ticket, report, case_files.case_documents(ticket), enrolments, now)
    old = db.get(Document, report.final_document_id) if report.final_document_id else None
    document = store_document(db, ticket, f"{ticket.ticket_number}-final-report.pdf", "application/pdf", pdf, uploader_type="system", user=user, category="final_report")
    db.flush()
    report.final_document_id, report.final_generated_at, report.status = document.id, now, "final_generated"
    if old:
        # Only the latest draft for signature is kept.
        _remove_document(db, ticket, old)
    tickets.add_event(db, ticket, "final_report_generated", user)
    tickets.audit(db, user, "report.final_generated", ticket.id, checksum=document.checksum_sha256)
    ticket.updated_at = now
    db.commit()
    return _detail(db, ticket)

@router.post("/admin/tickets/{ticket_number}/report/signed")
def upload_signed(ticket_number: str, file: UploadFile = File(...), user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """The scan of the printed final report, signed by the advocates. The customer can download it from then on."""
    ticket = _get_ticket(db, user, ticket_number)
    report = ticket.report
    if report is None or report.status != "final_generated":
        raise HTTPException(status_code=409, detail="Generate the final report, print it and sign it first.")
    filename, content_type, data = _read_upload(file, SIGNED_TYPES)
    ext = os.path.splitext(filename)[1].lower()
    document = store_document(db, ticket, f"{ticket.ticket_number}-signed-report{ext}", content_type, data, uploader_type="staff", user=user, category="signed_report")
    db.flush()
    report.signed_document_id, report.signed_at, report.status = document.id, utcnow(), "signed"
    tickets.add_event(db, ticket, "report_signed", user)
    tickets.queue_notifications(db, ticket, "report_signed", f"Homexo Legal: your signed legal report for {ticket.ticket_number} is ready to download on the Track your request page.")
    tickets.audit(db, user, "report.signed_uploaded", ticket.id, checksum=document.checksum_sha256)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)

# ---- Staff: government fetch queue ----

@router.get("/admin/fetch-queue")
def fetch_queue(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Public records the team gets from government portals so the buyer doesn't have to, across visible tickets."""
    visible = _visible_tickets(user).subquery()
    rows = db.execute(
        select(ReportItem, LegalReport.service_request_id)
        .join(LegalReport, LegalReport.id == ReportItem.report_id)
        .where(LegalReport.service_request_id.in_(select(visible.c.id)), LegalReport.status == "issued",
               ReportItem.fetch_by == "homexo", ReportItem.status.in_(("pending", "rejected")))
        .order_by(LegalReport.issued_at, ReportItem.position)
    ).all()
    items = []
    for item, ticket_id in rows:
        ticket = db.get(ServiceRequest, ticket_id)
        prop = ticket.prop
        items.append({
            "ticket_number": ticket.ticket_number,
            "customer_name": (ticket.structured_answers or {}).get("customer_name") or ticket.customer.full_name,
            "item": {"id": str(item.id), "tag": item.tag, "label": item.label, "guidance": item.guidance, "status": item.status, "note": item.review_note},
            "source": gov_sources.source_view(item.source),
            "property": tickets.property_view(prop) if prop else None,
        })
    # Intake requests create official-record tasks immediately, without pretending a lawyer has issued a report.
    for ticket in db.scalars(_visible_tickets(user).where(ServiceRequest.status.not_in(CLOSED_STATUSES))).unique().all():
        if ticket.report and ticket.report.status != "draft":
            continue
        for item in document_requirements.view(ticket)["items"]:
            if item["fetch_by"] == "homexo" and item["status"] == "pending":
                items.append({"ticket_number": ticket.ticket_number, "customer_name": ticket.customer.full_name,
                    "item": {key: item[key] for key in ("id", "tag", "label", "guidance", "status", "note")},
                    "source": item["source"], "property": tickets.property_view(ticket.prop) if ticket.prop else None})
    return {"items": items, "sources": [gov_sources.source_view(key) for key in gov_sources.SOURCES]}

@router.patch("/admin/tickets/{ticket_number}/property-intake")
def staff_intake(ticket_number: str, payload: document_requirements.PropertyIntake,
                 user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    if ticket.report and ticket.report.status == "signed":
        raise HTTPException(409, "The signed report is on file. Its intake cannot be changed.")
    values = payload.model_dump()
    if document_requirements.intake(ticket) == values:
        return _detail(db, ticket)
    ticket.structured_answers = {**(ticket.structured_answers or {}), "property_intake": values}
    if ticket.prop:
        for field in ("survey_number", "property_id_or_pid", "village", "taluk", "district"):
            if values[field].strip():
                setattr(ticket.prop, field, values[field].strip())
    if ticket.report:
        existing = {i.tag: i for i in ticket.report.items}
        for item in document_requirements.checklist(ticket):
            if item["tag"] not in existing:
                ticket.report.items.append(ReportItem(**item, position=len(ticket.report.items), status="pending"))
        if values["state"] != "Karnataka":
            for item in ticket.report.items:
                item.source = None
        else:
            for item in ticket.report.items:
                if not item.source:
                    item.source = gov_sources.source_for(item.tag)
        if ticket.report.status == "final_generated":
            ticket.report.status = "issued"
        case_files.sync_items(ticket)
    tickets.add_event(db, ticket, "intake_updated", user, new={"state": values["state"]})
    tickets.queue_notifications(db, ticket, "documents_requested", f"{ticket.ticket_number}: {document_requirements.view(ticket)['prompt']}")
    tickets.audit(db, user, "property.intake_updated", ticket.id)
    ticket.updated_at = utcnow()
    db.commit()
    return _detail(db, ticket)
