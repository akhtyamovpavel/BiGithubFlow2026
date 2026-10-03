"""Unit tests for teacher conflict detection (issue #11)."""

from collections.abc import AsyncGenerator
from datetime import date
from itertools import count

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, Table
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import Base, create_engine_and_sessionmaker
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.services.conflict_service import (
    ConflictType,
    check_teacher_conflict,
    overlapping_parities,
    parities_overlap,
)

TEACHER = 1
OTHER_TEACHER = 2
SLOT = 10
OTHER_SLOT = 11
DATE = date(2026, 10, 5)
OTHER_DATE = date(2026, 10, 12)

_FK_TARGET_TABLES = ("subjects", "teachers", "groups", "classrooms", "time_slots")
_group_ids = count(1)


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
    time_slot_id: int = SLOT,
    parity: WeekParity = WeekParity.ALWAYS,
    specific_date: date | None = None,
) -> Lesson:
    lesson = Lesson(
        subject_id=1,
        teacher_id=teacher_id,
        group_id=next(_group_ids),
        classroom_id=1,
        time_slot_id=time_slot_id,
        lesson_type=LessonType.LECTURE,
        parity=parity,
        specific_date=specific_date,
    )
    session.add(lesson)
    await session.flush()
    return lesson


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
