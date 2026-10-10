"""TimeSlot SQLAlchemy model."""

from datetime import time

from sqlalchemy import CheckConstraint, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class TimeSlot(Base):
    """TimeSlot entity representing a scheduled pair/slot in the weekly timetable."""

    __tablename__ = "time_slots"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_time_slots_end_after_start"),
    )

    slot_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )
    end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TimeSlot id={self.id} slot={self.slot_number} day={self.day_of_week} "
            f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}>"
        )
