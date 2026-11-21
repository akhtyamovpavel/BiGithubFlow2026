"""Tests for JSON/readable logging, X-Request-ID propagation, secret scrubbing, and isolation."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import time
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schedule_service.core.auth import hash_password
from schedule_service.core.config import Settings
from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
    get_async_session,
)
from schedule_service.core.logging import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    ReadableFormatter,
    RequestIdFilter,
    get_request_id,
    resolve_log_format,
    resolve_request_id,
)
from schedule_service.core.middleware import RequestContextMiddleware
from schedule_service.main import app, create_app
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson
from schedule_service.models.lesson_exception import LessonException
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.models.user import LoginSession, User, UserRole


class _JsonLogCapture:
    """Attach a temporary JsonFormatter StreamHandler to capture serialized JSON logs."""

    def __init__(self, logger_name: str = "schedule_service") -> None:
        self._logger = logging.getLogger(logger_name)
        self._stream = io.StringIO()
        self._handler = logging.StreamHandler(self._stream)
        self._handler.setLevel(logging.DEBUG)
        self._handler.setFormatter(JsonFormatter())
        self._handler.addFilter(RequestIdFilter())
        self._prev_level = self._logger.level

    def __enter__(self) -> _JsonLogCapture:
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev_level)

    @property
    def raw(self) -> str:
        return self._stream.getvalue()

    def records(self) -> list[dict[str, Any]]:
        lines = [line for line in self.raw.splitlines() if line.strip()]
        return [json.loads(line) for line in lines]


@pytest_asyncio.fixture
async def lesson_db_context() -> (
    AsyncGenerator[
        tuple[AsyncClient, async_sessionmaker[AsyncSession]],
        None,
    ]
):
    """Provide AsyncClient and in-memory SQLite DB with all schedule and auth tables."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,  # type: ignore[list-item]
                    LoginSession.__table__,  # type: ignore[list-item]
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


