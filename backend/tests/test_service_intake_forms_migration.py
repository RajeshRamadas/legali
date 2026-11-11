import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def schema():
    engine=sa.create_engine("sqlite://");meta=sa.MetaData()
    services=sa.Table("service_types",meta,sa.Column("id",sa.Integer(),primary_key=True),sa.Column("description",sa.Text()))
    drafts=sa.Table("intake_drafts",meta,sa.Column("id",sa.Integer(),primary_key=True),sa.Column("answers",sa.JSON()))
    sa.Table("audit_logs",meta,sa.Column("id",sa.Integer(),primary_key=True),sa.Column("action",sa.Text()))
    meta.create_all(engine)
    spec=importlib.util.spec_from_file_location("intake_forms_migration",Path(__file__).resolve().parents[1]/"migrations/versions/0038_service_intake_forms.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as db,Operations.context(MigrationContext.configure(db)):
        db.execute(services.insert().values(id=1,description="Retained service description"))
        db.execute(drafts.insert().values(id=1,answers={"goal":"Retained customer goal"}))
        yield db,migration
    engine.dispose()


def test_roundtrip_preserves_legacy_answers_and_standard_copy(schema):
    db,migration=schema;migration.upgrade()
    services=sa.Table("service_types",sa.MetaData(),autoload_with=db)
    drafts=sa.Table("intake_drafts",sa.MetaData(),autoload_with=db)
    assert db.execute(sa.select(services.c.intake_questions,services.c.intake_form_revision)).one()==([],1)
    assert db.scalar(sa.select(drafts.c.service_form_snapshot))=={}
    migration.downgrade();migration.upgrade()
    assert db.scalar(sa.text("SELECT description FROM service_types"))=="Retained service description"
    assert db.scalar(sa.select(drafts.c.answers))=={"goal":"Retained customer goal"}
    with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(sa.text("UPDATE service_types SET intake_form_revision=0"))


@pytest.mark.parametrize("state",["configured","cleared","snapshot","history"])
def test_downgrade_protects_questions_snapshots_and_retained_history(schema,state):
    db,migration=schema;migration.upgrade()
    services=sa.Table("service_types",sa.MetaData(),autoload_with=db)
    drafts=sa.Table("intake_drafts",sa.MetaData(),autoload_with=db)
    if state=="configured":db.execute(services.update().values(intake_questions=[{"prompt":"Retained question"}]))
    elif state=="cleared":db.execute(services.update().values(intake_form_revision=3))
    elif state=="snapshot":db.execute(drafts.update().values(service_form_snapshot={"revision":2,"questions":[{"prompt":"Pinned question"}]}))
    else:db.execute(sa.text("INSERT INTO audit_logs (id,action) VALUES (1,'service.intake_form_published')"))
    with pytest.raises(RuntimeError,match="Cannot remove published intake questions"):migration.downgrade()
    assert db.scalar(sa.select(drafts.c.answers))=={"goal":"Retained customer goal"}
