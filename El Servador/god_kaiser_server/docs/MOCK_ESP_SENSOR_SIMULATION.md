# Mock-ESP Sensor Simulation (Paket B.1)

**Status:** ✅ VOLLSTÄNDIG IMPLEMENTIERT
**Version:** 1.1.0
**Datum:** 2026-03-07

---

## Übersicht

Die Mock-ESP Sensor-Simulation ermöglicht es, realistische Sensor-Daten ohne echte Hardware zu generieren. Die Implementierung folgt dem **DB-First Prinzip** (Database as Single Source of Truth) und nutzt den **CentralScheduler** für zeitgesteuerte Jobs.

### Kernfeatures

✅ **3 Variation Patterns:** CONSTANT, RANDOM, DRIFT
✅ **Manual Override:** Sensor-Werte manuell setzen
✅ **Identische Payloads:** Exakt wie echte ESP32-Devices
✅ **Dynamisches Management:** Sensoren zur Laufzeit hinzufügen/entfernen
✅ **Konfigurierbare Intervals:** Individuelles Publishing-Intervall pro Sensor
✅ **DB-First Architecture:** Konfiguration überlebt Server-Restart
✅ **Multi-Value Sensor Split:** SHT31/BMP280/BME280 werden automatisch in Einzelwerte expandiert

---

## Architektur

### Komponenten-Hierarchie

```
┌─────────────────────────────────────────────────────────────┐
│ REST API (debug.py)                                         │
│ ─ POST /debug/mock-esp/{id}/sensors                        │
│ ─ POST /debug/mock-esp/{id}/sensors/{gpio}/value           │
│ ─ DELETE /debug/mock-esp/{id}/sensors/{gpio}/value         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ ESPRepository (esp_repo.py)                                 │
│ ─ add_sensor_to_mock()                                      │
│ ─ set_manual_sensor_override()                              │
│ ─ clear_manual_sensor_override()                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PostgreSQL (esp_devices.device_metadata)                    │
│ ─ simulation_config.sensors                                 │
│ ─ simulation_config.manual_overrides                        │
└─────────────────────────────────────────────────────────────┘
                          ↑
┌─────────────────────────────────────────────────────────────┐
│ SimulationScheduler (scheduler.py)                          │
│ ─ start_mock() → Lädt Sensor-Config aus DB                 │
│ ─ _sensor_job() → Berechnet Wert, publiziert MQTT          │
│ ─ _calculate_sensor_value() → Pattern + Override           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ CentralScheduler (scheduler.py in core/)                    │
│ ─ APScheduler: Intervall-Jobs für jeden Sensor             │
│ ─ Job-ID: mock_{esp_id}_sensor_{gpio}_{sensor_type}        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ MQTT Broker (Mosquitto)                                     │
│ ─ Topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data        │
│ ─ Payload: IDENTISCH zu echtem ESP32                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Database-Schema

### ESP Device Metadata

Sensor-Konfiguration wird in `esp_devices.device_metadata` als JSON gespeichert:

```json
{
  "simulation_config": {
    "sensors": {
      "4_ds18b20": {
        "sensor_type": "ds18b20",
        "base_value": 22.0,
        "unit": "°C",
        "interval_seconds": 30.0,
        "variation_pattern": "random",
        "variation_range": 0.5,
        "min_value": 15.0,
        "max_value": 35.0,
        "quality": "good",
        "name": "Temperatur Sensor 1",
        "subzone_id": null,
        "raw_mode": true,
        "gpio": 4
      },
      "21_sht31_temp": {
        "sensor_type": "sht31_temp",
        "base_value": 23.0,
        "unit": "",
        "quality": "good",
        "gpio": 21
      },
      "21_sht31_humidity": {
        "sensor_type": "sht31_humidity",
        "base_value": 23.0,
        "unit": "",
        "quality": "good",
        "gpio": 21
      }
    },
    "manual_overrides": {
      "4": 35.0
    },
    "actuators": {},
    "heartbeat_interval": 60
  },
  "simulation_state": "running",
  "mock": true
}
```

> **Key-Format:** `"{gpio}_{sensor_type}"` — Multi-Value-Sensoren (SHT31, BMP280, BME280) werden bei der Erstellung automatisch in Einzelwerte expandiert (z.B. `"sht31"` → `"21_sht31_temp"` + `"21_sht31_humidity"`).

---

## Variation Patterns

### 1. CONSTANT - Fester Wert

```python
# Konfiguration
{
    "base_value": 22.0,
    "variation_pattern": "constant",
    "variation_range": 0.0  # Wird ignoriert
}

