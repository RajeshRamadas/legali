import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migration_preserves_messages_and_guards_unread_receipts():
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    requests = sa.Table("support_requests", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("subject", sa.Text()))
    messages = sa.Table("support_messages", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("support_request_id", sa.Integer(), sa.ForeignKey("support_requests.id")), sa.Column("body", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("unread_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0032_support_unread_replies.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        connection.execute(requests.insert().values(id=1, subject="Retained support subject"))
        connection.execute(messages.insert().values(id=1, support_request_id=1, body="Retained old reply"))
        migration.upgrade()
        assert connection.execute(sa.text("SELECT customer_update_revision,customer_read_revision FROM support_requests")).one() == (0,0)
        connection.execute(sa.text("UPDATE support_requests SET customer_update_revision=2,customer_read_revision=1"))
        with pytest.raises(RuntimeError, match="unread support replies"):
            migration.downgrade()
        assert connection.execute(sa.select(messages.c.body)).scalar_one() == "Retained old reply"
        connection.execute(sa.text("UPDATE support_requests SET customer_read_revision=2"))
        migration.downgrade(); migration.upgrade()
        assert connection.execute(sa.select(requests.c.subject)).scalar_one() == "Retained support subject"
        assert connection.execute(sa.select(messages.c.body)).scalar_one() == "Retained old reply"
    engine.dispose()
