"""API tests for classrooms endpoints (/api/v1/classrooms)."""

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

SAMPLE_CLASSROOM_DATA = {
    "building": "Главный корпус",
    "room_number": "115",
    "capacity": 60,
    "has_projector": True,
    "has_computers": False,
    "is_active": True,
}


@pytest_asyncio.fixture
async def client_with_db() -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired to a fresh in-memory SQLite database."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[Classroom.__table__],  # type: ignore[list-item]
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
async def test_list_classrooms_empty(client_with_db: AsyncClient) -> None:
    """GET /api/v1/classrooms returns an empty list initially."""
    response = await client_with_db.get("/api/v1/classrooms/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_classroom_success(client_with_db: AsyncClient) -> None:
    """POST /api/v1/classrooms creates a new classroom and returns 201 Created."""
    response = await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["building"] == "Главный корпус"
    assert data["room_number"] == "115"
    assert data["capacity"] == 60
    assert data["has_projector"] is True
    assert data["has_computers"] is False
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_classroom_duplicate_conflict(client_with_db: AsyncClient) -> None:
    """POST /api/v1/classrooms returns 409 Conflict on duplicate (building, room_number)."""
    res1 = await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)
    assert res1.status_code == 201

    res2 = await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_create_classroom_validation_error(client_with_db: AsyncClient) -> None:
    """POST /api/v1/classrooms returns 422 on invalid payload."""
    invalid_data = {
        "building": "   ",
        "room_number": "115",
        "capacity": 0,
    }
    response = await client_with_db.post("/api/v1/classrooms/", json=invalid_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_classroom_by_id_success(client_with_db: AsyncClient) -> None:
    """GET /api/v1/classrooms/{id} returns 200 OK with classroom data."""
    created = (await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)).json()
    classroom_id = created["id"]

    response = await client_with_db.get(f"/api/v1/classrooms/{classroom_id}")
    assert response.status_code == 200
    assert response.json()["id"] == classroom_id
    assert response.json()["room_number"] == "115"


@pytest.mark.asyncio
async def test_get_classroom_by_id_not_found(client_with_db: AsyncClient) -> None:
    """GET /api/v1/classrooms/{id} returns 404 Not Found for nonexistent ID."""
    response = await client_with_db.get("/api/v1/classrooms/9999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_classrooms_filtering_and_pagination(
    client_with_db: AsyncClient,
) -> None:
    """GET /api/v1/classrooms supports capacity, equipment, building, and status filters."""
    classrooms = [
        {
            "building": "ГК",
            "room_number": "115",
            "capacity": 120,
            "has_projector": True,
            "has_computers": False,
            "is_active": True,
        },
        {
            "building": "УЛК",
            "room_number": "412",
            "capacity": 30,
            "has_projector": True,
            "has_computers": True,
            "is_active": True,
        },
        {
            "building": "ГК",
            "room_number": "202",
            "capacity": 55,
            "has_projector": False,
            "has_computers": False,
            "is_active": False,
        },
    ]
    for item in classrooms:
        res = await client_with_db.post("/api/v1/classrooms/", json=item)
        assert res.status_code == 201

    # Filter by min_capacity=50 & has_projector=true
    res_cap_proj = await client_with_db.get(
        "/api/v1/classrooms/?min_capacity=50&has_projector=true"
    )
    assert res_cap_proj.status_code == 200
    data_cap_proj = res_cap_proj.json()
    assert len(data_cap_proj) == 1
    assert data_cap_proj[0]["room_number"] == "115"

    # Filter by has_computers=true
    res_comp = await client_with_db.get("/api/v1/classrooms/?has_computers=true")
    assert res_comp.status_code == 200
    assert len(res_comp.json()) == 1
    assert res_comp.json()[0]["room_number"] == "412"

    # Filter by building
    res_bldg = await client_with_db.get("/api/v1/classrooms/?building=ГК")
    assert res_bldg.status_code == 200
    assert len(res_bldg.json()) == 2

    # Filter by is_active
    res_inactive = await client_with_db.get("/api/v1/classrooms/?is_active=false")
    assert res_inactive.status_code == 200
    assert len(res_inactive.json()) == 1
    assert res_inactive.json()[0]["room_number"] == "202"

    # Pagination
    res_page = await client_with_db.get("/api/v1/classrooms/?skip=1&limit=1")
    assert res_page.status_code == 200
    assert len(res_page.json()) == 1
    assert res_page.json()[0]["room_number"] == "412"


@pytest.mark.asyncio
async def test_update_classroom_success(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/classrooms/{id} updates fields and returns 200 OK."""
    created = (await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)).json()
    classroom_id = created["id"]

    update_payload = {
        "room_number": "116",
        "capacity": 80,
        "has_computers": True,
    }
    response = await client_with_db.put(f"/api/v1/classrooms/{classroom_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["room_number"] == "116"
    assert data["capacity"] == 80
    assert data["has_computers"] is True
    assert data["building"] == "Главный корпус"


@pytest.mark.asyncio
async def test_update_classroom_not_found(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/classrooms/{id} returns 404 Not Found for nonexistent ID."""
    response = await client_with_db.put("/api/v1/classrooms/9999", json={"capacity": 40})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_classroom_duplicate_conflict(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/classrooms/{id} returns 409 Conflict on duplicate room in building."""
    await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)
    second = (
        await client_with_db.post(
            "/api/v1/classrooms/",
            json={**SAMPLE_CLASSROOM_DATA, "room_number": "116"},
        )
    ).json()

    response = await client_with_db.put(
        f"/api/v1/classrooms/{second['id']}",
        json={"room_number": "115"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_classroom_success_and_not_found(
    client_with_db: AsyncClient,
) -> None:
    """DELETE /api/v1/classrooms/{id} deletes record (204) and returns 404 on repeat."""
    created = (await client_with_db.post("/api/v1/classrooms/", json=SAMPLE_CLASSROOM_DATA)).json()
    classroom_id = created["id"]

    del_res = await client_with_db.delete(f"/api/v1/classrooms/{classroom_id}")
    assert del_res.status_code == 204

    get_res = await client_with_db.get(f"/api/v1/classrooms/{classroom_id}")
    assert get_res.status_code == 404

    del_again = await client_with_db.delete(f"/api/v1/classrooms/{classroom_id}")
    assert del_again.status_code == 404
