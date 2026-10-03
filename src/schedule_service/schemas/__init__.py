"""Pydantic schemas module."""

from schedule_service.schemas.health import HealthResponse
from schedule_service.schemas.lesson import (
    ClassroomNestedRead,
    GroupNestedRead,
    LessonBase,
    LessonCreate,
    LessonRead,
    LessonType,
    LessonUpdate,
    SubjectNestedRead,
    TeacherNestedRead,
    TimeSlotNestedRead,
    WeekParity,
)

__all__ = [
    "ClassroomNestedRead",
    "GroupNestedRead",
    "HealthResponse",
    "LessonBase",
    "LessonCreate",
    "LessonRead",
    "LessonType",
    "LessonUpdate",
    "SubjectNestedRead",
    "TeacherNestedRead",
    "TimeSlotNestedRead",
    "WeekParity",
]
