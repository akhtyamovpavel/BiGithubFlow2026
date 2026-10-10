"""API tests for teachers endpoints (/api/v1/teachers)."""

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
from schedule_service.models.teacher import Teacher

SAMPLE_TEACHER_DATA = {
    "full_name": "Иванов Иван Иванович",
    "email": "ivanov@phystech.edu",
    "department": "Кафедра 1С",
    "position": "доцент",
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
                tables=[Teacher.__table__],  # type: ignore[list-item]
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
async def test_list_teachers_empty(client_with_db: AsyncClient) -> None:
    """GET /api/v1/teachers returns an empty list initially."""
    response = await client_with_db.get("/api/v1/teachers/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_teacher_success(client_with_db: AsyncClient) -> None:
    """POST /api/v1/teachers creates a teacher and returns 201 Created."""
    response = await client_with_db.post("/api/v1/teachers/", json=SAMPLE_TEACHER_DATA)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["full_name"] == "Иванов Иван Иванович"
    assert data["email"] == "ivanov@phystech.edu"
    assert data["department"] == "Кафедра 1С"
    assert data["position"] == "доцент"
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_teacher_duplicate_email_conflict(client_with_db: AsyncClient) -> None:
    """POST /api/v1/teachers returns 409 Conflict on duplicate email."""
    res1 = await client_with_db.post("/api/v1/teachers/", json=SAMPLE_TEACHER_DATA)
    assert res1.status_code == 201

    # Same email with different case/spaces
    res2 = await client_with_db.post(
        "/api/v1/teachers/",
        json={**SAMPLE_TEACHER_DATA, "email": " Ivanov@Phystech.EDU "},
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_create_teacher_validation_error(client_with_db: AsyncClient) -> None:
    """POST /api/v1/teachers returns 422 on invalid email format or empty name."""
    invalid_data = {
        "full_name": "",
        "email": "not-an-email",
        "department": "Кафедра 1С",
    }
    response = await client_with_db.post("/api/v1/teachers/", json=invalid_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_teacher_by_id_success(client_with_db: AsyncClient) -> None:
    """GET /api/v1/teachers/{id} returns 200 OK with teacher details."""
    created = (await client_with_db.post("/api/v1/teachers/", json=SAMPLE_TEACHER_DATA)).json()
    teacher_id = created["id"]

    response = await client_with_db.get(f"/api/v1/teachers/{teacher_id}")
    assert response.status_code == 200
    assert response.json()["id"] == teacher_id
    assert response.json()["full_name"] == "Иванов Иван Иванович"


@pytest.mark.asyncio
async def test_get_teacher_by_id_not_found(client_with_db: AsyncClient) -> None:
    """GET /api/v1/teachers/{id} returns 404 for nonexistent teacher ID."""
    response = await client_with_db.get("/api/v1/teachers/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Teacher with id 99999 not found"


@pytest.mark.asyncio
async def test_list_teachers_filtering_and_pagination(client_with_db: AsyncClient) -> None:
    """GET /api/v1/teachers supports filtering by department, is_active, and pagination."""
    teachers = [
        {
            "full_name": "Петров Петр",
            "email": "petrov@mipt.ru",
            "department": "ФПМИ",
            "is_active": True,
        },
        {
            "full_name": "Сидоров Сидор",
            "email": "sidorov@mipt.ru",
            "department": "ФПМИ",
            "is_active": False,
        },
        {
            "full_name": "Кузнецов Кузьма",
            "email": "kuznetsov@mipt.ru",
            "department": "ФРКТ",
            "is_active": True,
        },
    ]
    for t in teachers:
        res = await client_with_db.post("/api/v1/teachers/", json=t)
        assert res.status_code == 201

    # Filter by department
    res = await client_with_db.get("/api/v1/teachers/?department=ФПМИ")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # Filter by is_active
    res = await client_with_db.get("/api/v1/teachers/?is_active=false")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["email"] == "sidorov@mipt.ru"

    # Pagination skip/limit
    res = await client_with_db.get("/api/v1/teachers/?skip=1&limit=1")
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_update_teacher_success(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/teachers/{id} updates teacher details."""
    created = (await client_with_db.post("/api/v1/teachers/", json=SAMPLE_TEACHER_DATA)).json()
    teacher_id = created["id"]

    update_payload = {
        "position": "профессор",
        "department": "Кафедра алгоритмов",
        "is_active": False,
    }
    response = await client_with_db.put(f"/api/v1/teachers/{teacher_id}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["position"] == "профессор"
    assert data["department"] == "Кафедра алгоритмов"
    assert data["is_active"] is False
    assert data["email"] == "ivanov@phystech.edu"


@pytest.mark.asyncio
async def test_update_teacher_not_found(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/teachers/{id} returns 404 for nonexistent teacher."""
    response = await client_with_db.put("/api/v1/teachers/9999", json={"position": "доцент"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_teacher_email_conflict(client_with_db: AsyncClient) -> None:
    """PUT /api/v1/teachers/{id} returns 409 Conflict if email is taken."""
    await client_with_db.post(
        "/api/v1/teachers/",
        json={**SAMPLE_TEACHER_DATA, "email": "t1@mipt.ru"},
    )
    t2 = (
        await client_with_db.post(
            "/api/v1/teachers/",
            json={**SAMPLE_TEACHER_DATA, "email": "t2@mipt.ru"},
        )
    ).json()

    response = await client_with_db.put(
        f"/api/v1/teachers/{t2['id']}", json={"email": "t1@mipt.ru"}
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_teacher_success(client_with_db: AsyncClient) -> None:
    """DELETE /api/v1/teachers/{id} removes the teacher and returns 204 No Content."""
    created = (await client_with_db.post("/api/v1/teachers/", json=SAMPLE_TEACHER_DATA)).json()
    teacher_id = created["id"]

    del_res = await client_with_db.delete(f"/api/v1/teachers/{teacher_id}")
    assert del_res.status_code == 204

    get_res = await client_with_db.get(f"/api/v1/teachers/{teacher_id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_teacher_not_found(client_with_db: AsyncClient) -> None:
    """DELETE /api/v1/teachers/{id} returns 404 for nonexistent teacher."""
    response = await client_with_db.delete("/api/v1/teachers/9999")
    assert response.status_code == 404