# Verhalten
# Sensor sendet IMMER 22.0
```

**Use Case:** Baseline-Tests, exakte Reproduzierbarkeit

---

### 2. RANDOM - Zufällige Variation

```python
# Konfiguration
{
    "base_value": 22.0,
    "variation_pattern": "random",
    "variation_range": 0.5,
    "min_value": 21.0,
    "max_value": 23.0
}

# Verhalten
# Jeder Sensor-Job wählt zufälligen Wert:
# value = base_value + random.uniform(-variation_range, +variation_range)
# value = 22.0 + random.uniform(-0.5, +0.5)
# Beispiel-Sequenz: [22.3, 21.8, 22.5, 21.6, 22.1, ...]
```

**Use Case:** Normale Sensor-Fluktuation simulieren

---

### 3. DRIFT - Kontinuierliche Änderung

```python
# Konfiguration
{
    "base_value": 22.0,
    "variation_pattern": "drift",
    "variation_range": 0.2,
    "min_value": 20.0,
    "max_value": 25.0
}

# Verhalten
# Wert ändert sich kontinuierlich, kehrt an Grenzen um:
# Schritt: variation_range * 0.1 = 0.02 pro Iteration
# Beispiel-Sequenz:
# Start: 22.0 (direction: +1)
# 22.02 → 22.04 → ... → 24.98 → 25.0 (kehrt um, direction: -1)
# 24.98 → 24.96 → ... → 20.02 → 20.0 (kehrt um, direction: +1)
# 20.02 → 20.04 → ...
```

**Use Case:** Sensor-Alterung, langsame Umweltänderungen, Tag/Nacht-Zyklen

---

## Runtime-State (In-Memory)

Der `SimulationScheduler` speichert transiente Daten nur im RAM:

```python
@dataclass
class MockESPRuntime:
    esp_id: str
    kaiser_id: str
    zone_id: str
    start_time: float  # time.time() bei start_mock()

    # Drift-Pattern State (wird NICHT in DB gespeichert)
    drift_values: Dict[int, float]      # {gpio: current_value}
    drift_directions: Dict[int, int]    # {gpio: +1 oder -1}

    # Sensor-Jobs Tracking
    active_sensor_jobs: Dict[str, str]  # {gpio_type: job_id} e.g. "21_sht31_temp": "mock_..."
```

**Warum nicht in DB?**
- Drift-Werte sind transient und verändern sich sekündlich
- Bei Server-Restart: Drift beginnt von vorne (von `base_value`)
- DB speichert nur Konfiguration, nicht Zustand

---

## MQTT Payload-Format

### Sensor-Daten (KRITISCH: Identisch zu echtem ESP!)

```json
{
    "ts": 1735818000000,         // MILLISEKUNDEN (int(time.time() * 1000))
    "esp_id": "MOCK_001",
    "gpio": 4,
    "sensor_type": "DS18B20",
    "raw": 2250,                  // INTEGER (int(value * 100))
    "raw_value": 22.5,            // FLOAT
    "raw_mode": true,             // BOOLEAN (REQUIRED!)
    "value": 22.5,
    "unit": "°C",
    "quality": "good",
    "zone_id": "greenhouse_1",
    "subzone_id": ""
}
```

**KRITISCHE Unterschiede zu alten Mock-Implementierungen:**
- ✅ `ts` in **MILLISEKUNDEN** (nicht Sekunden)
- ✅ `raw` als **INTEGER** (nicht Float)
- ✅ `raw_mode: true` **MUSS vorhanden sein** (Handler-Requirement)

**Validierung durch sensor_handler.py:**
- `ts` oder `timestamp` MUSS vorhanden sein
- `raw` oder `raw_value` MUSS vorhanden sein
- `raw_mode` MUSS `true` sein (Zeile 257-310 in sensor_handler.py)

---

## API Endpoints

### 1. Sensor hinzufügen

```bash
POST /api/v1/debug/mock-esp/{esp_id}/sensors

{
    "gpio": 4,
    "sensor_type": "DS18B20",
    "raw_value": 22.0,              # Wird als base_value verwendet
    "unit": "°C",
    "interval_seconds": 30.0,        # Publishing-Intervall
    "variation_pattern": "random",   # constant, random, drift
    "variation_range": 0.5,          # Für random/drift
    "min_value": 15.0,               # Optional (default: raw_value - 10)
    "max_value": 35.0                # Optional (default: raw_value + 10)
}

