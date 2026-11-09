"""Shared worker observations for administrator operational monitoring."""
from alembic import op
import sqlalchemy as sa

revision = "0022_operations_monitoring"
down_revision = "0021_api_abuse_protection"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("worker_pulses",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_code", sa.Text()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_table("worker_pulses")
