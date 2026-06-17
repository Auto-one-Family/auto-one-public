"""
Unit Tests: MQTT Authentication Service

Tests for MQTT authentication service with realistic scenarios.
These tests verify actual behavior, not just mocks.
"""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.repositories.esp_repo import ESPRepository
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.services.mqtt_auth_service import MQTTAuthService


class TestPasswordHashing:
    """Test password hashing functionality."""

    def test_hash_format_correct(self):
        """Test that password hash has correct Mosquitto format."""
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        password = "TestPassword123!@#"
        hashed = service.hash_mosquitto_password(password)

        # Verify format: $6$salt$hash
        assert hashed.startswith("$6$"), "Should start with $6$ (SHA-512)"
        parts = hashed.split("$")
        assert len(parts) == 4, f"Expected 4 parts, got {len(parts)}: {hashed}"
        assert parts[0] == "", "First part should be empty"
        assert parts[1] == "6", "Second part should be '6' (SHA-512)"
        assert len(parts[2]) == 32, "Salt should be 32 hex chars (16 bytes)"
        assert len(parts[3]) == 128, "Hash should be 128 hex chars (64 bytes SHA-512)"

    def test_hash_deterministic_salt(self):
        """Test that hashing produces different results (due to random salt)."""
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        password = "SamePassword123"
        hash1 = service.hash_mosquitto_password(password)
        hash2 = service.hash_mosquitto_password(password)

        # Hashes should be different due to random salt
        assert hash1 != hash2, "Hashes should differ due to random salt"

    def test_hash_length_consistent(self):
        """Test that all hashes have consistent length."""
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        passwords = ["Short1!", "VeryLongPassword123!@#$%^&*()", "NormalP@ss123"]
        hashes = [service.hash_mosquitto_password(pwd) for pwd in passwords]

        # All hashes should have same length (format is fixed)
        lengths = [len(h) for h in hashes]
        assert len(set(lengths)) == 1, f"All hashes should have same length, got: {lengths}"


class TestPasswdFileOperations:
    """Test password file operations."""

    def test_update_passwd_file_creates_file(self):
        """Test that passwd file is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            passwd_file = os.path.join(tmpdir, "passwd")

            service = MQTTAuthService(
                system_config_repo=MagicMock(),
                esp_repo=None,
            )
            service.passwd_file_path = passwd_file

            # Update file
            service._update_passwd_file("testuser", "$6$salt$hash")

            # Verify file exists
            assert os.path.exists(passwd_file), "Passwd file should be created"

            # Verify content
            with open(passwd_file, "r") as f:
                content = f.read()
                assert "testuser:$6$salt$hash" in content

    def test_update_passwd_file_updates_existing(self):
        """Test that existing entries are updated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            passwd_file = os.path.join(tmpdir, "passwd")

            # Create initial file
            with open(passwd_file, "w") as f:
                f.write("olduser:$6$oldsalt$oldhash\n")
                f.write("otheruser:$6$othersalt$otherhash\n")

            service = MQTTAuthService(
                system_config_repo=MagicMock(),
                esp_repo=None,
            )
            service.passwd_file_path = passwd_file

            # Update existing user
            service._update_passwd_file("olduser", "$6$newsalt$newhash")

            # Verify content
            with open(passwd_file, "r") as f:
                lines = f.readlines()
                assert len(lines) == 2, "Should have 2 entries"
                assert (
                    "olduser:$6$newsalt$newhash" in lines[0]
                    or "olduser:$6$newsalt$newhash" in lines[1]
                )
                assert (
                    "otheruser:$6$othersalt$otherhash" in lines[0]
                    or "otheruser:$6$othersalt$otherhash" in lines[1]
                )

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
    def test_update_passwd_file_sets_permissions(self):
        """Test that passwd file has correct permissions (600)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            passwd_file = os.path.join(tmpdir, "passwd")

            service = MQTTAuthService(
                system_config_repo=MagicMock(),
                esp_repo=None,
            )
            service.passwd_file_path = passwd_file

            service._update_passwd_file("testuser", "$6$salt$hash")

            # Verify permissions (600 = rw-------)
            stat_info = os.stat(passwd_file)
            mode = stat_info.st_mode & 0o777
            assert mode == 0o600, f"File should have 600 permissions, got {oct(mode)}"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not supported on Windows")
    def test_update_passwd_file_handles_permission_error(self):
        """Test that permission errors are raised correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            passwd_file = os.path.join(tmpdir, "passwd")

            # Create read-only directory (simulate permission issue)
            os.chmod(tmpdir, 0o555)  # Read and execute only

            service = MQTTAuthService(
                system_config_repo=MagicMock(),
                esp_repo=None,
            )
            service.passwd_file_path = passwd_file

            # Should raise PermissionError
            with pytest.raises(PermissionError):
                service._update_passwd_file("testuser", "$6$salt$hash")

            # Restore permissions for cleanup
            os.chmod(tmpdir, 0o755)


class TestMosquittoReload:
    """Test Mosquitto reload functionality."""

    def test_reload_tries_multiple_methods(self):
        """Test that reload tries multiple methods in order."""
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        # Mock all methods to fail except the last one
        with patch("subprocess.run") as mock_run:
            # First call (mosquitto_ctrl) - FileNotFoundError
            # Second call (pgrep) - FileNotFoundError
            # Third call (docker) - success
            mock_run.side_effect = [
                FileNotFoundError(),  # mosquitto_ctrl not found
                FileNotFoundError(),  # pgrep not found
                MagicMock(returncode=0),  # docker succeeds
            ]

            result = service.reload_mosquitto()
            assert result is True, "Should succeed with Docker method"
            assert mock_run.call_count == 3, "Should try all 3 methods"

    def test_reload_returns_false_if_all_fail(self):
        """Test that reload returns False if all methods fail."""
        service = MQTTAuthService(
            system_config_repo=MagicMock(),
            esp_repo=None,
        )

        with patch("subprocess.run") as mock_run:
            # All methods fail
            mock_run.side_effect = [
                FileNotFoundError(),  # mosquitto_ctrl
                FileNotFoundError(),  # pgrep
                FileNotFoundError(),  # docker
            ]

            result = service.reload_mosquitto()
            assert result is False, "Should return False if all methods fail"


