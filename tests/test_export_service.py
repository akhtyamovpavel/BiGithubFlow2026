"""Unit and API tests for iCalendar (.ics) and CSV schedule export (Issue #19)."""

import csv
import datetime as dt
import io
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from icalendar import Calendar
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
from schedule_service.services.export_service import (
    CSV_COLUMNS,
    CalendarExportService,
    date_week_parity,
    export_group_to_csv,
    export_group_to_ics,
)


@pytest_asyncio.fixture
async def export_db_context() -> (
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
        yield client, session_maker

    app.dependency_overrides.clear()
    await engine.dispose()


async def _seed_export_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    """Seed reference entities and lessons for export tests."""
    async with session_maker() as session:
        group = Group(
            name="Б05-201",
            faculty="ФПМИ",
            course_number=2,
            student_count=28,
            is_active=True,
        )
        teacher1 = Teacher(
            full_name="Иванов Иван Иванович",
            email="ivanov@mipt.ru",
            department="Кафедра высшей математики",
            position="Профессор",
            is_active=True,
        )
        teacher2 = Teacher(
            full_name="Петров Пётр Петрович",
            email="petrov@mipt.ru",
            department="Кафедра АиСД",
            position="Доцент",
            is_active=True,
        )
        subj_math = Subject(
            name="Математический анализ",
            code="MATH-201",
            description="Курс математического анализа",
        )
        subj_algo = Subject(
            name="Алгоритмы и структуры данных",
            code="CS-202",
            description="Курс АиСД",
        )
        subj_phys = Subject(
            name="Общая физика",
            code="PHYS-201",
            description="Курс общей физики",
        )
        room_gk = Classroom(
            building="ГК",
            room_number="110",
            capacity=150,
            has_projector=True,
            has_computers=False,
            is_active=True,
        )
        room_ulk = Classroom(
            building="УЛК",
            room_number="412",
            capacity=30,
            has_projector=True,
            has_computers=True,
            is_active=True,
        )

        # Monday slot 1 & slot 2, Wednesday slot 2
        ts_mon_1 = TimeSlot(
            slot_number=1,
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 25),
            day_of_week=1,
        )
        ts_mon_2 = TimeSlot(
            slot_number=2,
            start_time=dt.time(10, 45),
            end_time=dt.time(12, 10),
            day_of_week=1,
        )
        ts_wed_2 = TimeSlot(
            slot_number=2,
            start_time=dt.time(10, 45),
            end_time=dt.time(12, 10),
            day_of_week=3,
        )

        session.add_all(
            [
                group,
                teacher1,
                teacher2,
                subj_math,
                subj_algo,
                subj_phys,
                room_gk,
                room_ulk,
                ts_mon_1,
                ts_mon_2,
                ts_wed_2,
            ]
        )
        await session.flush()

        # Monday slot 1: ALWAYS
        l_always = Lesson(
            subject_id=subj_math.id,
            teacher_id=teacher1.id,
            group_id=group.id,
            classroom_id=room_gk.id,
            time_slot_id=ts_mon_1.id,
            lesson_type=LessonType.LECTURE,
            parity=WeekParity.ALWAYS,
            specific_date=None,
        )
        # Monday slot 2: ODD_WEEK
        l_odd = Lesson(
            subject_id=subj_algo.id,
            teacher_id=teacher2.id,
            group_id=group.id,
            classroom_id=room_ulk.id,
            time_slot_id=ts_mon_2.id,
            lesson_type=LessonType.LAB,
            parity=WeekParity.ODD_WEEK,
            specific_date=None,
        )
        # Monday slot 2: EVEN_WEEK
        l_even = Lesson(
            subject_id=subj_phys.id,
            teacher_id=teacher1.id,
            group_id=group.id,
            classroom_id=room_gk.id,
            time_slot_id=ts_mon_2.id,
            lesson_type=LessonType.SEMINAR,
            parity=WeekParity.EVEN_WEEK,
            specific_date=None,
        )
        # Wednesday 2026-10-21 (ISO week 43, odd): specific_date lesson
        l_specific = Lesson(
            subject_id=subj_algo.id,
            teacher_id=teacher2.id,
            group_id=group.id,
            classroom_id=room_ulk.id,
            time_slot_id=ts_wed_2.id,
            lesson_type=LessonType.SEMINAR,
            parity=WeekParity.ALWAYS,
            specific_date=dt.date(2026, 10, 21),
        )

        session.add_all([l_always, l_odd, l_even, l_specific])
        await session.commit()

        return {
            "group_id": group.id,
            "teacher1_id": teacher1.id,
            "teacher2_id": teacher2.id,
        }


def test_date_week_parity() -> None:
    """Verify ISO week parity helper on known even and odd weeks."""
    # 2026-10-12 is Monday of ISO week 42 (even)
    assert date_week_parity(dt.date(2026, 10, 12)) == WeekParity.EVEN_WEEK
    # 2026-10-19 is Monday of ISO week 43 (odd)
    assert date_week_parity(dt.date(2026, 10, 19)) == WeekParity.ODD_WEEK


