# MQTT Client API Specification
## services/communication/mqtt_client.h/cpp

**Version:** 2.1 (SAFETY-P4 Disconnect vs. sofortiges Safe-State, 2026-03-31)  
**Zweck:** MQTT-Client-Wrapper für ESP32 mit Auto-Reconnect, Offline-Buffering und Heartbeat-System  
**Status:** ✅ IMPLEMENTED (Phase 2)

**SAFETY-RTOS M2:** Build-Flag `MQTT_USE_PUBSUBCLIENT` (siehe `platformio.ini`) — wenn gesetzt: PubSubClient-Pfad (Offline-Buffer, blocking reconnect). Wenn NICHT gesetzt (Default): **ESP-IDF MQTT** (`#include <mqtt_client.h>` aus dem Arduino-Framework, nicht der lokale Header, Non-Blocking, eigener FreeRTOS-Task). `isConnected()` liest im ESP-IDF-Pfad `g_mqtt_connected` (atomic). Dieses Dokument beschreibt weiterhin primär den PubSubClient-Pfad; Abweichungen sind in `mqtt_client.h`/`mqtt_client.cpp` nach `#ifndef MQTT_USE_PUBSUBCLIENT` dokumentiert.

**SAFETY-RTOS M3:** Im normalen Betrieb (volles `setup()` mit Safety-/Communication-Tasks) ruft **`tasks/communication_task.cpp`** periodisch `mqttClient.loop()` und (nur bei `MQTT_USE_ESP_IDF`) `mqttClient.processPublishQueue()` auf — **nicht** `main.cpp::loop()`. Letzteres ist nach vollem Init minimal (`vTaskDelay`). Bei frühem `setup()`-Return ohne Tasks gilt weiterhin ein Legacy-Zweig in `main.cpp` mit WiFi/MQTT in der Arduino-`loop()`.

---

## Abhängigkeiten

```cpp
// Abhängig vom Build: siehe mqtt_client.h — entweder ESP-IDF MQTT oder:
#include <PubSubClient.h>           // Arduino MQTT Library (Fallback)
#include <WiFiClient.h>             // ESP32 WiFi Client (nur PubSubClient-Pfad)
#include <Arduino.h>
#include <functional>               // std::function for callbacks
#include "utils/logger.h"           // Logging (Phase 1)
#include "utils/topic_builder.h"   // Topic Generation (Phase 1)
#include "error_handling/error_tracker.h"  // Error Tracking (Phase 1)
#include "models/system_types.h"    // WiFiConfig (Phase 1)
```

---

## Datenstrukturen

### MQTTConfig
```cpp
struct MQTTConfig {
    String server;              // Broker IP/Hostname (REQUIRED)
    uint16_t port;             // Broker Port (default: 1883/8883)
    String client_id;           // ESP32 Client ID (REQUIRED)
    String username;            // Optional: MQTT Username (empty = Anonymous Mode)
    String password;            // Optional: MQTT Password (empty = Anonymous Mode)
    int keepalive;              // Keepalive Interval (default: 60s)
    int timeout;                // Connection Timeout (default: 10s)
};
```

**Hinweise:**
- `username` und `password` können leer sein → Anonymous Mode
- Transition von Anonymous → Authenticated via `transitionToAuthenticated()`

### MQTTMessage (Offline Buffer)
```cpp
struct MQTTMessage {
    String topic;               // MQTT Topic
    String payload;             // Message Payload
    uint8_t qos;                // QoS Level (0 or 1)
    unsigned long timestamp;    // Creation Timestamp (millis())
};
```

**Offline Buffer:**
- Fixed Array: `MQTTMessage offline_buffer_[MAX_OFFLINE_MESSAGES]`
- Circular Buffer (FIFO)
- Max 25 Messages (`MAX_OFFLINE_MESSAGES = 25`, reduziert von 100 fuer Heap-Einsparung)
- Processed on reconnection
- Nur im PubSubClient-Pfad — ESP-IDF-Pfad nutzt internen Outbox

---

## Public API

### Singleton Pattern

#### `static MQTTClient& getInstance()`
**Beschreibung:** Singleton-Zugriff auf MQTTClient  
**Rückgabe:** Referenz auf globale Instanz  
**Verwendung:**
```cpp
MQTTClient& mqtt = mqttClient;  // Global instance
```

---

### Initialisierung

#### `bool begin()`
**Beschreibung:** Initialisiert MQTT-Client  
**Rückgabe:** `true` bei Erfolg  
**Fehlerbehandlung:**
- Double-init wird ignoriert (LOG_WARNING)
- Setzt PubSubClient Callback

**Verhalten:**
- Setzt static callback für PubSubClient
- Initialisiert interne Zustandsvariablen
- Setzt `initialized_` Flag

**Beispiel:**
```cpp
if (!mqttClient.begin()) {
    LOG_ERROR("MQTTClient initialization failed");
    return;
}
```

---

### Verbindungsmanagement

#### `bool connect(const MQTTConfig& config)`
**Beschreibung:** Stellt Verbindung zum MQTT-Broker her  
**Parameter:**
- `config`: MQTT-Konfiguration (REQUIRED)

**Rückgabe:** `true` bei erfolgreicher Verbindung  
**Fehlerbehandlung:**
- Validiert Server-Adresse (nicht leer)
- Loggt Fehler via ErrorTracker (ERROR_MQTT_INIT_FAILED, ERROR_MQTT_CONNECT_FAILED)
- Bei Fehler: Exponential Backoff wird gestartet

**Verhalten:**
- Prüft Anonymous vs. Authenticated Mode (username leer?)
- Setzt PubSubClient Server und Port
- Ruft `connectToBroker()` auf
- Bei Erfolg: Verarbeitet Offline-Buffer
- Reset Reconnect-Counter

**Beispiel:**
```cpp
MQTTConfig config;
config.server = "192.168.1.100";
config.port = 1883;
config.client_id = "ESP_12AB34CD";
config.username = "";  // Anonymous mode
config.password = "";
config.keepalive = 60;
config.timeout = 10;

if (!mqttClient.connect(config)) {
    LOG_ERROR("MQTT connection failed");
}
```

---

#### `bool disconnect()`
**Beschreibung:** Trennt MQTT-Verbindung (Graceful Shutdown)  
**Rückgabe:** `true` bei Erfolg  
**Verhalten:**
- Ruft `mqtt_.disconnect()` auf
- Loggt Disconnection

---

#### `bool isConnected() const`
**Beschreibung:** Prüft MQTT-Verbindungsstatus  
**Rückgabe:** `true` wenn verbunden  
**Verhalten:**
- Prüft `mqtt_.connected()` Status

---

