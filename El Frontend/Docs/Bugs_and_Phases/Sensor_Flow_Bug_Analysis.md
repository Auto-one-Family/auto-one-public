# Sensor-Flow Bug-Analyse

> **Dokument-Version:** 2.0
> **Erstellt:** 2025-12-31
> **Status:** ✅ BUGS GEFIXT (2025-12-31)

---

## 1. Executive Summary

### Bug-Beschreibung
1. User fügt Sensor hinzu mit Startwert 20°C
2. Es wird aber **0°C angezeigt** (Startwert ignoriert)
3. Nach einiger Zeit zeigt es **2000°C** an (offensichtlich falscher Wert)

### Identifizierte Ursachen

| Bug | Ursache | Datei | Status |
|-----|---------|-------|--------|
| **0°C** | Naming-Inkonsistenz: Wert wird als `base_value` gespeichert, aber als `raw_value` gelesen | `debug.py` | ✅ GEFIXT |
| **2000°C** | `raw` Feld wird mit `value * 100` berechnet, aber sensor_handler verwendet `raw` vor `raw_value` | `scheduler.py` | ✅ GEFIXT |

### Implementierte Fixes

| Fix | Beschreibung | Datei | Änderung |
|-----|--------------|-------|----------|
| **Fix 1** | Fallback-Chain für raw_value | `debug.py:122` | `config.get("raw_value", config.get("base_value", 0.0))` |
| **Fix 2** | Dual-Key-System in add_sensor | `debug.py:773-776` | Speichert BEIDE Keys: `raw_value` und `base_value` |
| **Fix 3** | Dual-Key-System in create_mock_esp | `debug.py:224-225` | Speichert BEIDE Keys |
| **Fix 4** | raw*100 Bug entfernt | `scheduler.py:1357-1368` | `raw` Feld komplett entfernt |

---

## 2. System-Architektur (Nach Fix)

### 2.1 Mock-ESP Sensor Flow (KORRIGIERT)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MOCK ESP SENSOR FLOW (NACH FIX)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Frontend                    Server                       Database          │
│  ────────                    ──────                       ────────          │
│                                                                              │
│  1. User klickt             2. POST /debug/mock-esp/{id}/sensors            │
│     "Sensor hinzufügen"        └─> add_sensor()                             │
│     └─> raw_value: 20              └─> sensor_config = {                    │
│                                          "raw_value": 20.0,  ✓ Für Frontend │
│                                          "base_value": 20.0, ✓ Für Scheduler│
│                                        }                                     │
│                                                                              │
│  3. SimulationScheduler startet Sensor-Job                                  │
│     └─> _calculate_sensor_value()                                           │
│         └─> base_value = sensor_config.get("base_value", 0.0)  ✓            │
│     └─> MQTT Publish                                                        │
│         {                                                                    │
│           "raw_value": 20.0,   ✓ (KEIN "raw" Feld mehr!)                    │
│           "raw_mode": true,                                                  │
│           "sensor_type": "DS18B20",                                          │
│           ...                                                                │
│         }                                                                    │
│                                                                              │
│  4. Frontend ruft getMockEsp() auf                                          │
│     └─> _build_mock_esp_response()                                          │
│         └─> raw_value = config.get("raw_value",                             │
│                                    config.get("base_value", 0.0))  ✓        │
│                                                                              │
│  5. Frontend zeigt 20°C an  ✓                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Mock-ESP vs Real-ESP Unterschiede

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SENSOR-WERT-SEMANTIK: MOCK vs REAL                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MOCK ESP (Simuliert):                                                       │
│  ─────────────────────                                                       │
│  • User gibt HUMAN-READABLE Werte ein (z.B. 20.0 für 20°C)                  │
│  • raw_value = value = user_input (KEINE ADC-Konvertierung)                 │
│  • Kein Pi-Enhanced Processing nötig                                         │
│  • raw_mode = True, aber Wert ist bereits in finaler Einheit                │
│                                                                              │
│  REAL ESP (Hardware):                                                        │
│  ────────────────────                                                        │
│  • Temperature (DS18B20, SHT31):                                            │
│    - DallasTemperature/Adafruit Library konvertiert BEREITS zu Celsius      │
│    - raw_value = celsius (KEINE weitere Konvertierung nötig)                │
│    - Server macht nur Validation + Calibration Offset                       │
│                                                                              │
│  • Analog Sensoren (pH, EC, Moisture):                                      │
│    - raw_value = ADC 0-4095 (echter Hardware-Wert)                          │
│    - Server konvertiert: ADC → Voltage → pH/EC/%                            │
│    - Pi-Enhanced Processing erforderlich                                     │
│                                                                              │
│  WICHTIG: Mock-ESPs umgehen die ADC-Layer komplett!                         │
│  Der eingegebene Wert IST der finale Wert.                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Implementierte Code-Änderungen

