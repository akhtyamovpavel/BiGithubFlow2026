"""Health and readiness check response schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check endpoint response schema (liveness probe)."""

    status: str = Field(default="ok", description="Service status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")


class ReadinessResponse(BaseModel):
    """Readiness check endpoint response schema (readiness probe)."""

    status: str = Field(..., description="Service readiness status ('ok' or 'unavailable')")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    database: str = Field(..., description="Database status ('ok' or 'unavailable')")
