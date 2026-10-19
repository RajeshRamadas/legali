"""Blog: articles and case studies. Anyone can read published posts; only admins write, publish and delete them."""
import math
import re
import unicodedata
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import POST_STATUSES, POST_TYPES, AuditLog, Post, User, utcnow
from .security import require_admin

router = APIRouter(prefix="/api/v1")

POST_TYPE_LABELS = {"article": "Article", "case_study": "Case study"}
_SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

class Highlight(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=160)

def _clean_image_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if not re.match(r"^(https?://|/)\S+$", value):
        raise ValueError("Use an http(s) address or a path on this site.")
    return value

def _clean_tags(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    cleaned: list[str] = []
    for tag in value:
        tag = " ".join(tag.split())[:40]
        if tag and tag.lower() not in {t.lower() for t in cleaned}:
            cleaned.append(tag)
    return cleaned

class PostFields(BaseModel):
    excerpt: str = Field(default="", max_length=400, description="One or two sentences for listings and search results.")
    body: str = Field(default="", max_length=60000, description="Markdown.")
    cover_image_url: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    highlights: list[Highlight] = Field(default_factory=list, max_length=8)

    _image_url = field_validator("cover_image_url")(lambda cls, v: _clean_image_url(v))
    _tags = field_validator("tags")(lambda cls, v: _clean_tags(v))

class PostCreate(PostFields):
    post_type: Literal[POST_TYPES]  # type: ignore[valid-type]
    title: str = Field(min_length=3, max_length=200)
    slug: str | None = Field(default=None, max_length=120, pattern=_SLUG, description="Generated from the title when left out.")
    status: Literal[POST_STATUSES] = "draft"  # type: ignore[valid-type]

class PostUpdate(BaseModel):
    post_type: Literal[POST_TYPES] | None = None  # type: ignore[valid-type]
    title: str | None = Field(default=None, min_length=3, max_length=200)
    slug: str | None = Field(default=None, max_length=120, pattern=_SLUG)
    status: Literal[POST_STATUSES] | None = None  # type: ignore[valid-type]
    excerpt: str | None = Field(default=None, max_length=400)
    body: str | None = Field(default=None, max_length=60000)
    cover_image_url: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=8)
    highlights: list[Highlight] | None = Field(default=None, max_length=8)

    _image_url = field_validator("cover_image_url")(lambda cls, v: _clean_image_url(v))
    _tags = field_validator("tags")(lambda cls, v: _clean_tags(v))

def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80].strip("-") or "post"

def _unique_slug(db: Session, base: str) -> str:
    slug, n = base, 2
    while db.scalars(select(Post.id).where(Post.slug == slug)).first():
        slug, n = f"{base}-{n}", n + 1
    return slug

def _reading_minutes(body: str) -> int:
    return max(1, math.ceil(len(body.split()) / 200))

def _summary(post: Post) -> dict:
    return {
        "id": str(post.id),
        "slug": post.slug,
        "post_type": post.post_type,
        "type_label": POST_TYPE_LABELS[post.post_type],
        "status": post.status,
        "title": post.title,
        "excerpt": post.excerpt,
        "cover_image_url": post.cover_image_url,
        "tags": post.tags,
        "author": post.author.display_name if post.author else "Homexo Legal",
        "reading_minutes": _reading_minutes(post.body),
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "updated_at": post.updated_at.isoformat(),
    }

def _detail(post: Post) -> dict:
    return {**_summary(post), "body": post.body, "highlights": post.highlights}

def _audit(db: Session, user: User, action: str, post: Post, **metadata) -> None:
    db.add(AuditLog(actor_user_id=user.id, action=action, entity_type="post", entity_id=post.id, metadata_={"slug": post.slug, **metadata}))

def _set_status(post: Post, status: str) -> None:
    post.status = status
    if status == "published" and post.published_at is None:
        post.published_at = utcnow()

def _page(db: Session, query, page: int, page_size: int, order) -> dict:
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_summary(p) for p in items], "total": total, "page": page, "page_size": page_size}

def _search(query, q: str | None):
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(Post.title).like(like), func.lower(Post.excerpt).like(like)))
    return query

