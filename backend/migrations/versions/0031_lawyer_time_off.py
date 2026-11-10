"""Preserve staff unavailability separately from weekly consultation hours."""
from alembic import op
import sqlalchemy as sa

revision = "0031_lawyer_time_off"
down_revision = "0030_service_availability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("lawyer_time_off",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lawyer_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submission_key", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("ends_at > starts_at", name="ck_lawyer_time_off_range"),
        sa.UniqueConstraint("lawyer_user_id", "submission_key", name="uq_lawyer_time_off_submission"))
    op.create_index("ix_lawyer_time_off_window", "lawyer_time_off", ["lawyer_user_id", "starts_at", "ends_at"])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE lawyer_time_off IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(sa.text("SELECT count(*) FROM lawyer_time_off WHERE cancelled_at IS NULL AND ends_at > CURRENT_TIMESTAMP")).scalar():
        raise RuntimeError("Cannot remove time-off controls while upcoming time off is active.")
    op.drop_table("lawyer_time_off")
