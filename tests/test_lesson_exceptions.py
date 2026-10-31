"""Integration coverage for changes to individual occurrences."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schedule_service.core.auth import hash_password
from schedule_service.core.database import Base, create_engine_and_sessionmaker, get_async_session
from schedule_service.main import app
from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.models.time_slot import TimeSlot
from schedule_service.models.user import User
from tests.test_api_schedule import _seed_schedule_data
from tests.test_auth import auth_db, authorization, login  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.auth_integration]


@pytest_asyncio.fixture
async def concurrent_db(
    tmp_path: Path,
) -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker[AsyncSession]], None]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}"
    engine, factory = create_engine_and_sessionmaker(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory.begin() as session:
        session.add(
            User(
                username="dispatcher",
                role="dispatcher",
                is_active=True,
                password_hash=hash_password("password123"),
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
    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


async def test_move_occurrence_is_visible_everywhere(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    client, factory = auth_db
    ids = await _seed_schedule_data(factory)
    async with factory.begin() as session:
        lesson = (
            await session.execute(select(Lesson).where(Lesson.parity == WeekParity.ODD_WEEK))
        ).scalar_one()
        lesson_id = lesson.id
        classroom_id = lesson.classroom_id
        old_slot = lesson.time_slot_id
        slot = TimeSlot(slot_number=1, start_time=time(9), end_time=time(10), day_of_week=4)
        session.add(slot)
        await session.flush()
        new_slot = slot.id
    headers = authorization(await login(client, "dispatcher"))
    payload = {
        "occurrence_date": "2026-10-19",
        "action": "move",
        "reason": "Room change",
        "target_date": "2026-10-22",
        "time_slot_id": new_slot,
        "classroom_id": classroom_id,
    }
    url = f"/api/v1/lessons/{lesson_id}/exceptions"
    response = await client.post(url, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    replacement_id = response.json()["replacement_lesson_id"]
    assert response.json()["reason"] == "Room change"
    assert response.json()["author_id"] > 0
    retry = await client.post(url, json=payload, headers=headers)
    assert retry.json()["id"] == response.json()["id"]
    different = dict(payload, reason="Other")
    assert (await client.post(url, json=different, headers=headers)).status_code == 409

    for path in (f"group/{ids['g1_id']}", f"teacher/{ids['t2_id']}"):
        old = await client.get(f"/api/v1/schedule/{path}?date=2026-10-19", headers=headers)
        new = await client.get(f"/api/v1/schedule/{path}?date=2026-10-22", headers=headers)
        assert lesson_id not in [item["id"] for item in old.json()["days"][0]["lessons"]]
        assert replacement_id in [item["id"] for item in new.json()["days"][3]["lessons"]]
        csv_url = f"/api/v1/schedule/{path}/export/csv?date=2026-10-22"
        csv = await client.get(csv_url, headers=headers)
        assert "Алгоритмы" in csv.text
        ics = await client.get(
            f"/api/v1/schedule/{path}/export/ics?start_date=2026-10-19&end_date=2026-10-22",
            headers=headers,
        )
        assert f"lesson-{lesson_id}-2026-10-19" not in ics.text
        assert f"lesson-{replacement_id}-2026-10-22" in ics.text

    rooms = await client.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={old_slot}&date=2026-10-19",
        headers=headers,
    )
    assert classroom_id in [room["id"] for room in rooms.json()]
    rooms = await client.get(
        f"/api/v1/schedule/classrooms/available?time_slot_id={new_slot}&date=2026-10-22",
        headers=headers,
    )
    assert classroom_id not in [room["id"] for room in rooms.json()]
    weekly = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}", headers=headers)
    lessons = weekly.json()["days"][0]["lessons"]
    source = next(item for item in lessons if item["id"] == lesson_id)
    assert source["exceptions"][0]["occurrence_date"] == "2026-10-19"
    csv = await client.get(f"/api/v1/schedule/group/{ids['g1_id']}/export/csv", headers=headers)
    assert "2026-10-19,move" in csv.text
    following = await client.get(
        f"/api/v1/schedule/group/{ids['g1_id']}?date=2026-11-02", headers=headers
    )
    assert lesson_id in [item["id"] for item in following.json()["days"][0]["lessons"]]


async def test_permissions_and_invalid_occurrence(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    client, factory = auth_db
    await _seed_schedule_data(factory)
    async with factory() as session:
        query = select(Lesson).where(Lesson.parity == WeekParity.ODD_WEEK)
        lesson = (await session.execute(query)).scalar_one()
        lesson_id = lesson.id
    url = f"/api/v1/lessons/{lesson_id}/exceptions"
    payload = {"occurrence_date": "2026-10-26", "action": "cancel", "reason": "Cancelled"}
    assert (await client.post(url, json=payload)).status_code == 401
    reader = authorization(await login(client, "reader"))
    assert (await client.post(url, json=payload, headers=reader)).status_code == 403
    dispatcher = authorization(await login(client, "dispatcher"))
    assert (await client.post(url, json=payload, headers=dispatcher)).status_code == 422
    payload["occurrence_date"] = "2026-10-19"
    assert (await client.post(url, json=payload, headers=dispatcher)).status_code == 201


async def test_conflict_and_cancel_one_off(
    auth_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    client, factory = auth_db
    ids = await _seed_schedule_data(factory)
    async with factory() as session:
        query = select(Lesson).where(Lesson.specific_date.is_not(None))
        lesson = (await session.execute(query)).scalar_one()
        lesson_id = lesson.id
        classroom_id = lesson.classroom_id
        time_slot_id = lesson.time_slot_id
    headers = authorization(await login(client, "dispatcher"))
    url = f"/api/v1/lessons/{lesson_id}/exceptions"
    data = {
        "occurrence_date": "2026-10-21",
        "action": "move",
        "reason": "Conflict",
        "target_date": "2026-10-21",
        "time_slot_id": time_slot_id,
        "classroom_id": classroom_id,
    }
    # The original is excluded, but a different lesson occupies the target teacher or room.
    data["classroom_id"] = 1
    result = await client.post(url, json=data, headers=headers)
    assert result.status_code == 409
    schedule_url = f"/api/v1/schedule/group/{ids['g1_id']}?date=2026-10-21"
    before = await client.get(schedule_url, headers=headers)
    assert [item["id"] for item in before.json()["days"][2]["lessons"]] == [lesson_id]
    cancel = {"occurrence_date": "2026-10-21", "action": "cancel", "reason": "Cancelled"}
    assert (await client.post(url, json=cancel, headers=headers)).status_code == 201
    after = await client.get(schedule_url, headers=headers)
    assert after.json()["days"][2]["lessons"] == []
    ics_url = f"/api/v1/schedule/group/{ids['g1_id']}/export/ics"
    ics_url += "?start_date=2026-10-21&end_date=2026-10-21"
    ics = await client.get(ics_url, headers=headers)
    assert f"lesson-{lesson_id}-2026-10-21" not in ics.text


async def test_concurrent_changes_keep_single_exception(
    concurrent_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = concurrent_db
    await _seed_schedule_data(factory)
    async with factory() as session:
        query = select(Lesson).where(Lesson.parity == WeekParity.ODD_WEEK)
        lesson_id = (await session.execute(query)).scalar_one().id
    headers = authorization(await login(client, "dispatcher"))
    url = f"/api/v1/lessons/{lesson_id}/exceptions"
    first = {"occurrence_date": "2026-10-19", "action": "cancel", "reason": "First"}
    second = dict(first, reason="Second")
    responses = await asyncio.gather(
        client.post(url, json=first, headers=headers),
        client.post(url, json=second, headers=headers),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]


async def test_concurrent_moves_cannot_reserve_same_resources(
    concurrent_db: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = concurrent_db
    await _seed_schedule_data(factory)
    async with factory.begin() as session:
        odd_query = select(Lesson).where(Lesson.parity == WeekParity.ODD_WEEK)
        one_off_query = select(Lesson).where(Lesson.specific_date.is_not(None))
        first_id = (await session.execute(odd_query)).scalar_one().id
        second = (await session.execute(one_off_query)).scalar_one()
        second_id = second.id
        classroom_id = second.classroom_id
        slot = TimeSlot(slot_number=1, start_time=time(9), end_time=time(10), day_of_week=4)
        session.add(slot)
        await session.flush()
        slot_id = slot.id
    headers = authorization(await login(client, "dispatcher"))
    destination = {
        "action": "move",
        "reason": "Move",
        "target_date": "2026-10-22",
        "time_slot_id": slot_id,
        "classroom_id": classroom_id,
    }
    first = dict(destination, occurrence_date="2026-10-19")
    second_data = dict(destination, occurrence_date="2026-10-21")
    responses = await asyncio.gather(
        client.post(f"/api/v1/lessons/{first_id}/exceptions", json=first, headers=headers),
        client.post(f"/api/v1/lessons/{second_id}/exceptions", json=second_data, headers=headers),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
