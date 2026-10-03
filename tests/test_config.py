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


def test_env_override(monkeypatch):
    """Verify settings loaded from environment variables."""
    monkeypatch.setenv("APP_NAME", "TestService")
    monkeypatch.setenv("VERSION", "1.2.3")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9999")

    settings = Settings()
    assert settings.app_name == "TestService"
    assert settings.version == "1.2.3"
    assert settings.environment == "production"
    assert settings.debug is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 9999


def test_invalid_port_validation(monkeypatch):
    """Verify validation error when invalid port is provided."""
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ValidationError):
        Settings()
