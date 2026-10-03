"""Tests for Group SQLAlchemy model."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from schedule_service.core.database import Base, create_engine_and_sessionmaker
from schedule_service.models.group import Group


@pytest.mark.asyncio
async def test_create_and_query_group() -> None:
    """Test persisting and querying Group entity in in-memory SQLite."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        group = Group(
            name="Б05-201",
            faculty="ФРКТ",
            course_number=2,
            student_count=25,
            is_active=True,
        )
        session.add(group)
        await session.commit()
        await session.refresh(group)

        assert group.id is not None
        assert group.name == "Б05-201"
        assert group.faculty == "ФРКТ"
        assert group.course_number == 2
        assert group.student_count == 25
        assert group.is_active is True
        assert isinstance(group.created_at, datetime)
        assert isinstance(group.updated_at, datetime)
        assert "Б05-201" in repr(group)

    async with session_maker() as session:
        stmt = select(Group).where(Group.name == "Б05-201")
        result = await session.execute(stmt)
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.id == group.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_group_name_unique_constraint() -> None:
    """Test unique constraint on group name."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        g1 = Group(
            name="Б05-301",
            faculty="ФРКТ",
            course_number=3,
            student_count=20,
        )
        session.add(g1)
        await session.commit()

    async with session_maker() as session:
        g2 = Group(
            name="Б05-301",
            faculty="ФПМИ",
            course_number=3,
            student_count=22,
        )
        session.add(g2)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()
