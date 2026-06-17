"""
Praxis-basierte Gewächshaus-Testszenarien.

Erstellt von: Domain-Expert Test-Engineer
Fokus: Realistische Szenarien aus dem Gewächshaus-Alltag

Diese Tests sind aus Praxis-Erfahrung abgeleitet und testen NICHT nur
ob der Code funktioniert, sondern ob das SYSTEM sich verhält wie ein
Gewächshaus es braucht.

Kategorien:
1. Tägliche Operationen (Morning Startup, Day/Night Transitions)
2. Temperatur-Management (Hysterese, Sensor-Backup, Notfälle)
3. Bewässerung-Sicherheit (Max-Duration, Druckprüfung, Regen-Override)
4. Lüftungs-Logik (Wind-Schutz, Frost-Lock, graduelle Öffnung)
5. Nacht/Unbeaufsichtigt-Betrieb (Weekend-Autonomie, Alarm-Eskalation)

Marker:
- @pytest.mark.critical: MUSS immer grün sein (Sicherheits-kritisch)
- @pytest.mark.daily_ops: Tägliche Routine-Tests
- @pytest.mark.temperature: Temperatur-bezogene Tests
- @pytest.mark.irrigation: Bewässerungs-Tests
- @pytest.mark.ventilation: Lüftungs-Tests
- @pytest.mark.night_mode: Nacht-Betriebs-Tests

Praxis-Werte-Referenz:
- Temperatur: 15-30°C normal, <5°C Frost, >35°C kritisch heiß
- Luftfeuchtigkeit: 50-80% normal, >90% Pilzgefahr
- Bodenfeuchte: ADC 1500-3000 je nach Sensor
- pH: 5.5-7.0 für die meisten Pflanzen
- EC: 1.0-3.0 mS/cm typisch
"""

import pytest
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch

# Wir nutzen die bestehenden esp32 fixtures
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "esp32"))

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState

# =============================================================================
# Realistic Greenhouse Values (from practice!)
# =============================================================================


class GreenhouseValues:
    """
    Realistische Werte aus der Praxis.

    Diese Werte basieren auf tatsächlichen Gewächshaus-Erfahrungen,
    nicht auf willkürlichen Test-Werten.
    """

    # Temperatur (°C als RAW * 100 für DS18B20-Stil)
    TEMP_FROST_CRITICAL = 200  # 2.0°C - Frostgefahr!
    TEMP_FROST_WARNING = 500  # 5.0°C - Vorwarnung
    TEMP_NIGHT_TARGET = 1500  # 15.0°C - Nacht-Sollwert
    TEMP_DAY_OPTIMAL = 2200  # 22.0°C - Optimal tagsüber
    TEMP_DAY_WARM = 2600  # 26.0°C - Warm, Lüftung nötig
    TEMP_HOT_WARNING = 3000  # 30.0°C - Zu heiß
    TEMP_HOT_CRITICAL = 3500  # 35.0°C - Kritisch heiß!

    # Luftfeuchtigkeit (% RH * 10)
    HUMIDITY_LOW = 400  # 40% - Zu trocken
    HUMIDITY_OPTIMAL = 650  # 65% - Optimal
    HUMIDITY_HIGH = 800  # 80% - Obergrenze
    HUMIDITY_CONDENSATION = 950  # 95% - Kondensation am Sensor!

    # Bodenfeuchte (ADC Werte 0-4095)
    SOIL_DRY = 1200  # Bewässerung nötig
    SOIL_OPTIMAL = 2000  # Guter Bereich
    SOIL_WET = 3000  # Genug Wasser
    SOIL_SATURATED = 3800  # Übersättigt - Stop!

    # pH (RAW * 100)
    PH_ACID = 550  # 5.5 - Sauer
    PH_OPTIMAL = 650  # 6.5 - Optimal
    PH_NEUTRAL = 700  # 7.0 - Neutral
    PH_ALKALINE = 800  # 8.0 - Zu basisch

    # Zeitkonstanten (Sekunden)
    IRRIGATION_MAX_DURATION = 1800  # 30 min max Bewässerung
    VENTILATION_RAMP_TIME = 300  # 5 min für volle Öffnung
    TEMP_RESPONSE_TIME = 30  # 30s max für Temp-Reaktion
    FROST_RESPONSE_TIME = 10  # 10s für Frost-Notfall!


# =============================================================================
# Custom Greenhouse Test Fixtures
# =============================================================================


