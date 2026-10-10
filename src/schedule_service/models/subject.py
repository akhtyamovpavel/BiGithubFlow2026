"""Subject SQLAlchemy model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.core.database import Base


class Subject(Base):
    """Subject (academic discipline / course) entity."""

    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    code: Mapped[str | None] = mapped_column(
        String(64),
        index=True,
        nullable=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Subject id={self.id} name='{self.name}' code='{self.code}'>"
