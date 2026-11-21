"""CSV schedule import service: template, parsing, validation, preview, and atomic commit."""

import csv
import datetime as dt
import hashlib
import io
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.import_batch import ImportBatchStatus, ScheduleImportBatch
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.schemas.csv_import import (
    CsvImportBatchResponse,
    ImportPreviewRow,
    ImportRowError,
)
from schedule_service.schemas.lesson import LessonCreate
from schedule_service.services.conflict_service import (
    ConflictType,
    ScheduleConflictException,
    ScheduleValidationService,
    parities_overlap,
)
from schedule_service.services.occurrences import lock_schedule

logger = logging.getLogger("schedule_service.csv_import")

CSV_IMPORT_COLUMNS: tuple[str, ...] = (
    "group_name",
    "teacher_email",
    "subject_code",
    "classroom_building",
    "classroom_room",
    "day_of_week",
    "slot_number",
    "lesson_type",
    "parity",
    "specific_date",
)
REQUIRED_CSV_COLUMNS: frozenset[str] = frozenset(CSV_IMPORT_COLUMNS[:-2])
CSV_IMPORT_MAX_BYTES = 1 * 1024 * 1024
CSV_IMPORT_MAX_ROWS = 500
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONFLICT_FIELD_MAP: dict[ConflictType, str] = {
    ConflictType.TEACHER_BUSY: "teacher_email",
    ConflictType.CLASSROOM_BUSY: "classroom_room",
    ConflictType.CAPACITY_EXCEEDED: "classroom_room",
    ConflictType.GROUP_BUSY: "group_name",
}


class ImportPayloadTooLargeError(ValueError):
    """Raised when uploaded CSV exceeds byte size limit."""


class ImportFormatError(ValueError):
    """Raised when CSV encoding, header, or row count is invalid."""


class ImportBatchNotFoundError(LookupError):
    """Raised when batch_id does not exist."""


