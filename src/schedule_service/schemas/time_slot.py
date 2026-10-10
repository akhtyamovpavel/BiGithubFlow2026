"""TimeSlot Pydantic schemas module."""

from datetime import datetime, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeSlotBase(BaseModel):
    """Base schema for TimeSlot attributes."""

    slot_number: int = Field(
        ...,
        ge=1,
        le=12,
        description="Period sequence number in the schedule (1..7+)",
    )
    start_time: time = Field(
        ...,
        description="Slot start time (e.g. 09:00)",
    )
    end_time: time = Field(
        ...,
        description="Slot end time (e.g. 10:30)",
    )
    day_of_week: int = Field(
        ...,
        ge=1,
        le=7,
        description="Day of week: 1 - Monday ... 7 - Sunday",
    )

    @model_validator(mode="after")
    def validate_end_after_start(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly greater than start_time")
        return self


class TimeSlotCreate(TimeSlotBase):
    """Schema for creating a new time slot."""


class TimeSlotUpdate(BaseModel):
    """Schema for updating an existing time slot."""

    slot_number: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="Period sequence number in the schedule",
    )
    start_time: time | None = Field(
        default=None,
        description="Slot start time",
    )
    end_time: time | None = Field(
        default=None,
        description="Slot end time",
    )
    day_of_week: int | None = Field(
        default=None,
        ge=1,
        le=7,
        description="Day of week: 1 - Monday ... 7 - Sunday",
    )

    @model_validator(mode="after")
    def validate_end_after_start(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be strictly greater than start_time")
        return self


class TimeSlotRead(TimeSlotBase):
    """Schema for reading time slot data with database metadata."""

    id: int = Field(..., description="Unique time slot identifier")
    created_at: datetime = Field(..., description="Timestamp of record creation")
    updated_at: datetime = Field(..., description="Timestamp of last record update")

    model_config = ConfigDict(from_attributes=True)
