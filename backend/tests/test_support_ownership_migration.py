import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_owner_migration_preserves_support_and_guards_assigned_work():
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    users = sa.Table("users", meta, sa.Column("id", sa.Integer(), primary_key=True))
    requests = sa.Table("support_requests", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("subject", sa.Text()), sa.Column("status", sa.Text()), sa.Column("reply_due_at", sa.DateTime()))
    messages = sa.Table("support_messages", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("support_request_id", sa.Integer(), sa.ForeignKey("support_requests.id")), sa.Column("body", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("owner_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0033_support_ownership.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(users.insert().values(id=1))
        db.execute(requests.insert().values(id=1, subject="Retained support", status="open"))
        db.execute(messages.insert().values(id=1, support_request_id=1, body="Retained visible reply"))
        migration.upgrade()
        assert db.execute(sa.text("SELECT assignee_user_id FROM support_requests")).scalar_one() is None
        db.execute(sa.text("UPDATE support_requests SET assignee_user_id=1"))
        with pytest.raises(RuntimeError, match="assigned requests remain"):
            migration.downgrade()
        db.execute(sa.text("UPDATE support_requests SET assignee_user_id=NULL"))
        migration.downgrade(); migration.upgrade()
        assert db.execute(sa.select(messages.c.body)).scalar_one() == "Retained visible reply"
        assert db.execute(sa.select(requests.c.subject)).scalar_one() == "Retained support"
    engine.dispose()
