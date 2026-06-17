"""
Mock-ESP Simulation Scheduler.

Nutzt den zentralen Scheduler für Mock-ESP Heartbeats und Sensor-Daten.
Jeder Mock-ESP bekommt:
- 1 Heartbeat-Job (konfigurierbar, default 60s)
- N Sensor-Jobs (je nach Konfiguration, individuelles Intervall)
- MQTT Subscriptions für Actuator-Commands (Paket G)

Job-IDs folgen dem Pattern:
- Heartbeat: "mock_{esp_id}_heartbeat"
- Sensor: "mock_{esp_id}_sensor_{gpio}_{sensor_type}" (MULTI-VALUE SUPPORT)
- Auto-Off: "mock_{esp_id}_auto_off_{gpio}"

MULTI-VALUE SUPPORT:
- Sensor configs are keyed by "{gpio}_{sensor_type}" (e.g., "21_sht31_temp")
- Each sensor_type gets its own job, even on the same GPIO
- SHT31: Creates "21_sht31_temp" + "21_sht31_humidity" jobs on same GPIO 21
"""

import re
import time
import random
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Any, List, TYPE_CHECKING
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.scheduler import get_central_scheduler, JobCategory
from ...core.logging_config import get_logger
from ...mqtt.topics import TopicBuilder

if TYPE_CHECKING:
    from .actuator_handler import MockActuatorHandler

logger = get_logger(__name__)


@dataclass
class MockESPRuntime:
    """
    Runtime-State für einen simulierten Mock-ESP.

    Speichert transiente Daten die NICHT in der DB sind:
    - Drift-Werte für Sensor-Simulation
    - Uptime-Tracking
    - Actuator-States für Actuator-Simulation (Paket G)
    """

    esp_id: str
    kaiser_id: str
    zone_id: str
    start_time: float = field(default_factory=time.time)

    # Drift-State für DRIFT-Pattern Sensoren
    drift_values: Dict[int, float] = field(default_factory=dict)
    drift_directions: Dict[int, int] = field(default_factory=dict)

    # Sensor-Jobs tracking (für dynamisches Add/Remove)
    active_sensor_jobs: Dict[int, str] = field(default_factory=dict)  # {gpio: job_id}

    # Actuator-State (Paket G - Actuator-Simulation)
    actuator_states: Dict[int, bool] = field(default_factory=dict)  # {gpio: True/False}
    actuator_pwm_values: Dict[int, int] = field(default_factory=dict)  # {gpio: 0-255}
    actuator_runtime_ms: Dict[int, int] = field(default_factory=dict)  # {gpio: milliseconds}
    last_commands: Dict[int, str] = field(default_factory=dict)  # {gpio: last_command}
    emergency_stopped: bool = False  # Global E-Stop flag
    subscriptions: List[str] = field(default_factory=list)  # Active MQTT subscriptions

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time


