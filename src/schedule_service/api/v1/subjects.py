"""REST API router for academic subjects (disciplines) management."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from schedule_service.core.database import get_async_session
from schedule_service.models.subject import Subject
from schedule_service.schemas.subject import SubjectCreate, SubjectRead, SubjectUpdate

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


def _case_insensitive_contains(
    column: InstrumentedAttribute[Any], term: str
) -> ColumnElement[bool]:
    """Build case-insensitive substring condition compatible with PostgreSQL and SQLite."""
    variants = {
        term,
        term.lower(),
        term.upper(),
        term.capitalize(),
        term.title(),
    }
    return or_(*(column.ilike(f"%{v}%") for v in variants))


@router.get(
    "/",
    response_model=list[SubjectRead],
    summary="List subjects",
    description=(
        "Retrieve a paginated list of academic subjects with optional search "
        "by name/code or exact code filtering."
    ),
)
async def list_subjects(
    search: Annotated[
        str | None,
        Query(description="Search subjects by substring in name or code"),
    ] = None,
    name: Annotated[
        str | None,
        Query(description="Filter subjects by substring in name"),
    ] = None,
    code: Annotated[
        str | None,
        Query(description="Filter subjects by exact discipline code"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Max number of records to return"),
    ] = 100,
    session: SessionDep = None,  # type: ignore[assignment]
) -> list[Subject]:
    """List subjects with search, filtering, and pagination."""
    query = select(Subject)
    if search is not None and search.strip():
        cleaned_search = search.strip()
        query = query.where(
            or_(
                _case_insensitive_contains(Subject.name, cleaned_search),
                _case_insensitive_contains(Subject.code, cleaned_search),
            )
        )
    if name is not None and name.strip():
        cleaned_name = name.strip()
        query = query.where(_case_insensitive_contains(Subject.name, cleaned_name))
    if code is not None and code.strip():
        query = query.where(Subject.code == code.strip())

    query = query.order_by(Subject.id).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{subject_id}",
    response_model=SubjectRead,
    summary="Get subject by ID",
    description="Retrieve detailed information about a specific academic subject.",
    responses={
        404: {"description": "Subject not found"},
    },
)
async def get_subject(
    subject_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Subject:
    """Get subject details by ID."""
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with id {subject_id} not found",
        )
    return subject


@router.post(
    "/",
    response_model=SubjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create subject",
    description="Register a new academic subject in the system.",
    responses={
        201: {"description": "Subject successfully created"},
        409: {"description": "Subject with the same name or code already exists"},
        422: {"description": "Validation error"},
    },
)
async def create_subject(
    subject_in: SubjectCreate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Subject:
    """Create a new subject."""
    existing_name = await session.execute(select(Subject).where(Subject.name == subject_in.name))
    if existing_name.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subject with name '{subject_in.name}' already exists",
        )

    if subject_in.code is not None:
        existing_code = await session.execute(
            select(Subject).where(Subject.code == subject_in.code)
        )
        if existing_code.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subject with code '{subject_in.code}' already exists",
            )

    subject = Subject(**subject_in.model_dump())
    session.add(subject)
    try:
        await session.flush()
        await session.refresh(subject)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subject '{subject_in.name}' already exists",
        ) from err
    return subject


@router.put(
    "/{subject_id}",
    response_model=SubjectRead,
    summary="Update subject",
    description="Update fields of an existing academic subject.",
    responses={
        200: {"description": "Subject successfully updated"},
        404: {"description": "Subject not found"},
        409: {"description": "Subject with the same name or code already exists"},
        422: {"description": "Validation error"},
    },
)
async def update_subject(
    subject_id: int,
    subject_in: SubjectUpdate,
    session: SessionDep = None,  # type: ignore[assignment]
) -> Subject:
    """Update existing subject details."""
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with id {subject_id} not found",
        )

    if subject_in.name is not None and subject_in.name != subject.name:
        existing_name = await session.execute(
            select(Subject).where(
                Subject.name == subject_in.name,
                Subject.id != subject_id,
            )
        )
        if existing_name.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subject with name '{subject_in.name}' already exists",
            )

    if subject_in.code is not None and subject_in.code != subject.code:
        existing_code = await session.execute(
            select(Subject).where(
                Subject.code == subject_in.code,
                Subject.id != subject_id,
            )
        )
        if existing_code.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subject with code '{subject_in.code}' already exists",
            )

    update_data = subject_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subject, field, value)

    try:
        await session.flush()
        await session.refresh(subject)
    except IntegrityError as err:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subject '{subject.name}' already exists",
        ) from err

    return subject


@router.delete(
    "/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete subject",
    description="Permanently delete an academic subject by its ID.",
    responses={
        204: {"description": "Subject successfully deleted"},
        404: {"description": "Subject not found"},
    },
)
async def delete_subject(
    subject_id: int,
    session: SessionDep = None,  # type: ignore[assignment]
) -> None:
    """Delete an academic subject by ID."""
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with id {subject_id} not found",
        )

    await session.delete(subject)
    await session.flush()
