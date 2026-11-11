"""Explicit case AI choices; no legacy consent or processing is inferred."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0043_case_ai_consent"
down_revision = "0042_verification_usage"
branch_labels = depends_on = None


def upgrade():
    op.create_table("case_ai_consents",
        sa.Column("service_request_id",sa.Uuid(),sa.ForeignKey("service_requests.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("customer_account_id",sa.Uuid(),sa.ForeignKey("customer_accounts.id",ondelete="SET NULL")),
        sa.Column("allowed",sa.Boolean(),nullable=False),sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("processing_revision",sa.String(64)),sa.Column("notice_version",sa.String(40)),
        sa.Column("notice_snapshot",sa.JSON().with_variant(JSONB(),"postgresql"),nullable=False),
        sa.Column("changed_at",sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("revision >= 0",name="ck_case_ai_consent_revision"))
    op.add_column("verification_jobs",sa.Column("consent_revision",sa.Integer()))


def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":
        bind.execute(sa.text("LOCK TABLE case_ai_consents, verification_jobs IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT count(*) FROM case_ai_consents")) or bind.scalar(sa.text("SELECT count(*) FROM verification_jobs WHERE consent_revision IS NOT NULL")):
        raise RuntimeError("Cannot remove retained AI processing choices. Use a forward fix or reviewed recovery.")
    op.drop_column("verification_jobs","consent_revision")
    op.drop_table("case_ai_consents")
