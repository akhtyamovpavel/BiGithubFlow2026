"""REST API router for timetable time slots management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.time_slot import TimeSlot
from schedule_service.schemas.time_slot import (
    TimeSlotCreate,
    TimeSlotRead,
    TimeSlotUpdate,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get(
    "/",
    response_model=list[TimeSlotRead],
    summary="List time slots",
    description=(
        "Retrieve the bell schedule (time slots) ordered by day of week and slot number, "
        "with optional filtering by day of week or slot number."
    ),
)
async def list_time_slots(
    day_of_week: Annotated[
        int | None,
        Query(ge=1, le=7, description="Filter by day of week (1=Monday .. 7=Sunday)"),
    ] = None,
    slot_number: Annotated[
        int | None,
        Query(ge=1, le=12, description="Filter by slot/period sequence number"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Max number of records to return"),
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[TimeSlot]:
    """List time slots with filtering and pagination."""
    query = select(TimeSlot)
    if day_of_week is not None:
        query = query.where(TimeSlot.day_of_week == day_of_week)
    if slot_number is not None:
        query = query.where(TimeSlot.slot_number == slot_number)

    query = (
        query.order_by(TimeSlot.day_of_week, TimeSlot.slot_number, TimeSlot.id)
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{time_slot_id}",
    response_model=TimeSlotRead,
    summary="Get time slot by ID",
    description="Retrieve detailed information about a specific time slot.",
    responses={
        404: {"description": "Time slot not found"},
    },
)
async def get_time_slot(
    time_slot_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> TimeSlot:
    """Get time slot details by ID."""
    result = await session.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))
    slot = result.scalar_one_or_none()
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TimeSlot with id {time_slot_id} not found",
        )
    return slot


@router.post(
    "/",
    response_model=TimeSlotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create time slot",
    description=(
        "Create a new time slot in the weekly bell schedule. "
        "The combination of (day_of_week, slot_number) must be unique."
    ),
    responses={
        201: {"description": "Time slot successfully created"},
        409: {"description": "Time slot for this day and period already exists"},
        422: {"description": "Validation error"},
    },
)
async def create_time_slot(
    slot_in: TimeSlotCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> TimeSlot:
    """Create a new time slot."""
    existing = await session.execute(
        select(TimeSlot).where(
            TimeSlot.day_of_week == slot_in.day_of_week,
            TimeSlot.slot_number == slot_in.slot_number,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"TimeSlot with slot_number {slot_in.slot_number} on "
                f"day_of_week {slot_in.day_of_week} already exists"
            ),
        )

    slot = TimeSlot(**slot_in.model_dump())
    session.add(slot)
    try:
        await session.flush()
        await session.refresh(slot)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"TimeSlot with slot_number {slot_in.slot_number} on "
                f"day_of_week {slot_in.day_of_week} already exists"
            ),
        ) from err
    return slot


@router.put(
    "/{time_slot_id}",
    response_model=TimeSlotRead,
    summary="Update time slot",
    description="Update fields of an existing time slot.",
    responses={
        200: {"description": "Time slot successfully updated"},
        404: {"description": "Time slot not found"},
        409: {"description": "Time slot for this day and period already exists"},
        422: {"description": "Validation error"},
    },
)
async def update_time_slot(
    time_slot_id: int,
    slot_in: TimeSlotUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> TimeSlot:
    """Update existing time slot details."""
    result = await session.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))
    slot = result.scalar_one_or_none()
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TimeSlot with id {time_slot_id} not found",
        )

    new_start_time = slot_in.start_time if slot_in.start_time is not None else slot.start_time
    new_end_time = slot_in.end_time if slot_in.end_time is not None else slot.end_time
    if new_end_time <= new_start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_time must be strictly greater than start_time",
        )

    new_day = slot_in.day_of_week if slot_in.day_of_week is not None else slot.day_of_week
    new_slot_number = slot_in.slot_number if slot_in.slot_number is not None else slot.slot_number
    if (new_day, new_slot_number) != (slot.day_of_week, slot.slot_number):
        existing = await session.execute(
            select(TimeSlot).where(
                TimeSlot.day_of_week == new_day,
                TimeSlot.slot_number == new_slot_number,
                TimeSlot.id != time_slot_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"TimeSlot with slot_number {new_slot_number} on "
                    f"day_of_week {new_day} already exists"
                ),
            )

    update_data = slot_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(slot, field, value)

    try:
        await session.flush()
        await session.refresh(slot)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"TimeSlot with slot_number {new_slot_number} on "
                f"day_of_week {new_day} already exists"
            ),
        ) from err

    return slot


@router.delete(
    "/{time_slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete time slot",
    description="Permanently delete a time slot by its ID.",
    responses={
        204: {"description": "Time slot successfully deleted"},
        404: {"description": "Time slot not found"},
    },
)
async def delete_time_slot(
    time_slot_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a time slot by ID."""
    result = await session.execute(select(TimeSlot).where(TimeSlot.id == time_slot_id))
    slot = result.scalar_one_or_none()
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TimeSlot with id {time_slot_id} not found",
        )

    await session.delete(slot)
    await session.flush()
