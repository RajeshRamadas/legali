"""Persist malware scan metadata. Existing files remain pending until scanned."""
from alembic import op
import sqlalchemy as sa

revision = "0017_document_scanning"
down_revision = "0016_notification_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("scanned_at", sa.DateTime(timezone=True)))
    op.add_column("documents", sa.Column("scan_detail", sa.Text()))


def downgrade():
    op.drop_column("documents", "scan_detail")
    op.drop_column("documents", "scanned_at")
