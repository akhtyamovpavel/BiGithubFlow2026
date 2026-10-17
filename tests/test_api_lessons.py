"""End-to-end API integration tests for Lesson CRUD endpoints (/api/v1/lessons, issue #16)."""

from collections.abc import AsyncGenerator
from datetime import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
async def db_context() -> (
    AsyncGenerator[
        tuple[AsyncClient, async_sessionmaker[AsyncSession]],
        None,
    ]
):
    """Provide an AsyncClient and session_maker wired to an in-memory SQLite database."""
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
        yield client, session_maker

    app.dependency_overrides.clear()
    await engine.dispose()


async def _seed_reference_entities(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    """Create sample subjects, teachers, groups, classrooms, and time slots."""
    async with session_maker() as session:
        subj1 = Subject(name="Алгоритмы и структуры данных", code="CS-101")
        subj2 = Subject(name="Базы данных", code="CS-202")

        teacher1 = Teacher(
            full_name="Иванов Иван Иванович",
            email="ivanov@mipt.ru",
            department="АТП",
            position="Доцент",
        )
        teacher2 = Teacher(
            full_name="Петров Пётр Петрович",
            email="petrov@mipt.ru",
            department="ВМ",
            position="Профессор",
        )

        group1 = Group(
            name="Б05-301",
            faculty="ФПМИ",
            course_number=3,
            student_count=25,
        )
        group2 = Group(
            name="Б05-302",
            faculty="ФПМИ",
            course_number=3,
            student_count=28,
        )

        room_large = Classroom(
            building="ГК",
            room_number="110",
            capacity=100,
            has_projector=True,
            has_computers=False,
        )
        room_medium = Classroom(
            building="УЛК",
            room_number="412",
            capacity=30,
            has_projector=True,
            has_computers=True,
        )
        room_small = Classroom(
            building="ЛК",
            room_number="205",
            capacity=15,
            has_projector=False,
            has_computers=False,
        )

        slot1 = TimeSlot(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(10, 25),
            day_of_week=1,
        )
        slot2 = TimeSlot(
            slot_number=2,
            start_time=time(10, 45),
            end_time=time(12, 10),
            day_of_week=1,
        )

        session.add_all(
            [
                subj1,
                subj2,
                teacher1,
                teacher2,
                group1,
                group2,
                room_large,
                room_medium,
                room_small,
                slot1,
                slot2,
            ]
        )
        await session.commit()

        return {
            "subj1": subj1.id,
            "subj2": subj2.id,
            "teacher1": teacher1.id,
            "teacher2": teacher2.id,
            "group1": group1.id,
            "group2": group2.id,
            "room_large": room_large.id,
            "room_medium": room_medium.id,
            "room_small": room_small.id,
            "slot1": slot1.id,
            "slot2": slot2.id,
        }


@pytest.mark.asyncio
async def test_create_get_and_list_valid_lesson(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """POST /api/v1/lessons saves valid lesson (201) and GET retrieves it with nested objects."""
    client, session_maker = db_context
    refs = await _seed_reference_entities(session_maker)

    payload = {
        "subject_id": refs["subj1"],
        "teacher_id": refs["teacher1"],
        "group_id": refs["group1"],
        "classroom_id": refs["room_medium"],
        "time_slot_id": refs["slot1"],
        "lesson_type": "LECTURE",
        "parity": "ALWAYS",
        "specific_date": None,
    }

    create_res = await client.post("/api/v1/lessons", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    lesson_id = created["id"]
    assert created["subject_id"] == refs["subj1"]
    assert created["teacher_id"] == refs["teacher1"]
    assert created["group_id"] == refs["group1"]
    assert created["classroom_id"] == refs["room_medium"]
    assert created["time_slot_id"] == refs["slot1"]
    assert created["lesson_type"] == "LECTURE"
    assert created["parity"] == "ALWAYS"
    assert created["subject"]["name"] == "Алгоритмы и структуры данных"
    assert created["teacher"]["full_name"] == "Иванов Иван Иванович"
    assert created["group"]["name"] == "Б05-301"
    assert created["classroom"]["room_number"] == "412"
    assert created["time_slot"]["slot_number"] == 1

    get_res = await client.get(f"/api/v1/lessons/{lesson_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == lesson_id

    list_res = await client.get("/api/v1/lessons/", params={"group_id": refs["group1"]})
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["id"] == lesson_id


@pytest.mark.asyncio
async def test_get_lesson_not_found_returns_404(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/lessons/{id} returns 404 for a non-existent lesson."""
    client, _ = db_context
    res = await client.get("/api/v1/lessons/9999")
    assert res.status_code == 404
    assert "9999" in res.json()["detail"]


@pytest.mark.asyncio
async def test_create_conflicting_lesson_returns_409_with_conflict_list(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """POST /api/v1/lessons returns HTTP 409 Conflict with all detected violations."""
    client, session_maker = db_context
    refs = await _seed_reference_entities(session_maker)

    first_res = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subj1"],
            "teacher_id": refs["teacher1"],
            "group_id": refs["group1"],
            "classroom_id": refs["room_medium"],
            "time_slot_id": refs["slot1"],
            "lesson_type": "LECTURE",
            "parity": "ALWAYS",
        },
    )
    assert first_res.status_code == 201
    existing_id = first_res.json()["id"]

    # Attempt to schedule a lesson in the same slot with the same teacher, same group,
    # and a classroom whose capacity (15) is smaller than group1's student_count (25).
    conflict_res = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subj2"],
            "teacher_id": refs["teacher1"],
            "group_id": refs["group1"],
            "classroom_id": refs["room_small"],
            "time_slot_id": refs["slot1"],
            "lesson_type": "SEMINAR",
            "parity": "ODD_WEEK",
        },
    )
    assert conflict_res.status_code == 409
    body = conflict_res.json()
    conflicts = body["conflicts"]
    assert body["detail"]["conflicts"] == conflicts
    assert [c["conflict_type"] for c in conflicts] == [
        "TEACHER_BUSY",
        "GROUP_BUSY",
        "CAPACITY_EXCEEDED",
    ]
    assert conflicts[0]["conflicting_lesson_id"] == existing_id
    assert conflicts[1]["conflicting_lesson_id"] == existing_id
    assert conflicts[2]["conflicting_lesson_id"] is None


@pytest.mark.asyncio
async def test_update_lesson_valid_and_conflict(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """PUT /api/v1/lessons/{id} updates lesson without self-conflict and returns 409 on clash."""
    client, session_maker = db_context
    refs = await _seed_reference_entities(session_maker)

    res1 = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subj1"],
            "teacher_id": refs["teacher1"],
            "group_id": refs["group1"],
            "classroom_id": refs["room_medium"],
            "time_slot_id": refs["slot1"],
            "lesson_type": "LECTURE",
            "parity": "ODD_WEEK",
        },
    )
    assert res1.status_code == 201
    lesson1_id = res1.json()["id"]

    res2 = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subj2"],
            "teacher_id": refs["teacher2"],
            "group_id": refs["group2"],
            "classroom_id": refs["room_large"],
            "time_slot_id": refs["slot1"],
            "lesson_type": "SEMINAR",
            "parity": "ODD_WEEK",
        },
    )
    assert res2.status_code == 201
    lesson2_id = res2.json()["id"]

    # Updating lesson1 in-place (changing lesson_type) must not conflict with itself.
    update_ok = await client.put(
        f"/api/v1/lessons/{lesson1_id}",
        json={"lesson_type": "LAB"},
    )
    assert update_ok.status_code == 200
    assert update_ok.json()["lesson_type"] == "LAB"

    # Moving lesson2 into room_medium (occupied by lesson1 in slot1 on ODD_WEEK) returns 409.
    update_conflict = await client.put(
        f"/api/v1/lessons/{lesson2_id}",
        json={"classroom_id": refs["room_medium"]},
    )
    assert update_conflict.status_code == 409
    conflicts = update_conflict.json()["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "CLASSROOM_BUSY"
    assert conflicts[0]["conflicting_lesson_id"] == lesson1_id

    # Updating a non-existent lesson returns 404.
    update_missing = await client.put("/api/v1/lessons/9999", json={"lesson_type": "LAB"})
    assert update_missing.status_code == 404


@pytest.mark.asyncio
async def test_delete_lesson_frees_slot_resources(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """DELETE /api/v1/lessons/{id} returns 204 and frees teacher, classroom, and group in slot."""
    client, session_maker = db_context
    refs = await _seed_reference_entities(session_maker)

    payload = {
        "subject_id": refs["subj1"],
        "teacher_id": refs["teacher1"],
        "group_id": refs["group1"],
        "classroom_id": refs["room_medium"],
        "time_slot_id": refs["slot1"],
        "lesson_type": "LECTURE",
        "parity": "ALWAYS",
    }

    first_res = await client.post("/api/v1/lessons", json=payload)
    assert first_res.status_code == 201
    lesson_id = first_res.json()["id"]

    # While first lesson exists, scheduling the same slot fails with 409.
    dup_res = await client.post("/api/v1/lessons", json=payload)
    assert dup_res.status_code == 409

    # Delete the lesson (204 No Content).
    del_res = await client.delete(f"/api/v1/lessons/{lesson_id}")
    assert del_res.status_code == 204

    # Subsequent delete or get returns 404.
    assert (await client.delete(f"/api/v1/lessons/{lesson_id}")).status_code == 404
    assert (await client.get(f"/api/v1/lessons/{lesson_id}")).status_code == 404

    # Slot resources are now free: scheduling in the same slot succeeds (201 Created).
    recreate_res = await client.post("/api/v1/lessons", json=payload)
    assert recreate_res.status_code == 201
