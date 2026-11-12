"""Index authorized file access review without rewriting existing audit history."""
from alembic import op

revision = "0047_file_access_history_index"
down_revision = "0046_staff_sessions"
branch_labels = depends_on = None


def upgrade():
    op.create_index("ix_audit_logs_action_created_id", "audit_logs", ["action", "created_at", "id"])
    op.create_index("ix_audit_logs_entity_action_created", "audit_logs", ["entity_type", "entity_id", "action", "created_at", "id"])


def downgrade():
    op.drop_index("ix_audit_logs_entity_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_created_id", table_name="audit_logs")
