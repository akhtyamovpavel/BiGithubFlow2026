"""Main application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.api.v1.router import api_v1_router
from schedule_service.core.config import Settings, get_settings
from schedule_service.core.database import check_database_health, get_async_session
from schedule_service.core.logging import configure_logging
from schedule_service.core.metrics import refresh_db_entity_counts, render_metrics
from schedule_service.core.middleware import RequestContextMiddleware
from schedule_service.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger("schedule_service.main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to validate configuration on startup."""
    # Instantiating settings validates all environment variables at startup
    settings = get_settings()
    configure_logging(settings)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings: Settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_v1_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        for error in errors:
            error.pop("input", None)
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Health Check (Liveness)",
        description="Returns application health status and version metadata.",
        tags=["Health"],
    )
    @app.get(
        "/health/live",
        response_model=HealthResponse,
        summary="Liveness Probe",
        description="Returns application liveness status.",
        tags=["Health"],
    )
    async def health_check() -> HealthResponse:
        """Return liveness status of the application."""
        return HealthResponse(
            status="ok",
            app_name=settings.app_name,
            version=settings.version,
        )

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={
            200: {
                "model": ReadinessResponse,
                "description": "Application and database are ready",
            },
            503: {
                "model": ReadinessResponse,
                "description": "Database or application is unavailable",
            },
        },
        summary="Readiness Probe",
        description="Checks application readiness and database connectivity.",
        tags=["Health"],
    )
    async def readiness_check(
        response: Response,
        db_healthy: bool = Depends(check_database_health),
    ) -> ReadinessResponse:
        """Return readiness status including database connection health."""
        if db_healthy:
            return ReadinessResponse(
                status="ok",
                app_name=settings.app_name,
                version=settings.version,
                database="ok",
            )
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="unavailable",
            app_name=settings.app_name,
            version=settings.version,
            database="unavailable",
        )

    @app.get(
        "/metrics",
        summary="Prometheus Metrics",
        description=(
            "Exposes HTTP RED metrics and ScheduleService business metrics "
            "in Prometheus text exposition format."
        ),
        tags=["Observability"],
        response_class=Response,
    )
    async def metrics_endpoint(
        session: Annotated[AsyncSession, Depends(get_async_session)],
    ) -> Response:
        """Refresh database entity gauges and return Prometheus metrics."""
        try:
            await refresh_db_entity_counts(session)
        except Exception:
            await session.rollback()
            logger.warning(
                "Failed to refresh database entity counts for /metrics",
                extra={"event": "metrics_db_refresh_failed"},
                exc_info=True,
            )
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return app


app = create_app()
