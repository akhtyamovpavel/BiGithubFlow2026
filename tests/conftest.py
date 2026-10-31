"""Keep existing resource tests focused on resource behavior."""

from collections.abc import Generator

import pytest

from schedule_service.core.auth import get_current_user
from schedule_service.main import app
from schedule_service.models.user import User, UserRole


@pytest.fixture(autouse=True)
def resource_test_identity(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if request.node.get_closest_marker("auth_integration") is None:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, username="test-admin", password_hash="", role=UserRole.ADMIN.value, is_active=True
        )
    yield
    app.dependency_overrides.pop(get_current_user, None)