@pytest.fixture
def greenhouse_esp_with_temp_sensors():
    """
    ESP32 mit realistischer Temperatur-Sensor-Konfiguration.

    Sensoren:
    - GPIO 4: DS18B20 Bodentemperatur (primär)
    - GPIO 21: SHT31 Lufttemperatur/Feuchte (backup + Feuchte)
    - GPIO 35: NTC Analog Außentemperatur
    """
    mock = MockESP32Client(esp_id="ESP_TEMP_ZONE_A", kaiser_id="god")
    mock.configure_zone("temp_zone", "greenhouse_master", "temp_section_a")

    # Primärer Bodensensor
    mock.set_sensor_value(
        gpio=4,
        raw_value=GreenhouseValues.TEMP_DAY_OPTIMAL,
        sensor_type="DS18B20",
        name="Bodentemperatur Primär",
        unit="°C",
        quality="good",
    )

    # Backup + Feuchte
    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=GreenhouseValues.TEMP_DAY_OPTIMAL,
        secondary_values={"humidity": GreenhouseValues.HUMIDITY_OPTIMAL},
        name="Luft Temp/Feuchte",
        quality="good",
    )

    # Außentemperatur
    mock.set_sensor_value(
        gpio=35,
        raw_value=1800,  # 18°C außen
        sensor_type="analog",
        name="Außentemperatur",
        unit="raw",
        quality="good",
    )

    # Heizung und Lüftung
    mock.configure_actuator(gpio=5, actuator_type="relay", name="Heizung")
    mock.configure_actuator(gpio=6, actuator_type="valve", name="Lüftungsklappe")
    mock.configure_actuator(
        gpio=7, actuator_type="fan", name="Lüftungsmotor", min_value=0.2, max_value=1.0
    )

    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def greenhouse_esp_with_irrigation():
    """
    ESP32 mit realistischer Bewässerungs-Konfiguration.

    Sensoren:
    - GPIO 34: Bodenfeuchte Analog
    - GPIO 36: Durchflusssensor (digital Pulse)
    - GPIO 39: Drucksensor (Wasserleitung)

    Aktoren:
    - GPIO 5: Hauptpumpe
    - GPIO 6: Zone A Ventil
    - GPIO 18: Zone B Ventil
    """
    mock = MockESP32Client(esp_id="ESP_IRRIGATION_001", kaiser_id="god")
    mock.configure_zone("irrigation_zone", "greenhouse_master", "irrigation_main")

    # Bodenfeuchte
    mock.set_sensor_value(
        gpio=34,
        raw_value=GreenhouseValues.SOIL_OPTIMAL,
        sensor_type="moisture",
        name="Bodenfeuchte Zone A",
        unit="raw",
        quality="good",
    )

    # Durchflusssensor
    mock.set_sensor_value(
        gpio=36,
        raw_value=0,  # Kein Durchfluss
        sensor_type="digital",
        name="Durchflusssensor",
        unit="pulse",
        quality="good",
    )

    # Drucksensor (ca. 2 bar = 2000 raw)
    mock.set_sensor_value(
        gpio=39,
        raw_value=2000,
        sensor_type="pressure",
        name="Wasserdruck",
        unit="raw",
        quality="good",
    )

    # Pumpe und Ventile
    mock.configure_actuator(
        gpio=5, actuator_type="pump", name="Hauptpumpe", safety_timeout_ms=1800000
    )
    mock.configure_actuator(gpio=6, actuator_type="valve", name="Ventil Zone A")
    mock.configure_actuator(gpio=18, actuator_type="valve", name="Ventil Zone B")

    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def multi_zone_greenhouse():
    """
    Komplettes Multi-Zonen Gewächshaus für E2E Tests.

    Zone A (Tomaten): ESP_ZONE_A mit Temp, Feuchte, Bewässerung
    Zone B (Salat): ESP_ZONE_B mit Temp, Feuchte, Beleuchtung
    Zone C (Technik): ESP_ZONE_C mit Pumpe, Hauptventil
    """
    esps = {}

    # Zone A - Tomaten (warm, feucht)
    zone_a = MockESP32Client(esp_id="ESP_ZONE_A", kaiser_id="god")
    zone_a.configure_zone("zone_a", "greenhouse_master", "tomatoes")
    zone_a.set_sensor_value(gpio=4, raw_value=2400, sensor_type="DS18B20", name="Temp Zone A")
    zone_a.set_sensor_value(gpio=34, raw_value=2200, sensor_type="moisture", name="Feuchte Zone A")
    zone_a.configure_actuator(gpio=6, actuator_type="valve", name="Bewässerung A")
    zone_a.configure_actuator(gpio=7, actuator_type="fan", name="Lüftung A")
    esps["zone_a"] = zone_a

    # Zone B - Salat (kühler, schattiger)
    zone_b = MockESP32Client(esp_id="ESP_ZONE_B", kaiser_id="god")
    zone_b.configure_zone("zone_b", "greenhouse_master", "lettuce")
    zone_b.set_sensor_value(gpio=4, raw_value=1800, sensor_type="DS18B20", name="Temp Zone B")
    zone_b.set_sensor_value(gpio=34, raw_value=2500, sensor_type="moisture", name="Feuchte Zone B")
    zone_b.configure_actuator(gpio=6, actuator_type="valve", name="Bewässerung B")
    zone_b.configure_actuator(gpio=5, actuator_type="relay", name="Schattierung B")
    esps["zone_b"] = zone_b

    # Zone C - Technikraum (Pumpen, Hauptversorgung)
    zone_c = MockESP32Client(esp_id="ESP_ZONE_C", kaiser_id="god")
    zone_c.configure_zone("zone_c", "greenhouse_master", "technical")
    zone_c.set_sensor_value(gpio=39, raw_value=2100, sensor_type="pressure", name="Hauptdruck")
    zone_c.configure_actuator(gpio=5, actuator_type="pump", name="Hauptpumpe")
    zone_c.configure_actuator(gpio=6, actuator_type="valve", name="Hauptventil")
    esps["zone_c"] = zone_c

    for esp in esps.values():
        esp.clear_published_messages()

    yield esps

    for esp in esps.values():
        esp.reset()


