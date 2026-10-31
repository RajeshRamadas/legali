"""villas, farmhouses, plantation estates and industrial land as property types

Revision ID: 0013_more_property_types
Revises: 0012_document_checks
Create Date: 2026-10-19 18:00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0013_more_property_types'
down_revision: Union[str, Sequence[str], None] = '0012_document_checks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = ('apartment', 'independent_house', 'commercial', 'residential_plot', 'agricultural_land', 'other')
NEW = ('apartment', 'villa', 'independent_house', 'commercial', 'residential_plot', 'agricultural_land', 'farmhouse', 'plantation_estate', 'industrial_land', 'other')


def _check(values: tuple) -> str:
    return f"property_type IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('properties') as batch:
        batch.drop_constraint('ck_properties_type', type_='check')
        batch.create_check_constraint('ck_properties_type', _check(NEW))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE properties SET property_type = 'other' WHERE property_type IN ('villa', 'farmhouse', 'plantation_estate', 'industrial_land')")
    with op.batch_alter_table('properties') as batch:
        batch.drop_constraint('ck_properties_type', type_='check')
        batch.create_check_constraint('ck_properties_type', _check(OLD))
