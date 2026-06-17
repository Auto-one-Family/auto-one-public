# Error Recovery Flow

## Overview

Comprehensive error tracking, circuit breaker patterns, automatic reconnection, and safe-mode triggering to ensure system reliability and hardware safety even under failure conditions.

## Files Analyzed

- `src/error_handling/error_tracker.cpp` (lines 1-251) - Error tracking implementation
- `src/error_handling/error_tracker.h` (lines 1-102) - Error tracker interface
- `src/error_handling/circuit_breaker.cpp` (lines 1-188) - Circuit breaker pattern implementation
- `src/error_handling/circuit_breaker.h` (lines 1-147) - Circuit breaker interface
- `src/services/actuator/safety_controller.cpp` (lines 1-151) - Emergency stop and recovery
- `src/services/actuator/safety_controller.h` (lines 1-51) - Safety controller interface
- `src/services/communication/wifi_manager.cpp` (lines 1-253) - WiFi reconnection
- `src/services/communication/wifi_manager.h` (lines 1-62) - WiFi manager interface
- `src/services/communication/mqtt_client.cpp` (lines 1-603) - MQTT reconnection and offline buffer
- `src/services/communication/mqtt_client.h` (lines 1-136) - MQTT client interface
- `src/drivers/gpio_manager.cpp` (lines 169-209) - Safe-mode triggering
- `src/models/error_codes.h` (lines 1-196) - Error code definitions
- `src/main.cpp` (lines 637-666) - Main loop with health monitoring

## Error Categories

**File:** `src/error_handling/error_tracker.h` (lines 9-14)

```cpp
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM (1000-1999)
  ERROR_SERVICE = 2000,        // Sensor, Actuator, Config (2000-2999)
  ERROR_COMMUNICATION = 3000,  // MQTT, HTTP, WiFi (3000-3999)
  ERROR_APPLICATION = 4000     // State, Memory, System (4000-4999)
};
```

**Severity Levels:**

```cpp
enum ErrorSeverity {
  ERROR_SEVERITY_WARNING = 1,  // Recoverable warning
  ERROR_SEVERITY_ERROR = 2,    // Error but system can continue
  ERROR_SEVERITY_CRITICAL = 3  // Critical error, system unstable
};
```

---

## Flow 1: Error Tracking

### Error Structure

```cpp
struct ErrorEntry {
  unsigned long timestamp;
  uint16_t error_code;
  ErrorSeverity severity;
  char message[128];
  uint8_t occurrence_count;  // Duplicate tracking
};
```

### Tracking Error

**File:** `src/error_handling/error_tracker.cpp` (lines 43-49)

```cpp
void ErrorTracker::trackError(uint16_t error_code, ErrorSeverity severity, const char* message) {
  // Log to Logger (always, not throttled)
  logErrorToLogger(error_code, severity, message);

  // Add to circular buffer (always, not throttled)
  addToBuffer(error_code, severity, message);

  // Publish to MQTT (rate-limited: max 1 per error code per 60s)
  publishErrorToMqtt(error_code, severity, message);
}
```

### Duplicate Detection and Occurrence Counting

**File:** `src/error_handling/error_tracker.cpp` (lines 175-204)

```cpp
void ErrorTracker::addToBuffer(uint16_t error_code, ErrorSeverity severity, const char* message) {
  // Check if this error already exists in recent entries (last 5) - occurrence counting
  for (int i = 0; i < 5 && i < (int)error_count_; i++) {
    int check_index = (error_buffer_index_ - 1 - i + MAX_ERROR_ENTRIES) % MAX_ERROR_ENTRIES;
    ErrorEntry& entry = error_buffer_[check_index];
    
    if (entry.error_code == error_code && strcmp(entry.message, message) == 0) {
      entry.occurrence_count++;
      entry.timestamp = millis();  // Update timestamp
      return;  // Don't add duplicate
    }
  }
  
  // Add new entry
  size_t index = error_buffer_index_;
  error_buffer_[index].timestamp = millis();
  error_buffer_[index].error_code = error_code;
  error_buffer_[index].severity = severity;
  strncpy(error_buffer_[index].message, message, sizeof(error_buffer_[index].message) - 1);
  error_buffer_[index].message[sizeof(error_buffer_[index].message) - 1] = '\0';
  error_buffer_[index].occurrence_count = 1;
  
  // Advance circular buffer index
  error_buffer_index_ = (error_buffer_index_ + 1) % MAX_ERROR_ENTRIES;
  
  // Track total count (up to MAX_ERROR_ENTRIES)
  if (error_count_ < MAX_ERROR_ENTRIES) {
    error_count_++;
  }
}
```

**Features:**
- Circular buffer (50 entries, `MAX_ERROR_ENTRIES = 50`)
- Duplicate detection: Checks last 5 entries for same error code + message
- Occurrence counting: Increments counter and updates timestamp on duplicate
- Automatic log integration via `logErrorToLogger()`
- Fixed-size buffer: No dynamic allocation

**Usage:**

```cpp
errorTracker.trackError(ERROR_SENSOR_READ_FAILED, 
                       ERROR_SEVERITY_ERROR,
                       "DS18B20 read timeout");
```

---

## Flow 2: Circuit Breaker Pattern

### Purpose

