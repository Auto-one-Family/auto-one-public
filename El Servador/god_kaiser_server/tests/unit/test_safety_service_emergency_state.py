from unittest.mock import AsyncMock

import pytest

from src.services.safety_service import SafetyService


@pytest.mark.asyncio
async def test_emergency_state_shared_across_instances():
    actuator_repo_a = AsyncMock()
    esp_repo_a = AsyncMock()
    actuator_repo_b = AsyncMock()
    esp_repo_b = AsyncMock()

    service_a = SafetyService(actuator_repo_a, esp_repo_a)
    service_b = SafetyService(actuator_repo_b, esp_repo_b)
    await service_a.clear_emergency_stop(None)

    await service_a.emergency_stop_esp("ESP_TEST_01")

    assert await service_b.is_emergency_stop_active("ESP_TEST_01") is True
    await service_b.clear_emergency_stop("ESP_TEST_01")
    assert await service_a.is_emergency_stop_active("ESP_TEST_01") is False