### 3.1 Fix 1: _build_mock_esp_response() - Fallback-Chain

**Datei:** `El Servador/god_kaiser_server/src/api/v1/debug.py`
**Zeilen:** 106-134

```python
# Build sensor responses
sensors = []
for gpio_str, config in sensors_config.items():
    # =====================================================================
    # SENSOR VALUE LOADING - Consistent Fallback Chain
    # =====================================================================
    # Mock-ESP sensors store their value in TWO keys (for historical reasons):
    #   - "raw_value": Display value for Frontend (what user sees)
    #   - "base_value": Base value for SimulationScheduler calculations
    #
    # Both contain the SAME value (user-entered, e.g., 20.0 for 20°C).
    # This is NOT an ADC value - Mock ESPs work with human-readable values.
    #
    # For real ESP32s, raw_value would be hardware-specific (ADC 0-4095 for
    # analog sensors, or already-converted values for digital sensors like
    # DS18B20 which outputs Celsius directly).
    #
    # See: add_sensor() below for where these values are stored.
    # =====================================================================
    sensor_value = config.get("raw_value", config.get("base_value", 0.0))

    sensors.append(MockSensorResponse(
        gpio=int(gpio_str),
        sensor_type=config.get("sensor_type", "GENERIC"),
        name=config.get("name"),
        subzone_id=config.get("subzone_id"),
        raw_value=sensor_value,  # ← Verwendet jetzt Fallback-Chain
        unit=config.get("unit", ""),
        quality=config.get("quality", "good"),
        raw_mode=config.get("raw_mode", True),
        last_read=None,
    ))
```

---

### 3.2 Fix 2: add_sensor() - Dual-Key-System

**Datei:** `El Servador/god_kaiser_server/src/api/v1/debug.py`
**Zeilen:** 757-787

```python
# =========================================================================
# SENSOR CONFIG STORAGE - Dual-Key System for Consistency
# =========================================================================
# We store the user-entered value under TWO keys:
#
#   "raw_value"  - Used by _build_mock_esp_response() for Frontend display
#   "base_value" - Used by SimulationScheduler._calculate_sensor_value()
#
# IMPORTANT: For Mock ESPs, the user enters human-readable values (e.g., 20°C),
# NOT hardware ADC values. This differs from real ESP32s where:
#   - DS18B20/SHT31: Already output Celsius (raw_value = celsius)
#   - pH/EC sensors: Output ADC 0-4095 (raw_value = adc, server converts)
#
# Mock ESPs bypass the ADC layer entirely - the value the user enters
# is the value that gets displayed and processed.
# =========================================================================
sensor_config = {
    "sensor_type": config.sensor_type,
    "raw_value": config.raw_value,   # For Frontend display
    "base_value": config.raw_value,  # For SimulationScheduler calculations
    "unit": config.unit,
    "quality": config.quality,
    "name": config.name,
    "subzone_id": config.subzone_id,
    "raw_mode": config.raw_mode,
    "interval_seconds": getattr(config, "interval_seconds", 30.0),
    "variation_pattern": getattr(config, "variation_pattern", "constant"),
    "variation_range": getattr(config, "variation_range", 0.0),
    "min_value": getattr(config, "min_value", config.raw_value - 10.0),
    "max_value": getattr(config, "max_value", config.raw_value + 10.0),
}
```

---

### 3.3 Fix 3: create_mock_esp() - Dual-Key-System

**Datei:** `El Servador/god_kaiser_server/src/api/v1/debug.py`
**Zeilen:** 215-233

