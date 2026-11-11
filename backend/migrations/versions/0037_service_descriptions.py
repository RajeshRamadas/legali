"""Keep reviewed public description overrides independent of reference data."""
from alembic import op
import sqlalchemy as sa

revision = "0037_service_descriptions"
down_revision = "0036_support_deadline_email"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("service_types") as batch:
        batch.add_column(sa.Column("description_override", sa.Text()))
        batch.add_column(sa.Column("description_revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_service_description_revision", "description_revision >= 1")
        batch.create_check_constraint("ck_service_description_length", "description_override IS NULL OR length(description_override) BETWEEN 10 AND 800")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE service_types IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM service_types WHERE description_override IS NOT NULL OR description_revision > 1")).scalar() or bind.execute(sa.text("SELECT count(*) FROM audit_logs WHERE action = 'service.description_changed'")).scalar():
        raise RuntimeError("Cannot remove reviewed service descriptions or their publication history. Use a forward fix or reviewed recovery.")
    with op.batch_alter_table("service_types") as batch:
        batch.drop_constraint("ck_service_description_length", type_="check")
        batch.drop_constraint("ck_service_description_revision", type_="check")
        batch.drop_column("description_revision")
        batch.drop_column("description_override")