Prevent connection storms that could:
- Crash ESP32 (stack overflow)
- Overload MQTT broker
- Drain battery on reconnection attempts

### Circuit Breaker States

```
CLOSED → (failures) → OPEN → (timeout) → HALF_OPEN → (test) → CLOSED or OPEN
```

**CLOSED:** Normal operation, requests pass through

**OPEN:** Too many failures, block all requests for timeout period

**HALF_OPEN:** Test mode, allow one request to test recovery

### Implementation

**File:** `src/error_handling/circuit_breaker.h` (lines 44-143)

```cpp
class CircuitBreaker {
public:
  CircuitBreaker(const char* service_name, 
                 uint8_t failure_threshold = 5, 
                 unsigned long recovery_timeout_ms = 30000,
                 unsigned long halfopen_timeout_ms = 10000);
  
  bool allowRequest();           // Check if request allowed
  void recordSuccess();          // Record successful operation
  void recordFailure();          // Record failed operation
  void reset();                  // Force reset to CLOSED
  
  bool isOpen() const;           // Check if OPEN
  bool isClosed() const;        // Check if CLOSED
  CircuitState getState() const; // Get current state
  uint8_t getFailureCount() const;
  const char* getServiceName() const;
  
private:
  const char* service_name_;
  uint8_t failure_threshold_;
  unsigned long recovery_timeout_ms_;
  unsigned long halfopen_timeout_ms_;
  CircuitState state_;
  uint8_t failure_count_;
  unsigned long last_failure_time_;
  unsigned long state_change_time_;
  
  void transitionTo(CircuitState new_state);
  bool shouldAttemptRecovery() const;
  bool halfOpenTestTimedOut() const;
};
```

**State Enum:**

**File:** `src/error_handling/circuit_breaker.h` (lines 9-13)

```cpp
enum class CircuitState : uint8_t {
  CLOSED = 0,      // Normal operation, requests allowed
  OPEN,            // Service failed, requests blocked
  HALF_OPEN        // Testing recovery, limited requests allowed
};
```

### Circuit Breaker State Machine

**File:** `src/error_handling/circuit_breaker.cpp` (lines 29-70)

```cpp
bool CircuitBreaker::allowRequest() {
  // STATE: CLOSED (Normal Operation)
  if (state_ == CircuitState::CLOSED) {
    return true;  // All requests allowed
  }
  
  // STATE: OPEN (Service Failed)
  if (state_ == CircuitState::OPEN) {
    // Check if recovery timeout elapsed
    if (shouldAttemptRecovery()) {
      LOG_INFO("CircuitBreaker [" + String(service_name_) + "]: Attempting recovery → HALF_OPEN");
      transitionTo(CircuitState::HALF_OPEN);
      return true;  // Allow ONE test request
    }
    return false;  // Still in OPEN state, block request
  }
  
  // STATE: HALF_OPEN (Testing Recovery)
  if (state_ == CircuitState::HALF_OPEN) {
    // Check if test timed out
    if (halfOpenTestTimedOut()) {
      LOG_WARNING("CircuitBreaker [" + String(service_name_) + "]: HALF_OPEN test timed out → OPEN");
      transitionTo(CircuitState::OPEN);
      return false;
    }
    return true;  // Allow test request
  }
  
  return false;
}
```

**Success/Failure Recording:**

**File:** `src/error_handling/circuit_breaker.cpp` (lines 75-118)

```cpp
void CircuitBreaker::recordSuccess() {
  if (state_ == CircuitState::HALF_OPEN) {
    // HALF_OPEN → CLOSED (Recovery successful)
    LOG_INFO("CircuitBreaker [" + String(service_name_) + "]: Recovery successful → CLOSED");
    failure_count_ = 0;
    transitionTo(CircuitState::CLOSED);
  } else if (state_ == CircuitState::CLOSED) {
    // Reset failure count on any success in CLOSED state
    if (failure_count_ > 0) {
      LOG_DEBUG("CircuitBreaker [" + String(service_name_) + "]: Failure count reset");
      failure_count_ = 0;
    }
  }
}

void CircuitBreaker::recordFailure() {
  last_failure_time_ = millis();
  failure_count_++;
  
  LOG_WARNING("CircuitBreaker [" + String(service_name_) + "]: Failure recorded (count: " + 
              String(failure_count_) + "/" + String(failure_threshold_) + ")");
  
  // CLOSED → Check Threshold
  if (state_ == CircuitState::CLOSED) {
    if (failure_count_ >= failure_threshold_) {
      LOG_ERROR("CircuitBreaker [" + String(service_name_) + "]: Failure threshold reached → OPEN");
      transitionTo(CircuitState::OPEN);
    }
  }
  // HALF_OPEN → Back to OPEN
  else if (state_ == CircuitState::HALF_OPEN) {
    LOG_WARNING("CircuitBreaker [" + String(service_name_) + "]: Recovery test failed → OPEN");
    transitionTo(CircuitState::OPEN);
  }
}
```

### WiFi Circuit Breaker

**File:** `src/services/communication/wifi_manager.cpp` (lines 27-36)

**Configuration:**

