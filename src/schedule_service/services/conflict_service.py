"""Schedule conflict detection service (Conflict Detection Engine).

Collision rules used by the checks in this module:

* Two lessons can collide only if they are in the same ``time_slot_id``
  (a time slot already encodes the day of week and the lesson number).
* Week parity overlap:
    - ``ALWAYS`` overlaps with ``ALWAYS``, ``ODD_WEEK`` and ``EVEN_WEEK``;
    - ``ODD_WEEK`` overlaps with ``ALWAYS`` and ``ODD_WEEK`` only;
    - ``EVEN_WEEK`` overlaps with ``ALWAYS`` and ``EVEN_WEEK`` only.
* Specific (one-off) dates:
    - a recurring lesson (``specific_date is None``) overlaps with every lesson
      in the slot whose parity overlaps, including one-off lessons;
    - a one-off lesson overlaps with recurring lessons whose parity overlaps
      and with one-off lessons scheduled on the very same date.
"""

import enum
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.models.lesson import Lesson, WeekParity

__all__ = [
    "ConflictType",
    "ScheduleConflict",
    "check_teacher_conflict",
    "overlapping_parities",
    "parities_overlap",
]


class ConflictType(str, enum.Enum):
    """Kind of a detected schedule conflict."""

    TEACHER_BUSY = "TEACHER_BUSY"


@dataclass(frozen=True, slots=True)
class ScheduleConflict:
    """Description of a single detected schedule conflict."""

    conflict_type: ConflictType
    message: str
    conflicting_lesson_id: int


_PARITY_OVERLAPS: dict[WeekParity, frozenset[WeekParity]] = {
    WeekParity.ALWAYS: frozenset(
        {WeekParity.ALWAYS, WeekParity.ODD_WEEK, WeekParity.EVEN_WEEK},
    ),
    WeekParity.ODD_WEEK: frozenset({WeekParity.ALWAYS, WeekParity.ODD_WEEK}),
    WeekParity.EVEN_WEEK: frozenset({WeekParity.ALWAYS, WeekParity.EVEN_WEEK}),
}


def overlapping_parities(parity: WeekParity) -> frozenset[WeekParity]:
    """Return all parities that share at least one week with ``parity``."""
    return _PARITY_OVERLAPS[parity]


def parities_overlap(first: WeekParity, second: WeekParity) -> bool:
    """Return ``True`` if lessons with these parities may happen in the same week."""
    return second in _PARITY_OVERLAPS[first]


async def check_teacher_conflict(
    session: AsyncSession,
    teacher_id: int,
    time_slot_id: int,
    parity: WeekParity,
    specific_date: date | None,
    exclude_lesson_id: int | None = None,
) -> list[ScheduleConflict]:
    """Find lessons that make the teacher unavailable for the requested slot.

    Args:
        session: Active async database session.
        teacher_id: Teacher to be assigned to the lesson.
        time_slot_id: Time slot of the lesson.
        parity: Week parity of the lesson.
        specific_date: Date of a one-off lesson, ``None`` for a recurring one.
        exclude_lesson_id: Lesson to ignore (the lesson being updated), so it
            does not conflict with itself.

    Returns:
        List of detected conflicts ordered by conflicting lesson id;
        an empty list means the teacher is available.
    """
    stmt = select(Lesson).where(
        Lesson.teacher_id == teacher_id,
        Lesson.time_slot_id == time_slot_id,
        Lesson.parity.in_(overlapping_parities(parity)),
    )
    if specific_date is not None:
        stmt = stmt.where(
            or_(Lesson.specific_date.is_(None), Lesson.specific_date == specific_date),
        )
    if exclude_lesson_id is not None:
        stmt = stmt.where(Lesson.id != exclude_lesson_id)
    stmt = stmt.order_by(Lesson.id)

    result = await session.execute(stmt)
    return [
        ScheduleConflict(
            conflict_type=ConflictType.TEACHER_BUSY,
            message=(
                f"Teacher {teacher_id} is already busy in time slot {time_slot_id} "
                f"with lesson {lesson.id} (parity={lesson.parity.value}, "
                f"date={lesson.specific_date.isoformat() if lesson.specific_date else 'recurring'})"
            ),
            conflicting_lesson_id=lesson.id,
        )
        for lesson in result.scalars()
    ]
