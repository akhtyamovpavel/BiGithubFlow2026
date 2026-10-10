"""Main application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status

from schedule_service.api.v1.router import api_v1_router
from schedule_service.core.config import Settings, get_settings
from schedule_service.core.database import check_database_health
from schedule_service.schemas.health import HealthResponse, ReadinessResponse


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to validate configuration on startup."""
    # Instantiating settings validates all environment variables at startup
    _ = get_settings()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings: Settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.include_router(api_v1_router)

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

    return app


app = create_app()
