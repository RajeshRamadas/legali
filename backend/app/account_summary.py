"""Verified-owner activity summaries, with explicit field and collection limits."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from . import ai_processing, notification_preferences, tickets
from .customer_auth import current_customer
from .db import get_db
from .models import AuditLog, CaseAIConsent, CaseDocumentHold, Customer, CustomerAccount, CustomerNotificationPreference, Document, Meeting, Payment, ServiceRequest, ServiceType, utcnow

router=APIRouter(prefix="/api/v1/account/data-summary")
LIMITS={"requests":1000,"meetings":2000,"payments":2000}
MAX_BYTES=5*1024*1024
FORMAT_VERSION="homexo-account-summary-v1"
SECTIONS=["profile","notification_preferences","requests","meetings","payments"]
EXCLUDED=["document_contents","messages_and_chat","case_reports","internal_notes","authentication_records","provider_records","historical_audit_records"]
TOO_LARGE="This account needs a reviewed summary because it exceeds the self-service download limits. Use Privacy requests to ask for a copy."


def owned(account):
    return select(ServiceRequest.id).join(Customer,Customer.id==ServiceRequest.customer_id).where(Customer.phone_normalized==account.phone_normalized)


def stamp(value):
    return tickets.aware(value).isoformat() if value else None


def count_records(db,account):
    scope=owned(account)
    return {"requests":db.scalar(select(func.count()).select_from(ServiceRequest).where(ServiceRequest.id.in_(scope))),
        "meetings":db.scalar(select(func.count()).select_from(Meeting).where(Meeting.service_request_id.in_(scope))),
        "payments":db.scalar(select(func.count()).select_from(Payment).where(Payment.service_request_id.in_(scope)))}


@router.get("")
def overview(account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    counts=count_records(db,account)
    return {"format_version":FORMAT_VERSION,"counts":counts,"limits":LIMITS,"ready":all(counts[key]<=LIMITS[key] for key in LIMITS),
        "sections":SECTIONS,"excluded":EXCLUDED,"checked_at":utcnow().isoformat()}


def build(db,account):
    # Select named columns rather than serializing ORM objects or the staff case view.
    rows=db.execute(select(ServiceRequest.id,ServiceRequest.ticket_number,ServiceRequest.title,ServiceRequest.package,ServiceRequest.status,
        ServiceRequest.created_at,ServiceRequest.updated_at,ServiceType.name.label("service_name"),CaseDocumentHold.held,
        CaseAIConsent.allowed,CaseAIConsent.revision.label("ai_revision"),CaseAIConsent.processing_revision,CaseAIConsent.changed_at.label("ai_changed_at"))
        .join(ServiceType,ServiceType.id==ServiceRequest.service_type_id)
        .outerjoin(CaseDocumentHold,CaseDocumentHold.service_request_id==ServiceRequest.id)
        .outerjoin(CaseAIConsent,CaseAIConsent.service_request_id==ServiceRequest.id)
        .where(ServiceRequest.id.in_(owned(account))).order_by(ServiceRequest.created_at,ServiceRequest.id).limit(LIMITS["requests"]+1)).all()
    if len(rows)>LIMITS["requests"]:raise HTTPException(409,TOO_LARGE)
    references={row.id:row.ticket_number for row in rows}
    ids=list(references)
    meetings=db.execute(select(Meeting.service_request_id,Meeting.starts_at,Meeting.ends_at,Meeting.status,Meeting.created_at)
        .where(Meeting.service_request_id.in_(ids)).order_by(Meeting.created_at,Meeting.id).limit(LIMITS["meetings"]+1)).all() if ids else []
    payments=db.execute(select(Payment.service_request_id,Payment.amount_paise,Payment.currency,Payment.status,Payment.created_at,Payment.paid_at,
        Payment.refunded_paise,Payment.refund_pending_paise).where(Payment.service_request_id.in_(ids))
        .order_by(Payment.created_at,Payment.id).limit(LIMITS["payments"]+1)).all() if ids else []
    if len(meetings)>LIMITS["meetings"] or len(payments)>LIMITS["payments"]:raise HTTPException(409,TOO_LARGE)
    document_counts=dict(db.execute(select(Document.service_request_id,func.count()).where(Document.service_request_id.in_(ids),
        or_(Document.document_category.is_(None),Document.document_category.not_in(("final_report","signed_report"))))
        .group_by(Document.service_request_id)).all()) if ids else {}
    disclosure=ai_processing.disclosure()
    request_rows=[]
    for row in rows:
        status="not_allowed"
        if row.ai_revision:
            status="withdrawn" if not row.allowed else "allowed" if disclosure["configured"] and row.processing_revision==disclosure["processing_revision"] else "review_required"
        request_rows.append({"ticket_number":row.ticket_number,"title":row.title,"service_name":row.service_name,"package":row.package,
            "status":row.status,"status_label":tickets.status_label(row.status),"created_at":stamp(row.created_at),"updated_at":stamp(row.updated_at),
            "document_count":document_counts.get(row.id,0),"document_preservation_active":bool(row.held),
            "external_document_ai":{"status":status,"changed_at":stamp(row.ai_changed_at)}})
    # Recheck ownership before preparing the response, including after concurrent
    # changes to case/customer links. No case outside the selected set is added.
    if set(db.scalars(owned(account).where(ServiceRequest.id.in_(ids))))!=set(ids):
        raise HTTPException(409,"Account records changed while preparing the summary. Refresh and try again.")
    return {"format_version":FORMAT_VERSION,"generated_at":utcnow().isoformat(),"scope":"current_account_activity_summary",
        "counts":{"requests":len(rows),"meetings":len(meetings),"payments":len(payments)},"sections":SECTIONS,"excluded":EXCLUDED,
        "profile":{"name":account.full_name,"email":account.email,"verified_phone":account.phone_normalized,
            "account_created_at":stamp(account.created_at),"profile_updated_at":stamp(account.updated_at)},
        "notification_preferences":notification_preferences.view(db.get(CustomerNotificationPreference,account.id)),
        "requests":request_rows,
        "meetings":[{"ticket_number":references[row.service_request_id],"starts_at":stamp(row.starts_at),"ends_at":stamp(row.ends_at),
            "status":row.status,"created_at":stamp(row.created_at)} for row in meetings],
        "payments":[{"ticket_number":references[row.service_request_id],"amount_paise":row.amount_paise,"currency":row.currency,"status":row.status,
            "created_at":stamp(row.created_at),"paid_at":stamp(row.paid_at),"refunded_paise":row.refunded_paise,"refund_pending_paise":row.refund_pending_paise} for row in payments]}


@router.get("/download")
def download(account:CustomerAccount=Depends(current_customer),db=Depends(get_db)):
    summary=build(db,account)
    encoded=json.dumps(summary,ensure_ascii=False,allow_nan=False,indent=2).encode("utf-8")
    if len(encoded)>MAX_BYTES:raise HTTPException(409,TOO_LARGE)
    db.add(AuditLog(action="privacy.account_summary_prepared",entity_type="customer_account",entity_id=account.id,
        metadata_={"format_version":FORMAT_VERSION,"counts":summary["counts"]}))
    db.commit()
    return Response(encoded,media_type="application/json",headers={"Content-Disposition":"attachment; filename=homexo-account-summary.json",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
