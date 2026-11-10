"""Signed-event refund ledger and administrator follow-up. No provider refund initiation."""
import hashlib
import re
import uuid
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, Customer, Payment, Refund, ServiceRequest, User, utcnow
from .security import require_admin

router = APIRouter(prefix="/api/v1/admin/refunds")


def lock_references(db, *references):
    if db.get_bind().dialect.name == "postgresql":
        # Serialize events even before a payment reference is known by an application payment row.
        keys = sorted({int.from_bytes(hashlib.sha256(("razorpay-refund:" + value).encode()).digest()[:8], "big", signed=True) for value in references if value})
        for key in keys:
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def audit(db, item, action, actor=None):
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity_type="refund", entity_id=item.id,
        metadata_={"status": item.status, "revision": item.revision, "amount_paise": item.amount_paise, "review_code": item.review_code}))


def recompute(db, payment):
    db.flush()
    rows = list(db.scalars(select(Refund).where(Refund.payment_id == payment.id)))
    processed = sum(item.amount_paise for item in rows if item.status == "processed")
    pending = sum(item.amount_paise for item in rows if item.status == "pending")
    reason = "legacy_unverified" if payment.refund_review_reason == "legacy_unverified" else None
    if reason is None:
        if any(item.review_code for item in rows): reason = "conflicting_event"
        elif any(item.currency != payment.currency for item in rows): reason = "currency_mismatch"
        elif processed + pending > payment.amount_paise: reason = "amount_exceeds_payment"
        elif rows and payment.status == "created": reason = "payment_not_captured"
    before = payment.refunded_paise or 0
    payment.refund_pending_paise = pending
    payment.refund_review_reason = reason
    if reason is None:
        payment.refunded_paise = processed
        if processed == payment.amount_paise:
            payment.status = "refunded"
        if processed > before:
            from . import tickets
            tickets.add_event(db, payment.service_request, "payment_refunded" if processed == payment.amount_paise else "payment_refund_partial", None,
                new={"amount_paise": processed - before, "total_refunded_paise": processed}, reason="A provider-confirmed refund update was recorded.")


def attach(db, reference):
    payments = list(db.scalars(select(Payment).where(Payment.provider == "razorpay", Payment.provider_payment_id == reference)
        .order_by(Payment.id).with_for_update().execution_options(populate_existing=True)))
    if len(payments) > 1:
        for payment in payments: payment.refund_review_reason = "ambiguous_payment"
        return
    if not payments: return
    payment = payments[0]
    for item in db.scalars(select(Refund).where(Refund.provider_payment_id == reference).with_for_update()):
        if item.payment_id is None:
            item.payment_id = payment.id; item.revision += 1; item.updated_at = utcnow()
    recompute(db, payment)


