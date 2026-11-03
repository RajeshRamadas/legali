"""Persist notification attempts and worker leases.

Revision ID: 0016_notification_delivery
Revises: 0015_blog_agent
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_notification_delivery"
down_revision = "0015_blog_agent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notifications", sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("notifications", sa.Column("first_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("processing_until", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("claim_token", sa.Uuid()))


def downgrade():
    for name in ("claim_token", "processing_until", "last_attempt_at", "first_attempt_at", "attempts"):
        op.drop_column("notifications", name)
