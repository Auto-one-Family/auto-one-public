# Server Architecture Dependencies - God-Kaiser ↔ ESP32 Integration

> **Zweck:** Server-ESP32-Abhängigkeiten verstehen für sichere Server-Code-Änderungen

**Version:** 1.1
**Letzte Aktualisierung:** 2025-12

---

## 🎯 Kritische ESP32-Dokumentation für Server-Entwicklung

Der God-Kaiser Server **MUSS** folgende ESP32-Dokumentation kennen, um korrekt mit ESPs zu interagieren:

### MQTT Protocol Contract (KRITISCH!)

| ESP32 Dokumentation | Server-Komponente | Abhängigkeit |
|---------------------|-------------------|--------------|
| `El Trabajante/docs/Mqtt_Protocoll.md` | `src/mqtt/subscriber.py`, `src/mqtt/handlers/` | **KRITISCH** - Topic-Schemas, Payload-Strukturen |
| `El Trabajante/docs/MQTT_CLIENT_API.md` | `src/mqtt/client.py` | HIGH - QoS-Levels, Wildcards |

**Warum kritisch:**
- Server MUSS exakt die gleichen Topic-Patterns verwenden
- Payload-Schemas MÜSSEN 100% kompatibel sein
- Breaking Changes in MQTT-Protokoll brechen die gesamte Kommunikation

### System Flows (HIGH)

| ESP32 Flow | Server-Service | Abhängigkeit |
|------------|----------------|--------------|
| `El Trabajante/docs/system-flows/02-sensor-reading-flow.md` | `src/mqtt/handlers/sensor_handler.py`, `src/sensors/library_loader.py` | **HIGH** - Server empfängt Sensor-Daten |
| `El Trabajante/docs/system-flows/03-actuator-command-flow.md` | `src/mqtt/handlers/actuator_handler.py`, `src/services/actuator_service.py` | **HIGH** - Server sendet Actuator-Commands |
| `El Trabajante/docs/system-flows/08-zone-assignment-flow.md` | `src/services/zone_service.py` | MEDIUM - Zone-Management |
| `El Trabajante/docs/system-flows/01-boot-sequence.md` | `src/services/esp_service.py` | MEDIUM - ESP Discovery & Registration |

**Warum wichtig:**
- Zeigt, wie ESP32 auf Server-Commands reagiert
- Dokumentiert, welche Daten Server empfängt
- Erklärt Timing-Constraints (z.B. Sensor-Intervalle)

### Datenmodelle (MEDIUM)

| ESP32 Datei | Server-Schema | Abhängigkeit |
|-------------|---------------|--------------|
| `El Trabajante/src/models/sensor_types.h` | `src/schemas/sensor.py` | MEDIUM - Sensor-Konfiguration |
| `El Trabajante/src/models/actuator_types.h` | `src/schemas/actuator.py` | MEDIUM - Actuator-Konfiguration |
| `El Trabajante/src/models/error_codes.h` | (noch zu erstellen) | MEDIUM - Error-Handling |

**Warum wichtig:**
- Pydantic Schemas MÜSSEN mit C++ Structs übereinstimmen
- Field-Namen MÜSSEN identisch sein
- Enum-Werte MÜSSEN synchron bleiben

### Configuration (LOW-MEDIUM)

| ESP32 Dokumentation | Server-Service | Abhängigkeit |
|---------------------|----------------|--------------|
| `El Trabajante/docs/NVS_KEYS.md` | `src/services/esp_service.py` | LOW - Server kennt, was ESP32 speichert |
| `El Trabajante/docs/Dynamic Zones and Provisioning/` | `src/services/zone_service.py` | MEDIUM - Zone-Hierarchie |

---

## 📡 MQTT Topic-Abhängigkeiten (Server-Perspektive)

### Topics die der Server SUBSCRIBED (ESP32 → Server)

| Topic Pattern | ESP32 Source | Server Handler | Payload-Schema |
|---------------|--------------|----------------|----------------|
| `kaiser/+/esp/+/sensor/+/data` | `El Trabajante/src/services/sensor/sensor_manager.cpp` | `src/mqtt/handlers/sensor_handler.py` | `Mqtt_Protocoll.md` Line 84-100 |
| `kaiser/+/esp/+/actuator/+/status` | `El Trabajante/src/services/actuator/actuator_manager.cpp` | `src/mqtt/handlers/actuator_handler.py` | `Mqtt_Protocoll.md` Line 185-203 |
| `kaiser/+/esp/+/actuator/+/response` | `El Trabajante/src/services/actuator/actuator_manager.cpp` | `src/mqtt/handlers/actuator_handler.py` | `Mqtt_Protocoll.md` Line 208-226 |
| `kaiser/+/esp/+/system/heartbeat` | `El Trabajante/src/services/communication/mqtt_client.cpp` | `src/mqtt/handlers/heartbeat_handler.py` | `Mqtt_Protocoll.md` Line 316-335 |
| `kaiser/+/esp/+/system/diagnostics` | `El Trabajante/src/error_handling/health_monitor.cpp` | `src/mqtt/handlers/system_handler.py` | `Mqtt_Protocoll.md` Line 340-362 |

