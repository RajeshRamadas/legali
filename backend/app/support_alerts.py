"""Private response incidents with optional administrator email queued for the worker."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from . import config, support_deadline_email
from .support_deadline_email import active
from .db import get_db
from .models import AuditLog, CustomerAccount, SupportDeadlineAlert, SupportRequest, User, utcnow
from .security import require_admin
from .support import find, lock_account, owner_view
from .tickets import aware

router = APIRouter(prefix="/api/v1/admin/support-requests/deadline-alerts")


class Acknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=1, le=2147483647)


def audit(db, item, alert, action, actor=None):
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, entity_type="support_request", entity_id=item.id,
        metadata_={"alert_id": str(alert.id), "target_at": aware(alert.target_at).isoformat(), "alert_revision": alert.revision}))


def reconcile(db: Session, now=None):
    """Page candidates and follow the support account/request lock order across workers."""
    now = aware(now or utcnow())
    cursor, created = None, 0
    while True:
        candidate = or_(
            (SupportRequest.status != "resolved") & (SupportRequest.reply_due_at < now),
            exists().where(SupportDeadlineAlert.support_request_id == SupportRequest.id, SupportDeadlineAlert.resolved_at.is_(None)))
        query = select(SupportRequest.id, SupportRequest.account_id).where(candidate).order_by(SupportRequest.id).limit(100)
        if cursor is not None:
            query = query.where(SupportRequest.id > cursor)
        rows = list(db.execute(query))
        if not rows:
            break
        for request_id, account_id in rows:
            locked = db.scalar(select(CustomerAccount.id).where(CustomerAccount.id == account_id).with_for_update(skip_locked=True))
            if locked is None:
                db.rollback()
                continue
            item = db.scalar(select(SupportRequest).where(SupportRequest.id == request_id).with_for_update().execution_options(populate_existing=True))
            if item is None:
                db.rollback()
                continue
            pending = list(db.scalars(select(SupportDeadlineAlert).where(SupportDeadlineAlert.support_request_id == item.id, SupportDeadlineAlert.resolved_at.is_(None))))
            for alert in pending:
                if not active(alert, item, now):
                    alert.resolved_at, alert.revision = now, alert.revision+1
                    audit(db, item, alert, "support.deadline_resolved")
                    support_deadline_email.sync_alert(db, alert, item, now)
            if item.status != "resolved" and item.reply_due_at and aware(item.reply_due_at) < now:
                due = aware(item.reply_due_at)
                alert = db.scalar(select(SupportDeadlineAlert).where(SupportDeadlineAlert.support_request_id == item.id, SupportDeadlineAlert.target_at == due))
                if alert is None:
                    alert = SupportDeadlineAlert(support_request_id=item.id, target_at=due, created_at=now, revision=1)
                    db.add(alert); db.flush(); created += 1
                    audit(db, item, alert, "support.deadline_alerted")
                elif alert.resolved_at is not None:
                    alert.resolved_at = alert.acknowledged_at = alert.acknowledged_by_id = None
                    alert.revision += 1
                    audit(db, item, alert, "support.deadline_reopened")
                if alert.escalated_at is None and due + timedelta(hours=config.SUPPORT_ESCALATION_HOURS) <= now:
                    alert.escalated_at = now
                    alert.acknowledged_at = alert.acknowledged_by_id = None
                    alert.revision += 1
                    audit(db, item, alert, "support.deadline_escalated")
                support_deadline_email.sync_alert(db, alert, item, now)
            db.commit()
        cursor = rows[-1][0]
    return created


def active_query(now):
    # Revalidate current support state even when the monitoring worker is behind.
    return select(SupportDeadlineAlert).join(SupportRequest, SupportRequest.id == SupportDeadlineAlert.support_request_id).where(
        SupportDeadlineAlert.resolved_at.is_(None), SupportRequest.status != "resolved",
        SupportRequest.reply_due_at == SupportDeadlineAlert.target_at, SupportDeadlineAlert.target_at < now)


def counts(db, now):
    pending = active_query(now).where(SupportDeadlineAlert.acknowledged_at.is_(None)).subquery()
    return dict(db.execute(select(func.count().label("unacknowledged"),
        func.count(pending.c.escalated_at).label("escalated")).select_from(pending)).mappings().one())


def views(db, rows):
    requests = {item.id: item for item in db.scalars(select(SupportRequest).where(SupportRequest.id.in_({row.support_request_id for row in rows})))} if rows else {}
    ids = {value for row in rows for value in (row.acknowledged_by_id, requests[row.support_request_id].assignee_user_id) if value}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    def person(id):
        return {"id": str(id), "name": users[id].display_name if id in users else "Former administrator"} if id else None
    return [{"id": str(row.id), "support_request_id": str(row.support_request_id), "reference": "SR-"+row.support_request_id.hex.upper(),
        "kind": requests[row.support_request_id].kind, "revision": row.revision,
        "owner": owner_view(users.get(requests[row.support_request_id].assignee_user_id), requests[row.support_request_id].assignee_user_id),
        "target_at": aware(row.target_at).isoformat(), "created_at": aware(row.created_at).isoformat(),
        "escalated_at": aware(row.escalated_at).isoformat() if row.escalated_at else None,
        "acknowledged_at": aware(row.acknowledged_at).isoformat() if row.acknowledged_at else None,
        "acknowledged_by": person(row.acknowledged_by_id)} for row in rows]


@router.get("")
def list_alerts(include_acknowledged: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    _: User = Depends(require_admin), db: Session = Depends(get_db)):
    now = utcnow()
    query = active_query(now)
    if not include_acknowledged:
        query = query.where(SupportDeadlineAlert.acknowledged_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(db.scalars(query.order_by(SupportDeadlineAlert.escalated_at.is_(None), SupportDeadlineAlert.target_at, SupportDeadlineAlert.id)
        .offset((page-1)*page_size).limit(page_size)))
    return {"items": views(db, rows), "total": total, **counts(db, now), "page": page, "page_size": page_size,
        "check_interval_seconds": config.NOTIFY_INTERVAL_SECONDS, "email_delivery": support_deadline_email.delivery_status()}


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: uuid.UUID, payload: Acknowledge, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    alert = db.get(SupportDeadlineAlert, alert_id)
    if alert is None:
        raise HTTPException(404, "Support alert not found.")
    item = find(db, alert.support_request_id)
    lock_account(db, item.account_id)
    item = find(db, item.id, lock=True)
    db.refresh(alert, with_for_update=True)
    if not active(alert, item, utcnow()) or payload.revision != alert.revision:
        raise HTTPException(409, "This support alert changed or no longer needs attention. Refresh before acknowledging it.")
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by_id = utcnow(), actor.id
        audit(db, item, alert, "support.deadline_acknowledged", actor)
        support_deadline_email.cancel_pending(db, alert.id)
        db.commit()
    return views(db, [alert])[0]


if __name__ == "__main__":
    from .db import SessionLocal
    with SessionLocal() as session:
        reconcile(session)
