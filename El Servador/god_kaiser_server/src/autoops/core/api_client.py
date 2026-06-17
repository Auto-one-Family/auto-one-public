"""
AutoOps API Client - REST API wrapper for God-Kaiser Server.

Provides a typed, async HTTP client that mirrors what a user would do
through the frontend. Every method maps to a frontend action.

Features:
- Automatic retry with exponential backoff on transient failures
- Full action logging for session documentation
- Covers all God-Kaiser API endpoints including zones, subzones, sequences
- Proper structured logging via server's logging framework

Usage:
    client = GodKaiserClient("http://localhost:8000")
    await client.authenticate("admin", "admin123")

    esp = await client.create_mock_esp("Test ESP", hardware_type="ESP32_WROOM")
    sensor = await client.add_sensor(esp["device_id"], gpio=4, sensor_type="DS18B20")
"""

import asyncio
import logging
import secrets
from typing import Any, Optional

import httpx

from .base_plugin import ActionSeverity, PluginAction


def _get_logger(name: str) -> logging.Logger:
    """Get a logger, preferring the server's logging_config if available."""
    try:
        from ...core.logging_config import get_logger

        return get_logger(name)
    except (ImportError, ValueError):
        return logging.getLogger(name)


logger = _get_logger("autoops.api_client")


class APIError(Exception):
    """Raised when an API call fails."""

    def __init__(self, status_code: int, detail: str, endpoint: str):
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(f"API {status_code} at {endpoint}: {detail}")


