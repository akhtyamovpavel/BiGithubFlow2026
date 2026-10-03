"""Academic group SQLAlchemy model."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class Group(Base):
    """Academic group entity."""

    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    faculty: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    course_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    student_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} name='{self.name}' course={self.course_number}>"
