"""Unit tests for Subject and TimeSlot models, schemas, and Alembic migrations."""

import importlib.util
from datetime import datetime, time
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from schedule_service.core.database import (
    Base,
    create_engine_and_sessionmaker,
)
from schedule_service.models.subject import Subject
from schedule_service.models.time_slot import TimeSlot
from schedule_service.schemas.subject import (
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
)
from schedule_service.schemas.time_slot import (
    TimeSlotCreate,
    TimeSlotRead,
    TimeSlotUpdate,
)


def test_subject_model_structure() -> None:
    """Verify Subject model table name, columns, and repr."""
    assert Subject.__tablename__ == "subjects"

    cols = {col.name: col for col in Subject.__table__.columns}
    assert {"id", "name", "code", "description", "created_at", "updated_at"}.issubset(cols.keys())

    assert cols["id"].primary_key is True
    assert cols["name"].nullable is False
    assert cols["code"].nullable is True
    assert cols["description"].nullable is False

    subject = Subject(id=1, name="Calculus", code="MATH101", description="Calculus I")
    repr_str = repr(subject)
    assert "Subject" in repr_str
    assert "id=1" in repr_str
    assert "Calculus" in repr_str
    assert "MATH101" in repr_str


def test_timeslot_model_structure() -> None:
    """Verify TimeSlot model table name, columns, constraints, and repr."""
    assert TimeSlot.__tablename__ == "time_slots"

    cols = {col.name: col for col in TimeSlot.__table__.columns}
    assert {
        "id",
        "slot_number",
        "start_time",
        "end_time",
        "day_of_week",
        "created_at",
        "updated_at",
    }.issubset(cols.keys())

    assert cols["id"].primary_key is True
    assert cols["slot_number"].nullable is False
    assert cols["start_time"].nullable is False
    assert cols["end_time"].nullable is False
    assert cols["day_of_week"].nullable is False

    # Check constraint
    constraints = {c.name: c for c in TimeSlot.__table__.constraints if hasattr(c, "name")}
    assert "ck_time_slots_end_after_start" in constraints

    slot = TimeSlot(
        id=5,
        slot_number=2,
        start_time=time(10, 45),
        end_time=time(12, 15),
        day_of_week=1,
    )
    repr_str = repr(slot)
    assert "TimeSlot" in repr_str
    assert "id=5" in repr_str
    assert "slot=2" in repr_str
    assert "day=1" in repr_str
    assert "10:45-12:15" in repr_str


def test_subject_schemas_validation() -> None:
    """Verify Subject Pydantic schemas (create, update, read)."""
    # Create valid
    subj = SubjectCreate(name="  Physics  ", code=" PHYS-1 ", description="General Physics")
    assert subj.name == "Physics"
    assert subj.code == "PHYS-1"
    assert subj.description == "General Physics"

    # Default description & None code
    subj2 = SubjectCreate(name="Chemistry")
    assert subj2.code is None
    assert subj2.description == ""

    # Invalid empty name
    with pytest.raises(ValidationError):
        SubjectCreate(name="   ")

    # Update valid
    update = SubjectUpdate(name=" Advanced Physics ", description="New desc")
    assert update.name == "Advanced Physics"
    assert update.description == "New desc"

    # Update invalid blank name
    with pytest.raises(ValidationError):
        SubjectUpdate(name="   ")

    # Read schema
    now = datetime.now()
    subj_read = SubjectRead(
        id=10,
        name="Linear Algebra",
        code="LA1",
        description="Matrices",
        created_at=now,
        updated_at=now,
    )
    assert subj_read.id == 10
    assert subj_read.name == "Linear Algebra"


