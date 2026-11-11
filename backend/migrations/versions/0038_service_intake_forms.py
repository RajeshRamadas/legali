"""Reviewed supplemental service questions and immutable draft selections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038_service_intake_forms"
down_revision = "0037_service_descriptions"
branch_labels = depends_on = None
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("service_types") as batch:
        batch.add_column(sa.Column("intake_questions", JSON, nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("intake_form_revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_service_intake_form_revision", "intake_form_revision >= 1")
    with op.batch_alter_table("intake_drafts") as batch:
        batch.add_column(sa.Column("service_form_snapshot", JSON, nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE service_types, intake_drafts IN ACCESS EXCLUSIVE MODE"))
    forms = sa.table("service_types", sa.column("intake_questions", JSON), sa.column("intake_form_revision", sa.Integer()))
    drafts = sa.table("intake_drafts", sa.column("service_form_snapshot", JSON))
    used = any(questions or version > 1 for questions, version in bind.execute(sa.select(forms.c.intake_questions, forms.c.intake_form_revision)))
    pinned = any(value.get("questions") or value.get("revision", 1) > 1 for value in bind.scalars(sa.select(drafts.c.service_form_snapshot)))
    history = bind.execute(sa.text("SELECT count(*) FROM audit_logs WHERE action = 'service.intake_form_published'")).scalar()
    if used or pinned or history:
        raise RuntimeError("Cannot remove published intake questions, draft snapshots or publication history. Use a forward fix or reviewed recovery.")
    with op.batch_alter_table("intake_drafts") as batch:
        batch.drop_column("service_form_snapshot")
    with op.batch_alter_table("service_types") as batch:
        batch.drop_constraint("ck_service_intake_form_revision", type_="check")
        batch.drop_column("intake_form_revision")
        batch.drop_column("intake_questions")
