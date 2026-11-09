"""Verified customer privacy requests and administrator review. Business records are retained."""
import uuid
import math
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .customer_auth import current_customer, owned_ticket
from .db import get_db
from .models import AuditLog, Conversation, CustomerAccount, PrivacyRequest, ServiceRequest, User, utcnow
from .security import require_admin
from .tickets import aware

router = APIRouter(prefix="/api/v1")
NOTICE_VERSION = "privacy-requests-v1"
OPEN = ("submitted", "in_review")
Kind = Literal["access", "correction", "deletion"]
Reason = Literal["legal_retention", "scope_or_identity", "not_held", "other"]


class Create(BaseModel):
    kind: Kind
    details: str = Field(min_length=10, max_length=2000)
    ticket_number: str | None = Field(default=None, max_length=40)
    submission_key: uuid.UUID
    notice_version: str = Field(min_length=1, max_length=80)

    @field_validator("details", "ticket_number", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Unsupported character in this field.")
        return value.strip() if isinstance(value, str) else value


class Revision(BaseModel):
    revision: int = Field(ge=1)


class Review(Revision):
    status: Literal["in_review", "closed"]
    customer_response: str = Field(default="", max_length=2000)
    internal_note: str = Field(default="", max_length=2000)
    resolution: Literal["fulfilled", "partial", "declined"] | None = None
    retention_reason: Reason | None = None

    @field_validator("customer_response", "internal_note", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Unsupported character in this field.")
        return value.strip() if isinstance(value, str) else value


@router.get("/privacy/notice")
def notice():
    return {"version": NOTICE_VERSION, "review_target_days": config.PRIVACY_REVIEW_DAYS, "chat_retention_days": config.CHAT_RETENTION_DAYS,
        "summary": ["Request access to your information, a correction, or deletion through your verified account.",
            "The team reviews the scope and applicable retention requirements. Case evidence, signed reports, payment and consent records may need to be retained.",
            "The review target is an operational target, not a statutory deadline. The team will explain its decision here.",
            f"Unlinked anonymous chats may be removed after {config.CHAT_RETENTION_DAYS} days of inactivity. Case-linked records and conversations on hold are preserved."]}


def view(db, item, *, staff=False, detail=True):
    ticket = db.get(ServiceRequest, item.service_request_id) if item.service_request_id else None
    result = {"id": str(item.id), "reference": "PR-" + item.id.hex.upper(), "kind": item.kind, "status": item.status,
        "revision": item.revision, "ticket_number": ticket.ticket_number if ticket else None,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "due_at": item.due_at.isoformat(),
        "overdue": item.status in OPEN and aware(item.due_at) < utcnow(), "review_started_at": item.review_started_at.isoformat() if item.review_started_at else None,
        "closed_at": item.closed_at.isoformat() if item.closed_at else None, "resolution": item.resolution,
        "retention_reason": item.retention_reason, "customer_response": item.customer_response}
    if detail:
        result["details"] = item.details
        result["notice_version"] = item.notice_version
    if staff:
        account = db.get(CustomerAccount, item.account_id)
        result["customer"] = {"name": account.full_name, "phone_last4": account.phone_normalized[-4:]}
        if detail:
            result["internal_note"] = item.internal_note
    return result


def audit(db, item, action, *, actor=None, previous=None):
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity_type="privacy_request", entity_id=item.id,
        metadata_={"kind": item.kind, "status": item.status, "previous_status": previous, "revision": item.revision}))


def lock_account(db, account_id):
    db.scalar(select(CustomerAccount.id).where(CustomerAccount.id == account_id).with_for_update())


def locked_request(db, request_id, account_id=None):
    query = select(PrivacyRequest).where(PrivacyRequest.id == request_id)
    if account_id is not None:
        query = query.where(PrivacyRequest.account_id == account_id)
    item = db.scalar(query.with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, "Privacy request not found.")
    return item


