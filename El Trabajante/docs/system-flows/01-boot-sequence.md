# Boot Sequence Flow

## Overview

Complete system initialization from power-on to operational state. This is the most critical flow in El Trabajante, establishing all subsystems in a carefully ordered sequence to ensure hardware safety and reliable operation.

## Files Analyzed

- `src/main.cpp` (lines 54-632) - Complete setup() function
- `src/drivers/gpio_manager.cpp` (lines 31-88) - Safe-mode initialization
- `src/drivers/gpio_manager.h` (lines 1-151) - GPIO manager interface
- `src/utils/logger.cpp` (lines 32-39) - Logger initialization
- `src/utils/logger.h` (lines 1-106) - Logger interface
- `src/services/config/storage_manager.cpp` (lines 64-79) - NVS initialization
- `src/services/config/storage_manager.h` (lines 1-79) - Storage interface
- `src/services/config/config_manager.h` - Configuration management
- `src/error_handling/error_tracker.h` (lines 1-102) - Error tracking
- `src/utils/topic_builder.cpp` (lines 14-22) - Topic builder configuration
- `src/services/communication/wifi_manager.h` (lines 1-66) - WiFi management
- `src/services/communication/wifi_manager.cpp` (complete file) - Circuit breaker + reconnection logic
- `src/services/communication/mqtt_client.h` (lines 1-136) - MQTT client
- `src/services/communication/mqtt_client.cpp` (complete file) - Connection handling, callback, offline buffer
- `src/drivers/i2c_bus.h` (lines 1-124) - I2C bus manager
- `src/drivers/onewire_bus.h` - OneWire bus manager
- `src/drivers/pwm_controller.h` - PWM controller
- `src/services/sensor/sensor_manager.h` (lines 1-168) - Sensor management
- `src/services/sensor/sensor_manager.cpp` (complete file) - Runtime registry + MQTT publishing
- `src/services/actuator/actuator_manager.h` (lines 1-101) - Actuator management
- `src/services/actuator/actuator_manager.cpp` (complete file) - Driver lifecycle + MQTT hooks
- `src/services/actuator/safety_controller.h` (lines 1-51) - Safety system
- `src/services/provisioning/provision_manager.h` - Provisioning system
- `src/services/provisioning/provision_manager.cpp` (complete file) - AP/HTTP state machine

## Prerequisites

- ESP32 powered on
- Serial connection at 115200 baud (for monitoring)
- Valid firmware flashed to device

## Trigger

Automatic on power-on or reset. The `setup()` function in `main.cpp` is called once by the Arduino framework.

---

## Flow Steps

### STEP 1: Hardware Initialization

**File:** `src/main.cpp` (lines 58-59)

**Code:**

```cpp
Serial.begin(115200);
delay(100);  // Allow Serial to stabilize
```

**Purpose:** Enable logging output before any other operations

**Delay:** 100 ms (explicit `delay(100)` before any other subsystem)

**Dependencies:** None - this must be first

**Details:**
- Initializes UART0 serial port at 115200 baud
- 100ms delay ensures serial interface is stable before first log messages
- Critical for debugging - all subsequent operations can log status

---

### STEP 2: Boot Banner

**File:** `src/main.cpp` (lines 64-69)

**Code:**

```cpp
Serial.println("\n╔════════════════════════════════════════╗");
Serial.println("║  ESP32 Sensor Network v4.0 (Phase 2)  ║");
Serial.println("╚════════════════════════════════════════╝");
Serial.printf("Chip Model: %s\n", ESP.getChipModel());
Serial.printf("CPU Frequency: %d MHz\n", ESP.getCpuFreqMHz());
Serial.printf("Free Heap: %d bytes\n\n", ESP.getFreeHeap());
```

**Purpose:** System identification and hardware information

**Output Example:**

```
╔════════════════════════════════════════╗
║  ESP32 Sensor Network v4.0 (Phase 2)  ║
╚════════════════════════════════════════╝
Chip Model: ESP32-D0WDQ6
CPU Frequency: 240 MHz
Free Heap: 298532 bytes
```

**Dependencies:** Serial.begin()

---

### STEP 2.5: Factory Reset Check (Boot Button)

**File:** `src/main.cpp` (lines 74-134)

**Code:**

```cpp
const uint8_t BOOT_BUTTON_PIN = 0;  // GPIO 0 on ESP32
const unsigned long HOLD_TIME_MS = 10000;  // 10 seconds

pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);

if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
  Serial.println("╔════════════════════════════════════════╗");
  Serial.println("║  ⚠️  BOOT BUTTON PRESSED              ║");
  Serial.println("║  Hold for 10 seconds for Factory Reset║");
  Serial.println("╚════════════════════════════════════════╝");
  
  unsigned long start_time = millis();
  bool held_for_10s = true;
  uint8_t last_second = 0;
  
  while (millis() - start_time < HOLD_TIME_MS) {
    if (digitalRead(BOOT_BUTTON_PIN) == HIGH) {
      held_for_10s = false;
      Serial.println("\nButton released - Factory Reset cancelled");
      break;
    }
    
    // Progress indicator (every second)
    uint8_t current_second = (millis() - start_time) / 1000;
    if (current_second > last_second) {
      Serial.print(".");
      last_second = current_second;
    }
    
    delay(100);
  }
  
  if (held_for_10s) {
    Serial.println("\n╔════════════════════════════════════════╗");
    Serial.println("║  🔥 FACTORY RESET TRIGGERED           ║");
    Serial.println("╚════════════════════════════════════════╝");
    
    // Initialize minimal systems for NVS access
    storageManager.begin();
    configManager.begin();
    
    // Clear WiFi config
    configManager.resetWiFiConfig();
    Serial.println("✅ WiFi configuration cleared");
    
    // Clear zone config
    KaiserZone kaiser;
    MasterZone master;
    configManager.saveZoneConfig(kaiser, master);
    Serial.println("✅ Zone configuration cleared");
    
    Serial.println("\n╔════════════════════════════════════════╗");
    Serial.println("║  ✅ FACTORY RESET COMPLETE            ║");
    Serial.println("╚════════════════════════════════════════╝");
    Serial.println("Rebooting in 2 seconds...");
    delay(2000);
    ESP.restart();
  }
}
```

**Purpose:** Allow user-initiated factory reset without reflashing firmware

**Trigger:** GPIO 0 (boot button) held LOW for 10 seconds during boot

**NVS Operations:**
- **Namespace:** `wifi_config` - All keys cleared
- **Namespace:** `zone_config` - All keys cleared

**Behavior:**
- **Button not pressed:** Continue to Step 3 immediately
- **Button pressed < 10s:** Continue to Step 3 after release
- **Button held 10s:** Clear configs and reboot

**Critical Note:** This happens BEFORE GPIO safe-mode initialization because we need to read GPIO 0's state

---

### STEP 3: GPIO Safe-Mode Initialization

**File:** `src/main.cpp` (line 140)

**Code:**

```cpp
gpioManager.initializeAllPinsToSafeMode();
```

**Purpose:** Prevent hardware damage from undefined GPIO states

**Implementation:** `src/drivers/gpio_manager.cpp` (lines 31-88)

