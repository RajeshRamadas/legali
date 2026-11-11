"""Retain revisioned administrator support deadline email history."""
from alembic import op
import sqlalchemy as sa

revision = "0036_support_deadline_email"
down_revision = "0035_support_reply_notifications"
branch_labels = depends_on = None

SCOPE = "(template_key = 'support_deadline_email' AND channel = 'email' AND support_alert_revision IS NOT NULL AND support_alert_revision >= 1 AND customer_id IS NULL AND account_id IS NULL AND support_request_id IS NULL AND support_update_revision IS NULL AND service_request_id IS NULL AND meeting_id IS NULL AND case_alert_id IS NULL) OR (template_key <> 'support_deadline_email' AND support_alert_id IS NULL AND support_alert_revision IS NULL)"


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("support_alert_id", sa.Uuid()))
        batch.add_column(sa.Column("support_alert_revision", sa.Integer()))
        batch.create_foreign_key("fk_notifications_support_alert", "support_deadline_alerts", ["support_alert_id"], ["id"], ondelete="SET NULL")
        batch.create_check_constraint("ck_notifications_support_alert_scope", SCOPE)
        batch.create_index("idx_notifications_support_alert", ["support_alert_id", "delivery_status"])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE notifications IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM notifications WHERE template_key = 'support_deadline_email' OR support_alert_id IS NOT NULL OR support_alert_revision IS NOT NULL")).scalar():
        raise RuntimeError("Cannot remove retained support deadline email history. Use reviewed recovery or a forward fix.")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("idx_notifications_support_alert")
        batch.drop_constraint("ck_notifications_support_alert_scope", type_="check")
        batch.drop_constraint("fk_notifications_support_alert", type_="foreignkey")
        batch.drop_column("support_alert_revision")
        batch.drop_column("support_alert_id")
