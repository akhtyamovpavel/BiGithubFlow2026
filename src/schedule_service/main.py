"""Main application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from schedule_service.core.config import Settings, get_settings
from schedule_service.schemas.health import HealthResponse


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

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Health Check",
        description="Returns application health status and version metadata.",
        tags=["Health"],
    )
    async def health_check() -> HealthResponse:
        """Return health status of the application."""
        return HealthResponse(
            status="ok",
            app_name=settings.app_name,
            version=settings.version,
        )

    return app


app = create_app()
