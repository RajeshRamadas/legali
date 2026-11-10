"""Private administrator review decisions; customer text and ratings are never edited."""
import uuid
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, LawyerReview, LawyerReviewDecision, Meeting, ServiceRequest, User, utcnow
from .security import require_admin


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/admin/reviews", dependencies=[Depends(no_store)])


def iso(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def review_query():
    return (select(LawyerReview, User.display_name, ServiceRequest.ticket_number)
        .join(User, User.id == LawyerReview.lawyer_user_id)
        .join(Meeting, Meeting.id == LawyerReview.meeting_id)
        .join(ServiceRequest, ServiceRequest.id == Meeting.service_request_id))


def view(row):
    review, lawyer_name, ticket = row
    return {"id": str(review.id), "rating": review.rating, "comment": review.comment,
        "reviewer_name": review.reviewer_name, "created_at": iso(review.created_at), "updated_at": iso(review.updated_at),
        "status": review.publication_status, "withdrawn_at": iso(review.withdrawn_at) if review.withdrawn_at else None,
        "revision": review.revision, "ticket_number": ticket,
        "lawyer": {"id": str(review.lawyer_user_id), "name": lawyer_name}}


@router.get("")
def queue(status: Literal["pending", "published", "hidden", "withdrawn", "all"] = "pending",
          q: str = Query("", max_length=120), page: int = Query(1, ge=1, le=10000),
          _: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = review_query()
    publication = case((LawyerReview.withdrawn_at.is_not(None), "withdrawn"), else_=LawyerReview.moderation_status)
    if status != "all": query = query.where(publication == status)
    if q.strip():
        needle = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(User.display_name.ilike(needle, escape="\\"), ServiceRequest.ticket_number.ilike(needle, escape="\\")))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = (LawyerReview.created_at.asc(), LawyerReview.id) if status == "pending" else (LawyerReview.updated_at.desc(), LawyerReview.id)
    rows = db.execute(query.order_by(*order).offset((page - 1) * 20).limit(20)).all()
    counts = dict(db.execute(select(publication, func.count()).group_by(publication)).all())
    return {"items": [view(row) for row in rows], "total": total, "page": page, "page_size": 20,
        "counts": {key: counts.get(key, 0) for key in ("pending", "published", "hidden", "withdrawn")}}


@router.get("/{review_id}")
def detail(review_id: uuid.UUID, page: int = Query(1, ge=1, le=10000),
           _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.execute(review_query().where(LawyerReview.id == review_id)).first()
    if row is None: raise HTTPException(404, "Review not found.")
    query = select(LawyerReviewDecision, User.display_name).outerjoin(User, User.id == LawyerReviewDecision.actor_id).where(LawyerReviewDecision.review_id == review_id)
    rows = db.execute(query.order_by(LawyerReviewDecision.revision.desc()).offset((page - 1) * 20).limit(20)).all()
    return {"review": view(row), "history": [{"id": str(item.id), "from_status": item.from_status, "to_status": item.to_status,
        "reason": item.reason, "note": item.note, "revision": item.revision, "actor": name or "Former administrator", "created_at": iso(item.created_at)} for item, name in rows],
        "total": db.scalar(select(func.count()).select_from(LawyerReviewDecision).where(LawyerReviewDecision.review_id == review_id)), "page": page, "page_size": 20}


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    status: Literal["published", "hidden"]
    reason: Literal["approved", "privacy", "abuse", "off_topic", "authenticity", "other"]
    note: str = Field(min_length=5, max_length=1000)
    reviewed: bool = Field(strict=True)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value):
        if isinstance(value, str):
            if any(ord(char) < 32 and char not in "\n\r\t" for char in value): raise ValueError("Unsupported control character.")
            return value.strip()
        return value

    @model_validator(mode="after")
    def reviewed_and_consistent(self):
        if not self.reviewed: raise ValueError("Confirm that you reviewed the feedback before deciding.")
        if (self.status == "published") != (self.reason == "approved"):
            raise ValueError("Choose approved for publication or a reason for withholding the review.")
        return self


@router.patch("/{review_id}")
def decide(review_id: uuid.UUID, payload: Decision, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    review = db.get(LawyerReview, review_id)
    if review is None: raise HTTPException(404, "Review not found.")
    if review.withdrawn_at is not None: raise HTTPException(409, "The customer withdrew this review. It cannot be republished or moderated.")
    if review.lawyer_user_id == actor.id: raise HTTPException(403, "Another administrator must moderate reviews of your own profile.")
    if review.revision != payload.revision or review.moderation_status == payload.status:
        raise HTTPException(409, "This review changed or already has that status. Reload before deciding.")
    previous = review.moderation_status
    changed = db.execute(update(LawyerReview).where(LawyerReview.id == review_id, LawyerReview.revision == payload.revision, LawyerReview.withdrawn_at.is_(None))
        .values(moderation_status=payload.status, revision=payload.revision + 1, updated_at=utcnow()).returning(LawyerReview.id)).scalar_one_or_none()
    if changed is None: raise HTTPException(409, "This review changed. Reload before deciding.")
    db.add(LawyerReviewDecision(review_id=review_id, actor_id=actor.id, from_status=previous, to_status=payload.status,
        reason=payload.reason, note=payload.note, revision=payload.revision + 1))
    db.add(AuditLog(actor_user_id=actor.id, action="review.moderated", entity_type="lawyer_review", entity_id=review_id,
        metadata_={"from_status": previous, "to_status": payload.status, "revision": payload.revision + 1, "reason": payload.reason}))
    db.commit()
    return view(db.execute(review_query().where(LawyerReview.id == review_id)).one())
