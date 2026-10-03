"""Unit tests for configuration."""

import pytest
from pydantic import ValidationError

from schedule_service.core.config import Settings


def test_default_settings():
    """Verify default configuration values."""
    settings = Settings()
    assert settings.app_name == "ScheduleService"
    assert settings.version == "0.1.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert "postgresql+asyncpg" in settings.database_url
    assert settings.postgres_server == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_user == "postgres"
    assert settings.postgres_password == "postgres"
    assert settings.postgres_db == "schedule_db"


def test_env_override(monkeypatch):
    """Verify settings loaded from environment variables."""
    monkeypatch.setenv("APP_NAME", "TestService")
    monkeypatch.setenv("VERSION", "1.2.3")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/custom_db")
    monkeypatch.setenv("POSTGRES_SERVER", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")
    monkeypatch.setenv("POSTGRES_DB", "custom_db")

    settings = Settings()
    assert settings.app_name == "TestService"
    assert settings.version == "1.2.3"
    assert settings.environment == "production"
    assert settings.debug is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 9999
    assert settings.database_url == "postgresql+asyncpg://user:pass@db:5432/custom_db"
    assert settings.postgres_server == "db"
    assert settings.postgres_port == 5433
    assert settings.postgres_user == "user"
    assert settings.postgres_password == "pass"
    assert settings.postgres_db == "custom_db"


def test_invalid_port_validation(monkeypatch):
    """Verify validation error when invalid port is provided."""
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ValidationError):
        Settings()
