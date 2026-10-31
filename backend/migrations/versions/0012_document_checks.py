"""Automatic upload check result on each document."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_document_checks"
down_revision = "0011_verification"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("documents", sa.Column("ai_check", sa.JSON().with_variant(JSONB(), "postgresql")))

def downgrade():
    op.drop_column("documents", "ai_check")
