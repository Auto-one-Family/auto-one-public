"""
Integration Test Configuration.

Provides MQTT singleton isolation to prevent cross-test pollution.
The MQTTClient singleton must be reset between tests because:
- Direct MQTTClient.get_instance() calls bypass FastAPI DI mocks
- Stale connections from previous tests cause timeouts
- Singleton _initialized flag prevents re-initialization
"""

import pytest


@pytest.fixture(autouse=True)
def reset_mqtt_singleton():
    """
    Reset MQTT client singleton before each integration test.

    Without this, tests that call MQTTClient.get_instance() directly
    (e.g., test_resilience_integration.py, test_data_buffer.py) inherit
    stale connections from previous tests, causing 10s+ timeouts in CI.
    """
    from src.mqtt.client import MQTTClient

    # Store original state
    original_instance = MQTTClient._instance
    original_initialized = MQTTClient._initialized

    # Reset singleton before test
    if MQTTClient._instance is not None:
        try:
            MQTTClient._instance.disconnect()
        except Exception:
            pass
    MQTTClient._instance = None
    MQTTClient._initialized = False

    yield

    # Cleanup after test
    if MQTTClient._instance is not None:
        try:
            MQTTClient._instance.disconnect()
        except Exception:
            pass
    MQTTClient._instance = None
    MQTTClient._initialized = False
