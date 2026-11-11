import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def schema():
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    services = sa.Table("service_types", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("description", sa.Text()), sa.Column("intake_paused", sa.Boolean()))
    cases = sa.Table("service_requests", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("service_type_id", sa.Integer(), sa.ForeignKey("service_types.id")))
    sa.Table("audit_logs", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("action", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("description_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0037_service_descriptions.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(services.insert().values(id=1, description="Retained standard description", intake_paused=True))
        db.execute(cases.insert().values(id=1, service_type_id=1))
        yield db, migration
    engine.dispose()


def test_roundtrip_preserves_copy_pause_and_existing_case(schema):
    db, migration = schema; migration.upgrade()
    assert db.execute(sa.text("SELECT description_override, description_revision FROM service_types")).one() == (None,1)
    migration.downgrade(); migration.upgrade()
    assert db.execute(sa.text("SELECT description,intake_paused,description_revision FROM service_types")).one() == ("Retained standard description",1,1)
    assert db.execute(sa.text("SELECT service_type_id FROM service_requests")).scalar_one() == 1
    for values in ("description_revision=0", "description_override='short'"):
        with pytest.raises(sa.exc.IntegrityError), db.begin_nested(): db.execute(sa.text("UPDATE service_types SET "+values))


@pytest.mark.parametrize("state", ["custom", "reset", "audit"])
def test_rollback_refuses_any_retained_publication_including_reset_history(schema, state):
    db, migration = schema; migration.upgrade()
    if state == "custom": db.execute(sa.text("UPDATE service_types SET description_override='Retained public description',description_revision=2"))
    elif state == "reset": db.execute(sa.text("UPDATE service_types SET description_revision=3"))
    else: db.execute(sa.text("INSERT INTO audit_logs (id,action) VALUES (1,'service.description_changed')"))
    with pytest.raises(RuntimeError, match="reviewed service descriptions"): migration.downgrade()
    assert db.execute(sa.text("SELECT count(*) FROM service_requests")).scalar_one() == 1
