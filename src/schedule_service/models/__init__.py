"""Data models package."""

from schedule_service.core.database import Base
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, LessonParity, LessonType, WeekParity
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot

__all__ = [
    "Base",
    "Classroom",
    "Group",
    "Lesson",
    "LessonParity",
    "LessonType",
    "Subject",
    "Teacher",
    "TimeSlot",
    "WeekParity",
]
