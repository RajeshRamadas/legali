import json
import uuid
from datetime import timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app import config, retention
from app.db import SessionLocal, engine
from app.models import AuditLog, Consent, Conversation, ConversationMessage, CustomerAccount, ServiceRequest, utcnow
from conftest import authenticate_customer


def old_chat(db, **fields):
    old = utcnow() - timedelta(days=200)
    item = Conversation(created_at=old, updated_at=old, **fields)
    db.add(item); db.flush()
    db.add(ConversationMessage(conversation_id=item.id, sender_type="customer", body="PRIVATE OLD CONTENT", created_at=old))
    return item


def test_preview_and_disabled_policy_never_delete_and_logs_are_count_only(monkeypatch, capsys):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", False)
    with SessionLocal() as db:
        item = old_chat(db); db.commit(); identifier = item.id
    assert retention.main(["cleanup"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["eligible"] == 1 and "PRIVATE" not in output.out and str(identifier) not in output.out
    assert retention.main(["cleanup", "--apply"]) == 1
    assert "disabled" in capsys.readouterr().err
    with SessionLocal() as db:
        assert db.get(Conversation, identifier) is not None
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1


def test_only_expired_unlinked_anonymous_chats_are_removed(client, raise_ticket, monkeypatch):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", True)
    number = raise_ticket()
    with SessionLocal() as db:
        account = db.scalar(select(CustomerAccount))
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        removable = old_chat(db)
        linked_case = old_chat(db); ticket.conversation_id = linked_case.id
        customer_linked = old_chat(db, customer_id=ticket.customer_id)
        account_linked = old_chat(db, account_id=account.id)
        held = old_chat(db, retention_hold=True)
        metadata = old_chat(db, intake_data={"property": "private intake"})
        submitted = old_chat(db, state="submitted")
        consent = old_chat(db)
        db.add(Consent(conversation_id=consent.id, purpose="test", notice_version="v1", consented=False, source="test"))
        recent_message = old_chat(db)
        db.add(ConversationMessage(conversation_id=recent_message.id, sender_type="assistant", body="recent", created_at=utcnow()))
        recent_parent = old_chat(db); recent_parent.updated_at = utcnow()
        preserved = [row.id for row in (linked_case, customer_linked, account_linked, held, metadata, submitted, consent, recent_message, recent_parent)]
        db.commit(); removed_id = removable.id
    result = retention.cleanup(apply=True)
    assert result["removed"] == 1 and result["eligible"] == 1
    with SessionLocal() as db:
        assert db.get(Conversation, removed_id) is None
        assert db.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == removed_id)) == 0
        assert all(db.get(Conversation, identifier) is not None for identifier in preserved)
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 1
        assert db.scalar(select(func.count()).select_from(Consent)) == 1


def test_cleanup_is_bounded_idempotent_and_audited(monkeypatch):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", True)
    with SessionLocal() as db:
        old_chat(db); old_chat(db); db.commit()
    assert retention.cleanup(apply=True, batch_size=1)["more_eligible"]
    assert retention.cleanup(apply=True, batch_size=1)["removed"] == 1
    assert retention.cleanup(apply=True)["removed"] == 0
    with SessionLocal() as db:
        records = db.scalars(select(AuditLog).where(AuditLog.action == "retention.chats_cleaned")).all()
        assert len(records) == 2 and "PRIVATE" not in str([row.metadata_ for row in records])


def test_hold_release_preserves_activity_time_and_case_exclusions(monkeypatch):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", True)
    with SessionLocal() as db:
        item = old_chat(db); db.commit(); identifier, old = item.id, item.updated_at
    assert retention.set_hold(identifier, True, "privacy_review") == {"held": True}
    assert retention.cleanup(apply=True)["removed"] == 0
    assert retention.set_hold(identifier, False, "manual_review") == {"held": False}
    with SessionLocal() as db:
        assert db.get(Conversation, identifier).updated_at.replace(tzinfo=timezone.utc) == old.replace(tzinfo=timezone.utc)
    assert retention.cleanup(apply=True)["removed"] == 1


def test_failed_cleanup_rolls_back_parent_and_message_deletion(monkeypatch):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", True)
    with SessionLocal() as db:
        item = old_chat(db); db.commit(); identifier = item.id
    def fail(**kwargs):
        raise OperationalError("PRIVATE SQL", {}, Exception("PRIVATE DETAILS"))
    monkeypatch.setattr(retention, "AuditLog", fail)
    with pytest.raises(OperationalError):
        retention.cleanup(apply=True)
    with SessionLocal() as db:
        assert db.get(Conversation, identifier) is not None
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1


def test_invalid_limits_and_unknown_hold_are_rejected():
    with pytest.raises(retention.RetentionError): retention.cleanup(batch_size=501)
    with pytest.raises(retention.RetentionError): retention.set_hold(uuid.uuid4(), True, "privacy_review")


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Skip-locked cleanup requires PostgreSQL")
def test_cleanup_skips_locked_active_chat_and_rechecks_activity(monkeypatch):
    monkeypatch.setattr(config, "CHAT_RETENTION_ENABLED", True)
    with SessionLocal() as db:
        item = old_chat(db); db.commit(); identifier = item.id
    with SessionLocal() as writer:
        item = writer.scalar(select(Conversation).where(Conversation.id == identifier).with_for_update())
        assert retention.cleanup(apply=True)["removed"] == 0
        item.updated_at = utcnow()
        writer.add(ConversationMessage(conversation_id=identifier, sender_type="customer", body="active conversation"))
        writer.commit()
    assert retention.cleanup(apply=True)["removed"] == 0
