"""REST API router for schedule lessons management with conflict validation."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.models.lesson_exception import LessonException
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.schemas.lesson import (
    ClassroomNestedRead,
    GroupNestedRead,
    LessonCreate,
    LessonRead,
    LessonUpdate,
    SubjectNestedRead,
    TeacherNestedRead,
    TimeSlotNestedRead,
)
from schedule_service.services.conflict_service import (
    ScheduleConflictException,
    ScheduleValidationService,
)
from schedule_service.services.occurrences import lock_schedule

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


def _conflict_response(exc: ScheduleConflictException) -> JSONResponse:
    """Convert ScheduleConflictException into an HTTP 409 Conflict JSON response."""
    payload = exc.to_dict()
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": payload,
            "message": payload["message"],
            "conflicts": payload["conflicts"],
        },
    )


async def _build_lesson_read(session: AsyncSession, lesson: Lesson) -> LessonRead:
    """Build LessonRead DTO enriched with nested related entities when present."""
    subject = await session.get(Subject, lesson.subject_id)
    teacher = await session.get(Teacher, lesson.teacher_id)
    group = await session.get(Group, lesson.group_id)
    classroom = await session.get(Classroom, lesson.classroom_id)
    time_slot = await session.get(TimeSlot, lesson.time_slot_id)

    return LessonRead(
        id=lesson.id,
        subject_id=lesson.subject_id,
        teacher_id=lesson.teacher_id,
        group_id=lesson.group_id,
        classroom_id=lesson.classroom_id,
        time_slot_id=lesson.time_slot_id,
        lesson_type=lesson.lesson_type,
        parity=lesson.parity,
        specific_date=lesson.specific_date,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        subject=SubjectNestedRead.model_validate(subject) if subject is not None else None,
        teacher=TeacherNestedRead.model_validate(teacher) if teacher is not None else None,
        group=GroupNestedRead.model_validate(group) if group is not None else None,
        classroom=(
            ClassroomNestedRead.model_validate(classroom) if classroom is not None else None
        ),
        time_slot=(TimeSlotNestedRead.model_validate(time_slot) if time_slot is not None else None),
    )


@router.get(
    "/",
    response_model=list[LessonRead],
    summary="List schedule lessons",
    description=(
        "Retrieve a paginated list of lessons with optional filtering "
        "by group, teacher, classroom, subject, time slot, lesson type, or parity."
    ),
)
@router.get(
    "",
    response_model=list[LessonRead],
    include_in_schema=False,
)
async def list_lessons(
    group_id: Annotated[int | None, Query(gt=0, description="Filter by group ID")] = None,
    teacher_id: Annotated[int | None, Query(gt=0, description="Filter by teacher ID")] = None,
    classroom_id: Annotated[int | None, Query(gt=0, description="Filter by classroom ID")] = None,
    subject_id: Annotated[int | None, Query(gt=0, description="Filter by subject ID")] = None,
    time_slot_id: Annotated[int | None, Query(gt=0, description="Filter by time slot ID")] = None,
    lesson_type: Annotated[LessonType | None, Query(description="Filter by lesson type")] = None,
    parity: Annotated[WeekParity | None, Query(description="Filter by week parity")] = None,
    specific_date: Annotated[
        date | None, Query(description="Filter by specific one-off date")
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Max number of records to return")
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[LessonRead]:
    """List lessons with optional filtering and pagination."""
    query = select(Lesson)
    if group_id is not None:
        query = query.where(Lesson.group_id == group_id)
    if teacher_id is not None:
        query = query.where(Lesson.teacher_id == teacher_id)
    if classroom_id is not None:
        query = query.where(Lesson.classroom_id == classroom_id)
    if subject_id is not None:
        query = query.where(Lesson.subject_id == subject_id)
    if time_slot_id is not None:
        query = query.where(Lesson.time_slot_id == time_slot_id)
    if lesson_type is not None:
        query = query.where(Lesson.lesson_type == lesson_type)
    if parity is not None:
        query = query.where(Lesson.parity == parity)
    if specific_date is not None:
        query = query.where(Lesson.specific_date == specific_date)

    query = query.order_by(Lesson.id).offset(skip).limit(limit)
    result = await session.execute(query)
    lessons = list(result.scalars().all())
    return [await _build_lesson_read(session, lesson) for lesson in lessons]


@router.get(
    "/{lesson_id}",
    response_model=LessonRead,
    summary="Get lesson by ID",
    description="Retrieve detailed information about a specific scheduled lesson.",
    responses={
        404: {"description": "Lesson not found"},
    },
)
async def get_lesson(
    lesson_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> LessonRead:
    """Get lesson details by ID."""
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson with id {lesson_id} not found",
        )
    return await _build_lesson_read(session, lesson)


@router.post(
    "/",
    response_model=LessonRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create lesson",
    description=(
        "Schedule a new lesson after validating teacher, classroom, group occupancy "
        "and classroom seating capacity."
    ),
    responses={
        201: {"description": "Lesson successfully scheduled"},
        409: {"description": "Schedule conflict detected"},
        422: {"description": "Validation error"},
    },
)
@router.post(
    "",
    response_model=LessonRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_lesson(
    lesson_in: LessonCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> LessonRead | JSONResponse:
    """Create a new scheduled lesson with conflict detection."""
    await lock_schedule(session)
    try:
        await ScheduleValidationService.validate_lesson(session, lesson_in)
    except ScheduleConflictException as exc:
        return _conflict_response(exc)

    lesson = Lesson(**lesson_in.model_dump())
    session.add(lesson)
    try:
        await session.flush()
        await session.refresh(lesson)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to create lesson due to a database integrity constraint",
        ) from err

    return await _build_lesson_read(session, lesson)


@router.put(
    "/{lesson_id}",
    response_model=LessonRead,
    summary="Update lesson",
    description=(
        "Update an existing scheduled lesson after validating all conflict rules "
        "(excluding the lesson being updated from self-conflict)."
    ),
    responses={
        200: {"description": "Lesson successfully updated"},
        404: {"description": "Lesson not found"},
        409: {"description": "Schedule conflict detected"},
        422: {"description": "Validation error"},
    },
)
async def update_lesson(
    lesson_id: int,
    lesson_in: LessonUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> LessonRead | JSONResponse:
    """Update an existing scheduled lesson with conflict detection."""
    await lock_schedule(session)
    await _reject_exception_lesson(session, lesson_id)
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson with id {lesson_id} not found",
        )

    update_data = lesson_in.model_dump(exclude_unset=True)
    merged_data: dict[str, Any] = {
        "subject_id": update_data.get("subject_id", lesson.subject_id),
        "teacher_id": update_data.get("teacher_id", lesson.teacher_id),
        "group_id": update_data.get("group_id", lesson.group_id),
        "classroom_id": update_data.get("classroom_id", lesson.classroom_id),
        "time_slot_id": update_data.get("time_slot_id", lesson.time_slot_id),
        "lesson_type": update_data.get("lesson_type", lesson.lesson_type),
        "parity": update_data.get("parity", lesson.parity),
        "specific_date": update_data.get("specific_date", lesson.specific_date),
    }

    try:
        await ScheduleValidationService.validate_lesson(
            session,
            merged_data,
            exclude_lesson_id=lesson_id,
        )
    except ScheduleConflictException as exc:
        return _conflict_response(exc)

    for field, value in update_data.items():
        setattr(lesson, field, value)

    try:
        await session.flush()
        await session.refresh(lesson)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to update lesson due to a database integrity constraint",
        ) from err

    return await _build_lesson_read(session, lesson)


@router.delete(
    "/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete lesson",
    description="Cancel and permanently delete a scheduled lesson by its ID.",
    responses={
        204: {"description": "Lesson successfully deleted"},
        404: {"description": "Lesson not found"},
    },
)
async def delete_lesson(
    lesson_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a scheduled lesson by ID."""
    await lock_schedule(session)
    await _reject_exception_lesson(session, lesson_id)
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson with id {lesson_id} not found",
        )

    await session.delete(lesson)
    await session.flush()


async def _reject_exception_lesson(session: AsyncSession, lesson_id: int) -> None:
    """Avoid silently changing or deleting recorded exceptions."""
    query = select(LessonException.id).where(
        (LessonException.lesson_id == lesson_id)
        | (LessonException.replacement_lesson_id == lesson_id)
    )
    if (await session.execute(query)).first() is not None:
        raise HTTPException(status_code=409, detail="Lesson has an occurrence exception")
