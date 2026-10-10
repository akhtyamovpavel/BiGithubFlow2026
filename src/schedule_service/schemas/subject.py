"""Subject Pydantic schemas module."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Subject name cannot be empty or contain only whitespace")
    return cleaned


def _normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class SubjectBase(BaseModel):
    """Base schema for Subject attributes."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the discipline / subject",
    )
    code: str | None = Field(
        default=None,
        max_length=64,
        description="Optional course/discipline code (e.g. CS101, МАТ-2)",
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Detailed description of the subject",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_name(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return _normalize_code(value)


class SubjectCreate(SubjectBase):
    """Schema for creating a new subject."""


class SubjectUpdate(BaseModel):
    """Schema for updating an existing subject."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Name of the discipline / subject",
    )
    code: str | None = Field(
        default=None,
        max_length=64,
        description="Optional course/discipline code",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Detailed description of the subject",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_name(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return _normalize_code(value)


class SubjectRead(SubjectBase):
    """Schema for reading subject data with database metadata."""

    id: int = Field(..., description="Unique subject identifier")
    created_at: datetime = Field(..., description="Timestamp of record creation")
    updated_at: datetime = Field(..., description="Timestamp of last record update")

    model_config = ConfigDict(from_attributes=True)
