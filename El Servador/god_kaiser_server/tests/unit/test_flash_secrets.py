"""
Unit Tests for Flash Secrets Service — AUT-766

All tests use tmp_path for filesystem isolation and mock subprocess for
nvs_partition_gen. No real hardware, no network, no credentials required.
Covers: read (404), write (correct CSV, 422 on missing field), build (422 no CSV, success).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.schemas.flash import NvsEnv, NvsSecretsCreate
from src.services.flash.secrets_service import (
    _CSV_HEADER,
    _NVS_NAMESPACE,
    _NVS_SIZE,
    _PASSWORD_MASK,
    build_nvs_binary,
    read_secrets,
    write_secrets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_secrets(**overrides) -> NvsSecretsCreate:
    defaults = dict(
        ssid="TestSSID",
        password="wifi-pass",
        server_address="192.168.0.2",
        mqtt_port=1883,
        mqtt_username="esp_user",
        mqtt_password="mqtt-pass",
        configured=1,
    )
    defaults.update(overrides)
    return NvsSecretsCreate(**defaults)


def _patch_secrets_dir(tmp_path: Path):
    """Patch get_secrets_dir() to return tmp_path."""
    return patch(
        "src.services.flash.secrets_service.get_secrets_dir",
        return_value=tmp_path,
    )


# =============================================================================
# NvsSecretsCreate — Pydantic validation (maps to 422 at API level)
# =============================================================================


class TestNvsSecretsCreateValidation:
    def test_valid_payload_accepted(self) -> None:
        s = _make_secrets()
        assert s.ssid == "TestSSID"
        assert s.configured == 1

    def test_missing_ssid_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            NvsSecretsCreate(
                password="p",
                server_address="host",
                mqtt_port=1883,
                mqtt_username="u",
                mqtt_password="p",
            )

    def test_missing_mqtt_password_defaults_to_none(self) -> None:
        # S0 (AUT-767): mqtt_password is now Optional — omit = keep existing
        s = NvsSecretsCreate(
            ssid="s",
            password="p",
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
        )
        assert s.mqtt_password is None

    def test_mqtt_port_out_of_range_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _make_secrets(mqtt_port=70000)

    def test_mqtt_port_zero_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _make_secrets(mqtt_port=0)

    def test_configured_defaults_to_1(self) -> None:
        s = NvsSecretsCreate(
            ssid="s",
            password="p",
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password="p",
        )
        assert s.configured == 1


# =============================================================================
# read_secrets — FileNotFoundError when CSV missing (maps to 404)
# =============================================================================


class TestReadSecrets:
    def test_raises_file_not_found_when_csv_missing(self, tmp_path: Path) -> None:
        with _patch_secrets_dir(tmp_path):
            with pytest.raises(FileNotFoundError):
                read_secrets("dev-local")

    def test_returns_masked_passwords(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)
            response = read_secrets("dev-local")

        assert response.password == _PASSWORD_MASK
        assert response.mqtt_password == _PASSWORD_MASK

    def test_returns_correct_non_sensitive_fields(self, tmp_path: Path) -> None:
        secrets = _make_secrets(ssid="MyNet", server_address="10.0.0.1", mqtt_port=8883)
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)
            response = read_secrets("dev-local")

        assert response.ssid == "MyNet"
        assert response.server_address == "10.0.0.1"
        assert response.mqtt_port == 8883
        assert response.mqtt_username == "esp_user"
        assert response.env == "dev-local"

    def test_returns_correct_configured_flag(self, tmp_path: Path) -> None:
        secrets = _make_secrets(configured=0)
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)
            response = read_secrets("dev-local")

        assert response.configured == 0


# =============================================================================
# write_secrets — correct CSV written, all required fields present
# =============================================================================


class TestWriteSecrets:
    def test_writes_csv_with_correct_header(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        lines = path.read_text().splitlines()
        assert lines[0] == ",".join(_CSV_HEADER)

    def test_writes_namespace_row(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        content = path.read_text()
        assert f"{_NVS_NAMESPACE},namespace,," in content

    def test_writes_all_required_keys(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        content = path.read_text()
        for key in ("ssid", "password", "server_address", "mqtt_port", "mqtt_username", "mqtt_password", "configured"):
            assert key in content, f"Key '{key}' missing from CSV"

    def test_writes_correct_ssid_value(self, tmp_path: Path) -> None:
        secrets = _make_secrets(ssid="GardenNet")
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        content = path.read_text()
        assert "ssid,data,string,GardenNet" in content

    def test_writes_correct_mqtt_port(self, tmp_path: Path) -> None:
        secrets = _make_secrets(mqtt_port=1884)
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        content = path.read_text()
        assert "mqtt_port,data,u16,1884" in content

    def test_creates_secrets_dir_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "secrets"
        with patch(
            "src.services.flash.secrets_service.get_secrets_dir",
            return_value=nested,
        ):
            write_secrets("pi-home", _make_secrets())

        assert nested.exists()

    def test_env_name_used_in_filename(self, tmp_path: Path) -> None:
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("pi-elbherb", _make_secrets())

        assert path.name == "nvs_secrets.pi-elbherb.csv"

    def test_overwrites_existing_csv(self, tmp_path: Path) -> None:
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", _make_secrets(ssid="First"))
            write_secrets("dev-local", _make_secrets(ssid="Second"))
            response = read_secrets("dev-local")

        assert response.ssid == "Second"


# =============================================================================
# build_nvs_binary — 422 when CSV missing; .bin created on success
# =============================================================================


class TestBuildNvsBinary:
    def test_raises_file_not_found_when_csv_missing(self, tmp_path: Path) -> None:
        with _patch_secrets_dir(tmp_path):
            with pytest.raises(FileNotFoundError):
                build_nvs_binary("dev-local")

    def test_calls_nvs_partition_gen_with_correct_args(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)
            csv_path = tmp_path / "nvs_secrets.dev-local.csv"
            bin_path = tmp_path / "nvs_secrets.dev-local.bin"

            mock_result = MagicMock()
            mock_result.returncode = 0
            bin_path.write_bytes(b"\x00" * 128)  # simulate generated binary

            with patch("src.services.flash.secrets_service.subprocess.run", return_value=mock_result) as mock_run:
                build_nvs_binary("dev-local")

        call_args = mock_run.call_args[0][0]
        assert "esp_idf_nvs_partition_gen.nvs_partition_gen" in call_args
        assert "generate" in call_args
        assert str(csv_path) in call_args
        assert str(bin_path) in call_args
        assert _NVS_SIZE in call_args

    def test_returns_binary_path_and_size(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        bin_data = b"\xAA" * 256
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)
            bin_path = tmp_path / "nvs_secrets.dev-local.bin"
            bin_path.write_bytes(bin_data)

            mock_result = MagicMock()
            mock_result.returncode = 0

            with patch("src.services.flash.secrets_service.subprocess.run", return_value=mock_result):
                response = build_nvs_binary("dev-local")

        assert response.success is True
        assert response.env == "dev-local"
        assert response.size_bytes == 256
        assert "nvs_secrets.dev-local.bin" in response.binary_path

    def test_raises_runtime_error_on_nonzero_returncode(self, tmp_path: Path) -> None:
        secrets = _make_secrets()
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", secrets)

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "partition gen error"
            mock_result.stdout = ""

            with patch("src.services.flash.secrets_service.subprocess.run", return_value=mock_result):
                with pytest.raises(RuntimeError, match="nvs_partition_gen failed"):
                    build_nvs_binary("dev-local")


# =============================================================================
# NvsSecretsCreate — optional password validation (S0 — AUT-767)
# =============================================================================


class TestNvsSecretsCreateOptionalPasswords:
    def test_password_none_accepted(self) -> None:
        s = NvsSecretsCreate(
            ssid="s",
            password=None,
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password="p",
        )
        assert s.password is None

    def test_mqtt_password_none_accepted(self) -> None:
        s = NvsSecretsCreate(
            ssid="s",
            password="p",
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password=None,
        )
        assert s.mqtt_password is None

    def test_both_passwords_none_accepted(self) -> None:
        s = NvsSecretsCreate(
            ssid="s",
            password=None,
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password=None,
        )
        assert s.password is None
        assert s.mqtt_password is None

    def test_empty_password_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="empty string"):
            NvsSecretsCreate(
                ssid="s",
                password="",
                server_address="host",
                mqtt_port=1883,
                mqtt_username="u",
                mqtt_password="p",
            )

    def test_empty_mqtt_password_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="empty string"):
            NvsSecretsCreate(
                ssid="s",
                password="p",
                server_address="host",
                mqtt_port=1883,
                mqtt_username="u",
                mqtt_password="",
            )


# =============================================================================
# write_secrets — partial update (S0 — AUT-767)
# =============================================================================


class TestWriteSecretsPartialUpdate:
    def test_keeps_existing_passwords_when_both_none(self, tmp_path: Path) -> None:
        initial = _make_secrets(password="initial-wifi", mqtt_password="initial-mqtt")
        update = NvsSecretsCreate(
            ssid="NewSSID",
            password=None,
            server_address="10.0.0.1",
            mqtt_port=1884,
            mqtt_username="new_user",
            mqtt_password=None,
        )
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", initial)
            write_secrets("dev-local", update)
            response = read_secrets("dev-local")

        # Passwords kept, other fields updated
        assert response.ssid == "NewSSID"
        assert response.mqtt_port == 1884
        assert response.password == _PASSWORD_MASK
        assert response.mqtt_password == _PASSWORD_MASK

        # Verify raw CSV has original passwords (not blank)
        content = (tmp_path / "nvs_secrets.dev-local.csv").read_text()
        assert "initial-wifi" in content
        assert "initial-mqtt" in content

    def test_keeps_only_wifi_password_when_mqtt_provided(self, tmp_path: Path) -> None:
        initial = _make_secrets(password="wifi-pass", mqtt_password="old-mqtt")
        update = NvsSecretsCreate(
            ssid="Net",
            password=None,
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password="new-mqtt",
        )
        with _patch_secrets_dir(tmp_path):
            write_secrets("dev-local", initial)
            write_secrets("dev-local", update)

        content = (tmp_path / "nvs_secrets.dev-local.csv").read_text()
        assert "wifi-pass" in content
        assert "new-mqtt" in content
        assert "old-mqtt" not in content

    def test_raises_value_error_when_no_csv_and_password_none(self, tmp_path: Path) -> None:
        secrets = NvsSecretsCreate(
            ssid="s",
            password=None,
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password="p",
        )
        with _patch_secrets_dir(tmp_path):
            with pytest.raises(ValueError, match="no CSV exists yet"):
                write_secrets("dev-local", secrets)

    def test_raises_value_error_when_no_csv_and_mqtt_password_none(self, tmp_path: Path) -> None:
        secrets = NvsSecretsCreate(
            ssid="s",
            password="p",
            server_address="host",
            mqtt_port=1883,
            mqtt_username="u",
            mqtt_password=None,
        )
        with _patch_secrets_dir(tmp_path):
            with pytest.raises(ValueError, match="no CSV exists yet"):
                write_secrets("dev-local", secrets)

    def test_full_update_without_none_always_succeeds(self, tmp_path: Path) -> None:
        secrets = _make_secrets(password="wifi-new", mqtt_password="mqtt-new")
        with _patch_secrets_dir(tmp_path):
            path = write_secrets("dev-local", secrets)

        content = path.read_text()
        assert "wifi-new" in content
        assert "mqtt-new" in content


# =============================================================================
# NvsEnv — valid enum values
# =============================================================================


class TestNvsEnv:
    def test_all_valid_envs_exist(self) -> None:
        assert NvsEnv("dev-local") == NvsEnv.dev_local
        assert NvsEnv("pi-home") == NvsEnv.pi_home
        assert NvsEnv("pi-elbherb") == NvsEnv.pi_elbherb

    def test_invalid_env_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            NvsEnv("staging")
