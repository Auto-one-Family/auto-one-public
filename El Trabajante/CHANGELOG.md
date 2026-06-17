# Changelog

All notable changes to ESP32 Sensor Network v4.0 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - TCP-Stack-Härtung + Publish-Pacing - 2026-05-30

### Fixed

- **AUT-539 Fix 1 (vendor):** SO_KEEPALIVE auf ESP-IDF-Transport-Layer gesetzt via
  `esp_transport_tcp_set_keep_alive()` (idle=10s, interval=5s, count=3). Verhindert
  TCP-Half-Open/Socket-Leak im Reconnect-Loop nach NAT-Timeout.
- **AUT-539 Fix 2 (`mqtt_client.cpp`):** `processManagedReconnect_()` führt Hard-Reset
  (`esp_mqtt_client_stop()` + 200ms + `esp_mqtt_client_start()`) nach >5 Soft-Reconnect-
  Versuchen durch. Behebt finales Stuck-State bei CLOSE_WAIT-Zombie-Socket.
- **AUT-539 Fix 3 (`main.cpp`):** `mqtt_config.keepalive` von 90s auf 60s reduziert.
  5 PINGREQ/5min statt 3, gibt mehr Marge gegen FritzBox-NAT-Timeout (~300s).
- **AUT-484 (`mqtt_client.cpp`):** Runtime-Critical-Publish-Pacing via
  `deferRuntimeCriticalPublishPace_()` — Mindestabstand `RUNTIME_CRITICAL_PUBLISH_INTER_PACE_MS=120ms`
  zwischen intent_outcome/realtime-response Publishes. Schützt keepalive/TCP bei Burst.
- **AUT-484 (`mqtt_client.cpp`):** Bootstrap-Subscription-Pacing — nach jeder
  config-subscription wird `SUBSCRIPTION_INTER_PACE_MS` Verzögerung auf nächste Subscription
  gesetzt. Verhindert Subscribe-Burst beim Verbindungsaufbau.
- **Compile-Fix (`publish_queue.h/.cpp`):** `tryQueuePublish()` akzeptiert jetzt optionales
  7. Argument `unsigned long defer_ms = 0` (Placeholder für zukünftige deferred-publish-
  Unterstützung, aktuell ignoriert). Behebt Build-Fehler durch AUT-484-Call-Site.
- **Partition-Fix (`partitions_custom.csv`):** `app0`/`app1` von `0x180000` (1,572,864 B) auf
  `0x190000` (1,638,400 B) erweitert (+64 KB je Slot); `spiffs` von `0xD0000` auf `0xB0000`
  (-128 KB). Behebt Boot-Loop nach AUT-539/AUT-484-Merge: merged Binary überschritt alte
  Partition um 4,768 B (Bootloader SHA256-Fehler, keine App-Output). Flash jetzt 95.9%.
  **Flash-Pflicht:** Vor diesem Binary einmalig `erase_flash` ausführen — NVS wird gelöscht,
  ESP startet in Provisioning-Mode (AP `AutoOne-<ESP_ID>`).

---

## [1.0.0] - Phase 1 Core Infrastructure - 2025-11-14

### Added

#### Core Modules

- **Logger System** (`src/utils/logger.*`)
  - 5 log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Circular buffer for log history (50 entries)
  - Serial output with timestamps
  - Log level filtering
  - const char* Primary API + String wrappers

- **StorageManager** (`src/services/config/storage_manager.*`)
  - NVS abstraction layer
  - Namespace management (begin/end)
  - Type-safe read/write (String, int, uint8/16, bool, ulong)
  - const char* Primary API + String wrappers
  - Static buffer for zero-copy getString()

- **ConfigManager** (`src/services/config/config_manager.*`)
  - Configuration orchestration (WiFi/Zone/System)
  - loadAllConfigs() orchestration
  - Validation logic for all configs
  - isConfigurationComplete() status check
  - Server-Centric scope (no Sensor/Actuator arrays in Phase 1)

- **TopicBuilder** (`src/utils/topic_builder.*`)
  - 8 critical MQTT topic patterns
  - Static buffers (no heap allocation)
  - ESP ID / Kaiser ID substitution
  - setEspId() / setKaiserId() configuration

