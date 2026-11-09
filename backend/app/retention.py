"""Bounded cleanup of expired anonymous chats. Defaults to a count-only preview."""
import argparse
import json
import sys
import uuid
from datetime import timedelta

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from . import config
from .db import SessionLocal
from .models import AuditLog, Consent, Conversation, ConversationMessage, ServiceRequest, utcnow


class RetentionError(Exception):
    pass


def eligible(cutoff):
    return (
        Conversation.account_id.is_(None), Conversation.customer_id.is_(None), Conversation.property_id.is_(None),
        Conversation.retention_hold.is_(False), Conversation.state != "submitted",
        Conversation.created_at < cutoff, Conversation.updated_at < cutoff,
        Conversation.consented_at.is_(None), Conversation.consent_notice_version.is_(None),
        Conversation.intake_data == {},
        ~exists().where(ServiceRequest.conversation_id == Conversation.id),
        ~exists().where(Consent.conversation_id == Conversation.id),
        ~exists().where(ConversationMessage.conversation_id == Conversation.id, ConversationMessage.created_at >= cutoff),
    )


def cleanup(*, apply=False, batch_size=100, now=None):
    if not 1 <= batch_size <= 500:
        raise RetentionError("Batch size must be between 1 and 500.")
    if apply and not config.CHAT_RETENTION_ENABLED:
        raise RetentionError("Cleanup is disabled. Review the retention policy and enable CHAT_RETENTION_ENABLED before applying it.")
    now = now or utcnow()
    cutoff = now - timedelta(days=config.CHAT_RETENTION_DAYS)
    with SessionLocal() as db:
        criteria = eligible(cutoff)
        count = db.scalar(select(func.count()).select_from(Conversation).where(*criteria))
        removed = 0
        if apply:
            # Every chat append/link and hold operation locks this same parent row.
            ids = list(db.scalars(select(Conversation.id).where(*criteria).order_by(Conversation.updated_at, Conversation.id)
                .limit(batch_size).with_for_update(skip_locked=True)))
            if ids:
                # Explicit child deletion also keeps SQLite fixtures consistent without FK enforcement.
                db.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id.in_(ids)))
                removed = db.execute(delete(Conversation).where(Conversation.id.in_(ids))).rowcount
                db.add(AuditLog(action="retention.chats_cleaned", entity_type="retention_run", entity_id=uuid.uuid4(),
                    metadata_={"removed": removed, "retention_days": config.CHAT_RETENTION_DAYS, "cutoff": cutoff.isoformat()}))
            db.commit()
        return {"dry_run": not apply, "enabled": config.CHAT_RETENTION_ENABLED, "retention_days": config.CHAT_RETENTION_DAYS,
            "eligible": count, "removed": removed, "batch_size": batch_size, "more_eligible": count > removed if apply else count > 0}


def set_hold(conversation_id, held, reason):
    if reason not in ("privacy_review", "legal_obligation", "manual_review"):
        raise RetentionError("Choose a supported hold reason.")
    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
        if conversation is None:
            raise RetentionError("Conversation not found.")
        if conversation.retention_hold != held:
            db.execute(update(Conversation).where(Conversation.id == conversation.id).values(retention_hold=held, updated_at=Conversation.updated_at))
            db.add(AuditLog(action="retention.hold_set" if held else "retention.hold_released", entity_type="conversation", entity_id=conversation.id,
                metadata_={"held": held, "reason": reason}))
            db.commit()
    return {"held": held}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    clean = sub.add_parser("cleanup", help="Preview counts; --apply and enabled policy are both required to delete")
    clean.add_argument("--apply", action="store_true")
    clean.add_argument("--batch-size", type=int, default=100)
    for name in ("hold", "release"):
        command = sub.add_parser(name)
        command.add_argument("conversation_id", type=uuid.UUID)
        command.add_argument("--reason", choices=("privacy_review", "legal_obligation", "manual_review"), required=True)
    args = parser.parse_args(argv if argv is not None else (sys.argv[1:] or ["cleanup"]))
    try:
        result = cleanup(apply=args.apply, batch_size=args.batch_size) if args.command == "cleanup" else set_hold(args.conversation_id, args.command == "hold", args.reason)
        print(json.dumps(result))
        return 0
    except (RetentionError, SQLAlchemyError) as error:
        message = str(error) if isinstance(error, RetentionError) else "Database operation failed; no cleanup was committed."
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
