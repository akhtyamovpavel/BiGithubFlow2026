"""Teacher Pydantic schemas module."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pragmatic e-mail check: local@domain.tld, no spaces, single "@".
# Kept dependency-free on purpose (no email-validator in poetry.lock).
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Full name: letters (Latin/Cyrillic), spaces, hyphens, apostrophes and dots.
FULL_NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s.'\-]*$")


def _normalize_email(value: str) -> str:
    cleaned = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(cleaned):
        raise ValueError("Invalid email format")
    return cleaned


def _normalize_full_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Full name cannot be empty")
    if not FULL_NAME_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Full name may contain only letters, spaces, hyphens, apostrophes and dots"
        )
    return cleaned


def _normalize_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Field cannot be empty or contain only whitespaces")
    return cleaned


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class TeacherBase(BaseModel):
    """Base attributes for teacher."""

    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Teacher full name, e.g. Иванов Иван Иванович",
    )
    email: str = Field(
        ...,
        max_length=255,
        description="Unique e-mail used for contact and notifications",
    )
    department: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Academic department",
    )
    position: str | None = Field(
        default=None,
        max_length=128,
        description="Academic position, e.g. профессор, доцент, ассистент",
    )
    is_active: bool = Field(default=True, description="Active status flag")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        return _normalize_full_name(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str) -> str:
        return _normalize_required_text(v)

    @field_validator("position")
    @classmethod
    def validate_position(cls, v: str | None) -> str | None:
        return _normalize_optional_text(v)


class TeacherCreate(TeacherBase):
    """Schema for creating a new teacher."""


class TeacherUpdate(BaseModel):
    """Schema for partial update of an existing teacher."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, min_length=1, max_length=128)
    position: str | None = Field(default=None, max_length=128)
    is_active: bool | None = Field(default=None)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        return None if v is None else _normalize_full_name(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return None if v is None else _normalize_email(v)

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str | None) -> str | None:
        return None if v is None else _normalize_required_text(v)

    @field_validator("position")
    @classmethod
    def validate_position(cls, v: str | None) -> str | None:
        return _normalize_optional_text(v)


class TeacherRead(TeacherBase):
    """Schema for reading teacher details with metadata."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