#### `void reconnect()`
**Beschreibung:** Versucht MQTT-Reconnection mit Exponential Backoff und Circuit Breaker  
**File:** `src/services/communication/mqtt_client.cpp` (lines 155-203)

**Tatsächliche Implementierung:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 165-220)

```cpp
void MQTTClient::reconnect() {
    if (isConnected()) {
        LOG_DEBUG("MQTT already connected");
        circuit_breaker_.recordSuccess();  // Reset on successful connection
        return;
    }
    
    // Circuit Breaker Check (Phase 6+)
    if (!circuit_breaker_.allowRequest()) {
        LOG_DEBUG("MQTT reconnect blocked by Circuit Breaker (waiting for recovery)");
        return;  // Skip reconnect attempt
    }
    
    if (!shouldAttemptReconnect()) {
        return;
    }
    
    reconnect_attempts_++;
    last_reconnect_attempt_ = millis();
    
    LOG_INFO("Attempting MQTT reconnection (attempt " + 
             String(reconnect_attempts_) + "/" + 
             String(MAX_RECONNECT_ATTEMPTS) + ")");
    
    if (!connectToBroker()) {
        // Reconnect failed
        circuit_breaker_.recordFailure();
        
        // Exponential backoff
        reconnect_delay_ms_ = calculateBackoffDelay();
        
        if (reconnect_attempts_ >= MAX_RECONNECT_ATTEMPTS) {
            LOG_CRITICAL("Max MQTT reconnection attempts reached");
            errorTracker.logCommunicationError(ERROR_MQTT_CONNECT_FAILED, 
                                               "Max reconnection attempts reached");
        }
        
        // Check if Circuit Breaker opened
        if (circuit_breaker_.isOpen()) {
            LOG_WARNING("Circuit Breaker OPENED after reconnect failures");
            LOG_WARNING("  Will retry in 30 seconds");
        }
    } else {
        // Reconnect successful
        LOG_INFO("MQTT reconnected successfully");
        circuit_breaker_.recordSuccess();
        reconnect_attempts_ = 0;
        reconnect_delay_ms_ = RECONNECT_BASE_DELAY_MS;
        
        // Process offline buffer
        processOfflineBuffer();
    }
}
```

**Verhalten:**
- Prüft ob bereits verbunden → return (keine Aktion)
- Prüft Circuit Breaker → blockiert wenn OPEN
- Prüft ob Reconnect erlaubt (`shouldAttemptReconnect()`)
- Prüft Backoff-Delay → wartet wenn nötig
- Incrementiert Reconnect-Counter
- Ruft `connectToBroker()` auf
- Bei Erfolg:
  - Record Success im Circuit Breaker
  - Reset Reconnect-Counter
  - Verarbeitet Offline-Buffer (`processOfflineBuffer()`)
- Bei Fehler:
  - Record Failure im Circuit Breaker
  - Berechnet neuen Backoff-Delay
  - Bei Max Attempts (10): Loggt Critical Error

**Exponential Backoff:**
- Base Delay: 1000ms (`RECONNECT_BASE_DELAY_MS`)
- Max Delay: 60000ms (`RECONNECT_MAX_DELAY_MS`)
- Formula: `delay = base * (2^attempts)`, capped at max
- Max Attempts: 10 (`MAX_RECONNECT_ATTEMPTS`)

**Backoff Sequence:**
- Attempt 1: 1s delay
- Attempt 2: 2s delay
- Attempt 3: 4s delay
- Attempt 4: 8s delay
- Attempt 5: 16s delay
- Attempt 6: 32s delay
- Attempt 7+: 60s delay (capped)

---

#### `bool transitionToAuthenticated(const String& username, const String& password)`
**Beschreibung:** Wechselt von Anonymous zu Authenticated Mode  
**Parameter:**
- `username`: MQTT Username (REQUIRED)
- `password`: MQTT Password (REQUIRED)

**Rückgabe:** `true` bei Erfolg  
**Verhalten:**
- Prüft ob bereits authenticated → return true
- Aktualisiert Config mit Credentials
- Setzt `anonymous_mode_` Flag
- Disconnect + Reconnect mit Authentication

**Beispiel:**
```cpp
if (mqttClient.isAnonymousMode()) {
    mqttClient.transitionToAuthenticated("user", "pass");
}
```

---

#### `bool isAnonymousMode() const`
**Beschreibung:** Prüft ob Anonymous Mode aktiv ist  
**Rückgabe:** `true` wenn Anonymous Mode

---

### Publishing

#### `PublishFailureReasonClass`
**Beschreibung:** Kanonische Klassifikation des letzten Publish-Fehlschlags.  
**Werte:**
- `None`
- `CircuitBreakerOpen`
- `QueueShed`
- `OutboxFull`
- `TransportError`

---

#### `bool publish(const String& topic, const String& payload, uint8_t qos = 1)`
**Beschreibung:** Publiziert MQTT-Message  
**Parameter:**
- `topic`: MQTT Topic (REQUIRED)
- `payload`: Message Payload (REQUIRED)
- `qos`: QoS Level (default: 1, supported: 0 or 1)

**Rückgabe:** `true` bei erfolgreicher Übertragung oder Buffering  
**Fehlerbehandlung:**
- Nicht verbunden → Message in Offline-Buffer
- Publish fehlgeschlagen → Message in Offline-Buffer
- Loggt Fehler via ErrorTracker (ERROR_MQTT_PUBLISH_FAILED)

**Verhalten:**
- Wenn verbunden: Sofort senden via `mqtt_.publish()`
- Wenn nicht verbunden: In Offline-Buffer speichern
- QoS 1 wird als `mqtt_.publish(topic, payload, true)` gesendet
- QoS 0 wird als `mqtt_.publish(topic, payload, false)` gesendet

**Beispiel:**
```cpp
String topic = "kaiser/god/esp/ESP_12AB34CD/sensor/4/data";
String payload = "{\"value\":21.5}";
mqttClient.publish(topic, payload, 1);
```

---

#### `PublishFailureReasonClass getLastPublishFailureReasonClass() const`
**Beschreibung:** Liefert die letzte Publish-Fehlerklasse als Enum.  
**Rückgabe:** Letzte Fehlerklasse (`PublishFailureReasonClass`), bei Erfolg `None`.

---

#### `const char* getLastPublishFailureReasonClassName() const`
**Beschreibung:** Liefert die letzte Publish-Fehlerklasse als kanonischen String.  
**Rückgabe:** Einer von `cb_open`, `queue_shed`, `outbox_full`, `transport_error`.

---

