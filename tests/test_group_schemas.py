"""Tests for academic group Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from schedule_service.schemas.group import GroupCreate, GroupRead, GroupUpdate


def test_group_create_valid() -> None:
    """Test creating GroupCreate schema with valid attributes."""
    data = {
        "name": "  Б05-201  ",
        "faculty": "  ФРКТ  ",
        "course_number": 3,
        "student_count": 28,
        "is_active": True,
    }
    schema = GroupCreate(**data)
    assert schema.name == "Б05-201"
    assert schema.faculty == "ФРКТ"
    assert schema.course_number == 3
    assert schema.student_count == 28
    assert schema.is_active is True


@pytest.mark.parametrize("invalid_name", ["", "   "])
def test_group_create_invalid_name(invalid_name: str) -> None:
    """Test validation failure on empty or blank group name."""
    with pytest.raises(ValidationError) as exc_info:
        GroupCreate(
            name=invalid_name,
            faculty="ФРКТ",
            course_number=1,
            student_count=20,
        )
    assert "name" in str(exc_info.value)


@pytest.mark.parametrize("invalid_faculty", ["", "   "])
def test_group_create_invalid_faculty(invalid_faculty: str) -> None:
    """Test validation failure on empty faculty string."""
    with pytest.raises(ValidationError) as exc_info:
        GroupCreate(
            name="Б05-101",
            faculty=invalid_faculty,
            course_number=1,
            student_count=20,
        )
    assert "faculty" in str(exc_info.value)


@pytest.mark.parametrize("invalid_count", [0, -1, -50])
def test_group_create_invalid_student_count(invalid_count: int) -> None:
    """Test validation failure when student count is non-positive."""
    with pytest.raises(ValidationError) as exc_info:
        GroupCreate(
            name="Б05-101",
            faculty="ФРКТ",
            course_number=1,
            student_count=invalid_count,
        )
    assert "student_count" in str(exc_info.value)


@pytest.mark.parametrize("invalid_course", [0, 7, -1, 10])
def test_group_create_invalid_course_number(invalid_course: int) -> None:
    """Test validation failure when course number is outside 1..6."""
    with pytest.raises(ValidationError) as exc_info:
        GroupCreate(
            name="Б05-101",
            faculty="ФРКТ",
            course_number=invalid_course,
            student_count=25,
        )
    assert "course_number" in str(exc_info.value)


def test_group_update_partial() -> None:
    """Test partial update schema with valid optional fields."""
    update_data = GroupUpdate(student_count=32, is_active=False)
    assert update_data.student_count == 32
    assert update_data.is_active is False
    assert update_data.name is None
    assert update_data.faculty is None
    assert update_data.course_number is None


def test_group_update_blank_name_fails() -> None:
    """Test update schema rejects whitespace-only name."""
    with pytest.raises(ValidationError) as exc_info:
        GroupUpdate(name="   ")
    assert "name" in str(exc_info.value)


def test_group_read_from_attributes() -> None:
    """Test GroupRead schema parses attributes from an object."""
    now = datetime.now(UTC)

    class DummyGroup:
        id = 1
        name = "М05-401"
        faculty = "Кафедра 1С"
        course_number = 5
        student_count = 15
        is_active = True
        created_at = now
        updated_at = now

    read_schema = GroupRead.model_validate(DummyGroup())
    assert read_schema.id == 1
    assert read_schema.name == "М05-401"
    assert read_schema.faculty == "Кафедра 1С"
    assert read_schema.course_number == 5
    assert read_schema.student_count == 15
    assert read_schema.created_at == now
