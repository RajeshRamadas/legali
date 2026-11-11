import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("status", ["queued", "sent", "cancelled"])
def test_migration_preserves_old_delivery_data_and_guards_all_support_history(status):
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    for name in ("customer_accounts", "support_requests"):
        sa.Table(name, meta, sa.Column("id", sa.Uuid(), primary_key=True))
    old = sa.Table("notifications", meta, sa.Column("id", sa.Uuid(), primary_key=True),
        *[sa.Column(name, sa.Uuid()) for name in ("customer_id", "user_id", "service_request_id", "meeting_id", "case_alert_id")],
        sa.Column("template_key", sa.Text(), nullable=False), sa.Column("delivery_status", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("support_reply_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0035_support_reply_notifications.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    identifier, account, request = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(old.insert().values(id=identifier, template_key="staff_message", delivery_status="sent", body="Preserved legacy message"))
        migration.upgrade(); migration.downgrade(); migration.upgrade()
        table = sa.Table("notifications", sa.MetaData(), autoload_with=db)
        original = db.execute(sa.select(table).where(table.c.id == identifier.hex)).one()
        assert original.body == "Preserved legacy message" and original.delivery_status == "sent" and original.account_id is None
        # Do not allow account-scoped fields to be silently used as case/staff alerts.
        with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
            db.execute(table.insert().values(id=uuid.uuid4().hex, template_key="staff_message", delivery_status="queued", account_id=account.hex))
        db.execute(meta.tables["customer_accounts"].insert().values(id=account))
        db.execute(meta.tables["support_requests"].insert().values(id=request))
        db.execute(table.insert().values(id=uuid.uuid4().hex, template_key="support_reply", delivery_status=status,
            account_id=account.hex, support_request_id=request.hex, support_update_revision=1, body="Generic notice"))
        with pytest.raises(RuntimeError, match="retained support notification history"):
            migration.downgrade()
        assert db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 2
        assert db.execute(sa.select(table.c.body).where(table.c.id == identifier.hex)).scalar_one() == "Preserved legacy message"
    engine.dispose()
