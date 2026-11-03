"""Case deadline monitoring, staff-only alerts and bounded escalation emails."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session

from . import config, tickets
from .admin import _get_ticket, _visible_tickets
from .db import get_db
from .models import AuditLog, CaseDeadlineAlert, CLOSED_STATUSES, Notification, ServiceRequest, User, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1/admin/case-alerts")
LABELS = {"case_due": "Case target missed", "first_response": "First response overdue"}


def target(ticket, kind):
    return ticket.due_at if kind == "case_due" else ticket.first_response_due_at if ticket.first_response_at is None else None

def active(alert, ticket, now):
    due = target(ticket, alert.kind) if ticket else None
    return bool(ticket and ticket.status not in (*CLOSED_STATUSES, "draft", "on_hold") and not alert.resolved_at and due
                and tickets.aware(due) == tickets.aware(alert.target_at) and tickets.aware(due) < now)

def _recipients(db, ticket, escalated):
    admins = list(db.scalars(select(User).where(User.account_status == "active", User.roles.any(name="admin"))))
    supers = list(db.scalars(select(User).where(User.account_status == "active", User.roles.any(name="super_admin"))))
    admins = {u.id: u for u in admins + supers}
    assignment = ticket.active_assignment
    owner = db.get(User, assignment.agent_user_id, populate_existing=True) if assignment else None
    if not owner or owner.account_status != "active" or not (owner.role_names & {"agent", "admin", "super_admin"}):
        owner = None
    return {**(admins if escalated or owner is None else {}), **({owner.id: owner} if owner else {})}

def _audit(db, ticket, action, alert):
    db.add(AuditLog(action=action, entity_type="service_request", entity_id=ticket.id,
        metadata_={"alert_id": str(alert.id), "kind": alert.kind, "target_at": tickets.aware(alert.target_at).isoformat()}))

def _cancel(db, alert_id):
    # An in-flight provider request may already have been accepted; leave its result truthful.
    db.execute(update(Notification).where(Notification.case_alert_id == alert_id, Notification.delivery_status == "queued",
        Notification.claim_token.is_(None)).values(delivery_status="cancelled", error_code="alert_no_longer_pending"))


def reconcile(db: Session, now=None):
    """Walk candidates in bounded pages; lock each case so parallel workers cannot duplicate incidents."""
    now = now or utcnow()
    cursor = None
    created = 0
    while True:
        candidate = or_(
            ServiceRequest.status.not_in((*CLOSED_STATUSES, "draft", "on_hold")) & or_(
                ServiceRequest.due_at < now,
                ServiceRequest.first_response_at.is_(None) & (ServiceRequest.first_response_due_at < now)),
            exists().where(CaseDeadlineAlert.service_request_id == ServiceRequest.id, CaseDeadlineAlert.resolved_at.is_(None)))
        query = select(ServiceRequest.id).where(candidate).order_by(ServiceRequest.id).limit(100)
        if cursor is not None:
            query = query.where(ServiceRequest.id > cursor)
        ids = list(db.scalars(query))
        if not ids:
            break
        for id in ids:
            ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.id == id)
                .with_for_update(skip_locked=True, of=ServiceRequest).execution_options(populate_existing=True))
            if ticket is None:
                db.rollback()
                continue
            alerts = list(db.scalars(select(CaseDeadlineAlert).where(CaseDeadlineAlert.service_request_id == id)))
            for alert in alerts:
                if alert.resolved_at is None and not active(alert, ticket, now):
                    alert.resolved_at = now; _cancel(db, alert.id)
                    _audit(db, ticket, "case.deadline_resolved", alert)
            if ticket.status not in (*CLOSED_STATUSES, "draft", "on_hold"):
                for kind in LABELS:
                    due = target(ticket, kind)
                    if due is None or tickets.aware(due) >= now:
                        continue
                    due = tickets.aware(due)
                    alert = next((a for a in alerts if a.kind == kind and tickets.aware(a.target_at) == due), None)
                    if alert is None:
                        alert = CaseDeadlineAlert(service_request_id=id, kind=kind, target_at=due, created_at=now)
                        db.add(alert); db.flush(); created += 1
                        _audit(db, ticket, "case.deadline_alerted", alert)
                    elif alert.resolved_at is not None:
                        # Reusing the same target after a temporary condition change revives the same incident.
                        alert.resolved_at = None
                    if due + timedelta(hours=config.CASE_ESCALATION_HOURS) <= now and alert.escalated_at is None:
                        alert.escalated_at = now
                        alert.acknowledged_at = alert.acknowledged_by_id = None
                        _audit(db, ticket, "case.deadline_escalated", alert)
                    if alert.acknowledged_at:
                        continue
                    phase = "escalated" if alert.escalated_at else "initial"
                    for user in _recipients(db, ticket, bool(alert.escalated_at)).values():
                        if not user.email:
                            continue
                        key = f"case-alert:{alert.id}:{user.id}:{phase}"
                        if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)) is None:
                            db.add(Notification(service_request_id=id, user_id=user.id, case_alert_id=alert.id,
                                channel="email", template_key="case_deadline_alert", recipient=user.email, params=[kind, phase],
                                dedupe_key=key, send_after=now))
            db.commit()
        cursor = ids[-1]
    return created


def delivery_allowed(db, notification, now):
    if notification.template_key != "case_deadline_alert":
        return True
    if not notification.case_alert_id or not notification.user_id:
        return False
    alert = db.get(CaseDeadlineAlert, notification.case_alert_id, populate_existing=True)
    ticket = db.get(ServiceRequest, notification.service_request_id, populate_existing=True) if notification.service_request_id else None
    if not alert or not active(alert, ticket, now) or alert.acknowledged_at:
        return False
    user = _recipients(db, ticket, bool(alert.escalated_at)).get(notification.user_id)
    phase = "escalated" if alert.escalated_at else "initial"
    return bool(user and notification.recipient == user.email and notification.params == [alert.kind, phase])


def _query(user, now):
    visible = _visible_tickets(user).with_only_columns(ServiceRequest.id).order_by(None)
    return select(CaseDeadlineAlert).join(ServiceRequest, ServiceRequest.id == CaseDeadlineAlert.service_request_id).where(
        ServiceRequest.id.in_(visible), ServiceRequest.status.not_in((*CLOSED_STATUSES, "draft", "on_hold")),
        CaseDeadlineAlert.resolved_at.is_(None), CaseDeadlineAlert.target_at < now,
        or_((CaseDeadlineAlert.kind == "case_due") & (CaseDeadlineAlert.target_at == ServiceRequest.due_at),
            (CaseDeadlineAlert.kind == "first_response") & ServiceRequest.first_response_at.is_(None)
            & (CaseDeadlineAlert.target_at == ServiceRequest.first_response_due_at)))

def _view(db, alert):
    ticket = db.get(ServiceRequest, alert.service_request_id)
    actor = db.get(User, alert.acknowledged_by_id) if alert.acknowledged_by_id else None
    owner = ticket.active_assignment.agent if ticket.active_assignment else None
    return {"id": str(alert.id), "ticket_number": ticket.ticket_number, "label": LABELS[alert.kind], "kind": alert.kind,
            "target_at": tickets.aware(alert.target_at).isoformat(), "created_at": tickets.aware(alert.created_at).isoformat(),
            "escalated_at": tickets.aware(alert.escalated_at).isoformat() if alert.escalated_at else None,
            "acknowledged_at": tickets.aware(alert.acknowledged_at).isoformat() if alert.acknowledged_at else None,
            "acknowledged_by": {"name": actor.display_name, "id": str(actor.id)} if actor else None,
            "owner": {"name": owner.display_name, "id": str(owner.id)} if owner else None}


@router.get("")
def list_alerts(include_acknowledged: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                user: User = Depends(current_staff), db: Session = Depends(get_db)):
    query = _query(user, utcnow())
    pending = query.where(CaseDeadlineAlert.acknowledged_at.is_(None))
    count = db.scalar(select(func.count()).select_from(pending.subquery()))
    escalated = db.scalar(select(func.count()).select_from(pending.where(CaseDeadlineAlert.escalated_at.is_not(None)).subquery()))
    if not include_acknowledged:
        query = pending
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(CaseDeadlineAlert.escalated_at.is_(None), CaseDeadlineAlert.target_at, CaseDeadlineAlert.id)
        .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_view(db, a) for a in rows], "total": total, "unacknowledged": count, "escalated": escalated,
            "page": page, "page_size": page_size, "check_interval_seconds": config.NOTIFY_INTERVAL_SECONDS}


@router.post("/{id}/acknowledge")
def acknowledge(id: uuid.UUID, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    alert = db.get(CaseDeadlineAlert, id)
    if alert is None:
        raise HTTPException(404, "Deadline alert not found.")
    ticket = db.get(ServiceRequest, alert.service_request_id)
    _get_ticket(db, user, ticket.ticket_number, lock=True)
    db.refresh(alert, with_for_update=True)
    if not active(alert, ticket, utcnow()):
        raise HTTPException(409, "This alert is no longer active. Refresh the alerts list.")
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by_id = utcnow(), user.id
        _cancel(db, alert.id)
        tickets.audit(db, user, "case.deadline_acknowledged", ticket.id, alert_id=str(alert.id), kind=alert.kind)
        db.commit()
    return _view(db, alert)


if __name__ == "__main__":
    from .db import SessionLocal
    with SessionLocal() as session:
        reconcile(session)
