"""Pause case clocks and persist deduplicated deadline escalations."""
from alembic import op
import sqlalchemy as sa

revision = "0020_case_deadline_alerts"
down_revision = "0019_guided_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("service_requests", sa.Column("deadline_paused_at", sa.DateTime(timezone=True)))
    op.add_column("service_requests", sa.Column("deadline_pause_seconds", sa.BigInteger(), server_default=sa.text("0"), nullable=False))
    # Existing holds start pausing at deployment; do not guess historical elapsed time.
    op.execute("UPDATE service_requests SET deadline_paused_at = CURRENT_TIMESTAMP WHERE status = 'on_hold'")
    op.create_table("case_deadline_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("service_request_id", "kind", "target_at", name="uq_case_deadline_alert_target"),
        sa.CheckConstraint("kind IN ('case_due', 'first_response')", name="ck_case_deadline_alert_kind"))
    op.create_index("idx_case_deadline_alert_open", "case_deadline_alerts", ["resolved_at", "created_at"])
    op.add_column("notifications", sa.Column("case_alert_id", sa.Uuid(), sa.ForeignKey("case_deadline_alerts.id", ondelete="SET NULL", name="fk_notifications_case_alert")))
    op.create_index("ix_notifications_case_alert_id", "notifications", ["case_alert_id"])


def downgrade():
    op.drop_index("ix_notifications_case_alert_id", table_name="notifications")
    op.drop_constraint("fk_notifications_case_alert", "notifications", type_="foreignkey")
    op.drop_column("notifications", "case_alert_id")
    op.drop_table("case_deadline_alerts")
    op.drop_column("service_requests", "deadline_pause_seconds")
    op.drop_column("service_requests", "deadline_paused_at")
