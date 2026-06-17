"""
AutoOps CLI Runner - Entry point for running AutoOps from command line.

Can be invoked directly or via Claude Code slash commands.

Usage:
    # Full autonomous run with sensor specs
    python -m src.autoops.runner --mode configure --sensors DS18B20,SHT31 --actuators relay

    # Health check only
    python -m src.autoops.runner --mode health

    # Debug & fix scan
    python -m src.autoops.runner --mode debug

    # Full workflow (health -> configure -> debug -> verify)
    python -m src.autoops.runner --mode full --sensors DS18B20,PH --zone "Gewächshaus"

    # Real device mode (register existing hardware)
    python -m src.autoops.runner --mode configure --device-mode real --device-id ESP_AABBCCDD
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from typing import Any

import httpx

from .core.agent import AutoOpsAgent
from .core.context import ActuatorSpec, DeviceMode, ESPSpec, SensorSpec

# Sensor type presets with intelligent defaults
SENSOR_PRESETS: dict[str, dict[str, Any]] = {
    "DS18B20": {
        "sensor_type": "temperature",
        "name": "DS18B20 Temperature",
        "interface_type": "ONEWIRE",
        "raw_value": 22.0,
        "unit": "°C",
    },
    "SHT31": {
        "sensor_type": "temperature",
        "name": "SHT31 Temperature",
        "interface_type": "I2C",
        "i2c_address": 0x44,
        "raw_value": 22.0,
        "unit": "°C",
    },
    "SHT31_HUMIDITY": {
        "sensor_type": "humidity",
        "name": "SHT31 Humidity",
        "interface_type": "I2C",
        "i2c_address": 0x44,
        "raw_value": 55.0,
        "unit": "%",
    },
    "PH": {
        "sensor_type": "ph",
        "name": "pH Sensor",
        "interface_type": "ANALOG",
        "raw_value": 6.5,
        "unit": "pH",
    },
    "EC": {
        "sensor_type": "ec",
        "name": "EC Sensor",
        "interface_type": "ANALOG",
        "raw_value": 1.2,
        "unit": "mS/cm",
    },
    "MOISTURE": {
        "sensor_type": "moisture",
        "name": "Soil Moisture",
        "interface_type": "ANALOG",
        "raw_value": 40.0,
        "unit": "%",
    },
    "CO2": {
        "sensor_type": "co2",
        "name": "CO2 Sensor",
        "interface_type": "ANALOG",
        "raw_value": 400.0,
        "unit": "ppm",
    },
    "LIGHT": {
        "sensor_type": "light",
        "name": "Light Sensor",
        "interface_type": "ANALOG",
        "raw_value": 500.0,
        "unit": "lux",
    },
}

ACTUATOR_PRESETS: dict[str, dict[str, Any]] = {
    "RELAY": {"actuator_type": "relay", "name": "Relay"},
    "PUMP": {"actuator_type": "relay", "name": "Water Pump"},
    "VALVE": {"actuator_type": "valve", "name": "Water Valve"},
    "FAN": {"actuator_type": "pwm_fan", "name": "Ventilation Fan"},
    "PWM": {"actuator_type": "pwm_fan", "name": "PWM Output"},
}


def _is_server_reachable(base_url: str, timeout_seconds: float = 2.0) -> bool:
    """Quick reachability probe for the God-Kaiser API."""
    url = base_url.rstrip("/") + "/api/v1/health/live"
    try:
        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False


def _detect_docker_server_url() -> str | None:
    """Resolve backend container IP when localhost does not point to God-Kaiser."""
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "automationone-server",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    ip = result.stdout.strip()
    if not ip:
        return None

    candidate = f"http://{ip}:8000"
    return candidate if _is_server_reachable(candidate) else None


def _resolve_server_url(server_url: str | None) -> str:
    """Resolve best server URL for local host + Docker setups."""
    if server_url:
        return server_url

    env_url = os.environ.get("AUTOOPS_SERVER")
    if env_url:
        return env_url

    default_url = "http://localhost:8000"
    if _is_server_reachable(default_url):
        return default_url

    docker_url = _detect_docker_server_url()
    if docker_url:
        return docker_url

    return default_url


def parse_sensors(sensor_str: str) -> list[SensorSpec]:
    """Parse comma-separated sensor types into SensorSpec list."""
    specs = []
    for raw in sensor_str.split(","):
        name = raw.strip().upper()
        if not name:
            continue

        preset = SENSOR_PRESETS.get(name)
        if preset:
            specs.append(SensorSpec(**preset))
            # SHT31 auto-adds humidity as second value
            if name == "SHT31" and "SHT31_HUMIDITY" in SENSOR_PRESETS:
                specs.append(SensorSpec(**SENSOR_PRESETS["SHT31_HUMIDITY"]))
        else:
            # Unknown sensor - create generic
            specs.append(
                SensorSpec(
                    sensor_type=name.lower(),
                    name=f"{name} Sensor",
                    raw_value=0.0,
                )
            )

    return specs


def parse_actuators(actuator_str: str) -> list[ActuatorSpec]:
    """Parse comma-separated actuator types into ActuatorSpec list."""
    specs = []
    for raw in actuator_str.split(","):
        name = raw.strip().upper()
        if not name:
            continue

        preset = ACTUATOR_PRESETS.get(name)
        if preset:
            specs.append(ActuatorSpec(**preset))
        else:
            specs.append(
                ActuatorSpec(
                    actuator_type=name.lower(),
                    name=f"{name} Actuator",
                )
            )

    return specs


def build_esp_spec(
    sensors: list[SensorSpec],
    actuators: list[ActuatorSpec],
    name: str = "AutoOps ESP",
    zone: str | None = None,
    hardware: str = "ESP32_WROOM",
    device_mode: DeviceMode = DeviceMode.MOCK,
    device_id: str | None = None,
) -> ESPSpec:
    """Build an ESPSpec from parsed components."""
    return ESPSpec(
        name=name,
        device_id=device_id,
        hardware_type=hardware,
        zone_name=zone,
        sensors=sensors,
        actuators=actuators,
        auto_heartbeat=device_mode == DeviceMode.MOCK,  # Only auto-heartbeat for mocks
        heartbeat_interval=60,
        device_mode=device_mode,
    )


async def run_autoops(
    mode: str = "full",
    server_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    sensors_str: str = "",
    actuators_str: str = "",
    zone: str | None = None,
    esp_name: str = "AutoOps ESP",
    hardware: str = "ESP32_WROOM",
    dry_run: bool = False,
    verbose: bool = True,
    device_mode: str = "mock",
    device_id: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Main entry point for AutoOps execution.

    Args:
        mode: "full", "health", "configure", "debug"
        server_url: God-Kaiser server URL (env: AUTOOPS_SERVER)
        username: Auth username (env: AUTOOPS_USER)
        password: Auth password (env: AUTOOPS_PASSWORD)
        sensors_str: Comma-separated sensor types (DS18B20,SHT31,PH)
        actuators_str: Comma-separated actuator types (RELAY,PUMP,FAN)
        zone: Zone name to assign
        esp_name: Name for the created ESP
        hardware: Hardware type (ESP32_WROOM, XIAO_ESP32_C3)
        dry_run: If True, only plan without executing
        verbose: Verbose output
        device_mode: "mock", "real", or "hybrid"
        device_id: Specific device ID (for real mode)
        max_retries: Max API retry attempts

    Returns:
        Session result dict
    """
    # Resolve from environment with correct defaults
    resolved_url = _resolve_server_url(server_url)
    resolved_user = username or os.environ.get("AUTOOPS_USER", "admin")
    resolved_pass = password or os.environ.get("AUTOOPS_PASSWORD", "admin123")

    agent = AutoOpsAgent(
        server_url=resolved_url,
        username=resolved_user,
        password=resolved_pass,
        dry_run=dry_run,
        verbose=verbose,
        device_mode=device_mode,
        max_retries=max_retries,
    )

    try:
        # Initialize
        init_result = await agent.initialize()
        if verbose:
            print(f"[AutoOps] Session: {init_result['session_id']}")
            print(f"[AutoOps] Plugins: {len(init_result['plugins'])} discovered")
            print(f"[AutoOps] Auth: {init_result['auth_status']}")
            print(f"[AutoOps] Health: {init_result['health_status']}")
            print()

        # Build ESP specs if configuring
        if mode in ("full", "configure") and (sensors_str or device_id):
            sensors = parse_sensors(sensors_str) if sensors_str else []
            actuators = parse_actuators(actuators_str) if actuators_str else []
            spec = build_esp_spec(
                sensors,
                actuators,
                name=esp_name,
                zone=zone,
                hardware=hardware,
                device_mode=DeviceMode(device_mode),
                device_id=device_id,
            )
            agent.context.esp_specs = [spec]

            if verbose:
                print(f"[AutoOps] ESP Config: {esp_name}")
                print(f"[AutoOps]   Mode: {device_mode}")
                if device_id:
                    print(f"[AutoOps]   Device ID: {device_id}")
                print(f"[AutoOps]   Sensors: {[s.sensor_type for s in sensors]}")
                print(f"[AutoOps]   Actuators: {[a.actuator_type for a in actuators]}")
                if zone:
                    print(f"[AutoOps]   Zone: {zone}")
                print()

        # Determine plugins based on mode
        plugins = None
        if mode == "health":
            plugins = ["health_check"]
        elif mode == "configure":
            plugins = ["health_check", "esp_configurator"]
        elif mode == "debug":
            plugins = ["health_check", "debug_fix"]
        # mode == "full" → runs all plugins (default)

        # Execute
        result = await agent.run_autonomous(plugins=plugins)

        if verbose:
            print()
            print(result.get("summary", ""))
            print()
            print(f"[AutoOps] Report: {result.get('report_path', 'N/A')}")

        return result

    finally:
        await agent.cleanup()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AutoOps - Autonomous Operations Agent for AutomationOne"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "health", "configure", "debug"],
        default="full",
        help="Operation mode",
    )
    parser.add_argument(
        "--server",
        default=None,
        help="God-Kaiser server URL (env: AUTOOPS_SERVER, default: http://localhost:8000)",
    )
    parser.add_argument(
        "--username", default=None, help="Auth username (env: AUTOOPS_USER, default: admin)"
    )
    parser.add_argument("--password", default=None, help="Auth password (env: AUTOOPS_PASSWORD)")
    parser.add_argument(
        "--sensors",
        default="",
        help="Comma-separated sensor types (DS18B20,SHT31,PH,EC,MOISTURE,CO2,LIGHT)",
    )
    parser.add_argument(
        "--actuators", default="", help="Comma-separated actuator types (RELAY,PUMP,VALVE,FAN,PWM)"
    )
    parser.add_argument("--zone", default=None, help="Zone name")
    parser.add_argument("--esp-name", default="AutoOps ESP", help="ESP device name")
    parser.add_argument(
        "--hardware",
        default="ESP32_WROOM",
        choices=["ESP32_WROOM", "XIAO_ESP32_C3"],
        help="Hardware type",
    )
    parser.add_argument(
        "--device-mode",
        default="mock",
        choices=["mock", "real", "hybrid"],
        help="Device mode: mock (default), real (hardware), hybrid (mix)",
    )
    parser.add_argument(
        "--device-id", default=None, help="Specific device ID (for real mode, e.g. ESP_AABBCCDD)"
    )
    parser.add_argument(
        "--max-retries", type=int, default=3, help="Max API retry attempts (default: 3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no execution")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    result = asyncio.run(
        run_autoops(
            mode=args.mode,
            server_url=args.server,
            username=args.username,
            password=args.password,
            sensors_str=args.sensors,
            actuators_str=args.actuators,
            zone=args.zone,
            esp_name=args.esp_name,
            hardware=args.hardware,
            dry_run=args.dry_run,
            verbose=not args.quiet,
            device_mode=args.device_mode,
            device_id=args.device_id,
            max_retries=args.max_retries,
        )
    )

    if args.json:
        # Clean result for JSON output (remove non-serializable items)
        clean = {k: v for k, v in result.items() if k != "summary"}  # summary is already printed
        print(json.dumps(clean, indent=2, default=str))

    sys.exit(0 if result.get("all_passed", False) else 1)


if __name__ == "__main__":
    main()
