"""API tests for schedule view endpoints (/api/v1/schedule)."""

from collections.abc import AsyncGenerator
from datetime import date, time

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
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
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


async def _seed_schedule_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    """Seed sample groups, teachers, subjects, classrooms, time slots, and lessons."""
    async with session_maker() as session:
        g1 = Group(
            name="Б05-201",
            faculty="ФПМИ",
            course_number=2,
            student_count=28,
            is_active=True,
        )
        g2 = Group(
            name="Б05-202",
            faculty="ФПМИ",
            course_number=2,
            student_count=25,
            is_active=True,
        )
        g_empty = Group(
            name="Б05-203",
            faculty="ФПМИ",
            course_number=2,
            student_count=20,
            is_active=True,
        )

        t1 = Teacher(
            full_name="Иванов Иван Иванович",
            email="ivanov@mipt.ru",
            department="Кафедра высшей математики",
            position="Профессор",
            is_active=True,
        )
        t2 = Teacher(
            full_name="Петров Пётр Петрович",
            email="petrov@mipt.ru",
            department="Кафедра алгоритмов и технологий программирования",
            position="Доцент",
            is_active=True,
        )
        t_empty = Teacher(
            full_name="Сидоров Сидор Сидорович",
            email="sidorov@mipt.ru",
            department="Кафедра общей физики",
            position="Старший преподаватель",
            is_active=True,
        )

        s_math = Subject(
            name="Математический анализ",
            code="MATH-201",
            description="Курс математического анализа",
        )
        s_algo = Subject(
            name="Алгоритмы и структуры данных",
            code="CS-202",
            description="Курс АиСД",
        )
        s_phys = Subject(
            name="Общая физика",
            code="PHYS-201",
            description="Электричество и магнетизм",
        )

        c_lect = Classroom(
            building="ГК",
            room_number="110",
            capacity=150,
            has_projector=True,
            has_computers=False,
            is_active=True,
        )
        c_lab = Classroom(
            building="УЛК",
            room_number="412",
            capacity=30,
            has_projector=True,
            has_computers=True,
            is_active=True,
        )

        # Monday slot 1 & slot 3, Wednesday slot 2
        ts_mon_1 = TimeSlot(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(10, 25),
            day_of_week=1,
        )
        ts_mon_3 = TimeSlot(
            slot_number=3,
            start_time=time(12, 20),
            end_time=time(13, 45),
            day_of_week=1,
        )
        ts_wed_2 = TimeSlot(
            slot_number=2,
            start_time=time(10, 45),
            end_time=time(12, 10),
            day_of_week=3,
        )

        session.add_all(
            [
                g1,
                g2,
                g_empty,
                t1,
                t2,
                t_empty,
                s_math,
                s_algo,
                s_phys,
                c_lect,
                c_lab,
                ts_mon_1,
                ts_mon_3,
                ts_wed_2,
            ]
        )
        await session.flush()

        # Insert Monday slot 3 BEFORE Monday slot 1 to verify sorting by slot_number
        l_mon_slot3_odd = Lesson(
            subject_id=s_algo.id,
            teacher_id=t2.id,
            group_id=g1.id,
            classroom_id=c_lab.id,
            time_slot_id=ts_mon_3.id,
            lesson_type=LessonType.LAB,
            parity=WeekParity.ODD_WEEK,
            specific_date=None,
        )
        l_mon_slot3_even = Lesson(
            subject_id=s_phys.id,
            teacher_id=t1.id,
            group_id=g1.id,
            classroom_id=c_lect.id,
            time_slot_id=ts_mon_3.id,
            lesson_type=LessonType.SEMINAR,
            parity=WeekParity.EVEN_WEEK,
            specific_date=None,
        )
        l_mon_slot1_always = Lesson(
            subject_id=s_math.id,
            teacher_id=t1.id,
            group_id=g1.id,
            classroom_id=c_lect.id,
            time_slot_id=ts_mon_1.id,
            lesson_type=LessonType.LECTURE,
            parity=WeekParity.ALWAYS,
            specific_date=None,
        )
        # Wednesday slot 2 recurring lesson for g2 with t1
        l_wed_g2 = Lesson(
            subject_id=s_math.id,
            teacher_id=t1.id,
            group_id=g2.id,
            classroom_id=c_lect.id,
            time_slot_id=ts_wed_2.id,
            lesson_type=LessonType.SEMINAR,
            parity=WeekParity.ALWAYS,
            specific_date=None,
        )
        # One-off lesson on Wednesday 2026-10-21 for g1 with t2
        l_wed_specific = Lesson(
            subject_id=s_algo.id,
            teacher_id=t2.id,
            group_id=g1.id,
            classroom_id=c_lab.id,
            time_slot_id=ts_wed_2.id,
            lesson_type=LessonType.SEMINAR,
            parity=WeekParity.ALWAYS,
            specific_date=date(2026, 10, 21),
        )

        session.add_all(
            [
                l_mon_slot3_odd,
                l_mon_slot3_even,
                l_mon_slot1_always,
                l_wed_g2,
                l_wed_specific,
            ]
        )
        await session.commit()

        return {
            "g1_id": g1.id,
            "g2_id": g2.id,
            "g_empty_id": g_empty.id,
            "t1_id": t1.id,
            "t2_id": t2.id,
            "t_empty_id": t_empty.id,
        }


