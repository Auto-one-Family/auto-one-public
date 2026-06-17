# API Reference - Phase 1 Core Infrastructure

Complete API documentation for all Phase 1 modules. All modules follow a consistent design pattern: **Singleton instances** with **const char\* primary API** and **String wrapper convenience methods**.

---

## Table of Contents

1. [Logger System](#logger-system)
2. [StorageManager](#storagemanager)
3. [ConfigManager](#configmanager)
4. [ErrorTracker](#errortracker)
5. [HealthMonitor](#healthmonitor)
6. [TopicBuilder](#topicbuilder)
7. [GPIOManager](#gpiomanager)
8. [Error Codes Reference](#error-codes-reference)
9. [Type Definitions](#type-definitions)

---

## Logger System

### Header
```cpp
#include "utils/logger.h"
```

### Log Levels
```cpp
enum LogLevel {
  LOG_DEBUG = 0,      // Detailed diagnostic information
  LOG_INFO = 1,       // General informational messages
  LOG_WARNING = 2,    // Warning conditions
  LOG_ERROR = 3,      // Error conditions
  LOG_CRITICAL = 4    // Critical errors, system unstable
};
```

### Initialization

```cpp
// Get singleton instance
Logger& logger = Logger::getInstance();

// Initialize logger (must call in setup())
void logger.begin();

// Configure log output level (default: LOG_DEBUG)
void logger.setLogLevel(LogLevel level);

// Enable/disable serial output (default: true)
void logger.setSerialEnabled(bool enabled);

// Set maximum log buffer entries (default: 50)
void logger.setMaxLogEntries(size_t max_entries);
```

### Logging Methods - Primary API (const char\*)

**Zero-copy, memory-efficient methods for production code.**

```cpp
void logger.log(LogLevel level, const char* message);
void logger.debug(const char* message);
void logger.info(const char* message);
void logger.warning(const char* message);
void logger.error(const char* message);
void logger.critical(const char* message);
```

### Logging Methods - Wrapper API (String)

**Convenience methods for code that generates dynamic messages.**

```cpp
inline void logger.log(LogLevel level, const String& message);
inline void logger.debug(const String& message);
inline void logger.info(const String& message);
inline void logger.warning(const String& message);
inline void logger.error(const String& message);
inline void logger.critical(const String& message);
```

### Convenience Macros

**Use macros for cleaner, more readable logging code.**

```cpp
LOG_DEBUG(msg)      // Expands to logger.debug(msg)
LOG_INFO(msg)       // Expands to logger.info(msg)
LOG_WARNING(msg)    // Expands to logger.warning(msg)
LOG_ERROR(msg)      // Expands to logger.error(msg)
LOG_CRITICAL(msg)   // Expands to logger.critical(msg)
```

### Log Management and Queries

```cpp
// Clear all log entries
void logger.clearLogs();

// Retrieve formatted log history
// Returns: String with formatted log entries
// min_level: Minimum log level to include (default: LOG_DEBUG)
// max_entries: Maximum entries to return (default: 50)
String logger.getLogs(LogLevel min_level = LOG_DEBUG, size_t max_entries = 50) const;

// Get total number of logged entries
size_t logger.getLogCount() const;

// Check if a specific log level is enabled
bool logger.isLogLevelEnabled(LogLevel level) const;

// Convert LogLevel to string representation
static const char* logger.getLogLevelString(LogLevel level);

// Convert string to LogLevel (returns LOG_DEBUG if invalid)
static LogLevel logger.getLogLevelFromString(const char* level_str);
```

### Log Entry Structure

```cpp
struct LogEntry {
  unsigned long timestamp;   // Milliseconds since boot (millis())
  LogLevel level;            // Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  char message[128];         // Fixed-size message buffer
};
```

**Note:** Messages longer than 127 characters will be truncated.

### Usage Examples

```cpp
// Basic initialization
logger.begin();
logger.setLogLevel(LOG_INFO);

// Using macros (recommended)
LOG_INFO("System started");
LOG_DEBUG("Debug info");
LOG_ERROR("Error occurred");

// Using direct methods
logger.info("Temperature reading");
logger.warning("Low battery");
logger.critical("Critical failure");

// Using String (dynamic messages)
String sensor_name = "Temperature";
logger.info(String("Reading from ") + sensor_name);

// Retrieving logs
String history = logger.getLogs(LOG_INFO, 20);
Serial.println(history);

// Checking log status
size_t count = logger.getLogCount();
if (logger.isLogLevelEnabled(LOG_WARNING)) {
  LOG_WARNING("Warning level is enabled");
}
```

### Design Notes

- **Circular buffer:** Automatically overwrites oldest entries when buffer is full
- **Fixed memory:** All entries stored in fixed-size array (no heap fragmentation)
- **Dual API:** const char\* for performance, String for convenience
- **Serial output:** Each log entry is also printed to serial in real-time
- **Thread-safe:** Safe for use in FreeRTOS tasks

---

## StorageManager

### Header
```cpp
#include "services/config/storage_manager.h"
```

Abstraction layer over ESP32 NVS (Non-Volatile Storage) using Preferences API.

### Initialization

```cpp
// Get singleton instance
StorageManager& storageManager = StorageManager::getInstance();

// Initialize NVS storage (must call in setup())
bool storageManager.begin();  // Returns: true on success
```

### Namespace Management

**NVS organizes data into logical namespaces. Must manage namespace lifecycle.**

```cpp
// Open a namespace for reading/writing
// read_only: Set to true to prevent modifications
bool storageManager.beginNamespace(const char* namespace_name, bool read_only = false);

// Close current namespace
// Must be called before opening a different namespace
void storageManager.endNamespace();
```

### String Storage (Primary API)

```cpp
// Store string value
bool storageManager.putString(const char* key, const char* value);

// Retrieve string value
// Returns: Pointer to internal buffer or default_value if not found
// WARNING: Value is valid only until next call!
const char* storageManager.getString(const char* key, const char* default_value = nullptr);

// Convenience method: Check if key exists
bool storageManager.keyExists(const char* key);
```

### String Storage (Wrapper API)

```cpp
// Store string from String object
inline bool storageManager.putString(const char* key, const String& value);

// Retrieve as String object
// Returns: String object (safe for storage in variables)
inline String storageManager.getStringObj(const char* key, const String& default_value = "");
```

### Numeric Storage (Primary API)

```cpp
// Integer storage
bool storageManager.putInt(const char* key, int value);
int storageManager.getInt(const char* key, int default_value = 0);

// Unsigned 8-bit integer (0-255)
bool storageManager.putUInt8(const char* key, uint8_t value);
uint8_t storageManager.getUInt8(const char* key, uint8_t default_value = 0);

// Unsigned 16-bit integer (0-65535)
bool storageManager.putUInt16(const char* key, uint16_t value);
uint16_t storageManager.getUInt16(const char* key, uint16_t default_value = 0);

// Boolean storage
bool storageManager.putBool(const char* key, bool value);
bool storageManager.getBool(const char* key, bool default_value = false);

// Unsigned long storage
bool storageManager.putULong(const char* key, unsigned long value);
unsigned long storageManager.getULong(const char* key, unsigned long default_value = 0);
```

### Namespace Utilities

```cpp
// Clear all key-value pairs in current namespace
bool storageManager.clearNamespace();

// Get number of free entries in current namespace
size_t storageManager.getFreeEntries();
```

### Static Buffer

StorageManager maintains a static internal buffer for string storage:
```cpp
static char string_buffer_[256];  // Max string length: 255 characters
```

### Usage Examples

```cpp
// Initialize storage
storageManager.begin();

// Store WiFi credentials
storageManager.beginNamespace("wifi");
storageManager.putString("ssid", "MyNetwork");
storageManager.putString("password", "MyPassword123");
storageManager.endNamespace();

// Retrieve WiFi credentials
storageManager.beginNamespace("wifi", true);  // Read-only mode
const char* ssid = storageManager.getString("ssid");
String password = storageManager.getStringObj("password");
storageManager.endNamespace();

// Store numeric configuration
storageManager.beginNamespace("device");
storageManager.putInt("boot_count", 42);
storageManager.putBool("initialized", true);
storageManager.putUInt16("port", 8883);
storageManager.endNamespace();

// Retrieve with type checking
storageManager.beginNamespace("device", true);
int boots = storageManager.getInt("boot_count", 0);
bool initialized = storageManager.getBool("initialized", false);
storageManager.endNamespace();

// Clear a namespace
storageManager.beginNamespace("temp_data");
storageManager.clearNamespace();  // Remove all entries
storageManager.endNamespace();
```

### Design Notes

- **NVS backend:** Persistent storage survives power cycles
- **Limited writes:** Each key can be written ~100,000 times (wear leveling applies)
- **Static buffer:** Strings returned from `getString()` use internal buffer—copy immediately if needed for later use
- **Namespace isolation:** Data in different namespaces doesn't interfere with each other
- **Type consistency:** Retrieve data with the same type it was stored as

### Thread-Safety Warning

**⚠️ Thread-Safety Status (Phase 6):**

- ESP32 Preferences API ist nicht thread-safe → parallele Zugriffe benötigen einen Mutex.
- Standard-Builds (Flag **nicht** gesetzt) laufen weiter im Single-Task-Modus – identisches Verhalten wie zuvor.
- Wird das Build-Flag `CONFIG_ENABLE_THREAD_SAFETY` definiert, erstellt `StorageManager` automatisch einen FreeRTOS-Mutex (`SemaphoreHandle_t nvs_mutex_`) und schützt **alle** `beginNamespace()`, `put*()`, `get*()` und `clearNamespace()` Aufrufe.

**Aktivierung:**
```ini
; platformio.ini
[env:esp32]
build_flags =
  -D CONFIG_ENABLE_THREAD_SAFETY
```

Nach Aktivierung erscheint im Log:
```
StorageManager: Thread-safety enabled (mutex created)
```

**Multitask-Einsatz (Phase 7+):**
- Tasks können StorageManager direkt nutzen – der interne Mutex serialisiert die Zugriffe.
- Kein manuelles `xSemaphoreTake` mehr notwendig, solange alle Zugriffe über StorageManager laufen.
- Für lange Operationen kann optional weiterhin ein externer Mutex verwendet werden (z.B. um mehrere `put*()` Calls atomar zu bündeln).

**Single-Task Empfehlung:**
- Ohne Flag bleibt Verhalten identisch zu Phase 5 (nur `setup()` greift auf NVS zu).
- Keine Codeänderung nötig, solange keine parallelen Tasks NVS aufrufen.

---

## ConfigManager

### Header
```cpp
#include "services/config/config_manager.h"
```

Orchestrates loading, saving, and validating system configuration across multiple sources.

### Initialization

```cpp
// Get singleton instance
ConfigManager& configManager = ConfigManager::getInstance();

// Initialize ConfigManager and load storage
bool configManager.begin();

// Load all saved configurations into memory
bool configManager.loadAllConfigs();
```

### WiFi Configuration

```cpp
// Load WiFi configuration from storage
bool configManager.loadWiFiConfig(WiFiConfig& config);

// Save WiFi configuration to storage
bool configManager.saveWiFiConfig(const WiFiConfig& config);

// Validate WiFi configuration completeness
bool configManager.validateWiFiConfig(const WiFiConfig& config);

// Reset WiFi configuration to defaults
void configManager.resetWiFiConfig();
```

### Zone Configuration

```cpp
// Load Kaiser and Master zone configurations
bool configManager.loadZoneConfig(KaiserZone& kaiser, MasterZone& master);

// Save Kaiser and Master zone configurations
bool configManager.saveZoneConfig(const KaiserZone& kaiser, const MasterZone& master);

// Validate Kaiser zone configuration
bool configManager.validateZoneConfig(const KaiserZone& kaiser);

// Phase 7: Dynamic Zone Assignment (Runtime zone update via MQTT)
bool configManager.updateZoneAssignment(const String& zone_id, 
                                        const String& master_zone_id, 
                                        const String& zone_name, 
                                        const String& kaiser_id);
```

**File:** `src/services/config/config_manager.cpp` (lines 257-286)

**updateZoneAssignment() Implementation:**

```cpp
bool ConfigManager::updateZoneAssignment(const String& zone_id, 
                                        const String& master_zone_id, 
                                        const String& zone_name, 
                                        const String& kaiser_id) {
  LOG_INFO("ConfigManager: Updating zone assignment...");
  LOG_INFO("  Zone ID: " + zone_id);
  LOG_INFO("  Master Zone: " + master_zone_id);
  LOG_INFO("  Zone Name: " + zone_name);
  LOG_INFO("  Kaiser ID: " + kaiser_id);
  
  // Update kaiser_ structure
  kaiser_.zone_id = zone_id;
  kaiser_.master_zone_id = master_zone_id;
  kaiser_.zone_name = zone_name;
  kaiser_.zone_assigned = true;
  
  // Update kaiser_id if provided
  if (kaiser_id.length() > 0) {
    kaiser_.kaiser_id = kaiser_id;
  }
  
  // Persist to NVS via saveZoneConfig()
  bool success = saveZoneConfig(kaiser_, master_);
  
  if (success) {
    LOG_INFO("ConfigManager: Zone assignment updated successfully");
  } else {
    LOG_ERROR("ConfigManager: Failed to update zone assignment");
  }
  
  return success;
}
```

**Usage Example:**

```cpp
// Called from MQTT zone assignment handler (main.cpp:442)
if (configManager.updateZoneAssignment(zone_id, master_zone_id, zone_name, kaiser_id)) {
  // Update global variables
  g_kaiser.zone_id = zone_id;
  g_kaiser.master_zone_id = master_zone_id;
  g_kaiser.zone_name = zone_name;
  g_kaiser.zone_assigned = true;
  if (kaiser_id.length() > 0) {
    g_kaiser.kaiser_id = kaiser_id;
    TopicBuilder::setKaiserId(kaiser_id.c_str());
  }
}
```

### System Configuration

```cpp
// Load system configuration (ESP ID, state, boot count)
bool configManager.loadSystemConfig(SystemConfig& config);

// Save system configuration
bool configManager.saveSystemConfig(const SystemConfig& config);
```

### Configuration Status

```cpp
// Check if all required configurations are loaded
bool configManager.isConfigurationComplete() const;

// Print configuration status to Serial (for debugging)
void configManager.printConfigurationStatus() const;
```

### Cached Accessors

ConfigManager caches configurations in memory. Use these methods to access cached values:

```cpp
// Get cached WiFi configuration
const WiFiConfig& configManager.getWiFiConfig() const;

// Get cached Kaiser zone
const KaiserZone& configManager.getKaiser() const;

// Get cached Master zone
const MasterZone& configManager.getMasterZone() const;

// Get cached system configuration
const SystemConfig& configManager.getSystemConfig() const;

// Quick access to Kaiser ID (for TopicBuilder)
String configManager.getKaiserId() const;

// Quick access to ESP ID (for TopicBuilder)
String configManager.getESPId() const;
```

### Configuration Structures

#### WiFiConfig
```cpp
struct WiFiConfig {
  String ssid = "";                    // WiFi network name
  String password = "";                // WiFi network password
  String server_address = "";          // Bibliothek (God-Kaiser Server) IP
  uint16_t mqtt_port = 8883;           // MQTT port (default: 8883 for TLS)
  String mqtt_username = "";           // MQTT username (optional, anonymous if empty)
  String mqtt_password = "";           // MQTT password (optional, anonymous if empty)
  bool configured = false;             // Configuration status flag
};
```

#### KaiserZone

**File:** `src/models/system_types.h` (lines 23-39)

```cpp
// Kaiser Zone - ENHANCED (Phase 7: Dynamic Zones)
struct KaiserZone {
  // Primary Zone Identification (NEW - Phase 7)
  String zone_id = "";              // Primary zone identifier (e.g., "greenhouse_zone_1")
  String master_zone_id = "";       // Parent zone for hierarchy (e.g., "greenhouse")
  String zone_name = "";            // Human-readable zone name
  bool zone_assigned = false;       // Zone configuration status
  
  // Kaiser Communication (Existing)
  String kaiser_id = "";            // God-Kaiser identifier
  String kaiser_name = "";          // Kaiser name (optional)
  String system_name = "";          // System name (optional)
  bool connected = false;           // MQTT connection status
  bool id_generated = false;        // Kaiser ID generation flag
};
```

**Phase 7 Enhancements:**
- `zone_id`: Primary zone identifier assigned by God-Kaiser
- `master_zone_id`: Parent master zone for hierarchical organization
- `zone_name`: Human-readable zone name for UI display
- `zone_assigned`: Boolean flag indicating zone assignment status

**NVS Storage:** All fields persisted in `zone_config` namespace via `saveZoneConfig()`.

#### MasterZone
```cpp
struct MasterZone {
  String master_zone_id = "";          // Master zone unique identifier
  String master_zone_name = "";        // Master zone name
  bool assigned = false;               // Whether assigned to a zone
  bool is_master_esp = false;          // Whether this ESP is the master
};
```

#### SystemConfig
```cpp
struct SystemConfig {
  String esp_id = "";                  // Unique ESP device identifier
  String device_name = "ESP32";        // Human-readable device name
  SystemState current_state = STATE_BOOT;  // Current system state
  String safe_mode_reason = "";        // Reason if in safe mode
  uint16_t boot_count = 0;             // Number of system boots
};
```

### Usage Examples

```cpp
// Initialize and load all configurations
configManager.begin();
configManager.loadAllConfigs();

// Check if fully configured
if (!configManager.isConfigurationComplete()) {
  LOG_WARNING("System not fully configured");
}

// Load WiFi configuration for editing
WiFiConfig wifi = configManager.getWiFiConfig();
wifi.ssid = "NewNetwork";
wifi.password = "NewPassword";
if (configManager.saveWiFiConfig(wifi)) {
  LOG_INFO("WiFi config saved");
}

// Use cached Kaiser ID for MQTT topics
String kaiser_id = configManager.getKaiserId();
LOG_INFO("Kaiser ID: " + kaiser_id);

// Get quick access values
String esp_id = configManager.getESPId();
const SystemConfig& sys_config = configManager.getSystemConfig();
LOG_INFO("System state: " + String(sys_config.current_state));
```

### Design Notes

- **Caching:** All configurations are cached in memory after loading
- **Orchestration:** Manages configurations from multiple sources (StorageManager)
- **Validation:** Provides validation methods for configuration integrity
- **Phase 1 scope:** Handles WiFi, Zone, and System configurations
- **Phase 3 deferred:** Sensor/Actuator configuration deferred to Phase 3

---

## ConfigResponseBuilder

**Files:** `src/services/config/config_response.h` / `.cpp`  
**Purpose:** Baut das standardisierte MQTT-Response-Protokoll für Sensor- und Actuator-Konfigurationen auf `/config_response`.

### API Overview

```cpp
#include "services/config/config_response.h"
```

#### `bool publishSuccess(ConfigType type, uint8_t count, const String& message)`

Publiziert ein ACK (`status: "success"`).  
`type` unterscheidet Sensor/Actuator/WiFi/System, `count` beschreibt die Anzahl der erfolgreich angewendeten Items.

```cpp
ConfigResponseBuilder::publishSuccess(
    ConfigType::SENSOR,
    success_count,
    "Configured " + String(success_count) + " sensor(s) successfully");
```

#### `bool publishError(ConfigType type, ConfigErrorCode error_code, const String& message, JsonVariantConst failed_item = JsonVariantConst())`

Publiziert eine Fehlerantwort (NACK) inklusive standardisiertem Fehlercode.  
`failed_item` kann das problematische JSON-Objekt (Sensor/Actuator) enthalten.

```cpp
ConfigResponseBuilder::publishError(
    ConfigType::ACTUATOR,
    ConfigErrorCode::MISSING_FIELD,
    "Actuator config missing required field 'gpio'",
    actuatorObj);
```

#### `bool publish(const ConfigResponsePayload& payload)`

Low-Level Hook, falls Payload extern aufgebaut wird (z.B. Tests). Ruft intern `mqttClient.safePublish()` mit QoS 1 auf.

### Payload Structure

```cpp
struct ConfigResponsePayload {
  ConfigStatus status = ConfigStatus::SUCCESS;
  ConfigType type = ConfigType::UNKNOWN;
  uint8_t count = 0;
  String message;
  String error_code = "NONE";
  DynamicJsonDocument failed_item{256};
};
```

### ConfigErrorCode Cheatsheet

| Code               | Beschreibung                                   |
|--------------------|-----------------------------------------------|
| `NONE`             | Platzhalter bei Erfolg                        |
| `JSON_PARSE_ERROR` | JSON konnte nicht deserialisiert werden       |
| `VALIDATION_FAILED`| Feld-/GPIO-Validation fehlgeschlagen          |
| `GPIO_CONFLICT`    | GPIO ist bereits anderweitig belegt           |
| `NVS_WRITE_FAILED` | Persistenz-Operation fehlgeschlagen           |
| `TYPE_MISMATCH`    | Datentyp stimmt nicht mit Erwartung überein   |
| `MISSING_FIELD`      | Pflichtfeld fehlt im Payload                           |
| `OUT_OF_RANGE`       | Wert außerhalb zulässigem Bereich                      |
| `PAYLOAD_TOO_LARGE`  | Config-Payload > CONFIG_PAYLOAD_MAX_LEN (4096 B) — CP-F4 |
| `UNKNOWN_ERROR`      | Fallback für nicht klassifizierte Fehler               |

### Usage Pattern

```cpp
DynamicJsonDocument doc(4096);
auto error = deserializeJson(doc, payload);
if (error) {
  ConfigResponseBuilder::publishError(
      ConfigType::SENSOR,
      ConfigErrorCode::JSON_PARSE_ERROR,
      "Failed to parse JSON: " + String(error.c_str()));
  return;
}

JsonArray sensors = doc["sensors"].as<JsonArray>();
uint8_t success_count = 0;
for (JsonObject sensorObj : sensors) {
  if (parseAndConfigureSensor(sensorObj)) {
    success_count++;
  }
}

if (success_count == sensors.size()) {
  ConfigResponseBuilder::publishSuccess(
      ConfigType::SENSOR,
      success_count,
      "Configured " + String(success_count) + " sensor(s) successfully");
}
```

### Thread-Safety Warning

**⚠️ Thread-Safety Status:**

- `ConfigResponseBuilder` ist **NICHT thread-safe**, da es auf `mqttClient.safePublish()` zugreift.
- `mqttClient` ist ein Singleton ohne Mutex-Protection → parallele Aufrufe von `publishSuccess()` / `publishError()` aus mehreren FreeRTOS-Tasks können zu Race-Conditions führen.
- **Empfehlung:** Alle Config-Operationen (Sensor/Actuator/WiFi/System) sollten im **Main-Loop-Task** ausgeführt werden.
- **Phase 6 Design:** Aktuell wird ConfigResponseBuilder nur synchron aus MQTT-Callback-Handler (main.cpp, actuator_manager.cpp) aufgerufen → kein Multi-Threading aktiv → **safe**.
- **Für FreeRTOS-Integration (Phase 7+):** Falls Config-Operationen in separaten Tasks laufen, muss ein Mutex um `ConfigResponseBuilder::publish*()` Aufrufe gelegt werden.

**Code-Beispiel (FreeRTOS-Safe Pattern):**
```cpp
// Phase 7+ (Multi-Threading): Mutex Protection erforderlich
SemaphoreHandle_t config_mutex = xSemaphoreCreateMutex();

void taskSafeConfigResponse() {
  if (xSemaphoreTake(config_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
    ConfigResponseBuilder::publishSuccess(ConfigType::SENSOR, 1, "OK");
    xSemaphoreGive(config_mutex);
  } else {
    LOG_ERROR("Config mutex timeout");
  }
}
```

**Aktueller Status (Phase 6):** Keine Mutex-Protection nötig, da alle Aufrufe synchron im Main-Loop erfolgen.

---

## ErrorTracker

### Header
```cpp
#include "error_handling/error_tracker.h"
```

Tracks system errors with categorization, severity levels, and occurrence counting.

### Error Categories

```cpp
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM, sensors, actuators
  ERROR_SERVICE = 2000,        // Storage, config, logger
  ERROR_COMMUNICATION = 3000,  // WiFi, MQTT, HTTP
  ERROR_APPLICATION = 4000     // State machine, memory, system
};
```

### Error Severity Levels

```cpp
enum ErrorSeverity {
  ERROR_SEVERITY_WARNING = 1,    // Recoverable warning
  ERROR_SEVERITY_ERROR = 2,      // Error, system can continue
  ERROR_SEVERITY_CRITICAL = 3    // Critical, system unstable
};
```

### Initialization

```cpp
// Get singleton instance
ErrorTracker& errorTracker = ErrorTracker::getInstance();

// Initialize ErrorTracker (must call in setup())
void errorTracker.begin();
```

### Error Tracking - Primary API

```cpp
// Track error with full details
void errorTracker.trackError(uint16_t error_code, ErrorSeverity severity, const char* message);

// Track error with default severity (ERROR_SEVERITY_ERROR)
void errorTracker.trackError(uint16_t error_code, const char* message);
```

### Convenience Methods (Category-Specific)

```cpp
// Track hardware error
void errorTracker.logHardwareError(uint16_t code, const char* message);

// Track service error
void errorTracker.logServiceError(uint16_t code, const char* message);

// Track communication error
void errorTracker.logCommunicationError(uint16_t code, const char* message);

// Track application error
void errorTracker.logApplicationError(uint16_t code, const char* message);
```

### Error Retrieval

```cpp
// Get formatted error history (most recent first)
String errorTracker.getErrorHistory(uint8_t max_entries = 20) const;

// Get errors filtered by category
String errorTracker.getErrorsByCategory(ErrorCategory category, uint8_t max_entries = 10) const;

// Get total number of tracked errors
size_t errorTracker.getErrorCount() const;

// Get error count for specific category
size_t errorTracker.getErrorCountByCategory(ErrorCategory category) const;
```

### Error Status Queries

```cpp
// Check if any errors are currently active
bool errorTracker.hasActiveErrors() const;

// Check if any critical errors are active
bool errorTracker.hasCriticalErrors() const;

// Clear all tracked errors
void errorTracker.clearErrors();
```

### Error Utilities

```cpp
// Get category name for error code
static const char* errorTracker.getCategoryString(uint16_t error_code);

// Get category from error code
static ErrorCategory errorTracker.getCategory(uint16_t error_code);
```

### Error Entry Structure

```cpp
struct ErrorEntry {
  unsigned long timestamp;         // When error occurred (millis())
  uint16_t error_code;             // Error code (see error_codes.h)
  ErrorSeverity severity;          // Severity level (WARNING/ERROR/CRITICAL)
  char message[128];               // Error message (max 127 chars)
  uint8_t occurrence_count;        // Number of times this error occurred
  
  ErrorEntry();                    // Default constructor
};
```

### Usage Examples

```cpp
// Initialize error tracking
errorTracker.begin();

// Track errors with different severities
errorTracker.trackError(ERROR_I2C_INIT_FAILED, 
                       ERROR_SEVERITY_CRITICAL, 
                       "I2C bus initialization failed");

errorTracker.trackError(ERROR_SENSOR_READ_FAILED, 
                       "Temperature sensor read timeout");

// Using convenience methods
errorTracker.logHardwareError(ERROR_GPIO_RESERVED, "GPIO 5 already in use");
errorTracker.logCommunicationError(ERROR_MQTT_CONNECT_FAILED, "MQTT broker unreachable");

// Check error status
if (errorTracker.hasCriticalErrors()) {
  LOG_CRITICAL("System has critical errors!");
  logger.info(errorTracker.getErrorHistory(10));  // Show last 10 errors
}

// Filter errors by category
String hardware_errors = errorTracker.getErrorsByCategory(ERROR_HARDWARE, 5);
LOG_INFO(hardware_errors);

// Monitor error count
if (errorTracker.getErrorCountByCategory(ERROR_COMMUNICATION) > 5) {
  LOG_WARNING("Multiple communication errors detected");
}

// Clear errors after handling
errorTracker.clearErrors();
```

### MQTT Error Publishing

```cpp
// Enable MQTT error publishing (called after MQTT connection)
errorTracker.setMqttPublishCallback(callback, esp_id);

// Disable MQTT error publishing
errorTracker.clearMqttPublishCallback();
```

**Rate-Limiting:** MQTT error publishing is throttled to max 1 publish per error code per 60 seconds. Serial logging and the internal ring buffer are not affected by rate-limiting. Suppressed error counts are logged to serial when the throttle window expires.

### Design Notes

- **Circular buffer:** Automatically overwrites oldest errors when full (max 50)
- **Occurrence counting:** Duplicate errors increment occurrence counter instead of creating new entries
- **Logger integration:** All tracked errors are also logged to Logger
- **MQTT rate-limiting:** Max 1 MQTT publish per error code per 60s (32 hash slots, static allocation)
- **Categorization:** Error codes automatically map to categories based on numeric range
- **Severity tracking:** Critical errors can trigger emergency procedures

---

## HealthMonitor

### Header
```cpp
#include "error_handling/health_monitor.h"
```

Monitors system health metrics and publishes diagnostics snapshots via MQTT.

### Initialization

```cpp
// Get singleton instance
HealthMonitor& healthMonitor = HealthMonitor::getInstance();

// Initialize HealthMonitor (must call in setup())
bool healthMonitor.begin();

// Configure publish interval (default: 60000ms = 60s)
void healthMonitor.setPublishInterval(unsigned long interval_ms);

// Enable/disable change detection (default: true)
void healthMonitor.setChangeDetectionEnabled(bool enabled);
```

### Health Snapshot Generation

```cpp
// Get current health snapshot
HealthSnapshot healthMonitor.getCurrentSnapshot() const;

// Get snapshot as JSON string
String healthMonitor.getSnapshotJSON() const;
```

### Publishing

```cpp
// Publish snapshot immediately (ignores change detection)
void healthMonitor.publishSnapshot();

// Publish snapshot only if significant changes detected
void healthMonitor.publishSnapshotIfChanged();

// Loop method (call in main loop for automatic publishing)
void healthMonitor.loop();
```

### Status Getters

```cpp
// Get heap information
uint32_t healthMonitor.getHeapFree() const;
uint32_t healthMonitor.getHeapMinFree() const;
uint8_t healthMonitor.getHeapFragmentation() const;

// Get uptime
unsigned long healthMonitor.getUptimeSeconds() const;
```

### HealthSnapshot Structure

```cpp
struct HealthSnapshot {
    unsigned long timestamp;              // Seconds since boot
    uint32_t heap_free;                   // Free heap (bytes)
    uint32_t heap_min_free;               // Minimum free heap since boot
    uint8_t heap_fragmentation_percent;  // Heap fragmentation (0-100)
    unsigned long uptime_seconds;         // Uptime in seconds
    size_t error_count;                   // Total error count from ErrorTracker
    bool wifi_connected;                  // WiFi connection status
    int8_t wifi_rssi;                    // WiFi signal strength (dBm)
    bool mqtt_connected;                 // MQTT connection status
    uint8_t sensor_count;                 // Active sensor count
    uint8_t actuator_count;               // Active actuator count
    SystemState system_state;             // Current system state
};
```

### Change Detection

HealthMonitor publishes snapshots automatically when:
- **Heap change:** >20% relative change
- **RSSI change:** >10 dBm absolute change
- **Connection status:** WiFi or MQTT connection state changes
- **Component count:** Sensor or actuator count changes
- **System state:** SystemState changes
- **Error count:** >5 errors since last publish

**Thresholds:**
- `HEAP_CHANGE_THRESHOLD_PERCENT = 20`
- `RSSI_CHANGE_THRESHOLD_DBM = 10`

### MQTT Integration

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/diagnostics`  
**QoS:** 0 (at most once)  
**Frequency:** Every 60s (configurable) + on significant changes  
**TopicBuilder:** `TopicBuilder::buildSystemDiagnosticsTopic()`

**JSON Payload Example:**
```json
{
  "ts": 1735818000,
  "esp_id": "ESP_12AB34CD",
  "heap_free": 150000,
  "heap_min_free": 120000,
  "heap_fragmentation": 15,
  "uptime_seconds": 3600,
  "error_count": 3,
  "wifi_connected": true,
  "wifi_rssi": -65,
  "mqtt_connected": true,
  "sensor_count": 4,
  "actuator_count": 2,
  "system_state": "OPERATIONAL"
}
```

### Usage Examples

```cpp
// Initialize in setup()
healthMonitor.begin();
healthMonitor.setPublishInterval(60000);  // 60 seconds
healthMonitor.setChangeDetectionEnabled(true);

// In main loop()
void loop() {
    healthMonitor.loop();  // Publishes automatically if needed
}

// Manual snapshot
HealthSnapshot snapshot = healthMonitor.getCurrentSnapshot();
LOG_INFO("Heap free: " + String(snapshot.heap_free) + " bytes");
LOG_INFO("Uptime: " + String(snapshot.uptime_seconds) + " seconds");

// Get JSON for custom publishing
String json = healthMonitor.getSnapshotJSON();
mqttClient.publish(custom_topic, json);
```

### Design Notes

- **Singleton pattern:** Only one instance manages health monitoring
- **Change detection:** Reduces MQTT traffic by publishing only on significant changes
- **Automatic publishing:** `loop()` handles timing and change detection
- **Dependencies:** Uses WiFiManager, MQTTClient, SensorManager, ActuatorManager, ErrorTracker
- **Topic consistency:** Uses TopicBuilder for topic generation
- **QoS 0:** Diagnostics are non-critical (next snapshot in 60s)

---

## TopicBuilder

### Header
```cpp
#include "utils/topic_builder.h"
```

Generates MQTT topic strings for the 8 critical Phase 1 communication patterns.

### Configuration

```cpp
// Set ESP device ID for topic generation
static void TopicBuilder::setEspId(const char* esp_id);

// Set Kaiser device ID for topic generation
static void TopicBuilder::setKaiserId(const char* kaiser_id);
```

### Topic Generation Methods - Phase 1 Patterns

#### Pattern 1: Sensor Data Topic (GPIO-Specific)
```cpp
// Build topic for individual sensor data
static const char* TopicBuilder::buildSensorDataTopic(uint8_t gpio);
// Example output: "/kaiser/Kaiser0/esp/Esp0/sensor/gpio_5/data"
```

#### Pattern 2: Sensor Batch Topic (All Sensors)
```cpp
// Build topic for batch sensor data from all sensors
static const char* TopicBuilder::buildSensorBatchTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/sensor/batch"
```

#### Pattern 3: Actuator Command Topic (GPIO-Specific)
```cpp
// Build topic for sending commands to specific actuator
static const char* TopicBuilder::buildActuatorCommandTopic(uint8_t gpio);
// Example output: "/kaiser/Kaiser0/esp/Esp0/actuator/gpio_5/command"
```

#### Pattern 4: Actuator Status Topic (GPIO-Specific)
```cpp
// Build topic for actuator status feedback
static const char* TopicBuilder::buildActuatorStatusTopic(uint8_t gpio);
// Example output: "/kaiser/Kaiser0/esp/Esp0/actuator/gpio_5/status"
```

#### Pattern 5: System Heartbeat Topic
```cpp
// Build topic for periodic system heartbeat
static const char* TopicBuilder::buildSystemHeartbeatTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/system/heartbeat"
```

#### Pattern 6: System Command Topic
```cpp
// Build topic for receiving system commands
static const char* TopicBuilder::buildSystemCommandTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/system/command"
```

#### Pattern 7: Configuration Topic
```cpp
// Build topic for configuration updates
static const char* TopicBuilder::buildConfigTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/config"
```

#### Pattern 8: Broadcast Emergency Topic
```cpp
// Build topic for emergency broadcasts (all ESPs subscribe)
static const char* TopicBuilder::buildBroadcastEmergencyTopic();
// Example output: "/kaiser/Kaiser0/broadcast/emergency"
```

#### Pattern 9: Actuator Response Topic (Phase 5)
```cpp
// Build topic for actuator command responses
static const char* TopicBuilder::buildActuatorResponseTopic(uint8_t gpio);
// Example output: "/kaiser/Kaiser0/esp/Esp0/actuator/gpio_5/response"
```

#### Pattern 10: Actuator Alert Topic (Phase 5)
```cpp
// Build topic for actuator alerts (emergency stops, errors, etc.)
static const char* TopicBuilder::buildActuatorAlertTopic(uint8_t gpio);
// Example output: "/kaiser/Kaiser0/esp/Esp0/actuator/gpio_5/alert"
```

#### Pattern 11: Actuator Emergency Topic (Phase 5)
```cpp
// Build topic for actuator emergency commands (subscribe)
static const char* TopicBuilder::buildActuatorEmergencyTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/actuator/emergency"
```

#### Pattern 12: Config Response Topic
```cpp
// Build topic for configuration response (ACK/NACK)
static const char* TopicBuilder::buildConfigResponseTopic();
// Example output: "/kaiser/Kaiser0/esp/Esp0/config_response"
```

#### Pattern 13: System Diagnostics Topic (Phase 7)
```cpp
// Build topic for system diagnostics/health monitoring
static const char* TopicBuilder::buildSystemDiagnosticsTopic();
// Example output: "kaiser/god/esp/ESP_12AB34CD/system/diagnostics"
```

### Static Buffers

```cpp
static char topic_buffer_[256];   // Topic string buffer
static char esp_id_[32];          // Current ESP ID
static char kaiser_id_[64];       // Current Kaiser ID
```

### Usage Examples

```cpp
// Configure with IDs from ConfigManager
String esp_id = configManager.getESPId();
String kaiser_id = configManager.getKaiserId();
TopicBuilder::setEspId(esp_id.c_str());
TopicBuilder::setKaiserId(kaiser_id.c_str());

// Generate sensor data topic
const char* sensor_topic = TopicBuilder::buildSensorDataTopic(5);
mqttClient.publish(sensor_topic, "25.5");  // Publish temperature

// Generate actuator command topic
const char* actuator_topic = TopicBuilder::buildActuatorCommandTopic(12);
mqttClient.subscribe(actuator_topic);  // Subscribe to commands

// Generate batch sensor topic
const char* batch_topic = TopicBuilder::buildSensorBatchTopic();
mqttClient.publish(batch_topic, sensor_batch_json);

// Generate system topics
const char* heartbeat_topic = TopicBuilder::buildSystemHeartbeatTopic();
const char* command_topic = TopicBuilder::buildSystemCommandTopic();

// Emergency topic (broadcast to all ESPs)
const char* emergency_topic = TopicBuilder::buildBroadcastEmergencyTopic();
mqttClient.publish(emergency_topic, "SYSTEM_SHUTDOWN");
```

### Topic Pattern Structure

All topics follow this hierarchy:
```
/kaiser/{KAISER_ID}/esp/{ESP_ID}/sensor/{type}/{subtype}
/kaiser/{KAISER_ID}/esp/{ESP_ID}/actuator/{type}/{subtype}
/kaiser/{KAISER_ID}/esp/{ESP_ID}/system/{function}
/kaiser/{KAISER_ID}/esp/{ESP_ID}/config
/kaiser/{KAISER_ID}/broadcast/{emergency}
```

Where:
- `{KAISER_ID}` = Kaiser device ID (e.g., "Kaiser0")
- `{ESP_ID}` = ESP device ID (e.g., "Esp0")
- `{type}` = Component type ("gpio_N", "batch", "heartbeat", etc.)
- `{subtype}` = Operation ("data", "command", "status")

### Design Notes

- **Static class:** No instances, only static methods
- **Buffer reuse:** Returns pointer to static buffer—copy if needed for later use
- **Guard length:** 256-char buffer accommodates all Phase 1-5 patterns
- **Initialization required:** Must call `setEspId()` and `setKaiserId()` before generating topics
- **No validation:** Topics are generated without checking ID format—ensure valid IDs are provided
- **Buffer validation:** All methods use `validateTopicBuffer()` to detect truncation and encoding errors
- **Phase 5 additions:** `buildActuatorResponseTopic()`, `buildActuatorAlertTopic()`, `buildActuatorEmergencyTopic()`, and `buildConfigResponseTopic()` added in Phase 5
- **Phase 7 additions:** `buildSystemDiagnosticsTopic()` added in Phase 7

---

## GPIOManager

### Header
```cpp
#include "drivers/gpio_manager.h"
```

Hardware safety system preventing GPIO misuse and resource conflicts. **CRITICAL: Must initialize before any GPIO operations.**

### Initialization - CRITICAL

```cpp
// Get singleton instance
GPIOManager& gpioManager = GPIOManager::getInstance();

// ⚠️ MUST be called as FIRST action in setup()!
// Initializes all GPIO pins to INPUT_PULLUP safe mode
void gpioManager.initializeAllPinsToSafeMode();
```

**Why first?** Uninitialized GPIO pins are in undefined states and can trigger actuators, causing hardware damage.

### Pin Management

```cpp
// Request exclusive use of a GPIO pin
// Returns: true if pin is available and allocated
// owner: "sensor", "actuator", "system", etc.
// component_name: Specific name for debugging ("DS18B20", "Pump1", etc.)
bool gpioManager.requestPin(uint8_t gpio, const char* owner, const char* component_name);

// Release GPIO pin, returning it to safe mode (INPUT_PULLUP)
bool gpioManager.releasePin(uint8_t gpio);

// Configure pin mode (INPUT, OUTPUT, INPUT_PULLUP)
// Validates hardware limitations (e.g., can't use certain pins as output)
bool gpioManager.configurePinMode(uint8_t gpio, uint8_t mode);
```

### Pin Query Methods

```cpp
// Check if pin is available for allocation
bool gpioManager.isPinAvailable(uint8_t gpio) const;

// Check if pin is reserved (boot pins, UART, SPI, etc.)
bool gpioManager.isPinReserved(uint8_t gpio) const;

// Check if pin is currently in safe mode
bool gpioManager.isPinInSafeMode(uint8_t gpio) const;
```

### Emergency Safe Mode

```cpp
// Emergency function: Return ALL pins to safe mode
// Use in error conditions to prevent hardware damage
void gpioManager.enableSafeModeForAllPins();
```

### Information Methods

```cpp
// Get detailed information about a pin
GPIOPinInfo gpioManager.getPinInfo(uint8_t gpio) const;

// Print status of all GPIO pins to Serial (for debugging)
void gpioManager.printPinStatus() const;

// Get count of currently available pins
uint8_t gpioManager.getAvailablePinCount() const;
```

### Special PIN Management

```cpp
// Release I2C pins (SDA/SCL)
// ⚠️ WARNING: Only call if I2C will never be used!
void gpioManager.releaseI2CPins();
```

### GPIOPinInfo Structure

```cpp
struct GPIOPinInfo {
  uint8_t pin;                  // GPIO pin number
  char owner[32];               // Owner ("sensor", "actuator", "system")
  char component_name[32];      // Component name ("DS18B20", "Pump1")
  uint8_t mode;                 // Pin mode (INPUT, OUTPUT, INPUT_PULLUP)
  bool in_safe_mode;            // Whether pin is in safe mode (INPUT_PULLUP)
  
  GPIOPinInfo();                // Default constructor (initializes safely)
};
```

### Usage Examples

```cpp
// CRITICAL: Initialize safe mode FIRST!
void setup() {
  Serial.begin(115200);
  gpioManager.initializeAllPinsToSafeMode();  // ⚠️ MUST BE FIRST!
  
  // Now safe to initialize other systems
  logger.begin();
  storageManager.begin();
  
  // Request pins for components
  gpioManager.requestPin(5, "sensor", "Temperature_DS18B20");
  gpioManager.requestPin(12, "actuator", "Pump_1");
  
  // Configure pin modes
  gpioManager.configurePinMode(5, INPUT);
  gpioManager.configurePinMode(12, OUTPUT);
}

// Check pin availability
if (gpioManager.isPinAvailable(15)) {
  gpioManager.requestPin(15, "sensor", "New_Sensor");
  gpioManager.configurePinMode(15, INPUT);
} else {
  LOG_WARNING("GPIO 15 already in use");
}

// Query pin status
GPIOPinInfo pin_info = gpioManager.getPinInfo(12);
LOG_INFO("Pin 12 owner: " + String(pin_info.owner));
LOG_INFO("Pin 12 component: " + String(pin_info.component_name));

// Monitor available pins
uint8_t available = gpioManager.getAvailablePinCount();
LOG_INFO("Available pins: " + String(available));

// Print complete status
gpioManager.printPinStatus();

// Emergency: Return all pins to safe mode
if (errorTracker.hasCriticalErrors()) {
  gpioManager.enableSafeModeForAllPins();
  LOG_CRITICAL("All GPIO pins returned to safe mode!");
}

// Release pin when no longer needed
gpioManager.releasePin(5);

// Release I2C pins if I2C is not used
gpioManager.releaseI2CPins();  // Frees SDA/SCL for other uses
```

### GPIO Reservations (ESP32 WROOM-32)

**Reserved pins** (cannot be used):
- GPIO 6, 8, 9, 10, 11: SPI Flash
- GPIO 0: Boot/Strapping (use with care)
- GPIO 12: Boot/Strapping (use with care)
- GPIO 15: Strapping

**Input-only pins**:
- GPIO 34, 35, 36, 39: No output capability

**Special considerations**:
- Pins used for UART (typically 1, 3)
- Pins used for I2C (typically 21, 22)
- Pins used for SPI (typically 18, 19, 23)

### Design Notes

- **Singleton pattern:** Only one instance manages all GPIO
- **Safe-mode critical:** Always initializes all pins to INPUT_PULLUP
- **Allocation tracking:** Prevents conflicts and resource leaks
- **Board-specific:** Handles ESP32 WROOM-32 and XIAO ESP32C3 variants
- **Emergency mode:** Can force all pins to safe state for recovery
- **Debugging support:** `printPinStatus()` helps diagnose allocation issues

---

## Error Codes Reference

All error codes are organized into four categories with specific numeric ranges.

### Hardware Errors (1000-1999)

**GPIO Errors:**
- `ERROR_GPIO_RESERVED` (1001) - Pin already reserved
- `ERROR_GPIO_CONFLICT` (1002) - Pin allocation conflict
- `ERROR_GPIO_INIT_FAILED` (1003) - Initialization failed
- `ERROR_GPIO_INVALID_MODE` (1004) - Invalid pin mode
- `ERROR_GPIO_READ_FAILED` (1005) - Read operation failed
- `ERROR_GPIO_WRITE_FAILED` (1006) - Write operation failed

**I2C Errors:**
- `ERROR_I2C_INIT_FAILED` (1010) - I2C bus initialization failed
- `ERROR_I2C_DEVICE_NOT_FOUND` (1011) - I2C device not found at address
- `ERROR_I2C_READ_FAILED` (1012) - I2C read operation failed
- `ERROR_I2C_WRITE_FAILED` (1013) - I2C write operation failed
- `ERROR_I2C_BUS_ERROR` (1014) - I2C bus error

**OneWire Errors:**
- `ERROR_ONEWIRE_INIT_FAILED` (1020) - OneWire initialization failed
- `ERROR_ONEWIRE_NO_DEVICES` (1021) - No devices found on bus
- `ERROR_ONEWIRE_READ_FAILED` (1022) - OneWire read operation failed

**PWM Errors:**
- `ERROR_PWM_INIT_FAILED` (1030) - PWM initialization failed
- `ERROR_PWM_CHANNEL_FULL` (1031) - No free PWM channels
- `ERROR_PWM_SET_FAILED` (1032) - PWM value set failed

**Sensor Errors:**
- `ERROR_SENSOR_READ_FAILED` (1040) - Sensor read failed
- `ERROR_SENSOR_INIT_FAILED` (1041) - Sensor initialization failed
- `ERROR_SENSOR_NOT_FOUND` (1042) - Sensor not found
- `ERROR_SENSOR_TIMEOUT` (1043) - Sensor read timeout

**Actuator Errors:**
- `ERROR_ACTUATOR_SET_FAILED` (1050) - Actuator command failed
- `ERROR_ACTUATOR_INIT_FAILED` (1051) - Actuator initialization failed
- `ERROR_ACTUATOR_NOT_FOUND` (1052) - Actuator not found
- `ERROR_ACTUATOR_CONFLICT` (1053) - Actuator resource conflict

### Service Errors (2000-2999)

**NVS Storage Errors:**
- `ERROR_NVS_INIT_FAILED` (2001) - NVS initialization failed
- `ERROR_NVS_READ_FAILED` (2002) - NVS read operation failed
- `ERROR_NVS_WRITE_FAILED` (2003) - NVS write operation failed
- `ERROR_NVS_NAMESPACE_FAILED` (2004) - Namespace operation failed
- `ERROR_NVS_CLEAR_FAILED` (2005) - Namespace clear failed

**Configuration Errors:**
- `ERROR_CONFIG_INVALID` (2010) - Invalid configuration data
- `ERROR_CONFIG_MISSING` (2011) - Required configuration missing
- `ERROR_CONFIG_LOAD_FAILED` (2012) - Configuration load failed
- `ERROR_CONFIG_SAVE_FAILED` (2013) - Configuration save failed
- `ERROR_CONFIG_VALIDATION` (2014) - Configuration validation failed

**Logger Errors:**
- `ERROR_LOGGER_INIT_FAILED` (2020) - Logger initialization failed
- `ERROR_LOGGER_BUFFER_FULL` (2021) - Log buffer overflow

**Storage Errors:**
- `ERROR_STORAGE_INIT_FAILED` (2030) - Storage manager initialization failed
- `ERROR_STORAGE_READ_FAILED` (2031) - Storage read operation failed
- `ERROR_STORAGE_WRITE_FAILED` (2032) - Storage write operation failed

### Communication Errors (3000-3999)

**WiFi Errors:**
- `ERROR_WIFI_INIT_FAILED` (3001) - WiFi initialization failed
- `ERROR_WIFI_CONNECT_TIMEOUT` (3002) - WiFi connection timeout
- `ERROR_WIFI_CONNECT_FAILED` (3003) - WiFi connection failed
- `ERROR_WIFI_DISCONNECT` (3004) - WiFi disconnected
- `ERROR_WIFI_NO_SSID` (3005) - SSID not found

**MQTT Errors:**
- `ERROR_MQTT_INIT_FAILED` (3010) - MQTT initialization failed
- `ERROR_MQTT_CONNECT_FAILED` (3011) - MQTT connection failed
- `ERROR_MQTT_PUBLISH_FAILED` (3012) - MQTT publish failed
- `ERROR_MQTT_SUBSCRIBE_FAILED` (3013) - MQTT subscribe failed
- `ERROR_MQTT_DISCONNECT` (3014) - MQTT disconnected
- `ERROR_MQTT_BUFFER_FULL` (3015) - MQTT buffer overflow
- `ERROR_MQTT_PAYLOAD_INVALID` (3016) - MQTT payload invalid

**HTTP Errors:**
- `ERROR_HTTP_INIT_FAILED` (3020) - HTTP initialization failed
- `ERROR_HTTP_REQUEST_FAILED` (3021) - HTTP request failed
- `ERROR_HTTP_RESPONSE_INVALID` (3022) - HTTP response invalid
- `ERROR_HTTP_TIMEOUT` (3023) - HTTP operation timeout

**Network Errors:**
- `ERROR_NETWORK_UNREACHABLE` (3030) - Network unreachable
- `ERROR_DNS_FAILED` (3031) - DNS resolution failed
- `ERROR_CONNECTION_LOST` (3032) - Connection lost

### Application Errors (4000-4999)

**State Machine Errors:**
- `ERROR_STATE_INVALID` (4001) - Invalid system state
- `ERROR_STATE_TRANSITION` (4002) - Invalid state transition
- `ERROR_STATE_MACHINE_STUCK` (4003) - State machine stuck

**Operation Errors:**
- `ERROR_OPERATION_TIMEOUT` (4010) - Operation timeout
- `ERROR_OPERATION_FAILED` (4011) - Operation failed
- `ERROR_OPERATION_CANCELLED` (4012) - Operation cancelled

**Command Errors:**
- `ERROR_COMMAND_INVALID` (4020) - Invalid command
- `ERROR_COMMAND_PARSE_FAILED` (4021) - Command parsing failed
- `ERROR_COMMAND_EXEC_FAILED` (4022) - Command execution failed

**Payload Errors:**
- `ERROR_PAYLOAD_INVALID` (4030) - Invalid payload
- `ERROR_PAYLOAD_TOO_LARGE` (4031) - Payload too large
- `ERROR_PAYLOAD_PARSE_FAILED` (4032) - Payload parsing failed

**Memory Errors:**
- `ERROR_MEMORY_FULL` (4040) - Memory full
- `ERROR_MEMORY_ALLOCATION` (4041) - Memory allocation failed
- `ERROR_MEMORY_LEAK` (4042) - Memory leak detected

**System Errors:**
- `ERROR_SYSTEM_INIT_FAILED` (4050) - System initialization failed
- `ERROR_SYSTEM_RESTART` (4051) - System restart required
- `ERROR_SYSTEM_SAFE_MODE` (4052) - System in safe mode

**Task Errors:**
- `ERROR_TASK_FAILED` (4060) - Task failed
- `ERROR_TASK_TIMEOUT` (4061) - Task timeout
- `ERROR_TASK_QUEUE_FULL` (4062) - Task queue full

---

## Type Definitions

### SystemState Enum

```cpp
enum SystemState {
  STATE_BOOT = 0,                   // System booting
  STATE_WIFI_SETUP,                 // WiFi configuration
  STATE_WIFI_CONNECTED,             // WiFi connected
  STATE_MQTT_CONNECTING,            // Connecting to MQTT
  STATE_MQTT_CONNECTED,             // Connected to MQTT
  STATE_AWAITING_USER_CONFIG,       // Waiting for configuration
  STATE_ZONE_CONFIGURED,            // Zone configuration complete
  STATE_SENSORS_CONFIGURED,         // Sensors configured
  STATE_OPERATIONAL,                // System operational
  STATE_LIBRARY_DOWNLOADING,        // Downloading library (Phase 3 optional)
  STATE_SAFE_MODE,                  // Safe mode (error recovery)
  STATE_ERROR                       // Error state
};

// Convert SystemState to string
String getSystemStateString(SystemState state);
```

### LogLevel Enum

```cpp
enum LogLevel {
  LOG_DEBUG = 0,       // Detailed diagnostic information
  LOG_INFO = 1,        // General informational messages
  LOG_WARNING = 2,     // Warning conditions
  LOG_ERROR = 3,       // Error conditions
  LOG_CRITICAL = 4     // Critical errors, system unstable
};
```

### ErrorCategory Enum

```cpp
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM, sensors, actuators
  ERROR_SERVICE = 2000,        // Storage, config, logger
  ERROR_COMMUNICATION = 3000,  // WiFi, MQTT, HTTP
  ERROR_APPLICATION = 4000     // State machine, memory, system
};
```

### ErrorSeverity Enum

```cpp
enum ErrorSeverity {
  ERROR_SEVERITY_WARNING = 1,    // Recoverable warning
  ERROR_SEVERITY_ERROR = 2,      // Error, system can continue
  ERROR_SEVERITY_CRITICAL = 3    // Critical, system unstable
};
```

---

## Best Practices & Design Patterns

### 1. Initialization Order (Critical!)

```cpp
void setup() {
  Serial.begin(115200);
  
  // 1. GPIO safe mode FIRST (prevents hardware damage)
  gpioManager.initializeAllPinsToSafeMode();
  
  // 2. Core services
  logger.begin();
  storageManager.begin();
  errorTracker.begin();
  
  // 3. Configuration
  configManager.begin();
  configManager.loadAllConfigs();
  
  // 4. Topic builder
  TopicBuilder::setEspId(configManager.getESPId().c_str());
  TopicBuilder::setKaiserId(configManager.getKaiserId().c_str());
  
  // 5. Application-specific
  // ... your code ...
}
```

### 2. Error Handling Pattern

```cpp
if (!storageManager.begin()) {
  errorTracker.logServiceError(ERROR_STORAGE_INIT_FAILED, 
                              "StorageManager initialization failed");
  logger.critical("Fatal: Cannot continue without storage");
  return;
}
```

### 3. Logging Pattern

```cpp
// Prefer macros for fixed messages
LOG_INFO("System initialized");

// Use direct methods for dynamic messages
String message = "Device temperature: " + String(temp);
logger.info(message);
```

### 4. Resource Cleanup

```cpp
// Allocate resource
gpioManager.requestPin(5, "sensor", "Temperature");

// Use resource
// ... operations ...

// Release resource
gpioManager.releasePin(5);
```

### 5. Configuration Access Pattern

```cpp
// Load configuration once
configManager.begin();
configManager.loadAllConfigs();

// Access from cache frequently
const WiFiConfig& wifi = configManager.getWiFiConfig();
String esp_id = configManager.getESPId();
```

---

## Summary Table

| Module | Purpose | Singleton | Global Instance |
|--------|---------|-----------|-----------------|
| **Logger** | Logging with circular buffer | Yes | `extern Logger& logger` |
| **StorageManager** | NVS abstraction (key-value storage) | Yes | `extern StorageManager& storageManager` |
| **ConfigManager** | Configuration orchestration | Yes | `extern ConfigManager& configManager` |
| **ErrorTracker** | Error tracking with categorization | Yes | `extern ErrorTracker& errorTracker` |
| **HealthMonitor** | System health monitoring | Yes | `extern HealthMonitor& healthMonitor` |
| **TopicBuilder** | MQTT topic generation | Static class (no instance) | `TopicBuilder::` prefix |
| **GPIOManager** | GPIO safety & allocation | Yes | `extern GPIOManager& gpioManager` |

---

## Hardware Abstraction Layer (Phase 3)

### I2C Bus Manager

#### Header
```cpp
#include "drivers/i2c_bus.h"
```

#### Singleton Access
```cpp
I2CBusManager& i2cBusManager = I2CBusManager::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize I2C bus (loads HardwareConfig, reserves GPIO pins)
bool begin();

// Deinitialize I2C bus (releases GPIO pins)
void end();

// Check initialization status
bool isInitialized() const;
```

#### Bus Operations
```cpp
// Scan I2C bus for devices (0x08-0x77)
// addresses: output array for found device addresses
// max_addresses: size of addresses array
// found_count: output parameter with number of devices found
bool scanBus(uint8_t addresses[], uint8_t max_addresses, uint8_t& found_count);

// Check if specific device is present
bool isDevicePresent(uint8_t address);
```

#### Raw Data Operations (Pi-Enhanced Mode)
```cpp
// Read raw bytes from I2C device register
bool readRaw(uint8_t device_address, uint8_t register_address, 
             uint8_t* buffer, size_t length);

// Write raw bytes to I2C device register
bool writeRaw(uint8_t device_address, uint8_t register_address,
              const uint8_t* data, size_t length);
```

#### Status Queries
```cpp
// Get detailed bus status string
String getBusStatus() const;  // Format: "I2C[SDA:4,SCL:5,Freq:100kHz,Init:true]"
```

#### Example Usage
```cpp
// Initialize
if (!i2cBusManager.begin()) {
    LOG_ERROR("I2C initialization failed");
    return;
}

// Scan for devices
uint8_t addresses[10];
uint8_t found;
i2cBusManager.scanBus(addresses, 10, found);

// Read from device
uint8_t buffer[2];
if (i2cBusManager.readRaw(0x44, 0x00, buffer, 2)) {
    // Process raw data (send to God-Kaiser for processing)
}
```

---

### OneWire Bus Manager

#### Header
```cpp
#include "drivers/onewire_bus.h"
```

#### Singleton Access
```cpp
OneWireBusManager& oneWireBusManager = OneWireBusManager::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize OneWire bus
bool begin();

// Deinitialize OneWire bus
void end();

// Check initialization status
bool isInitialized() const;
```

#### Device Discovery
```cpp
// Scan OneWire bus for devices
// rom_codes: output array [max_devices][8] for ROM codes
// max_devices: maximum number of devices to scan
// found_count: output parameter with number of devices found
bool scanDevices(uint8_t rom_codes[][8], uint8_t max_devices, uint8_t& found_count);

// Check if specific device is present
bool isDevicePresent(const uint8_t rom_code[8]);
```

#### Raw Temperature Reading (Pi-Enhanced Mode)
```cpp
// Read raw temperature from DS18B20
// rom_code: 8-byte ROM code of device
// raw_value: output 12-bit signed temperature value
//            Range: -550 to +1250 (represents -55.0°C to +125.0°C)
//            Resolution: 0.0625°C per LSB
// NOTE: NO local conversion - raw value sent to God-Kaiser
bool readRawTemperature(const uint8_t rom_code[8], int16_t& raw_value);
```

#### Status Queries
```cpp
// Get detailed bus status string
String getBusStatus() const;  // Format: "OneWire[Pin:6,Init:true]"
```

#### Example Usage
```cpp
// Initialize
if (!oneWireBusManager.begin()) {
    LOG_ERROR("OneWire initialization failed");
    return;
}

// Discover devices
uint8_t rom_codes[5][8];
uint8_t found;
oneWireBusManager.scanDevices(rom_codes, 5, found);

// Read temperature
int16_t raw_temp;
if (oneWireBusManager.readRawTemperature(rom_codes[0], raw_temp)) {
    // Send raw value to God-Kaiser for processing
    // Server will convert: temp_celsius = raw_temp * 0.0625
}
```

---

### PWM Controller

#### Header
```cpp
#include "drivers/pwm_controller.h"
```

#### Singleton Access
```cpp
PWMController& pwmController = PWMController::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize PWM controller (configures all channels)
bool begin();

// Deinitialize PWM controller (detaches all channels)
void end();

// Check initialization status
bool isInitialized() const;
```

#### Channel Management
```cpp
// Attach GPIO to PWM channel
// gpio: GPIO pin to attach
// channel_out: output parameter with assigned channel number
bool attachChannel(uint8_t gpio, uint8_t& channel_out);

// Detach PWM channel
bool detachChannel(uint8_t channel);

// Check if channel is attached
bool isChannelAttached(uint8_t channel) const;

// Get channel number for GPIO
uint8_t getChannelForGPIO(uint8_t gpio) const;  // Returns 255 if not found
```

#### PWM Configuration
```cpp
// Set PWM frequency (1 Hz - 40 MHz)
bool setFrequency(uint8_t channel, uint32_t frequency);

// Set PWM resolution (1-16 bits)
bool setResolution(uint8_t channel, uint8_t resolution_bits);
```

#### PWM Output Control
```cpp
// Set duty cycle (absolute value)
// duty_cycle: 0 to (2^resolution - 1)
// Example: For 12-bit resolution, range is 0-4095
bool write(uint8_t channel, uint32_t duty_cycle);

// Set duty cycle (percentage)
// percent: 0.0 to 100.0
bool writePercent(uint8_t channel, float percent);
```

#### Status Queries
```cpp
// Get detailed status of all channels
String getChannelStatus() const;
```

#### Example Usage
```cpp
// Initialize
if (!pwmController.begin()) {
    LOG_ERROR("PWM initialization failed");
    return;
}

// Attach channel
uint8_t channel;
if (pwmController.attachChannel(10, channel)) {
    // Set to 50% duty cycle
    pwmController.writePercent(channel, 50.0);
    
    // Or set absolute value (2048 = 50% of 4095 for 12-bit)
    pwmController.write(channel, 2048);
}
```

---

## Hardware Configuration

Phase 3 modules automatically load board-specific configuration:

### XIAO ESP32-C3
```cpp
I2C:     SDA = GPIO 4,  SCL = GPIO 5,  Frequency = 100 kHz
OneWire: Pin = GPIO 6
PWM:     6 Channels, Frequency = 1 kHz, Resolution = 12-bit
```

### ESP32-WROOM-32
```cpp
I2C:     SDA = GPIO 21, SCL = GPIO 22, Frequency = 100 kHz
OneWire: Pin = GPIO 4
PWM:     16 Channels, Frequency = 1 kHz, Resolution = 12-bit
```

All pins are automatically reserved via GPIOManager during initialization.

---

## Error Codes Reference - Phase 3

### I2C Error Codes (1010-1014)
```cpp
ERROR_I2C_INIT_FAILED       1010  // I2C bus initialization failed
ERROR_I2C_DEVICE_NOT_FOUND  1011  // I2C device not found at address
ERROR_I2C_READ_FAILED       1012  // I2C read operation failed
ERROR_I2C_WRITE_FAILED      1013  // I2C write operation failed
ERROR_I2C_BUS_ERROR         1014  // I2C bus error (timeout, SCL/SDA stuck)
```

### OneWire Error Codes (1020-1022)
```cpp
ERROR_ONEWIRE_INIT_FAILED   1020  // OneWire initialization failed
ERROR_ONEWIRE_NO_DEVICES    1021  // No devices found on bus
ERROR_ONEWIRE_READ_FAILED   1022  // OneWire read operation failed
```

### PWM Error Codes (1030-1032)
```cpp
ERROR_PWM_INIT_FAILED       1030  // PWM initialization failed
ERROR_PWM_CHANNEL_FULL      1031  // No free PWM channels
ERROR_PWM_SET_FAILED        1032  // PWM value set failed
```

### Error Handling Example
```cpp
if (!i2cBusManager.readRaw(0x44, 0x00, buffer, 2)) {
    // Error automatically logged to ErrorTracker
    // Check error with: errorTracker.getErrorHistory()
}
```

---

## Communication Layer (Phase 2)

### WiFiManager

#### Header
```cpp
#include "services/communication/wifi_manager.h"
```

#### Singleton Access
```cpp
WiFiManager& wifiManager = WiFiManager::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize WiFi manager
bool begin();

// Connect to WiFi network
bool connect(const WiFiConfig& config);

// Disconnect from WiFi
bool disconnect();

// Check connection status
bool isConnected() const;

// Attempt reconnection
void reconnect();

// Monitor connection (call in loop)
void loop();
```

#### Status Queries
```cpp
// Get connection status string
String getConnectionStatus() const;

// Get WiFi signal strength (RSSI)
int8_t getRSSI() const;

// Get local IP address
IPAddress getLocalIP() const;

// Get connected SSID
String getSSID() const;
```

#### Example Usage
```cpp
// Initialize
wifiManager.begin();

// Connect
WiFiConfig config;
config.ssid = "MyNetwork";
config.password = "MyPassword";
wifiManager.connect(config);

// Monitor in loop
void loop() {
    wifiManager.loop();
}
```

---

### MQTTClient

#### Header
```cpp
#include "services/communication/mqtt_client.h"
```

#### Singleton Access
```cpp
MQTTClient& mqttClient = MQTTClient::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize MQTT client
bool begin();

// Connect to MQTT broker
bool connect(const MQTTConfig& config);

// Disconnect from broker
bool disconnect();

// Check connection status
bool isConnected() const;

// Attempt reconnection
void reconnect();

// Monitor connection (call in loop)
void loop();
```

#### Authentication
```cpp
// Transition from anonymous to authenticated mode
bool transitionToAuthenticated(const String& username, const String& password);

// Check if in anonymous mode
bool isAnonymousMode() const;
```

#### Publishing
```cpp
// Publish message
bool publish(const String& topic, const String& payload, uint8_t qos = 1);

// Publish with retry logic
bool safePublish(const String& topic, const String& payload, uint8_t qos = 1, uint8_t retries = 3);
```

#### Subscription
```cpp
// Subscribe to topic
bool subscribe(const String& topic);

// Unsubscribe from topic
bool unsubscribe(const String& topic);

// Set message callback
void setCallback(std::function<void(const String&, const String&)> callback);
```

#### Heartbeat
```cpp
// Publish heartbeat (automatic every 60s)
void publishHeartbeat();
```

#### Status Queries
```cpp
// Get connection status string
String getConnectionStatus() const;

// Get connection attempt count
uint16_t getConnectionAttempts() const;

// Check for offline messages
bool hasOfflineMessages() const;

// Get offline message count
uint16_t getOfflineMessageCount() const;
```

#### MQTTConfig Structure
```cpp
struct MQTTConfig {
    String server;              // Broker IP/Hostname
    uint16_t port;             // Broker Port (default: 1883/8883)
    String client_id;           // ESP32 Client ID
    String username;            // Optional (empty = anonymous)
    String password;            // Optional (empty = anonymous)
    int keepalive;              // Keepalive Interval (default: 60s)
    int timeout;                // Connection Timeout (default: 10s)
};
```

#### Example Usage
```cpp
// Initialize
mqttClient.begin();

// Connect
MQTTConfig config;
config.server = "192.168.1.100";
config.port = 1883;
config.client_id = configManager.getESPId();
config.username = "";  // Anonymous mode
config.password = "";
mqttClient.connect(config);

// Subscribe
mqttClient.subscribe(TopicBuilder::buildSystemCommandTopic());

// Set callback
mqttClient.setCallback([](const String& topic, const String& payload) {
    LOG_INFO("MQTT message: " + topic);
});

// Monitor in loop
void loop() {
    mqttClient.loop();
}
```

---

## Sensor System (Phase 4)

### HTTPClient

#### Header
```cpp
#include "services/communication/http_client.h"
```

#### Singleton Access
```cpp
HTTPClient& httpClient = HTTPClient::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize HTTP client
bool begin();

// Deinitialize HTTP client
void end();

// Check initialization status
bool isInitialized() const;
```

#### HTTP Requests
```cpp
// POST request (Primary API - const char*)
HTTPResponse post(const char* url, const char* payload, 
                 const char* content_type = "application/json",
                 int timeout_ms = 5000);

// POST request (String wrapper)
inline HTTPResponse post(const String& url, const String& payload,
                        const String& content_type = "application/json",
                        int timeout_ms = 5000);

// GET request
HTTPResponse get(const char* url, int timeout_ms = 5000);

// GET request (String wrapper)
inline HTTPResponse get(const String& url, int timeout_ms = 5000);
```

#### Configuration
```cpp
// Set default timeout
void setTimeout(int timeout_ms);

// Get current timeout
int getTimeout() const;
```

#### HTTPResponse Structure
```cpp
struct HTTPResponse {
    int status_code = 0;        // HTTP status code (200, 404, etc.)
    String body;                // Response body (max 1KB for sensor responses)
    bool success = false;       // true if status_code 2xx
    char error_message[128];    // Error message if failed
};
```

#### Example Usage
```cpp
// Initialize
httpClient.begin();

// POST request
String url = "http://192.168.1.100:8000/api/v1/sensors/process";
String payload = "{\"gpio\":4,\"sensor_type\":\"ph_sensor\",\"raw_value\":2048}";
HTTPResponse response = httpClient.post(url, payload);

if (response.success) {
    LOG_INFO("Response: " + response.body);
} else {
    LOG_ERROR("HTTP Error: " + String(response.error_message));
}
```

---

### PiEnhancedProcessor

#### Header
```cpp
#include "services/sensor/pi_enhanced_processor.h"
```

#### Singleton Access
```cpp
PiEnhancedProcessor& piEnhancedProcessor = PiEnhancedProcessor::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize processor
bool begin();

// Deinitialize processor
void end();
```

#### Raw Data Processing
```cpp
// Send raw sensor data to God-Kaiser Server
bool sendRawData(const RawSensorData& data, ProcessedSensorData& processed_out);
```

#### Server Status
```cpp
// Check if Pi server is available
bool isPiAvailable() const;

// Get server address
String getPiServerAddress() const;

// Get server port
uint16_t getPiServerPort() const;

// Get last response time
unsigned long getLastResponseTime() const;
```

#### Circuit-Breaker Pattern
```cpp
// Check if circuit breaker is open (server unavailable)
bool isCircuitOpen() const;

// Manually reset circuit breaker
void resetCircuitBreaker();

// Get consecutive failure count
uint8_t getConsecutiveFailures() const;
```

#### Data Structures
```cpp
struct RawSensorData {
    uint8_t gpio;               // GPIO pin number
    String sensor_type;          // "ph_sensor", "temperature_ds18b20", etc.
    uint32_t raw_value;          // ADC value (0-4095) or OneWire raw
    unsigned long timestamp;     // Timestamp in milliseconds
    String metadata;             // Optional: JSON with additional info
};

struct ProcessedSensorData {
    float value;                 // Processed value (e.g., 7.2 pH)
    String unit;                 // "pH", "°C", "ppm", etc.
    String quality;              // "excellent", "good", "fair", "poor", "bad", "stale"
    unsigned long timestamp;     // Timestamp
    bool valid;                  // true if processing successful
    String error_message;        // Error message if failed
};
```

#### Example Usage
```cpp
// Initialize
piEnhancedProcessor.begin();

// Send raw data
RawSensorData raw_data;
raw_data.gpio = 4;
raw_data.sensor_type = "ph_sensor";
raw_data.raw_value = 2048;
raw_data.timestamp = millis();
raw_data.metadata = "{}";

ProcessedSensorData processed;
if (piEnhancedProcessor.sendRawData(raw_data, processed)) {
    LOG_INFO("Processed value: " + String(processed.value) + " " + processed.unit);
} else {
    LOG_ERROR("Processing failed: " + processed.error_message);
}

// Check circuit breaker
if (piEnhancedProcessor.isCircuitOpen()) {
    LOG_WARNING("Pi server unavailable, circuit breaker open");
}
```

---

### SensorManager

#### Header
```cpp
#include "services/sensor/sensor_manager.h"
```

#### Singleton Access
```cpp
SensorManager& sensorManager = SensorManager::getInstance();
```

#### Lifecycle Management
```cpp
// Initialize sensor manager
bool begin();

// Deinitialize sensor manager
void end();

// Check initialization status
bool isInitialized() const;
```

#### Sensor Configuration
```cpp
// Configure a sensor
bool configureSensor(const SensorConfig& config);

// Remove a sensor
bool removeSensor(uint8_t gpio);

// Get sensor configuration
SensorConfig getSensorConfig(uint8_t gpio) const;

// Check if sensor exists on GPIO
bool hasSensorOnGPIO(uint8_t gpio) const;

// Get active sensor count
uint8_t getActiveSensorCount() const;
```

#### Sensor Reading
```cpp
// Perform measurement for a specific GPIO-based sensor
bool performMeasurement(uint8_t gpio, SensorReading& reading_out);

// Perform measurements for all active sensors (publishes via MQTT automatically)
void performAllMeasurements();
```

#### Raw Data Reading Methods
```cpp
// Read raw analog value
uint32_t readRawAnalog(uint8_t gpio);

// Read raw digital value
uint32_t readRawDigital(uint8_t gpio);

// Read raw I2C data
bool readRawI2C(uint8_t gpio, uint8_t device_address, 
                uint8_t reg, uint8_t* buffer, size_t len);

// Read raw OneWire data
bool readRawOneWire(uint8_t gpio, const uint8_t rom[8], int16_t& raw_value);
```

#### Legacy Phase 3 Methods
```cpp
// Perform I2C measurement (Phase 3 compatibility)
bool performI2CMeasurement(uint8_t device_address, uint8_t reg, 
                           uint8_t* buffer, size_t len);

// Perform OneWire measurement (Phase 3 compatibility)
bool performOneWireMeasurement(const uint8_t rom[8], int16_t& raw_value);
```

#### Status Queries
```cpp
// Get sensor info string
String getSensorInfo(uint8_t gpio) const;
```

#### SensorConfig Structure
```cpp
struct SensorConfig {
    uint8_t gpio = 255;                    // GPIO pin
    String sensor_type = "";               // "ph_sensor", "temperature_ds18b20", etc.
    String sensor_name = "";               // User-defined name
    String subzone_id = "";                // Subzone assignment
    bool active = false;                   // Sensor active?
    bool raw_mode = true;                  // Always true (raw data mode)
    uint32_t last_raw_value = 0;           // Last raw value (ADC 0-4095)
    unsigned long last_reading = 0;        // Timestamp of last reading
};
```

#### SensorReading Structure
```cpp
struct SensorReading {
    uint8_t gpio;                          // GPIO pin
    String sensor_type;                    // Sensor type
    uint32_t raw_value;                    // ADC value
    float processed_value;                 // Processed value from server
    String unit;                           // Unit from server
    String quality;                        // Quality from server
    unsigned long timestamp;               // Timestamp
    bool valid;                            // true if reading successful
    String error_message;                  // Error message if failed
    uint32_t window_ms;                    // Pulse-counting window in ms (0 = non-pulse sensor)
};
```

#### Example Usage
```cpp
// Initialize
sensorManager.begin();

// Configure sensor
SensorConfig config;
config.gpio = 4;
config.sensor_type = "ph_sensor";
config.sensor_name = "Boden pH";
config.subzone_id = "zone_1";
config.active = true;
config.raw_mode = true;

if (sensorManager.configureSensor(config)) {
    LOG_INFO("Sensor configured on GPIO " + String(config.gpio));
}

// Perform measurement for specific sensor
SensorReading reading;
if (sensorManager.performMeasurement(4, reading)) {
    LOG_INFO("Value: " + String(reading.processed_value) + " " + reading.unit);
}

// Perform all measurements (automatic MQTT publishing)
sensorManager.performAllMeasurements();

// In main loop
void loop() {
    sensorManager.performAllMeasurements();  // Measures all sensors every 30s
}
```

---

## Actuator System (Phase 5 - Complete)

### ActuatorManager

#### Header
```cpp
#include "services/actuator/actuator_manager.h"
```

#### Singleton Access
```cpp
ActuatorManager& actuatorManager = ActuatorManager::getInstance();
```

#### Memory Management

**Memory-Safe Design:**
- Drivers werden als `std::unique_ptr<IActuatorDriver>` gespeichert
- Automatische Deallocation beim `removeActuator()` oder `end()`
- RAII-Pattern verhindert Memory-Leaks
- Move-Semantics für effiziente Ownership-Transfer

**Implementation:**
```cpp
// In actuator_manager.cpp:
auto driver = createDriver(config.actuator_type);  // unique_ptr created
slot->driver = std::move(driver);                  // Ownership transferred
// Wenn slot->driver überschrieben wird: alter Driver automatisch deleted
```

**Heap-Usage:**
- RegisteredActuator Array: 12 slots × ~150 bytes = ~2KB
- Driver Objects: ~100-200 bytes pro Driver
- **Total:** ~2-4KB (abhängig von Driver-Count)

**Max Actuators:**
- XIAO ESP32-C3: 8 Actuators
- ESP32 WROOM-32: 12 Actuators

#### Lifecycle Management
```cpp
// Initialize actuator manager
bool begin();

// Deinitialize actuator manager (stops all actuators, releases GPIO)
void end();

// Check initialization status
bool isInitialized() const;
```

#### Actuator Configuration
```cpp
// Configure/register an actuator
// If active=false: removes actuator
// If GPIO conflict detected: returns false
bool configureActuator(const ActuatorConfig& config);

// Remove actuator from registry
bool removeActuator(uint8_t gpio);

// Check if actuator exists on GPIO
bool hasActuatorOnGPIO(uint8_t gpio) const;

// Get actuator configuration
ActuatorConfig getActuatorConfig(uint8_t gpio) const;

// Get count of active actuators
uint8_t getActiveActuatorCount() const;
```

#### Actuator Control
```cpp
// Control actuator with normalized value (0.0-1.0)
// For PWM: sets PWM duty cycle
// For Binary: >=0.5 = ON, <0.5 = OFF
// Returns false if emergency-stopped
bool controlActuator(uint8_t gpio, float value);

// Control binary actuator (ON/OFF)
// Returns false if emergency-stopped
bool controlActuatorBinary(uint8_t gpio, bool state);
```

#### Safety Operations
```cpp
// Emergency stop all actuators
// Sets all actuators to OFF, marks as emergency-stopped
bool emergencyStopAll();

// Emergency stop specific actuator
bool emergencyStopActuator(uint8_t gpio);

// Clear emergency-stop flags (actuators remain OFF!)
bool clearEmergencyStop();

// Clear emergency for specific actuator
bool clearEmergencyStopActuator(uint8_t gpio);

// Get emergency-stop status
bool getEmergencyStopStatus(uint8_t gpio) const;

// Schrittweise Reaktivierung (nach clearEmergencyStop)
bool resumeOperation();

// Process actuator loops (call in main loop)
void processActuatorLoops();
```

#### MQTT Integration
```cpp
// Handle incoming actuator command from MQTT
// Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/command
// Payload: {"command":"ON","value":1.0,"duration":0}
bool handleActuatorCommand(const String& topic, const String& payload);

// Handle actuator config from MQTT
// Topic: kaiser/god/esp/{esp_id}/config
// Payload: {"actuators":[...]}
bool handleActuatorConfig(const String& payload);

// Publish actuator status
void publishActuatorStatus(uint8_t gpio);

// Publish all actuator statuses
void publishAllActuatorStatus();

// Publish command response
void publishActuatorResponse(const ActuatorCommand& command, bool success, const String& message);

// Publish alert
void publishActuatorAlert(uint8_t gpio, const String& alert_type, const String& message);
```

#### Example Usage
```cpp
// Initialize
actuatorManager.begin();

// Configure pump actuator
ActuatorConfig config;
config.gpio = 5;
config.actuator_type = "pump";
config.actuator_name = "Bewässerungspumpe";
config.active = true;
config.critical = true;
config.inverted_logic = false;
config.default_state = false;

if (actuatorManager.configureActuator(config)) {
  LOG_INFO("Pump configured on GPIO 5");
}

// Control actuator
actuatorManager.controlActuatorBinary(5, true);  // Turn ON

// Emergency stop
actuatorManager.emergencyStopAll();

// Clear emergency (actuators stay OFF)
actuatorManager.clearEmergencyStop();

// Resume operation
actuatorManager.resumeOperation();

// In main loop
void loop() {
  actuatorManager.processActuatorLoops();
}
```

---

### SafetyController

#### Header
```cpp
#include "services/actuator/safety_controller.h"
```

#### Singleton Access
```cpp
SafetyController& safetyController = SafetyController::getInstance();
```

#### Emergency-Stop vs. Safe-Mode

**Emergency-Stop (Actuator-Level):**
- Stoppt **NUR Aktoren** (Sensoren, MQTT, WiFi laufen weiter)
- Schnelle Recovery möglich (Resume-Command von Server)
- System bleibt operational
- Dauer: Temporär (Sekunden bis Minuten)
- **Use-Case:** User-Stop, Routine-Maintenance, Sensor-Triggered-Stop

**Safe-Mode (System-Level):**
- Stoppt **ALLE Subsysteme** außer WiFi/MQTT
- Nur via Reboot oder `exit_safe_mode` Command verlassbar
- System geht in "frozen state" (keine Operationen)
- Dauer: Persistent bis manueller Eingriff
- **Use-Case:** Kritischer Hardware-Fehler, GPIO-Konflikt, Memory-Corruption

**Wichtig:** Emergency-Stop ≠ Safe-Mode! Emergency-Stop ist reversibel, Safe-Mode ist kritisch.

**Code-Unterschied:**
```cpp
// Emergency-Stop (reversibel):
safetyController.emergencyStopAll("User request");
safetyController.clearEmergencyStop();       // Flags gelöscht
actuatorManager.resumeOperation();           // Aktoren wieder an

// Safe-Mode (kritisch):
systemController.enterSafeMode("GPIO conflict");
// → System frozen, nur Reboot oder exit_safe_mode hilft
```

#### Lifecycle Management
```cpp
// Initialize safety controller
bool begin();

// Deinitialize safety controller
void end();
```

#### Emergency Operations
```cpp
// Emergency stop all actuators
bool emergencyStopAll(const String& reason);

// Emergency stop specific actuator
bool emergencyStopActuator(uint8_t gpio, const String& reason);

// Clear emergency-stop (with safety verification)
bool clearEmergencyStop();

// Clear emergency for specific actuator
bool clearEmergencyStopActuator(uint8_t gpio);

// Resume operation (schrittweise Reaktivierung)
bool resumeOperation();
```

#### Status Queries
```cpp
// Check if emergency is active (system-wide)
bool isEmergencyActive() const;

// Check if emergency is active for specific actuator
bool isEmergencyActive(uint8_t gpio) const;

// Get emergency state
EmergencyState getEmergencyState() const;

// Get emergency reason
String getEmergencyReason() const;

// Get recovery progress string
String getRecoveryProgress() const;
```

#### Configuration
```cpp
// Set recovery configuration
void setRecoveryConfig(const RecoveryConfig& config);

// Get recovery configuration
RecoveryConfig getRecoveryConfig() const;
```

#### RecoveryConfig Structure
```cpp
struct RecoveryConfig {
  uint32_t inter_actuator_delay_ms = 2000;    // Delay between actuator activations
  bool critical_first = true;                  // Activate critical actuators first
  uint32_t verification_timeout_ms = 5000;     // Safety verification timeout
  uint8_t max_retry_attempts = 3;              // Max retry attempts
};
```

#### Example Usage
```cpp
// Initialize
safetyController.begin();

// Emergency stop with reason
safetyController.emergencyStopAll("User triggered emergency");

// Check status
if (safetyController.isEmergencyActive()) {
  LOG_WARNING("System in emergency mode");
  String reason = safetyController.getEmergencyReason();
  LOG_INFO("Reason: " + reason);
}

// Clear emergency
if (safetyController.clearEmergencyStop()) {
  LOG_INFO("Emergency cleared, ready to resume");
}

// Resume operation
if (safetyController.resumeOperation()) {
  LOG_INFO("Operation resumed");
}
```

---

### IActuatorDriver (Interface)

#### Header
```cpp
#include "services/actuator/actuator_drivers/iactuator_driver.h"
```

#### Driver Performance & Characteristics

**Übersicht:**

| Driver | Type | Response-Time | Max-Frequency | Lifetime | Power-Draw |
|--------|------|---------------|---------------|----------|------------|
| **PumpActuator** | Binary (Relay) | 10-20ms | 1 Hz | ~100k Cycles | 50-100mA |
| **PWMActuator** | Analog (PWM) | <1ms | Beliebig | Unlimited | Negligible |
| **ValveActuator** | Positional (Servo) | 200-600ms | 0.5 Hz | Unlimited | 100-500mA |

**PumpActuator (Relay-based):**
- **Switching-Time:** 10-20ms (Relay-Latenz)
- **Max-Frequency:** 1 Switch/Sekunde empfohlen (Relay-Schonung)
- **Lifetime:** ~100.000 Cycles (Relay-Verschleiß)
- **Runtime-Protection:** 1h Max-Runtime, 30s Cooldown, 60 Activations/Hour

**PWMActuator (PWM-based):**
- **PWM-Frequency:** 1 kHz (Standard, konfigurierbar bis 40 kHz)
- **Resolution:** 8-bit (0-255)
- **Response-Time:** <1ms (instant)
- **Max-Frequency:** Beliebig (keine mechanischen Teile)
- **Use-Case:** LED-Dimming, Motor-Speed-Control, Heizung

**ValveActuator (H-Bridge-controlled):**
- **Motor-Type:** DC-Motor mit H-Bridge (Direction + Enable Pin)
- **Response-Time:** 200-600ms (Mechanical Full-Sweep)
- **Position-Range:** 0-100 (0=closed, 100=open)
- **Movement-Control:** Timed movement (transition_time_ms)
- **Max-Frequency:** 0.5 Hz empfohlen (Motor-Schonung)
- **Use-Case:** Motorventile, Klappen, Positionierungssysteme

#### Abstract Interface
```cpp
class IActuatorDriver {
public:
  virtual ~IActuatorDriver() = default;

  // Lifecycle
  virtual bool begin(const ActuatorConfig& config) = 0;
  virtual void end() = 0;
  virtual bool isInitialized() const = 0;

  // Control operations
  virtual bool setValue(float normalized_value) = 0;  // 0.0 - 1.0
  virtual bool setBinary(bool state) = 0;             // true = ON/OPEN

  // Safety
  virtual bool emergencyStop(const String& reason) = 0;
  virtual bool clearEmergency() = 0;
  virtual void loop() = 0;  // Optional periodic processing

  // Status
  virtual ActuatorStatus getStatus() const = 0;
  virtual const ActuatorConfig& getConfig() const = 0;
  virtual String getType() const = 0;
};
```

**Note:** This is an abstract interface. Use concrete drivers: PumpActuator, PWMActuator, ValveActuator.

---

### PumpActuator (Binary Actuator)

#### Header
```cpp
#include "services/actuator/actuator_drivers/pump_actuator.h"
```

#### Construction
```cpp
PumpActuator pump;
```

#### Lifecycle
```cpp
// Initialize pump with configuration
bool begin(const ActuatorConfig& config);

// Deinitialize pump (turns OFF, releases GPIO)
void end();

// Check initialization status
bool isInitialized() const;
```

#### Control
```cpp
// Set value (normalized 0.0-1.0)
// >=0.5 = ON, <0.5 = OFF
bool setValue(float normalized_value);

// Set binary state
bool setBinary(bool state);
```

#### Safety
```cpp
// Emergency stop pump
bool emergencyStop(const String& reason);

// Clear emergency flag
bool clearEmergency();

// Loop processing (runtime protection)
void loop();
```

#### Status
```cpp
// Get actuator status
ActuatorStatus getStatus() const;

// Get configuration
const ActuatorConfig& getConfig() const;

// Get type
String getType() const;  // Returns "pump"

// Check if running
bool isRunning() const;

// Check if can activate (runtime protection)
bool canActivate() const;
```

#### Runtime Protection
```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;      // 1h continuous runtime
  uint16_t max_activations_per_hour = 60;        // Duty-cycle protection
  unsigned long cooldown_ms = 30000UL;           // 30s cooldown
  unsigned long activation_window_ms = 3600000UL; // 1h window
};

// Set runtime protection configuration
void setRuntimeProtection(const RuntimeProtection& protection);
```

#### Implementation Details

**Runtime-Protection Parameters:**
```cpp
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;      // 1h continuous (default)
  uint16_t max_activations_per_hour = 60;        // Duty-cycle protection
  unsigned long cooldown_ms = 30000UL;           // 30s cooldown
  unsigned long activation_window_ms = 3600000UL; // 1h window
};
```

**Protection-Logic:**
- Tracked in RAM (not persisted in NVS in Phase 5)
- Accumulated runtime resets after cooldown
- Activation-History: Last 60 activations tracked
- Protection triggered: Log ERROR, publish Alert, refuse activation

**GPIO-Control:**
- **Inverted-Logic Support:** `LOW = ON` wenn `config.inverted_logic = true`
- **Default-State:** Applied on `begin()` (Failsafe)
- **Emergency-Stop:** Immediate GPIO → LOW (oder HIGH wenn inverted)

#### Example Usage
```cpp
PumpActuator pump;

ActuatorConfig config;
config.gpio = 5;
config.actuator_type = "pump";
config.actuator_name = "Bewässerungspumpe";
config.default_state = false;
config.inverted_logic = false;  // HIGH = ON
config.critical = true;          // High-priority actuator

if (pump.begin(config)) {
  // Turn ON
  pump.setBinary(true);
  
  // Check status
  if (pump.isRunning()) {
    LOG_INFO("Pump is running");
  }
  
  // Emergency stop
  pump.emergencyStop("Overcurrent detected");
  
  // Process runtime protection (call in loop!)
  pump.loop();
}

// Configure runtime protection
PumpActuator::RuntimeProtection protection;
protection.max_runtime_ms = 1800000UL;  // 30min max
protection.cooldown_ms = 60000UL;       // 1min cooldown
pump.setRuntimeProtection(protection);
```

---

### PWMActuator

#### Header
```cpp
#include "services/actuator/actuator_drivers/pwm_actuator.h"
```

#### Lifecycle
```cpp
// Initialize PWM actuator
bool begin(const ActuatorConfig& config);

// Deinitialize PWM actuator
void end();

// Check initialization status
bool isInitialized() const;
```

#### Control
```cpp
// Set PWM value (normalized 0.0-1.0)
// Internally converted to 0-255
bool setValue(float normalized_value);

// Set binary state (0.0 or 1.0)
bool setBinary(bool state);
```

#### Safety
```cpp
// Emergency stop (sets PWM to 0)
bool emergencyStop(const String& reason);

// Clear emergency flag
bool clearEmergency();

// Loop processing (not used)
void loop();
```

#### Status
```cpp
// Get actuator status
ActuatorStatus getStatus() const;

// Get configuration
const ActuatorConfig& getConfig() const;

// Get type
String getType() const;  // Returns "pwm"
```

#### Implementation Details

**PWM-Channel Management:**
- Auto-assigned via `PWMController::getInstance()`
- Channel stored in `config.pwm_channel` after `begin()`
- Default PWM-Frequency: 1 kHz
- Resolution: 8-bit (0-255 internal)

**Value Conversion:**
```cpp
// API: Normalized 0.0-1.0
setValue(0.5f);

// Internal: PWM 0-255
pwm_value_ = (uint8_t)(normalized_value * 255.0f);  // = 128

// Hardware: ledc_set_duty()
ledcWrite(pwm_channel_, pwm_value_);
```

**Emergency-Stop-Behavior:**
- Sets PWM to 0
- Channel remains attached
- Clearable via `clearEmergency()`

#### Example Usage
```cpp
PWMActuator pwm;

ActuatorConfig config;
config.gpio = 12;
config.actuator_type = "pwm";
config.actuator_name = "LED Dimmer";
config.pwm_channel = 255;  // Auto-assign
config.default_pwm = 0;    // Start OFF

if (pwm.begin(config)) {
  // Channel was auto-assigned:
  LOG_INFO("PWM Channel: " + String(pwm.getConfig().pwm_channel));
  
  // Set to 50%
  pwm.setValue(0.5f);  // → PWM = 128
  
  // Set to 100%
  pwm.setValue(1.0f);  // → PWM = 255
  
  // Turn OFF
  pwm.setValue(0.0f);  // → PWM = 0
  
  // Binary control
  pwm.setBinary(true);  // → PWM = 255
  pwm.setBinary(false); // → PWM = 0
}
```

---

### ValveActuator (H-Bridge Controlled)

#### Header
```cpp
#include "services/actuator/actuator_drivers/valve_actuator.h"
```

#### Lifecycle
```cpp
// Initialize valve
bool begin(const ActuatorConfig& config);

// Deinitialize valve
void end();

// Check initialization status
bool isInitialized() const;
```

#### Control
```cpp
// Set valve position (normalized 0.0-1.0)
// 0.0 = fully closed, 1.0 = fully open
bool setValue(float normalized_value);

// Set binary state (closed/open)
bool setBinary(bool state);
```

#### Safety
```cpp
// Emergency stop valve (stops movement)
bool emergencyStop(const String& reason);

// Clear emergency flag
bool clearEmergency();

// Loop processing (movement control)
void loop();
```

#### Status
```cpp
// Get actuator status
ActuatorStatus getStatus() const;

// Get configuration
const ActuatorConfig& getConfig() const;

// Get type
String getType() const;  // Returns "valve"

// Get current position (0-100)
uint8_t getCurrentPosition() const;

// Check if moving
bool isMoving() const;
```

#### Configuration
```cpp
// Set transition time for valve movement
void setTransitionTime(uint32_t transition_time_ms);
```

#### Implementation Details

**H-Bridge Control:**
- **Enable Pin (gpio):** Motor-Enable (HIGH = Motor an)
- **Direction Pin (aux_gpio):** Motor-Richtung (HIGH = open, LOW = close)
- **Position-Tracking:** 0-100 (0 = closed, 100 = open)
- **Movement-Control:** Timed (transition_time_ms, Default: 5000ms für 0→100)

**Movement-Algorithm:**
```cpp
// setValue(0.75f) → Target Position = 75
current_position_ = 0;  // Start closed
target_position_ = 75;

// Calculate movement time
int32_t delta = target_position_ - current_position_;  // +75
uint32_t move_time = abs(delta) * transition_time_ms_ / 100;  // 3750ms

// Apply direction
digitalWrite(direction_pin_, delta > 0 ? HIGH : LOW);  // HIGH = open
digitalWrite(enable_pin_, HIGH);  // Enable motor

// Wait for movement (in loop())
// After move_time: digitalWrite(enable_pin_, LOW)
```

**Emergency-Stop-Behavior:**
- Stops movement immediately (Enable → LOW)
- Current position preserved
- Clearable via `clearEmergency()`

**Wichtig:** `loop()` MUSS aufgerufen werden für Movement-Completion!

#### Example Usage
```cpp
ValveActuator valve;

ActuatorConfig config;
config.gpio = 14;           // Enable pin (Motor ON/OFF)
config.aux_gpio = 15;       // Direction pin (Open/Close)
config.actuator_type = "valve";
config.actuator_name = "Hauptventil";
config.default_state = false;  // Start closed

if (valve.begin(config)) {
  // Set transition time (5s for full sweep)
  valve.setTransitionTime(5000);
  
  // Open valve fully
  valve.setValue(1.0f);  // Target: Position 100
  
  // Wait for movement in loop
  while (valve.isMoving()) {
    valve.loop();  // REQUIRED!
    delay(50);
  }
  LOG_INFO("Valve fully open");
  
  // Set to 50% open
  valve.setValue(0.5f);  // Target: Position 50
  
  // Close valve
  valve.setValue(0.0f);  // Target: Position 0
  
  // Check status
  LOG_INFO("Current position: " + String(valve.getCurrentPosition()));
  
  // In main loop
  valve.loop();  // MUST call for movement control!
}
```

---

### Data Structures (Phase 5)

#### ActuatorConfig
```cpp
struct ActuatorConfig {
  uint8_t gpio = 255;              // Primary GPIO pin
  uint8_t aux_gpio = 255;          // Auxiliary GPIO (valves, H-bridge)
  String actuator_type = "";       // "pump", "valve", "pwm", "relay"
  String actuator_name = "";       // Human-readable name
  String subzone_id = "";          // Optional grouping
  bool active = false;             // Enabled flag
  bool critical = false;           // Safety priority
  
  uint8_t pwm_channel = 255;       // PWM channel (auto-assigned)
  bool inverted_logic = false;     // LOW = ON
  uint8_t default_pwm = 0;         // Default PWM value (0-255)
  bool default_state = false;      // Failsafe state
  
  bool current_state = false;      // Live state (not persisted)
  uint8_t current_pwm = 0;         // Live PWM duty
  unsigned long last_command_ts = 0;
  unsigned long accumulated_runtime_ms = 0;
};
```

#### ActuatorCommand
```cpp
struct ActuatorCommand {
  uint8_t gpio = 255;
  String command = "";        // "ON","OFF","PWM","TOGGLE"
  float value = 0.0f;         // 0.0 - 1.0
  uint32_t duration_s = 0;    // Optional duration
  unsigned long timestamp = 0;
};
```

#### ActuatorStatus
```cpp
struct ActuatorStatus {
  uint8_t gpio = 255;
  String actuator_type = "";
  bool current_state = false;
  uint8_t current_pwm = 0;
  unsigned long runtime_ms = 0;
  bool error_state = false;
  String error_message = "";
  EmergencyState emergency_state = EmergencyState::EMERGENCY_NORMAL;
};
```

#### EmergencyState Enum
```cpp
enum class EmergencyState : uint8_t {
  EMERGENCY_NORMAL = 0,      // Normal operation
  EMERGENCY_ACTIVE,          // Emergency stop active
  EMERGENCY_CLEARING,        // Clearing emergency flags
  EMERGENCY_RESUMING         // Resuming operation
};
```

---

**Last Updated:** 2025-01-29  
**Phase:** 1, 2, 3, 4, 5 & 7 - Core Infrastructure + Communication + Hardware Abstraction + Sensor System + Actuator System + Error Handling & Health Monitoring  
**Status:** Production Ready (Phase 0-5, 7 Complete)

---

## ⚠️ Phase 5 Implementation Notes

**Implemented Features:**
- ✅ ActuatorManager (Registry, Control, Emergency-Stop)
- ✅ SafetyController (Emergency-Stop, Recovery)
- ✅ 3 Concrete Drivers (PumpActuator, PWMActuator, ValveActuator)
- ✅ MQTT Integration (Command, Status, Response, Alert)
- ✅ Server-Centric Architecture (MQTT-only config, no NVS persistence)

**NOT Implemented (Deferred to Phase 6+):**
- ❌ Interlock System (Hardware-Interlock zwischen Aktoren)
- ❌ Watchdog Timers (Hardware-Watchdog für Actuator-Timeouts)
- ❌ Advanced Safety-Topics (safety/status, safety/alert)
- ❌ Extended Status-Metrics (activation_count, temperature, power_consumption)
- ❌ NVS-Persistence für Runtime-Protection-Parameter
- ❌ Emergency-Response-Topic (separate Response für Emergency-Stop)

**Design Philosophy:**
Phase 5 fokussiert auf **minimale, funktionierende Actuator-Control** mit **Server-Centric Safety**. Erweiterte Safety-Features (Interlock, Watchdog) werden bewusst server-seitig implementiert, um ESP32-Komplexität minimal zu halten.

