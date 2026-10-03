"""Unit tests for Lesson model, Pydantic schemas, and database migration."""

from datetime import date, datetime, time

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, Integer, Table, inspect, select

from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
)
from schedule_service.models.lesson import (
    Lesson,
    LessonParity,
    LessonType,
    WeekParity,
)
from schedule_service.schemas.lesson import (
    ClassroomNestedRead,
    GroupNestedRead,
    LessonCreate,
    LessonRead,
    LessonUpdate,
    SubjectNestedRead,
    TeacherNestedRead,
    TimeSlotNestedRead,
)


def test_lesson_model_structure() -> None:
    """Verify Lesson model table name, columns, foreign keys, and indexes."""
    assert Lesson.__tablename__ == "lessons"

    columns = {col.name: col for col in Lesson.__table__.columns}
    expected_columns = {
        "id",
        "created_at",
        "updated_at",
        "subject_id",
        "teacher_id",
        "group_id",
        "classroom_id",
        "time_slot_id",
        "lesson_type",
        "parity",
        "specific_date",
    }
    assert expected_columns.issubset(columns.keys())

    # Check primary key
    assert columns["id"].primary_key is True

    # Check nullability
    assert columns["subject_id"].nullable is False
    assert columns["teacher_id"].nullable is False
    assert columns["group_id"].nullable is False
    assert columns["classroom_id"].nullable is False
    assert columns["time_slot_id"].nullable is False
    assert columns["lesson_type"].nullable is False
    assert columns["parity"].nullable is False
    assert columns["specific_date"].nullable is True

    # Check foreign keys
    foreign_keys = {fk.parent.name: fk for fk in Lesson.__table__.foreign_keys}
    assert "subject_id" in foreign_keys
    assert foreign_keys["subject_id"].target_fullname == "subjects.id"
    assert foreign_keys["subject_id"].ondelete == "CASCADE"

    assert "teacher_id" in foreign_keys
    assert foreign_keys["teacher_id"].target_fullname == "teachers.id"
    assert foreign_keys["teacher_id"].ondelete == "CASCADE"

    assert "group_id" in foreign_keys
    assert foreign_keys["group_id"].target_fullname == "groups.id"
    assert foreign_keys["group_id"].ondelete == "CASCADE"

    assert "classroom_id" in foreign_keys
    assert foreign_keys["classroom_id"].target_fullname == "classrooms.id"
    assert foreign_keys["classroom_id"].ondelete == "CASCADE"

    assert "time_slot_id" in foreign_keys
    assert foreign_keys["time_slot_id"].target_fullname == "time_slots.id"
    assert foreign_keys["time_slot_id"].ondelete == "CASCADE"

    # Check indexes on FKs
    indexed_columns = {col.name for idx in Lesson.__table__.indexes for col in idx.columns}
    assert "subject_id" in indexed_columns
    assert "teacher_id" in indexed_columns
    assert "group_id" in indexed_columns
    assert "classroom_id" in indexed_columns
    assert "time_slot_id" in indexed_columns


def test_lesson_repr_and_enums() -> None:
    """Verify Lesson __repr__ and enum definitions."""
    lesson = Lesson(
        id=42,
        subject_id=1,
        teacher_id=2,
        group_id=3,
        classroom_id=4,
        time_slot_id=5,
        lesson_type=LessonType.LECTURE,
        parity=WeekParity.ODD_WEEK,
    )
    repr_str = repr(lesson)
    assert "Lesson" in repr_str
    assert "id=42" in repr_str
    assert "subject_id=1" in repr_str
    assert "teacher_id=2" in repr_str
    assert "group_id=3" in repr_str
    assert "classroom_id=4" in repr_str
    assert "time_slot_id=5" in repr_str
    assert "LECTURE" in repr_str
    assert "ODD_WEEK" in repr_str

    assert LessonType.LECTURE.value == "LECTURE"
    assert LessonType.SEMINAR.value == "SEMINAR"
    assert LessonType.LAB.value == "LAB"

    assert WeekParity.ALWAYS.value == "ALWAYS"
    assert WeekParity.ODD_WEEK.value == "ODD_WEEK"
    assert WeekParity.EVEN_WEEK.value == "EVEN_WEEK"
    assert LessonParity is WeekParity


