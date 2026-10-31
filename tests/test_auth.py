"""Integration tests for authentication and role enforcement."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schedule_service.core.auth import hash_password
from schedule_service.core.database import Base, create_engine_and_sessionmaker, get_async_session
from schedule_service.main import app
from schedule_service.models.user import LoginSession, User, UserRole

pytestmark = [pytest.mark.asyncio, pytest.mark.auth_integration]


@pytest_asyncio.fixture
async def auth_db() -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker[AsyncSession]], None]:
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory.begin() as session:
        for role in UserRole:
            session.add(
                User(
                    username=role.value,
                    password_hash=hash_password("password123"),
                    role=role.value,
                    is_active=True,
                )
            )

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "password123"}
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_access_matrix(auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, _ = auth_db
    assert (await client.get("/api/v1/groups/")).status_code == 401
    assert (await client.get("/api/v1/users")).status_code == 401
    for role in UserRole:
        headers = authorization(await login(client, role.value))
        assert (await client.get("/api/v1/groups/", headers=headers)).status_code == 200
        data = {"name": role.value, "faculty": "F", "course_number": 1, "student_count": 10}
        response = await client.post("/api/v1/groups/", json=data, headers=headers)
        expected = 403 if role == UserRole.READER else 201
        assert response.status_code == expected
        response = await client.get("/api/v1/users", headers=headers)
        expected = 200 if role == UserRole.ADMIN else 403
        assert response.status_code == expected
    admin_headers = authorization(await login(client, "admin"))
    groups = (await client.get("/api/v1/groups/", headers=admin_headers)).json()
    assert {group["name"] for group in groups} == {"admin", "dispatcher"}


async def test_account_lifecycle(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = auth_db
    headers = authorization(await login(client, "admin"))
    data = {"username": "new", "password": "password123", "role": "reader"}
    response = await client.post("/api/v1/users", headers=headers, json=data)
    assert response.status_code == 201
    user_id = response.json()["id"]
    assert "password" not in response.text
    assert (await client.post("/api/v1/users", headers=headers, json=data)).status_code == 409
    new_headers = authorization(await login(client, "new"))
    assert (
        await client.patch(f"/api/v1/users/{user_id}", headers=new_headers, json={"role": "admin"})
    ).status_code == 403
    response = await client.patch(
        f"/api/v1/users/{user_id}", headers=headers, json={"role": "dispatcher"}
    )
    assert response.json()["role"] == "dispatcher"
    assert (await client.get("/api/v1/auth/me", headers=new_headers)).json()["role"] == "dispatcher"
    await client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"is_active": False})
    assert (await client.get("/api/v1/auth/me", headers=new_headers)).status_code == 401
    await client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"is_active": True})
    assert (await client.get("/api/v1/auth/me", headers=new_headers)).status_code == 401
    async with factory() as session:
        user = await session.get(User, user_id)
        assert user is not None and user.password_hash != "password123"
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_expiry_and_bad_credentials(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = auth_db
    response = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "bad"}
    )
    assert response.status_code == 401
    token = await login(client, "admin")
    async with factory.begin() as session:
        entry = await session.scalar(select(LoginSession))
        assert entry is not None
        assert entry.token_hash != token
        entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.get("/api/v1/auth/me", headers=authorization(token))).status_code == 401


async def test_all_schedule_routes_require_expected_role(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    from fastapi.routing import APIRoute

    client, _ = auth_db
    reader_headers = authorization(await login(client, "reader"))
    dispatcher_headers = authorization(await login(client, "dispatcher"))
    prefixes = (
        "/api/v1/groups",
        "/api/v1/teachers",
        "/api/v1/classrooms",
        "/api/v1/subjects",
        "/api/v1/time-slots",
        "/api/v1/lessons",
        "/api/v1/schedule",
    )
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(prefixes):
            continue
        path = route.path_format
        for parameter in route.param_convertors:
            path = path.replace("{" + parameter + "}", "999")
        for method in route.methods or set():
            anonymous = await client.request(method, path)
            assert anonymous.status_code == 401, (method, path, anonymous.text)
            reader = await client.request(method, path, headers=reader_headers)
            dispatcher = await client.request(method, path, headers=dispatcher_headers)
            if method == "GET":
                assert reader.status_code != 403, (method, path)
            else:
                assert reader.status_code == 403, (method, path)
            assert dispatcher.status_code not in (401, 403), (method, path)


async def test_validation_does_not_return_password(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = auth_db
    headers = authorization(await login(client, "admin"))
    response = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"username": "new", "password": "secret", "role": "reader"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text
