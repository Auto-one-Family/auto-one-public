#ifndef MODELS_ERROR_CODES_H
#define MODELS_ERROR_CODES_H

#include <Arduino.h>

// ============================================
// ERROR CODE RANGES (Guide-konform)
// ============================================
// HARDWARE:       1000-1999
// SERVICE:        2000-2999
// COMMUNICATION:  3000-3999
// APPLICATION:    4000-4999

// ============================================
// HARDWARE ERROR CODES (1000-1999)
// ============================================
#define ERROR_GPIO_RESERVED         1001
#define ERROR_GPIO_CONFLICT         1002
#define ERROR_GPIO_INIT_FAILED      1003
#define ERROR_GPIO_INVALID_MODE     1004
#define ERROR_GPIO_READ_FAILED      1005
#define ERROR_GPIO_WRITE_FAILED     1006

#define ERROR_I2C_INIT_FAILED       1010
#define ERROR_I2C_DEVICE_NOT_FOUND  1011
#define ERROR_I2C_READ_FAILED       1012
#define ERROR_I2C_WRITE_FAILED      1013
#define ERROR_I2C_BUS_ERROR         1014
// I2C Bus-Recovery (1015-1018)
#define ERROR_I2C_BUS_STUCK               1015  // SDA or SCL stuck low
#define ERROR_I2C_BUS_RECOVERY_STARTED    1016  // Recovery attempt initiated
#define ERROR_I2C_BUS_RECOVERY_FAILED     1017  // Recovery attempt failed
#define ERROR_I2C_BUS_RECOVERED           1018  // Recovery successful

// I2C Protocol-Layer Errors (1007-1009, 1019)
#define ERROR_I2C_TIMEOUT                 1007  // I2C operation timed out
#define ERROR_I2C_CRC_FAILED              1009  // CRC validation failed
#define ERROR_I2C_PROTOCOL_UNSUPPORTED    1019  // Sensor type not in protocol registry

#define ERROR_ONEWIRE_INIT_FAILED   1020
#define ERROR_ONEWIRE_NO_DEVICES    1021
#define ERROR_ONEWIRE_READ_FAILED   1022
#define ERROR_ONEWIRE_INVALID_ROM_LENGTH  1023  // ROM-Code not 16 hex chars
#define ERROR_ONEWIRE_INVALID_ROM_FORMAT  1024  // ROM-Code contains non-hex chars
#define ERROR_ONEWIRE_INVALID_ROM_CRC     1025  // ROM-Code CRC8 validation failed
#define ERROR_ONEWIRE_DEVICE_NOT_FOUND    1026  // Device not present on bus
#define ERROR_ONEWIRE_BUS_NOT_INITIALIZED 1027  // OneWire bus not initialized
#define ERROR_ONEWIRE_READ_TIMEOUT        1028  // Device read timeout
#define ERROR_ONEWIRE_DUPLICATE_ROM       1029  // ROM-Code already registered

#define ERROR_UART_INIT_FAILED            1033  // UART CO2 bus init failed
#define ERROR_UART_READ_TIMEOUT           1034  // UART CO2 read timeout
#define ERROR_UART_CHECKSUM_FAILED        1035  // UART CO2 frame checksum failed
#define ERROR_UART_INVALID_PPM            1036  // UART CO2 PPM out of range

#define ERROR_PWM_INIT_FAILED       1030
#define ERROR_PWM_CHANNEL_FULL      1031
#define ERROR_PWM_SET_FAILED        1032

#define ERROR_SENSOR_READ_FAILED    1040
#define ERROR_SENSOR_INIT_FAILED    1041
#define ERROR_SENSOR_NOT_FOUND      1042
#define ERROR_SENSOR_TIMEOUT        1043

#define ERROR_ACTUATOR_SET_FAILED   1050
#define ERROR_ACTUATOR_INIT_FAILED  1051
#define ERROR_ACTUATOR_NOT_FOUND    1052
#define ERROR_ACTUATOR_CONFLICT     1053

