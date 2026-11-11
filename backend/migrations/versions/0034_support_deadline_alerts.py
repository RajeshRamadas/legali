"""Persistent private support response alerts, preserving incident history on rollback."""
from alembic import op
import sqlalchemy as sa

revision = "0034_support_deadline_alerts"
down_revision = "0033_support_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("support_deadline_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("support_request_id", sa.Uuid(), sa.ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("support_request_id", "target_at", name="uq_support_deadline_target"),
        sa.CheckConstraint("revision >= 1", name="ck_support_deadline_revision"))
    op.create_index("ix_support_deadline_active", "support_deadline_alerts", ["resolved_at", "acknowledged_at", "target_at"])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE support_deadline_alerts IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM support_deadline_alerts")).scalar():
        raise RuntimeError("Cannot remove retained support deadline alerts. Use reviewed recovery or a forward fix.")
    op.drop_index("ix_support_deadline_active", table_name="support_deadline_alerts")
    op.drop_table("support_deadline_alerts")
