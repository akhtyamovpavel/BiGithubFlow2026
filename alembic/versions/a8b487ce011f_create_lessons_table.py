"""create_lessons_table

Revision ID: a8b487ce011f
Revises:
Create Date: 2026-10-03 20:35:25.026617

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b487ce011f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to include lessons table."""
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("classroom_id", sa.Integer(), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), nullable=False),
        sa.Column("lesson_type", sa.String(length=20), nullable=False),
        sa.Column("parity", sa.String(length=20), nullable=False),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["time_slot_id"],
            ["time_slots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lessons_subject_id"), "lessons", ["subject_id"], unique=False)
    op.create_index(op.f("ix_lessons_teacher_id"), "lessons", ["teacher_id"], unique=False)
    op.create_index(op.f("ix_lessons_group_id"), "lessons", ["group_id"], unique=False)
    op.create_index(op.f("ix_lessons_classroom_id"), "lessons", ["classroom_id"], unique=False)
    op.create_index(op.f("ix_lessons_time_slot_id"), "lessons", ["time_slot_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema by dropping lessons table."""
    op.drop_index(op.f("ix_lessons_time_slot_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_classroom_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_group_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_teacher_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_subject_id"), table_name="lessons")
    op.drop_table("lessons")