@router.post("/account/privacy-requests", status_code=201)
def create(payload: Create, response: Response, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    lock_account(db, account.id)
    ticket = owned_ticket(db, payload.ticket_number.upper(), account) if payload.ticket_number else None
    existing = db.scalar(select(PrivacyRequest).where(PrivacyRequest.account_id == account.id, PrivacyRequest.submission_key == payload.submission_key))
    if existing:
        if (existing.kind, existing.details, existing.service_request_id, existing.notice_version) != (payload.kind, payload.details, ticket.id if ticket else None, payload.notice_version):
            raise HTTPException(409, "This submission has already been used. Start a new request to change its details.")
        response.status_code = 200
        return view(db, existing)
    if payload.notice_version != NOTICE_VERSION:
        raise HTTPException(409, "The privacy notice has changed. Refresh the page and review it before sending.")
    if db.scalar(select(PrivacyRequest.id).where(PrivacyRequest.account_id == account.id, PrivacyRequest.kind == payload.kind, PrivacyRequest.status.in_(OPEN))):
        raise HTTPException(409, "You already have an open request of this type. Check its progress below.")
    recent = db.scalar(select(func.count()).select_from(PrivacyRequest).where(PrivacyRequest.account_id == account.id, PrivacyRequest.created_at >= utcnow() - timedelta(days=1)))
    if recent >= config.PRIVACY_REQUESTS_PER_DAY:
        first = db.scalar(select(func.min(PrivacyRequest.created_at)).where(PrivacyRequest.account_id == account.id, PrivacyRequest.created_at >= utcnow() - timedelta(days=1)))
        retry = max(1, math.ceil((aware(first) + timedelta(days=1) - utcnow()).total_seconds()))
        raise HTTPException(429, "You have reached the privacy-request limit for the last 24 hours. Please try again later.", headers={"Retry-After": str(retry)})
    item = PrivacyRequest(account_id=account.id, service_request_id=ticket.id if ticket else None, submission_key=payload.submission_key,
        kind=payload.kind, details=payload.details, notice_version=NOTICE_VERSION, due_at=utcnow() + timedelta(days=config.PRIVACY_REVIEW_DAYS))
    db.add(item); db.flush()
    audit(db, item, "privacy.requested")
    db.commit()
    return view(db, item)


@router.get("/account/privacy-requests")
def mine(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    query = select(PrivacyRequest).where(PrivacyRequest.account_id == account.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(PrivacyRequest.created_at.desc(), PrivacyRequest.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [view(db, item) for item in items], "total": total, "page": page, "page_size": page_size}


@router.post("/account/privacy-requests/{request_id}/withdraw")
def withdraw(request_id: uuid.UUID, payload: Revision, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    lock_account(db, account.id)
    item = locked_request(db, request_id, account.id)
    if item.status == "withdrawn":
        return view(db, item)
    if item.revision != payload.revision or item.status not in OPEN:
        raise HTTPException(409, "This request changed. Refresh its progress before withdrawing it.")
    previous = item.status
    item.status, item.closed_at, item.revision = "withdrawn", utcnow(), item.revision + 1
    audit(db, item, "privacy.withdrawn", previous=previous)
    db.commit()
    return view(db, item)


@router.get("/admin/privacy-requests")
def queue(status: Literal["open", "submitted", "in_review", "closed", "withdrawn", "all"] = "open", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = select(PrivacyRequest)
    if status == "open": query = query.where(PrivacyRequest.status.in_(OPEN))
    elif status != "all": query = query.where(PrivacyRequest.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    overdue = db.scalar(select(func.count()).select_from(PrivacyRequest).where(PrivacyRequest.status.in_(OPEN), PrivacyRequest.due_at < utcnow()))
    items = db.scalars(query.order_by(PrivacyRequest.due_at, PrivacyRequest.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [view(db, item, staff=True, detail=False) for item in items], "total": total, "overdue": overdue, "page": page, "page_size": page_size}


@router.get("/admin/privacy-requests/{request_id}")
def detail(request_id: uuid.UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(PrivacyRequest, request_id)
    if item is None: raise HTTPException(404, "Privacy request not found.")
    return view(db, item, staff=True)


@router.get("/admin/privacy-retention")
def retention_preview(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    from .retention import cleanup
    result = cleanup()
    return {"cleanup_enabled": result["enabled"], "retention_days": result["retention_days"], "eligible_anonymous_chats": result["eligible"],
        "held_conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.retention_hold.is_(True)))}


@router.patch("/admin/privacy-requests/{request_id}")
def review(request_id: uuid.UUID, payload: Review, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(PrivacyRequest, request_id)
    if item is None: raise HTTPException(404, "Privacy request not found.")
    lock_account(db, item.account_id)
    item = locked_request(db, request_id)
    if item.revision != payload.revision or item.status not in OPEN:
        raise HTTPException(409, "This privacy request changed. Reload it before saving.")
    if payload.status == "closed":
        if item.status != "in_review": raise HTTPException(409, "Start reviewing this request before closing it.")
        if not payload.resolution or len(payload.customer_response) < 20: raise HTTPException(422, "Choose an outcome and explain the completed action or decision to the customer (at least 20 characters).")
        if payload.resolution != "fulfilled" and not payload.retention_reason: raise HTTPException(422, "Choose a reason for a partial or declined request.")
    elif payload.resolution or payload.retention_reason:
        raise HTTPException(422, "Resolution fields are only used when closing a request.")
    previous = item.status
    item.status, item.revision, item.reviewed_by_id = payload.status, item.revision + 1, actor.id
    item.review_started_at = item.review_started_at or utcnow()
    item.customer_response, item.internal_note = payload.customer_response or None, payload.internal_note or None
    if item.status == "closed":
        item.closed_at, item.resolution = utcnow(), payload.resolution
        item.retention_reason = payload.retention_reason if payload.resolution != "fulfilled" else None
    audit(db, item, "privacy.reviewed", actor=actor, previous=previous)
    db.commit()
    return view(db, item, staff=True)
