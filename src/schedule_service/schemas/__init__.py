"""Pydantic schemas module."""

from schedule_service.schemas.group import GroupBase, GroupCreate, GroupRead, GroupUpdate
from schedule_service.schemas.health import HealthResponse, ReadinessResponse
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
from schedule_service.schemas.subject import (
    SubjectBase,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
)
from schedule_service.schemas.teacher import (
    TeacherBase,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)
from schedule_service.schemas.time_slot import (
    TimeSlotBase,
    TimeSlotCreate,
    TimeSlotRead,
    TimeSlotUpdate,
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
    "ReadinessResponse",
    "SubjectBase",
    "SubjectCreate",
    "SubjectNestedRead",
    "SubjectRead",
    "SubjectUpdate",
    "TeacherBase",
    "TeacherCreate",
    "TeacherNestedRead",
    "TeacherRead",
    "TeacherUpdate",
    "TimeSlotBase",
    "TimeSlotCreate",
    "TimeSlotNestedRead",
    "TimeSlotRead",
    "TimeSlotUpdate",
    "WeekParity",
]
