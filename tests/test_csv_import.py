"""API, idempotency, RBAC, and migration tests for CSV schedule import (Issue #57)."""

import csv
import datetime as dt
import io
import os
import sqlite3
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schedule_service.core.auth import hash_password
from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
    get_async_session,
)
from schedule_service.main import app
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.import_batch import ScheduleImportBatch
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.models.lesson_exception import LessonException
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.models.user import LoginSession, User, UserRole
from schedule_service.services.csv_import_service import (
    CSV_IMPORT_COLUMNS,
    CSV_IMPORT_MAX_BYTES,
    CSV_IMPORT_MAX_ROWS,
)

HEADER_LINE = ",".join(CSV_IMPORT_COLUMNS)


def _csv_bytes(*rows: str) -> bytes:
    return ("\n".join([HEADER_LINE, *rows]) + "\n").encode("utf-8")


@pytest_asyncio.fixture
async def import_ctx() -> (
    AsyncGenerator[
        tuple[AsyncClient, async_sessionmaker[AsyncSession]],
        None,
    ]
):
    """Provide AsyncClient and sessionmaker wired to an in-memory SQLite DB."""
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
                    ScheduleImportBatch.__table__,  # type: ignore[list-item]
                ],
            )
        )

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_maker
    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


async def _seed_refs(session_maker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with session_maker() as session:
        g1 = Group(name="Б05-401", faculty="ФПМИ", course_number=1, student_count=28)
        g2 = Group(name="Б05-402", faculty="ФПМИ", course_number=1, student_count=25)
        t1 = Teacher(
            full_name="Иванов И.И.", email="ivanov@mipt.ru", department="ВМ", position="Профессор"
        )
        t2 = Teacher(
            full_name="Петров П.П.", email="petrov@mipt.ru", department="АиСД", position="Доцент"
        )
        s1 = Subject(name="Математический анализ", code="MATH-101")
        s2 = Subject(name="Алгоритмы", code="CS-101")
        c_big = Classroom(building="ГК", room_number="115", capacity=100)
        c_small = Classroom(building="УЛК", room_number="201", capacity=15)
        ts_mon_1 = TimeSlot(
            slot_number=1, start_time=dt.time(9, 0), end_time=dt.time(10, 25), day_of_week=1
        )
        ts_mon_2 = TimeSlot(
            slot_number=2, start_time=dt.time(10, 45), end_time=dt.time(12, 10), day_of_week=1
        )
        session.add_all([g1, g2, t1, t2, s1, s2, c_big, c_small, ts_mon_1, ts_mon_2])
        await session.commit()
        return {
            "g1_id": g1.id,
            "g2_id": g2.id,
            "t1_id": t1.id,
            "t2_id": t2.id,
            "s1_id": s1.id,
            "s2_id": s2.id,
            "c_big_id": c_big.id,
            "c_small_id": c_small.id,
            "ts_mon_1_id": ts_mon_1.id,
            "ts_mon_2_id": ts_mon_2.id,
        }


async def _lesson_count(session_maker: async_sessionmaker[AsyncSession]) -> int:
    async with session_maker() as session:
        return len((await session.execute(select(Lesson.id))).scalars().all())


@pytest.mark.asyncio
async def test_download_csv_template(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """GET /api/v1/schedule/import/template returns UTF-8 CSV with expected columns."""
    client, _ = import_ctx
    res = await client.get("/api/v1/schedule/import/template")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert 'filename="schedule_import_template.csv"' in res.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(res.text)))
    assert tuple(rows[0]) == CSV_IMPORT_COLUMNS
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_valid_csv_preview_and_atomic_commit(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Valid CSV previews cleanly and confirm inserts expected lessons atomically."""
    client, session_maker = import_ctx
    await _seed_refs(session_maker)

    payload = _csv_bytes(
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,",
        "Б05-402,petrov@mipt.ru,CS-101,ГК,115,1,2,SEMINAR,ODD_WEEK,2026-10-19",
    )
    prev = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("schedule.csv", payload, "text/csv")},
    )
    assert prev.status_code == 200
    data = prev.json()
    assert data["status"] == "preview"
    assert data["can_commit"] is True
    assert data["total_rows"] == 2
    assert data["valid_rows"] == 2
    assert data["error_rows"] == 0
    assert await _lesson_count(session_maker) == 0

    conf = await client.post(f"/api/v1/schedule/import/{data['batch_id']}/confirm")
    assert conf.status_code == 200
    committed = conf.json()
    assert committed["status"] == "committed"
    assert committed["created_count"] == 2
    assert len(committed["created_lesson_ids"]) == 2
    assert await _lesson_count(session_maker) == 2


@pytest.mark.asyncio
async def test_errors_unknown_refs_dates_capacity_do_not_mutate_db(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Unknown refs, bad dates, weekday mismatch, and capacity errors block commit atomically."""
    client, session_maker = import_ctx
    await _seed_refs(session_maker)

    payload = _csv_bytes(
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,",  # row 2: valid
        "NO-GRP,no@mipt.ru,NO-SUBJ,ГК,999,1,6,LECTURE,ALWAYS,",  # row 3: unknown refs
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,2,LECTURE,ALWAYS,2026-02-30",  # row 4: bad date
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,2,LECTURE,ALWAYS,2026-10-20",  # row 5: Tue!=Mon
        "Б05-401,petrov@mipt.ru,CS-101,УЛК,201,1,2,LAB,ALWAYS,",  # row 6: capacity 15 < 28
    )
    prev = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("broken.csv", payload, "text/csv")},
    )
    assert prev.status_code == 200
    data = prev.json()
    assert data["can_commit"] is False
    assert data["valid_rows"] == 1
    assert data["error_rows"] == 4

    err_triples = {(e["row"], e["field"], e["code"]) for e in data["errors"]}
    assert (3, "group_name", "UNKNOWN_GROUP") in err_triples
    assert (3, "teacher_email", "UNKNOWN_TEACHER") in err_triples
    assert (3, "subject_code", "UNKNOWN_SUBJECT") in err_triples
    assert (3, "classroom_room", "UNKNOWN_CLASSROOM") in err_triples
    assert (3, "slot_number", "UNKNOWN_TIME_SLOT") in err_triples
    assert (4, "specific_date", "INVALID_DATE") in err_triples
    assert (5, "specific_date", "DATE_WEEKDAY_MISMATCH") in err_triples
    assert (6, "classroom_room", "CAPACITY_EXCEEDED") in err_triples

    # Confirming an invalid batch must return 409 and insert ZERO lessons (even row 2)
    conf = await client.post(f"/api/v1/schedule/import/{data['batch_id']}/confirm")
    assert conf.status_code == 409
    assert await _lesson_count(session_maker) == 0


