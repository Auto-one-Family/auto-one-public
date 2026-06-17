# Safety-Pattern-Ökosystem Analyse - AutomationOne

**Erstellt:** 2026-01-30
**Analyst:** Claude System-Architekt
**Version:** 1.0
**Status:** VOLLSTÄNDIG

---

## Executive Summary

### Wichtigste Erkenntnisse

1. **5 ESP32-Safety-Module** vollständig analysiert:
   - Circuit Breaker (WiFi + MQTT geschützt)
   - Watchdog (Industrial-Grade mit 3 Modi)
   - Error Tracker (Circular Buffer, MQTT-Publishing)
   - Health Monitor (Diagnostics mit Watchdog-Status)
   - Safety Controller (Emergency-Stop, Subzone-Isolation)

2. **Server-seitige Resilience** spiegelt ESP32-Patterns:
   - Circuit Breaker für MQTT, Database, External API
   - ResilienceRegistry als Singleton für zentrale Verwaltung
   - Async-Support mit Thread-Safety (asyncio.Lock)

3. **Kritische Integration:** Watchdog ↔ Circuit Breaker
   - WiFi Circuit Breaker OPEN → Watchdog-Feed blockiert (ERROR_WATCHDOG_FEED_BLOCKED)
   - MQTT Circuit Breaker OPEN → Rate-Limited Warning (kein Feed-Block)
   - Health Monitor publiziert Watchdog-Status alle 60s

4. **Anzahl analysierter Dateien:** 19 Kern-Dateien
5. **Code-Qualität:** Production-Ready (Industrial-Grade)

---

## 1. System-Kontext

### 1.1 4-Layer-Architektur verstanden

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: God-Kaiser (Raspberry Pi 5)                        │
│ - Single Source of Truth                                    │
│ - Server-seitige Resilience (CircuitBreaker, Retry, Timeout)│
│ - MQTT Handler mit Error-Isolation                          │
└─────────────────────────────────────────────────────────────┘
                          ↕ MQTT (TLS)
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: ESP32-Agenten ("El Trabajante")                    │
│ - ESP-seitige Safety-Patterns                               │
│ - Watchdog, Circuit Breaker, Error Tracker                  │
│ - Health Monitor, Safety Controller                         │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Server-Centric-Prinzip

- **ESP32:** "Dumme" Datensammler, senden RAW-Daten
- **Server:** Alle Business-Logik, Processing, Storage
- **Safety-Patterns:** Beide Seiten haben unabhängige, aber koordinierte Patterns

---

## 2. ESP32 Safety-Module

### 2.1 Circuit Breaker

**Location:** `El Trabajante/src/error_handling/circuit_breaker.h/.cpp`

#### 2.1.1 Struktur & API

```cpp
// States (circuit_breaker.h:9-13)
enum class CircuitState : uint8_t {
  CLOSED = 0,      // Normal operation, requests allowed
  OPEN,            // Service failed, requests blocked
  HALF_OPEN        // Testing recovery, limited requests allowed
};

// Constructor (circuit_breaker.h:53-56)
CircuitBreaker(const char* service_name,
               uint8_t failure_threshold = 5,
               unsigned long recovery_timeout_ms = 30000,
               unsigned long halfopen_timeout_ms = 10000);

// Public API (circuit_breaker.h:67-122)
bool allowRequest();          // Check if request allowed
void recordSuccess();         // Record success, reset failures
void recordFailure();         // Record failure, may trigger OPEN
void reset();                 // Manual reset to CLOSED

// Status Queries
bool isOpen() const;
bool isClosed() const;
CircuitState getState() const;
uint8_t getFailureCount() const;
const char* getServiceName() const;
```

#### 2.1.2 States & Transitions

| From | To | Condition | Code Location |
|------|-----|-----------|---------------|
| CLOSED | OPEN | `failure_count >= failure_threshold` | circuit_breaker.cpp:103-108 |
| OPEN | HALF_OPEN | `time_since_open >= recovery_timeout_ms` | circuit_breaker.cpp:43-46 |
| HALF_OPEN | CLOSED | `recordSuccess()` aufgerufen | circuit_breaker.cpp:76-80 |
| HALF_OPEN | OPEN | `recordFailure()` aufgerufen ODER Timeout | circuit_breaker.cpp:114-117, 58-61 |

```
┌────────┐  failure >= threshold  ┌────────┐
│ CLOSED │ ────────────────────→  │  OPEN  │
│        │                        │        │
└────────┘                        └────────┘
    ↑                                  │
    │ recordSuccess()                  │ recovery_timeout elapsed
    │                                  ↓
    └─────────────────────────── ┌───────────┐
                                 │ HALF_OPEN │
                                 └───────────┘
                                      │
                    recordFailure()   │
                    ─────────────────→ OPEN
```

#### 2.1.3 Konfiguration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `failure_threshold` | 5 | Anzahl Fehler bis OPEN |
| `recovery_timeout_ms` | 30000 | Zeit in OPEN vor HALF_OPEN Test (30s) |
| `halfopen_timeout_ms` | 10000 | Maximale Zeit in HALF_OPEN (10s) |

**Konfiguration zur Compile-Time im Konstruktor.**

#### 2.1.4 Instanzen & Services

| Service | Location | Failure Threshold | Recovery | Half-Open | Code |
|---------|----------|-------------------|----------|-----------|------|
| **WiFi** | wifi_manager.cpp:35 | 10 | 60s | 15s | `circuit_breaker_("WiFi", 10, 60000, 15000)` |
| **MQTT** | mqtt_client.cpp:55 | 5 | 30s | 10s | `circuit_breaker_("MQTT", 5, 30000, 10000)` |

**WiFi hat höhere Toleranz:** 10 Fehler (vs. 5 bei MQTT) weil WiFi-Verbindungen länger brauchen und mehr Variabilität haben.

#### 2.1.5 Integrationen

| Modul | Integration | Direction | Description |
|-------|-------------|-----------|-------------|
| Watchdog | main.cpp:1500-1530 | CB → WD | WiFi CB OPEN blockiert Watchdog-Feed |
| WiFiManager | wifi_manager.h:55 | Member | Interne CB-Instanz für WiFi-Verbindungen |
| MQTTClient | mqtt_client.h:117 | Member | Interne CB-Instanz für MQTT-Verbindungen |
| HealthMonitor | health_monitor.cpp:104 | Query | Liest CB-States für Diagnostics |

#### 2.1.6 MQTT-Interaktion

**Circuit Breaker selbst publiziert NICHT auf MQTT.** States werden via:
- HealthMonitor: `healthMonitor.getCurrentSnapshot()` enthält CB-States
- Watchdog Diagnostics: `WatchdogDiagnostics.wifi_breaker_state`, `mqtt_breaker_state`

#### 2.1.7 Error-Handling

| Situation | Error Code | Tracked In |
|-----------|------------|------------|
| WiFi CB blocks WD feed | ERROR_WATCHDOG_FEED_BLOCKED (4071) | ErrorTracker |
| State transitions | Logged via LOG_INFO/LOG_WARNING | Logger |

---

### 2.2 Watchdog

**Location:** `El Trabajante/src/models/watchdog_types.h` + `El Trabajante/src/main.cpp`

#### 2.2.1 Struktur & API

```cpp
// Watchdog Modes (watchdog_types.h:12-17)
enum class WatchdogMode : uint8_t {
    WDT_DISABLED = 0,  // No watchdog (WOKWI simulation)
    PROVISIONING,      // Relaxed watchdog (300s timeout, no panic)
    PRODUCTION,        // Strict watchdog (60s timeout, panic=true)
    SAFE_MODE          // Extended timeout (120s timeout, no panic)
};

// Configuration (watchdog_types.h:22-33)
struct WatchdogConfig {
    WatchdogMode mode;
    unsigned long timeout_ms;
    unsigned long feed_interval_ms;
    bool panic_enabled;
};

// Diagnostics (watchdog_types.h:38-62)
struct WatchdogDiagnostics {
    unsigned long last_feed_time;
    const char* last_feed_component;
    uint32_t feed_count;
    unsigned long timestamp;
    SystemState system_state;
    CircuitState wifi_breaker_state;   // ← Integration mit CB!
    CircuitState mqtt_breaker_state;   // ← Integration mit CB!
    size_t error_count;
    uint32_t heap_free;
};

// Global State (watchdog_types.h:67-69)
extern WatchdogConfig g_watchdog_config;
extern WatchdogDiagnostics g_watchdog_diagnostics;
extern volatile bool g_watchdog_timeout_flag;

// API Functions (watchdog_types.h:79-90)
bool feedWatchdog(const char* component_id);
void handleWatchdogTimeout();
uint8_t getWatchdogCountLast24h();
```