def ingest(db, entity, status):
    if (not isinstance(entity, dict) or type(entity.get("amount")) is not int or not 1 <= entity["amount"] <= 2147483647
        or not all(isinstance(entity.get(key), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", entity[key]) for key in ("id", "payment_id"))
        or not isinstance(entity.get("currency", "INR"), str) or not re.fullmatch(r"[A-Z]{3}", entity.get("currency", "INR"))):
        raise HTTPException(422, "Invalid refund event fields.")
    reference = entity["payment_id"]
    original = db.scalar(select(Refund.provider_payment_id).where(Refund.provider_refund_id == entity["id"]))
    lock_references(db, reference, original)
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    now = utcnow()
    inserted = db.execute(insert(Refund).values(id=uuid.uuid4(), provider_refund_id=entity["id"], provider_payment_id=reference,
        amount_paise=entity["amount"], currency=entity.get("currency", "INR"), status=status, revision=1, internal_note="", created_at=now, updated_at=now)
        .on_conflict_do_nothing(index_elements=["provider_refund_id"]).returning(Refund.id)).scalar_one_or_none()
    item = db.scalar(select(Refund).where(Refund.provider_refund_id == entity["id"]).with_for_update().execution_options(populate_existing=True))
    if item.provider_payment_id != reference and original is None:
        raise HTTPException(409, "Refund event conflicted with another delivery. Retry this event.")
    conflict = (item.provider_payment_id != reference or item.amount_paise != entity["amount"] or item.currency != entity.get("currency", "INR"))
    changed = bool(inserted)
    if conflict and not item.review_code:
        item.review_code = "conflicting_refund_event"; changed = True
    elif not conflict and item.status != "processed" and item.status != status and (status != "pending" or item.status == "pending"):
        item.status = status; changed = True
    if changed:
        if not inserted: item.revision += 1
        item.updated_at = now
        audit(db, item, "refund.recorded" if inserted else "refund.updated")
    db.flush()
    attach(db, item.provider_payment_id)


def view(item):
    updated = item.updated_at if item.updated_at.tzinfo else item.updated_at.replace(tzinfo=timezone.utc)
    return {"id": str(item.id), "provider_refund_id": item.provider_refund_id, "provider_payment_id": item.provider_payment_id,
        "amount_paise": item.amount_paise, "currency": item.currency, "status": item.status, "review_code": item.review_code,
        "revision": item.revision, "internal_note": item.internal_note,
        "updated_at": updated.isoformat()}


def queue_filters():
    pending = exists(select(Refund.id).where(Refund.payment_id == Payment.id, Refund.status == "pending"))
    failed = exists(select(Refund.id).where(Refund.payment_id == Payment.id, Refund.status == "failed"))
    disputed = exists(select(Refund.id).where(Refund.payment_id == Payment.id, Refund.review_code.is_not(None)))
    review = or_(Payment.refund_review_reason.is_not(None), disputed)
    return {"review": review, "completed": (Payment.status == "refunded") & ~review,
        "pending": pending & ~review,
        "needs_action": ~review & ~pending & (Payment.status != "refunded") & or_(Payment.status == "refund_due", Payment.refunded_paise > 0, failed)}


@router.get("")
def queue(state: Literal["all", "needs_action", "pending", "completed", "review"] = "needs_action",
          q: str = Query("", max_length=120), page: int = Query(1, ge=1), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    filters = queue_filters()
    relevant = or_(*filters.values())
    base = select(Payment, ServiceRequest.ticket_number, Customer.full_name).join(ServiceRequest, ServiceRequest.id == Payment.service_request_id).join(Customer, Customer.id == ServiceRequest.customer_id)
    base = base.where(relevant if state == "all" else filters[state])
    if q.strip():
        needle = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        base = base.where(or_(ServiceRequest.ticket_number.ilike(needle, escape="\\"), Payment.provider_payment_id.ilike(needle, escape="\\"), Payment.provider_order_id.ilike(needle, escape="\\")))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = list(db.execute(base.order_by(Payment.updated_at.desc(), Payment.id).offset((page - 1) * 20).limit(20)))
    counts = db.execute(select(*(func.sum(case((condition, 1), else_=0)).label(name) for name, condition in filters.items()))).one()
    return {"items": [{"id": str(item.id), "ticket_number": ticket, "customer_name": name, "provider": item.provider,
        "provider_payment_id": item.provider_payment_id, "provider_order_id": item.provider_order_id, "status": item.status,
        "amount_paise": item.amount_paise, "currency": item.currency, "refunded_paise": item.refunded_paise,
        "pending_paise": item.refund_pending_paise, "remaining_paise": item.amount_paise - item.refunded_paise,
        "review_reason": item.refund_review_reason} for item, ticket, name in rows],
        "counts": {name: int(getattr(counts, name) or 0) for name in filters},
        "unmatched": db.scalar(select(func.count()).select_from(Refund).where(Refund.payment_id.is_(None))),
        "total": total, "page": page, "page_size": 20}


@router.get("/unmatched")
def unmatched(page: int = Query(1, ge=1), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = select(Refund).where(Refund.payment_id.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Refund.updated_at.desc(), Refund.id).offset((page - 1) * 20).limit(20))
    return {"items": [view(item) for item in rows], "total": total, "page": page, "page_size": 20}


@router.get("/payments/{payment_id}")
def detail(payment_id: uuid.UUID, page: int = Query(1, ge=1), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Payment, payment_id)
    if item is None: raise HTTPException(404, "Payment not found.")
    return {"items": [view(row) for row in db.scalars(select(Refund).where(Refund.payment_id == item.id).order_by(Refund.created_at.desc(), Refund.id).offset((page - 1) * 20).limit(20))],
        "total": db.scalar(select(func.count()).select_from(Refund).where(Refund.payment_id == item.id)), "page": page, "page_size": 20}


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    internal_note: str = Field(min_length=1, max_length=2000)

    @field_validator("internal_note", mode="before")
    @classmethod
    def clean(cls, value):
        if isinstance(value, str):
            if any(ord(char) < 32 and char not in "\n\r\t" for char in value): raise ValueError("Unsupported control character.")
            return value.strip()
        return value


@router.patch("/{refund_id}/note")
def note(refund_id: uuid.UUID, payload: Note, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    changed = db.execute(update(Refund).where(Refund.id == refund_id, Refund.revision == payload.revision)
        .values(internal_note=payload.internal_note, revision=payload.revision + 1, updated_at=utcnow()).returning(Refund.id)).scalar_one_or_none()
    if changed is None:
        if db.get(Refund, refund_id) is None: raise HTTPException(404, "Refund record not found.")
        raise HTTPException(409, "This refund changed. Reload its history before saving a note.")
    item = db.get(Refund, refund_id)
    audit(db, item, "refund.note_saved", actor)
    db.commit()
    return view(item)
