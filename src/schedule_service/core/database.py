"""Database connection and session management module."""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from schedule_service.core.config import get_settings


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base class with common fields."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def create_engine_and_sessionmaker(
    database_url: str | None = None,
    **engine_kwargs: Any,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create async engine and sessionmaker."""
    url = database_url or get_settings().database_url
    engine = create_async_engine(
        url,
        echo=get_settings().debug,
        future=True,
        **engine_kwargs,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


async_engine, async_session_factory = create_engine_and_sessionmaker()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session with transaction management."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
