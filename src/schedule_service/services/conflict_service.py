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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, WeekParity

__all__ = [
    "ClassroomCapacityExceededError",
    "ConflictType",
    "LessonConflictData",
    "ScheduleConflict",
    "ScheduleConflictException",
    "ScheduleValidationService",
    "check_classroom_capacity",
    "check_classroom_conflict",
    "check_group_conflict",
    "check_teacher_conflict",
    "overlapping_parities",
    "parities_overlap",
    "validate_classroom_capacity",
    "validate_lesson",
]


class ConflictType(str, enum.Enum):
    """Kind of a detected schedule conflict."""

    TEACHER_BUSY = "TEACHER_BUSY"
    CLASSROOM_BUSY = "CLASSROOM_BUSY"
    GROUP_BUSY = "GROUP_BUSY"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"


class LessonConflictData(Protocol):
    """Structural protocol for lesson data accepted by ``validate_lesson``."""

    @property
    def teacher_id(self) -> int: ...

    @property
    def classroom_id(self) -> int: ...

    @property
    def group_id(self) -> int: ...

    @property
    def time_slot_id(self) -> int: ...

    @property
    def parity(self) -> WeekParity: ...

    @property
    def specific_date(self) -> date | None: ...


class ClassroomCapacityExceededError(ValueError):
    """Raised when a student group exceeds the capacity of a classroom."""

    def __init__(
        self,
        *,
        capacity: int,
        student_count: int,
        classroom_id: int | None = None,
        group_id: int | None = None,
    ) -> None:
        self.classroom_id = classroom_id
        self.group_id = group_id
        self.capacity = capacity
        self.student_count = student_count
        self.deficit = student_count - capacity
        super().__init__(
            f"Classroom {classroom_id} capacity ({capacity}) is insufficient for "
            f"group {group_id} ({student_count} students): deficit of {self.deficit} seats"
        )