#### `bool safePublish(const String& topic, const String& payload, uint8_t qos = 1, uint8_t retries = 3)`
**Beschreibung:** Publiziert mit Retry-Logic  
**Parameter:**
- `topic`: MQTT Topic (REQUIRED)
- `payload`: Message Payload (REQUIRED)
- `qos`: QoS Level (default: 1)
- `retries`: Anzahl Wiederholungen (default: 3)

**Rückgabe:** `true` wenn erfolgreich (auch nach Retry)  
**Verhalten:**
- Versucht `publish()` `retries` mal
- Wartet 100ms zwischen Versuchen
- Bei Erfolg: return true
- Nach allen Retries: return false

---

#### `void setTestPublishHook(std::function<void(const String&, const String&)> hook)`
**Beschreibung:** Setzt einen Test-Hook für Unit-Tests (interceptiert `publish()` Aufrufe)  
**Parameter:**
- `hook`: Callback-Funktion die bei jedem `publish()` aufgerufen wird (topic, payload)

**Verhalten:**
- Hook wird vor tatsächlichem MQTT-Publish aufgerufen
- Ermöglicht Unit-Tests ohne echten MQTT-Broker
- Hook wird nur einmal pro `publish()` aufgerufen

**Beispiel:**
```cpp
// In Unit-Test
mqttClient.setTestPublishHook([](const String& topic, const String& payload) {
    EXPECT_EQ(topic, "test/topic");
    EXPECT_EQ(payload, "{\"test\": true}");
});

mqttClient.publish("test/topic", "{\"test\": true}", 1);
// Hook wird aufgerufen, aber kein echter MQTT-Publish
```

**Hinweis:** Test-Hooks sind nur für Unit-Tests gedacht. In Produktions-Code nicht verwenden!

---

#### `void clearTestPublishHook()`
**Beschreibung:** Entfernt Test-Hook (normaler Betrieb)  
**Verhalten:**
- Entfernt gesetzten Hook
- Nachfolgende `publish()` Aufrufe gehen an echten MQTT-Broker

**Beispiel:**
```cpp
mqttClient.clearTestPublishHook();
mqttClient.publish("test/topic", "payload", 1);  // Echter MQTT-Publish
```

---

### Config JSON-Schemas

#### Sensor-Config Payload

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config`  
**Direction:** Server → ESP (PUBLISH)  
**QoS:** 1 (Guaranteed Delivery)  
**Retention:** false

**JSON-Schema:**
```json
{
  "sensors": [
    {
      "gpio": 4,
      "sensor_type": "ph_sensor",
      "sensor_name": "Boden pH Zone 1",
      "subzone_id": "zone_1",
      "active": true,
      "raw_mode": true
    },
    {
      "gpio": 5,
      "sensor_type": "temperature_ds18b20",
      "sensor_name": "Wasser Temp",
      "subzone_id": "zone_1",
      "active": true,
      "raw_mode": false
    }
  ]
}
```

**Field-Beschreibungen:**
- `gpio`: GPIO Pin für Sensor (ADC: 32-39, Digital: 0-39)
- `sensor_type`: Sensor-Typ-Identifier (Server-definiert)
- `sensor_name`: Human-Readable Name für Logging/UI
- `subzone_id`: Zuordnung zu Subzone (Optional)
- `active`: Sensor aktiv (true) oder deaktiviert (false)
- `raw_mode`: Raw ADC-Werte (true) oder kalibrierte Werte (false)

**Validation-Rules:**
- GPIO 0-39 (ESP32-Standard)
- `sensor_type` nicht leer
- `sensor_name` nicht leer
- Kein GPIO-Konflikt mit anderen Sensoren/Aktoren

---

#### Actuator-Config Payload

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config`  
**Direction:** Server → ESP (PUBLISH)  
**QoS:** 1 (Guaranteed Delivery)  
**Retention:** false

**JSON-Schema:**
```json
{
  "actuators": [
    {
      "gpio": 5,
      "aux_gpio": 255,
      "actuator_type": "pump",
      "actuator_name": "Haupt-Pumpe A",
      "subzone_id": "zone_1",
      "active": true,
      "critical": true,
      "inverted_logic": false,
      "default_state": false,
      "default_pwm": 0
    },
    {
      "gpio": 18,
      "aux_gpio": 19,
      "actuator_type": "pwm",
      "actuator_name": "Lüfter PWM",
      "subzone_id": "zone_2",
      "active": true,
      "critical": false,
      "inverted_logic": false,
      "default_state": false,
      "default_pwm": 128
    }
  ]
}
```

**Field-Beschreibungen:**
- `gpio`: Primary GPIO Pin (Output)
- `aux_gpio`: Secondary GPIO Pin (z.B. H-Bridge Direction, 255=unused)
- `actuator_type`: Actuator-Type (`"pump"`, `"pwm"`, `"valve"`, `"relay"`)
- `actuator_name`: Human-Readable Name
- `subzone_id`: Subzone-Zuordnung
- `active`: Aktor aktiv (true) oder deaktiviert (false)
- `critical`: Kritischer Aktor (true) → Safe-Mode bevorzugt
- `inverted_logic`: LOW=ON (true) oder HIGH=ON (false)
- `default_state`: Default Boot-State (ON/OFF)
- `default_pwm`: Default PWM Duty-Cycle (0-255, nur für PWM)

**Validation-Rules:**
- GPIO 0-39
- `actuator_type` ∈ {pump, pwm, valve, relay}
- `actuator_name` nicht leer
- Kein GPIO-Konflikt
- `aux_gpio` ≠ `gpio` (falls verwendet)

---

#### Config-Update-Flow

```
┌──────────────┐                      ┌─────────────┐                      ┌──────────────┐
│   Server     │                      │    MQTT     │                      │    ESP32     │
│ (God-Kaiser) │                      │   Broker    │                      │   (Client)   │
└──────┬───────┘                      └──────┬──────┘                      └──────┬───────┘
       │                                     │                                     │
       │ 1. Config ändern (UI/Logic)         │                                     │
       │                                     │                                     │
       │ 2. PUBLISH /config (JSON)           │                                     │
       ├────────────────────────────────────>│                                     │
       │    QoS: 1, Retain: false            │                                     │
       │                                     │                                     │
       │                                     │ 3. DELIVER /config (QoS 1)          │
       │                                     ├────────────────────────────────────>│
       │                                     │                                     │
       │                                     │                 4. Parse JSON       │
       │                                     │                 5. Validate Config  │
       │                                     │                    ├─> GPIO Range   │
       │                                     │                    ├─> Type Check   │
       │                                     │                    └─> Conflict Det │
       │                                     │                                     │
       │                                     │                 6. Apply Config     │
       │                                     │                    ├─> sensorManager│
       │                                     │                    └─> actuatorMgr  │
       │                                     │                                     │
       │                                     │                 7. NVS Save         │
       │                                     │                    (Nur Sensors!)   │
       │                                     │                                     │
       │                                     │                 8. Register HAL     │
       │                                     │                    (GPIO-Setup)     │
       │                                     │                                     │
       │                                     │ 9. PUBLISH /config_response (ACK)   │
       │                                     │<────────────────────────────────────┤
       │                                     │    {"status":"success","count":2}   │
       │                                     │                                     │
       │ 10. RECEIVE /config_response        │                                     │
       │<────────────────────────────────────┤                                     │
       │                                     │                                     │
       │ 11. UI Update (Success Notification)│                                     │
       │                                     │                                     │
```