```cpp
WiFiManager::WiFiManager() 
    : circuit_breaker_("WiFi", 10, 60000, 15000) {
  // Circuit Breaker configured:
  // - 10 failures → OPEN (WiFi needs more tolerance)
  // - 60s recovery timeout (WiFi takes longer)
  // - 15s half-open test timeout
}
```

**Usage in WiFi reconnection:**

**File:** `src/services/communication/wifi_manager.cpp` (lines 133-171)

```cpp
void WiFiManager::reconnect() {
    if (isConnected()) {
        LOG_DEBUG("WiFi already connected");
        circuit_breaker_.recordSuccess();  // Reset on successful connection
        return;
    }
    
    // CIRCUIT BREAKER CHECK (Phase 6+)
    if (!circuit_breaker_.allowRequest()) {
        LOG_DEBUG("WiFi reconnect blocked by Circuit Breaker (waiting for recovery)");
        return;  // Skip reconnect attempt
    }
    
    if (!shouldAttemptReconnect()) {
        return;
    }
    
    reconnect_attempts_++;
    last_reconnect_attempt_ = millis();
    
    LOG_INFO("Attempting WiFi reconnection (attempt " + 
             String(reconnect_attempts_) + "/" + 
             String(MAX_RECONNECT_ATTEMPTS) + ")");
    
    if (!connectToNetwork()) {
        // connectToNetwork already calls circuit_breaker_.recordFailure()
        
        if (reconnect_attempts_ >= MAX_RECONNECT_ATTEMPTS) {
            LOG_CRITICAL("Max WiFi reconnection attempts reached");
            errorTracker.logCommunicationError(ERROR_WIFI_CONNECT_FAILED, 
                                               "Max reconnection attempts reached");
        }
    } else {
        // ✅ RECONNECT SUCCESS
        // connectToNetwork already calls circuit_breaker_.recordSuccess()
    }
}
```

### MQTT Circuit Breaker

**File:** `src/services/communication/mqtt_client.cpp` (lines 44-58)

**Configuration:**

```cpp
MQTTClient::MQTTClient() 
    : circuit_breaker_("MQTT", 5, 30000, 10000) {
  // Circuit Breaker configured:
  // - 5 failures → OPEN
  // - 30s recovery timeout
  // - 10s half-open test timeout
}
```

**Usage in MQTT Publishing:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 243-303)

```cpp
bool MQTTClient::publish(const String& topic, const String& payload, uint8_t qos) {
    // CIRCUIT BREAKER CHECK
    if (!circuit_breaker_.allowRequest()) {
        LOG_WARNING("MQTT publish blocked by Circuit Breaker (Service DOWN)");
        LOG_DEBUG("  Topic: " + topic);
        LOG_DEBUG("  Circuit State: OPEN (waiting for recovery)");
        // Don't add to offline buffer when circuit is open
        return false;
    }

    // CONNECTION CHECK
    if (!isConnected()) {
        LOG_WARNING("MQTT not connected, adding to offline buffer");
        circuit_breaker_.recordFailure();  // Connection failure counts
        return addToOfflineBuffer(topic, payload, qos);
    }
    
    // MQTT PUBLISH
    bool success = mqtt_.publish(topic.c_str(), payload.c_str(), qos == 1);
    
    if (success) {
        circuit_breaker_.recordSuccess();
        LOG_DEBUG("Published: " + topic);
    } else {
        circuit_breaker_.recordFailure();
        LOG_ERROR("Publish failed: " + topic);
        errorTracker.logCommunicationError(ERROR_MQTT_PUBLISH_FAILED, 
                                           ("Publish failed: " + topic).c_str());
        
        if (circuit_breaker_.isOpen()) {
            LOG_WARNING("Circuit Breaker OPENED after failure threshold");
            LOG_WARNING("  MQTT will be unavailable for 30 seconds");
        }
        
        addToOfflineBuffer(topic, payload, qos);
    }
    
    return success;
}
```

---

## Flow 3: WiFi Reconnection

### Automatic Reconnection

**File:** `src/main.cpp` (line 639)

```cpp
void loop() {
  wifiManager.loop();  // Check and reconnect if needed
  // ...
}
```

**File:** `src/services/communication/wifi_manager.cpp` (lines 176-202)

```cpp
void WiFiManager::loop() {
    if (!initialized_) {
        return;
    }
    
    // Check connection status
    if (!isConnected()) {
        handleDisconnection();
    }
}

void WiFiManager::handleDisconnection() {
    static bool disconnection_logged = false;
    
    if (!disconnection_logged) {
        LOG_WARNING("WiFi disconnected");
        errorTracker.logCommunicationError(ERROR_WIFI_DISCONNECT, 
                                           "WiFi connection lost");
        disconnection_logged = true;
    }
    
    reconnect();
    
    if (isConnected()) {
        disconnection_logged = false;
    }
}
```

**Connection Logic:**

**File:** `src/services/communication/wifi_manager.cpp` (lines 84-119)