```python
# Build simulation config for DB storage
# =====================================================================
# SENSOR CONFIG - Dual-Key System (see add_sensor() for details)
# Both raw_value and base_value contain the same user-entered value.
# =====================================================================
simulation_config = {
    "sensors": {
        str(sensor.gpio): {
            "sensor_type": sensor.sensor_type,
            "raw_value": sensor.raw_value,   # For Frontend display
            "base_value": sensor.raw_value,  # For SimulationScheduler
            "unit": sensor.unit,
            "quality": sensor.quality,
            "name": sensor.name,
            "subzone_id": sensor.subzone_id,
            "raw_mode": sensor.raw_mode,
        }
        for sensor in config.sensors
    },
    # ...
}
```

---

### 3.4 Fix 4: set_sensor_value() - raw*100 Bug entfernt

**Datei:** `El Servador/god_kaiser_server/src/services/simulation/scheduler.py`
**Zeilen:** 1324-1368

```python
# Publish if requested
if publish and self._mqtt_publish:
    runtime = self.get_runtime(esp_id)
    if runtime:
        # =====================================================================
        # MQTT PAYLOAD FOR MOCK ESP SENSOR DATA
        # =====================================================================
        # Mock ESPs send human-readable values (e.g., 20.0 for 20°C), NOT
        # hardware ADC values. This is different from real ESP32s where:
        #
        #   - Temperature sensors (DS18B20, SHT31): Already output Celsius,
        #     so raw_value = celsius (no ADC conversion needed)
        #   - Analog sensors (pH, EC): Output ADC 0-4095, server converts
        #
        # For Mock ESPs, we intentionally:
        #   1. Do NOT include a "raw" field (legacy ADC field)
        #   2. Set raw_value = value (both are the user-entered value)
        #   3. Set raw_mode = True (tells server to use raw_value as-is)
        #
        # The sensor_handler.py uses: payload.get("raw", payload.get("raw_value"))
        # By omitting "raw", it falls back to "raw_value" which is correct.
        #
        # BUG FIX: Previously had "raw": int(value * 100) which caused 20°C
        # to become 2000 in the database (the sensor_handler used "raw" first).
        # =====================================================================

        # Get sensor_type from config for complete payload
        sensors_config = sim_config.get("sensors", {})
        sensor_config = sensors_config.get(str(gpio), {})
        sensor_type = sensor_config.get("sensor_type", "GENERIC")
        unit = sensor_config.get("unit", "")

        topic = TopicBuilder.build_sensor_data_topic(esp_id, gpio, runtime.kaiser_id)
        payload = {
            "ts": int(time.time() * 1000),
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": sensor_type,
            "raw_value": value,      # User-entered value (human-readable)
            "value": value,          # Same as raw_value for Mock ESPs
            "unit": unit,
            "quality": "good",
            "raw_mode": True,        # Server should use raw_value directly
        }
        self._mqtt_publish(topic, payload, 0)
```

---

## 4. Test-Plan

### 4.1 Verifizierung Bug 1 Fix (0°C → 20°C)

```gherkin
Gegeben ein Mock ESP existiert
Wenn ich einen DS18B20 Sensor mit Startwert 20°C hinzufüge
Dann sollte das Frontend 20°C anzeigen (nicht 0°C)
Und die DB sollte raw_value=20.0 UND base_value=20.0 enthalten
```

**Test-Schritte:**
1. Mock ESP erstellen
2. Sensor hinzufügen mit raw_value: 20
3. Frontend-Anzeige prüfen
4. `/database` View öffnen → `esp_devices` Tabelle → `device_metadata` prüfen

### 4.2 Verifizierung Bug 2 Fix (2000°C → 25°C)

```gherkin
Gegeben ein Mock ESP mit Sensor existiert
Wenn ich den Sensor-Wert manuell auf 25°C setze
Dann sollte das Frontend 25°C anzeigen (nicht 2500°C)
Und die MQTT-Nachricht sollte raw_value=25.0 enthalten (KEIN "raw" Feld)
```

**Test-Schritte:**
1. Mock ESP mit Sensor erstellen
2. Sensor-Wert bearbeiten auf 25
3. `/mqtt-log` View öffnen
4. Payload prüfen: `raw_value: 25` (kein `raw: 2500`)

### 4.3 Regression Tests

```gherkin
# Automatische Sensor-Jobs
Gegeben ein Mock ESP mit Sensor und Auto-Heartbeat läuft
Wenn 30 Sekunden vergehen
Dann sollte der korrekte Wert via MQTT gepublished werden

# Batch Updates
Gegeben ein Mock ESP mit mehreren Sensoren
Wenn ich Batch-Update mit verschiedenen Werten mache
Dann sollten alle Werte korrekt angezeigt werden

# Bestehendes Mock ESP (vor Fix erstellt)
Gegeben ein Mock ESP das VOR dem Fix erstellt wurde
Wenn ich getMockEsp() aufrufe
Dann sollte der Fallback auf base_value greifen
```

