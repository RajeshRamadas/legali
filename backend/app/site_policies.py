"""Administrator-reviewed public policies; private drafts and revision-checked publishing."""
import re
import uuid
from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, SitePolicy, SitePolicyVersion, User, utcnow
from .security import require_admin

router = APIRouter(prefix="/api/v1")
Kind = Literal["privacy", "terms", "grievance"]
LABELS = {"privacy": "Privacy notice", "terms": "Terms of service", "grievance": "Contact & grievance"}


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=600)
    body: str = Field(default="", max_length=20000)
    organization: str = Field(default="", max_length=160)
    contact_email: str = Field(default="", max_length=254)
    contact_phone: str = Field(default="", max_length=30)
    postal_address: str = Field(default="", max_length=1000)
    grievance_officer: str = Field(default="", max_length=160)

    @field_validator("*", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str):
            if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
                raise ValueError("Unsupported control character.")
            return value.strip()
        return value


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)


class Save(Revision):
    content: Content


class Publish(Revision):
    reviewed: bool = Field(strict=True)


class Withdraw(Publish):
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("Unsupported control character.")
        return value.strip() if isinstance(value, str) else value


def uncached(response):
    response.headers["Cache-Control"] = "no-store"


def snapshot(kind, item):
    # Explicit public allowlist: never expose staff identities, draft revisions or withdrawal reasons.
    published_at = item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=timezone.utc)
    return {"kind": kind, "number": item.number, "published_at": published_at.isoformat(),
        "content": Content.model_validate(item.content).model_dump()}


def head_view(db, kind):
    head = db.scalar(select(SitePolicy).where(SitePolicy.kind == kind))
    published = db.scalar(select(SitePolicyVersion).where(SitePolicyVersion.policy_id == head.id,
        SitePolicyVersion.number == head.published_version)) if head and head.published_version else None
    return {"kind": kind, "revision": head.revision if head else 0, "draft": head.draft if head else None,
        "published": snapshot(kind, published) if published else None,
        "withdraw_reason": head.withdraw_reason if head else None, "version_counter": head.version_counter if head else 0}


def locked(db, kind, revision, create=False):
    if create:
        insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
        db.execute(insert(SitePolicy).values(id=uuid.uuid4(), kind=kind, revision=0, version_counter=0, updated_at=utcnow())
            .on_conflict_do_nothing(index_elements=["kind"]))
    head = db.scalar(select(SitePolicy).where(SitePolicy.kind == kind).with_for_update().execution_options(populate_existing=True))
    if head is None:
        raise HTTPException(404, "Policy draft not found.")
    if head.revision != revision:
        raise HTTPException(409, "This policy changed. Reload the latest version before saving or publishing.")
    return head


def change(db, head, revision, **values):
    changed = db.execute(update(SitePolicy).where(SitePolicy.id == head.id, SitePolicy.revision == revision)
        .values(**values, revision=revision + 1, updated_at=utcnow()).returning(SitePolicy.id),
        execution_options={"synchronize_session": False}).scalar_one_or_none()
    if changed is None:
        raise HTTPException(409, "This policy changed. Reload the latest version before saving or publishing.")
    db.refresh(head)


def audit(db, head, actor, action):
    db.add(AuditLog(actor_user_id=actor.id, action=action, entity_type="site_policy", entity_id=head.id,
        metadata_={"kind": head.kind, "revision": head.revision, "version": head.published_version, "version_counter": head.version_counter}))


def publication_errors(kind, content):
    errors = []
    if len(content.title) < 5 or len(content.summary) < 20 or len(content.body) < 100 or len(content.organization) < 3:
        errors.append("Complete the title, summary, policy text and organization before publishing.")
    email = content.contact_email
    if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email)
        or email.rsplit("@", 1)[-1].lower().endswith((".invalid", ".example", ".test", ".localhost"))
        or email.rsplit("@", 1)[-1].lower() in ("example.com", "example.org", "example.net")):
        errors.append("Supply a real public contact email before publishing.")
    if content.contact_phone and (not re.fullmatch(r"\+?[0-9][0-9 ()-]{6,28}", content.contact_phone)
        or not 8 <= sum(char.isdigit() for char in content.contact_phone) <= 16):
        errors.append("Check the public phone number or leave it empty.")
    if kind == "grievance" and (len(content.grievance_officer) < 3 or len(content.postal_address) < 10):
        errors.append("Contact & grievance publication needs an accountable contact name and postal address.")
    return errors


