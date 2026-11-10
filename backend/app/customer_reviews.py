"""Verified customers can list and permanently withdraw their own consultation feedback."""
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .customer_auth import current_customer
from .db import get_db
from .models import AuditLog, Customer, CustomerAccount, LawyerReview, Meeting, ServiceRequest, User, utcnow

router = APIRouter(prefix="/api/v1/account/reviews")


def iso(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def owned(account):
    return (select(LawyerReview, User.display_name, ServiceRequest.ticket_number)
        .join(User, User.id == LawyerReview.lawyer_user_id)
        .join(Meeting, Meeting.id == LawyerReview.meeting_id)
        .join(ServiceRequest, ServiceRequest.id == Meeting.service_request_id)
        .join(Customer, Customer.id == ServiceRequest.customer_id)
        .where(Customer.phone_normalized == account.phone_normalized))


def view(row):
    review, lawyer_name, ticket = row
    return {"id": str(review.id), "lawyer_name": lawyer_name, "ticket_number": ticket,
        "rating": review.rating, "comment": review.comment, "created_at": iso(review.created_at),
        "status": review.publication_status, "withdrawn_at": iso(review.withdrawn_at) if review.withdrawn_at else None}


@router.get("")
def list_reviews(response: Response, page: int = Query(1, ge=1, le=10000),
                 account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    query = owned(account)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(LawyerReview.created_at.desc(), LawyerReview.id).offset((page - 1) * 20).limit(20)).all()
    return {"items": [view(row) for row in rows], "total": total, "page": page, "page_size": 20}


class Withdrawal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if not value: raise ValueError("Confirm that you want to withdraw this feedback.")
        return value


@router.post("/{review_id}/withdraw")
def withdraw(review_id: uuid.UUID, payload: Withdrawal, response: Response,
             account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    # The immutable content is identified by review ID. A concurrent administrator
    # decision cannot cancel the owner's withdrawal intent; the latest row is locked.
    row = db.execute(owned(account).where(LawyerReview.id == review_id)
        .with_for_update(of=LawyerReview).execution_options(populate_existing=True)).first()
    if row is None: raise HTTPException(404, "Review not found.")
    review = row[0]
    if review.withdrawn_at is None:
        previous = review.publication_status
        review.moderation_status = "hidden"
        review.withdrawn_at = review.updated_at = utcnow()
        review.revision += 1
        db.add(AuditLog(actor_user_id=None, action="review.withdrawn", entity_type="lawyer_review", entity_id=review.id,
            metadata_={"source": "customer", "account_id": str(account.id), "from_status": previous,
                "to_status": "withdrawn", "revision": review.revision}))
        db.commit()
    return view(row)
