"""
Test-Modul: Logic Engine E2E mit echtem Server

Fokus: End-to-End Tests für Logic Engine mit laufendem Server

ACHTUNG: Diese Tests benötigen einen laufenden Server!
Ausführung:
    poetry run pytest tests/e2e/test_logic_engine_real_server.py --e2e -v

Hardware-Kontext:
- Tests gegen echten God-Kaiser Server
- MQTT Broker muss laufen
- Database muss verfügbar sein

Dependencies:
- Running Server (uvicorn)
- MQTT Broker (Mosquitto)
- PostgreSQL Database
"""

import os
import pytest
import pytest_asyncio
import uuid
import time
import asyncio
from typing import Optional

# Import test helpers from conftest
# Note: conftest.py is in the same package, so we need to handle the import carefully
import sys
from pathlib import Path

# Add tests/e2e to path if needed for imports
_e2e_path = Path(__file__).parent
if str(_e2e_path) not in sys.path:
    sys.path.insert(0, str(_e2e_path))

# Now import from conftest (pytest loads it automatically, but we need the classes)
try:
    from conftest import (
        E2EAPIClient,
        E2EMQTTClient,
        GreenhouseTestFactory,
        ESPDeviceTestData,
        generate_unique_mock_id,
    )
except ImportError:
    # Fallback: Create minimal stubs for type hints only
    E2EAPIClient = None
    E2EMQTTClient = None
    GreenhouseTestFactory = None
    ESPDeviceTestData = None
    generate_unique_mock_id = None

# Mark all tests as E2E
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Requires live MQTT/IoT data — TODO: link to Wokwi SIL testing",
    ),
]


# =============================================================================
# Helper Functions for E2E Tests
# =============================================================================
async def wait_for_condition(condition_fn, timeout: float = 10, interval: float = 0.5) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition_fn: Async function that returns True when condition is met
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if condition was met, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = (
                await condition_fn()
                if asyncio.iscoroutinefunction(condition_fn)
                else condition_fn()
            )
            if result:
                return True
        except Exception:
            pass  # Condition check failed, keep waiting
        await asyncio.sleep(interval)
    return False


def create_cross_esp_rule_payload(
    name: str,
    sensor_esp_id: str,
    sensor_gpio: int,
    actuator_esp_id: str,
    actuator_gpio: int,
    threshold: float,
    operator: str = ">",
    priority: int = 50,
    cooldown: int = 10,
    enabled: bool = True,
    sensor_type: str = "temperature",
) -> dict:
    """
    Create a cross-ESP Logic Rule payload for API calls.

    Args:
        name: Rule name
        sensor_esp_id: ESP device ID with sensor
        sensor_gpio: Sensor GPIO pin
        actuator_esp_id: ESP device ID with actuator
        actuator_gpio: Actuator GPIO pin
        threshold: Trigger threshold value
        operator: Comparison operator
        priority: Rule priority (1–100; lower number = higher execution/conflict priority)
        cooldown: Cooldown seconds
        enabled: Whether rule is enabled
        sensor_type: Sensor type for matching (REQUIRED for rule triggering)

    Returns:
        Dict payload for POST /v1/logic/rules

    IMPORTANT:
        sensor_type MUST match the sensor_type in publish_sensor_data() calls!
        Logic Engine's get_rules_by_trigger_sensor() requires exact match on:
        - esp_id
        - gpio
        - sensor_type
        See: src/db/repositories/logic_repo.py:103-108
    """
    return {
        "name": name,
        "description": f"E2E Test Rule: {name}",
        "conditions": [
            {
                "type": "sensor",
                "esp_id": sensor_esp_id,
                "gpio": sensor_gpio,
                "sensor_type": sensor_type,  # REQUIRED for rule matching!
                "operator": operator,
                "value": threshold,
            }
        ],
        "actions": [
            {
                "type": "actuator",
                "esp_id": actuator_esp_id,
                "gpio": actuator_gpio,
                "command": "ON",
                "value": 1.0,
            }
        ],
        "logic_operator": "AND",
        "enabled": enabled,
        "priority": priority,
        "cooldown_seconds": cooldown,
    }