// DS18B20-specific Temperature Errors (1060-1069)
#define ERROR_DS18B20_SENSOR_FAULT        1060  // -127°C: Sensor disconnected or CRC failure
#define ERROR_DS18B20_POWER_ON_RESET      1061  // 85°C on first read: No conversion done
#define ERROR_DS18B20_OUT_OF_RANGE        1062  // Temperature outside valid range
#define ERROR_DS18B20_DISCONNECTED_RUNTIME 1063  // Device was present, now gone

// Subzone Management Errors (2500-2599) - SERVICE RANGE
#define ERROR_SUBZONE_INVALID_ID          2500  // Invalid subzone_id format
#define ERROR_SUBZONE_GPIO_CONFLICT       2501  // GPIO already assigned to different subzone
#define ERROR_SUBZONE_PARENT_MISMATCH     2502  // parent_zone_id doesn't match ESP zone
#define ERROR_SUBZONE_NOT_FOUND           2503  // Subzone doesn't exist
#define ERROR_SUBZONE_GPIO_INVALID        2504  // GPIO not in safe pins list
#define ERROR_SUBZONE_SAFE_MODE_FAILED    2505  // Safe-mode activation failed
#define ERROR_SUBZONE_CONFIG_SAVE_FAILED  2506  // Persistence failed

// ============================================
// SERVICE ERROR CODES (2000-2999)
// ============================================
#define ERROR_NVS_INIT_FAILED       2001
#define ERROR_NVS_READ_FAILED       2002
#define ERROR_NVS_WRITE_FAILED      2003
#define ERROR_NVS_NAMESPACE_FAILED  2004
#define ERROR_NVS_CLEAR_FAILED      2005

#define ERROR_CONFIG_INVALID        2010
#define ERROR_CONFIG_MISSING        2011
#define ERROR_CONFIG_LOAD_FAILED    2012
#define ERROR_CONFIG_SAVE_FAILED    2013
#define ERROR_CONFIG_VALIDATION     2014

#define ERROR_LOGGER_INIT_FAILED    2020
#define ERROR_LOGGER_BUFFER_FULL    2021

#define ERROR_STORAGE_INIT_FAILED   2030
#define ERROR_STORAGE_READ_FAILED   2031
#define ERROR_STORAGE_WRITE_FAILED  2032

// Package 09 - transactional persistence errors (AP-01A)
#define ERROR_TRANSACTION_OPEN_FAILED     2301
#define ERROR_NAMESPACE_CONFLICT          2302
#define ERROR_WRITE_WITHOUT_TRANSACTION   2303
#define ERROR_COMMIT_FAILED               2304
#define ERROR_ROLLBACK_FAILED             2305
#define ERROR_WRITE_TIMEOUT               2306

// ============================================
// COMMUNICATION ERROR CODES (3000-3999)
// ============================================
#define ERROR_WIFI_INIT_FAILED      3001
#define ERROR_WIFI_CONNECT_TIMEOUT  3002
#define ERROR_WIFI_CONNECT_FAILED   3003
#define ERROR_WIFI_DISCONNECT       3004
#define ERROR_WIFI_NO_SSID          3005

#define ERROR_MQTT_INIT_FAILED      3010
#define ERROR_MQTT_CONNECT_FAILED   3011
#define ERROR_MQTT_PUBLISH_FAILED   3012
#define ERROR_MQTT_SUBSCRIBE_FAILED 3013
#define ERROR_MQTT_DISCONNECT       3014
#define ERROR_MQTT_BUFFER_FULL      3015
#define ERROR_MQTT_PAYLOAD_INVALID  3016

#define ERROR_HTTP_INIT_FAILED      3020
#define ERROR_HTTP_REQUEST_FAILED   3021
#define ERROR_HTTP_RESPONSE_INVALID 3022
#define ERROR_HTTP_TIMEOUT          3023

#define ERROR_NETWORK_UNREACHABLE   3030
#define ERROR_DNS_FAILED            3031
#define ERROR_CONNECTION_LOST       3032

// AUT-62: Emergency fail-closed rejection (3500-3509)
#define ERROR_EMERGENCY_REJECTED_NO_TOKEN 3501

