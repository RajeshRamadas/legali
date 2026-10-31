"""Bridge evidence screening to the existing advocate-led report/signature flow."""
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import case_files, document_requirements, property_law, report_templates, tickets, verification
from .admin import _detail, _get_ticket
from .db import get_db
from .models import LawyerProfile, LegalReport, ReportItem, User, VerificationRun, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1/admin/tickets")

class DraftRequest(BaseModel):
    run_id: uuid.UUID

class LawReview(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=12)
    notes: str = Field(min_length=20, max_length=4000)
    current_law_and_applicability_confirmed: bool
    official_checks_reviewed: bool


def evidence_fingerprint(ticket):
    scope = verification.snapshot(ticket)
    return verification.fingerprint({key: scope[key] for key in ("documents", "property", "intake")})


def require_current_draft(ticket):
    marker = (ticket.structured_answers or {}).get("agent_report")
    if not marker or not ticket.report:
        raise HTTPException(409, "Prepare an agent report draft first.")
    if marker["evidence_fingerprint"] != evidence_fingerprint(ticket):
        raise HTTPException(409, "Case evidence or intake changed. Run verification again and refresh the draft before approval.")
    if marker["law_version"] != property_law.LAW_VERSION:
        raise HTTPException(409, "The law reference pack changed. Refresh the analysis and report before approval.")
    return marker


