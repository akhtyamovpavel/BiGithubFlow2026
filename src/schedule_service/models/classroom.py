"""Classroom SQLAlchemy model."""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class Classroom(Base):
    """Classroom (auditorium/room) entity."""

    __tablename__ = "classrooms"

    building: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    room_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    has_projector: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    has_computers: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("building", "room_number", name="uq_classrooms_building_room_number"),
    )

    def __repr__(self) -> str:
        return (
            f"<Classroom id={self.id} building='{self.building}' "
            f"room_number='{self.room_number}' capacity={self.capacity}>"
        )