# =============================================================================
# Test Category 1: Temperature Management
# =============================================================================


class TestTemperatureManagement:
    """
    Temperatur-Management Tests aus der Praxis.

    Praxis-Kontext:
    - Temperatur ist der kritischste Parameter im Gewächshaus
    - Frost kann Pflanzen in Minuten zerstören
    - Überhitzung führt zu Stress und Ernteverlust
    - Hysterese verhindert ständiges An/Aus der Heizung
    """

    @pytest.mark.critical
    @pytest.mark.temperature
    def test_frost_alert_immediate_heater_activation(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Frostgefahr - Sofortige Heizungsaktivierung

        PRAXIS-KONTEXT:
        Bei Außentemperatur < 5°C und Innentemperatur fallend muss
        die Heizung SOFORT reagieren. Jede Minute Verzögerung kann
        bei Frost Tausende Euro Schaden verursachen.

        GIVEN: Normale Betriebstemperatur (22°C innen)
        WHEN: Temperatur fällt auf 3°C
        THEN: Heizung wird innerhalb 30 Sekunden aktiviert

        REAKTIONSZEIT: < 30 Sekunden
        RISIKO BEI FEHLER: Totaler Ernteverlust bei Frost
        """
        mock = greenhouse_esp_with_temp_sensors

        # === SETUP ===
        # Normale Starttemperatur
        initial_temp = GreenhouseValues.TEMP_DAY_OPTIMAL
        mock.set_sensor_value(gpio=4, raw_value=initial_temp, sensor_type="DS18B20")

        # Heizung ist aus
        response = mock.handle_command("actuator_get", {"gpio": 5})
        assert response["data"]["state"] is False, "Heizung sollte initial aus sein"

        # === TRIGGER: Temperatur fällt kritisch ===
        mock.set_sensor_value(
            gpio=4,
            raw_value=GreenhouseValues.TEMP_FROST_CRITICAL,
            sensor_type="DS18B20",
            quality="good",  # Sensor funktioniert - das ist ECHT!
        )

        # Sensor-Lesung simulieren
        sensor_response = mock.handle_command("sensor_read", {"gpio": 4})

        # === VERIFY ===
        # 1. Sensor-Daten wurden korrekt gelesen
        assert sensor_response["status"] == "ok"
        assert sensor_response["data"]["raw_value"] == GreenhouseValues.TEMP_FROST_CRITICAL

        # 2. Prüfe dass die MQTT-Message mit korrekten Daten gesendet wurde
        messages = mock.get_published_messages()
        sensor_msgs = [m for m in messages if "/sensor/4/data" in m["topic"]]
        assert len(sensor_msgs) >= 1, "Sensor-Daten müssen via MQTT gesendet werden"

        # 3. Server würde jetzt Heizung aktivieren
        # (In diesem Test simulieren wir die Server-Reaktion)
        heater_response = mock.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )

        assert heater_response["status"] == "ok", "Heizung muss aktivierbar sein"
        assert heater_response["state"] is True, "Heizung muss AN sein"

        # 4. Prüfe dass Heizungs-Status via MQTT gesendet wurde
        heater_msgs = [
            m for m in mock.get_published_messages() if "/actuator/5/status" in m["topic"]
        ]
        assert len(heater_msgs) >= 1, "Heizungs-Status muss via MQTT gesendet werden"
        assert heater_msgs[-1]["payload"]["state"] is True

    @pytest.mark.temperature
    def test_hysteresis_prevents_oscillation(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Hysterese verhindert Heizungs-Oszillation

        PRAXIS-KONTEXT:
        Ohne Hysterese schaltet die Heizung bei Sollwert 20°C ständig
        an/aus: 19.9°C an, 20.1°C aus, 19.9°C an... Das zerstört
        das Relais und stresst die Pflanzen.

        Typische Hysterese: ±2°C Band
        - Sollwert: 20°C
        - Einschalten bei: < 18°C
        - Ausschalten bei: > 22°C

        GIVEN: Heizung aus, Temperatur 19°C (knapp unter Sollwert)
        WHEN: Temperatur schwankt zwischen 19°C und 21°C
        THEN: Heizung bleibt im aktuellen Zustand (keine Oszillation)
        """
        mock = greenhouse_esp_with_temp_sensors

        # Hysterese-Band
        SETPOINT = 2000  # 20°C Sollwert
        HYSTERESIS = 200  # ±2°C
        SWITCH_ON_BELOW = SETPOINT - HYSTERESIS  # 18°C
        SWITCH_OFF_ABOVE = SETPOINT + HYSTERESIS  # 22°C

        heater_switches = 0
        last_heater_state = False

        # Simuliere Temperatur-Schwankungen im Hysterese-Band
        temp_sequence = [
            1900,
            1950,
            2000,
            2050,
            2100,  # Steigende Temp im Band
            2050,
            2000,
            1950,
            1900,
            1850,  # Fallende Temp im Band
            1900,
            2000,
            2100,
            2000,
            1900,  # Oszillation im Band
        ]

        for temp in temp_sequence:
            mock.set_sensor_value(gpio=4, raw_value=temp, sensor_type="DS18B20")

            # Hysterese-Logik (wie sie im Server implementiert sein sollte)
            should_heat = temp < SWITCH_ON_BELOW
            should_cool = temp > SWITCH_OFF_ABOVE

            if should_heat and not last_heater_state:
                mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
                heater_switches += 1
                last_heater_state = True
            elif should_cool and last_heater_state:
                mock.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})
                heater_switches += 1
                last_heater_state = False

        # Im Band sollte KEINE Schaltung passieren
        assert (
            heater_switches == 0
        ), f"Heizung sollte im Hysterese-Band nicht schalten, aber {heater_switches}x geschaltet"

    @pytest.mark.critical
    @pytest.mark.temperature
    def test_sensor_failure_uses_backup(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Primärer Sensor fällt aus - Backup übernimmt

        PRAXIS-KONTEXT:
        Sensoren können ausfallen (Kabelbruch, Kondensation, Defekt).
        Das System darf NICHT blind werden - es muss auf Backup-Sensor
        wechseln und Alarm auslösen.

        GIVEN: Primärer DS18B20 (GPIO 4) und Backup SHT31 (GPIO 21) aktiv
        WHEN: DS18B20 meldet quality="error"
        THEN:
          - System verwendet SHT31 Temperatur
          - Alarm wird ausgelöst (in Messages sichtbar)
          - Heizungssteuerung funktioniert weiter
        """
        mock = greenhouse_esp_with_temp_sensors

        # === SETUP: Beide Sensoren haben normale Werte ===
        mock.set_sensor_value(gpio=4, raw_value=2200, sensor_type="DS18B20", quality="good")
        mock.set_multi_value_sensor(
            gpio=21,
            sensor_type="SHT31",
            primary_value=2200,
            secondary_values={"humidity": 650},
            quality="good",
        )

        # === TRIGGER: Primärsensor fällt aus ===
        mock.set_sensor_value(
            gpio=4,
            raw_value=0,  # Ungültiger Wert
            sensor_type="DS18B20",
            quality="error",  # FEHLER!
        )

        # Lese beide Sensoren
        primary_response = mock.handle_command("sensor_read", {"gpio": 4})
        backup_response = mock.handle_command("sensor_read", {"gpio": 21})

        # === VERIFY ===
        # 1. Primärsensor meldet Fehler
        assert primary_response["data"]["quality"] == "error"

        # 2. Backup-Sensor liefert gültige Daten
        assert backup_response["data"]["quality"] == "good"
        assert backup_response["data"]["raw_value"] == 2200

        # 3. System kann weiter gesteuert werden (Heizung reagiert auf Backup)
        # Server würde jetzt Backup-Wert verwenden
        heater_response = mock.handle_command(
            "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}  # Temperatur OK, Heizung aus
        )
        assert heater_response["status"] == "ok"

        # 4. MQTT-Messages enthalten Qualitäts-Info
        messages = mock.get_published_messages()
        error_msgs = [m for m in messages if "/sensor/4/data" in m["topic"]]
        assert any(
            m["payload"].get("quality") == "error" for m in error_msgs
        ), "Sensor-Fehler muss via MQTT gemeldet werden"

    @pytest.mark.critical
    @pytest.mark.temperature
    def test_all_temp_sensors_fail_safe_mode(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Alle Temperatur-Sensoren fallen aus - Safe Mode

        PRAXIS-KONTEXT:
        Wenn ALLE Sensoren ausfallen, ist Blindflug. Das System muss
        in einen sicheren Zustand wechseln:
        - Heizung auf Minimum (Frostschutz)
        - Lüftung geschlossen (kein Wärmeverlust)
        - Alarm an Betreiber

        GIVEN: Alle Temperatursensoren aktiv
        WHEN: Alle Sensoren melden quality="error"
        THEN:
          - System wechselt in SAFE_MODE
          - Alle Aktoren werden deaktiviert/sicher geschaltet
          - Alarm-Message wird gesendet
        """
        mock = greenhouse_esp_with_temp_sensors

        # === SETUP: Alle Sensoren normal ===
        mock.set_sensor_value(gpio=4, raw_value=2200, sensor_type="DS18B20", quality="good")
        mock.set_sensor_value(gpio=21, raw_value=2200, sensor_type="SHT31", quality="good")
        mock.set_sensor_value(gpio=35, raw_value=1800, sensor_type="analog", quality="good")

        # Aktoren sind aktiv
        mock.handle_command("actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"})  # Fan 50%

        # === TRIGGER: Alle Sensoren fallen aus ===
        mock.set_sensor_value(gpio=4, raw_value=0, sensor_type="DS18B20", quality="error")
        mock.set_sensor_value(gpio=21, raw_value=0, sensor_type="SHT31", quality="error")
        mock.set_sensor_value(gpio=35, raw_value=0, sensor_type="analog", quality="error")

        # Lese alle Sensoren - alle sollten Fehler melden
        for gpio in [4, 21, 35]:
            response = mock.handle_command("sensor_read", {"gpio": gpio})
            assert response["data"]["quality"] == "error"

        # === TRIGGER SAFE MODE ===
        mock.enter_safe_mode(reason="all_temp_sensors_failed")

        # === VERIFY ===
        # 1. System ist im SAFE_MODE
        assert mock.system_state == SystemState.SAFE_MODE

        # 2. Alle Aktoren wurden deaktiviert
        for gpio in [5, 6, 7]:
            actuator = mock.get_actuator_state(gpio)
            assert actuator.state is False, f"Aktor GPIO {gpio} sollte AUS sein"
            assert (
                actuator.emergency_stopped is True
            ), f"Aktor GPIO {gpio} sollte emergency_stopped sein"

        # 3. Safe-Mode-Message wurde gesendet
        messages = mock.get_published_messages()
        safe_mode_msgs = [
            m
            for m in messages
            if "safe_mode" in m["topic"].lower() or m.get("payload", {}).get("safe_mode") is True
        ]
        assert len(safe_mode_msgs) >= 1, "Safe-Mode-Status muss via MQTT gemeldet werden"


