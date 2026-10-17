"""API tests for academic subjects endpoints (/api/v1/subjects)."""

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
from schedule_service.models.subject import Subject

SAMPLE_SUBJECT_DATA = {
    "name": "Математический анализ",
    "code": "MATH-101",
    "description": "Дифференциальное и интегральное исчисление",
}


@pytest_asyncio.fixture
async def client_with_db() -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired to a fresh in-memory SQLite database."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[Subject.__table__],  # type: ignore[list-item]
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
async def test_list_subjects_empty(client_with_db: AsyncClient) -> None:
    """GET /api/v1/subjects returns an empty list initially."""
    response = await client_with_db.get("/api/v1/subjects/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_subject_success(client_with_db: AsyncClient) -> None:
    """POST /api/v1/subjects creates a new subject and returns 201 Created."""
    response = await client_with_db.post("/api/v1/subjects/", json=SAMPLE_SUBJECT_DATA)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Математический анализ"
    assert data["code"] == "MATH-101"
    assert data["description"] == "Дифференциальное и интегральное исчисление"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_subject_duplicate_conflict(client_with_db: AsyncClient) -> None:
    """POST /api/v1/subjects returns 409 Conflict on duplicate name or code."""
    res1 = await client_with_db.post("/api/v1/subjects/", json=SAMPLE_SUBJECT_DATA)
    assert res1.status_code == 201

    # Duplicate name
    res_dup_name = await client_with_db.post(
        "/api/v1/subjects/",
        json={**SAMPLE_SUBJECT_DATA, "code": "MATH-102"},
    )
    assert res_dup_name.status_code == 409
    assert "already exists" in res_dup_name.json()["detail"]

    # Duplicate code
    res_dup_code = await client_with_db.post(
        "/api/v1/subjects/",
        json={**SAMPLE_SUBJECT_DATA, "name": "Линейная алгебра"},
    )
    assert res_dup_code.status_code == 409
    assert "already exists" in res_dup_code.json()["detail"]


@pytest.mark.asyncio
async def test_create_subject_validation_error(client_with_db: AsyncClient) -> None:
    """POST /api/v1/subjects returns 422 on blank name."""
    response = await client_with_db.post("/api/v1/subjects/", json={"name": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_subject_by_id_success_and_not_found(
    client_with_db: AsyncClient,
) -> None:
    """GET /api/v1/subjects/{id} returns 200 OK or 404 Not Found."""
    created = (await client_with_db.post("/api/v1/subjects/", json=SAMPLE_SUBJECT_DATA)).json()
    subject_id = created["id"]

    res_ok = await client_with_db.get(f"/api/v1/subjects/{subject_id}")
    assert res_ok.status_code == 200
    assert res_ok.json()["name"] == "Математический анализ"

    res_404 = await client_with_db.get("/api/v1/subjects/9999")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_list_subjects_search_and_filtering(
    client_with_db: AsyncClient,
) -> None:
    """GET /api/v1/subjects supports search by name/code, name filter, and exact code filter."""
    subjects = [
        {"name": "Математический анализ", "code": "MATH-101", "description": ""},
        {"name": "Алгоритмы и структуры данных", "code": "CS-201", "description": ""},
        {"name": "Дискретная математика", "code": "MATH-102", "description": ""},
    ]
    for s in subjects:
        res = await client_with_db.post("/api/v1/subjects/", json=s)
        assert res.status_code == 201

    # Search by name substring
    res_search = await client_with_db.get("/api/v1/subjects/?search=математ")
    assert res_search.status_code == 200
    assert len(res_search.json()) == 2

    # Filter by name parameter
    res_name = await client_with_db.get("/api/v1/subjects/?name=Алгоритмы")
    assert res_name.status_code == 200
    assert len(res_name.json()) == 1
    assert res_name.json()[0]["code"] == "CS-201"

    # Filter by exact code
    res_code = await client_with_db.get("/api/v1/subjects/?code=MATH-102")
    assert res_code.status_code == 200
    assert len(res_code.json()) == 1
    assert res_code.json()[0]["name"] == "Дискретная математика"


@pytest.mark.asyncio
async def test_update_subject_success_and_conflicts(
    client_with_db: AsyncClient,
) -> None:
    """PUT /api/v1/subjects/{id} updates fields and handles 404/409 errors."""
    s1 = (await client_with_db.post("/api/v1/subjects/", json=SAMPLE_SUBJECT_DATA)).json()
    s2 = (
        await client_with_db.post(
            "/api/v1/subjects/",
            json={"name": "Общая физика", "code": "PHYS-101"},
        )
    ).json()

    # Valid update
    res_upd = await client_with_db.put(
        f"/api/v1/subjects/{s1['id']}",
        json={"name": "Матанализ I", "description": "Обновленное описание"},
    )
    assert res_upd.status_code == 200
    assert res_upd.json()["name"] == "Матанализ I"
    assert res_upd.json()["description"] == "Обновленное описание"

    # Conflict on name
    res_conflict_name = await client_with_db.put(
        f"/api/v1/subjects/{s2['id']}",
        json={"name": "Матанализ I"},
    )
    assert res_conflict_name.status_code == 409

    # Conflict on code
    res_conflict_code = await client_with_db.put(
        f"/api/v1/subjects/{s2['id']}",
        json={"code": "MATH-101"},
    )
    assert res_conflict_code.status_code == 409

    # Not found
    res_404 = await client_with_db.put(
        "/api/v1/subjects/9999",
        json={"name": "Неизвестный предмет"},
    )
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_delete_subject_success_and_not_found(
    client_with_db: AsyncClient,
) -> None:
    """DELETE /api/v1/subjects/{id} deletes subject (204) and returns 404 on repeat."""
    created = (await client_with_db.post("/api/v1/subjects/", json=SAMPLE_SUBJECT_DATA)).json()
    subject_id = created["id"]

    del_res = await client_with_db.delete(f"/api/v1/subjects/{subject_id}")
    assert del_res.status_code == 204

    del_again = await client_with_db.delete(f"/api/v1/subjects/{subject_id}")
    assert del_again.status_code == 404
