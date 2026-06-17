"""
Cross-ESP Verkettungs-Tests - Praxisbasierte Multi-Device Szenarien.

Erstellt von: Domain-Expert Test-Engineer
Fokus: Koordination zwischen mehreren ESP32-Geräten im Gewächshaus

Diese Tests decken ab:
1. Pumpe-Ventil Koordination (kritische Reihenfolge)
2. Sensor-Zone triggert Aktor-Zone
3. Kaskadenfehler-Isolation (ESP fällt aus)
4. Synchronisierte Bewässerung über Zonen
5. Emergency-Broadcast über alle ESPs

Praxis-Kontext:
In einem typischen Gewächshaus sind Sensoren und Aktoren auf
verschiedene ESP32 verteilt:
- Technikraum: Pumpen, Hauptventile (robust, geschützt)
- Zonen: Sensoren, Zonenventile, lokale Lüftung
- Wettermast: Außensensoren (Wind, Regen, Temperatur)

Die Server-Logik muss diese ESPs koordinieren und dabei:
- Reihenfolgen einhalten (Ventil vor Pumpe)
- Ausfälle isolieren (Zone A tot → Zone B läuft weiter)
- Kaskaden vermeiden (ein Problem → nicht alles kaputt)
"""

import pytest
import time
from typing import Dict, Any, List
from datetime import datetime

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "esp32"))

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState

# =============================================================================
# Fixtures for Cross-ESP Testing
# =============================================================================


@pytest.fixture
def irrigation_system_3_esp():
    """
    3-ESP Bewässerungssystem mit klarer Rollenverteilung.

    ESP_PUMP (Technikraum):
        - GPIO 5: Hauptpumpe
        - GPIO 6: Hauptventil (nach Pumpe)
        - GPIO 39: Drucksensor

    ESP_ZONE_A (Zone A - Tomaten):
        - GPIO 6: Zonenventil A
        - GPIO 34: Bodenfeuchte A

    ESP_ZONE_B (Zone B - Salat):
        - GPIO 6: Zonenventil B
        - GPIO 34: Bodenfeuchte B
    """
    esps = {}

    # Technikraum ESP
    pump_esp = MockESP32Client(esp_id="ESP_PUMP_TECH", kaiser_id="god")
    pump_esp.configure_zone("technical", "greenhouse", "pump_room")
    pump_esp.configure_actuator(
        gpio=5, actuator_type="pump", name="Hauptpumpe", safety_timeout_ms=1800000
    )
    pump_esp.configure_actuator(gpio=6, actuator_type="valve", name="Hauptventil")
    pump_esp.set_sensor_value(gpio=39, raw_value=2100, sensor_type="pressure", name="Systemdruck")
    esps["pump"] = pump_esp

    # Zone A ESP
    zone_a = MockESP32Client(esp_id="ESP_ZONE_A", kaiser_id="god")
    zone_a.configure_zone("zone_a", "greenhouse", "tomatoes")
    zone_a.configure_actuator(gpio=6, actuator_type="valve", name="Ventil Zone A")
    zone_a.set_sensor_value(gpio=34, raw_value=1800, sensor_type="moisture", name="Feuchte A")
    esps["zone_a"] = zone_a

    # Zone B ESP
    zone_b = MockESP32Client(esp_id="ESP_ZONE_B", kaiser_id="god")
    zone_b.configure_zone("zone_b", "greenhouse", "lettuce")
    zone_b.configure_actuator(gpio=6, actuator_type="valve", name="Ventil Zone B")
    zone_b.set_sensor_value(gpio=34, raw_value=2200, sensor_type="moisture", name="Feuchte B")
    esps["zone_b"] = zone_b

    for esp in esps.values():
        esp.clear_published_messages()

    yield esps

    for esp in esps.values():
        esp.reset()


