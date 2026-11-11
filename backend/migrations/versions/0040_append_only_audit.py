"""Reject audit updates/deletes and PostgreSQL truncation without rewriting history."""
from alembic import op
from app.audit_guard_v1 import install, remove

revision = "0040_append_only_audit"
down_revision = "0039_activity_history_index"
branch_labels = depends_on = None


def upgrade():
    install(op.get_bind())


def downgrade():
    remove(op.get_bind())
