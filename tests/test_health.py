"""Unit tests for health endpoint and OpenAPI documentation."""

from fastapi.testclient import TestClient

from schedule_service.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify GET /health returns expected status and metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "ScheduleService",
        "version": "0.1.0",
    }


def test_docs_endpoint():
    """Verify Swagger UI documentation is accessible at /docs."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_openapi_spec():
    """Verify OpenAPI JSON schema includes health check endpoint."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "ScheduleService"
    assert data["info"]["version"] == "0.1.0"
    assert "/health" in data["paths"]