**Timing:**
- Step 2-3: <100ms (MQTT-Latency)
- Step 4-8: <500ms (Parse + Validate + Apply + NVS)
- Step 9-10: <100ms (MQTT-Latency)
- **Total:** <700ms (Server → ESP → Response)

---

#### Config-Response Topic

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/config_response`  
**Direction:** ESP → Server (PUBLISH)  
**QoS:** 1  
**Retention:** false  
**Implementation:** `ConfigResponseBuilder` (`src/services/config/config_response.*`)  
**Verwendet von:** Sensor- und Actuator-Konfiguration (Phase 6)

**Success Response:**
```json
{
  "status": "success",
  "type": "sensor",
  "count": 2,
  "message": "Configured 2 sensors successfully"
}
```

**Error Response (Validation-Fehler):**
```json
{
  "status": "error",
  "type": "sensor",
  "error_code": "VALIDATION_FAILED",
  "message": "Sensor validation failed: GPIO 50 out of range (max 39)",
  "failed_item": {
    "gpio": 50,
    "sensor_type": "ph_sensor"
  }
}
```

**Error Response (GPIO-Conflict):**
```json
{
  "status": "error",
  "type": "actuator",
  "error_code": "GPIO_CONFLICT",
  "message": "GPIO 5 already used by Sensor 'Boden pH'",
  "failed_item": {
    "gpio": 5,
    "actuator_type": "pump"
  }
}
```

**Error Response (JSON-Parse-Fehler):**
```json
{
  "status": "error",
  "type": "unknown",
  "error_code": "JSON_PARSE_ERROR",
  "message": "Failed to parse JSON: Missing closing brace"
}
```

---

**Standardisierte Config-Error-Codes (`ConfigErrorCode`):**

- `JSON_PARSE_ERROR` – JSON konnte nicht deserialisiert werden
- `VALIDATION_FAILED` – Feldvalidierung fehlgeschlagen (Range, Pflichtfeld, etc.)
- `GPIO_CONFLICT` – GPIO bereits durch Sensor oder Actuator belegt
- `NVS_WRITE_FAILED` – Preferences/NVS Schreibvorgang fehlgeschlagen
- `TYPE_MISMATCH` – Datentyp stimmt nicht mit Erwartung überein
- `MISSING_FIELD` – Pflichtfeld fehlt im Payload
- `OUT_OF_RANGE` – Wert außerhalb zulässigem Bereich
- `UNKNOWN_ERROR` – Fallback für nicht spezifizierte Fehler
- `NONE` – Platzhalter bei Erfolgsnachrichten

---

#### Error-Handling-Matrix

| Error-Type | ESP-Action | Response | Server-Action |
|------------|------------|----------|---------------|
| **JSON-Parse-Fehler** | `LOG_ERROR`, Abort | NACK (`JSON_PARSE_ERROR`) | Retry mit korrigiertem JSON |
| **Validation-Fehler** | `LOG_WARNING`, Abort | NACK (`VALIDATION_FAILED`) | Fix Config, Retry |
| **GPIO-Conflict** | `LOG_ERROR`, Abort | NACK (`GPIO_CONFLICT`) | Resolve Conflict, Retry |
| **NVS-Write-Fehler** | `LOG_ERROR`, Abort | NACK (`NVS_WRITE_FAILED`) | Retry oder Factory-Reset |
| **Success** | `LOG_INFO`, Apply | ACK (`success`) | UI-Update, Continue |

**Note:** Bei NACK wird **keine Config angewendet** (Transactional Semantics).

---

### Test Hooks (Unit Testing)

#### `void setTestPublishHook(std::function<void(const String&, const String&)> hook)`
**Beschreibung:** Setzt einen Test-Hook für Unit-Tests (interceptiert `publish()` Aufrufe)  
**Parameter:**
- `hook`: Callback-Funktion die bei jedem `publish()` aufgerufen wird (topic, payload)

**Verhalten:**
- Hook wird vor tatsächlichem MQTT-Publish aufgerufen
- Ermöglicht Unit-Tests ohne echten MQTT-Broker
- Hook wird nur einmal pro `publish()` aufgerufen

**Beispiel:**
```cpp
// In Unit-Test
mqttClient.setTestPublishHook([](const String& topic, const String& payload) {
    EXPECT_EQ(topic, "test/topic");
    EXPECT_EQ(payload, "{\"test\": true}");
});

