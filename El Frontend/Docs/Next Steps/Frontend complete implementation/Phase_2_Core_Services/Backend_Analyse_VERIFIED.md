# Phase 2 Core Services - Vollständige Backend-Analyse (VERIFIED)

**Analysedatum:** 2026-01-29
**Analyst:** Claude Opus 4.5
**Verifikationsdatum:** 2026-01-29
**Reviewer:** Claude Opus 4.5 (Second Review)
**Scope:** ESP32 Firmware + God-Kaiser Server (Core Services)

---

## 1. Executive Summary

### Haupterkenntnisse

Die Phase 2 Core Services bilden das Herzstück des AutomationOne IoT-Frameworks. Das System folgt einem **Server-Centric Design**, bei dem der ESP32 als "dummer Agent" fungiert und alle Intelligenz (Verarbeitung, Logik, Entscheidungen) auf dem Server liegt.

**Kritische Abhängigkeiten:**

```
ESP32 SensorManager
    ↓ MQTT (QoS 1)
Server sensor_handler
    ↓ Pi-Enhanced Processing
Server sensor_service
    ↓ PostgreSQL
sensor_data (Time-Series)
    ↓ WebSocket
Frontend Live-Updates
```

```
Frontend Command
    ↓ REST API
Server actuator_service
    ↓ safety_service.validate()
Server Publisher
    ↓ MQTT (QoS 2)
ESP32 ActuatorManager
    ↓ GPIO/PWM
Physical Actuator
```

### Architektur-Prinzipien

1. **Server-Centric Processing:** ESP32 sendet RAW-Daten, Server verarbeitet
2. **Safety-First:** Jeder Aktor-Befehl durchläuft SafetyService-Validierung
3. **Singleton-Pattern:** Alle Manager sind Singletons (ESP32 + Server)
4. **Resilient Design:** Circuit-Breaker, Retry-Logic, Timeout-Protection

---

## 2. ESP32 Module

### 2.1 SensorManager

**Dateien:**
- Header: [sensor_manager.h](El%20Trabajante/src/services/sensor/sensor_manager.h)
- Implementation: [sensor_manager.cpp](El%20Trabajante/src/services/sensor/sensor_manager.cpp) (1317 Zeilen)
<!-- VERIFIZIERT: Zeilenzahl korrekt (wc -l bestätigt 1317) -->

**Kritische Code-Stellen:**
| Zeile | Methode | Funktion |
|-------|---------|----------|
| 58-94 | `begin()` | Initialisierung, PiEnhancedProcessor-Setup |
| 157-465 | `configureSensor()` | Sensor-Konfiguration, GPIO/I2C/OneWire-Handling |
| 555-866 | `performMeasurement()` | Einzelmessung mit Retry-Logik |
| 987-1059 | `performAllMeasurements()` | Autonomer Messzyklus (pro Sensor-Intervall) |
| 1228-1246 | `publishSensorReading()` | MQTT-Publishing |
| 1248-1316 | `buildMQTTPayload()` | Payload-Konstruktion |
<!-- KORRIGIERT: begin() endet bei Zeile 94, nicht 93 -->
<!-- VERIFIZIERT: Alle anderen Zeilennummern exakt korrekt -->

**Lifecycle:**

```
1. begin()
   ├── PiEnhancedProcessor.begin()
   ├── Reset sensor registry
   └── Initialize component references

2. configureSensor(config)
   ├── Validate GPIO (255 = invalid)
   ├── Determine interface type (I2C/OneWire/GPIO)
   ├── Check GPIO conflicts
   │   ├── I2C: No GPIO reservation (bus managed)
   │   ├── OneWire: Shared bus with ROM-Code validation
   │   └── GPIO: requestPin() with owner tracking
   ├── Add to sensors_[] array
   └── Persist to NVS via configManager

3. performMeasurement(gpio) / performAllMeasurements()
   ├── Find sensor config
   ├── Read RAW value based on interface type
   │   ├── I2C: readRawI2C()
   │   ├── OneWire: readRawOneWire() with retry (3 attempts)
   │   └── Analog: readRawAnalog() (analogRead)
   ├── DS18B20 special handling:
   │   ├── -127°C detection (sensor fault)
   │   ├── 85°C power-on-reset detection
   │   └── Range validation (-55°C to +125°C)
   ├── Send to PiEnhancedProcessor
   └── Publish via MQTT

4. removeSensor(gpio)
   ├── Release GPIO (non-I2C only)
   ├── Remove from sensors_[] array
   └── Persist to NVS
```
<!-- VERIFIZIERT: Lifecycle-Flow stimmt mit Code überein -->

**MQTT-Payload-Schema (Sensor Data):**

```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "subzone_id": "subzone_1",
  "gpio": 34,
  "sensor_type": "ds18b20",
  "raw": 400,
  "value": 0.0,
  "unit": "",
  "quality": "good",
  "ts": 1735818000,
  "raw_mode": true,
  "onewire_address": "28FF641E8D3C0C79"
}
```

**Required Fields:** `esp_id`, `gpio`, `sensor_type`, `raw` (oder `raw_value`), `ts` (oder `timestamp`), `raw_mode`

**Quality-System:**
- `good`: Wert innerhalb Datasheet-Grenzen
- `fair`: Leichte Abweichungen
- `poor`: Signifikante Abweichungen
- `suspect`: DS18B20 out-of-range
- `error`: Lesefehler, -127°C, 85°C (first read)
- `unknown`: Keine Validierung möglich

**Operating Modes:**
- `continuous`: Automatische Messung nach `measurement_interval_ms`
- `on_demand`: Nur bei explizitem Trigger (Phase 2C)
- `scheduled`: Server-getriggert (Phase 2D)
- `paused`: Keine Messungen

**Error-Codes (aus error_codes.h):**
| Code | Konstante | Beschreibung |
|------|-----------|--------------|
| 1040 | `ERROR_SENSOR_READ_FAILED` | Sensor-Lesefehler |
| 1041 | `ERROR_SENSOR_INIT_FAILED` | Initialisierungsfehler |
| 1042 | `ERROR_SENSOR_NOT_FOUND` | Sensor nicht konfiguriert |
| 1043 | `ERROR_SENSOR_TIMEOUT` | Timeout beim Lesen |
| 1060 | `ERROR_DS18B20_SENSOR_FAULT` | -127°C (Disconnect/CRC) |
| 1061 | `ERROR_DS18B20_POWER_ON_RESET` | 85°C beim ersten Lesen |
| 1062 | `ERROR_DS18B20_OUT_OF_RANGE` | Außerhalb gültigem Bereich |
| 1063 | `ERROR_DS18B20_DISCONNECTED_RUNTIME` | Device war present, jetzt weg |
| 1020-1029 | OneWire-Fehler | ROM-Code, Bus, Device |
<!-- ERGÄNZT: Error-Code 1063 fehlte in Erstanalyse -->
<!-- VERIFIZIERT: Alle Error-Codes gegen error_codes.h geprüft -->

