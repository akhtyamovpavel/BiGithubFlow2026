"""Create schedule_import_batches table for CSV import preview and atomic commit.

Revision ID: bb23cc45dd67
Revises: aa12bb34cc56
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb23cc45dd67"
down_revision: str | Sequence[str] | None = "aa12bb34cc56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
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
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="preview"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_lesson_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("batch_id", name="uq_schedule_import_batches_batch_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_schedule_import_batches_idempotency_key"),
    )
    op.create_index(
        "ix_schedule_import_batches_batch_id",
        "schedule_import_batches",
        ["batch_id"],
        unique=True,
    )
    op.create_index(
        "ix_schedule_import_batches_content_hash",
        "schedule_import_batches",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_import_batches_content_hash", table_name="schedule_import_batches")
    op.drop_index("ix_schedule_import_batches_batch_id", table_name="schedule_import_batches")
    op.drop_table("schedule_import_batches")