def test_schema_lesson_create_valid() -> None:
    """Verify LessonCreate schema with valid data and default parity."""
    data = LessonCreate(
        subject_id=1,
        teacher_id=2,
        group_id=3,
        classroom_id=4,
        time_slot_id=5,
        lesson_type=LessonType.SEMINAR,
    )
    assert data.subject_id == 1
    assert data.parity == WeekParity.ALWAYS
    assert data.specific_date is None

    # Test with explicit parity and date
    specific = date(2026, 11, 15)
    data2 = LessonCreate(
        subject_id=10,
        teacher_id=20,
        group_id=30,
        classroom_id=40,
        time_slot_id=50,
        lesson_type=LessonType.LAB,
        parity=WeekParity.EVEN_WEEK,
        specific_date=specific,
    )
    assert data2.parity == WeekParity.EVEN_WEEK
    assert data2.specific_date == specific


def test_schema_lesson_create_validation_errors() -> None:
    """Verify LessonCreate raises ValidationError on invalid foreign key or missing fields."""
    with pytest.raises(ValidationError):
        LessonCreate(  # type: ignore[call-arg]
            subject_id=1,
            teacher_id=2,
            group_id=3,
            classroom_id=4,
            # missing time_slot_id and lesson_type
        )

    with pytest.raises(ValidationError):
        LessonCreate(
            subject_id=0,  # ID must be > 0
            teacher_id=2,
            group_id=3,
            classroom_id=4,
            time_slot_id=5,
            lesson_type=LessonType.LECTURE,
        )


def test_schema_lesson_update() -> None:
    """Verify LessonUpdate allows partial updates and validates field ranges."""
    empty_update = LessonUpdate()
    assert empty_update.subject_id is None
    assert empty_update.lesson_type is None

    partial = LessonUpdate(
        classroom_id=105,
        lesson_type=LessonType.LAB,
        parity=WeekParity.ODD_WEEK,
    )
    dumped = partial.model_dump(exclude_unset=True)
    assert dumped == {
        "classroom_id": 105,
        "lesson_type": LessonType.LAB,
        "parity": WeekParity.ODD_WEEK,
    }

    with pytest.raises(ValidationError):
        LessonUpdate(group_id=-1)


def test_schema_lesson_read_with_and_without_nested() -> None:
    """Verify LessonRead serialization with IDs only and with full nested objects."""
    now = datetime.now()
    read_simple = LessonRead(
        id=1,
        subject_id=10,
        teacher_id=20,
        group_id=30,
        classroom_id=40,
        time_slot_id=50,
        lesson_type=LessonType.LECTURE,
        parity=WeekParity.ALWAYS,
        created_at=now,
        updated_at=now,
    )
    assert read_simple.id == 1
    assert read_simple.subject is None
    assert read_simple.teacher is None
    assert read_simple.group is None
    assert read_simple.classroom is None
    assert read_simple.time_slot is None

    # Read with nested objects
    subject_nested = SubjectNestedRead(
        id=10, name="Operating Systems", code="OS-201", description="Core CS"
    )
    teacher_nested = TeacherNestedRead(
        id=20,
        full_name="Prof. Smith",
        email="smith@uni.edu",
        department="Computer Science",
    )
    group_nested = GroupNestedRead(
        id=30,
        name="CS-21",
        faculty="Informatics",
        course_number=2,
        student_count=28,
    )
    classroom_nested = ClassroomNestedRead(
        id=40,
        building="Main",
        room_number="301",
        capacity=35,
        has_projector=True,
    )
    timeslot_nested = TimeSlotNestedRead(
        id=50,
        slot_number=2,
        start_time=time(10, 45),
        end_time=time(12, 15),
        day_of_week=2,
    )

    read_full = LessonRead(
        id=2,
        subject_id=10,
        teacher_id=20,
        group_id=30,
        classroom_id=40,
        time_slot_id=50,
        lesson_type=LessonType.SEMINAR,
        parity=WeekParity.ODD_WEEK,
        specific_date=date(2026, 10, 1),
        created_at=now,
        updated_at=now,
        subject=subject_nested,
        teacher=teacher_nested,
        group=group_nested,
        classroom=classroom_nested,
        time_slot=timeslot_nested,
    )

    dumped = read_full.model_dump()
    assert dumped["id"] == 2
    assert dumped["subject"]["name"] == "Operating Systems"
    assert dumped["teacher"]["email"] == "smith@uni.edu"
    assert dumped["group"]["name"] == "CS-21"
    assert dumped["classroom"]["room_number"] == "301"
    assert dumped["time_slot"]["slot_number"] == 2


