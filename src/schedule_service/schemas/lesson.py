"""Lesson Pydantic schemas module."""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from schedule_service.models.lesson import LessonType, WeekParity

__all__ = [
    "ClassroomNestedRead",
    "GroupNestedRead",
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


class SubjectNestedRead(BaseModel):
    """Nested schema for Subject details in LessonRead."""

    id: int = Field(..., description="Subject unique identifier")
    name: str = Field(..., description="Subject name")
    code: str | None = Field(default=None, description="Course code")
    description: str | None = Field(default=None, description="Subject description")

    model_config = ConfigDict(from_attributes=True)


class TeacherNestedRead(BaseModel):
    """Nested schema for Teacher details in LessonRead."""

    id: int = Field(..., description="Teacher unique identifier")
    full_name: str = Field(..., description="Teacher full name")
    email: str = Field(..., description="Teacher email address")
    department: str = Field(..., description="Academic department")
    position: str | None = Field(default=None, description="Academic position/rank")
    is_active: bool = Field(default=True, description="Active status")

    model_config = ConfigDict(from_attributes=True)


class GroupNestedRead(BaseModel):
    """Nested schema for Group details in LessonRead."""

    id: int = Field(..., description="Group unique identifier")
    name: str = Field(..., description="Group name/code")
    faculty: str = Field(..., description="Faculty or department")
    course_number: int = Field(..., description="Course/study year (1..6)")
    student_count: int = Field(..., description="Number of students in group")
    is_active: bool = Field(default=True, description="Active status")

    model_config = ConfigDict(from_attributes=True)


class ClassroomNestedRead(BaseModel):
    """Nested schema for Classroom details in LessonRead."""

    id: int = Field(..., description="Classroom unique identifier")
    building: str = Field(..., description="Building name or number")
    room_number: str = Field(..., description="Room number")
    capacity: int = Field(..., description="Seating capacity")
    has_projector: bool = Field(default=False, description="Projector available")
    has_computers: bool = Field(default=False, description="Computers available")
    is_active: bool = Field(default=True, description="Active status")

    model_config = ConfigDict(from_attributes=True)


class TimeSlotNestedRead(BaseModel):
    """Nested schema for TimeSlot details in LessonRead."""

    id: int = Field(..., description="TimeSlot unique identifier")
    slot_number: int = Field(..., description="Lesson slot sequence number (1..7)")
    start_time: time = Field(..., description="Slot start time")
    end_time: time = Field(..., description="Slot end time")
    day_of_week: int = Field(..., description="Day of week (1=Monday..7=Sunday)")

    model_config = ConfigDict(from_attributes=True)


class LessonBase(BaseModel):
    """Base schema for Lesson attributes."""

    subject_id: int = Field(..., gt=0, description="Subject ID")
    teacher_id: int = Field(..., gt=0, description="Teacher ID")
    group_id: int = Field(..., gt=0, description="Group ID")
    classroom_id: int = Field(..., gt=0, description="Classroom ID")
    time_slot_id: int = Field(..., gt=0, description="TimeSlot ID")
    lesson_type: LessonType = Field(..., description="Lesson type (LECTURE, SEMINAR, LAB)")
    parity: WeekParity = Field(
        default=WeekParity.ALWAYS,
        description="Week parity (ALWAYS, ODD_WEEK, EVEN_WEEK)",
    )
    specific_date: date | None = Field(
        default=None,
        description="Specific date for one-off lesson (optional)",
    )


class LessonCreate(LessonBase):
    """Schema for creating a new lesson."""


class LessonUpdate(BaseModel):
    """Schema for updating an existing lesson."""

    subject_id: int | None = Field(default=None, gt=0, description="Subject ID")
    teacher_id: int | None = Field(default=None, gt=0, description="Teacher ID")
    group_id: int | None = Field(default=None, gt=0, description="Group ID")
    classroom_id: int | None = Field(default=None, gt=0, description="Classroom ID")
    time_slot_id: int | None = Field(default=None, gt=0, description="TimeSlot ID")
    lesson_type: LessonType | None = Field(default=None, description="Lesson type")
    parity: WeekParity | None = Field(default=None, description="Week parity")
    specific_date: date | None = Field(default=None, description="Specific date")


class LessonRead(LessonBase):
    """Schema for reading lesson data, including timestamps and optional nested objects."""

    id: int = Field(..., description="Unique lesson ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    subject: SubjectNestedRead | None = Field(
        default=None,
        description="Detailed nested subject info",
    )
    teacher: TeacherNestedRead | None = Field(
        default=None,
        description="Detailed nested teacher info",
    )
    group: GroupNestedRead | None = Field(
        default=None,
        description="Detailed nested group info",
    )
    classroom: ClassroomNestedRead | None = Field(
        default=None,
        description="Detailed nested classroom info",
    )
    time_slot: TimeSlotNestedRead | None = Field(
        default=None,
        description="Detailed nested time slot info",
    )

    model_config = ConfigDict(from_attributes=True)
