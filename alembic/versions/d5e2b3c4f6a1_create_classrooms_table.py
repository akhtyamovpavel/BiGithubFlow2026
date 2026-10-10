"""Create classrooms table.

Revision ID: d5e2b3c4f6a1
Revises: c4f1a2d7e9b3
Create Date: 2026-10-10 20:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e2b3c4f6a1"
down_revision: str | Sequence[str] | None = "c4f1a2d7e9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "classrooms",
        sa.Column("building", sa.String(length=128), nullable=False),
        sa.Column("room_number", sa.String(length=64), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("has_projector", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_computers", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building", "room_number", name="uq_classrooms_building_room_number"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("classrooms")
