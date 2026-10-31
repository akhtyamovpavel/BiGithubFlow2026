"""Create exceptions for individual lesson occurrences.

Revision ID: aa12bb34cc56
Revises: f9a1b2c3d4e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa12bb34cc56"
down_revision: str | Sequence[str] | None = "f9a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lessons.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column(
            "replacement_lesson_id",
            sa.Integer(),
            sa.ForeignKey("lessons.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("lesson_id", "occurrence_date", name="uq_lesson_exception_occurrence"),
        sa.CheckConstraint(
            "action IN ('cancel','move') AND (replacement_lesson_id IS NULL) = (action = 'cancel')",
            name="ck_lesson_exception_action",
        ),
    )
    op.create_index("ix_lesson_exceptions_lesson_id", "lesson_exceptions", ["lesson_id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_exceptions_lesson_id", table_name="lesson_exceptions")
    op.drop_table("lesson_exceptions")
