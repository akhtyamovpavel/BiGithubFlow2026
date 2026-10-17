"""Add lesson foreign keys after all referenced tables exist.

Revision ID: e7f8a9b0c1d2
Revises: c6e7e906c2f0
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "c6e7e906c2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LESSON_REFERENCES = (
    ("subject_id", "subjects"),
    ("teacher_id", "teachers"),
    ("group_id", "groups"),
    ("classroom_id", "classrooms"),
    ("time_slot_id", "time_slots"),
)


def upgrade() -> None:
    """Attach deferred constraints on databases supporting ALTER TABLE."""
    if not op.get_bind().dialect.supports_alter:
        return

    for column, table in LESSON_REFERENCES:
        op.create_foreign_key(
            f"fk_lessons_{column}_{table}",
            "lessons",
            table,
            [column],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Remove deferred constraints before dropping their referenced tables."""
    if not op.get_bind().dialect.supports_alter:
        return

    for column, table in reversed(LESSON_REFERENCES):
        op.drop_constraint(f"fk_lessons_{column}_{table}", "lessons", type_="foreignkey")