#### 2.2.2 Watchdog-Typ

**Simple Watchdog mit Conditional Feeds:**
- Timeout-basiert (nicht Window-Watchdog)
- Feed wird blockiert wenn Circuit Breaker OPEN (Production Mode)
- ESP32 Task WDT wird genutzt (`esp_task_wdt_reset()`)

#### 2.2.3 Modi & Konfiguration

| Mode | Timeout | Feed Interval | Panic | Use Case |
|------|---------|---------------|-------|----------|
| WDT_DISABLED | 0 | 0 | false | Wokwi Simulation |
| PROVISIONING | 300s (5min) | 60s | false | AP-Mode Setup |
| PRODUCTION | 60s | 10s | true | Normal Operation |
| SAFE_MODE | 120s | - | false | Recovery (geplant) |

**Mode-Auswahl:** main.cpp:365-397
- Wenn `needsProvisioning()` → PROVISIONING
- Sonst → PRODUCTION

#### 2.2.4 Feed-Mechanismus

**feedWatchdog() Implementation (main.cpp:1496-1554):**

```cpp
bool feedWatchdog(const char* component_id) {
  // 1. Circuit Breaker Check (nur in Production Mode)
  if (g_watchdog_config.mode == WatchdogMode::PRODUCTION) {
    // WiFi CB OPEN? → BLOCK FEED! (kritisch)
    if (wifiManager.getCircuitBreakerState() == CircuitState::OPEN) {
      errorTracker.logApplicationError(ERROR_WATCHDOG_FEED_BLOCKED, ...);
      return false;  // ← Feed blockiert!
    }
    // MQTT CB OPEN? → Warning only (nicht kritisch)
    if (mqttClient.getCircuitBreakerState() == CircuitState::OPEN) {
      // Rate-limited warning, feed NOT blocked
    }
  }

  // 2. Critical Errors Check
  if (errorTracker.hasCriticalErrors()) {
    errorTracker.logApplicationError(ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL, ...);
    return false;  // ← Feed blockiert!
  }

  // 3. Actually feed the watchdog
  esp_task_wdt_reset();

  // 4. Update Diagnostics
  g_watchdog_diagnostics.last_feed_time = millis();
  g_watchdog_diagnostics.last_feed_component = component_id;
  g_watchdog_diagnostics.feed_count++;

  return true;
}
```

**Feed-Aufruf in loop() (main.cpp:1639-1650):**
```cpp
if (g_watchdog_config.mode != WatchdogMode::WDT_DISABLED) {
  if (millis() - last_feed_time >= g_watchdog_config.feed_interval_ms) {
    if (feedWatchdog("MAIN_LOOP")) {
      last_feed_time = millis();
    }
  }
}
```

#### 2.2.5 Timeout-Handling

**handleWatchdogTimeout() (main.cpp:1560-1617):**

1. Track Critical Error (ERROR_WATCHDOG_TIMEOUT)
2. Collect Diagnostics (System State, CB States, Error Count, Heap)
3. Persist to NVS (für Post-Reboot-Analyse)
4. Publish Emergency MQTT (wenn möglich)
5. Mode-spezifische Aktion:
   - **PRODUCTION:** Panic → ESP Reset
   - **PROVISIONING:** Kein Panic, nur Safe-Mode Entry

#### 2.2.6 Integration mit Circuit Breaker

**KRITISCH:** Watchdog-Feed wird NUR blockiert wenn:
1. **WiFi Circuit Breaker OPEN** (Production Mode) → ERROR_WATCHDOG_FEED_BLOCKED (4071)
2. **Critical Errors aktiv** → ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL (4072)

**MQTT Circuit Breaker OPEN blockiert NICHT** den Watchdog-Feed (nur Warning).

**Rationale:**
- WiFi-Ausfall = ESP kann gar nichts tun → Reboot sinnvoll
- MQTT-Ausfall = ESP kann lokal weiter operieren → Kein Reboot nötig

#### 2.2.7 Modi (Provisioning vs Production)

| Aspekt | PROVISIONING | PRODUCTION |
|--------|--------------|------------|
| Timeout | 300s | 60s |
| Feed Interval | 60s | 10s |
| Panic | false | true |
| CB-Check | Nein | Ja |
| Use Case | AP-Mode, Setup | Normal Operation |

---

### 2.3 Error Tracker

**Location:** `El Trabajante/src/error_handling/error_tracker.h/.cpp`

#### 2.3.1 Struktur & API

```cpp
// Categories (error_tracker.h:9-14)
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM
  ERROR_SERVICE = 2000,        // Sensor, Actuator, Config
  ERROR_COMMUNICATION = 3000,  // MQTT, HTTP, WiFi
  ERROR_APPLICATION = 4000     // State, Memory, System
};

// Severity (error_tracker.h:19-23)
enum ErrorSeverity {
  ERROR_SEVERITY_WARNING = 1,
  ERROR_SEVERITY_ERROR = 2,
  ERROR_SEVERITY_CRITICAL = 3
};

// Entry Structure (error_tracker.h:28-41)
struct ErrorEntry {
  unsigned long timestamp;
  uint16_t error_code;
  ErrorSeverity severity;
  char message[128];
  uint8_t occurrence_count;  // Duplicate tracking
};

// Primary API (error_tracker.h:63-71)
void trackError(uint16_t error_code, ErrorSeverity severity, const char* message);
void logHardwareError(uint16_t code, const char* message);
void logServiceError(uint16_t code, const char* message);
void logCommunicationError(uint16_t code, const char* message);
void logApplicationError(uint16_t code, const char* message);

// Retrieval (error_tracker.h:73-81)
String getErrorHistory(uint8_t max_entries = 20) const;
size_t getErrorCount() const;
bool hasActiveErrors() const;
bool hasCriticalErrors() const;
void clearErrors();

// MQTT Publishing (error_tracker.h:109-114)
void setMqttPublishCallback(MqttErrorPublishCallback callback, const String& esp_id);
void clearMqttPublishCallback();
```

#### 2.3.2 Error-Categories & Severities

| Range | Category | Examples |
|-------|----------|----------|
| 1000-1999 | HARDWARE | GPIO, I2C, OneWire, PWM, Sensor, Actuator |
| 2000-2999 | SERVICE | NVS, Config, Logger, Storage, Subzone |
| 3000-3999 | COMMUNICATION | WiFi, MQTT, HTTP, Network |
| 4000-4999 | APPLICATION | State, Operation, Command, Payload, Memory, System, Task, Watchdog |

| Severity | Value | Behandlung |
|----------|-------|------------|
| WARNING | 1 | Recoverable, logged |
| ERROR | 2 | Error but system continues |
| CRITICAL | 3 | System unstable, blocks WD feed |

#### 2.3.3 History-Management

- **Circular Buffer:** 50 Einträge (MAX_ERROR_ENTRIES)
- **FIFO:** Älteste Einträge werden überschrieben
- **Duplicate Tracking:** Letzte 5 Einträge werden auf Duplikate geprüft, `occurrence_count` wird erhöht
- **Code:** error_tracker.cpp:184-213

#### 2.3.4 Integrationen

| Modul | Integration | Code Location |
|-------|-------------|---------------|
| Watchdog | `hasCriticalErrors()` blockiert Feed | main.cpp:1530-1545 |
| HealthMonitor | `getErrorCount()` in Snapshot | health_monitor.cpp:83 |
| SafetyController | Error-Tracking bei Emergency | safety_controller.cpp:73-82 |
| All Managers | Fehler werden via `logXxxError()` gemeldet | Überall |

