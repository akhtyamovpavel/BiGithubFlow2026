"""Tests for Teacher SQLAlchemy model and Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from schedule_service.core.database import create_engine_and_sessionmaker
from schedule_service.models.teacher import Teacher
from schedule_service.schemas.lesson import TeacherNestedRead
from schedule_service.schemas.teacher import TeacherCreate, TeacherRead, TeacherUpdate

VALID_TEACHER = {
    "full_name": "Иванов Иван Иванович",
    "email": "ivanov@phystech.edu",
    "department": "Кафедра 1С",
    "position": "доцент",
}


# --- Schemas -----------------------------------------------------------------


def test_teacher_create_valid_and_normalized() -> None:
    schema = TeacherCreate(
        full_name="  Иванов   Иван  Иванович ",
        email="  Ivanov@Phystech.EDU ",
        department="  Кафедра 1С ",
        position="  доцент ",
    )
    assert schema.full_name == "Иванов Иван Иванович"
    assert schema.email == "ivanov@phystech.edu"
    assert schema.department == "Кафедра 1С"
    assert schema.position == "доцент"
    assert schema.is_active is True


@pytest.mark.parametrize("full_name", ["Anna-Maria O'Neil", "Салтыков-Щедрин М. Е."])
def test_teacher_create_accepts_compound_names(full_name: str) -> None:
    assert TeacherCreate(**{**VALID_TEACHER, "full_name": full_name}).full_name == full_name


def test_teacher_position_is_optional_and_blank_becomes_none() -> None:
    data = {k: v for k, v in VALID_TEACHER.items() if k != "position"}
    assert TeacherCreate(**data).position is None
    assert TeacherCreate(**{**VALID_TEACHER, "position": "   "}).position is None


@pytest.mark.parametrize(
    "email",
    ["", "   ", "ivanov", "ivanov@", "@phystech.edu", "ivanov@phystech", "iva nov@a.ru", "a@@b.ru"],
)
def test_teacher_create_invalid_email(email: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TeacherCreate(**{**VALID_TEACHER, "email": email})
    assert "email" in str(exc_info.value)


@pytest.mark.parametrize("full_name", ["", "   ", "Иванов123", "John_Doe", "-Иванов"])
def test_teacher_create_invalid_full_name(full_name: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TeacherCreate(**{**VALID_TEACHER, "full_name": full_name})
    assert "full_name" in str(exc_info.value)


@pytest.mark.parametrize("department", ["", "   "])
def test_teacher_create_invalid_department(department: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TeacherCreate(**{**VALID_TEACHER, "department": department})
    assert "department" in str(exc_info.value)


def test_teacher_update_partial() -> None:
    update = TeacherUpdate(email="NEW@Mipt.RU", is_active=False)
    assert update.email == "new@mipt.ru"
    assert update.is_active is False
    assert update.full_name is None
    assert update.model_dump(exclude_unset=True) == {"email": "new@mipt.ru", "is_active": False}


@pytest.mark.parametrize(
    "payload",
    [{"email": "broken"}, {"full_name": "   "}, {"department": "  "}],
)
def test_teacher_update_rejects_invalid_values(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        TeacherUpdate(**payload)


def test_teacher_read_from_attributes() -> None:
    now = datetime.now(UTC)
    teacher = Teacher(id=7, is_active=True, created_at=now, updated_at=now, **VALID_TEACHER)

    read = TeacherRead.model_validate(teacher)
    assert read.id == 7
    assert read.email == "ivanov@phystech.edu"
    assert read.created_at == now


def test_teacher_model_compatible_with_lesson_nested_schema() -> None:
    """Teacher ORM object must serialize into TeacherNestedRead used by LessonRead (#10)."""
    teacher = Teacher(id=1, is_active=True, **VALID_TEACHER)
    nested = TeacherNestedRead.model_validate(teacher)
    assert nested.full_name == "Иванов Иван Иванович"
    assert nested.position == "доцент"


# --- Model / DB --------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_query_teacher() -> None:
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Teacher.__table__.create(sync_conn))

    async with session_maker() as session:
        teacher = Teacher(**TeacherCreate(**VALID_TEACHER).model_dump())
        session.add(teacher)
        await session.commit()
        await session.refresh(teacher)

        assert teacher.id is not None
        assert teacher.is_active is True
        assert isinstance(teacher.created_at, datetime)
        assert "ivanov@phystech.edu" in repr(teacher)

    async with session_maker() as session:
        result = await session.execute(
            select(Teacher).where(Teacher.email == "ivanov@phystech.edu")
        )
        fetched = result.scalar_one()
        assert fetched.full_name == "Иванов Иван Иванович"
        assert fetched.position == "доцент"

    await engine.dispose()


@pytest.mark.asyncio
async def test_teacher_email_unique_constraint() -> None:
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Teacher.__table__.create(sync_conn))

    async with session_maker() as session:
        session.add(Teacher(**VALID_TEACHER))
        await session.commit()

    async with session_maker() as session:
        session.add(Teacher(**{**VALID_TEACHER, "full_name": "Петров Пётр"}))
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


def test_teacher_table_has_unique_email_index() -> None:
    indexes = {idx.name: idx for idx in Teacher.__table__.indexes}
    assert "ix_teachers_email" in indexes
    assert indexes["ix_teachers_email"].unique is True
    assert [c.name for c in indexes["ix_teachers_email"].columns] == ["email"]