class GodKaiserClient:
    """
    Async HTTP client for the God-Kaiser REST API.

    Mirrors all frontend API actions so AutoOps can operate
    like a real user. Every call is logged for documentation.
    Includes automatic retry with exponential backoff for transient failures.
    """

    RETRYABLE_STATUS_CODES = {502, 503, 504, 429}

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._action_log: list[PluginAction] = []

    @property
    def action_log(self) -> list[PluginAction]:
        """Get all logged API actions."""
        return list(self._action_log)

    def clear_action_log(self) -> None:
        """Clear the action log."""
        self._action_log.clear()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        params: dict | None = None,
        action_name: str = "",
        target: str = "",
        expect_json: bool = True,
    ) -> dict[str, Any]:
        """Make an API request with full logging and automatic retry.

        Args:
            expect_json: If False, wraps non-JSON responses in {"raw_text": ...}
                         instead of raising JSONDecodeError.
        """
        client = await self._ensure_client()
        url = f"/api{endpoint}" if not endpoint.startswith("/api") else endpoint
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                    headers=self._headers(),
                )

                # Log the action
                severity = (
                    ActionSeverity.SUCCESS if response.status_code < 400 else ActionSeverity.ERROR
                )
                self._action_log.append(
                    PluginAction.create(
                        action=action_name or f"{method} {endpoint}",
                        target=target or endpoint,
                        details={
                            "request_body": json_data if json_data else {},
                            "params": params if params else {},
                            "attempt": attempt + 1 if attempt > 0 else None,
                        },
                        result=f"HTTP {response.status_code}",
                        severity=severity,
                        api_endpoint=url,
                        api_method=method,
                        api_response_code=response.status_code,
                    )
                )

                # Retry on transient server errors
                if (
                    response.status_code in self.RETRYABLE_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        "Retryable HTTP %d at %s, attempt %d/%d, waiting %.1fs",
                        response.status_code,
                        url,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code >= 400:
                    detail = response.text
                    try:
                        detail = response.json().get("detail", response.text)
                    except Exception:
                        pass
                    raise APIError(response.status_code, str(detail), url)

                if response.status_code == 204:
                    return {}

                # Handle non-JSON responses (e.g. Prometheus metrics)
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()

                if not expect_json:
                    return {"raw_text": response.text, "content_type": content_type}

                # Try JSON parsing, fallback to raw text wrapper
                try:
                    return response.json()
                except Exception:
                    return {"raw_text": response.text, "content_type": content_type}

            except httpx.RequestError as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        "Connection error at %s: %s, attempt %d/%d, waiting %.1fs",
                        url,
                        e,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                self._action_log.append(
                    PluginAction.create(
                        action=action_name or f"{method} {endpoint}",
                        target=target or endpoint,
                        details={"error": str(e), "attempts": attempt + 1},
                        result=f"Connection error after {attempt + 1} attempts: {e}",
                        severity=ActionSeverity.ERROR,
                        api_endpoint=url,
                        api_method=method,
                    )
                )
                raise APIError(0, f"Connection error after {attempt + 1} attempts: {e}", url) from e

        # Should not reach here, but safety fallback
        raise APIError(0, f"Max retries exceeded: {last_error}", url)

    # =========================================================================
    # Authentication
    # =========================================================================

    async def authenticate(self, username: str, password: str) -> dict[str, Any]:
        """Login and store the JWT token."""
        result = await self._request(
            "POST",
            "/v1/auth/login",
            json_data={"username": username, "password": password},
            action_name="Authenticate",
            target=f"user:{username}",
        )
        # Token may be at top level or nested under "tokens"
        tokens = result.get("tokens", {})
        self._token = tokens.get("access_token", "") or result.get("access_token", "")
        return result

    async def check_health(self) -> dict[str, Any]:
        """Check server health (no auth required)."""
        return await self._request(
            "GET",
            "/v1/health/",
            action_name="Health Check",
            target="server",
        )

    # =========================================================================
    # ESP Device Management (mirrors frontend esp.ts API)
    # =========================================================================

    async def list_devices(self, include_offline: bool = True) -> dict[str, Any]:
        """List all ESP devices."""
        return await self._request(
            "GET",
            "/v1/esp/devices",
            params={"include_offline": include_offline},
            action_name="List ESP Devices",
            target="all_devices",
        )

    async def get_device(self, esp_id: str) -> dict[str, Any]:
        """Get details of a specific ESP device."""
        return await self._request(
            "GET",
            f"/v1/esp/devices/{esp_id}",
            action_name="Get ESP Device",
            target=esp_id,
        )

    async def create_device(self, device_data: dict[str, Any]) -> dict[str, Any]:
        """Register a new ESP device."""
        return await self._request(
            "POST",
            "/v1/esp/devices",
            json_data=device_data,
            action_name="Create ESP Device",
            target=device_data.get("device_id", "new_device"),
        )

    async def update_device(self, esp_id: str, update_data: dict[str, Any]) -> dict[str, Any]:
        """Update an ESP device."""
        return await self._request(
            "PATCH",
            f"/v1/esp/devices/{esp_id}",
            json_data=update_data,
            action_name="Update ESP Device",
            target=esp_id,
        )

    async def delete_device(self, esp_id: str) -> dict[str, Any]:
        """Delete an ESP device."""
        return await self._request(
            "DELETE",
            f"/v1/esp/devices/{esp_id}",
            action_name="Delete ESP Device",
            target=esp_id,
        )

    async def get_gpio_status(self, esp_id: str) -> dict[str, Any]:
        """Get GPIO pin availability for a device."""
        return await self._request(
            "GET",
            f"/v1/esp/devices/{esp_id}/gpio-status",
            action_name="Get GPIO Status",
            target=esp_id,
        )

    # =========================================================================
    # Mock ESP Management (mirrors frontend debug.ts API)
    # =========================================================================

    async def create_mock_esp(
        self,
        name: str = "",
        hardware_type: str = "ESP32_WROOM",
        device_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        sensors: Optional[list[dict[str, Any]]] = None,
        actuators: Optional[list[dict[str, Any]]] = None,
        auto_heartbeat: bool = False,
        heartbeat_interval_seconds: int = 60,
    ) -> dict[str, Any]:
        """Create a mock ESP device (like clicking 'Add Mock ESP' in frontend).

        The API requires esp_id in format ESP_XXXXXX or MOCK_XXXXXX.
        If device_id is not provided, a MOCK_XXXXXX ID is auto-generated.
        """
        esp_id = device_id or f"MOCK_{secrets.token_hex(4).upper()[:6]}"
        data: dict[str, Any] = {"esp_id": esp_id}
        if zone_name:
            data["zone_name"] = zone_name
        if sensors:
            data["sensors"] = sensors
        if actuators:
            data["actuators"] = actuators
        if auto_heartbeat:
            data["auto_heartbeat"] = True
            data["heartbeat_interval_seconds"] = heartbeat_interval_seconds
        return await self._request(
            "POST",
            "/v1/debug/mock-esp",
            json_data=data,
            action_name="Create Mock ESP",
            target=esp_id,
        )

    async def list_mock_esps(self) -> dict[str, Any]:
        """List all mock ESPs."""
        return await self._request(
            "GET",
            "/v1/debug/mock-esp",
            action_name="List Mock ESPs",
            target="all_mocks",
        )

    async def delete_mock_esp(self, esp_id: str) -> dict[str, Any]:
        """Delete a mock ESP."""
        return await self._request(
            "DELETE",
            f"/v1/debug/mock-esp/{esp_id}",
            action_name="Delete Mock ESP",
            target=esp_id,
        )

    async def trigger_heartbeat(self, esp_id: str) -> dict[str, Any]:
        """Trigger a heartbeat for a mock ESP."""
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/heartbeat",
            action_name="Trigger Heartbeat",
            target=esp_id,
        )

    async def set_auto_heartbeat(
        self, esp_id: str, enabled: bool, interval_seconds: int = 60
    ) -> dict[str, Any]:
        """Configure auto-heartbeat for a mock ESP.

        The server endpoint uses Query parameters, not JSON body.
        """
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/auto-heartbeat",
            params={"enabled": enabled, "interval_seconds": interval_seconds},
            action_name="Set Auto-Heartbeat",
            target=esp_id,
        )

    # =========================================================================
    # Sensor Management (mirrors frontend sensors.ts API)
    # =========================================================================

    async def add_sensor(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        name: Optional[str] = None,
        enabled: bool = True,
        processing_mode: str = "pi_enhanced",
        interval_ms: int = 30000,
        interface_type: Optional[str] = None,
        i2c_address: Optional[int] = None,
        onewire_address: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add or update a sensor config via POST /v1/sensors/{esp_id}/{gpio}."""
        data: dict[str, Any] = {
            "sensor_type": sensor_type,
            "enabled": enabled,
            "interval_ms": interval_ms,
        }
        if name:
            data["name"] = name
        if interface_type:
            data["interface_type"] = interface_type
        if i2c_address is not None:
            data["i2c_address"] = i2c_address
        if onewire_address:
            data["onewire_address"] = onewire_address

        return await self._request(
            "POST",
            f"/v1/sensors/{esp_id}/{gpio}",
            json_data=data,
            action_name=f"Add Sensor ({sensor_type})",
            target=f"{esp_id}/gpio:{gpio}",
        )

    async def get_sensor(self, esp_id: str, gpio: int) -> dict[str, Any]:
        """Get sensor configuration."""
        return await self._request(
            "GET",
            f"/v1/sensors/{esp_id}/{gpio}",
            action_name="Get Sensor Config",
            target=f"{esp_id}/gpio:{gpio}",
        )

    async def list_sensors(self, esp_id: Optional[str] = None) -> dict[str, Any]:
        """List all sensors, optionally filtered by ESP."""
        params = {}
        if esp_id:
            params["esp_id"] = esp_id
        return await self._request(
            "GET",
            "/v1/sensors/",
            params=params,
            action_name="List Sensors",
            target=esp_id or "all",
        )

    async def delete_sensor(self, esp_id: str, config_id: str) -> dict[str, Any]:
        """Delete a sensor configuration by its UUID config_id.

        The server endpoint is DELETE /v1/sensors/{esp_id}/{config_id}
        where config_id is the sensor_config UUID (not GPIO number).
        This avoids MultipleResultsFound when sensors share a GPIO.
        """
        return await self._request(
            "DELETE",
            f"/v1/sensors/{esp_id}/{config_id}",
            action_name="Delete Sensor",
            target=f"{esp_id}/{config_id}",
        )

    async def set_mock_sensor_value(
        self, esp_id: str, gpio: int, raw_value: float, publish: bool = True
    ) -> dict[str, Any]:
        """Set a mock sensor's value (simulates real sensor reading)."""
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/sensors/{gpio}/value",
            json_data={"raw_value": raw_value, "publish": publish},
            action_name="Set Sensor Value",
            target=f"{esp_id}/gpio:{gpio}",
        )

    # =========================================================================
    # Mock Sensor Management (via Debug API)
    # =========================================================================

    async def add_mock_sensor(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        name: Optional[str] = None,
        raw_value: float = 0.0,
        unit: str = "",
        interval_seconds: float = 30.0,
        interface_type: Optional[str] = None,
        i2c_address: Optional[int] = None,
        onewire_address: Optional[str] = None,
        variation_pattern: str = "constant",
        variation_range: float = 0.0,
    ) -> dict[str, Any]:
        """Add a mock sensor to a mock ESP (via Debug API)."""
        data: dict[str, Any] = {
            "gpio": gpio,
            "sensor_type": sensor_type,
            "raw_value": raw_value,
            "unit": unit,
            "raw_mode": True,
            "interval_seconds": interval_seconds,
            "variation_pattern": variation_pattern,
            "variation_range": variation_range,
        }
        if name:
            data["name"] = name
        if interface_type:
            data["interface_type"] = interface_type
        if i2c_address is not None:
            data["i2c_address"] = i2c_address
        if onewire_address:
            data["onewire_address"] = onewire_address

        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/sensors",
            json_data=data,
            action_name=f"Add Mock Sensor ({sensor_type})",
            target=f"{esp_id}/gpio:{gpio}",
        )

    # =========================================================================
    # Actuator Management (mirrors frontend actuators.ts API)
    # =========================================================================

    async def add_actuator(
        self,
        esp_id: str,
        gpio: int,
        actuator_type: str,
        name: Optional[str] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add or update an actuator on an ESP."""
        data: dict[str, Any] = {
            "esp_id": esp_id,
            "gpio": gpio,
            "actuator_type": actuator_type,
            "enabled": enabled,
        }
        if name:
            data["name"] = name
        return await self._request(
            "POST",
            f"/v1/actuators/{esp_id}/{gpio}",
            json_data=data,
            action_name=f"Add Actuator ({actuator_type})",
            target=f"{esp_id}/gpio:{gpio}",
        )

    async def send_actuator_command(
        self,
        esp_id: str,
        gpio: int,
        command: str,
        value: Optional[float] = None,
        duration: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send a command to an actuator (ON, OFF, PWM, TOGGLE)."""
        data: dict[str, Any] = {"command": command}
        if value is not None:
            data["value"] = value
        if duration is not None:
            data["duration"] = duration
        return await self._request(
            "POST",
            f"/v1/actuators/{esp_id}/{gpio}/command",
            json_data=data,
            action_name=f"Actuator Command ({command})",
            target=f"{esp_id}/gpio:{gpio}",
        )

    async def list_actuators(self, esp_id: Optional[str] = None) -> dict[str, Any]:
        """List all actuators, optionally filtered by ESP."""
        params = {}
        if esp_id:
            params["esp_id"] = esp_id
        return await self._request(
            "GET",
            "/v1/actuators/",
            params=params,
            action_name="List Actuators",
            target=esp_id or "all",
        )

    async def delete_actuator(self, esp_id: str, gpio: int) -> dict[str, Any]:
        """Delete an actuator configuration."""
        return await self._request(
            "DELETE",
            f"/v1/actuators/{esp_id}/{gpio}",
            action_name="Delete Actuator",
            target=f"{esp_id}/gpio:{gpio}",
        )

    # =========================================================================
    # Mock Actuator Management (via Debug API)
    # =========================================================================

    async def add_mock_actuator(
        self,
        esp_id: str,
        gpio: int,
        actuator_type: str,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add a mock actuator to a mock ESP (via Debug API)."""
        data: dict[str, Any] = {
            "gpio": gpio,
            "actuator_type": actuator_type,
        }
        if name:
            data["name"] = name
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/actuators",
            json_data=data,
            action_name=f"Add Mock Actuator ({actuator_type})",
            target=f"{esp_id}/gpio:{gpio}",
        )

    # =========================================================================
    # Zone Management
    # =========================================================================

    async def assign_zone(
        self,
        esp_id: str,
        zone_id: str,
        zone_name: Optional[str] = None,
        subzone_strategy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Assign an ESP to a zone.

        Args:
            esp_id: Device ID (e.g. 'ESP_472204')
            zone_id: Target zone ID
            zone_name: Optional display name for the zone
            subzone_strategy: What to do with existing subzones on zone change.
                'transfer' = move subzones to new zone (updates parent_zone_id)
                'reset' = delete all subzones of this ESP
                'copy' = keep originals, create copies in new zone
                None = server default (no subzone handling)
        """
        data: dict[str, Any] = {"zone_id": zone_id}
        if zone_name:
            data["zone_name"] = zone_name
        if subzone_strategy:
            data["subzone_strategy"] = subzone_strategy
        return await self._request(
            "POST",
            f"/v1/zone/devices/{esp_id}/assign",
            json_data=data,
            action_name="Assign Zone",
            target=f"{esp_id} -> {zone_id}",
        )

    async def list_zones(self) -> dict[str, Any]:
        """List all zones via dedicated GET /v1/zone/zones endpoint.

        Includes empty zones from ZoneContext table, not just device-derived ones.
        """
        return await self._request(
            "GET",
            "/v1/zone/zones",
            action_name="List Zones",
            target="all_zones",
        )

    # =========================================================================
    # System & Diagnostics
    # =========================================================================

    async def get_server_health(self) -> dict[str, Any]:
        """Get comprehensive server health."""
        return await self._request(
            "GET",
            "/v1/health/detailed",
            action_name="Server Health Check",
            target="server",
        )

    async def list_sensor_data(
        self,
        esp_id: Optional[str] = None,
        gpio: Optional[int] = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Query recent sensor data."""
        params: dict[str, Any] = {"limit": limit}
        if esp_id:
            params["esp_id"] = esp_id
        if gpio is not None:
            params["gpio"] = gpio
        return await self._request(
            "GET",
            "/v1/sensors/data",
            params=params,
            action_name="Query Sensor Data",
            target=f"{esp_id or 'all'}/gpio:{gpio or 'all'}",
        )

    # =========================================================================
    # State Transition (Mock ESP lifecycle)
    # =========================================================================

    async def set_mock_state(
        self, esp_id: str, state: str, reason: Optional[str] = None
    ) -> dict[str, Any]:
        """Set mock ESP system state."""
        data: dict[str, Any] = {"state": state}
        if reason:
            data["reason"] = reason
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/state",
            json_data=data,
            action_name=f"Set State ({state})",
            target=esp_id,
        )

    async def start_simulation(self, esp_id: str) -> dict[str, Any]:
        """Start sensor simulation for a mock ESP."""
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/simulation/start",
            action_name="Start Simulation",
            target=esp_id,
        )

    async def stop_simulation(self, esp_id: str) -> dict[str, Any]:
        """Stop sensor simulation for a mock ESP."""
        return await self._request(
            "POST",
            f"/v1/debug/mock-esp/{esp_id}/simulation/stop",
            action_name="Stop Simulation",
            target=esp_id,
        )

    # =========================================================================
    # Database Explorer (Debug)
    # =========================================================================

    async def list_tables(self) -> dict[str, Any]:
        """List available database tables."""
        return await self._request(
            "GET",
            "/v1/debug/db/tables",
            action_name="List DB Tables",
            target="database",
        )

    async def query_table(
        self, table_name: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """Query a database table."""
        return await self._request(
            "GET",
            f"/v1/debug/db/{table_name}",
            params={"limit": limit, "offset": offset},
            action_name=f"Query Table ({table_name})",
            target=f"db:{table_name}",
        )

    # =========================================================================
    # Subzone Management
    # =========================================================================

    async def list_subzones(self, esp_id: str) -> dict[str, Any]:
        """List subzones for a specific device."""
        return await self._request(
            "GET",
            f"/v1/subzone/devices/{esp_id}/subzones",
            action_name="List Subzones",
            target=esp_id,
        )

    async def assign_subzone(
        self, esp_id: str, subzone_name: str, subzone_type: str = "bed"
    ) -> dict[str, Any]:
        """Assign a subzone to a device."""
        return await self._request(
            "POST",
            f"/v1/subzone/devices/{esp_id}/subzones/assign",
            json_data={"name": subzone_name, "subzone_type": subzone_type},
            action_name="Assign Subzone",
            target=f"{esp_id}/{subzone_name}",
        )

    # =========================================================================
    # Zone Creation
    # =========================================================================

    async def create_zone(
        self,
        zone_id: str,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a zone entity via POST /v1/zones.

        This creates a persistent ZoneContext entry independent of device assignments.
        """
        data: dict[str, Any] = {"zone_id": zone_id, "name": name}
        if description:
            data["description"] = description
        return await self._request(
            "POST",
            "/v1/zones",
            json_data=data,
            action_name="Create Zone",
            target=zone_id,
        )

    # =========================================================================
    # Sensor Type Defaults
    # =========================================================================

    async def get_sensor_type_defaults(self, sensor_type: str) -> dict[str, Any]:
        """Get default configuration for a specific sensor type."""
        return await self._request(
            "GET",
            f"/v1/sensors/type-defaults/{sensor_type}",
            action_name=f"Sensor Type Defaults ({sensor_type})",
            target=f"sensor_type:{sensor_type}",
        )

    # =========================================================================
    # Health Metrics
    # =========================================================================

    async def get_health_metrics(self) -> dict[str, Any]:
        """Get server performance metrics (Prometheus text format → parsed dict)."""
        result = await self._request(
            "GET",
            "/v1/health/metrics",
            action_name="Health Metrics",
            target="server_metrics",
            expect_json=False,
        )
        # Parse Prometheus text format into key metrics
        raw = result.get("raw_text", "")
        if raw:
            return self._parse_prometheus_metrics(raw)
        return result

    @staticmethod
    def _parse_prometheus_metrics(text: str) -> dict[str, Any]:
        """Extract key metrics from Prometheus exposition format."""
        metrics: dict[str, Any] = {}
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            # Format: metric_name{labels} value  or  metric_name value
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0].split("{")[0]
                try:
                    value = float(parts[-1])
                except ValueError:
                    continue
                if name not in metrics:
                    metrics[name] = value
                elif isinstance(metrics[name], list):
                    metrics[name].append(value)
                else:
                    metrics[name] = [metrics[name], value]
        return {"format": "prometheus", "metric_count": len(metrics), "metrics": metrics}

    async def get_liveness(self) -> dict[str, Any]:
        """Kubernetes-style liveness probe."""
        return await self._request(
            "GET",
            "/v1/health/live",
            action_name="Liveness Probe",
            target="server",
        )

    async def get_readiness(self) -> dict[str, Any]:
        """Kubernetes-style readiness probe."""
        return await self._request(
            "GET",
            "/v1/health/ready",
            action_name="Readiness Probe",
            target="server",
        )

    # =========================================================================
    # Audit Log
    # =========================================================================

    async def list_audit_logs(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Query the audit log."""
        return await self._request(
            "GET",
            "/v1/audit/",
            params={"limit": limit, "offset": offset},
            action_name="List Audit Logs",
            target="audit_log",
        )

    # =========================================================================
    # OneWire Scan (Sensor Discovery)
    # =========================================================================

    async def scan_onewire(self, esp_id: str) -> dict[str, Any]:
        """Trigger a OneWire bus scan on an ESP."""
        return await self._request(
            "POST",
            f"/v1/sensors/esp/{esp_id}/onewire/scan",
            action_name="OneWire Scan",
            target=esp_id,
        )

    async def get_onewire_devices(self, esp_id: str) -> dict[str, Any]:
        """Get discovered OneWire devices on an ESP."""
        return await self._request(
            "GET",
            f"/v1/sensors/esp/{esp_id}/onewire",
            action_name="Get OneWire Devices",
            target=esp_id,
        )

    # =========================================================================
    # Logic Engine
    # =========================================================================

    async def list_logic_rules(self) -> dict[str, Any]:
        """List all automation logic rules."""
        return await self._request(
            "GET",
            "/v1/logic/rules",
            action_name="List Logic Rules",
            target="logic_engine",
        )

    # =========================================================================
    # Real Device Registration (for device_mode=real)
    # =========================================================================

    async def register_real_device(
        self,
        device_id: str,
        name: str,
        hardware_type: str = "ESP32_WROOM",
        firmware_version: str = "",
    ) -> dict[str, Any]:
        """Register a real ESP device (not mock)."""
        data: dict[str, Any] = {
            "device_id": device_id,
            "name": name,
            "hardware_type": hardware_type,
        }
        if firmware_version:
            data["firmware_version"] = firmware_version
        return await self._request(
            "POST",
            "/v1/esp/devices",
            json_data=data,
            action_name="Register Real Device",
            target=device_id,
        )

    async def approve_device(
        self,
        device_id: str,
        zone_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Approve a pending device for operation."""
        data: dict[str, Any] = {}
        if zone_name:
            data["zone_name"] = zone_name
        return await self._request(
            "POST",
            f"/v1/esp/devices/{device_id}/approve",
            json_data=data,
            action_name="Approve Device",
            target=device_id,
        )