@pytest.mark.asyncio
async def test_size_row_and_header_limits(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Enforce 1 MiB byte size limit (413), 500-row limit (422), and required headers (422)."""
    client, _ = import_ctx

    oversized = b"a" * (CSV_IMPORT_MAX_BYTES + 10)
    res_big = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("huge.csv", oversized, "text/csv")},
    )
    assert res_big.status_code == 413

    many_rows = _csv_bytes(
        *(
            "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,"
            for _ in range(CSV_IMPORT_MAX_ROWS + 1)
        )
    )
    res_rows = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("many.csv", many_rows, "text/csv")},
    )
    assert res_rows.status_code == 422

    bad_header = b"wrong_col,other_col\n1,2\n"
    res_hdr = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("bad.csv", bad_header, "text/csv")},
    )
    assert res_hdr.status_code == 422


@pytest.mark.asyncio
async def test_intra_file_conflicts_and_db_change_after_preview(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Detect intra-file collisions AND re-check DB collisions added after preview."""
    client, session_maker = import_ctx
    refs = await _seed_refs(session_maker)

    # 1. Intra-file collision: row 2 and row 3 use same classroom/teacher/slot
    intra_csv = _csv_bytes(
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,",
        "Б05-402,ivanov@mipt.ru,CS-101,ГК,115,1,1,SEMINAR,ODD_WEEK,",
    )
    res_intra = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("intra.csv", intra_csv, "text/csv")},
    )
    assert res_intra.status_code == 200
    intra_codes = {(e["row"], e["code"]) for e in res_intra.json()["errors"]}
    assert (3, "FILE_TEACHER_CONFLICT") in intra_codes
    assert (3, "FILE_CLASSROOM_CONFLICT") in intra_codes

    # 2. Clean preview, then DB changes before confirm -> confirm rejects atomically (0 inserted)
    clean_csv = _csv_bytes(
        "Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,",
        "Б05-402,petrov@mipt.ru,CS-101,ГК,115,1,2,SEMINAR,ALWAYS,",
    )
    prev = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("clean.csv", clean_csv, "text/csv")},
    )
    assert prev.status_code == 200
    batch_id = prev.json()["batch_id"]
    assert prev.json()["can_commit"] is True

    # Mutate DB after preview: occupy slot 2 with teacher petrov + room ГК 115
    async with session_maker() as session:
        session.add(
            Lesson(
                subject_id=refs["s2_id"],
                teacher_id=refs["t2_id"],
                group_id=refs["g2_id"],
                classroom_id=refs["c_big_id"],
                time_slot_id=refs["ts_mon_2_id"],
                lesson_type=LessonType.LAB,
                parity=WeekParity.ALWAYS,
            )
        )
        await session.commit()

    conf = await client.post(f"/api/v1/schedule/import/{batch_id}/confirm")
    assert conf.status_code == 409
    conf_data = conf.json()
    assert conf_data["can_commit"] is False
    codes = {e["code"] for e in conf_data["errors"]}
    assert {"TEACHER_BUSY", "CLASSROOM_BUSY", "GROUP_BUSY"} <= codes
    # Only the 1 pre-existing lesson exists; row 2 from the batch was NOT committed
    assert await _lesson_count(session_maker) == 1


