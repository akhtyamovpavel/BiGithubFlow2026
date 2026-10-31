"""REST API router for classrooms (auditoriums) management."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.classroom import Classroom
from schedule_service.models.lesson import Lesson, WeekParity
from schedule_service.schemas.classroom import (
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
)
from schedule_service.services.conflict_service import overlapping_parities
from schedule_service.services.occurrences import active_on, week_parity

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


async def query_available_classrooms(
    session: AsyncSession,
    *,
    time_slot_id: int,
    parity: WeekParity = WeekParity.ALWAYS,
    target_date: dt.date | None = None,
    min_capacity: int | None = None,
    requires_projector: bool | None = None,
    requires_computers: bool | None = None,
    building: str | None = None,
) -> list[Classroom]:
    """Return active classrooms that have no conflicting lessons in the given time slot."""
    occupied_subquery = select(Lesson.classroom_id).where(
        Lesson.time_slot_id == time_slot_id,
    )
    if target_date is not None:
        if parity not in (WeekParity.ALWAYS, week_parity(target_date)):
            raise HTTPException(status_code=422, detail="Parity does not match the date")
        occupied_subquery = occupied_subquery.where(
            or_(
                Lesson.specific_date.is_(None),
                Lesson.specific_date == target_date,
            ),
            active_on(target_date),
            (Lesson.specific_date.is_not(None))
            | Lesson.parity.in_([WeekParity.ALWAYS, week_parity(target_date)]),
        )
    else:
        occupied_subquery = occupied_subquery.where(Lesson.parity.in_(overlapping_parities(parity)))

    query = select(Classroom).where(
        Classroom.is_active.is_(True),
        Classroom.id.not_in(occupied_subquery),
    )
    if min_capacity is not None:
        query = query.where(Classroom.capacity >= min_capacity)
    if requires_projector is not None:
        query = query.where(Classroom.has_projector == requires_projector)
    if requires_computers is not None:
        query = query.where(Classroom.has_computers == requires_computers)
    if building is not None and building.strip():
        query = query.where(Classroom.building == building.strip())

    query = query.order_by(Classroom.id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/",
    response_model=list[ClassroomRead],
    summary="List classrooms",
    description=(
        "Retrieve a paginated list of classrooms with optional filtering "
        "by minimum capacity, projector, computers, building, or active status."
    ),
)
async def list_classrooms(
    min_capacity: Annotated[
        int | None,
        Query(ge=1, description="Filter classrooms with capacity >= min_capacity"),
    ] = None,
    has_projector: Annotated[
        bool | None,
        Query(description="Filter classrooms by projector availability"),
    ] = None,
    has_computers: Annotated[
        bool | None,
        Query(description="Filter classrooms by computer equipment availability"),
    ] = None,
    building: Annotated[
        str | None,
        Query(description="Filter classrooms by building name"),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Filter classrooms by active status"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Max number of records to return"),
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[Classroom]:
    """List classrooms with filtering and pagination."""
    query = select(Classroom)
    if min_capacity is not None:
        query = query.where(Classroom.capacity >= min_capacity)
    if has_projector is not None:
        query = query.where(Classroom.has_projector == has_projector)
    if has_computers is not None:
        query = query.where(Classroom.has_computers == has_computers)
    if building is not None:
        query = query.where(Classroom.building == building.strip())
    if is_active is not None:
        query = query.where(Classroom.is_active == is_active)

    query = query.order_by(Classroom.id).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/available",
    response_model=list[ClassroomRead],
    summary="Find available classrooms for a time slot",
    description=(
        "Find active classrooms that are not occupied in the specified time slot "
        "and match optional capacity and equipment filters."
    ),
)
async def get_available_classrooms_endpoint(
    time_slot_id: Annotated[
        int,
        Query(gt=0, description="Target time slot ID"),
    ],
    parity: Annotated[
        WeekParity,
        Query(description="Week parity (ALWAYS, ODD_WEEK, EVEN_WEEK)"),
    ] = WeekParity.ALWAYS,
    target_date: Annotated[
        dt.date | None,
        Query(alias="date", description="Optional specific date (YYYY-MM-DD)"),
    ] = None,
    min_capacity: Annotated[
        int | None,
        Query(ge=1, description="Minimum required seating capacity"),
    ] = None,
    requires_projector: Annotated[
        bool | None,
        Query(description="Filter by projector availability"),
    ] = None,
    requires_computers: Annotated[
        bool | None,
        Query(description="Filter by computer equipment availability"),
    ] = None,
    building: Annotated[
        str | None,
        Query(description="Filter by building name"),
    ] = None,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[Classroom]:
    """Find free classrooms for the given time slot and filters."""
    return await query_available_classrooms(
        session,
        time_slot_id=time_slot_id,
        parity=parity,
        target_date=target_date,
        min_capacity=min_capacity,
        requires_projector=requires_projector,
        requires_computers=requires_computers,
        building=building,
    )


@router.get(
    "/{classroom_id}",
    response_model=ClassroomRead,
    summary="Get classroom by ID",
    description="Retrieve detailed information about a specific classroom.",
    responses={
        404: {"description": "Classroom not found"},
    },
)
async def get_classroom(
    classroom_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Classroom:
    """Get classroom details by ID."""
    result = await session.execute(select(Classroom).where(Classroom.id == classroom_id))
    classroom = result.scalar_one_or_none()
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classroom with id {classroom_id} not found",
        )
    return classroom


@router.post(
    "/",
    response_model=ClassroomRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create classroom",
    description=(
        "Register a new classroom in the system. "
        "The combination of (building, room_number) must be unique."
    ),
    responses={
        201: {"description": "Classroom successfully created"},
        409: {"description": "Classroom in this building already exists"},
        422: {"description": "Validation error"},
    },
)
async def create_classroom(
    classroom_in: ClassroomCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Classroom:
    """Create a new classroom."""
    existing = await session.execute(
        select(Classroom).where(
            Classroom.building == classroom_in.building,
            Classroom.room_number == classroom_in.room_number,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Classroom '{classroom_in.room_number}' in building "
                f"'{classroom_in.building}' already exists"
            ),
        )

    classroom = Classroom(**classroom_in.model_dump())
    session.add(classroom)
    try:
        await session.flush()
        await session.refresh(classroom)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Classroom '{classroom_in.room_number}' in building "
                f"'{classroom_in.building}' already exists"
            ),
        ) from err
    return classroom


@router.put(
    "/{classroom_id}",
    response_model=ClassroomRead,
    summary="Update classroom",
    description=(
        "Update fields of an existing classroom. "
        "If building or room_number is modified, their pair must remain unique."
    ),
    responses={
        200: {"description": "Classroom successfully updated"},
        404: {"description": "Classroom not found"},
        409: {"description": "Classroom with this building and room_number already exists"},
        422: {"description": "Validation error"},
    },
)
async def update_classroom(
    classroom_id: int,
    classroom_in: ClassroomUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Classroom:
    """Update existing classroom details."""
    result = await session.execute(select(Classroom).where(Classroom.id == classroom_id))
    classroom = result.scalar_one_or_none()
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classroom with id {classroom_id} not found",
        )

    new_building = (
        classroom_in.building if classroom_in.building is not None else classroom.building
    )
    new_room_number = (
        classroom_in.room_number if classroom_in.room_number is not None else classroom.room_number
    )

    if (new_building, new_room_number) != (classroom.building, classroom.room_number):
        existing = await session.execute(
            select(Classroom).where(
                Classroom.building == new_building,
                Classroom.room_number == new_room_number,
                Classroom.id != classroom_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Classroom '{new_room_number}' in building " f"'{new_building}' already exists"
                ),
            )

    update_data = classroom_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(classroom, field, value)

    try:
        await session.flush()
        await session.refresh(classroom)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Classroom '{new_room_number}' in building " f"'{new_building}' already exists"
            ),
        ) from err

    return classroom


@router.delete(
    "/{classroom_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete classroom",
    description="Permanently delete a classroom by its ID.",
    responses={
        204: {"description": "Classroom successfully deleted"},
        404: {"description": "Classroom not found"},
    },
)
async def delete_classroom(
    classroom_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a classroom by ID."""
    result = await session.execute(select(Classroom).where(Classroom.id == classroom_id))
    classroom = result.scalar_one_or_none()
    if classroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classroom with id {classroom_id} not found",
        )

    await session.delete(classroom)
    await session.flush()