- **ErrorTracker** (`src/error_handling/error_tracker.*`)
  - Error history with circular buffer (50 entries)
  - 4 error categories (HARDWARE, SERVICE, COMMUNICATION, APPLICATION)
  - 3 severity levels (WARNING, ERROR, CRITICAL)
  - Occurrence counting for duplicate errors
  - Automatic Logger integration

#### Models

- **Error Codes** (`src/models/error_codes.h`)
  - 76 error codes defined (1000-4999)
  - 4 categories with 1000-value ranges

- **System Types** (`src/models/system_types.h`)
  - SystemConfig structure
  - WiFiConfig, KaiserZone, MasterZone structures

#### Integration

- **GPIO Manager Logger Integration** (`src/drivers/gpio_manager.cpp`)
  - 26 Serial.print* calls migrated to LOG_* macros
  - Boot banner retained as Serial (lines 32-33)
  - Complete structured logging integration

- **main.cpp Initialization Order** (`src/main.cpp`)
  - Correct initialization sequence implemented
  - GPIO Safe-Mode FIRST (hardware safety)
  - Logger AFTER GPIO (dependency correct)
  - Config BEFORE TopicBuilder (esp_id/kaiser_id needed)

#### Testing

- **Unit Tests** (`test/`)
  - test_logger.cpp (6 tests)
  - test_storage_manager.cpp (6 tests)
  - test_config_manager.cpp (6 tests)
  - test_topic_builder.cpp (9 tests)
  - test_error_tracker.cpp (8 tests)
  - test_integration.cpp (6 integration tests)
  - **Total: 41 tests**

### Changed

- GPIO Manager: Migrated from Serial output to structured logging
- main.cpp: Implemented complete Phase 1 initialization order
- Memory Strategy: Stack > Heap (fixed arrays, static buffers)

### Removed

- None (Phase 1 initial implementation)

### Known Issues