```cpp
bool WiFiManager::connectToNetwork() {
    LOG_INFO("Connecting to WiFi: " + current_config_.ssid);
    
    WiFi.begin(current_config_.ssid.c_str(), 
               current_config_.password.c_str());
    
    // Wait for connection with timeout
    unsigned long start_time = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start_time > WIFI_TIMEOUT_MS) {
            // ❌ CONNECTION FAILED
            LOG_ERROR("WiFi connection timeout");
            errorTracker.logCommunicationError(ERROR_WIFI_CONNECT_TIMEOUT, 
                                               "WiFi connection timeout");
            circuit_breaker_.recordFailure();
            
            // Check if Circuit Breaker opened
            if (circuit_breaker_.isOpen()) {
                LOG_WARNING("WiFi Circuit Breaker OPENED after failure threshold");
                LOG_WARNING("  Will retry in 60 seconds");
            }
            
            return false;
        }
        delay(100);
    }
    
    // ✅ CONNECTION SUCCESS
    LOG_INFO("WiFi connected! IP: " + WiFi.localIP().toString());
    LOG_INFO("WiFi RSSI: " + String(WiFi.RSSI()) + " dBm");
    
    reconnect_attempts_ = 0;
    circuit_breaker_.recordSuccess();
    
    return true;
}
```

**Timing Constants:**

**File:** `src/services/communication/wifi_manager.cpp` (lines 7-9)

```cpp
const unsigned long RECONNECT_INTERVAL_MS = 30000;  // 30 seconds
const uint16_t MAX_RECONNECT_ATTEMPTS = 10;
const unsigned long WIFI_TIMEOUT_MS = 10000;  // 10 seconds
```

**Timing:**
- Retry interval: 30 seconds (`RECONNECT_INTERVAL_MS`)
- Connection timeout: 10 seconds (`WIFI_TIMEOUT_MS`)
- Max attempts: 10 (`MAX_RECONNECT_ATTEMPTS`)
- Circuit breaker: After 10 failures → 60s pause, then 15s half-open test

---

## Flow 4: MQTT Reconnection

### Automatic Reconnection

**File:** `src/services/communication/mqtt_client.cpp` (lines 413-428)

```cpp
void MQTTClient::loop() {
    if (!initialized_) {
        return;
    }
    
    // Process MQTT loop
    if (isConnected()) {
        mqtt_.loop();
        
        // Publish heartbeat
        publishHeartbeat();
    } else {
        // Attempt reconnection
        reconnect();
    }
}
```

**Reconnection Logic:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 165-213)

```cpp
void MQTTClient::reconnect() {
    if (isConnected()) {
        LOG_DEBUG("MQTT already connected");
        circuit_breaker_.recordSuccess();  // Reset on successful connection
        return;
    }
    
    // CIRCUIT BREAKER CHECK (Phase 6+)
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
        // ❌ RECONNECT FAILED
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
        // ✅ RECONNECT SUCCESS
        circuit_breaker_.recordSuccess();
    }
}
```

**Connection to Broker:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 118-151)

```cpp
bool MQTTClient::connectToBroker() {
    LOG_INFO("Connecting to MQTT broker: " + current_config_.server + ":" + String(current_config_.port));
    
    bool connected = false;
    
    if (anonymous_mode_) {
        // Anonymous connection
        connected = mqtt_.connect(current_config_.client_id.c_str());
    } else {
        // Authenticated connection
        connected = mqtt_.connect(current_config_.client_id.c_str(),
                                 current_config_.username.c_str(),
                                 current_config_.password.c_str());
    }
    
    if (connected) {
        LOG_INFO("MQTT connected!");
        reconnect_attempts_ = 0;
        reconnect_delay_ms_ = RECONNECT_BASE_DELAY_MS;
        
        // Reset Circuit Breaker on successful connection (Phase 6+)
        circuit_breaker_.recordSuccess();
        
        // Process offline buffer
        processOfflineBuffer();
        
        return true;
    } else {
        LOG_ERROR("MQTT connection failed, rc=" + String(mqtt_.state()));
        errorTracker.logCommunicationError(ERROR_MQTT_CONNECT_FAILED, 
                                           ("MQTT connection failed, rc=" + String(mqtt_.state())).c_str());
        return false;
    }
}
```

### Exponential Backoff

**File:** `src/services/communication/mqtt_client.cpp` (lines 526-536)

**Constants:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 17-19)

```cpp
const unsigned long RECONNECT_BASE_DELAY_MS = 1000;   // 1 second
const unsigned long RECONNECT_MAX_DELAY_MS = 60000;   // 60 seconds
const uint16_t MAX_RECONNECT_ATTEMPTS = 10;
```

**Implementation:**

```cpp
unsigned long MQTTClient::calculateBackoffDelay() const {
    // Exponential backoff: delay * 2^attempts
    unsigned long delay = RECONNECT_BASE_DELAY_MS * (1 << reconnect_attempts_);
    
    // Cap at max delay
    if (delay > RECONNECT_MAX_DELAY_MS) {
        delay = RECONNECT_MAX_DELAY_MS;
    }
    
    return delay;
}
```

**Backoff Sequence:**
- Attempt 1: 1s (2^0 * 1000ms)
- Attempt 2: 2s (2^1 * 1000ms)
- Attempt 3: 4s (2^2 * 1000ms)
- Attempt 4: 8s (2^3 * 1000ms)
- Attempt 5: 16s (2^4 * 1000ms)
- Attempt 6+: 60s (capped at `RECONNECT_MAX_DELAY_MS`)

### Offline Message Buffer

**Buffer Structure:**

