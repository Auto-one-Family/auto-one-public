"""
Kaiser Service — Business Logic for Kaiser Relay Node Management

Phase 1: Kaiser hierarchy implementation.
Status: IMPLEMENTED

Provides:
- Kaiser registration and heartbeat
- ESP assignment management
- God-Kaiser initialization at startup
- Full hierarchy traversal (Kaiser → Zones → Subzones → Devices)

The "god" Kaiser is the default server-centric node.
Real Kaisers (Pi Zero relay nodes) are for scaling beyond 50 ESPs.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.actuator import ActuatorConfig
from ..db.models.esp import ESPDevice
from ..db.models.kaiser import KaiserRegistry
from ..db.models.sensor import SensorConfig
from ..db.models.subzone import SubzoneConfig
from ..db.models.zone_context import ZoneContext
from ..db.repositories.kaiser_repo import KaiserRepository

logger = get_logger(__name__)

GOD_KAISER_ID = "god"


class KaiserService:
    """Kaiser management business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = KaiserRepository(session)

    async def ensure_god_kaiser(self) -> KaiserRegistry:
        """Create the "god" Kaiser if it doesn't exist. Called at startup."""
        existing = await self.repo.get_by_kaiser_id(GOD_KAISER_ID)
        if existing:
            await self.repo.update_status(GOD_KAISER_ID, "online")
            logger.info("God-Kaiser already exists, marked online")
            return existing

        kaiser = await self.repo.create(
            kaiser_id=GOD_KAISER_ID,
            zone_ids=[],
            capabilities={
                "max_esps": 1000,
                "is_god_kaiser": True,
                "features": ["mqtt_broker", "database", "logic_engine", "web_ui"],
            },
            status="online",
            kaiser_metadata={"description": "Server-centric god-kaiser node (El Servador)"},
        )
        logger.info("God-Kaiser created successfully")
        return kaiser

    async def sync_god_kaiser_zones(self) -> int:
        """Sync god-Kaiser zone_ids from all ESPs that have kaiser_id='god'."""
        stmt = (
            select(ESPDevice.zone_id)
            .where(
                ESPDevice.kaiser_id == GOD_KAISER_ID,
                ESPDevice.zone_id.isnot(None),
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        zone_ids = [r for r in result.scalars().all() if r]

        kaiser = await self.repo.get_by_kaiser_id(GOD_KAISER_ID)
        if kaiser:
            kaiser.zone_ids = zone_ids
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(kaiser, "zone_ids")
            await self.session.flush()

        return len(zone_ids)

    async def set_default_kaiser_for_orphans(self) -> int:
        """Set kaiser_id='god' for all ESPs that have no kaiser_id."""
        stmt = select(ESPDevice).where(
            (ESPDevice.kaiser_id.is_(None)) | (ESPDevice.kaiser_id == "")
        )
        result = await self.session.execute(stmt)
        orphans = list(result.scalars().all())

        for device in orphans:
            device.kaiser_id = GOD_KAISER_ID

        if orphans:
            await self.session.flush()
            logger.info(f"Set kaiser_id='{GOD_KAISER_ID}' for {len(orphans)} orphan ESPs")

        return len(orphans)

    async def get_all_kaisers(self) -> List[KaiserRegistry]:
        return await self.repo.get_all()

    async def get_kaiser(self, kaiser_id: str) -> Optional[KaiserRegistry]:
        return await self.repo.get_by_kaiser_id(kaiser_id)

    async def register_kaiser(
        self,
        kaiser_id: str,
        zone_ids: Optional[List[str]] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        mac_address: Optional[str] = None,
    ) -> KaiserRegistry:
        """Register a new Kaiser relay node.

        Raises:
            ValueError: If a Kaiser with this ``kaiser_id`` already exists.
        """
        existing = await self.repo.get_by_kaiser_id(kaiser_id)
        if existing:
            raise ValueError(f"Kaiser '{kaiser_id}' already exists")

        kaiser = await self.repo.create(
            kaiser_id=kaiser_id,
            zone_ids=zone_ids or [],
            capabilities=capabilities,
            ip_address=ip_address,
            mac_address=mac_address,
        )
        await self.session.commit()
        return kaiser

    async def get_hierarchy(self, kaiser_id: str) -> Optional[Dict[str, Any]]:
        """Full hierarchy: Kaiser → Zones → Subzones → Devices."""
        kaiser = await self.repo.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return None

        stmt = select(ESPDevice).where(ESPDevice.kaiser_id == kaiser_id)
        result = await self.session.execute(stmt)
        devices = list(result.scalars().all())

        zones_map: Dict[str, Dict] = {}
        unassigned_devices: List[Dict] = []

        for device in devices:
            zone_id = device.zone_id or "__unassigned__"

            if zone_id == "__unassigned__":
                unassigned_devices.append(
                    {
                        "device_id": device.device_id,
                        "name": device.name,
                        "status": device.status,
                        "hardware_type": device.hardware_type,
                    }
                )
                continue

            if zone_id not in zones_map:
                ctx = await self.session.execute(
                    select(ZoneContext).where(ZoneContext.zone_id == zone_id)
                )
                zone_ctx = ctx.scalar_one_or_none()
                zones_map[zone_id] = {
                    "zone_id": zone_id,
                    "zone_name": device.zone_name,
                    "context": (
                        {
                            "variety": zone_ctx.variety if zone_ctx else None,
                            "growth_phase": zone_ctx.growth_phase if zone_ctx else None,
                            "plant_count": zone_ctx.plant_count if zone_ctx else None,
                            "substrate": zone_ctx.substrate if zone_ctx else None,
                        }
                        if zone_ctx
                        else None
                    ),
                    "subzones": {},
                    "devices": [],
                }

            # Check for subzones
            sz_stmt = select(SubzoneConfig).where(
                SubzoneConfig.esp_id == device.device_id,
                SubzoneConfig.parent_zone_id == zone_id,
            )
            sz_result = await self.session.execute(sz_stmt)
            subzones = list(sz_result.scalars().all())

            device_info = {
                "device_id": device.device_id,
                "name": device.name,
                "status": device.status,
                "hardware_type": device.hardware_type,
                "is_zone_master": device.is_zone_master,
            }

            if subzones:
                for sz in subzones:
                    sz_id = sz.subzone_id
                    assigned_gpios = sz.assigned_gpios or []
                    # B2: Resolve sensors/actuators from assigned_gpios
                    sensors_list: List[Dict[str, Any]] = []
                    actuators_list: List[Dict[str, Any]] = []
                    if assigned_gpios:
                        sens_stmt = select(SensorConfig).where(
                            SensorConfig.esp_id == device.id,
                            SensorConfig.gpio.in_(assigned_gpios),
                        )
                        sens_result = await self.session.execute(sens_stmt)
                        for sc in sens_result.scalars().all():
                            sensors_list.append(
                                {
                                    "id": str(sc.id),
                                    "gpio": sc.gpio,
                                    "sensor_type": sc.sensor_type,
                                    "sensor_name": sc.sensor_name,
                                    "esp_id": device.device_id,
                                }
                            )
                        act_stmt = select(ActuatorConfig).where(
                            ActuatorConfig.esp_id == device.id,
                            ActuatorConfig.gpio.in_(assigned_gpios),
                        )
                        act_result = await self.session.execute(act_stmt)
                        for ac in act_result.scalars().all():
                            actuators_list.append(
                                {
                                    "id": str(ac.id),
                                    "gpio": ac.gpio,
                                    "actuator_type": ac.actuator_type,
                                    "actuator_name": ac.actuator_name,
                                    "esp_id": device.device_id,
                                }
                            )
                    if sz_id not in zones_map[zone_id]["subzones"]:
                        zones_map[zone_id]["subzones"][sz_id] = {
                            "subzone_id": sz_id,
                            "subzone_name": sz.subzone_name,
                            "assigned_gpios": assigned_gpios,
                            "safe_mode_active": sz.safe_mode_active,
                            "custom_data": sz.custom_data if hasattr(sz, "custom_data") else {},
                            "devices": [],
                            "sensors": sensors_list,
                            "actuators": actuators_list,
                        }
                    else:
                        zones_map[zone_id]["subzones"][sz_id]["sensors"].extend(sensors_list)
                        zones_map[zone_id]["subzones"][sz_id]["actuators"].extend(actuators_list)
                    zones_map[zone_id]["subzones"][sz_id]["devices"].append(device_info)
            else:
                zones_map[zone_id]["devices"].append(device_info)

        # B2: Add "Keine Subzone" group with sensors/actuators from zone-level devices (no subzone)
        for zone_data in zones_map.values():
            no_sz_sensors: List[Dict[str, Any]] = []
            no_sz_actuators: List[Dict[str, Any]] = []
            for dev_info in zone_data["devices"]:
                dev_id_str = dev_info["device_id"]
                dev_stmt = select(ESPDevice).where(ESPDevice.device_id == dev_id_str)
                dev_res = await self.session.execute(dev_stmt)
                dev_obj = dev_res.scalar_one_or_none()
                if not dev_obj:
                    continue
                sens_stmt = select(SensorConfig).where(SensorConfig.esp_id == dev_obj.id)
                for sc in (await self.session.execute(sens_stmt)).scalars().all():
                    no_sz_sensors.append(
                        {
                            "id": str(sc.id),
                            "gpio": sc.gpio,
                            "sensor_type": sc.sensor_type,
                            "sensor_name": sc.sensor_name,
                            "esp_id": dev_obj.device_id,
                        }
                    )
                act_stmt = select(ActuatorConfig).where(ActuatorConfig.esp_id == dev_obj.id)
                for ac in (await self.session.execute(act_stmt)).scalars().all():
                    no_sz_actuators.append(
                        {
                            "id": str(ac.id),
                            "gpio": ac.gpio,
                            "actuator_type": ac.actuator_type,
                            "actuator_name": ac.actuator_name,
                            "esp_id": dev_obj.device_id,
                        }
                    )
            if no_sz_sensors or no_sz_actuators:
                zone_data["no_subzone"] = {
                    "subzone_id": "__no_subzone__",
                    "subzone_name": "Keine Subzone",
                    "assigned_gpios": [],
                    "sensors": no_sz_sensors,
                    "actuators": no_sz_actuators,
                }

        # Convert subzones dict to list
        for zone_data in zones_map.values():
            subzones_list = list(zone_data["subzones"].values())
            if "no_subzone" in zone_data:
                subzones_list.append(zone_data["no_subzone"])
                del zone_data["no_subzone"]
            zone_data["subzones"] = subzones_list

        return {
            "kaiser_id": kaiser.kaiser_id,
            "status": kaiser.status,
            "capabilities": kaiser.capabilities,
            "last_seen": kaiser.last_seen.isoformat() if kaiser.last_seen else None,
            "zones": list(zones_map.values()),
            "unassigned_devices": unassigned_devices,
            "total_devices": len(devices),
            "total_zones": len(zones_map),
        }