mqttClient.publish("test/topic", "{\"test\": true}", 1);
// Hook wird aufgerufen, aber kein echter MQTT-Publish
```

#### `void clearTestPublishHook()`
**Beschreibung:** Entfernt Test-Hook (normaler Betrieb)  
**Verhalten:**
- Entfernt gesetzten Hook
- Nachfolgende `publish()` Aufrufe gehen an echten MQTT-Broker

**Beispiel:**
```cpp
mqttClient.clearTestPublishHook();
mqttClient.publish("test/topic", "payload", 1);  // Echter MQTT-Publish
```

**Hinweis:** Test-Hooks sind nur für Unit-Tests gedacht. In Produktions-Code nicht verwenden!

---

### Subscription

#### `bool subscribe(const String& topic, uint8_t qos = 0)`
**Beschreibung:** Subscribed zu MQTT-Topic
**Parameter:**
- `topic`: MQTT Topic (REQUIRED)
- `qos`: QoS Level (default: 0, supported: 0 or 1)

**Rückgabe:** `true` bei Erfolg
**Fehlerbehandlung:**
- Nicht verbunden → Loggt Fehler (ERROR_MQTT_SUBSCRIBE_FAILED)
- Subscribe fehlgeschlagen → Loggt Fehler

**Verhalten:**
- Prüft Verbindungsstatus
- Subscribed via `mqtt_.subscribe(topic.c_str(), qos)`
- Loggt Subscription mit QoS-Level

**Beispiel:**
```cpp
mqttClient.subscribe("kaiser/god/esp/ESP_12AB34CD/system/command", 1);  // QoS 1
mqttClient.subscribe("kaiser/god/esp/ESP_12AB34CD/config", 1);          // QoS 1
mqttClient.subscribe("kaiser/god/esp/ESP_12AB34CD/heartbeat/ack");      // QoS 0 (default)
```

---

#### `bool unsubscribe(const String& topic)`
**Beschreibung:** Unsubscribed von Topic  
**Parameter:**
- `topic`: MQTT Topic (REQUIRED)

**Rückgabe:** `true` bei Erfolg  
**Verhalten:**
- Prüft Verbindungsstatus
- Unsubscribed via `mqtt_.unsubscribe(topic.c_str())`
- Loggt Unsubscription

---

#### `void setCallback(std::function<void(const String&, const String&)> callback)`
**Beschreibung:** Setzt Callback für eingehende Messages
**Parameter:**
- `callback`: Lambda/Function mit (topic, payload)

**Verhalten:**
- Callback wird bei jedem empfangenen Message aufgerufen
- WICHTIG: Callback MUSS schnell sein (nicht blockierend)
- Lange Verarbeitung → in Task auslagern

---

#### `void setOnConnectCallback(std::function<void()> callback)` *(SAFETY-P1 2026-03-30)*
**Beschreibung:** Setzt Callback der nach jedem erfolgreichen MQTT-Connect ausgelöst wird (initial + reconnect)
**Parameter:**
- `callback`: Parameterloser Callback

**Verhalten:**
- Wird in `connectToBroker()` nach `processOfflineBuffer()` aufgerufen
- Genutzt für: Re-Subscribe aller Topics (Mech A), Server-ACK-Reset (Mech D), State-Sync nach Reconnect (Mech E)
- Callback wird VOR `return true` ausgeführt — MQTT ist garantiert verbunden

**Beispiel:**
```cpp
mqttClient.setOnConnectCallback([]() {
    subscribeToAllTopics();
    g_last_server_ack_ms = millis();
});
```

**Beispiel:**
```cpp
mqttClient.setCallback([](const String& topic, const String& payload) {
    LOG_INFO("MQTT message received: " + topic);
    LOG_DEBUG("Payload: " + payload);
    // Parse payload...
});
```

---

### Heartbeat System

#### `void publishHeartbeat()`
**Beschreibung:** Publiziert System-Heartbeat (automatisch alle 60s)  
**File:** `src/services/communication/mqtt_client.cpp` (lines 380-408)

**Verhalten:**
- Prüft ob 60s seit letztem Heartbeat vergangen (`HEARTBEAT_INTERVAL_MS = 60000`)
- Baut Heartbeat-Topic via `TopicBuilder::buildSystemHeartbeatTopic()`
- Baut JSON Payload via **manuelle String-Konkatenation** (nicht DynamicJsonDocument für Performance)

**Tatsächliche Implementierung:**

```cpp
void MQTTClient::publishHeartbeat() {
    unsigned long current_time = millis();
    
    if (current_time - last_heartbeat_ < HEARTBEAT_INTERVAL_MS) {
        return;
    }
    
    last_heartbeat_ = current_time;
    
    // Build heartbeat topic
    const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
    
    // Build heartbeat payload (JSON) - Phase 7: Enhanced with Zone Info
    String payload = "{";
    payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
    payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
    payload += "\"master_zone_id\":\"" + g_kaiser.master_zone_id + "\",";
    payload += "\"zone_assigned\":" + String(g_kaiser.zone_assigned ? "true" : "false") + ",";
    payload += "\"ts\":" + String(current_time) + ",";
    payload += "\"uptime\":" + String(millis() / 1000) + ",";
    payload += "\"heap_free\":" + String(ESP.getFreeHeap()) + ",";
    payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
    payload += "\"sensor_count\":" + String(sensorManager.getActiveSensorCount()) + ",";
    payload += "\"actuator_count\":" + String(actuatorManager.getActiveActuatorCount());
    payload += "}";
    
    // Publish with QoS 0 (heartbeat doesn't need guaranteed delivery)
    publish(topic, payload, 0);
}
```

**Heartbeat Payload Format (Phase 7):**

```json
{
  "esp_id": "ESP_AB12CD",
  "zone_id": "greenhouse_zone_1",
  "master_zone_id": "greenhouse_master",
  "zone_assigned": true,
  "ts": 1234567890,
  "uptime": 12345,
  "heap_free": 250000,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 2
}
```

**Fields:**
- `esp_id`: ESP device identifier (from `g_system_config.esp_id`)
- `zone_id`: Primary zone identifier (Phase 7, from `g_kaiser.zone_id`)
- `master_zone_id`: Parent master zone (Phase 7, from `g_kaiser.master_zone_id`)
- `zone_assigned`: Zone assignment status flag (Phase 7, boolean)
- `ts`: Timestamp in milliseconds (`millis()`)
- `uptime`: Uptime in seconds (`millis() / 1000`)
- `heap_free`: Free heap memory in bytes (`ESP.getFreeHeap()`)
- `wifi_rssi`: WiFi signal strength (`WiFi.RSSI()`)
- `sensor_count`: Active sensor count (from `sensorManager.getActiveSensorCount()`)
- `actuator_count`: Active actuator count (from `actuatorManager.getActiveActuatorCount()`)

**Heartbeat Interval:** 60 Sekunden (`HEARTBEAT_INTERVAL_MS = 60000`)

**QoS:** 0 (at most once - heartbeat doesn't need guaranteed delivery)

**Automatic Publishing:** Wird über `MQTTClient::loop()` → `publishHeartbeat()` getriggert wenn verbunden; im normalen Betrieb läuft das im **Communication-Task**, nicht in `main.cpp::loop()`.

---

### Monitoring

#### `void loop()`
**Beschreibung:** MUSS regelmässig aufgerufen werden — im **normalen Betrieb** aus `communication_task.cpp` (Core 0); bei Legacy-Boot ohne RTOS-Tasks aus `main.cpp`.  
**File:** `src/services/communication/mqtt_client.cpp`

**Frequenz:** Jede Iteration (non-blocking)  

**Tatsächliche Implementierung:**

```cpp
void MQTTClient::loop() {
    if (!initialized_) {
        return;
    }
    
    // Process MQTT loop
    if (isConnected()) {
        mqtt_.loop();  // Process incoming messages
        
        // Publish heartbeat (automatic, every 60s)
        publishHeartbeat();
    } else {
        // Attempt reconnection (with exponential backoff)
        reconnect();
    }
}
```

**Verhalten:**
- Prüft Initialisierung (`initialized_` Flag)
- Wenn verbunden:
  - Ruft `mqtt_.loop()` auf (verarbeitet eingehende Messages, ruft Callback auf)
  - Ruft `publishHeartbeat()` auf (automatisch alle 60s)
- Wenn nicht verbunden:
  - Versucht Reconnection via `reconnect()` (mit Exponential Backoff und Circuit Breaker)

**Beispiel (Zusammen mit WiFi — typisch Communication-Task / früher main loop):**
```cpp
void communicationTaskFunction(void* param) {
    wifiManager.loop();
    mqttClient.loop();  // REQUIRED für Heartbeat + NTP (ESP-IDF: kein blockierendes reconnect hier)
    // ...
}
```

**Wichtig:** `MQTTClient::loop()` ist **non-blocking** im ESP-IDF-Pfad (Reconnect im MQTT-Event-Task). Im PubSubClient-Pfad kann Reconnect blockieren — daher SAFETY-RTOS-Trennung.

---

### Status & Monitoring

#### `String getConnectionStatus() const`
**Beschreibung:** Gibt Verbindungsstatus als String zurück  
**Rückgabe:** Status-String ("Connected", "Disconnected", "Connection timeout", etc.)  
**Verhalten:**
- Prüft `mqtt_.connected()`
- Bei Disconnected: Gibt PubSubClient State-String zurück

**Mögliche Werte:**
- "Connected"
- "Connection timeout"
- "Connection lost"
- "Connect failed"
- "Disconnected"
- "Bad protocol"
- "Bad client ID"
- "Server unavailable"
- "Bad credentials"
- "Unauthorized"

---

#### `uint16_t getConnectionAttempts() const`
**Beschreibung:** Gibt Anzahl Reconnect-Versuche zurück  
**Rückgabe:** Anzahl Versuche seit letztem erfolgreichen Connect

---

#### `bool hasOfflineMessages() const`
**Beschreibung:** Prüft ob Messages im Offline-Buffer sind  
**Rückgabe:** `true` wenn Buffer nicht leer

---

#### `uint16_t getOfflineMessageCount() const`
**Beschreibung:** Gibt Anzahl Messages im Offline-Buffer zurück  
**Rückgabe:** Anzahl gepufferter Messages (0-100)

---

## Private Methoden (Intern)

### `bool connectToBroker()`
**Beschreibung:** Interne Methode für Broker-Connection  
**Verhalten:**
- Prüft Anonymous vs. Authenticated Mode
- Ruft `mqtt_.connect()` mit entsprechenden Parametern auf
- Bei Erfolg: Verarbeitet Offline-Buffer
- Bei Fehler: Loggt Fehler mit State-Code

---

### `void handleDisconnection()`
**Beschreibung:** Behandelt Verbindungsabbruch (**nur PubSubClient-Pfad**, z. B. Seeed/Wokwi)
**Verhalten:**
- Ruft immer `offlineModeManager.onDisconnect()` (SAFETY-P4: 30s Grace, State-Machine)
- **Aktoren:** `setAllActuatorsToSafeState()` nur wenn `offlineModeManager.getOfflineRuleCount() == 0`; bei geladenen Offline-Rules bleibt der Zustand unverändert bis P4 `OFFLINE_ACTIVE` und `evaluateOfflineRules()`
- Loggt Disconnection (nur einmal)
- Triggert Reconnection

**Hinweis ESP-IDF:** Bei `MQTT_EVENT_DISCONNECTED` erfolgt kein direkter Aufruf von `handleDisconnection()`; stattdessen `onDisconnect()` auf Core 0 und `NOTIFY_MQTT_DISCONNECTED` an den Safety-Task — gleiche Regel für sofortiges Safe-State vs. Delegation an P4 (`tasks/safety_task.cpp`).

---

### `bool shouldAttemptReconnect() const`
**Beschreibung:** Prüft ob Reconnect erlaubt ist  
**Rückgabe:** `true` wenn Reconnect erlaubt  
**Verhalten:**
- Prüft Max Attempts (10)
- Prüft Backoff-Delay (exponential)

---

### `void processOfflineBuffer()`
**Beschreibung:** Verarbeitet Offline-Buffer nach Reconnection  
**File:** `src/services/communication/mqtt_client.cpp` (lines 468-500)

**Tatsächliche Implementierung:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 473-503)

```cpp
void MQTTClient::processOfflineBuffer() {
    if (offline_buffer_count_ == 0) {
        return;
    }
    
    LOG_INFO("Processing offline buffer (" + String(offline_buffer_count_) + " messages)");
    
    uint16_t processed = 0;
    for (uint16_t i = 0; i < offline_buffer_count_; i++) {
        if (publish(offline_buffer_[i].topic, 
                   offline_buffer_[i].payload, 
                   offline_buffer_[i].qos)) {
            processed++;
        } else {
            // Failed to publish, keep remaining messages in buffer
            break;
        }
    }
    
    // Remove processed messages from buffer
    if (processed > 0) {
        uint16_t remaining = offline_buffer_count_ - processed;
        for (uint16_t i = 0; i < remaining; i++) {
            offline_buffer_[i] = offline_buffer_[i + processed];
        }
        offline_buffer_count_ = remaining;
        
        LOG_INFO("Processed " + String(processed) + " offline messages, " + 
                 String(remaining) + " remaining");
    }
}
```

**Verhalten:**
- Prüft Verbindungsstatus und Buffer-Status
- Sendet gepufferte Messages in FIFO-Reihenfolge (älteste zuerst)
- Bei erfolgreichem Publish: Incrementiert `processed` Counter
- Bei fehlgeschlagenem Publish: Stoppt Verarbeitung (behält restliche Messages)
- Entfernt erfolgreich gesendete Messages aus Buffer (shift remaining messages)
- Aktualisiert `offline_buffer_count_`

**Wichtig:** 
- Verarbeitung stoppt bei erstem Fehler (um Connection-Storm zu vermeiden)
- Restliche Messages bleiben im Buffer für nächsten Reconnect
- Buffer ist FIFO (First-In-First-Out)

---

### `bool addToOfflineBuffer(const String& topic, const String& payload, uint8_t qos)`
**Beschreibung:** Fügt Message zu Offline-Buffer hinzu  
**File:** `src/services/communication/mqtt_client.cpp` (lines 505-521)

**Tatsächliche Implementierung:**

```cpp
bool MQTTClient::addToOfflineBuffer(const String& topic, const String& payload, uint8_t qos) {
    if (offline_buffer_count_ >= MAX_OFFLINE_MESSAGES) {
        LOG_ERROR("Offline buffer full, dropping message");
        errorTracker.logCommunicationError(ERROR_MQTT_BUFFER_FULL, 
                                           "Offline buffer full");
        return false;
    }
    
    offline_buffer_[offline_buffer_count_].topic = topic;
    offline_buffer_[offline_buffer_count_].payload = payload;
    offline_buffer_[offline_buffer_count_].qos = qos;
    offline_buffer_[offline_buffer_count_].timestamp = millis();
    offline_buffer_count_++;
    
    LOG_DEBUG("Added to offline buffer (count: " + String(offline_buffer_count_) + ")");
    return true;
}
```

**Rückgabe:** `true` bei Erfolg, `false` wenn Buffer voll  
**Fehlerbehandlung:**
- Buffer voll (100 Messages) → Loggt Fehler (ERROR_MQTT_BUFFER_FULL)
- Message wird verworfen (nicht gespeichert)
- **Wichtig:** Keine FIFO-Überschreibung - neue Message wird verworfen

**Buffer Capacity:** `MAX_OFFLINE_MESSAGES = 100`

---

### `unsigned long calculateBackoffDelay() const`
**Beschreibung:** Berechnet Exponential Backoff Delay  
**Rückgabe:** Delay in Millisekunden  
**Formel:** `delay = base * (2^attempts)`, capped at max (60s)

---

### `static void staticCallback(char* topic, byte* payload, unsigned int length)`
**Beschreibung:** Static Callback für PubSubClient  
**Verhalten:**
- Konvertiert Topic und Payload zu String
- Ruft User-Callback auf (wenn gesetzt)

---

## Error-Handling

### Connection-Loss
```
1. mqtt_.connected() → false
2. Neue Messages → Offline-Buffer
3. loop() erkennt Disconnection
4. reconnect() wird aufgerufen (Exponential Backoff)
5. Nach Reconnect: processOfflineBuffer()
```

### Circuit Breaker Integration (Phase 6+)

**File:** `src/services/communication/mqtt_client.cpp` (lines 53, 265, 276, 288, 294-297, 309-312, 319-323)

**Configuration:**
```cpp
// Constructor (mqtt_client.cpp:44-58)
circuit_breaker_("MQTT", 5, 30000, 10000)
// - 5 failures → OPEN
// - 30s recovery timeout
// - 10s half-open test timeout
```

**Integration Points:**

1. **Publish Failure:**
```cpp
if (!success) {
    circuit_breaker_.recordFailure();
    if (circuit_breaker_.isOpen()) {
        LOG_WARNING("Circuit Breaker OPENED after failure threshold");
        LOG_WARNING("  MQTT will be unavailable for 30 seconds");
    }
    addToOfflineBuffer(topic, payload, qos);
}
```

2. **Publish Success:**
```cpp
if (success) {
    circuit_breaker_.recordSuccess();
}
```

3. **Connection Check:**
```cpp
if (!isConnected()) {
    circuit_breaker_.recordFailure();  // Connection failure counts
    return addToOfflineBuffer(topic, payload, qos);
}
```

4. **SafePublish with Circuit Breaker:**
```cpp
if (circuit_breaker_.isOpen()) {
    LOG_DEBUG("SafePublish: Circuit Breaker OPEN, skipping retries");
    return publish(topic, payload, qos);  // Single attempt only
}
```

**Behavior:**
- After 5 consecutive failures → Circuit Breaker opens
- All publish attempts blocked for 30 seconds
- After timeout → Half-open state (allows one test request)
- If test succeeds → Circuit Breaker closes (normal operation)
- If test fails → Circuit Breaker opens again (another 30s timeout)

### Publish-Fehler
```
1. publish() fehlgeschlagen
2. LOG_ERROR mit Fehlercode (ERROR_MQTT_PUBLISH_FAILED)
3. Message in Offline-Buffer
```

### Buffer-Overflow
```
1. Offline-Buffer voll (100 Messages)
2. LOG_ERROR (ERROR_MQTT_BUFFER_FULL)
3. Message wird verworfen (return false)
```

### Subscribe-Fehler
```
1. subscribe() fehlgeschlagen
2. LOG_ERROR (ERROR_MQTT_SUBSCRIBE_FAILED)
3. Subscribe wird nicht wiederholt (muss manuell retry)
```

---

## QoS-Handling

| QoS | PubSubClient | ESP32 Verhalten |
|-----|--------------|-----------------|
| 0 | At most once | Fire-and-forget, keine ACK (Heartbeat) |
| 1 | At least once | Wartet auf PUBACK (Sensor Data, Commands) |

**Wichtig:** QoS 2 wird NICHT unterstützt (PubSubClient-Limit)

---

## Thread-Safety

**NICHT Thread-Safe!**
- Alle Methoden müssen vom selben Task aufgerufen werden
- Bei FreeRTOS: Verwende Mutex für Multi-Task-Zugriff
- Callbacks laufen im MQTT-Task-Context

---

## Memory-Management

### Heap-Usage
- Offline-Buffer: ~20KB (100 Messages à ~200 Bytes durchschnittlich)
- PubSubClient-Buffer: Konfigurierbar (default: 256 bytes)
- WiFiClient: ~4KB
- **Gesamt: ~25KB Heap**

### Buffer-Size-Empfehlungen
- Standard (Sensor-Data): PubSubClient default (256 bytes) ist ausreichend
- Große Messages: PubSubClient Buffer kann erhöht werden (nicht in Phase 2)

---

## Verwendungsbeispiel

```cpp
#include "services/communication/mqtt_client.h"
#include "services/communication/wifi_manager.h"
#include "services/config/config_manager.h"

