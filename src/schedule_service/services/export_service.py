"""Calendar export service for generating iCalendar (.ics, RFC 5545) and CSV schedules."""

import csv
import datetime as dt
import io
from collections.abc import Sequence

from icalendar import Calendar, Event
from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot

__all__ = [
    "CSV_COLUMNS",
    "CalendarExportService",
    "DAY_NAMES_RU",
    "date_week_parity",
    "export_group_to_csv",
    "export_group_to_ics",
    "export_teacher_to_csv",
    "export_teacher_to_ics",
]

DAY_NAMES_RU: dict[int, str] = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
    7: "Воскресенье",
}

CSV_COLUMNS: list[str] = [
    "День",
    "Время",
    "Предмет",
    "Преподаватель",
    "Аудитория",
    "Тип недели",
]

LessonRow = Row[Lesson, Subject, Teacher, Group, Classroom, TimeSlot]


def date_week_parity(target_date: dt.date) -> WeekParity:
    """Return ODD_WEEK or EVEN_WEEK based on the ISO week number of ``target_date``."""
    iso_week = target_date.isocalendar().week
    return WeekParity.ODD_WEEK if iso_week % 2 == 1 else WeekParity.EVEN_WEEK


def _resolve_date_range(
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> tuple[dt.date, dt.date]:
    """Normalize optional start_date/end_date into an inclusive calendar range."""
    if start_date is None and end_date is None:
        today = dt.date.today()
        resolved_start = today - dt.timedelta(days=today.weekday())
        resolved_end = resolved_start + dt.timedelta(days=13)
    elif start_date is not None and end_date is None:
        resolved_start = start_date
        resolved_end = start_date + dt.timedelta(days=6)
    elif start_date is None and end_date is not None:
        resolved_end = end_date
        resolved_start = end_date - dt.timedelta(days=6)
    else:
        assert start_date is not None and end_date is not None
        resolved_start = start_date
        resolved_end = end_date

    if resolved_end < resolved_start:
        raise ValueError("end_date must be greater than or equal to start_date")

    return resolved_start, resolved_end


async def _fetch_lessons_for_export(
    session: AsyncSession,
    *,
    group_id: int | None = None,
    teacher_id: int | None = None,
    parity: WeekParity | None = None,
) -> Sequence[LessonRow]:
    """Fetch lessons with joined reference entities ordered by day and slot."""
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

    query = query.order_by(
        TimeSlot.day_of_week,
        TimeSlot.slot_number,
        TimeSlot.start_time,
        Lesson.id,
    )

    result = await session.execute(query)
    return result.all()


def _build_ics_calendar(
    rows: Sequence[LessonRow],
    *,
    calendar_name: str,
    start_date: dt.date,
    end_date: dt.date,
) -> bytes:
    """Build an RFC 5545 iCalendar (.ics) byte stream from lesson rows over a date range."""
    cal = Calendar()
    cal.add("prodid", "-//ScheduleService//BiGithubFlow2026//RU")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calendar_name)

    dtstamp = dt.datetime.now(dt.UTC)
    total_days = (end_date - start_date).days + 1

    for offset in range(total_days):
        current_date = start_date + dt.timedelta(days=offset)
        weekday = current_date.isoweekday()
        current_parity = date_week_parity(current_date)

        for lesson, subject, teacher, group, classroom, time_slot in rows:
            if lesson.specific_date is not None:
                if lesson.specific_date != current_date:
                    continue
            else:
                if time_slot.day_of_week != weekday:
                    continue
                if lesson.parity not in (WeekParity.ALWAYS, current_parity):
                    continue

            event = Event()
            uid = f"lesson-{lesson.id}-{current_date.isoformat()}@schedule-service"
            summary = f"{subject.name} ({lesson.lesson_type.value})"
            location = f"{classroom.building}, ауд. {classroom.room_number}"
            description = (
                f"Предмет: {subject.name}\n"
                f"Тип занятия: {lesson.lesson_type.value}\n"
                f"Преподаватель: {teacher.full_name}\n"
                f"Группа: {group.name}\n"
                f"Аудитория: {location}\n"
                f"Тип недели: {lesson.parity.value}"
            )

            dtstart = dt.datetime.combine(current_date, time_slot.start_time)
            dtend = dt.datetime.combine(current_date, time_slot.end_time)

            event.add("uid", uid)
            event.add("dtstamp", dtstamp)
            event.add("dtstart", dtstart)
            event.add("dtend", dtend)
            event.add("summary", summary)
            event.add("description", description)
            event.add("location", location)
            event.add("categories", [lesson.lesson_type.value])

            cal.add_component(event)

    return bytes(cal.to_ical())


