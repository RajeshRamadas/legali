"""Track one recorded physical shipment per courier request."""
from alembic import op
import sqlalchemy as sa

revision = "0048_courier_shipments"
down_revision = "0047_file_access_history_index"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "courier_shipments",
        sa.Column("service_request_id", sa.Uuid(), sa.ForeignKey("service_requests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("carrier", sa.String(80), nullable=False),
        sa.Column("tracking_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('dispatched', 'in_transit', 'out_for_delivery', 'delivered', 'delivery_issue', 'returned')",
            name="ck_courier_shipment_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_courier_shipment_revision"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE courier_shipments IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT 1 FROM courier_shipments LIMIT 1")):
        raise RuntimeError("Courier shipments exist. Use a forward fix or reviewed recovery to retain tracking records.")
    op.drop_table("courier_shipments")
