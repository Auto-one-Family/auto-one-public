"""
E2E Test Configuration - Real Server Integration Tests.

WICHTIG: Diese Tests benötigen einen LAUFENDEN Server!
Sie werden nur ausgeführt wenn explizit angefordert.

Starten Sie den Server vor dem Testen:
    cd "El Servador/god_kaiser_server"
    poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

Dann Tests ausführen:
    poetry run pytest tests/e2e/ -v --e2e

Domain-Expert Perspektive:
    Diese Tests validieren das ECHTE Verhalten eines Gewächshaus-Systems:
    - Geräte-Discovery funktioniert wie erwartet
    - Sensordaten fließen zum Frontend
    - Cross-ESP Rules triggern korrekt
    - System erholt sich von Netzwerk-Problemen
"""

import os
import asyncio
import json
import random
import string
import sys
import time
import warnings
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

# CRITICAL: Set Windows SelectorEventLoop policy for Python 3.14 compatibility
# The ProactorEventLoop doesn't support add_reader/add_writer which aiomqtt needs
if sys.platform == "win32":
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message=".*WindowsSelectorEventLoopPolicy.*"
    )
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
import pytest
import pytest_asyncio


# =============================================================================
# Device ID Helpers - Must match pattern: ^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$
# =============================================================================
def generate_valid_mock_id(prefix: str = "") -> str:
    """
    Generate a valid MOCK device ID matching pattern: ^MOCK_[A-Z0-9]+$

    IMPORTANT: No underscores allowed after MOCK_ prefix!

    Args:
        prefix: Optional prefix to include (will be uppercased, no underscores)

    Returns:
        Valid MOCK device ID like "MOCK_LAT8A7B3X2K" or "MOCK_A7B3X2K9"

    Examples:
        generate_valid_mock_id() → "MOCK_A7B3X2K9"
        generate_valid_mock_id("LAT") → "MOCK_LAT8B3X2K9"
        generate_valid_mock_id("COOL") → "MOCK_COOL3X2K9A"
    """
    # Clean prefix: uppercase, remove underscores
    clean_prefix = prefix.upper().replace("_", "")

    # Generate random suffix (alphanumeric only)
    suffix_len = 8 - len(clean_prefix) if len(clean_prefix) < 8 else 4
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=suffix_len))

    return f"MOCK_{clean_prefix}{suffix}"


def generate_valid_esp_id() -> str:
    """
    Generate a valid ESP device ID matching pattern: ^ESP_[A-F0-9]{6,8}$

    Returns:
        Valid ESP device ID like "ESP_A1B2C3D4"
    """
    # 6-8 Hex characters (uppercase)
    suffix = "".join(random.choices("ABCDEF0123456789", k=8))
    return f"ESP_{suffix}"


def generate_unique_mock_id(prefix: str = "") -> str:
    """
    Generate a unique MOCK device ID using timestamp + random.

    Args:
        prefix: Optional prefix (will be uppercased, no underscores)

    Returns:
        Unique MOCK device ID like "MOCK_LAT1A2B3C4D"
    """
    clean_prefix = prefix.upper().replace("_", "")[:4]  # Max 4 chars
    # Use timestamp hex + random for uniqueness
    ts_hex = f"{int(time.time()) % 0xFFFF:04X}"
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"MOCK_{clean_prefix}{ts_hex}{random_part}"


# =============================================================================
# E2E Skip Marker - Tests nur wenn --e2e Flag gesetzt
# =============================================================================
def pytest_configure(config):
    """Register custom markers for E2E tests."""
    config.addinivalue_line(
        "markers", "e2e: End-to-End tests requiring a running server (skip without --e2e flag)"
    )
    config.addinivalue_line(
        "markers", "slow_e2e: Slow E2E tests (>30s) - use --slow-e2e to include"
    )


