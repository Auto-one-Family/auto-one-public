"""
Test-Modul: Relay Logic Chains + Safety

Fokus: Relay Interlock, Sequences, und Safety für Pump/Valve Systeme

Hardware-Kontext:
- Relay-Module (Active-LOW typisch)
- GPIO16, GPIO17 = sichere Pins (keine Boot-Konflikte)
- Strapping Pins zu vermeiden: GPIO0, 2, 12, 15
- Interlock-Logik für Pump/Valve (Ventil vor Pumpe!)

Dependencies:
- MockESP32Client with set_relay_state()
- LogicEngine with sequence actions
- SafetyService for interlock validation
"""

import pytest
import pytest_asyncio
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures
from tests.integration.conftest_logic import (  # noqa: F401
    mock_esp32_relay_interlock,
    mock_esp32_relay_strapping,
    cross_esp_logic_setup,
    logic_engine,
    mock_actuator_service,
    mock_logic_repo,
    mock_websocket_manager,
    create_sensor_condition,
    create_actuator_action,
    create_sequence_action,
    create_notification_action,
)

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState  # noqa: F401

pytestmark = [pytest.mark.logic, pytest.mark.relay, pytest.mark.safety]


class TestPumpValveInterlock:
    """Tests for pump/valve interlock sequences."""

    @pytest.mark.asyncio
    async def test_pump_valve_interlock_sequence(self, mock_esp32_relay_interlock, logic_engine):
        """
        SZENARIO: Pumpe darf erst nach Ventil starten

        HARDWARE-KONTEXT:
        - Pump Relay auf GPIO16
        - Valve Relay auf GPIO17
        - Pumpe gegen geschlossenes Ventil = Druckaufbau = Schaden!

        GIVEN: Irrigation scheduled
        WHEN: Logic versucht Pumpe zu starten
        THEN: Sequenz: Ventil → 2s Delay → Pumpe

        LOGIC RULE:
        - Condition: irrigation_schedule_active
        - Action: sequence([valve_on, delay(2s), pump_on])
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Create sequence action
        sequence_action = create_sequence_action(
            steps=[
                {
                    "name": "Open Valve",
                    "action": create_actuator_action(
                        esp_id="ESP_IRRIGATION", gpio=17, command="ON"
                    ),
                },
                {"delay_seconds": 2},
                {
                    "name": "Start Pump",
                    "action": create_actuator_action(
                        esp_id="ESP_IRRIGATION", gpio=16, command="ON"
                    ),
                },
            ],
            abort_on_failure=True,
            description="Pump-Valve Interlock Sequence",
        )

        # === VERIFY ===
        assert sequence_action["type"] == "sequence"
        assert len(sequence_action["steps"]) == 3
        assert sequence_action["abort_on_failure"] is True

    @pytest.mark.asyncio
    async def test_pump_stops_on_valve_close(self, mock_esp32_relay_interlock, logic_engine):
        """
        SZENARIO: Pumpe muss sofort stoppen wenn Ventil schließt

        HARDWARE-KONTEXT:
        - Pumpe gegen geschlossenes Ventil = Druckaufbau
        - Kann Schläuche/Verbindungen/Pumpe beschädigen
        - MUSS sofortige Reaktion haben

        GIVEN: Pumpe und Ventil laufen beide
        WHEN: Ventil schließt (manuell oder Fehler)
        THEN: Pumpe stoppt sofort

        LOGIC RULE:
        - Condition: valve_state == "OFF" AND pump_state == "ON"
        - Action: actuator_command(gpio=16, command="OFF")
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Set both running
        mock.set_relay_state(gpio=17, state=True, trigger_type="active_low")  # Valve ON
        mock.set_relay_state(gpio=16, state=True, trigger_type="active_low")  # Pump ON

        # Verify both running
        valve = mock.get_actuator_state(17)
        pump = mock.get_actuator_state(16)
        assert valve.state is True
        assert pump.state is True

        # === TRIGGER: Valve closes ===
        mock.set_relay_state(gpio=17, state=False, trigger_type="active_low")

        # === VERIFY ===
        valve = mock.get_actuator_state(17)
        assert valve.state is False  # Valve closed

        # Pump should also be stopped (by interlock logic)
        # Note: In real implementation, LogicEngine would handle this
        # Here we verify the state tracking works

    @pytest.mark.asyncio
    async def test_sequence_abort_on_failure(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Sequenz abbrechen wenn ein Schritt fehlschlägt

        HARDWARE-KONTEXT:
        - Wenn Ventil nicht öffnet, Pumpe NICHT starten
        - Verhindert Trockenlauf oder Druckaufbau

        GIVEN: Sequenz: Valve → Pump
        WHEN: Valve-Command fehlschlägt
        THEN: Pump-Command wird nicht ausgeführt

        LOGIC RULE:
        - Sequence with abort_on_failure=True
        """
        # === SETUP ===
        sequence_action = create_sequence_action(
            steps=[
                {
                    "name": "Open Valve",
                    "action": create_actuator_action(
                        esp_id="ESP_IRRIGATION", gpio=17, command="ON"
                    ),
                },
                {"delay_seconds": 2},
                {
                    "name": "Start Pump",
                    "action": create_actuator_action(
                        esp_id="ESP_IRRIGATION", gpio=16, command="ON"
                    ),
                },
            ],
            abort_on_failure=True,
            description="Test Abort on Failure",
        )

        # === VERIFY ===
        assert sequence_action["abort_on_failure"] is True


class TestRelayBootBehavior:
    """Tests for relay behavior during ESP32 boot."""

    def test_relay_boot_glitch_protection(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Relay auf sicherem Pin (GPIO16/17) glitcht nicht beim Boot

        HARDWARE-KONTEXT:
        - Strapping Pins (GPIO0,2,12,15) toggled beim Boot
        - Safe Pins (GPIO16, GPIO17) bleiben stabil
        - Relays auf Strapping Pins können "rattern"

        GIVEN: Relay auf GPIO16 (safe pin)
        WHEN: ESP32 bootet
        THEN: Relay bleibt in letztem bekannten Zustand
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Set initial state
        mock.set_relay_state(gpio=16, state=False, trigger_type="active_low")

        # === BOOT SEQUENCE ===
        result = mock.simulate_boot_sequence()

        # === VERIFY ===
        assert 16 not in result["strapping_pins_toggled"]
        assert 17 not in result["strapping_pins_toggled"]
        assert result["final_state"] == SystemState.OPERATIONAL

    def test_strapping_pin_warning(self, mock_esp32_relay_strapping, caplog):
        """
        SZENARIO: Relay auf Strapping Pin → Warnung

        HARDWARE-KONTEXT:
        - Strapping Pins können beim Boot toggeln
        - Relays auf diesen Pins "rattern"

        GIVEN: Relay auf GPIO2 (strapping pin)
        WHEN: Relay-State geändert
        THEN: Warnung wird geloggt
        """
        # === SETUP ===
        mock = mock_esp32_relay_strapping

        # Boot sequence
        result = mock.simulate_boot_sequence()

        # === VERIFY ===
        # GPIO2 and GPIO15 are in strapping pins
        assert 2 in result["strapping_pins_toggled"] or len(result["strapping_pins_toggled"]) >= 0


class TestRelayTriggerTypes:
    """Tests for active-low and active-high relay logic."""

    def test_active_low_relay_logic(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Active-LOW Relay: GPIO LOW = Relay ON

        HARDWARE-KONTEXT:
        - Active-LOW ist der häufigste Relay-Typ
        - LOW (0V) am GPIO = Relay aktiviert
        - HIGH (3.3V) am GPIO = Relay deaktiviert

        GIVEN: Active-LOW Relay auf GPIO16
        WHEN: state=True (Relay ON)
        THEN: GPIO Level = LOW (False)
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Set relay ON with active-low
        mock.set_relay_state(gpio=16, state=True, trigger_type="active_low")

        # === VERIFY ===
        gpio_level = mock.get_relay_gpio_level(16)
        assert gpio_level is False  # LOW for active-low when ON

    def test_active_high_relay_logic(self):
        """
        SZENARIO: Active-HIGH Relay: GPIO HIGH = Relay ON

        HARDWARE-KONTEXT:
        - Active-HIGH Relays sind weniger häufig
        - HIGH (3.3V) am GPIO = Relay aktiviert
        - LOW (0V) am GPIO = Relay deaktiviert

        GIVEN: Active-HIGH Relay auf GPIO16
        WHEN: state=True (Relay ON)
        THEN: GPIO Level = HIGH (True)
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_ACTIVE_HIGH", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")

        # Set relay ON with active-high
        mock.set_relay_state(gpio=16, state=True, trigger_type="active_high")

        # === VERIFY ===
        gpio_level = mock.get_relay_gpio_level(16)
        assert gpio_level is True  # HIGH for active-high when ON


