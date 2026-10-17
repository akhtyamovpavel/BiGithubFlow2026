"""REST API router for viewing group and teacher schedules."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.schemas.lesson import (
    ClassroomNestedRead,
    GroupNestedRead,
    LessonRead,
    SubjectNestedRead,
    TeacherNestedRead,
    TimeSlotNestedRead,
)
from schedule_service.schemas.schedule import (
    DaySchedule,
    GroupScheduleResponse,
    TeacherScheduleResponse,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


async def _fetch_days_schedule(
    session: AsyncSession,
    *,
    group_id: int | None = None,
    teacher_id: int | None = None,
    parity: WeekParity | None = None,
    target_date: dt.date | None = None,
) -> list[DaySchedule]:
    """Fetch lessons with joined entities and group by day of the week (1..6)."""
    query = (
        select(Lesson, Subject, Teacher, Group, Classroom, TimeSlot)
        .join(Subject, Lesson.subject_id == Subject.id)
        .join(Teacher, Lesson.teacher_id == Teacher.id)
        .join(Group, Lesson.group_id == Group.id)
        .join(Classroom, Lesson.classroom_id == Classroom.id)
        .join(TimeSlot, Lesson.time_slot_id == TimeSlot.id)
    )

    if group_id is not None:
        query = query.where(Lesson.group_id == group_id)
    if teacher_id is not None:
        query = query.where(Lesson.teacher_id == teacher_id)

    if parity in (WeekParity.ODD_WEEK, WeekParity.EVEN_WEEK):
        query = query.where(Lesson.parity.in_([parity, WeekParity.ALWAYS]))
    elif parity == WeekParity.ALWAYS:
        query = query.where(Lesson.parity == WeekParity.ALWAYS)

    if target_date is not None:
        weekday = target_date.isoweekday()
        query = query.where(
            or_(
                Lesson.specific_date == target_date,
                and_(
                    Lesson.specific_date.is_(None),
                    TimeSlot.day_of_week == weekday,
                ),
            )
        )

    query = query.order_by(
        TimeSlot.day_of_week,
        TimeSlot.slot_number,
        TimeSlot.start_time,
        Lesson.id,
    )

    result = await session.execute(query)
    days_map: dict[int, list[LessonRead]] = {day: [] for day in range(1, 7)}

    for lesson, subject, teacher, group, classroom, time_slot in result.all():
        lesson_read = LessonRead(
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
            subject=SubjectNestedRead.model_validate(subject),
            teacher=TeacherNestedRead.model_validate(teacher),
            group=GroupNestedRead.model_validate(group),
            classroom=ClassroomNestedRead.model_validate(classroom),
            time_slot=TimeSlotNestedRead.model_validate(time_slot),
        )
        day = time_slot.day_of_week
        if day not in days_map:
            days_map[day] = []
        days_map[day].append(lesson_read)

    return [DaySchedule(day_of_week=day, lessons=days_map[day]) for day in sorted(days_map.keys())]


@router.get(
    "/group/{group_id}",
    response_model=GroupScheduleResponse,
    summary="Get weekly schedule for a group",
    description=(
        "Retrieve weekly schedule for a specific academic group grouped by days of the week "
        "(1..6) and ordered by time slot, with optional filtering by week parity and date."
    ),
    responses={
        404: {"description": "Academic group not found"},
    },
)
async def get_group_schedule(
    group_id: int,
    parity: Annotated[
        WeekParity | None,
        Query(description="Filter by week parity (ODD_WEEK, EVEN_WEEK, ALWAYS)"),
    ] = None,
    target_date: Annotated[
        dt.date | None,
        Query(alias="date", description="Filter by specific calendar date (YYYY-MM-DD)"),
    ] = None,
    session: SessionDep = None,  # type: ignore[assignment]
) -> GroupScheduleResponse:
    """Get structured weekly schedule for an academic group."""
    group_result = await session.execute(select(Group).where(Group.id == group_id))
    group = group_result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with id {group_id} not found",
        )

    days = await _fetch_days_schedule(
        session,
        group_id=group_id,
        parity=parity,
        target_date=target_date,
    )

    return GroupScheduleResponse(
        group_id=group.id,
        group=GroupNestedRead.model_validate(group),
        parity=parity,
        date=target_date,
        days=days,
    )


@router.get(
    "/teacher/{teacher_id}",
    response_model=TeacherScheduleResponse,
    summary="Get weekly schedule for a teacher",
    description=(
        "Retrieve weekly schedule for a specific teacher grouped by days of the week "
        "(1..6) and ordered by time slot, with optional filtering by week parity and date."
    ),
    responses={
        404: {"description": "Teacher not found"},
    },
)
async def get_teacher_schedule(
    teacher_id: int,
    parity: Annotated[
        WeekParity | None,
        Query(description="Filter by week parity (ODD_WEEK, EVEN_WEEK, ALWAYS)"),
    ] = None,
    target_date: Annotated[
        dt.date | None,
        Query(alias="date", description="Filter by specific calendar date (YYYY-MM-DD)"),
    ] = None,
    session: SessionDep = None,  # type: ignore[assignment]
) -> TeacherScheduleResponse:
    """Get structured weekly schedule for a teacher."""
    teacher_result = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = teacher_result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with id {teacher_id} not found",
        )

    days = await _fetch_days_schedule(
        session,
        teacher_id=teacher_id,
        parity=parity,
        target_date=target_date,
    )

    return TeacherScheduleResponse(
        teacher_id=teacher.id,
        teacher=TeacherNestedRead.model_validate(teacher),
        parity=parity,
        date=target_date,
        days=days,
    )
