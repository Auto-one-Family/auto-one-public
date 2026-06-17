#ifndef MODELS_CONFIG_TYPES_H
#define MODELS_CONFIG_TYPES_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>

/**
 * @brief Status values for configuration responses.
 * Phase 4: Added PARTIAL_SUCCESS for mixed success/failure scenarios.
 */
enum class ConfigStatus : uint8_t {
  SUCCESS = 0,
  PARTIAL_SUCCESS = 1,  // Phase 4: Some items succeeded, some failed
  ERROR = 2
};

/**
 * @brief Structure for tracking individual configuration failures (Phase 4).
 * Used to provide detailed error information back to the server.
 * Max 10 failures are stored to prevent memory issues.
 */
struct ConfigFailureItem {
  const char* type;          // "sensor" or "actuator"
  uint8_t gpio;              // GPIO pin number
  uint16_t error_code;       // Error code from error_codes.h
  const char* error_name;    // Short name: "GPIO_CONFLICT"
  String detail;             // Human-readable details

  ConfigFailureItem()
      : type("unknown"), gpio(0), error_code(0), error_name("UNKNOWN"), detail("") {}

  ConfigFailureItem(const char* t, uint8_t g, uint16_t ec, const char* en, const String& d)
      : type(t), gpio(g), error_code(ec), error_name(en), detail(d) {}
};

// Maximum number of failures to track (prevents memory issues)
constexpr uint8_t MAX_CONFIG_FAILURES = 10;

/**
 * @brief Configuration types that can emit responses.
 */
enum class ConfigType : uint8_t {
  SENSOR = 0,
  ACTUATOR,
  WIFI,
  ZONE,
  SYSTEM,
  UNKNOWN
};

/**
 * @brief Unified MQTT payload for configuration responses.
 *
 * Matches the structure documented in docs/MQTT_CLIENT_API.md.
 */
struct ConfigResponsePayload {
  ConfigStatus status;
  ConfigType type;
  uint8_t count;
  String message;
  String error_code;
  DynamicJsonDocument failed_item;
  String correlation_id;  // Phase 3: Event correlation tracking

  ConfigResponsePayload()
      : status(ConfigStatus::SUCCESS),
        type(ConfigType::UNKNOWN),
        count(0),
        message(""),
        error_code(""),
        failed_item(256),
        correlation_id("") {}

  bool hasFailedItem() const {
    return !failed_item.isNull() && failed_item.size() > 0;
  }
};

inline const char* configStatusToString(ConfigStatus status) {
  switch (status) {
    case ConfigStatus::SUCCESS:
      return "success";
    case ConfigStatus::PARTIAL_SUCCESS:
      return "partial_success";
    case ConfigStatus::ERROR:
    default:
      return "error";
  }
}

inline const char* configTypeToString(ConfigType type) {
  switch (type) {
    case ConfigType::SENSOR:
      return "sensor";
    case ConfigType::ACTUATOR:
      return "actuator";
    case ConfigType::WIFI:
      return "wifi";
    case ConfigType::ZONE:
      return "zone";
    case ConfigType::SYSTEM:
      return "system";
    default:
      return "unknown";
  }
}

#endif  // MODELS_CONFIG_TYPES_H

