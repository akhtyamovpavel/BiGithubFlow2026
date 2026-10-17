"""REST API router for classrooms (auditoriums) management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.classroom import Classroom
from schedule_service.schemas.classroom import (
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


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