# Response
{
    "success": true,
    "esp_id": "MOCK_001",
    "command": "add_sensor",
    "result": {
        "gpio": 4,
        "sensor_type": "DS18B20",
        "db_updated": true,
        "job_started": true  # Falls Simulation läuft
    }
}
```

**Flow:**
1. Validiere Sensor-Konfiguration (Pydantic Schema)
2. Speichere in DB (`simulation_config.sensors`)
3. Falls Simulation läuft: Starte Sensor-Job sofort via `add_sensor_job()`
4. Sensor beginnt MQTT-Publishing nach `interval_seconds`

---

### 2. Manual Override setzen

```bash
POST /api/v1/debug/mock-esp/{esp_id}/sensors/{gpio}/value

{
    "raw_value": 35.0,
    "quality": "good",
    "publish": true  # Ignoriert (nicht implementiert)
}

# Response
{
    "success": true,
    "esp_id": "MOCK_001",
    "command": "set_manual_sensor_override",
    "result": {
        "gpio": 4,
        "override_value": 35.0,
        "db_updated": true
    }
}
```

**Flow:**
1. Prüfe ob Sensor existiert
2. Speichere in DB (`simulation_config.manual_overrides`)
3. Nächster Sensor-Job verwendet Override-Wert
4. Sensor sendet konstant 35.0 bis Override entfernt wird

**Priorität:**
```python
# In _calculate_sensor_value():
if manual_override exists:
    return override_value  # HÖCHSTE PRIORITÄT
elif pattern == "constant":
    return base_value
elif pattern == "random":
    return base_value + random_variation
elif pattern == "drift":
    return drift_value
```

---

### 3. Manual Override entfernen

```bash
DELETE /api/v1/debug/mock-esp/{esp_id}/sensors/{gpio}/value

# Response
{
    "success": true,
    "esp_id": "MOCK_001",
    "command": "clear_manual_sensor_override",
    "result": {
        "gpio": 4,
        "override_cleared": true
    }
}
```

**Flow:**
1. Entferne aus DB (`simulation_config.manual_overrides`)
2. Nächster Sensor-Job kehrt zu Pattern zurück
3. Bei DRIFT: Wert setzt bei `base_value` neu an (kein Speicher)

---

### 4. Sensor entfernen

```bash
DELETE /api/v1/debug/mock-esp/{esp_id}/sensors/{gpio}

# Response
{
    "success": true,
    "esp_id": "MOCK_001",
    "command": "remove_sensor",
    "result": {
        "gpio": 4,
        "db_updated": true,
        "job_stopped": true  # Falls Simulation läuft
    }
}
```

**Flow:**
1. Falls Simulation läuft: Stoppe Sensor-Job via `remove_sensor_job()`
2. Lösche aus DB (`simulation_config.sensors`)
3. Cleanup Runtime-State (Drift-Werte, Job-IDs)

---

## Job-Management (APScheduler)

### Job-ID Pattern

```python
# Heartbeat-Job (pro Mock-ESP)
job_id = f"mock_{esp_id}_heartbeat"
# Beispiel: mock_MOCK_001_heartbeat

# Sensor-Job (pro Sensor-Type)
job_id = f"mock_{esp_id}_sensor_{gpio}_{sensor_type}"
# Beispiel: mock_MOCK_001_sensor_4_ds18b20
# Multi-Value: mock_MOCK_001_sensor_21_sht31_temp
```

### Job-Lifecycle

```
Mock erstellen (auto_start=True)
    ↓
start_mock()
    ↓
Heartbeat-Job erstellen (mock_{esp_id}_heartbeat)
    ↓
Sensor-Config aus DB laden
    ↓
Für jeden Sensor: Sensor-Job erstellen (mock_{esp_id}_sensor_{gpio}_{type})
    ↓
Jobs laufen periodisch (APScheduler)
    ↓
stop_mock()
    ↓
Alle Jobs entfernen (remove_jobs_by_prefix(f"mock_{esp_id}_"))
    ↓
Runtime-State entfernen
```

### Sensor-Job hinzufügen (zur Laufzeit)

```python
# API Call: POST /debug/mock-esp/MOCK_001/sensors
#   → esp_repo.add_sensor_to_mock(esp_id, gpio, sensor_config)
#   → DB UPDATE

# Falls Simulation läuft:
sim_scheduler.add_sensor_job(
    esp_id="MOCK_001",
    gpio=4,
    interval_seconds=30.0
)
    ↓
