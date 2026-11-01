"""Case management: case tasks, case team, deadlines, close-out and the case fee on service requests.

Revision ID: 0014_case_management
Revises: 0013_more_property_types
Create Date: 2026-11-01 06:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_case_management"
down_revision = "0013_more_property_types"
branch_labels = None
depends_on = None

FEE_STATUSES = ("none", "quoted", "paid", "waived")

def _check(column: str, values: tuple) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"

def upgrade():
    with op.batch_alter_table("service_requests") as batch:
        batch.add_column(sa.Column("first_response_due_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("first_response_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("closure_outcome", sa.Text()))
        batch.add_column(sa.Column("closure_summary", sa.Text()))
        batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("fee_status", sa.Text(), nullable=False, server_default=sa.text("'none'")))
        batch.add_column(sa.Column("fee_quote_paise", sa.Integer()))
        batch.add_column(sa.Column("fee_paid_paise", sa.Integer()))
        batch.add_column(sa.Column("fee_reference", sa.Text()))
        batch.add_column(sa.Column("fee_paid_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("fee_note", sa.Text()))
        batch.create_check_constraint("ck_service_requests_fee_status", _check("fee_status", FEE_STATUSES))
    op.create_index("idx_requests_status_due", "service_requests", ["status", "due_at"])

    op.create_table(
        "case_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(_check("role", ("associate", "paralegal", "reviewer")), name="ck_case_members_role"),
    )
    op.create_index("idx_case_members_user_active", "case_members", ["user_id"],
                    postgresql_where=sa.text("removed_at IS NULL"), sqlite_where=sa.text("removed_at IS NULL"))

    op.create_table(
        "case_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("assignee_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("playbook_key", sa.Text()),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(_check("status", ("open", "done", "cancelled")), name="ck_case_tasks_status"),
        sa.CheckConstraint(_check("source", ("manual", "playbook")), name="ck_case_tasks_source"),
    )
    op.create_index("idx_case_tasks_request", "case_tasks", ["service_request_id"])
    op.create_index("idx_case_tasks_assignee_open", "case_tasks", ["assignee_user_id", "due_at"],
                    postgresql_where=sa.text("status = 'open'"), sqlite_where=sa.text("status = 'open'"))

def downgrade():
    op.drop_index("idx_case_tasks_assignee_open", table_name="case_tasks")
    op.drop_index("idx_case_tasks_request", table_name="case_tasks")
    op.drop_table("case_tasks")
    op.drop_index("idx_case_members_user_active", table_name="case_members")
    op.drop_table("case_members")
    op.drop_index("idx_requests_status_due", table_name="service_requests")
    with op.batch_alter_table("service_requests") as batch:
        batch.drop_constraint("ck_service_requests_fee_status", type_="check")
        for column in ("fee_note", "fee_paid_at", "fee_reference", "fee_paid_paise", "fee_quote_paise", "fee_status",
                       "closed_at", "closure_summary", "closure_outcome", "first_response_at", "first_response_due_at"):
            batch.drop_column(column)