void setup() {
    // ... Phase 1 initialization ...
    
    // WiFi Connection
    wifiManager.begin();
    WiFiConfig wifi_config = configManager.getWiFiConfig();
    wifiManager.connect(wifi_config);
    
    // MQTT Connection
    mqttClient.begin();
    MQTTConfig mqtt_config;
    mqtt_config.server = wifi_config.server_address;
    mqtt_config.port = wifi_config.mqtt_port;
    mqtt_config.client_id = configManager.getESPId();
    mqtt_config.username = wifi_config.mqtt_username;  // Can be empty
    mqtt_config.password = wifi_config.mqtt_password;  // Can be empty
    mqtt_config.keepalive = 60;
    mqtt_config.timeout = 10;
    
    mqttClient.connect(mqtt_config);
    
    // Subscribe to topics (QoS 1 for commands/config, QoS 0 for heartbeat)
    mqttClient.subscribe(TopicBuilder::buildSystemCommandTopic(), 1);
    mqttClient.subscribe(TopicBuilder::buildConfigTopic(), 1);
    mqttClient.subscribe(TopicBuilder::buildBroadcastEmergencyTopic(), 1);
    
    // Set callback
    mqttClient.setCallback([](const String& topic, const String& payload) {
        LOG_INFO("MQTT message received: " + topic);
        // Handle message...
    });
}

