"""Private customer support requests and separate customer/internal message threads."""
from alembic import op
import sqlalchemy as sa

revision = "0024_customer_support"
down_revision = "0023_privacy_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("support_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("customer_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="SET NULL")),
        sa.Column("submission_key", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False), sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reply_due_at", sa.DateTime(timezone=True)), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('case_update','documents','payment','complaint','other')", name="ck_support_kind"),
        sa.CheckConstraint("status IN ('open','in_progress','waiting_for_customer','resolved')", name="ck_support_status"),
        sa.CheckConstraint("revision >= 1", name="ck_support_revision"),
        sa.UniqueConstraint("account_id", "submission_key", name="uq_support_submission"))
    op.create_index("ix_support_account_created", "support_requests", ["account_id", "created_at"])
    op.create_index("ix_support_queue", "support_requests", ["status", "reply_due_at"])
    op.create_table("support_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("support_request_id", sa.Uuid(), sa.ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_key", sa.Uuid(), nullable=False), sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("visibility", sa.Text(), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("author_type IN ('customer','staff')", name="ck_support_message_author"),
        sa.CheckConstraint("visibility IN ('customer','internal')", name="ck_support_message_visibility"),
        sa.CheckConstraint("author_type = 'staff' OR visibility = 'customer'", name="ck_support_customer_visibility"),
        sa.UniqueConstraint("support_request_id", "submission_key", name="uq_support_message_submission"))
    op.create_index("ix_support_message_thread", "support_messages", ["support_request_id", "created_at"])


def downgrade():
    op.drop_table("support_messages")
    op.drop_table("support_requests")