**File:** `src/services/communication/mqtt_client.h` (lines 94-97)

```cpp
static const uint16_t MAX_OFFLINE_MESSAGES = 100;
MQTTMessage offline_buffer_[MAX_OFFLINE_MESSAGES];
uint16_t offline_buffer_count_;
```

**Adding to Buffer:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 505-521)

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

**Processing Buffer:**

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

**Buffer Behavior:**
- **Capacity:** 100 messages (`MAX_OFFLINE_MESSAGES`)
- **When Full:** New messages are dropped, `ERROR_MQTT_BUFFER_FULL` logged
- **Processing:** Sequential, stops on first failure
- **Removal:** Shift remaining messages to front of array
- **Timestamps:** Each message stores `millis()` when buffered

---

## Flow 5: Emergency Stop and Recovery

### Emergency Stop Trigger

**Sources:**
1. ESP-specific MQTT command
2. Broadcast MQTT emergency
3. SafetyController manual trigger
4. Runtime protection (max runtime exceeded)

**File:** `src/services/actuator/safety_controller.cpp` (lines 37-48)

```cpp
bool SafetyController::emergencyStopAll(const String& reason) {
    if (!initialized_ && !begin()) {
        return false;
    }

    emergency_state_ = EmergencyState::EMERGENCY_ACTIVE;
    emergency_reason_ = reason;
    emergency_timestamp_ = millis();
    logEmergencyEvent(reason, 255);

    return actuatorManager.emergencyStopAll();
}
```

**Note:** MQTT alert publishing is handled by ActuatorManager, not SafetyController directly.

### Emergency Recovery

**File:** `src/services/actuator/safety_controller.cpp` (lines 63-95)

```cpp
bool SafetyController::clearEmergencyStop() {
    emergency_state_ = EmergencyState::EMERGENCY_CLEARING;
    if (!verifySystemSafety()) {
        actuatorManager.publishActuatorAlert(255, "verification_failed", "clear_emergency");
        LOG_WARNING("SafetyController verification failed during clearEmergencyStop");
        return false;
    }

    bool success = actuatorManager.clearEmergencyStop();
    if (success) {
        emergency_state_ = EmergencyState::EMERGENCY_RESUMING;
    }
    return success;
}

bool SafetyController::resumeOperation() {
    if (emergency_state_ != EmergencyState::EMERGENCY_RESUMING &&
        emergency_state_ != EmergencyState::EMERGENCY_ACTIVE) {
        return true;
    }

    delay(recovery_config_.inter_actuator_delay_ms);
    emergency_state_ = EmergencyState::EMERGENCY_NORMAL;
    emergency_reason_.clear();
    return true;
}
```

**Safety Verification:**

**File:** `src/services/actuator/safety_controller.cpp` (lines 122-131)

```cpp
bool SafetyController::verifySystemSafety() const {
    if (recovery_config_.max_retry_attempts == 0) {
        return false;
    }
    if (recovery_config_.verification_timeout_ms == 0 || emergency_timestamp_ == 0) {
        return true;
    }
    unsigned long elapsed = millis() - emergency_timestamp_;
    return elapsed >= recovery_config_.verification_timeout_ms;
}
```

**Recovery Configuration:**

**File:** `src/models/actuator_types.h` (RecoveryConfig structure)

```cpp
struct RecoveryConfig {
  uint32_t inter_actuator_delay_ms = 2000;  // 2s between actuators
  bool critical_first = true;                // Critical actuators first
  uint32_t verification_timeout_ms = 5000;   // 5s verification
  uint8_t max_retry_attempts = 3;            // 3 retry attempts
};
```

**Emergency States:**

```cpp
enum class EmergencyState {
  EMERGENCY_NORMAL,      // Normal operation
  EMERGENCY_ACTIVE,      // Emergency stop active
  EMERGENCY_CLEARING,    // Clearing emergency stop
  EMERGENCY_RESUMING     // Resuming operation
};
```

---

## Flow 6: Safe-Mode Triggering

### Hardware Safe-Mode

**File:** `src/drivers/gpio_manager.cpp` (lines 169-209)

```cpp
void GPIOManager::enableSafeModeForAllPins() {
    LOG_CRITICAL("GPIOManager: Emergency safe-mode activated");
    
    uint8_t de_energized_count = 0;
    uint8_t warning_count = 0;
    
    for (auto& pin_info : pins_) {
        // Enhanced safety - De-energize outputs BEFORE mode change
        if (pin_info.mode == OUTPUT) {
            digitalWrite(pin_info.pin, LOW);  // Turn off actuator
            de_energized_count++;
            delayMicroseconds(10);
            LOG_INFO("Emergency: GPIO " + String(pin_info.pin) + " de-energized before safe-mode");
        }
        
        // Now safe to change mode
        pinMode(pin_info.pin, INPUT_PULLUP);
        
        // Verify emergency safe mode
        if (!verifyPinState(pin_info.pin, INPUT_PULLUP)) {
            LOG_WARNING("GPIO " + String(pin_info.pin) + " emergency safe-mode failed");
            warning_count++;
        }
        
        // Update tracking
        pin_info.in_safe_mode = true;
        pin_info.owner[0] = '\0';
        pin_info.mode = INPUT_PULLUP;
    }
    
    if (warning_count > 0) {
        LOG_CRITICAL("Emergency safe-mode: " + String(warning_count) + " pins failed verification!");
    }
    
    LOG_INFO("GPIOManager: All pins returned to safe mode");
}
```