**OneWire Error-Codes (Detail):**
| Code | Konstante | Beschreibung |
|------|-----------|--------------|
| 1020 | `ERROR_ONEWIRE_INIT_FAILED` | Bus-Initialisierung fehlgeschlagen |
| 1021 | `ERROR_ONEWIRE_NO_DEVICES` | Keine Geräte auf Bus gefunden |
| 1022 | `ERROR_ONEWIRE_READ_FAILED` | Lesefehler |
| 1023 | `ERROR_ONEWIRE_INVALID_ROM_LENGTH` | ROM-Code nicht 16 Zeichen |
| 1024 | `ERROR_ONEWIRE_INVALID_ROM_FORMAT` | ROM-Code enthält ungültige Zeichen |
| 1025 | `ERROR_ONEWIRE_INVALID_ROM_CRC` | ROM-Code CRC fehlgeschlagen |
| 1026 | `ERROR_ONEWIRE_DEVICE_NOT_FOUND` | Gerät nicht auf Bus gefunden |
| 1027 | `ERROR_ONEWIRE_BUS_NOT_INITIALIZED` | Bus nicht initialisiert |
| 1028 | `ERROR_ONEWIRE_READ_TIMEOUT` | Lese-Timeout |
| 1029 | `ERROR_ONEWIRE_DUPLICATE_ROM` | ROM-Code bereits registriert |
<!-- ERGÄNZT: Vollständige OneWire Error-Code-Liste hinzugefügt -->

**Abhängigkeiten:**
- `GPIOManager`: Pin-Reservation (non-I2C)
- `I2CBusManager`: I2C-Kommunikation
- `OneWireBusManager`: OneWire-Kommunikation
- `MQTTClient`: Publishing
- `PiEnhancedProcessor`: Server-Processing-Client
- `ConfigManager`: NVS-Persistierung
- `TimeManager`: NTP-Timestamps
- `ErrorTracker`: Error-Logging und -Tracking
<!-- ERGÄNZT: ErrorTracker fehlte in Abhängigkeitsliste -->

---

### 2.2 ActuatorManager

**Dateien:**
- Header: [actuator_manager.h](El%20Trabajante/src/services/actuator/actuator_manager.h)
- Implementation: [actuator_manager.cpp](El%20Trabajante/src/services/actuator/actuator_manager.cpp) (855 Zeilen)
<!-- VERIFIZIERT: Zeilenzahl korrekt -->

**Kritische Code-Stellen:**
| Zeile | Methode | Funktion |
|-------|---------|----------|
| 94-108 | `begin()` | Initialisierung |
| 184-284 | `configureActuator()` | Aktor-Konfiguration mit Driver-Factory |
| 338-380 | `controlActuator()` | PWM-Steuerung mit Safety-Checks |
| 382-409 | `controlActuatorBinary()` | Binary ON/OFF |
| 411-433 | `emergencyStopAll()` / `emergencyStopActuator()` | E-Stop |
| 478-517 | `processActuatorLoops()` | Timeout-Protection |
| 537-576 | `handleActuatorCommand()` | MQTT-Command-Parsing |
<!-- KORRIGIERT: controlActuator() endet bei 380, nicht 379 -->
<!-- VERIFIZIERT: Alle Zeilennummern gegen Code geprüft -->

**Lifecycle:**

```
1. begin()
   └── Initialize actuators_[] array

2. configureActuator(config)
   ├── Validate config (GPIO, type)
   ├── Check GPIO conflict with SensorManager
   ├── Handle reconfiguration (removeActuator first)
   ├── Create driver via createDriver(type)
   │   ├── "pump" → PumpActuator
   │   ├── "valve" → ValveActuator
   │   ├── "pwm" → PWMActuator
   │   └── "relay" → PumpActuator (binary)
   ├── driver->begin(config)
   ├── Add to actuators_[] array
   └── Persist to NVS

3. controlActuator(gpio, value) / controlActuatorBinary(gpio, state)
   ├── Find actuator
   ├── Check emergency_stopped flag
   ├── Validate value range (PWM: 0.0-1.0)
   ├── driver->setValue() / driver->setBinary()
   ├── Track activation timestamp (Runtime Protection)
   └── publishActuatorStatus()

4. processActuatorLoops() [called in main loop]
   ├── For each active actuator:
   │   ├── Check timeout_enabled && current_state
   │   ├── Calculate runtime = now - activation_start_ms
   │   ├── If runtime > max_runtime_ms:
   │   │   ├── emergencyStopActuator(gpio)
   │   │   └── publishActuatorAlert("runtime_protection")
   │   └── driver->loop()

5. handleActuatorCommand(topic, payload)
   ├── Extract GPIO from topic
   ├── Parse command (ON/OFF/PWM/TOGGLE)
   ├── Execute via controlActuatorBinary() / controlActuator()
   └── publishActuatorResponse()
```

**MQTT-Payload-Schema (Actuator Status):**

```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "subzone_id": "subzone_1",
  "ts": 1735818000,
  "gpio": 25,
  "type": "pump",
  "state": true,
  "pwm": 255,
  "runtime_ms": 3600000,
  "emergency": "normal"
}
```

**MQTT-Payload-Schema (Actuator Response):**

```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "ts": 1735818000,
  "gpio": 25,
  "command": "ON",
  "value": 1.0,
  "duration": 0,
  "success": true,
  "message": "Command executed",
  "correlation_id": "uuid-from-server"
}
```

**Aktor-Typen (aus actuator_types.h):**
| Token | Konstantenwert | Verhalten |
|-------|----------------|-----------|
| `pump` | "pump" | Binary ON/OFF |
| `valve` | "valve" | Binary ON/OFF |
| `pwm` | "pwm" | PWM 0.0-1.0 |
| `relay` | "relay" | Binary (wie pump) |
<!-- VERIFIZIERT: Aktor-Typen in createDriver() geprüft (Zeilen 167-182) -->

**RuntimeProtection-Struct:**
```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;  // 1h default
  bool timeout_enabled = true;
  unsigned long activation_start_ms = 0;
};
```

**EmergencyState-Enum:**
| Wert | Bedeutung |
|------|-----------|
| `EMERGENCY_NORMAL` | Normalbetrieb |
| `EMERGENCY_ACTIVE` | E-Stop aktiv |
| `EMERGENCY_CLEARING` | E-Stop wird aufgehoben |
| `EMERGENCY_RESUMING` | Wiederaufnahme läuft |

**Error-Codes:**
| Code | Konstante | Beschreibung |
|------|-----------|--------------|
| 1050 | `ERROR_ACTUATOR_SET_FAILED` | Setzen fehlgeschlagen |
| 1051 | `ERROR_ACTUATOR_INIT_FAILED` | Initialisierung fehlgeschlagen |
| 1052 | `ERROR_ACTUATOR_NOT_FOUND` | Aktor nicht konfiguriert |
| 1053 | `ERROR_ACTUATOR_CONFLICT` | GPIO-Konflikt mit Sensor |
<!-- VERIFIZIERT: Alle Error-Codes gegen error_codes.h geprüft -->

**Abhängigkeiten:**
- `GPIOManager`: Pin-Reservation
- `SensorManager`: GPIO-Konflikt-Check
- `MQTTClient`: Publishing
- `ConfigManager`: NVS-Persistierung
- `TimeManager`: NTP-Timestamps
- `IActuatorDriver`: Abstrakte Treiber-Schnittstelle
- `ErrorTracker`: Error-Logging
<!-- ERGÄNZT: ErrorTracker fehlte -->

---

### 2.3 SafetyController