```cpp
void GPIOManager::initializeAllPinsToSafeMode() {
    Serial.println("\n=== GPIO SAFE-MODE INITIALIZATION ===");
    Serial.printf("Board Type: %s\n", BOARD_TYPE);
    
    // Clear any existing pin information
    pins_.clear();
    pins_.reserve(HardwareConfig::SAFE_PIN_COUNT);
    
    uint8_t warning_count = 0;  // Track failed verifications
    
    // Initialize all safe GPIO pins to INPUT_PULLUP
    for (uint8_t i = 0; i < HardwareConfig::SAFE_PIN_COUNT; i++) {
        uint8_t pin = HardwareConfig::SAFE_GPIO_PINS[i];
        
        // Set hardware pin mode to INPUT_PULLUP (safe state)
        pinMode(pin, INPUT_PULLUP);
        
        // Verify pin state
        if (!verifyPinState(pin, INPUT_PULLUP)) {
            LOG_WARNING("GPIO " + String(pin) + " may not be in safe state!");
            warning_count++;
        }
        
        // Register pin in tracking system
        GPIOPinInfo info;
        info.pin = pin;
        info.owner[0] = '\0';
        info.component_name[0] = '\0';
        info.mode = INPUT_PULLUP;
        info.in_safe_mode = true;
        pins_.push_back(info);
        
        LOG_DEBUG("GPIO " + String(pin) + ": Safe-Mode (INPUT_PULLUP)");
    }
    
    // Auto-reserve I2C pins for system use
    bool i2c_sda = requestPin(HardwareConfig::I2C_SDA_PIN, "system", "I2C_SDA");
    bool i2c_scl = requestPin(HardwareConfig::I2C_SCL_PIN, "system", "I2C_SCL");
    
    if (i2c_sda && i2c_scl) {
        LOG_INFO("I2C pins auto-reserved (SDA: GPIO " + String(HardwareConfig::I2C_SDA_PIN) + 
                 ", SCL: GPIO " + String(HardwareConfig::I2C_SCL_PIN) + ")");
    } else {
        LOG_WARNING("GPIOManager: I2C pin auto-reservation failed");
    }
    
    // Log initialization summary
    if (warning_count > 0) {
        LOG_WARNING("GPIOManager: " + String(warning_count) + " pins failed safe-mode verification");
    } else {
        LOG_INFO("All pins successfully set to Safe-Mode");
    }
    LOG_INFO("Board: " + String(BOARD_TYPE));
    LOG_INFO("Available Pins: " + String(HardwareConfig::SAFE_PIN_COUNT));
    LOG_INFO("Reserved Pins: " + String(HardwareConfig::RESERVED_PIN_COUNT));
    
    LOG_INFO("GPIOManager: Safe-Mode initialization complete");
}
```

**Critical Importance:**
- **MUST be first hardware operation** after serial
- Prevents actuators from triggering during boot
- Sets all GPIO to high-impedance safe state (INPUT_PULLUP)
- Automatically reserves I2C pins (SDA/SCL)

**Pin Count by Board (`HardwareConfig::SAFE_PIN_COUNT`):**
- ESP32 WROOM (`config/hardware/esp32_dev.h`): 16 safe pins (GPIO 4,5,14,15,16,17,18,19,21,22,23,25,26,27,32,33)
- XIAO ESP32C3 (`config/hardware/xiao_esp32c3.h`): 9 safe pins (GPIO 2,4,5,6,7,8,9,10,21)

---

### STEP 4: Logger Initialization

**File:** `src/main.cpp` (lines 145-147)

**Code:**

```cpp
logger.begin();
logger.setLogLevel(LOG_INFO);
LOG_INFO("Logger system initialized");
```

**Implementation:** `src/utils/logger.cpp` (lines 32-39)

```cpp
void Logger::begin() {
  if (serial_enabled_) {
    Serial.println("\n=== Logger System Initialized ===");
    Serial.printf("Log Level: %s\n", getLogLevelString(current_log_level_));
    Serial.printf("Buffer Size: %d entries\n", MAX_LOG_ENTRIES);
    Serial.println("=================================\n");
  }
}
```

**Purpose:** Enable structured logging for all subsequent modules

**Features:**
- Circular buffer for 50 log entries (in-memory)
- 5 log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Thread-safe (optional, via build flags)
- Zero-copy API (const char* primary interface)

**Log Levels:**
- `LOG_DEBUG = 0` - Detailed debug information
- `LOG_INFO = 1` - General information (default)
- `LOG_WARNING = 2` - Warning conditions
- `LOG_ERROR = 3` - Error conditions
- `LOG_CRITICAL = 4` - Critical failures

**Memory Usage:** ~6.5KB static allocation (50 entries × 128 bytes + overhead)

**Dependencies:** Serial.begin()

---

### STEP 5: Storage Manager (NVS)

**File:** `src/main.cpp` (lines 152-155)

**Code:**

```cpp
if (!storageManager.begin()) {
  LOG_ERROR("StorageManager initialization failed!");
  // Continue anyway (can work without persistence)
}
```

**Implementation:** `src/services/config/storage_manager.cpp` (lines 64-79)

```cpp
bool StorageManager::begin() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (nvs_mutex_ == nullptr) {
    nvs_mutex_ = xSemaphoreCreateMutex();
    if (nvs_mutex_ == nullptr) {
      LOG_ERROR("StorageManager: Failed to create mutex");
      return false;
    }
    LOG_INFO("StorageManager: Thread-safety enabled (mutex created)");
  }
#endif
  namespace_open_ = false;
  current_namespace_[0] = '\0';
  LOG_INFO("StorageManager: Initialized");
  return true;
}
```

**Purpose:** Initialize NVS (Non-Volatile Storage) access layer

**NVS Namespaces Used:**
- `wifi_config` - WiFi and MQTT settings
- `zone_config` - Kaiser and zone assignments
- `system_config` - ESP system configuration
- `sensor_config` - Sensor definitions
- `actuator_config` - Actuator definitions

**Failure Behavior:** Non-fatal - system continues without persistence

**Memory Usage:** Primarily the optional FreeRTOS mutex handle plus the static 256-byte scratch buffer used by `getString()`

**Thread Safety:** Optional mutex protection (via CONFIG_ENABLE_THREAD_SAFETY)

---

### STEP 6: Config Manager

**File:** `src/main.cpp` (lines 160-170)

**Code:**

```cpp
configManager.begin();
if (!configManager.loadAllConfigs()) {
  LOG_WARNING("Some configurations failed to load - using defaults");
}

// Load configs into global variables
configManager.loadWiFiConfig(g_wifi_config);
configManager.loadZoneConfig(g_kaiser, g_master);
configManager.loadSystemConfig(g_system_config);

configManager.printConfigurationStatus();
```

**Purpose:** Load all configurations from NVS into memory

**Configurations Loaded:**

1. **WiFi Configuration**
   - SSID, password
   - MQTT broker address and port
   - MQTT credentials (optional)
   
2. **Zone Configuration**
   - Kaiser ID
   - Zone ID and name
   - Master zone information
   
3. **System Configuration**
   - ESP ID (auto-generated from MAC if missing)
   - Device name
   - Current state
   - Boot count

**Default Behavior:** Uses default values if NVS keys don't exist

**Example Output:**