CentralScheduler.add_interval_job(
    job_id="mock_MOCK_001_sensor_4_DS18B20",
    func=_sensor_job,
    seconds=30.0,
    args=["MOCK_001", 4, "DS18B20"],
    category=JobCategory.MOCK_ESP
)
    ↓
Job startet sofort (start_immediately=True)
```

---

## Recovery nach Server-Restart

### Problem

APScheduler-Jobs sind **In-Memory** → Bei Server-Restart verloren!

### Lösung: DB-First Recovery

```python
# In main.py (Zeile 216-223)
async for session in get_session():
    sim_scheduler = get_simulation_scheduler()
    recovered = await sim_scheduler.recover_mocks(session)
    logger.info(f"Recovered {recovered} mock simulations from database")
    break
```

**Flow:**
1. Server startet → CentralScheduler initialisiert (leer)
2. SimulationScheduler initialisiert
3. `recover_mocks()` lädt alle Mocks mit `simulation_state="running"` aus DB
4. Für jeden Mock:
   - Heartbeat-Job erstellen
   - Sensor-Config aus DB laden
   - Sensor-Jobs erstellen
5. Simulation läuft weiter, als wäre nichts passiert

**SQL-Query (intern):**
```sql
SELECT * FROM esp_devices
WHERE hardware_type = 'MOCK_ESP32'
AND device_metadata->>'simulation_state' = 'running'
```

---

## Wertberechnung (Pseudocode)

```python
def _calculate_sensor_value(
    gpio: int,
    sensor_config: dict,
    runtime: MockESPRuntime,
    manual_overrides: dict
) -> float:

    # PRIORITÄT 1: Manual Override
    if str(gpio) in manual_overrides:
        return float(manual_overrides[str(gpio)])

    # Extract config
    base_value = sensor_config.get("base_value", 0.0)
    pattern = sensor_config.get("variation_pattern", "constant").lower()
    range_ = sensor_config.get("variation_range", 0.0)
    min_val = sensor_config.get("min_value", base_value - 10.0)
    max_val = sensor_config.get("max_value", base_value + 10.0)

    # PRIORITÄT 2: Pattern-basierte Berechnung
    if pattern == "constant":
        value = base_value

    elif pattern == "random":
        variation = random.uniform(-range_, +range_)
        value = base_value + variation

    elif pattern == "drift":
        # Initialisiere Drift-State falls nicht vorhanden
        if gpio not in runtime.drift_values:
            runtime.drift_values[gpio] = base_value
            runtime.drift_directions[gpio] = random.choice([-1, 1])

        # Drift-Wert ändern
        drift_step = range_ * 0.1
        runtime.drift_values[gpio] += drift_step * runtime.drift_directions[gpio]

        # Richtung umkehren an Grenzen
        if runtime.drift_values[gpio] >= max_val:
            runtime.drift_values[gpio] = max_val
            runtime.drift_directions[gpio] = -1
        elif runtime.drift_values[gpio] <= min_val:
            runtime.drift_values[gpio] = min_val
            runtime.drift_directions[gpio] = 1

        value = runtime.drift_values[gpio]

    else:
        # Fallback: CONSTANT
        value = base_value

    # PRIORITÄT 3: Clamp zu min/max
    value = max(min_val, min(max_val, value))

    # PRIORITÄT 4: Round zu 2 Dezimalstellen
    return round(value, 2)
```

---

## Verifikation-Checkliste

### 1. Payload-Validierung

```bash
# MQTT Monitor
mosquitto_sub -t "kaiser/god/esp/+/sensor/+/data" -v

# Erwartetes Payload:
{
    "ts": 1735818000000,   # ✓ MILLISEKUNDEN
    "esp_id": "MOCK_001",
    "gpio": 4,
    "sensor_type": "DS18B20",
    "raw": 2205,            # ✓ INTEGER
    "raw_value": 22.05,     # ✓ FLOAT
    "raw_mode": true,       # ✓ BOOLEAN
    "value": 22.05,
    "unit": "°C",
    "quality": "good",
    "zone_id": "",
    "subzone_id": ""
}
```

**Checks:**
- [ ] `ts` ist Millisekunden (13 Digits)
- [ ] `raw` ist Integer
- [ ] `raw_mode` ist Boolean `true`
- [ ] Topic verwendet TopicBuilder
- [ ] Payload wird von `sensor_handler.py` akzeptiert

---

### 2. Pattern-Tests

**CONSTANT:**
```bash
# Sensor mit CONSTANT erstellen
curl -X POST http://localhost:8000/api/v1/debug/mock-esp/MOCK_001/sensors \
  -d '{"gpio":4, "sensor_type":"DS18B20", "raw_value":22.0, "variation_pattern":"constant"}'