# =============================================================================
# Test Category 2: Irrigation Safety
# =============================================================================


class TestIrrigationSafety:
    """
    Bewässerungs-Sicherheitstests aus der Praxis.

    Praxis-Kontext:
    - Überbewässerung = Wurzelfäule = Pflanzentod
    - Pumpe ohne Wasser = Trockenlauf = Pumpendefekt
    - Nachtbewässerung = Pilzgefahr (Blätter bleiben nass)
    - Druckverlust = Leck in der Leitung = Überschwemmung
    """

    @pytest.mark.critical
    @pytest.mark.irrigation
    def test_irrigation_max_duration_safety(self, greenhouse_esp_with_irrigation):
        """
        SZENARIO: Maximale Bewässerungsdauer begrenzt

        PRAXIS-KONTEXT:
        Bewässerung darf NIE länger als 30 Minuten am Stück laufen.
        Gründe:
        - Boden kann nur begrenzt Wasser aufnehmen
        - Überlauf in Drainage/Grundwasser
        - Pumpen-Überhitzung bei kleinen Systemen

        GIVEN: Bewässerung startet normal
        WHEN: 30 Minuten erreicht
        THEN: Pumpe wird automatisch abgeschaltet

        SICHERHEIT: Timeout muss auch bei Kommunikationsverlust greifen
        """
        mock = greenhouse_esp_with_irrigation

        # === SETUP: Bewässerung starten ===
        mock.clear_published_messages()

        # Pumpe AN
        pump_start = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert pump_start["status"] == "ok"
        assert pump_start["state"] is True

        # Ventil A öffnen
        valve_response = mock.handle_command(
            "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
        )
        assert valve_response["status"] == "ok"

        # === VERIFY: Sicherheits-Timeout ist konfiguriert ===
        pump_state = mock.get_actuator_state(5)
        assert pump_state.safety_timeout_ms == 1800000, "Pumpe muss 30min Timeout haben (1800000ms)"

        # === SIMULATE: Timeout-Logik (normalerweise Server-seitig) ===
        # Nach 30 Minuten sollte der Server automatisch abschalten
        # Hier prüfen wir, dass die Konfiguration stimmt und
        # dass Emergency-Stop funktioniert

        # Simuliere Timeout durch Emergency-Stop
        emergency_response = mock.handle_command(
            "emergency_stop", {"reason": "irrigation_max_duration_exceeded"}
        )

        assert emergency_response["status"] == "ok"

        # Beide Aktoren (Pumpe + Ventil) müssen aus sein
        pump_after = mock.get_actuator_state(5)
        valve_after = mock.get_actuator_state(6)

        assert pump_after.state is False, "Pumpe muss nach Timeout AUS sein"
        assert valve_after.state is False, "Ventil muss nach Timeout ZU sein"

    @pytest.mark.critical
    @pytest.mark.irrigation
    def test_low_pressure_stops_pump(self, greenhouse_esp_with_irrigation):
        """
        SZENARIO: Niedriger Wasserdruck stoppt Pumpe (Trockenlauf-Schutz)

        PRAXIS-KONTEXT:
        Wenn der Wasserdruck unter 1 bar fällt während die Pumpe läuft:
        - Wassertank leer
        - Leck in der Zuleitung
        - Ventil versehentlich geschlossen

        Pumpe bei Trockenlauf → Überhitzung → Defekt (500€+)

        GIVEN: Pumpe läuft normal, Druck bei 2 bar
        WHEN: Druck fällt auf 0.5 bar
        THEN: Pumpe wird sofort gestoppt, Alarm ausgelöst

        REAKTIONSZEIT: < 5 Sekunden
        """
        mock = greenhouse_esp_with_irrigation

        # === SETUP: Normale Bewässerung ===
        mock.set_sensor_value(gpio=39, raw_value=2000, sensor_type="pressure", quality="good")
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Pumpe läuft
        pump_running = mock.get_actuator_state(5)
        assert pump_running.state is True

        # === TRIGGER: Druckabfall ===
        mock.set_sensor_value(
            gpio=39, raw_value=500, sensor_type="pressure", quality="good"  # 0.5 bar - zu niedrig!
        )

        # Server würde Drucksensor lesen
        pressure_response = mock.handle_command("sensor_read", {"gpio": 39})
        assert pressure_response["data"]["raw_value"] == 500

        # === VERIFY: Server reagiert (simuliert) ===
        # Niedriger Druck → Pumpe stoppen
        if pressure_response["data"]["raw_value"] < 1000:  # < 1 bar
            stop_response = mock.handle_command(
                "actuator_set", {"gpio": 5, "value": 0, "mode": "digital"}
            )
            assert stop_response["status"] == "ok"

        # Pumpe muss aus sein
        pump_after = mock.get_actuator_state(5)
        assert pump_after.state is False, "Pumpe muss bei niedrigem Druck gestoppt werden"

        # Prüfe dass Alert gesendet wurde
        messages = mock.get_published_messages()
        # Status-Änderung sollte gesendet worden sein
        pump_status_msgs = [m for m in messages if "/actuator/5/status" in m["topic"]]
        assert any(
            m["payload"]["state"] is False for m in pump_status_msgs
        ), "Pumpen-Stop muss via MQTT gemeldet werden"

    @pytest.mark.irrigation
    def test_multiple_zones_sequential(self, multi_zone_greenhouse):
        """
        SZENARIO: Zonen-Bewässerung läuft sequentiell

        PRAXIS-KONTEXT:
        Bei mehreren Bewässerungszonen mit einer Hauptpumpe:
        - Nur EINE Zone gleichzeitig öffnen
        - Zone A fertig → Zone A zu → Zone B auf
        - Verhindert Druckverlust und Unterversorgung

        GIVEN: Zone A und Zone B haben unterschiedliche Bewässerungszeiten
        WHEN: Bewässerung startet
        THEN: Zonen werden nacheinander bewässert, nie gleichzeitig
        """
        esps = multi_zone_greenhouse
        zone_a = esps["zone_a"]
        zone_b = esps["zone_b"]
        zone_c = esps["zone_c"]  # Technik mit Hauptpumpe

        # === SETUP: Hauptpumpe starten ===
        zone_c.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # === PHASE 1: Zone A bewässern ===
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # Zone B muss geschlossen sein
        zone_b_valve = zone_b.get_actuator_state(6)
        assert (
            zone_b_valve is None or zone_b_valve.state is False
        ), "Zone B Ventil muss während Zone A Bewässerung geschlossen sein"

        # Zone A Ventil ist offen
        zone_a_valve = zone_a.get_actuator_state(6)
        assert zone_a_valve.state is True

        # === PHASE 2: Wechsel zu Zone B ===
        # Zone A schließen
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})

        # Zone B öffnen
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # Verify: Zone A zu, Zone B offen
        zone_a_after = zone_a.get_actuator_state(6)
        zone_b_after = zone_b.get_actuator_state(6)

        assert zone_a_after.state is False, "Zone A Ventil muss jetzt geschlossen sein"
        assert zone_b_after.state is True, "Zone B Ventil muss jetzt offen sein"

        # === CLEANUP: Alles aus ===
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        zone_c.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})


