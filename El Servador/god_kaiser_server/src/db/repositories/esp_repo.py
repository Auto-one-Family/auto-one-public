"""
ESP Repository: Device Queries and Updates

Extended with Mock-ESP CRUD operations for Database as Single Source of Truth.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.esp import ESPDevice
from ..models.zone import Zone
from .base_repo import BaseRepository


class ESPRepository(BaseRepository[ESPDevice]):
    """
    ESP Repository with device-specific queries.

    Extends BaseRepository with ESP32-specific operations like
    device_id lookups, zone queries, and status management.

    Soft-Delete (T02-Fix1):
    - All listing methods exclude soft-deleted devices by default.
    - Use include_deleted=True for audit queries.
    - get_by_device_id always finds devices (including deleted) for internal lookups.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ESPDevice, session)

    @staticmethod
    def _not_deleted():
        """Filter clause to exclude soft-deleted devices."""
        return ESPDevice.deleted_at.is_(None)

    async def get_by_device_id(
        self, device_id: str, include_deleted: bool = False
    ) -> Optional[ESPDevice]:
        """
        Get ESP device by device_id.

        Args:
            device_id: ESP device ID (e.g., ESP_A1B2C3D4)
            include_deleted: If True, also return soft-deleted devices

        Returns:
            ESPDevice or None if not found
        """
        stmt = select(ESPDevice).where(ESPDevice.device_id == device_id)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self, skip: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> list[ESPDevice]:
        """Get all devices with optional soft-delete filter."""
        stmt = select(self.model)
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_with_components(
        self, *, include_deleted: bool = False
    ) -> list[ESPDevice]:
        """Return all devices with sensors + actuators eager-loaded.

        AUT-224 A2: replaces an inline ``select(ESPDevice).options(selectinload(...))``
        in ``api/v1/component_export.py``. Eager-loading prevents
        ``MissingGreenlet`` errors when the API serializes relationships.
        """
        from sqlalchemy.orm import selectinload  # local import: keep module surface small

        stmt = select(self.model).options(
            selectinload(self.model.sensors),
            selectinload(self.model.actuators),
        )
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, device_id: str, deleted_by: str) -> Optional[ESPDevice]:
        """
        Soft-delete a device by setting deleted_at timestamp.

        Args:
            device_id: ESP device ID
            deleted_by: Username performing the deletion

        Returns:
            Updated ESPDevice or None if not found
        """
        device = await self.get_by_device_id(device_id, include_deleted=False)
        if not device:
            return None

        device.deleted_at = datetime.now(timezone.utc)
        device.deleted_by = deleted_by
        device.status = "deleted"

        await self.session.flush()
        await self.session.refresh(device)
        return device

    async def get_by_zone(self, zone_id: str) -> list[ESPDevice]:
        """
        Get all active ESP devices in a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            List of ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.zone_id == zone_id, self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_master_zone(self, master_zone_id: str) -> list[ESPDevice]:
        """
        Get all active ESP devices in a master zone hierarchy.

        Args:
            master_zone_id: Master zone identifier

        Returns:
            List of ESPDevice instances
        """
        stmt = select(ESPDevice).where(
            ESPDevice.master_zone_id == master_zone_id, self._not_deleted()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_kaiser(self, kaiser_id: str) -> list[ESPDevice]:
        """
        Get all active ESP devices assigned to a Kaiser node.

        WP2-Fix5a: DB-Query via indexed kaiser_id column instead of metadata filter.

        Args:
            kaiser_id: Kaiser node identifier

        Returns:
            List of ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.kaiser_id == kaiser_id, self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_zone_masters(self, zone_id: Optional[str] = None) -> list[ESPDevice]:
        """
        Get active zone master devices.

        Args:
            zone_id: Optional zone ID filter

        Returns:
            List of zone master ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.is_zone_master == True, self._not_deleted())
        if zone_id:
            stmt = stmt.where(ESPDevice.zone_id == zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_online(self) -> list[ESPDevice]:
        """
        Get all online ESP devices.

        Returns:
            List of online ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.status == "online", self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: str) -> list[ESPDevice]:
        """
        Get ESP devices by status.

        Args:
            status: Device status (online, offline, error, unknown)

        Returns:
            List of ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.status == status, self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_hardware_type(self, hardware_type: str) -> list[ESPDevice]:
        """
        Get active ESP devices by hardware type.

        Args:
            hardware_type: Hardware type (ESP32_WROOM, XIAO_ESP32_C3)

        Returns:
            List of ESPDevice instances
        """
        stmt = select(ESPDevice).where(
            ESPDevice.hardware_type == hardware_type, self._not_deleted()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_last_seen(self, device_id: str, timestamp: datetime) -> None:
        """
        Update only last_seen without changing device status.

        Used by sensor_handler as secondary health indicator.
        Unlike update_status(), this does NOT modify the status field.
        """
        device = await self.get_by_device_id(device_id)
        if device:
            device.last_seen = timestamp
            await self.session.flush()

    async def update_status(
        self, device_id: str, status: str, last_seen: Optional[datetime] = None
    ) -> Optional[ESPDevice]:
        """
        Update device status and last_seen timestamp.

        Args:
            device_id: ESP device ID
            status: New status (online, offline, error, unknown)
            last_seen: Optional explicit last_seen timestamp.
                - If provided, it is always stored.
                - If omitted and status != "offline", defaults to now.
                - If omitted and status == "offline", the previous heartbeat
                  timestamp is preserved.

        Returns:
            Updated ESPDevice or None if not found
        """
        device = await self.get_by_device_id(device_id)
        if device is None:
            return None

        device.status = status
        if last_seen is not None:
            device.last_seen = last_seen
        elif status != "offline":
            device.last_seen = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(device)
        return device

    async def update_capabilities(self, device_id: str, capabilities: dict) -> Optional[ESPDevice]:
        """
        Update device capabilities.

        Args:
            device_id: ESP device ID
            capabilities: New capabilities dict

        Returns:
            Updated ESPDevice or None if not found
        """
        device = await self.get_by_device_id(device_id)
        if device is None:
            return None

        device.capabilities = capabilities

        await self.session.flush()
        await self.session.refresh(device)
        return device

    async def assign_zone(
        self, device_id: str, zone_id: str, zone_name: str, is_zone_master: bool = False
    ) -> Optional[ESPDevice]:
        """
        Assign device to a zone.

        Args:
            device_id: ESP device ID
            zone_id: Zone identifier
            zone_name: Human-readable zone name
            is_zone_master: Whether device is zone master

        Returns:
            Updated ESPDevice or None if not found
        """
        device = await self.get_by_device_id(device_id)
        if device is None:
            return None

        device.zone_id = zone_id
        device.zone_name = zone_name
        device.is_zone_master = is_zone_master

        await self.session.flush()
        await self.session.refresh(device)
        return device

    # =========================================================================
    # Mock ESP Methods (for Scheduler Integration)
    # =========================================================================

    async def get_mock_devices(self) -> list[ESPDevice]:
        """
        Get all active Mock-ESP devices.

        Returns:
            List of Mock ESPDevice instances
        """
        stmt = select(ESPDevice).where(ESPDevice.hardware_type == "MOCK_ESP32", self._not_deleted())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_online_mock_devices(self) -> list[ESPDevice]:
        """
        Get all online Mock-ESP devices.

        Used for simulation recovery after server restart.

        Returns:
            List of online Mock ESPDevice instances
        """
        stmt = select(ESPDevice).where(
            ESPDevice.hardware_type == "MOCK_ESP32",
            ESPDevice.status == "online",
            self._not_deleted(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_running_mock_devices(self) -> List[ESPDevice]:
        """
        Get all Mock-ESP devices with simulation_state == 'running'.

        Used for simulation recovery after server restart.
        Checks device_metadata["simulation_state"] for running simulations.

        Returns:
            List of Mock ESPDevice instances with active simulations
        """
        all_mocks = await self.get_mock_devices()
        return [
            device
            for device in all_mocks
            if device.device_metadata
            and device.device_metadata.get("simulation_state") == "running"
        ]

    async def update_simulation_state(self, device_id: str, state: str) -> Optional[ESPDevice]:
        """
        Update simulation state in device metadata.

        Stores simulation state for tracking which Mock-ESPs have
        active simulations running in the CentralScheduler.

        Args:
            device_id: ESP device ID
            state: Simulation state ("running", "stopped", "paused")

        Returns:
            Updated ESPDevice or None if not found

        Example:
            await repo.update_simulation_state("ESP_TEST001", "running")
        """
        device = await self.get_by_device_id(device_id)
        if not device:
            return None

        # Initialize metadata if needed
        if not device.device_metadata:
            device.device_metadata = {}

        # Update simulation state
        device.device_metadata["simulation_state"] = state
        device.device_metadata["simulation_updated_at"] = datetime.now(timezone.utc).isoformat()

        # Mark as modified for SQLAlchemy to track changes
        flag_modified(device, "device_metadata")

        await self.session.flush()
        await self.session.refresh(device)
        return device

    async def update_simulation_config(self, device_id: str, config: dict) -> Optional[ESPDevice]:
        """
        Update simulation configuration in device metadata.

        Stores configuration for Mock-ESP simulations (sensors, actuators,
        intervals, patterns).

        Args:
            device_id: ESP device ID
            config: Simulation config dict with keys:
                    - sensors: Dict[gpio, sensor_config]
                    - actuators: Dict[gpio, actuator_config]
                    - heartbeat_interval: int

        Returns:
            Updated ESPDevice or None if not found

        Example:
            config = {
                "sensors": {
                    "34": {"sensor_type": "temperature", "base_value": 22.0},
                },
                "actuators": {},
                "heartbeat_interval": 60
            }
            await repo.update_simulation_config("ESP_TEST001", config)
        """
        device = await self.get_by_device_id(device_id)
        if not device:
            return None

        # Initialize metadata if needed
        if not device.device_metadata:
            device.device_metadata = {}

        # Update simulation config
        device.device_metadata["simulation_config"] = config
        device.device_metadata["simulation_config_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        # Mark as modified for SQLAlchemy to track changes
        flag_modified(device, "device_metadata")

        await self.session.flush()
        await self.session.refresh(device)
        return device

    # =========================================================================
    # Mock-ESP CRUD (Database as Single Source of Truth)
    # =========================================================================

    async def create_mock_device(
        self,
        device_id: str,
        kaiser_id: str = "god",
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        master_zone_id: Optional[str] = None,
        heartbeat_interval: float = 60.0,
        simulation_config: Optional[Dict[str, Any]] = None,
        auto_start: bool = False,
    ) -> ESPDevice:
        """
        Create new Mock-ESP in Database (Single Source of Truth).

        Args:
            device_id: Unique ESP-ID (e.g., "ESP_MOCK_001")
            kaiser_id: Kaiser-ID (default: "god")
            zone_id: Optional Zone-ID (auto-generated from zone_name if not provided)
            zone_name: Optional human-readable zone name
            master_zone_id: Optional master zone ID
            heartbeat_interval: Heartbeat interval in seconds
            simulation_config: JSON with sensor/actuator configuration
            auto_start: Whether to start simulation immediately

        Returns:
            Created ESPDevice

        Raises:
            ValueError: If device_id already exists
        """
        # Check if device already exists
        existing = await self.get_by_device_id(device_id)
        if existing:
            raise ValueError(f"Device {device_id} already exists")

        # Auto-generate zone_id from zone_name if needed
        if zone_name and not zone_id:
            zone_id = zone_name.lower()
            zone_id = (
                zone_id.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            )
            zone_id = re.sub(r"[^a-z0-9]+", "_", zone_id).strip("_")

        # Ensure zone exists in the zones table (FK constraint: esp_devices.zone_id → zones.zone_id)
        # Auto-create the zone if it doesn't exist yet (get-or-create pattern for mock ESPs).
        if zone_id:
            existing_zone_stmt = select(Zone).where(Zone.zone_id == zone_id)
            existing_zone_result = await self.session.execute(existing_zone_stmt)
            existing_zone = existing_zone_result.scalar_one_or_none()
            if not existing_zone:
                display_name = zone_name or zone_id
                new_zone = Zone(
                    zone_id=zone_id,
                    name=display_name,
                    description="Auto-created for mock ESP",
                )
                self.session.add(new_zone)
                await self.session.flush()

        # Generate unique MAC address from device_id
        esp_suffix = device_id.replace("ESP_MOCK_", "").replace("ESP_", "").upper()
        esp_suffix = esp_suffix.zfill(6)[-6:]
        mock_mac = f"MO:CK:{esp_suffix[0:2]}:{esp_suffix[2:4]}:{esp_suffix[4:6]}:00"

        # Build device name (kurz und menschenverständlich)
        # Nur letzte 4 Zeichen der ID für Unterscheidung, da zone_name separat angezeigt wird
        short_id = device_id[-4:].upper()  # z.B. "A733" aus "MOCK_067EA733"
        db_name = f"Mock #{short_id}"

        # Build simulation config
        sim_config = simulation_config or {"sensors": {}, "actuators": {}}

        # Build device metadata
        device_metadata = {
            "mock": True,
            "simulation_state": "running" if auto_start else "stopped",
            "simulation_config": sim_config,
            "heartbeat_interval": heartbeat_interval,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Create device
        device = ESPDevice(
            device_id=device_id,
            name=db_name,
            hardware_type="MOCK_ESP32",
            kaiser_id=kaiser_id,
            zone_id=zone_id,
            zone_name=zone_name,
            master_zone_id=master_zone_id,
            status="online" if auto_start else "offline",
            ip_address="127.0.0.1",
            mac_address=mock_mac,
            firmware_version="MOCK_1.0.0",
            capabilities={"max_sensors": 20, "max_actuators": 12, "mock": True},
            device_metadata=device_metadata,
        )

        self.session.add(device)
        await self.session.flush()
        await self.session.refresh(device)

        return device

    async def get_mock_device(self, device_id: str) -> Optional[ESPDevice]:
        """
        Get active Mock-ESP from Database.

        Returns:
            ESPDevice or None if not found, not a mock, or soft-deleted
        """
        stmt = select(ESPDevice).where(
            ESPDevice.device_id == device_id,
            ESPDevice.hardware_type == "MOCK_ESP32",
            self._not_deleted(),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_mock_devices(self) -> List[ESPDevice]:
        """
        Get all active Mock-ESPs sorted by creation date (newest first).

        Returns:
            List of Mock ESPDevice instances
        """
        stmt = (
            select(ESPDevice)
            .where(ESPDevice.hardware_type == "MOCK_ESP32", self._not_deleted())
            .order_by(ESPDevice.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_sensor_to_mock(
        self, device_id: str, gpio: int, sensor_config: Dict[str, Any]
    ) -> bool:
        """
        Add sensor to simulation_config.

        MULTI-VALUE SUPPORT: Key is now "{gpio}_{sensor_type}" to allow
        multiple sensor types on the same GPIO (e.g., SHT31: temp + humidity).

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin
            sensor_config: {"sensor_type": "DS18B20", "base_value": 22.0, ...}

        Returns:
            True if successfully added
        """
        device = await self.get_mock_device(device_id)
        if not device:
            return False

        # Initialize metadata if needed
        if not device.device_metadata:
            device.device_metadata = {}

        # Get or create simulation_config
        sim_config = device.device_metadata.get(
            "simulation_config", {"sensors": {}, "actuators": {}}
        )
        if "sensors" not in sim_config:
            sim_config["sensors"] = {}

        # MULTI-VALUE FIX: Use "{gpio}_{sensor_type}" as key to support
        # multiple sensor types on same GPIO (e.g., SHT31 temp + humidity)
        sensor_type = sensor_config.get("sensor_type", "GENERIC")
        sensor_key = f"{gpio}_{sensor_type}"

        # Store gpio in config for backwards compatibility
        sensor_config["gpio"] = gpio

        sim_config["sensors"][sensor_key] = sensor_config
        device.device_metadata["simulation_config"] = sim_config
        device.device_metadata["simulation_config_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        flag_modified(device, "device_metadata")
        await self.session.flush()
        return True

    async def remove_sensor_from_mock(
        self, device_id: str, gpio: int, sensor_type: Optional[str] = None
    ) -> bool:
        """
        Remove sensor from simulation_config.

        MULTI-VALUE SUPPORT: If sensor_type is provided, removes only that
        specific sensor. If not provided, removes ALL sensors on that GPIO
        (backwards compatible behavior).

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin
            sensor_type: Optional sensor type (e.g., "sht31_temp")

        Returns:
            True if successfully removed
        """
        device = await self.get_mock_device(device_id)
        if not device or not device.device_metadata:
            return False

        sim_config = device.device_metadata.get("simulation_config", {})
        sensors = sim_config.get("sensors", {})

        removed = False

        if sensor_type:
            # MULTI-VALUE: Remove specific sensor_type on GPIO
            sensor_key = f"{gpio}_{sensor_type}"
            if sensor_key in sensors:
                del sensors[sensor_key]
                removed = True
        else:
            # BACKWARDS COMPAT: Remove all sensors on this GPIO
            # Check both old format (gpio only) and new format (gpio_type)
            keys_to_remove = [k for k in sensors if k == str(gpio) or k.startswith(f"{gpio}_")]
            for key in keys_to_remove:
                del sensors[key]
                removed = True

        if removed:
            device.device_metadata["simulation_config"]["sensors"] = sensors
            device.device_metadata["simulation_config_updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            flag_modified(device, "device_metadata")
            await self.session.flush()

        return removed

    async def add_actuator_to_mock(
        self, device_id: str, gpio: int, actuator_config: Dict[str, Any]
    ) -> bool:
        """
        Add actuator to simulation_config.

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin
            actuator_config: {"actuator_type": "relay", "initial_state": False, ...}

        Returns:
            True if successfully added
        """
        device = await self.get_mock_device(device_id)
        if not device:
            return False

        # Initialize metadata if needed
        if not device.device_metadata:
            device.device_metadata = {}

        # Get or create simulation_config
        sim_config = device.device_metadata.get(
            "simulation_config", {"sensors": {}, "actuators": {}}
        )
        if "actuators" not in sim_config:
            sim_config["actuators"] = {}

        # Add actuator
        sim_config["actuators"][str(gpio)] = actuator_config
        device.device_metadata["simulation_config"] = sim_config
        device.device_metadata["simulation_config_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        flag_modified(device, "device_metadata")
        await self.session.flush()
        return True

    async def remove_actuator_from_mock(self, device_id: str, gpio: int) -> bool:
        """
        Remove actuator from simulation_config.

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin

        Returns:
            True if successfully removed
        """
        device = await self.get_mock_device(device_id)
        if not device or not device.device_metadata:
            return False

        sim_config = device.device_metadata.get("simulation_config", {})
        actuators = sim_config.get("actuators", {})

        if str(gpio) in actuators:
            del actuators[str(gpio)]
            device.device_metadata["simulation_config"]["actuators"] = actuators
            device.device_metadata["simulation_config_updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            flag_modified(device, "device_metadata")
            await self.session.flush()
            return True

        return False

    async def set_manual_sensor_override(self, device_id: str, gpio: int, value: float) -> bool:
        """
        Set manual override value for sensor.

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin
            value: Override value

        Returns:
            True if successfully set
        """
        device = await self.get_mock_device(device_id)
        if not device or not device.device_metadata:
            return False

        sim_config = device.device_metadata.get("simulation_config", {})
        # Keys are now "cfg_{uuid}" format. Match by entry's gpio field,
        # with backward compat for legacy "{gpio}" and "{gpio}_{type}" keys.
        sensors = sim_config.get("sensors", {})
        sensor_exists = any(
            k == str(gpio)
            or k.startswith(f"{gpio}_")
            or (isinstance(v, dict) and v.get("gpio") == gpio)
            for k, v in sensors.items()
        )
        if not sensor_exists:
            return False

        # Add manual override
        if "manual_overrides" not in sim_config:
            sim_config["manual_overrides"] = {}
        sim_config["manual_overrides"][str(gpio)] = value

        device.device_metadata["simulation_config"] = sim_config
        flag_modified(device, "device_metadata")
        await self.session.flush()
        return True

    async def clear_manual_sensor_override(self, device_id: str, gpio: int) -> bool:
        """
        Clear manual override value for sensor.

        Args:
            device_id: ESP Device ID
            gpio: GPIO Pin

        Returns:
            True if successfully cleared
        """
        device = await self.get_mock_device(device_id)
        if not device or not device.device_metadata:
            return False

        sim_config = device.device_metadata.get("simulation_config", {})
        manual_overrides = sim_config.get("manual_overrides", {})

        if str(gpio) in manual_overrides:
            del manual_overrides[str(gpio)]
            device.device_metadata["simulation_config"]["manual_overrides"] = manual_overrides
            flag_modified(device, "device_metadata")
            await self.session.flush()
            return True

        return False

    async def delete_mock_device(self, device_id: str, deleted_by: str = "system") -> bool:
        """
        Soft-delete Mock-ESP from Database.

        SAFETY: Only soft-deletes if hardware_type='MOCK_ESP32'

        Args:
            device_id: ESP Device ID
            deleted_by: Username performing the deletion

        Returns:
            True if successfully soft-deleted
        """
        device = await self.get_mock_device(device_id)
        if not device:
            return False

        # Cleanup: Delete sensor_configs and actuator_configs for this device.
        # sensor_data has no FK to sensor_configs (only to esp_devices with SET NULL),
        # so historical sensor data is preserved.
        from ..models.sensor import SensorConfig
        from ..models.actuator import ActuatorConfig

        await self.session.execute(delete(SensorConfig).where(SensorConfig.esp_id == device.id))
        await self.session.execute(delete(ActuatorConfig).where(ActuatorConfig.esp_id == device.id))

        device.deleted_at = datetime.now(timezone.utc)
        device.deleted_by = deleted_by
        device.status = "deleted"

        await self.session.flush()
        return True

    async def get_mock_count(self) -> int:
        """
        Get count of all active Mock-ESPs.

        Returns:
            Number of active Mock-ESPs in database
        """
        stmt = (
            select(func.count())
            .select_from(ESPDevice)
            .where(ESPDevice.hardware_type == "MOCK_ESP32", self._not_deleted())
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    def get_simulation_config(self, device: ESPDevice) -> Dict[str, Any]:
        """
        Extract simulation config from device metadata.

        Helper method for retrieving simulation configuration.

        Args:
            device: ESPDevice instance

        Returns:
            Simulation config dict or empty default
        """
        if not device.device_metadata:
            return {"sensors": {}, "actuators": {}}
        return device.device_metadata.get("simulation_config", {"sensors": {}, "actuators": {}})

    async def rebuild_simulation_config(
        self,
        device: ESPDevice,
        sensor_configs: list,
    ) -> Dict[str, Any]:
        """
        Rebuild simulation_config.sensors from sensor_configs DB (Write-Through Cache).

        This is the ONLY place where simulation_config.sensors is written.
        Called after every CUD operation on sensor_configs for this device.

        Keys use cfg_{id} format to prevent collisions when multiple sensors
        share the same GPIO (e.g., 2x DS18B20 on GPIO 4, or SHT31 temp+humidity).

        Simulation-specific params (base_value, variation_pattern, etc.) are
        preserved from old entries via (gpio, sensor_type) reverse lookup,
        or from sensor_metadata.simulation if available.

        Args:
            device: ESPDevice instance (must be attached to session)
            sensor_configs: List of SensorConfig instances for this device

        Returns:
            Updated simulation_config dict
        """
        if not device.device_metadata:
            device.device_metadata = {}

        old_sim_config = device.device_metadata.get(
            "simulation_config", {"sensors": {}, "actuators": {}}
        )
        old_sensors = old_sim_config.get("sensors", {})

        # Build reverse lookup: (gpio, sensor_type) -> old sim params
        old_by_identity: Dict[tuple, dict] = {}
        for _key, entry in old_sensors.items():
            gpio = entry.get("gpio")
            stype = entry.get("sensor_type", "")
            if gpio is not None:
                old_by_identity[(int(gpio), stype.lower())] = entry

        # Simulation-specific param keys (NOT in SensorConfig model)
        SIM_PARAMS = {
            "base_value",
            "variation_pattern",
            "variation_range",
            "min_value",
            "max_value",
            "interval_seconds",
            "quality",
            "raw_mode",
        }

        new_sensors: Dict[str, dict] = {}
        for cfg in sensor_configs:
            if not cfg.enabled:
                continue

            # Virtual sensors (e.g., VPD) are event-driven, never scheduled.
            # Exclude them from simulation_config to prevent spurious jobs.
            if cfg.interface_type and cfg.interface_type.upper() == "VIRTUAL":
                continue  # Virtual sensors are event-driven, never scheduled

            key = f"cfg_{cfg.id}"
            gpio = cfg.gpio if cfg.gpio is not None else 0
            sensor_type = cfg.sensor_type or ""

            # Start with basic config from DB
            entry: Dict[str, Any] = {
                "sensor_type": sensor_type,
                "gpio": gpio,
                "name": cfg.sensor_name,
            }

            if cfg.i2c_address is not None:
                entry["i2c_address"] = cfg.i2c_address
            if cfg.interface_type:
                entry["interface_type"] = cfg.interface_type
            if cfg.onewire_address is not None:
                entry["onewire_address"] = cfg.onewire_address
            if hasattr(cfg, "device_scope") and cfg.device_scope:
                entry["device_scope"] = cfg.device_scope
            if hasattr(cfg, "assigned_zones") and cfg.assigned_zones:
                entry["assigned_zones"] = cfg.assigned_zones

            # Resolve simulation-specific params with 3-tier fallback:
            # 1. sensor_metadata.simulation (persistent per-sensor storage)
            # 2. old entry match by (gpio, sensor_type)
            # 3. type-based defaults
            sim_meta = {}
            if cfg.sensor_metadata and isinstance(cfg.sensor_metadata, dict):
                sim_meta = cfg.sensor_metadata.get("simulation", {})

            old_entry = old_by_identity.get((gpio, sensor_type.lower()), {})

            for param in SIM_PARAMS:
                if param in sim_meta:
                    entry[param] = sim_meta[param]
                elif param in old_entry:
                    entry[param] = old_entry[param]
                # else: omit — scheduler uses its own defaults

            new_sensors[key] = entry

        # Preserve non-sensor parts (actuators, manual_overrides, heartbeat)
        new_sim_config = {
            "sensors": new_sensors,
            "actuators": old_sim_config.get("actuators", {}),
        }
        # Preserve manual_overrides if they exist
        if "manual_overrides" in old_sim_config:
            new_sim_config["manual_overrides"] = old_sim_config["manual_overrides"]

        device.device_metadata["simulation_config"] = new_sim_config
        device.device_metadata["simulation_config_updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        flag_modified(device, "device_metadata")
        await self.session.flush()

        return new_sim_config

    def get_heartbeat_interval(self, device: ESPDevice) -> float:
        """
        Extract heartbeat interval from device metadata.

        Args:
            device: ESPDevice instance

        Returns:
            Heartbeat interval in seconds (default: 60.0)
        """
        if not device.device_metadata:
            return 60.0
        return device.device_metadata.get("heartbeat_interval", 60.0)
