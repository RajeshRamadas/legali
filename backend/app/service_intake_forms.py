"""Reviewed, bounded service questions; draft selections are pinned, never retargeted."""
import uuid
from copy import deepcopy
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, ServiceType, User
from .security import require_admin
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/intake-forms")


class Text(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str):
            if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in value):
                raise ValueError("Use plain text without control characters.")
            return value.strip()
        return value


class Question(Text):
    id: uuid.UUID
    prompt: str = Field(min_length=5, max_length=160)
    help: str = Field(default="", max_length=400)
    kind: Literal["text", "textarea", "select"]
    required: bool = Field(strict=True)
    max_length: int = Field(strict=True, ge=1, le=1000)
    options: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def choices(self):
        self.options = [value.strip() for value in self.options]
        if self.kind == "select":
            if not 2 <= len(self.options) <= 8 or any(not value or len(value) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in value) for value in self.options):
                raise ValueError("Give two to eight plain-text choices, each 1–80 characters.")
            if len({value.casefold() for value in self.options}) != len(self.options):
                raise ValueError("Choices must be distinct.")
        elif self.options:
            raise ValueError("Text questions do not have choices.")
        return self


class Publication(Text):
    revision: int = Field(strict=True, ge=1, le=2147483646)
    questions: list[Question] = Field(max_length=5)
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool = Field(strict=True)

    @model_validator(mode="after")
    def reviewed(self):
        if not self.confirmed: raise ValueError("Review the questions before publishing.")
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("Question identifiers must be distinct.")
        return self


def view(service):
    return {"slug": service.slug, "name": service.name, "active": service.is_active,
        "revision": service.intake_form_revision, "questions": service.intake_questions}


def locked_service(db, slug, revision):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug).with_for_update().execution_options(populate_existing=True))
    if service is None: raise HTTPException(404, "Service not found.")
    if not service.is_active: raise HTTPException(409, "Retired service forms cannot be published.")
    if service.intake_form_revision != revision:
        raise HTTPException(409, "This form changed. Your draft is kept. Reload the published form before saving again.")
    return service


def save_publication(db, service, questions, reason, actor, **provenance):
    previous = service.intake_questions
    service.intake_questions = deepcopy(questions); service.intake_form_revision += 1
    db.add(AuditLog(actor_user_id=actor.id, action="service.intake_form_published", entity_type="service_type", entity_id=service.id,
        metadata_={"questions": questions, "previous_questions": previous, "revision": service.intake_form_revision, "reason": reason, **provenance}))
    db.commit()
    return view(service)


@router.get("")
def catalogue(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [view(service) for service in db.scalars(select(ServiceType).order_by(ServiceType.name))]}


@router.patch("/{slug}")
def publish(slug: str, payload: Publication, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = locked_service(db, slug, payload.revision)
    questions = [question.model_dump(mode="json") for question in payload.questions]
    if service.intake_questions == questions: return view(service)
    return save_publication(db, service, questions, payload.reason, actor)


class Restoration(Text):
    revision: int = Field(strict=True, ge=1, le=2147483646)
    source_revision: int = Field(strict=True, ge=1, le=2147483646)
    preview_questions: list[Question] = Field(max_length=5)
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool = Field(strict=True)

    @model_validator(mode="after")
    def reviewed(self):
        if not self.confirmed: raise ValueError("Review the earlier questions before restoring.")
        if len({row.id for row in self.preview_questions}) != len(self.preview_questions):
            raise ValueError("Question identifiers must be distinct.")
        return self


@router.post("/{slug}/restore")
def restore(slug: str, payload: Restoration, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = locked_service(db, slug, payload.revision)
    if payload.source_revision >= service.intake_form_revision:
        raise HTTPException(409, "Choose an earlier retained version to restore.")
    scope = select(AuditLog).where(AuditLog.entity_type == "service_type", AuditLog.entity_id == service.id,
        AuditLog.action == "service.intake_form_published")
    version = cast(AuditLog.metadata_["revision"].as_string(), String)
    expected_version = payload.source_revision
    events = db.scalars(scope.where(version == str(expected_version)).limit(2)).all()
    field = "questions"
    if not events:
        # The following publication also retains the preceding definition,
        # including the original empty form before the first publication.
        expected_version += 1
        events = db.scalars(scope.where(version == str(expected_version)).limit(2)).all()
        field = "previous_questions"
    if not events: raise HTTPException(404, "This service version is no longer retained in publication history.")
    if len(events) != 1: raise HTTPException(409, "This version has ambiguous history. Review the retained records before restoring.")
    event = events[0]
    if type(event.metadata_.get("revision")) is not int or event.metadata_["revision"] != expected_version:
        raise HTTPException(409, "This version has invalid history metadata. Review the retained records before restoring.")
    try:
        validated = Publication.model_validate({"revision":payload.revision, "questions":event.metadata_.get(field), "reason":payload.reason, "confirmed":True})
    except ValidationError:
        raise HTTPException(409, "This retained version cannot be restored safely. Review its definitions before proceeding.")
    questions = [row.model_dump(mode="json") for row in validated.questions]
    if questions != [row.model_dump(mode="json") for row in payload.preview_questions]:
        raise HTTPException(409, "The retained questions differ from your preview. Reload history and review the version again.")
    if questions == service.intake_questions:
        raise HTTPException(409, "These questions already match the published form. No restoration was made.")
    return save_publication(db, service, questions, payload.reason, actor,
        restored_from_revision=payload.source_revision, source_event_id=str(event.id), source_snapshot=field)


@router.get("/{slug}/history")
def history(slug: str, page: int = Query(1, ge=1, le=10000), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.scalar(select(ServiceType).where(ServiceType.slug == slug))
    if service is None: raise HTTPException(404, "Service not found.")
    query = select(AuditLog, User.display_name).outerjoin(User, User.id == AuditLog.actor_user_id).where(
        AuditLog.entity_type == "service_type", AuditLog.entity_id == service.id, AuditLog.action == "service.intake_form_published")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id).offset((page-1)*20).limit(20)).all()
    return {"items": [{"id": str(event.id), "at": aware(event.created_at).isoformat(), "actor": name or "Former administrator",
        **{key: event.metadata_.get(key) for key in ("questions", "previous_questions", "revision", "reason", "restored_from_revision")}} for event, name in rows],
        "page": page, "page_size": 20, "total": total}


def snapshot(db, slug):
    # One row read keeps the revision and content consistent with concurrent publication.
    row = db.execute(select(ServiceType.slug, ServiceType.intake_form_revision, ServiceType.intake_questions).where(ServiceType.slug == slug)).first()
    return {"service_slug": row.slug, "revision": row.intake_form_revision, "questions": deepcopy(row.intake_questions)} if row else {}


def selected_questions(snapshot, answers):
    if not snapshot or snapshot.get("service_slug") != answers.get("service_slug"): return []
    return [{"key": "extra_"+uuid.UUID(row["id"]).hex, "prompt": row["prompt"], "help": row["help"], "kind": row["kind"],
        "required": row["required"], "min_length": 1 if row["required"] else 0, "max_length": row["max_length"],
        "options": [{"value": str(index+1), "label": label} for index, label in enumerate(row["options"])]}
        for row in snapshot["questions"]]
