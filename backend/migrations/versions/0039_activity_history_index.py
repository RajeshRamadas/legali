"""Index retained audit history for chronological administrator review."""
from alembic import op

revision = "0039_activity_history_index"
down_revision = "0038_service_intake_forms"
branch_labels = depends_on = None


def upgrade():
    op.create_index("ix_audit_logs_created_id", "audit_logs", ["created_at", "id"])


def downgrade():
    op.drop_index("ix_audit_logs_created_id", table_name="audit_logs")