```
=== Configuration Status ===
ESP ID: ESP_AB12CD
WiFi SSID: MyNetwork
MQTT Broker: 192.168.0.198:8883
Kaiser ID: (not assigned)
Zone: (not assigned)
===========================
```

**Timing:** Only bounded by NVS access—there are no extra delays inside `loadAllConfigs()`

---

### STEP 6.5: Provisioning Check

**File:** `src/main.cpp` (lines 176-232)

**Code:**

```cpp
// Check if ESP needs provisioning (no config or empty SSID)
if (!g_wifi_config.configured || g_wifi_config.ssid.length() == 0) {
  LOG_INFO("╔════════════════════════════════════════╗");
  LOG_INFO("║   NO CONFIG - STARTING PROVISIONING   ║");
  LOG_INFO("╚════════════════════════════════════════╝");
  LOG_INFO("ESP is not provisioned. Starting AP-Mode...");
  
  // Initialize Provision Manager
  if (!provisionManager.begin()) {
    LOG_ERROR("ProvisionManager initialization failed!");
    LOG_CRITICAL("Cannot provision ESP - check logs");
    return;  // Stop setup
  }
  
  // Start AP-Mode
  if (provisionManager.startAPMode()) {
    LOG_INFO("╔════════════════════════════════════════╗");
    LOG_INFO("║  ACCESS POINT MODE ACTIVE             ║");
    LOG_INFO("╚════════════════════════════════════════╝");
    LOG_INFO("Connect to: AutoOne-" + g_system_config.esp_id);
    LOG_INFO("Password: provision");
    LOG_INFO("Open browser: http://192.168.4.1");
    LOG_INFO("");
    LOG_INFO("Waiting for configuration (timeout: 10 minutes)...");
    
    // Block until config received (or timeout: 10 minutes)
    if (provisionManager.waitForConfig(600000)) {
      // ✅ SUCCESS: Config received
      LOG_INFO("╔════════════════════════════════════════╗");
      LOG_INFO("║  ✅ PROVISIONING SUCCESSFUL           ║");
      LOG_INFO("╚════════════════════════════════════════╝");
      LOG_INFO("Configuration saved to NVS");
      LOG_INFO("Rebooting in 2 seconds...");
      delay(2000);
      ESP.restart();  // Reboot to apply config
    } else {
      // ❌ TIMEOUT: No config received
      LOG_ERROR("╔════════════════════════════════════════╗");
      LOG_ERROR("║  ❌ PROVISIONING TIMEOUT              ║");
      LOG_ERROR("╚════════════════════════════════════════╝");
      LOG_ERROR("No configuration received within 10 minutes");
      LOG_ERROR("ESP will enter Safe-Mode");
      
      // Provisioning failed - stays in AP-Mode
      return;  // Stop setup - AP stays active
    }
  } else {
    LOG_CRITICAL("Failed to start AP-Mode!");
    return;  // Stop setup
  }
}

LOG_INFO("Configuration found - starting normal flow");
```

**Purpose:** Handle unconfigured ESPs (first boot or after factory reset)

**Provisioning Flow:**
1. Check if WiFi SSID is configured
2. If not configured → Start Access Point mode
3. ESP creates AP: `AutoOne-{ESP_ID}` with password `provision`
4. User connects to AP and opens `http://192.168.4.1`
5. Web interface requests config from God-Kaiser (or direct HTTP POST)
6. Config received → Save to NVS → Reboot
7. On timeout (10 min) → Enter Safe-Mode (`STATE_SAFE_MODE_PROVISIONING`), AP stays active

**Nach Provisioning:**
- ESP rebootet → WiFi-Connect → MQTT-Connect → Initial Heartbeat
- **Wichtig:** ESP muss zuerst über REST API registriert werden (`POST /api/v1/esp/register`)
- God-Kaiser kann dann Zone Assignment via MQTT senden (siehe [Zone Assignment Flow](08-zone-assignment-flow.md))

**AP Mode Details:**
- SSID: `AutoOne-{ESP_ID}` (e.g., `AutoOne-ESP_AB12CD`)
- Password: `provision`
- IP: `192.168.4.1`
- Timeout: 10 minutes
- `WiFi.softAP(ssid, password, 1, 0, 1)` fixes the channel to 1, keeps the network visible, and restricts AP connections to a single client

**Exit Conditions:**
- Config received → Reboot with new config
- Timeout → Enter Safe-Mode (`STATE_SAFE_MODE_PROVISIONING`), AP stays active (unbegrenzt)
- AP start failed → Stop setup (error state)

**State Machine:**
- Provisioning Timeout → `STATE_SAFE_MODE_PROVISIONING` (State 20, dokumentiert in `src/models/system_types.h`)
- AP bleibt aktiv für manuelles Provisioning (unbegrenzt)
- LED blinkt Fehler-Pattern (10× blink auf GPIO 2)
- System State wird in NVS gespeichert mit `safe_mode_reason`

**Provision Manager internals (`provision_manager.cpp`):**
- HTTP endpoints hosted by the embedded `WebServer`:
  - `GET /` serves the HTML landing page (values substituted for `%ESP_ID%`, `%MAC_ADDRESS%`, `%HEAP_FREE%`, etc.)
  - `POST /provision` accepts the JSON payload (`ssid`, `password`, `server_address`, `mqtt_port`, optional `mqtt_username` / `mqtt_password`, `kaiser_id`, `master_zone_id`)
  - `GET /status` exposes live telemetry (ESP ID, MAC, uptime, heap stats, current provisioning state)
  - `POST /reset` performs a factory reset when `{"confirm":true}` is supplied
- mDNS advertises the host as `<esp-id-lowercase>.local` with `_http._tcp` and `_autoone._tcp` records so the AP can be discovered without typing the IP.
- `waitForConfig()` enforces `AP_MODE_TIMEOUT_MS = 600000` (10 min). Each timeout increments `retry_count` and restarts AP mode up to `MAX_RETRY_COUNT = 3`. After the third timeout `enterSafeMode()` persists `STATE_SAFE_MODE` + `safe_mode_reason` to `system_config`, flashes GPIO2 ten times, and leaves the AP running for manual intervention.
- Successful provisioning writes WiFi + optional zone data via `configManager.save*`, replies with JSON, delays `REBOOT_DELAY_MS = 2000`, then calls `ESP.restart()`.

**Important:** If provisioning is needed, setup() STOPS here. Normal flow only continues if already provisioned.

---

### STEP 7: Error Tracker

**File:** `src/main.cpp` (line 242)

**Code:**

```cpp
errorTracker.begin();
```

**Purpose:** Initialize error tracking and history

**Features:**
- Circular buffer for 50 error entries
- Categorized errors (Hardware, Service, Communication, Application)
- Severity levels (Warning, Error, Critical)
- Duplicate detection with occurrence counting

**Error Categories:**

```cpp
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM (1000-1999)
  ERROR_SERVICE = 2000,        // Sensor, Actuator, Config (2000-2999)
  ERROR_COMMUNICATION = 3000,  // MQTT, HTTP, WiFi (3000-3999)
  ERROR_APPLICATION = 4000     // State, Memory, System (4000-4999)
};
```

**Usage Example:**

```cpp
errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, 
                       ERROR_SEVERITY_CRITICAL,
                       "Sensor initialization failed");
```

