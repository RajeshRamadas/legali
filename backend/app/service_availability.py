"""Admission controls for new cases; existing customer records remain accessible."""
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, ServiceType, User
from .security import require_admin

router = APIRouter(prefix="/api/v1/admin/services")
PAUSED = "This service is temporarily not accepting new requests. Choose another available service or try again later."


def public_view(service):
    return {"slug": service.slug, "name": service.name, "category": service.category,
        "description": service.description_override if service.description_override is not None else service.description,
        "property_types": service.supported_property_types}


def accepts_requests(db: Session, slug: str) -> bool:
    return db.scalar(select(ServiceType.id).where(ServiceType.slug == slug, ServiceType.is_active.is_(True), ServiceType.intake_paused.is_(False))) is not None


def admit_new_request(db: Session, service: ServiceType) -> None:
    # Hold a shared service-row lock until creation commits. An administrator's
    # exclusive pause waits for already-admitted work, then blocks later requests.
    row = db.execute(select(ServiceType.is_active, ServiceType.intake_paused)
        .where(ServiceType.id == service.id).with_for_update(read=True, of=ServiceType)).first()
    if row is None or not row.is_active or row.intake_paused:
        raise HTTPException(409, PAUSED)


def view(service):
    return {**public_view(service), "id": str(service.id), "active": service.is_active,
        "paused": service.intake_paused, "revision": service.availability_revision,
        "description_revision": service.description_revision, "description_customized": service.description_override is not None,
        "default_description": service.description}


@router.get("")
def catalogue(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ServiceType).order_by(ServiceType.name)).all()
    return {"items": [view(service) for service in rows]}


class Availability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=1, le=2147483646)
    paused: bool = Field(strict=True)
    confirmed: bool = Field(strict=True)
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 10: raise ValueError("Give a private operational reason of at least ten characters.")
        return value.strip()

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if not value: raise ValueError("Confirm that you reviewed the effect on new requests.")
        return value


@router.patch("/{slug}")
def change(slug: str, payload: Availability, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug).with_for_update().execution_options(populate_existing=True))
    if service is None: raise HTTPException(404, "Service not found.")
    if not service.is_active: raise HTTPException(409, "This service is retired. Availability controls cannot reactivate it.")
    if service.availability_revision != payload.revision or service.intake_paused == payload.paused:
        raise HTTPException(409, "Service availability changed or already has this state. Reload the catalogue before saving.")
    service.intake_paused = payload.paused
    service.availability_revision += 1
    db.add(AuditLog(actor_user_id=actor.id, action="service.availability_changed", entity_type="service_type", entity_id=service.id,
        metadata_={"paused": payload.paused, "revision": service.availability_revision, "reason": payload.reason}))
    db.commit()
    return view(service)


@router.get("/{slug}/history")
def history(slug: str, page: int = Query(1, ge=1, le=10000), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug))
    if service is None: raise HTTPException(404, "Service not found.")
    query = select(AuditLog, User.display_name).outerjoin(User, User.id == AuditLog.actor_user_id).where(
        AuditLog.entity_type == "service_type", AuditLog.entity_id == service.id, AuditLog.action == "service.availability_changed")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id).offset((page-1)*20).limit(20)).all()
    return {"items": [{"id": str(event.id), **event.metadata_, "actor": actor or "Former administrator",
        "at": (event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=timezone.utc)).isoformat()} for event, actor in rows],
        "page": page, "page_size": 20, "total": total}
