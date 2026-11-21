"""Pydantic schemas for CSV schedule import preview, status, and atomic commit."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schedule_service.models.import_batch import ImportBatchStatus
from schedule_service.models.lesson import LessonType, WeekParity

__all__ = [
    "CsvImportBatchResponse",
    "ImportPreviewRow",
    "ImportRowError",
]


class ImportRowError(BaseModel):
    """Single validation or conflict error tied to a CSV row and field."""

    row: int = Field(..., ge=1, description="1-based CSV row number (header is row 1)")
    field: str = Field(..., description="CSV column name or 'file' for structural errors")
    code: str = Field(..., description="Machine-readable error/conflict code")
    message: str = Field(..., description="Human-readable error description")


class ImportPreviewRow(BaseModel):
    """Parsed CSV row with resolved entity IDs and per-row validation errors."""

    row: int = Field(..., ge=2, description="1-based CSV row number")
    status: Literal["valid", "error"] = Field(..., description="Row validation status")
    group_name: str = Field(default="", description="Academic group name from CSV")
    teacher_email: str = Field(default="", description="Teacher email from CSV")
    subject_code: str = Field(default="", description="Subject code or name from CSV")
    classroom_building: str = Field(default="", description="Classroom building from CSV")
    classroom_room: str = Field(default="", description="Classroom room number from CSV")
    day_of_week: int | None = Field(default=None, description="Parsed day of week (1..7)")
    slot_number: int | None = Field(default=None, description="Parsed time slot number (1..7)")
    lesson_type: LessonType | None = Field(default=None, description="Parsed lesson type")
    parity: WeekParity | None = Field(default=None, description="Parsed week parity")
    specific_date: date | None = Field(default=None, description="Parsed specific date")
    group_id: int | None = Field(default=None, description="Resolved Group ID")
    teacher_id: int | None = Field(default=None, description="Resolved Teacher ID")
    subject_id: int | None = Field(default=None, description="Resolved Subject ID")
    classroom_id: int | None = Field(default=None, description="Resolved Classroom ID")
    time_slot_id: int | None = Field(default=None, description="Resolved TimeSlot ID")
    errors: list[ImportRowError] = Field(default_factory=list, description="Errors for this row")


class CsvImportBatchResponse(BaseModel):
    """Unified response for preview, status lookup, and atomic commit confirmation."""

    batch_id: str = Field(..., description="Unique import batch identifier (UUID)")
    status: ImportBatchStatus = Field(..., description="Batch lifecycle status")
    can_commit: bool = Field(..., description="Whether this batch can currently be committed")
    already_committed: bool = Field(
        default=False,
        description="True when returning an already-committed batch (idempotent retry)",
    )
    filename: str | None = Field(default=None, description="Uploaded CSV filename")
    content_hash: str = Field(..., description="SHA-256 hex digest of uploaded CSV payload")
    total_rows: int = Field(..., ge=0, description="Total non-empty data rows in CSV")
    valid_rows: int = Field(..., ge=0, description="Count of valid conflict-free rows")
    error_rows: int = Field(..., ge=0, description="Count of rows with at least one error")
    created_count: int = Field(default=0, ge=0, description="Number of lessons created on commit")
    created_lesson_ids: list[int] = Field(
        default_factory=list,
        description="IDs of lessons created when the batch was committed",
    )
    rows: list[ImportPreviewRow] = Field(
        default_factory=list,
        description="Row-by-row preview with resolved IDs and errors",
    )
    errors: list[ImportRowError] = Field(
        default_factory=list,
        description="Flattened list of all row and conflict errors",
    )
    created_at: datetime = Field(..., description="Batch creation timestamp")
    committed_at: datetime | None = Field(default=None, description="Commit timestamp if committed")

    model_config = ConfigDict(from_attributes=True)
