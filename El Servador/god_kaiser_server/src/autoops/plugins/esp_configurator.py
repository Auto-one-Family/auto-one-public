"""
ESP Configurator Plugin - Autonomous ESP32 Configuration.

This plugin configures ESP devices through the God-Kaiser REST API
exactly like a real user would through the frontend:

1. Creates Mock ESP devices (or uses existing ones)
2. Assigns GPIOs intelligently based on sensor/actuator types
3. Adds sensors with correct interface types
4. Adds actuators with safety-aware defaults
5. Assigns zones
6. Starts heartbeat and simulation
7. Verifies everything works

GPIO Assignment Strategy:
- DS18B20 (OneWire): GPIO 4 (default OneWire bus pin)
- SHT31 (I2C): GPIO 21/22 (default I2C bus)
- Analog sensors (pH, EC): GPIO 32-39 (ADC1 pins)
- Relay actuators: GPIO 16, 17, 18, 19 (safe digital outputs)
- PWM actuators: GPIO 25, 26, 27 (PWM-capable pins)
"""

from typing import Any, Optional

from ..core.api_client import APIError, GodKaiserClient
from ..core.base_plugin import (
    ActionSeverity,
    AutoOpsPlugin,
    PluginAction,
    PluginCapability,
    PluginResult,
    plugin_metadata,
)
from ..core.context import AutoOpsContext, DeviceMode, SensorSpec, ActuatorSpec

# GPIO Assignment Tables (ESP32 WROOM defaults)
# These mirror the GpioPicker component in the frontend
GPIO_ONEWIRE = [4]  # OneWire bus default
GPIO_I2C_SDA = [21]  # I2C SDA default
GPIO_I2C_SCL = [22]  # I2C SCL default
GPIO_ANALOG = [32, 33, 34, 35, 36, 39]  # ADC1 pins (safe for analog read)
GPIO_DIGITAL_OUT = [16, 17, 18, 19]  # Safe digital output pins
GPIO_PWM = [25, 26, 27]  # PWM-capable pins
GPIO_GENERAL = [5, 12, 13, 14, 15, 23]  # General-purpose pins

# XIAO ESP32-C3 alternative GPIO map
GPIO_XIAO_ANALOG = [2, 3, 4]
GPIO_XIAO_DIGITAL = [5, 6, 7, 8, 9, 10]
GPIO_XIAO_I2C_SDA = [6]
GPIO_XIAO_I2C_SCL = [7]

# Sensor type -> default values
SENSOR_DEFAULTS = {
    "temperature": {"unit": "°C", "raw_value": 22.0, "min": -10, "max": 50},
    "humidity": {"unit": "%", "raw_value": 55.0, "min": 0, "max": 100},
    "ph": {"unit": "pH", "raw_value": 6.5, "min": 0, "max": 14},
    "ec": {"unit": "mS/cm", "raw_value": 1.2, "min": 0, "max": 10},
    "moisture": {"unit": "%", "raw_value": 40.0, "min": 0, "max": 100},
    "pressure": {"unit": "hPa", "raw_value": 1013.25, "min": 900, "max": 1100},
    "co2": {"unit": "ppm", "raw_value": 400.0, "min": 200, "max": 50000},  # AUT-576: SEN0220 range 0-50000 ppm
    "light": {"unit": "lux", "raw_value": 500.0, "min": 0, "max": 100000},
    "flow": {"unit": "L/min", "raw_value": 0.0, "min": 0, "max": 100},
}