class SimulationScheduler:
    """
    Verwaltet Mock-ESP Simulationen über den zentralen Scheduler.

    ARCHITEKTUR (Paket B - Database as Single Source of Truth):
    - Nutzt CentralScheduler für Job-Management
    - Speichert nur Runtime-State (Drift-Werte, Uptime) in Memory
    - Konfiguration kommt aus Database (ESPRepository)
    - Nach Server-Restart: recover_mocks() lädt alle 'running' Mocks aus DB

    PAKET G ERWEITERUNG (Actuator-Simulation):
    - Registriert MQTT Handler für Actuator-Commands
    - MockActuatorHandler verarbeitet Commands für aktive Mocks
    - Response und Status werden via MQTT publiziert

    VERWENDUNG:

    1. Simulation starten:
        await sim_scheduler.start_mock("ESP001", heartbeat_interval=60)

    2. Simulation stoppen:
        await sim_scheduler.stop_mock("ESP001")

    3. Alle stoppen:
        await sim_scheduler.stop_all_mocks()

    4. Recovery nach Server-Restart:
        recovered = await sim_scheduler.recover_mocks(session)
    """

    def __init__(self, mqtt_publish: Optional[Callable] = None):
        """
        Args:
            mqtt_publish: Callback für MQTT Publishing
                         Signatur: def publish(topic: str, payload: dict, qos: int = 1)
        """
        self._mqtt_publish = mqtt_publish
        self._runtimes: Dict[str, MockESPRuntime] = {}
        self._actuator_handler: Optional["MockActuatorHandler"] = None
        self._subscriptions_registered: bool = False
        # Track sensors that already warned about missing config (suppress repeated warnings)
        self._warned_missing_sensors: set[str] = set()

    def set_mqtt_callback(self, callback: Callable) -> None:
        """Setzt den MQTT Publish Callback."""
        self._mqtt_publish = callback
        # Also update actuator handler
        if self._actuator_handler:
            self._actuator_handler.set_mqtt_callback(callback)

    def _init_actuator_handler(self) -> None:
        """Initialize the MockActuatorHandler (lazy initialization)."""
        if self._actuator_handler is None:
            from .actuator_handler import MockActuatorHandler

            self._actuator_handler = MockActuatorHandler(
                scheduler=self, mqtt_publish=self._mqtt_publish
            )
            logger.debug("MockActuatorHandler initialized")

    # ================================================================
    # SIMULATION LIFECYCLE
    # ================================================================

    async def start_mock(
        self,
        esp_id: str,
        kaiser_id: str = "god",
        zone_id: str = "",
        heartbeat_interval: float = 60.0,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Startet Simulation für einen Mock-ESP.

        Erstellt Heartbeat-Job und Sensor-Jobs über den zentralen Scheduler.
        Lädt Sensor- und Actuator-Konfiguration aus DB.
        Registriert MQTT Handler für Actuator-Commands (Paket G).

        Args:
            esp_id: ESP Device ID
            kaiser_id: Kaiser ID (default: "god")
            zone_id: Zone ID
            heartbeat_interval: Heartbeat-Intervall in Sekunden
            session: Optional DB-Session (für Recovery)

        Returns:
            True wenn erfolgreich gestartet
        """
        scheduler = get_central_scheduler()

        # Prüfe ob bereits aktiv
        if esp_id in self._runtimes:
            logger.warning(f"Mock {esp_id} already running")
            return False

        # Initialize actuator handler if needed
        self._init_actuator_handler()

        # Register actuator command handler with MQTT subscriber (once)
        await self._register_actuator_command_handler()

        # Runtime erstellen
        runtime = MockESPRuntime(esp_id=esp_id, kaiser_id=kaiser_id, zone_id=zone_id)
        self._runtimes[esp_id] = runtime

        # Heartbeat Job (job_id pattern: mock_{esp_id}_heartbeat)
        scheduler.add_interval_job(
            job_id=f"mock_{esp_id}_heartbeat",
            func=self._heartbeat_job,
            seconds=heartbeat_interval,
            args=[esp_id],
            category=JobCategory.MOCK_ESP,
            start_immediately=True,
        )

        # Sensor-Jobs aus DB laden
        sensor_count = 0
        actuator_count = 0
        try:
            # Use provided session or create temporary one
            if session:
                await self._start_sensor_jobs_from_db(esp_id, runtime, session)
                sensor_count = len(runtime.active_sensor_jobs)
                # Initialize actuators (Paket G)
                actuator_count = await self._actuator_handler.initialize_actuators(esp_id, runtime)
            else:
                from ...db.session import get_session

                async for db_session in get_session():
                    await self._start_sensor_jobs_from_db(esp_id, runtime, db_session)
                    sensor_count = len(runtime.active_sensor_jobs)
                    # Initialize actuators (Paket G)
                    actuator_count = await self._actuator_handler.initialize_actuators(
                        esp_id, runtime
                    )
                    break

        except Exception as e:
            logger.error(f"Failed to load jobs for {esp_id}: {e}", exc_info=True)

        logger.info(
            f"Started mock simulation: {esp_id} "
            f"(heartbeat every {heartbeat_interval}s, {sensor_count} sensors, {actuator_count} actuators)"
        )
        return True

    async def _register_actuator_command_handler(self) -> None:
        """
        Register MQTT handler for actuator commands (Paket G).

        Subscribes to actuator command topics and routes them to MockActuatorHandler.
        Only registered once (idempotent).
        """
        if self._subscriptions_registered:
            return

        try:
            from ...mqtt.client import MQTTClient

            # Get the global subscriber instance
            # Note: The subscriber is registered via set_on_message_callback
            mqtt_client = MQTTClient.get_instance()

            # Register handler patterns for mock actuator commands
            # These patterns are checked against incoming messages
            command_pattern = "kaiser/+/esp/+/actuator/+/command"
            emergency_pattern = "kaiser/+/esp/+/actuator/emergency"
            broadcast_emergency_pattern = "kaiser/broadcast/emergency"

            # Subscribe to these patterns
            if mqtt_client.is_connected():
                mqtt_client.subscribe(command_pattern, qos=2)
                mqtt_client.subscribe(emergency_pattern, qos=2)
                mqtt_client.subscribe(broadcast_emergency_pattern, qos=2)

                logger.info(
                    f"Subscribed to actuator command topics for mock ESPs: "
                    f"{command_pattern}, {emergency_pattern}, {broadcast_emergency_pattern}"
                )

            self._subscriptions_registered = True

        except Exception as e:
            logger.warning(f"Failed to register actuator command handler: {e}")

    async def handle_mqtt_message(self, topic: str, payload_str: str) -> Optional[bool]:
        """
        Handle incoming MQTT message for mock ESPs.

        Called by the MQTT subscriber for actuator command topics.
        Routes to MockActuatorHandler if target ESP is an active mock.

        Args:
            topic: MQTT topic string
            payload_str: JSON payload string

        Returns:
            True if handled by a mock, None if not applicable (real ESP / no mock).
        """
        if not self._actuator_handler:
            return None

        # Check if this is an actuator command
        if "/actuator/" in topic and topic.endswith("/command"):
            # Parse esp_id from topic
            esp_id = self._extract_esp_id_from_topic(topic)
            if esp_id and self.is_mock_active(esp_id):
                return await self._actuator_handler.handle_command(topic, payload_str)

        # Check for ESP-specific emergency
        elif "/actuator/emergency" in topic and not topic.startswith("kaiser/broadcast"):
            esp_id = self._extract_esp_id_from_topic(topic)
            if esp_id and self.is_mock_active(esp_id):
                return await self._actuator_handler.handle_emergency(topic, payload_str, esp_id)

        # Check for broadcast emergency
        elif topic == "kaiser/broadcast/emergency":
            return await self._actuator_handler.handle_broadcast_emergency(topic, payload_str)

        return None

    def _extract_esp_id_from_topic(self, topic: str) -> Optional[str]:
        """
        Extract ESP ID from MQTT topic.

        Args:
            topic: MQTT topic string

        Returns:
            ESP ID or None
        """
        # Pattern: kaiser/{kaiser_id}/esp/{esp_id}/...
        pattern = r"kaiser/[a-zA-Z0-9_]+/esp/([A-Za-z0-9_]+)/"
        match = re.search(pattern, topic)
        if match:
            return match.group(1)
        return None

    async def _start_sensor_jobs_from_db(
        self, esp_id: str, runtime: MockESPRuntime, session: AsyncSession
    ) -> None:
        """
        Lädt Sensor-Config aus DB und startet Sensor-Jobs.

        MULTI-VALUE SUPPORT: Keys are now "{gpio}_{sensor_type}" format.
        Each sensor_type gets its own job, even on the same GPIO.

        Args:
            esp_id: ESP Device ID
            runtime: Mock Runtime
            session: DB Session
        """
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if not device or not device.device_metadata:
            return

        sim_config = device.device_metadata.get("simulation_config", {})
        sensors = sim_config.get("sensors", {})

        scheduler = get_central_scheduler()

        for sensor_key, sensor_config in sensors.items():
            try:
                # Key formats: "cfg_{uuid}" (new), "{gpio}_{sensor_type}" (legacy), "{gpio}" (oldest)
                sensor_type = sensor_config.get("sensor_type", "GENERIC")

                # Guard: skip virtual (event-driven) sensors — they must never be scheduled.
                from ...sensors.sensor_type_registry import VIRTUAL_SENSOR_TYPES

                if sensor_type.lower() in VIRTUAL_SENSOR_TYPES:
                    logger.debug(
                        f"[{esp_id}] Skipping VIRTUAL sensor {sensor_type} on key {sensor_key}"
                    )
                    continue

                # Extract GPIO from config dict (reliable) or key (legacy fallback)
                if "gpio" in sensor_config:
                    gpio = int(sensor_config["gpio"])
                elif sensor_key.startswith("cfg_"):
                    # cfg_{id} format — gpio MUST be in config dict
                    logger.error(f"cfg_ key '{sensor_key}' missing 'gpio' in config, skipping")
                    continue
                elif "_" in sensor_key and not sensor_key.isdigit():
                    gpio = int(sensor_key.split("_")[0])
                else:
                    gpio = int(sensor_key)

                interval = sensor_config.get("interval_seconds", 30.0)

                # MULTI-VALUE: Job-ID includes sensor_type
                job_id = f"mock_{esp_id}_sensor_{gpio}_{sensor_type}"
                scheduler.add_interval_job(
                    job_id=job_id,
                    func=self._sensor_job,
                    seconds=interval,
                    args=[esp_id, gpio, sensor_type],  # Pass sensor_type to job
                    category=JobCategory.MOCK_ESP,
                    start_immediately=True,
                )

                # Track in Runtime using sensor_key (gpio_type)
                runtime.active_sensor_jobs[sensor_key] = job_id

                logger.debug(
                    f"[{esp_id}] Started sensor job: GPIO {gpio}, "
                    f"type {sensor_type}, interval {interval}s"
                )

            except (ValueError, KeyError) as e:
                logger.error(f"Invalid sensor key '{sensor_key}' in config: {e}")

    async def stop_mock(self, esp_id: str) -> bool:
        """
        Stoppt Simulation für einen Mock-ESP.

        Entfernt alle zugehörigen Jobs.

        Args:
            esp_id: ESP Device ID

        Returns:
            True wenn erfolgreich gestoppt
        """
        scheduler = get_central_scheduler()

        if esp_id not in self._runtimes:
            logger.warning(f"Mock {esp_id} not running")
            return False

        # Alle Jobs für diesen Mock entfernen
        removed = scheduler.remove_jobs_by_prefix(f"mock_{esp_id}_")

        # Runtime entfernen
        del self._runtimes[esp_id]

        logger.info(f"Stopped mock simulation: {esp_id} ({removed} jobs removed)")
        return True

    async def stop_all_mocks(self) -> int:
        """
        Stoppt alle laufenden Mock-Simulationen.

        Wird bei Server-Shutdown aufgerufen.

        Returns:
            Anzahl gestoppter Simulationen
        """
        count = 0
        for esp_id in list(self._runtimes.keys()):
            if await self.stop_mock(esp_id):
                count += 1
        return count

    async def recover_mocks(self, session: AsyncSession) -> int:
        """
        Recover all Mock-ESPs with simulation_state='running' from database.

        Called at server startup to restore simulation state.
        This is the key method for "Database as Single Source of Truth".

        Args:
            session: Database session

        Returns:
            Number of recovered mocks
        """
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)
        recovered = 0
        failed = 0

        try:
            # Load all mocks with simulation_state='running' from DB
            running_mocks = await esp_repo.get_running_mock_devices()

            if not running_mocks:
                logger.info("No running mock simulations to recover")
                return 0

            logger.info(f"Recovering {len(running_mocks)} mock simulations from database...")

            for device in running_mocks:
                try:
                    # Get simulation config from metadata
                    heartbeat_interval = esp_repo.get_heartbeat_interval(device)

                    # Start simulation
                    success = await self.start_mock(
                        esp_id=device.device_id,
                        kaiser_id=device.kaiser_id or "god",
                        zone_id=device.zone_id or "",
                        heartbeat_interval=heartbeat_interval,
                    )

                    if success:
                        recovered += 1
                        # Update device status to online AND last_seen to current time
                        # Bug Y Fix: Set last_seen BEFORE health-check can run to avoid
                        # race condition where health-check sees old last_seen and marks
                        # device as timed out before heartbeat-handler can update it.
                        device.status = "online"
                        device.last_seen = datetime.now(timezone.utc)
                        logger.debug(f"Recovered mock simulation: {device.device_id}")
                    else:
                        failed += 1
                        logger.warning(f"Failed to recover mock simulation: {device.device_id}")

                except Exception as e:
                    failed += 1
                    logger.error(f"Error recovering mock {device.device_id}: {e}")

            # Commit status updates
            await session.commit()

            logger.info(
                f"Mock recovery complete: {recovered} recovered, {failed} failed "
                f"(out of {len(running_mocks)} total)"
            )

        except Exception as e:
            logger.error(f"Mock recovery failed: {e}", exc_info=True)

        return recovered

    async def cleanup_orphaned_runtimes(self, session: AsyncSession) -> int:
        """
        Remove in-memory runtimes whose devices no longer exist in the database.

        Called after recover_mocks() at server startup to catch edge cases
        where DB was restored/cleaned while scheduler had active mocks.

        Args:
            session: Database session

        Returns:
            Number of orphaned runtimes removed
        """
        from ...db.repositories import ESPRepository

        if not self._runtimes:
            return 0

        esp_repo = ESPRepository(session)
        orphaned = []

        for esp_id in list(self._runtimes.keys()):
            device = await esp_repo.get_by_device_id(esp_id)
            if not device:
                orphaned.append(esp_id)

        for esp_id in orphaned:
            await self.stop_mock(esp_id)
            logger.warning(f"Removed orphaned mock runtime: {esp_id} (not found in database)")

        if orphaned:
            logger.info(f"Orphaned runtime cleanup: removed {len(orphaned)} stale mocks")

        return len(orphaned)

    def update_zone(self, esp_id: str, zone_id: str, kaiser_id: str = "god") -> bool:
        """
        Aktualisiert Zone-Informationen für einen Mock.

        Args:
            esp_id: ESP Device ID
            zone_id: Neue Zone ID
            kaiser_id: Kaiser ID

        Returns:
            True wenn erfolgreich
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return False

        runtime.zone_id = zone_id
        runtime.kaiser_id = kaiser_id
        return True

    def add_sensor_job(
        self, esp_id: str, gpio: int, interval_seconds: float = 30.0, sensor_type: str = "GENERIC"
    ) -> bool:
        """
        Fügt dynamisch einen Sensor-Job hinzu (während Simulation läuft).

        Diese Methode wird von der API aufgerufen wenn ein Sensor zu einem
        laufenden Mock hinzugefügt wird.

        MULTI-VALUE SUPPORT: Each sensor_type on the same GPIO gets its own job.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO Pin
            interval_seconds: Sensor-Intervall
            sensor_type: Sensor type (e.g., "sht31_temp", "sht31_humidity")

        Returns:
            True wenn Job erfolgreich hinzugefügt
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            logger.warning(f"Cannot add sensor job: Mock {esp_id} not running")
            return False

        # Guard: virtual (event-driven) sensors must never be scheduled.
        from ...sensors.sensor_type_registry import VIRTUAL_SENSOR_TYPES

        if sensor_type.lower() in VIRTUAL_SENSOR_TYPES:
            logger.debug(
                f"[{esp_id}] Skipping add_sensor_job for VIRTUAL sensor {sensor_type} on GPIO {gpio}"
            )
            return False

        # MULTI-VALUE: Use gpio_sensor_type as key
        sensor_key = f"{gpio}_{sensor_type}"

        # Prüfe ob Sensor bereits aktiv
        if sensor_key in runtime.active_sensor_jobs:
            logger.warning(f"[{esp_id}] Sensor {sensor_key} already active")
            return False

        scheduler = get_central_scheduler()

        # MULTI-VALUE: Job-ID includes sensor_type
        job_id = f"mock_{esp_id}_sensor_{gpio}_{sensor_type}"
        scheduler.add_interval_job(
            job_id=job_id,
            func=self._sensor_job,
            seconds=interval_seconds,
            args=[esp_id, gpio, sensor_type],  # Pass sensor_type to job
            category=JobCategory.MOCK_ESP,
            start_immediately=True,
        )

        # Track in Runtime using sensor_key
        runtime.active_sensor_jobs[sensor_key] = job_id

        logger.info(
            f"[{esp_id}] Added sensor job: GPIO {gpio}, type {sensor_type}, interval {interval_seconds}s"
        )
        return True

    async def trigger_immediate_sensor_publish(
        self, esp_id: str, gpio: int, sensor_type: str = "GENERIC"
    ) -> bool:
        """
        Triggert sofortigen Sensor-Publish (für initialen Wert nach Sensor-Erstellung).

        Diese Methode wird von der API aufgerufen um einen Sensor-Wert sofort zu
        publishen, anstatt auf das nächste Intervall zu warten.

        MULTI-VALUE SUPPORT: Requires sensor_type to identify the correct sensor.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO Pin
            sensor_type: Sensor type (e.g., "sht31_temp")

        Returns:
            True wenn Publish erfolgreich
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            logger.warning(f"Cannot publish: Mock {esp_id} not running")
            return False

        try:
            # Führe den Sensor-Job direkt aus (mit sensor_type)
            await self._sensor_job(esp_id, gpio, sensor_type)
            logger.info(f"[{esp_id}] Immediate sensor publish for GPIO {gpio} type {sensor_type}")
            return True
        except Exception as e:
            logger.error(f"[{esp_id}] Immediate publish failed: {e}")
            return False

    def remove_sensor_job(self, esp_id: str, gpio: int, sensor_type: Optional[str] = None) -> bool:
        """
        Entfernt dynamisch einen Sensor-Job (während Simulation läuft).

        Diese Methode wird von der API aufgerufen wenn ein Sensor von einem
        laufenden Mock entfernt wird.

        MULTI-VALUE SUPPORT: If sensor_type is provided, removes only that
        specific sensor job. If not provided, removes ALL jobs on that GPIO.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO Pin
            sensor_type: Optional sensor type (e.g., "sht31_temp")

        Returns:
            True wenn Job erfolgreich entfernt
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            logger.warning(f"Cannot remove sensor job: Mock {esp_id} not running")
            return False

        scheduler = get_central_scheduler()
        removed_any = False

        if sensor_type:
            # MULTI-VALUE: Remove specific sensor_type on GPIO
            sensor_key = f"{gpio}_{sensor_type}"
            if sensor_key in runtime.active_sensor_jobs:
                job_id = runtime.active_sensor_jobs[sensor_key]
                if scheduler.remove_job(job_id):
                    del runtime.active_sensor_jobs[sensor_key]
                    removed_any = True
                    logger.info(f"[{esp_id}] Removed sensor job: {sensor_key}")
        else:
            # BACKWARDS COMPAT: Remove all sensors on this GPIO
            keys_to_remove = [
                k for k in runtime.active_sensor_jobs if k == str(gpio) or k.startswith(f"{gpio}_")
            ]
            for sensor_key in keys_to_remove:
                job_id = runtime.active_sensor_jobs[sensor_key]
                if scheduler.remove_job(job_id):
                    del runtime.active_sensor_jobs[sensor_key]
                    removed_any = True
                    logger.info(f"[{esp_id}] Removed sensor job: {sensor_key}")

        # Clean up drift state for this GPIO
        if removed_any:
            if gpio in runtime.drift_values:
                del runtime.drift_values[gpio]
            if gpio in runtime.drift_directions:
                del runtime.drift_directions[gpio]

        return removed_any

    # ================================================================
    # JOB IMPLEMENTATIONS
    # ================================================================

    async def _heartbeat_job(self, esp_id: str) -> None:
        """Heartbeat Job - wird vom Scheduler aufgerufen."""
        runtime = self._runtimes.get(esp_id)
        if not runtime or not self._mqtt_publish:
            return

        # Sensor/Actuator Counts aus Runtime (Paket G: actuators now tracked)
        sensor_count = len(runtime.active_sensor_jobs)
        actuator_count = len(runtime.actuator_states)

        # Determine state based on emergency status
        state = "SAFE_MODE" if runtime.emergency_stopped else "OPERATIONAL"

        topic = TopicBuilder.build_heartbeat_topic(esp_id, runtime.kaiser_id)

        payload = {
            "esp_id": esp_id,
            "zone_id": runtime.zone_id,
            "master_zone_id": runtime.kaiser_id,  # Fixed: Should be kaiser_id, not zone_id
            "zone_assigned": bool(runtime.zone_id),
            "ts": int(time.time()),
            "uptime": int(runtime.uptime_seconds),
            "heap_free": random.randint(40000, 50000),
            "wifi_rssi": random.randint(-60, -40),
            "sensor_count": sensor_count,
            "actuator_count": actuator_count,
            "system_state": state,
            "metrics_schema_version": 1,
            "mqtt_connected": True,
            "safe_mode": runtime.emergency_stopped,
            "persistence_degraded": False,
            "persistence_degraded_reason": "",
            "runtime_state_degraded": runtime.emergency_stopped,
            "mqtt_circuit_breaker_open": False,
            "wifi_circuit_breaker_open": False,
            "network_degraded": False,
            "critical_outcome_drop_count": 0,
            "publish_outbox_drop_count": 0,
            "persistence_drift_count": 0,
        }

        try:
            self._mqtt_publish(topic, payload, 0)
            logger.info(f"[AUTO-HB] {esp_id} heartbeat published (state={state})")
        except Exception as e:
            logger.error(f"[AUTO-HB] {esp_id} heartbeat failed: {e}")

    async def trigger_heartbeat(self, esp_id: str) -> Optional[Dict[str, Any]]:
        """
        Manually trigger a heartbeat for a mock ESP.

        Paket X: Manual heartbeat trigger for API endpoints.

        Args:
            esp_id: ESP Device ID

        Returns:
            Heartbeat payload dict or None if mock not active
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return None

        # Call the heartbeat job directly
        await self._heartbeat_job(esp_id)

        # Return payload for API response
        sensor_count = len(runtime.active_sensor_jobs)
        actuator_count = len(runtime.actuator_states)
        state = "SAFE_MODE" if runtime.emergency_stopped else "OPERATIONAL"

        return {
            "esp_id": esp_id,
            "zone_id": runtime.zone_id,
            "master_zone_id": runtime.kaiser_id,
            "zone_assigned": bool(runtime.zone_id),
            "ts": int(time.time()),
            "uptime": int(runtime.uptime_seconds),
            "heap_free": random.randint(40000, 50000),
            "wifi_rssi": random.randint(-60, -40),
            "sensor_count": sensor_count,
            "actuator_count": actuator_count,
            "system_state": state,
            "metrics_schema_version": 1,
            "mqtt_connected": True,
            "safe_mode": runtime.emergency_stopped,
            "persistence_degraded": False,
            "runtime_state_degraded": runtime.emergency_stopped,
            "mqtt_circuit_breaker_open": False,
            "wifi_circuit_breaker_open": False,
            "network_degraded": False,
            "critical_outcome_drop_count": 0,
            "publish_outbox_drop_count": 0,
        }

    async def _sensor_job(self, esp_id: str, gpio: int, sensor_type: str = "GENERIC") -> None:
        """
        Sensor Job - wird vom Scheduler aufgerufen.

        Sendet simulierte Sensor-Daten identisch zu echtem ESP32.

        MULTI-VALUE SUPPORT: Uses "{gpio}_{sensor_type}" key to load config.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO Pin
            sensor_type: Sensor type (e.g., "sht31_temp", "sht31_humidity")
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime or not self._mqtt_publish:
            return

        # Sensor identifier for logging
        sensor_ident = f"GPIO{gpio}_{sensor_type}"

        # Sensor-Wert berechnen
        try:
            # Load sensor config from DB via async context
            from ...db.session import get_session
            from ...db.repositories import ESPRepository

            async for session in get_session():
                esp_repo = ESPRepository(session)
                device = await esp_repo.get_by_device_id(esp_id)

                if not device or not device.device_metadata:
                    warn_key = f"{esp_id}:{sensor_ident}:no_device"
                    if warn_key not in self._warned_missing_sensors:
                        self._warned_missing_sensors.add(warn_key)
                        logger.warning(
                            f"[{esp_id}] No device metadata for sensor {sensor_ident} — suppressing further warnings"
                        )
                    return

                sim_config = device.device_metadata.get("simulation_config", {})
                sensors = sim_config.get("sensors", {})

                # Find sensor config by (gpio, sensor_type) match across all key formats:
                # cfg_{id} (new), {gpio}_{type} (legacy), {gpio} (oldest)
                sensor_config = None
                for _k, entry in sensors.items():
                    if (
                        entry.get("gpio") is not None
                        and int(entry["gpio"]) == gpio
                        and entry.get("sensor_type", "").lower() == sensor_type.lower()
                    ):
                        sensor_config = entry
                        break

                if not sensor_config:
                    # Fallback: legacy key formats
                    sensor_config = sensors.get(f"{gpio}_{sensor_type}") or sensors.get(str(gpio))

                if not sensor_config:
                    warn_key = f"{esp_id}:{sensor_ident}:not_in_config"
                    if warn_key not in self._warned_missing_sensors:
                        self._warned_missing_sensors.add(warn_key)
                        logger.warning(
                            f"[{esp_id}] Sensor {sensor_ident} not in config — removing orphaned job"
                        )
                    # Auto-remove the orphaned sensor job
                    scheduler = get_central_scheduler()
                    job_id = f"mock_{esp_id}_sensor_{gpio}_{sensor_type}"
                    scheduler.remove_job(job_id)
                    return

                # Berechne Sensor-Wert
                value = self._calculate_sensor_value(
                    gpio=gpio,
                    sensor_config=sensor_config,
                    runtime=runtime,
                    manual_overrides=sim_config.get("manual_overrides", {}),
                )

                # Build MQTT Topic (MUST use TopicBuilder!)
                topic = TopicBuilder.build_sensor_data_topic(esp_id, gpio, runtime.kaiser_id)

                # Build Payload (Format wie echter ESP - raw_value ist der korrekte Wert)
                # MULTI-VALUE: sensor_type from parameter, not from config (for precision)
                payload = {
                    "ts": int(time.time() * 1000),  # MILLISEKUNDEN (KRITISCH!)
                    "esp_id": esp_id,
                    "gpio": gpio,
                    "sensor_type": sensor_type,  # Use parameter for precision
                    "raw_value": value,  # FLOAT - Der korrekte Sensor-Wert
                    "raw_mode": True,  # BOOLEAN (KRITISCH! - Required by handler)
                    "value": value,
                    "unit": sensor_config.get("unit", ""),
                    "quality": sensor_config.get("quality", "good"),
                    "zone_id": runtime.zone_id or "",
                    "subzone_id": sensor_config.get("subzone_id", ""),
                }

                # MQTT Publish
                self._mqtt_publish(topic, payload, 0)
                logger.debug(
                    f"[{esp_id}] Sensor {sensor_ident} published: "
                    f"{value:.2f} {sensor_config.get('unit', '')} (type={sensor_type})"
                )

                break  # Exit async for loop

        except Exception as e:
            logger.error(f"[{esp_id}] Sensor {sensor_ident} job failed: {e}", exc_info=True)

    def _calculate_sensor_value(
        self, gpio: int, sensor_config: dict, runtime: MockESPRuntime, manual_overrides: dict
    ) -> float:
        """
        Berechnet simulierten Sensor-Wert basierend auf Pattern.

        Variation Patterns:
        - CONSTANT: Fester base_value
        - RANDOM: base_value ± variation_range (zufällig)
        - DRIFT: Langsame Veränderung mit Umkehr an Grenzen

        Args:
            gpio: GPIO Pin
            sensor_config: Sensor-Konfiguration aus DB
            runtime: Runtime-State für Drift-Tracking
            manual_overrides: Manual Override-Werte

        Returns:
            Berechneter Sensor-Wert (Float)
        """
        # 1. HÖCHSTE PRIORITÄT: Manual Override
        if str(gpio) in manual_overrides:
            return float(manual_overrides[str(gpio)])

        # Extract config values
        base_value = sensor_config.get("base_value", 0.0)
        variation_pattern = sensor_config.get("variation_pattern", "constant").lower()
        variation_range = sensor_config.get("variation_range", 0.0)

        # Handle None values explicitly - .get() returns None if key exists with None value
        # This happens when sensor config is created without min/max values specified
        min_value_raw = sensor_config.get("min_value")
        max_value_raw = sensor_config.get("max_value")
        min_value = min_value_raw if min_value_raw is not None else (base_value - 10.0)
        max_value = max_value_raw if max_value_raw is not None else (base_value + 10.0)

        # 2. Pattern-basierte Berechnung
        if variation_pattern == "constant":
            value = base_value

        elif variation_pattern == "random":
            # Zufällige Variation um base_value
            variation = random.uniform(-variation_range, variation_range)
            value = base_value + variation

        elif variation_pattern == "drift":
            # Drift: Langsame kontinuierliche Veränderung

            # Initialisiere Drift-State falls nicht vorhanden
            if gpio not in runtime.drift_values:
                runtime.drift_values[gpio] = base_value
                runtime.drift_directions[gpio] = random.choice([-1, 1])

            # Drift-Wert inkrementell ändern
            drift_step = variation_range * 0.1  # 10% des Range pro Step
            runtime.drift_values[gpio] += drift_step * runtime.drift_directions[gpio]

            # Richtung umkehren an Grenzen
            if runtime.drift_values[gpio] >= max_value:
                runtime.drift_values[gpio] = max_value
                runtime.drift_directions[gpio] = -1
            elif runtime.drift_values[gpio] <= min_value:
                runtime.drift_values[gpio] = min_value
                runtime.drift_directions[gpio] = 1

            value = runtime.drift_values[gpio]

        else:
            # Fallback: CONSTANT
            logger.warning(
                f"Unknown variation_pattern '{variation_pattern}' for GPIO {gpio}, "
                f"using CONSTANT"
            )
            value = base_value

        # 3. Clamp zu min/max
        value = max(min_value, min(max_value, value))

        # 4. Round zu 2 Dezimalstellen
        return round(value, 2)

    # ================================================================
    # ACTUATOR MANAGEMENT (Paket G)
    # ================================================================

    async def emergency_stop(self, esp_id: str, reason: Optional[str] = None) -> bool:
        """
        Trigger emergency stop for a specific mock ESP.

        Paket X: Emergency stop operation.

        Args:
            esp_id: ESP device ID
            reason: Optional reason for emergency stop

        Returns:
            True if emergency stop activated successfully
        """
        if not self._actuator_handler:
            return False

        return await self._actuator_handler.emergency_stop(esp_id, reason)

    async def clear_emergency(self, esp_id: str) -> bool:
        """
        Clear emergency stop for a specific mock ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            True if emergency cleared successfully
        """
        if not self._actuator_handler:
            return False

        return await self._actuator_handler.clear_emergency(esp_id)

    def get_actuator_handler(self) -> Optional["MockActuatorHandler"]:
        """Get the MockActuatorHandler instance."""
        return self._actuator_handler

    def get_actuator_state(self, esp_id: str, gpio: int) -> Optional[Dict[str, Any]]:
        """
        Get current actuator state for a specific GPIO.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number

        Returns:
            Actuator state dict or None
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return None

        if gpio not in runtime.actuator_states:
            return None

        return {
            "gpio": gpio,
            "state": runtime.actuator_states.get(gpio, False),
            "pwm_value": runtime.actuator_pwm_values.get(gpio, 0),
            "last_command": runtime.last_commands.get(gpio, ""),
            "runtime_ms": runtime.actuator_runtime_ms.get(gpio, 0),
            "emergency_stopped": runtime.emergency_stopped,
        }

    def get_all_actuator_states(self, esp_id: str) -> Dict[int, Dict[str, Any]]:
        """
        Get all actuator states for a mock ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            Dict mapping GPIO to state info
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return {}

        states = {}
        for gpio in runtime.actuator_states.keys():
            states[gpio] = self.get_actuator_state(esp_id, gpio)

        return states

    # ================================================================
    # STATUS
    # ================================================================

    def get_active_mocks(self) -> List[str]:
        """Gibt IDs aller aktiven Mocks zurück."""
        return list(self._runtimes.keys())

    def is_mock_active(self, esp_id: str) -> bool:
        """Prüft ob Mock aktiv ist."""
        return esp_id in self._runtimes

    def get_runtime(self, esp_id: str) -> Optional[MockESPRuntime]:
        """
        Get runtime state for a mock ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            MockESPRuntime instance or None if mock not active
        """
        return self._runtimes.get(esp_id)

    def get_mock_status(self, esp_id: str) -> Optional[Dict[str, Any]]:
        """Gibt Status eines Mocks zurück."""
        runtime = self.get_runtime(esp_id)
        if not runtime:
            return None

        scheduler = get_central_scheduler()
        jobs = scheduler.get_jobs_by_category(JobCategory.MOCK_ESP)
        mock_jobs = [j for j in jobs if j["id"].startswith(f"mock_{esp_id}_")]

        return {
            "esp_id": esp_id,
            "kaiser_id": runtime.kaiser_id,
            "zone_id": runtime.zone_id,
            "uptime_seconds": runtime.uptime_seconds,
            "sensor_count": len(runtime.active_sensor_jobs),
            "actuator_count": len(runtime.actuator_states),
            "emergency_stopped": runtime.emergency_stopped,
            "actuator_states": dict(runtime.actuator_states),
            "actuator_pwm_values": dict(runtime.actuator_pwm_values),
            "last_commands": dict(runtime.last_commands),
            "jobs": mock_jobs,
        }

    # ================================================================
    # CRUD OPERATIONS (Paket X - Database as Single Source of Truth)
    # ================================================================

    async def create_mock_esp(
        self,
        esp_id: str,
        session: AsyncSession,
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        kaiser_id: str = "god",
        master_zone_id: Optional[str] = None,
        auto_start: bool = True,
        sensors: Optional[List[Dict[str, Any]]] = None,
        actuators: Optional[List[Dict[str, Any]]] = None,
        heartbeat_interval: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Erstellt Mock-ESP in Database UND startet Simulation.

        Paket X: Vollständige CRUD-Operation die ESPRepository nutzt.

        Args:
            esp_id: ESP Device ID (must be unique)
            session: Database session
            zone_id: Zone ID (optional)
            zone_name: Human-readable zone name (optional)
            kaiser_id: Kaiser ID (default: "god")
            master_zone_id: Master zone ID (optional)
            auto_start: Start simulation immediately
            sensors: List of sensor configs (optional)
            actuators: List of actuator configs (optional)
            heartbeat_interval: Heartbeat interval in seconds

        Returns:
            Dict with created mock ESP data

        Raises:
            DuplicateESPError: If esp_id already exists
            ValidationError: If validation fails
        """
        from ...db.repositories import ESPRepository
        from ...core.exceptions import DuplicateESPError

        esp_repo = ESPRepository(session)

        # Check if already exists
        existing = await esp_repo.get_by_device_id(esp_id)
        if existing:
            raise DuplicateESPError(esp_id)

        # Build simulation config with actuators only.
        # Sensors populated via rebuild_simulation_config() after DB entries.
        simulation_config = {
            "sensors": {},
            "actuators": {
                str(actuator["gpio"]): {
                    "actuator_type": actuator.get("actuator_type", "relay"),
                    "name": actuator.get("name"),
                    "state": actuator.get("state", False),
                    "pwm_value": actuator.get("pwm_value", 0.0),
                    "min_value": actuator.get("min_value", 0.0),
                    "max_value": actuator.get("max_value", 1.0),
                }
                for actuator in (actuators or [])
            },
            "heartbeat_interval": heartbeat_interval,
            "auto_heartbeat": auto_start,
        }

        # Create in database
        device = await esp_repo.create_mock_device(
            device_id=esp_id,
            kaiser_id=kaiser_id,
            zone_id=zone_id,
            zone_name=zone_name,
            master_zone_id=master_zone_id,
            heartbeat_interval=heartbeat_interval,
            simulation_config=simulation_config,
            auto_start=auto_start,
        )

        await session.commit()
        await session.refresh(device)

        # Create SensorConfig entries in DB and rebuild simulation_config
        from ...db.repositories import SensorRepository
        from ...sensors.sensor_type_registry import (
            expand_multi_value,
            get_device_type_from_sensor_type,
            get_i2c_address,
            is_multi_value_sensor,
        )

        sensor_repo = SensorRepository(session)
        for sensor_data in sensors or []:
            gpio = sensor_data.get("gpio", 0)
            raw_sensor_type = sensor_data.get("sensor_type", "GENERIC")
            base_value = sensor_data.get("base_value", sensor_data.get("raw_value", 0.0))

            sim_meta = {
                "base_value": base_value,
                "raw_mode": sensor_data.get("raw_mode", True),
                "quality": sensor_data.get("quality", "good"),
                "interval_seconds": sensor_data.get("interval_seconds", 30.0),
                "variation_pattern": sensor_data.get("variation_pattern", "constant"),
                "variation_range": sensor_data.get("variation_range", 0.0),
            }
            if sensor_data.get("min_value") is not None:
                sim_meta["min_value"] = sensor_data["min_value"]
            if sensor_data.get("max_value") is not None:
                sim_meta["max_value"] = sensor_data["max_value"]

            # Multi-value split
            if is_multi_value_sensor(raw_sensor_type):
                sub_types = expand_multi_value(
                    raw_sensor_type,
                    sensor_data.get("name", ""),
                    gpio=gpio,
                )
                # Resolve i2c_address + interface_type from registry (V19-F13)
                device_type = (
                    get_device_type_from_sensor_type(sub_types[0]["sensor_type"])
                    if sub_types
                    else None
                )
                resolved_i2c = get_i2c_address(device_type) if device_type else None
                resolved_iface = "I2C" if resolved_i2c is not None else "ANALOG"
                for sub in sub_types:
                    try:
                        await sensor_repo.create_if_not_exists(
                            esp_id=device.id,
                            gpio=gpio,
                            sensor_type=sub["sensor_type"],
                            sensor_name=sub.get("name", f"{sub['sensor_type']}_{gpio}"),
                            enabled=True,
                            pi_enhanced=False,
                            sample_interval_ms=int(sim_meta["interval_seconds"] * 1000),
                            interface_type=resolved_iface,
                            i2c_address=resolved_i2c,
                            sensor_metadata={"source": "mock_esp", "simulation": sim_meta},
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create SensorConfig {sub['sensor_type']}: {e}")
            else:
                try:
                    await sensor_repo.create_if_not_exists(
                        esp_id=device.id,
                        gpio=gpio,
                        sensor_type=raw_sensor_type,
                        sensor_name=sensor_data.get("name", f"{raw_sensor_type}_{gpio}"),
                        enabled=True,
                        pi_enhanced=False,
                        sample_interval_ms=int(sim_meta["interval_seconds"] * 1000),
                        sensor_metadata={"source": "mock_esp", "simulation": sim_meta},
                    )
                except Exception as e:
                    logger.warning(f"Failed to create SensorConfig {raw_sensor_type}: {e}")

        # Rebuild simulation_config from DB (Write-Through Cache)
        all_cfgs = await sensor_repo.get_by_esp(device.id)
        await esp_repo.rebuild_simulation_config(device, all_cfgs)
        await session.commit()
        await session.refresh(device)

        # Start simulation if requested
        simulation_started = False
        if auto_start:
            simulation_started = await self.start_mock(
                esp_id=esp_id,
                kaiser_id=kaiser_id,
                zone_id=zone_id or "",
                heartbeat_interval=heartbeat_interval,
                session=session,
            )

            if simulation_started:
                # Update status to online
                device.status = "online"
                await session.commit()

        logger.info(f"Created mock ESP: {esp_id} (simulation_started={simulation_started})")

        return {
            "esp_id": esp_id,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "simulation_started": simulation_started,
        }

    async def delete_mock_esp(
        self,
        esp_id: str,
        session: AsyncSession,
    ) -> bool:
        """
        Stoppt Simulation UND löscht aus Database.

        Paket X: Vollständige Delete-Operation.

        Args:
            esp_id: ESP Device ID
            session: Database session

        Returns:
            True if deleted successfully

        Raises:
            ESPNotFoundError: If ESP not found
        """
        from ...db.repositories import ESPRepository
        from ...core.exceptions import ESPNotFoundError

        esp_repo = ESPRepository(session)

        # Check if exists
        device = await esp_repo.get_by_device_id(esp_id)
        if not device or device.hardware_type != "MOCK_ESP32":
            raise ESPNotFoundError(esp_id)

        # Stop simulation if running
        if self.is_mock_active(esp_id):
            await self.stop_mock(esp_id)
            logger.info(f"Stopped simulation for {esp_id}")

        # Delete from database
        await esp_repo.delete(device.id)
        await session.commit()

        logger.info(f"Deleted mock ESP: {esp_id}")
        return True

    async def get_mock_esp(
        self,
        esp_id: str,
        session: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """
        Kombiniert DB-Daten mit Runtime-State.

        Paket X: Get-Operation die DB + Runtime kombiniert.

        Args:
            esp_id: ESP Device ID
            session: Database session

        Returns:
            Dict with mock ESP data or None if not found
        """
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if not device or device.hardware_type != "MOCK_ESP32":
            return None

        # Get runtime status if active
        runtime_status = None
        if self.is_mock_active(esp_id):
            runtime_status = self.get_mock_status(esp_id)

        # Combine DB + Runtime
        sim_config = (
            device.device_metadata.get("simulation_config", {}) if device.device_metadata else {}
        )

        return {
            "esp_id": device.device_id,
            "zone_id": device.zone_id,
            "zone_name": device.zone_name,
            "master_zone_id": device.master_zone_id,
            "status": device.status,
            "simulation_active": self.is_mock_active(esp_id),
            "runtime_status": runtime_status,
            "sensors": sim_config.get("sensors", {}),
            "actuators": sim_config.get("actuators", {}),
            "heartbeat_interval": sim_config.get("heartbeat_interval", 60.0),
            "created_at": device.created_at.isoformat() if device.created_at else None,
        }

    async def list_mock_esps(
        self,
        session: AsyncSession,
        include_stopped: bool = True,
        zone_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Liste aller Mock-ESPs mit Status.

        Paket X: List-Operation.

        Args:
            session: Database session
            include_stopped: Include stopped simulations
            zone_id: Filter by zone_id (optional)

        Returns:
            List of mock ESP dicts
        """
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)

        if zone_id:
            devices = await esp_repo.get_by_zone(zone_id)
            devices = [d for d in devices if d.hardware_type == "MOCK_ESP32"]
        else:
            devices = await esp_repo.get_mock_devices()

        results = []
        for device in devices:
            mock_data = await self.get_mock_esp(device.device_id, session)
            if mock_data:
                if include_stopped or mock_data["simulation_active"]:
                    results.append(mock_data)

        return results

    async def set_sensor_value(
        self,
        esp_id: str,
        gpio: int,
        value: float,
        session: AsyncSession,
        publish: bool = True,
    ) -> bool:
        """
        Setzt Sensor-Wert (Override) und optional publisht.

        Paket X: Sensor-Operation.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO pin
            value: Sensor value
            session: Database session
            publish: Publish MQTT message

        Returns:
            True if successful

        Raises:
            SimulationNotRunningError: If simulation not running
            SensorNotFoundError: If sensor not found
        """
        from ...core.exceptions import SimulationNotRunningError, SensorNotFoundError

        if not self.is_mock_active(esp_id):
            raise SimulationNotRunningError(esp_id)

        # Update manual override in DB
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if not device or not device.device_metadata:
            raise SensorNotFoundError(esp_id, gpio)

        sim_config = device.device_metadata.get("simulation_config", {})
        manual_overrides = sim_config.get("manual_overrides", {})
        manual_overrides[str(gpio)] = value
        sim_config["manual_overrides"] = manual_overrides
        device.device_metadata["simulation_config"] = sim_config

        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(device, "device_metadata")
        await session.commit()

        # Publish if requested
        if publish and self._mqtt_publish:
            runtime = self.get_runtime(esp_id)
            if runtime:
                # =====================================================================
                # MQTT PAYLOAD FOR MOCK ESP SENSOR DATA
                # =====================================================================
                # Mock ESPs send human-readable values (e.g., 20.0 for 20°C), NOT
                # hardware ADC values. This is different from real ESP32s where:
                #
                #   - Temperature sensors (DS18B20, SHT31): Already output Celsius,
                #     so raw_value = celsius (no ADC conversion needed)
                #   - Analog sensors (pH, EC): Output ADC 0-4095, server converts
                #
                # For Mock ESPs, we intentionally:
                #   1. Do NOT include a "raw" field (legacy ADC field)
                #   2. Set raw_value = value (both are the user-entered value)
                #   3. Set raw_mode = True (tells server to use raw_value as-is)
                #
                # The sensor_handler.py uses: payload.get("raw", payload.get("raw_value"))
                # By omitting "raw", it falls back to "raw_value" which is correct.
                #
                # BUG FIX: Previously had "raw": int(value * 100) which caused 20°C
                # to become 2000 in the database (the sensor_handler used "raw" first).
                # =====================================================================

                # Get sensor_type from config for complete payload
                sensors_config = sim_config.get("sensors", {})
                sensor_config = sensors_config.get(str(gpio), {})
                sensor_type = sensor_config.get("sensor_type", "GENERIC")
                unit = sensor_config.get("unit", "")

                topic = TopicBuilder.build_sensor_data_topic(esp_id, gpio, runtime.kaiser_id)
                payload = {
                    "ts": int(time.time() * 1000),
                    "esp_id": esp_id,
                    "gpio": gpio,
                    "sensor_type": sensor_type,
                    "raw_value": value,  # User-entered value (human-readable)
                    "value": value,  # Same as raw_value for Mock ESPs
                    "unit": unit,
                    "quality": "good",
                    "raw_mode": True,  # Server should use raw_value directly
                }
                self._mqtt_publish(topic, payload, 0)

        logger.info(f"Set sensor {esp_id}:GPIO{gpio} = {value}")
        return True

    async def set_actuator_state(
        self,
        esp_id: str,
        gpio: int,
        state: bool,
        session: AsyncSession,
        pwm_value: Optional[int] = None,
    ) -> bool:
        """
        Setzt Actuator-State direkt (ohne MQTT Round-Trip).

        Paket X: Actuator-Operation.

        Args:
            esp_id: ESP Device ID
            gpio: GPIO pin
            state: On/Off state
            session: Database session
            pwm_value: Optional PWM value (0-255)

        Returns:
            True if successful

        Raises:
            SimulationNotRunningError: If simulation not running
            ActuatorNotFoundError: If actuator not found
        """
        from ...core.exceptions import SimulationNotRunningError, ActuatorNotFoundError

        if not self.is_mock_active(esp_id):
            raise SimulationNotRunningError(esp_id)

        runtime = self.get_runtime(esp_id)
        if not runtime:
            raise SimulationNotRunningError(esp_id)

        # Check if actuator exists in config
        from ...db.repositories import ESPRepository

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if not device or not device.device_metadata:
            raise ActuatorNotFoundError(esp_id, gpio)

        sim_config = device.device_metadata.get("simulation_config", {})
        actuators = sim_config.get("actuators", {})

        if str(gpio) not in actuators:
            raise ActuatorNotFoundError(esp_id, gpio)

        # Update runtime state
        runtime.actuator_states[gpio] = state
        if pwm_value is not None:
            runtime.actuator_pwm_values[gpio] = pwm_value
        else:
            runtime.actuator_pwm_values[gpio] = 255 if state else 0

        # Update DB state so fetchDevice returns correct data
        actuator_entry = actuators[str(gpio)]
        actuator_entry["state"] = state
        if pwm_value is not None:
            actuator_entry["pwm_value"] = pwm_value
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(device, "device_metadata")
        await session.commit()

        # Publish MQTT status so server processes it and sends WebSocket event
        if self._mqtt_publish:
            import time as _time

            actuator_type = actuator_entry.get("actuator_type", "relay")
            topic = f"kaiser/{runtime.kaiser_id}/esp/{esp_id}/actuator/{gpio}/status"
            payload = {
                "esp_id": esp_id,
                "zone_id": runtime.zone_id or "",
                "subzone_id": "",
                "ts": int(_time.time() * 1000),
                "gpio": gpio,
                "actuator_type": actuator_type,
                "type": actuator_type,
                "state": state,
                "value": runtime.actuator_pwm_values.get(gpio, 0),
                "pwm": runtime.actuator_pwm_values.get(gpio, 0),
                "last_command": "ON" if state else "OFF",
                "runtime_ms": runtime.actuator_runtime_ms.get(gpio, 0),
                "emergency": "active" if runtime.emergency_stopped else "normal",
                "error": None,
            }
            try:
                self._mqtt_publish(topic, payload, 1)
            except Exception as e:
                logger.warning(f"Failed to publish actuator status for {esp_id}:GPIO{gpio}: {e}")

        logger.info(f"Set actuator {esp_id}:GPIO{gpio} = {state} (PWM={pwm_value})")
        return True

    async def set_batch_sensor_values(
        self,
        esp_id: str,
        values: Dict[int, float],
        session: AsyncSession,
        publish: bool = True,
    ) -> Dict[str, Any]:
        """
        Setzt mehrere Sensor-Werte gleichzeitig.

        Paket X: Batch-Sensor-Operation.

        Args:
            esp_id: ESP Device ID
            values: Dict mapping GPIO to value
            session: Database session
            publish: Publish MQTT messages

        Returns:
            Dict with results per GPIO

        Raises:
            SimulationNotRunningError: If simulation not running
        """
        from ...core.exceptions import SimulationNotRunningError

        if not self.is_mock_active(esp_id):
            raise SimulationNotRunningError(esp_id)

        results = {}
        for gpio, value in values.items():
            try:
                success = await self.set_sensor_value(
                    esp_id=esp_id,
                    gpio=int(gpio),
                    value=value,
                    session=session,
                    publish=publish,
                )
                results[str(gpio)] = {"success": success, "value": value}
            except Exception as e:
                results[str(gpio)] = {"success": False, "error": str(e)}

        logger.info(
            f"Batch set sensors for {esp_id}: {len(values)} values",
            extra={"esp_id": esp_id, "gpio_count": len(values), "category": "sensor_operation"},
        )
        return {
            "esp_id": esp_id,
            "sensors_updated": len([r for r in results.values() if r.get("success")]),
            "results": results,
        }

    async def set_auto_heartbeat(
        self,
        esp_id: str,
        enabled: bool,
        interval_seconds: float,
        session: AsyncSession,
    ) -> bool:
        """
        Konfiguriert Auto-Heartbeat (startet/stoppt Simulation).

        Paket X: Auto-Heartbeat-Konfiguration.

        Args:
            esp_id: ESP Device ID
            enabled: Enable/disable heartbeat
            interval_seconds: Heartbeat interval
            session: Database session

        Returns:
            True if successful

        Raises:
            ESPNotFoundError: If ESP not found
        """
        from ...db.repositories import ESPRepository
        from ...core.exceptions import ESPNotFoundError

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if not device or device.hardware_type != "MOCK_ESP32":
            raise ESPNotFoundError(esp_id)

        # Helper function to update auto_heartbeat in simulation_config
        async def update_auto_heartbeat_config(enable: bool) -> None:
            """Update auto_heartbeat field in simulation_config."""
            # Get existing simulation_config or create empty one
            metadata = device.device_metadata or {}
            sim_config = metadata.get("simulation_config", {})

            # Update auto_heartbeat and interval
            sim_config["auto_heartbeat"] = enable
            sim_config["heartbeat_interval"] = interval_seconds

            # Persist to database
            await esp_repo.update_simulation_config(esp_id, sim_config)

        if enabled:
            # Start simulation if not running
            if not self.is_mock_active(esp_id):
                success = await self.start_mock(
                    esp_id=esp_id,
                    kaiser_id=device.kaiser_id or "god",
                    zone_id=device.zone_id or "",
                    heartbeat_interval=interval_seconds,
                    session=session,
                )
                if success:
                    await esp_repo.update_simulation_state(esp_id, "running")
                    await update_auto_heartbeat_config(True)
                return success
            else:
                # Already running, just update the config
                await update_auto_heartbeat_config(True)
            return True
        else:
            # Stop simulation if running
            if self.is_mock_active(esp_id):
                success = await self.stop_mock(esp_id)
                if success:
                    await esp_repo.update_simulation_state(esp_id, "stopped")
                    await update_auto_heartbeat_config(False)
                return success
            else:
                # Already stopped, just update the config
                await update_auto_heartbeat_config(False)
            return True

    async def set_state(
        self,
        esp_id: str,
        state: str,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Setzt System-State für Mock-ESP.

        Paket X: System-State-Operation (für Kompatibilität).
        Nur SAFE_MODE wird als Emergency-Stop behandelt.

        Args:
            esp_id: ESP Device ID
            state: State string (OPERATIONAL, SAFE_MODE, etc.)
            reason: Optional reason

        Returns:
            Dict with state info or None if mock not found
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return None

        # SAFE_MODE = Emergency Stop
        if state.upper() == "SAFE_MODE":
            await self.emergency_stop(esp_id, reason)
        elif state.upper() == "OPERATIONAL" and runtime.emergency_stopped:
            await self.clear_emergency(esp_id)

        current_state = "SAFE_MODE" if runtime.emergency_stopped else "OPERATIONAL"

        logger.info(
            f"Set state for {esp_id}: {current_state}",
            extra={
                "esp_id": esp_id,
                "state": current_state,
                "reason": reason,
                "category": "simulation_control",
            },
        )

        return {
            "esp_id": esp_id,
            "state": current_state,
            "reason": reason,
            "previous_state": "SAFE_MODE" if not runtime.emergency_stopped else "OPERATIONAL",
        }

    def has_mock_esp(self, esp_id: str) -> bool:
        """
        Prüft ob Mock-ESP aktiv ist (Kompatibilität mit MockESPManager).

        Args:
            esp_id: ESP Device ID

        Returns:
            True if mock is active
        """
        return self.is_mock_active(esp_id)


# ================================================================
# DEPENDENCY INJECTION
# ================================================================

_sim_scheduler_instance: Optional[SimulationScheduler] = None


def get_simulation_scheduler() -> SimulationScheduler:
    """FastAPI Dependency für SimulationScheduler."""
    global _sim_scheduler_instance
    if _sim_scheduler_instance is None:
        raise RuntimeError("SimulationScheduler not initialized")
    return _sim_scheduler_instance


def init_simulation_scheduler(mqtt_callback: Callable) -> SimulationScheduler:
    """
    Initialisiert den SimulationScheduler.

    MUSS nach init_central_scheduler() aufgerufen werden.

    Args:
        mqtt_callback: Callback für MQTT Publishing
                      Signatur: def publish(topic: str, payload: dict, qos: int = 1)

    Returns:
        Initialisierte SimulationScheduler-Instanz
    """
    global _sim_scheduler_instance

    if _sim_scheduler_instance is not None:
        logger.warning("SimulationScheduler already initialized")
        return _sim_scheduler_instance

    _sim_scheduler_instance = SimulationScheduler(mqtt_publish=mqtt_callback)
    logger.info("SimulationScheduler initialized")

    return _sim_scheduler_instance
