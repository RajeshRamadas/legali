import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_time_off_migration_guard_and_round_trip_preserve_staff():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.Text()))
    metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("time_off_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0031_lawyer_time_off.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    person = uuid.uuid4()
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        connection.execute(users.insert().values(id=person, name="Retained staff fixture"))
        migration.upgrade()
        table = sa.Table("lawyer_time_off", sa.MetaData(), autoload_with=connection)
        now = datetime.now(timezone.utc)
        connection.execute(table.insert().values(id=uuid.uuid4().hex, lawyer_user_id=person.hex, submission_key=uuid.uuid4().hex,
            starts_at=now+timedelta(days=1), ends_at=now+timedelta(days=2), reason="Retained absence fixture", created_at=now))
        with pytest.raises(RuntimeError, match="upcoming time off"):
            migration.downgrade()
        assert connection.execute(sa.select(table.c.reason)).scalar_one() == "Retained absence fixture"
        connection.execute(table.update().values(cancelled_at=now))
        migration.downgrade(); migration.upgrade()
        assert connection.execute(sa.select(users.c.name)).scalar_one() == "Retained staff fixture"
        assert connection.execute(sa.text("SELECT count(*) FROM lawyer_time_off")).scalar_one() == 0
    engine.dispose()
