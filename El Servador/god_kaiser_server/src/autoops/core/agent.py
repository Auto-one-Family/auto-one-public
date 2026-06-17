"""
AutoOps Agent - Main orchestrator for autonomous operations.

The agent:
1. Initializes context and discovers plugins
2. Asks initial questions if needed (sensor types, preferences)
3. Executes plugins in the correct order (capability-based)
4. Handles rollback on critical failures
5. Documents everything with structured logging
6. Reports results

Usage:
    agent = AutoOpsAgent(server_url="http://localhost:8000")
    await agent.initialize()

    # Option A: Full autonomous run
    result = await agent.run_autonomous(esp_specs=[...])

    # Option B: Interactive with questions
    questions = await agent.get_initial_questions()
    # ... user answers ...
    result = await agent.run_with_answers(answers={...})
"""

import logging
from typing import Any

from .api_client import APIError, GodKaiserClient
from .base_plugin import PluginCapability, PluginResult
from .context import AutoOpsContext, DeviceMode, ESPSpec
from .plugin_registry import PluginRegistry
from .reporter import AutoOpsReporter


def _get_logger(name: str) -> logging.Logger:
    """Get a logger, preferring the server's logging_config if available."""
    try:
        from ...core.logging_config import get_logger

        return get_logger(name)
    except (ImportError, ValueError):
        return logging.getLogger(name)


logger = _get_logger("autoops.agent")


