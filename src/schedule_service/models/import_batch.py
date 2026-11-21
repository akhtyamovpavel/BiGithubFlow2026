"""SQLAlchemy ORM model for tracking CSV schedule import batches."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class ImportBatchStatus(str, enum.Enum):
    """Lifecycle status of a CSV schedule import batch."""

    PREVIEW = "preview"
    COMMITTED = "committed"
    FAILED = "failed"


class ScheduleImportBatch(Base):
    """Persisted CSV import preview/commit batch for idempotency and status recovery."""

    __tablename__ = "schedule_import_batches"

    batch_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, default=None
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImportBatchStatus.PREVIEW.value
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_lesson_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
