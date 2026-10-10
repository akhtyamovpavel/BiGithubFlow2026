"""Unit tests for health endpoints and OpenAPI documentation."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from schedule_service.core.database import check_database_health
from schedule_service.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_dependency_overrides() -> Generator[None, None, None]:
    """Clear FastAPI dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


def test_health_endpoint() -> None:
    """Verify legacy GET /health returns expected status and metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "ScheduleService",
        "version": "0.1.0",
    }


def test_liveness_endpoint() -> None:
    """Verify GET /health/live returns 200 OK with liveness metadata."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "ScheduleService",
        "version": "0.1.0",
    }


def test_readiness_endpoint_healthy() -> None:
    """Verify GET /health/ready returns 200 OK when database is accessible."""
    app.dependency_overrides[check_database_health] = lambda: True

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "ScheduleService",
        "version": "0.1.0",
        "database": "ok",
    }


def test_readiness_endpoint_database_unavailable() -> None:
    """Verify GET /health/ready returns 503 Service Unavailable when DB is down."""
    app.dependency_overrides[check_database_health] = lambda: False

    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "app_name": "ScheduleService",
        "version": "0.1.0",
        "database": "unavailable",
    }


def test_docs_endpoint() -> None:
    """Verify Swagger UI documentation is accessible at /docs."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_openapi_spec() -> None:
    """Verify OpenAPI JSON schema includes health check and readiness endpoints."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "ScheduleService"
    assert data["info"]["version"] == "0.1.0"
    assert "/health" in data["paths"]
    assert "/health/live" in data["paths"]
    assert "/health/ready" in data["paths"]
