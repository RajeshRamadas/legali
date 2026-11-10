"""Track verified refund amounts without treating partial or historical refunds as fully returned."""
from alembic import op
import sqlalchemy as sa

revision = "0026_refund_tracking"
down_revision = "0025_site_policies"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payments", sa.Column("refunded_paise", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("refund_pending_paise", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("refund_review_reason", sa.Text()))
    op.execute("UPDATE payments SET refund_review_reason = 'legacy_unverified' WHERE status = 'refunded'")
    with op.batch_alter_table("payments") as batch:
        batch.create_check_constraint("ck_payment_refund_amounts", "refunded_paise >= 0 AND refunded_paise <= amount_paise AND refund_pending_paise >= 0")
    op.create_table("refunds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("provider_refund_id", sa.Text(), nullable=False), sa.Column("provider_payment_id", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False), sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("review_code", sa.Text()),
        sa.Column("internal_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_refund_id", name="uq_refund_provider_id"),
        sa.CheckConstraint("status IN ('pending','processed','failed')", name="ck_refund_status"),
        sa.CheckConstraint("amount_paise > 0 AND revision >= 1", name="ck_refund_values"))
    op.create_index("ix_refund_provider_payment", "refunds", ["provider_payment_id"])
    op.create_index("ix_refund_payment_status", "refunds", ["payment_id", "status"])


def downgrade():
    op.drop_table("refunds")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("ck_payment_refund_amounts", type_="check")
        batch.drop_column("refund_review_reason")
        batch.drop_column("refund_pending_paise")
        batch.drop_column("refunded_paise")
