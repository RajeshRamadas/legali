"""consultation payments

Revision ID: 0007_consultation_payments
Revises: 0006
Create Date: 2026-10-19 12:00:00

Online payment of booking fees through Razorpay: one row per order or payment link, with its outcome.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0007_consultation_payments'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('payments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('service_request_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('currency', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('provider_order_id', sa.Text(), nullable=False),
    sa.Column('pay_url', sa.Text(), nullable=True),
    sa.Column('provider_payment_id', sa.Text(), nullable=True),
    sa.Column('method', sa.Text(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('created', 'paid', 'refund_due', 'refunded')", name='ck_payments_status'),
    sa.CheckConstraint("provider IN ('razorpay', 'test')", name='ck_payments_provider'),
    sa.CheckConstraint("kind IN ('checkout', 'link')", name='ck_payments_kind'),
    sa.CheckConstraint('amount_paise > 0', name='ck_payments_amount'),
    sa.ForeignKeyConstraint(['service_request_id'], ['service_requests.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_order_id')
    )
    op.create_index('idx_payments_request', 'payments', ['service_request_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_payments_request', table_name='payments')
    op.drop_table('payments')
