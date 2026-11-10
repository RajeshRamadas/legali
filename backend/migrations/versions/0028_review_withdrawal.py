"""Retain customer withdrawal intent and prevent legacy moderation from republishing it."""
from alembic import op
import sqlalchemy as sa

revision = "0028_review_withdrawal"
down_revision = "0027_review_moderation"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lawyer_reviews") as batch:
        batch.add_column(sa.Column("withdrawn_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint("ck_lawyer_review_withdrawal", "withdrawn_at IS NULL OR moderation_status = 'hidden'")


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE lawyer_reviews IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT COUNT(*) FROM lawyer_reviews WHERE withdrawn_at IS NOT NULL")).scalar_one():
        raise RuntimeError("Cannot remove customer withdrawal protection while withdrawn reviews exist. Keep this schema and review the rollback procedure.")
    with op.batch_alter_table("lawyer_reviews") as batch:
        batch.drop_constraint("ck_lawyer_review_withdrawal", type_="check")
        batch.drop_column("withdrawn_at")