class AutoOpsAgent:
    """
    Main AutoOps orchestrator.

    Coordinates plugins, manages context, handles errors,
    and generates comprehensive documentation.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        username: str = "admin",
        password: str = "admin123",
        dry_run: bool = False,
        verbose: bool = True,
        device_mode: str = "mock",
        max_retries: int = 3,
    ):
        self.context = AutoOpsContext(
            server_url=server_url,
            username=username,
            password=password,
            dry_run=dry_run,
            verbose=verbose,
            device_mode=DeviceMode(device_mode),
            max_retries=max_retries,
        )
        self.client = GodKaiserClient(
            base_url=server_url,
            max_retries=max_retries,
        )
        self.registry = PluginRegistry()
        self.reporter = AutoOpsReporter()
        self._plugin_results: list[tuple[str, PluginResult]] = []
        self._initialized = False

    async def initialize(self) -> dict[str, Any]:
        """
        Initialize the agent: discover plugins, authenticate, check health.

        Returns dict with initialization status and discovered plugins.
        """
        logger.info("Initializing AutoOps session %s", self.context.session_id)

        # Discover plugins
        self.registry.reset()
        discovered = self.registry.discover_plugins()
        logger.info("Discovered %d plugins", discovered)

        # Authenticate with server
        auth_status = "not_attempted"
        try:
            await self.client.authenticate(self.context.username, self.context.password)
            self.context.auth_token = self.client._token
            auth_status = "authenticated"
            logger.info("Authentication successful for user '%s'", self.context.username)
        except APIError as e:
            auth_status = f"failed: {e.detail}"
            self.context.log_error(f"Authentication failed: {e.detail}")
        except Exception as e:
            auth_status = f"error: {str(e)}"
            self.context.log_error(f"Authentication error: {str(e)}")

        # Check server health
        health_status = "unknown"
        try:
            health = await self.client.check_health()
            health_status = health.get("status", "unknown")
            self.context.system_snapshot = None  # Will be populated on first scan
            logger.info("Server health: %s", health_status)
        except Exception as e:
            health_status = f"unreachable: {str(e)}"
            logger.error("Server unreachable: %s", e)

        self._initialized = True

        return {
            "session_id": self.context.session_id,
            "plugins_discovered": discovered,
            "plugins": self.registry.list_plugins(),
            "auth_status": auth_status,
            "health_status": health_status,
            "server_url": self.context.server_url,
            "device_mode": self.context.device_mode.value,
        }

    async def scan_system(self) -> dict[str, Any]:
        """
        Scan the current system state.

        Discovers existing devices, sensors, actuators, and zones.
        """
        from .context import SystemSnapshot

        snapshot = SystemSnapshot()

        try:
            # Get all devices
            devices_response = await self.client.list_devices()
            devices = devices_response.get("devices", devices_response.get("data", []))
            if (
                isinstance(devices_response, dict)
                and "devices" not in devices_response
                and "data" not in devices_response
            ):
                devices = devices_response.get("items", [])
            snapshot.esp_devices = devices if isinstance(devices, list) else []
            snapshot.online_devices = sum(
                1
                for d in snapshot.esp_devices
                if isinstance(d, dict) and d.get("status") == "online"
            )
            snapshot.offline_devices = len(snapshot.esp_devices) - snapshot.online_devices
            snapshot.mock_devices = sum(
                1
                for d in snapshot.esp_devices
                if isinstance(d, dict)
                and (d.get("device_id", "").startswith("MOCK_") or d.get("is_mock", False))
            )
            snapshot.real_devices = len(snapshot.esp_devices) - snapshot.mock_devices

            # Get zones
            try:
                zones_response = await self.client.list_zones()
                zones = zones_response.get("zones", zones_response.get("data", []))
                snapshot.zones = [
                    z.get("zone_id", z.get("name", "unknown"))
                    for z in (zones if isinstance(zones, list) else [])
                ]
            except APIError:
                snapshot.zones = []

            # Count sensors and actuators
            try:
                sensors_response = await self.client.list_sensors()
                sensors = sensors_response.get("sensors", sensors_response.get("data", []))
                snapshot.total_sensors = len(sensors) if isinstance(sensors, list) else 0
            except APIError:
                snapshot.total_sensors = 0

            try:
                actuators_response = await self.client.list_actuators()
                actuators = actuators_response.get("actuators", actuators_response.get("data", []))
                snapshot.total_actuators = len(actuators) if isinstance(actuators, list) else 0
            except APIError:
                snapshot.total_actuators = 0

        except APIError as e:
            self.context.log_error(f"System scan failed: {e.detail}")

        from datetime import datetime, timezone

        snapshot.timestamp = datetime.now(timezone.utc).isoformat()
        self.context.system_snapshot = snapshot

        logger.info(
            "System scan: %d devices (%d online, %d mock, %d real), %d sensors, %d actuators",
            len(snapshot.esp_devices),
            snapshot.online_devices,
            snapshot.mock_devices,
            snapshot.real_devices,
            snapshot.total_sensors,
            snapshot.total_actuators,
        )

        return {
            "devices": len(snapshot.esp_devices),
            "online": snapshot.online_devices,
            "offline": snapshot.offline_devices,
            "mock": snapshot.mock_devices,
            "real": snapshot.real_devices,
            "sensors": snapshot.total_sensors,
            "actuators": snapshot.total_actuators,
            "zones": snapshot.zones,
        }

    def get_initial_questions(self) -> list[dict[str, Any]]:
        """
        Generate initial questions for the user before autonomous execution.

        These questions gather the information needed to configure ESPs.
        Returns a list of question dicts compatible with Claude Code's AskUserQuestion.
        """
        return [
            {
                "question": "Welche Sensoren soll der ESP haben?",
                "header": "Sensoren",
                "options": [
                    {
                        "label": "DS18B20 (Temperatur)",
                        "description": "OneWire Temperatursensor, wasserdicht",
                    },
                    {
                        "label": "SHT31 (Temp+Humidity)",
                        "description": "I2C Temperatur- und Feuchtigkeitssensor",
                    },
                    {"label": "PH Sensor", "description": "Analoger pH-Wert-Sensor"},
                    {"label": "EC Sensor", "description": "Analoger EC/Leitfähigkeitssensor"},
                ],
                "multiSelect": True,
            },
            {
                "question": "Welche Aktoren soll der ESP haben?",
                "header": "Aktoren",
                "options": [
                    {
                        "label": "Relay (Pumpe)",
                        "description": "Digitales Relay für Pumpensteuerung",
                    },
                    {
                        "label": "Relay (Ventil)",
                        "description": "Digitales Relay für Ventilsteuerung",
                    },
                    {"label": "PWM Fan", "description": "PWM-gesteuerter Lüfter"},
                    {"label": "Keine", "description": "Keine Aktoren konfigurieren"},
                ],
                "multiSelect": True,
            },
            {
                "question": "In welche Zone soll der ESP?",
                "header": "Zone",
                "options": [
                    {"label": "Gewächshaus", "description": "Zone: gewaechshaus"},
                    {"label": "Zelt 1", "description": "Zone: zelt_1"},
                    {"label": "Outdoor", "description": "Zone: outdoor"},
                    {"label": "Keine Zone", "description": "Erstmal ohne Zone"},
                ],
                "multiSelect": False,
            },
        ]

    def configure_from_answers(self, answers: dict[str, Any]) -> ESPSpec:
        """
        Build an ESPSpec from user answers.

        Maps user selections to concrete sensor/actuator configurations.
        """
        from .context import ActuatorSpec, SensorSpec

        spec = ESPSpec(hardware_type="ESP32_WROOM")
        sensors: list[SensorSpec] = []
        actuators: list[ActuatorSpec] = []

        # Sensor type mapping with defaults
        sensor_map = {
            "DS18B20": SensorSpec(
                sensor_type="temperature",
                name="Temperature Sensor",
                interface_type="ONEWIRE",
                raw_value=22.0,
                unit="°C",
            ),
            "SHT31": SensorSpec(
                sensor_type="temperature",
                name="SHT31 Temperature",
                interface_type="I2C",
                i2c_address=0x44,
                raw_value=22.0,
                unit="°C",
            ),
            "SHT31_humidity": SensorSpec(
                sensor_type="humidity",
                name="SHT31 Humidity",
                interface_type="I2C",
                i2c_address=0x44,
                raw_value=55.0,
                unit="%",
            ),
            "PH": SensorSpec(
                sensor_type="ph",
                name="pH Sensor",
                interface_type="ANALOG",
                raw_value=6.5,
                unit="pH",
            ),
            "EC": SensorSpec(
                sensor_type="ec",
                name="EC Sensor",
                interface_type="ANALOG",
                raw_value=1.2,
                unit="mS/cm",
            ),
        }

        # Actuator type mapping
        actuator_map = {
            "relay_pump": ActuatorSpec(actuator_type="relay", name="Water Pump"),
            "relay_valve": ActuatorSpec(actuator_type="valve", name="Water Valve"),
            "pwm_fan": ActuatorSpec(actuator_type="pwm_fan", name="Ventilation Fan"),
        }

        # Parse sensor selections
        selected_sensors = answers.get("sensors", [])
        if isinstance(selected_sensors, str):
            selected_sensors = [selected_sensors]

        for selection in selected_sensors:
            sel_lower = selection.lower()
            if "ds18b20" in sel_lower:
                sensors.append(sensor_map["DS18B20"])
            if "sht31" in sel_lower:
                sensors.append(sensor_map["SHT31"])
                sensors.append(sensor_map["SHT31_humidity"])
            if "ph" in sel_lower:
                sensors.append(sensor_map["PH"])
            if "ec" in sel_lower:
                sensors.append(sensor_map["EC"])

        # Parse actuator selections
        selected_actuators = answers.get("actuators", [])
        if isinstance(selected_actuators, str):
            selected_actuators = [selected_actuators]

        for selection in selected_actuators:
            sel_lower = selection.lower()
            if "keine" in sel_lower:
                continue
            if "pump" in sel_lower:
                actuators.append(actuator_map["relay_pump"])
            if "ventil" in sel_lower or "valve" in sel_lower:
                actuators.append(actuator_map["relay_valve"])
            if "fan" in sel_lower or "pwm" in sel_lower:
                actuators.append(actuator_map["pwm_fan"])

        # Parse zone
        zone = answers.get("zone", "")
        if isinstance(zone, str) and zone and "keine" not in zone.lower():
            # Auto-generate zone_id from zone_name
            zone_id = (
                zone.lower()
                .replace(" ", "_")
                .replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
            )
            spec.zone_name = zone
        else:
            zone_id = None

        spec.sensors = sensors
        spec.actuators = actuators
        if zone_id:
            spec.zone_name = zone

        return spec

    async def run_plugin(
        self,
        plugin_name: str,
        **kwargs: Any,
    ) -> PluginResult:
        """Run a single plugin by name."""
        plugin = self.registry.get(plugin_name)
        if not plugin:
            return PluginResult.failure(
                f"Plugin '{plugin_name}' not found",
                errors=[f"Available: {[p.name for p in self.registry.get_all()]}"],
            )

        # Validate preconditions
        pre_result = await plugin.validate_preconditions(self.context, self.client)
        if not pre_result.success:
            self._plugin_results.append((plugin_name, pre_result))
            return pre_result
        if pre_result.needs_user_input:
            self._plugin_results.append((plugin_name, pre_result))
            return pre_result

        # Execute
        try:
            result = await plugin.execute(self.context, self.client)
        except Exception as e:
            result = PluginResult.failure(
                f"Plugin '{plugin_name}' crashed: {str(e)}",
                errors=[str(e)],
            )

        self._plugin_results.append((plugin_name, result))
        return result

    async def run_autonomous(
        self,
        esp_specs: list[ESPSpec] | None = None,
        plugins: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run the agent autonomously with given specs.

        Args:
            esp_specs: ESP configurations to create. If None, uses context.esp_specs.
            plugins: Specific plugins to run. If None, runs all applicable.

        Returns:
            Session result with report path.
        """
        if not self._initialized:
            await self.initialize()

        if esp_specs:
            self.context.esp_specs = esp_specs

        # Scan current system
        scan_result = await self.scan_system()

        # Determine which plugins to run
        if plugins:
            plugins_to_run = [
                self.registry.get(name) for name in plugins if self.registry.get(name)
            ]
        else:
            # Run all plugins in capability order
            order = [
                PluginCapability.VALIDATE,  # First: check system health
                PluginCapability.CONFIGURE,  # Then: configure devices
                PluginCapability.DIAGNOSE,  # Then: diagnose issues
                PluginCapability.FIX,  # Then: fix issues
                PluginCapability.CLEANUP,  # Then: cleanup stale resources
                PluginCapability.MONITOR,  # Then: verify
                PluginCapability.DOCUMENT,  # Finally: document
            ]
            seen = set()
            plugins_to_run = []
            for cap in order:
                for p in self.registry.get_by_capability(cap):
                    if p.name not in seen:
                        seen.add(p.name)
                        plugins_to_run.append(p)

        # Execute plugins
        logger.info("Executing %d plugins in order", len(plugins_to_run))
        for plugin in plugins_to_run:
            if plugin is None:
                continue

            logger.info("Running plugin: %s", plugin.name)
            result = await self.run_plugin(plugin.name)
            logger.info(
                "Plugin %s: %s - %s",
                plugin.name,
                "PASS" if result.success else "FAIL",
                result.summary,
            )

            # Stop on critical failure, attempt rollback
            if not result.success and any(a.severity.value == "critical" for a in result.actions):
                self.context.log_error(f"Critical failure in {plugin.name}, stopping execution")
                # Attempt rollback for the failed plugin
                try:
                    rollback_result = await plugin.rollback(
                        self.context,
                        self.client,
                        result.actions,
                    )
                    if rollback_result.success:
                        logger.info("Rollback for %s completed", plugin.name)
                    else:
                        logger.warning(
                            "Rollback for %s failed: %s", plugin.name, rollback_result.summary
                        )
                except Exception as e:
                    logger.error("Rollback error for %s: %s", plugin.name, e)
                break

        # Generate report
        report_path = self.reporter.generate_session_report(
            session_id=self.context.session_id,
            context_summary=self.context.get_summary(),
            plugin_results=self._plugin_results,
            api_actions=self.client.action_log,
        )

        summary = self.reporter.generate_quick_summary(self._plugin_results)
        all_passed = all(r.success for _, r in self._plugin_results)

        logger.info(
            "Session %s complete: %d plugins, %s, report: %s",
            self.context.session_id,
            len(self._plugin_results),
            "ALL PASSED" if all_passed else "ISSUES FOUND",
            report_path,
        )

        return {
            "session_id": self.context.session_id,
            "report_path": report_path,
            "summary": summary,
            "scan": scan_result,
            "plugins_run": len(self._plugin_results),
            "all_passed": all_passed,
            "context": self.context.get_summary(),
        }

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.client.close()
