from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.esp_service import ESPService


def _build_service(
    device: SimpleNamespace, publish_success: bool = True
) -> tuple[ESPService, MagicMock, AsyncMock]:
    esp_repo = MagicMock()
    esp_repo.get_by_device_id = AsyncMock(return_value=device)
    esp_repo.session = AsyncMock()
    publisher = MagicMock()
    publisher.publish_config.return_value = publish_success
    service = ESPService(esp_repo=esp_repo, publisher=publisher)
    ws_broadcast = AsyncMock()
    return service, publisher, ws_broadcast


@pytest.mark.asyncio
async def test_send_config_mock_device_emits_terminal_config_response() -> None:
    device = SimpleNamespace(status="online", hardware_type="MOCK_ESP32")
    service, publisher, ws_broadcast = _build_service(device)
    config = {"sensors": [{"gpio": 5}], "actuators": [], "offline_rules": []}

    with (
        patch("src.services.esp_service.AuditLogRepository") as audit_repo_cls,
        patch(
            "src.websocket.manager.WebSocketManager.get_instance",
            new=AsyncMock(return_value=SimpleNamespace(broadcast=ws_broadcast)),
        ),
    ):
        audit_repo_cls.return_value.create = AsyncMock()
        result = await service.send_config("MOCK_TEST01", config)

    assert result["success"] is True
    publisher.publish_config.assert_called_once()
    published_config = publisher.publish_config.call_args.kwargs["config"]
    assert published_config["reason_code"] == "manual_config_sync"
    assert isinstance(published_config["generation"], int)
    assert published_config["generation"] > 0
    assert isinstance(published_config["config_fingerprint"], str)
    assert len(published_config["config_fingerprint"]) == 64

    event_types = [call.args[0] for call in ws_broadcast.await_args_list]
    assert "config_published" in event_types
    assert "config_response" in event_types

    terminal_call = next(
        call for call in ws_broadcast.await_args_list if call.args[0] == "config_response"
    )
    payload = terminal_call.args[1]
    assert payload["esp_id"] == "MOCK_TEST01"
    assert payload["status"] == "success"
    assert payload["correlation_id"] == result["correlation_id"]


@pytest.mark.asyncio
async def test_send_config_real_device_does_not_emit_synthetic_config_response() -> None:
    device = SimpleNamespace(status="online", hardware_type="ESP32_WROOM")
    service, _, ws_broadcast = _build_service(device)
    config = {"sensors": [{"gpio": 5}], "actuators": [], "offline_rules": []}

    with (
        patch("src.services.esp_service.AuditLogRepository") as audit_repo_cls,
        patch(
            "src.websocket.manager.WebSocketManager.get_instance",
            new=AsyncMock(return_value=SimpleNamespace(broadcast=ws_broadcast)),
        ),
    ):
        audit_repo_cls.return_value.create = AsyncMock()
        result = await service.send_config("ESP_A1B2C3D4", config)

    assert result["success"] is True
    event_types = [call.args[0] for call in ws_broadcast.await_args_list]
    assert event_types.count("config_published") == 1
    assert "config_response" not in event_types


def test_config_fingerprint_is_stable_for_semantically_equal_payloads() -> None:
    service, _, _ = _build_service(SimpleNamespace(status="online", hardware_type="ESP32_WROOM"))
    payload_a = {
        "sensors": [{"gpio": 4, "sensor_type": "ds18b20"}],
        "actuators": [{"gpio": 25, "actuator_type": "relay"}],
        "offline_rules": [],
    }
    payload_b = {
        "offline_rules": [],
        "actuators": [{"actuator_type": "relay", "gpio": 25}],
        "sensors": [{"sensor_type": "ds18b20", "gpio": 4}],
    }

    fingerprint_a = service._compute_config_fingerprint(payload_a)
    fingerprint_b = service._compute_config_fingerprint(payload_b)

    assert fingerprint_a == fingerprint_b


# =============================================================================
# AUT-59: _strip_inconsistent_offline_rules
# =============================================================================


