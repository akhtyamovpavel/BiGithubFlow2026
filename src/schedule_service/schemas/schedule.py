"""Pydantic schemas for weekly schedule view endpoints."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from schedule_service.models.lesson import WeekParity
from schedule_service.schemas.lesson import (
    GroupNestedRead,
    LessonRead,
    TeacherNestedRead,
)

__all__ = [
    "DaySchedule",
    "GroupScheduleResponse",
    "TeacherScheduleResponse",
]


class DaySchedule(BaseModel):
    """Schedule for a single day of the week."""

    day_of_week: int = Field(
        ...,
        ge=1,
        le=7,
        description="Day of week (1=Monday .. 6=Saturday, 7=Sunday)",
    )
    lessons: list[LessonRead] = Field(
        default_factory=list,
        description="Lessons scheduled for this day ordered by time slot",
    )

    model_config = ConfigDict(from_attributes=True)


class GroupScheduleResponse(BaseModel):
    """Structured weekly schedule response for an academic group."""

    group_id: int = Field(..., description="Academic group ID")
    group: GroupNestedRead = Field(..., description="Academic group details")
    parity: WeekParity | None = Field(
        default=None,
        description="Applied week parity filter (ODD_WEEK, EVEN_WEEK, ALWAYS)",
    )
    date: dt.date | None = Field(
        default=None,
        description="Applied specific date filter",
    )
    days: list[DaySchedule] = Field(
        default_factory=list,
        description="Schedule grouped by days of the week (1..6)",
    )

    model_config = ConfigDict(from_attributes=True)


class TeacherScheduleResponse(BaseModel):
    """Structured weekly schedule response for a teacher."""

    teacher_id: int = Field(..., description="Teacher ID")
    teacher: TeacherNestedRead = Field(..., description="Teacher details")
    parity: WeekParity | None = Field(
        default=None,
        description="Applied week parity filter (ODD_WEEK, EVEN_WEEK, ALWAYS)",
    )
    date: dt.date | None = Field(
        default=None,
        description="Applied specific date filter",
    )
    days: list[DaySchedule] = Field(
        default_factory=list,
        description="Schedule grouped by days of the week (1..6)",
    )

    model_config = ConfigDict(from_attributes=True)