**Dateien:**
- Header: [safety_controller.h](El%20Trabajante/src/services/actuator/safety_controller.h)
- Implementation: [safety_controller.cpp](El%20Trabajante/src/services/actuator/safety_controller.cpp) (176 Zeilen)
<!-- VERIFIZIERT: Zeilenzahl korrekt -->

**Kritische Code-Stellen:**
| Zeile | Methode | Funktion |
|-------|---------|----------|
| 40-51 | `emergencyStopAll()` | Fleet-weiter E-Stop |
| 53-64 | `emergencyStopActuator()` | Einzelner E-Stop |
| 66-86 | `isolateSubzone()` | Subzone-Isolation (Phase 9) |
| 88-101 | `clearEmergencyStop()` | E-Stop aufheben (mit Verifikation) |
| 147-156 | `verifySystemSafety()` | Systemprüfung vor Clear |
<!-- VERIFIZIERT: Alle Zeilennummern exakt korrekt -->

**Lifecycle:**

```
1. emergencyStopAll(reason)
   ├── Set emergency_state_ = EMERGENCY_ACTIVE
   ├── Store reason and timestamp
   ├── Call actuatorManager.emergencyStopAll()
   └── Log emergency event

2. emergencyStopActuator(gpio, reason)
   ├── Set emergency_state_ = EMERGENCY_ACTIVE
   ├── Store reason and timestamp
   ├── Call actuatorManager.emergencyStopActuator(gpio)
   └── Log emergency event

3. isolateSubzone(subzone_id, reason) [Phase 9]
   ├── Call gpioManager.enableSafeModeForSubzone()
   ├── Track error via errorTracker
   └── Log isolation event

4. clearEmergencyStop()
   ├── Set emergency_state_ = EMERGENCY_CLEARING
   ├── verifySystemSafety()
   │   ├── Check max_retry_attempts > 0
   │   └── Check verification_timeout_ms elapsed
   ├── Call actuatorManager.clearEmergencyStop()
   └── Set emergency_state_ = EMERGENCY_RESUMING

5. resumeOperation()
   ├── Wait inter_actuator_delay_ms
   ├── Set emergency_state_ = EMERGENCY_NORMAL
   └── Clear emergency_reason_
```

**RecoveryConfig-Struct:**
```cpp
struct RecoveryConfig {
  uint32_t inter_actuator_delay_ms = 2000;     // 2s zwischen Aktoren
  bool critical_first = true;                   // Kritische zuerst
  uint32_t verification_timeout_ms = 5000;      // 5s Verifikation
  uint8_t max_retry_attempts = 3;               // Max 3 Versuche
};
```

**Abhängigkeiten:**
- `ActuatorManager`: E-Stop-Ausführung
- `GPIOManager`: Subzone-Isolation (Phase 9)
- `ErrorTracker`: Error-Logging

**Bestätigte Methode:** `gpioManager.enableSafeModeForSubzone(subzone_id)` existiert und wird in `isolateSubzone()` aufgerufen (Zeile 71).
<!-- ERGÄNZT: Bestätigung dass isolateSubzone gpioManager korrekt nutzt -->

---

## 3. Server Module

### 3.1 MQTT Handler

#### 3.1.1 SensorDataHandler

**Datei:** [sensor_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/sensor_handler.py) (697 Zeilen)
<!-- KORRIGIERT: War 698, tatsächlich 697 Zeilen -->

**Topic:** `kaiser/god/esp/+/sensor/+/data` (QoS 1)

**Kritische Code-Stellen:**
| Zeile | Methode | Funktion |
|-------|---------|----------|
| 79-351 | `handle_sensor_data()` | Hauptverarbeitung |
| 353-482 | `_validate_payload()` | Payload-Validierung |
| 565-665 | `_trigger_pi_enhanced_processing()` | Pi-Enhanced auslösen |

**Verarbeitungs-Flow:**

```
1. Parse topic → extract esp_id, gpio
2. Validate payload
   ├── Required: ts/timestamp, esp_id, gpio, sensor_type, raw/raw_value, raw_mode
   ├── Type validation (int, bool, numeric)
   └── Quality validation (good/fair/poor/suspect/error/unknown)
3. Database lookup (resilient_session)
   ├── Get ESP device by device_id
   ├── Get sensor config (3-way: esp_id, gpio, sensor_type)
   └── OneWire: 4-way lookup (+onewire_address)
4. Determine processing mode
   ├── raw_mode=true && pi_enhanced=true → Pi-Enhanced
   └── raw_mode=false → Local processing
5. Pi-Enhanced Processing (if enabled)
   ├── Load processor via library_loader
   ├── Process raw value → processed_value, unit, quality
   └── Publish response to ESP
6. Save to database (sensor_data table)
7. WebSocket broadcast ("sensor_data")
8. Logic Engine trigger (non-blocking asyncio.create_task)
```

**Required Payload Fields:**
| Field | Type | Beschreibung |
|-------|------|--------------|
| `ts` / `timestamp` | int | Unix timestamp (Sekunden) |
| `esp_id` | string | ESP Device ID |
| `gpio` | int | GPIO Pin |
| `sensor_type` | string | Sensor-Typ |
| `raw` / `raw_value` | numeric | RAW-Wert |
| `raw_mode` | bool | true = Server verarbeitet |

**Optional Fields:**
| Field | Type | Beschreibung |
|-------|------|--------------|
| `value` | float | Bereits verarbeiteter Wert |
| `unit` | string | Einheit |
| `quality` | string | Qualitätsindikator |
| `onewire_address` | string | OneWire ROM-Code (16 hex) |
| `error_code` | int | ESP32 Error-Code |

#### 3.1.2 ActuatorStatusHandler

**Datei:** [actuator_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_handler.py) (457 Zeilen)
<!-- KORRIGIERT: War 458, tatsächlich 457 Zeilen -->

**Topic:** `kaiser/god/esp/+/actuator/+/status` (QoS 1)

**Verarbeitungs-Flow:**

```
1. Parse topic → extract esp_id, gpio
2. Validate payload
   ├── Required: ts, esp_id, gpio, actuator_type/type, state, value/pwm
   └── State: boolean true/false OR string on/off/pwm/error/unknown
3. Database lookup
   ├── Get ESP device
   └── Get actuator config
4. Update actuator state (actuator_states table)
5. Log to history (actuator_history table)
6. Audit log with correlation_id (if present)
7. WebSocket broadcast ("actuator_status")
```

#### 3.1.3 ActuatorResponseHandler

**Datei:** [actuator_response_handler.py](El%20Servador/god_kaiser_server/src/mqtt/handlers/actuator_response_handler.py) (279 Zeilen)
<!-- KORRIGIERT: War 280, tatsächlich 279 Zeilen -->

**Topic:** `kaiser/god/esp/+/actuator/+/response` (QoS 1)

**Verarbeitungs-Flow:**

```
1. Validate payload (ts, esp_id, gpio, command, success)
2. Convert timestamp (auto-detect ms vs s)
3. Lookup ESP device
4. Log command response to history
5. Audit log with correlation_id
6. WebSocket broadcast ("actuator_response")
```

#### 3.1.4 Weitere Handler (ergänzt)
<!-- ERGÄNZT: Fehlende Handler dokumentiert -->