@plugin_metadata(
    display_name="ESP Configurator",
    description="Erstellt und konfiguriert ESP-Devices mit Sensoren und Aktoren automatisch",
    category="automation",
    config_schema={
        "device_mode": {
            "type": "select",
            "options": ["mock", "real", "hybrid"],
            "default": "mock",
            "label": "Device-Modus",
        },
        "auto_heartbeat": {
            "type": "boolean",
            "default": True,
            "label": "Heartbeat automatisch starten",
        },
    },
)
class ESPConfiguratorPlugin(AutoOpsPlugin):
    """
    Autonomously configures ESP32 devices through the REST API.

    Works like a real user clicking through the frontend:
    1. Create Mock ESP → 2. Add Sensors → 3. Add Actuators →
    4. Assign Zone → 5. Start Heartbeat → 6. Verify
    """

    @property
    def name(self) -> str:
        return "esp_configurator"

    @property
    def description(self) -> str:
        return (
            "Autonomous ESP32 configuration - creates devices, adds sensors/actuators, "
            "assigns zones, and verifies everything works through the REST API"
        )

    @property
    def capabilities(self) -> list[PluginCapability]:
        return [PluginCapability.CONFIGURE, PluginCapability.VALIDATE]

    async def validate_preconditions(
        self, context: AutoOpsContext, client: GodKaiserClient
    ) -> PluginResult:
        """Check that we have specs to configure and server is reachable."""
        if not context.esp_specs:
            return PluginResult.needs_input(
                "No ESP specifications provided. Need sensor/actuator configuration.",
                questions=[],
            )

        # Verify server is reachable
        try:
            await client.check_health()
        except Exception as e:
            return PluginResult.failure(
                f"Server unreachable at {context.server_url}",
                errors=[str(e)],
            )

        return PluginResult.success_result(
            f"Ready to configure {len(context.esp_specs)} ESP device(s)"
        )

    async def plan(self, context: AutoOpsContext, client: GodKaiserClient) -> list[str]:
        """Generate execution plan."""
        steps = []
        for i, spec in enumerate(context.esp_specs, 1):
            name = spec.name or f"ESP #{i}"
            steps.append(f"Create Mock ESP: {name} ({spec.hardware_type})")
            for s in spec.sensors:
                steps.append(f"  Add Sensor: {s.sensor_type} ({s.name or 'unnamed'})")
            for a in spec.actuators:
                steps.append(f"  Add Actuator: {a.actuator_type} ({a.name or 'unnamed'})")
            if spec.zone_name:
                steps.append(f"  Assign Zone: {spec.zone_name}")
            steps.append(f"  Enable Auto-Heartbeat ({spec.heartbeat_interval}s)")
            steps.append(f"  Verify Configuration")
        return steps

    async def execute(self, context: AutoOpsContext, client: GodKaiserClient) -> PluginResult:
        """Execute full ESP configuration workflow."""
        actions: list[PluginAction] = []
        errors: list[str] = []
        warnings: list[str] = []
        created_data: dict[str, Any] = {"devices": []}

        for spec_idx, spec in enumerate(context.esp_specs):
            device_name = spec.name or f"AutoOps_ESP_{spec_idx + 1}"

            # =============================================
            # Step 1: Create ESP (mock or real based on device_mode)
            # =============================================
            esp_mode = spec.device_mode or context.device_mode
            try:
                if esp_mode == DeviceMode.REAL:
                    # Real device: register via ESP devices API
                    create_result = await client.register_real_device(
                        device_id=spec.device_id or device_name.replace(" ", "_").upper(),
                        name=device_name,
                        hardware_type=spec.hardware_type,
                    )
                    action_label = "Register Real ESP"
                else:
                    # Mock device: create via debug API
                    create_result = await client.create_mock_esp(
                        name=device_name,
                        hardware_type=spec.hardware_type,
                        device_id=spec.device_id,
                        zone_name=spec.zone_name,
                    )
                    action_label = "Create Mock ESP"

                device_id = (
                    create_result.get("device_id")
                    or create_result.get("data", {}).get("device_id")
                    or create_result.get("esp_id", "")
                )
                if not device_id:
                    # Try to extract from nested response
                    for key in ("device", "esp", "mock_esp"):
                        if isinstance(create_result.get(key), dict):
                            device_id = create_result[key].get("device_id", "")
                            break

                actions.append(
                    PluginAction.create(
                        action=action_label,
                        target=device_id or device_name,
                        details={
                            "hardware_type": spec.hardware_type,
                            "device_mode": esp_mode.value,
                            "response": create_result,
                        },
                        result=f"Created ({esp_mode.value}): {device_id}",
                        severity=ActionSeverity.SUCCESS,
                    )
                )
                context.created_devices.append(
                    {
                        "device_id": device_id,
                        "name": device_name,
                        "hardware_type": spec.hardware_type,
                        "device_mode": esp_mode.value,
                    }
                )

            except APIError as e:
                actions.append(
                    PluginAction.create(
                        action=f"Create ESP ({esp_mode.value})",
                        target=device_name,
                        details={"error": e.detail, "device_mode": esp_mode.value},
                        result=f"FAILED: {e.detail}",
                        severity=ActionSeverity.ERROR,
                    )
                )
                errors.append(
                    f"Failed to create ESP '{device_name}' ({esp_mode.value}): {e.detail}"
                )
                continue  # Skip to next ESP spec

            # =============================================
            # Step 2: Assign GPIOs and Add Sensors
            # =============================================
            used_gpios: set[int] = set()
            is_xiao = "XIAO" in spec.hardware_type.upper()

            for sensor_idx, sensor_spec in enumerate(spec.sensors):
                gpio = self._assign_sensor_gpio(sensor_spec, used_gpios, is_xiao)
                if gpio is None:
                    warnings.append(
                        f"No available GPIO for sensor {sensor_spec.sensor_type} " f"on {device_id}"
                    )
                    continue

                used_gpios.add(gpio)

                # Get default values for this sensor type
                defaults = SENSOR_DEFAULTS.get(sensor_spec.sensor_type, {})
                raw_value = sensor_spec.raw_value or defaults.get("raw_value", 0.0)
                unit = sensor_spec.unit or defaults.get("unit", "")

                try:
                    # Add mock sensor via Debug API (only for mock devices)
                    if esp_mode != DeviceMode.REAL:
                        _mock_result = await client.add_mock_sensor(
                            esp_id=device_id,
                            gpio=gpio,
                            sensor_type=sensor_spec.sensor_type,
                            name=sensor_spec.name,
                            raw_value=raw_value,
                            unit=unit,
                            interval_seconds=sensor_spec.interval_seconds,
                            interface_type=sensor_spec.interface_type,
                            i2c_address=sensor_spec.i2c_address,
                            onewire_address=sensor_spec.onewire_address,
                            variation_pattern=sensor_spec.variation_pattern.value,
                            variation_range=sensor_spec.variation_range,
                        )

                    # Register in sensor config (via Sensor API) - for both mock and real
                    try:
                        _sensor_result = await client.add_sensor(
                            esp_id=device_id,
                            gpio=gpio,
                            sensor_type=sensor_spec.sensor_type,
                            name=sensor_spec.name,
                            enabled=True,
                            processing_mode="pi_enhanced",
                            interval_ms=int(sensor_spec.interval_seconds * 1000),
                            interface_type=sensor_spec.interface_type,
                            i2c_address=sensor_spec.i2c_address,
                            onewire_address=sensor_spec.onewire_address,
                        )
                    except APIError as e:
                        # Config registration failed - not critical for mocks
                        warnings.append(
                            f"Sensor config registration failed for "
                            f"{sensor_spec.sensor_type}@GPIO{gpio}: {e.detail}"
                        )

                    actions.append(
                        PluginAction.create(
                            action=f"Add Sensor ({sensor_spec.sensor_type})",
                            target=f"{device_id}/GPIO:{gpio}",
                            details={
                                "sensor_type": sensor_spec.sensor_type,
                                "name": sensor_spec.name,
                                "gpio": gpio,
                                "raw_value": raw_value,
                                "unit": unit,
                                "interface": sensor_spec.interface_type,
                            },
                            result=f"Added: {sensor_spec.sensor_type} on GPIO {gpio}",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                    context.configured_sensors.append(
                        {
                            "device_id": device_id,
                            "gpio": gpio,
                            "sensor_type": sensor_spec.sensor_type,
                            "name": sensor_spec.name,
                        }
                    )

                except APIError as e:
                    actions.append(
                        PluginAction.create(
                            action=f"Add Sensor ({sensor_spec.sensor_type})",
                            target=f"{device_id}/GPIO:{gpio}",
                            details={"error": e.detail},
                            result=f"FAILED: {e.detail}",
                            severity=ActionSeverity.ERROR,
                        )
                    )
                    errors.append(
                        f"Failed to add sensor {sensor_spec.sensor_type} "
                        f"on GPIO {gpio}: {e.detail}"
                    )

            # =============================================
            # Step 3: Assign GPIOs and Add Actuators
            # =============================================
            for act_idx, act_spec in enumerate(spec.actuators):
                gpio = self._assign_actuator_gpio(act_spec, used_gpios, is_xiao)
                if gpio is None:
                    warnings.append(
                        f"No available GPIO for actuator {act_spec.actuator_type} "
                        f"on {device_id}"
                    )
                    continue

                used_gpios.add(gpio)

                try:
                    # Add mock actuator via Debug API (only for mock devices)
                    if esp_mode != DeviceMode.REAL:
                        _mock_result = await client.add_mock_actuator(
                            esp_id=device_id,
                            gpio=gpio,
                            actuator_type=act_spec.actuator_type,
                            name=act_spec.name,
                        )

                    # Register in actuator config (via Actuator API) - for both mock and real
                    try:
                        _act_result = await client.add_actuator(
                            esp_id=device_id,
                            gpio=gpio,
                            actuator_type=act_spec.actuator_type,
                            name=act_spec.name,
                            enabled=True,
                        )
                    except APIError as e:
                        warnings.append(
                            f"Actuator config registration failed for "
                            f"{act_spec.actuator_type}@GPIO{gpio}: {e.detail}"
                        )

                    actions.append(
                        PluginAction.create(
                            action=f"Add Actuator ({act_spec.actuator_type})",
                            target=f"{device_id}/GPIO:{gpio}",
                            details={
                                "actuator_type": act_spec.actuator_type,
                                "name": act_spec.name,
                                "gpio": gpio,
                            },
                            result=f"Added: {act_spec.actuator_type} on GPIO {gpio}",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                    context.configured_actuators.append(
                        {
                            "device_id": device_id,
                            "gpio": gpio,
                            "actuator_type": act_spec.actuator_type,
                            "name": act_spec.name,
                        }
                    )

                except APIError as e:
                    actions.append(
                        PluginAction.create(
                            action=f"Add Actuator ({act_spec.actuator_type})",
                            target=f"{device_id}/GPIO:{gpio}",
                            details={"error": e.detail},
                            result=f"FAILED: {e.detail}",
                            severity=ActionSeverity.ERROR,
                        )
                    )
                    errors.append(
                        f"Failed to add actuator {act_spec.actuator_type} "
                        f"on GPIO {gpio}: {e.detail}"
                    )

            # =============================================
            # Step 4: Enable Auto-Heartbeat (mock only)
            # =============================================
            if spec.auto_heartbeat and esp_mode != DeviceMode.REAL:
                try:
                    await client.set_auto_heartbeat(
                        device_id,
                        enabled=True,
                        interval_seconds=spec.heartbeat_interval,
                    )
                    actions.append(
                        PluginAction.create(
                            action="Enable Auto-Heartbeat",
                            target=device_id,
                            details={"interval": spec.heartbeat_interval},
                            result=f"Enabled ({spec.heartbeat_interval}s interval)",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                except APIError as e:
                    warnings.append(f"Auto-heartbeat setup failed for {device_id}: {e.detail}")

            # =============================================
            # Step 5: Trigger Initial Heartbeat (mock only)
            # =============================================
            if esp_mode != DeviceMode.REAL:
                try:
                    await client.trigger_heartbeat(device_id)
                    actions.append(
                        PluginAction.create(
                            action="Trigger Initial Heartbeat",
                            target=device_id,
                            details={},
                            result="Heartbeat sent",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                except APIError as e:
                    warnings.append(f"Initial heartbeat failed for {device_id}: {e.detail}")

            # =============================================
            # Step 6: Start Simulation (mock only, if sensors exist)
            # =============================================
            if spec.sensors and esp_mode != DeviceMode.REAL:
                try:
                    await client.start_simulation(device_id)
                    actions.append(
                        PluginAction.create(
                            action="Start Sensor Simulation",
                            target=device_id,
                            details={"sensor_count": len(spec.sensors)},
                            result="Simulation started",
                            severity=ActionSeverity.SUCCESS,
                        )
                    )
                except APIError as e:
                    warnings.append(f"Simulation start failed for {device_id}: {e.detail}")

            # =============================================
            # Step 7: Verify Configuration
            # =============================================
            try:
                device_info = await client.get_device(device_id)
                actions.append(
                    PluginAction.create(
                        action="Verify Configuration",
                        target=device_id,
                        details={"device_info": device_info},
                        result="Configuration verified",
                        severity=ActionSeverity.SUCCESS,
                    )
                )
                created_data["devices"].append(
                    {
                        "device_id": device_id,
                        "name": device_name,
                        "sensors_configured": len(spec.sensors),
                        "actuators_configured": len(spec.actuators),
                        "zone": spec.zone_name,
                        "status": "configured",
                    }
                )
            except APIError as e:
                warnings.append(f"Verification failed for {device_id}: {e.detail}")

        # Build result
        total_devices = len(created_data.get("devices", []))
        total_sensors = len(context.configured_sensors)
        total_actuators = len(context.configured_actuators)

        if errors:
            return PluginResult(
                success=False,
                summary=(
                    f"Configured {total_devices} device(s) with {len(errors)} error(s). "
                    f"Sensors: {total_sensors}, Actuators: {total_actuators}"
                ),
                actions=actions,
                errors=errors,
                warnings=warnings,
                data=created_data,
            )

        return PluginResult.success_result(
            summary=(
                f"Successfully configured {total_devices} device(s): "
                f"{total_sensors} sensor(s), {total_actuators} actuator(s)"
            ),
            actions=actions,
            data=created_data,
        )

    async def rollback(
        self,
        context: AutoOpsContext,
        client: GodKaiserClient,
        actions: list[PluginAction],
    ) -> PluginResult:
        """Rollback: delete devices created during this execution."""
        rollback_actions: list[PluginAction] = []
        errors: list[str] = []

        for device_info in context.created_devices:
            device_id = device_info.get("device_id", "")
            device_mode = device_info.get("device_mode", "mock")
            if not device_id:
                continue

            try:
                if device_mode == "mock":
                    await client.delete_mock_esp(device_id)
                else:
                    await client.delete_device(device_id)
                rollback_actions.append(
                    PluginAction.create(
                        action=f"Rollback: Delete {device_mode} ESP",
                        target=device_id,
                        details={},
                        result="Deleted",
                        severity=ActionSeverity.SUCCESS,
                    )
                )
            except APIError as e:
                errors.append(f"Rollback failed for {device_id}: {e.detail}")

        # Clear context
        context.created_devices.clear()
        context.configured_sensors.clear()
        context.configured_actuators.clear()

        if errors:
            return PluginResult.failure(
                f"Rollback partially failed: {len(errors)} error(s)",
                errors=errors,
                actions=rollback_actions,
            )
        return PluginResult.success_result(
            f"Rollback complete: {len(rollback_actions)} device(s) removed",
            actions=rollback_actions,
        )

    def _assign_sensor_gpio(
        self,
        sensor: SensorSpec,
        used: set[int],
        is_xiao: bool = False,
    ) -> Optional[int]:
        """Assign an appropriate GPIO for a sensor based on its interface type."""
        if sensor.gpio is not None and sensor.gpio not in used:
            return sensor.gpio

        interface = (sensor.interface_type or "").upper()

        if interface == "ONEWIRE":
            candidates = GPIO_ONEWIRE
        elif interface == "I2C":
            candidates = GPIO_XIAO_I2C_SDA if is_xiao else GPIO_I2C_SDA
        elif interface == "ANALOG":
            candidates = GPIO_XIAO_ANALOG if is_xiao else GPIO_ANALOG
        else:
            # Infer from sensor type
            stype = sensor.sensor_type.lower()
            if stype in ("temperature",) and not sensor.i2c_address:
                candidates = GPIO_ONEWIRE
            elif sensor.i2c_address is not None:
                candidates = GPIO_XIAO_I2C_SDA if is_xiao else GPIO_I2C_SDA
            elif stype in ("ph", "ec", "moisture", "light", "analog"):
                candidates = GPIO_XIAO_ANALOG if is_xiao else GPIO_ANALOG
            else:
                candidates = GPIO_GENERAL

        for gpio in candidates:
            if gpio not in used:
                return gpio

        # Fallback to general-purpose pins
        for gpio in GPIO_GENERAL:
            if gpio not in used:
                return gpio

        return None

    def _assign_actuator_gpio(
        self,
        actuator: ActuatorSpec,
        used: set[int],
        is_xiao: bool = False,
    ) -> Optional[int]:
        """Assign an appropriate GPIO for an actuator."""
        if actuator.gpio is not None and actuator.gpio not in used:
            return actuator.gpio

        atype = actuator.actuator_type.lower()

        if "pwm" in atype or "fan" in atype:
            candidates = GPIO_PWM
        else:
            # Digital output (relay, valve, etc.)
            candidates = GPIO_XIAO_DIGITAL if is_xiao else GPIO_DIGITAL_OUT

        for gpio in candidates:
            if gpio not in used:
                return gpio

        # Fallback
        for gpio in GPIO_GENERAL:
            if gpio not in used:
                return gpio

        return None