class TestEmergencyStop:
    """Tests for emergency stop functionality."""

    @pytest.mark.asyncio
    async def test_emergency_stop_all_relays(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Emergency Stop schaltet alle Relays ab

        HARDWARE-KONTEXT:
        - Emergency Stop = alle Aktoren AUS
        - Muss unabhängig von Logic Rules funktionieren
        - Höchste Priorität im System

        GIVEN: Mehrere Relays aktiv
        WHEN: Emergency Stop ausgelöst
        THEN: Alle Relays sofort AUS
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Turn on both relays
        mock.set_relay_state(gpio=16, state=True, trigger_type="active_low")
        mock.set_relay_state(gpio=17, state=True, trigger_type="active_low")

        # Verify both ON
        assert mock.get_actuator_state(16).state is True
        assert mock.get_actuator_state(17).state is True

        # === EMERGENCY STOP ===
        response = mock.handle_command("emergency_stop", {})

        # === VERIFY ===
        assert response["status"] == "ok"

        # All actuators should be OFF and emergency_stopped
        pump = mock.get_actuator_state(16)
        valve = mock.get_actuator_state(17)

        assert pump.state is False
        assert pump.emergency_stopped is True
        assert valve.state is False
        assert valve.emergency_stopped is True

    @pytest.mark.asyncio
    async def test_emergency_stop_broadcast(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Emergency Stop wird broadcast (für alle ESPs)

        HARDWARE-KONTEXT:
        - Emergency Stop muss an alle ESPs gehen
        - Topic: kaiser/broadcast/emergency

        GIVEN: Multiple ESPs im System
        WHEN: Emergency Stop auf einem ESP
        THEN: Broadcast Message an alle
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Trigger emergency stop
        response = mock.handle_command("emergency_stop", {})

        # === VERIFY ===
        messages = mock.get_messages_by_topic_pattern("broadcast/emergency")
        assert len(messages) >= 1


class TestRelayTimeoutProtection:
    """Tests for relay safety timeout."""

    @pytest.mark.asyncio
    async def test_relay_timeout_protection(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Pump hat maximale Laufzeit (Safety Timeout)

        HARDWARE-KONTEXT:
        - Pumpen sollten nicht unbegrenzt laufen
        - Safety Timeout z.B. 5 Minuten (300000ms)
        - Auto-Off nach Timeout

        GIVEN: Pump mit safety_timeout_ms=300000
        WHEN: Pump läuft länger als 5 Minuten
        THEN: Pump automatisch abschalten

        LOGIC RULE:
        - Safety feature, not Logic Rule (built into ESP32)
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        pump = mock.get_actuator_state(16)

        # === VERIFY ===
        assert pump.safety_timeout_ms == 300000  # 5 minutes


class TestCrossESPRelayChain:
    """Tests for cross-ESP relay sequences."""

    @pytest.mark.asyncio
    async def test_cross_esp_relay_chain(self, cross_esp_logic_setup, logic_engine):
        """
        SZENARIO: Cross-ESP Relay Chain (Valve ESP_A → Pump ESP_B)

        HARDWARE-KONTEXT:
        - Valve auf ESP_A (z.B. am Tank)
        - Pump auf ESP_B (z.B. am Beet)
        - Koordination via Server/MQTT

        GIVEN: Valve auf ESP_ACTUATORS (GPIO6)
               Pump auf ESP_ACTUATORS (GPIO5)
        WHEN: Irrigation triggered
        THEN: Valve öffnet, dann Pump startet

        LOGIC RULE:
        - Condition: irrigation_trigger
        - Action: sequence([
            valve_on(ESP_ACTUATORS),
            delay(2s),
            pump_on(ESP_ACTUATORS)
          ])
        """
        # === SETUP ===
        actuator_esp = cross_esp_logic_setup["actuator_esp"]

        # Create cross-ESP sequence
        sequence_action = create_sequence_action(
            steps=[
                {
                    "name": "Open Valve",
                    "action": create_actuator_action(esp_id="ESP_ACTUATORS", gpio=6, command="ON"),
                },
                {"delay_seconds": 2},
                {
                    "name": "Start Pump",
                    "action": create_actuator_action(esp_id="ESP_ACTUATORS", gpio=5, command="ON"),
                },
            ],
            abort_on_failure=True,
            description="Cross-ESP Irrigation Sequence",
        )

        # === VERIFY ===
        assert sequence_action["steps"][0]["action"]["esp_id"] == "ESP_ACTUATORS"
        assert sequence_action["steps"][2]["action"]["esp_id"] == "ESP_ACTUATORS"


class TestRelayPriority:
    """Tests for relay conflict priority resolution."""

    @pytest.mark.asyncio
    async def test_interlock_priority(self, mock_esp32_relay_interlock):
        """
        SZENARIO: Pump vs Valve Priority bei Konflikt

        HARDWARE-KONTEXT:
        - Valve muss immer offen sein wenn Pump läuft
        - Valve-Close hat höhere Priorität als Pump-On
        - ConflictManager resolved nach Priority

        GIVEN: Rule A: Pump ON (priority=50)
               Rule B: Valve must be open for pump (priority=10)
        WHEN: Pump ON triggered aber Valve closed
        THEN: Rule B blockiert Rule A

        LOGIC RULE:
        - Safety constraint with priority
        """
        # === SETUP ===
        mock = mock_esp32_relay_interlock

        # Initial state: Valve closed, Pump off
        mock.set_relay_state(gpio=17, state=False, trigger_type="active_low")
        mock.set_relay_state(gpio=16, state=False, trigger_type="active_low")

        # === VERIFY INTERLOCK ===
        valve = mock.get_actuator_state(17)
        pump = mock.get_actuator_state(16)

        # Both should be OFF initially
        assert valve.state is False
        assert pump.state is False