| Handler | Datei | Topic | Beschreibung |
|---------|-------|-------|--------------|
| `ActuatorAlertHandler` | `actuator_alert_handler.py` | `.../actuator/+/alert`, `.../actuator/emergency` | Emergency/Timeout Alerts |
| `HeartbeatHandler` | `heartbeat_handler.py` | `.../system/heartbeat` | ESP Health Monitoring |
| `ConfigHandler` | `config_handler.py` | `.../config_response` | Config Acknowledgment |
| `ZoneAckHandler` | `zone_ack_handler.py` | `.../zone/ack` | Zone Assignment ACK |
| `SubzoneAckHandler` | `subzone_ack_handler.py` | `.../subzone/ack` | Subzone Assignment ACK |
| `LWTHandler` | `lwt_handler.py` | Last Will Testament | ESP Disconnect Detection |
| `ErrorHandler` | `error_handler.py` | `.../system/error` | System Error Messages |
| `DiscoveryHandler` | `discovery_handler.py` | (deprecated) | Legacy Discovery |

---

### 3.2 Services

#### 3.2.1 SensorService

**Datei:** [sensor_service.py](El%20Servador/god_kaiser_server/src/services/sensor_service.py) (545 Zeilen)
<!-- KORRIGIERT: War 546, tatsächlich 545 Zeilen -->

**Methoden:**

| Methode | Signatur | Beschreibung |
|---------|----------|--------------|
| `get_config` | `(esp_id, gpio) → SensorConfig?` | Sensor-Config abrufen |
| `create_or_update_config` | `(esp_id, gpio, type, ...)` | Config erstellen/aktualisieren |
| `delete_config` | `(esp_id, gpio) → bool` | Config löschen |
| `process_reading` | `(esp_id, gpio, type, raw, ...)` | Pi-Enhanced Processing |
| `query_data` | `(filters...) → List[SensorData]` | Daten abfragen |
| `get_latest_reading` | `(esp_id, gpio) → SensorData?` | Letzten Wert abrufen |
| `get_stats` | `(esp_id, gpio, time_range)` | Statistiken |
| `calibrate` | `(esp_id, gpio, points, method)` | Kalibrierung berechnen |
| `trigger_measurement` | `(esp_id, gpio)` | On-Demand Messung (Phase 2D) |

#### 3.2.2 ActuatorService

**Datei:** [actuator_service.py](El%20Servador/god_kaiser_server/src/services/actuator_service.py) (279 Zeilen)
<!-- KORRIGIERT: War 280, tatsächlich 279 Zeilen -->

**Methoden:**

| Methode | Signatur | Beschreibung |
|---------|----------|--------------|
| `send_command` | `(esp_id, gpio, command, value, duration, issued_by)` | Befehl senden |

**send_command Flow:**

```
1. Generate correlation_id (UUID)
2. Safety validation via SafetyService.validate_actuator_command()
   ├── Check emergency stop
   ├── Check value range (0.0-1.0)
   └── Check actuator config (exists, enabled)
3. If safety check fails:
   ├── Log failed command
   ├── Audit log
   └── WebSocket broadcast ("actuator_command_failed")
4. Publish MQTT command via Publisher
5. Log successful command
6. Audit log with correlation_id
7. WebSocket broadcast ("actuator_command")
```

#### 3.2.3 SafetyService

**Datei:** [safety_service.py](El%20Servador/god_kaiser_server/src/services/safety_service.py) (264 Zeilen)
<!-- KORRIGIERT: War 265, tatsächlich 264 Zeilen -->

**Methoden:**

| Methode | Signatur | Beschreibung |
|---------|----------|--------------|
| `validate_actuator_command` | `(esp_id, gpio, command, value)` | Command validieren |
| `check_safety_constraints` | `(esp_id, gpio, value)` | Constraints prüfen |
| `emergency_stop_all` | `()` | Fleet-weiter E-Stop |
| `emergency_stop_esp` | `(esp_id)` | ESP-spezifischer E-Stop |
| `clear_emergency_stop` | `(esp_id?)` | E-Stop aufheben |
| `is_emergency_stop_active` | `(esp_id?)` | Status abfragen |

**validate_actuator_command Checks:**

1. **Emergency Stop Check:** `__ALL__` oder ESP-spezifisch aktiv?
2. **Value Range:** 0.0 ≤ value ≤ 1.0 (KRITISCH: PWM-Werte nicht 0-255!)
3. **Actuator Config:** Existiert, enabled, min/max_value
4. **Timeout Constraints:** Warnung wenn bereits aktiv
5. **GPIO Conflicts:** Warnung bei mehreren Aktoren auf gleichem GPIO

**SafetyCheckResult:**
```python
@dataclass
class SafetyCheckResult:
    valid: bool                      # Command erlaubt?
    error: Optional[str] = None      # Fehlergrund
    warnings: Optional[list[str]] = None  # Warnungen
```

---

### 3.3 MQTT Publisher

**Datei:** [publisher.py](El%20Servador/god_kaiser_server/src/mqtt/publisher.py) (441 Zeilen)
<!-- KORRIGIERT: War 442, tatsächlich 441 Zeilen -->

**Methoden:**

| Methode | Topic | QoS | Beschreibung |
|---------|-------|-----|--------------|
| `publish_actuator_command` | `kaiser/god/esp/{esp_id}/actuator/{gpio}/command` | 2 | Aktor-Befehl |
| `publish_sensor_command` | `kaiser/god/esp/{esp_id}/sensor/{gpio}/command` | 1 | Sensor-Befehl |
| `publish_sensor_config` | `kaiser/god/esp/{esp_id}/config/sensor/{gpio}` | 2 | Sensor-Config |
| `publish_actuator_config` | `kaiser/god/esp/{esp_id}/config/actuator/{gpio}` | 2 | Aktor-Config |
| `publish_config` | `kaiser/god/esp/{esp_id}/config` | 2 | Combined Config |
| `publish_system_command` | `kaiser/god/esp/{esp_id}/system/command` | 2 | System-Befehl |
| `publish_pi_enhanced_response` | `kaiser/god/esp/{esp_id}/sensor/{gpio}/processed` | 1 | Pi-Enhanced Result |

**Retry-Logic:**
- Exponential Backoff mit konfigurierbaren Parametern
- Circuit-Breaker via MQTTClient
- Jitter zur Vermeidung von Thundering Herd

---

## 4. Datenbank-Schema

### 4.1 Sensor-Tabellen

#### sensor_configs

```sql
CREATE TABLE sensor_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    esp_id UUID NOT NULL REFERENCES esp_devices(id) ON DELETE CASCADE,
    gpio INTEGER,                    -- nullable for I2C/OneWire
    sensor_type VARCHAR(50) NOT NULL,
    sensor_name VARCHAR(100) NOT NULL,
    interface_type VARCHAR(20) DEFAULT 'ANALOG',  -- I2C, ONEWIRE, ANALOG, DIGITAL
    i2c_address INTEGER,             -- for I2C sensors (e.g., 0x44)
    onewire_address VARCHAR(16),     -- for OneWire sensors (ROM-Code)
    provides_values JSON,            -- multi-value sensor types
    enabled BOOLEAN DEFAULT TRUE,
    pi_enhanced BOOLEAN DEFAULT TRUE,
    sample_interval_ms INTEGER DEFAULT 1000,
    calibration_data JSON,
    thresholds JSON,
    sensor_metadata JSON DEFAULT '{}',
    -- Operating Mode (Phase 2A)
    operating_mode VARCHAR(20),      -- continuous, on_demand, scheduled, paused
    timeout_seconds INTEGER,
    timeout_warning_enabled BOOLEAN,
    schedule_config JSON,
    last_manual_request TIMESTAMP,
    -- Config Status (Phase 4)
    config_status VARCHAR(20) DEFAULT 'pending',
    config_error VARCHAR(50),
    config_error_detail VARCHAR(200),
    -- Timestamps (via TimestampMixin)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Constraints
    CONSTRAINT unique_esp_gpio_sensor_type_onewire
        UNIQUE (esp_id, gpio, sensor_type, onewire_address)
);

-- Indices
CREATE INDEX idx_sensor_type_enabled ON sensor_configs(sensor_type, enabled);
CREATE INDEX idx_i2c_address ON sensor_configs(i2c_address);
```
<!-- ERGÄNZT: created_at, updated_at via TimestampMixin hinzugefügt -->
<!-- VERIFIZIERT: Schema gegen SQLAlchemy Model geprüft -->

