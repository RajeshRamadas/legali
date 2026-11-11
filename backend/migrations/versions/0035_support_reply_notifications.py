"""Account-scoped, revisioned support reply delivery records; no historical sends."""
from alembic import op
import sqlalchemy as sa

revision = "0035_support_reply_notifications"
down_revision = "0034_support_deadline_alerts"
branch_labels = depends_on = None

SCOPE = "(template_key = 'support_reply' AND support_update_revision IS NOT NULL AND support_update_revision >= 1 AND customer_id IS NULL AND user_id IS NULL AND service_request_id IS NULL AND meeting_id IS NULL AND case_alert_id IS NULL) OR (template_key <> 'support_reply' AND account_id IS NULL AND support_request_id IS NULL AND support_update_revision IS NULL)"


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid()))
        batch.add_column(sa.Column("support_request_id", sa.Uuid()))
        batch.add_column(sa.Column("support_update_revision", sa.Integer()))
        batch.create_foreign_key("fk_notifications_account", "customer_accounts", ["account_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_notifications_support", "support_requests", ["support_request_id"], ["id"], ondelete="SET NULL")
        batch.create_check_constraint("ck_notifications_support_scope", SCOPE)
        batch.create_index("idx_notifications_account", ["account_id", "delivery_status"])
        batch.create_index("idx_notifications_support", ["support_request_id", "delivery_status"])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE notifications IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM notifications WHERE template_key = 'support_reply' OR account_id IS NOT NULL OR support_request_id IS NOT NULL OR support_update_revision IS NOT NULL")).scalar():
        raise RuntimeError("Cannot remove retained support notification history. Use reviewed recovery or a forward fix.")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("idx_notifications_account")
        batch.drop_index("idx_notifications_support")
        batch.drop_constraint("ck_notifications_support_scope", type_="check")
        batch.drop_constraint("fk_notifications_account", type_="foreignkey")
        batch.drop_constraint("fk_notifications_support", type_="foreignkey")
        batch.drop_column("support_update_revision")
        batch.drop_column("support_request_id")
        batch.drop_column("account_id")