def _build_csv_schedule(rows: Sequence[LessonRow]) -> str:
    """Build a CSV string with standard Russian schedule headers."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)

    for lesson, subject, teacher, _group, classroom, time_slot in rows:
        day_label = DAY_NAMES_RU.get(time_slot.day_of_week, str(time_slot.day_of_week))
        time_label = (
            f"{time_slot.start_time.strftime('%H:%M')}-{time_slot.end_time.strftime('%H:%M')}"
        )
        classroom_label = f"{classroom.building} {classroom.room_number}"

        writer.writerow(
            [
                day_label,
                time_label,
                subject.name,
                teacher.full_name,
                classroom_label,
                lesson.parity.value,
            ]
        )

    return buffer.getvalue()


async def export_group_to_ics(
    session: AsyncSession,
    group_id: int,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> bytes:
    """Export an academic group's schedule to iCalendar (.ics) bytes."""
    group_res = await session.execute(select(Group).where(Group.id == group_id))
    group = group_res.scalar_one_or_none()
    if group is None:
        raise LookupError(f"Group with id {group_id} not found")

    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)
    rows = await _fetch_lessons_for_export(session, group_id=group_id)
    return _build_ics_calendar(
        rows,
        calendar_name=f"Расписание группы {group.name}",
        start_date=resolved_start,
        end_date=resolved_end,
    )


async def export_group_to_csv(
    session: AsyncSession,
    group_id: int,
    parity: WeekParity | None = None,
) -> str:
    """Export an academic group's schedule to a CSV string."""
    group_res = await session.execute(select(Group).where(Group.id == group_id))
    group = group_res.scalar_one_or_none()
    if group is None:
        raise LookupError(f"Group with id {group_id} not found")

    rows = await _fetch_lessons_for_export(session, group_id=group_id, parity=parity)
    return _build_csv_schedule(rows)


async def export_teacher_to_ics(
    session: AsyncSession,
    teacher_id: int,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> bytes:
    """Export a teacher's schedule to iCalendar (.ics) bytes."""
    teacher_res = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = teacher_res.scalar_one_or_none()
    if teacher is None:
        raise LookupError(f"Teacher with id {teacher_id} not found")

    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)
    rows = await _fetch_lessons_for_export(session, teacher_id=teacher_id)
    return _build_ics_calendar(
        rows,
        calendar_name=f"Расписание преподавателя {teacher.full_name}",
        start_date=resolved_start,
        end_date=resolved_end,
    )


async def export_teacher_to_csv(
    session: AsyncSession,
    teacher_id: int,
    parity: WeekParity | None = None,
) -> str:
    """Export a teacher's schedule to a CSV string."""
    teacher_res = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = teacher_res.scalar_one_or_none()
    if teacher is None:
        raise LookupError(f"Teacher with id {teacher_id} not found")

    rows = await _fetch_lessons_for_export(session, teacher_id=teacher_id, parity=parity)
    return _build_csv_schedule(rows)


class CalendarExportService:
    """High-level service facade for exporting group and teacher schedules to ICS and CSV."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def export_group_to_ics(
        self,
        group_id: int,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
    ) -> bytes:
        """Export an academic group's schedule to iCalendar (.ics) bytes."""
        return await export_group_to_ics(
            self._session,
            group_id=group_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def export_group_to_csv(
        self,
        group_id: int,
        parity: WeekParity | None = None,
    ) -> str:
        """Export an academic group's schedule to CSV format."""
        return await export_group_to_csv(
            self._session,
            group_id=group_id,
            parity=parity,
        )

    async def export_teacher_to_ics(
        self,
        teacher_id: int,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
    ) -> bytes:
        """Export a teacher's schedule to iCalendar (.ics) bytes."""
        return await export_teacher_to_ics(
            self._session,
            teacher_id=teacher_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def export_teacher_to_csv(
        self,
        teacher_id: int,
        parity: WeekParity | None = None,
    ) -> str:
        """Export a teacher's schedule to CSV format."""
        return await export_teacher_to_csv(
            self._session,
            teacher_id=teacher_id,
            parity=parity,
        )