#### sensor_data

```sql
CREATE TABLE sensor_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    esp_id UUID NOT NULL REFERENCES esp_devices(id) ON DELETE CASCADE,
    gpio INTEGER NOT NULL,
    sensor_type VARCHAR(50) NOT NULL,
    raw_value FLOAT NOT NULL,
    processed_value FLOAT,
    unit VARCHAR(20),
    processing_mode VARCHAR(20) NOT NULL,  -- pi_enhanced, local, raw
    quality VARCHAR(20),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    sensor_metadata JSON,
    data_source VARCHAR(20) DEFAULT 'production'  -- production, mock, test, simulation
);

-- Indices (Time-Series Optimized)
CREATE INDEX idx_esp_gpio_timestamp ON sensor_data(esp_id, gpio, timestamp);
CREATE INDEX idx_sensor_type_timestamp ON sensor_data(sensor_type, timestamp);
CREATE INDEX idx_timestamp_desc ON sensor_data(timestamp DESC);
CREATE INDEX idx_data_source_timestamp ON sensor_data(data_source, timestamp);
```

### 4.2 Actuator-Tabellen

#### actuator_configs

```sql
CREATE TABLE actuator_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    esp_id UUID NOT NULL REFERENCES esp_devices(id) ON DELETE CASCADE,
    gpio INTEGER NOT NULL,
    actuator_type VARCHAR(50) NOT NULL,
    actuator_name VARCHAR(100) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    min_value FLOAT DEFAULT 0.0,
    max_value FLOAT DEFAULT 1.0,
    default_value FLOAT DEFAULT 0.0,
    timeout_seconds INTEGER,
    safety_constraints JSON,
    actuator_metadata JSON DEFAULT '{}',
    -- Config Status
    config_status VARCHAR(20) DEFAULT 'pending',
    config_error VARCHAR(50),
    config_error_detail VARCHAR(200),
    -- Timestamps (via TimestampMixin)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    -- Constraints
    CONSTRAINT unique_esp_gpio_actuator UNIQUE (esp_id, gpio)
);

CREATE INDEX idx_actuator_type_enabled ON actuator_configs(actuator_type, enabled);
```
<!-- ERGÄNZT: created_at, updated_at via TimestampMixin hinzugefügt -->

#### actuator_states

```sql
CREATE TABLE actuator_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    esp_id UUID NOT NULL REFERENCES esp_devices(id) ON DELETE CASCADE,
    gpio INTEGER NOT NULL,
    actuator_type VARCHAR(50) NOT NULL,
    current_value FLOAT NOT NULL,
    target_value FLOAT,
    state VARCHAR(20) NOT NULL,      -- idle, active, error, emergency_stop
    last_command_timestamp TIMESTAMP,
    runtime_seconds INTEGER DEFAULT 0,
    last_command VARCHAR(50),
    error_message VARCHAR(500),
    state_metadata JSON,
    data_source VARCHAR(20) DEFAULT 'production'
);

CREATE INDEX idx_esp_gpio_state ON actuator_states(esp_id, gpio);
CREATE INDEX idx_actuator_state ON actuator_states(state);
CREATE INDEX idx_esp_state ON actuator_states(esp_id, state);
```

#### actuator_history

```sql
CREATE TABLE actuator_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    esp_id UUID NOT NULL REFERENCES esp_devices(id) ON DELETE CASCADE,
    gpio INTEGER NOT NULL,
    actuator_type VARCHAR(50) NOT NULL,
    command_type VARCHAR(50) NOT NULL,
    value FLOAT,
    issued_by VARCHAR(100),          -- user:123, logic:456, system, esp32_response
    success BOOLEAN NOT NULL,
    error_message VARCHAR(500),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    command_metadata JSON,
    data_source VARCHAR(20) DEFAULT 'production'
);

-- Indices (Time-Series Optimized)
CREATE INDEX idx_esp_gpio_timestamp_hist ON actuator_history(esp_id, gpio, timestamp);
CREATE INDEX idx_command_type_timestamp ON actuator_history(command_type, timestamp);
CREATE INDEX idx_timestamp_desc_hist ON actuator_history(timestamp DESC);
CREATE INDEX idx_success_timestamp ON actuator_history(success, timestamp);
CREATE INDEX idx_actuator_data_source_timestamp ON actuator_history(data_source, timestamp);
```

---

## 5. Kommunikations-Diagramme

### 5.1 Sensor-Datenfluss

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ESP32: SensorManager                                                    │
│                                                                         │
│ performAllMeasurements()                                                │
│    └── for each sensor (continuous mode, interval elapsed):            │
│         ├── performMeasurement(gpio)                                   │
│         │    ├── readRawOneWire() / readRawI2C() / readRawAnalog()    │
│         │    ├── DS18B20: Retry 3x, -127°C/85°C detection             │
│         │    └── PiEnhancedProcessor.sendRawData()                    │
│         ├── buildMQTTPayload()                                         │
│         │    ├── esp_id, zone_id, subzone_id                          │
│         │    ├── gpio, sensor_type, raw, raw_mode=true                │
│         │    ├── quality, ts (NTP), onewire_address                   │
│         │    └── JSON String                                           │
│         └── MQTTClient.publish(topic, payload, QoS=1)                  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ MQTT Topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Server: sensor_handler.handle_sensor_data()                            │
│                                                                         │
│ 1. TopicBuilder.parse_sensor_data_topic(topic)                         │
│    └── Extract esp_id, gpio                                            │
│                                                                         │
│ 2. _validate_payload(payload)                                          │
│    ├── Check required: ts, esp_id, gpio, sensor_type, raw, raw_mode   │
│    ├── Type validation                                                 │
│    └── Quality validation                                              │
│                                                                         │
│ 3. Database Lookup (resilient_session with circuit breaker)            │
│    ├── ESPRepository.get_by_device_id(esp_id)                         │
│    └── SensorRepository.get_by_esp_gpio_and_type()                    │
│        └── OneWire: get_by_esp_gpio_type_and_onewire()                │
│                                                                         │
│ 4. Pi-Enhanced Processing (if pi_enhanced=true && raw_mode=true)       │
│    ├── library_loader.get_processor(sensor_type)                      │
│    ├── processor.process(raw_value, calibration, params)              │
│    └── Returns: {processed_value, unit, quality}                      │
│                                                                         │
│ 5. SensorRepository.save_data()                                        │
│    └── INSERT INTO sensor_data (...)                                  │
│                                                                         │
│ 6. session.commit()                                                    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ├──────────────────────────────────────────┐
                             │                                          │
                             ▼                                          ▼