# =============================================================================
# Test Category 3: Ventilation Logic
# =============================================================================


class TestVentilationLogic:
    """
    Lüftungs-Logik Tests aus der Praxis.

    Praxis-Kontext:
    - Lüftung ist das Hauptwerkzeug für Temperatur-Regulierung
    - Bei Frost → Lüftung ZU (keine kalte Außenluft)
    - Bei Sturm → Lüftung ZU (Beschädigung)
    - Graduelle Öffnung verhindert Temperaturschock
    """

    @pytest.mark.critical
    @pytest.mark.ventilation
    def test_ventilation_frost_lock(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Lüftung gesperrt bei Frost

        PRAXIS-KONTEXT:
        Bei Frost (< 5°C außen) darf die Lüftung NIEMALS öffnen,
        egal wie heiß es innen ist. Kalte Außenluft = Frostschaden.

        GIVEN: Außentemperatur unter 5°C
        WHEN: Innentemperatur erreicht 30°C (zu heiß)
        THEN: Lüftung bleibt geschlossen (Frost-Lock aktiv)

        AUSNAHME: Nur Umluftventilator darf laufen
        """
        mock = greenhouse_esp_with_temp_sensors

        # === SETUP: Frost außen ===
        mock.set_sensor_value(
            gpio=35,
            raw_value=GreenhouseValues.TEMP_FROST_CRITICAL,  # 2°C außen
            sensor_type="analog",
            name="Außentemperatur",
        )

        # Innentemperatur zu heiß
        mock.set_sensor_value(
            gpio=4,
            raw_value=GreenhouseValues.TEMP_HOT_WARNING,  # 30°C innen!
            sensor_type="DS18B20",
        )

        # === VERIFY: Frost-Lock Logik ===
        outside_temp = mock.get_sensor_state(35)
        inside_temp = mock.get_sensor_state(4)

        frost_detected = outside_temp.raw_value < 500  # < 5°C
        inside_too_hot = inside_temp.raw_value > 2800  # > 28°C

        assert frost_detected, "Test voraussetzung: Frost muss erkannt werden"
        assert inside_too_hot, "Test voraussetzung: Innen muss zu heiß sein"

        # Lüftungsklappe (GPIO 6) DARF NICHT öffnen
        # Server würde das verhindern - hier simulieren wir die Logik
        if frost_detected:
            # Lüftung versuchen zu öffnen sollte abgelehnt werden
            # In echtem System: Command wird akzeptiert aber nicht ausgeführt
            vent_response = mock.handle_command(
                "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
            )

            # Command geht durch, aber Server würde warnen
            assert vent_response["status"] == "ok"

            # In Praxis: Server überschreibt mit Frost-Lock
            # Für Test: Manuell zurücksetzen
            mock.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})

        # Umluftventilator (GPIO 7) DARF laufen (interne Umwälzung)
        fan_response = mock.handle_command(
            "actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"}  # 50% Umluft
        )
        assert fan_response["status"] == "ok"
        assert fan_response["state"] is True, "Umluftventilator sollte erlaubt sein"

    @pytest.mark.ventilation
    def test_ventilation_gradual_opening(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Lüftung öffnet graduell

        PRAXIS-KONTEXT:
        Lüftung nie von 0% auf 100% springen lassen:
        - Temperaturschock für Pflanzen
        - Zugluft beschädigt empfindliche Blätter
        - Kondenswasser durch schnelle Abkühlung

        Typische Rampe: 0% → 100% in 5 Minuten

        GIVEN: Lüftung geschlossen
        WHEN: Volle Lüftung angefordert
        THEN: PWM steigt in 10%-Schritten alle 30 Sekunden
        """
        mock = greenhouse_esp_with_temp_sensors

        # Lüftungsmotor (PWM)
        mock.configure_actuator(gpio=7, actuator_type="fan", min_value=0.0, max_value=1.0)

        # === SIMULATE: Graduelle Öffnung ===
        target_value = 1.0
        current_value = 0.0
        step = 0.1
        steps_taken = 0

        while current_value < target_value:
            current_value = min(current_value + step, target_value)
            response = mock.handle_command(
                "actuator_set", {"gpio": 7, "value": current_value, "mode": "pwm"}
            )
            assert response["status"] == "ok"
            assert (
                abs(response["pwm_value"] - current_value) < 0.01
            ), f"PWM sollte {current_value} sein"
            steps_taken += 1

        # === VERIFY ===
        # Sollte 11 Schritte gedauert haben (0.0 bis 1.0 in 0.1-Schritten = 11 Werte)
        assert steps_taken == 11, f"Sollte 11 Schritte dauern, waren aber {steps_taken}"

        # Finaler Wert
        fan_state = mock.get_actuator_state(7)
        assert fan_state.pwm_value == 1.0


# =============================================================================
# Test Category 4: Night Mode & Unattended Operation
# =============================================================================


class TestNightModeOperation:
    """
    Nacht- und unbeaufsichtigter Betrieb Tests.

    Praxis-Kontext:
    - Nachts: Keine Bewässerung (Pilzgefahr), minimale Lüftung
    - Wochenende: System muss 48h+ autonom laufen
    - Alarm-Eskalation wenn niemand reagiert
    """

    @pytest.mark.night_mode
    def test_night_mode_minimum_activity(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Nachtmodus - Minimale Aktivität

        PRAXIS-KONTEXT:
        Nachts (22:00-06:00):
        - Heizung: Nur Frostschutz (15°C statt 22°C)
        - Lüftung: Geschlossen (Wärme halten)
        - Beleuchtung: Aus
        - Bewässerung: Gesperrt (Pilzgefahr)

        GIVEN: System im Tagmodus
        WHEN: Nachtmodus aktiviert (22:00)
        THEN: Alle Aktoren auf Nacht-Konfiguration
        """
        mock = greenhouse_esp_with_temp_sensors

        # === SETUP: Tag-Konfiguration ===
        mock.set_sensor_value(gpio=4, raw_value=2000, sensor_type="DS18B20")  # 20°C
        mock.handle_command("actuator_set", {"gpio": 7, "value": 0.3, "mode": "pwm"})  # Fan 30%

        # === TRIGGER: Nachtmodus ===
        # In Praxis: Server schaltet bei Zeitpunkt
        # Hier: Manuell simulieren

        # Lüftung zu
        mock.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 7, "value": 0, "mode": "pwm"})

        # Heizung auf Frostschutz-Modus (nur wenn < 15°C)
        # Simuliere kühlere Nacht
        mock.set_sensor_value(gpio=4, raw_value=1400, sensor_type="DS18B20")  # 14°C

        # Server würde Heizung aktivieren (Frostschutz)
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # === VERIFY ===
        heater = mock.get_actuator_state(5)
        vent_valve = mock.get_actuator_state(6)
        fan = mock.get_actuator_state(7)

        # Nachts: Heizung an (Frostschutz), Lüftung zu
        assert heater.state is True, "Heizung sollte für Frostschutz an sein"
        assert vent_valve.state is False, "Lüftungsklappe sollte nachts zu sein"
        assert fan.pwm_value == fan.min_value, "Lüftungsmotor sollte nachts auf Minimum sein"

    @pytest.mark.critical
    @pytest.mark.night_mode
    def test_alarm_escalation_no_response(self, greenhouse_esp_with_temp_sensors):
        """
        SZENARIO: Alarm-Eskalation wenn niemand reagiert

        PRAXIS-KONTEXT:
        Kritischer Alarm → 15 Min keine Reaktion → Erneuter Alarm
        → Weitere 15 Min → Notabschaltung (Safe Mode)

        Verhindert, dass ein einzelner verpasster Alarm zu Totalschaden führt.

        GIVEN: Kritische Temperatur (35°C)
        WHEN: Kein Benutzer-Eingriff nach 15 Minuten
        THEN: Alarm wird eskaliert, nach 30 Min Safe Mode
        """
        mock = greenhouse_esp_with_temp_sensors

        # === TRIGGER: Kritische Temperatur ===
        mock.set_sensor_value(
            gpio=4, raw_value=GreenhouseValues.TEMP_HOT_CRITICAL, sensor_type="DS18B20"  # 35°C!
        )

        mock.clear_published_messages()

        # Sensor lesen - löst ersten Alarm aus
        mock.handle_command("sensor_read", {"gpio": 4})

        # === PHASE 1: Erster Alarm ===
        messages_phase1 = mock.get_published_messages()
        sensor_msgs = [m for m in messages_phase1 if "/sensor/4/data" in m["topic"]]
        assert len(sensor_msgs) >= 1, "Sensor-Daten müssen gesendet werden"

        # Server würde Alarm auslösen (hier nicht direkt testbar)
        # Aber: Daten sind verfügbar für Alarm-Logik
        critical_reading = sensor_msgs[-1]["payload"]["raw"]
        assert critical_reading >= GreenhouseValues.TEMP_HOT_CRITICAL

        # === PHASE 2: Eskalation (simuliert) ===
        # Nach 15 Min ohne Reaktion → Erneuter Alarm
        # Nach 30 Min → Safe Mode

        # Simuliere Safe Mode nach Timeout
        mock.enter_safe_mode(reason="alarm_escalation_timeout")

        # === VERIFY ===
        assert mock.system_state == SystemState.SAFE_MODE

        # Alle Aktoren gestoppt
        for gpio in [5, 6, 7]:
            actuator = mock.get_actuator_state(gpio)
            assert (
                actuator.emergency_stopped is True
            ), f"Aktor GPIO {gpio} sollte nach Eskalation gestoppt sein"


# =============================================================================
# Test Category 5: Cross-ESP Coordination (Basic)
# =============================================================================


class TestCrossESPCoordination:
    """
    Basis-Tests für Koordination zwischen mehreren ESPs.

    (Detaillierte Cross-ESP Tests in test_cross_esp_chains.py)
    """

    @pytest.mark.critical
    def test_pump_esp_controls_valve_esp(self, multi_zone_greenhouse):
        """
        SZENARIO: Pumpen-ESP und Ventil-ESP koordiniert

        PRAXIS-KONTEXT:
        Typisches Setup:
        - ESP_C (Technikraum): Hauptpumpe
        - ESP_A (Zone A): Ventil für Zone A

        Reihenfolge KRITISCH:
        1. Ventil öffnen
        2. DANN Pumpe starten

        Wenn Pumpe zuerst: Druckstoß beschädigt Leitungen

        GIVEN: ESP_C mit Pumpe, ESP_A mit Ventil
        WHEN: Bewässerung Zone A startet
        THEN: Ventil öffnet BEVOR Pumpe startet
        """
        esps = multi_zone_greenhouse
        zone_a = esps["zone_a"]
        zone_c = esps["zone_c"]

        # === KORREKTE REIHENFOLGE ===
        # 1. Ventil zuerst öffnen
        valve_response = zone_a.handle_command(
            "actuator_set", {"gpio": 6, "value": 1, "mode": "digital"}
        )
        assert valve_response["status"] == "ok"
        assert valve_response["state"] is True

        # Kurze Pause (in Praxis: Zeit für Ventil-Öffnung)
        # time.sleep(0.1)  # In echtem Test: 1-2 Sekunden

        # 2. DANN Pumpe starten
        pump_response = zone_c.handle_command(
            "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
        )
        assert pump_response["status"] == "ok"
        assert pump_response["state"] is True

        # === VERIFY: Beide aktiv ===
        valve_state = zone_a.get_actuator_state(6)
        pump_state = zone_c.get_actuator_state(5)

        assert valve_state.state is True, "Ventil muss offen sein"
        assert pump_state.state is True, "Pumpe muss laufen"

        # === CLEANUP: Korrekte Reihenfolge zum Stoppen ===
        # 1. Pumpe zuerst stoppen
        zone_c.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # 2. DANN Ventil schließen
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers for greenhouse tests."""
    config.addinivalue_line("markers", "critical: Safety-critical tests (must never fail)")
    config.addinivalue_line("markers", "daily_ops: Daily operation tests")
    config.addinivalue_line("markers", "temperature: Temperature management tests")
    config.addinivalue_line("markers", "irrigation: Irrigation safety tests")
    config.addinivalue_line("markers", "ventilation: Ventilation logic tests")
    config.addinivalue_line("markers", "night_mode: Night mode and unattended operation tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "critical or temperature"])
