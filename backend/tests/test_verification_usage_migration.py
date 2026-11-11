import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_empty_roundtrip_and_used_history_blocks_downgrade():
    engine=sa.create_engine("sqlite://")
    spec=importlib.util.spec_from_file_location("usage_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0042_verification_usage.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        migration.upgrade();migration.downgrade();migration.upgrade()
        table=sa.Table("verification_usage",sa.MetaData(),autoload_with=db)
        assert not sa.inspect(db).get_foreign_keys("verification_usage")
        values={"id":uuid.uuid4().hex,"service_request_id":uuid.uuid4().hex,"job_id":uuid.uuid4().hex,"provider":"anthropic",
            "model":"fixture-model","step":"extract","status":"started","started_at":datetime(2026,11,11),"usage_complete":False,"estimate_reason":"attempt_unfinished"}
        db.execute(table.insert().values(**values))
        for changes in ({"status":"bad"},{"input_tokens":-1},{"output_tokens":1000000001},{"duration_ms":-1},{"estimated_usd":-1},{"input_rate":-1}):
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(table.insert().values(**{**values,"id":uuid.uuid4().hex,**changes}))
        with pytest.raises(RuntimeError,match="retained provider usage"):migration.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(table))==1
    engine.dispose()
