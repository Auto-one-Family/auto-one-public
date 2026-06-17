"""
Monitor Data Service — Zone Monitor L2 Data Aggregation

Phase: Monitor L2 Optimized Design
Status: IMPLEMENTED

Builds ZoneMonitorData for GET /zone/{zone_id}/monitor-data.
Groups sensors/actuators by subzone (GPIO-based via subzone_configs.assigned_gpios).
"""

from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.actuator import ActuatorConfig, ActuatorState
from ..db.models.esp import ESPDevice
from ..db.models.sensor import SensorConfig
from ..db.models.subzone import SubzoneConfig
from ..schemas.monitor import (
    SubzoneActuatorEntry,
    SubzoneGroup,
    SubzoneSensorEntry,
    ZoneMonitorData,
)


class MonitorDataService:
    """
    Service for aggregating zone monitor data (L2 display).

    Groups sensors and actuators by subzone using GPIO-based assignment
    from subzone_configs.assigned_gpios.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_zone_monitor_data(self, zone_id: str) -> ZoneMonitorData:
        """
        Get full monitor data for a zone.

        Returns sensors and actuators grouped by subzone (GPIO-based).
        Devices without subzone assignment go to "Keine Subzone".
        """
        # 1. Load ESPs in zone
        esp_stmt = select(ESPDevice).where(ESPDevice.zone_id == zone_id)
        esp_result = await self.session.execute(esp_stmt)
        esps = list(esp_result.scalars().all())

        if not esps:
            zone_name = zone_id  # Fallback
            return ZoneMonitorData(
                zone_id=zone_id,
                zone_name=zone_name,
                subzones=[],
                sensor_count=0,
                actuator_count=0,
                alarm_count=0,
            )

        zone_name = esps[0].zone_name or zone_id
        esp_uuids = [e.id for e in esps]

        # 2. Build (esp_id, gpio) -> (subzone_id, subzone_name) map
        #    Also collect all configured subzone keys (for empty subzone inclusion)
        gpio_to_subzone: Dict[Tuple[str, int], Tuple[str, str]] = {}
        configured_subzone_keys: Set[Tuple[Optional[str], str]] = set()
        subzone_configs_stmt = select(SubzoneConfig).where(SubzoneConfig.parent_zone_id == zone_id)
        subzone_result = await self.session.execute(subzone_configs_stmt)
        for sc in subzone_result.scalars().all():
            subzone_id = sc.subzone_id
            subzone_name = sc.subzone_name or subzone_id
            configured_subzone_keys.add((subzone_id, subzone_name))
            for gpio in sc.assigned_gpios or []:
                gpio_to_subzone[(sc.esp_id, gpio)] = (subzone_id, subzone_name)

        # 3. Load sensor configs for ESPs in zone
        sensor_stmt = (
            select(SensorConfig, ESPDevice.device_id)
            .join(ESPDevice, SensorConfig.esp_id == ESPDevice.id)
            .where(SensorConfig.esp_id.in_(esp_uuids), SensorConfig.enabled == True)
        )
        sensor_result = await self.session.execute(sensor_stmt)
        sensor_configs: List[Tuple[SensorConfig, str]] = list(sensor_result.all())

        # 4. Load actuator configs for ESPs in zone
        actuator_stmt = (
            select(ActuatorConfig, ESPDevice.device_id)
            .join(ESPDevice, ActuatorConfig.esp_id == ESPDevice.id)
            .where(ActuatorConfig.esp_id.in_(esp_uuids), ActuatorConfig.enabled == True)
        )
        actuator_result = await self.session.execute(actuator_stmt)
        actuator_configs: List[Tuple[ActuatorConfig, str]] = list(actuator_result.all())

        # 5. Load latest sensor readings (batch)
        from ..db.repositories.sensor_repo import SensorRepository

        sensor_repo = SensorRepository(self.session)
        sensor_keys: List[Tuple] = []
        for sc, _ in sensor_configs:
            sensor_keys.append((sc.esp_id, sc.gpio, sc.sensor_type))
        latest_readings = await sensor_repo.get_latest_readings_batch_by_config(sensor_keys)

        # 6. Load actuator states
        state_stmt = select(ActuatorState).where(
            ActuatorState.esp_id.in_(esp_uuids),
        )
        state_result = await self.session.execute(state_stmt)
        state_map: Dict[Tuple, ActuatorState] = {}
        for s in state_result.scalars().all():
            state_map[(s.esp_id, s.gpio)] = s

        # 7. Build sensor entries with latest values
        sensor_entries: Dict[Tuple[Optional[str], Optional[str]], List[SubzoneSensorEntry]] = {}
        alarm_count = 0

        for sc, device_id in sensor_configs:
            if sc.gpio is None:
                continue
            gpio = sc.gpio
            subzone_id, subzone_name = gpio_to_subzone.get(
                (device_id, gpio), (None, "Keine Subzone")
            )
            key = (subzone_id, subzone_name)

            reading = latest_readings.get((sc.esp_id, gpio, sc.sensor_type))
            raw_value = None
            quality = "unknown"
            last_read = None
            if reading:
                val = (
                    reading.processed_value
                    if reading.processed_value is not None
                    else reading.raw_value
                )
                raw_value = float(val) if val is not None else None
                quality = reading.quality or "unknown"
                last_read = reading.timestamp.isoformat() if reading.timestamp else None

            if quality in ("error", "bad"):
                alarm_count += 1

            unit = self._get_sensor_unit(sc.sensor_type)
            entry = SubzoneSensorEntry(
                esp_id=device_id,
                gpio=gpio,
                sensor_type=sc.sensor_type,
                name=sc.sensor_name or None,
                raw_value=raw_value,
                unit=unit,
                quality=quality,
                last_read=last_read,
                operating_mode=sc.operating_mode,
            )
            if key not in sensor_entries:
                sensor_entries[key] = []
            sensor_entries[key].append(entry)

        # 8. Build actuator entries
        actuator_entries: Dict[Tuple[Optional[str], Optional[str]], List[SubzoneActuatorEntry]] = {}

        for ac, device_id in actuator_configs:
            gpio = ac.gpio
            subzone_id, subzone_name = gpio_to_subzone.get(
                (device_id, gpio), (None, "Keine Subzone")
            )
            key = (subzone_id, subzone_name)

            state = state_map.get((ac.esp_id, gpio))
            current_state = False
            pwm_value = 0.0
            emergency_stopped = False
            if state:
                current_state = state.state in ("on", "pwm") or (state.current_value or 0) > 0
                # Pass normalized 0.0–1.0 value directly; frontend handles display conversion.
                # Avoids double-multiplication: frontend does val * 100 for % display.
                pwm_value = float(state.current_value or 0.0)
                emergency_stopped = state.state == "emergency_stop"

            entry = SubzoneActuatorEntry(
                esp_id=device_id,
                gpio=gpio,
                actuator_type=ac.actuator_type,
                name=ac.actuator_name or None,
                state=current_state,
                pwm_value=pwm_value,
                emergency_stopped=emergency_stopped,
            )
            if key not in actuator_entries:
                actuator_entries[key] = []
            actuator_entries[key].append(entry)

        # 9. Merge sensors and actuators into SubzoneGroups
        #    Include empty subzones (from SubzoneConfig) that have no sensors/actuators
        all_keys: Set[Tuple[Optional[str], Optional[str]]] = set(sensor_entries.keys()) | set(
            actuator_entries.keys()
        )

        # Add configured subzones that may be empty (no GPIOs assigned yet)
        all_keys |= configured_subzone_keys

        subzones: List[SubzoneGroup] = []
        total_sensors = 0
        total_actuators = 0

        # Sort: named subzones first (alpha), then "Keine Subzone" last
        sorted_keys = sorted(
            all_keys,
            key=lambda k: (k[0] is None, k[1] or ""),
        )

        for subzone_id, subzone_name in sorted_keys:
            sensors = sensor_entries.get((subzone_id, subzone_name), [])
            actuators = actuator_entries.get((subzone_id, subzone_name), [])
            subzones.append(
                SubzoneGroup(
                    subzone_id=subzone_id,
                    subzone_name=subzone_name,
                    sensors=sensors,
                    actuators=actuators,
                )
            )
            total_sensors += len(sensors)
            total_actuators += len(actuators)

        return ZoneMonitorData(
            zone_id=zone_id,
            zone_name=zone_name,
            subzones=subzones,
            sensor_count=total_sensors,
            actuator_count=total_actuators,
            alarm_count=alarm_count,
        )

    def _get_sensor_unit(self, sensor_type: str) -> str:
        """Simple unit lookup for common sensor types."""
        units = {
            "sht31_temp": "°C",
            "sht31_humidity": "%RH",
            "bmp280_temp": "°C",
            "bmp280_humidity": "%RH",
            "ds18b20": "°C",
            "ph": "",
            "ec": "µS/cm",
            "moisture": "%",
            "light": "lux",
        }
        return units.get(sensor_type, "")
