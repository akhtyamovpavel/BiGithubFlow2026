"""Shared rules for dated lesson occurrences."""

from datetime import date

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.models.lesson_exception import LessonException


def active_on(target_date: date) -> ColumnElement[bool]:
    """Match lessons that are not suppressed on this occurrence date."""
    exception = exists(
        select(LessonException.id).where(
            LessonException.lesson_id == Lesson.id,
            LessonException.occurrence_date == target_date,
        )
    )
    return ~exception


def week_parity(target_date: date) -> WeekParity:
    """Use ISO week numbering throughout the application."""
    if target_date.isocalendar().week % 2:
        return WeekParity.ODD_WEEK
    return WeekParity.EVEN_WEEK


async def lock_schedule(session: AsyncSession) -> None:
    """Serialize schedule writes until commit, including checks for free resources."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(548643065)"))
    elif dialect == "sqlite":
        await session.execute(text("UPDATE lessons SET id = id WHERE 0 = 1"))
    else:
        raise RuntimeError("Schedule writes require PostgreSQL or SQLite")
