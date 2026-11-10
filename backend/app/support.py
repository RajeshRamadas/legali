"""Verified-account support and administrator triage; no payment or case mutations."""
import math
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import config
from .customer_auth import current_customer, owned_ticket
from .db import get_db
from .models import AuditLog, CustomerAccount, ServiceRequest, SupportMessage, SupportRequest, User, utcnow
from .security import require_admin
from .tickets import aware

router = APIRouter(prefix="/api/v1")
Kind = Literal["case_update", "documents", "payment", "complaint", "other"]
Status = Literal["open", "in_progress", "waiting_for_customer", "resolved"]


class TextFields(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("Unsupported character in this field.")
            return value.strip()
        return value


class Create(TextFields):
    kind: Kind
    subject: str = Field(min_length=5, max_length=160)
    details: str = Field(min_length=10, max_length=4000)
    ticket_number: str | None = Field(default=None, max_length=40)
    submission_key: uuid.UUID


class Reply(TextFields):
    body: str = Field(min_length=1, max_length=4000)
    submission_key: uuid.UUID


class Review(TextFields):
    revision: int = Field(ge=1)
    status: Status
    customer_response: str = Field(default="", max_length=4000)
    internal_note: str = Field(default="", max_length=4000)


def lock_account(db, account_id):
    db.scalar(select(CustomerAccount.id).where(CustomerAccount.id == account_id).with_for_update())


def find(db, request_id, account_id=None, *, lock=False):
    query = select(SupportRequest).where(SupportRequest.id == request_id)
    if account_id is not None:
        query = query.where(SupportRequest.account_id == account_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None:
        raise HTTPException(404, "Support request not found.")
    return item


def view(db, item, *, staff=False, detail=True, ticket_numbers=None, customers=None):
    ticket_number = (ticket_numbers.get(item.service_request_id) if ticket_numbers is not None else
        db.scalar(select(ServiceRequest.ticket_number).where(ServiceRequest.id == item.service_request_id)) if item.service_request_id else None)
    result = {"id": str(item.id), "reference": "SR-" + item.id.hex.upper(), "kind": item.kind,
        "subject": item.subject, "status": item.status, "revision": item.revision,
        "ticket_number": ticket_number,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        "reply_due_at": item.reply_due_at.isoformat() if item.reply_due_at else None,
        "overdue": item.status != "resolved" and item.reply_due_at is not None and aware(item.reply_due_at) < utcnow(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None}
    if detail:
        result["details"] = item.details
    if staff:
        if customers is not None:
            result["customer"] = customers[item.account_id]
        else:
            account = db.get(CustomerAccount, item.account_id)
            result["customer"] = {"name": account.full_name, "phone_last4": account.phone_normalized[-4:]}
    return result


def audit(db, item, action, actor=None, previous=None):
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity_type="support_request", entity_id=item.id,
        metadata_={"status": item.status, "previous_status": previous, "revision": item.revision}))


def enforce_limit(count, limit, first, message):
    if count >= limit:
        retry = max(1, math.ceil((aware(first) + timedelta(days=1) - utcnow()).total_seconds())) if first else 3600
        raise HTTPException(429, message, headers={"Retry-After": str(retry)})


def open_limit(db, account_id):
    count = db.scalar(select(func.count()).select_from(SupportRequest).where(SupportRequest.account_id == account_id, SupportRequest.status != "resolved"))
    enforce_limit(count, config.SUPPORT_OPEN_LIMIT, None, "You have reached the open support-request limit. Reply to an existing request or wait for the team to resolve one.")


@router.post("/account/support-requests", status_code=201)
def create(payload: Create, response: Response, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    lock_account(db, account.id)
    ticket = owned_ticket(db, payload.ticket_number.upper(), account) if payload.ticket_number else None
    existing = db.scalar(select(SupportRequest).where(SupportRequest.account_id == account.id, SupportRequest.submission_key == payload.submission_key))
    if existing:
        if (existing.kind, existing.subject, existing.details, existing.service_request_id) != (payload.kind, payload.subject, payload.details, ticket.id if ticket else None):
            raise HTTPException(409, "This submission was already used. Start a new request to change its details.")
        response.status_code = 200
        return view(db, existing)
    open_limit(db, account.id)
    recent = select(SupportRequest).where(SupportRequest.account_id == account.id, SupportRequest.created_at >= utcnow() - timedelta(days=1))
    recent = recent.subquery()
    count, first = db.execute(select(func.count(), func.min(recent.c.created_at)).select_from(recent)).one()
    enforce_limit(count, config.SUPPORT_REQUESTS_PER_DAY, first, "You have reached the support-request limit for the last 24 hours. Please try again later.")
    item = SupportRequest(account_id=account.id, service_request_id=ticket.id if ticket else None, submission_key=payload.submission_key,
        kind=payload.kind, subject=payload.subject, details=payload.details, reply_due_at=utcnow() + timedelta(hours=config.SUPPORT_RESPONSE_HOURS))
    db.add(item); db.flush(); audit(db, item, "support.created"); db.commit()
    return view(db, item)


def listing(db, query, page, page_size, *, staff=False):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(SupportRequest.updated_at.desc(), SupportRequest.id).offset((page - 1) * page_size).limit(page_size)).all()
    ticket_ids = {item.service_request_id for item in items if item.service_request_id}
    ticket_numbers = dict(db.execute(select(ServiceRequest.id, ServiceRequest.ticket_number).where(ServiceRequest.id.in_(ticket_ids))).all()) if ticket_ids else {}
    account_ids = {item.account_id for item in items}
    customers = {account_id: {"name": name, "phone_last4": phone[-4:]} for account_id, name, phone in db.execute(
        select(CustomerAccount.id, CustomerAccount.full_name, CustomerAccount.phone_normalized).where(CustomerAccount.id.in_(account_ids)))} if staff and account_ids else {}
    return {"items": [view(db, item, staff=staff, detail=False, ticket_numbers=ticket_numbers, customers=customers) for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/account/support-requests")
def mine(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    return listing(db, select(SupportRequest).where(SupportRequest.account_id == account.id), page, page_size)


@router.get("/account/support-requests/{request_id}")
def detail(request_id: uuid.UUID, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    return view(db, find(db, request_id, account.id))


def thread(db, item, page, page_size, *, staff=False):
    query = select(SupportMessage).where(SupportMessage.support_request_id == item.id)
    if not staff:
        query = query.where(SupportMessage.visibility == "customer")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(SupportMessage.created_at.desc(), SupportMessage.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": str(row.id), "body": row.body, "author_type": row.author_type, "visibility": row.visibility, "created_at": row.created_at.isoformat()} for row in items],
        "total": total, "page": page, "page_size": page_size}


@router.get("/account/support-requests/{request_id}/messages")
def messages(request_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    return thread(db, find(db, request_id, account.id), page, page_size)


@router.post("/account/support-requests/{request_id}/messages", status_code=201)
def reply(request_id: uuid.UUID, payload: Reply, response: Response, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    lock_account(db, account.id)
    item = find(db, request_id, account.id, lock=True)
    existing = db.scalar(select(SupportMessage).where(SupportMessage.support_request_id == item.id, SupportMessage.submission_key == payload.submission_key))
    if existing:
        if existing.author_type != "customer" or existing.body != payload.body:
            raise HTTPException(409, "This reply submission was already used with different content.")
        response.status_code = 200
        return view(db, item)
    recent = select(SupportMessage.created_at).join(SupportRequest, SupportRequest.id == SupportMessage.support_request_id).where(
        SupportRequest.account_id == account.id, SupportMessage.author_type == "customer", SupportMessage.created_at >= utcnow() - timedelta(days=1)).subquery()
    count, first = db.execute(select(func.count(), func.min(recent.c.created_at)).select_from(recent)).one()
    enforce_limit(count, config.SUPPORT_MESSAGES_PER_DAY, first, "You have reached the support-reply limit for the last 24 hours. Please try again later.")
    if item.status == "resolved": open_limit(db, account.id)
    previous = item.status
    if item.status in ("resolved", "waiting_for_customer"): item.status = "open"
    item.resolved_at = None
    # Consecutive customer messages must not postpone an already outstanding response target.
    item.reply_due_at = item.reply_due_at or utcnow() + timedelta(hours=config.SUPPORT_RESPONSE_HOURS)
    item.revision += 1
    db.add(SupportMessage(support_request_id=item.id, submission_key=payload.submission_key, author_type="customer", visibility="customer", body=payload.body))
    audit(db, item, "support.customer_replied", previous=previous); db.commit()
    return view(db, item)


@router.get("/admin/support-requests")
def queue(status: Literal["active", "all", "open", "in_progress", "waiting_for_customer", "resolved"] = "active", kind: Kind | None = None,
    q: str = Query("", max_length=120, pattern=r"^[^\x00]*$"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = select(SupportRequest)
    if status == "active": query = query.where(SupportRequest.status != "resolved")
    elif status != "all": query = query.where(SupportRequest.status == status)
    if kind: query = query.where(SupportRequest.kind == kind)
    if q.strip():
        term = q.strip().lower()
        try:
            request_id = uuid.UUID(term.removeprefix("sr-"))
        except ValueError:
            request_id = None
        query = query.where(or_(func.lower(SupportRequest.subject).contains(term, autoescape=True), SupportRequest.id == request_id))
    result = listing(db, query, page, page_size, staff=True)
    result["overdue"] = db.scalar(select(func.count()).select_from(SupportRequest).where(SupportRequest.status != "resolved", SupportRequest.reply_due_at < utcnow()))
    return result


@router.get("/admin/support-requests/{request_id}")
def staff_detail(request_id: uuid.UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return view(db, find(db, request_id), staff=True)


@router.get("/admin/support-requests/{request_id}/messages")
def staff_messages(request_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return thread(db, find(db, request_id), page, page_size, staff=True)


@router.patch("/admin/support-requests/{request_id}")
def review(request_id: uuid.UUID, payload: Review, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = find(db, request_id)
    lock_account(db, item.account_id)
    item = find(db, request_id, lock=True)
    if item.revision != payload.revision:
        raise HTTPException(409, "This request changed. Reload it before saving; your draft has been kept.")
    if payload.status != item.status and payload.status in ("resolved", "waiting_for_customer") and len(payload.customer_response) < 10:
        raise HTTPException(422, "Explain the decision or what the customer needs to provide (at least 10 characters).")
    if item.status == "resolved" and payload.status != "resolved": open_limit(db, item.account_id)
    if item.status == payload.status and not payload.customer_response and not payload.internal_note:
        raise HTTPException(422, "Add a response, internal note or status change.")
    previous = item.status
    item.status, item.revision = payload.status, item.revision + 1
    item.resolved_at = (item.resolved_at or utcnow()) if item.status == "resolved" else None
    if payload.customer_response:
        item.reply_due_at = None
    elif previous == "resolved" and item.status != "resolved":
        item.reply_due_at = utcnow() + timedelta(hours=config.SUPPORT_RESPONSE_HOURS)
    for visibility, body in (("customer", payload.customer_response), ("internal", payload.internal_note)):
        if body: db.add(SupportMessage(support_request_id=item.id, submission_key=uuid.uuid4(), author_type="staff", author_user_id=actor.id, visibility=visibility, body=body))
    audit(db, item, "support.reviewed", actor=actor, previous=previous); db.commit()
    return view(db, item, staff=True)