**KRITISCH:** Payload-Schemas MÜSSEN synchron bleiben!

### Topics auf die der Server PUBLISHED (Server → ESP32)

| Topic Pattern | Server Service | ESP32 Handler | Payload-Schema |
|---------------|----------------|---------------|----------------|
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command` | `src/services/actuator_service.py` | `El Trabajante/src/services/actuator/actuator_manager.cpp` | `Mqtt_Protocoll.md` Line 143-161 |
| `kaiser/{kaiser_id}/esp/{esp_id}/config` | `src/services/esp_service.py` | `El Trabajante/src/services/config/config_manager.cpp` | `Mqtt_Protocoll.md` Line 401-430 |
| `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` | `src/services/zone_service.py` | `El Trabajante/src/services/provisioning/provision_manager.cpp` | `Mqtt_Protocoll.md` Line 465-485 |
| `kaiser/broadcast/emergency` | `src/services/actuator_service.py` | `El Trabajante/src/services/actuator/actuator_manager.cpp` | `Mqtt_Protocoll.md` Line 529-547 |
| `kaiser/{kaiser_id}/esp/{esp_id}/pi_enhanced/response` | `src/mqtt/publisher.py::publish_pi_enhanced_response` | ESP32 SensorManager | `Mqtt_Protocoll.md` Line 550-565 |

**KRITISCH:** ESP32 erwartet exakte Payload-Struktur!

---

## 🏗️ Server-Module-Abhängigkeiten

### Sensor Processing Layer

```
┌─────────────────────────────────────────────────────────────┐
│ ESP32: SensorManager                                        │
│ File: El Trabajante/src/services/sensor/sensor_manager.cpp │
└─────────────────────────────────────────────────────────────┘
                          ↓ (MQTT Publish)
                   kaiser/god/esp/{esp_id}/sensor/{gpio}/data
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: SensorHandler                                       │
│ File: src/mqtt/handlers/sensor_handler.py                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: LibraryLoader → Sensor Processor                    │
│ Files: src/sensors/library_loader.py                        │
│        src/sensors/sensor_libraries/active/*.py             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: SensorService → Database                            │
│ Files: src/services/sensor_service.py                       │
│        src/db/repositories/sensor_repo.py                   │
└─────────────────────────────────────────────────────────────┘
```

**Abhängigkeiten:**
- `sensor_handler.py` MUSS `Mqtt_Protocoll.md` Line 84-100 implementieren
- `library_loader.py` MUSS sensor_types aus `El Trabajante/src/models/sensor_types.h` kennen
- Sensor Processors MÜSSEN `raw_value` aus ESP32 verarbeiten können
- `SensorRepository.get_stats` nutzt DB-Aggregation (min/max/avg/stddev, Qualitätsverteilung) – große Zeiträume erfordern keine RAM-Last mehr

### Actuator Control Layer

```
┌─────────────────────────────────────────────────────────────┐
│ Server: ActuatorService                                     │
│ File: src/services/actuator_service.py                      │
└─────────────────────────────────────────────────────────────┘
                          ↓ (MQTT Publish)
            kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ ESP32: ActuatorManager                                      │
│ File: El Trabajante/src/services/actuator/actuator_manager.cpp │
└─────────────────────────────────────────────────────────────┘
                          ↓ (Safety Check)
┌─────────────────────────────────────────────────────────────┐
│ ESP32: SafetyController                                     │
│ File: El Trabajante/src/services/actuator/safety_controller.cpp │
└─────────────────────────────────────────────────────────────┘
                          ↓ (MQTT Publish Response)
            kaiser/god/esp/{esp_id}/actuator/{gpio}/response
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: ActuatorHandler                                     │
│ File: src/mqtt/handlers/actuator_handler.py                 │
└─────────────────────────────────────────────────────────────┘
```

**Abhängigkeiten:**
- `actuator_service.py` MUSS `Mqtt_Protocoll.md` Line 143-161 implementieren
- Server MUSS Safety-Constraints respektieren (Emergency Stop, Timeout)
- `actuator_handler.py` MUSS Response-Payloads parsen können
- MQTT Subscriber-Threadpool ist konfigurierbar (`MQTT_SUBSCRIBER_MAX_WORKERS`), sollte bei Lastanpassungen berücksichtigt werden

### ESP Management Layer

```
┌─────────────────────────────────────────────────────────────┐
│ ESP32: Boot Sequence                                        │
│ Flow: El Trabajante/docs/system-flows/01-boot-sequence.md  │
└─────────────────────────────────────────────────────────────┘
                          ↓ (MQTT Publish Heartbeat)
              kaiser/god/esp/{esp_id}/system/heartbeat
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: HeartbeatHandler                                    │
│ File: src/mqtt/handlers/heartbeat_handler.py                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Server: ESPService → ESP Registration                       │
│ Files: src/services/esp_service.py                          │
│        src/db/repositories/esp_repo.py                      │
└─────────────────────────────────────────────────────────────┘
```

**Abhängigkeiten:**
- `heartbeat_handler.py` MUSS Heartbeat-Payload aus `Mqtt_Protocoll.md` Line 316-335 parsen
- `esp_service.py` MUSS ESP-Capabilities verstehen (MAX_SENSORS, MAX_ACTUATORS)
- Timeout/Online-Erkennung folgt `HEARTBEAT_TIMEOUT` und prüft `last_seen`; keine Auto-Registration aktiv (Registration required)

---

## 🔄 Cross-System Workflows

### Workflow 1: Sensor Reading & Processing

**ESP32 Side (El Trabajante):**
1. `SensorManager::performAllMeasurements()` (sensor_manager.cpp:360-384)
2. Read RAW value via I2C/OneWire/Analog GPIO
3. Publish to `kaiser/god/esp/{esp_id}/sensor/{gpio}/data`
4. Payload: `{ "raw": 2048, "sensor_type": "ph_sensor", ... }`

**Server Side (El Servador):**
1. `sensor_handler.py::handle_sensor_data()` empfängt Payload
2. `library_loader.py` lädt passende Sensor-Library
3. `ph_sensor.py::process()` konvertiert RAW → pH-Wert
4. `sensor_service.py` speichert in Database
5. `logic_engine.py` evaluiert Automation-Rules

**Kritische Abhängigkeiten:**
- Topic-Pattern MUSS übereinstimmen
- Payload-Schema MUSS synchron sein
- `sensor_type` MUSS in Server-Library existieren

### Workflow 2: Actuator Command & Response

**Server Side (El Servador):**
1. User/API sendet Actuator-Command
2. `actuator_service.py::send_command()` validiert
3. Publish to `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`
4. Payload: `{ "command": "ON", "value": 1.0, ... }`

**ESP32 Side (El Trabajante):**
1. `MQTTClient::onMessage()` empfängt Command
2. `ActuatorManager::handleCommand()` validiert
3. `SafetyController::checkConstraints()` prüft Safety
4. `IActuatorDriver::setValue()` steuert Hardware
5. Publish Response to `kaiser/god/esp/{esp_id}/actuator/{gpio}/response`

**Server Side (El Servador):**
6. `actuator_handler.py::handle_actuator_response()` empfängt Response
7. `actuator_service.py` aktualisiert Status in Database

**Kritische Abhängigkeiten:**
- Command-Payload MUSS ESP32-Format folgen
- Server MUSS Emergency-Stop respektieren
- Timeout-Handling auf beiden Seiten

---

## ⚠️ Breaking Change Prevention

### MQTT Protocol Changes

**Regel:** Wenn ESP32 Topic/Payload ändert → Server MUSS synchron geändert werden!

**Beispiel:**
```cpp
// ESP32: El Trabajante/src/services/sensor/sensor_manager.cpp
// VORHER:
payload["raw_value"] = raw;  // ← Field-Name geändert

// NACHHER:
payload["raw"] = raw;  // ← Neuer Field-Name

// Server MUSS auch ändern:
# src/mqtt/handlers/sensor_handler.py
raw_value = payload.get("raw")  # ← Anpassen!
```

**Checklist vor MQTT-Änderung:**
- [ ] `El Trabajante/docs/Mqtt_Protocoll.md` aktualisiert?
- [ ] Server-Handler angepasst?
- [ ] Pydantic Schemas aktualisiert?
- [ ] Tests für neue Payload-Struktur?

### Sensor Type Changes

**Regel:** Neuer Sensor-Typ auf ESP32 → Server-Library erstellen!

**Workflow:**
1. ESP32 sendet: `{ "sensor_type": "co2_sensor", "raw": 400 }`
2. Server MUSS haben: `src/sensors/sensor_libraries/active/co2_sensor.py`
3. Processor MUSS implementieren: `process(raw_value) → { "value": 400, "unit": "ppm" }`

**Wenn Library fehlt:**
- Server kann RAW-Werte nicht verarbeiten
- Daten werden als "unknown" markiert
- Frontend zeigt keine sinnvollen Werte

### Actuator Type Changes

**Regel:** Neuer Actuator-Typ auf ESP32 → Server MUSS Type erkennen!

**Workflow:**
1. ESP32 registriert: `{ "actuator_type": "heater", "gpio": 5 }`
2. Server speichert in Database: `actuator_configs` Tabelle
3. Server sendet Commands: MUSS `heater`-spezifische Constraints kennen

---

## 📊 Dependency Matrix

| Server-Modul | ESP32-Datei | Dependency-Type | Impact |
|--------------|-------------|-----------------|--------|
| `src/mqtt/subscriber.py` | `El Trabajante/docs/Mqtt_Protocoll.md` | MQTT Topics | CRITICAL |
| `src/mqtt/handlers/sensor_handler.py` | `El Trabajante/docs/Mqtt_Protocoll.md` (Line 84-100) | Payload Schema | CRITICAL |
| `src/mqtt/handlers/actuator_handler.py` | `El Trabajante/docs/Mqtt_Protocoll.md` (Line 143-161) | Payload Schema | CRITICAL |
| `src/sensors/library_loader.py` | `El Trabajante/src/models/sensor_types.h` | Sensor Types | HIGH |
| `src/schemas/sensor.py` | `El Trabajante/src/models/sensor_types.h` | Data Models | HIGH |
| `src/schemas/actuator.py` | `El Trabajante/src/models/actuator_types.h` | Data Models | HIGH |
| `src/services/zone_service.py` | `El Trabajante/docs/Dynamic Zones and Provisioning/` | Zone Hierarchy | MEDIUM |
| `src/services/esp_service.py` | `El Trabajante/docs/system-flows/01-boot-sequence.md` | ESP Discovery | MEDIUM |

---

## 🛠️ Server Development Best Practices

### 1. Before Changing MQTT Handlers

```bash
# Check ESP32 MQTT Protocol
cat "El Trabajante/docs/Mqtt_Protocoll.md"

# Check System Flows
cat "El Trabajante/docs/system-flows/02-sensor-reading-flow.md"
cat "El Trabajante/docs/system-flows/03-actuator-command-flow.md"
```

### 2. Before Adding Sensor Library

```bash
# Check existing sensor types
cat "El Trabajante/src/models/sensor_types.h"

# Check MQTT Payload format
cat "El Trabajante/docs/Mqtt_Protocoll.md" | grep -A 20 "Sensor Data"
```

### 3. Before Changing Schemas

```bash
# Compare Pydantic Schema with C++ Struct
# ESP32:
cat "El Trabajante/src/models/sensor_types.h"

# Server:
cat "El Servador/god_kaiser_server/src/schemas/sensor.py"

# MUST match!
```

---

## 📚 Related Documentation

### Server-Specific

- **Server Reference:** `.claude/CLAUDE_SERVER.md` - Vollständige Server-Dokumentation
- **ESP32 Testing:** `El Servador/docs/ESP32_TESTING.md` - Server-orchestrierte Tests
- **MQTT Test Protocol:** `El Servador/docs/MQTT_TEST_PROTOCOL.md` - Test-Commands

### ESP32-Specific (KRITISCH FÜR SERVER!)

- **MQTT Protocol:** `El Trabajante/docs/Mqtt_Protocoll.md` - **PFLICHTLEKTÜRE**
- **System Flows:** `El Trabajante/docs/system-flows/` - ESP32 Behavior
- **Sensor Types:** `El Trabajante/src/models/sensor_types.h` - C++ Structs
- **Actuator Types:** `El Trabajante/src/models/actuator_types.h` - C++ Structs
- **Error Codes:** `El Trabajante/src/models/error_codes.h` - Error-Definitionen

### Integration

- **Workflow Patterns:** `.claude/WORKFLOW_PATTERNS.md` - Code-Patterns
- **Test Workflow:** `.claude/TEST_WORKFLOW.md` - Test-Strategie

---

**Letzte Aktualisierung:** 2025-01
**Version:** 1.0 (Server-ESP32-Integration)