┌────────────────────────────────────────┐    ┌───────────────────────────────┐
│ WebSocket Broadcast                     │    │ Logic Engine Trigger          │
│                                         │    │                               │
│ ws_manager.broadcast("sensor_data", {   │    │ asyncio.create_task(          │
│   esp_id, message, gpio, sensor_type,   │    │   logic_engine.evaluate(      │
│   value, unit, quality, timestamp       │    │     esp_id, gpio, value       │
│ })                                      │    │   )                           │
│                                         │    │ )                             │
│ → Frontend erhält Live-Update          │    │ → Non-blocking Evaluation     │
└────────────────────────────────────────┘    └───────────────────────────────┘
```
<!-- VERIFIZIERT: Flow stimmt mit Code überein -->

### 5.2 Aktor-Command-Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Frontend: User klickt "Pump ON"                                         │
│                                                                         │
│ POST /api/v1/actuators/{esp_id}/{gpio}/command                         │
│ Body: { "command": "ON", "value": 1.0 }                                │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Server: actuator_service.send_command()                                │
│                                                                         │
│ 1. Generate correlation_id (UUID)                                      │
│                                                                         │
│ 2. SafetyService.validate_actuator_command(esp_id, gpio, cmd, value)   │
│    ├── Check emergency_stop_active (global + ESP-specific)            │
│    ├── Validate value range (0.0 ≤ value ≤ 1.0)                       │
│    └── check_safety_constraints()                                      │
│         ├── ESP device exists?                                         │
│         ├── Actuator config exists & enabled?                         │
│         ├── Value in min/max range?                                    │
│         └── Timeout warning if already active                          │
│                                                                         │
│ 3. If valid=false:                                                     │
│    ├── Log to actuator_history (success=false)                        │
│    ├── Audit log with correlation_id                                  │
│    ├── WebSocket: "actuator_command_failed"                           │
│    └── Return false                                                    │
│                                                                         │
│ 4. Publisher.publish_actuator_command()                                │
│    ├── Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/command         │
│    ├── Payload: {command, value, duration, timestamp, correlation_id} │
│    └── QoS: 2 (Exactly Once)                                          │
│                                                                         │
│ 5. Log to actuator_history (success=true)                              │
│ 6. Audit log with correlation_id                                       │
│ 7. WebSocket: "actuator_command"                                       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ MQTT Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/command
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ESP32: ActuatorManager.handleActuatorCommand()                         │
│                                                                         │
│ 1. extractGPIOFromTopic(topic)                                         │
│ 2. Parse command: ON, OFF, PWM, TOGGLE                                 │
│ 3. Extract value, duration, correlation_id                             │
│                                                                         │
│ 4. Execute:                                                            │
│    ├── "ON"  → controlActuatorBinary(gpio, true)                      │
│    ├── "OFF" → controlActuatorBinary(gpio, false)                     │
│    ├── "PWM" → controlActuator(gpio, value)                           │
│    └── "TOGGLE" → controlActuatorBinary(gpio, !current_state)         │
│                                                                         │
│ 5. controlActuator(gpio, value):                                       │
│    ├── Check emergency_stopped → reject                                │
│    ├── Normalize PWM value (0.0-1.0)                                   │
│    ├── driver->setValue(normalized_value)                             │
│    ├── Track activation_start_ms (for timeout)                        │
│    └── publishActuatorStatus(gpio)                                     │
│                                                                         │
│ 6. publishActuatorResponse(command, success, message)                  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
┌─────────────────────────────┐  ┌──────────────────────────────┐
│ MQTT: .../actuator/status   │  │ MQTT: .../actuator/response   │
│                             │  │                              │
│ {esp_id, gpio, type,        │  │ {esp_id, gpio, command,      │
│  state, pwm, runtime_ms,    │  │  value, success, message,    │
│  emergency, ts}             │  │  correlation_id, ts}         │
└──────────────┬──────────────┘  └──────────────┬───────────────┘
               │                                │
               ▼                                ▼
┌─────────────────────────────┐  ┌──────────────────────────────┐
│ Server: actuator_handler    │  │ Server: actuator_response_h. │
│                             │  │                              │
│ 1. Update actuator_states   │  │ 1. Log to actuator_history   │
│ 2. Log to actuator_history  │  │ 2. Audit log (correlation)   │
│ 3. Audit log (correlation)  │  │ 3. WebSocket broadcast       │
│ 4. WebSocket broadcast      │  └──────────────────────────────┘
└─────────────────────────────┘
```

### 5.3 Emergency-Stop-Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TRIGGER: Server-initiated Emergency (via REST API or Logic Engine)     │
│                                                                         │
│ POST /api/v1/actuators/emergency-stop                                   │
│ Body: { "esp_id": "ESP_12AB34CD" } (optional, ohne = fleet-weit)       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Server: SafetyService.emergency_stop_all() / emergency_stop_esp()      │
│                                                                         │
│ 1. Set emergency_stop_active["__ALL__"] = True                         │
│    OR emergency_stop_active[esp_id] = True                             │
│                                                                         │
│ 2. Log CRITICAL event                                                   │
│                                                                         │
│ 3. Publisher publishes to broadcast topic:                             │
│    Topic: kaiser/broadcast/emergency                                    │
│    Payload: { "command": "EMERGENCY_STOP", "reason": "...", "ts": ... }│
└────────────────────────────┬────────────────────────────────────────────┘
                             │ MQTT QoS 2
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ESP32: MQTTClient receives on kaiser/broadcast/emergency               │
│                                                                         │
│ → Callback triggers SafetyController.emergencyStopAll(reason)          │
│                                                                         │
│ SafetyController.emergencyStopAll():                                   │
│    ├── Set emergency_state_ = EMERGENCY_ACTIVE                         │
│    ├── Store reason, timestamp                                         │
│    └── ActuatorManager.emergencyStopAll()                              │
│                                                                         │
│ ActuatorManager.emergencyStopAll():                                    │
│    └── for each actuator:                                              │
│         ├── driver->emergencyStop("EmergencyStopAll")                  │
│         │    └── driver->setBinary(false) + set emergency flag         │
│         ├── actuator.emergency_stopped = true                          │
│         └── publishActuatorAlert(gpio, "emergency_stop", "...")        │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ MQTT: .../actuator/{gpio}/alert
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Server: actuator_alert_handler                                         │
│                                                                         │
│ 1. Log alert to database                                               │
│ 2. Audit log                                                           │
│ 3. WebSocket broadcast ("actuator_alert")                              │
│ 4. Frontend zeigt Emergency-Warnung                                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ RECOVERY: SafetyService.clear_emergency_stop()                         │
│                                                                         │
│ 1. Set emergency_stop_active.pop("__ALL__" / esp_id)                   │
│ 2. Log INFO event                                                       │
│ 3. Publish via system command: "CLEAR_EMERGENCY"                       │
│                                                                         │
│ ESP32: SafetyController.clearEmergencyStop()                           │
│    ├── Set emergency_state_ = EMERGENCY_CLEARING                       │
│    ├── verifySystemSafety()                                            │
│    │    └── Check verification_timeout_ms elapsed                      │
│    ├── ActuatorManager.clearEmergencyStop()                            │
│    │    └── for each: driver->clearEmergency()                        │
│    └── resumeOperation()                                                │
│         ├── Wait inter_actuator_delay_ms                               │
│         └── Set emergency_state_ = EMERGENCY_NORMAL                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. MQTT-Topic-Übersicht (Vollständig)

