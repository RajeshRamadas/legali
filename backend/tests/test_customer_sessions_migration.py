import importlib.util
import uuid
from datetime import datetime,timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_empty_roundtrip_preserves_accounts_and_refuses_retained_sessions():
    engine=sa.create_engine("sqlite://");meta=sa.MetaData()
    accounts=sa.Table("customer_accounts",meta,sa.Column("id",sa.Uuid,primary_key=True),sa.Column("token_version",sa.Integer))
    meta.create_all(engine)
    spec=importlib.util.spec_from_file_location("customer_sessions_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0045_customer_sessions.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        db.execute(accounts.insert().values(id=uuid.uuid4(),token_version=4));migration.upgrade()
        assert db.scalar(sa.text("SELECT count(*) FROM customer_sessions"))==0
        migration.downgrade();migration.upgrade()
        assert db.scalar(sa.select(accounts.c.token_version))==4
        table=sa.Table("customer_sessions",sa.MetaData(),autoload_with=db);now=datetime(2026,11,12)
        values={"id":uuid.uuid4().hex,"account_id":uuid.uuid4().hex,"token_version":1,"browser":"Synthetic browser","device":"Synthetic device","created_at":now,"last_seen_at":now,"expires_at":now+timedelta(days=1)}
        db.execute(table.insert().values(**values))
        with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(table.insert().values(**{**values,"id":uuid.uuid4().hex,"expires_at":now}))
        with pytest.raises(RuntimeError,match="retained customer session records"):migration.downgrade()
        assert db.scalar(sa.select(sa.func.count()).select_from(table))==1
    engine.dispose()
