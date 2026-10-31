"""Changes to individual occurrences of a lesson."""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class LessonException(Base):
    """Cancellation or replacement of a single scheduled occurrence."""

    __tablename__ = "lesson_exceptions"
    __table_args__ = (
        UniqueConstraint("lesson_id", "occurrence_date", name="uq_lesson_exception_occurrence"),
        CheckConstraint(
            "action IN ('cancel','move') AND (replacement_lesson_id IS NULL) = (action = 'cancel')",
            name="ck_lesson_exception_action",
        ),
    )

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), index=True
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    replacement_lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), unique=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
