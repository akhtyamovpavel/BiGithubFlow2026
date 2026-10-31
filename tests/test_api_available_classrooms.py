"""API tests for searching available classrooms (/api/v1/schedule/classrooms/available)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
async def client_with_db() -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired to a fresh in-memory SQLite database with all tables."""
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
                    Base.metadata.tables["lesson_exceptions"],
                ],
            )
        )

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _seed_entities(client: AsyncClient) -> dict[str, int]:
    """Create sample classrooms, group, teacher, subject, and time slots."""
    c_small = (
        await client.post(
            "/api/v1/classrooms/",
            json={
                "building": "УЛК",
                "room_number": "201",
                "capacity": 25,
                "has_projector": False,
                "has_computers": True,
                "is_active": True,
            },
        )
    ).json()
    c_medium = (
        await client.post(
            "/api/v1/classrooms/",
            json={
                "building": "ГК",
                "room_number": "115",
                "capacity": 60,
                "has_projector": True,
                "has_computers": False,
                "is_active": True,
            },
        )
    ).json()
    c_large = (
        await client.post(
            "/api/v1/classrooms/",
            json={
                "building": "ГК",
                "room_number": "Большая физическая",
                "capacity": 150,
                "has_projector": True,
                "has_computers": True,
                "is_active": True,
            },
        )
    ).json()
    c_inactive = (
        await client.post(
            "/api/v1/classrooms/",
            json={
                "building": "ГК",
                "room_number": "999",
                "capacity": 200,
                "has_projector": True,
                "has_computers": True,
                "is_active": False,
            },
        )
    ).json()

    group = (
        await client.post(
            "/api/v1/groups/",
            json={
                "name": "Б05-201",
                "faculty": "ФПМИ",
                "course_number": 2,
                "student_count": 25,
            },
        )
    ).json()
    teacher = (
        await client.post(
            "/api/v1/teachers/",
            json={
                "full_name": "Иванов Иван Иванович",
                "email": "ivanov@phystech.edu",
                "department": "Высшая математика",
                "position": "Профессор",
            },
        )
    ).json()
    subject = (
        await client.post(
            "/api/v1/subjects/",
            json={"name": "Математический анализ", "code": "MATH-101"},
        )
    ).json()
    slot1 = (
        await client.post(
            "/api/v1/time-slots/",
            json={
                "slot_number": 1,
                "start_time": "09:00:00",
                "end_time": "10:25:00",
                "day_of_week": 1,
            },
        )
    ).json()
    slot2 = (
        await client.post(
            "/api/v1/time-slots/",
            json={
                "slot_number": 2,
                "start_time": "10:45:00",
                "end_time": "12:10:00",
                "day_of_week": 1,
            },
        )
    ).json()

    return {
        "c_small": c_small["id"],
        "c_medium": c_medium["id"],
        "c_large": c_large["id"],
        "c_inactive": c_inactive["id"],
        "group_id": group["id"],
        "teacher_id": teacher["id"],
        "subject_id": subject["id"],
        "slot1_id": slot1["id"],
        "slot2_id": slot2["id"],
    }


@pytest.mark.asyncio
async def test_available_classrooms_filters_by_capacity_and_equipment(
    client_with_db: AsyncClient,
) -> None:
    """GET /api/v1/schedule/classrooms/available filters by capacity, projector, and computers."""
    ids = await _seed_entities(client_with_db)

    # All active classrooms in slot1 (inactive 999 is excluded)
    res_all = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
    )
    assert res_all.status_code == 200
    returned_ids = [c["id"] for c in res_all.json()]
    assert returned_ids == [ids["c_small"], ids["c_medium"], ids["c_large"]]

    # Filter min_capacity=50 & requires_projector=true
    res_cap_proj = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
        "&min_capacity=50&requires_projector=true"
    )
    assert res_cap_proj.status_code == 200
    assert [c["id"] for c in res_cap_proj.json()] == [ids["c_medium"], ids["c_large"]]

    # Filter min_capacity=100 & requires_computers=true
    res_large_comp = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
        "&min_capacity=100&requires_computers=true"
    )
    assert res_large_comp.status_code == 200
    assert [c["id"] for c in res_large_comp.json()] == [ids["c_large"]]

    # Filter by building
    res_bldg = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}&building=УЛК"
    )
    assert res_bldg.status_code == 200
    assert [c["id"] for c in res_bldg.json()] == [ids["c_small"]]


