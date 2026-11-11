import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import audit_guard_v1


def test_migration_roundtrip_keeps_existing_data_and_reinstalls_guards():
    engine=sa.create_engine("sqlite://")
    table=sa.Table("audit_logs",sa.MetaData(),sa.Column("id",sa.Integer(),primary_key=True),sa.Column("action",sa.Text()),
        sa.Column("created_at",sa.DateTime()),sa.Column("metadata",sa.JSON()))
    table.create(engine)
    spec=importlib.util.spec_from_file_location("append_audit_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0040_append_only_audit.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        db.execute(table.insert().values(id=1,action="legacy.event",created_at=datetime(2026,11,11),metadata={"private":"Retained legacy payload"}))
        original=db.execute(sa.select(table)).mappings().all()
        for _ in range(2):
            migration.upgrade()
            assert audit_guard_v1.protection(db)=={"state":"configured"}
            for statement in (table.update().values(action="rewrite"),table.delete()):
                with pytest.raises(sa.exc.IntegrityError,match="append-only"),db.begin_nested():db.execute(statement)
            assert db.execute(sa.select(table)).mappings().all()==original
            migration.downgrade()
            assert audit_guard_v1.protection(db)=={"state":"missing"}
            assert db.execute(sa.select(table)).mappings().all()==original
    engine.dispose()