void loop() {
    wifiManager.loop();
    mqttClient.loop();  // REQUIRED - processes messages + heartbeat
    
    // Publish sensor data
    String topic = TopicBuilder::buildSensorDataTopic(4);
    String payload = "{\"value\":21.5}";
    mqttClient.publish(topic, payload, 1);
}
```

---

## Integration mit System

### Verwendet von
- `src/main.cpp` → Initialisierung; `mqttClient.loop()` nach vollem Init im **Communication-Task**, sonst Legacy-`loop()`-Zweig
- `src/tasks/communication_task.cpp` → periodischer `mqttClient.loop()` + `processPublishQueue()` (ESP-IDF)
- `services/sensor/sensor_manager.cpp` → Sensor-Data publishing (Phase 4)
- `services/actuator/actuator_manager.cpp` → Actuator-Status/-Response/-Alert publishing + Command subscription (Phase 5)

### Verwendet
- `utils/logger.h` → Logging (Phase 1)
- `utils/topic_builder.h` → Topic-Generierung (Phase 1)
- `error_handling/error_tracker.h` → Error-Logging (Phase 1)
- `services/communication/wifi_manager.h` → WiFi-Verbindung (Phase 2)

---

## Testing-Anforderungen

### Unit-Tests (Phase 2)
1. ✅ `begin()` Initialisierung
2. ✅ `connect()` mit valider Config (Anonymous Mode)
3. ✅ `connect()` mit Authentication
4. ✅ `publish()` bei verbunden → sofort senden
5. ✅ `publish()` bei getrennt → Buffer
6. ✅ `subscribe()` mit Topic
7. ✅ Reconnect nach Connection-Loss
8. ✅ Offline-Buffer Flush nach Reconnect
9. ✅ Buffer-Overflow Handling
10. ✅ Heartbeat Publishing (60s interval)

### Integration-Tests (Phase 2)
1. ✅ End-to-End WiFi → MQTT Flow
2. ✅ Heartbeat Publishing Verification
3. ✅ Message Reception via Callback

---

## Logging

Alle Logs verwenden `utils/logger.h`:

```cpp
LOG_DEBUG("MQTT: Connecting to " + server);
LOG_INFO("MQTT: Connected!");
LOG_WARNING("MQTT: Reconnecting...");
LOG_ERROR("MQTT: Publish failed: " + topic);
LOG_CRITICAL("MQTT: Max reconnection attempts reached");
```

---

## Error Codes (from error_codes.h)

```cpp
ERROR_MQTT_INIT_FAILED = 3010       // MQTT initialization failed
ERROR_MQTT_CONNECT_FAILED = 3011    // MQTT connection failed
ERROR_MQTT_PUBLISH_FAILED = 3012    // MQTT publish failed
ERROR_MQTT_SUBSCRIBE_FAILED = 3013  // MQTT subscribe failed
ERROR_MQTT_DISCONNECT = 3014        // MQTT disconnected
ERROR_MQTT_BUFFER_FULL = 3015       // MQTT buffer overflow
ERROR_MQTT_PAYLOAD_INVALID = 3016   // MQTT payload invalid
```

---

**Status:** ✅ API vollständig implementiert (Phase 2) - Verwendet in Phase 4 & 5  
**Implementierungszeit:** ~10 Tage (wie geplant)  
**Komplexität:** Mittel-Hoch (PubSubClient + Offline-Buffer + Heartbeat)  
**Code-Qualität:** Industrial-Grade (follows Phase 1 patterns)  
**Phase 5 Integration:** Wird für Actuator-MQTT-Communication verwendet (keine API-Änderungen)

---

## Performance Guidelines

### Loop-Call Requirements

**CRITICAL:** `mqttClient.loop()` MUSS regelmässig laufen — nach **SAFETY-RTOS M3** im **Communication-Task** (`communication_task.cpp`, typisch alle 50 ms operational), nicht in `main.cpp::loop()`. Sensor-/Aktor-Arbeit läuft im **Safety-Task** (`safety_task.cpp`).

**Frequenz-Requirements:**
- **Minimum:** 10 Hz (alle 100ms) für reliable Message-Processing
- **Empfohlen:** 20-50 Hz (alle 20-50ms) für responsive Command-Handling
- **Maximum:** 100+ Hz (alle 10ms) möglich, aber unnötig (kein Performance-Vorteil)

**Timing-Verhalten:**
- **QoS 0:** Non-blocking, sofortiger Return (~<1ms)
- **QoS 1:** Wartet auf PUBACK (typisch 5-50ms, max 5s Timeout)
- **Callback:** MQTT-Event-/PubSub-Context — MUSS schnell sein, nicht blockierend

**Best Practice (aktuell):**
```cpp
// Communication-Task (Core 0) — siehe communication_task.cpp
wifiManager.loop();
mqttClient.loop();
// processPublishQueue() wenn MQTT_USE_ESP_IDF

