"""Revocable customer sign-ins. Legacy bearer tokens require fresh verification."""
from alembic import op
import sqlalchemy as sa

revision = "0045_customer_sessions"
down_revision = "0044_document_preservation"
branch_labels = depends_on = None


def upgrade():
    op.create_table("customer_sessions",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("account_id",sa.Uuid(),sa.ForeignKey("customer_accounts.id",ondelete="CASCADE"),nullable=False),
        sa.Column("token_version",sa.Integer(),nullable=False),sa.Column("browser",sa.String(40),nullable=False),sa.Column("device",sa.String(40),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("last_seen_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked_at",sa.DateTime(timezone=True)),sa.Column("revoke_reason",sa.String(30)),
        sa.CheckConstraint("expires_at > created_at",name="ck_customer_session_expiry"),
        sa.CheckConstraint("token_version >= 1",name="ck_customer_session_version"),
        sa.CheckConstraint("revoke_reason IS NULL OR revoke_reason IN ('customer','other_sessions','all_sessions','session_limit')",name="ck_customer_session_reason"))
    op.create_index("ix_customer_session_active","customer_sessions",["account_id","revoked_at","expires_at"])


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":bind.execute(sa.text("LOCK TABLE customer_sessions IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT count(*) FROM customer_sessions")):
        raise RuntimeError("Cannot remove retained customer session records. Use a forward fix or reviewed recovery.")
    op.drop_table("customer_sessions")