#### 2.3.5 MQTT-Interaktion

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/error` (via TopicBuilder)

**Payload (error_tracker.cpp:310-334):**
```json
{
  "error_code": 1020,
  "severity": 2,
  "category": "HARDWARE",
  "message": "Sensor read failed",
  "context": {"esp_id": "ESP_12AB34", "uptime_ms": 123456},
  "ts": 1735818000
}
```

**Recursion Protection:** `mqtt_publish_in_progress_` Flag verhindert endlose Rekursion wenn MQTT-Publish selbst fehlschlägt.

---

### 2.4 Health Monitor

**Location:** `El Trabajante/src/error_handling/health_monitor.h/.cpp`

#### 2.4.1 Struktur & API

```cpp
// Snapshot Structure (health_monitor.h:11-35)
struct HealthSnapshot {
    unsigned long timestamp;
    uint32_t heap_free;
    uint32_t heap_min_free;
    uint8_t heap_fragmentation_percent;
    unsigned long uptime_seconds;
    size_t error_count;
    bool wifi_connected;
    int8_t wifi_rssi;
    bool mqtt_connected;
    uint8_t sensor_count;
    uint8_t actuator_count;
    SystemState system_state;

    // Watchdog Status (Industrial-Grade)
    WatchdogMode watchdog_mode;
    unsigned long watchdog_timeout_ms;
    unsigned long last_watchdog_feed;
    const char* last_feed_component;
    uint32_t watchdog_feed_count;
    uint8_t watchdog_timeouts_24h;
    bool watchdog_timeout_pending;
};

// API (health_monitor.h:46-67)
HealthSnapshot getCurrentSnapshot() const;
String getSnapshotJSON() const;
void publishSnapshot();
void publishSnapshotIfChanged();
void loop();  // Call in main loop
void setPublishInterval(unsigned long interval_ms);
void setChangeDetectionEnabled(bool enabled);
```

#### 2.4.2 Snapshot-Struktur (Details)

| Feld | Typ | Quelle | Beschreibung |
|------|-----|--------|--------------|
| `timestamp` | unsigned long | `millis()/1000` | Uptime in Sekunden |
| `heap_free` | uint32_t | `ESP.getFreeHeap()` | Aktueller freier Heap |
| `heap_min_free` | uint32_t | `ESP.getMinFreeHeap()` | Minimum seit Boot |
| `heap_fragmentation_percent` | uint8_t | Berechnet | `(free - min_free) / free * 100` |
| `uptime_seconds` | unsigned long | `millis()/1000` | System-Uptime |
| `error_count` | size_t | ErrorTracker | Anzahl Fehler im Buffer |
| `wifi_connected` | bool | WiFiManager | WiFi-Status |
| `wifi_rssi` | int8_t | WiFiManager | Signal-Stärke |
| `mqtt_connected` | bool | MQTTClient | MQTT-Status |
| `sensor_count` | uint8_t | SensorManager | Aktive Sensoren |
| `actuator_count` | uint8_t | ActuatorManager | Aktive Aktoren |
| `system_state` | SystemState | g_system_config | STATE_OPERATIONAL etc. |
| `watchdog_mode` | WatchdogMode | g_watchdog_config | PRODUCTION etc. |
| `watchdog_timeout_ms` | unsigned long | g_watchdog_config | Aktueller Timeout |
| `last_watchdog_feed` | unsigned long | g_watchdog_diagnostics | Letzter Feed Timestamp |
| `last_feed_component` | const char* | g_watchdog_diagnostics | "MAIN_LOOP" etc. |
| `watchdog_feed_count` | uint32_t | g_watchdog_diagnostics | Feeds seit Boot |
| `watchdog_timeouts_24h` | uint8_t | `getWatchdogCountLast24h()` | Timeouts in 24h |
| `watchdog_timeout_pending` | bool | g_watchdog_timeout_flag | Timeout aktiv? |

#### 2.4.3 Publishing-Mechanismus

- **Intervall:** 60 Sekunden (Default, konfigurierbar)
- **Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/diagnostics`
- **Change Detection:** Publish bei signifikanten Änderungen:
  - Heap-Änderung > 20%
  - RSSI-Änderung > 10 dBm
  - Connection Status Change (WiFi/MQTT)
  - Sensor/Actuator Count Change
  - System State Change
  - Error Count Change > 5

**Code:** health_monitor.cpp:150-195 (hasSignificantChanges)

#### 2.4.4 Server-Verarbeitung

- **Handler:** HeartbeatHandler verarbeitet ESP-Health
- **Storage:** ESP-Device-Status wird in DB aktualisiert
- **WebSocket:** Broadcast an Frontend für Live-Updates

---

### 2.5 Safety Controller

**Location:** `El Trabajante/src/services/actuator/safety_controller.h/.cpp`

#### 2.5.1 Struktur & API

```cpp
// Emergency States (actuator_types.h:10-15)
enum class EmergencyState : uint8_t {
  EMERGENCY_NORMAL = 0,
  EMERGENCY_ACTIVE,
  EMERGENCY_CLEARING,
  EMERGENCY_RESUMING
};

// Recovery Config (actuator_types.h:103-108)
struct RecoveryConfig {
  uint32_t inter_actuator_delay_ms = 2000;
  bool critical_first = true;
  uint32_t verification_timeout_ms = 5000;
  uint8_t max_retry_attempts = 3;
};

// API (safety_controller.h:12-32)
bool emergencyStopAll(const String& reason);
bool emergencyStopActuator(uint8_t gpio, const String& reason);
bool isolateSubzone(const String& subzone_id, const String& reason);  // Phase 9
bool clearEmergencyStop();
bool clearEmergencyStopActuator(uint8_t gpio);
bool resumeOperation();
bool isEmergencyActive() const;
bool isEmergencyActive(uint8_t gpio) const;
EmergencyState getEmergencyState() const;
void setRecoveryConfig(const RecoveryConfig& config);
String getEmergencyReason() const;
String getRecoveryProgress() const;
```

#### 2.5.2 Emergency-Stop-Mechanismus

**emergencyStopAll() (safety_controller.cpp:40-51):**
1. Set `emergency_state_` to `EMERGENCY_ACTIVE`
2. Store reason and timestamp
3. Log emergency event
4. Delegate to `actuatorManager.emergencyStopAll()`

**emergencyStopActuator() (safety_controller.cpp:53-64):**
- Gleicher Flow, aber für einzelnen GPIO

#### 2.5.3 Subzone-Isolation (Phase 9)

**isolateSubzone() (safety_controller.cpp:66-86):**
1. Log Warning
2. Enable Safe-Mode für alle Pins der Subzone via `gpioManager.enableSafeModeForSubzone(subzone_id)`
3. Track Error (ERROR_SUBZONE_SAFE_MODE_FAILED)
4. Return success/failure

**Use Case:** Wenn ein Teil des Systems (Subzone) fehlschlägt, wird nur diese Subzone isoliert, nicht das ganze System.

#### 2.5.4 State Transitions

```
┌────────────────┐  emergencyStop()  ┌──────────────────┐
│ EMERGENCY_     │ ───────────────→  │ EMERGENCY_ACTIVE │
│ NORMAL         │                   │                  │
└────────────────┘                   └──────────────────┘
       ↑                                     │
       │ resumeOperation()                   │ clearEmergencyStop()
       │                                     ↓
       │                            ┌───────────────────┐
       │                            │ EMERGENCY_CLEARING │
       │                            └───────────────────┘
       │                                     │
       │                                     │ verifySystemSafety()
       │                                     ↓
       │                            ┌───────────────────┐
       └──────────────────────────  │ EMERGENCY_RESUMING │
                                    └───────────────────┘
```

#### 2.5.5 Integrationen

| Modul | Integration | Code Location |
|-------|-------------|---------------|
| ActuatorManager | Delegiert Stop/Clear | safety_controller.cpp:50,96 |
| GPIOManager | Subzone Safe-Mode | safety_controller.cpp:71 |
| ErrorTracker | Error-Logging | safety_controller.cpp:73-82 |

#### 2.5.6 Integration mit Watchdog

**Aktuell:** SafetyController wird NICHT automatisch bei Watchdog-Timeout aufgerufen.

**handleWatchdogTimeout() (main.cpp:1560-1617):**
- Publiziert Emergency MQTT, ruft aber NICHT `safetyController.emergencyStopAll()` auf
- ESP wird stattdessen neu gestartet (Production Mode)

**Empfehlung:** Bei PROVISIONING/SAFE_MODE könnte `emergencyStopAll()` vor Safe-Mode-Entry sinnvoll sein.

