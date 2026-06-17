"""
MQTT Authentication Service

Manages MQTT broker authentication configuration for ESP32 devices.
Handles password hashing, Mosquitto passwd file updates, and credential broadcasting.
"""

import hashlib
import os
import signal
import subprocess
import time
from typing import List, Optional

from ..core.config import get_settings
from ..core.logging_config import get_logger
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.system_config_repo import SystemConfigRepository
from ..mqtt.publisher import Publisher
from ..mqtt.topics import TopicBuilder

logger = get_logger(__name__)
settings = get_settings()


class MQTTAuthService:
    """
    MQTT Authentication Service.

    Manages MQTT broker authentication for ESP32 devices:
    - Password hashing (Mosquitto SHA-512 format)
    - Passwd file management
    - Mosquitto reload
    - Credential broadcasting to ESPs
    """

    def __init__(
        self,
        system_config_repo: SystemConfigRepository,
        esp_repo: Optional[ESPRepository] = None,
    ):
        """
        Initialize MQTT Auth Service.

        Args:
            system_config_repo: SystemConfigRepository instance
            esp_repo: ESPRepository instance (optional, for broadcasting)
        """
        self.system_config_repo = system_config_repo
        self.esp_repo = esp_repo
        self.publisher = Publisher()
        self.passwd_file_path = settings.mqtt.passwd_file_path

    @staticmethod
    def hash_mosquitto_password(password: str) -> str:
        """
        Hash password in Mosquitto SHA-512 format.

        Mosquitto uses SHA-512 with salt: $6$salt$hash
        Format: username:$6$salt$hash

        Args:
            password: Plain text password

        Returns:
            Hashed password string in Mosquitto format
        """
        # Generate random salt (16 bytes = 32 hex chars)
        salt_bytes = os.urandom(16)
        salt_hex = salt_bytes.hex()

        # Hash password with SHA-512
        # Format: $6$salt$hash (6 = SHA-512)
        password_bytes = password.encode("utf-8")
        salt_bytes_for_hash = salt_hex.encode("utf-8")

        # SHA-512 hash: sha512(password + salt)
        hash_obj = hashlib.sha512()
        hash_obj.update(password_bytes)
        hash_obj.update(salt_bytes_for_hash)
        password_hash = hash_obj.hexdigest()

        # Mosquitto format: $6$salt$hash
        return f"$6${salt_hex}${password_hash}"

    async def configure_credentials(
        self,
        username: str,
        password: str,
        enabled: bool = True,
    ) -> bool:
        """
        Configure MQTT authentication credentials.

        Steps:
        1. Hash password for Mosquitto
        2. Update password file
        3. Reload Mosquitto broker
        4. Persist configuration to database

        Args:
            username: MQTT username
            password: Plain text password
            enabled: Whether to enable authentication

        Returns:
            True if configuration successful

        Raises:
            ValueError: If password file cannot be written
            RuntimeError: If Mosquitto reload fails
        """
        if not enabled:
            # Disable authentication
            return await self.disable_authentication()

        # Hash password
        password_hash = self.hash_mosquitto_password(password)

        # Update password file
        try:
            self._update_passwd_file(username, password_hash)
        except Exception as e:
            logger.error(f"Failed to update passwd file: {e}", exc_info=True)
            raise ValueError(f"Cannot update password file: {e}")

        # Reload Mosquitto
        reload_success = self.reload_mosquitto()
        if not reload_success:
            logger.warning("Mosquitto reload failed, but continuing...")
            # Don't fail completely - config might still work

        # Persist to database
        await self.system_config_repo.set_mqtt_auth_config(
            enabled=True,
            username=username,
            password_hash=password_hash,
        )

        logger.info(f"MQTT authentication configured: username={username}, enabled=True")
        return True

    def _update_passwd_file(self, username: str, password_hash: str) -> None:
        """
        Update Mosquitto password file.

        Args:
            username: MQTT username
            password_hash: Hashed password (Mosquitto format)

        Raises:
            PermissionError: If file cannot be written
            FileNotFoundError: If directory doesn't exist
        """
        # Format: username:$6$salt$hash
        entry = f"{username}:{password_hash}\n"

        # Read existing file (if exists)
        existing_entries = {}
        if os.path.exists(self.passwd_file_path):
            try:
                with open(self.passwd_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and ":" in line:
                            user, _ = line.split(":", 1)
                            existing_entries[user] = line
            except Exception as e:
                logger.warning(f"Could not read existing passwd file: {e}")

        # Update or add entry
        existing_entries[username] = entry.strip()

        # Write file
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.passwd_file_path), exist_ok=True)

            with open(self.passwd_file_path, "w", encoding="utf-8") as f:
                for user_entry in existing_entries.values():
                    f.write(f"{user_entry}\n")

            # Set file permissions to 600 (read/write for owner only)
            os.chmod(self.passwd_file_path, 0o600)

            logger.info(f"Updated passwd file: {self.passwd_file_path}")
        except PermissionError:
            logger.error(f"Permission denied: Cannot write to {self.passwd_file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to write passwd file: {e}", exc_info=True)
            raise

    def reload_mosquitto(self) -> bool:
        """
        Reload Mosquitto broker configuration.

        Tries multiple methods in order:
        1. mosquitto_ctrl reload (if available)
        2. SIGHUP signal to Mosquitto process
        3. Docker exec (if running in Docker)

        Returns:
            True if reload successful, False otherwise
        """
        # Method 1: Try mosquitto_ctrl
        try:
            result = subprocess.run(
                ["mosquitto_ctrl", "reload"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("Mosquitto reloaded via mosquitto_ctrl")
                return True
        except FileNotFoundError:
            logger.debug("mosquitto_ctrl not found, trying SIGHUP...")
        except Exception as e:
            logger.debug(f"mosquitto_ctrl failed: {e}")

        # Method 2: Try SIGHUP signal
        try:
            # Find Mosquitto process
            result = subprocess.run(
                ["pgrep", "-f", "mosquitto"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        os.kill(pid, signal.SIGHUP)
                        logger.info(f"Sent SIGHUP to Mosquitto process {pid}")
                        time.sleep(0.5)  # Give it time to reload
                        return True
                    except (ValueError, ProcessLookupError, PermissionError):
                        continue
        except FileNotFoundError:
            logger.debug("pgrep not found, trying Docker...")
        except Exception as e:
            logger.debug(f"SIGHUP method failed: {e}")

        # Method 3: Try Docker exec
        try:
            result = subprocess.run(
                ["docker", "exec", "mosquitto", "kill", "-HUP", "1"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("Mosquitto reloaded via Docker")
                return True
        except FileNotFoundError:
            logger.debug("Docker not found")
        except Exception as e:
            logger.debug(f"Docker method failed: {e}")

        logger.warning("All Mosquitto reload methods failed")
        return False

    async def get_current_config(self) -> dict:
        """
        Get current MQTT authentication configuration.

        Returns:
            Dict with keys: enabled, username, password_hash, last_configured
        """
        return await self.system_config_repo.get_mqtt_auth_config()

    async def disable_authentication(self) -> bool:
        """
        Disable MQTT authentication (allow anonymous).

        This removes the password requirement but does not delete the passwd file.
        Mosquitto must be configured to allow anonymous access.

        Returns:
            True if disabled successfully
        """
        await self.system_config_repo.set_mqtt_auth_config(
            enabled=False,
            username=None,
            password_hash=None,
        )

        logger.info("MQTT authentication disabled")
        return True

    async def broadcast_auth_update(
        self,
        username: str,
        password: str,
        esp_ids: Optional[List[str]] = None,
        action: str = "update",
    ) -> int:
        """
        Broadcast MQTT authentication update to ESP32 devices.

        Sends credentials to ESPs via MQTT topic:
        kaiser/{kaiser_id}/esp/{esp_id}/mqtt/auth_update

        **SECURITY:** Only broadcasts if TLS is enabled!

        Args:
            username: MQTT username
            password: Plain text password (sent over TLS)
            esp_ids: List of ESP IDs to send to (None = all ESPs)
            action: Action type ("update" or "revoke")

        Returns:
            Number of ESPs that received the update

        Raises:
            RuntimeError: If TLS is not enabled
        """
        # Security check: Only send over TLS
        if not settings.mqtt.use_tls:
            logger.warning(
                "MQTT auth_update broadcast refused: TLS not enabled. "
                "Credentials cannot be sent securely without TLS."
            )
            raise RuntimeError(
                "Cannot broadcast MQTT credentials: TLS is not enabled. "
                "Enable MQTT_USE_TLS in settings before configuring authentication."
            )

        # Get ESP IDs if not provided
        if esp_ids is None:
            if self.esp_repo is None:
                logger.warning("ESP repository not available, cannot broadcast to all ESPs")
                return 0

            # Get all active ESP devices
            esp_devices = await self.esp_repo.get_all()
            esp_ids = [esp.device_id for esp in esp_devices]

        if not esp_ids:
            logger.warning("No ESP devices found for auth_update broadcast")
            return 0

        # Build payload
        payload = {
            "ts": int(time.time()),
            "username": username,
            "password": password,  # Plain text - sent over TLS
            "action": action,
            "force_reconnect": True,
        }

        # Broadcast to each ESP
        success_count = 0
        for esp_id in esp_ids:
            try:
                topic = TopicBuilder.build_mqtt_auth_update_topic(esp_id)
                success = self.publisher._publish_with_retry(
                    topic,
                    payload,
                    qos=2,  # QoS 2 for critical config
                    retry=True,
                )
                if success:
                    success_count += 1
                    logger.info(f"Auth update sent to {esp_id}")
                else:
                    logger.warning(f"Failed to send auth update to {esp_id}")
            except Exception as e:
                logger.error(f"Error sending auth update to {esp_id}: {e}", exc_info=True)

        logger.info(f"Auth update broadcast complete: {success_count}/{len(esp_ids)} ESPs")
        return success_count
