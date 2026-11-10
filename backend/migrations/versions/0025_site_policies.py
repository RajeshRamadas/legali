"""Private policy drafts and immutable publication snapshots, with explicit public visibility."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025_site_policies"
down_revision = "0024_customer_support"
branch_labels = None
depends_on = None


def upgrade():
    content = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table("site_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draft", content), sa.Column("published_version", sa.Integer()),
        sa.Column("withdraw_reason", sa.Text()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('privacy','terms','grievance')", name="ck_site_policy_kind"),
        sa.CheckConstraint("revision >= 0 AND version_counter >= 0", name="ck_site_policy_counters"),
        sa.UniqueConstraint("kind", name="uq_site_policy_kind"))
    op.create_table("site_policy_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("site_policies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False), sa.Column("content", content, nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("number >= 1", name="ck_site_policy_version_number"),
        sa.UniqueConstraint("policy_id", "number", name="uq_site_policy_version"))


def downgrade():
    op.drop_table("site_policy_versions")
    op.drop_table("site_policies")