---

## 3. Server-seitige Resilience

### 3.1 ResilienceSettings

**Location:** `El Servador/god_kaiser_server/src/core/config.py:578-680`

#### Circuit Breaker Konfiguration

| Service | Failure Threshold | Recovery Timeout | Half-Open Timeout | Env Variable |
|---------|-------------------|------------------|-------------------|--------------|
| **MQTT** | 5 | 30s | 10s | `CIRCUIT_BREAKER_MQTT_*` |
| **Database** | 3 | 10s | 5s | `CIRCUIT_BREAKER_DB_*` |
| **External API** | 5 | 60s | 15s | `CIRCUIT_BREAKER_API_*` |

**Note:** Database hat niedrigere Toleranz (3 Fehler) weil DB-Ausfälle kritischer sind.

#### Retry Configuration

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `retry_max_attempts` | 3 | 1-10 | Max Retry-Versuche |
| `retry_base_delay` | 1.0s | 0.1-10 | Basis-Delay für Exponential Backoff |

### 3.2 Circuit Breaker (Server)

**Location:** `El Servador/god_kaiser_server/src/core/resilience/circuit_breaker.py`

#### Struktur

```python
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_timeout: float = 10.0
    half_open_max_requests: int = 1
    success_threshold: int = 1

class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, recovery_timeout=30.0, ...):
        ...

    def allow_request(self) -> bool:           # Sync version
    async def allow_request_async(self) -> bool:  # Async version with state transitions
    def record_success(self) -> None:
    def record_failure(self) -> None:
    def reset(self) -> None:
    def force_open(self) -> None:              # For testing
    def get_state(self) -> CircuitState:
    def get_metrics(self) -> dict:
```

**Thread-Safety:** `asyncio.Lock` für async Code (circuit_breaker.py:125)

**Decorator:** `@circuit_breaker_decorator("breaker_name")` für einfache Integration

### 3.3 ResilienceRegistry

**Location:** `El Servador/god_kaiser_server/src/core/resilience/registry.py`

```python
class ResilienceRegistry:
    """Singleton registry for managing resilience components."""

    @classmethod
    def get_instance(cls) -> "ResilienceRegistry":

    def register_circuit_breaker(self, name: str, breaker: CircuitBreaker):
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
    def get_health_status(self) -> Dict[str, Any]:  # Aggregated health
    def get_metrics(self) -> Dict[str, Any]:
    def reset(self, name: str) -> bool:
    def reset_all(self) -> int:
    def force_open(self, name: str) -> bool:
```

### 3.4 ESP-Health-Verarbeitung

| Handler | Location | Funktion |
|---------|----------|----------|
| HeartbeatHandler | `mqtt/handlers/heartbeat_handler.py` | ESP-Heartbeat verarbeiten, DB-Status aktualisieren |
| LWTHandler | `mqtt/handlers/lwt_handler.py` | Last Will Testament, instant offline detection |

---

## 4. Integrations-Analyse

### 4.1 ESP32-interne Integration-Matrix

```
                  Circuit   Error    Health   Safety   Watchdog
                  Breaker   Tracker  Monitor  Ctrl
Circuit Breaker      -        ←        ←        -        →
Error Tracker        →        -        →        ←        ←
Health Monitor       →        →        -        -        →
Safety Controller    -        →        -        -        -
Watchdog             ←        →        ←        -        -
```

**Legende:** → nutzt | ← wird genutzt von | - keine direkte Integration

#### Detaillierte Erklärung

| Integration | Direction | Beschreibung | Code Location |
|-------------|-----------|--------------|---------------|
| CB → WD | Watchdog nutzt CB | WiFi CB OPEN blockiert WD-Feed | main.cpp:1502 |
| WD → ET | Watchdog nutzt ErrorTracker | Fehler bei blockiertem Feed | main.cpp:1503-1505 |
| HM → CB | HealthMonitor liest CB | CB-States in Diagnostics | health_monitor.cpp:102-103 |
| HM → ET | HealthMonitor liest ErrorTracker | Error-Count in Snapshot | health_monitor.cpp:83 |
| HM → WD | HealthMonitor liest Watchdog | WD-Status in Snapshot | health_monitor.cpp:99-108 |
| SC → ET | SafetyController nutzt ErrorTracker | Error-Logging bei Emergency | safety_controller.cpp:73-82 |
| ET → CB | ErrorTracker wird von CB-Events getriggert | Indirekt via Manager-Fehler | wifi_manager.cpp, mqtt_client.cpp |

### 4.2 ESP32 ↔ Server Integration

#### Health-Data-Flow

```
┌───────────────┐     MQTT Topic                    ┌──────────────────┐
│ HealthMonitor │ ─────────────────────────────────→│ HeartbeatHandler │
│ (ESP32)       │  kaiser/{kaiser}/esp/{esp}/       │ (Server)         │
│               │  system/diagnostics               │                  │
└───────────────┘                                   └──────────────────┘
                                                            │
                                                            ↓
                                                    ┌──────────────────┐
                                                    │ ESP Repository   │
                                                    │ (DB Update)      │
                                                    └──────────────────┘
                                                            │
                                                            ↓
                                                    ┌──────────────────┐
                                                    │ WebSocket        │
                                                    │ (Frontend)       │
                                                    └──────────────────┘
```

#### Error-Reporting-Flow

```
┌───────────────┐     MQTT Topic                    ┌──────────────────┐
│ ErrorTracker  │ ─────────────────────────────────→│ Error Handler?   │
│ (ESP32)       │  kaiser/{kaiser}/esp/{esp}/       │ (Server)         │
│               │  system/error                     │                  │
└───────────────┘                                   └──────────────────┘
```

**Note:** Kein dedizierter Error-Handler auf Server-Seite gefunden. Errors werden möglicherweise nur geloggt.

#### Circuit Breaker Koordination

**ESP32 und Server haben UNABHÄNGIGE Circuit Breakers:**
- ESP32: WiFi CB, MQTT CB (lokal für Reconnect-Schutz)
- Server: MQTT CB, DB CB, API CB (für Handler/Service-Schutz)

**Keine direkte Koordination** zwischen ESP32 und Server Circuit Breakers.

#### Watchdog-Events auf Server

**Der Server erfährt von Watchdog-Timeouts durch:**
1. **LWT (Last Will Testament):** Bei ESP-Disconnect wird LWT-Message publiziert → LWTHandler
2. **Nach Reboot:** ESP sendet neuen Heartbeat mit Reset-Reason `ESP_RST_TASK_WDT`
3. **Optional:** Emergency MQTT vor Timeout (wenn MQTT noch funktioniert)

---

## 5. Entdeckte zusätzliche Patterns

### 5.1 Exponential Backoff

**Location:** mqtt_client.cpp (calculateBackoffDelay)

```cpp
const unsigned long RECONNECT_BASE_DELAY_MS = 1000;   // 1 second
const unsigned long RECONNECT_MAX_DELAY_MS = 60000;   // 60 seconds

// Backoff: 1s → 2s → 4s → 8s → ... → 60s max
unsigned long MQTTClient::calculateBackoffDelay() const {
    return min(RECONNECT_BASE_DELAY_MS * (1 << reconnect_attempts_),
               RECONNECT_MAX_DELAY_MS);
}
```

### 5.2 Offline Buffer Pattern

**Location:** mqtt_client.h:98-100

```cpp
static const uint16_t MAX_OFFLINE_MESSAGES = 100;
MQTTMessage offline_buffer_[MAX_OFFLINE_MESSAGES];
uint16_t offline_buffer_count_;
```

Messages werden gepuffert wenn MQTT offline, und bei Reconnect nachgesendet.

### 5.3 Rate-Limited Warnings

**Location:** main.cpp:1516-1524

```cpp
static unsigned long last_mqtt_cb_warning = 0;
if (millis() - last_mqtt_cb_warning > 10000) {  // Max once per 10 seconds
    LOG_WARNING("MQTT CB OPEN - degraded mode, WD feed continues");
    last_mqtt_cb_warning = millis();
}
```

### 5.4 GPIO Safe-Mode Pattern

**Location:** gpio_manager.h/.cpp

Alle GPIO-Pins werden beim Boot als `INPUT_PULLUP` initialisiert (Safe-Mode). Erst nach expliziter Reservierung werden sie für Sensoren/Aktoren konfiguriert.

