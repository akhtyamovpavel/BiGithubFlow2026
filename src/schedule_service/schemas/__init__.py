"""Pydantic schemas module."""

from schedule_service.schemas.classroom import (
    ClassroomBase,
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
)
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
from schedule_service.schemas.schedule import (
    DaySchedule,
    GroupScheduleResponse,
    TeacherScheduleResponse,
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
    "ClassroomBase",
    "ClassroomCreate",
    "ClassroomNestedRead",
    "ClassroomRead",
    "ClassroomUpdate",
    "DaySchedule",
    "GroupBase",
    "GroupCreate",
    "GroupNestedRead",
    "GroupRead",
    "GroupScheduleResponse",
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
    "TeacherScheduleResponse",
    "TeacherUpdate",
    "TimeSlotBase",
    "TimeSlotCreate",
    "TimeSlotNestedRead",
    "TimeSlotRead",
    "TimeSlotUpdate",
    "WeekParity",
]