# MQTT-Monitor: Alle Werte sollten EXAKT 22.0 sein
# ✓ 22.0, 22.0, 22.0, 22.0, ...
```

**RANDOM:**
```bash
# Sensor mit RANDOM erstellen
curl -X POST ... \
  -d '{"gpio":34, "variation_pattern":"random", "variation_range":0.5, "base_value":45.0}'

# MQTT-Monitor: Werte sollten um 45.0 schwanken
# ✓ 45.3, 44.7, 45.5, 44.6, 45.1, ...
```

**DRIFT:**
```bash
# Sensor mit DRIFT erstellen
curl -X POST ... \
  -d '{"gpio":35, "variation_pattern":"drift", "variation_range":0.2, "min":30.0, "max":60.0}'

# MQTT-Monitor: Werte sollten kontinuierlich steigen/fallen
# ✓ 45.0 → 45.02 → 45.04 → ... → 59.98 → 60.0 → 59.98 → ...
```

---

### 3. Manual Override

```bash
# 1. Override setzen
curl -X POST http://localhost:8000/api/v1/debug/mock-esp/MOCK_001/sensors/4/value \
  -d '{"raw_value": 35.0}'

# MQTT-Monitor: Wert sollte sofort 35.0 sein (konstant)
# ✓ 35.0, 35.0, 35.0, ...

# 2. Override entfernen
curl -X DELETE http://localhost:8000/api/v1/debug/mock-esp/MOCK_001/sensors/4/value

# MQTT-Monitor: Wert kehrt zu Pattern zurück
# ✓ 22.3, 21.8, 22.5, ... (falls random)
```

---

### 4. Handler-Akzeptanz

```bash
# Server-Logs (DEBUG Level)
LOG_LEVEL=DEBUG poetry run uvicorn src.main:app

# Erwartete Logs (KEINE Fehler):
[sensor_handler] Processing sensor data from MOCK_001
[sensor_handler] ✓ Sensor data saved: MOCK_001, GPIO 4

# FEHLER wenn:
[sensor_handler] Invalid payload: missing required field 'raw_mode'  # ❌
[sensor_handler] ESP device not found: MOCK_001                      # ❌
```

---

### 5. DB-Speicherung

```sql
SELECT esp_id, gpio, sensor_type, raw_value, processed_value, timestamp, data_source
FROM sensor_data
WHERE esp_id LIKE 'MOCK_%'
ORDER BY timestamp DESC
LIMIT 10;

-- Erwartete Ergebnisse:
-- ✓ esp_id: MOCK_001
-- ✓ gpio: 4
-- ✓ sensor_type: DS18B20
-- ✓ raw_value: 22.05
-- ✓ data_source: MOCK (automatisch erkannt via hardware_type)
```

---

### 6. Recovery-Test

```bash
# 1. Mock mit Sensor erstellen + auto_start
curl -X POST http://localhost:8000/api/v1/debug/mock-esp \
  -d '{"esp_id":"MOCK_001", "auto_heartbeat":true, "sensors":[{"gpio":4, ...}]}'

# 2. Server stoppen
^C

# 3. Server starten
poetry run uvicorn src.main:app

# 4. Log prüfen:
# ✓ "Recovered 1 mock simulations from database"
# ✓ "Started mock simulation: MOCK_001 (heartbeat every 60s, 1 sensors)"