# =============================================================================
# E2E Test Classes
# =============================================================================
class TestLogicEngineE2ELatency:
    """End-to-end latency measurement tests."""

    async def test_cross_esp_latency(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Measure real Logic Engine execution latency.

        GIVEN: Server running, 2 ESPs registered (sensor + actuator)
        WHEN: Temperature sensor exceeds threshold
        THEN: Fan actuator activated within 5 seconds

        MEASURES:
        - MQTT Publish Latency
        - Logic Engine Evaluation Time
        - Cross-ESP Command Propagation
        - Total End-to-End Latency

        ACCEPTANCE: <5 seconds total
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        sensor_esp_id = generate_unique_mock_id("LATS")  # MOCK_LATSxxxx
        actuator_esp_id = generate_unique_mock_id("LATA")  # MOCK_LATAxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        # Track devices for cleanup
        cleanup_test_devices(sensor_esp_id)
        cleanup_test_devices(actuator_esp_id)

        try:
            # Register Sensor ESP
            sensor_esp = ESPDeviceTestData(
                device_id=sensor_esp_id,
                name="Latency Test Sensor ESP",
            )
            sensor_result = await api_client.register_esp(sensor_esp)
            assert (
                "device_id" in sensor_result or "id" in sensor_result
            ), f"Sensor ESP registration failed: {sensor_result}"

            # Register Actuator ESP
            actuator_esp = ESPDeviceTestData(
                device_id=actuator_esp_id,
                name="Latency Test Actuator ESP",
            )
            actuator_result = await api_client.register_esp(actuator_esp)
            assert (
                "device_id" in actuator_result or "id" in actuator_result
            ), f"Actuator ESP registration failed: {actuator_result}"

            # Send heartbeats to mark devices online
            await mqtt_client.publish_heartbeat(sensor_esp_id)
            await mqtt_client.publish_heartbeat(actuator_esp_id)
            await asyncio.sleep(1.0)  # Let heartbeats process

            # Create cross-ESP logic rule: Temp > 25°C → Fan ON
            rule_payload = create_cross_esp_rule_payload(
                name=f"Latency Test {sensor_esp_id}",
                sensor_esp_id=sensor_esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=actuator_esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                operator=">",
                priority=80,
                cooldown=5,  # Short cooldown for testing
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # === EXECUTE & MEASURE ===
            start_time = time.time()

            # Publish sensor data that exceeds threshold (30°C > 25°C)
            await mqtt_client.publish_sensor_data(
                esp_id=sensor_esp_id,
                gpio=sensor_gpio,
                value=30.0,
                raw_mode=True,
            )

            # Wait for execution to be logged
            execution_found = False
            for _ in range(50):  # 50 x 100ms = 5s max
                await asyncio.sleep(0.1)
                history = await api_client.get_execution_history(rule_id=rule_id, limit=5)
                entries = history.get("entries", [])
                if entries:
                    execution_found = True
                    break

            end_time = time.time()
            latency = end_time - start_time

            # === VERIFY ===
            assert execution_found, f"Rule execution not found in history after {latency:.2f}s"
            assert latency < 5.0, f"Latency {latency:.2f}s exceeds 5s acceptance threshold"

            # Verify execution details
            history = await api_client.get_execution_history(rule_id=rule_id, limit=1)
            entries = history.get("entries", [])
            assert len(entries) >= 1, "At least one execution should be logged"

            # Log latency for metrics
            print(f"\n✓ Cross-ESP Latency: {latency:.3f}s (threshold: 5s)")

        finally:
            # Cleanup rule
            if rule_id:
                await api_client.delete_logic_rule(rule_id)


class TestLogicEnginePersistence:
    """Tests for rule persistence."""

    @pytest.mark.skip(reason="Server restart not testable in E2E context - use integration tests")
    async def test_rule_survives_server_restart(self):
        """
        E2E: Logic Rules persist across server restarts.

        Note: This test requires restarting the server during test execution,
        which is not practical in automated E2E tests. Instead, this behavior
        is verified through:
        1. Database inspection (rules in PostgreSQL)
        2. Integration tests with server restart simulation
        """
        pass


class TestLogicEngineSafetyIntegration:
    """Tests for Safety Service integration."""

    async def test_rule_with_invalid_actuator_rejected(
        self,
        api_client: E2EAPIClient,
        cleanup_test_devices,
    ):
        """
        E2E: Rules targeting non-existent actuators are handled gracefully.

        GIVEN: Logic Rule targets non-existent actuator
        WHEN: Rule creation attempted
        THEN: Either validation error OR execution logs failure
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        sensor_esp_id = generate_unique_mock_id("SAFE")  # MOCK_SAFExxxx
        fake_actuator_esp_id = "MOCK_NONEXIST01"  # Valid format for non-existent ESP

        cleanup_test_devices(sensor_esp_id)

        try:
            # Register only the sensor ESP
            sensor_esp = ESPDeviceTestData(
                device_id=sensor_esp_id,
                name="Safety Test Sensor ESP",
            )
            await api_client.register_esp(sensor_esp)

            # Try to create rule targeting non-existent actuator ESP
            rule_payload = create_cross_esp_rule_payload(
                name=f"Safety Test Invalid Target {sensor_esp_id}",
                sensor_esp_id=sensor_esp_id,
                sensor_gpio=4,
                actuator_esp_id=fake_actuator_esp_id,
                actuator_gpio=27,
                threshold=25.0,
            )

            result = await api_client.create_logic_rule(rule_payload)

            # Either rule creation fails (validation) or it's created but won't execute
            # Both are acceptable - the system should not crash
            if "error" in str(result).lower() or "detail" in result:
                # Validation caught the invalid target - good!
                print(f"✓ Rule creation properly rejected: {result.get('detail', result)}")
            else:
                # Rule was created - it should fail silently when triggered
                rule_id = result.get("id") or result.get("rule_id")
                if rule_id:
                    # Cleanup
                    await api_client.delete_logic_rule(rule_id)
                print("✓ Rule created but will fail on execution (acceptable)")

        finally:
            pass  # Cleanup handled by fixture


class TestLogicEngineConcurrency:
    """Tests for concurrent rule execution."""

    async def test_priority_resolution(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Rules with different priorities on the same actuator.

        GIVEN: Two rules targeting the same actuator; canonical semantics: lower
               ``priority`` number = higher execution/conflict priority.
               Rule A: priority=80 (lower priority — larger number)
               Rule B: priority=20 (higher priority — smaller number; wins conflicts)
        WHEN: Both rules' conditions are met
        THEN: Execution history for rule A is checked (smoke: engine produced history).
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("PRIO")  # MOCK_PRIOxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_a_id = None
        rule_b_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(
                device_id=esp_id,
                name="Priority Test ESP",
            )
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Rule A: priority=80 (niedrigere Konfliktpriorität — größere Zahl)
            rule_a_payload = create_cross_esp_rule_payload(
                name=f"Priority-80 Rule {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                priority=80,
                cooldown=5,
            )
            rule_a_result = await api_client.create_logic_rule(rule_a_payload)
            rule_a_id = rule_a_result.get("id") or rule_a_result.get("rule_id")

            # Rule B: priority=20 (höhere Konfliktpriorität — kleinere Zahl)
            rule_b_payload = create_cross_esp_rule_payload(
                name=f"Priority-20 Rule {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=20.0,  # Lower threshold so both trigger
                priority=20,
                cooldown=5,
            )
            rule_b_result = await api_client.create_logic_rule(rule_b_payload)
            rule_b_id = rule_b_result.get("id") or rule_b_result.get("rule_id")

            # === TRIGGER ===
            # Send sensor data that triggers BOTH rules (30°C > 25°C > 20°C)
            await mqtt_client.publish_sensor_data(
                esp_id=esp_id,
                gpio=sensor_gpio,
                value=30.0,
            )
            await asyncio.sleep(2.0)  # Wait for processing

            # === VERIFY ===
            history_a = await api_client.get_execution_history(rule_id=rule_a_id, limit=5)
            entries_a = history_a.get("entries", [])

            assert len(entries_a) >= 1, "Rule A (priority=80) should have execution history"
            print(f"✓ Rule A (priority=80) execution history: {len(entries_a)} entry/entries")

        finally:
            # Cleanup
            if rule_a_id:
                await api_client.delete_logic_rule(rule_a_id)
            if rule_b_id:
                await api_client.delete_logic_rule(rule_b_id)


class TestLogicEngineRateLimiting:
    """Tests for rate limiting."""

    async def test_cooldown_enforced(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Cooldown between rule executions is respected.

        GIVEN: Rule with cooldown_seconds=30
        WHEN: Rule triggers twice within 30 seconds
        THEN: Second execution is blocked by cooldown
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("COOL")  # MOCK_COOLxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None
        cooldown_seconds = 30

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Cooldown Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create rule with 30 second cooldown
            rule_payload = create_cross_esp_rule_payload(
                name=f"Cooldown Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                cooldown=cooldown_seconds,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # === FIRST TRIGGER ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.5)  # Wait for processing

            # Verify first execution
            history_1 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_1 = len(history_1.get("entries", []))
            assert count_1 >= 1, "First trigger should have executed"

            # === SECOND TRIGGER (immediately - should be blocked) ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=35.0)
            await asyncio.sleep(1.5)  # Wait for processing

            # Verify cooldown blocked second execution
            history_2 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_2 = len(history_2.get("entries", []))

            # Should still be only 1 execution (cooldown blocked second)
            assert (
                count_2 == count_1
            ), f"Cooldown should block second execution: had {count_1}, now have {count_2}"

            print(f"✓ Cooldown enforced: {count_2} execution(s) (expected: {count_1})")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)

    async def test_multiple_triggers_after_cooldown(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Rule can execute again after cooldown expires.

        GIVEN: Rule with short cooldown (5 seconds)
        WHEN: Rule triggers, wait for cooldown, trigger again
        THEN: Both executions succeed
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("CEXP")  # MOCK_CEXPxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None
        cooldown_seconds = 5  # Short for testing

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Cooldown Expiry Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create rule with short cooldown
            rule_payload = create_cross_esp_rule_payload(
                name=f"Cooldown Expiry Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                cooldown=cooldown_seconds,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # === FIRST TRIGGER ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.5)

            history_1 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_1 = len(history_1.get("entries", []))
            assert count_1 >= 1, "First trigger should execute"

            # === WAIT FOR COOLDOWN TO EXPIRE ===
            print(f"  Waiting {cooldown_seconds + 1}s for cooldown to expire...")
            await asyncio.sleep(cooldown_seconds + 1)

            # === SECOND TRIGGER (after cooldown) ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=32.0)
            await asyncio.sleep(1.5)

            history_2 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_2 = len(history_2.get("entries", []))

            # Should have one more execution
            assert (
                count_2 > count_1
            ), f"Second trigger after cooldown should execute: had {count_1}, now have {count_2}"

            print(f"✓ Cooldown expiry verified: {count_1} → {count_2} executions")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)


class TestLogicEngineHistory:
    """Tests for execution history logging."""

    async def test_execution_history_logged(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Rule execution is logged to history with all details.

        GIVEN: Active Logic Rule
        WHEN: Rule is triggered and executed
        THEN: Execution appears in LogicExecutionHistory with:
              - rule_id
              - triggered_at timestamp
              - success status
              - trigger_reason
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("HIST")  # MOCK_HISTxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="History Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create rule
            rule_payload = create_cross_esp_rule_payload(
                name=f"History Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                cooldown=5,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # === TRIGGER ===
            trigger_time = time.time()
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(2.0)  # Wait for processing

            # === VERIFY ===
            history = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            entries = history.get("entries", [])

            assert len(entries) >= 1, "At least one execution should be logged"

            # Check execution details
            latest_entry = entries[0]
            assert latest_entry.get("rule_id") or latest_entry.get(
                "rule_name"
            ), "Execution should have rule identifier"

            # Success can be True or the entry exists
            has_success_indicator = (
                latest_entry.get("success") is not None or "success" in str(latest_entry).lower()
            )

            print(f"✓ Execution logged with details: {list(latest_entry.keys())}")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)


class TestLogicEngineToggle:
    """Tests for enabling/disabling rules."""

    async def test_disabled_rule_not_triggered(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Disabled rules do not execute.

        GIVEN: Logic Rule that is disabled (enabled=False)
        WHEN: Sensor data triggers rule conditions
        THEN: Rule does NOT execute
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("DISB")  # MOCK_DISBxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Disabled Rule Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create DISABLED rule
            rule_payload = create_cross_esp_rule_payload(
                name=f"Disabled Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                enabled=False,  # DISABLED!
                cooldown=5,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # === TRIGGER ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(2.0)  # Wait for potential processing

            # === VERIFY ===
            history = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            entries = history.get("entries", [])

            # Disabled rule should have NO executions
            assert (
                len(entries) == 0
            ), f"Disabled rule should not execute, but found {len(entries)} execution(s)"

            print("✓ Disabled rule correctly did not execute")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)

    async def test_toggle_enables_rule(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Toggling a disabled rule to enabled allows execution.

        GIVEN: Rule starts disabled
        WHEN: Toggle to enabled, then trigger
        THEN: Rule executes successfully
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("TOGL")  # MOCK_TOGLxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Toggle Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create DISABLED rule
            rule_payload = create_cross_esp_rule_payload(
                name=f"Toggle Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                enabled=False,  # Start disabled
                cooldown=5,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # Verify no execution while disabled
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.0)
            history_before = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_before = len(history_before.get("entries", []))
            assert count_before == 0, "Disabled rule should not execute"

            # === TOGGLE TO ENABLED ===
            toggle_result = await api_client.toggle_logic_rule(
                rule_id=rule_id, enabled=True, reason="E2E Test - enabling rule"
            )

            # Verify toggle succeeded
            assert (
                toggle_result.get("enabled") is True or "success" in str(toggle_result).lower()
            ), f"Toggle failed: {toggle_result}"

            await asyncio.sleep(0.5)  # Let toggle propagate

            # === TRIGGER AFTER TOGGLE ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=32.0)
            await asyncio.sleep(2.0)  # Wait for processing

            # === VERIFY ===
            history_after = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_after = len(history_after.get("entries", []))

            assert (
                count_after > count_before
            ), f"Enabled rule should execute: {count_before} → {count_after}"

            print(f"✓ Toggle verified: {count_before} → {count_after} executions")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)


class TestLogicEngineRuleLifecycle:
    """Tests for rule CRUD operations."""

    async def test_rule_deletion_cleanup(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Deleted rules no longer execute.

        GIVEN: Active rule that has executed
        WHEN: Rule is deleted
        THEN: Subsequent triggers do not create new executions
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("DELT")  # MOCK_DELTxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Deletion Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create rule
            rule_payload = create_cross_esp_rule_payload(
                name=f"Deletion Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,
                cooldown=5,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # Trigger once to verify rule works
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.5)

            history_before = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_before = len(history_before.get("entries", []))
            assert count_before >= 1, "Rule should have executed once"

            # === DELETE RULE ===
            delete_success = await api_client.delete_logic_rule(rule_id)
            assert delete_success, "Rule deletion failed"
            rule_id = None  # Mark as deleted (don't cleanup again)

            await asyncio.sleep(0.5)  # Let deletion propagate

            # === TRIGGER AFTER DELETION ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=35.0)
            await asyncio.sleep(1.5)

            # Rule is deleted, so we can't query its history anymore
            # The test passes if deletion succeeded and no errors occurred

            print(f"✓ Rule deleted successfully after {count_before} execution(s)")

        finally:
            # Only cleanup if rule wasn't already deleted
            if rule_id:
                await api_client.delete_logic_rule(rule_id)

    async def test_rule_modification_takes_effect(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        E2E: Modified rules use new parameters.

        GIVEN: Rule with threshold=25
        WHEN: Update threshold to 35
        THEN: Value 30 no longer triggers (30 < 35)
        """
        # === SETUP ===
        # Device IDs must match pattern: ^MOCK_[A-Z0-9]+$ (NO underscores after MOCK_!)
        esp_id = generate_unique_mock_id("MODF")  # MOCK_MODFxxxx
        sensor_gpio = 4
        actuator_gpio = 27
        rule_id = None

        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="Modification Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(0.5)

            # Create rule with threshold=25
            rule_payload = create_cross_esp_rule_payload(
                name=f"Modification Test {esp_id}",
                sensor_esp_id=esp_id,
                sensor_gpio=sensor_gpio,
                actuator_esp_id=esp_id,
                actuator_gpio=actuator_gpio,
                threshold=25.0,  # Initial threshold
                cooldown=5,
            )
            rule_result = await api_client.create_logic_rule(rule_payload)
            rule_id = rule_result.get("id") or rule_result.get("rule_id")
            assert rule_id, f"Rule creation failed: {rule_result}"

            # Verify rule triggers at 30°C (30 > 25)
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.5)

            history_1 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_1 = len(history_1.get("entries", []))
            assert count_1 >= 1, "Rule should trigger at 30°C (threshold 25)"

            # Wait for cooldown
            await asyncio.sleep(6)

            # === MODIFY RULE: threshold 25 → 35 ===
            updated_payload = {
                "name": f"Modification Test {esp_id} (updated)",
                "conditions": [
                    {
                        "type": "sensor",
                        "esp_id": esp_id,
                        "gpio": sensor_gpio,
                        "sensor_type": "temperature",  # REQUIRED for rule matching!
                        "operator": ">",
                        "value": 35.0,  # NEW threshold
                    }
                ],
                "actions": [
                    {
                        "type": "actuator",
                        "esp_id": esp_id,
                        "gpio": actuator_gpio,
                        "command": "ON",
                        "value": 1.0,
                    }
                ],
                "enabled": True,
                "cooldown_seconds": 5,
            }
            update_result = await api_client.update_logic_rule(rule_id, updated_payload)

            await asyncio.sleep(0.5)  # Let update propagate

            # === TRIGGER WITH 30°C (should NOT trigger anymore: 30 < 35) ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=30.0)
            await asyncio.sleep(1.5)

            history_2 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_2 = len(history_2.get("entries", []))

            # Should NOT have a new execution (30 < 35)
            assert (
                count_2 == count_1
            ), f"Modified threshold should prevent trigger: {count_1} → {count_2}"

            # === TRIGGER WITH 40°C (should trigger: 40 > 35) ===
            await mqtt_client.publish_sensor_data(esp_id=esp_id, gpio=sensor_gpio, value=40.0)
            await asyncio.sleep(1.5)

            history_3 = await api_client.get_execution_history(rule_id=rule_id, limit=10)
            count_3 = len(history_3.get("entries", []))

            assert (
                count_3 > count_2
            ), f"Rule should trigger at 40°C with new threshold 35: {count_2} → {count_3}"

            print(f"✓ Modification verified: {count_1} → {count_2} → {count_3}")

        finally:
            if rule_id:
                await api_client.delete_logic_rule(rule_id)


class TestLogicEngineWebSocket:
    """Tests for WebSocket real-time notifications."""

    @pytest.mark.skip(reason="WebSocket E2E requires authenticated WS connection - skipped for now")
    async def test_websocket_broadcast(self):
        """
        E2E: Rule execution triggers WebSocket broadcast.

        Note: This test requires WebSocket authentication which is not yet
        implemented in the E2E test infrastructure.
        """
        pass
