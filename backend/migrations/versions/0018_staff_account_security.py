"""Staff session revocation, encrypted MFA enrollment and one-time authentication tokens."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_staff_account_security"
down_revision = "0017_document_scanning"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default=sa.text("1"), nullable=False))
    for name in ("mfa_secret", "mfa_pending_secret"):
        op.add_column("users", sa.Column(name, sa.Text()))
    op.add_column("users", sa.Column("mfa_pending_until", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("mfa_last_counter", sa.BigInteger()))
    op.add_column("users", sa.Column("mfa_recovery_hashes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")))
    op.create_table("staff_auth_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), unique=True, nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_staff_auth_tokens_user_id", "staff_auth_tokens", ["user_id"])
    op.create_table("staff_auth_buckets",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("staff_auth_buckets")
    op.drop_table("staff_auth_tokens")
    for name in ("mfa_recovery_hashes", "mfa_last_counter", "mfa_pending_until", "mfa_pending_secret", "mfa_secret", "token_version"):
        op.drop_column("users", name)
