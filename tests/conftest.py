"""Shared test configuration."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The mocked MQTT client leaves its own reconnect timer behind; it is not ours."""
    return True
