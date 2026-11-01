"""AI case-to-blog desk: case scan runs, case leads, and review fields on posts

Revision ID: 0014_blog_agent
Revises: 0013_more_property_types
Create Date: 2026-11-01 05:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0014_blog_agent'
down_revision: Union[str, Sequence[str], None] = '0013_more_property_types'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        'case_scan_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('trigger', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('started_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('found', sa.Integer(), nullable=False),
        sa.Column('added', sa.Integer(), nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('usage', JSON, nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.CheckConstraint("trigger IN ('schedule', 'admin', 'cli')", name='ck_case_scan_runs_trigger'),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name='ck_case_scan_runs_status'),
        sa.ForeignKeyConstraint(['started_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_case_scan_runs_started_at', 'case_scan_runs', ['started_at'])
    op.create_table(
        'case_leads',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=True),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('case_key', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('court', sa.Text(), nullable=False),
        sa.Column('case_number', sa.Text(), nullable=False),
        sa.Column('decision_date', sa.Date(), nullable=True),
        sa.Column('source_name', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('why_it_matters', sa.Text(), nullable=False),
        sa.Column('topics', JSON, nullable=False),
        sa.Column('relevance', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('post_id', sa.Uuid(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('new', 'drafting', 'drafted', 'dismissed', 'failed')", name='ck_case_leads_status'),
        sa.ForeignKeyConstraint(['run_id'], ['case_scan_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
        sa.UniqueConstraint('case_key'),
    )
    op.create_index('idx_case_leads_status', 'case_leads', ['status', 'created_at'])
    with op.batch_alter_table('posts') as batch:
        batch.add_column(sa.Column('origin', sa.Text(), server_default='manual', nullable=False))
        batch.add_column(sa.Column('ai_review', JSON, nullable=True))
        batch.add_column(sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_posts_reviewed_by_user_id', 'users', ['reviewed_by_user_id'], ['id'], ondelete='SET NULL')
        batch.create_check_constraint('ck_posts_origin', "origin IN ('manual', 'ai')")


def downgrade() -> None:
    with op.batch_alter_table('posts') as batch:
        batch.drop_constraint('ck_posts_origin', type_='check')
        batch.drop_constraint('fk_posts_reviewed_by_user_id', type_='foreignkey')
        batch.drop_column('reviewed_at')
        batch.drop_column('reviewed_by_user_id')
        batch.drop_column('ai_review')
        batch.drop_column('origin')
    op.drop_index('idx_case_leads_status', table_name='case_leads')
    op.drop_table('case_leads')
    op.drop_index('ix_case_scan_runs_started_at', table_name='case_scan_runs')
    op.drop_table('case_scan_runs')
