"""Pydantic schemas module."""

from schedule_service.schemas.group import GroupBase, GroupCreate, GroupRead, GroupUpdate
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
from schedule_service.schemas.teacher import (
    TeacherBase,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)

__all__ = [
    "ClassroomNestedRead",
    "GroupBase",
    "GroupCreate",
    "GroupNestedRead",
    "GroupRead",
    "GroupUpdate",
    "HealthResponse",
    "LessonBase",
    "LessonCreate",
    "LessonRead",
    "LessonType",
    "LessonUpdate",
    "SubjectNestedRead",
    "TeacherBase",
    "TeacherCreate",
    "TeacherNestedRead",
    "TeacherRead",
    "TeacherUpdate",
    "TimeSlotNestedRead",
    "WeekParity",
]
