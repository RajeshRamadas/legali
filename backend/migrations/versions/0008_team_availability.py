"""team availability

Revision ID: 0008_team_availability
Revises: 0007_consultation_payments
Create Date: 2026-10-19 12:30:00

Staff say whether the team can call them now, with a short note. Seen only in the staff workspace.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0008_team_availability'
down_revision: Union[str, Sequence[str], None] = '0007_consultation_payments'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('available_for_calls', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('availability_note', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('availability_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'availability_updated_at')
    op.drop_column('users', 'availability_note')
    op.drop_column('users', 'available_for_calls')