### 6.1 ESP32 → Server (Publish)

| Topic Pattern | QoS | Handler | Beschreibung |
|---------------|-----|---------|--------------|
| `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data` | 1 | `sensor_handler` | Sensor-Daten |
| `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/response` | 1 | (Phase 2C) | On-Demand Response |
| `kaiser/{kaiser_id}/esp/{esp_id}/sensor/batch` | 1 | `sensor_handler` | Batch-Daten |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status` | 1 | `actuator_handler` | Aktor-Status |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response` | 1 | `actuator_response_handler` | Command-Bestätigung |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert` | 1 | `actuator_alert_handler` | Aktor-Alert |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` | 1 | `actuator_alert_handler` | ESP-Emergency |
| `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` | 0 | `heartbeat_handler` | Heartbeat (60s) |
| `kaiser/{kaiser_id}/esp/{esp_id}/system/diagnostics` | 1 | (Phase 7) | Health-Diagnostics |
| `kaiser/{kaiser_id}/esp/{esp_id}/system/error` | 1 | `error_handler` | System-Fehler |
| `kaiser/{kaiser_id}/esp/{esp_id}/config_response` | 1 | `config_handler` | Config-ACK |
| `kaiser/{kaiser_id}/esp/{esp_id}/zone/ack` | 1 | `zone_ack_handler` | Zone-ACK |
| `kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack` | 1 | `subzone_ack_handler` | Subzone-ACK |
| `kaiser/{kaiser_id}/esp/{esp_id}/subzone/status` | 1 | (Phase 9) | Subzone-Status |
| `kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe` | 1 | (Phase 9) | Safe-Mode-Status |
<!-- KORRIGIERT: system/error Handler ist error_handler, nicht "(Phase 0)" -->
<!-- VERIFIZIERT: Alle Topics gegen TopicBuilder geprüft -->

### 6.2 Server → ESP32 (Subscribe)

