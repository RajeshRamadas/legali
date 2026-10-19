"""A ticket's document repository and legal report: views for customers and staff, download links, checklist state.

Kept free of ticket workflow imports so tickets.py can include documents and the report in its views.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from . import config, gov_sources, report_templates
from .models import Document, LegalReport, ReportItem, ServiceRequest

REPORT_STATUS_LABELS = {
    "draft": "Preliminary report in draft",
    "issued": "Collecting documents",
    "final_generated": "Final report awaiting signature",
    "signed": "Final report signed",
}
CUSTOMER_ITEM_LABELS = {
    "pending": "Needed", "received": "Received, under review", "verified": "Accepted", "rejected": "Please upload again", "waived": "Not needed",
    "fetching": "Homexo is getting this for you",
}
STAFF_ITEM_LABELS = {"pending": "Waiting", "received": "To review", "verified": "Verified", "rejected": "Rejected", "waived": "Waived", "fetching": "To fetch"}
# Files the system keeps for the report rather than case documents.
REPORT_CATEGORIES = ("final_report", "signed_report")
DONE_ITEM_STATUSES = ("verified", "waived")
_AUDIENCE = "homexo-download"

def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None

def download_token(**claims) -> str:
    """A short-lived link to one file (doc=<id>) or a rendered report (report=<id>, kind=preliminary)."""
    payload = {**claims, "aud": _AUDIENCE, "exp": datetime.now(timezone.utc) + timedelta(minutes=config.DOWNLOAD_LINK_MINUTES)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

def read_download_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], audience=_AUDIENCE)
    except jwt.PyJWTError:
        return None

def file_url(document_id: uuid.UUID) -> str:
    return f"/api/v1/files/{download_token(doc=str(document_id))}"

def preliminary_url(report: LegalReport) -> str:
    return f"/api/v1/files/{download_token(report=str(report.id), kind='preliminary')}"

def case_documents(ticket: ServiceRequest) -> list[Document]:
    return [d for d in ticket.documents if d.document_category not in REPORT_CATEGORIES]

def checklist_complete(report: LegalReport) -> bool:
    return bool(report.items) and all(item.status in DONE_ITEM_STATUSES for item in report.items)

def sync_items(ticket: ServiceRequest) -> None:
    """Move items between "needed" and "received" as documents are filed under or taken off their tags.

    Verified and waived items stay as the lawyer left them. A rejected item comes back for review once a newer file arrives.
    """
    report = ticket.report
    if report is None:
        return
    by_tag: dict[str, list[Document]] = {}
    for document in case_documents(ticket):
        if document.tag:
            by_tag.setdefault(document.tag, []).append(document)
    for item in report.items:
        files = by_tag.get(item.tag, [])
        if item.status in ("pending", "received"):
            item.status = "received" if files else "pending"
        elif item.status == "rejected" and item.reviewed_at and any(_aware(d.created_at) > _aware(item.reviewed_at) for d in files):
            item.status = "received"

def document_view(document: Document, *, staff: bool = False, locked_tags: set[str] = frozenset()) -> dict:
    view = {
        "id": str(document.id),
        "filename": document.original_filename,
        "content_type": document.content_type,
        "size": document.byte_size,
        "tag": document.tag,
        "note": document.note,
        "at": _iso(document.created_at),
        "download_url": file_url(document.id),
    }
    if staff:
        return view | {"uploaded_by": document.uploader_type, "checksum_sha256": document.checksum_sha256}
    return view | {
        "uploaded_by": "you" if document.uploader_type == "customer" else "homexo",
        # Customers can remove their own files until the lawyer has accepted the item they are filed under.
        "can_delete": document.uploader_type == "customer" and (document.tag or "") not in locked_tags,
    }

def locked_tags(ticket: ServiceRequest) -> set[str]:
    report = ticket.report
    if report is None:
        return set()
    if report.status in ("final_generated", "signed"):
        return {d.tag or "" for d in ticket.documents}
    return {item.tag for item in report.items if item.status == "verified"}

def _item_view(item: ReportItem, files: dict[str, list[str]], labels: dict) -> dict:
    status_label = labels[item.status]
    if item.fetch_by == "homexo" and item.status == "pending":
        status_label = labels["fetching"]
    return {
        "id": str(item.id), "tag": item.tag, "label": item.label, "guidance": item.guidance, "status": item.status,
        "status_label": status_label, "note": item.review_note, "documents": files.get(item.tag, []),
        "fetch_by": item.fetch_by, "source": gov_sources.source_view(item.source),
    }

def _files_by_tag(ticket: ServiceRequest) -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for document in case_documents(ticket):
        if document.tag:
            files.setdefault(document.tag, []).append(str(document.id))
    return files

def _progress(report: LegalReport) -> dict:
    return {"done": sum(1 for i in report.items if i.status in DONE_ITEM_STATUSES), "total": len(report.items)}

def customer_report_view(ticket: ServiceRequest) -> dict | None:
    report = ticket.report
    if report is None or report.status == "draft":
        return None
    files = _files_by_tag(ticket)
    return {
        "status": report.status,
        "status_label": REPORT_STATUS_LABELS[report.status],
        "issued_at": _iso(report.issued_at),
        "lawyer_name": report.lawyer.display_name if report.lawyer else None,
        "sections": report_templates.section_view(report_templates.PRELIMINARY_SECTIONS, report.preliminary),
        "items": [_item_view(i, files, CUSTOMER_ITEM_LABELS) for i in report.items],
        "progress": _progress(report),
        "preliminary_pdf_url": preliminary_url(report),
        "signed_report_url": file_url(report.signed_document_id) if report.status == "signed" and report.signed_document_id else None,
        "signed_at": _iso(report.signed_at),
    }

def _ref(user) -> dict | None:
    return {"id": str(user.id), "name": user.display_name} if user else None

def staff_report_view(ticket: ServiceRequest) -> dict | None:
    report = ticket.report
    if report is None:
        return None
    files = _files_by_tag(ticket)
    return {
        "status": report.status,
        "status_label": REPORT_STATUS_LABELS[report.status],
        "issued_at": _iso(report.issued_at),
        "lawyer": _ref(report.lawyer),
        "reviewer": _ref(report.reviewer),
        "sections": report_templates.section_view(report_templates.PRELIMINARY_SECTIONS, report.preliminary),
        "final_sections": report_templates.section_view(report_templates.FINAL_SECTIONS, report.final),
        "items": [_item_view(i, files, STAFF_ITEM_LABELS) | {"reviewed_at": _iso(i.reviewed_at)} for i in report.items],
        "progress": _progress(report),
        "checklist_complete": checklist_complete(report),
        "preliminary_pdf_url": preliminary_url(report),
        "final_pdf_url": file_url(report.final_document_id) if report.final_document_id else None,
        "final_generated_at": _iso(report.final_generated_at),
        "signed_report_url": file_url(report.signed_document_id) if report.signed_document_id else None,
        "signed_at": _iso(report.signed_at),
    }

def customer_documents_view(ticket: ServiceRequest) -> list[dict]:
    locked = locked_tags(ticket)
    return [document_view(d, locked_tags=locked) for d in case_documents(ticket)]

def staff_documents_view(ticket: ServiceRequest) -> list[dict]:
    return [document_view(d, staff=True) for d in case_documents(ticket)]