# 5. MQTT-Monitor: Daten sollten sofort fließen
# ✓ kaiser/god/esp/MOCK_001/sensor/4/data: {...}
```

---

## Code-Locations

| Komponente | Datei | Zeilen |
|------------|-------|--------|
| **SimulationScheduler** | `src/services/simulation/scheduler.py` | 54-717 |
| - `_sensor_job()` | `scheduler.py` | 487-565 |
| - `_calculate_sensor_value()` | `scheduler.py` | 567-645 |
| - `add_sensor_job()` | `scheduler.py` | 353-402 |
| - `remove_sensor_job()` | `scheduler.py` | 404-447 |
| **ESPRepository** | `src/db/repositories/esp_repo.py` | - |
| - `add_sensor_to_mock()` | `esp_repo.py` | 458-495 |
| - `set_manual_sensor_override()` | `esp_repo.py` | 600-633 |
| - `clear_manual_sensor_override()` | `esp_repo.py` | 635-664 |
| **API Endpoints** | `src/api/v1/debug.py` | - |
| - `POST /sensors` | `debug.py` | 647-724 |
| - `POST /sensors/{gpio}/value` | `debug.py` | 788-847 |
| - `DELETE /sensors/{gpio}/value` | `debug.py` | 850-901 |
| **Pydantic Schema** | `src/schemas/debug.py` | 56-92 |
| **CentralScheduler** | `src/core/scheduler.py` | 63-594 |
| **main.py Integration** | `src/main.py` | 194-205 |

---

## FAQ

### Q: Warum `raw` als Integer?

**A:** Der `sensor_handler.py` erwartet `raw` als ADC-Rohwert (0-4095 typisch). Echte ESPs senden Integer-Werte. Für Kompatibilität: `raw = int(value * 100)`.

---

### Q: Warum `ts` in Millisekunden?

**A:** JavaScript Date-Objekte verwenden Millisekunden. Echte ESPs senden `int(millis())`. Frontend-Kompatibilität.

---

### Q: Was passiert bei Server-Restart mit DRIFT-Pattern?

**A:** Drift-State ist **In-Memory**. Bei Restart: Sensor beginnt wieder bei `base_value`. Das ist Absicht (vermeidet DB-Overhead).

---

### Q: Kann ich Sensor-Intervall zur Laufzeit ändern?

**A:** Ja, via:
1. `PATCH /api/v1/esp/devices/{id}` → Update `device_metadata`
2. Sensor-Job entfernen + neu erstellen mit neuem Intervall

**Einfacher:** Mock löschen + neu erstellen.

---

### Q: Warum werden Manual Overrides nicht in `sensor_data` gespeichert?

**A:** Override ist **Konfiguration**, nicht **Daten**. Sensor sendet Werte wie gewohnt → Handler speichert in DB. Override beeinflusst nur `_calculate_sensor_value()`.

---

### Q: Kann ich Pi-Enhanced Processing testen?

**A:** Ja! Setze in `sensor_config`:
```json
{
    "sensor_type": "DS18B20",  // Muss Sensor-Library haben
    "raw_mode": true,          // REQUIRED
    "raw_value": 2250          // ADC-Rohwert (int)
}
```

Server wird Processing triggern, wenn `sensor_config.pi_enhanced == True` in DB.

---

## Changelog

### v1.2.0 (2026-03-07) — T02-Fix2
- ✅ Bug B2: `sensor_configs.onewire_address` von `varchar(16)` auf `varchar(32)` erweitert (Alembic Migration)
- ✅ Bug B2: Auto-generierte OneWire-Adressen von `AUTO_` (21 chars) auf `SIM_` Prefix (16 chars) gekürzt
- ✅ Bug B2: Pydantic Schemas (`SensorConfigCreate`, `MockSensorConfig`) `max_length` auf 32 angepasst
- ✅ Bug B3: Debug-API `POST /mock-esp/{id}/actuators` erstellt jetzt `actuator_configs` DB-Record zusätzlich zur `device_metadata` JSON
- ✅ Bug B3: Mock-Aktoren sind nun über Standard-APIs (`GET /actuators/{esp_id}`) und Logic Engine auffindbar

### v1.1.0 (2026-03-07)
- ✅ Multi-Value Sensor Split: `create_mock_esp()` expandiert `"sht31"` → `"sht31_temp"` + `"sht31_humidity"` (via `is_multi_value_sensor()`)
- ✅ Dict-Key-Format: `simulation_config.sensors` Keys von `str(gpio)` auf `"{gpio}_{sensor_type}"` (verhindert Überschreibung bei Multi-Value-Sensoren auf gleichem GPIO)
- ✅ SensorConfig DB-Einträge: Expanded sensor configs werden einzeln in DB erstellt
- ✅ 14 Unit Tests: `test_mock_esp_multi_value.py`

### v1.0.0 (2025-12-26)
- ✅ Sensor-Simulation vollständig implementiert
- ✅ API Endpoints DB-First umgestellt
- ✅ 3 Variation Patterns (CONSTANT, RANDOM, DRIFT)
- ✅ Manual Override Support
- ✅ Recovery nach Server-Restart
- ✅ Payload-Kompatibilität mit echtem ESP32
- ✅ Dokumentation erstellt

---

**Ende der Dokumentation**
