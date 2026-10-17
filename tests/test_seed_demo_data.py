"""Tests for the demonstration data seed script (scripts/seed_demo_data.py)."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from scripts.seed_demo_data import run_seed, seed_demo_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
    get_async_session,
)
from schedule_service.main import app
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot


@pytest_asyncio.fixture
async def seeded_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an in-memory SQLite session with all schema tables created."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Group.__table__,  # type: ignore[list-item]
                    Teacher.__table__,  # type: ignore[list-item]
                    Classroom.__table__,  # type: ignore[list-item]
                    Subject.__table__,  # type: ignore[list-item]
                    TimeSlot.__table__,  # type: ignore[list-item]
                    Lesson.__table__,  # type: ignore[list-item]
                ],
            )
        )

    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_demo_data_populates_and_is_idempotent(
    seeded_session: AsyncSession,
) -> None:
    """seed_demo_data populates 5 groups, 8 teachers, 10 classrooms, 12 subjects, 36 slots."""
    summary1 = await seed_demo_data(seeded_session)
    assert summary1.groups == 5
    assert summary1.teachers == 8
    assert summary1.classrooms == 10
    assert summary1.subjects == 12
    assert summary1.time_slots == 36
    assert summary1.lessons >= 15

    # Run a second time to verify idempotency (no duplicates or errors)
    summary2 = await seed_demo_data(seeded_session)
    assert summary2 == summary1

    groups_count = (await seeded_session.execute(select(func.count(Group.id)))).scalar_one()
    teachers_count = (await seeded_session.execute(select(func.count(Teacher.id)))).scalar_one()
    classrooms_count = (await seeded_session.execute(select(func.count(Classroom.id)))).scalar_one()
    subjects_count = (await seeded_session.execute(select(func.count(Subject.id)))).scalar_one()
    slots_count = (await seeded_session.execute(select(func.count(TimeSlot.id)))).scalar_one()
    lessons_count = (await seeded_session.execute(select(func.count(Lesson.id)))).scalar_one()

    assert groups_count == 5
    assert teachers_count == 8
    assert classrooms_count == 10
    assert subjects_count == 12
    assert slots_count == 36
    assert lessons_count == summary1.lessons


@pytest.mark.asyncio
async def test_schedule_endpoints_return_seeded_data(
    seeded_session: AsyncSession,
) -> None:
    """Schedule endpoints return populated weekly timetable after running seed_demo_data."""
    await seed_demo_data(seeded_session)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield seeded_session

    app.dependency_overrides[get_async_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            groups_res = await client.get("/api/v1/groups/")
            assert groups_res.status_code == 200
            groups = groups_res.json()
            assert len(groups) == 5

            first_group_id = groups[0]["id"]
            sched_res = await client.get(f"/api/v1/schedule/group/{first_group_id}")
            assert sched_res.status_code == 200
            sched_data = sched_res.json()
            total_group_lessons = sum(len(day["lessons"]) for day in sched_data["days"])
            assert total_group_lessons > 0

            teachers_res = await client.get("/api/v1/teachers/")
            assert teachers_res.status_code == 200
            first_teacher_id = teachers_res.json()[0]["id"]
            teacher_sched_res = await client.get(f"/api/v1/schedule/teacher/{first_teacher_id}")
            assert teacher_sched_res.status_code == 200
            total_teacher_lessons = sum(
                len(day["lessons"]) for day in teacher_sched_res.json()["days"]
            )
            assert total_teacher_lessons > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_seed_with_sqlite_file(tmp_path: Path) -> None:
    """run_seed initializes schema and is idempotent across repeated invocations."""
    db_file = tmp_path / "demo_seed.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    s1 = await run_seed(db_url)
    s2 = await run_seed(db_url)
    assert s1 == s2
    assert s1.groups == 5
    assert s1.time_slots == 36