**Memory Usage:** ~6.5KB static allocation (50 entries × 128 bytes + overhead)

---

### STEP 8: Topic Builder Configuration

**File:** `src/main.cpp` (lines 247-250)

**Code:**

```cpp
TopicBuilder::setEspId(g_system_config.esp_id.c_str());
TopicBuilder::setKaiserId(g_kaiser.kaiser_id.c_str());

LOG_INFO("TopicBuilder configured with ESP ID: " + g_system_config.esp_id);
```

**Implementation:** `src/utils/topic_builder.cpp` (lines 14-22)

```cpp
void TopicBuilder::setEspId(const char* esp_id) {
  strncpy(esp_id_, esp_id, sizeof(esp_id_) - 1);
  esp_id_[sizeof(esp_id_) - 1] = '\0';
}

void TopicBuilder::setKaiserId(const char* kaiser_id) {
  strncpy(kaiser_id_, kaiser_id, sizeof(kaiser_id_) - 1);
  kaiser_id_[sizeof(kaiser_id_) - 1] = '\0';
}
```

**Purpose:** Configure MQTT topic generator with ESP and Kaiser IDs

**Topic Patterns Generated (`topic_builder.cpp`):**
- `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data`
- `kaiser/{kaiser_id}/esp/{esp_id}/sensor/batch`
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status`
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response`
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert`
- `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency`
- `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat`
- `kaiser/{kaiser_id}/esp/{esp_id}/system/command`
- `kaiser/{kaiser_id}/esp/{esp_id}/config`
- `kaiser/{kaiser_id}/esp/{esp_id}/config_response`
- `kaiser/broadcast/emergency`

**Default Values:**
- ESP ID: Generated from MAC address (e.g., `ESP_AB12CD`)
- Kaiser ID: `"god"` if not assigned to a zone

**Memory Usage:** Static buffers (256 bytes topic buffer, 32 bytes ESP ID, 64 bytes Kaiser ID)

---

### STEP 9: Phase 1 Complete Banner

**File:** `src/main.cpp` (lines 255-271)

**Code:**

```cpp
LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 1: Core Infrastructure READY  ║");
LOG_INFO("╚════════════════════════════════════════╝");
LOG_INFO("Modules Initialized:");
LOG_INFO("  ✅ GPIO Manager (Safe-Mode)");
LOG_INFO("  ✅ Logger System");
LOG_INFO("  ✅ Storage Manager");
LOG_INFO("  ✅ Config Manager");
LOG_INFO("  ✅ Error Tracker");
LOG_INFO("  ✅ Topic Builder");