class TestConfigureCredentials:
    """Test credential configuration."""

    @pytest.mark.asyncio
    async def test_configure_credentials_calls_all_steps(self, db_session):
        """Test that configure_credentials performs all required steps."""
        system_config_repo = SystemConfigRepository(db_session)
        service = MQTTAuthService(system_config_repo, None)

        # Track method calls
        update_file_called = False
        reload_called = False

        def mock_update_file(*args, **kwargs):
            nonlocal update_file_called
            update_file_called = True

        def mock_reload():
            nonlocal reload_called
            reload_called = True
            return True

        service._update_passwd_file = mock_update_file
        service.reload_mosquitto = mock_reload

        # Configure credentials
        result = await service.configure_credentials(
            username="testuser",
            password="TestP@ss123",
            enabled=True,
        )

        assert result is True
        assert update_file_called, "Should update passwd file"
        assert reload_called, "Should reload Mosquitto"

        # Verify DB persistence
        config = await system_config_repo.get_mqtt_auth_config()
        assert config["enabled"] is True
        assert config["username"] == "testuser"
        assert config["password_hash"] is not None

    @pytest.mark.asyncio
    async def test_configure_credentials_disables_auth(self, db_session):
        """Test that configure_credentials can disable authentication."""
        system_config_repo = SystemConfigRepository(db_session)
        service = MQTTAuthService(system_config_repo, None)

        # Mock file operations to avoid permission errors
        service._update_passwd_file = MagicMock()
        service.reload_mosquitto = MagicMock(return_value=True)

        # First enable
        await service.configure_credentials(
            username="testuser",
            password="TestP@ss123",
            enabled=True,
        )
        await db_session.commit()

        # Then disable
        result = await service.disable_authentication()
        assert result is True

        # Verify disabled in DB
        config = await system_config_repo.get_mqtt_auth_config()
        assert config["enabled"] is False


class TestBroadcastAuthUpdate:
    """Test auth update broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_requires_tls(self, db_session):
        """Test that broadcast fails without TLS."""
        system_config_repo = SystemConfigRepository(db_session)
        esp_repo = ESPRepository(db_session)
        service = MQTTAuthService(system_config_repo, esp_repo)

        # Mock settings to disable TLS
        with patch("src.services.mqtt_auth_service.settings") as mock_settings:
            mock_settings.mqtt.use_tls = False

            with pytest.raises(RuntimeError) as exc_info:
                await service.broadcast_auth_update(
                    username="testuser",
                    password="testpass",
                )

            assert "TLS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_broadcast_to_specific_esps(self, db_session):
        """Test broadcasting to specific ESP devices."""
        from src.db.models.esp import ESPDevice

        # Create test ESP devices
        esp1 = ESPDevice(
            device_id="ESP_001",
            name="ESP 1",
            status="online",
            hardware_type="ESP32_WROOM",
        )
        esp2 = ESPDevice(
            device_id="ESP_002",
            name="ESP 2",
            status="online",
            hardware_type="ESP32_WROOM",
        )
        db_session.add(esp1)
        db_session.add(esp2)
        await db_session.commit()

        system_config_repo = SystemConfigRepository(db_session)
        esp_repo = ESPRepository(db_session)
        service = MQTTAuthService(system_config_repo, esp_repo)

        # Mock publisher
        mock_publisher = MagicMock()
        mock_publisher._publish_with_retry = MagicMock(return_value=True)
        service.publisher = mock_publisher

        # Mock TLS enabled
        with patch("src.services.mqtt_auth_service.settings") as mock_settings:
            mock_settings.mqtt.use_tls = True

            count = await service.broadcast_auth_update(
                username="testuser",
                password="testpass",
                esp_ids=["ESP_001"],  # Only broadcast to ESP_001
            )

            assert count == 1
            assert mock_publisher._publish_with_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_all_esps(self, db_session):
        """Test broadcasting to all ESP devices."""
        from src.db.models.esp import ESPDevice

        # Create multiple ESP devices
        for i in range(3):
            esp = ESPDevice(
                device_id=f"ESP_{i:03d}",
                name=f"ESP {i}",
                status="online",
                hardware_type="ESP32_WROOM",
            )
            db_session.add(esp)
        await db_session.commit()

        system_config_repo = SystemConfigRepository(db_session)
        esp_repo = ESPRepository(db_session)
        service = MQTTAuthService(system_config_repo, esp_repo)

        # Mock publisher
        mock_publisher = MagicMock()
        mock_publisher._publish_with_retry = MagicMock(return_value=True)
        service.publisher = mock_publisher

        # Mock TLS enabled
        with patch("src.services.mqtt_auth_service.settings") as mock_settings:
            mock_settings.mqtt.use_tls = True

            count = await service.broadcast_auth_update(
                username="testuser",
                password="testpass",
                esp_ids=None,  # Broadcast to all
            )

            assert count == 3, "Should broadcast to all 3 ESPs"
            assert mock_publisher._publish_with_retry.call_count == 3
