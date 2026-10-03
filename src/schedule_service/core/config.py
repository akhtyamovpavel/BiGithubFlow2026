"""Application configuration module."""

from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    app_name: str = Field(
        default="ScheduleService",
        validation_alias=AliasChoices("app_name", "APP_NAME"),
        description="Name of the application",
    )
    version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices("version", "VERSION", "app_version", "APP_VERSION"),
        description="Application version",
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("environment", "ENVIRONMENT"),
        description="Deployment environment (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("debug", "DEBUG"),
        description="Debug mode enabled flag",
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("host", "HOST"),
        description="Server host bind address",
    )
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("port", "PORT"),
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