// Print memory stats
LOG_INFO("=== Memory Status (Phase 1) ===");
LOG_INFO("Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
LOG_INFO("Min Free Heap: " + String(ESP.getMinFreeHeap()) + " bytes");
LOG_INFO("Heap Size: " + String(ESP.getHeapSize()) + " bytes");
LOG_INFO("=====================");
```

**Purpose:** Confirm Phase 1 completion and report memory status

**Milestone:** Core infrastructure ready - safe to proceed to communication layer

---

### STEP 10: Phase 2 - Communication Layer

**File:** `src/main.cpp` (lines 274-508)

**Code (WiFi):**

```cpp
LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 2: Communication Layer         ║");
LOG_INFO("║   (with Circuit Breaker Protection)    ║");
LOG_INFO("╚════════════════════════════════════════╝");

// WiFi Manager (Circuit Breaker: 10 failures → 60s timeout)
if (!wifiManager.begin()) {
  LOG_ERROR("WiFiManager initialization failed!");
  return;
}

WiFiConfig wifi_config = configManager.getWiFiConfig();
if (!wifiManager.connect(wifi_config)) {
  LOG_ERROR("WiFi connection failed");
  LOG_WARNING("System will continue but WiFi features unavailable");
} else {
  LOG_INFO("WiFi connected successfully");
}
```

**WiFi Connection:**
- Loads SSID/password from NVS (`WiFiConfig`)
- `connectToNetwork()` waits up to `WIFI_TIMEOUT_MS` (10 s) for `WL_CONNECTED`
- Circuit breaker configuration: `("WiFi", 10 failures, 60 s recovery timeout, 15 s half-open)`
- `MAX_RECONNECT_ATTEMPTS = 10`, `RECONNECT_INTERVAL_MS = 30 s`
- `wifiManager.loop()` keeps retrying while honoring the circuit breaker, so boot continues even if WiFi stays offline
- If `wifiManager.begin()` itself fails (hardware or driver issue) `setup()` returns immediately—no later phases execute
- Successful connections log the acquired IP address and RSSI (`WiFi.localIP()` / `WiFi.RSSI()`) before moving on

**Code (MQTT):**

```cpp
// MQTT Client (Circuit Breaker: 5 failures → 30s timeout)
if (!mqttClient.begin()) {
  LOG_ERROR("MQTTClient initialization failed!");
  return;
}

MQTTConfig mqtt_config;
mqtt_config.server = wifi_config.server_address;
mqtt_config.port = wifi_config.mqtt_port;
mqtt_config.client_id = configManager.getESPId();
mqtt_config.username = wifi_config.mqtt_username;  // Can be empty (Anonymous)
mqtt_config.password = wifi_config.mqtt_password;  // Can be empty (Anonymous)
mqtt_config.keepalive = 60;
mqtt_config.timeout = 10;

if (!mqttClient.connect(mqtt_config)) {
  LOG_ERROR("MQTT connection failed");
  LOG_WARNING("System will continue but MQTT features unavailable");
} else {
  LOG_INFO("MQTT connected successfully");
  
  // Phase 7: Send initial heartbeat for ESP discovery/registration
  mqttClient.publishHeartbeat();
  LOG_INFO("Initial heartbeat sent for ESP registration");
  
  // Subscribe to critical topics
  String system_command_topic = TopicBuilder::buildSystemCommandTopic();
  String config_topic = TopicBuilder::buildConfigTopic();
  String broadcast_emergency_topic = TopicBuilder::buildBroadcastEmergencyTopic();
  String actuator_command_topic = TopicBuilder::buildActuatorCommandTopic(0);
  String actuator_command_wildcard = actuator_command_topic;
  actuator_command_wildcard.replace("/0/command", "/+/command");
  String esp_emergency_topic = TopicBuilder::buildActuatorEmergencyTopic();
  
  // Phase 7: Zone assignment topic
  String zone_assign_topic = "kaiser/" + g_kaiser.kaiser_id + "/esp/" + 
                            g_system_config.esp_id + "/zone/assign";
  if (g_kaiser.kaiser_id.length() == 0) {
    zone_assign_topic = "kaiser/god/esp/" + g_system_config.esp_id + "/zone/assign";
  }
  
  mqttClient.subscribe(system_command_topic);
  mqttClient.subscribe(config_topic);
  mqttClient.subscribe(broadcast_emergency_topic);
  mqttClient.subscribe(actuator_command_wildcard);
  mqttClient.subscribe(esp_emergency_topic);
  mqttClient.subscribe(zone_assign_topic);
  
  LOG_INFO("Subscribed to system + actuator + zone assignment topics");
```

**MQTT Topics Subscribed:**

| Topic Pattern | Purpose |
|---------------|---------|
| `kaiser/{kaiser_id}/esp/{esp_id}/system/command` | System commands (factory reset, etc.) |
| `kaiser/{kaiser_id}/esp/{esp_id}/config` | Sensor/actuator configuration |
| `kaiser/broadcast/emergency` | Global emergency stop |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/+/command` | Actuator commands (wildcard for all GPIOs) |
| `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency` | ESP-specific emergency stop |
| `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` | Zone assignment |

**MQTT Callback Setup (lines 344-492):**

See [MQTT Message Routing Flow](06-mqtt-message-routing-flow.md) for complete callback documentation.

**Circuit Breaker Protection:**
- WiFi: 10 failures → 60s timeout
- MQTT: 5 failures → 30s timeout
- Prevents connection storms that could crash the ESP

**MQTT Connection Behavior (`mqtt_client.cpp`):**
- `MQTTConfig.keepalive = 60` seconds, `timeout = 10` seconds
- Circuit breaker parameters: `("MQTT", 5 failures, 30 s recovery timeout, 10 s half-open)`
- Reconnect attempts follow exponential backoff from `RECONNECT_BASE_DELAY_MS = 1 s` up to `RECONNECT_MAX_DELAY_MS = 60 s`, capped at 10 attempts
- `MAX_OFFLINE_MESSAGES = 100`; unsent publishes are buffered until the broker connection returns
- If `mqttClient.begin()` fails, `setup()` returns early (no sensor/actuator phases). Connection failures after `begin()` are non-fatal and handled by the reconnect loop.

**MQTT Callback Responsibilities (registered via `mqttClient.setCallback`):**
- Config topic (`TopicBuilder::buildConfigTopic()`): calls `handleSensorConfig()` and `handleActuatorConfig()` to apply OTA provisioning messages
- Actuator command wildcard (`kaiser/{k}/esp/{e}/actuator/+/command`): `actuatorManager.handleActuatorCommand()` routes JSON commands such as `{"command":"PWM","value":0.6}`
- Emergency topics:
  - ESP-specific: `TopicBuilder::buildActuatorEmergencyTopic()` → `safetyController.emergencyStopAll("ESP emergency command")`
  - Broadcast: `TopicBuilder::buildBroadcastEmergencyTopic()` → `safetyController.emergencyStopAll("Broadcast emergency")`
- System command topic: expects JSON `{ "command": "factory_reset", "confirm": true }`, publishes an acknowledgement on `/response`, wipes WiFi + zone config, and reboots after 3 s
- Zone assignment topic: parses `zone_id`, `master_zone_id`, `zone_name`, `kaiser_id`, updates NVS via `configManager.updateZoneAssignment()`, refreshes the globals (`g_kaiser`, `TopicBuilder::setKaiserId()`), persists `STATE_ZONE_CONFIGURED`, publishes an ACK on `/zone/ack`, and sends a fresh heartbeat

After all WiFi/MQTT work is attempted, `setup()` prints the “Phase 2 … READY” banner followed by another memory snapshot (`Free Heap`, `Min Free Heap`, `Heap Size`) before entering Phase 3.

---

### STEP 11: Phase 3 - Hardware Abstraction Layer

**File:** `src/main.cpp` (lines 513-561)

**Code:**

```cpp
LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 3: Hardware Abstraction Layer  ║");
LOG_INFO("╚════════════════════════════════════════╝");

// I2C Bus Manager
if (!i2cBusManager.begin()) {
  LOG_ERROR("I2C Bus Manager initialization failed!");
  errorTracker.trackError(ERROR_I2C_INIT_FAILED, 
                         ERROR_SEVERITY_CRITICAL,
                         "I2C begin() failed");
} else {
  LOG_INFO("I2C Bus Manager initialized");
}

// OneWire Bus Manager
if (!oneWireBusManager.begin()) {
  LOG_ERROR("OneWire Bus Manager initialization failed!");
  errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED,
                         ERROR_SEVERITY_CRITICAL,
                         "OneWire begin() failed");
} else {
  LOG_INFO("OneWire Bus Manager initialized");
}

// PWM Controller
if (!pwmController.begin()) {
  LOG_ERROR("PWM Controller initialization failed!");
  errorTracker.trackError(ERROR_PWM_INIT_FAILED,
                         ERROR_SEVERITY_CRITICAL,
                         "PWM begin() failed");
} else {
  LOG_INFO("PWM Controller initialized");
}

LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 3: Hardware Abstraction READY  ║");
LOG_INFO("╚════════════════════════════════════════╝");
LOG_INFO("Modules Initialized:");
LOG_INFO("  ✅ I2C Bus Manager");
LOG_INFO("  ✅ OneWire Bus Manager");
LOG_INFO("  ✅ PWM Controller");
```

**Purpose:** Initialize hardware interfaces for sensors and actuators

**I2C Bus Manager:**
- Initializes I2C bus with board-specific pins
- Typical pins: SDA=GPIO 21, SCL=GPIO 22 (ESP32 WROOM)
- Frequency: 100kHz (standard mode)
- Enables I2C sensor communication (SHT31, etc.)

**OneWire Bus Manager:**
- Initializes OneWire protocol support on `HardwareConfig::DEFAULT_ONEWIRE_PIN`
- Uses `gpioManager` to reserve that pin; all DS18B20 sensors share the same bus
- Warns when no devices respond to the initial bus reset

**PWM Controller:**
- Initializes ESP32 LEDC peripheral using board settings (`PWM_CHANNELS`, `PWM_FREQUENCY = 1 kHz`, `PWM_RESOLUTION = 12 bit`)
- ESP32 WROOM exposes 16 channels; XIAO ESP32C3 exposes 6 channels
- Provides per-channel frequency and resolution controls; drivers typically call `writePercent()` (0–100 %)

**Error Handling:** Errors are logged but non-fatal - system continues

---

### STEP 12: Phase 4 - Sensor System

**File:** `src/main.cpp` (lines 566-602)

**Code:**

```cpp
LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 4: Sensor System               ║");
LOG_INFO("╚════════════════════════════════════════╝");

// Sensor Manager
if (!sensorManager.begin()) {
  LOG_ERROR("Sensor Manager initialization failed!");
  errorTracker.trackError(ERROR_SENSOR_INIT_FAILED,
                         ERROR_SEVERITY_CRITICAL,
                         "SensorManager begin() failed");
} else {
  LOG_INFO("Sensor Manager initialized");
  
  // Load sensor configs from NVS
  SensorConfig sensors[10];
  uint8_t loaded_count = 0;
  if (configManager.loadSensorConfig(sensors, 10, loaded_count)) {
    LOG_INFO("Loaded " + String(loaded_count) + " sensor configs from NVS");
    for (uint8_t i = 0; i < loaded_count; i++) {
      sensorManager.configureSensor(sensors[i]);
    }
  }
}

LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 4: Sensor System READY         ║");
LOG_INFO("╚════════════════════════════════════════╝");
LOG_INFO("Modules Initialized:");
LOG_INFO("  ✅ Sensor Manager");
```

**Purpose:** Initialize sensor management and load persisted sensor configs

**Sensor Configuration Loading:**

1. Read `sensor_count` from NVS namespace `sensor_config`
2. For each sensor index `i` (0 to count-1):
   - Load `sensor_{i}_gpio`
   - Load `sensor_{i}_type`
   - Load `sensor_{i}_name`
   - Load `sensor_{i}_subzone`
   - Load `sensor_{i}_active`
   - Load `sensor_{i}_raw_mode`
3. Configure each sensor via `sensorManager.configureSensor()`

**NVS Keys Used:**
- Namespace: `sensor_config`
- Keys:
  - `sensor_count` (uint8_t) - Number of sensors
  - `sensor_{i}_gpio` (uint8_t) - GPIO pin
  - `sensor_{i}_type` (String) - Sensor type (e.g., "temp_ds18b20")
  - `sensor_{i}_name` (String) - Human-readable name
  - `sensor_{i}_subzone` (String) - Subzone identifier
  - `sensor_{i}_active` (bool) - Active flag
  - `sensor_{i}_raw_mode` (bool) - Raw mode flag

**Example Sensors:**
- DS18B20 temperature sensor (OneWire)
- SHT31 temperature/humidity (I2C)
- pH sensor (analog)

---

### STEP 13: Phase 5 - Actuator System

**File:** `src/main.cpp` (lines 607-632)

**Code:**

```cpp
LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 5: Actuator System            ║");
LOG_INFO("╚════════════════════════════════════════╝");

if (!safetyController.begin()) {
  LOG_ERROR("Safety Controller initialization failed!");
  errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                          ERROR_SEVERITY_CRITICAL,
                          "SafetyController begin() failed");
} else {
  LOG_INFO("Safety Controller initialized");
}

if (!actuatorManager.begin()) {
  LOG_ERROR("Actuator Manager initialization failed!");
  errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                          ERROR_SEVERITY_CRITICAL,
                          "ActuatorManager begin() failed");
} else {
  LOG_INFO("Actuator Manager initialized");

  // Load actuator configs from NVS (analog to sensor loading in Phase 4)
  ActuatorConfig actuators[MAX_ACTUATORS];
  uint8_t loaded_actuator_count = 0;
  if (configManager.loadActuatorConfig(actuators, MAX_ACTUATORS, loaded_actuator_count)) {
    LOG_INFO("Loaded %d actuator configs from NVS", loaded_actuator_count);
    for (uint8_t i = 0; i < loaded_actuator_count; i++) {
      actuatorManager.configureActuator(actuators[i]);
    }
  }
}

LOG_INFO("╔════════════════════════════════════════╗");
LOG_INFO("║   Phase 5: Actuator System READY      ║");
LOG_INFO("╚════════════════════════════════════════╝");
```

**Purpose:** Initialize actuator control and safety systems

**Safety Controller:**
- Manages emergency stops
- Tracks emergency state per actuator
- Provides recovery mechanisms
- Prevents unsafe actuator operations

**Actuator Manager:**
- Manages actuator registry (max 12 actuators on ESP32 WROOM, 8 on XIAO)
- Starts with an empty registry at boot; actuator definitions arrive via MQTT `/config`
- Persists changes to NVS (`config_manager.saveActuatorConfig`) when configs are added or removed, but `setup()` does **not** load them back yet
- Handles MQTT command routing to actuator drivers
- Publishes actuator status (`buildActuatorStatusTopic`), acknowledgements (`buildActuatorResponseTopic`), and alerts (`buildActuatorAlertTopic`); the Communication-Task (SAFETY-RTOS M3) also calls `actuatorManager.publishAllActuatorStatus()` once post-reconnect with 50ms stagger between actuators (AUT-590 F2/7.1)

**Boot-Safe GPIO State (AUT-737):**
- `PumpActuator::begin()` always writes `LOW` regardless of `default_state` — prevents ~27s uncontrolled pump run and suppresses ESP32 GPIO transient HIGH (documented for GPIO25 and other non-strapping pins)
- `default_state` is applied via `PumpActuator::loop()` after `ACTUATOR_BOOT_SETTLE_MS = 5000ms` — driven by the Safety Task's `processActuatorLoops()` call
- Server commands (`setBinary`/`setValue`) bypass the boot gate and fire immediately
- `ValveActuator` and `PWMActuator` already boot to LOW/0 — not affected

**Actuator Types Supported:**
- Pump (ON/OFF)
- Valve (ON/OFF)
- PWM (normalized floating-point value 0.0–1.0 mapped to LEDC percent output)
- Relay (ON/OFF — mapped to PumpActuator internally)

**NVS Persistence Notes:**
- `ActuatorManager` saves the active registry to the `actuator_config` namespace whenever MQTT provisioning updates arrive
- Future phases may reload this data, but current boot flow expects the God-Kaiser backend to resend actuator definitions after startup

---

### STEP 14: SAFETY-RTOS M1+M3 — Queues, Safety Task, Communication Task

**File:** `src/main.cpp` (STEP „SAFETY-RTOS M1+M3“, nach Actuator-Init)

**Code:**

```cpp
// ============================================
// SAFETY-RTOS M1+M3: Queues + Safety Task + Communication Task
// ============================================
initActuatorCommandQueue();   // Must be before createSafetyTask()
initSensorCommandQueue();
initPublishQueue();           // M3: Core 1 → Core 0 publish queue (ESP-IDF publish path)
createSafetyTask();

// Deregister Arduino loopTask from WDT — Safety-Task takes over WDT
#ifndef WOKWI_SIMULATION
esp_task_wdt_delete(xTaskGetCurrentTaskHandle());
#endif
LOG_I(TAG, "[SAFETY-RTOS M1] Safety task created, loopTask deregistered from WDT");

createCommunicationTask();    // M3: Core 0 — WiFi/MQTT/Debounce/Heartbeat-Trigger/Publish-Drain
g_safety_rtos_tasks_created = true;
LOG_I(TAG, "[SAFETY-RTOS M3] Communication task created on Core 0");
```

**Purpose:** Create a dedicated FreeRTOS task (Core 1, Priority 5) that runs sensor measurements, actuator loops, safety checks and WDT feeding independently of `loop()`

**Safety Task (`src/tasks/safety_task.cpp`):**
- Pinned to Core 1 (APP_CPU), Priority 5 (higher than loop() at 1)
- 8 KB stack
- Calls `esp_task_wdt_add(NULL)` on startup — registers itself with the WDT
- Loop: `esp_task_wdt_reset()` → `sensorManager.performAllMeasurements()` → `actuatorManager.processActuatorLoops()` → `checkServerAckTimeout()` → queue drains → `healthMonitor.loop()` → SAFETY-P4 offline (`checkDelayTimer`, `evaluateOfflineRules()` when active) → `vTaskDelay(10ms)`
- Logs stack highwater mark every ~60 s

**Command Queues (`src/tasks/actuator_command_queue.h`, `sensor_command_queue.h`):**
- `g_actuator_cmd_queue` / `g_sensor_cmd_queue` — size 10 each
- MQTT command routing uses these queues (Core 0 → Core 1)

**Publish Queue (`publish_queue_constants.h` / `publish_queue.h`, M3, ESP-IDF path):**
- `g_publish_queue` — **10** slots (Shed watermark **5**); Core 1 (Safety-Task) → Core 0; `MQTTClient::publish()` on Core 1 enqueues; Communication-Task calls `processPublishQueue()` (adaptive drain 1–2/Tick, AUT-481 P3)

**Communication Task (`src/tasks/communication_task.cpp`, M3):**
- Pinned to Core 0 (PRO_CPU), Priority 3, 6144 B stack
- Loop: `wifiManager.loop()` → `mqttClient.loop()` (NTP + heartbeat scheduling) → `processPublishQueue()` (ESP-IDF only) → debounce timers → `vTaskDelay(50ms)` (operational); provisioning/pending branches as in code

**WDT Deregistration (CRITICAL):**
- `esp_task_wdt_delete(xTaskGetCurrentTaskHandle())` removes the Arduino `loopTask` from WDT supervision
- Without this: `loop()` no longer feeds WDT → 60 s reset
- Skipped under `WOKWI_SIMULATION` (no hardware WDT)

**Atomic Shared State (M1.5 / M2):**
- `g_last_server_ack_ms` → `std::atomic<uint32_t>` (thread-safe between tasks)
- `g_server_timeout_triggered` → `std::atomic<bool>`
- `g_mqtt_connected` → `std::atomic<bool>` (ESP-IDF path; M2)

**Dependencies:** All subsystems (Sensor, Actuator, HealthMonitor) must be initialized before `createSafetyTask()`

---

## Boot Sequence Complete

After Step 14, the ESP32 is fully initialized with three concurrent execution contexts (plus ESP-IDF MQTT internal task when `MQTT_USE_ESP_IDF`):

**`CommunicationTask` (`src/tasks/communication_task.cpp`, Core 0, Priority 3):**
- `wifiManager.loop()` + `mqttClient.loop()` — WiFi/MQTT + NTP + heartbeat scheduling
- `mqttClient.processPublishQueue()` — drains Core 1 → Core 0 publish queue (ESP-IDF only)
- Disconnect-Debounce + MQTT Persistent Failure timers
- `handleWatchdogTimeout()` / boot-counter reset as in code

**`loop()` (Core 1, loopTask, Priority 1):**
- After full init: **minimal** — `vTaskDelay(1000)` only (Arduino `loop()` must not be empty)
- If `setup()` returned before tasks were created (early provisioning / failure paths): **legacy** branch in `main.cpp` runs the former single-threaded WiFi/MQTT/provisioning logic (no Communication/Safety tasks)

**`safetyTaskFunction()` (Core 1, SafetyTask, Priority 5):**
- Sensor measurements, actuator loop timers, P1 ACK-timeout, health monitoring, SAFETY-P4 offline evaluation
- WDT feeding — runs independently of MQTT blocking

**File:** `src/main.cpp` + `src/tasks/safety_task.cpp` + `src/tasks/communication_task.cpp`

```cpp
// loop() — after full SAFETY-RTOS init (typical)
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}

// communicationTaskFunction() — Core 0 (conceptual)
void communicationTaskFunction(void* param) {
  wifiManager.loop();
  mqttClient.loop();
  // processPublishQueue() wenn MQTT_USE_ESP_IDF
  // debounce timers, ...
  vTaskDelay(pdMS_TO_TICKS(50));
}

// safetyTaskFunction() — Core 1
void safetyTaskFunction(void* param) {
  esp_task_wdt_add(NULL);
  for (;;) {
    esp_task_wdt_reset();
    sensorManager.performAllMeasurements();
    actuatorManager.processActuatorLoops();
    checkServerAckTimeout();
    processActuatorCommandQueue();
    processSensorCommandQueue();
    healthMonitor.loop();
    offlineModeManager.checkDelayTimer();
    // evaluateOfflineRules when offline active ...
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
```

**Note (historical):** Before SAFETY-RTOS M1, `loop()` contained sensor/actuator/MQTT together. M1 splits Safety; M3 moves communication to Core 0. MQTT blocking during reconnect no longer stalls sensor reads or safety checks.

```cpp
// ORIGINAL loop() (pre-M1) — kept here for reference only:
// wifiManager.loop();
// mqttClient.loop();
// sensorManager.performAllMeasurements();
// actuatorManager.processActuatorLoops();
// ... SAFETY-P1 Mechanism D inline ...
// healthMonitor.loop();
// delay(10);
```

```cpp
// CURRENT loop() (post-M1):
// wifiManager.loop();
// mqttClient.loop();
// ... timers only ...
// offlineModeManager.checkDelayTimer();
// delay(10);
```

```cpp
// Pre-M1 start of loop():
  static unsigned long last_health_check = 0;
  if (millis() - last_health_check >= 300000) {
    last_health_check = millis();
    
    LOG_INFO("=== System Health Check ===");
    LOG_INFO("WiFi Status: " + wifiManager.getConnectionStatus());
    LOG_INFO("MQTT Status: " + mqttClient.getConnectionStatus());
    LOG_INFO("Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
    LOG_INFO("Uptime: " + String(millis() / 1000) + " seconds");
    LOG_INFO("==========================");
  }
  
  delay(10);  // Small delay to prevent watchdog issues
}
```

---

## Phase Summary

### Phase 1: Core Infrastructure (Steps 1-9)

**Notes:** Includes the mandatory `delay(100)` after `Serial.begin()` and an optional 10 s wait if the factory-reset button remains pressed.

**Modules:**
- GPIO Manager (Safe-Mode)
- Logger System
- Storage Manager (NVS)
- Config Manager
- Error Tracker
- Topic Builder

**Critical Success Criteria:**
- All GPIO pins in safe mode
- Logger operational
- NVS accessible

---

### Phase 2: Communication Layer (Step 10)

**Notes:** WiFi attempts each connection for up to 10 s and retries every 30 s (with circuit-breaker limits). MQTT uses exponential backoff between 1 s and 60 s with its own circuit breaker.

**Modules:**
- WiFi Manager
- MQTT Client

**Critical Success Criteria:**
- WiFi connected
- MQTT connected
- Topics subscribed
- Initial heartbeat sent

**Network Requirements:**
- Valid WiFi credentials in NVS
- MQTT broker accessible
- Network latency < 5s

---

### Phase 3: Hardware Abstraction (Step 11)

**Notes:** Hardware dependencies (I2C pins, OneWire default pin, PWM channel counts) come from `config/hardware/*.h` and differ per board definition.

**Modules:**
- I2C Bus Manager
- OneWire Bus Manager
- PWM Controller

**Critical Success Criteria:**
- I2C bus operational
- OneWire bus ready
- PWM channels available

---

### Phase 4: Sensor System (Step 12)

**Notes:** Up to `MAX_SENSORS = 10` entries are fetched from `sensor_config` and re-applied through `sensorManager.configureSensor()`.

**Modules:**
- Sensor Manager
- Sensor configs loaded from NVS

**Critical Success Criteria:**
- Sensor Manager initialized
- Persisted sensors configured

---

### Phase 5: Actuator System (Step 13)

**Notes:** Actuator configs are loaded from NVS on boot (analog to sensor loading in Phase 4). If NVS is empty (first boot), actuator definitions arrive via MQTT `/config` payloads and are persisted to NVS at that point.

**Modules:**
- Safety Controller
- Actuator Manager
- Offline Mode Manager (SAFETY-P4, NVS rule load)

**Critical Success Criteria:**
- Safety system operational
- Actuator Manager ready for commands

---

### Phase 6: SAFETY-RTOS M1 (Step 14)

**Notes:** FreeRTOS Safety Task decouples sensor/actuator/safety execution from `loop()`. MQTT blocking (TCP-Timeout up to 30 s) no longer freezes safety checks. Queues are infrastructure for future MQTT migration (M2/M3).

**Modules:**
- Actuator Command Queue (`src/tasks/actuator_command_queue`)
- Sensor Command Queue (`src/tasks/sensor_command_queue`)
- Safety Task (`src/tasks/safety_task`, Core 1, Priority 5, 8 KB Stack)

**Critical Success Criteria:**
- `[SAFETY] Safety task running on core 1` appears in Serial log
- loopTask deregistered from WDT (`esp_task_wdt_delete`)
- No double-call of sensor/actuator functions (removed from loop)

---

## Boot Duration Considerations

- Serial initialization explicitly waits 100 ms; factory reset requires holding GPIO 0 for `HOLD_TIME_MS = 10000` before a 2 s reboot delay.
- WiFi connection attempts use `WIFI_TIMEOUT_MS = 10000` and retry every `RECONNECT_INTERVAL_MS = 30000` unless the WiFi circuit breaker (10 consecutive failures) opens for 60 s.
- MQTT reconnection uses exponential backoff from 1 s up to 60 s with a 5-failure circuit breaker that pauses attempts for 30 s.
- Provisioning mode blocks inside `waitForConfig(600000)` (10 minutes). If no configuration arrives, setup() returns early and the AP stays active for manual intervention.

---

## Success Criteria

Boot sequence is successful when:

- ✅ All five phase banners (`Phase N: ... READY`) appear without preceding `LOG_CRITICAL` errors or early `return`
- ✅ If provisioning was required, the log `Configuration found - starting normal flow` appears after the AP flow exits
- ✅ Network subsystems print `WiFi connected successfully` and `MQTT connected successfully` (otherwise the device keeps running offline)
- ✅ `sensorManager` and `actuatorManager` report successful initialization (sensors may additionally log how many configs were re-applied)
- ✅ GPIO Manager reports “Safe-Mode initialization complete” before any other hardware driver starts
- ✅ `[SAFETY] Safety task running on core 1` appears after Phase 5 (SAFETY-RTOS M1)

---

## Error Handling

### Non-Fatal Errors

Continue boot sequence but log error:

- Storage Manager initialization failure → Continue without persistence
- WiFi connection failure → Continue without network
- MQTT connection failure → Continue without server communication
- I2C/OneWire/PWM initialization failure → Continue without that subsystem

### Fatal Errors

Stop boot sequence:

- GPIO Manager initialization failure → Cannot ensure hardware safety
- `provisionManager.begin()` failure → No way to enter provisioning flow
- Provisioning mode AP start failure → Cannot configure ESP
- `wifiManager.begin()` failure → Communication stack can’t start (later phases never run)
- `mqttClient.begin()` failure → MQTT stack unavailable (setup returns immediately)
- Logger initialization failure (rare) → Cannot debug

### Recovery Mechanisms

- **Circuit Breakers:** Prevent connection storms (WiFi/MQTT)
- **Automatic Reconnection:** WiFi and MQTT attempt reconnection in loop()
- **Safe-Mode:** All GPIO pins return to safe state on error
- **Provisioning Fallback:** Unconfigured ESP enters AP mode

---

## Memory Instrumentation

- After Phases 1–4, `setup()` logs `ESP.getFreeHeap()`, `ESP.getMinFreeHeap()` and `ESP.getHeapSize()`. Use those logs to track actual usage for the current firmware build and board; there are no baked-in thresholds.
- `SensorManager` stores up to `MAX_SENSORS = 10` `SensorConfig` objects that come from NVS at boot. `ActuatorManager` keeps up to 12 (ESP32 WROOM) or 8 (XIAO ESP32C3) `ActuatorConfig` objects once MQTT provisioning defines them.
- Fixed buffers in the codebase:
  - Logger: `MAX_LOG_ENTRIES = 50`, each `LogEntry` reserves 128 bytes for the message (≈6.5 KB total)
  - ErrorTracker: 50-entry circular buffer with 128-byte messages (≈6.5 KB)
  - TopicBuilder: 256-byte topic buffer plus `esp_id_[32]` and `kaiser_id_[64]`
  - MQTT offline buffer: `MAX_OFFLINE_MESSAGES = 100`, each slot stores two `String`s plus metadata, so memory consumption depends on topic/payload size
  - Circuit breaker and configuration structs live on the stack and contribute minimally compared to the buffers above

---

## Next Flows

After boot sequence completes successfully:

→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - For incoming commands  
→ [Sensor Reading Flow](02-sensor-reading-flow.md) - For periodic measurements  
→ [Actuator Command Flow](03-actuator-command-flow.md) - For actuator control  
→ [Zone Assignment Flow](08-zone-assignment-flow.md) - For runtime zone configuration  
→ [Provisioning Documentation](../Dynamic%20Zones%20and%20Provisioning/PROVISIONING.md) - Initial WiFi/Server setup

---

## Troubleshooting

### Boot Fails at Phase 1

**Symptoms:** No log output after boot banner

**Causes:**
- GPIO Manager critical failure
- Hardware defect

**Solutions:**
- Check serial connection
- Verify hardware configuration
- Reflash firmware

### Boot Hangs at Phase 2 (WiFi)

**Symptoms:** "Attempting WiFi connection..." but never completes

**Causes:**
- Invalid WiFi credentials
- WiFi network unavailable
- Weak signal

**Solutions:**
- Perform factory reset (hold boot button 10s)
- Provision with correct credentials
- Move closer to access point

### Boot Hangs at Phase 2 (MQTT)

**Symptoms:** WiFi connected but MQTT connection fails

**Causes:**
- MQTT broker offline
- Incorrect broker address/port
- Network firewall blocking MQTT

**Solutions:**
- Verify God-Kaiser server is running
- Check MQTT broker logs
- Test network connectivity

### Memory Issues

**Symptoms:** Frequent reboots, watchdog resets

**Causes:**
- Too many sensors/actuators configured
- Memory leak
- Stack overflow

**Solutions:**
- Reduce sensor/actuator count
- Monitor heap usage in loop()
- Check for recursive function calls

---

## Development Notes

### Adding New Initialization Steps

When adding new subsystems:

1. Choose appropriate phase based on dependencies
2. Initialize AFTER dependencies are ready
3. Use non-fatal error handling when possible
4. Log initialization status
5. Track memory impact
6. Update this documentation

### Modifying Boot Order

**Warning:** Changing boot order can break the system!

**Dependencies:**
- Logger requires Serial
- Config Manager requires Storage Manager
- WiFi Manager requires Config Manager
- MQTT requires WiFi
- Sensors require I2C/OneWire/PWM
- Actuators require GPIO Manager + PWM

### Performance Optimization

To reduce boot time:

1. Cache WiFi credentials (done)
2. Optimize NVS reads (already minimal)
3. Parallelize independent initializations (risky on ESP32)
4. Reduce MQTT connection timeout (not recommended)

**Current boot time (3-6s) is acceptable for this application.**

---

**End of Boot Sequence Documentation**