// ============================================
// APPLICATION ERROR CODES (4000-4999)
// ============================================
#define ERROR_STATE_INVALID         4001
#define ERROR_STATE_TRANSITION      4002
#define ERROR_STATE_MACHINE_STUCK   4003

#define ERROR_OPERATION_TIMEOUT     4010
#define ERROR_OPERATION_FAILED      4011
#define ERROR_OPERATION_CANCELLED   4012

#define ERROR_COMMAND_INVALID       4020
#define ERROR_COMMAND_PARSE_FAILED  4021
#define ERROR_COMMAND_EXEC_FAILED   4022

#define ERROR_PAYLOAD_INVALID       4030
#define ERROR_PAYLOAD_TOO_LARGE     4031
#define ERROR_PAYLOAD_PARSE_FAILED  4032
#define ERROR_CONTRACT_CORRELATION_MISSING 4033

#define ERROR_MEMORY_FULL           4040
#define ERROR_MEMORY_ALLOCATION     4041
#define ERROR_MEMORY_LEAK           4042

#define ERROR_SYSTEM_INIT_FAILED    4050
#define ERROR_SYSTEM_RESTART        4051
#define ERROR_SYSTEM_SAFE_MODE      4052

#define ERROR_TASK_FAILED           4060
#define ERROR_TASK_TIMEOUT          4061
#define ERROR_TASK_QUEUE_FULL       4062

// Watchdog Error Codes (Industrial-Grade) - Unique values to avoid conflicts
#define ERROR_WATCHDOG_TIMEOUT      4070  // Watchdog timeout detected
#define ERROR_WATCHDOG_FEED_BLOCKED 4071  // Watchdog feed blocked: Circuit breakers open
#define ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL 4072  // Watchdog feed blocked: Critical errors active

// Device Discovery & Approval (Phase 2) - 4200-4209
#define ERROR_DEVICE_REJECTED       4200  // Device rejected by server administrator
#define ERROR_APPROVAL_TIMEOUT      4201  // Timeout waiting for server approval
#define ERROR_APPROVAL_REVOKED      4202  // Previously approved device was revoked

// ============================================
// TEST INFRASTRUCTURE ERROR CODES (6000-6099)
// Only used in test reports, NOT in production
// ============================================
#define ERROR_TEST_WOKWI_TIMEOUT              6000  // Wokwi simulation timeout exceeded
#define ERROR_TEST_WOKWI_BOOT_INCOMPLETE      6001  // ESP32 boot in simulation incomplete
#define ERROR_TEST_MOCK_ESP_CONFIG_INVALID     6002  // Mock-ESP configuration invalid
#define ERROR_TEST_SCENARIO_ASSERTION_FAILED   6010  // Wokwi scenario assertion failed
#define ERROR_TEST_SCENARIO_NOT_FOUND          6011  // Referenced scenario does not exist
#define ERROR_TEST_MQTT_INJECTION_FAILED       6020  // MQTT inject in test failed
#define ERROR_TEST_MQTT_BROKER_UNAVAILABLE     6021  // Test MQTT broker not reachable
#define ERROR_TEST_DOCKER_SERVICE_UNHEALTHY    6030  // Docker service unhealthy during test
#define ERROR_TEST_DB_SEED_FAILED              6031  // Test data seeding failed
#define ERROR_TEST_PLAYWRIGHT_TIMEOUT          6040  // Frontend E2E test timeout
#define ERROR_TEST_PLAYWRIGHT_ELEMENT_NOT_FOUND 6041  // UI element not found in E2E test
#define ERROR_TEST_SERIAL_LOG_MISSING          6050  // Expected serial log pattern not found