**Initialization Safe-Mode:**

**File:** `src/drivers/gpio_manager.cpp` (lines 31-88)

```cpp
void GPIOManager::initializeAllPinsToSafeMode() {
    Serial.println("\n=== GPIO SAFE-MODE INITIALIZATION ===");
    
    // Initialize all safe GPIO pins to INPUT_PULLUP
    for (uint8_t i = 0; i < HardwareConfig::SAFE_PIN_COUNT; i++) {
        uint8_t pin = HardwareConfig::SAFE_GPIO_PINS[i];
        
        // Set hardware pin mode to INPUT_PULLUP (safe state)
        pinMode(pin, INPUT_PULLUP);
        
        // Register pin in tracking system
        GPIOPinInfo info;
        info.pin = pin;
        info.mode = INPUT_PULLUP;
        info.in_safe_mode = true;
        pins_.push_back(info);
    }
    
    LOG_INFO("GPIOManager: Safe-Mode initialization complete");
}
```

**Triggered by:**
- **Boot initialization:** `initializeAllPinsToSafeMode()` called first in `setup()`
- **Critical hardware error:** Via `enableSafeModeForAllPins()`
- **Watchdog reset:** System restart → safe-mode initialization
- **Manual command:** Via GPIO manager API
- **Safety Controller:** Emergency stop triggers safe-mode
- **Provisioning timeout:** System enters safe-mode state

**Safe-Mode State:**

**File:** `src/models/system_types.h`

```cpp
enum SystemState {
  STATE_INITIALIZING,
  STATE_SAFE_MODE,      // Safe-mode active
  STATE_PROVISIONING,
  // ... other states
};
```

---

## Error Statistics

### Retrieving Error History

**File:** `src/error_handling/error_tracker.cpp` (lines 77-100)

```cpp
String ErrorTracker::getErrorHistory(uint8_t max_entries) const {
    String result = "";
    size_t entries_added = 0;
    
    // Start from oldest entry
    size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
    
    for (size_t i = 0; i < error_count_ && entries_added < max_entries; i++) {
        size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
        const ErrorEntry& entry = error_buffer_[index];
        
        result += "[" + String(entry.timestamp) + "] ";
        result += "[" + String(entry.error_code) + "] ";
        result += "[" + String(getCategoryString(entry.error_code)) + "] ";
        result += String(entry.message);
        if (entry.occurrence_count > 1) {
            result += " (x" + String(entry.occurrence_count) + ")";
        }
        result += "\n";
        entries_added++;
    }
    
    return result;
}
```

### Error Retrieval by Category

**File:** `src/error_handling/error_tracker.cpp` (lines 102-125)

```cpp
String ErrorTracker::getErrorsByCategory(ErrorCategory category, uint8_t max_entries) const {
    String result = "";
    size_t entries_added = 0;
    
    size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
    
    for (size_t i = 0; i < error_count_ && entries_added < max_entries; i++) {
        size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
        const ErrorEntry& entry = error_buffer_[index];
        
        if (getCategory(entry.error_code) == category) {
            result += "[" + String(entry.timestamp) + "] ";
            result += "[" + String(entry.error_code) + "] ";
            result += String(entry.message);
            if (entry.occurrence_count > 1) {
                result += " (x" + String(entry.occurrence_count) + ")";
            }
            result += "\n";
            entries_added++;
        }
    }
    
    return result;
}
```

### Error Status Queries

**File:** `src/error_handling/error_tracker.cpp` (lines 127-170)

```cpp
size_t ErrorTracker::getErrorCount() const {
    return error_count_;
}

size_t ErrorTracker::getErrorCountByCategory(ErrorCategory category) const {
    size_t count = 0;
    
    size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
    
    for (size_t i = 0; i < error_count_; i++) {
        size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
        if (getCategory(error_buffer_[index].error_code) == category) {
            count++;
        }
    }
    
    return count;
}

bool ErrorTracker::hasActiveErrors() const {
    return error_count_ > 0;
}

bool ErrorTracker::hasCriticalErrors() const {
    size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
    
    for (size_t i = 0; i < error_count_; i++) {
        size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
        if (error_buffer_[index].severity == ERROR_SEVERITY_CRITICAL) {
            return true;
        }
    }
    
    return false;
}

void ErrorTracker::clearErrors() {
    error_buffer_index_ = 0;
    error_count_ = 0;
    LOG_INFO("ErrorTracker: Error history cleared");
}
```

**Example Output:**

```
[1234567] [1001] [HARDWARE] GPIO conflict on pin 4
[1234890] [3011] [COMMUNICATION] MQTT connection timeout (x5)
[1235123] [2041] [SERVICE] Sensor read failed GPIO 4
```

### Error Code Ranges

**File:** `src/models/error_codes.h` (lines 7-12)

| Range | Category | Examples |
|-------|----------|----------|
| 1000-1999 | HARDWARE | GPIO, I2C, PWM, Sensor, Actuator |
| 2000-2999 | SERVICE | NVS, Config, Logger, Storage |
| 3000-3999 | COMMUNICATION | WiFi, MQTT, HTTP, Network |
| 4000-4999 | APPLICATION | State, Memory, System, Task |

