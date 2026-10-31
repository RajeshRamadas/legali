"""customer accounts with phone sign-in codes

Revision ID: 0010_customer_accounts
Revises: 0009
Create Date: 2026-10-19 18:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0010_customer_accounts'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('customer_accounts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('phone_normalized', sa.Text(), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=True),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('phone_normalized')
    )
    op.create_table('login_codes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('phone_normalized', sa.Text(), nullable=False),
    sa.Column('code_hash', sa.Text(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('client_key', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_login_codes_client_created', 'login_codes', ['client_key', 'created_at'], unique=False)
    op.create_index('idx_login_codes_phone_created', 'login_codes', ['phone_normalized', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_login_codes_phone_created', table_name='login_codes')
    op.drop_index('idx_login_codes_client_created', table_name='login_codes')
    op.drop_table('login_codes')
    op.drop_table('customer_accounts')