@router.post("/{ticket_number}/verification/report-draft")
def draft(ticket_number: str, payload: DraftRequest, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    run = db.get(VerificationRun, payload.run_id)
    if run is None or run.service_request_id != ticket.id:
        raise HTTPException(404, "Verification run not found")
    if verification.view(run, ticket)["stale"]:
        raise HTTPException(409, "This analysis is out of date. Run verification again before drafting.")
    result = run.result
    if result["llm_status"] != "completed":
        raise HTTPException(409, "Complete LLM evidence analysis before preparing an agent report draft.")
    if result["state"].lower() != "karnataka":
        raise HTTPException(409, "This report workflow currently supports Karnataka. Other states need a specialist report.")
    report = ticket.report
    if report and report.status in ("signed", "final_generated"):
        raise HTTPException(409, "A final report is already on file; it cannot be overwritten by the agent.")
    old_marker = (ticket.structured_answers or {}).get("agent_report", {})
    if report and any((report.final or {}).values()) and old_marker.get("draft_hash") != verification.fingerprint(report.final):
        raise HTTPException(409, "The report contains advocate-written text. Preserve it; the agent will not overwrite it.")
    if report is None:
        report = LegalReport(service_request_id=ticket.id, lawyer_user_id=user.id,
            preliminary=report_templates.blank_sections(report_templates.PRELIMINARY_SECTIONS), final={})
        report.items = [ReportItem(**i, position=n, status="pending") for n, i in enumerate(document_requirements.checklist(ticket))]
        ticket.report = report
        db.add(report)
    lines = ["AUTOMATED DRAFT - requires advocate review", result["reason"], "Screening verdict: " + result["verdict"]]
    for finding in result["findings"]:
        lines += [finding["severity"].upper() + ": " + finding["title"], finding["reason"]]
        for evidence in finding["evidence"]:
            doc = next(d for d in result["documents"] if d["id"] == evidence["document_id"])
            lines.append(f"{doc['filename']}, page/part {evidence['page']}: {evidence['quote']}")
        lines.append("Legal references: " + "; ".join(property_law.BY_ID[key]["act"] + " - " + property_law.BY_ID[key]["sections"] for key in finding["law_ids"]))
    chain_lines = [result.get("title_chain", {}).get("note", "Title chain requires advocate reconstruction.")]
    for transfer in result.get("title_chain", {}).get("transfers", []):
        chain_lines.append(transfer["filename"])
        for field, facts in transfer["fields"].items():
            for fact in facts:
                chain_lines.append(f"{field}: {fact['value']} (page/part {fact['evidence']['page']}: {fact['evidence']['quote']})")
        chain_lines += transfer["gaps"]
    legal_references = [f"{law['act']} - {law['sections']}\n{law['principle']}\nOfficial reference: {law['url']}" for law in result.get("laws", verification.applicable_laws("Karnataka"))]
    report.final = {**report_templates.blank_sections(report_templates.FINAL_SECTIONS),
        "title_flow": "\n".join(chain_lines), "opinion": "\n".join(lines),
        "conditions": "\n\n".join([c["title"] + ": " + c["action"] for c in result["open_checks"]] + result["limitations"] +
            ["Legal reference pack " + result["law_version"] + ": current amendments, applicability and case law must be confirmed before finalisation."] + legal_references)}
    for key in report.final:
        # Keep the complete evidence run separately; avoid silently truncating report sections.
        if len(report.final[key]) > 8000:
            raise HTTPException(422, "This analysis is too large for a report section. Prepare the report manually using the exported evidence report.")
    db.flush()
    case_files.sync_items(ticket)
    marker = {"run_id": str(run.id), "evidence_fingerprint": evidence_fingerprint(ticket), "law_version": result["law_version"],
              "draft_hash": verification.fingerprint(report.final), "approval": None}
    ticket.structured_answers = {**(ticket.structured_answers or {}), "agent_report": marker}
    tickets.add_event(db, ticket, "agent_report_drafted", user, new={"run_id": str(run.id)})
    tickets.audit(db, user, "verification.report_drafted", ticket.id, run_id=str(run.id))
    db.commit()
    return _detail(db, ticket)


@router.post("/{ticket_number}/verification/approve")
def approve(ticket_number: str, payload: LawReview, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = _get_ticket(db, user, ticket_number)
    marker = require_current_draft(ticket)
    profile = db.scalar(select(LawyerProfile).where(LawyerProfile.user_id == user.id))
    if profile is None or not (profile.bar_enrolment or "").strip():
        raise HTTPException(403, "An advocate profile with a recorded bar enrolment is required for this approval.")
    if ticket.report.status in ("signed", "final_generated"):
        raise HTTPException(409, "The final report is already on file.")
    if not payload.current_law_and_applicability_confirmed or not payload.official_checks_reviewed:
        raise HTTPException(422, "Confirm current-law applicability and review of the independent checks.")
    if len(payload.notes.strip()) < 20:
        raise HTTPException(422, "Provide substantive advocate review notes.")
    if document_requirements.intake(ticket)["state"] != "Karnataka" or document_requirements.view(ticket)["questions"]:
        raise HTTPException(409, "Resolve the outstanding property-intake questions before advocate approval.")
    if not case_files.checklist_complete(ticket.report):
        raise HTTPException(409, "Resolve every checklist item before advocate approval.")
    if any(i.status == "waived" and len((i.review_note or "").strip()) < 20 for i in ticket.report.items):
        raise HTTPException(409, "Explain the reason for every waived document before approval.")
    if (ticket.report.final or {}).get("opinion", "").startswith("AUTOMATED DRAFT"):
        raise HTTPException(409, "Replace the automated draft opinion with the advocate's reasoned opinion before approval.")
    for item in ticket.report.items:
        if item.status == "verified" and not any(d.tag == item.tag for d in case_files.case_documents(ticket)) and len((item.review_note or "").strip()) < 20:
            raise HTTPException(409, "Each verified item needs an attached record or substantive verification notes.")
    for source in payload.sources:
        url = urlparse(source)
        host = (url.hostname or "").lower()
        if len(source) > 1000 or url.scheme != "https" or url.username or url.password or not (host == "indiacode.nic.in" or host.endswith(".gov.in") or host.endswith(".nic.in")):
            raise HTTPException(422, "Record HTTPS official government or court source links for the law review.")
    approval = {"by": str(user.id), "name": user.display_name, "bar_enrolment": profile.bar_enrolment,
        "at": utcnow().isoformat(), "sources": payload.sources, "notes": payload.notes.strip(),
        "report_hash": verification.fingerprint(ticket.report.final),
        "checklist_hash": verification.fingerprint(verification.snapshot(ticket)["checklist"]),
        "law_version": marker["law_version"]}
    ticket.structured_answers = {**ticket.structured_answers, "agent_report": {**marker, "approval": approval}}
    ticket.report.lawyer_user_id = user.id
    tickets.audit(db, user, "verification.advocate_approved", ticket.id, run_id=marker["run_id"])
    db.commit()
    return _detail(db, ticket)


def validate_final_approval(ticket):
    marker = (ticket.structured_answers or {}).get("agent_report")
    if not marker:
        return
    require_current_draft(ticket)
    approval = marker.get("approval")
    if not approval or approval["report_hash"] != verification.fingerprint(ticket.report.final) or approval["checklist_hash"] != verification.fingerprint(verification.snapshot(ticket)["checklist"]):
        raise HTTPException(409, "Record advocate approval of this report, current laws and independent checks before generating the final PDF. Changes to the report or checklist require fresh approval.")