### 5.5 Singleton-Pattern (überall)

Alle Manager sind Singletons mit `getInstance()`:
- WiFiManager, MQTTClient, SensorManager, ActuatorManager
- ConfigManager, GPIOManager, ErrorTracker, HealthMonitor, SafetyController

---

## 6. Code-Referenzen

### 6.1 ESP32 Safety-Module

| Datei | Zeilen | Inhalt |
|-------|--------|--------|
| `src/error_handling/circuit_breaker.h` | 1-147 | CircuitBreaker Class Definition |
| `src/error_handling/circuit_breaker.cpp` | 1-188 | CircuitBreaker Implementation |
| `src/models/watchdog_types.h` | 1-93 | WatchdogMode, WatchdogConfig, WatchdogDiagnostics |
| `src/main.cpp` | 72-74 | Global Watchdog State |
| `src/main.cpp` | 365-402 | Watchdog Initialization |
| `src/main.cpp` | 1496-1554 | feedWatchdog() Implementation |
| `src/main.cpp` | 1560-1617 | handleWatchdogTimeout() Implementation |
| `src/main.cpp` | 1639-1655 | Watchdog Feed in loop() |
| `src/error_handling/error_tracker.h` | 1-151 | ErrorTracker Class Definition |
| `src/error_handling/error_tracker.cpp` | 1-342 | ErrorTracker Implementation |
| `src/error_handling/health_monitor.h` | 1-100 | HealthMonitor, HealthSnapshot |
| `src/error_handling/health_monitor.cpp` | 1-319 | HealthMonitor Implementation |
| `src/services/actuator/safety_controller.h` | 1-54 | SafetyController Class Definition |
| `src/services/actuator/safety_controller.cpp` | 1-176 | SafetyController Implementation |
| `src/models/actuator_types.h` | 10-15 | EmergencyState Enum |
| `src/models/actuator_types.h` | 103-108 | RecoveryConfig Struct |
| `src/models/error_codes.h` | 155-158 | Watchdog Error Codes (4070-4072) |
| `src/services/communication/wifi_manager.h` | 55 | WiFi Circuit Breaker Member |
| `src/services/communication/wifi_manager.cpp` | 35 | WiFi CB Initialization |
| `src/services/communication/mqtt_client.h` | 117 | MQTT Circuit Breaker Member |
| `src/services/communication/mqtt_client.cpp` | 55 | MQTT CB Initialization |

### 6.2 Server Resilience-Module

| Datei | Zeilen | Inhalt |
|-------|--------|--------|
| `src/core/config.py` | 578-680 | ResilienceSettings |
| `src/core/resilience/circuit_breaker.py` | 1-455 | CircuitBreaker Implementation |
| `src/core/resilience/registry.py` | 1-320 | ResilienceRegistry Singleton |
| `src/core/resilience/exceptions.py` | - | CircuitBreakerOpenError etc. |
| `src/core/resilience/retry.py` | - | Retry Patterns |
| `src/core/resilience/timeout.py` | - | Timeout Patterns |

---

## 7. Offene Fragen

### 7.1 Für Rückfragen an Domain-Experten

1. **Watchdog ↔ SafetyController:** Sollte bei Watchdog-Timeout in PROVISIONING/SAFE_MODE `safetyController.emergencyStopAll()` aufgerufen werden bevor Safe-Mode aktiviert wird?

2. **Error-Handler auf Server:** Gibt es einen Handler für `kaiser/{kaiser}/esp/{esp}/system/error` Topics? ErrorTracker publiziert Errors, aber ich fand keinen dedizierten Handler.

3. **Server CB → ESP Notification:** Sollte der Server den ESP benachrichtigen wenn ein Server-seitiger Circuit Breaker OPEN ist? (z.B. "bitte keine Daten senden, DB ist down")

4. **Watchdog Reset Reason Persistence:** Wird der Reset-Reason (`ESP_RST_TASK_WDT`) nach Reboot an den Server gesendet? (Im Heartbeat-Payload?)

5. **Pi-Enhanced Circuit Breaker:** Gibt es einen Circuit Breaker für Pi-Enhanced HTTP-Requests auf ESP32? (Nicht gefunden)

### 7.2 Offene Implementierungsdetails

1. **SAFE_MODE Watchdog:** Der SAFE_MODE (120s Timeout) ist in `WatchdogMode` definiert, aber ich fand keine Code-Pfade die ihn aktivieren.

2. **getWatchdogCountLast24h():** Die Funktion ist deklariert (watchdog_types.h:90), aber ich fand keine Implementation.

---

## 8. Zusammenfassung

Das Safety-Pattern-Ökosystem in AutomationOne ist **industrietauglich** implementiert:

### Stärken

1. **Klare State Machines:** Circuit Breaker mit CLOSED/OPEN/HALF_OPEN
2. **Conditional Watchdog Feeds:** Integration mit Circuit Breaker verhindert sinnlose Resets
3. **Mehrschichtige Safety:** Circuit Breaker → Error Tracker → Watchdog → Safety Controller
4. **Server-Parität:** Server hat äquivalente Resilience-Patterns
5. **Observability:** Health Monitor publiziert alle Safety-States

### Verbesserungspotential

1. **SafetyController bei WD-Timeout:** Aktuell kein Emergency-Stop vor ESP-Reset
2. **Server Error-Handler:** Fehlt für ESP-Error-Topic
3. **Cross-Layer Coordination:** ESP und Server CBs arbeiten unabhängig

### Code-Qualität

- **ESP32:** ~2500 Zeilen Safety-Code (Production-Ready)
- **Server:** ~1500 Zeilen Resilience-Code (Production-Ready)
- **Dokumentation:** Gut inline-dokumentiert, fehlte nur konsolidierte Übersicht (→ dieses Dokument)

---

---

## ERGÄNZUNGEN: Detaillierte Nutzungsanalyse

> **Ergänzt von:** ESP32-Spezialist (Deep-Dive)
> **Datum:** 2026-01-30

---

### 2.1.8 WiFi Circuit Breaker: Detaillierte Nutzungsanalyse

#### 1. INITIALISIERUNG (wifi_manager.cpp:31-40)

```cpp
WiFiManager::WiFiManager()
    : last_reconnect_attempt_(0),
      reconnect_attempts_(0),
      initialized_(false),
      circuit_breaker_("WiFi", 10, 60000, 15000) {
  // Circuit Breaker configured:
  // - 10 failures → OPEN (WiFi needs more tolerance)
  // - 60s recovery timeout (WiFi takes longer)
  // - 15s half-open test timeout
}
```

**Erstellung:** Im Konstruktor als Member-Variable
**Phase:** Vor `WiFiManager::begin()`, beim statischen Singleton-Init (wifi_manager.cpp:18)

#### 2. NUTZUNG IM NORMALBETRIEB

| Operation | CB-Methode | Zeilen | Beschreibung |
|-----------|------------|--------|--------------|
| `reconnect()` | `allowRequest()` | wifi_manager.cpp:215 | Prüft ob Reconnect erlaubt |
| `connectToNetwork()` SUCCESS | `recordSuccess()` | wifi_manager.cpp:153 | Reset nach erfolgreicher Verbindung |
| `connectToNetwork()` FAIL | `recordFailure()` | wifi_manager.cpp:129 | Zählt Fehlversuch |
| `reconnect()` - already connected | `recordSuccess()` | wifi_manager.cpp:208 | Reset wenn bereits verbunden |
| `shouldAttemptReconnect()` | `getState()`, `isOpen()` | wifi_manager.cpp:277, 282 | HALF_OPEN Bypass + OPEN Check |

#### 3. FLOW: WiFi-Reconnect mit Circuit Breaker

```
reconnect() aufgerufen
    │
    ├─> isConnected()?
    │       │
    │       └─> JA: recordSuccess() → return
    │
    ├─> circuit_breaker_.allowRequest()? → NEIN: LOG_DEBUG, return
    │
    ├─> shouldAttemptReconnect()?
    │       │
    │       ├─> HALF_OPEN? → sofort return true (bypass backoff!)
    │       ├─> OPEN? → return false
    │       └─> check reconnect interval → return true/false
    │
    └─> connectToNetwork()
            │
            ├─> WiFi.begin() + wait loop
            │       └─> esp_task_wdt_reset() während wait! (Zeile 143)
            │
            ├─> TIMEOUT (20s): recordFailure(), check isOpen()
            └─> SUCCESS: recordSuccess(), NTP sync
```