@dataclass(frozen=True, slots=True)
class ScheduleConflict:
    """Description of a single detected schedule conflict."""

    conflict_type: ConflictType
    message: str
    conflicting_lesson_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize conflict to a JSON-friendly dictionary."""
        return {
            "conflict_type": self.conflict_type.value,
            "message": self.message,
            "conflicting_lesson_id": self.conflicting_lesson_id,
        }


class ScheduleConflictException(Exception):
    """Raised when lesson validation detects one or more schedule conflicts."""

    def __init__(self, conflicts: Sequence[ScheduleConflict]) -> None:
        self.conflicts: list[ScheduleConflict] = list(conflicts)
        summary = "; ".join(conflict.message for conflict in self.conflicts)
        super().__init__(
            f"Schedule validation failed with {len(self.conflicts)} conflict(s): {summary}"
            if self.conflicts
            else "Schedule validation failed"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize all conflicts to a JSON-friendly dictionary."""
        return {
            "message": str(self),
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


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


def validate_classroom_capacity(classroom: Classroom, group: Group) -> None:
    """Ensure ``classroom`` can accommodate all students of ``group``.

    Raises:
        ClassroomCapacityExceededError: If ``group.student_count > classroom.capacity``.
    """
    if group.student_count > classroom.capacity:
        raise ClassroomCapacityExceededError(
            classroom_id=classroom.id,
            group_id=group.id,
            capacity=classroom.capacity,
            student_count=group.student_count,
        )


async def check_classroom_capacity(
    session: AsyncSession,
    classroom_id: int,
    group_id: int,
) -> None:
    """Load classroom and group by ID and validate that the group fits in the classroom.

    Raises:
        ValueError: If the classroom or group does not exist.
        ClassroomCapacityExceededError: If ``group.student_count > classroom.capacity``.
    """
    classroom = await session.get(Classroom, classroom_id)
    if classroom is None:
        raise ValueError(f"Classroom {classroom_id} not found")
    group = await session.get(Group, group_id)
    if group is None:
        raise ValueError(f"Group {group_id} not found")
    validate_classroom_capacity(classroom, group)


async def check_classroom_conflict(
    session: AsyncSession,
    classroom_id: int,
    time_slot_id: int,
    parity: WeekParity,
    specific_date: date | None,
    exclude_lesson_id: int | None = None,
    group_id: int | None = None,
) -> list[ScheduleConflict]:
    """Find lessons that occupy the classroom in the requested slot and check capacity.

    Args:
        session: Active async database session.
        classroom_id: Classroom to be assigned to the lesson.
        time_slot_id: Time slot of the lesson.
        parity: Week parity of the lesson.
        specific_date: Date of a one-off lesson, ``None`` for a recurring one.
        exclude_lesson_id: Lesson to ignore (the lesson being updated), so it
            does not conflict with itself.
        group_id: Optional academic group ID; when provided, also verifies that
            ``group.student_count <= classroom.capacity``.

    Returns:
        List of detected classroom occupancy conflicts ordered by conflicting
        lesson id; an empty list means the classroom is free in the slot.

    Raises:
        ClassroomCapacityExceededError: If ``group_id`` is provided and
            ``group.student_count > classroom.capacity``.
    """
    stmt = select(Lesson).where(
        Lesson.classroom_id == classroom_id,
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
    conflicts = [
        ScheduleConflict(
            conflict_type=ConflictType.CLASSROOM_BUSY,
            message=(
                f"Classroom {classroom_id} is already occupied in time slot {time_slot_id} "
                f"by lesson {lesson.id} (parity={lesson.parity.value}, "
                f"date={lesson.specific_date.isoformat() if lesson.specific_date else 'recurring'})"
            ),
            conflicting_lesson_id=lesson.id,
        )
        for lesson in result.scalars()
    ]

    if group_id is not None:
        await check_classroom_capacity(session, classroom_id, group_id)

    return conflicts


async def check_group_conflict(
    session: AsyncSession,
    group_id: int,
    time_slot_id: int,
    parity: WeekParity,
    specific_date: date | None = None,
    exclude_lesson_id: int | None = None,
) -> list[ScheduleConflict]:
    """Find lessons that occupy the academic group in the requested slot.

    Args:
        session: Active async database session.
        group_id: Academic group to be assigned to the lesson.
        time_slot_id: Time slot of the lesson.
        parity: Week parity of the lesson.
        specific_date: Date of a one-off lesson, ``None`` for a recurring one.
        exclude_lesson_id: Lesson to ignore (the lesson being updated), so it
            does not conflict with itself.

    Returns:
        List of detected group occupancy conflicts ordered by conflicting
        lesson id; an empty list means the group is available in the slot.
    """
    stmt = select(Lesson).where(
        Lesson.group_id == group_id,
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
            conflict_type=ConflictType.GROUP_BUSY,
            message=(
                f"Group {group_id} is already busy in time slot {time_slot_id} "
                f"with lesson {lesson.id} (parity={lesson.parity.value}, "
                f"date={lesson.specific_date.isoformat() if lesson.specific_date else 'recurring'})"
            ),
            conflicting_lesson_id=lesson.id,
        )
        for lesson in result.scalars()
    ]


def _extract_lesson_fields(
    lesson_data: LessonConflictData | Mapping[str, Any],
) -> tuple[int, int, int, int, WeekParity, date | None]:
    """Extract conflict-relevant fields from a schema, ORM model, or mapping."""
    if isinstance(lesson_data, Mapping):
        teacher_id = int(lesson_data["teacher_id"])
        classroom_id = int(lesson_data["classroom_id"])
        group_id = int(lesson_data["group_id"])
        time_slot_id = int(lesson_data["time_slot_id"])
        raw_parity = lesson_data.get("parity") or WeekParity.ALWAYS
        parity = raw_parity if isinstance(raw_parity, WeekParity) else WeekParity(raw_parity)
        specific_date: date | None = lesson_data.get("specific_date")
        return teacher_id, classroom_id, group_id, time_slot_id, parity, specific_date

    raw_parity = getattr(lesson_data, "parity", None) or WeekParity.ALWAYS
    parity = raw_parity if isinstance(raw_parity, WeekParity) else WeekParity(raw_parity)
    specific_date = getattr(lesson_data, "specific_date", None)
    return (
        lesson_data.teacher_id,
        lesson_data.classroom_id,
        lesson_data.group_id,
        lesson_data.time_slot_id,
        parity,
        specific_date,
    )


async def validate_lesson(
    session: AsyncSession,
    lesson_data: LessonConflictData | Mapping[str, Any],
    exclude_lesson_id: int | None = None,
) -> None:
    """Validate a lesson against teacher, classroom, group, and capacity rules.

    Runs all four checks without short-circuiting and aggregates all detected
    violations into a single ``ScheduleConflictException``.

    Args:
        session: Active async database session.
        lesson_data: Lesson payload (``LessonCreate``, ``Lesson``, or mapping).
        exclude_lesson_id: Optional ID of the lesson being updated so it does
            not conflict with itself.

    Raises:
        ScheduleConflictException: If one or more conflicts are detected.
    """
    (
        teacher_id,
        classroom_id,
        group_id,
        time_slot_id,
        parity,
        specific_date,
    ) = _extract_lesson_fields(lesson_data)

    conflicts: list[ScheduleConflict] = []

    teacher_conflicts = await check_teacher_conflict(
        session,
        teacher_id,
        time_slot_id,
        parity,
        specific_date,
        exclude_lesson_id=exclude_lesson_id,
    )
    conflicts.extend(teacher_conflicts)

    classroom_conflicts = await check_classroom_conflict(
        session,
        classroom_id,
        time_slot_id,
        parity,
        specific_date,
        exclude_lesson_id=exclude_lesson_id,
    )
    conflicts.extend(classroom_conflicts)

    group_conflicts = await check_group_conflict(
        session,
        group_id,
        time_slot_id,
        parity,
        specific_date,
        exclude_lesson_id=exclude_lesson_id,
    )
    conflicts.extend(group_conflicts)

    classroom = await session.get(Classroom, classroom_id)
    group = await session.get(Group, group_id)
    if classroom is not None and group is not None:
        try:
            validate_classroom_capacity(classroom, group)
        except ClassroomCapacityExceededError as exc:
            conflicts.append(
                ScheduleConflict(
                    conflict_type=ConflictType.CAPACITY_EXCEEDED,
                    message=str(exc),
                    conflicting_lesson_id=None,
                )
            )

    if conflicts:
        raise ScheduleConflictException(conflicts)


class ScheduleValidationService:
    """Facade service combining all schedule conflict and capacity checks."""

    check_teacher_conflict = staticmethod(check_teacher_conflict)
    check_classroom_conflict = staticmethod(check_classroom_conflict)
    check_group_conflict = staticmethod(check_group_conflict)
    check_classroom_capacity = staticmethod(check_classroom_capacity)
    validate_classroom_capacity = staticmethod(validate_classroom_capacity)
    validate_lesson = staticmethod(validate_lesson)
