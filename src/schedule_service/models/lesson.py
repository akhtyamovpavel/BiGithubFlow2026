"""Lesson SQLAlchemy model module."""

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class LessonType(str, enum.Enum):
    """Enum representing type of the lesson."""

    LECTURE = "LECTURE"
    SEMINAR = "SEMINAR"
    LAB = "LAB"


class WeekParity(str, enum.Enum):
    """Enum representing week parity for recurring lessons."""

    ALWAYS = "ALWAYS"
    ODD_WEEK = "ODD_WEEK"
    EVEN_WEEK = "EVEN_WEEK"


LessonParity = WeekParity


class Lesson(Base):
    """Schedule lesson entity linking subject, teacher, group, classroom and time slot."""

    __tablename__ = "lessons"

    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    classroom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    time_slot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("time_slots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_type: Mapped[LessonType] = mapped_column(
        Enum(LessonType, native_enum=False, length=20),
        nullable=False,
    )
    parity: Mapped[WeekParity] = mapped_column(
        Enum(WeekParity, native_enum=False, length=20),
        nullable=False,
        default=WeekParity.ALWAYS,
    )
    specific_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return (
            f"<Lesson id={self.id} subject_id={self.subject_id} teacher_id={self.teacher_id} "
            f"group_id={self.group_id} classroom_id={self.classroom_id} "
            f"time_slot_id={self.time_slot_id} type={self.lesson_type} parity={self.parity}>"
        )