// ============================================
// CONFIGURATION RESPONSE ERROR CODES (Enum)
// ============================================
enum class ConfigErrorCode : uint8_t {
  NONE = 0,
  JSON_PARSE_ERROR,
  VALIDATION_FAILED,
  GPIO_CONFLICT,
  NVS_WRITE_FAILED,
  TYPE_MISMATCH,
  MISSING_FIELD,
  OUT_OF_RANGE,
  PAYLOAD_TOO_LARGE,
  QUEUE_FULL,
  STALE_SCOPE,
  STALE_SENSOR_SCOPE,
  STALE_ACTUATOR_SCOPE,
  STALE_OFFLINE_SCOPE,
  WRITE_TIMEOUT,
  COMMIT_FAILED,
  REPLAY_QUEUE_FULL,
  OUTBOX_FULL,
  PERSISTENCE_DRIFT,
  CONTRACT_MISSING_CORRELATION,
  UNKNOWN_ERROR
};

inline const char* configErrorCodeToString(ConfigErrorCode code) {
  switch (code) {
    case ConfigErrorCode::NONE:
      return "NONE";
    case ConfigErrorCode::JSON_PARSE_ERROR:
      return "JSON_PARSE_ERROR";
    case ConfigErrorCode::VALIDATION_FAILED:
      return "VALIDATION_FAILED";
    case ConfigErrorCode::GPIO_CONFLICT:
      return "GPIO_CONFLICT";
    case ConfigErrorCode::NVS_WRITE_FAILED:
      return "NVS_WRITE_FAILED";
    case ConfigErrorCode::TYPE_MISMATCH:
      return "TYPE_MISMATCH";
    case ConfigErrorCode::MISSING_FIELD:
      return "MISSING_FIELD";
    case ConfigErrorCode::OUT_OF_RANGE:
      return "OUT_OF_RANGE";
    case ConfigErrorCode::PAYLOAD_TOO_LARGE:
      return "PAYLOAD_TOO_LARGE";
    case ConfigErrorCode::QUEUE_FULL:
      return "QUEUE_FULL";
    case ConfigErrorCode::STALE_SCOPE:
      return "STALE_SCOPE";
    case ConfigErrorCode::STALE_SENSOR_SCOPE:
      return "STALE_SENSOR_SCOPE";
    case ConfigErrorCode::STALE_ACTUATOR_SCOPE:
      return "STALE_ACTUATOR_SCOPE";
    case ConfigErrorCode::STALE_OFFLINE_SCOPE:
      return "STALE_OFFLINE_SCOPE";
    case ConfigErrorCode::WRITE_TIMEOUT:
      return "WRITE_TIMEOUT";
    case ConfigErrorCode::COMMIT_FAILED:
      return "COMMIT_FAILED";
    case ConfigErrorCode::REPLAY_QUEUE_FULL:
      return "REPLAY_QUEUE_FULL";
    case ConfigErrorCode::OUTBOX_FULL:
      return "OUTBOX_FULL";
    case ConfigErrorCode::PERSISTENCE_DRIFT:
      return "PERSISTENCE_DRIFT";
    case ConfigErrorCode::CONTRACT_MISSING_CORRELATION:
      return "CONTRACT_MISSING_CORRELATION";
    default:
      return "UNKNOWN_ERROR";
  }
}

