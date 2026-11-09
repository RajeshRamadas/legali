"""Privacy request review workflow and explicit conversation retention holds."""
from alembic import op
import sqlalchemy as sa

revision = "0023_privacy_requests"
down_revision = "0022_operations_monitoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("retention_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("conversations", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_conversations_account", "conversations", "customer_accounts", ["account_id"], ["id"], ondelete="SET NULL")
    # Historical general chats did not record authenticated account ownership.
    op.execute("UPDATE conversations SET retention_hold = true WHERE customer_id IS NULL")
    op.create_index("ix_conversations_retention", "conversations", ["retention_hold", "updated_at"])
    op.create_table("privacy_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("customer_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="SET NULL")),
        sa.Column("submission_key", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("notice_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_started_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.Text()), sa.Column("retention_reason", sa.Text()),
        sa.Column("customer_response", sa.Text()), sa.Column("internal_note", sa.Text()),
        sa.Column("reviewed_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('access','correction','deletion')", name="ck_privacy_requests_kind"),
        sa.CheckConstraint("status IN ('submitted','in_review','closed','withdrawn')", name="ck_privacy_requests_status"),
        sa.CheckConstraint("resolution IS NULL OR resolution IN ('fulfilled','partial','declined')", name="ck_privacy_requests_resolution"),
        sa.CheckConstraint("revision >= 1", name="ck_privacy_requests_revision"),
        sa.UniqueConstraint("account_id", "submission_key", name="uq_privacy_requests_submission"))
    op.create_index("uq_privacy_requests_open_kind", "privacy_requests", ["account_id", "kind"], unique=True,
        postgresql_where=sa.text("status IN ('submitted','in_review')"), sqlite_where=sa.text("status IN ('submitted','in_review')"))
    op.create_index("ix_privacy_requests_queue", "privacy_requests", ["status", "due_at"])
    op.create_index("ix_privacy_requests_account_created", "privacy_requests", ["account_id", "created_at"])


def downgrade():
    op.drop_table("privacy_requests")
    op.drop_index("ix_conversations_retention", table_name="conversations")
    op.drop_constraint("fk_conversations_account", "conversations", type_="foreignkey")
    op.drop_column("conversations", "account_id")
    op.drop_column("conversations", "retention_hold")
