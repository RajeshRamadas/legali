"""Explicit document preservation choices; no historical holds are inferred."""
from alembic import op
import sqlalchemy as sa

revision = "0044_document_preservation"
down_revision = "0043_case_ai_consent"
branch_labels = depends_on = None


def upgrade():
    op.create_table("case_document_holds",
        sa.Column("service_request_id",sa.Uuid(),sa.ForeignKey("service_requests.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("held",sa.Boolean(),nullable=False),sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("reason",sa.String(30),nullable=False),sa.Column("note",sa.Text(),nullable=False),
        sa.Column("changed_by_user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("changed_at",sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("revision >= 1",name="ck_document_hold_revision"),
        sa.CheckConstraint("reason IN ('privacy_review','legal_obligation','manual_review')",name="ck_document_hold_reason"))
    op.create_index("ix_document_hold_queue","case_document_holds",["held","changed_at"])


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":bind.execute(sa.text("LOCK TABLE case_document_holds IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT count(*) FROM case_document_holds")):
        raise RuntimeError("Cannot remove retained document preservation decisions. Use a forward fix or reviewed recovery.")
    op.drop_table("case_document_holds")
