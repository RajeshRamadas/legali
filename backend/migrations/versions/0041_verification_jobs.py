"""Durable case-scoped verification jobs, with no historical processing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0041_verification_jobs"
down_revision = "0040_append_only_audit"
branch_labels = depends_on = None


def upgrade():
    op.create_table("verification_jobs",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("service_request_id",sa.Uuid(),sa.ForeignKey("service_requests.id",ondelete="CASCADE"),nullable=False),
        sa.Column("requested_by_user_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("submission_key",sa.Uuid(),nullable=False),
        sa.Column("request",sa.JSON().with_variant(JSONB(),"postgresql"),nullable=False),
        sa.Column("input_fingerprint",sa.String(64),nullable=False),sa.Column("configuration_revision",sa.String(64),nullable=False),
        sa.Column("status",sa.Text(),nullable=False),sa.Column("phase",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("started_at",sa.DateTime(timezone=True)),
        sa.Column("finished_at",sa.DateTime(timezone=True)),sa.Column("lease_until",sa.DateTime(timezone=True)),
        sa.Column("claim_token",sa.Uuid()),sa.Column("run_id",sa.Uuid(),sa.ForeignKey("verification_runs.id",ondelete="SET NULL")),
        sa.Column("reason_code",sa.Text()),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','cancelled','stale')",name="ck_verification_job_status"),
        sa.CheckConstraint("phase IN ('queued','extracting','analysing','finalizing','finished')",name="ck_verification_job_phase"),
        sa.UniqueConstraint("service_request_id","submission_key",name="uq_verification_job_submission"))
    active=sa.text("status IN ('queued','running')")
    op.create_index("uq_verification_job_active","verification_jobs",["service_request_id"],unique=True,postgresql_where=active,sqlite_where=active)
    op.create_index("ix_verification_job_queue","verification_jobs",["status","created_at"])
    op.create_index("ix_verification_job_case","verification_jobs",["service_request_id","created_at"])


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":bind.execute(sa.text("LOCK TABLE verification_jobs IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT count(*) FROM verification_jobs")):
        raise RuntimeError("Cannot remove retained verification jobs. Use a forward fix or reviewed recovery.")
    op.drop_table("verification_jobs")
