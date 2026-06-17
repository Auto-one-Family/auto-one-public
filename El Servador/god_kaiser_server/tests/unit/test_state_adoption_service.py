import pytest

from src.services.state_adoption_service import StateAdoptionService


@pytest.mark.asyncio
async def test_reconnect_cycle_blocks_then_allows_enforce():
    service = StateAdoptionService()
    esp_id = "ESP_TEST_01"

    await service.start_reconnect_cycle(esp_id=esp_id, last_offline_seconds=120.0)
    assert await service.is_adopting(esp_id) is True
    assert await service.is_adoption_completed(esp_id) is False

    await service.mark_adoption_completed(esp_id)
    assert await service.is_adoption_completed(esp_id) is True


@pytest.mark.asyncio
async def test_records_adopted_actuator_states_during_adopting():
    service = StateAdoptionService()
    esp_id = "ESP_TEST_02"

    await service.start_reconnect_cycle(esp_id=esp_id, last_offline_seconds=61.0)
    await service.record_adopted_state(esp_id=esp_id, gpio=5, state="on", value=1.0)

    adopted = await service.get_adopted_state(esp_id=esp_id, gpio=5)
    assert adopted is not None
    assert adopted.state == "on"
    assert adopted.value == 1.0


@pytest.mark.asyncio
async def test_no_cycle_means_adoption_completed():
    service = StateAdoptionService()
    assert await service.is_adoption_completed("ESP_UNKNOWN") is True
