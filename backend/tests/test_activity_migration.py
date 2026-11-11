import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_activity_index_roundtrip_preserves_retained_payloads():
    engine = sa.create_engine("sqlite://")
    table = sa.Table("audit_logs", sa.MetaData(), sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("metadata", sa.JSON))
    table.create(engine)
    spec = importlib.util.spec_from_file_location("activity_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0039_activity_history_index.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(table.insert().values(id=uuid.uuid4(), metadata={"reason": "Retained private reason"}))
        for _ in range(2):
            migration.upgrade()
            index = next(item for item in sa.inspect(db).get_indexes("audit_logs") if item["name"] == "ix_audit_logs_created_id")
            assert index["column_names"] == ["created_at", "id"]
            migration.downgrade()
            assert "ix_audit_logs_created_id" not in {item["name"] for item in sa.inspect(db).get_indexes("audit_logs")}
        assert db.scalar(sa.select(table.c.metadata)) == {"reason": "Retained private reason"}
    engine.dispose()
