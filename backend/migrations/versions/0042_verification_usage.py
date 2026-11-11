"""Background provider attempt metadata. No historical calls are backfilled."""
from alembic import op
import sqlalchemy as sa

revision = "0042_verification_usage"
down_revision = "0041_verification_jobs"
branch_labels = depends_on = None


def upgrade():
    op.create_table("verification_usage",
        sa.Column("id",sa.Uuid(),primary_key=True),
        # Deliberately no foreign keys: provider accounting must not lock cases,
        # and case deletion must not erase an already incurred attempt.
        sa.Column("service_request_id",sa.Uuid(),nullable=False),
        sa.Column("job_id",sa.Uuid(),nullable=False),
        sa.Column("provider",sa.String(20),nullable=False),sa.Column("model",sa.String(120),nullable=False),
        sa.Column("step",sa.String(20),nullable=False),sa.Column("status",sa.String(20),nullable=False),
        sa.Column("started_at",sa.DateTime(timezone=True),nullable=False),sa.Column("finished_at",sa.DateTime(timezone=True)),
        sa.Column("duration_ms",sa.Integer()),sa.Column("input_tokens",sa.BigInteger()),
        sa.Column("output_tokens",sa.BigInteger()),sa.Column("cache_tokens",sa.BigInteger()),
        sa.Column("usage_complete",sa.Boolean(),nullable=False),sa.Column("estimated_usd",sa.Numeric(24,12)),
        sa.Column("input_rate",sa.Numeric(18,6)),sa.Column("output_rate",sa.Numeric(18,6)),
        sa.Column("rate_version",sa.String(40)),sa.Column("estimate_reason",sa.String(40),nullable=False),
        sa.Column("error_category",sa.String(40)),
        sa.CheckConstraint("provider IN ('anthropic','openai')",name="ck_usage_provider"),
        sa.CheckConstraint("step IN ('extract','compare')",name="ck_usage_step"),
        sa.CheckConstraint("status IN ('started','succeeded','failed')",name="ck_usage_status"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms BETWEEN 0 AND 2147483647",name="ck_usage_duration"),
        sa.CheckConstraint("input_tokens IS NULL OR input_tokens BETWEEN 0 AND 1000000000",name="ck_usage_input"),
        sa.CheckConstraint("output_tokens IS NULL OR output_tokens BETWEEN 0 AND 1000000000",name="ck_usage_output"),
        sa.CheckConstraint("cache_tokens IS NULL OR cache_tokens BETWEEN 0 AND input_tokens",name="ck_usage_cache"),
        sa.CheckConstraint("estimated_usd IS NULL OR estimated_usd >= 0",name="ck_usage_cost"),
        sa.CheckConstraint("input_rate IS NULL OR input_rate BETWEEN 0 AND 1000000",name="ck_usage_input_rate"),
        sa.CheckConstraint("output_rate IS NULL OR output_rate BETWEEN 0 AND 1000000",name="ck_usage_output_rate"))
    op.create_index("ix_usage_started","verification_usage",["started_at","id"])
    op.create_index("ix_usage_job","verification_usage",["job_id"])


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":bind.execute(sa.text("LOCK TABLE verification_usage IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT count(*) FROM verification_usage")):
        raise RuntimeError("Cannot remove retained provider usage. Use a forward fix or reviewed recovery.")
    op.drop_table("verification_usage")
