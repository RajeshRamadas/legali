"""Evidence-based property verification runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_verification"
down_revision = "0010_customer_accounts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("verification_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False))
    op.create_index("ix_verification_runs_service_request_id", "verification_runs", ["service_request_id"])

def downgrade():
    op.drop_index("ix_verification_runs_service_request_id", "verification_runs")
    op.drop_table("verification_runs")