@pytest.mark.asyncio
async def test_service_export_group_to_ics_rfc5545_and_parity(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Verify RFC 5545 compliance and parity expansion across an even and odd week."""
    _, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)

    # Range covering Monday 2026-10-12 (week 42, EVEN) through Sunday 2026-10-25 (week 43, ODD)
    start_date = dt.date(2026, 10, 12)
    end_date = dt.date(2026, 10, 25)

    async with session_maker() as session:
        service = CalendarExportService(session)
        ics_bytes = await service.export_group_to_ics(
            ids["group_id"],
            start_date=start_date,
            end_date=end_date,
        )

    assert isinstance(ics_bytes, bytes)
    text = ics_bytes.decode("utf-8")
    assert "BEGIN:VCALENDAR" in text
    assert "VERSION:2.0" in text
    assert "END:VCALENDAR" in text

    cal = Calendar.from_ical(ics_bytes)
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    # Week 42 (even) Monday: ALWAYS + EVEN_WEEK (2 events)
    # Week 43 (odd) Monday: ALWAYS + ODD_WEEK (2 events)
    # Week 43 Wednesday 2026-10-21: specific_date (1 event)
    # Total = 5 VEVENTs
    assert len(events) == 5

    summaries = [str(ev.get("summary")) for ev in events]
    assert summaries.count("Математический анализ (LECTURE)") == 2
    assert summaries.count("Общая физика (SEMINAR)") == 1
    assert summaries.count("Алгоритмы и структуры данных (LAB)") == 1
    assert summaries.count("Алгоритмы и структуры данных (SEMINAR)") == 1

    first_ev = events[0]
    assert first_ev.get("uid") is not None
    assert first_ev.get("dtstart").dt == dt.datetime(2026, 10, 12, 9, 0)
    assert first_ev.get("dtend").dt == dt.datetime(2026, 10, 12, 10, 25)
    assert str(first_ev.get("location")) == "ГК, ауд. 110"
    assert "Иванов Иван Иванович" in str(first_ev.get("description"))


@pytest.mark.asyncio
async def test_service_export_group_to_csv_columns_and_rows(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Verify CSV export contains required Russian headers and properly formatted rows."""
    _, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)

    async with session_maker() as session:
        csv_text = await export_group_to_csv(session, ids["group_id"])

    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader[0] == CSV_COLUMNS
    assert reader[0] == [
        "День",
        "Время",
        "Предмет",
        "Преподаватель",
        "Аудитория",
        "Тип недели",
    ]
    # 4 lessons seeded for group
    assert len(reader) == 5
    assert reader[1] == [
        "Понедельник",
        "09:00-10:25",
        "Математический анализ",
        "Иванов Иван Иванович",
        "ГК 110",
        "ALWAYS",
    ]


@pytest.mark.asyncio
async def test_api_export_group_ics_endpoint(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id}/export/ics returns valid .ics attachment."""
    client, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)
    gid = ids["group_id"]

    response = await client.get(
        f"/api/v1/schedule/group/{gid}/export/ics?start_date=2026-10-19&end_date=2026-10-25"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="schedule_group_{gid}.ics"'
    )

    cal = Calendar.from_ical(response.content)
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    # Odd week 43: Monday ALWAYS + Monday ODD_WEEK + Wednesday 2026-10-21 specific_date = 3 events
    assert len(events) == 3


@pytest.mark.asyncio
async def test_api_export_group_csv_endpoint(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/group/{id}/export/csv returns valid .csv attachment."""
    client, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)
    gid = ids["group_id"]

    response = await client.get(f"/api/v1/schedule/group/{gid}/export/csv?parity=ODD_WEEK")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="schedule_group_{gid}.csv"'
    )

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == CSV_COLUMNS
    # ODD_WEEK filter excludes EVEN_WEEK lesson -> 3 lessons remain
    assert len(rows) == 4
    parities = [r[5] for r in rows[1:]]
    assert "EVEN_WEEK" not in parities


@pytest.mark.asyncio
async def test_api_export_teacher_ics_and_csv_endpoints(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/teacher/{id}/export/ics and /csv return valid attachments."""
    client, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)
    tid = ids["teacher1_id"]

    ics_res = await client.get(
        f"/api/v1/schedule/teacher/{tid}/export/ics?start_date=2026-10-12&end_date=2026-10-18"
    )
    assert ics_res.status_code == 200
    assert ics_res.headers["content-type"].startswith("text/calendar")
    assert (
        ics_res.headers["content-disposition"]
        == f'attachment; filename="schedule_teacher_{tid}.ics"'
    )
    cal = Calendar.from_ical(ics_res.content)
    events = [comp for comp in cal.walk() if comp.name == "VEVENT"]
    # Teacher 1 in even week 42 has Monday slot 1 ALWAYS and Monday slot 2 EVEN_WEEK = 2 events
    assert len(events) == 2

    csv_res = await client.get(f"/api/v1/schedule/teacher/{tid}/export/csv")
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert (
        csv_res.headers["content-disposition"]
        == f'attachment; filename="schedule_teacher_{tid}.csv"'
    )
    rows = list(csv.reader(io.StringIO(csv_res.text)))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_api_export_not_found_and_invalid_dates(
    export_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Verify 404 for nonexistent group/teacher and 422 when end_date < start_date."""
    client, session_maker = export_db_context
    ids = await _seed_export_data(session_maker)
    gid = ids["group_id"]

    assert (await client.get("/api/v1/schedule/group/99999/export/ics")).status_code == 404
    assert (await client.get("/api/v1/schedule/group/99999/export/csv")).status_code == 404
    assert (await client.get("/api/v1/schedule/teacher/99999/export/ics")).status_code == 404
    assert (await client.get("/api/v1/schedule/teacher/99999/export/csv")).status_code == 404

    bad_range = await client.get(
        f"/api/v1/schedule/group/{gid}/export/ics?start_date=2026-10-25&end_date=2026-10-12"
    )
    assert bad_range.status_code == 422

    # Default date range works when no dates are provided
    default_range = await client.get(f"/api/v1/schedule/group/{gid}/export/ics")
    assert default_range.status_code == 200
    assert b"BEGIN:VCALENDAR" in default_range.content

    async with session_maker() as session:
        with pytest.raises(LookupError):
            await export_group_to_ics(session, 99999)
