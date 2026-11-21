"""REST API router for CSV schedule import preview, status recovery, and atomic commit."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.auth import require_schedule_editor
from schedule_service.core.database import get_async_session
from schedule_service.models.user import User
from schedule_service.schemas.csv_import import CsvImportBatchResponse
from schedule_service.services.csv_import_service import (
    CSV_IMPORT_MAX_BYTES,
    ImportBatchNotFoundError,
    ImportConflictError,
    ImportFormatError,
    ImportPayloadTooLargeError,
    build_csv_template,
    confirm_csv_import,
    get_import_batch,
    preview_csv_import,
)

router = APIRouter(dependencies=[Depends(require_schedule_editor)])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
EditorDep = Annotated[User, Depends(require_schedule_editor)]


@router.get(
    "/template",
    summary="Download CSV import template",
    description="Download UTF-8 CSV template with required column headers and an example row.",
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV template attachment"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin or dispatcher role required"},
    },
)
async def download_csv_template() -> Response:
    """Return the official CSV schedule import template."""
    return Response(
        content=build_csv_template(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="schedule_import_template.csv"',
        },
    )


@router.post(
    "/preview",
    response_model=CsvImportBatchResponse,
    summary="Upload CSV and preview validation results",
    description=(
        "Upload a CSV file (<= 1 MiB, <= 500 rows), validate references, dates, "
        "intra-file and database conflicts, and return a persisted batch_id for confirmation."
    ),
    responses={
        200: {"description": "Preview generated or idempotent batch returned"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin or dispatcher role required"},
        409: {"description": "Idempotency-Key reused with different payload"},
        413: {"description": "CSV file exceeds maximum size limit"},
        422: {"description": "Invalid CSV format, missing columns, or row limit exceeded"},
    },
)
async def upload_csv_preview(
    file: Annotated[UploadFile, File(description="UTF-8 CSV file with lessons to import")],
    editor: EditorDep,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            max_length=128,
            description="Optional idempotency key to prevent duplicate uploads on retry",
        ),
    ] = None,
) -> CsvImportBatchResponse:
    """Upload CSV, validate all rows without mutating lessons, and persist preview batch."""
    raw_bytes = await file.read(CSV_IMPORT_MAX_BYTES + 1)
    cleaned_key = idempotency_key.strip() if idempotency_key else None
    try:
        return await preview_csv_import(
            session,
            raw_bytes=raw_bytes,
            filename=file.filename,
            created_by=editor.username,
            idempotency_key=cleaned_key or None,
        )
    except ImportPayloadTooLargeError as err:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(err),
        ) from err
    except ImportFormatError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except ImportConflictError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err.message,
        ) from err


@router.get(
    "/{batch_id}",
    response_model=CsvImportBatchResponse,
    summary="Get CSV import batch status",
    description=(
        "Inspect current status of an import batch (safe to call after connection loss "
        "during confirmation to check whether lessons were committed)."
    ),
    responses={
        200: {"description": "Current batch status and preview/commit summary"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin or dispatcher role required"},
        404: {"description": "Import batch not found"},
    },
)
async def get_csv_import_status(
    batch_id: str,
    session: SessionDep,
) -> CsvImportBatchResponse:
    """Return batch status for safe recovery after connection drop."""
    try:
        return await get_import_batch(session, batch_id=batch_id)
    except ImportBatchNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.post(
    "/{batch_id}/confirm",
    response_model=CsvImportBatchResponse,
    summary="Confirm and atomically commit CSV import batch",
    description=(
        "Re-validate the batch against the latest database state under a schedule lock "
        "and insert all lessons in a single transaction. Idempotent on repeated calls."
    ),
    responses={
        200: {"description": "Batch committed (or already committed idempotently)"},
        401: {"description": "Authentication required"},
        403: {"description": "Admin or dispatcher role required"},
        404: {"description": "Import batch not found"},
        409: {"description": "Validation or schedule conflict detected on confirm"},
    },
)
async def confirm_csv_import_batch(
    batch_id: str,
    session: SessionDep,
) -> CsvImportBatchResponse | JSONResponse:
    """Atomically commit a validated CSV import batch."""
    try:
        return await confirm_csv_import(session, batch_id=batch_id)
    except ImportBatchNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except ImportConflictError as err:
        if err.batch is not None:
            content = err.batch.model_dump(mode="json")
            content["detail"] = err.message
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=content)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.message) from err
