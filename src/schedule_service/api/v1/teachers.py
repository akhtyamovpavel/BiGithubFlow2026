"""REST API router for teachers management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.teacher import Teacher
from schedule_service.schemas.teacher import TeacherCreate, TeacherRead, TeacherUpdate

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get(
    "/",
    response_model=list[TeacherRead],
    summary="List teachers",
    description=(
        "Retrieve a paginated list of teachers with optional filtering by "
        "department or active status."
    ),
)
async def list_teachers(
    department: Annotated[
        str | None,
        Query(description="Filter teachers by academic department"),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Filter teachers by active status"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Max number of records to return"),
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[Teacher]:
    """List teachers with filtering and pagination."""
    query = select(Teacher)
    if department is not None:
        query = query.where(Teacher.department == department.strip())
    if is_active is not None:
        query = query.where(Teacher.is_active == is_active)

    query = query.order_by(Teacher.id).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{teacher_id}",
    response_model=TeacherRead,
    summary="Get teacher by ID",
    description="Retrieve detailed information about a specific teacher.",
    responses={
        404: {"description": "Teacher not found"},
    },
)
async def get_teacher(
    teacher_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Teacher:
    """Get teacher details by ID."""
    result = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with id {teacher_id} not found",
        )
    return teacher


@router.post(
    "/",
    response_model=TeacherRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create teacher",
    description="Register a new teacher in the system. Email address must be unique.",
    responses={
        201: {"description": "Teacher successfully created"},
        409: {"description": "Teacher with this email already exists"},
        422: {"description": "Validation error"},
    },
)
async def create_teacher(
    teacher_in: TeacherCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Teacher:
    """Create a new teacher."""
    existing = await session.execute(select(Teacher).where(Teacher.email == teacher_in.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher with email '{teacher_in.email}' already exists",
        )

    teacher = Teacher(**teacher_in.model_dump())
    session.add(teacher)
    try:
        await session.flush()
        await session.refresh(teacher)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher with email '{teacher_in.email}' already exists",
        ) from err
    return teacher


@router.put(
    "/{teacher_id}",
    response_model=TeacherRead,
    summary="Update teacher",
    description="Update fields of an existing teacher. If email is changed, it must remain unique.",
    responses={
        200: {"description": "Teacher successfully updated"},
        404: {"description": "Teacher not found"},
        409: {"description": "Teacher with this email already exists"},
        422: {"description": "Validation error"},
    },
)
async def update_teacher(
    teacher_id: int,
    teacher_in: TeacherUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Teacher:
    """Update existing teacher details."""
    result = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with id {teacher_id} not found",
        )

    if teacher_in.email is not None and teacher_in.email != teacher.email:
        existing = await session.execute(
            select(Teacher).where(Teacher.email == teacher_in.email, Teacher.id != teacher_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Teacher with email '{teacher_in.email}' already exists",
            )

    update_data = teacher_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(teacher, field, value)

    try:
        await session.flush()
        await session.refresh(teacher)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher with email '{teacher_in.email}' already exists",
        ) from err

    return teacher


@router.delete(
    "/{teacher_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete teacher",
    description="Permanently delete a teacher by their ID.",
    responses={
        204: {"description": "Teacher successfully deleted"},
        404: {"description": "Teacher not found"},
    },
)
async def delete_teacher(
    teacher_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a teacher by ID."""
    result = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with id {teacher_id} not found",
        )

    await session.delete(teacher)
    await session.flush()