@pytest.mark.asyncio
async def test_lesson_database_persistence() -> None:
    """Verify Lesson entity persistence, query, and cascade metadata using SQLite in-memory."""
    # Ensure foreign key referenced tables are registered for SQLite in-memory test
    for tbl_name in ("subjects", "teachers", "groups", "classrooms", "time_slots"):
        Table(
            tbl_name,
            Base.metadata,
            Column("id", Integer, primary_key=True),
            extend_existing=True,
        )

    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        lesson = Lesson(
            subject_id=1,
            teacher_id=2,
            group_id=3,
            classroom_id=4,
            time_slot_id=5,
            lesson_type=LessonType.LECTURE,
            parity=WeekParity.ALWAYS,
            specific_date=date(2026, 9, 1),
        )
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)

        assert lesson.id is not None
        assert lesson.subject_id == 1
        assert lesson.lesson_type == LessonType.LECTURE
        assert lesson.parity == WeekParity.ALWAYS
        assert lesson.specific_date == date(2026, 9, 1)
        assert isinstance(lesson.created_at, datetime)
        assert isinstance(lesson.updated_at, datetime)

        # Test querying back
        result = await session.execute(select(Lesson).filter_by(teacher_id=2))
        fetched = result.scalar_one_or_none()
        assert fetched is not None
        assert fetched.id == lesson.id

        # Test validating into Pydantic schema from attributes
        read_dto = LessonRead.model_validate(fetched)
        assert read_dto.id == lesson.id
        assert read_dto.subject_id == 1
        assert read_dto.lesson_type == LessonType.LECTURE

    await engine.dispose()


def test_alembic_migration_upgrade_and_downgrade(pytestconfig: pytest.Config) -> None:
    """Verify that the Alembic migration runs upgrade and downgrade cleanly."""
    import importlib.util
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    root_dir = Path(pytestconfig.rootpath)
    version_files = list((root_dir / "alembic" / "versions").glob("*_create_lessons_table.py"))
    assert len(version_files) == 1, "Expected exactly one migration file for lessons table"
    migration_file = version_files[0]

    spec = importlib.util.spec_from_file_location("migration_mod", migration_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)

        # Test upgrade
        with Operations.context(ctx):
            mod.upgrade()

        inspector = inspect(conn)
        assert "lessons" in inspector.get_table_names()

        cols = {col["name"] for col in inspector.get_columns("lessons")}
        assert {
            "id",
            "subject_id",
            "teacher_id",
            "group_id",
            "classroom_id",
            "time_slot_id",
            "lesson_type",
            "parity",
            "specific_date",
            "created_at",
            "updated_at",
        }.issubset(cols)

        # Test downgrade
        with Operations.context(ctx):
            mod.downgrade()

        inspector = inspect(conn)
        assert "lessons" not in inspector.get_table_names()

    engine.dispose()