def pytest_addoption(parser):
    """Add custom command line options for E2E tests."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E tests that require a running server",
    )
    parser.addoption(
        "--slow-e2e",
        action="store_true",
        default=False,
        help="Include slow E2E tests (>30 seconds)",
    )
    parser.addoption(
        "--server-url",
        action="store",
        default="http://localhost:8000",
        help="URL of the running server for E2E tests",
    )
    parser.addoption(
        "--mqtt-host", action="store", default="localhost", help="MQTT broker host for E2E tests"
    )
    parser.addoption(
        "--mqtt-port", action="store", default=1883, type=int, help="MQTT broker port for E2E tests"
    )


def pytest_collection_modifyitems(config, items):
    """Skip E2E tests unless explicitly requested."""
    if not config.getoption("--e2e"):
        skip_e2e = pytest.mark.skip(reason="E2E tests require --e2e flag and running server")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)

    if not config.getoption("--slow-e2e"):
        skip_slow = pytest.mark.skip(reason="Slow E2E tests require --slow-e2e flag")
        for item in items:
            if "slow_e2e" in item.keywords:
                item.add_marker(skip_slow)


# =============================================================================
# E2E Configuration Data Classes
# =============================================================================
@dataclass
class E2EConfig:
    """Configuration for E2E tests."""

    server_url: str
    mqtt_host: str
    mqtt_port: int
    api_base: str
    ws_url: str

    # Timeouts für verschiedene Operationen (in Sekunden)
    device_discovery_timeout: float = 15.0
    sensor_data_timeout: float = 10.0
    rule_trigger_timeout: float = 10.0
    network_recovery_timeout: float = 60.0
    server_restart_timeout: float = 45.0

    @classmethod
    def from_pytest_config(cls, config) -> "E2EConfig":
        """Create E2EConfig from pytest configuration."""
        server_url = config.getoption("--server-url")
        return cls(
            server_url=server_url,
            mqtt_host=config.getoption("--mqtt-host"),
            mqtt_port=config.getoption("--mqtt-port"),
            api_base=f"{server_url}/api/v1",
            ws_url=server_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws",
        )


@dataclass
class ESPDeviceTestData:
    """Represents an ESP device for E2E testing."""

    device_id: str
    name: str
    zone_id: Optional[str] = None
    sensors: list = None
    actuators: list = None

    def __post_init__(self):
        if self.sensors is None:
            self.sensors = []
        if self.actuators is None:
            self.actuators = []


# =============================================================================
# E2E Fixtures
# =============================================================================
@pytest.fixture(scope="session")
def e2e_config(request) -> E2EConfig:
    """Get E2E test configuration."""
    return E2EConfig.from_pytest_config(request.config)


@pytest_asyncio.fixture(scope="function")
async def http_client() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """Create an HTTP client for E2E tests (function-scoped for event loop safety)."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def e2e_http_client() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """Create a function-scoped HTTP client for E2E tests."""
    async with aiohttp.ClientSession() as session:
        yield session


# Module-level flag to avoid redundant health checks
_server_health_verified = False

# Shared auth token cache — prevents auth rate limit exhaustion across tests.
# The auth endpoint allows 10 requests/min per IP; with function-scoped fixtures
# each test would re-authenticate and exhaust the limit after ~10 tests.
# The token is valid for the full test session (default JWT expiry: 24h).
_shared_e2e_auth_token: Optional[str] = None


@pytest_asyncio.fixture(scope="function")
async def server_health_check(e2e_config: E2EConfig, e2e_http_client: aiohttp.ClientSession):
    """
    Verify server is running before E2E tests.

    Domain-Expert Note:
        In einem echten Gewächshaus-System muss der Server zuverlässig
        laufen bevor Tests beginnen. Diese Fixture stellt das sicher.

    Uses function-scope to avoid event loop conflicts with pytest-asyncio.
    Module-level flag prevents redundant checks after first verification.
    """
    global _server_health_verified
    if _server_health_verified:
        return True

    health_url = f"{e2e_config.server_url}/health"
    max_retries = 5
    retry_delay = 2.0

    for attempt in range(max_retries):
        try:
            async with e2e_http_client.get(
                health_url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    _server_health_verified = True
                    return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

    pytest.fail(
        f"Server not reachable at {e2e_config.server_url}. "
        "Please start the server before running E2E tests:\n"
        "  cd 'El Servador/god_kaiser_server'\n"
        "  poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
    )


# =============================================================================
# API Helper Class
# =============================================================================
class E2EAPIClient:
    """
    Helper class for E2E API interactions.

    Domain-Expert Note:
        Diese Klasse abstrahiert die API-Kommunikation für Tests.
        Sie spiegelt wider, wie ein Gewächshaus-Frontend mit dem
        Server kommunizieren würde.
    """

    def __init__(self, config: E2EConfig, session: aiohttp.ClientSession):
        self.config = config
        self.session = session
        self._auth_token: Optional[str] = None

    async def authenticate(self, username: str = "admin", password: str = "Admin1234") -> bool:
        """
        Authenticate and store token.

        If login fails, tries to create initial admin via /auth/setup endpoint.

        Returns:
            bool: True if authentication succeeded, False otherwise.

        Side effects:
            Sets self._auth_token on success.
            Sets self._last_auth_error for debugging on failure.
        """
        self._last_auth_error = None

        # First, try to login
        try:
            async with self.session.post(
                f"{self.config.api_base}/auth/login",
                json={"username": username, "password": password},
            ) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        data = {}
                    # Token is nested: {"tokens": {"access_token": "..."}}
                    tokens = data.get("tokens", {})
                    self._auth_token = tokens.get("access_token") or data.get("access_token")
                    if self._auth_token:
                        print(f"[E2E Auth] Login successful for user: {username}")
                        return True
                    else:
                        self._last_auth_error = (
                            f"Login returned 200 but no token in response: {response_text[:200]}"
                        )
                else:
                    self._last_auth_error = (
                        f"Login failed with status {response.status}: {response_text[:200]}"
                    )
        except Exception as e:
            self._last_auth_error = f"Login request failed: {type(e).__name__}: {e}"

        # Login failed - try to create initial admin user via setup endpoint
        setup_payload = {
            "username": username,
            "email": f"{username}@e2e-test.dev",
            "password": password,
            "full_name": "E2E Test Admin",
        }
        try:
            async with self.session.post(
                f"{self.config.api_base}/auth/setup", json=setup_payload
            ) as response:
                response_text = await response.text()
                if response.status in (200, 201):
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        data = {}
                    tokens = data.get("tokens", {})
                    self._auth_token = tokens.get("access_token") or data.get("access_token")
                    if self._auth_token:
                        print(f"[E2E Auth] Setup successful for user: {username}")
                        return True
                    else:
                        self._last_auth_error = (
                            f"Setup returned {response.status} but no token: {response_text[:200]}"
                        )
                else:
                    # Setup might fail if users already exist (403) - try login again
                    setup_error = (
                        f"Setup failed with status {response.status}: {response_text[:200]}"
                    )
                    result = await self._try_login(username, password)
                    if not result:
                        self._last_auth_error = f"{setup_error}; Retry login also failed"
                    return result
        except Exception as e:
            self._last_auth_error = f"Setup request failed: {type(e).__name__}: {e}"
            return False

        return False

    async def _try_login(self, username: str, password: str) -> bool:
        """Helper to try login without setup fallback."""
        async with self.session.post(
            f"{self.config.api_base}/auth/login", json={"username": username, "password": password}
        ) as response:
            if response.status == 200:
                data = await response.json()
                tokens = data.get("tokens", {})
                self._auth_token = tokens.get("access_token") or data.get("access_token")
                return bool(self._auth_token)
            return False

    @property
    def headers(self) -> dict:
        """Get headers with auth token if available."""
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    async def register_esp(
        self, device: ESPDeviceTestData, max_retries: int = 3, auto_approve: bool = True
    ) -> dict:
        """
        Register an ESP device with retry logic and optional auto-approval.

        Uses exponential backoff to handle connection issues (ConnectionResetError)
        that can occur when registering multiple devices in rapid succession.
        Auto-approves the device by default so it can be used immediately in E2E tests.
        """
        # Generate unique MAC/IP per device to avoid unique constraint violations
        id_hash = abs(hash(device.device_id)) % 0xFFFFFF
        mac_bytes = [(id_hash >> (i * 4)) & 0xFF for i in range(6)]
        unique_mac = ":".join(f"{b:02X}" for b in mac_bytes)
        unique_ip = f"192.168.{(id_hash >> 8) & 0xFF}.{id_hash & 0xFF or 1}"

        payload = {
            "device_id": device.device_id,
            "name": device.name,
            "ip_address": unique_ip,
            "mac_address": unique_mac,
            "hardware_type": "ESP32_WROOM",
            "firmware_version": "1.0.0",
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                async with self.session.post(
                    f"{self.config.api_base}/esp/devices", json=payload, headers=self.headers
                ) as response:
                    result = await response.json()
                    registration_ok = response.status in (200, 201)

                # Auto-approve after successful registration
                if auto_approve and registration_ok and result.get("device_id"):
                    await self.approve_esp(device.device_id)

                return result
            except (ConnectionResetError, aiohttp.ClientError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.5s, 1.0s, 2.0s
                    backoff = 0.5 * (2**attempt)
                    await asyncio.sleep(backoff)
                    continue
                raise

        # Should not reach here, but just in case
        raise last_error or Exception("register_esp failed after retries")

    async def approve_esp(self, device_id: str) -> dict:
        """Approve a pending ESP device for normal operation."""
        async with self.session.post(
            f"{self.config.api_base}/esp/devices/{device_id}/approve", json={}, headers=self.headers
        ) as response:
            result = await response.json()
            if response.status not in (200, 201):
                raise RuntimeError(
                    f"approve_esp failed for {device_id}: HTTP {response.status} - {result}"
                )
            return result

    async def get_esp_status(self, device_id: str) -> dict:
        """Get ESP device status."""
        async with self.session.get(
            f"{self.config.api_base}/esp/devices/{device_id}", headers=self.headers
        ) as response:
            if response.status == 200:
                return await response.json()
            return {}

    async def get_all_esp_devices(self) -> list:
        """Get all registered ESP devices."""
        async with self.session.get(
            f"{self.config.api_base}/esp/devices", headers=self.headers
        ) as response:
            if response.status == 200:
                result = await response.json()
                # Response is paginated: {"data": [...], "pagination": {...}}
                return result.get("data", [])
            return []

    async def send_actuator_command(self, device_id: str, gpio: int, value: float) -> dict:
        """Send actuator command."""
        payload = {"device_id": device_id, "gpio": gpio, "value": value}
        async with self.session.post(
            f"{self.config.api_base}/actuators/command", json=payload, headers=self.headers
        ) as response:
            return await response.json()

    async def get_sensor_data(
        self,
        device_id: str,
        gpio: int = None,
        limit: int = 10,
        sensor_type: str = None,
    ) -> list:
        """Get recent sensor data via GET /sensors/data query endpoint."""
        params = {"esp_id": device_id, "limit": limit}
        if gpio is not None:
            params["gpio"] = gpio
        if sensor_type is not None:
            params["sensor_type"] = sensor_type
        async with self.session.get(
            f"{self.config.api_base}/sensors/data", params=params, headers=self.headers
        ) as response:
            if response.status == 200:
                result = await response.json()
                return result.get("readings", [])
            return []

    async def create_logic_rule(self, rule: dict) -> dict:
        """Create a cross-ESP logic rule."""
        async with self.session.post(
            f"{self.config.api_base}/logic/rules", json=rule, headers=self.headers
        ) as response:
            return await response.json()

    async def delete_esp(self, device_id: str) -> bool:
        """Delete an ESP device (cleanup)."""
        async with self.session.delete(
            f"{self.config.api_base}/esp/devices/{device_id}", headers=self.headers
        ) as response:
            return response.status in (200, 204)

    # =========================================================================
    # Logic Engine API Methods
    # =========================================================================
    async def get_logic_rule(self, rule_id: str) -> dict:
        """Get a specific logic rule by ID."""
        async with self.session.get(
            f"{self.config.api_base}/logic/rules/{rule_id}", headers=self.headers
        ) as response:
            if response.status == 200:
                return await response.json()
            return {}

    async def list_logic_rules(self, enabled: bool = None) -> list:
        """List all logic rules with optional filtering."""
        params = {}
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        async with self.session.get(
            f"{self.config.api_base}/logic/rules", params=params, headers=self.headers
        ) as response:
            if response.status == 200:
                result = await response.json()
                # Response may be paginated
                if isinstance(result, dict):
                    return result.get("data", result.get("rules", []))
                return result
            return []

    async def update_logic_rule(self, rule_id: str, rule_data: dict) -> dict:
        """Update an existing logic rule."""
        async with self.session.put(
            f"{self.config.api_base}/logic/rules/{rule_id}", json=rule_data, headers=self.headers
        ) as response:
            return await response.json()

    async def delete_logic_rule(self, rule_id: str) -> bool:
        """Delete a logic rule (cleanup)."""
        async with self.session.delete(
            f"{self.config.api_base}/logic/rules/{rule_id}", headers=self.headers
        ) as response:
            return response.status in (200, 204)

    async def toggle_logic_rule(self, rule_id: str, enabled: bool, reason: str = None) -> dict:
        """Enable or disable a logic rule."""
        payload = {"enabled": enabled}
        if reason:
            payload["reason"] = reason
        async with self.session.post(
            f"{self.config.api_base}/logic/rules/{rule_id}/toggle",
            json=payload,
            headers=self.headers,
        ) as response:
            return await response.json()

    async def test_logic_rule(
        self,
        rule_id: str,
        mock_sensor_values: dict = None,
        mock_time: str = None,
        dry_run: bool = True,
    ) -> dict:
        """Test/simulate a logic rule execution."""
        payload = {"dry_run": dry_run}
        if mock_sensor_values:
            payload["mock_sensor_values"] = mock_sensor_values
        if mock_time:
            payload["mock_time"] = mock_time
        async with self.session.post(
            f"{self.config.api_base}/logic/rules/{rule_id}/test", json=payload, headers=self.headers
        ) as response:
            return await response.json()

    async def get_execution_history(
        self, rule_id: str = None, success: bool = None, limit: int = 50
    ) -> dict:
        """Get logic rule execution history."""
        params = {"limit": limit}
        if rule_id:
            params["rule_id"] = rule_id
        if success is not None:
            params["success"] = str(success).lower()
        async with self.session.get(
            f"{self.config.api_base}/logic/execution_history", params=params, headers=self.headers
        ) as response:
            if response.status == 200:
                return await response.json()
            return {"entries": [], "total_count": 0}

    # =========================================================================
    # Sensor & Actuator Config API Methods
    # =========================================================================
    async def create_sensor_config(
        self, esp_id: str, gpio: int, sensor_type: str, name: str = None
    ) -> dict:
        """Create a sensor configuration on an ESP."""
        payload = {
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": sensor_type,
            "name": name or f"{sensor_type}_gpio{gpio}",
            "enabled": True,
            "pi_enhanced": False,
            "read_interval": 30,
        }
        async with self.session.post(
            f"{self.config.api_base}/sensors", json=payload, headers=self.headers
        ) as response:
            return await response.json()

    async def create_actuator_config(
        self, esp_id: str, gpio: int, actuator_type: str, name: str = None
    ) -> dict:
        """Create an actuator configuration on an ESP."""
        payload = {
            "esp_id": esp_id,
            "gpio": gpio,
            "actuator_type": actuator_type,
            "name": name or f"{actuator_type}_gpio{gpio}",
            "enabled": True,
            "default_state": 0,
        }
        async with self.session.post(
            f"{self.config.api_base}/actuators", json=payload, headers=self.headers
        ) as response:
            return await response.json()

    async def get_actuator_state(self, esp_id: str, gpio: int) -> dict:
        """Get current state of an actuator."""
        async with self.session.get(
            f"{self.config.api_base}/actuators/{esp_id}/{gpio}/state", headers=self.headers
        ) as response:
            if response.status == 200:
                return await response.json()
            return {}

    async def delete_sensor_config(self, sensor_id: str) -> bool:
        """Delete a sensor configuration."""
        async with self.session.delete(
            f"{self.config.api_base}/sensors/{sensor_id}", headers=self.headers
        ) as response:
            return response.status in (200, 204)

    async def delete_actuator_config(self, actuator_id: str) -> bool:
        """Delete an actuator configuration."""
        async with self.session.delete(
            f"{self.config.api_base}/actuators/{actuator_id}", headers=self.headers
        ) as response:
            return response.status in (200, 204)


@pytest_asyncio.fixture
async def api_client(
    e2e_config: E2EConfig, e2e_http_client: aiohttp.ClientSession, server_health_check
) -> E2EAPIClient:
    """
    Create an API client for E2E tests with authentication.

    Tries multiple credential combinations and warns if all fail.
    The auth token is cached at module level to avoid exhausting the server's
    auth rate limit (10 requests/min) when running many tests in one session.
    """
    global _shared_e2e_auth_token
    client = E2EAPIClient(e2e_config, e2e_http_client)

    # Reuse cached token from earlier fixture call in this session
    if _shared_e2e_auth_token:
        client._auth_token = _shared_e2e_auth_token
        return client

    # First call: authenticate and cache the token
    credentials_to_try = [
        ("admin", os.environ.get("E2E_TEST_PASSWORD", "")),  # Seeded admin user
        ("admin", "Admin1234"),  # Fallback
    ]

    auth_errors = []
    for username, password in credentials_to_try:
        auth_success = await client.authenticate(username, password)
        if auth_success and client._auth_token:
            _shared_e2e_auth_token = client._auth_token
            return client
        # Capture error for debugging
        if hasattr(client, "_last_auth_error") and client._last_auth_error:
            auth_errors.append(f"{username}: {client._last_auth_error}")

    # All authentication attempts failed - warn but continue
    # (Some E2E tests may not need auth, but protected endpoints will fail)
    import warnings

    error_details = "; ".join(auth_errors) if auth_errors else "No error details captured"
    warnings.warn(
        "E2E API client could not authenticate. "
        "Protected API endpoints will return 401. "
        f"Tried credentials: {[c[0] for c in credentials_to_try]}. "
        f"Last errors: {error_details}",
        UserWarning,
    )
    return client


# =============================================================================
# MQTT Helper for E2E Tests
# =============================================================================
class E2EMQTTClient:
    """
    MQTT client helper for E2E tests.

    Domain-Expert Note:
        Simuliert die MQTT-Kommunikation wie ein echter ESP32 im
        Gewächshaus. Sendet Sensordaten und empfängt Befehle.
    """

    def __init__(self, config: E2EConfig):
        self.config = config
        self._client = None
        self._connected = False
        self._received_messages: list = []

    async def connect(self, max_retries: int = 3, retry_delay: float = 2.0):
        """Connect to MQTT broker with retry/backoff for CI resilience."""
        try:
            import aiomqtt
        except ImportError:
            pytest.skip("aiomqtt not installed - skipping MQTT E2E tests")

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"[E2E MQTT] Connecting to {self.config.mqtt_host}:{self.config.mqtt_port} (attempt {attempt}/{max_retries})..."
                )
                self._client = aiomqtt.Client(
                    hostname=self.config.mqtt_host, port=self.config.mqtt_port
                )
                await self._client.__aenter__()
                self._connected = True
                print("[E2E MQTT] Connected successfully!")
                return
            except Exception as e:
                if attempt < max_retries:
                    wait = retry_delay * attempt
                    print(
                        f"[E2E MQTT] Connection failed (attempt {attempt}): {type(e).__name__}: {e}. Retrying in {wait:.0f}s..."
                    )
                    import asyncio

                    await asyncio.sleep(wait)
                else:
                    print(
                        f"[E2E MQTT] Connection failed after {max_retries} attempts: {type(e).__name__}: {e}"
                    )
                    raise

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client and self._connected:
            await self._client.__aexit__(None, None, None)
            self._connected = False

    async def publish_sensor_data(
        self,
        esp_id: str,
        gpio: int,
        value: float,
        sensor_type: str = "temperature",
        raw_mode: bool = True,
        kaiser_id: str = "god",
    ):
        """
        Publish sensor data like a real ESP32 would.

        IMPORTANT: Payload must contain ALL required fields for sensor_handler:
        - ts (timestamp)
        - esp_id (device identifier)
        - gpio (pin number)
        - sensor_type (e.g., "temperature", "ph", "humidity")
        - raw (raw sensor value)
        - raw_mode (True if ESP sends raw ADC value)

        See: src/mqtt/handlers/sensor_handler.py:_validate_payload()
        """
        import json
        import time

        if not self._connected or not self._client:
            print(f"[E2E MQTT] ERROR: Not connected! Cannot publish sensor data for {esp_id}")
            return

        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data"

        # All required fields per sensor_handler._validate_payload()
        payload = {
            "ts": int(time.time()),
            "esp_id": esp_id,  # REQUIRED - was missing!
            "gpio": gpio,
            "sensor_type": sensor_type,  # REQUIRED - was missing!
            "raw": int(value * 100),  # REQUIRED - raw ADC-like value
            "value": value,  # Processed value
            "unit": "°C" if sensor_type == "temperature" else "",
            "raw_mode": raw_mode,
            "quality": "good",
        }

        try:
            # Use QoS 1 for reliability
            await self._client.publish(topic, json.dumps(payload), qos=1)
            print(f"[E2E MQTT] Published to {topic}: value={value}, sensor_type={sensor_type}")
        except Exception as e:
            print(f"[E2E MQTT] ERROR publishing to {topic}: {type(e).__name__}: {e}")
            raise

        # Small delay to ensure broker processes message
        await asyncio.sleep(0.1)

    async def publish_heartbeat(
        self, esp_id: str, heap_free: int = 98304, uptime: int = 3600, kaiser_id: str = "god"
    ):
        """Publish heartbeat like a real ESP32 would."""
        import json
        import time

        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat"
        payload = {
            "ts": int(time.time()),
            "esp_id": esp_id,
            "heap_free": heap_free,
            "uptime_seconds": uptime,
            "wifi_rssi": -45,
            "system_state": "OPERATIONAL",
        }
        await self._client.publish(topic, json.dumps(payload))

    async def publish_lwt(
        self,
        esp_id: str,
        reason: str = "unexpected_disconnect",
        retain: bool = False,
        kaiser_id: str = "god",
    ):
        """Publish LWT-like offline event for reconnect/recovery E2E tests."""
        import json
        import time

        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/system/will"
        payload = {
            "status": "offline",
            "reason": reason,
            "timestamp": int(time.time()),
        }
        await self._client.publish(topic, json.dumps(payload), retain=retain)

    async def publish_actuator_response(
        self,
        esp_id: str,
        gpio: int,
        command: str,
        value: float,
        success: bool,
        message: str,
        correlation_id: str = None,
        kaiser_id: str = "god",
    ):
        """
        Publish actuator command response like a real ESP32 would.

        Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response
        Payload matches mock_esp32_client._publish_actuator_response()
        """
        import json
        import time

        if not self._connected or not self._client:
            print(f"[E2E MQTT] ERROR: Not connected! Cannot publish actuator response for {esp_id}")
            return

        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response"

        payload = {
            "ts": int(time.time()),
            "esp_id": esp_id,
            "gpio": gpio,
            "command": command,
            "value": value,
            "command_id": correlation_id or f"cmd_{int(time.time())}",
            "success": success,
            "message": message,
        }

        try:
            await self._client.publish(topic, json.dumps(payload), qos=1)
            print(f"[E2E MQTT] Published actuator response to {topic}: success={success}")
        except Exception as e:
            print(f"[E2E MQTT] ERROR publishing actuator response: {type(e).__name__}: {e}")
            raise

        await asyncio.sleep(0.1)

    async def publish_actuator_alert(
        self,
        esp_id: str,
        gpio: int,
        alert_type: str,
        message: str,
        zone_id: str = None,
        kaiser_id: str = "god",
    ):
        """
        Publish actuator alert like a real ESP32 would.

        Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert
        Payload matches mock_esp32_client._publish_actuator_alert()

        Alert types: emergency_stop, runtime_protection, safety_violation, hardware_error
        """
        import json
        import time

        if not self._connected or not self._client:
            print(f"[E2E MQTT] ERROR: Not connected! Cannot publish actuator alert for {esp_id}")
            return

        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert"

        severity = "critical" if alert_type == "emergency_stop" else "warning"

        payload = {
            "ts": int(time.time()),
            "esp_id": esp_id,
            "gpio": gpio,
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
        }

        if zone_id:
            payload["zone_id"] = zone_id

        try:
            await self._client.publish(topic, json.dumps(payload), qos=1)
            print(
                f"[E2E MQTT] Published actuator alert to {topic}: type={alert_type}, severity={severity}"
            )
        except Exception as e:
            print(f"[E2E MQTT] ERROR publishing actuator alert: {type(e).__name__}: {e}")
            raise

        await asyncio.sleep(0.1)

    async def publish_emergency_broadcast(
        self,
        esp_id: str,
        reason: str = "manual",
        stopped_actuators: list = None,
        kaiser_id: str = "god",
    ):
        """
        Publish emergency stop broadcast like a real ESP32 would.

        Topic: kaiser/broadcast/emergency
        Used for system-wide emergency stop.
        """
        import json
        import time

        if not self._connected or not self._client:
            print("[E2E MQTT] ERROR: Not connected! Cannot publish emergency broadcast")
            return

        topic = "kaiser/broadcast/emergency"

        payload = {
            "esp_id": esp_id,
            "command_id": f"emg_{int(time.time())}",
            "stopped_actuators": stopped_actuators or [],
            "timestamp": int(time.time()),
            "reason": reason,
        }

        try:
            await self._client.publish(topic, json.dumps(payload), qos=1)
            print(f"[E2E MQTT] Published emergency broadcast: reason={reason}")
        except Exception as e:
            print(f"[E2E MQTT] ERROR publishing emergency broadcast: {type(e).__name__}: {e}")
            raise

        await asyncio.sleep(0.1)

    async def subscribe_to_commands(self, esp_id: str, kaiser_id: str = "god"):
        """Subscribe to actuator commands for an ESP."""
        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/actuator/+/command"
        await self._client.subscribe(topic)


# =============================================================================
# WebSocket Helper for E2E Tests
# =============================================================================
class E2EWebSocketClient:
    """
    WebSocket client helper for E2E tests.

    Connects to the server's WebSocket endpoint and captures real-time events.
    Used to verify that MQTT/API triggers produce correct WebSocket broadcasts.
    """

    def __init__(self, config: E2EConfig):
        self.config = config
        self._ws = None
        self._connected = False
        self._messages: list = []

    async def connect(self, token: str = None):
        """Connect to WebSocket endpoint at /api/v1/ws/realtime/{client_id}."""
        import uuid

        client_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
        ws_base = self.config.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_base}/api/v1/ws/realtime/{client_id}"
        if token:
            ws_url += f"?token={token}"
        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(ws_url)
            self._connected = True
        except Exception:
            if hasattr(self, "_session"):
                await self._session.close()
            raise

    async def disconnect(self):
        """Disconnect from WebSocket."""
        if self._ws:
            await self._ws.close()
        if hasattr(self, "_session") and self._session:
            await self._session.close()
        self._connected = False

    async def subscribe(self, subscription: dict):
        """Send subscription message to WebSocket.

        Server expects: {"action": "subscribe", "filters": {"types": [...], ...}}
        """
        if self._ws and self._connected:
            await self._ws.send_json({"action": "subscribe", "filters": subscription})

    async def wait_for_message(self, timeout: float = 10.0) -> Optional[dict]:
        """Wait for a WebSocket message with timeout."""
        if not self._ws or not self._connected:
            return None
        try:
            msg = await asyncio.wait_for(self._ws.receive_json(), timeout=timeout)
            self._messages.append(msg)
            return msg
        except asyncio.TimeoutError:
            return None

    async def wait_for_event(
        self, event_type: str, timeout: float = 10.0, match_fn=None
    ) -> Optional[dict]:
        """Wait for a specific event type, optionally matching a filter function."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            msg = await self.wait_for_message(timeout=remaining)
            if msg and msg.get("type") == event_type:
                if match_fn is None or match_fn(msg):
                    return msg
        return None

    def clear_messages(self):
        """Clear captured messages."""
        self._messages.clear()

    @property
    def messages(self) -> list:
        """Get all captured messages."""
        return list(self._messages)

    @property
    def received_messages(self) -> list:
        """Alias for messages - used by some test files."""
        return list(self._messages)


