"""REST API router for academic groups management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.group import Group
from schedule_service.schemas.group import GroupCreate, GroupRead, GroupUpdate

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get(
    "/",
    response_model=list[GroupRead],
    summary="List academic groups",
    description=(
        "Retrieve a paginated list of academic groups with optional filtering "
        "by course, faculty, or status."
    ),
)
async def list_groups(
    course_number: Annotated[
        int | None,
        Query(ge=1, le=6, description="Filter groups by academic course number"),
    ] = None,
    faculty: Annotated[
        str | None,
        Query(description="Filter groups by faculty name"),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Filter groups by active status"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Max number of records to return"),
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[Group]:
    """List academic groups with filtering and pagination."""
    query = select(Group)
    if course_number is not None:
        query = query.where(Group.course_number == course_number)
    if faculty is not None:
        query = query.where(Group.faculty == faculty.strip())
    if is_active is not None:
        query = query.where(Group.is_active == is_active)

    query = query.order_by(Group.id).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{group_id}",
    response_model=GroupRead,
    summary="Get group by ID",
    description="Retrieve detailed information about a specific academic group.",
    responses={
        404: {"description": "Group not found"},
    },
)
async def get_group(
    group_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Group:
    """Get group details by ID."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with id {group_id} not found",
        )
    return group


@router.post(
    "/",
    response_model=GroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create academic group",
    description="Register a new academic group in the system. Group name must be unique.",
    responses={
        201: {"description": "Group successfully created"},
        409: {"description": "Group name already exists"},
        422: {"description": "Validation error"},
    },
)
async def create_group(
    group_in: GroupCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Group:
    """Create a new academic group."""
    existing = await session.execute(select(Group).where(Group.name == group_in.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group with name '{group_in.name}' already exists",
        )

    group = Group(**group_in.model_dump())
    session.add(group)
    try:
        await session.flush()
        await session.refresh(group)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group with name '{group_in.name}' already exists",
        ) from err
    return group


@router.put(
    "/{group_id}",
    response_model=GroupRead,
    summary="Update academic group",
    description=(
        "Update fields of an existing academic group. If name is modified, it must remain unique."
    ),
    responses={
        200: {"description": "Group successfully updated"},
        404: {"description": "Group not found"},
        409: {"description": "Group name already exists"},
        422: {"description": "Validation error"},
    },
)
async def update_group(
    group_id: int,
    group_in: GroupUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Group:
    """Update existing academic group details."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with id {group_id} not found",
        )

    if group_in.name is not None and group_in.name != group.name:
        existing = await session.execute(
            select(Group).where(Group.name == group_in.name, Group.id != group_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Group with name '{group_in.name}' already exists",
            )

    update_data = group_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)

    try:
        await session.flush()
        await session.refresh(group)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group with name '{group_in.name}' already exists",
        ) from err

    return group


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete academic group",
    description="Permanently delete an academic group by its ID.",
    responses={
        204: {"description": "Group successfully deleted"},
        404: {"description": "Group not found"},
    },
)
async def delete_group(
    group_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete an academic group by ID."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group with id {group_id} not found",
        )

    await session.delete(group)
    await session.flush()