@pytest.fixture
def climate_control_4_esp():
    """
    4-ESP Klimakontroll-System.

    ESP_SENSORS (Sensor-Station):
        - GPIO 4: DS18B20 Innentemperatur
        - GPIO 21: SHT31 Luft Temp/Feuchte
        - GPIO 35: Außentemperatur

    ESP_VENTILATION (Lüftungs-Steuerung):
        - GPIO 5: Dachfenster Motor
        - GPIO 6: Seitenlüftung
        - GPIO 7: Umluftventilator (PWM)

    ESP_HEATING (Heizung):
        - GPIO 5: Heizungsventil
        - GPIO 6: Umwälzpumpe

    ESP_WEATHER (Außen-Station):
        - GPIO 34: Windgeschwindigkeit
        - GPIO 35: Regensensor
        - GPIO 36: Außentemperatur
    """
    esps = {}

    # Sensor Station
    sensors = MockESP32Client(esp_id="ESP_SENSORS", kaiser_id="god")
    sensors.configure_zone("sensor_station", "greenhouse", "center")
    sensors.set_sensor_value(gpio=4, raw_value=2200, sensor_type="DS18B20", name="Innen Temp")
    sensors.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=2200,
        secondary_values={"humidity": 650},
        name="Luft Klima",
    )
    esps["sensors"] = sensors

    # Lüftung
    ventilation = MockESP32Client(esp_id="ESP_VENTILATION", kaiser_id="god")
    ventilation.configure_zone("ventilation", "greenhouse", "roof")
    ventilation.configure_actuator(gpio=5, actuator_type="motor", name="Dachfenster")
    ventilation.configure_actuator(gpio=6, actuator_type="valve", name="Seitenlüftung")
    ventilation.configure_actuator(
        gpio=7, actuator_type="fan", name="Umluft", min_value=0.2, max_value=1.0
    )
    esps["ventilation"] = ventilation

    # Heizung
    heating = MockESP32Client(esp_id="ESP_HEATING", kaiser_id="god")
    heating.configure_zone("heating", "greenhouse", "boiler_room")
    heating.configure_actuator(gpio=5, actuator_type="valve", name="Heizventil")
    heating.configure_actuator(gpio=6, actuator_type="pump", name="Umwälzpumpe")
    esps["heating"] = heating

    # Wetter-Station
    weather = MockESP32Client(esp_id="ESP_WEATHER", kaiser_id="god")
    weather.configure_zone("weather", "greenhouse", "outside")
    weather.set_sensor_value(gpio=34, raw_value=100, sensor_type="wind", name="Wind")  # 10 km/h
    weather.set_sensor_value(gpio=35, raw_value=0, sensor_type="rain", name="Regen")  # Kein Regen
    weather.set_sensor_value(
        gpio=36, raw_value=1500, sensor_type="temperature", name="Außen"
    )  # 15°C
    esps["weather"] = weather

    for esp in esps.values():
        esp.clear_published_messages()

    yield esps

    for esp in esps.values():
        esp.reset()


# =============================================================================
# Test: Pump-Valve Coordination
# =============================================================================


