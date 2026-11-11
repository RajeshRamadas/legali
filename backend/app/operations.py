"""Readiness and administrator-only operational snapshots; no provider calls or mutations."""
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, create_engine, func, inspect, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from starlette.responses import JSONResponse

from . import audit_guard_v1, config, notification_providers, whatsapp, support_alerts
from .db import engine, get_db
from .models import CaseDeadlineAlert, CaseScanRun, Document, Notification, SupportRequest, User, VerificationJob, WorkerPulse, utcnow
from .security import require_admin

router = APIRouter()


@lru_cache
def expected_revisions():
    return set(ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations")).get_heads())


def schema_matches(connection):
    return inspect(connection).has_table("alembic_version") and set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()) == expected_revisions()


@lru_cache
def probe_engine():
    if engine.dialect.name != "postgresql":
        return engine
    # Health probes do not wait for the application's saturated pool or hold pooled connections.
    return create_engine(engine.url, poolclass=NullPool, hide_parameters=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=2000"})


@router.get("/ready", include_in_schema=False)
def ready():
    try:
        with probe_engine().connect() as connection:
            good = schema_matches(connection) and audit_guard_v1.protection(connection)["state"] == "configured"
    except SQLAlchemyError:
        good = False
    return JSONResponse({"status": "ready" if good else "not_ready"}, status_code=200 if good else 503,
        headers={"Cache-Control": "no-store"})


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def iso(value):
    return aware(value).isoformat() if value is not None else None


def worker_view(row, name, enabled, interval, now):
    threshold = max(300, interval * 3)
    if row is None:
        state = "not_observed" if name == "notifications" or enabled else "disabled"
    elif not row.started_at and not row.finished_at:
        state = "not_observed" if name == "notifications" or enabled else "disabled"
    elif aware(row.started_at or row.finished_at) > now + timedelta(seconds=60):
        state = "stale"
    elif not enabled and name == "blog_scan" and aware(row.started_at or row.finished_at) < now - timedelta(seconds=threshold):
        state = "disabled"
    elif row.finished_at and aware(row.finished_at) >= now - timedelta(seconds=threshold):
        state = "failed" if row.error_code else "healthy"
    elif row.started_at and aware(row.started_at) >= now - timedelta(seconds=threshold):
        state = "starting"
    else:
        state = "stale"
    return {"name": name, "state": state, "enabled_in_api": enabled, "stale_after_seconds": threshold,
        "started_at": iso(row.started_at) if row else None, "finished_at": iso(row.finished_at) if row else None,
        "last_success_at": iso(row.last_success_at) if row else None, "last_failure_at": iso(row.last_failure_at) if row else None,
        "duration_ms": row.duration_ms if row else None, "consecutive_failures": row.consecutive_failures if row else 0,
        "error_code": row.error_code if row else None}


@router.get("/api/v1/admin/operations")
def snapshot(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not schema_matches(db.connection()):
        raise HTTPException(503, "Apply the current database migrations before checking system health.")
    now = utcnow()
    audit_history = audit_guard_v1.protection(db.connection())
    since = now - timedelta(hours=24)
    old = now - timedelta(minutes=config.OPS_QUEUE_WARN_MINUTES)
    workers = [worker_view(db.get(WorkerPulse, name), name, enabled, interval, now) for name, enabled, interval in (
        ("notifications", config.NOTIFY_WORKER_ENABLED, config.NOTIFY_INTERVAL_SECONDS),
        ("blog_scan", config.BLOG_AGENT_ENABLED, 900),
    )]
    job_counts=dict(db.execute(select(VerificationJob.status,func.count()).group_by(VerificationJob.status)).all())
    interrupted=db.scalar(select(func.count()).select_from(VerificationJob).where(VerificationJob.status=="running",(VerificationJob.lease_until.is_(None))|(VerificationJob.lease_until<=now)))
    verification_jobs={"queued":job_counts.get("queued",0),"running":job_counts.get("running",0),"interrupted":interrupted,
        "failed_24h":db.scalar(select(func.count()).select_from(VerificationJob).where(VerificationJob.status=="failed",VerificationJob.finished_at>=since))}
    pulse=db.get(WorkerPulse,"verification")
    if pulse or verification_jobs["queued"] or verification_jobs["running"]:
        verification_worker=worker_view(pulse,"verification",True,10,now)
        verification_worker["enabled_in_api"]=False
        workers.append(verification_worker)
    due_at = func.coalesce(Notification.send_after, Notification.created_at)
    queued = Notification.delivery_status == "queued"
    due = queued & (due_at <= now)
    failed = (Notification.delivery_status == "failed") & (func.coalesce(Notification.last_attempt_at, Notification.created_at) >= since)
    counts = {row.channel: row for row in db.execute(select(Notification.channel,
        func.sum(case((due, 1), else_=0)).label("due"),
        func.sum(case((queued & (due_at > now), 1), else_=0)).label("scheduled"),
        func.sum(case((due & (due_at < old), 1), else_=0)).label("delayed"),
        func.sum(case((failed, 1), else_=0)).label("failed"),
        func.min(case((due, due_at), else_=None)).label("oldest_due_at"))
        .where(Notification.channel.in_(("email", "sms", "whatsapp")), or_(queued, failed)).group_by(Notification.channel))}
    channels = []
    for name in ("email", "sms", "whatsapp"):
        row = counts.get(name)
        channels.append({"name": name, "configured": whatsapp.enabled() if name == "whatsapp" else notification_providers.enabled(name),
            "due": int(row.due) if row else 0, "scheduled": int(row.scheduled) if row else 0,
            "delayed": int(row.delayed) if row else 0, "failed_24h": int(row.failed) if row else 0,
            "oldest_due_at": iso(row.oldest_due_at) if row else None})
    document_counts = dict(db.execute(select(Document.scan_status, func.count()).group_by(Document.scan_status)).all())
    documents = {name: document_counts.get(name, 0) for name in ("pending", "failed", "infected")}
    documents["delayed"] = db.scalar(select(func.count()).select_from(Document).where(Document.scan_status == "pending", Document.created_at < old))
    open_alerts = [CaseDeadlineAlert.resolved_at.is_(None), CaseDeadlineAlert.acknowledged_at.is_(None)]
    deadlines = {"unacknowledged": db.scalar(select(func.count()).select_from(CaseDeadlineAlert).where(*open_alerts)),
        "escalated": db.scalar(select(func.count()).select_from(CaseDeadlineAlert).where(*open_alerts, CaseDeadlineAlert.escalated_at.is_not(None)))}
    research = {"failed_24h": db.scalar(select(func.count()).select_from(CaseScanRun).where(CaseScanRun.status == "failed", CaseScanRun.started_at >= since))}
    support = {"overdue_requests": db.scalar(select(func.count()).select_from(SupportRequest).where(SupportRequest.status != "resolved", SupportRequest.reply_due_at < now)),
        **support_alerts.counts(db, now)}
    attention = audit_history["state"] != "configured" or any(worker["state"] not in ("healthy", "disabled") for worker in workers) or any(
        row["delayed"] or row["failed_24h"] or (row["due"] and not row["configured"]) for row in channels)
    attention = attention or any(documents[name] for name in ("delayed", "failed", "infected")) or deadlines["unacknowledged"] or research["failed_24h"] or support["overdue_requests"]
    attention = attention or bool(verification_jobs["interrupted"] or verification_jobs["failed_24h"])
    return {"checked_at": now.isoformat(), "status": "attention" if attention else "healthy", "database": "ready",
        "queue_warn_minutes": config.OPS_QUEUE_WARN_MINUTES, "workers": workers, "channels": channels,
        "documents": documents, "deadlines": deadlines, "research": research, "support": support, "audit_history": audit_history,"verification_jobs":verification_jobs}
