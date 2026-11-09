"""Atomic request budgets shared by API workers; identities are keyed hashes."""
from alembic import op
import sqlalchemy as sa

revision = "0021_api_abuse_protection"
down_revision = "0020_case_deadline_alerts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("api_rate_buckets",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False))
    op.create_index("ix_api_rate_buckets_window_start", "api_rate_buckets", ["window_start"])


def downgrade():
    op.drop_table("api_rate_buckets")