class TestPumpValveCoordination:
    """
    Tests für die kritische Pumpe-Ventil Koordination.

    KRITISCH: Falsche Reihenfolge = Druckstoß = Leitungsschaden!
    """

    @pytest.mark.critical
    def test_correct_startup_sequence(self, irrigation_system_3_esp):
        """
        SZENARIO: Korrekte Startreihenfolge Bewässerung

        PRAXIS-KONTEXT:
        Richtige Reihenfolge zum Starten:
        1. Zonenventil öffnen (2s warten)
        2. Hauptventil öffnen (1s warten)
        3. Pumpe starten

        Wenn Pumpe zuerst startet → geschlossene Ventile →
        Druckstoß → Wasserschlag → Leitungsschaden!

        GIVEN: System im Ruhezustand
        WHEN: Bewässerung Zone A startet
        THEN: Ventile öffnen BEVOR Pumpe startet
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]

        # === VERIFY: Alles aus am Start ===
        assert pump.get_actuator_state(5).state is False, "Pumpe sollte aus sein"
        assert pump.get_actuator_state(6).state is False, "Hauptventil sollte zu sein"
        assert zone_a.get_actuator_state(6).state is False, "Zonenventil A sollte zu sein"

        # === KORREKTE STARTREIHENFOLGE ===
        actions_log = []

        # 1. Zonenventil öffnen
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        actions_log.append(("zone_valve_open", time.time()))

        # 2. Hauptventil öffnen
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        actions_log.append(("main_valve_open", time.time()))

        # 3. Pumpe starten
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        actions_log.append(("pump_start", time.time()))

        # === VERIFY: Alle aktiv ===
        assert zone_a.get_actuator_state(6).state is True
        assert pump.get_actuator_state(6).state is True
        assert pump.get_actuator_state(5).state is True

        # === VERIFY: Reihenfolge war korrekt ===
        assert actions_log[0][0] == "zone_valve_open"
        assert actions_log[1][0] == "main_valve_open"
        assert actions_log[2][0] == "pump_start"

    @pytest.mark.critical
    def test_correct_shutdown_sequence(self, irrigation_system_3_esp):
        """
        SZENARIO: Korrekte Stoppreihenfolge Bewässerung

        PRAXIS-KONTEXT:
        Richtige Reihenfolge zum Stoppen:
        1. Pumpe stoppen (sofort - wichtigste!)
        2. Warten bis Druck abgebaut (2-3s)
        3. Hauptventil schließen
        4. Zonenventil schließen

        Wenn Ventile zuerst schließen bei laufender Pumpe →
        Druckstoß gegen geschlossenes Ventil!
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]

        # === SETUP: System läuft ===
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Verify läuft
        assert pump.get_actuator_state(5).state is True

        # === KORREKTE STOPPREIHENFOLGE ===
        actions_log = []

        # 1. PUMPE ZUERST STOPPEN!
        pump.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})
        actions_log.append(("pump_stop", time.time()))

        # 2. Hauptventil schließen
        pump.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        actions_log.append(("main_valve_close", time.time()))

        # 3. Zonenventil schließen
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        actions_log.append(("zone_valve_close", time.time()))

        # === VERIFY ===
        assert pump.get_actuator_state(5).state is False
        assert pump.get_actuator_state(6).state is False
        assert zone_a.get_actuator_state(6).state is False

        # Reihenfolge korrekt
        assert actions_log[0][0] == "pump_stop"

    @pytest.mark.critical
    def test_pressure_drop_stops_pump_not_valves(self, irrigation_system_3_esp):
        """
        SZENARIO: Druckabfall → Nur Pumpe stoppen, Ventile offen lassen

        PRAXIS-KONTEXT:
        Bei plötzlichem Druckabfall (Leck, Tank leer):
        - Pumpe SOFORT stoppen (Trockenlauf)
        - Ventile OFFEN lassen (Restdruck entweicht)

        Wenn Ventile bei Druckabfall schließen → Pumpe gegen
        geschlossenes System = doppelter Schaden!
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]

        # === SETUP: System läuft normal ===
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Normaler Druck
        pump.set_sensor_value(gpio=39, raw_value=2000, sensor_type="pressure")

        # === TRIGGER: Druckabfall ===
        pump.set_sensor_value(gpio=39, raw_value=500, sensor_type="pressure")  # Kritisch niedrig!

        # Server-Logik: Druck lesen und reagieren
        pressure = pump.handle_command("sensor_read", {"gpio": 39})
        assert pressure["data"]["raw_value"] == 500

        # === KORREKTE REAKTION: Nur Pumpe stoppen! ===
        pump.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # === VERIFY ===
        # Pumpe aus
        assert pump.get_actuator_state(5).state is False, "Pumpe muss gestoppt sein"

        # ABER: Ventile bleiben offen!
        assert pump.get_actuator_state(6).state is True, "Hauptventil sollte offen bleiben"
        assert zone_a.get_actuator_state(6).state is True, "Zonenventil sollte offen bleiben"


# =============================================================================
# Test: Cross-Zone Sensor-Actuator Triggers
# =============================================================================


class TestCrossZoneTriggers:
    """
    Tests für Sensor in Zone X triggert Aktor in Zone Y.

    Praxis-Beispiele:
    - Innentemperatur zu hoch → Dachfenster öffnen
    - Außen-Regen erkannt → Dachfenster schließen
    - Feuchtesensor Zone A → Bewässerung in Zone A+B (verbunden)
    """

    @pytest.mark.critical
    def test_temperature_triggers_ventilation(self, climate_control_4_esp):
        """
        SZENARIO: Hohe Innentemperatur → Lüftung aktivieren

        PRAXIS-KONTEXT:
        Sensor-Station misst 30°C → Server entscheidet →
        Lüftungs-ESP öffnet Dachfenster

        Dies ist Cross-ESP: Sensor auf ESP_SENSORS,
        Aktor auf ESP_VENTILATION

        GIVEN: Normaltemperatur (22°C)
        WHEN: Temperatur steigt auf 30°C
        THEN: Dachfenster öffnet (auf separatem ESP!)
        """
        esps = climate_control_4_esp
        sensors = esps["sensors"]
        ventilation = esps["ventilation"]

        # === SETUP: Normal-Temperatur ===
        sensors.set_sensor_value(gpio=4, raw_value=2200, sensor_type="DS18B20")  # 22°C

        # Lüftung geschlossen
        assert ventilation.get_actuator_state(5).state is False

        # === TRIGGER: Temperatur steigt ===
        sensors.set_sensor_value(gpio=4, raw_value=3000, sensor_type="DS18B20")  # 30°C!

        # Server liest Sensor (ESP_SENSORS)
        temp_reading = sensors.handle_command("sensor_read", {"gpio": 4})
        assert temp_reading["data"]["raw_value"] == 3000

        # === SERVER-LOGIK (simuliert) ===
        # Temperatur > 28°C → Lüftung öffnen
        if temp_reading["data"]["raw_value"] > 2800:
            # Command geht an ANDEREN ESP!
            vent_response = ventilation.handle_command(
                "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
            )
            assert vent_response["status"] == "ok"

        # === VERIFY: Lüftung ist offen ===
        assert (
            ventilation.get_actuator_state(5).state is True
        ), "Dachfenster sollte bei 30°C offen sein"

    @pytest.mark.critical
    def test_rain_overrides_ventilation(self, climate_control_4_esp):
        """
        SZENARIO: Regen erkannt → Lüftung schließen (Override)

        PRAXIS-KONTEXT:
        Auch wenn innen zu warm ist - bei Regen MUSS
        die Dachfenster-Lüftung geschlossen werden!

        Regen reinlassen = Pflanzenschaden + Technikschaden

        GIVEN: Lüftung offen wegen hoher Temperatur
        WHEN: Regensensor meldet Regen
        THEN: Dachfenster schließt SOFORT (trotz Wärme)
        """
        esps = climate_control_4_esp
        weather = esps["weather"]
        ventilation = esps["ventilation"]

        # === SETUP: Lüftung offen wegen Wärme ===
        ventilation.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert ventilation.get_actuator_state(5).state is True

        # === TRIGGER: Regen! ===
        weather.set_sensor_value(gpio=35, raw_value=1, sensor_type="rain")  # Regen erkannt!

        # Server liest Wetter-ESP
        rain_reading = weather.handle_command("sensor_read", {"gpio": 35})
        assert rain_reading["data"]["raw_value"] == 1  # Regen aktiv

        # === SERVER-LOGIK: Regen-Override ===
        if rain_reading["data"]["raw_value"] > 0:
            # OVERRIDE: Dachfenster schließen, egal wie warm!
            ventilation.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # === VERIFY ===
        assert (
            ventilation.get_actuator_state(5).state is False
        ), "Dachfenster MUSS bei Regen geschlossen sein"

    def test_wind_limits_ventilation_opening(self, climate_control_4_esp):
        """
        SZENARIO: Wind begrenzt Lüftungsöffnung

        PRAXIS-KONTEXT:
        Bei starkem Wind nicht voll öffnen:
        - Bis 20 km/h: Volle Öffnung erlaubt
        - 20-40 km/h: Max 50%
        - 40-60 km/h: Max 25%
        - >60 km/h: Geschlossen halten (Sturmschutz)

        GIVEN: Lüftung soll öffnen
        WHEN: Wind bei 35 km/h
        THEN: Lüftung öffnet nur 50%
        """
        esps = climate_control_4_esp
        weather = esps["weather"]
        ventilation = esps["ventilation"]

        # Wind: 35 km/h (350 raw)
        weather.set_sensor_value(gpio=34, raw_value=350, sensor_type="wind")

        wind_reading = weather.handle_command("sensor_read", {"gpio": 34})
        wind_speed = wind_reading["data"]["raw_value"]

        # === WIND-LIMIT-LOGIK ===
        if wind_speed > 600:  # > 60 km/h
            max_opening = 0.0
        elif wind_speed > 400:  # > 40 km/h
            max_opening = 0.25
        elif wind_speed > 200:  # > 20 km/h
            max_opening = 0.5
        else:
            max_opening = 1.0

        # Bei 35 km/h → max 50%
        assert max_opening == 0.5

        # Öffne Umluftventilator (PWM) mit Limit
        ventilation.handle_command(
            "actuator_set",
            {
                "gpio": 7,
                "value": min(1.0, max_opening),  # Angefordert: 100%, erlaubt: 50%
                "mode": "pwm",
            },
        )

        # === VERIFY ===
        fan_state = ventilation.get_actuator_state(7)
        assert (
            fan_state.pwm_value <= 0.5
        ), f"Lüftung sollte bei 35 km/h max 50% sein, ist aber {fan_state.pwm_value}"


# =============================================================================
# Test: Cascade Failure Isolation
# =============================================================================


class TestCascadeFailureIsolation:
    """
    Tests für Fehler-Isolation: Ein ESP fällt aus → Rest läuft weiter.

    Praxis-Kontext:
    Wenn ESP_ZONE_A ausfällt (Stromausfall, WiFi-Problem):
    - Zone A ist offline → OK, kann man akzeptieren
    - Zone B muss weiterlaufen!
    - Pumpe muss weiter steuerbar sein
    """

    @pytest.mark.critical
    def test_zone_a_fails_zone_b_continues(self, irrigation_system_3_esp):
        """
        SZENARIO: Zone A ESP fällt aus → Zone B arbeitet weiter

        PRAXIS-KONTEXT:
        Zone A hat Stromausfall oder Netzwerkproblem.
        Zone B und die Pumpe müssen unabhängig weiterlaufen.

        GIVEN: Alle ESPs online, Bewässerung Zone B aktiv
        WHEN: ESP_ZONE_A geht offline
        THEN: Zone B Bewässerung läuft ungestört weiter
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]
        zone_b = esps["zone_b"]

        # === SETUP: Zone B wird bewässert ===
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # Verify: Zone B läuft
        assert zone_b.get_actuator_state(6).state is True
        assert pump.get_actuator_state(5).state is True

        # === TRIGGER: Zone A geht offline ===
        zone_a.disconnect()
        assert zone_a.connected is False

        # Zone A ist nicht mehr erreichbar
        # (In echter Situation: Heartbeat-Timeout auf Server)

        # === VERIFY: Zone B unbeeinträchtigt ===
        # Zone B Ventil noch offen
        assert (
            zone_b.get_actuator_state(6).state is True
        ), "Zone B Ventil sollte trotz Zone A Ausfall offen bleiben"

        # Pumpe noch aktiv
        assert (
            pump.get_actuator_state(5).state is True
        ), "Pumpe sollte trotz Zone A Ausfall weiterlaufen"

        # === Zone B kann weiter gesteuert werden ===
        # Stoppe Zone B normal
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        assert zone_b.get_actuator_state(6).state is False

    @pytest.mark.critical
    def test_pump_esp_fails_emergency_stop_all(self, irrigation_system_3_esp):
        """
        SZENARIO: Pumpen-ESP fällt aus → Zonenventile schließen

        PRAXIS-KONTEXT:
        Wenn der Pumpen-ESP ausfällt, ist die Situation gefährlich:
        - Pumpe Zustand unbekannt (könnte noch laufen!)
        - Keine Drucküberwachung
        → Alle Zonenventile schließen als Sicherheit

        GIVEN: Bewässerung läuft
        WHEN: ESP_PUMP geht offline (Heartbeat-Timeout)
        THEN: Zonenventile werden geschlossen (Safe State)
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]
        zone_b = esps["zone_b"]

        # === SETUP: Bewässerung läuft ===
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # === TRIGGER: Pumpen-ESP offline ===
        pump.disconnect()

        # === SERVER-REAKTION: Zonenventile schließen ===
        # Server erkennt: Kritischer ESP offline → Safety!
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 0, "mode": "digital"})

        # Optional: Emergency-Stop auf allen erreichbaren ESPs
        zone_a.handle_command("emergency_stop", {"reason": "pump_esp_offline"})
        zone_b.handle_command("emergency_stop", {"reason": "pump_esp_offline"})

        # === VERIFY ===
        assert zone_a.get_actuator_state(6).emergency_stopped is True
        assert zone_b.get_actuator_state(6).emergency_stopped is True

    def test_sensor_esp_fails_uses_fallback(self, climate_control_4_esp):
        """
        SZENARIO: Sensor-ESP fällt aus → Wetter-ESP als Fallback

        PRAXIS-KONTEXT:
        Primäre Sensor-Station fällt aus.
        Außen-Wetterstation hat auch Temperatursensor → Fallback.

        GIVEN: Sensor-Station und Wetter-Station aktiv
        WHEN: Sensor-Station offline
        THEN: Temperaturregelung verwendet Außensensor (limitiert)
        """
        esps = climate_control_4_esp
        sensors = esps["sensors"]
        weather = esps["weather"]
        ventilation = esps["ventilation"]

        # === SETUP ===
        sensors.set_sensor_value(gpio=4, raw_value=2200, sensor_type="DS18B20")
        weather.set_sensor_value(gpio=36, raw_value=1500, sensor_type="temperature")

        # === TRIGGER: Sensor-ESP offline ===
        sensors.disconnect()

        # === FALLBACK: Wetter-ESP Temperatur ===
        fallback_temp = weather.handle_command("sensor_read", {"gpio": 36})
        assert fallback_temp["status"] == "ok"
        assert fallback_temp["data"]["raw_value"] == 1500  # 15°C außen

        # Server kann immer noch reagieren (konservativ)
        # Außentemperatur < 20°C → Lüftung nicht voll öffnen
        if fallback_temp["data"]["raw_value"] < 2000:
            ventilation.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})

        # === VERIFY ===
        assert (
            ventilation.get_actuator_state(5).state is False
        ), "Bei fehlender Innentemperatur und kühler Außentemperatur: Lüftung zu"


# =============================================================================
# Test: Synchronized Multi-Zone Operations
# =============================================================================


class TestSynchronizedOperations:
    """
    Tests für synchronisierte Operationen über mehrere Zonen.
    """

    def test_synchronized_irrigation_start(self, irrigation_system_3_esp):
        """
        SZENARIO: Beide Zonen gleichzeitig bewässern

        PRAXIS-KONTEXT:
        Manchmal sollen mehrere Zonen gleichzeitig bewässert werden
        (z.B. gleicher Pflanzentyp, gleiches Wasserbed

        GIVEN: Beide Zonenventile geschlossen
        WHEN: Synchronisierte Bewässerung startet
        THEN: Beide Ventile öffnen → Pumpe startet
        """
        esps = irrigation_system_3_esp
        pump = esps["pump"]
        zone_a = esps["zone_a"]
        zone_b = esps["zone_b"]

        # === SYNCHRONIZED START ===
        # 1. Beide Zonenventile gleichzeitig öffnen
        zone_a.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        zone_b.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # 2. Hauptventil
        pump.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # 3. Pumpe
        pump.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        # === VERIFY: Alles synchron offen ===
        assert zone_a.get_actuator_state(6).state is True
        assert zone_b.get_actuator_state(6).state is True
        assert pump.get_actuator_state(6).state is True
        assert pump.get_actuator_state(5).state is True

    def test_emergency_broadcast_stops_all(self, climate_control_4_esp):
        """
        SZENARIO: Emergency-Broadcast stoppt alle ESPs

        PRAXIS-KONTEXT:
        Bei kritischem Fehler (Feuer, Wasserrohrbruch) muss
        ALLES sofort stoppen - auf ALLEN ESPs.

        Server sendet Broadcast → Alle ESPs reagieren
        """
        esps = climate_control_4_esp
        ventilation = esps["ventilation"]
        heating = esps["heating"]

        # === SETUP: Systeme aktiv ===
        ventilation.handle_command("actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"})
        heating.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        heating.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})

        # Verify aktiv
        assert ventilation.get_actuator_state(7).pwm_value == 0.5
        assert heating.get_actuator_state(5).state is True

        # === TRIGGER: Emergency Broadcast ===
        for esp in esps.values():
            esp.handle_command("emergency_stop", {"reason": "system_emergency_broadcast"})

        # === VERIFY: Alles gestoppt ===
        for esp_name, esp in esps.items():
            for gpio, actuator in esp.actuators.items():
                assert (
                    actuator.emergency_stopped is True
                ), f"{esp_name} GPIO {gpio} sollte emergency_stopped sein"
                assert actuator.state is False, f"{esp_name} GPIO {gpio} sollte aus sein"


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers for cross-ESP tests."""
    config.addinivalue_line("markers", "critical: Safety-critical tests")
    config.addinivalue_line("markers", "cross_esp: Tests involving multiple ESPs")
    config.addinivalue_line("markers", "cascade_failure: Cascade failure isolation tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "critical"])
