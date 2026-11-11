import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_no_legacy_grant_empty_roundtrip_and_retained_choice_blocks_downgrade():
    engine=sa.create_engine("sqlite://");metadata=sa.MetaData()
    for name in ("service_requests","customer_accounts"):sa.Table(name,metadata,sa.Column("id",sa.Uuid,primary_key=True))
    jobs=sa.Table("verification_jobs",metadata,sa.Column("id",sa.Uuid,primary_key=True))
    metadata.create_all(engine)
    spec=importlib.util.spec_from_file_location("case_ai_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0043_case_ai_consent.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        db.execute(jobs.insert().values(id=uuid.uuid4()))
        migration.upgrade()
        assert db.scalar(sa.text("SELECT count(*) FROM case_ai_consents"))==0
        assert db.scalar(sa.text("SELECT consent_revision FROM verification_jobs")) is None
        migration.downgrade();migration.upgrade()
        table=sa.Table("case_ai_consents",sa.MetaData(),autoload_with=db)
        db.execute(table.insert().values(service_request_id=uuid.uuid4().hex,allowed=False,revision=1,notice_snapshot={"retained":"Synthetic choice"},changed_at=datetime(2026,11,12)))
        with pytest.raises(RuntimeError,match="retained AI processing choices"):migration.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(table))==1
    engine.dispose()
