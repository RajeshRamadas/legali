"""Private support ownership with safe preservation of assigned work."""
from alembic import op
import sqlalchemy as sa

revision = "0033_support_ownership"
down_revision = "0032_support_unread_replies"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("support_requests") as batch:
        batch.add_column(sa.Column("assignee_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_support_request_owner", "users", ["assignee_user_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_support_owner_queue", ["assignee_user_id", "status", "reply_due_at"])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE support_requests IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM support_requests WHERE assignee_user_id IS NOT NULL")).scalar():
        raise RuntimeError("Cannot remove support ownership while assigned requests remain.")
    with op.batch_alter_table("support_requests") as batch:
        batch.drop_index("ix_support_owner_queue")
        batch.drop_constraint("fk_support_request_owner", type_="foreignkey")
        batch.drop_column("assignee_user_id")
