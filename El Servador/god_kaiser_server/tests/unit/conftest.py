"""
Unit Test Configuration

This conftest overrides the autouse fixtures from the main conftest
for unit tests that don't need the full application setup.

Unit tests that test pure functions/classes (like DS18B20Processor)
don't need database, MQTT, or app setup.
"""

import pytest


@pytest.fixture(scope="function", autouse=True)
def override_get_db():
    """
    Override the autouse fixture from main conftest.

    Unit tests don't need database setup - they test pure functions.
    """
    yield


@pytest.fixture(scope="function", autouse=True)
def override_mqtt_publisher():
    """
    Override the autouse MQTT fixture from main conftest.

    Unit tests don't need MQTT setup.
    """
    yield


@pytest.fixture(scope="function", autouse=True)
def override_actuator_service():
    """
    Override the autouse actuator service fixture from main conftest.

    Unit tests don't need actuator service setup.
    """
    yield