**Common Error Codes:**

**Hardware (1000-1999):**
- `ERROR_GPIO_RESERVED` (1001)
- `ERROR_I2C_INIT_FAILED` (1010)
- `ERROR_SENSOR_READ_FAILED` (1040)
- `ERROR_ACTUATOR_SET_FAILED` (1050)

**Communication (3000-3999):**
- `ERROR_WIFI_CONNECT_TIMEOUT` (3002)
- `ERROR_WIFI_CONNECT_FAILED` (3003)
- `ERROR_WIFI_DISCONNECT` (3004)
- `ERROR_MQTT_CONNECT_FAILED` (3011)
- `ERROR_MQTT_PUBLISH_FAILED` (3012)
- `ERROR_MQTT_BUFFER_FULL` (3015)

**Application (4000-4999):**
- `ERROR_SYSTEM_SAFE_MODE` (4052)

---

## Health Monitoring

**File:** `src/main.cpp` (lines 653-666)

```cpp
// PHASE 6+: SYSTEM HEALTH MONITORING (every 5 minutes)
static unsigned long last_health_check = 0;
if (millis() - last_health_check >= 300000) {  // 5 minutes
    last_health_check = millis();
    
    LOG_INFO("=== System Health Check ===");
    LOG_INFO("WiFi Status: " + wifiManager.getConnectionStatus());
    LOG_INFO("MQTT Status: " + mqttClient.getConnectionStatus());
    LOG_INFO("Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
    LOG_INFO("Uptime: " + String(millis() / 1000) + " seconds");
    LOG_INFO("Error Count: " + String(errorTracker.getErrorCount()));
    LOG_INFO("==========================");
}
```

**Metrics Tracked:**
- **WiFi Status:** Connection state (Connected, Disconnected, etc.)
- **MQTT Status:** Connection state and error details
- **Free Heap:** Available RAM in bytes
- **Uptime:** System uptime in seconds
- **Error Count:** Total errors in circular buffer

**Connection Status Details:**

**WiFi Status Values:**
- `Connected` - WiFi connected
- `SSID not available` - Network not found
- `Connection failed` - Authentication failed
- `Connection lost` - Lost connection
- `Disconnected` - Not connected
- `Idle` - Initializing

**MQTT Status Values:**
- `Connected` - MQTT connected
- `Connection timeout` - Broker not responding
- `Connection lost` - Lost connection
- `Connect failed` - Connection attempt failed
- `Disconnected` - Not connected
- `Bad protocol` - Protocol version mismatch
- `Bad client ID` - Invalid client ID
- `Server unavailable` - Broker unavailable
- `Bad credentials` - Authentication failed
- `Unauthorized` - Access denied

**Heartbeat Integration:**

**File:** `src/services/communication/mqtt_client.cpp` (lines 380-408)

The heartbeat system publishes health metrics every 60 seconds:

```cpp
void MQTTClient::publishHeartbeat() {
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
    
    publish(topic, payload, 0);
}
```

**Heartbeat Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat`

---

## Performance Impact

| Mechanism | CPU | Memory | Notes |
|-----------|-----|--------|-------|
| Error tracking | <1% | ~6.5KB | Circular buffer (50 entries × ~130 bytes) |
| Circuit breaker | <0.1% | ~20 bytes | Per breaker instance |
| WiFi reconnect | 2-5% | Minimal | Only when disconnected, blocking |
| MQTT reconnect | 2-5% | ~25KB | Offline buffer (100 messages × ~250 bytes) |
| Health monitoring | <0.1% | Minimal | Every 5 min, non-blocking |
| Safe-mode GPIO | <1% | Minimal | One-time operation on emergency |

**Memory Breakdown:**
- **Error Buffer:** 50 entries × 130 bytes = ~6.5KB
- **MQTT Offline Buffer:** 100 messages × ~250 bytes = ~25KB
- **Circuit Breakers:** 2 instances (WiFi + MQTT) × ~20 bytes = ~40 bytes
- **Total:** ~32KB heap memory

**CPU Impact:**
- **Normal Operation:** <1% (error tracking + health checks)
- **Reconnection:** 2-5% during active reconnection attempts (blocking)
- **Emergency Safe-Mode:** <1% (one-time GPIO operations)

**Timing Characteristics:**
- **Error Tracking:** <1ms per error
- **Circuit Breaker Check:** <0.1ms per request
- **WiFi Reconnect:** 10s timeout (blocking)
- **MQTT Reconnect:** Variable (exponential backoff)
- **Health Check:** <10ms every 5 minutes
- **Safe-Mode GPIO:** ~100ms for all pins

---

## Integration Points

### Error Tracking Integration

Error tracking is integrated throughout the system:

**Hardware Layer:**
- GPIO conflicts → `ERROR_GPIO_CONFLICT`
- I2C failures → `ERROR_I2C_INIT_FAILED`
- Sensor read failures → `ERROR_SENSOR_READ_FAILED`

**Communication Layer:**
- WiFi disconnections → `ERROR_WIFI_DISCONNECT`
- MQTT publish failures → `ERROR_MQTT_PUBLISH_FAILED`
- Connection timeouts → `ERROR_MQTT_CONNECT_FAILED`

**Service Layer:**
- Config validation failures → `ERROR_CONFIG_INVALID`
- NVS write failures → `ERROR_NVS_WRITE_FAILED`

### Circuit Breaker Integration

Circuit breakers protect critical services:

**WiFi Manager:**
- Prevents connection storms during network outages
- 10 failure threshold (tolerant for WiFi)
- 60s recovery timeout

**MQTT Client:**
- Protects broker from overload
- 5 failure threshold (stricter for MQTT)
- 30s recovery timeout
- Blocks publishes when OPEN (prevents buffer overflow)

### Emergency Stop Integration

Emergency stops are triggered from multiple sources:

**MQTT Commands:**
- ESP-specific: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency`
- Broadcast: `kaiser/broadcast/emergency`

