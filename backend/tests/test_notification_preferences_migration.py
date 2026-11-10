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
    accounts = sa.Table("customer_accounts", metadata, sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("phone_normalized", sa.Text()))
    notifications = sa.Table("notifications", metadata, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("body", sa.Text()), sa.Column("delivery_status", sa.Text()))
    metadata.create_all(engine)
    import uuid
    identifier = uuid.uuid4()
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0029_notification_preferences.py"
    spec = importlib.util.spec_from_file_location("preferences_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(accounts.insert().values(id=identifier, phone_normalized="9999900001"))
        connection.execute(notifications.insert().values(id=1, body="Retained notification", delivery_status="cancelled"))
        with Operations.context(MigrationContext.configure(connection)):
            yield connection, migration, identifier
    engine.dispose()


def test_upgrade_and_permitted_rollback_preserve_accounts_and_notifications(schema):
    connection, migration, identifier = schema
    migration.upgrade()
    prefs = sa.Table("customer_notification_preferences", sa.MetaData(), autoload_with=connection)
    assert connection.execute(sa.select(sa.func.count()).select_from(prefs)).scalar_one() == 0
    from datetime import datetime, timezone
    connection.execute(prefs.insert().values(account_id=identifier.hex, email=True, sms=True, whatsapp=True, revision=1, updated_at=datetime.now(timezone.utc)))
    migration.downgrade()
    migration.upgrade()
    assert connection.execute(sa.text("SELECT phone_normalized FROM customer_accounts")).scalar_one() == "9999900001"
    assert connection.execute(sa.text("SELECT body, delivery_status FROM notifications")).one() == ("Retained notification", "cancelled")


@pytest.mark.parametrize("channel", ["email", "sms", "whatsapp"])
def test_rollback_refuses_to_discard_a_disabled_channel(schema, channel):
    connection, migration, identifier = schema
    migration.upgrade()
    from datetime import datetime, timezone
    prefs = sa.Table("customer_notification_preferences", sa.MetaData(), autoload_with=connection)
    connection.execute(prefs.insert().values(account_id=identifier.hex, email=True, sms=True, whatsapp=True, revision=1, updated_at=datetime.now(timezone.utc)))
    connection.execute(prefs.update().values(**{channel: False}))
    with pytest.raises(RuntimeError, match="customer has disabled a channel"):
        migration.downgrade()
    assert connection.execute(sa.select(prefs.c[channel])).scalar_one() is False
    assert connection.execute(sa.text("SELECT delivery_status FROM notifications")).scalar_one() == "cancelled"
