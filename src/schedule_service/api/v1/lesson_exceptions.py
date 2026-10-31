"""Cancel or move an individual occurrence of a lesson."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from schedule_service.core.auth import CurrentUser, SessionDep
from schedule_service.models.classroom import Classroom
from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.models.lesson_exception import LessonException
from schedule_service.models.time_slot import TimeSlot
from schedule_service.services.conflict_service import ScheduleConflictException, validate_lesson
from schedule_service.services.occurrences import lock_schedule, week_parity

router = APIRouter()


class ExceptionCreate(BaseModel):
    """The original occurrence and, for a move, its destination."""

    occurrence_date: date
    action: Literal["cancel", "move"]
    reason: str = Field(min_length=1, max_length=2000)
    target_date: date | None = None
    time_slot_id: int | None = Field(default=None, gt=0)
    classroom_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_destination(self) -> "ExceptionCreate":
        values = (self.target_date, self.time_slot_id, self.classroom_id)
        if self.action == "move" and any(value is None for value in values):
            raise ValueError("A move requires target_date, time_slot_id and classroom_id")
        if self.action == "cancel" and any(value is not None for value in values):
            raise ValueError("A cancellation cannot have a destination")
        if not self.reason.strip():
            raise ValueError("A reason is required")
        return self


class ExceptionRead(BaseModel):
    id: int
    lesson_id: int
    occurrence_date: date
    action: str
    replacement_lesson_id: int | None
    author_id: int
    reason: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


@router.post("/{lesson_id}/exceptions", response_model=ExceptionRead, status_code=201)
async def create_exception(
    lesson_id: int,
    data: ExceptionCreate,
    session: SessionDep,
    user: CurrentUser,
) -> LessonException:
    """Record one immutable exception; identical retries return the same record."""
    await lock_schedule(session)
    lesson = await session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    replacement_query = select(LessonException.id).where(
        LessonException.replacement_lesson_id == lesson_id
    )
    if (await session.execute(replacement_query)).first() is not None:
        raise HTTPException(status_code=409, detail="Cannot change a replacement lesson")
    query = select(LessonException).where(
        LessonException.lesson_id == lesson_id,
        LessonException.occurrence_date == data.occurrence_date,
    )
    existing = (await session.execute(query)).scalar_one_or_none()
    if existing is not None:
        replacement = None
        if existing.replacement_lesson_id is not None:
            replacement = await session.get(Lesson, existing.replacement_lesson_id)
        same = existing.action == data.action and existing.reason == data.reason
        if data.action == "move":
            same = same and replacement is not None
            if replacement is not None:
                same = same and replacement.specific_date == data.target_date
                same = same and replacement.time_slot_id == data.time_slot_id
                same = same and replacement.classroom_id == data.classroom_id
        if same:
            return existing
        raise HTTPException(status_code=409, detail="Occurrence already changed")

    slot = await session.get(TimeSlot, lesson.time_slot_id)
    assert slot is not None
    if lesson.specific_date is not None:
        valid = lesson.specific_date == data.occurrence_date
        valid = valid and slot.day_of_week == data.occurrence_date.isoweekday()
    else:
        valid = slot.day_of_week == data.occurrence_date.isoweekday()
        valid = valid and lesson.parity in (WeekParity.ALWAYS, week_parity(data.occurrence_date))
    if not valid:
        raise HTTPException(status_code=422, detail="No lesson occurrence on this date")

    replacement_id = None
    if data.action == "move":
        assert data.target_date is not None
        assert data.time_slot_id is not None
        assert data.classroom_id is not None
        target_slot = await session.get(TimeSlot, data.time_slot_id)
        classroom = await session.get(Classroom, data.classroom_id)
        if target_slot is None or classroom is None:
            raise HTTPException(status_code=404, detail="Destination slot or classroom not found")
        if target_slot.day_of_week != data.target_date.isoweekday():
            raise HTTPException(status_code=422, detail="Target date does not match slot weekday")
        replacement = Lesson(
            subject_id=lesson.subject_id,
            teacher_id=lesson.teacher_id,
            group_id=lesson.group_id,
            classroom_id=data.classroom_id,
            time_slot_id=data.time_slot_id,
            lesson_type=lesson.lesson_type,
            parity=week_parity(data.target_date),
            specific_date=data.target_date,
        )
        excluded = None
        if data.target_date == data.occurrence_date:
            excluded = lesson.id
        try:
            await validate_lesson(session, replacement, exclude_lesson_id=excluded)
        except ScheduleConflictException as exc:
            raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
        session.add(replacement)
        await session.flush()
        replacement_id = replacement.id

    exception = LessonException(
        lesson_id=lesson.id,
        occurrence_date=data.occurrence_date,
        action=data.action,
        replacement_lesson_id=replacement_id,
        author_id=user.id,
        reason=data.reason,
    )
    session.add(exception)
    await session.flush()
    await session.refresh(exception)
    return exception