**Safety Controller:**
- Runtime protection (max runtime exceeded)
- Manual trigger via API

**System Events:**
- Critical hardware errors
- Watchdog resets

### Safe-Mode Integration

Safe-mode is triggered at multiple points:

**Boot Sequence:**
- First operation in `setup()` → `initializeAllPinsToSafeMode()`
- Ensures hardware safety before any other operations

**Emergency Situations:**
- Critical errors → `enableSafeModeForAllPins()`
- Provisioning timeout → System enters `STATE_SAFE_MODE`

**GPIO Management:**
- Pin release → Returns to safe-mode (INPUT_PULLUP)
- Conflict resolution → Safe-mode for conflicting pins

## Error Recovery Scenarios

### Scenario 1: WiFi Disconnection

1. **Detection:** `WiFiManager::loop()` detects `WiFi.status() != WL_CONNECTED`
2. **Logging:** `ERROR_WIFI_DISCONNECT` tracked
3. **Reconnection:** `reconnect()` called with circuit breaker check
4. **Backoff:** 30s interval between attempts
5. **Circuit Breaker:** After 10 failures → 60s pause
6. **Recovery:** Successful connection → circuit breaker reset

### Scenario 2: MQTT Broker Unavailable

1. **Detection:** `MQTTClient::loop()` detects disconnection
2. **Buffering:** Messages added to offline buffer (max 100)
3. **Reconnection:** Exponential backoff (1s → 2s → 4s → ... → 60s)
4. **Circuit Breaker:** After 5 failures → 30s pause
5. **Recovery:** Connection restored → buffer processed → circuit breaker reset

### Scenario 3: Critical Hardware Error

1. **Detection:** Hardware error detected (e.g., I2C bus failure)
2. **Error Tracking:** `ERROR_I2C_BUS_ERROR` tracked with CRITICAL severity
3. **Safe-Mode:** `enableSafeModeForAllPins()` called
4. **Emergency Stop:** All actuators stopped via SafetyController
5. **Recovery:** Manual intervention required

### Scenario 4: Emergency Stop Command

1. **Reception:** MQTT emergency command received
2. **Routing:** Handled by MQTT message router
3. **Safety Controller:** `emergencyStopAll()` called
4. **Actuators:** All actuators stopped immediately
5. **State:** System enters `EMERGENCY_ACTIVE` state
6. **Recovery:** `clearEmergencyStop()` → `resumeOperation()`

## Best Practices

### Error Handling

1. **Always use ErrorTracker:** Track all errors with appropriate severity
2. **Use Convenience Methods:** `logHardwareError()`, `logCommunicationError()`, etc.
3. **Check Error Status:** Use `hasCriticalErrors()` before critical operations
4. **Clear Old Errors:** Periodically clear error history if needed

### Circuit Breaker Usage

1. **Check Before Operations:** Always call `allowRequest()` before service calls
2. **Record Results:** Always call `recordSuccess()` or `recordFailure()`
3. **Don't Bypass:** Never bypass circuit breaker (defeats purpose)
4. **Monitor State:** Log circuit breaker state changes for debugging

### Reconnection Logic

1. **Non-Blocking:** Reconnection attempts should not block main loop
2. **Exponential Backoff:** Use exponential backoff for reconnection delays
3. **Circuit Breaker:** Integrate circuit breaker to prevent storms
4. **Error Tracking:** Track reconnection failures for diagnostics

### Safe-Mode

1. **Boot First:** Always initialize safe-mode first in `setup()`
2. **Emergency Use:** Use `enableSafeModeForAllPins()` for emergencies
3. **Verify State:** Check `isPinInSafeMode()` before operations
4. **De-energize First:** Always de-energize outputs before mode change

## Next Flows

→ [Actuator Command Flow](03-actuator-command-flow.md) - Emergency stop integration  
→ [MQTT Message Routing](06-mqtt-message-routing-flow.md) - Emergency stop messages  
→ [Boot Sequence](01-boot-sequence.md) - Safe-mode initialization  

---

## Related Documentation

- `docs/MQTT_CLIENT_API.md` - MQTT client detailed API
- `docs/Mqtt_Protocoll.md` - God-Kaiser MQTT protocol specification
- `src/models/error_codes.h` - Complete error code definitions
- `src/models/actuator_types.h` - RecoveryConfig structure

---

**End of Error Recovery Flow Documentation**

