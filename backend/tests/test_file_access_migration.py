import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import audit_guard_v1


def test_file_access_indexes_preserve_existing_records_and_append_only_guards():
    engine = sa.create_engine("sqlite://")
    table = sa.Table("audit_logs", sa.MetaData(), sa.Column("id", sa.Integer(), primary_key=True), sa.Column("action", sa.Text()),
        sa.Column("entity_type", sa.Text()), sa.Column("entity_id", sa.Text()), sa.Column("created_at", sa.DateTime()), sa.Column("metadata", sa.JSON()))
    table.create(engine)
    path = Path(__file__).resolve().parents[1]/"migrations/versions/0047_file_access_history_index.py"
    spec = importlib.util.spec_from_file_location("file_access_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(table.insert().values(id=1, action="legacy.event", entity_type="service_request", entity_id="retained-case", created_at=datetime(2026,11,12), metadata={"private":"Retained legacy payload"}))
        audit_guard_v1.install(db)
        original = db.execute(sa.select(table)).mappings().all()
        for _ in range(2):
            migration.upgrade()
            assert {row["name"] for row in sa.inspect(db).get_indexes("audit_logs")} == {"ix_audit_logs_action_created_id","ix_audit_logs_entity_action_created"}
            assert audit_guard_v1.protection(db) == {"state":"configured"}
            with pytest.raises(sa.exc.IntegrityError, match="append-only"), db.begin_nested(): db.execute(table.delete())
            migration.downgrade()
            assert audit_guard_v1.protection(db) == {"state":"configured"}
            assert db.execute(sa.select(table)).mappings().all() == original
    engine.dispose()
