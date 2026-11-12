import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_empty_roundtrip_and_retained_decisions_block_downgrade():
    engine=sa.create_engine("sqlite://");metadata=sa.MetaData()
    for name in ("service_requests","users"):sa.Table(name,metadata,sa.Column("id",sa.Uuid,primary_key=True))
    metadata.create_all(engine)
    spec=importlib.util.spec_from_file_location("preservation_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0044_document_preservation.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        migration.upgrade()
        assert db.scalar(sa.text("SELECT count(*) FROM case_document_holds"))==0
        migration.downgrade();migration.upgrade()
        table=sa.Table("case_document_holds",sa.MetaData(),autoload_with=db)
        values={"service_request_id":uuid.uuid4().hex,"held":False,"revision":2,"reason":"manual_review","note":"Retained release review.","changed_at":datetime(2026,11,12)}
        db.execute(table.insert().values(**values))
        for changes in ({"revision":0},{"reason":"unknown"}):
            with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(table.insert().values(**{**values,"service_request_id":uuid.uuid4().hex,**changes}))
        with pytest.raises(RuntimeError,match="retained document preservation decisions"):migration.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(table))==1
    engine.dispose()
