import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def schema():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    reviews = sa.Table("lawyer_reviews", metadata,
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("moderation_status", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False), sa.Column("rating", sa.Integer(), nullable=False))
    decisions = sa.Table("lawyer_review_decisions", metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("lawyer_reviews.id", ondelete="CASCADE")),
        sa.Column("note", sa.Text(), nullable=False))
    metadata.create_all(engine)
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0028_review_withdrawal.py"
    spec = importlib.util.spec_from_file_location("withdrawal_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(reviews.insert().values(id=1, moderation_status="published", comment="Original feedback.", rating=1))
        connection.execute(decisions.insert().values(id=1, review_id=1, note="Original private decision."))
        with Operations.context(MigrationContext.configure(connection)):
            yield connection, migration
    engine.dispose()


def test_round_trip_without_withdrawals_preserves_feedback_and_decision_history(schema):
    connection, migration = schema
    migration.upgrade()
    assert connection.execute(sa.text("SELECT moderation_status, comment, rating, withdrawn_at FROM lawyer_reviews")).one() == ("published", "Original feedback.", 1, None)
    migration.downgrade()
    assert "withdrawn_at" not in {column["name"] for column in sa.inspect(connection).get_columns("lawyer_reviews")}
    assert connection.execute(sa.text("SELECT comment, rating FROM lawyer_reviews")).one() == ("Original feedback.", 1)
    assert connection.execute(sa.text("SELECT note FROM lawyer_review_decisions")).scalar_one() == "Original private decision."


def test_withdrawal_blocks_legacy_publication_and_prevents_unsafe_rollback(schema):
    connection, migration = schema
    migration.upgrade()
    connection.execute(sa.text("UPDATE lawyer_reviews SET moderation_status='hidden', withdrawn_at='2026-11-10 00:00:00' WHERE id=1"))
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(sa.text("UPDATE lawyer_reviews SET moderation_status='published' WHERE id=1"))
    with pytest.raises(RuntimeError, match="Cannot remove customer withdrawal protection"):
        migration.downgrade()
    assert "withdrawn_at" in {column["name"] for column in sa.inspect(connection).get_columns("lawyer_reviews")}
    assert connection.execute(sa.text("SELECT withdrawn_at FROM lawyer_reviews")).scalar_one() is not None
    assert connection.execute(sa.text("SELECT note FROM lawyer_review_decisions")).scalar_one() == "Original private decision."
