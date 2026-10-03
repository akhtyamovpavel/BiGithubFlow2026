"""Application configuration module."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    app_name: str = Field(
        default="ScheduleService",
        description="Name of the application",
    )
    version: str = Field(
        default="0.1.0",
        description="Application version",
    )
    environment: str = Field(
        default="development",
        description="Deployment environment (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        description="Debug mode enabled flag",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Server host bind address",
    )
    port: int = Field(
        default=8000,
        description="Server port",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
