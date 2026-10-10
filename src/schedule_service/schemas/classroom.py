"""Classroom Pydantic schemas module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_and_validate_not_empty(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Field cannot be empty or contain only whitespaces")
    return cleaned


def _strip_and_validate_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Field cannot be empty or contain only whitespaces")
    return cleaned


class ClassroomBase(BaseModel):
    """Base attributes for classroom."""

    building: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Building name or number, e.g. Главный корпус, АК",
    )
    room_number: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Room number, e.g. 115, Физхим 4",
    )
    capacity: int = Field(
        ...,
        gt=0,
        description="Seating capacity for students (must be > 0)",
    )
    has_projector: bool = Field(
        default=False,
        description="Whether the classroom has a projector",
    )
    has_computers: bool = Field(
        default=False,
        description="Whether the classroom is equipped with computers",
    )
    is_active: bool = Field(
        default=True,
        description="Active status flag",
    )

    @field_validator("building", "room_number")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        return _strip_and_validate_not_empty(v)


class ClassroomCreate(ClassroomBase):
    """Schema for creating a new classroom."""


class ClassroomUpdate(BaseModel):
    """Schema for updating an existing classroom."""

    building: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Building name or number",
    )
    room_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Room number",
    )
    capacity: int | None = Field(
        default=None,
        gt=0,
        description="Seating capacity",
    )
    has_projector: bool | None = Field(
        default=None,
        description="Projector available flag",
    )
    has_computers: bool | None = Field(
        default=None,
        description="Computers available flag",
    )
    is_active: bool | None = Field(
        default=None,
        description="Active status flag",
    )

    @field_validator("building", "room_number")
    @classmethod
    def validate_optional_strings(cls, v: str | None) -> str | None:
        return _strip_and_validate_optional(v)


class ClassroomRead(ClassroomBase):
    """Schema for reading classroom details with metadata."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
