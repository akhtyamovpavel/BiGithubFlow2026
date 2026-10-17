"""API tests for time slots endpoints (/api/v1/time-slots)."""

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
from schedule_service.models.time_slot import TimeSlot

SAMPLE_SLOT_DATA = {
    "slot_number": 1,
    "start_time": "09:00:00",
    "end_time": "10:25:00",
    "day_of_week": 1,
}


@pytest_asyncio.fixture
async def client_with_db() -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired to a fresh in-memory SQLite database."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[TimeSlot.__table__],  # type: ignore[list-item]
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


@pytest.mark.asyncio
async def test_list_time_slots_empty(client_with_db: AsyncClient) -> None:
    """GET /api/v1/time-slots returns an empty list initially."""
    response = await client_with_db.get("/api/v1/time-slots/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_time_slot_success(client_with_db: AsyncClient) -> None:
    """POST /api/v1/time-slots creates a new time slot and returns 201 Created."""
    response = await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["slot_number"] == 1
    assert data["start_time"] == "09:00:00"
    assert data["end_time"] == "10:25:00"
    assert data["day_of_week"] == 1


@pytest.mark.asyncio
async def test_create_time_slot_duplicate_conflict(client_with_db: AsyncClient) -> None:
    """POST /api/v1/time-slots returns 409 Conflict on duplicate (day_of_week, slot_number)."""
    res1 = await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)
    assert res1.status_code == 201

    res2 = await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_create_time_slot_validation_error(client_with_db: AsyncClient) -> None:
    """POST /api/v1/time-slots returns 422 when end_time <= start_time or invalid day."""
    invalid_slot = {
        "slot_number": 1,
        "start_time": "10:30:00",
        "end_time": "09:00:00",
        "day_of_week": 1,
    }
    response = await client_with_db.post("/api/v1/time-slots/", json=invalid_slot)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_time_slot_by_id_success_and_not_found(
    client_with_db: AsyncClient,
) -> None:
    """GET /api/v1/time-slots/{id} returns 200 OK or 404 Not Found."""
    created = (await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)).json()
    slot_id = created["id"]

    res_ok = await client_with_db.get(f"/api/v1/time-slots/{slot_id}")
    assert res_ok.status_code == 200
    assert res_ok.json()["slot_number"] == 1

    res_404 = await client_with_db.get("/api/v1/time-slots/9999")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_list_time_slots_filtering(client_with_db: AsyncClient) -> None:
    """GET /api/v1/time-slots supports filtering by day_of_week and slot_number."""
    slots = [
        {
            "slot_number": 1,
            "start_time": "09:00:00",
            "end_time": "10:25:00",
            "day_of_week": 1,
        },
        {
            "slot_number": 2,
            "start_time": "10:45:00",
            "end_time": "12:10:00",
            "day_of_week": 1,
        },
        {
            "slot_number": 1,
            "start_time": "09:00:00",
            "end_time": "10:25:00",
            "day_of_week": 2,
        },
    ]
    for s in slots:
        res = await client_with_db.post("/api/v1/time-slots/", json=s)
        assert res.status_code == 201

    res_day = await client_with_db.get("/api/v1/time-slots/?day_of_week=1")
    assert res_day.status_code == 200
    assert len(res_day.json()) == 2

    res_num = await client_with_db.get("/api/v1/time-slots/?slot_number=1")
    assert res_num.status_code == 200
    assert len(res_num.json()) == 2


@pytest.mark.asyncio
async def test_update_time_slot_success_and_errors(
    client_with_db: AsyncClient,
) -> None:
    """PUT /api/v1/time-slots/{id} updates fields and validates time ordering and conflicts."""
    s1 = (await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)).json()
    s2 = (
        await client_with_db.post(
            "/api/v1/time-slots/",
            json={
                "slot_number": 2,
                "start_time": "10:45:00",
                "end_time": "12:10:00",
                "day_of_week": 1,
            },
        )
    ).json()

    # Valid update
    res_upd = await client_with_db.put(
        f"/api/v1/time-slots/{s1['id']}",
        json={"end_time": "10:30:00"},
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["end_time"] == "10:30:00"

    # Partial update making end_time <= existing start_time
    res_invalid_time = await client_with_db.put(
        f"/api/v1/time-slots/{s1['id']}",
        json={"end_time": "08:30:00"},
    )
    assert res_invalid_time.status_code == 422

    # Conflict on (day_of_week, slot_number)
    res_conflict = await client_with_db.put(
        f"/api/v1/time-slots/{s2['id']}",
        json={"slot_number": 1},
    )
    assert res_conflict.status_code == 409

    # 404 Not Found
    res_404 = await client_with_db.put(
        "/api/v1/time-slots/9999",
        json={"slot_number": 3},
    )
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_delete_time_slot_success_and_not_found(
    client_with_db: AsyncClient,
) -> None:
    """DELETE /api/v1/time-slots/{id} deletes slot (204) and returns 404 on repeat."""
    created = (await client_with_db.post("/api/v1/time-slots/", json=SAMPLE_SLOT_DATA)).json()
    slot_id = created["id"]

    del_res = await client_with_db.delete(f"/api/v1/time-slots/{slot_id}")
    assert del_res.status_code == 204

    del_again = await client_with_db.delete(f"/api/v1/time-slots/{slot_id}")
    assert del_again.status_code == 404