async def _seed_lesson_refs(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with session_maker() as session:
        subj = Subject(name="Distributed Systems", code="DS-101")
        teacher = Teacher(
            full_name="Иванов Иван",
            email="ivanov-log@mipt.ru",
            department="CS",
        )
        group = Group(name="Б05-401", faculty="ФПМИ", course_number=4, student_count=25)
        room_ok = Classroom(building="ГК", room_number="201", capacity=40)
        room_small = Classroom(building="ГК", room_number="202", capacity=10)
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


# ---------------------------------------------------------------------------
# Unit tests: format selection, request_id validation, secret scrubbing
# ---------------------------------------------------------------------------


def test_resolve_log_format_auto_and_explicit() -> None:
    assert resolve_log_format(Settings(environment="development", log_format="auto")) == "text"
    assert resolve_log_format(Settings(environment="local", log_format="auto")) == "text"
    assert resolve_log_format(Settings(environment="production", log_format="auto")) == "json"
    assert resolve_log_format(Settings(environment="staging", log_format="auto")) == "json"
    assert resolve_log_format(Settings(environment="development", log_format="json")) == "json"
    assert resolve_log_format(Settings(environment="production", log_format="text")) == "text"


@pytest.mark.parametrize(
    "valid_id",
    [
        "9f86d081884c7d659a2feaa0c55ad015",
        "req-2026.trace_01",
        "550e8400-e29b-41d4-a716-446655440000",
    ],
)
def test_resolve_request_id_accepts_safe_values(valid_id: str) -> None:
    assert resolve_request_id(valid_id) == valid_id


@pytest.mark.parametrize(
    "unsafe_id",
    [
        None,
        "",
        "   ",
        "id-with-newline\r\nX-Injected: evil",
        "id with spaces",
        "<script>alert(1)</script>",
        "a" * 129,
    ],
)
def test_resolve_request_id_replaces_unsafe_values_with_uuid(unsafe_id: str | None) -> None:
    resolved = resolve_request_id(unsafe_id)
    assert resolved != unsafe_id
    parsed = uuid.UUID(resolved)
    assert parsed.version == 4


def test_formatters_exclude_passwords_tokens_and_sessions() -> None:
    record = logging.LogRecord(
        name="schedule_service.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Auth header Bearer super-secret-jwt password=hunter2 token=tok123",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-secret-test"
    record.password = "hunter2"
    record.access_token = "tok123"
    record.session_id = "sess-abc-999"
    record.authorization = "Bearer super-secret-jwt"
    record.nested = {"secret": "top-secret", "token_hash": "deadbeef", "safe": "visible"}
    record.lesson_id = 42

    json_line = JsonFormatter().format(record)
    parsed = json.loads(json_line)
    assert parsed["request_id"] == "req-secret-test"
    assert parsed["lesson_id"] == 42
    assert parsed["nested"] == {"safe": "visible"}
    for forbidden in ("password", "access_token", "session_id", "authorization"):
        assert forbidden not in parsed
    for leaked in (
        "hunter2",
        "tok123",
        "sess-abc-999",
        "super-secret-jwt",
        "top-secret",
        "deadbeef",
    ):
        assert leaked not in json_line

    readable_line = ReadableFormatter().format(record)
    assert "[req=req-secret-test]" in readable_line
    assert "lesson_id=42" in readable_line
    for leaked in (
        "hunter2",
        "tok123",
        "sess-abc-999",
        "super-secret-jwt",
        "top-secret",
        "deadbeef",
    ):
        assert leaked not in readable_line


# ---------------------------------------------------------------------------
# HTTP integration tests: X-Request-ID generation, propagation & errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_generated_and_matched_in_json_log() -> None:
    transport = ASGITransport(app=app)
    with _JsonLogCapture() as capture:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id is not None
    uuid.UUID(request_id)

    http_logs = [r for r in capture.records() if r.get("event") == "http_request"]
    assert len(http_logs) == 1
    log = http_logs[0]
    assert log["request_id"] == request_id
    assert log["method"] == "GET"
    assert log["path"] == "/health"
    assert log["status_code"] == 200
    assert isinstance(log["duration_ms"], int | float)
    assert log["duration_ms"] >= 0
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_request_id_propagated_from_valid_header_and_rejected_when_unsafe() -> None:
    transport = ASGITransport(app=app)
    incoming_id = "nginx-req-0123456789abcdef"

    with _JsonLogCapture() as capture:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            valid_resp = await client.get("/health", headers={REQUEST_ID_HEADER: incoming_id})
            unsafe_resp = await client.get(
                "/health",
                headers={REQUEST_ID_HEADER: "bad value with spaces"},
            )

    assert valid_resp.headers[REQUEST_ID_HEADER] == incoming_id
    unsafe_id = unsafe_resp.headers[REQUEST_ID_HEADER]
    assert unsafe_id != "bad value with spaces"
    uuid.UUID(unsafe_id)

    http_logs = [r for r in capture.records() if r.get("event") == "http_request"]
    assert [log["request_id"] for log in http_logs] == [incoming_id, unsafe_id]


@pytest.mark.asyncio
async def test_error_responses_include_matching_request_id(
    lesson_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = lesson_db_context

    with _JsonLogCapture() as capture:
        resp_404 = await client.get(
            "/api/v1/lessons/999999",
            headers={REQUEST_ID_HEADER: "err-404-id"},
        )
        resp_422 = await client.post(
            "/api/v1/lessons",
            json={"subject_id": -1},
            headers={REQUEST_ID_HEADER: "err-422-id"},
        )

    assert resp_404.status_code == 404
    assert resp_404.headers[REQUEST_ID_HEADER] == "err-404-id"
    assert resp_422.status_code == 422
    assert resp_422.headers[REQUEST_ID_HEADER] == "err-422-id"

    http_logs = [r for r in capture.records() if r.get("event") == "http_request"]
    assert [(log["status_code"], log["request_id"], log["level"]) for log in http_logs] == [
        (404, "err-404-id", "WARNING"),
        (422, "err-422-id", "WARNING"),
    ]


@pytest.mark.asyncio
async def test_unhandled_500_response_includes_matching_request_id() -> None:
    test_app = create_app()

    @test_app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("boom failure")

    transport = ASGITransport(app=test_app)
    with _JsonLogCapture() as capture:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/_test/boom", headers={REQUEST_ID_HEADER: "err-500-id"})

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "err-500-id"

    records = capture.records()
    exc_logs = [r for r in records if r.get("event") == "unhandled_exception"]
    http_logs = [r for r in records if r.get("event") == "http_request"]
    assert len(exc_logs) == 1
    assert exc_logs[0]["request_id"] == "err-500-id"
    assert exc_logs[0]["level"] == "ERROR"
    assert len(http_logs) == 1
    assert http_logs[0]["request_id"] == "err-500-id"
    assert http_logs[0]["status_code"] == 500
    assert http_logs[0]["level"] == "ERROR"


# ---------------------------------------------------------------------------
# Domain events & 409 conflict WARNING logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lesson_lifecycle_and_conflict_domain_logs(
    lesson_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_maker = lesson_db_context
    refs = await _seed_lesson_refs(session_maker)

    with _JsonLogCapture() as capture:
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
            headers={REQUEST_ID_HEADER: "req-create-1"},
        )
        assert create_res.status_code == 201
        lesson_id = create_res.json()["id"]

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
            headers={REQUEST_ID_HEADER: "req-conflict-1"},
        )
        assert conflict_res.status_code == 409
        assert conflict_res.headers[REQUEST_ID_HEADER] == "req-conflict-1"

        update_res = await client.put(
            f"/api/v1/lessons/{lesson_id}",
            json={"time_slot_id": refs["slot2_id"]},
            headers={REQUEST_ID_HEADER: "req-update-1"},
        )
        assert update_res.status_code == 200

        delete_res = await client.delete(
            f"/api/v1/lessons/{lesson_id}",
            headers={REQUEST_ID_HEADER: "req-delete-1"},
        )
        assert delete_res.status_code == 204

    records = capture.records()
    created_logs = [r for r in records if r.get("event") == "lesson_created"]
    conflict_logs = [r for r in records if r.get("event") == "lesson_conflict"]
    updated_logs = [r for r in records if r.get("event") == "lesson_updated"]
    deleted_logs = [r for r in records if r.get("event") == "lesson_deleted"]

    assert len(created_logs) == 1
    assert created_logs[0]["request_id"] == "req-create-1"
    assert created_logs[0]["level"] == "INFO"
    assert created_logs[0]["lesson_id"] == lesson_id

    assert len(conflict_logs) == 1
    assert conflict_logs[0]["request_id"] == "req-conflict-1"
    assert conflict_logs[0]["level"] == "WARNING"
    assert conflict_logs[0]["conflict_types"] == [
        "CAPACITY_EXCEEDED",
        "GROUP_BUSY",
        "TEACHER_BUSY",
    ]
    assert conflict_logs[0]["conflict_count"] == 3

    assert len(updated_logs) == 1
    assert updated_logs[0]["request_id"] == "req-update-1"
    assert updated_logs[0]["lesson_id"] == lesson_id
    assert updated_logs[0]["updated_fields"] == ["time_slot_id"]

    assert len(deleted_logs) == 1
    assert deleted_logs[0]["request_id"] == "req-delete-1"
    assert deleted_logs[0]["lesson_id"] == lesson_id


# ---------------------------------------------------------------------------
# Security: auth passwords, tokens, and sessions must never appear in logs
# ---------------------------------------------------------------------------


@pytest.mark.auth_integration
@pytest.mark.asyncio
async def test_auth_flow_never_logs_passwords_tokens_or_sessions(
    lesson_db_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_maker = lesson_db_context
    secret_password = "UltraSecretPassword!987"
    async with session_maker() as session:
        session.add(
            User(
                username="log-admin",
                password_hash=hash_password(secret_password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )
        await session.commit()

    with _JsonLogCapture() as capture:
        unauth_res = await client.get(
            "/api/v1/auth/me",
            headers={REQUEST_ID_HEADER: "auth-unauth-1"},
        )
        assert unauth_res.status_code == 401
        assert unauth_res.headers[REQUEST_ID_HEADER] == "auth-unauth-1"

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"username": "log-admin", "password": secret_password},
            headers={REQUEST_ID_HEADER: "auth-login-1"},
        )
        assert login_res.status_code == 200
        access_token = login_res.json()["access_token"]

        me_res = await client.get(
            "/api/v1/auth/me",
            headers={
                REQUEST_ID_HEADER: "auth-me-1",
                "Authorization": f"Bearer {access_token}",
                "Cookie": "session_id=cookie-secret-xyz",
            },
        )
        assert me_res.status_code == 200

        logout_res = await client.post(
            "/api/v1/auth/logout",
            headers={
                REQUEST_ID_HEADER: "auth-logout-1",
                "Authorization": f"Bearer {access_token}",
            },
        )
        assert logout_res.status_code == 204

    raw_logs = capture.raw
    assert secret_password not in raw_logs
    assert access_token not in raw_logs
    assert "cookie-secret-xyz" not in raw_logs

    http_ids = [r["request_id"] for r in capture.records() if r.get("event") == "http_request"]
    assert http_ids == ["auth-unauth-1", "auth-login-1", "auth-me-1", "auth-logout-1"]


# ---------------------------------------------------------------------------
# Concurrency: contextvars isolation across interleaved parallel requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_requests_isolate_request_id_context() -> None:
    isolated_app = FastAPI()
    isolated_app.add_middleware(RequestContextMiddleware)
    route_logger = logging.getLogger("schedule_service.concurrent_test")

    @isolated_app.get("/work/{worker_id}")
    async def work(worker_id: int) -> dict[str, Any]:
        before_id = get_request_id()
        route_logger.info("before-sleep", extra={"event": "work_before", "worker_id": worker_id})
        await asyncio.sleep(0.02 if worker_id % 2 == 0 else 0.005)
        after_id = get_request_id()
        route_logger.info("after-sleep", extra={"event": "work_after", "worker_id": worker_id})
        return {"worker_id": worker_id, "before_id": before_id, "after_id": after_id}

    transport = ASGITransport(app=isolated_app)
    with _JsonLogCapture("schedule_service") as capture:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                *[
                    client.get(
                        f"/work/{idx}",
                        headers={REQUEST_ID_HEADER: f"parallel-req-{idx}"},
                    )
                    for idx in range(12)
                ]
            )

    for idx, response in enumerate(responses):
        expected_id = f"parallel-req-{idx}"
        assert response.status_code == 200
        assert response.headers[REQUEST_ID_HEADER] == expected_id
        payload = response.json()
        assert payload["before_id"] == expected_id
        assert payload["after_id"] == expected_id

    records = capture.records()
    for event_name in ("work_before", "work_after"):
        event_logs = [r for r in records if r.get("event") == event_name]
        assert len(event_logs) == 12
        for log in event_logs:
            assert log["request_id"] == f"parallel-req-{log['worker_id']}"

    assert get_request_id() is None