// Safety-Task (Core 1) — Sensoren/Aktoren, nicht in mqttClient.loop()
```

**Warnung:** Lange Callback-Operationen (>100ms) blockieren MQTT-Processing! Schweres Arbeiten liegt im Safety-Task oder in Queues.

---

### Payload-Size Limits

**PubSubClient Default:** 256 bytes max payload size (MQTT_MAX_PACKET_SIZE)

**Praktische Payload-Größen (Phase 5):**

| Message-Type | Typical Size | Max Size | Status |
|--------------|--------------|----------|--------|
| `sensor/data` | 150-200 bytes | 256 bytes | ✅ OK |
| `actuator/status` | 120-180 bytes | 256 bytes | ✅ OK |
| `actuator/response` | 150 bytes | 256 bytes | ✅ OK |
| `actuator/alert` | 100 bytes | 256 bytes | ✅ OK |
| `heartbeat` | 180 bytes | 256 bytes | ✅ OK |
| `config` (5 actuators) | 800+ bytes | 256 bytes | ❌ OVERFLOW |

**Config-Overflow-Problem:**
- Config mit >3 Aktoren überschreitet 256 bytes
- **Workaround (Phase 5):** Max 2-3 Aktoren pro Config-Message
- **Lösung (Phase 6+):** `MQTT_MAX_PACKET_SIZE` erhöhen oder Config fragmentieren

**Buffer-Size-Erhöhung (Optional):**
```cpp
// In platformio.ini:
build_flags = 
    -DMQTT_MAX_PACKET_SIZE=1024    // 1KB Payload-Limit (nicht in Phase 5)
```

**Memory-Impact:** +768 bytes Heap pro vergrößertes Paket

**Empfehlung Phase 5:** Behalte 256 bytes, fragmentiere große Configs manuell.
