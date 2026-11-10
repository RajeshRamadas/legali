"""Queue all unreviewed consultation feedback before public display."""
from alembic import op
import sqlalchemy as sa

revision = "0027_review_moderation"
down_revision = "0026_refund_tracking"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lawyer_reviews") as batch:
        batch.add_column(sa.Column("moderation_status", sa.Text(), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.create_check_constraint("ck_lawyer_review_moderation", "moderation_status IN ('pending','published','hidden') AND revision >= 1")
    op.create_index("ix_lawyer_review_moderation_queue", "lawyer_reviews", ["moderation_status", "created_at"])
    op.create_table("lawyer_review_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("review_id", sa.Uuid(), sa.ForeignKey("lawyer_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("from_status", sa.Text(), nullable=False), sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("note", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("review_id", "revision", name="uq_lawyer_review_decision_revision"),
        sa.CheckConstraint("from_status IN ('pending','published','hidden') AND to_status IN ('published','hidden') AND from_status <> to_status AND revision >= 2", name="ck_lawyer_review_decision"))


def downgrade():
    op.drop_table("lawyer_review_decisions")
    op.drop_index("ix_lawyer_review_moderation_queue", table_name="lawyer_reviews")
    with op.batch_alter_table("lawyer_reviews") as batch:
        batch.drop_constraint("ck_lawyer_review_moderation", type_="check")
        batch.drop_column("updated_at")
        batch.drop_column("revision")
        batch.drop_column("moderation_status")
