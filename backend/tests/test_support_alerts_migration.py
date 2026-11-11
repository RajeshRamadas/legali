import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_alert_migration_preserves_support_and_refuses_loss_of_incident_history():
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    sa.Table("users", meta, sa.Column("id", sa.Uuid(), primary_key=True))
    requests = sa.Table("support_requests", meta, sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("subject", sa.Text()), sa.Column("revision", sa.Integer()))
    messages = sa.Table("support_messages", meta, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("body", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("support_alerts_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0034_support_deadline_alerts.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    id = uuid.uuid4()
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(requests.insert().values(id=id, subject="Retained support record", revision=7))
        db.execute(messages.insert().values(id=1, body="Preserved conversation"))
        migration.upgrade(); migration.downgrade(); migration.upgrade()
        alerts = sa.Table("support_deadline_alerts", sa.MetaData(), autoload_with=db)
        db.execute(alerts.insert().values(id=uuid.uuid4().hex, support_request_id=id.hex, target_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc)))
        with pytest.raises(RuntimeError, match="retained support deadline alerts"):
            migration.downgrade()
        assert db.execute(sa.select(sa.func.count()).select_from(alerts)).scalar_one() == 1
        assert db.execute(sa.select(requests.c.revision)).scalar_one() == 7
        assert db.execute(sa.select(messages.c.body)).scalar_one() == "Preserved conversation"
    engine.dispose()