- TopicBuilder: Buffer-overflow checks missing (non-blocking, see #XX)
- Doxygen documentation incomplete (work in progress)

### Performance

- Logger::log() disabled: ~0.5 µs
- Logger::log() enabled: ~5 µs
- TopicBuilder::buildTopic(): ~2 µs
- Memory usage: ~19 KB / 320 KB (5.9%)

### Dependencies

- PlatformIO
- Arduino Framework for ESP32
- No external libraries (Phase 1)

---

## [2.0.0] - Phase 2 Communication Layer - 2025-11-14

### Added

#### Communication Modules

- **WiFiManager** (`src/services/communication/wifi_manager.*`)
  - WiFi connection management with auto-reconnect
  - Exponential backoff reconnection (30s base interval, max 10 attempts)
  - Connection monitoring via `loop()` method
  - Status reporting (RSSI, IP, SSID, connection status)
  - Error logging via ErrorTracker (ERROR_WIFI_* codes)
  - Integration with WiFiConfig from ConfigManager
  - Singleton pattern (consistent with Phase 1)

- **MQTTClient** (`src/services/communication/mqtt_client.*`)
  - MQTT client management with PubSubClient wrapper
  - Anonymous and authenticated modes (transition support)
  - Offline message buffer (100 messages max, circular buffer)
  - Exponential backoff reconnection (1s base, 60s max)
  - Heartbeat system (60s interval, QoS 0, JSON payload)
  - Message callback routing
  - Safe publish with retries
  - Connection status reporting
  - Singleton pattern (consistent with Phase 1)

#### Integration

- **main.cpp Phase 2 Integration** (`src/main.cpp`)
  - WiFiManager initialization after ConfigManager
  - WiFi connection using ConfigManager.getWiFiConfig()
  - MQTTClient initialization after WiFi connection
  - MQTTConfig built from WiFiConfig and SystemConfig
  - Topic subscriptions:
    - System command topic
    - Config topic
    - Broadcast emergency topic
  - MQTT callback for message routing (placeholder for Phase 4)
  - Loop integration: `wifiManager.loop()` and `mqttClient.loop()`

#### Testing

- **Unit Tests** (`test/`)
  - test_wifi_manager.cpp (4 tests)
  - test_mqtt_client.cpp (7 tests)
  - test_phase2_integration.cpp (3 integration tests)
  - **Total: 14 new tests**

### Changed

- main.cpp: Added Phase 2 communication layer initialization
- main.cpp: Updated loop() to include WiFi and MQTT monitoring
- Banner updated to reflect Phase 2 completion

### Removed

- None

### Known Issues

- HTTPClient, WebServer, NetworkDiscovery deferred (optional modules)
- TopicBuilder buffer-overflow checks still pending (non-blocking)

### Performance

- WiFi connection timeout: 10 seconds
- WiFi reconnection interval: 30 seconds
- MQTT heartbeat interval: 60 seconds
- MQTT reconnection backoff: 1s → 60s (exponential)
- Offline buffer processing: <100ms on reconnect
- Memory usage: ~25 KB / 320 KB (7.8%)

### Dependencies

- PubSubClient library (MQTT client)
- WiFi.h (ESP32 Core)
- WiFiClient.h (ESP32 Core)

---

## [3.0.0] - Phase 3 Hardware Abstraction Layer - 2025-01-28

### Added

#### Hardware Abstraction Modules

- **I2CBusManager** (`src/drivers/i2c_bus.*`)
  - I2C bus initialization and management
  - Bus scanning for device detection
  - Raw read/write operations
  - Error handling with ErrorTracker integration
  - Hardware-specific configuration (XIAO ESP32-C3, ESP32-WROOM-32)
  - Singleton pattern (consistent with Phase 1-2)

- **OneWireBusManager** (`src/drivers/onewire_bus.*`)
  - OneWire bus initialization and management
  - Device scanning (ROM address discovery)
  - Raw temperature reading (DS18B20 support)
  - Error handling with ErrorTracker integration
  - Hardware-specific pin configuration
  - Singleton pattern (consistent with Phase 1-2)

- **PWMController** (`src/drivers/pwm_controller.*`)
  - PWM channel management (6 channels for XIAO, 16 for WROOM)
  - Channel attachment/detachment
  - 12-bit resolution support (0-4095)
  - Frequency configuration (default: 1 kHz)
  - Percentage-based and absolute value writing
  - Error handling with ErrorTracker integration
  - Singleton pattern (consistent with Phase 1-2)

#### Integration

- **main.cpp Phase 3 Integration** (`src/main.cpp`)
  - I2CBusManager initialization after WiFi connection
  - OneWireBusManager initialization
  - PWMController initialization
  - Hardware-specific pin auto-reservation via GPIOManager

### Changed

- GPIO Manager: Auto-reservation of I2C pins during initialization
- Memory Strategy: Hardware abstraction uses minimal heap allocation

### Removed

- None

### Known Issues

- None

### Performance

- I2C bus scan: ~100ms for 8-bit address space
- OneWire device scan: ~500ms (depends on device count)
- PWM update: <1ms per channel
- Memory usage: ~30 KB / 320 KB (9.4%)

### Dependencies

- Wire.h (ESP32 Core - I2C)
- OneWire library (ESP32 Core)
- ledc.h (ESP32 Core - PWM)

---

## [4.0.0] - Phase 4 Sensor System - 2025-01-28

### Added

#### Communication Modules

- **HTTPClient** (`src/services/communication/http_client.*`)
  - HTTP POST/GET request support
  - URL parsing (IP:Port or hostname)
  - JSON payload encoding
  - Response parsing (status code, body, max 1KB)
  - Timeout handling (default: 5000ms)
  - Error handling (connection failed, timeout, HTTP error)
  - WiFiClient integration via WiFiManager
  - Memory-safe response handling (String.reserve())
  - Singleton pattern (consistent with Phase 1-3)

#### Sensor Processing Modules

- **PiEnhancedProcessor** (`src/services/sensor/pi_enhanced_processor.*`)
  - HTTP communication with God-Kaiser Server (Port 8000)
  - Raw sensor data sending (RawSensorData → ProcessedSensorData)
  - JSON response parsing (without external library)
  - Circuit-breaker pattern (5 failures → 60s pause)
  - Server address from ConfigManager (WiFiConfig.server_address)
  - Error handling (circuit open, HTTP error, JSON parse error)
  - Singleton pattern (consistent with Phase 1-3)

#### Sensor Management Modules

- **SensorManager** (`src/services/sensor/sensor_manager.*`)
  - Sensor registry (SensorConfig array, max 20 sensors)
  - GPIO-based sensor management
  - Sensor configuration (configureSensor, removeSensor, getSensorConfig)
  - Raw data reading (Analog, Digital, I2C, OneWire)
  - Automatic MQTT publishing (every 30s via performAllMeasurements)
  - Integration with PiEnhancedProcessor (HTTP processing)
  - Legacy Phase 3 methods (performI2CMeasurement, performOneWireMeasurement)
  - Singleton pattern (consistent with Phase 1-3)

#### Models

- **SensorConfig** (`src/models/sensor_types.h`)
  - GPIO pin assignment
  - Sensor type (string-based: "ph_sensor", "temperature_ds18b20", etc.)
  - Sensor name and subzone assignment
  - Active status and raw_mode flag (always true for server-centric)
  - Last reading tracking

- **SensorReading** (`src/models/sensor_types.h`)
  - Raw value (ADC 0-4095 or OneWire raw)
  - Processed value from server
  - Unit and quality assessment
  - Timestamp and validation status
  - Error message support

- **RawSensorData** (`src/services/sensor/pi_enhanced_processor.h`)
  - GPIO, sensor type, raw value
  - Timestamp and metadata (JSON)

- **ProcessedSensorData** (`src/services/sensor/pi_enhanced_processor.h`)
  - Processed value, unit, quality
  - Timestamp and validation status
  - Error message support

#### Integration

- **main.cpp Phase 4 Integration** (`src/main.cpp`)
  - HTTPClient initialization
  - PiEnhancedProcessor initialization
  - SensorManager initialization
  - Sensor configuration via MQTT (config topic handler)
  - Sensor measurement loop (performAllMeasurements every 30s)
  - MQTT callback for sensor configuration updates

- **ConfigManager Sensor Support** (`src/services/config/config_manager.*`)
  - Sensor configuration save/load to NVS
  - NVS keys: `sensor_{i}_gpio`, `sensor_{i}_type`, `sensor_{i}_name`, `sensor_{i}_subzone`, `sensor_{i}_active`, `sensor_{i}_raw_mode`
  - Index-based sensor storage (not GPIO-based)
  - Sensor count tracking

#### MQTT Topics

- **Sensor Data Publishing**
  - Topic: `kaiser/god/esp/{esp_id}/sensor/{gpio}/data`
  - QoS: 1 (at least once)
  - Frequency: 30s (automatic)
  - Payload: JSON with timestamp, ESP-ID, GPIO, type, raw/processed value, unit, quality

- **Sensor Configuration**
  - Topic: `kaiser/god/esp/{esp_id}/config` (subscribe)
  - Payload: JSON array of sensor configurations
  - Automatic NVS storage via ConfigManager

#### HTTP API Integration

- **God-Kaiser Server API**
  - Endpoint: `http://{server_address}:8000/api/v1/sensors/process`
  - Method: POST
  - Content-Type: `application/json`
  - Request: Raw sensor data (esp_id, gpio, sensor_type, raw_value, timestamp, metadata)
  - Response: Processed sensor data (processed_value, unit, quality, timestamp)
  - Timeout: 5000ms

### Changed

- ConfigManager: Added sensor configuration methods (saveSensorConfig, loadSensorConfig, removeSensorConfig)
- main.cpp: Added sensor measurement loop and MQTT config handler
- NVS Keys: Added sensor-related keys (see NVS_KEYS.md)

### Removed

- None

### Known Issues

- None

### Performance

- HTTP request latency: ~100ms (HTTP roundtrip)
- Sensor reading cycle: 30s (all active sensors)
- Circuit-breaker timeout: 60s (after 5 consecutive failures)
- Memory usage: ~35 KB / 320 KB (10.9%)

### Dependencies

- HTTPClient (Phase 4)
- WiFiClient.h (ESP32 Core)
- MQTTClient (Phase 2)
- I2CBusManager, OneWireBusManager (Phase 3)

---

## Version History

- **4.0.0** - Phase 4 Sensor System (2025-01-28)
- **3.0.0** - Phase 3 Hardware Abstraction Layer (2025-01-28)
- **2.0.0** - Phase 2 Communication Layer (2025-11-14)
## [5.0.0] - Phase 5 Actuator System - 2025-11-18

### Added

- Actuator model extensions (`src/models/actuator_types.h`): expanded structs + helper utilities
- Actuator drivers (`PumpActuator`, `PWMActuator`, `ValveActuator`) + `IActuatorDriver` interface
- `SafetyController` emergency state-machine with broadcast + ESP-scoped topics
- `ActuatorManager` registry, MQTT command/response/alert/status handling, config parsing
- TopicBuilder Phase-5 helpers (response, alert, actuator emergency)
- ConfigManager actuator persistence hooks (`load/save/validateActuatorConfig`) for future Option 3 (currently unused in Option 2 mode)
- `main.cpp` Phase 5 integration (MQTT wildcard subscription, callback routing, loop maintenance)
- Tests: `test_topic_builder.cpp` (new Actuator topic cases), `test_actuator_models.cpp`

### Changed

- `docs/PHASE_5_IMPLEMENTATION.md`, `docs/Roadmap.md`, `docs/NVS_KEYS.md` updated for Phase 5 status + Option 2 decision
- `CHANGELOG.md` now documents Phase 5 milestone

### Notes

- Phase 5 remains **server-centric (Option 2)**. Persistence hooks are dormant until Phase 6 Hybrid rollout.

---

## [6.0.0] - Phase 6 Error Recovery & Circuit Breaker - 2025-01-28

### Added

#### Error Recovery Modules

- **CircuitBreaker** (`src/error_handling/circuit_breaker.*`)
  - Circuit breaker pattern for service protection
  - Three states: CLOSED, OPEN, HALF_OPEN
  - Configurable failure threshold, open timeout, half-open timeout
  - Automatic state transitions with recovery testing
  - Manual reset capability
  - Service-specific naming for logging
  - Singleton pattern (per service instance)

- **ProvisionManager** (`src/services/provisioning/provision_manager.*`)
  - WiFi Access Point mode for initial configuration
  - HTTP API for configuration provisioning
  - Automatic fallback to AP mode if WiFi not configured
  - Configuration timeout handling (10 minutes)
  - Integration with ConfigManager for WiFi config persistence

#### Circuit Breaker Integration

- **WiFiManager Circuit Breaker** (`src/services/communication/wifi_manager.*`)
  - Configuration: 10 failures → OPEN, 60s recovery timeout, 15s half-open test
  - Blocks reconnection attempts when OPEN
  - Automatic recovery testing in HALF_OPEN state
  - Success/failure tracking for state transitions

- **MQTTClient Circuit Breaker** (`src/services/communication/mqtt_client.*`)
  - Configuration: 5 failures → OPEN, 30s recovery timeout, 10s half-open test
  - Blocks publish and reconnect attempts when OPEN
  - Integrated into `publish()`, `reconnect()`, and `safePublish()`
  - Automatic recovery on successful operations

- **PiEnhancedProcessor Circuit Breaker** (`src/services/sensor/pi_enhanced_processor.*`)
  - Configuration: 5 failures → OPEN, 60s recovery timeout, 10s half-open test
  - Blocks HTTP requests when OPEN
  - Prevents connection storms to God-Kaiser server
  - Automatic recovery on successful HTTP responses

#### Integration

- **main.cpp Phase 6 Integration** (`src/main.cpp`)
  - ProvisionManager initialization and AP mode check (lines 173-231)
  - Circuit breaker protection for WiFi and MQTT (lines 274-295)
  - System health monitoring (every 5 minutes, lines 654-666)
  - Error recovery logging
  - Boot button factory reset check (lines 72-134)

### Changed

- WiFiManager: Added circuit breaker protection to prevent connection storms
- MQTTClient: Added circuit breaker protection for publish and reconnect operations
- PiEnhancedProcessor: Enhanced with circuit breaker for server failure handling
- Error recovery: Automatic reconnection with exponential backoff and circuit breaker protection
- Documentation: Updated API_REFERENCE.md and MQTT_CLIENT_API.md with circuit breaker details

### Performance

- Circuit breaker overhead: <0.1% CPU, ~100 bytes memory per breaker
- Reconnection protection: Prevents connection storms (stack overflow prevention)
- Recovery time: 30-60s timeout before retry attempts

### Dependencies

- CircuitBreaker (Phase 6)
- ProvisionManager (Phase 6)

---

## [7.0.0] - Phase 7 Dynamic Zone Assignment - 2025-01-28

### Added

#### Zone Management Modules

- **Dynamic Zone Assignment** (`src/services/config/config_manager.*`)
  - `updateZoneAssignment()` method for runtime zone updates via MQTT
  - Hierarchical zone support (zone_id, master_zone_id, zone_name)
  - Zone assignment status tracking (`zone_assigned` flag)
  - NVS persistence for zone configuration
  - TopicBuilder reconfiguration on zone assignment

- **KaiserZone Structure Enhancement** (`src/models/system_types.h`)
  - Phase 7 fields: `zone_id`, `master_zone_id`, `zone_name`, `zone_assigned`
  - Backward compatibility with existing `kaiser_id`, `kaiser_name` fields
  - Hierarchical zone organization support

#### MQTT Integration

- **Zone Assignment Handler** (`src/main.cpp` lines 329-340, 415-489)
  - Topic subscription: `kaiser/{kaiser_id}/esp/{esp_id}/zone/assign` (assigned ESPs)
  - Topic subscription: `kaiser/god/esp/{esp_id}/zone/assign` (unassigned ESPs)
  - JSON payload parsing (zone_id, master_zone_id, zone_name, kaiser_id)
  - Automatic TopicBuilder reconfiguration (`TopicBuilder::setKaiserId()`)
  - Global variable updates (`g_kaiser` structure)
  - Acknowledgment publishing (`kaiser/{kaiser_id}/esp/{esp_id}/zone/ack` topic, QoS 1)
  - System state update (`STATE_ZONE_CONFIGURED`)
  - Updated heartbeat publishing after assignment

- **Heartbeat Enhancement** (`src/services/communication/mqtt_client.cpp`)
  - Zone information included in heartbeat payload
  - Fields: `zone_id`, `master_zone_id`, `zone_assigned`
  - Automatic zone info inclusion from global `g_kaiser` variable
  - Manual string concatenation for performance (not DynamicJsonDocument)

#### NVS Storage

- **Zone Configuration Keys** (`docs/NVS_KEYS.md`)
  - Phase 7 keys: `zone_id`, `master_zone_id`, `zone_name`, `zone_assigned`
  - Legacy keys maintained for backward compatibility
  - Implementation details documented with code references

#### Documentation

- **Zone Assignment Flow** (`docs/system-flows/08-zone-assignment-flow.md`)
  - Complete flow documentation with code references
  - MQTT topic migration behavior
  - Subscription handling during boot and reassignment
  - Boot sequence integration

- **API Documentation Updates**
  - API_REFERENCE.md: KaiserZone structure and updateZoneAssignment() documented
  - MQTT_CLIENT_API.md: Heartbeat payload format with zone info
  - NVS_KEYS.md: Phase 7 zone configuration keys

### Changed

- ConfigManager: Enhanced with `updateZoneAssignment()` for runtime zone updates (lines 257-286)
- MQTTClient: Heartbeat payload enhanced with zone information (Phase 7, lines 392-404)
- TopicBuilder: Automatic kaiser_id update on zone assignment (`setKaiserId()`)
- System state: `STATE_ZONE_CONFIGURED` added to state machine (enum value: 6)
- SensorManager: Zone information included in sensor data publishing (Phase 7)
- ActuatorManager: Zone information included in actuator status publishing (Phase 7)
- Runtime reconfiguration: Sensor and actuator configs persist immediately to NVS (Phase 7)

### Removed

- None (backward compatible)

### Known Issues

- MQTT subscriptions not automatically updated on kaiser_id change (requires reconnection)
- Zone reassignment requires MQTT reconnection for subscription update

### Performance

- Zone assignment operation: 50-150ms (NVS writes + MQTT publish)
- Memory overhead: ~500 bytes (zone config namespace)
- Heartbeat payload: +50 bytes (zone info fields)

### Dependencies

- ConfigManager (Phase 1)
- MQTTClient (Phase 2)
- TopicBuilder (Phase 1)

---

## Version History

- **7.0.0** - Phase 7 Dynamic Zone Assignment (2025-01-28)
- **6.0.0** - Phase 6 Error Recovery & Circuit Breaker (2025-01-28)
- **5.0.0** - Phase 5 Actuator System (2025-11-18)
- **4.0.0** - Phase 4 Sensor System (2025-01-28)
- **3.0.0** - Phase 3 Hardware Abstraction Layer (2025-01-28)
- **2.0.0** - Phase 2 Communication Layer (2025-11-14)
- **1.0.0** - Phase 1 Core Infrastructure (2025-11-14)
- **0.0.0** - Project initialization (2025-11-13)

---

**Changelog Format:** [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)  
**Versioning:** [Semantic Versioning](https://semver.org/spec/v2.0.0.html)


