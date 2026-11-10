"""Persist customer channel choices without changing existing notification behavior."""
from alembic import op
import sqlalchemy as sa

revision = "0029_notification_preferences"
down_revision = "0028_review_withdrawal"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("customer_notification_preferences",
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("customer_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("email", sa.Boolean(), nullable=False),
        sa.Column("sms", sa.Boolean(), nullable=False),
        sa.Column("whatsapp", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_customer_notification_preferences_revision"))


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE customer_notification_preferences IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT COUNT(*) FROM customer_notification_preferences WHERE NOT email OR NOT sms OR NOT whatsapp")).scalar_one():
        raise RuntimeError("Cannot remove notification preferences while a customer has disabled a channel. Preserve these choices and review the rollback procedure.")
    op.drop_table("customer_notification_preferences")