class ImportConflictError(Exception):
    """Raised when batch cannot be committed or idempotency key conflicts."""

    def __init__(self, message: str, batch: CsvImportBatchResponse | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.batch = batch


@dataclass(frozen=True, slots=True)
class _ResolvedCandidate:
    row: int
    lesson: LessonCreate


def build_csv_template() -> str:
    """Return UTF-8 CSV template with header and one example row matching demo data."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_IMPORT_COLUMNS)
    writer.writerow(
        [
            "Б05-401",
            "s.ivanov@phystech.edu",
            "MATH-101",
            "Главный корпус",
            "115",
            "1",
            "1",
            "LECTURE",
            "ALWAYS",
            "",
        ]
    )
    return buf.getvalue()


def parse_csv_bytes(raw_bytes: bytes) -> list[dict[str, Any]]:
    """Decode and parse CSV bytes enforcing size, header, and row count limits."""
    if len(raw_bytes) > CSV_IMPORT_MAX_BYTES:
        raise ImportPayloadTooLargeError(
            f"CSV file exceeds maximum allowed size of {CSV_IMPORT_MAX_BYTES} bytes"
        )
    if not raw_bytes.strip():
        raise ImportFormatError("CSV file is empty")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise ImportFormatError("CSV file must be valid UTF-8") from err

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFormatError("CSV header row is missing")
    normalized_headers = [h.strip() for h in reader.fieldnames if h is not None]
    reader.fieldnames = normalized_headers

    missing = sorted(REQUIRED_CSV_COLUMNS - set(normalized_headers))
    if missing:
        raise ImportFormatError(f"Missing required CSV columns: {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    for row_num, raw in enumerate(reader, start=2):
        if None in raw:
            raise ImportFormatError(f"Row {row_num} has extra columns beyond header")
        cleaned = {col: (raw.get(col) or "").strip() for col in CSV_IMPORT_COLUMNS}
        if not any(cleaned.values()):
            continue
        rows.append({"row": row_num, **cleaned})
        if len(rows) > CSV_IMPORT_MAX_ROWS:
            raise ImportFormatError(
                f"CSV exceeds maximum allowed limit of {CSV_IMPORT_MAX_ROWS} rows"
            )

    if not rows:
        raise ImportFormatError("CSV file contains no data rows")
    return rows


def _parse_int_range(
    raw: str, row: int, field: str, low: int, high: int, errors: list[ImportRowError]
) -> int | None:
    if not raw:
        errors.append(ImportRowError(row=row, field=field, code="REQUIRED", message="Required"))
        return None
    try:
        val = int(raw)
    except ValueError:
        errors.append(
            ImportRowError(row=row, field=field, code="INVALID_INT", message=f"Invalid {field}")
        )
        return None
    if not (low <= val <= high):
        errors.append(
            ImportRowError(
                row=row,
                field=field,
                code="OUT_OF_RANGE",
                message=f"{field} must be between {low} and {high}",
            )
        )
        return None
    return val


async def _load_reference_maps(
    session: AsyncSession,
) -> tuple[
    dict[str, Group],
    dict[str, Teacher],
    dict[str, list[Subject]],
    dict[str, list[Subject]],
    dict[tuple[str, str], Classroom],
    dict[tuple[int, int], TimeSlot],
]:
    groups = {g.name: g for g in (await session.execute(select(Group))).scalars().all()}
    teachers = {
        t.email.lower(): t for t in (await session.execute(select(Teacher))).scalars().all()
    }
    subj_by_code: dict[str, list[Subject]] = {}
    subj_by_name: dict[str, list[Subject]] = {}
    for subj in (await session.execute(select(Subject))).scalars().all():
        if subj.code:
            subj_by_code.setdefault(subj.code, []).append(subj)
        subj_by_name.setdefault(subj.name, []).append(subj)
    classrooms = {
        (c.building, c.room_number): c
        for c in (await session.execute(select(Classroom))).scalars().all()
    }
    slots = {
        (s.day_of_week, s.slot_number): s
        for s in (await session.execute(select(TimeSlot))).scalars().all()
    }
    return groups, teachers, subj_by_code, subj_by_name, classrooms, slots


def _resolve_subject(
    key: str,
    by_code: dict[str, list[Subject]],
    by_name: dict[str, list[Subject]],
    row: int,
    errors: list[ImportRowError],
) -> Subject | None:
    if not key:
        errors.append(
            ImportRowError(row=row, field="subject_code", code="REQUIRED", message="Required")
        )
        return None
    matches = by_code.get(key) or by_name.get(key) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        errors.append(
            ImportRowError(
                row=row,
                field="subject_code",
                code="AMBIGUOUS_SUBJECT",
                message=f"Multiple subjects match '{key}'",
            )
        )
        return None
    errors.append(
        ImportRowError(
            row=row,
            field="subject_code",
            code="UNKNOWN_SUBJECT",
            message=f"Subject '{key}' not found",
        )
    )
    return None


def _check_intra_file_conflicts(
    resolved: list[_ResolvedCandidate],
    preview_by_row: dict[int, ImportPreviewRow],
) -> None:
    for idx, current in enumerate(resolved):
        cur = current.lesson
        row_obj = preview_by_row[current.row]
        for prev in resolved[:idx]:
            other = prev.lesson
            if cur.time_slot_id != other.time_slot_id:
                continue
            if not parities_overlap(cur.parity, other.parity):
                continue
            if (
                cur.specific_date is not None
                and other.specific_date is not None
                and cur.specific_date != other.specific_date
            ):
                continue
            if cur.teacher_id == other.teacher_id:
                row_obj.errors.append(
                    ImportRowError(
                        row=current.row,
                        field="teacher_email",
                        code="FILE_TEACHER_CONFLICT",
                        message=f"Teacher conflict with CSV row {prev.row}",
                    )
                )
            if cur.classroom_id == other.classroom_id:
                row_obj.errors.append(
                    ImportRowError(
                        row=current.row,
                        field="classroom_room",
                        code="FILE_CLASSROOM_CONFLICT",
                        message=f"Classroom conflict with CSV row {prev.row}",
                    )
                )
            if cur.group_id == other.group_id:
                row_obj.errors.append(
                    ImportRowError(
                        row=current.row,
                        field="group_name",
                        code="FILE_GROUP_CONFLICT",
                        message=f"Group conflict with CSV row {prev.row}",
                    )
                )
        if row_obj.errors:
            row_obj.status = "error"


async def validate_csv_rows(
    session: AsyncSession,
    raw_rows: list[dict[str, Any]],
) -> tuple[list[ImportPreviewRow], list[ImportRowError], list[LessonCreate]]:
    """Validate parsed rows against references, intra-file collisions, and live DB state."""
    groups, teachers, subj_by_code, subj_by_name, classrooms, slots = await _load_reference_maps(
        session
    )
    preview_rows: list[ImportPreviewRow] = []
    preview_by_row: dict[int, ImportPreviewRow] = {}
    resolved: list[_ResolvedCandidate] = []

    for item in raw_rows:
        row_num = int(item["row"])
        row_errors: list[ImportRowError] = []

        group_name = str(item["group_name"])
        teacher_email = str(item["teacher_email"])
        subject_code = str(item["subject_code"])
        building = str(item["classroom_building"])
        room = str(item["classroom_room"])

        group = groups.get(group_name)
        if not group_name:
            row_errors.append(
                ImportRowError(row=row_num, field="group_name", code="REQUIRED", message="Required")
            )
        elif group is None:
            row_errors.append(
                ImportRowError(
                    row=row_num,
                    field="group_name",
                    code="UNKNOWN_GROUP",
                    message=f"Group '{group_name}' not found",
                )
            )

        teacher = teachers.get(teacher_email.lower())
        if not teacher_email:
            row_errors.append(
                ImportRowError(
                    row=row_num, field="teacher_email", code="REQUIRED", message="Required"
                )
            )
        elif teacher is None:
            row_errors.append(
                ImportRowError(
                    row=row_num,
                    field="teacher_email",
                    code="UNKNOWN_TEACHER",
                    message=f"Teacher '{teacher_email}' not found",
                )
            )

        subject = _resolve_subject(subject_code, subj_by_code, subj_by_name, row_num, row_errors)

        classroom = classrooms.get((building, room))
        if not building:
            row_errors.append(
                ImportRowError(
                    row=row_num, field="classroom_building", code="REQUIRED", message="Required"
                )
            )
        if not room:
            row_errors.append(
                ImportRowError(
                    row=row_num, field="classroom_room", code="REQUIRED", message="Required"
                )
            )
        if building and room and classroom is None:
            row_errors.append(
                ImportRowError(
                    row=row_num,
                    field="classroom_room",
                    code="UNKNOWN_CLASSROOM",
                    message=f"Classroom '{building} {room}' not found",
                )
            )

        day_of_week = _parse_int_range(
            str(item["day_of_week"]), row_num, "day_of_week", 1, 7, row_errors
        )
        slot_number = _parse_int_range(
            str(item["slot_number"]), row_num, "slot_number", 1, 7, row_errors
        )

        time_slot: TimeSlot | None = None
        if day_of_week is not None and slot_number is not None:
            time_slot = slots.get((day_of_week, slot_number))
            if time_slot is None:
                row_errors.append(
                    ImportRowError(
                        row=row_num,
                        field="slot_number",
                        code="UNKNOWN_TIME_SLOT",
                        message=f"TimeSlot day={day_of_week} slot={slot_number} not found",
                    )
                )

        raw_type = str(item["lesson_type"]).upper()
        lesson_type: LessonType | None = None
        if not raw_type:
            row_errors.append(
                ImportRowError(
                    row=row_num, field="lesson_type", code="REQUIRED", message="Required"
                )
            )
        else:
            try:
                lesson_type = LessonType(raw_type)
            except ValueError:
                row_errors.append(
                    ImportRowError(
                        row=row_num,
                        field="lesson_type",
                        code="INVALID_LESSON_TYPE",
                        message=f"Invalid lesson_type '{raw_type}'",
                    )
                )

        raw_parity = str(item["parity"]).upper()
        parity: WeekParity | None = WeekParity.ALWAYS
        if raw_parity:
            try:
                parity = WeekParity(raw_parity)
            except ValueError:
                parity = None
                row_errors.append(
                    ImportRowError(
                        row=row_num,
                        field="parity",
                        code="INVALID_PARITY",
                        message=f"Invalid parity '{raw_parity}'",
                    )
                )

        raw_date = str(item["specific_date"])
        specific_date: dt.date | None = None
        if raw_date:
            if not _ISO_DATE_RE.match(raw_date):
                row_errors.append(
                    ImportRowError(
                        row=row_num,
                        field="specific_date",
                        code="INVALID_DATE",
                        message=f"Date '{raw_date}' must use YYYY-MM-DD format",
                    )
                )
            else:
                try:
                    specific_date = dt.date.fromisoformat(raw_date)
                except ValueError:
                    row_errors.append(
                        ImportRowError(
                            row=row_num,
                            field="specific_date",
                            code="INVALID_DATE",
                            message=f"Invalid calendar date '{raw_date}'",
                        )
                    )
                else:
                    if day_of_week is not None and specific_date.isoweekday() != day_of_week:
                        row_errors.append(
                            ImportRowError(
                                row=row_num,
                                field="specific_date",
                                code="DATE_WEEKDAY_MISMATCH",
                                message=(
                                    f"Date {raw_date} is weekday {specific_date.isoweekday()}, "
                                    f"expected {day_of_week}"
                                ),
                            )
                        )

        preview_row = ImportPreviewRow(
            row=row_num,
            status="error" if row_errors else "valid",
            group_name=group_name,
            teacher_email=teacher_email,
            subject_code=subject_code,
            classroom_building=building,
            classroom_room=room,
            day_of_week=day_of_week,
            slot_number=slot_number,
            lesson_type=lesson_type,
            parity=parity,
            specific_date=specific_date,
            group_id=group.id if group else None,
            teacher_id=teacher.id if teacher else None,
            subject_id=subject.id if subject else None,
            classroom_id=classroom.id if classroom else None,
            time_slot_id=time_slot.id if time_slot else None,
            errors=row_errors,
        )
        preview_rows.append(preview_row)
        preview_by_row[row_num] = preview_row

        if (
            not row_errors
            and group is not None
            and teacher is not None
            and subject is not None
            and classroom is not None
            and time_slot is not None
            and lesson_type is not None
            and parity is not None
        ):
            resolved.append(
                _ResolvedCandidate(
                    row=row_num,
                    lesson=LessonCreate(
                        subject_id=subject.id,
                        teacher_id=teacher.id,
                        group_id=group.id,
                        classroom_id=classroom.id,
                        time_slot_id=time_slot.id,
                        lesson_type=lesson_type,
                        parity=parity,
                        specific_date=specific_date,
                    ),
                )
            )

    _check_intra_file_conflicts(resolved, preview_by_row)

    for candidate in resolved:
        row_obj = preview_by_row[candidate.row]
        try:
            await ScheduleValidationService.validate_lesson(session, candidate.lesson)
        except ScheduleConflictException as exc:
            for conflict in exc.conflicts:
                row_obj.errors.append(
                    ImportRowError(
                        row=candidate.row,
                        field=_CONFLICT_FIELD_MAP[conflict.conflict_type],
                        code=conflict.conflict_type.value,
                        message=conflict.message,
                    )
                )
            row_obj.status = "error"

    all_errors = [err for row in preview_rows for err in row.errors]
    valid_candidates = [c.lesson for c in resolved if preview_by_row[c.row].status == "valid"]
    return preview_rows, all_errors, valid_candidates


def _to_response(
    batch: ScheduleImportBatch,
    *,
    rows: list[ImportPreviewRow],
    errors: list[ImportRowError],
    already_committed: bool = False,
) -> CsvImportBatchResponse:
    status_enum = ImportBatchStatus(batch.status)
    lesson_ids: list[int] = json.loads(batch.created_lesson_ids_json)
    return CsvImportBatchResponse(
        batch_id=batch.batch_id,
        status=status_enum,
        can_commit=status_enum == ImportBatchStatus.PREVIEW
        and batch.total_rows > 0
        and batch.error_rows == 0,
        already_committed=already_committed,
        filename=batch.filename,
        content_hash=batch.content_hash,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        error_rows=batch.error_rows,
        created_count=batch.created_count,
        created_lesson_ids=lesson_ids,
        rows=rows,
        errors=errors,
        created_at=batch.created_at,
        committed_at=batch.committed_at,
    )


async def _committed_lessons_still_exist(session: AsyncSession, batch: ScheduleImportBatch) -> bool:
    ids: list[int] = json.loads(batch.created_lesson_ids_json)
    if not ids:
        return False
    res = await session.execute(select(Lesson.id).where(Lesson.id.in_(ids)).limit(1))
    return res.scalar_one_or_none() is not None


async def preview_csv_import(
    session: AsyncSession,
    *,
    raw_bytes: bytes,
    filename: str | None,
    created_by: str,
    idempotency_key: str | None = None,
) -> CsvImportBatchResponse:
    """Parse, validate, and persist a preview batch with idempotency protection."""
    raw_rows = parse_csv_bytes(raw_bytes)
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    if idempotency_key:
        existing_key_batch = (
            await session.execute(
                select(ScheduleImportBatch).where(
                    ScheduleImportBatch.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing_key_batch is not None:
            if existing_key_batch.content_hash != content_hash:
                raise ImportConflictError(
                    "Idempotency-Key was already used with a different CSV file"
                )
            return await get_import_batch(session, batch_id=existing_key_batch.batch_id)

    existing_committed = (
        await session.execute(
            select(ScheduleImportBatch)
            .where(
                ScheduleImportBatch.content_hash == content_hash,
                ScheduleImportBatch.status == ImportBatchStatus.COMMITTED.value,
            )
            .order_by(ScheduleImportBatch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_committed is not None and await _committed_lessons_still_exist(
        session, existing_committed
    ):
        return _to_response(existing_committed, rows=[], errors=[], already_committed=True)

    preview_rows, errors, _ = await validate_csv_rows(session, raw_rows)
    valid_count = sum(1 for r in preview_rows if r.status == "valid")
    error_count = len(preview_rows) - valid_count

    existing_preview = (
        await session.execute(
            select(ScheduleImportBatch)
            .where(
                ScheduleImportBatch.content_hash == content_hash,
                ScheduleImportBatch.status == ImportBatchStatus.PREVIEW.value,
            )
            .order_by(ScheduleImportBatch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing_preview is not None and (
        idempotency_key is None or existing_preview.idempotency_key == idempotency_key
    ):
        batch = existing_preview
        batch.filename = filename or batch.filename
        batch.total_rows = len(preview_rows)
        batch.valid_rows = valid_count
        batch.error_rows = error_count
        batch.payload_json = json.dumps(raw_rows, ensure_ascii=False)
        batch.errors_json = json.dumps([e.model_dump() for e in errors], ensure_ascii=False)
        await session.flush()
        await session.refresh(batch)
        return _to_response(batch, rows=preview_rows, errors=errors)

    batch = ScheduleImportBatch(
        batch_id=str(uuid.uuid4()),
        content_hash=content_hash,
        idempotency_key=idempotency_key,
        filename=filename,
        created_by=created_by,
        status=ImportBatchStatus.PREVIEW.value,
        total_rows=len(preview_rows),
        valid_rows=valid_count,
        error_rows=error_count,
        payload_json=json.dumps(raw_rows, ensure_ascii=False),
        errors_json=json.dumps([e.model_dump() for e in errors], ensure_ascii=False),
    )
    session.add(batch)
    await session.flush()
    await session.refresh(batch)
    return _to_response(batch, rows=preview_rows, errors=errors)


async def get_import_batch(session: AsyncSession, *, batch_id: str) -> CsvImportBatchResponse:
    """Retrieve batch state safely after connection loss (re-validates live previews)."""
    batch = (
        await session.execute(
            select(ScheduleImportBatch).where(ScheduleImportBatch.batch_id == batch_id)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise ImportBatchNotFoundError(f"Import batch '{batch_id}' not found")

    if batch.status == ImportBatchStatus.COMMITTED.value:
        return _to_response(batch, rows=[], errors=[], already_committed=True)

    raw_rows: list[dict[str, Any]] = json.loads(batch.payload_json)
    preview_rows, errors, _ = await validate_csv_rows(session, raw_rows)
    batch.valid_rows = sum(1 for r in preview_rows if r.status == "valid")
    batch.error_rows = len(preview_rows) - batch.valid_rows
    batch.errors_json = json.dumps([e.model_dump() for e in errors], ensure_ascii=False)
    await session.flush()
    return _to_response(batch, rows=preview_rows, errors=errors)


async def confirm_csv_import(session: AsyncSession, *, batch_id: str) -> CsvImportBatchResponse:
    """Re-validate under schedule lock and atomically commit all lessons in one transaction."""
    await lock_schedule(session)

    batch = (
        await session.execute(
            select(ScheduleImportBatch).where(ScheduleImportBatch.batch_id == batch_id)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise ImportBatchNotFoundError(f"Import batch '{batch_id}' not found")

    if batch.status == ImportBatchStatus.COMMITTED.value:
        return _to_response(batch, rows=[], errors=[], already_committed=True)

    raw_rows: list[dict[str, Any]] = json.loads(batch.payload_json)
    preview_rows, errors, candidates = await validate_csv_rows(session, raw_rows)
    batch.valid_rows = sum(1 for r in preview_rows if r.status == "valid")
    batch.error_rows = len(preview_rows) - batch.valid_rows
    batch.errors_json = json.dumps([e.model_dump() for e in errors], ensure_ascii=False)

    if errors or len(candidates) != len(raw_rows):
        await session.flush()
        response = _to_response(batch, rows=preview_rows, errors=errors)
        logger.warning(
            "CSV import confirm rejected due to validation/conflict errors",
            extra={
                "event": "schedule_csv_import_rejected",
                "batch_id": batch.batch_id,
                "error_count": len(errors),
            },
        )
        raise ImportConflictError(
            "CSV import batch contains validation or conflict errors", response
        )

    created_lessons = [Lesson(**candidate.model_dump()) for candidate in candidates]
    session.add_all(created_lessons)
    await session.flush()

    created_ids = [lesson.id for lesson in created_lessons]
    batch.status = ImportBatchStatus.COMMITTED.value
    batch.created_count = len(created_ids)
    batch.created_lesson_ids_json = json.dumps(created_ids)
    batch.committed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    await session.refresh(batch)

    logger.info(
        "CSV schedule import committed",
        extra={
            "event": "schedule_csv_import_committed",
            "batch_id": batch.batch_id,
            "created_count": batch.created_count,
            "created_by": batch.created_by,
        },
    )
    return _to_response(batch, rows=preview_rows, errors=[], already_committed=False)
