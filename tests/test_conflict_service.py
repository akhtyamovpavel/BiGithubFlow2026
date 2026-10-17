"""Tests for schedule conflict detection and validation facade (issues #11, #12, #13)."""

from collections.abc import AsyncGenerator
from datetime import date
from itertools import count

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, Table
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import Base, create_engine_and_sessionmaker
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.schemas.lesson import LessonCreate
from schedule_service.services.conflict_service import (
    ClassroomCapacityExceededError,
    ConflictType,
    ScheduleConflictException,
    ScheduleValidationService,
    check_classroom_capacity,
    check_classroom_conflict,
    check_group_conflict,
    check_teacher_conflict,
    overlapping_parities,
    parities_overlap,
    validate_classroom_capacity,
    validate_lesson,
)

TEACHER = 1
OTHER_TEACHER = 2
CLASSROOM = 1
OTHER_CLASSROOM = 2
GROUP = 100
OTHER_GROUP = 101
SLOT = 10
OTHER_SLOT = 11
DATE = date(2026, 10, 5)
OTHER_DATE = date(2026, 10, 12)

_FK_TARGET_TABLES = ("subjects", "teachers", "groups", "classrooms", "time_slots")
_group_ids = count(1)
_room_numbers = count(101)
_group_names = count(1)


def _ensure_fk_target_tables() -> None:
    """Register minimal stubs for FK targets whose models are not implemented yet.

    Existing tables (e.g. a real ``groups`` model) are left untouched.
    """
    for name in _FK_TARGET_TABLES:
        if name not in Base.metadata.tables:
            Table(name, Base.metadata, Column("id", Integer, primary_key=True))


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a session bound to a fresh in-memory SQLite database."""
    _ensure_fk_target_tables()
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[name] for name in (*_FK_TARGET_TABLES, "lessons")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    async with session_maker() as db_session:
        yield db_session
    await engine.dispose()


async def _add_lesson(
    session: AsyncSession,
    *,
    teacher_id: int = TEACHER,
    classroom_id: int = CLASSROOM,
    group_id: int | None = None,
    time_slot_id: int = SLOT,
    parity: WeekParity = WeekParity.ALWAYS,
    specific_date: date | None = None,
) -> Lesson:
    lesson = Lesson(
        subject_id=1,
        teacher_id=teacher_id,
        group_id=group_id if group_id is not None else next(_group_ids),
        classroom_id=classroom_id,
        time_slot_id=time_slot_id,
        lesson_type=LessonType.LECTURE,
        parity=parity,
        specific_date=specific_date,
    )
    session.add(lesson)
    await session.flush()
    return lesson


async def _add_classroom(
    session: AsyncSession,
    *,
    capacity: int = 30,
    building: str = "Main",
    room_number: str | None = None,
) -> Classroom:
    classroom = Classroom(
        building=building,
        room_number=room_number or str(next(_room_numbers)),
        capacity=capacity,
    )
    session.add(classroom)
    await session.flush()
    return classroom


async def _add_group(
    session: AsyncSession,
    *,
    student_count: int = 25,
    name: str | None = None,
    faculty: str = "CS",
    course_number: int = 2,
) -> Group:
    group = Group(
        name=name or f"BI-2026-{next(_group_names)}",
        faculty=faculty,
        course_number=course_number,
        student_count=student_count,
    )
    session.add(group)
    await session.flush()
    return group


# ---------------------------------------------------------------------------
# Pure parity rules
# ---------------------------------------------------------------------------

_A, _O, _E = WeekParity.ALWAYS, WeekParity.ODD_WEEK, WeekParity.EVEN_WEEK


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (_A, _A, True),
        (_A, _O, True),
        (_A, _E, True),
        (_O, _A, True),
        (_O, _O, True),
        (_O, _E, False),
        (_E, _A, True),
        (_E, _E, True),
        (_E, _O, False),
    ],
)
def test_parities_overlap_matrix(first: WeekParity, second: WeekParity, expected: bool) -> None:
    assert parities_overlap(first, second) is expected
    # The relation must be symmetric.
    assert parities_overlap(second, first) is expected


def test_overlapping_parities_covers_every_parity() -> None:
    for parity in WeekParity:
        assert parity in overlapping_parities(parity)
    assert overlapping_parities(_A) == {_A, _O, _E}
    assert overlapping_parities(_O) == {_A, _O}
    assert overlapping_parities(_E) == {_A, _E}


# ---------------------------------------------------------------------------
# Database-backed checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conflict_on_empty_schedule(session: AsyncSession) -> None:
    assert await check_teacher_conflict(session, TEACHER, SLOT, _A, None) == []


@pytest.mark.asyncio
async def test_same_teacher_same_slot_conflicts(session: AsyncSession) -> None:
    existing = await _add_lesson(session)

    conflicts = await check_teacher_conflict(session, TEACHER, SLOT, _A, None)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type is ConflictType.TEACHER_BUSY
    assert conflicts[0].conflicting_lesson_id == existing.id
    assert f"Teacher {TEACHER}" in conflicts[0].message


@pytest.mark.asyncio
async def test_other_slot_or_other_teacher_does_not_conflict(session: AsyncSession) -> None:
    await _add_lesson(session, time_slot_id=OTHER_SLOT)
    await _add_lesson(session, teacher_id=OTHER_TEACHER)

    assert await check_teacher_conflict(session, TEACHER, SLOT, _A, None) == []


@pytest.mark.parametrize(
    ("existing_parity", "new_parity", "expected_conflict"),
    [
        (_A, _A, True),
        (_A, _O, True),
        (_A, _E, True),
        (_O, _A, True),
        (_O, _O, True),
        (_O, _E, False),
        (_E, _A, True),
        (_E, _O, False),
        (_E, _E, True),
    ],
)
@pytest.mark.asyncio
async def test_recurring_parity_matrix(
    session: AsyncSession,
    existing_parity: WeekParity,
    new_parity: WeekParity,
    expected_conflict: bool,
) -> None:
    await _add_lesson(session, parity=existing_parity)

    conflicts = await check_teacher_conflict(session, TEACHER, SLOT, new_parity, None)

    assert bool(conflicts) is expected_conflict


@pytest.mark.asyncio
async def test_teacher_can_take_free_week_in_shared_slot(session: AsyncSession) -> None:
    """Even week is taught by another teacher, odd week by ours: no collision."""
    await _add_lesson(session, teacher_id=OTHER_TEACHER, parity=_E)
    await _add_lesson(session, teacher_id=TEACHER, parity=_O)

    assert await check_teacher_conflict(session, TEACHER, SLOT, _E, None) == []
    assert await check_teacher_conflict(session, OTHER_TEACHER, SLOT, _O, None) == []


@pytest.mark.asyncio
async def test_teacher_with_both_parities_reports_all_conflicts(session: AsyncSession) -> None:
    odd = await _add_lesson(session, parity=_O)
    even = await _add_lesson(session, parity=_E)

    conflicts = await check_teacher_conflict(session, TEACHER, SLOT, _A, None)

    assert [c.conflicting_lesson_id for c in conflicts] == [odd.id, even.id]


@pytest.mark.asyncio
async def test_one_off_lesson_conflicts_with_recurring(session: AsyncSession) -> None:
    await _add_lesson(session, parity=_A)

    assert len(await check_teacher_conflict(session, TEACHER, SLOT, _A, DATE)) == 1


@pytest.mark.asyncio
async def test_one_off_lesson_respects_parity_of_recurring(session: AsyncSession) -> None:
    await _add_lesson(session, parity=_E)

    assert await check_teacher_conflict(session, TEACHER, SLOT, _O, DATE) == []


@pytest.mark.asyncio
async def test_one_off_lessons_conflict_only_on_same_date(session: AsyncSession) -> None:
    await _add_lesson(session, specific_date=DATE)

    assert len(await check_teacher_conflict(session, TEACHER, SLOT, _A, DATE)) == 1
    assert await check_teacher_conflict(session, TEACHER, SLOT, _A, OTHER_DATE) == []


@pytest.mark.asyncio
async def test_recurring_lesson_conflicts_with_existing_one_off(session: AsyncSession) -> None:
    await _add_lesson(session, specific_date=DATE)

    assert len(await check_teacher_conflict(session, TEACHER, SLOT, _A, None)) == 1


@pytest.mark.asyncio
async def test_exclude_lesson_id_prevents_self_conflict(session: AsyncSession) -> None:
    lesson = await _add_lesson(session)

    conflicts = await check_teacher_conflict(
        session, TEACHER, SLOT, _A, None, exclude_lesson_id=lesson.id
    )

    assert conflicts == []


@pytest.mark.asyncio
async def test_exclude_lesson_id_keeps_other_conflicts(session: AsyncSession) -> None:
    updated = await _add_lesson(session, parity=_O)
    other = await _add_lesson(session, parity=_O)

    conflicts = await check_teacher_conflict(
        session, TEACHER, SLOT, _O, None, exclude_lesson_id=updated.id
    )

    assert [c.conflicting_lesson_id for c in conflicts] == [other.id]


# ---------------------------------------------------------------------------
# Classroom conflict and capacity checks (issue #12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_classroom_conflict_on_empty_schedule(session: AsyncSession) -> None:
    assert await check_classroom_conflict(session, CLASSROOM, SLOT, _A, None) == []


@pytest.mark.asyncio
async def test_classroom_occupied_by_another_lesson_conflicts(session: AsyncSession) -> None:
    existing = await _add_lesson(session, classroom_id=CLASSROOM, time_slot_id=SLOT, parity=_A)

    conflicts = await check_classroom_conflict(session, CLASSROOM, SLOT, _A, None)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type is ConflictType.CLASSROOM_BUSY
    assert conflicts[0].conflicting_lesson_id == existing.id
    assert f"Classroom {CLASSROOM}" in conflicts[0].message


@pytest.mark.asyncio
async def test_other_slot_or_other_classroom_does_not_conflict(session: AsyncSession) -> None:
    await _add_lesson(session, classroom_id=CLASSROOM, time_slot_id=OTHER_SLOT)
    await _add_lesson(session, classroom_id=OTHER_CLASSROOM, time_slot_id=SLOT)

    assert await check_classroom_conflict(session, CLASSROOM, SLOT, _A, None) == []


@pytest.mark.parametrize(
    ("existing_parity", "new_parity", "expected_conflict"),
    [
        (_A, _A, True),
        (_A, _O, True),
        (_A, _E, True),
        (_O, _A, True),
        (_O, _O, True),
        (_O, _E, False),
        (_E, _A, True),
        (_E, _O, False),
        (_E, _E, True),
    ],
)
@pytest.mark.asyncio
async def test_classroom_recurring_parity_matrix(
    session: AsyncSession,
    existing_parity: WeekParity,
    new_parity: WeekParity,
    expected_conflict: bool,
) -> None:
    await _add_lesson(session, classroom_id=CLASSROOM, parity=existing_parity)

    conflicts = await check_classroom_conflict(session, CLASSROOM, SLOT, new_parity, None)

    assert bool(conflicts) is expected_conflict


@pytest.mark.asyncio
async def test_classroom_one_off_lessons_conflict_rules(session: AsyncSession) -> None:
    one_off = await _add_lesson(session, classroom_id=CLASSROOM, specific_date=DATE)

    same_date_conflicts = await check_classroom_conflict(session, CLASSROOM, SLOT, _A, DATE)
    assert len(same_date_conflicts) == 1
    assert same_date_conflicts[0].conflicting_lesson_id == one_off.id
    assert DATE.isoformat() in same_date_conflicts[0].message

    assert await check_classroom_conflict(session, CLASSROOM, SLOT, _A, OTHER_DATE) == []
    assert len(await check_classroom_conflict(session, CLASSROOM, SLOT, _A, None)) == 1


@pytest.mark.asyncio
async def test_classroom_exclude_lesson_id_prevents_self_conflict(session: AsyncSession) -> None:
    lesson = await _add_lesson(session, classroom_id=CLASSROOM)

    conflicts = await check_classroom_conflict(
        session, CLASSROOM, SLOT, _A, None, exclude_lesson_id=lesson.id
    )

    assert conflicts == []


@pytest.mark.asyncio
async def test_classroom_free_and_capacity_sufficient(session: AsyncSession) -> None:
    classroom = await _add_classroom(session, capacity=30)
    group = await _add_group(session, student_count=25)

    conflicts = await check_classroom_conflict(
        session,
        classroom.id,
        SLOT,
        _A,
        None,
        group_id=group.id,
    )

    assert conflicts == []


@pytest.mark.asyncio
async def test_classroom_free_and_exact_capacity_sufficient(session: AsyncSession) -> None:
    classroom = await _add_classroom(session, capacity=30)
    group = await _add_group(session, student_count=30)

    validate_classroom_capacity(classroom, group)
    await check_classroom_capacity(session, classroom.id, group.id)
    assert (
        await check_classroom_conflict(
            session,
            classroom.id,
            SLOT,
            _A,
            None,
            group_id=group.id,
        )
        == []
    )


@pytest.mark.asyncio
async def test_classroom_free_but_insufficient_capacity_raises_with_deficit(
    session: AsyncSession,
) -> None:
    classroom = await _add_classroom(session, capacity=20)
    group = await _add_group(session, student_count=28)

    with pytest.raises(ClassroomCapacityExceededError) as exc_info:
        await check_classroom_conflict(
            session,
            classroom.id,
            SLOT,
            _A,
            None,
            group_id=group.id,
        )

    err = exc_info.value
    assert err.classroom_id == classroom.id
    assert err.group_id == group.id
    assert err.capacity == 20
    assert err.student_count == 28
    assert err.deficit == 8
    assert "8" in str(err)
    assert "deficit" in str(err)


def test_validate_classroom_capacity_directly_raises_with_deficit() -> None:
    classroom = Classroom(id=5, building="A", room_number="101", capacity=15)
    group = Group(id=7, name="BI-1", faculty="CS", course_number=1, student_count=22)

    with pytest.raises(ClassroomCapacityExceededError) as exc_info:
        validate_classroom_capacity(classroom, group)

    assert exc_info.value.deficit == 7
    assert exc_info.value.capacity == 15
    assert exc_info.value.student_count == 22


@pytest.mark.asyncio
async def test_check_classroom_capacity_missing_entities(session: AsyncSession) -> None:
    classroom = await _add_classroom(session, capacity=30)

    with pytest.raises(ValueError, match="Classroom 9999 not found"):
        await check_classroom_capacity(session, 9999, 1)

    with pytest.raises(ValueError, match="Group 9999 not found"):
        await check_classroom_capacity(session, classroom.id, 9999)


# ---------------------------------------------------------------------------
# Group conflict checks (issue #13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_group_conflict_on_empty_schedule(session: AsyncSession) -> None:
    assert await check_group_conflict(session, GROUP, SLOT, _A, None) == []


@pytest.mark.asyncio
async def test_same_group_same_slot_conflicts(session: AsyncSession) -> None:
    existing = await _add_lesson(session, group_id=GROUP, time_slot_id=SLOT, parity=_A)

    conflicts = await check_group_conflict(session, GROUP, SLOT, _A, None)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type is ConflictType.GROUP_BUSY
    assert conflicts[0].conflicting_lesson_id == existing.id
    assert f"Group {GROUP}" in conflicts[0].message


@pytest.mark.asyncio
async def test_other_slot_or_other_group_does_not_conflict(session: AsyncSession) -> None:
    await _add_lesson(session, group_id=GROUP, time_slot_id=OTHER_SLOT)
    await _add_lesson(session, group_id=OTHER_GROUP, time_slot_id=SLOT)

    assert await check_group_conflict(session, GROUP, SLOT, _A, None) == []


@pytest.mark.parametrize(
    ("existing_parity", "new_parity", "expected_conflict"),
    [
        (_A, _A, True),
        (_A, _O, True),
        (_A, _E, True),
        (_O, _A, True),
        (_O, _O, True),
        (_O, _E, False),
        (_E, _A, True),
        (_E, _O, False),
        (_E, _E, True),
    ],
)
@pytest.mark.asyncio
async def test_group_recurring_parity_matrix(
    session: AsyncSession,
    existing_parity: WeekParity,
    new_parity: WeekParity,
    expected_conflict: bool,
) -> None:
    await _add_lesson(session, group_id=GROUP, parity=existing_parity)

    conflicts = await check_group_conflict(session, GROUP, SLOT, new_parity, None)

    assert bool(conflicts) is expected_conflict


@pytest.mark.asyncio
async def test_group_one_off_lessons_conflict_rules(session: AsyncSession) -> None:
    one_off = await _add_lesson(session, group_id=GROUP, specific_date=DATE)

    same_date_conflicts = await check_group_conflict(session, GROUP, SLOT, _A, DATE)
    assert len(same_date_conflicts) == 1
    assert same_date_conflicts[0].conflicting_lesson_id == one_off.id
    assert DATE.isoformat() in same_date_conflicts[0].message

    assert await check_group_conflict(session, GROUP, SLOT, _A, OTHER_DATE) == []
    assert len(await check_group_conflict(session, GROUP, SLOT, _A, None)) == 1


@pytest.mark.asyncio
async def test_group_exclude_lesson_id_prevents_self_conflict(session: AsyncSession) -> None:
    lesson = await _add_lesson(session, group_id=GROUP)

    conflicts = await check_group_conflict(
        session, GROUP, SLOT, _A, None, exclude_lesson_id=lesson.id
    )

    assert conflicts == []


# ---------------------------------------------------------------------------
# Schedule validation facade integration tests (issue #13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_lesson_passes_when_no_conflicts(session: AsyncSession) -> None:
    classroom = await _add_classroom(session, capacity=30)
    group = await _add_group(session, student_count=25)
    lesson_data = LessonCreate(
        subject_id=1,
        teacher_id=TEACHER,
        group_id=group.id,
        classroom_id=classroom.id,
        time_slot_id=SLOT,
        lesson_type=LessonType.LECTURE,
        parity=_A,
        specific_date=None,
    )

    await validate_lesson(session, lesson_data)
    await ScheduleValidationService.validate_lesson(session, lesson_data)


@pytest.mark.asyncio
async def test_validate_lesson_blocks_second_lesson_for_same_group_in_slot(
    session: AsyncSession,
) -> None:
    classroom1 = await _add_classroom(session, capacity=30)
    classroom2 = await _add_classroom(session, capacity=30)
    group = await _add_group(session, student_count=20)
    existing = await _add_lesson(
        session,
        teacher_id=TEACHER,
        classroom_id=classroom1.id,
        group_id=group.id,
        time_slot_id=SLOT,
        parity=_A,
    )

    candidate = LessonCreate(
        subject_id=1,
        teacher_id=OTHER_TEACHER,
        group_id=group.id,
        classroom_id=classroom2.id,
        time_slot_id=SLOT,
        lesson_type=LessonType.SEMINAR,
        parity=_A,
    )

    with pytest.raises(ScheduleConflictException) as exc_info:
        await validate_lesson(session, candidate)

    conflicts = exc_info.value.conflicts
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type is ConflictType.GROUP_BUSY
    assert conflicts[0].conflicting_lesson_id == existing.id
    assert f"Group {group.id}" in conflicts[0].message


@pytest.mark.asyncio
async def test_validate_lesson_aggregates_teacher_and_classroom_conflicts(
    session: AsyncSession,
) -> None:
    classroom1 = await _add_classroom(session, capacity=40)
    classroom2 = await _add_classroom(session, capacity=40)
    group1 = await _add_group(session, student_count=20)
    group2 = await _add_group(session, student_count=20)
    group3 = await _add_group(session, student_count=20)

    teacher_lesson = await _add_lesson(
        session,
        teacher_id=TEACHER,
        classroom_id=classroom2.id,
        group_id=group1.id,
        time_slot_id=SLOT,
        parity=_A,
    )
    classroom_lesson = await _add_lesson(
        session,
        teacher_id=OTHER_TEACHER,
        classroom_id=classroom1.id,
        group_id=group2.id,
        time_slot_id=SLOT,
        parity=_A,
    )

    candidate = LessonCreate(
        subject_id=1,
        teacher_id=TEACHER,
        group_id=group3.id,
        classroom_id=classroom1.id,
        time_slot_id=SLOT,
        lesson_type=LessonType.LECTURE,
        parity=_A,
    )

    with pytest.raises(ScheduleConflictException) as exc_info:
        await validate_lesson(session, candidate)

    conflicts = exc_info.value.conflicts
    assert [c.conflict_type for c in conflicts] == [
        ConflictType.TEACHER_BUSY,
        ConflictType.CLASSROOM_BUSY,
    ]
    assert [c.conflicting_lesson_id for c in conflicts] == [
        teacher_lesson.id,
        classroom_lesson.id,
    ]


@pytest.mark.asyncio
async def test_validate_lesson_aggregates_all_four_conflict_types(
    session: AsyncSession,
) -> None:
    small_classroom = await _add_classroom(session, capacity=15)
    other_classroom = await _add_classroom(session, capacity=40)
    third_classroom = await _add_classroom(session, capacity=40)
    large_group = await _add_group(session, student_count=28)
    other_group = await _add_group(session, student_count=20)
    third_group = await _add_group(session, student_count=20)

    teacher_lesson = await _add_lesson(
        session,
        teacher_id=TEACHER,
        classroom_id=other_classroom.id,
        group_id=other_group.id,
        time_slot_id=SLOT,
        parity=_A,
    )
    classroom_lesson = await _add_lesson(
        session,
        teacher_id=OTHER_TEACHER,
        classroom_id=small_classroom.id,
        group_id=third_group.id,
        time_slot_id=SLOT,
        parity=_A,
    )
    group_lesson = await _add_lesson(
        session,
        teacher_id=99,
        classroom_id=third_classroom.id,
        group_id=large_group.id,
        time_slot_id=SLOT,
        parity=_A,
    )

    candidate = LessonCreate(
        subject_id=1,
        teacher_id=TEACHER,
        group_id=large_group.id,
        classroom_id=small_classroom.id,
        time_slot_id=SLOT,
        lesson_type=LessonType.LAB,
        parity=_A,
    )

    with pytest.raises(ScheduleConflictException) as exc_info:
        await ScheduleValidationService.validate_lesson(session, candidate)

    err = exc_info.value
    assert [c.conflict_type for c in err.conflicts] == [
        ConflictType.TEACHER_BUSY,
        ConflictType.CLASSROOM_BUSY,
        ConflictType.GROUP_BUSY,
        ConflictType.CAPACITY_EXCEEDED,
    ]
    assert err.conflicts[0].conflicting_lesson_id == teacher_lesson.id
    assert err.conflicts[1].conflicting_lesson_id == classroom_lesson.id
    assert err.conflicts[2].conflicting_lesson_id == group_lesson.id
    assert err.conflicts[3].conflicting_lesson_id is None
    assert "deficit of 13 seats" in err.conflicts[3].message

    serialized = err.to_dict()
    assert len(serialized["conflicts"]) == 4
    assert [item["conflict_type"] for item in serialized["conflicts"]] == [
        "TEACHER_BUSY",
        "CLASSROOM_BUSY",
        "GROUP_BUSY",
        "CAPACITY_EXCEEDED",
    ]


@pytest.mark.asyncio
async def test_validate_lesson_exclude_lesson_id_for_update_and_mapping_input(
    session: AsyncSession,
) -> None:
    classroom = await _add_classroom(session, capacity=30)
    group = await _add_group(session, student_count=20)
    existing = await _add_lesson(
        session,
        teacher_id=TEACHER,
        classroom_id=classroom.id,
        group_id=group.id,
        time_slot_id=SLOT,
        parity=_O,
    )

    payload = {
        "teacher_id": TEACHER,
        "classroom_id": classroom.id,
        "group_id": group.id,
        "time_slot_id": SLOT,
        "parity": "ODD_WEEK",
        "specific_date": None,
    }

    # Updating the same lesson in place must not conflict with itself.
    await validate_lesson(session, payload, exclude_lesson_id=existing.id)

    # Without exclude_lesson_id, all three occupancy checks report the existing lesson.
    with pytest.raises(ScheduleConflictException) as exc_info:
        await validate_lesson(session, existing)

    assert [c.conflict_type for c in exc_info.value.conflicts] == [
        ConflictType.TEACHER_BUSY,
        ConflictType.CLASSROOM_BUSY,
        ConflictType.GROUP_BUSY,
    ]
