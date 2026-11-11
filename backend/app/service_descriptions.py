"""Reviewed public catalogue copy, independent of service admission settings."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, ServiceType, User
from .security import require_admin
from .service_availability import view, public_view
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/services")


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=1, le=2147483646)
    description: str | None = Field(min_length=10, max_length=800)
    standard_description: str | None = Field(default=None, min_length=10, max_length=800)
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool = Field(strict=True)

    @field_validator("description", "standard_description", "reason", mode="before")
    @classmethod
    def plain_text(cls, value):
        if isinstance(value, str):
            if any(ord(char) < 32 and char not in "\n\t" or ord(char) == 127 for char in value):
                raise ValueError("Use plain text without control characters.")
            return value.strip()
        return value

    @field_validator("confirmed")
    @classmethod
    def reviewed(cls, value):
        if not value: raise ValueError("Review the public description before publishing.")
        return value


@router.patch("/{slug}/description")
def publish(slug: str, payload: Publication, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug).with_for_update().execution_options(populate_existing=True))
    if service is None: raise HTTPException(404, "Service not found.")
    if not service.is_active: raise HTTPException(409, "Retired service descriptions cannot be published.")
    if payload.revision != service.description_revision:
        raise HTTPException(409, "This description changed. Your draft is kept. Reload the catalogue to review the latest copy before publishing.")
    if payload.description is None and payload.standard_description != service.description:
        raise HTTPException(409, "The standard description changed. Reload the catalogue and review the current standard copy before publishing.")
    if service.description_override == payload.description:
        return view(service)
    previous = public_view(service)["description"]
    service.description_override = payload.description
    service.description_revision += 1
    db.add(AuditLog(actor_user_id=actor.id, action="service.description_changed", entity_type="service_type", entity_id=service.id,
        metadata_={"previous_description": previous, "description": public_view(service)["description"],
            "uses_standard": payload.description is None, "revision": service.description_revision, "reason": payload.reason}))
    db.commit()
    return view(service)


@router.get("/{slug}/description/history")
def history(slug: str, page: int = Query(1, ge=1, le=10000), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug))
    if service is None: raise HTTPException(404, "Service not found.")
    query = select(AuditLog, User.display_name).outerjoin(User, User.id == AuditLog.actor_user_id).where(
        AuditLog.entity_type == "service_type", AuditLog.entity_id == service.id, AuditLog.action == "service.description_changed")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id).offset((page-1)*20).limit(20)).all()
    return {"items": [{"id": str(event.id), "at": aware(event.created_at).isoformat(), "actor": name or "Former administrator",
        **{key: event.metadata_.get(key) for key in ("previous_description", "description", "uses_standard", "revision", "reason")}}
        for event, name in rows], "page": page, "page_size": 20, "total": total}
