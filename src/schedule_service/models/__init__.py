"""Data models package."""

from schedule_service.core.database import Base
from schedule_service.models.group import Group

__all__ = ["Base", "Group"]
