import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def schema():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    services = sa.Table("service_types", metadata, sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text()), sa.Column("is_active", sa.Boolean(), nullable=False))
    cases = sa.Table("service_requests", metadata, sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_type_id", sa.Integer(), sa.ForeignKey("service_types.id")), sa.Column("title", sa.Text()))
    metadata.create_all(engine)
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0030_service_availability.py"
    spec = importlib.util.spec_from_file_location("availability_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(services.insert(), [{"id":1,"name":"Active fixture","is_active":True},{"id":2,"name":"Retired fixture","is_active":False}])
        connection.execute(cases.insert().values(id=1,service_type_id=1,title="Retained existing case"))
        with Operations.context(MigrationContext.configure(connection)):
            yield connection,migration
    engine.dispose()


def test_round_trip_preserves_retired_services_and_linked_cases(schema):
    connection,migration = schema
    migration.upgrade()
    assert connection.execute(sa.text("SELECT id,is_active,intake_paused,availability_revision FROM service_types ORDER BY id")).all() == [(1,1,0,1),(2,0,0,1)]
    migration.downgrade()
    migration.upgrade()
    assert connection.execute(sa.text("SELECT title,service_type_id FROM service_requests")).one() == ("Retained existing case",1)
    assert connection.execute(sa.text("SELECT is_active FROM service_types WHERE id=2")).scalar_one() == 0


def test_paused_service_blocks_rollback_without_losing_state_or_linked_case(schema):
    connection,migration = schema
    migration.upgrade()
    connection.execute(sa.text("UPDATE service_types SET intake_paused=true,availability_revision=2 WHERE id=1"))
    with pytest.raises(RuntimeError,match="while a service is paused"):
        migration.downgrade()
    assert connection.execute(sa.text("SELECT intake_paused,availability_revision FROM service_types WHERE id=1")).one() == (1,2)
    assert connection.execute(sa.text("SELECT title FROM service_requests")).scalar_one() == "Retained existing case"
