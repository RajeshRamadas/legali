"""customer documents with tags, legal reports and their document checklists

Revision ID: 0009
Revises: 0008_team_availability
Create Date: 2026-10-19 12:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008_team_availability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('uploader_type', sa.Text(), server_default='customer', nullable=False))
    op.add_column('documents', sa.Column('tag', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('note', sa.Text(), nullable=True))
    op.create_check_constraint('ck_documents_uploader_type', 'documents', "uploader_type IN ('customer', 'staff', 'system')")
    op.create_index('idx_documents_request_tag', 'documents', ['service_request_id', 'tag'], unique=False)

    op.create_table('legal_reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('service_request_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('preliminary', JSONType, nullable=False),
    sa.Column('final', JSONType, nullable=False),
    sa.Column('lawyer_user_id', sa.Uuid(), nullable=True),
    sa.Column('reviewer_user_id', sa.Uuid(), nullable=True),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('final_document_id', sa.Uuid(), nullable=True),
    sa.Column('final_generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('signed_document_id', sa.Uuid(), nullable=True),
    sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'issued', 'final_generated', 'signed')", name='ck_legal_reports_status'),
    sa.ForeignKeyConstraint(['service_request_id'], ['service_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lawyer_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['final_document_id'], ['documents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['signed_document_id'], ['documents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('service_request_id')
    )
    op.create_table('report_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('report_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('tag', sa.Text(), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('guidance', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('fetch_by', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'received', 'verified', 'rejected', 'waived')", name='ck_report_items_status'),
    sa.CheckConstraint("fetch_by IN ('customer', 'homexo')", name='ck_report_items_fetch_by'),
    sa.ForeignKeyConstraint(['report_id'], ['legal_reports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('report_id', 'tag', name='uq_report_items_tag')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('report_items')
    op.drop_table('legal_reports')
    op.drop_index('idx_documents_request_tag', table_name='documents')
    op.drop_constraint('ck_documents_uploader_type', 'documents', type_='check')
    op.drop_column('documents', 'note')
    op.drop_column('documents', 'tag')
    op.drop_column('documents', 'uploader_type')