inline ConfigErrorCode stringToConfigErrorCode(const String& code) {
  if (code == "NONE") {
    return ConfigErrorCode::NONE;
  }
  if (code == "JSON_PARSE_ERROR") {
    return ConfigErrorCode::JSON_PARSE_ERROR;
  }
  if (code == "VALIDATION_FAILED") {
    return ConfigErrorCode::VALIDATION_FAILED;
  }
  if (code == "GPIO_CONFLICT") {
    return ConfigErrorCode::GPIO_CONFLICT;
  }
  if (code == "NVS_WRITE_FAILED") {
    return ConfigErrorCode::NVS_WRITE_FAILED;
  }
  if (code == "TYPE_MISMATCH") {
    return ConfigErrorCode::TYPE_MISMATCH;
  }
  if (code == "MISSING_FIELD") {
    return ConfigErrorCode::MISSING_FIELD;
  }
  if (code == "OUT_OF_RANGE") {
    return ConfigErrorCode::OUT_OF_RANGE;
  }
  if (code == "PAYLOAD_TOO_LARGE") {
    return ConfigErrorCode::PAYLOAD_TOO_LARGE;
  }
  if (code == "QUEUE_FULL") {
    return ConfigErrorCode::QUEUE_FULL;
  }
  if (code == "STALE_SCOPE") {
    return ConfigErrorCode::STALE_SCOPE;
  }
  if (code == "STALE_SENSOR_SCOPE") {
    return ConfigErrorCode::STALE_SENSOR_SCOPE;
  }
  if (code == "STALE_ACTUATOR_SCOPE") {
    return ConfigErrorCode::STALE_ACTUATOR_SCOPE;
  }
  if (code == "STALE_OFFLINE_SCOPE") {
    return ConfigErrorCode::STALE_OFFLINE_SCOPE;
  }
  if (code == "WRITE_TIMEOUT") {
    return ConfigErrorCode::WRITE_TIMEOUT;
  }
  if (code == "COMMIT_FAILED") {
    return ConfigErrorCode::COMMIT_FAILED;
  }
  if (code == "REPLAY_QUEUE_FULL") {
    return ConfigErrorCode::REPLAY_QUEUE_FULL;
  }
  if (code == "OUTBOX_FULL") {
    return ConfigErrorCode::OUTBOX_FULL;
  }
  if (code == "PERSISTENCE_DRIFT") {
    return ConfigErrorCode::PERSISTENCE_DRIFT;
  }
  if (code == "CONTRACT_MISSING_CORRELATION") {
    return ConfigErrorCode::CONTRACT_MISSING_CORRELATION;
  }
  return ConfigErrorCode::UNKNOWN_ERROR;
}

