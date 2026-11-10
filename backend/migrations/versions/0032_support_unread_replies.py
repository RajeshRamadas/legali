"""Track customer-visible reply receipt without exposing internal support activity."""
from alembic import op
import sqlalchemy as sa

revision = "0032_support_unread_replies"
down_revision = "0031_lawyer_time_off"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("support_requests") as batch:
        batch.add_column(sa.Column("customer_update_revision", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("customer_read_revision", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint("ck_support_unread_replies", "customer_update_revision >= 0 AND customer_read_revision >= 0 AND customer_read_revision <= customer_update_revision")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE support_requests IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM support_requests WHERE customer_update_revision > customer_read_revision")).scalar():
        raise RuntimeError("Cannot remove reply receipts while unread support replies remain.")
    with op.batch_alter_table("support_requests") as batch:
        batch.drop_constraint("ck_support_unread_replies", type_="check")
        batch.drop_column("customer_read_revision")
        batch.drop_column("customer_update_revision")
