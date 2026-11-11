import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.parametrize("status", ["queued", "sent", "cancelled"])
def test_deadline_email_migration_preserves_customer_delivery_and_refuses_staff_history_loss(status):
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    alerts = sa.Table("support_deadline_alerts", meta, sa.Column("id", sa.Uuid(), primary_key=True))
    old = sa.Table("notifications", meta, sa.Column("id", sa.Uuid(), primary_key=True),
        *[sa.Column(name, sa.Uuid()) for name in ("user_id", "customer_id", "account_id", "support_request_id", "service_request_id", "meeting_id", "case_alert_id")],
        sa.Column("support_update_revision", sa.Integer()), sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("template_key", sa.Text(), nullable=False), sa.Column("delivery_status", sa.Text(), nullable=False), sa.Column("body", sa.Text()))
    meta.create_all(engine)
    spec = importlib.util.spec_from_file_location("support_deadline_email_migration", Path(__file__).resolve().parents[1]/"migrations/versions/0036_support_deadline_email.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    id, account, request, alert = (uuid.uuid4() for _ in range(4))
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        db.execute(old.insert().values(id=id, account_id=account, support_request_id=request, support_update_revision=2,
            template_key="support_reply", channel="sms", delivery_status="cancelled", body="Existing customer notice"))
        migration.upgrade(); migration.downgrade(); migration.upgrade()
        table = sa.Table("notifications", sa.MetaData(), autoload_with=db)
        saved = db.execute(sa.select(table).where(table.c.id==id.hex)).one()
        assert saved.account_id==account.hex and saved.support_update_revision==2 and saved.body=="Existing customer notice" and saved.support_alert_id is None
        with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
            db.execute(table.insert().values(id=uuid.uuid4().hex, template_key="support_deadline_email", channel="sms", delivery_status="queued", support_alert_revision=1))
        with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
            db.execute(table.insert().values(id=uuid.uuid4().hex, template_key="support_deadline_email", channel="email", delivery_status="queued", support_alert_revision=1, account_id=account.hex))
        db.execute(alerts.insert().values(id=alert))
        db.execute(table.insert().values(id=uuid.uuid4().hex, template_key="support_deadline_email", channel="email", delivery_status=status, support_alert_id=alert.hex, support_alert_revision=1))
        with pytest.raises(RuntimeError, match="retained support deadline email history"): migration.downgrade()
        assert db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()==2
    engine.dispose()
