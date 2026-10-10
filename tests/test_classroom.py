"""Tests for Classroom SQLAlchemy model and Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from schedule_service.core.database import create_engine_and_sessionmaker
from schedule_service.models.classroom import Classroom
from schedule_service.schemas.classroom import (
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
)
from schedule_service.schemas.lesson import ClassroomNestedRead

VALID_CLASSROOM = {
    "building": "Главный корпус",
    "room_number": "115",
    "capacity": 50,
    "has_projector": True,
    "has_computers": False,
    "is_active": True,
}


# --- Schemas -----------------------------------------------------------------


def test_classroom_create_valid_and_normalized() -> None:
    schema = ClassroomCreate(
        building="   Главный корпус   ",
        room_number="   115   ",
        capacity=45,
    )
    assert schema.building == "Главный корпус"
    assert schema.room_number == "115"
    assert schema.capacity == 45
    assert schema.has_projector is False
    assert schema.has_computers is False
    assert schema.is_active is True


@pytest.mark.parametrize("building", ["", "   "])
def test_classroom_create_invalid_building(building: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClassroomCreate(
            building=building,
            room_number="115",
            capacity=30,
        )
    assert "building" in str(exc_info.value)


@pytest.mark.parametrize("room_number", ["", "   "])
def test_classroom_create_invalid_room_number(room_number: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClassroomCreate(
            building="АК",
            room_number=room_number,
            capacity=30,
        )
    assert "room_number" in str(exc_info.value)


@pytest.mark.parametrize("capacity", [0, -1, -100])
def test_classroom_create_invalid_capacity(capacity: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClassroomCreate(
            building="АК",
            room_number="115",
            capacity=capacity,
        )
    assert "capacity" in str(exc_info.value)


def test_classroom_update_partial() -> None:
    update = ClassroomUpdate(capacity=75, has_projector=True)
    assert update.capacity == 75
    assert update.has_projector is True
    assert update.building is None
    assert update.room_number is None
    assert update.model_dump(exclude_unset=True) == {"capacity": 75, "has_projector": True}


@pytest.mark.parametrize(
    "payload",
    [{"building": "   "}, {"room_number": "   "}, {"capacity": 0}, {"capacity": -5}],
)
def test_classroom_update_rejects_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ClassroomUpdate(**payload)


def test_classroom_read_from_attributes() -> None:
    now = datetime.now(UTC)
    classroom = Classroom(
        id=12,
        created_at=now,
        updated_at=now,
        **VALID_CLASSROOM,
    )

    read = ClassroomRead.model_validate(classroom)
    assert read.id == 12
    assert read.building == "Главный корпус"
    assert read.room_number == "115"
    assert read.capacity == 50
    assert read.has_projector is True
    assert read.has_computers is False
    assert read.is_active is True
    assert read.created_at == now


def test_classroom_model_compatible_with_lesson_nested_schema() -> None:
    classroom = Classroom(id=3, **VALID_CLASSROOM)
    nested = ClassroomNestedRead.model_validate(classroom)
    assert nested.id == 3
    assert nested.building == "Главный корпус"
    assert nested.room_number == "115"
    assert nested.capacity == 50
    assert nested.has_projector is True
    assert nested.has_computers is False
    assert nested.is_active is True


# --- Model / DB --------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_query_classroom() -> None:
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Classroom.__table__.create(sync_conn))

    async with session_maker() as session:
        classroom = Classroom(**ClassroomCreate(**VALID_CLASSROOM).model_dump())
        session.add(classroom)
        await session.commit()
        await session.refresh(classroom)

        assert classroom.id is not None
        assert classroom.building == "Главный корпус"
        assert classroom.room_number == "115"
        assert classroom.capacity == 50
        assert classroom.is_active is True
        assert isinstance(classroom.created_at, datetime)
        assert "Главный корпус" in repr(classroom)
        assert "115" in repr(classroom)

    async with session_maker() as session:
        result = await session.execute(
            select(Classroom).where(
                Classroom.building == "Главный корпус",
                Classroom.room_number == "115",
            )
        )
        fetched = result.scalar_one()
        assert fetched.id == classroom.id
        assert fetched.capacity == 50

    await engine.dispose()


@pytest.mark.asyncio
async def test_classroom_unique_constraint() -> None:
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Classroom.__table__.create(sync_conn))

    async with session_maker() as session:
        session.add(Classroom(**VALID_CLASSROOM))
        await session.commit()

    # Same room in different building should succeed
    async with session_maker() as session:
        session.add(Classroom(**{**VALID_CLASSROOM, "building": "АК"}))
        await session.commit()

    # Same building and room number should raise IntegrityError
    async with session_maker() as session:
        session.add(Classroom(**{**VALID_CLASSROOM, "capacity": 100}))
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()