@router.get("/policies")
def public_index(response: Response, db: Session = Depends(get_db)):
    uncached(response)
    rows = {head.kind: item for head, item in db.execute(select(SitePolicy, SitePolicyVersion).join(SitePolicyVersion,
        (SitePolicyVersion.policy_id == SitePolicy.id) & (SitePolicyVersion.number == SitePolicy.published_version))
        .where(SitePolicyVersion.is_public.is_(True)))}
    return {"items": [{"kind": kind, "label": label, "available": kind in rows,
        "policy": snapshot(kind, rows[kind]) if kind in rows else None} for kind, label in LABELS.items()]}


def public_find(db, kind, number=None):
    query = select(SitePolicyVersion).join(SitePolicy, SitePolicy.id == SitePolicyVersion.policy_id).where(
        SitePolicy.kind == kind, SitePolicy.published_version.is_not(None), SitePolicyVersion.is_public.is_(True))
    query = query.where(SitePolicyVersion.number == (SitePolicy.published_version if number is None else number))
    item = db.scalar(query)
    if item is None:
        raise HTTPException(404, "This policy is not published.", headers={"Cache-Control": "no-store"})
    return snapshot(kind, item)


@router.get("/policies/{kind}")
def public_current(kind: Kind, response: Response, db: Session = Depends(get_db)):
    uncached(response)
    return public_find(db, kind)


@router.get("/policies/{kind}/versions/{number}")
def public_version(kind: Kind, number: int, response: Response, db: Session = Depends(get_db)):
    uncached(response)
    return public_find(db, kind, number)


@router.get("/admin/site-policies")
def admin_index(response: Response, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    uncached(response)
    return {"items": [head_view(db, kind) for kind in LABELS]}


@router.put("/admin/site-policies/{kind}/draft")
def save(kind: Kind, payload: Save, response: Response, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    uncached(response)
    head = locked(db, kind, payload.revision, create=True)
    change(db, head, payload.revision, draft=payload.content.model_dump())
    audit(db, head, actor, "site_policy_draft_saved")
    db.commit()
    return head_view(db, kind)


@router.post("/admin/site-policies/{kind}/publish")
def publish(kind: Kind, payload: Publish, response: Response, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    uncached(response)
    if not payload.reviewed:
        raise HTTPException(422, "Confirm that this version and its contact details are reviewed for publication.")
    head = locked(db, kind, payload.revision)
    if head.draft is None:
        raise HTTPException(409, "Save a draft before publishing.")
    content = Content.model_validate(head.draft)
    errors = publication_errors(kind, content)
    if errors:
        raise HTTPException(422, " ".join(errors))
    number = head.version_counter + 1
    change(db, head, payload.revision, published_version=number, version_counter=number, draft=None, withdraw_reason=None)
    db.add(SitePolicyVersion(policy_id=head.id, number=number, content=content.model_dump(), published_by_user_id=actor.id))
    audit(db, head, actor, "site_policy_published")
    db.commit()
    return head_view(db, kind)


@router.post("/admin/site-policies/{kind}/withdraw")
def withdraw(kind: Kind, payload: Withdraw, response: Response, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    uncached(response)
    if not payload.reviewed:
        raise HTTPException(422, "Confirm withdrawal of this policy and its public history.")
    head = locked(db, kind, payload.revision)
    if head.published_version is None:
        raise HTTPException(409, "This policy is already unpublished.")
    change(db, head, payload.revision, published_version=None, withdraw_reason=payload.reason)
    db.execute(update(SitePolicyVersion).where(SitePolicyVersion.policy_id == head.id).values(is_public=False))
    audit(db, head, actor, "site_policy_withdrawn")
    db.commit()
    return head_view(db, kind)


@router.get("/admin/site-policies/{kind}/versions")
def history(kind: Kind, response: Response, page: int = Query(1, ge=1), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    uncached(response)
    head = db.scalar(select(SitePolicy).where(SitePolicy.kind == kind))
    query = select(SitePolicyVersion).where(SitePolicyVersion.policy_id == head.id) if head else select(SitePolicyVersion).where(False)
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(SitePolicyVersion.number.desc()).offset((page - 1) * 10).limit(10))
    return {"items": [{**snapshot(kind, item), "is_public": item.is_public} for item in rows], "total": count, "page": page, "page_size": 10}
