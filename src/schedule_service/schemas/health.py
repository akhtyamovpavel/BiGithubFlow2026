"""Health check response schema."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check endpoint response schema."""

    status: str = Field(default="ok", description="Service status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