def test_timeslot_schemas_validation() -> None:
    """Verify TimeSlot Pydantic schemas (create, update, read) including end_time > start_time."""
    # Valid creation
    slot = TimeSlotCreate(
        slot_number=1,
        start_time=time(9, 0),
        end_time=time(10, 30),
        day_of_week=1,
    )
    assert slot.slot_number == 1
    assert slot.start_time == time(9, 0)
    assert slot.end_time == time(10, 30)
    assert slot.day_of_week == 1

    # Invalid: end_time == start_time
    with pytest.raises(ValidationError, match="end_time must be strictly greater than start_time"):
        TimeSlotCreate(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(9, 0),
            day_of_week=1,
        )

    # Invalid: end_time < start_time
    with pytest.raises(ValidationError, match="end_time must be strictly greater than start_time"):
        TimeSlotCreate(
            slot_number=1,
            start_time=time(11, 0),
            end_time=time(10, 0),
            day_of_week=1,
        )

    # Invalid day_of_week
    with pytest.raises(ValidationError):
        TimeSlotCreate(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(10, 30),
            day_of_week=8,
        )

    with pytest.raises(ValidationError):
        TimeSlotCreate(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(10, 30),
            day_of_week=0,
        )

    # Invalid slot_number
    with pytest.raises(ValidationError):
        TimeSlotCreate(
            slot_number=0,
            start_time=time(9, 0),
            end_time=time(10, 30),
            day_of_week=1,
        )

    # Update validation
    update_valid = TimeSlotUpdate(start_time=time(8, 30), end_time=time(10, 0))
    assert update_valid.start_time == time(8, 30)

    with pytest.raises(ValidationError, match="end_time must be strictly greater than start_time"):
        TimeSlotUpdate(start_time=time(10, 0), end_time=time(9, 0))

    # Read schema
    now = datetime.now()
    read_slot = TimeSlotRead(
        id=3,
        slot_number=2,
        start_time=time(10, 45),
        end_time=time(12, 15),
        day_of_week=2,
        created_at=now,
        updated_at=now,
    )
    assert read_slot.id == 3
    assert read_slot.slot_number == 2


@pytest.mark.asyncio
async def test_subject_and_timeslot_db_persistence() -> None:
    """Verify database persistence and constraints for Subject and TimeSlot."""
    engine, session_maker = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[Subject.__table__, TimeSlot.__table__]
            )
        )

    async with session_maker() as session:
        # Subject insert
        subj = Subject(
            name="Mathematical Analysis",
            code="MATH-101",
            description="Differential equations",
        )
        session.add(subj)

        # TimeSlot insert
        slot = TimeSlot(
            slot_number=1,
            start_time=time(9, 0),
            end_time=time(10, 30),
            day_of_week=1,
        )
        session.add(slot)
        await session.commit()
        await session.refresh(subj)
        await session.refresh(slot)

        assert subj.id is not None
        assert subj.name == "Mathematical Analysis"
        assert isinstance(subj.created_at, datetime)

        assert slot.id is not None
        assert slot.slot_number == 1
        assert slot.start_time == time(9, 0)
        assert isinstance(slot.created_at, datetime)

        # Query back
        res_subj = await session.execute(select(Subject).filter_by(code="MATH-101"))
        assert res_subj.scalar_one_or_none() is not None

        res_slot = await session.execute(select(TimeSlot).filter_by(slot_number=1, day_of_week=1))
        assert res_slot.scalar_one_or_none() is not None

        # Verify Pydantic model_validate from ORM
        read_subj = SubjectRead.model_validate(subj)
        assert read_subj.id == subj.id
        assert read_subj.name == subj.name

        read_slot = TimeSlotRead.model_validate(slot)
        assert read_slot.id == slot.id
        assert read_slot.slot_number == slot.slot_number

    # Verify CheckConstraint in DB
    async with session_maker() as session:
        invalid_slot = TimeSlot(
            slot_number=2,
            start_time=time(12, 0),
            end_time=time(11, 0),  # violates end_time > start_time
            day_of_week=2,
        )
        session.add(invalid_slot)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


def test_alembic_subjects_and_time_slots_migration(pytestconfig: pytest.Config) -> None:
    """Verify that Alembic migration runs upgrade/downgrade for subjects and time_slots."""
    root_dir = Path(pytestconfig.rootpath)
    version_files = list(
        (root_dir / "alembic" / "versions").glob("*_create_subjects_and_time_slots_tables.py")
    )
    assert (
        len(version_files) == 1
    ), "Expected exactly one migration file for subjects and time_slots"
    migration_file = version_files[0]

    spec = importlib.util.spec_from_file_location("migration_subj_slot", migration_file)
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
        tables = inspector.get_table_names()
        assert "subjects" in tables
        assert "time_slots" in tables

        subj_cols = {col["name"] for col in inspector.get_columns("subjects")}
        assert {"id", "name", "code", "description", "created_at", "updated_at"}.issubset(subj_cols)

        slot_cols = {col["name"] for col in inspector.get_columns("time_slots")}
        assert {
            "id",
            "slot_number",
            "start_time",
            "end_time",
            "day_of_week",
            "created_at",
            "updated_at",
        }.issubset(slot_cols)

        # Test downgrade
        with Operations.context(ctx):
            mod.downgrade()

        inspector = inspect(conn)
        tables_after = inspector.get_table_names()
        assert "subjects" not in tables_after
        assert "time_slots" not in tables_after

    engine.dispose()
