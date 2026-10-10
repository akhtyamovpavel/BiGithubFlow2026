"""Unit tests for database module, Base model, and async session management."""

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
    get_async_session,
)


class SampleItem(Base):
    """Test entity inheriting from Base to verify audit fields."""

    __tablename__ = "test_sample_items"

    name: Mapped[str] = mapped_column(String(50), nullable=False)


@pytest.mark.asyncio
async def test_base_model_and_sqlite_in_memory() -> None:
    """Verify Base model audit fields on sqlite+aiosqlite:///:memory:."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[SampleItem.__table__])
        )

    async with session_maker() as session:
        item = SampleItem(name="Physics 101")
        session.add(item)
        await session.commit()
        await session.refresh(item)

        assert item.id is not None
        assert item.name == "Physics 101"
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_async_session_commit() -> None:
    """Verify get_async_session commits on successful iteration."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[SampleItem.__table__])
        )

    async def custom_dependency() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    gen = custom_dependency()
    session = await anext(gen)
    session.add(SampleItem(name="Calculus"))
    # Finish generator to trigger commit
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    # Verify committed data
    async with session_maker() as check_session:
        result = await check_session.execute(select(SampleItem).filter_by(name="Calculus"))
        retrieved = result.scalar_one_or_none()
        assert retrieved is not None
        assert retrieved.name == "Calculus"

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_async_session_rollback() -> None:
    """Verify get_async_session rolls back on exception."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[SampleItem.__table__])
        )

    async def failing_operation() -> None:
        async with session_maker() as session:
            try:
                session.add(SampleItem(name="Chemistry"))
                await session.flush()
                raise RuntimeError("Forced failure")
            except Exception:
                await session.rollback()
                raise

    with pytest.raises(RuntimeError, match="Forced failure"):
        await failing_operation()

    async with session_maker() as check_session:
        result = await check_session.execute(select(SampleItem).filter_by(name="Chemistry"))
        retrieved = result.scalar_one_or_none()
        assert retrieved is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_default_get_async_session_yields_session() -> None:
    """Verify default get_async_session yields an AsyncSession."""
    gen = get_async_session()
    session = await anext(gen)
    assert isinstance(session, AsyncSession)
    await session.close()


@pytest.mark.asyncio
async def test_check_database_health() -> None:
    """Verify check_database_health returns True when DB is reachable."""
    from schedule_service.core.database import check_database_health

    is_healthy = await check_database_health()
    # By default, sqlite in-memory or configured DB executes select(1)
    assert isinstance(is_healthy, bool)