@pytest.mark.asyncio
async def test_idempotency_and_connection_loss_recovery(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Repeated upload, repeated confirm, and GET status prevent duplicates safely."""
    client, session_maker = import_ctx
    await _seed_refs(session_maker)

    payload = _csv_bytes("Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,")
    headers = {"Idempotency-Key": "import-req-123"}

    p1 = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("ok.csv", payload, "text/csv")},
        headers=headers,
    )
    p2 = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("ok.csv", payload, "text/csv")},
        headers=headers,
    )
    assert p1.status_code == 200 and p2.status_code == 200
    assert p1.json()["batch_id"] == p2.json()["batch_id"]

    # Same Idempotency-Key with different payload -> 409
    other = _csv_bytes("Б05-402,petrov@mipt.ru,CS-101,ГК,115,1,2,SEMINAR,ALWAYS,")
    p_conflict = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("other.csv", other, "text/csv")},
        headers=headers,
    )
    assert p_conflict.status_code == 409

    batch_id = p1.json()["batch_id"]
    c1 = await client.post(f"/api/v1/schedule/import/{batch_id}/confirm")
    assert c1.status_code == 200
    assert c1.json()["already_committed"] is False
    assert c1.json()["created_count"] == 1

    # Simulated retry after connection drop: confirm again + GET status + re-upload same CSV
    c2 = await client.post(f"/api/v1/schedule/import/{batch_id}/confirm")
    assert c2.status_code == 200
    assert c2.json()["already_committed"] is True
    assert c2.json()["created_lesson_ids"] == c1.json()["created_lesson_ids"]

    status_res = await client.get(f"/api/v1/schedule/import/{batch_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "committed"
    assert status_res.json()["created_lesson_ids"] == c1.json()["created_lesson_ids"]

    reupload = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("ok.csv", payload, "text/csv")},
    )
    assert reupload.status_code == 200
    assert reupload.json()["status"] == "committed"
    assert reupload.json()["already_committed"] is True
    assert await _lesson_count(session_maker) == 1


@pytest.mark.auth_integration
@pytest.mark.asyncio
async def test_import_rbac_admin_and_dispatcher_only(
    import_ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """Import endpoints require admin or dispatcher; anonymous gets 401 and reader gets 403."""
    client, session_maker = import_ctx
    await _seed_refs(session_maker)

    async with session_maker() as session:
        session.add_all(
            [
                User(
                    username="admin1",
                    password_hash=hash_password("Secret123!"),
                    role=UserRole.ADMIN.value,
                ),
                User(
                    username="disp1",
                    password_hash=hash_password("Secret123!"),
                    role=UserRole.DISPATCHER.value,
                ),
                User(
                    username="reader1",
                    password_hash=hash_password("Secret123!"),
                    role=UserRole.READER.value,
                ),
            ]
        )
        await session.commit()

    async def login(username: str) -> dict[str, str]:
        res = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": "Secret123!"}
        )
        assert res.status_code == 200
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    payload = _csv_bytes("Б05-401,ivanov@mipt.ru,MATH-101,ГК,115,1,1,LECTURE,ALWAYS,")

    # Anonymous -> 401
    assert (await client.get("/api/v1/schedule/import/template")).status_code == 401
    assert (
        await client.post(
            "/api/v1/schedule/import/preview",
            files={"file": ("s.csv", payload, "text/csv")},
        )
    ).status_code == 401

    # Reader -> 403 on every import endpoint (including GET template and GET status)
    reader_hdr = await login("reader1")
    assert (
        await client.get("/api/v1/schedule/import/template", headers=reader_hdr)
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/schedule/import/preview",
            files={"file": ("s.csv", payload, "text/csv")},
            headers=reader_hdr,
        )
    ).status_code == 403
    assert (
        await client.get("/api/v1/schedule/import/nonexistent", headers=reader_hdr)
    ).status_code == 403
    assert (
        await client.post("/api/v1/schedule/import/nonexistent/confirm", headers=reader_hdr)
    ).status_code == 403

    # Dispatcher -> allowed to download template, preview, and confirm
    disp_hdr = await login("disp1")
    assert (
        await client.get("/api/v1/schedule/import/template", headers=disp_hdr)
    ).status_code == 200
    prev = await client.post(
        "/api/v1/schedule/import/preview",
        files={"file": ("s.csv", payload, "text/csv")},
        headers=disp_hdr,
    )
    assert prev.status_code == 200
    batch_id = prev.json()["batch_id"]
    assert (
        await client.post(f"/api/v1/schedule/import/{batch_id}/confirm", headers=disp_hdr)
    ).status_code == 200

    # Admin -> allowed to inspect committed batch status
    admin_hdr = await login("admin1")
    status_res = await client.get(f"/api/v1/schedule/import/{batch_id}", headers=admin_hdr)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "committed"


def test_alembic_import_batches_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Verify Alembic migration bb23cc45dd67 creates and drops schedule_import_batches cleanly."""
    db_file = tmp_path / "import_mig.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "schedule_import_batches" in tables

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "aa12bb34cc56"],
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(db_file) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "schedule_import_batches" not in tables
