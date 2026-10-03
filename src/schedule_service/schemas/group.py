"""Group Pydantic schemas module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GroupBase(BaseModel):
    """Base attributes for academic group."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique name or code of the group, e.g. Б05-201",
    )
    faculty: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Faculty or department name",
    )
    course_number: int = Field(
        ...,
        ge=1,
        le=6,
        description="Academic year/course number (1 to 6)",
    )
    student_count: int = Field(
        ...,
        gt=0,
        description="Number of students in the group (must be > 0)",
    )
    is_active: bool = Field(
        default=True,
        description="Active status flag",
    )

    @field_validator("name", "faculty")
    @classmethod
    def strip_and_validate_not_empty(cls, v: str) -> str:
        """Strip whitespace and ensure string is not blank."""
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or contain only whitespaces")
        return cleaned


class GroupCreate(GroupBase):
    """Schema for creating a new academic group."""


class GroupUpdate(BaseModel):
    """Schema for updating an existing academic group."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Unique name or code of the group",
    )
    faculty: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Faculty or department name",
    )
    course_number: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="Academic year/course number",
    )
    student_count: int | None = Field(
        default=None,
        gt=0,
        description="Number of students in the group",
    )
    is_active: bool | None = Field(
        default=None,
        description="Active status flag",
    )

    @field_validator("name", "faculty")
    @classmethod
    def strip_and_validate_optional(cls, v: str | None) -> str | None:
        """Strip whitespace if present and ensure not blank."""
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or contain only whitespaces")
        return cleaned


class GroupRead(GroupBase):
    """Schema for reading group details with metadata."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
