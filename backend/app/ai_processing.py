"""Customer-owned, case-scoped permission for external document AI processing."""
import hashlib
import json
import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import config
from .customer_auth import current_customer, owned_ticket
from .db import SessionLocal, get_db
from .models import AuditLog, CaseAIConsent, CustomerAccount, User, utcnow
from .security import current_staff
from .tickets import aware

router=APIRouter(prefix="/api/v1")
NOTICE_VERSION="external-document-ai-v1"
NOTICE=[
    "External AI processing is optional for this case. Uploading files and advocate review remain available if you do not allow it.",
    "If allowed, document text, filenames, scanned page images, property details and curated legal references may be sent to the named processor for upload checks and staff-requested case analysis.",
    "AI advice can be wrong. It cannot verify official records, approve a checklist or replace an advocate's signed opinion.",
    "You can withdraw permission for future processing. Requests already admitted or in progress cannot be recalled, and information already sent follows the processor's terms and privacy policy. Existing case records and analysis are retained under the case retention policy.",
    "Allowing permission does not automatically reprocess older uploads or retry previous analysis. Chat and legal research are separate services outside this case-document choice.",
]
MESSAGE="Customer approval for external AI document processing is required. The customer can review this case's choice on the Documents page. Local extraction remains available."


class ApprovalRequired(HTTPException):
    def __init__(self):super().__init__(409,MESSAGE)


class Choice(BaseModel):
    model_config=ConfigDict(extra="forbid")
    allowed: bool=Field(strict=True)
    revision: int=Field(ge=0,le=2147483646,strict=True)
    notice_version: str=Field(default="",max_length=40)
    processing_revision: str=Field(default="",max_length=64)


def disclosure():
    name=config.VERIFICATION_PROCESSOR_NAME.strip();url=config.VERIFICATION_PROCESSOR_PRIVACY_URL.strip()
    valid=False
    try:
        parsed=urlparse(url)
        valid=(2<=len(name)<=120 and not re.search(r"[\x00-\x1f\x7f<>]",name) and len(url)<=500
            and not re.search(r"[\s\x00-\x1f\x7f]",url) and parsed.scheme=="https" and bool(parsed.hostname)
            and not parsed.username and not parsed.password and (parsed.port is None or parsed.port>0)
            and config.VERIFICATION_LLM_PROVIDER in ("anthropic","openai"))
        if config.VERIFICATION_LLM_PROVIDER=="openai":
            base=urlparse(config.VERIFICATION_LLM_BASE_URL)
            valid=valid and base.scheme=="https" and bool(base.hostname) and not base.username and not base.password and (base.port is None or base.port>0)
    except ValueError:valid=False
    revision=hashlib.sha256(json.dumps({"notice":NOTICE_VERSION,"text":NOTICE,"provider":config.VERIFICATION_LLM_PROVIDER,
        "base":config.VERIFICATION_LLM_BASE_URL if config.VERIFICATION_LLM_PROVIDER=="openai" else "anthropic",
        "name":name,"privacy":url},sort_keys=True).encode()).hexdigest() if valid else None
    return {"configured":bool(valid),"processor":name if valid else None,"privacy_url":url if valid else None,
        "notice_version":NOTICE_VERSION,"processing_revision":revision,"paragraphs":NOTICE}


def approved(db,case_id,expected=None,*,lock=False):
    notice=disclosure()
    query=select(CaseAIConsent.allowed,CaseAIConsent.revision,CaseAIConsent.processing_revision).where(CaseAIConsent.service_request_id==case_id)
    if lock:query=query.with_for_update(read=True)
    row=db.execute(query).first()
    if not notice["configured"] or not row or not row.allowed or row.processing_revision!=notice["processing_revision"] or (expected is not None and row.revision!=expected):
        raise ApprovalRequired()
    return row.revision


def fresh(case_id,expected=None):
    with SessionLocal() as db:return approved(db,uuid.UUID(str(case_id)),expected)


def view(db,case_id):
    row=db.get(CaseAIConsent,case_id);notice=disclosure()
    status="not_allowed"
    if row and row.revision:
        status="withdrawn" if not row.allowed else "allowed" if notice["configured"] and row.processing_revision==notice["processing_revision"] else "review_required"
    return {"status":status,"allowed":status=="allowed","revision":row.revision if row else 0,
        "changed_at":aware(row.changed_at).isoformat() if row else None,"can_withdraw":bool(row and row.allowed),"disclosure":notice}


@router.get("/account/requests/{ticket_number}/ai-processing")
def customer_choice(ticket_number:str,account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    return view(db,owned_ticket(db,ticket_number,account).id)


@router.get("/admin/tickets/{ticket_number}/ai-processing")
def staff_choice(ticket_number:str,user:User=Depends(current_staff),db=Depends(get_db)):
    from .admin import _get_ticket
    return view(db,_get_ticket(db,user,ticket_number).id)


@router.put("/account/requests/{ticket_number}/ai-processing")
def change(ticket_number:str,payload:Choice,account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    ticket=owned_ticket(db,ticket_number,account)
    # Independent choice-row lock: withdrawal never waits on the case lock held
    # by legacy synchronous analysis. Initial insertion alone references the case.
    insert=pg_insert if db.bind.dialect.name=="postgresql" else sqlite_insert
    db.execute(insert(CaseAIConsent).values(service_request_id=ticket.id,allowed=False,revision=0,notice_snapshot={},changed_at=utcnow())
        .on_conflict_do_nothing(index_elements=[CaseAIConsent.service_request_id]))
    row=db.scalar(select(CaseAIConsent).where(CaseAIConsent.service_request_id==ticket.id).with_for_update().execution_options(populate_existing=True))
    if row.revision!=payload.revision:raise HTTPException(409,"The AI processing choice changed. Refresh it and review your decision again.")
    notice=disclosure()
    if payload.allowed and (not notice["configured"] or payload.notice_version!=NOTICE_VERSION or payload.processing_revision!=notice["processing_revision"]):
        raise HTTPException(409,"Processing information changed or is unavailable. Refresh and review the current notice before allowing it.")
    if row.revision and row.allowed==payload.allowed and (not payload.allowed or row.processing_revision==notice["processing_revision"]):return view(db,ticket.id)
    row.allowed=payload.allowed;row.revision+=1;row.customer_account_id=account.id;row.changed_at=utcnow()
    if payload.allowed:
        row.processing_revision=notice["processing_revision"];row.notice_version=NOTICE_VERSION;row.notice_snapshot=notice
    db.add(AuditLog(action="case.ai_processing_allowed" if payload.allowed else "case.ai_processing_withdrawn",entity_type="service_request",entity_id=ticket.id,
        metadata_={"revision":row.revision,"customer_account_id":str(account.id),"notice":row.notice_snapshot,"allowed":row.allowed}))
    db.commit()
    return view(db,ticket.id)