#### 4. WICHTIGE ENTDECKUNG: Direkter Watchdog-Feed in WiFi-Connect

**wifi_manager.cpp:139-145:**
```cpp
// FIX #2: Non-blocking wait with watchdog feed
// WiFi connect can take up to 20s - feed watchdog to prevent reset
yield();
#ifdef ESP_PLATFORM
esp_task_wdt_reset();  // ← DIREKTER WDT-Feed, nicht via feedWatchdog()!
#endif
delay(100);
```

**WARUM direkt?** Der Connect-Loop kann bis zu 20 Sekunden dauern. Da `feedWatchdog()` in Production Mode den WiFi CB prüft (der während eines Connect-Versuchs CLOSED ist), wäre ein direkter Feed sicherer. Dies umgeht die CB-Checks bewusst.

#### 5. FEHLERFALL-BEHANDLUNG (wifi_manager.cpp:97-137)

```cpp
// CONNECTION FAILED
wl_status_t status = WiFi.status();
String error_message = getWiFiStatusMessage(status);  // Human-readable
// ... detailed logging ...
errorTracker.logCommunicationError(ERROR_WIFI_CONNECT_TIMEOUT, ...);
circuit_breaker_.recordFailure();  // ← CB-Update

if (circuit_breaker_.isOpen()) {
    LOG_WARNING("WiFi Circuit Breaker OPENED after failure threshold");
    LOG_WARNING("  Will retry in 60 seconds");
}
```

#### 6. RECOVERY-MECHANISMUS

**Trigger:** Nach 60s Recovery-Timeout wechselt CB automatisch zu HALF_OPEN (in `allowRequest()`)

**Test-Request:** `shouldAttemptReconnect()` erkennt HALF_OPEN (Zeile 277) und gibt sofort `true` zurück → Reconnect-Versuch ohne Backoff-Delay

**Ergebnis:**
- SUCCESS: `connectToNetwork()` → `recordSuccess()` → CLOSED
- FAILURE: `connectToNetwork()` timeout → `recordFailure()` → OPEN (erneut)

---

### 2.1.9 MQTT Circuit Breaker: Detaillierte Nutzungsanalyse

#### 1. INITIALISIERUNG (mqtt_client.cpp:46-60)

```cpp
MQTTClient::MQTTClient()
    : mqtt_(wifi_client_),
      // ... other members ...
      circuit_breaker_("MQTT", 5, 30000, 10000) {
  // Circuit Breaker configured:
  // - 5 failures → OPEN
  // - 30s recovery timeout
  // - 10s half-open test timeout
}
```

**Niedrigere Toleranz als WiFi:** MQTT-Verbindungen sind schneller, daher 5 Fehler (vs. 10 bei WiFi) und 30s Recovery (vs. 60s).

#### 2. NUTZUNG IM NORMALBETRIEB - ALLE Stellen

| Operation | CB-Methode | Zeilen | Beschreibung |
|-----------|------------|--------|--------------|
| `reconnect()` | `allowRequest()` | mqtt_client.cpp:371 | Reconnect-Erlaubnis |
| `reconnect()` already connected | `recordSuccess()` | mqtt_client.cpp:364 | Reset bei bestehender Verbindung |
| `reconnect()` FAIL | `recordFailure()` | mqtt_client.cpp:420 | Nach failed connectToBroker() |
| `reconnect()` SUCCESS | `recordSuccess()` | mqtt_client.cpp:437 | Nach successful connectToBroker() |
| `connectToBroker()` SUCCESS | `recordSuccess()` | mqtt_client.cpp:244 | Connection established |
| `publish()` | `allowRequest()` | mqtt_client.cpp:478 | Publish-Erlaubnis |
| `publish()` - not connected | `recordFailure()` | mqtt_client.cpp:491 | Offline → CB-Failure! |
| `publish()` SUCCESS | `recordSuccess()` | mqtt_client.cpp:502 | Successful publish |
| `publish()` FAIL | `recordFailure()` | mqtt_client.cpp:514 | Failed mqtt_.publish() |
| `safePublish()` | `isOpen()` | mqtt_client.cpp:535, 547 | Skip retries wenn OPEN |
| `shouldAttemptReconnect()` | `getState()` | mqtt_client.cpp:746 | HALF_OPEN → sofort true |

#### 3. FLOW: MQTT-Publish mit Circuit Breaker

```
publish(topic, payload, qos) aufgerufen
    │
    ├─> test_publish_hook_? → hook aufrufen, return true (Test-Mode)
    │
    ├─> circuit_breaker_.allowRequest()?
    │       │
    │       └─> NEIN: LOG_WARNING "blocked by Circuit Breaker"
    │                  return false (NICHT in offline buffer!)
    │
    ├─> isConnected()?
    │       │
    │       └─> NEIN: recordFailure(), addToOfflineBuffer()
    │
    └─> mqtt_.publish()
            │
            ├─> SUCCESS: recordSuccess()
            └─> FAIL: recordFailure(), check isOpen(), addToOfflineBuffer()
```

#### 4. KRITISCHE UNTERSCHEIDUNG: publish() vs safePublish()

**publish():**
- Prüft CB vor jedem Versuch
- Fügt NICHT zum Buffer hinzu wenn CB OPEN

**safePublish():**
- Prüft CB vor Retry-Loop
- Bei OPEN: nur EIN Versuch (kein Retry-Spam)
- Bei CLOSED: publish() + 1 Retry mit `yield()` statt `delay()`

#### 5. OFFLINE BUFFER INTERAKTION (mqtt_client.cpp:762-811)

```
CB OPEN + publish() aufgerufen
    │
    └─> NICHT in offline buffer! ("Don't add when circuit is open")

CB CLOSED + not connected + publish() aufgerufen
    │
    └─> recordFailure() + addToOfflineBuffer()

Reconnect SUCCESS → processOfflineBuffer()
    │
    └─> Iteriert durch Buffer, ruft publish() für jede Message
```

**WICHTIG:** Wenn CB OPEN ist, werden KEINE Messages gepuffert. Das verhindert Speicherüberlauf bei lang anhaltendem MQTT-Ausfall.

#### 6. HALF_OPEN BACKOFF BYPASS (mqtt_client.cpp:741-748)

```cpp
// ✅ FIX #2: HALF_OPEN bypasses exponential backoff (2026-01-20)
// Race Condition: Wenn Circuit Breaker auf HALF_OPEN wechselt, aber
// reconnect_delay_ms_ > halfopen_timeout (10s), wird nie ein Reconnect
// versucht und HALF_OPEN timeout zurück zu OPEN ohne Test.
if (circuit_breaker_.getState() == CircuitState::HALF_OPEN) {
    return true;  // Sofort versuchen, kein Backoff!
}
```

**Root-Cause Fix:** Ohne diesen Fix konnte HALF_OPEN-Timeout eintreten bevor ein Test-Request gemacht wurde.

---

### 2.1.10 PiServer Circuit Breaker: Detaillierte Nutzungsanalyse (NEU ENTDECKT!)

> **WICHTIG:** Dieser Circuit Breaker war in der ursprünglichen Analyse NICHT dokumentiert!

#### 1. INITIALISIERUNG (pi_enhanced_processor.cpp:24-34)

```cpp
PiEnhancedProcessor::PiEnhancedProcessor()
    : http_client_(nullptr),
      pi_server_address_(""),
      pi_server_port_(8000),
      last_response_time_(0),
      circuit_breaker_("PiServer", 5, 60000, 10000) {
  // Circuit Breaker configured (Phase 6+):
  // - 5 failures → OPEN (like MQTT)
  // - 60s recovery timeout
  // - 10s half-open test timeout
}
```

**Zweck:** Schützt HTTP-Requests zum God-Kaiser Server für Pi-Enhanced Sensor Processing.

#### 2. EINZIGE NUTZUNG: sendRawData()

