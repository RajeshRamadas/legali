"""Private, revisioned customer intake drafts with explicit saving consent."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_guided_intake"
down_revision = "0018_staff_account_security"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("intake_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("saving_notice_version", sa.Text(), nullable=False),
        sa.Column("saving_consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="SET NULL"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'submitted', 'discarded')", name="ck_intake_drafts_status"))
    op.create_index("idx_intake_drafts_account_created", "intake_drafts", ["account_id", "created_at"])


def downgrade():
    op.drop_table("intake_drafts")