@pytest.mark.asyncio
async def test_available_classrooms_excludes_occupied_and_restores_when_freed(
    client_with_db: AsyncClient,
) -> None:
    """Occupied classroom is excluded and immediately reappears once the lesson is deleted."""
    ids = await _seed_entities(client_with_db)

    # Schedule a lesson in c_medium at slot1 (ALWAYS)
    lesson_res = await client_with_db.post(
        "/api/v1/lessons/",
        json={
            "subject_id": ids["subject_id"],
            "teacher_id": ids["teacher_id"],
            "group_id": ids["group_id"],
            "classroom_id": ids["c_medium"],
            "time_slot_id": ids["slot1_id"],
            "lesson_type": "LECTURE",
            "parity": "ALWAYS",
        },
    )
    assert lesson_res.status_code == 201
    lesson_id = lesson_res.json()["id"]

    # Now c_medium must NOT appear in available classrooms for slot1
    res_busy = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
    )
    assert res_busy.status_code == 200
    assert [c["id"] for c in res_busy.json()] == [ids["c_small"], ids["c_large"]]

    # In slot2, c_medium is still available
    res_slot2 = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot2_id']}"
    )
    assert res_slot2.status_code == 200
    assert [c["id"] for c in res_slot2.json()] == [
        ids["c_small"],
        ids["c_medium"],
        ids["c_large"],
    ]

    # Free c_medium by deleting the lesson
    del_res = await client_with_db.delete(f"/api/v1/lessons/{lesson_id}")
    assert del_res.status_code == 204

    # c_medium immediately reappears in available classrooms for slot1
    res_freed = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
    )
    assert res_freed.status_code == 200
    assert [c["id"] for c in res_freed.json()] == [
        ids["c_small"],
        ids["c_medium"],
        ids["c_large"],
    ]


@pytest.mark.asyncio
async def test_available_classrooms_parity_and_date_filtering(
    client_with_db: AsyncClient,
) -> None:
    """Parity and specific date rules match Conflict Detection Engine semantics."""
    ids = await _seed_entities(client_with_db)

    # Occupy c_medium on ODD_WEEK only (recurring)
    res1 = await client_with_db.post(
        "/api/v1/lessons/",
        json={
            "subject_id": ids["subject_id"],
            "teacher_id": ids["teacher_id"],
            "group_id": ids["group_id"],
            "classroom_id": ids["c_medium"],
            "time_slot_id": ids["slot1_id"],
            "lesson_type": "SEMINAR",
            "parity": "ODD_WEEK",
        },
    )
    assert res1.status_code == 201

    # Occupy c_large on a specific date 2026-10-26 (ISO week 44)
    res2 = await client_with_db.post(
        "/api/v1/lessons/",
        json={
            "subject_id": ids["subject_id"],
            "teacher_id": ids["teacher_id"],
            "group_id": ids["group_id"],
            "classroom_id": ids["c_large"],
            "time_slot_id": ids["slot1_id"],
            "lesson_type": "LECTURE",
            "parity": "EVEN_WEEK",
            "specific_date": "2026-10-26",
        },
    )
    assert res2.status_code == 201

    # On ODD_WEEK: c_medium is busy, c_small and c_large are free
    res_odd = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}&parity=ODD_WEEK"
    )
    assert res_odd.status_code == 200
    assert [c["id"] for c in res_odd.json()] == [ids["c_small"], ids["c_large"]]

    # On EVEN_WEEK with date=2026-10-26: c_large is busy, c_small and c_medium are free
    res_date_busy = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
        "&parity=EVEN_WEEK&date=2026-10-26"
    )
    assert res_date_busy.status_code == 200
    assert [c["id"] for c in res_date_busy.json()] == [ids["c_small"], ids["c_medium"]]

    # On EVEN_WEEK with another date=2026-11-09: all 3 active classrooms are free
    res_date_free = await client_with_db.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={ids['slot1_id']}"
        "&parity=EVEN_WEEK&date=2026-11-09"
    )
    assert res_date_free.status_code == 200
    assert [c["id"] for c in res_date_free.json()] == [
        ids["c_small"],
        ids["c_medium"],
        ids["c_large"],
    ]

    # Alias endpoint /api/v1/classrooms/available also works identically
    res_alias = await client_with_db.get(
        f"/api/v1/classrooms/available?time_slot_id={ids['slot1_id']}&parity=ODD_WEEK"
    )
    assert res_alias.status_code == 200
    assert [c["id"] for c in res_alias.json()] == [ids["c_small"], ids["c_large"]]