| Operation | CB-Methode | Zeilen | Beschreibung |
|-----------|------------|--------|--------------|
| Entry | `allowRequest()` | pi_enhanced_processor.cpp:98 | Request-Erlaubnis |
| HTTP Client not init | `recordFailure()` | pi_enhanced_processor.cpp:124 | Client-Fehler zählt |
| HTTP Request FAIL | `recordFailure()` | pi_enhanced_processor.cpp:145 | Network/Server-Fehler |
| JSON Parse FAIL | `recordFailure()` | pi_enhanced_processor.cpp:163 | Ungültige Response |
| SUCCESS | `recordSuccess()` | pi_enhanced_processor.cpp:171 | Alles OK |

#### 3. UNIQUE FEATURE: Fallback-Mode bei OPEN

**pi_enhanced_processor.cpp:102-115:**
```cpp
if (!circuit_breaker_.allowRequest()) {
    // PHASE 2: HTTP-FALLBACK-MODE (Robustness)
    // Server unavailable → use local fallback processing
    LOG_INFO("Using local fallback processing - returning raw values");

    processed_out.value = (float)data.raw_value;  // RAW value directly
    processed_out.unit = "raw";                   // Mark as unprocessed
    processed_out.quality = "fair";               // Medium quality
    processed_out.timestamp = data.timestamp;
    processed_out.valid = true;
    processed_out.error_message = "Local fallback - server unavailable";

    return true;  // ← SUCCESS trotz CB OPEN!
}
```

**UNTERSCHIED zu WiFi/MQTT:** Bei OPEN wird nicht blockiert, sondern Fallback-Daten zurückgegeben. Das ermöglicht "Degraded Mode" für Sensoren.

#### 4. KEINE INTEGRATION MIT WATCHDOG

Der PiServer Circuit Breaker wird in `feedWatchdog()` (main.cpp) **NICHT** geprüft. Das ist beabsichtigt:
- HTTP-Ausfall ist noch weniger kritisch als MQTT
- ESP kann komplett ohne Pi-Enhanced Processing arbeiten

---

### 2.2.8 Watchdog: Detaillierte Nutzungsanalyse

#### 1. INITIALISIERUNG (main.cpp:360-402)

**Entscheidungslogik:**
```cpp
if (provisioning_needed) {
    // PROVISIONING MODE
    esp_task_wdt_init(300, false);  // 300s, no panic
    esp_task_wdt_add(NULL);         // Main task hinzufügen
    g_watchdog_config.mode = WatchdogMode::PROVISIONING;
    g_watchdog_config.timeout_ms = 300000;
    g_watchdog_config.feed_interval_ms = 60000;
    g_watchdog_config.panic_enabled = false;
} else {
    // PRODUCTION MODE
    esp_task_wdt_init(60, true);    // 60s, panic=true
    esp_task_wdt_add(NULL);         // Main task hinzufügen
    g_watchdog_config.mode = WatchdogMode::PRODUCTION;
    g_watchdog_config.timeout_ms = 60000;
    g_watchdog_config.feed_interval_ms = 10000;
    g_watchdog_config.panic_enabled = true;
}
g_watchdog_diagnostics = WatchdogDiagnostics();
g_watchdog_timeout_flag = false;
```

**Phase:** Während `setup()`, nach Provisioning-Check aber vor WiFi-Connect

#### 2. FEED-MECHANISMUS: ALLE Stellen

| Stelle | Datei:Zeile | Methode | Beschreibung |
|--------|-------------|---------|--------------|
| Main Loop | main.cpp:1642 | `feedWatchdog("MAIN_LOOP")` | Primärer Feed |
| WiFi Connect | wifi_manager.cpp:143 | `esp_task_wdt_reset()` | DIREKTER Feed (kein CB-Check!) |

**WICHTIG:** Es gibt nur ZWEI Stellen mit WDT-Feeds:
1. Der reguläre `feedWatchdog()` in loop()
2. Der direkte `esp_task_wdt_reset()` während WiFi-Connect

#### 3. feedWatchdog() VOLLSTÄNDIGE IMPLEMENTATION (main.cpp:1496-1554)

```cpp
bool feedWatchdog(const char* component_id) {
  // ═══════════════════════════════════════════════════════════════
  // 1. CIRCUIT BREAKER CHECK (nur Production Mode)
  // ═══════════════════════════════════════════════════════════════
  if (g_watchdog_config.mode == WatchdogMode::PRODUCTION) {

    // WiFi CB OPEN? → CRITICAL → BLOCK FEED!
    if (wifiManager.getCircuitBreakerState() == CircuitState::OPEN) {
      errorTracker.logApplicationError(
        ERROR_WATCHDOG_FEED_BLOCKED,   // 4071
        "Watchdog feed blocked: WiFi Circuit Breaker OPEN"
      );
      return false;
    }

    // MQTT CB OPEN? → WARNING ONLY (nicht critical)
    if (mqttClient.getCircuitBreakerState() == CircuitState::OPEN) {
      static unsigned long last_mqtt_cb_warning = 0;
      if (millis() - last_mqtt_cb_warning > 10000) {
        last_mqtt_cb_warning = millis();
        LOG_WARNING("MQTT Circuit Breaker OPEN - running in degraded mode");
      }
      // Continue with feed - don't block!
    }

    // Critical Errors? → BLOCK FEED!
    if (errorTracker.hasCriticalErrors()) {
      errorTracker.logApplicationError(
        ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL,  // 4072
        "Watchdog feed blocked: Critical errors active"
      );
      return false;
    }

    // System in ERROR State? → BLOCK FEED!
    if (g_system_config.current_state == STATE_ERROR) {
      return false;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 2. FEED THE WATCHDOG
  // ═══════════════════════════════════════════════════════════════
  #ifndef WOKWI_SIMULATION
  esp_task_wdt_reset();
  #endif

  // ═══════════════════════════════════════════════════════════════
  // 3. UPDATE DIAGNOSTICS
  // ═══════════════════════════════════════════════════════════════
  g_watchdog_diagnostics.last_feed_time = millis();
  g_watchdog_diagnostics.last_feed_component = component_id;
  g_watchdog_diagnostics.feed_count++;

  return true;
}
```

#### 4. FEED-AUFRUF IN loop() (main.cpp:1637-1650)

```cpp
static unsigned long last_feed_time = 0;

if (g_watchdog_config.mode != WatchdogMode::WDT_DISABLED) {
  unsigned long feed_interval = g_watchdog_config.feed_interval_ms;
  if (millis() - last_feed_time >= feed_interval) {
    if (feedWatchdog("MAIN_LOOP")) {
      last_feed_time = millis();
    } else {
      // Feed blocked → Watchdog wird timeout
      // Error wird getrackt in feedWatchdog()
    }
  }
}
```

**Feed-Frequenz:**
- Production: alle 10s
- Provisioning: alle 60s

#### 5. TIMEOUT-HANDLING (main.cpp:1560-1617)

```cpp
void handleWatchdogTimeout() {
  if (!g_watchdog_timeout_flag) return;

  // 1. Track Critical Error
  errorTracker.trackError(ERROR_WATCHDOG_TIMEOUT, ERROR_SEVERITY_CRITICAL, ...);

  // 2. Collect Diagnostics
  WatchdogDiagnostics diag;
  diag.timestamp = millis();
  diag.system_state = g_system_config.current_state;
  diag.last_feed_component = g_watchdog_diagnostics.last_feed_component;
  diag.last_feed_time = g_watchdog_diagnostics.last_feed_time;
  diag.wifi_breaker_state = wifiManager.getCircuitBreakerState();
  diag.mqtt_breaker_state = mqttClient.getCircuitBreakerState();
  diag.error_count = errorTracker.getErrorCount();
  diag.heap_free = ESP.getFreeHeap();

  // 3. Save to NVS (TODO)
  // storageManager.saveWatchdogDiagnostics(diag);

  // 4. Publish Health Snapshot if MQTT connected
  if (mqttClient.isConnected()) {
    healthMonitor.publishSnapshot();
  }

  // 5. Mode-specific action
  if (g_watchdog_config.mode == WatchdogMode::PRODUCTION) {
    LOG_CRITICAL("Production Mode Watchdog Timeout → ESP will reset");
    // panic=true → ESP32 Hardware-Reset automatisch
  } else {
    LOG_WARNING("Provisioning Mode Watchdog Timeout → Manual reset available");
    // LED-Blink als Signal (5x blink)
  }

  g_watchdog_timeout_flag = false;
}
```