// ============================================
// ERROR CODE DESCRIPTIONS (Human-Readable)
// ============================================
inline const char* getErrorDescription(uint16_t error_code) {
  switch (error_code) {
    // HARDWARE (1000-1999)
    case ERROR_GPIO_RESERVED: return "GPIO pin is reserved by system";
    case ERROR_GPIO_CONFLICT: return "GPIO pin already in use by another component";
    case ERROR_GPIO_INIT_FAILED: return "Failed to initialize GPIO pin";
    case ERROR_GPIO_INVALID_MODE: return "Invalid GPIO pin mode specified";
    case ERROR_GPIO_READ_FAILED: return "Failed to read GPIO pin value";
    case ERROR_GPIO_WRITE_FAILED: return "Failed to write GPIO pin value";

    case ERROR_I2C_INIT_FAILED: return "Failed to initialize I2C bus";
    case ERROR_I2C_DEVICE_NOT_FOUND: return "I2C device not found on bus";
    case ERROR_I2C_READ_FAILED: return "Failed to read from I2C device";
    case ERROR_I2C_WRITE_FAILED: return "Failed to write to I2C device";
    case ERROR_I2C_BUS_ERROR: return "I2C bus error (SDA/SCL stuck or timeout)";
    case ERROR_I2C_BUS_STUCK: return "I2C bus stuck (SDA or SCL held low by slave device)";
    case ERROR_I2C_BUS_RECOVERY_STARTED: return "I2C bus recovery initiated";
    case ERROR_I2C_BUS_RECOVERY_FAILED: return "I2C bus recovery failed after max attempts";
    case ERROR_I2C_BUS_RECOVERED: return "I2C bus recovered successfully";
    case ERROR_I2C_TIMEOUT: return "I2C operation timed out (sensor not responding)";
    case ERROR_I2C_CRC_FAILED: return "I2C sensor data CRC validation failed";
    case ERROR_I2C_PROTOCOL_UNSUPPORTED: return "I2C sensor type has no registered communication protocol";

    case ERROR_ONEWIRE_INIT_FAILED: return "Failed to initialize OneWire bus";
    case ERROR_ONEWIRE_NO_DEVICES: return "No OneWire devices found on bus";
    case ERROR_ONEWIRE_READ_FAILED: return "Failed to read from OneWire device";
    case ERROR_ONEWIRE_INVALID_ROM_LENGTH: return "OneWire ROM-Code must be 16 hex characters";
    case ERROR_ONEWIRE_INVALID_ROM_FORMAT: return "OneWire ROM-Code contains invalid characters (expected 0-9, A-F)";
    case ERROR_ONEWIRE_INVALID_ROM_CRC: return "OneWire ROM-Code CRC validation failed (corrupted or fake ROM)";
    case ERROR_ONEWIRE_DEVICE_NOT_FOUND: return "OneWire device not present on bus (check wiring)";
    case ERROR_ONEWIRE_BUS_NOT_INITIALIZED: return "OneWire bus not initialized (call begin() first)";
    case ERROR_ONEWIRE_READ_TIMEOUT: return "OneWire device read timeout (device not responding)";
    case ERROR_ONEWIRE_DUPLICATE_ROM: return "OneWire ROM-Code already registered for another sensor";

    case ERROR_UART_INIT_FAILED: return "Failed to initialize UART CO2 sensor";
    case ERROR_UART_READ_TIMEOUT: return "UART CO2 read timeout";
    case ERROR_UART_CHECKSUM_FAILED: return "UART CO2 frame checksum validation failed";
    case ERROR_UART_INVALID_PPM: return "UART CO2 PPM value out of valid range";

    case ERROR_PWM_INIT_FAILED: return "Failed to initialize PWM controller";
    case ERROR_PWM_CHANNEL_FULL: return "All PWM channels already in use";
    case ERROR_PWM_SET_FAILED: return "Failed to set PWM duty cycle";

    case ERROR_SENSOR_READ_FAILED: return "Failed to read sensor data";
    case ERROR_SENSOR_INIT_FAILED: return "Failed to initialize sensor";
    case ERROR_SENSOR_NOT_FOUND: return "Sensor not configured or not found";
    case ERROR_SENSOR_TIMEOUT: return "Sensor read timeout (device not responding)";

    case ERROR_ACTUATOR_SET_FAILED: return "Failed to set actuator state";
    case ERROR_ACTUATOR_INIT_FAILED: return "Failed to initialize actuator";
    case ERROR_ACTUATOR_NOT_FOUND: return "Actuator not configured or not found";
    case ERROR_ACTUATOR_CONFLICT: return "Actuator GPIO conflict with sensor";

    // DS18B20-specific Temperature Errors (1060-1069)
    case ERROR_DS18B20_SENSOR_FAULT: return "DS18B20 sensor fault: -127°C indicates disconnected sensor or CRC failure";
    case ERROR_DS18B20_POWER_ON_RESET: return "DS18B20 power-on reset: 85°C indicates no conversion was performed";
    case ERROR_DS18B20_OUT_OF_RANGE: return "DS18B20 temperature outside valid range (-55°C to +125°C)";
    case ERROR_DS18B20_DISCONNECTED_RUNTIME: return "DS18B20 device was present but is now disconnected";

    // Subzone Management Errors (2500-2599)
    case ERROR_SUBZONE_INVALID_ID: return "Invalid subzone_id format (must be 1-32 chars, alphanumeric + underscore)";
    case ERROR_SUBZONE_GPIO_CONFLICT: return "GPIO already assigned to different subzone";
    case ERROR_SUBZONE_PARENT_MISMATCH: return "parent_zone_id doesn't match ESP zone assignment";
    case ERROR_SUBZONE_NOT_FOUND: return "Subzone doesn't exist";
    case ERROR_SUBZONE_GPIO_INVALID: return "GPIO not in safe pins list";
    case ERROR_SUBZONE_SAFE_MODE_FAILED: return "Safe-mode activation failed for subzone";
    case ERROR_SUBZONE_CONFIG_SAVE_FAILED: return "Failed to save subzone configuration to NVS";

    // SERVICE (2000-2999)
    case ERROR_NVS_INIT_FAILED: return "Failed to initialize NVS (Non-Volatile Storage)";
    case ERROR_NVS_READ_FAILED: return "Failed to read from NVS";
    case ERROR_NVS_WRITE_FAILED: return "Failed to write to NVS (storage full or corrupted)";
    case ERROR_NVS_NAMESPACE_FAILED: return "Failed to open NVS namespace";
    case ERROR_NVS_CLEAR_FAILED: return "Failed to clear NVS namespace";

    case ERROR_CONFIG_INVALID: return "Configuration data is invalid";
    case ERROR_CONFIG_MISSING: return "Required configuration is missing";
    case ERROR_CONFIG_LOAD_FAILED: return "Failed to load configuration from NVS";
    case ERROR_CONFIG_SAVE_FAILED: return "Failed to save configuration to NVS";
    case ERROR_CONFIG_VALIDATION: return "Configuration validation failed";

    case ERROR_LOGGER_INIT_FAILED: return "Failed to initialize logger system";
    case ERROR_LOGGER_BUFFER_FULL: return "Logger buffer is full (messages dropped)";

    case ERROR_STORAGE_INIT_FAILED: return "Failed to initialize storage manager";
    case ERROR_STORAGE_READ_FAILED: return "Failed to read from storage";
    case ERROR_STORAGE_WRITE_FAILED: return "Failed to write to storage";
    case ERROR_TRANSACTION_OPEN_FAILED: return "Failed to open persistence transaction";
    case ERROR_NAMESPACE_CONFLICT: return "Persistence namespace conflict detected";
    case ERROR_WRITE_WITHOUT_TRANSACTION: return "Write attempted without active transaction";
    case ERROR_COMMIT_FAILED: return "Persistence transaction commit failed";
    case ERROR_ROLLBACK_FAILED: return "Persistence transaction rollback failed";
    case ERROR_WRITE_TIMEOUT: return "Persistence write timed out";

    // COMMUNICATION (3000-3999)
    case ERROR_WIFI_INIT_FAILED: return "Failed to initialize WiFi module";
    case ERROR_WIFI_CONNECT_TIMEOUT: return "WiFi connection timeout";
    case ERROR_WIFI_CONNECT_FAILED: return "WiFi connection failed (wrong password or SSID not found)";
    case ERROR_WIFI_DISCONNECT: return "WiFi disconnected unexpectedly";
    case ERROR_WIFI_NO_SSID: return "WiFi SSID not configured";

    case ERROR_MQTT_INIT_FAILED: return "Failed to initialize MQTT client";
    case ERROR_MQTT_CONNECT_FAILED: return "MQTT broker connection failed";
    case ERROR_MQTT_PUBLISH_FAILED: return "Failed to publish MQTT message";
    case ERROR_MQTT_SUBSCRIBE_FAILED: return "Failed to subscribe to MQTT topic";
    case ERROR_MQTT_DISCONNECT: return "MQTT disconnected from broker";
    case ERROR_MQTT_BUFFER_FULL: return "MQTT offline buffer is full (messages dropped)";
    case ERROR_MQTT_PAYLOAD_INVALID: return "MQTT payload is invalid or malformed";

    case ERROR_HTTP_INIT_FAILED: return "Failed to initialize HTTP client";
    case ERROR_HTTP_REQUEST_FAILED: return "HTTP request failed (server unreachable)";
    case ERROR_HTTP_RESPONSE_INVALID: return "HTTP response is invalid or malformed";
    case ERROR_HTTP_TIMEOUT: return "HTTP request timeout";

    case ERROR_NETWORK_UNREACHABLE: return "Network is unreachable";
    case ERROR_DNS_FAILED: return "DNS lookup failed (hostname not resolved)";
    case ERROR_CONNECTION_LOST: return "Network connection lost";
    case ERROR_EMERGENCY_REJECTED_NO_TOKEN: return "Emergency rejected: no token configured (fail-closed prod mode)";

    // APPLICATION (4000-4999)
    case ERROR_STATE_INVALID: return "Invalid system state";
    case ERROR_STATE_TRANSITION: return "Invalid state transition";
    case ERROR_STATE_MACHINE_STUCK: return "State machine is stuck (no valid transitions)";

    case ERROR_OPERATION_TIMEOUT: return "Operation timeout";
    case ERROR_OPERATION_FAILED: return "Operation failed";
    case ERROR_OPERATION_CANCELLED: return "Operation cancelled by user or system";

    case ERROR_COMMAND_INVALID: return "Command is invalid or unknown";
    case ERROR_COMMAND_PARSE_FAILED: return "Failed to parse command";
    case ERROR_COMMAND_EXEC_FAILED: return "Command execution failed";

    case ERROR_PAYLOAD_INVALID: return "Payload is invalid or malformed";
    case ERROR_PAYLOAD_TOO_LARGE: return "Payload size exceeds maximum allowed";
    case ERROR_PAYLOAD_PARSE_FAILED: return "Failed to parse payload (JSON syntax error)";
    case ERROR_CONTRACT_CORRELATION_MISSING: return "Contract violation: required correlation_id missing";

    case ERROR_MEMORY_FULL: return "Memory is full (heap exhausted)";
    case ERROR_MEMORY_ALLOCATION: return "Failed to allocate memory";
    case ERROR_MEMORY_LEAK: return "Memory leak detected";

    case ERROR_SYSTEM_INIT_FAILED: return "System initialization failed";
    case ERROR_SYSTEM_RESTART: return "System restart requested";
    case ERROR_SYSTEM_SAFE_MODE: return "System entered safe mode (errors detected)";

    case ERROR_TASK_FAILED: return "FreeRTOS task failed";
    case ERROR_TASK_TIMEOUT: return "FreeRTOS task timeout";
    case ERROR_TASK_QUEUE_FULL: return "FreeRTOS task queue is full";

    case ERROR_WATCHDOG_TIMEOUT: return "Watchdog timeout detected (system hang)";
    case ERROR_WATCHDOG_FEED_BLOCKED: return "Watchdog feed blocked: Circuit breakers open";
    case ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL: return "Watchdog feed blocked: Critical errors active";

    // Device Discovery & Approval (Phase 2)
    case ERROR_DEVICE_REJECTED: return "Device rejected by server administrator";
    case ERROR_APPROVAL_TIMEOUT: return "Timeout waiting for server approval";
    case ERROR_APPROVAL_REVOKED: return "Previously approved device was revoked";

    // TEST INFRASTRUCTURE (6000-6099)
    case ERROR_TEST_WOKWI_TIMEOUT: return "Wokwi simulation timeout exceeded";
    case ERROR_TEST_WOKWI_BOOT_INCOMPLETE: return "ESP32 boot in simulation incomplete";
    case ERROR_TEST_MOCK_ESP_CONFIG_INVALID: return "Mock-ESP configuration invalid";
    case ERROR_TEST_SCENARIO_ASSERTION_FAILED: return "Wokwi scenario assertion failed";
    case ERROR_TEST_SCENARIO_NOT_FOUND: return "Referenced scenario does not exist";
    case ERROR_TEST_MQTT_INJECTION_FAILED: return "MQTT inject in test failed";
    case ERROR_TEST_MQTT_BROKER_UNAVAILABLE: return "Test MQTT broker not reachable";
    case ERROR_TEST_DOCKER_SERVICE_UNHEALTHY: return "Docker service unhealthy during test";
    case ERROR_TEST_DB_SEED_FAILED: return "Test data seeding failed";
    case ERROR_TEST_PLAYWRIGHT_TIMEOUT: return "Frontend E2E test (Playwright) timeout";
    case ERROR_TEST_PLAYWRIGHT_ELEMENT_NOT_FOUND: return "UI element not found in E2E test";
    case ERROR_TEST_SERIAL_LOG_MISSING: return "Expected serial log pattern not found";

    default: return "Unknown error code";
  }
}

// Helper: Get error code range name
inline const char* getErrorCodeRange(uint16_t error_code) {
  if (error_code >= 1000 && error_code < 2000) return "HARDWARE";
  if (error_code >= 2000 && error_code < 3000) return "SERVICE";
  if (error_code >= 3000 && error_code < 4000) return "COMMUNICATION";
  if (error_code >= 4000 && error_code < 5000) return "APPLICATION";
  if (error_code >= 6000 && error_code < 6100) return "TEST";
  return "UNKNOWN";
}

#endif