@pytest.mark.asyncio
async def test_get_group_schedule_not_found(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id} returns 404 for nonexistent group."""
    client, _ = db_context
    response = await client.get("/api/v1/schedule/group/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Group with id 99999 not found"


@pytest.mark.asyncio
async def test_get_teacher_schedule_not_found(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/teacher/{id} returns 404 for nonexistent teacher."""
    client, _ = db_context
    response = await client.get("/api/v1/schedule/teacher/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher with id 99999 not found"


@pytest.mark.asyncio
async def test_get_group_schedule_empty_days(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id} returns days 1..6 with empty lessons when none exist."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    response = await client.get(f"/api/v1/schedule/group/{ids['g_empty_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["group_id"] == ids["g_empty_id"]
    assert data["group"]["name"] == "Б05-203"
    assert data["parity"] is None
    assert data["date"] is None
    assert len(data["days"]) == 6
    for idx, day_entry in enumerate(data["days"], start=1):
        assert day_entry["day_of_week"] == idx
        assert day_entry["lessons"] == []


@pytest.mark.asyncio
async def test_get_teacher_schedule_empty_days(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/teacher/{id} returns days 1..6 with empty lessons when none exist."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    response = await client.get(f"/api/v1/schedule/teacher/{ids['t_empty_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["teacher_id"] == ids["t_empty_id"]
    assert data["teacher"]["full_name"] == "Сидоров Сидор Сидорович"
    assert len(data["days"]) == 6
    assert all(day["lessons"] == [] for day in data["days"])


@pytest.mark.asyncio
async def test_get_group_schedule_sorting_and_nested_details(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id} groups by day, sorts by slot, and embeds nested info."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    response = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}")
    assert response.status_code == 200
    data = response.json()

    assert data["group_id"] == ids["g1_id"]
    assert data["group"]["name"] == "Б05-201"
    assert len(data["days"]) == 6

    monday = data["days"][0]
    assert monday["day_of_week"] == 1
    assert len(monday["lessons"]) == 3

    # Verify sorted by slot_number (slot 1 first, then slot 3 lessons)
    slot_numbers = [lesson["time_slot"]["slot_number"] for lesson in monday["lessons"]]
    assert slot_numbers == [1, 3, 3]

    first_lesson = monday["lessons"][0]
    assert first_lesson["subject"]["name"] == "Математический анализ"
    assert first_lesson["subject"]["code"] == "MATH-201"
    assert first_lesson["teacher"]["full_name"] == "Иванов Иван Иванович"
    assert first_lesson["group"]["name"] == "Б05-201"
    assert first_lesson["classroom"]["building"] == "ГК"
    assert first_lesson["classroom"]["room_number"] == "110"
    assert first_lesson["time_slot"]["start_time"] == "09:00:00"
    assert first_lesson["lesson_type"] == "LECTURE"
    assert first_lesson["parity"] == "ALWAYS"

    # Tuesday has no lessons
    assert data["days"][1]["day_of_week"] == 2
    assert data["days"][1]["lessons"] == []

    # Wednesday has 1 lesson for g1
    wednesday = data["days"][2]
    assert wednesday["day_of_week"] == 3
    assert len(wednesday["lessons"]) == 1
    assert wednesday["lessons"][0]["specific_date"] == "2026-10-21"


@pytest.mark.asyncio
async def test_get_group_schedule_filter_by_parity(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id}?parity=... filters ODD_WEEK, EVEN_WEEK, ALWAYS."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    # ODD_WEEK includes ALWAYS and ODD_WEEK
    res_odd = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?parity=ODD_WEEK")
    assert res_odd.status_code == 200
    odd_data = res_odd.json()
    assert odd_data["parity"] == "ODD_WEEK"
    monday_odd = odd_data["days"][0]["lessons"]
    assert len(monday_odd) == 2
    assert [item["parity"] for item in monday_odd] == ["ALWAYS", "ODD_WEEK"]

    # EVEN_WEEK includes ALWAYS and EVEN_WEEK
    res_even = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?parity=EVEN_WEEK")
    assert res_even.status_code == 200
    even_data = res_even.json()
    assert even_data["parity"] == "EVEN_WEEK"
    monday_even = even_data["days"][0]["lessons"]
    assert len(monday_even) == 2
    assert [item["parity"] for item in monday_even] == ["ALWAYS", "EVEN_WEEK"]

    # ALWAYS includes only ALWAYS
    res_always = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?parity=ALWAYS")
    assert res_always.status_code == 200
    always_data = res_always.json()
    monday_always = always_data["days"][0]["lessons"]
    assert len(monday_always) == 1
    assert monday_always[0]["parity"] == "ALWAYS"


@pytest.mark.asyncio
async def test_get_group_schedule_filter_by_date(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id}?date=... filters recurring and specific-date lessons."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    # Wednesday 2026-10-21 matches the specific_date lesson for g1
    res_match = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?date=2026-10-21")
    assert res_match.status_code == 200
    match_data = res_match.json()
    assert match_data["date"] == "2026-10-21"
    assert match_data["days"][0]["lessons"] == []  # Monday empty when filtering for Wednesday
    assert len(match_data["days"][2]["lessons"]) == 1
    assert match_data["days"][2]["lessons"][0]["specific_date"] == "2026-10-21"

    # Next Wednesday 2026-10-28 does NOT match specific_date=2026-10-21
    res_next_wed = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?date=2026-10-28")
    assert res_next_wed.status_code == 200
    assert res_next_wed.json()["days"][2]["lessons"] == []

    # Monday 2026-10-19 with parity=ODD_WEEK returns recurring Monday lessons for ODD_WEEK
    res_mon_odd = await client.get(
        f"/api/v1/schedule/group/{ids['g1_id']}?date=2026-10-19&parity=ODD_WEEK"
    )
    assert res_mon_odd.status_code == 200
    mon_lessons = res_mon_odd.json()["days"][0]["lessons"]
    assert len(mon_lessons) == 2
    assert [item["time_slot"]["slot_number"] for item in mon_lessons] == [1, 3]


@pytest.mark.asyncio
async def test_date_filter_uses_iso_week_parity(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """A date selects the recurring lessons for its ISO week in both schedules."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    for day, expected in [("2026-10-19", "ODD_WEEK"), ("2026-10-26", "EVEN_WEEK")]:
        response = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}?date={day}")
        assert response.status_code == 200
        lessons = response.json()["days"][0]["lessons"]
        assert [lesson["parity"] for lesson in lessons] == ["ALWAYS", expected]

    odd = await client.get(f"/api/v1/schedule/teacher/{ids['t1_id']}?date=2026-10-19")
    even = await client.get(f"/api/v1/schedule/teacher/{ids['t1_id']}?date=2026-10-26")
    assert len(odd.json()["days"][0]["lessons"]) == 1
    assert len(even.json()["days"][0]["lessons"]) == 2


@pytest.mark.asyncio
async def test_get_teacher_schedule_with_filters(
    db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/teacher/{id} returns teacher's lessons across groups with filters."""
    client, session_maker = db_context
    ids = await _seed_schedule_data(session_maker)

    # Teacher t1 teaches Monday (slot 1 ALWAYS, slot 3 EVEN_WEEK for g1) and Wednesday for g2
    res_t1 = await client.get(f"/api/v1/schedule/teacher/{ids['t1_id']}")
    assert res_t1.status_code == 200
    t1_data = res_t1.json()
    assert t1_data["teacher_id"] == ids["t1_id"]
    assert t1_data["teacher"]["full_name"] == "Иванов Иван Иванович"
    assert len(t1_data["days"][0]["lessons"]) == 2  # Monday
    assert len(t1_data["days"][2]["lessons"]) == 1  # Wednesday (for group Б05-202)
    assert t1_data["days"][2]["lessons"][0]["group"]["name"] == "Б05-202"

    # Filter t1 by ODD_WEEK -> Monday only has slot 1 ALWAYS
    res_t1_odd = await client.get(f"/api/v1/schedule/teacher/{ids['t1_id']}?parity=ODD_WEEK")
    assert res_t1_odd.status_code == 200
    assert len(res_t1_odd.json()["days"][0]["lessons"]) == 1
    assert res_t1_odd.json()["days"][0]["lessons"][0]["parity"] == "ALWAYS"

    # Filter t1 by date=2026-10-21 (Wednesday) -> returns recurring Wednesday lesson for g2
    res_t1_wed = await client.get(f"/api/v1/schedule/teacher/{ids['t1_id']}?date=2026-10-21")
    assert res_t1_wed.status_code == 200
    assert res_t1_wed.json()["days"][0]["lessons"] == []
    assert len(res_t1_wed.json()["days"][2]["lessons"]) == 1