#### 6. REBOOT-DETECTION (main.cpp:405-419)

```cpp
if (esp_reset_reason() == ESP_RST_TASK_WDT) {
    LOG_WARNING("ESP REBOOTED DUE TO WATCHDOG TIMEOUT");

    // Check: 3× Watchdog in 24h?
    uint8_t watchdog_count = getWatchdogCountLast24h();
    if (watchdog_count >= 3) {
        // → Safe-Mode Provisioning aktivieren
    }
}
```

**LIMITIERUNG:** `getWatchdogCountLast24h()` ist ein TODO-Stub (immer 0).

---

### 4.3 CB ↔ Watchdog: Verifizierter Interaktions-Flow

```
┌───────────────────────────────────────────────────────────────────┐
│                    feedWatchdog("MAIN_LOOP")                      │
│                         (main.cpp:1496)                           │
└───────────────────────────────────────────────────────────────────┘
                                │
                                ▼
              ┌─────────────────────────────────────┐
              │ g_watchdog_config.mode == PRODUCTION? │
              └─────────────────────────────────────┘
                     │                     │
                    JA                    NEIN
                     │                     │
                     ▼                     │
    ┌────────────────────────────────┐     │
    │ wifiManager.getCircuitBreakerState() │     │
    │              == OPEN?           │     │
    └────────────────────────────────┘     │
           │                 │             │
          JA                NEIN           │
           │                 │             │
           ▼                 ▼             │
    ┌──────────────┐   ┌────────────────┐  │
    │ ERROR 4071   │   │ MQTT CB OPEN?  │  │
    │ return false │   └────────────────┘  │
    └──────────────┘         │      │      │
                            JA     NEIN    │
                             │      │      │
                             ▼      │      │
                    ┌────────────┐  │      │
                    │ Rate-limited│  │      │
                    │ WARNING     │  │      │
                    │ (kein block)│  │      │
                    └────────────┘  │      │
                             │      │      │
                             └──────┼──────┘
                                    │
                                    ▼
                    ┌────────────────────────────┐
                    │ errorTracker.hasCriticalErrors()? │
                    └────────────────────────────┘
                           │              │
                          JA            NEIN
                           │              │
                           ▼              ▼
                    ┌──────────────┐  ┌────────────────────┐
                    │ ERROR 4072   │  │ STATE_ERROR?       │
                    │ return false │  │                    │
                    └──────────────┘  └────────────────────┘
                                           │         │
                                          JA       NEIN
                                           │         │
                                           ▼         ▼
                                    ┌──────────┐  ┌─────────────────┐
                                    │ return   │  │ esp_task_wdt_   │
                                    │ false    │  │ reset()         │
                                    └──────────┘  │ Update Diag     │
                                                  │ return true     │
                                                  └─────────────────┘
```

**VERIFIZIERT gegen Code:** Dieser Flow entspricht exakt der Implementation in main.cpp:1496-1554.

---

### 4.4 Timing-Analyse: Vollständige Übersicht

#### Circuit Breaker Timing-Tabelle

| Komponente | Parameter | Wert | Quelle |
|------------|-----------|------|--------|
| **WiFi CB** | Failure Threshold | **10** | wifi_manager.cpp:35 |
| **WiFi CB** | Recovery Timeout | **60.000ms (60s)** | wifi_manager.cpp:35 |
| **WiFi CB** | Half-Open Timeout | **15.000ms (15s)** | wifi_manager.cpp:35 |
| **MQTT CB** | Failure Threshold | **5** | mqtt_client.cpp:55 |
| **MQTT CB** | Recovery Timeout | **30.000ms (30s)** | mqtt_client.cpp:55 |
| **MQTT CB** | Half-Open Timeout | **10.000ms (10s)** | mqtt_client.cpp:55 |
| **PiServer CB** | Failure Threshold | **5** | pi_enhanced_processor.cpp:29 |
| **PiServer CB** | Recovery Timeout | **60.000ms (60s)** | pi_enhanced_processor.cpp:29 |
| **PiServer CB** | Half-Open Timeout | **10.000ms (10s)** | pi_enhanced_processor.cpp:29 |

#### Watchdog Timing-Tabelle

| Mode | Parameter | Wert | Quelle |
|------|-----------|------|--------|
| **PRODUCTION** | Timeout | **60.000ms (60s)** | main.cpp:385, 394 |
| **PRODUCTION** | Feed Interval | **10.000ms (10s)** | main.cpp:395 |
| **PRODUCTION** | Panic Enabled | **true** | main.cpp:385, 396 |
| **PROVISIONING** | Timeout | **300.000ms (5min)** | main.cpp:366, 375 |
| **PROVISIONING** | Feed Interval | **60.000ms (60s)** | main.cpp:376 |
| **PROVISIONING** | Panic Enabled | **false** | main.cpp:366, 377 |
| **WDT_DISABLED** | Timeout | **0** | main.cpp:159 |
| **SAFE_MODE** | Timeout | **120.000ms (2min)** | watchdog_types.h:16 (deklariert, NICHT implementiert) |

#### Andere Timing-Parameter

| Komponente | Parameter | Wert | Quelle |
|------------|-----------|------|--------|
| WiFi | Connect Timeout | **20.000ms (20s)** | wifi_manager.cpp:13 |
| WiFi | Reconnect Interval | **30.000ms (30s)** | wifi_manager.cpp:11 |
| MQTT | Reconnect Base Delay | **1.000ms (1s)** | mqtt_client.cpp:19 |
| MQTT | Reconnect Max Delay | **60.000ms (60s)** | mqtt_client.cpp:20 |
| MQTT | Heartbeat Interval | **60.000ms (60s)** | mqtt_client.h:111 |
| Pi-Enhanced | HTTP Timeout | **2.500ms (2.5s)** | pi_enhanced_processor.cpp:138 |
| HealthMonitor | Publish Interval | **60.000ms (60s)** | health_monitor.cpp:39 |
| MQTT CB Warning | Rate-Limit | **10.000ms (10s)** | main.cpp:1518 |

#### Kritische Timing-Berechnungen

**1. Feeds pro Watchdog-Timeout (Production):**
```
Timeout:       60.000ms
Feed Interval: 10.000ms
→ 6 Feed-Möglichkeiten bevor Timeout
```

**2. WiFi CB kann maximal offline sein ohne Watchdog-Reset:**
```
WiFi Recovery Timeout:     60.000ms
+ Half-Open Test + Retry:  ~5.000ms
+ Watchdog Buffer:         ~10.000ms (1 Feed-Interval)
≈ 75 Sekunden Maximum
```

**3. MQTT CB (kein direkter Impact auf Watchdog):**
```
MQTT CB OPEN blockiert NICHT feedWatchdog()
→ Unbegrenzt MQTT-Ausfall möglich ohne Watchdog-Reset
```

---

### 4.5 Offene Beobachtungen aus der Deep-Dive-Analyse

#### Verifizierte Implementierungslücken

1. **SAFE_MODE nie aktiviert:** In `WatchdogMode` deklariert (watchdog_types.h:16), aber kein Code-Pfad aktiviert ihn je.

2. **getWatchdogCountLast24h() ist Stub:** main.cpp:1624-1628 gibt immer 0 zurück.

3. **NVS-Persistenz TODO:** main.cpp:1588 - Watchdog-Diagnostics werden nicht in NVS gespeichert.

4. **SafetyController nicht bei Timeout:** handleWatchdogTimeout() ruft NICHT safetyController.emergencyStopAll() auf.

#### Code-Inkonsistenzen (Keine Bugs, aber bemerkenswert)

1. **Direkter WDT-Feed in WiFi:** wifi_manager.cpp:143 umgeht feedWatchdog() bewusst (dokumentiert).

2. **PiServer CB nicht im Watchdog-Check:** Absichtlich ausgelassen (niedrigste Kritikalität).

3. **MQTT CB Failure Count wird bei "not connected" erhöht:** mqtt_client.cpp:491 - Dies kann CB schnell öffnen bei Netzwerkproblemen.

---

**Deep-Dive-Analyse abgeschlossen:** 2026-01-30
**Analyst:** ESP32-Spezialist

---

**Analyse abgeschlossen:** 2026-01-30
**Analyst:** Claude System-Architekt