---

## 5. Architektur-Dokumentation

### 5.1 Dual-Key-System Erklärung

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DUAL-KEY-SYSTEM FÜR SENSOR-WERTE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  simulation_config.sensors["gpio"] = {                                       │
│      "sensor_type": "DS18B20",                                              │
│      "raw_value": 20.0,    ← Für Frontend (_build_mock_esp_response)        │
│      "base_value": 20.0,   ← Für SimulationScheduler (_calculate_sensor_value)
│      "unit": "°C",                                                          │
│      ...                                                                     │
│  }                                                                           │
│                                                                              │
│  WARUM ZWEI KEYS?                                                           │
│  ────────────────                                                           │
│  Historisch gewachsen - ursprünglich wurden unterschiedliche Namen verwendet:│
│  • base_value: Für den Scheduler (existierte zuerst)                        │
│  • raw_value: Für das Frontend (später hinzugefügt)                         │
│                                                                              │
│  JETZT: Beide enthalten denselben Wert, Fallback-Chain garantiert           │
│         Kompatibilität mit alten Daten.                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 MQTT Payload-Unterschiede

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MQTT PAYLOAD VERGLEICH                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MOCK ESP (nach Fix):                                                        │
│  {                                                                           │
│    "ts": 1735689600000,                                                      │
│    "esp_id": "MOCK_TEST01",                                                  │
│    "gpio": 4,                                                                │
│    "sensor_type": "DS18B20",                                                 │
│    "raw_value": 20.0,        ← Human-readable (Celsius)                     │
│    "value": 20.0,            ← Gleicher Wert                                │
│    "unit": "°C",                                                            │
│    "quality": "good",                                                        │
│    "raw_mode": true                                                          │
│  }                                                                           │
│  ↑ KEIN "raw" Feld! sensor_handler fällt auf raw_value zurück.              │
│                                                                              │
│  REAL ESP (DS18B20):                                                         │
│  {                                                                           │
│    "ts": 1735689600000,                                                      │
│    "esp_id": "ESP_12AB34CD",                                                 │
│    "gpio": 4,                                                                │
│    "sensor_type": "DS18B20",                                                 │
│    "raw": 2150,              ← Hardware-Rohwert (I2C/OneWire)               │
│    "value": 21.5,            ← Optional: lokal verarbeitet                  │
│    "raw_mode": true                                                          │
│  }                                                                           │
│                                                                              │
│  REAL ESP (pH Sensor):                                                       │
│  {                                                                           │
│    "ts": 1735689600000,                                                      │
│    "esp_id": "ESP_12AB34CD",                                                 │
│    "gpio": 34,                                                               │
│    "sensor_type": "ph",                                                      │
│    "raw": 2048,              ← ADC 0-4095                                   │
│    "raw_mode": true          ← Server muss ADC→pH konvertieren              │
│  }                                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Zusammenfassung

### Was wurde gefixt?

| Problem | Lösung | Risiko |
|---------|--------|--------|
| 0°C statt 20°C | Fallback-Chain + Dual-Key-System | Keins (Backward-kompatibel) |
| 2000°C statt 20°C | `raw` Feld entfernt | Keins (sensor_handler hat Fallback) |

### Geänderte Dateien

1. `El Servador/god_kaiser_server/src/api/v1/debug.py`
   - `_build_mock_esp_response()`: Fallback-Chain für raw_value
   - `add_sensor()`: Dual-Key-System
   - `create_mock_esp()`: Dual-Key-System

2. `El Servador/god_kaiser_server/src/services/simulation/scheduler.py`
   - `set_sensor_value()`: `raw` Feld entfernt, sensor_type hinzugefügt

### Keine Änderungen nötig

- `sensor_handler.py`: Funktioniert bereits mit Fallback (`payload.get("raw", payload.get("raw_value"))`)
- `_sensor_job()`: War bereits korrekt (kein `raw` Feld)
- Frontend: Keine Änderungen nötig

---

**Letzte Aktualisierung:** 2025-12-31
**Gefixt von:** Claude Code
