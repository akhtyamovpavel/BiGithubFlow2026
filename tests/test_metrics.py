"""Automated tests for Prometheus metrics endpoint (/metrics) and business counters (#49)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
    get_async_session,
)
from schedule_service.core.logging import REQUEST_ID_HEADER
from schedule_service.main import app
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson
from schedule_service.models.lesson_exception import LessonException
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot


def _parse_metrics(text: str) -> dict[str, dict[tuple[tuple[str, str], ...], float]]:
    """Parse Prometheus text exposition into {sample_name: {sorted_labels: value}}."""
    parsed: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            label_key = tuple(sorted(sample.labels.items()))
            parsed.setdefault(sample.name, {})[label_key] = float(sample.value)
    return parsed


def _metric_value(
    metrics: dict[str, dict[tuple[tuple[str, str], ...], float]],
    sample_name: str,
    **labels: str,
) -> float:
    return metrics.get(sample_name, {}).get(tuple(sorted(labels.items())), 0.0)


@pytest_asyncio.fixture
async def metrics_db_context() -> (
    AsyncGenerator[
        tuple[AsyncClient, async_sessionmaker[AsyncSession]],
        None,
    ]
):
    """Provide AsyncClient and in-memory SQLite database wired to the FastAPI app."""
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
                    LessonException.__table__,  # type: ignore[list-item]
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

    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


async def _seed_entities(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with session_maker() as session:
        subj = Subject(name="Monitoring 101", code="MON-101")
        teacher = Teacher(
            full_name="Иванов Пётр",
            email="metrics-teacher@mipt.ru",
            department="CS",
        )
        group = Group(name="Б05-501", faculty="ФПМИ", course_number=4, student_count=30)
        room_ok = Classroom(building="ГК", room_number="301", capacity=40)
        room_small = Classroom(building="ГК", room_number="302", capacity=10)
        slot1 = TimeSlot(slot_number=1, start_time=time(9, 0), end_time=time(10, 25), day_of_week=1)
        slot2 = TimeSlot(
            slot_number=2, start_time=time(10, 45), end_time=time(12, 10), day_of_week=1
        )
        session.add_all([subj, teacher, group, room_ok, room_small, slot1, slot2])
        await session.commit()
        return {
            "subject_id": subj.id,
            "teacher_id": teacher.id,
            "group_id": group.id,
            "room_ok_id": room_ok.id,
            "room_small_id": room_small.id,
            "slot1_id": slot1.id,
            "slot2_id": slot2.id,
        }


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_valid_prometheus_format_and_red_metrics(
    metrics_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = metrics_db_context

    before_resp = await client.get("/metrics")
    assert before_resp.status_code == 200
    assert "text/plain" in before_resp.headers["content-type"]
    before = _parse_metrics(before_resp.text)

    health_before = _metric_value(
        before,
        "http_requests_total",
        method="GET",
        route="/health",
        status_code="200",
        status_class="2xx",
    )
    duration_count_before = _metric_value(
        before,
        "http_request_duration_seconds_count",
        method="GET",
        route="/health",
    )

    health_resp = await client.get("/health")
    assert health_resp.status_code == 200

    after_resp = await client.get("/metrics")
    assert after_resp.status_code == 200
    after = _parse_metrics(after_resp.text)

    health_after = _metric_value(
        after,
        "http_requests_total",
        method="GET",
        route="/health",
        status_code="200",
        status_class="2xx",
    )
    duration_count_after = _metric_value(
        after,
        "http_request_duration_seconds_count",
        method="GET",
        route="/health",
    )

    assert health_after == health_before + 1.0
    assert duration_count_after == duration_count_before + 1.0
    assert "http_request_duration_seconds_bucket" in after


@pytest.mark.asyncio
async def test_business_counters_and_db_entity_gauges_update_accurately(
    metrics_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_maker = metrics_db_context
    refs = await _seed_entities(session_maker)

    before = _parse_metrics((await client.get("/metrics")).text)

    # Verify initial DB entity gauges match seeded counts.
    assert _metric_value(before, "schedule_db_entities_count", entity="groups") == 1.0
    assert _metric_value(before, "schedule_db_entities_count", entity="teachers") == 1.0
    assert _metric_value(before, "schedule_db_entities_count", entity="classrooms") == 2.0
    assert _metric_value(before, "schedule_db_entities_count", entity="subjects") == 1.0
    assert _metric_value(before, "schedule_db_entities_count", entity="time_slots") == 2.0
    assert _metric_value(before, "schedule_db_entities_count", entity="lessons") == 0.0

    created_before = _metric_value(before, "schedule_lessons_created_total", lesson_type="LECTURE")
    teacher_conflict_before = _metric_value(
        before, "schedule_conflicts_detected_total", conflict_type="TEACHER_BUSY"
    )
    group_conflict_before = _metric_value(
        before, "schedule_conflicts_detected_total", conflict_type="GROUP_BUSY"
    )
    capacity_conflict_before = _metric_value(
        before, "schedule_conflicts_detected_total", conflict_type="CAPACITY_EXCEEDED"
    )
    export_ics_group_before = _metric_value(
        before, "schedule_exports_total", format="ics", target="group"
    )
    export_csv_group_before = _metric_value(
        before, "schedule_exports_total", format="csv", target="group"
    )
    export_ics_teacher_before = _metric_value(
        before, "schedule_exports_total", format="ics", target="teacher"
    )
    export_csv_teacher_before = _metric_value(
        before, "schedule_exports_total", format="csv", target="teacher"
    )

    # 1. Create a valid lesson.
    create_res = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subject_id"],
            "teacher_id": refs["teacher_id"],
            "group_id": refs["group_id"],
            "classroom_id": refs["room_ok_id"],
            "time_slot_id": refs["slot1_id"],
            "lesson_type": "LECTURE",
            "parity": "ALWAYS",
        },
    )
    assert create_res.status_code == 201
    lesson_id = create_res.json()["id"]

    # 2. Trigger a multi-conflict 409 (TEACHER_BUSY + GROUP_BUSY + CAPACITY_EXCEEDED).
    conflict_res = await client.post(
        "/api/v1/lessons",
        json={
            "subject_id": refs["subject_id"],
            "teacher_id": refs["teacher_id"],
            "group_id": refs["group_id"],
            "classroom_id": refs["room_small_id"],
            "time_slot_id": refs["slot1_id"],
            "lesson_type": "SEMINAR",
            "parity": "ODD_WEEK",
        },
    )
    assert conflict_res.status_code == 409

    # 3. Trigger all four schedule export endpoints.
    assert (
        await client.get(f"/api/v1/schedule/group/{refs['group_id']}/export/ics")
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/schedule/group/{refs['group_id']}/export/csv")
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/schedule/teacher/{refs['teacher_id']}/export/ics")
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/schedule/teacher/{refs['teacher_id']}/export/csv")
    ).status_code == 200

    after = _parse_metrics((await client.get("/metrics")).text)

    assert (
        _metric_value(after, "schedule_lessons_created_total", lesson_type="LECTURE")
        == created_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_conflicts_detected_total", conflict_type="TEACHER_BUSY")
        == teacher_conflict_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_conflicts_detected_total", conflict_type="GROUP_BUSY")
        == group_conflict_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_conflicts_detected_total", conflict_type="CAPACITY_EXCEEDED")
        == capacity_conflict_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_exports_total", format="ics", target="group")
        == export_ics_group_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_exports_total", format="csv", target="group")
        == export_csv_group_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_exports_total", format="ics", target="teacher")
        == export_ics_teacher_before + 1.0
    )
    assert (
        _metric_value(after, "schedule_exports_total", format="csv", target="teacher")
        == export_csv_teacher_before + 1.0
    )
    assert _metric_value(after, "schedule_db_entities_count", entity="lessons") == 1.0

    # 4. Delete the lesson and verify DB entity gauge drops back to 0.
    assert (await client.delete(f"/api/v1/lessons/{lesson_id}")).status_code == 204
    after_delete = _parse_metrics((await client.get("/metrics")).text)
    assert _metric_value(after_delete, "schedule_db_entities_count", entity="lessons") == 0.0


@pytest.mark.asyncio
async def test_metrics_labels_exclude_pii_request_id_and_unbounded_values(
    metrics_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = metrics_db_context

    unique_request_id = "req-unbounded-cardinality-987654321"
    random_path_segment = "secret-user-email-alice@example.com-999888"

    resp_missing_lesson = await client.get(
        "/api/v1/lessons/987654",
        headers={REQUEST_ID_HEADER: unique_request_id},
    )
    assert resp_missing_lesson.status_code == 404

    resp_unknown_route = await client.get(
        f"/unknown/{random_path_segment}",
        headers={REQUEST_ID_HEADER: "req-another-unbounded-123456"},
    )
    assert resp_unknown_route.status_code == 404

    metrics_resp = await client.get("/metrics")
    assert metrics_resp.status_code == 200
    body = metrics_resp.text

    # No request_id, PII, or raw path parameter values may appear in Prometheus output.
    assert unique_request_id not in body
    assert "req-another-unbounded-123456" not in body
    assert random_path_segment not in body
    assert "987654" not in body

    parsed = _parse_metrics(body)
    for samples in parsed.values():
        for label_pairs in samples:
            label_names = {name for name, _ in label_pairs}
            assert "request_id" not in label_names
            assert "email" not in label_names
            assert "username" not in label_names
            assert "user_id" not in label_names

    # Parameterized route and unmatched 404 route must be normalized to bounded labels.
    assert (
        _metric_value(
            parsed,
            "http_requests_total",
            method="GET",
            route="/api/v1/lessons/{lesson_id}",
            status_code="404",
            status_class="4xx",
        )
        >= 1.0
    )
    assert (
        _metric_value(
            parsed,
            "http_requests_total",
            method="GET",
            route="unmatched",
            status_code="404",
            status_class="4xx",
        )
        >= 1.0
    )