# Public

@router.get("/posts")
def list_posts(
    type: Literal[POST_TYPES] | None = None,  # type: ignore[valid-type]
    tag: str | None = Query(None, max_length=40),
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = _search(select(Post).where(Post.status == "published"), q)
    if type:
        query = query.where(Post.post_type == type)
    if tag:
        # Tags are a short JSON list; filter in Python so this works the same on SQLite and PostgreSQL.
        ids = [p.id for p in db.scalars(query) if tag.lower() in {t.lower() for t in p.tags}]
        query = select(Post).where(Post.id.in_(ids))
    return _page(db, query, page, page_size, (Post.published_at.desc(), Post.id))

@router.get("/posts/{slug}")
def get_post(slug: str, db: Session = Depends(get_db)):
    post = db.scalars(select(Post).where(Post.slug == slug, Post.status == "published")).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    related = db.scalars(
        select(Post).where(Post.status == "published", Post.post_type == post.post_type, Post.id != post.id).order_by(Post.published_at.desc()).limit(3)
    ).all()
    return {**_detail(post), "related": [_summary(p) for p in related]}

# Admin

@router.get("/admin/posts")
def admin_list_posts(
    type: Literal[POST_TYPES] | None = None,  # type: ignore[valid-type]
    status: Literal[POST_STATUSES] | None = None,  # type: ignore[valid-type]
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = _search(select(Post), q)
    if type:
        query = query.where(Post.post_type == type)
    if status:
        query = query.where(Post.status == status)
    return _page(db, query, page, page_size, (Post.updated_at.desc(), Post.id))

def _admin_get(db: Session, post_id: uuid.UUID) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@router.get("/admin/posts/{post_id}")
def admin_get_post(post_id: uuid.UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _detail(_admin_get(db, post_id))

@router.post("/admin/posts", status_code=201)
def create_post(payload: PostCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.slug and db.scalars(select(Post.id).where(Post.slug == payload.slug)).first():
        raise HTTPException(status_code=409, detail="Another post already uses that web address.")
    post = Post(
        slug=payload.slug or _unique_slug(db, slugify(payload.title)),
        post_type=payload.post_type,
        title=payload.title.strip(),
        excerpt=payload.excerpt.strip(),
        body=payload.body,
        cover_image_url=payload.cover_image_url,
        tags=payload.tags,
        highlights=[h.model_dump() for h in payload.highlights],
        author_user_id=user.id,
    )
    _set_status(post, payload.status)
    db.add(post)
    db.flush()
    _audit(db, user, "post.created", post, status=post.status)
    db.commit()
    db.refresh(post)
    return _detail(post)

@router.patch("/admin/posts/{post_id}")
def update_post(post_id: uuid.UUID, payload: PostUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    post = _admin_get(db, post_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("slug") and changes["slug"] != post.slug and db.scalars(select(Post.id).where(Post.slug == changes["slug"], Post.id != post.id)).first():
        raise HTTPException(status_code=409, detail="Another post already uses that web address.")
    for field in ("post_type", "slug", "body", "cover_image_url", "tags"):
        if field in changes and (changes[field] is not None or field == "cover_image_url"):
            setattr(post, field, changes[field])
    for field in ("title", "excerpt"):
        if changes.get(field) is not None:
            setattr(post, field, changes[field].strip())
    if changes.get("highlights") is not None:
        post.highlights = changes["highlights"]
    old_status = post.status
    if changes.get("status"):
        _set_status(post, changes["status"])
    post.updated_at = utcnow()
    action = {("draft", "published"): "post.published", ("published", "draft"): "post.unpublished"}.get((old_status, post.status), "post.updated")
    _audit(db, user, action, post)
    db.commit()
    db.refresh(post)
    return _detail(post)

@router.delete("/admin/posts/{post_id}", status_code=204)
def delete_post(post_id: uuid.UUID, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    post = _admin_get(db, post_id)
    _audit(db, user, "post.deleted", post, title=post.title)
    db.delete(post)
    db.commit()
    return Response(status_code=204)
