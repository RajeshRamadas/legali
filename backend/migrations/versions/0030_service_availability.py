"""Retain administrator admission controls independently of seeded service copy."""
from alembic import op
import sqlalchemy as sa

revision = "0030_service_availability"
down_revision = "0029_notification_preferences"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("service_types") as batch:
        batch.add_column(sa.Column("intake_paused", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("availability_revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_service_availability_revision", "availability_revision >= 1")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE service_types IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT COUNT(*) FROM service_types WHERE intake_paused")).scalar_one():
        raise RuntimeError("Cannot remove service availability controls while a service is paused. Preserve admission restrictions and review the rollback procedure.")
    with op.batch_alter_table("service_types") as batch:
        batch.drop_constraint("ck_service_availability_revision", type_="check")
        batch.drop_column("availability_revision")
        batch.drop_column("intake_paused")
