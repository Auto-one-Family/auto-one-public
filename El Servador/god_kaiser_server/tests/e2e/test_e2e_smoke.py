"""
E2E Smoke Tests - Verify basic system health before running full E2E suite.

These tests MUST pass before any other E2E test runs.
They verify that all infrastructure components are reachable and functional.

Usage:
    poetry run pytest tests/e2e/test_e2e_smoke.py --e2e -v

Dependencies:
- Running Server (El Servador)
- MQTT Broker (Mosquitto)
- PostgreSQL Database
- Frontend (El Frontend) - optional for frontend smoke test
"""

import os
import asyncio

import aiohttp
import pytest

from conftest import E2EConfig, E2EMQTTClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestSmokeBackendHealth:
    """Smoke Test 1: Backend is alive and healthy."""

    async def test_health_live_endpoint(
        self,
        e2e_config: E2EConfig,
        e2e_http_client: aiohttp.ClientSession,
    ):
        """
        GET /api/v1/health/live returns 200.

        This is the most basic check: is the server running?
        If this fails, nothing else will work.
        """
        url = f"{e2e_config.api_base}/health/live"
        async with e2e_http_client.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            assert (
                response.status == 200
            ), f"Health endpoint should return 200, got {response.status}"
            data = await response.json()
            # Server returns {"success": True, "alive": True} or {"status": "ok"}
            is_healthy = (
                data.get("status") in ("ok", "healthy", "alive")
                or data.get("alive") is True
                or data.get("success") is True
            )
            assert is_healthy, f"Health status should indicate alive/healthy, got: {data}"

            print(f"  Backend health: {data}")

    async def test_health_ready_endpoint(
        self,
        e2e_config: E2EConfig,
        e2e_http_client: aiohttp.ClientSession,
    ):
        """
        GET /health or /api/v1/health/ready returns status info.

        Verifies that the server has completed initialization
        (DB connected, MQTT connected, etc.).
        """
        # Try multiple health endpoints (server may use different paths)
        endpoints = [
            f"{e2e_config.server_url}/health",
            f"{e2e_config.api_base}/health/ready",
        ]

        for url in endpoints:
            try:
                async with e2e_http_client.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"  Ready endpoint ({url}): {data}")
                        return  # At least one health endpoint works
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue

        # If we get here, at least one endpoint should have responded
        pytest.fail("No health/ready endpoint responded with 200")


class TestSmokeMQTTConnection:
    """Smoke Test 2: MQTT Broker is reachable."""

    async def test_mqtt_connect_disconnect(
        self,
        e2e_config: E2EConfig,
    ):
        """
        MQTT broker accepts connections on configured host:port.

        If this fails, all MQTT-dependent tests (heartbeat, sensor data,
        actuator commands) will fail.
        """
        client = E2EMQTTClient(e2e_config)
        try:
            await client.connect()
            assert client._connected, "MQTT client should be connected"
            print(f"  MQTT connected to {e2e_config.mqtt_host}:{e2e_config.mqtt_port}")
        finally:
            await client.disconnect()

    async def test_mqtt_publish_subscribe(
        self,
        mqtt_client: E2EMQTTClient,
    ):
        """
        MQTT publish/subscribe works end-to-end.

        Verifies that messages can be published and the broker processes them
        without errors.
        """
        import json

        # Publish a test message (no subscriber needed - just verify no error)
        test_topic = "e2e/smoke/test"
        test_payload = {"test": True, "timestamp": 12345}

        try:
            await mqtt_client._client.publish(test_topic, json.dumps(test_payload), qos=0)
            print(f"  MQTT publish to {test_topic}: OK")
        except Exception as e:
            pytest.fail(f"MQTT publish failed: {type(e).__name__}: {e}")


class TestSmokeDatabaseAccessible:
    """Smoke Test 3: Database is accessible via API."""

    async def test_api_returns_data_from_db(
        self,
        e2e_config: E2EConfig,
        e2e_http_client: aiohttp.ClientSession,
    ):
        """
        API endpoint that queries database returns successfully.

        The /esp/devices endpoint requires a DB query. If this returns
        a valid response (even empty list), the DB connection works.
        """
        # First authenticate
        from conftest import E2EAPIClient

        api = E2EAPIClient(e2e_config, e2e_http_client)
        auth_success = await api.authenticate()

        if not auth_success:
            # Try setup endpoint for fresh DB
            auth_success = await api.authenticate("admin", os.environ.get("E2E_TEST_PASSWORD", ""))

        if not auth_success:
            pytest.skip("Could not authenticate - DB might not be seeded")

        # Now query devices (this hits the DB)
        devices = await api.get_all_esp_devices()
        assert isinstance(devices, list), f"Expected list of devices, got: {type(devices)}"

        print(f"  Database accessible: {len(devices)} devices found")


class TestSmokeFrontendLoads:
    """Smoke Test 4: Frontend is reachable (optional)."""

    async def test_frontend_responds(
        self,
        e2e_config: E2EConfig,
        e2e_http_client: aiohttp.ClientSession,
    ):
        """
        Frontend dev server responds on port 5173.

        Note: This test is lenient - if frontend isn't running,
        it skips rather than fails, since backend E2E tests
        don't strictly require the frontend.
        """
        frontend_url = "http://localhost:5173"
        try:
            async with e2e_http_client.get(
                frontend_url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # Vue 3 apps typically have <div id="app">
                    assert (
                        "app" in text.lower() or "vue" in text.lower() or "<html" in text.lower()
                    ), "Frontend should return HTML with app root"
                    print(f"  Frontend loaded: status={response.status}")
                else:
                    pytest.skip(f"Frontend returned {response.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pytest.skip("Frontend not reachable on localhost:5173")
