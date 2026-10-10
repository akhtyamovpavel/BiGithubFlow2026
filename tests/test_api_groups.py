"""API tests for academic groups endpoints (/api/v1/groups)."""

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
from schedule_service.models.group import Group

SAMPLE_GROUP_DATA = {
    "name": "Б05-201",
    "faculty": "ФПМИ",
    "course_number": 2,
    "student_count": 28,
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
                tables=[Group.__table__],  # type: ignore[list-item]
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
async def test_list_groups_empty(client_with_db: AsyncClient) -> None:
    """GET /api/v1/groups returns an empty list initially."""
    response = await client_with_db.get("/api/v1/groups/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_group_success(client_with_db: AsyncClient) -> None:
    """POST /api/v1/groups creates a new group and returns 201 Created."""
    response = await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Б05-201"
    assert data["faculty"] == "ФПМИ"
    assert data["course_number"] == 2
    assert data["student_count"] == 28
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_group_duplicate_name_conflict(client_with_db: AsyncClient) -> None:
    """POST /api/v1/groups returns 409 Conflict on duplicate group name."""
    res1 = await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)
    assert res1.status_code == 201

    res2 = await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_create_group_validation_error(client_with_db: AsyncClient) -> None:
    """POST /api/v1/groups returns 422 on invalid payload."""
    invalid_data = {
        "name": "",
        "faculty": "ФПМИ",
        "course_number": 10,  # Invalid: > 6
        "student_count": 0,  # Invalid: <= 0
    }
    response = await client_with_db.post("/api/v1/groups/", json=invalid_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_group_by_id_success(client_with_db: AsyncClient) -> None:
    """GET /api/v1/groups/{id} returns 200 OK with group data."""
    created = (await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)).json()
    group_id = created["id"]

    response = await client_with_db.get(f"/api/v1/groups/{group_id}")
    assert response.status_code == 200
    assert response.json()["id"] == group_id
    assert response.json()["name"] == "Б05-201"


@pytest.mark.asyncio
async def test_get_group_by_id_not_found(client_with_db: AsyncClient) -> None:
    """GET /api/v1/groups/{id} returns 404 Not Found for nonexistent ID."""
    response = await client_with_db.get("/api/v1/groups/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Group with id 99999 not found"


@pytest.mark.asyncio
async def test_list_groups_filtering_and_pagination(client_with_db: AsyncClient) -> None:
    """GET /api/v1/groups supports pagination and filtering."""
    groups = [
        {
            "name": "Б01-101",
            "faculty": "ФРКТ",
            "course_number": 1,
            "student_count": 25,
            "is_active": True,
        },
        {
            "name": "Б02-102",
            "faculty": "ФАКТ",
            "course_number": 1,
            "student_count": 30,
            "is_active": True,
        },
        {
            "name": "Б05-201",
            "faculty": "ФПМИ",
            "course_number": 2,
            "student_count": 28,
            "is_active": True,
        },
        {
            "name": "Б05-202",
            "faculty": "ФПМИ",
            "course_number": 2,
            "student_count": 22,
            "is_active": False,
        },
        {
            "name": "М05-501",
            "faculty": "ФПМИ",
            "course_number": 5,
            "student_count": 15,
            "is_active": True,
        },
    ]
    for g in groups:
        res = await client_with_db.post("/api/v1/groups/", json=g)
        assert res.status_code == 201

    # Filter by course_number
    res = await client_with_db.get("/api/v1/groups/?course_number=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert {d["name"] for d in data} == {"Б05-201", "Б05-202"}

    # Filter by faculty
    res = await client_with_db.get("/api/v1/groups/?faculty=ФПМИ")
    assert res.status_code == 200
    assert len(res.json()) == 3

    # Filter by is_active
    res = await client_with_db.get("/api/v1/groups/?is_active=false")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "Б05-202"

    # Pagination skip/limit
    res = await client_with_db.get("/api/v1/groups/?skip=1&limit=2")
    assert res.status_code == 200
    assert len(res.json()) == 2


@pytest.mark.asyncio
async def test_update_group_success(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/groups/{id} updates group details and returns 200 OK."""
    created = (await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)).json()
    group_id = created["id"]

    update_payload = {
        "student_count": 35,
        "faculty": "ФПМИ ПМИ",
        "is_active": False,
    }
    response = await client_with_db.put(f"/api/v1/groups/{group_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["student_count"] == 35
    assert data["faculty"] == "ФПМИ ПМИ"
    assert data["is_active"] is False
    assert data["name"] == "Б05-201"  # Unchanged


@pytest.mark.asyncio
async def test_update_group_not_found(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/groups/{id} returns 404 for nonexistent group."""
    response = await client_with_db.put("/api/v1/groups/9999", json={"student_count": 30})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_group_name_conflict(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/groups/{id} returns 409 Conflict if renaming to an existing name."""
    await client_with_db.post("/api/v1/groups/", json={**SAMPLE_GROUP_DATA, "name": "Б05-101"})
    g2 = (
        await client_with_db.post("/api/v1/groups/", json={**SAMPLE_GROUP_DATA, "name": "Б05-102"})
    ).json()

    response = await client_with_db.put(f"/api/v1/groups/{g2['id']}", json={"name": "Б05-101"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_group_success(client_with_db: AsyncClient) -> None:
    """DELETE /api/v1/groups/{id} removes the group and returns 204 No Content."""
    created = (await client_with_db.post("/api/v1/groups/", json=SAMPLE_GROUP_DATA)).json()
    group_id = created["id"]

    del_res = await client_with_db.delete(f"/api/v1/groups/{group_id}")
    assert del_res.status_code == 204

    # Verify group is gone
    get_res = await client_with_db.get(f"/api/v1/groups/{group_id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_group_not_found(client_with_db: AsyncClient) -> None:
    """DELETE /api/v1/groups/{id} returns 404 for nonexistent group."""
    response = await client_with_db.delete("/api/v1/groups/9999")
    assert response.status_code == 404