| Topic Pattern | QoS | Publisher-Methode | Beschreibung |
|---------------|-----|-------------------|--------------|
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command` | 2 | `publish_actuator_command()` | Aktor-Befehl |
| `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/command` | 1 | `publish_sensor_command()` | Sensor-Befehl |
| `kaiser/{kaiser_id}/esp/{esp_id}/config` | 2 | `publish_config()` | Combined Config |
| `kaiser/{kaiser_id}/esp/{esp_id}/config/sensor/{gpio}` | 2 | `publish_sensor_config()` | Sensor-Config |
| `kaiser/{kaiser_id}/esp/{esp_id}/config/actuator/{gpio}` | 2 | `publish_actuator_config()` | Aktor-Config |
| `kaiser/{kaiser_id}/esp/{esp_id}/system/command` | 2 | `publish_system_command()` | System-Befehl |
| `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat/ack` | 0 | (Phase 2) | Heartbeat-ACK |
| `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/processed` | 1 | `publish_pi_enhanced_response()` | Pi-Enhanced Result |
| `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` | 2 | (main.cpp) | Zone-Zuweisung |
| `kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign` | 2 | (Phase 9) | Subzone-Zuweisung |
| `kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove` | 2 | (Phase 9) | Subzone-Entfernung |
| `kaiser/broadcast/emergency` | 2 | (Emergency) | Fleet-E-Stop |

---

## 7. User-Interaktionspunkte

### 7.1 REST API Endpoints

#### Sensor-Endpoints

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `GET /api/v1/sensors/{esp_id}` | GET | Alle Sensoren eines ESP |
| `GET /api/v1/sensors/{esp_id}/{gpio}` | GET | Sensor-Config abrufen |
| `POST /api/v1/sensors/{esp_id}` | POST | Sensor erstellen |
| `PUT /api/v1/sensors/{esp_id}/{gpio}` | PUT | Sensor aktualisieren |
| `DELETE /api/v1/sensors/{esp_id}/{gpio}` | DELETE | Sensor löschen |
| `GET /api/v1/sensors/{esp_id}/{gpio}/data` | GET | Sensor-Daten abfragen |
| `POST /api/v1/sensors/{esp_id}/{gpio}/calibrate` | POST | Kalibrierung |
| `POST /api/v1/sensors/{esp_id}/{gpio}/trigger` | POST | On-Demand Messung |

#### Actuator-Endpoints

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `GET /api/v1/actuators/{esp_id}` | GET | Alle Aktoren eines ESP |
| `GET /api/v1/actuators/{esp_id}/{gpio}` | GET | Aktor-Config abrufen |
| `POST /api/v1/actuators/{esp_id}` | POST | Aktor erstellen |
| `PUT /api/v1/actuators/{esp_id}/{gpio}` | PUT | Aktor aktualisieren |
| `DELETE /api/v1/actuators/{esp_id}/{gpio}` | DELETE | Aktor löschen |
| `POST /api/v1/actuators/{esp_id}/{gpio}/command` | POST | Befehl senden |
| `POST /api/v1/actuators/{esp_id}/{gpio}/emergency-stop` | POST | E-Stop (einzeln) |
| `POST /api/v1/actuators/emergency-stop` | POST | E-Stop (fleet/ESP) |
| `POST /api/v1/actuators/clear-emergency` | POST | E-Stop aufheben |

### 7.2 WebSocket Events

| Event | Richtung | Payload | Beschreibung |
|-------|----------|---------|--------------|
| `sensor_data` | Server → Frontend | `{esp_id, gpio, value, unit, quality, ...}` | Live Sensor-Wert |
| `actuator_status` | Server → Frontend | `{esp_id, gpio, state, value, emergency, ...}` | Aktor-Status |
| `actuator_response` | Server → Frontend | `{esp_id, gpio, command, success, ...}` | Command-Bestätigung |
| `actuator_alert` | Server → Frontend | `{esp_id, gpio, alert_type, message, ...}` | Emergency/Timeout |
| `actuator_command` | Server → Frontend | `{esp_id, gpio, command, issued_by, ...}` | Command gesendet |
| `actuator_command_failed` | Server → Frontend | `{esp_id, gpio, error, ...}` | Command fehlgeschlagen |

---

## 8. Offene Fragen / Unklarheiten

1. ~~**Pi-Enhanced Response an ESP:** Das ESP32 scheint die verarbeiteten Werte vom Server zu empfangen (`publish_pi_enhanced_response`), aber es ist unklar, wie diese auf dem ESP verwendet werden.~~
<!-- GELÖST: PiEnhancedProcessor auf ESP32 (src/services/sensor/pi_enhanced_processor.cpp)
empfängt Responses und kann sie lokal cachen. Primär für Display-Updates oder lokale
Alerts verwendet. Die ProcessedSensorData wird in SensorManager.performMeasurement()
zurückgegeben und kann in reading_out.processed_value abgelegt werden. -->

2. **Subzone-Isolation:** Phase 9 führt `isolateSubzone()` ein - Server-seitige Implementierung ist zu dokumentieren.
<!-- TEILWEISE GELÖST: ESP32-seitig existiert SafetyController.isolateSubzone()
(Zeile 66-86 in safety_controller.cpp), das gpioManager.enableSafeModeForSubzone()
aufruft. Server-seitig muss noch dokumentiert werden. -->

3. **Logic Engine Integration:** Die Logic Engine wird asynchron getriggert, aber die Fehlerbehandlung bei Logic-Evaluation-Fehlern ist nicht klar.

4. **Config-Response-Handling:** Der Server sendet Config, ESP32 antwortet mit `config_response`, aber die vollständige Feedback-Schleife (was passiert bei `PARTIAL_SUCCESS`?) ist nicht dokumentiert.

5. **Wokwi-Simulation:** Wie verhält sich das System bei Wokwi, wo echte Hardware fehlt? (I2C-Device-Checks werden übersprungen)
<!-- TEILWEISE GELÖST: SensorManager.configureSensor() loggt WARNING bei fehlenden
I2C-Devices (Zeile 282-286): "may be simulation mode" - kein Failure. -->

---

## 9. Empfehlungen für Test-Entwicklung

### 9.1 Kritische Szenarien

1. **Sensor-Ausfall-Szenarien:**
   - DS18B20 liefert -127°C (Disconnect)
   - DS18B20 liefert 85°C (Power-on-Reset)
   - I2C-Gerät antwortet nicht
   - OneWire-Bus-Timeout

2. **Aktor-Safety-Szenarien:**
   - Emergency-Stop während aktiver Aktion
   - Timeout-Protection triggert
   - PWM-Wert außerhalb 0.0-1.0
   - GPIO-Konflikt mit Sensor

3. **Kommunikations-Szenarien:**
   - MQTT-Disconnect während Command
   - Server nicht erreichbar
   - Payload-Validierung fehlschlägt
   - Correlation-ID-Tracking

4. **Multi-Geräte-Szenarien:**
   - Mehrere ESPs senden gleichzeitig
   - Fleet-weiter Emergency-Stop
   - OneWire-Bus mit mehreren DS18B20

### 9.2 Edge-Cases

1. **GPIO 255:** Ungültiger GPIO-Wert (Sentinel)
2. **Empty Payload:** Leere MQTT-Nachricht
3. **Timestamp 0:** Kein Timestamp vorhanden
4. **Millis vs Seconds:** Automatische Erkennung testen
5. **ROM-Code CRC:** Ungültiger OneWire-ROM-Code
6. **Max Sensors/Actuators:** Array-Grenzen erreicht

### 9.3 Integration-Tests

1. **End-to-End Sensor Flow:** ESP → MQTT → Handler → DB → WebSocket → Frontend
2. **End-to-End Actuator Flow:** Frontend → API → Safety → MQTT → ESP → Response
3. **Emergency-Stop Propagation:** Server → MQTT → ESP → Alert → Server → WebSocket
4. **Config Deployment:** Server → Config → ESP → Config-Response → Server

---

## 10. Verifikations-Protokoll

**Verifikationsdatum:** 2026-01-29
**Reviewer:** Claude Opus 4.5 (Second Review)

### Änderungsübersicht

| Abschnitt | Änderungstyp | Beschreibung |
|-----------|--------------|--------------|
| 2.1 | KORREKTUR | `begin()` endet bei Zeile 94, nicht 93 |
| 2.1 | ERGÄNZUNG | Error-Code 1063 `ERROR_DS18B20_DISCONNECTED_RUNTIME` hinzugefügt |
| 2.1 | ERGÄNZUNG | Vollständige OneWire Error-Code-Tabelle (1020-1029) |
| 2.1 | ERGÄNZUNG | ErrorTracker in Abhängigkeitsliste |
| 2.2 | KORREKTUR | `controlActuator()` endet bei Zeile 380, nicht 379 |
| 2.2 | ERGÄNZUNG | ErrorTracker in Abhängigkeitsliste |
| 2.3 | ERGÄNZUNG | Bestätigung dass `gpioManager.enableSafeModeForSubzone()` existiert |
| 3.1.1 | KORREKTUR | sensor_handler.py hat 697 Zeilen, nicht 698 |
| 3.1.2 | KORREKTUR | actuator_handler.py hat 457 Zeilen, nicht 458 |
| 3.1.3 | KORREKTUR | actuator_response_handler.py hat 279 Zeilen, nicht 280 |
| 3.1 | ERGÄNZUNG | Neue Section 3.1.4 mit allen fehlenden Handlern |
| 3.2.1 | KORREKTUR | sensor_service.py hat 545 Zeilen, nicht 546 |
| 3.2.2 | KORREKTUR | actuator_service.py hat 279 Zeilen, nicht 280 |
| 3.2.3 | KORREKTUR | safety_service.py hat 264 Zeilen, nicht 265 |
| 3.3 | KORREKTUR | publisher.py hat 441 Zeilen, nicht 442 |
| 4.1 | ERGÄNZUNG | `created_at`, `updated_at` via TimestampMixin dokumentiert |
| 4.2 | ERGÄNZUNG | `created_at`, `updated_at` via TimestampMixin dokumentiert |
| 6.1 | KORREKTUR | system/error Handler ist `error_handler`, nicht "(Phase 0)" |
| 8 | UPDATE | Offene Fragen 1 und 5 teilweise gelöst mit Code-Referenzen |

### Verifikations-Status

- [x] ESP32 SensorManager verifiziert (sensor_manager.cpp vollständig gelesen)
- [x] ESP32 ActuatorManager verifiziert (actuator_manager.cpp vollständig gelesen)
- [x] ESP32 SafetyController verifiziert (safety_controller.cpp vollständig gelesen)
- [x] Server MQTT Handler verifiziert (Handler-Liste und Zeilenzahlen geprüft)
- [x] Server Services verifiziert (Zeilenzahlen gegen `wc -l` geprüft)
- [x] Server Publisher verifiziert (Zeilenzahl gegen `wc -l` geprüft)
- [x] Datenbank-Schema verifiziert (gegen SQLAlchemy Models geprüft)
- [x] MQTT-Topics verifiziert (gegen TopicBuilder.cpp geprüft)
- [x] Error-Codes verifiziert (gegen error_codes.h geprüft)
- [x] Kommunikations-Diagramme verifiziert (Flows stimmen mit Code überein)
- [x] Offene Fragen bearbeitet (2 von 5 teilweise gelöst)

### Offene Punkte für Phase 3

1. **Server-seitige Subzone-Isolation** - Dokumentation der Server-Services für Phase 9
2. **Logic Engine Fehlerbehandlung** - Detaillierte Analyse der Error-Recovery
3. **Config PARTIAL_SUCCESS** - Vollständige Dokumentation der Feedback-Schleife
4. **WebSocket Event Filtering** - Wie können Frontend-Clients Events filtern?

### Qualitätsbewertung

- **Dokumentationsqualität:** 4.5/5 (sehr gut, kleinere Zeilenzahl-Abweichungen)
- **Codebase-Abdeckung:** 4.5/5 (ESP32 Core vollständig, Server Core vollständig)
- **Architektur-Verständnis:** 5/5 (korrekte Flows und Abhängigkeiten)
- **Testbarkeit:** 5/5 (klare Szenarien und Edge-Cases dokumentiert)

---

**Ende der verifizierten Analyse**

*Erstellt basierend auf Code-Analyse vom 2026-01-29*
*Verifiziert am 2026-01-29*
