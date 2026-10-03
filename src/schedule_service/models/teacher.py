"""Teacher SQLAlchemy model."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class Teacher(Base):
    """Teacher (faculty member) entity."""

    __tablename__ = "teachers"

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    department: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    position: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Teacher id={self.id} full_name='{self.full_name}' email='{self.email}'>"
