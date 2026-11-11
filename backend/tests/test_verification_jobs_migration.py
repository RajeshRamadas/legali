import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_empty_roundtrip_preserves_legacy_run_and_used_jobs_block_downgrade():
    engine=sa.create_engine("sqlite://");meta=sa.MetaData()
    for name in ("service_requests","users"):sa.Table(name,meta,sa.Column("id",sa.Uuid,primary_key=True))
    runs=sa.Table("verification_runs",meta,sa.Column("id",sa.Uuid,primary_key=True),sa.Column("result",sa.JSON))
    meta.create_all(engine)
    spec=importlib.util.spec_from_file_location("verification_jobs_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0041_verification_jobs.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        db.execute(runs.insert().values(id=uuid.uuid4(),result={"legacy":"Retained analysis evidence"}))
        migration.upgrade();migration.downgrade();migration.upgrade()
        assert db.scalar(sa.select(runs.c.result))=={"legacy":"Retained analysis evidence"}
        table=sa.Table("verification_jobs",sa.MetaData(),autoload_with=db);case=uuid.uuid4().hex
        values={"id":uuid.uuid4().hex,"service_request_id":case,"submission_key":uuid.uuid4().hex,"request":{"state":"Karnataka"},
            "input_fingerprint":"a"*64,"configuration_revision":"b"*64,"status":"queued","phase":"queued","created_at":datetime(2026,11,11)}
        db.execute(table.insert().values(**values))
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(table.insert().values(**{**values,"id":uuid.uuid4().hex,"submission_key":uuid.uuid4().hex}))
        with pytest.raises(RuntimeError,match="retained verification jobs"):migration.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(table))==1
    engine.dispose()