@pytest_asyncio.fixture
async def ws_client(
    e2e_config: E2EConfig,
    api_client: E2EAPIClient,
) -> AsyncGenerator[E2EWebSocketClient, None]:
    """Create a WebSocket client for E2E tests."""
    client = E2EWebSocketClient(e2e_config)
    try:
        token = api_client._auth_token if hasattr(api_client, "_auth_token") else None
        await client.connect(token=token)
        yield client
    except Exception:
        yield client  # Yield even on connect failure (tests will be skipped via --e2e)
    finally:
        await client.disconnect()


@pytest_asyncio.fixture
async def mqtt_client(e2e_config: E2EConfig) -> AsyncGenerator[E2EMQTTClient, None]:
    """Create an MQTT client for E2E tests."""
    client = E2EMQTTClient(e2e_config)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


# =============================================================================
# Test Data Factories
# =============================================================================
class GreenhouseTestFactory:
    """
    Factory for creating greenhouse test data.

    Domain-Expert Note:
        Erstellt realistische Testdaten basierend auf echten
        Gewächshaus-Konfigurationen. Jedes Gerät hat sinnvolle
        Sensor- und Aktor-Kombinationen.

    Device ID Format:
        MOCK_[A-Z0-9]+ - für E2E Test-Geräte (NO underscores after MOCK_!)
        ESP_[A-F0-9]{6,8} - für echte ESPs (nur Hex-Zeichen)
    """

    _counter = 0  # Counter for unique IDs

    @classmethod
    def _next_id(cls, prefix: str) -> str:
        """
        Generate unique device ID using MOCK_ format.

        IMPORTANT: Pattern is ^MOCK_[A-Z0-9]+$ - NO underscores after MOCK_!
        """
        cls._counter += 1
        # Clean prefix: uppercase, no underscores
        clean_prefix = prefix.upper().replace("_", "")
        return f"MOCK_{clean_prefix}{cls._counter:02d}"

    @classmethod
    def create_temperature_esp(cls, zone_id: str = "zone_1") -> ESPDeviceTestData:
        """Create an ESP with temperature sensors."""
        return ESPDeviceTestData(
            device_id=cls._next_id("TEMP"),
            name=f"Temperature Monitor {zone_id}",
            zone_id=zone_id,
            sensors=[
                {"gpio": 4, "type": "DS18B20", "name": "Air Temp"},
                {"gpio": 5, "type": "DS18B20", "name": "Soil Temp"},
            ],
            actuators=[],
        )

    @classmethod
    def create_irrigation_esp(cls, zone_id: str = "zone_1") -> ESPDeviceTestData:
        """Create an ESP for irrigation control."""
        return ESPDeviceTestData(
            device_id=cls._next_id("IRRIG"),
            name=f"Irrigation Controller {zone_id}",
            zone_id=zone_id,
            sensors=[
                {"gpio": 34, "type": "CAPACITIVE_SOIL", "name": "Soil Moisture"},
            ],
            actuators=[
                {"gpio": 25, "type": "VALVE", "name": "Water Valve"},
                {"gpio": 26, "type": "PUMP", "name": "Water Pump"},
            ],
        )

    @classmethod
    def create_climate_esp(cls, zone_id: str = "zone_1") -> ESPDeviceTestData:
        """Create an ESP for climate control."""
        return ESPDeviceTestData(
            device_id=cls._next_id("CLIM"),
            name=f"Climate Controller {zone_id}",
            zone_id=zone_id,
            sensors=[
                {"gpio": 21, "type": "SHT31", "name": "Temp/Humidity"},
            ],
            actuators=[
                {"gpio": 27, "type": "FAN", "name": "Ventilation Fan"},
                {"gpio": 32, "type": "HEATER", "name": "Heater"},
            ],
        )


@pytest.fixture
def greenhouse_factory() -> GreenhouseTestFactory:
    """Provide greenhouse test data factory."""
    return GreenhouseTestFactory()


# =============================================================================
# Cleanup Helpers
# =============================================================================
@pytest_asyncio.fixture
async def cleanup_test_devices(api_client: E2EAPIClient):
    """
    Cleanup fixture that removes test devices after tests.

    Domain-Expert Note:
        Wichtig für Testwiederholbarkeit - wie das Zurücksetzen
        eines Gewächshauses nach einem Experiment.
    """
    created_devices: list[str] = []

    def track_device(device_id: str):
        created_devices.append(device_id)

    yield track_device

    # Cleanup: Remove all tracked devices
    for device_id in created_devices:
        try:
            await api_client.delete_esp(device_id)
        except Exception:
            pass  # Best effort cleanup
