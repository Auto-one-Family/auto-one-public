"""
System Configuration Repository

Provides database operations for system-wide configuration settings.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.system import SystemConfig

# ---------------------------------------------------------------------------
# Sheets-Export Cursor Constants (AUT-446 / S3)
# ---------------------------------------------------------------------------

SHEETS_CURSOR_SENSOR = "sheets_export_sensor_cursor"
SHEETS_CURSOR_HISTORY = "sheets_export_history_cursor"
SHEETS_CURSOR_LOGIC = "sheets_export_logic_cursor"

ALLOWED_SHEETS_CURSOR_NAMES: frozenset[str] = frozenset(
    {
        SHEETS_CURSOR_SENSOR,
        SHEETS_CURSOR_HISTORY,
        SHEETS_CURSOR_LOGIC,
    }
)


class SystemConfigRepository:
    """
    System Configuration Repository.

    Manages system-wide configuration stored in SystemConfig model.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository.

        Args:
            session: Async database session
        """
        self.session = session

    async def get_by_key(self, config_key: str) -> Optional[SystemConfig]:
        """
        Get configuration entry by key.

        Args:
            config_key: Configuration key (e.g., "mqtt_auth_enabled")

        Returns:
            SystemConfig entry or None if not found
        """
        stmt = select(SystemConfig).where(SystemConfig.config_key == config_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_config(
        self,
        config_key: str,
        config_value: any,
        config_type: str = "mqtt",
        description: Optional[str] = None,
        is_secret: bool = False,
    ) -> SystemConfig:
        """
        Set or update configuration entry.

        Args:
            config_key: Configuration key
            config_value: Configuration value (any JSON-serializable type)
            config_type: Configuration type (default: "mqtt")
            description: Human-readable description
            is_secret: Whether this contains sensitive data

        Returns:
            Created or updated SystemConfig entry
        """
        existing = await self.get_by_key(config_key)

        # SystemConfig.config_value is JSON field, can store any JSON-serializable value
        # For simple values, wrap in dict with "value" key for consistency
        if isinstance(config_value, dict):
            config_value_dict = config_value
        else:
            # Store simple values as-is (JSON field handles it)
            config_value_dict = config_value

        if existing:
            # Update existing entry
            existing.config_value = config_value_dict
            existing.config_type = config_type
            if description:
                existing.description = description
            existing.is_secret = is_secret
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        else:
            # Create new entry
            new_config = SystemConfig(
                config_key=config_key,
                config_value=config_value_dict,
                config_type=config_type,
                description=description,
                is_secret=is_secret,
            )
            self.session.add(new_config)
            await self.session.flush()
            await self.session.refresh(new_config)
            return new_config

    async def get_mqtt_auth_config(self) -> dict:
        """
        Get MQTT authentication configuration.

        Returns:
            Dict with keys: enabled, username, password_hash, last_configured
        """
        enabled_entry = await self.get_by_key("mqtt_auth_enabled")
        username_entry = await self.get_by_key("mqtt_auth_username")
        password_hash_entry = await self.get_by_key("mqtt_auth_password_hash")
        last_configured_entry = await self.get_by_key("mqtt_auth_last_configured")

        # Extract values from config_value (may be direct value or dict)
        def extract_value(entry):
            if not entry:
                return None
            val = entry.config_value
            # If it's a dict with "value" key, extract it
            if isinstance(val, dict) and "value" in val:
                return val["value"]
            return val

        enabled_val = extract_value(enabled_entry)
        username_val = extract_value(username_entry)
        password_hash_val = extract_value(password_hash_entry)
        last_configured_val = extract_value(last_configured_entry)

        # Parse last_configured datetime
        last_configured_dt = None
        if last_configured_val:
            if isinstance(last_configured_val, str):
                try:
                    last_configured_dt = datetime.fromisoformat(last_configured_val)
                except ValueError:
                    pass
            elif isinstance(last_configured_val, datetime):
                last_configured_dt = last_configured_val

        return {
            "enabled": bool(enabled_val) if enabled_val is not None else False,
            "username": username_val if username_val else None,
            "password_hash": password_hash_val if password_hash_val else None,
            "last_configured": last_configured_dt,
        }

    # =========================================================================
    # Sheets-Export Cursor Methods (AUT-446 / S3)
    # =========================================================================

    async def get_sheets_export_cursor(self, cursor_name: str) -> Optional[str]:
        """
        Get the current value of a Sheets-Export cursor.

        Cursors are persisted as ISO-8601 timestamp strings or integer IDs
        stored in the ``sheets_export`` config_type bucket.

        Args:
            cursor_name: One of ALLOWED_SHEETS_CURSOR_NAMES.

        Returns:
            The cursor value string, or None when no cursor has been persisted yet.
        """
        entry = await self.get_by_key(cursor_name)
        if entry is None:
            return None
        val = entry.config_value
        if isinstance(val, dict) and "value" in val:
            return str(val["value"]) if val["value"] is not None else None
        return str(val) if val is not None else None

    async def set_sheets_export_cursor(self, cursor_name: str, value: str) -> SystemConfig:
        """
        Atomically persist a Sheets-Export cursor value.

        Creates the entry on first use; updates it on subsequent calls.
        The value must be a non-empty string (ISO-8601 timestamp or integer ID).

        Args:
            cursor_name: One of ALLOWED_SHEETS_CURSOR_NAMES.
            value: New cursor value (non-empty string).

        Returns:
            The created or updated SystemConfig entry.
        """
        return await self.set_config(
            config_key=cursor_name,
            config_value=value,
            config_type="sheets_export",
            description=f"Sheets-Export cursor: last successfully exported row ({cursor_name})",
            is_secret=False,
        )

    async def reset_sheets_export_cursor(self, cursor_name: str) -> bool:
        """
        Delete a Sheets-Export cursor entry so the next export run starts from the beginning.

        Args:
            cursor_name: One of ALLOWED_SHEETS_CURSOR_NAMES.

        Returns:
            True if an entry existed and was deleted, False if it did not exist.
        """
        existing = await self.get_by_key(cursor_name)
        if existing is None:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True

    async def set_mqtt_auth_config(
        self,
        enabled: bool,
        username: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> None:
        """
        Set MQTT authentication configuration.

        Args:
            enabled: Whether MQTT auth is enabled
            username: MQTT username (if enabled)
            password_hash: SHA-512 password hash (if enabled)
        """
        # Store simple values directly (JSON field accepts any JSON-serializable type)
        await self.set_config(
            "mqtt_auth_enabled",
            enabled,
            config_type="mqtt",
            description="MQTT authentication enabled flag",
            is_secret=False,
        )

        if enabled and username:
            await self.set_config(
                "mqtt_auth_username",
                username,
                config_type="mqtt",
                description="MQTT authentication username",
                is_secret=False,
            )
        elif not enabled:
            # Clear username when disabled
            existing = await self.get_by_key("mqtt_auth_username")
            if existing:
                await self.session.delete(existing)

        if enabled and password_hash:
            await self.set_config(
                "mqtt_auth_password_hash",
                password_hash,
                config_type="mqtt",
                description="MQTT authentication password hash (SHA-512)",
                is_secret=True,
            )
        elif not enabled:
            # Clear password hash when disabled
            existing = await self.get_by_key("mqtt_auth_password_hash")
            if existing:
                await self.session.delete(existing)

        # Update last_configured timestamp
        await self.set_config(
            "mqtt_auth_last_configured",
            datetime.now(timezone.utc).isoformat(),
            config_type="mqtt",
            description="Last MQTT auth configuration timestamp",
            is_secret=False,
        )