class TestStripInconsistentOfflineRules:
    """AUT-59: Defense-in-depth validation in ESPService.send_config."""

    def _service(self) -> ESPService:
        esp_repo = MagicMock()
        esp_repo.session = AsyncMock()
        publisher = MagicMock()
        return ESPService(esp_repo=esp_repo, publisher=publisher)

    def test_consistent_config_unchanged(self):
        """Config where offline_rules match actuator/sensor GPIOs is not mutated."""
        service = self._service()
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [{"gpio": 18}],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-1")

        assert stripped == []
        assert len(config["offline_rules"]) == 1

    def test_missing_actuator_gpio_stripped(self):
        """offline_rule with actuator_gpio not in actuator payloads is stripped."""
        service = self._service()
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [{"gpio": 22}],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-2")

        assert len(stripped) == 1
        assert stripped[0]["actuator_gpio"] == 18
        assert config["offline_rules"] == []

    def test_missing_sensor_gpio_stripped(self):
        """offline_rule with sensor_gpio not in sensor payloads is stripped."""
        service = self._service()
        config = {
            "sensors": [{"gpio": 7}],
            "actuators": [{"gpio": 18}],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-3")

        assert len(stripped) == 1
        assert config["offline_rules"] == []

    def test_no_offline_rules_returns_empty(self):
        """Config without offline_rules key returns empty stripped list."""
        service = self._service()
        config = {"sensors": [{"gpio": 4}], "actuators": [{"gpio": 18}]}

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-4")

        assert stripped == []

    def test_empty_actuators_strips_all_rules(self):
        """No actuators in config → all offline_rules stripped."""
        service = self._service()
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
                {"actuator_gpio": 19, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-5")

        assert len(stripped) == 2
        assert config["offline_rules"] == []

    def test_time_window_only_rule_not_stripped_by_sensor_gpio_255(self):
        """time-window-only rule uses synthetic sensor_gpio=255 and must stay in config."""
        service = self._service()
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [{"gpio": 25}],
            "offline_rules": [
                {"actuator_gpio": 25, "sensor_gpio": 255, "sensor_value_type": "__twindow_on"},
            ],
        }

        stripped = service._strip_inconsistent_offline_rules(config, "ESP_TEST01", "corr-6")

        assert stripped == []
        assert len(config["offline_rules"]) == 1

    @pytest.mark.asyncio
    async def test_send_config_strips_inconsistent_rules_before_publish(self):
        """Integration: send_config strips bad offline_rules before MQTT publish."""
        device = SimpleNamespace(status="online", hardware_type="ESP32_WROOM")
        service, publisher, ws_broadcast = _build_service(device)
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        with (
            patch("src.services.esp_service.AuditLogRepository") as audit_repo_cls,
            patch(
                "src.websocket.manager.WebSocketManager.get_instance",
                new=AsyncMock(return_value=SimpleNamespace(broadcast=ws_broadcast)),
            ),
        ):
            audit_repo_cls.return_value.create = AsyncMock()
            result = await service.send_config("ESP_TEST01", config)

        assert result["success"] is True
        published_config = publisher.publish_config.call_args[1]["config"]
        assert published_config.get("offline_rules", []) == []

    @pytest.mark.asyncio
    async def test_trigger_config_push_debounced_appends_extra_sensor_entries(self) -> None:
        """extra_sensor_entries are appended to the combined config before the push.

        Regression: deleting a sensor from the DB must send a tombstone entry
        (active=False) so the ESP removes it from NVS via its active=False path.
        """
        device = SimpleNamespace(status="online", hardware_type="ESP32_WROOM")
        service, _publisher, _ = _build_service(device)

        tombstone = {
            "gpio": 5,
            "sensor_type": "flow",
            "sensor_name": "Flow GPIO 5",
            "active": False,
            "onewire_address": "",
            "i2c_address": 0,
        }
        base_config = {
            "sensors": [{"gpio": 4, "sensor_type": "ds18b20", "active": True}],
            "actuators": [],
            "offline_rules": [],
        }

        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_builder_instance = MagicMock()
        mock_builder_instance.build_combined_config = AsyncMock(return_value=base_config)

        mock_delegated = AsyncMock()
        mock_delegated.send_config_coalesced = AsyncMock(
            return_value={"success": True, "correlation_id": "corr-tombstone", "coalesced": False}
        )

        with (
            patch(
                "src.services.esp_service.get_session_maker",
                return_value=MagicMock(return_value=mock_cm),
            ),
            patch("src.services.esp_service.ESPRepository"),
            patch("src.services.esp_service.ESPService", return_value=mock_delegated),
            patch("src.services.config_builder.ConfigPayloadBuilder", return_value=mock_builder_instance),
            patch("src.db.repositories.SensorRepository"),
            patch("src.db.repositories.ActuatorRepository"),
        ):
            result = await service.trigger_config_push_debounced(
                "ESP_AEAE64",
                reason_code="sensor_config_change",
                extra_sensor_entries=[tombstone],
            )

        assert result["correlation_id"] == "corr-tombstone"

        mock_delegated.send_config_coalesced.assert_called_once()
        pushed_config = mock_delegated.send_config_coalesced.call_args.kwargs["config"]
        pushed_sensors = pushed_config["sensors"]

        assert any(s.get("gpio") == 4 for s in pushed_sensors), "base sensor must be present"
        tombstone_entries = [s for s in pushed_sensors if s.get("active") is False]
        assert len(tombstone_entries) == 1, "exactly one tombstone entry expected"
        assert tombstone_entries[0]["gpio"] == 5
        assert tombstone_entries[0]["sensor_type"] == "flow"

    @pytest.mark.asyncio
    async def test_send_config_audit_log_for_stripped_rules(self):
        """When rules are stripped, an additional audit log entry is written."""
        device = SimpleNamespace(status="online", hardware_type="ESP32_WROOM")
        service, _, ws_broadcast = _build_service(device)
        config = {
            "sensors": [{"gpio": 4}],
            "actuators": [],
            "offline_rules": [
                {"actuator_gpio": 18, "sensor_gpio": 4, "sensor_value_type": "ds18b20"},
            ],
        }

        with (
            patch("src.services.esp_service.AuditLogRepository") as audit_repo_cls,
            patch(
                "src.websocket.manager.WebSocketManager.get_instance",
                new=AsyncMock(return_value=SimpleNamespace(broadcast=ws_broadcast)),
            ),
        ):
            mock_create = AsyncMock()
            audit_repo_cls.return_value.create = mock_create
            await service.send_config("ESP_TEST01", config)

        audit_calls = mock_create.await_args_list
        event_types = [call.kwargs.get("event_type") for call in audit_calls]
        assert "config_offline_rules_stripped" in event_types
