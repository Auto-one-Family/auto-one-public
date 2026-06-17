#ifndef MODELS_ACTUATOR_TYPES_H
#define MODELS_ACTUATOR_TYPES_H

#include <Arduino.h>

// ============================================
// ENUMS & CONSTANTS
// ============================================

enum class EmergencyState : uint8_t {
  EMERGENCY_NORMAL = 0,
  EMERGENCY_ACTIVE,
  EMERGENCY_CLEARING,
  EMERGENCY_RESUMING
};

// String tokens used by MQTT payloads (kept centralized for reuse)
namespace ActuatorTypeTokens {
  static const char* const PUMP = "pump";
  static const char* const VALVE = "valve";
  static const char* const PWM = "pwm";
  static const char* const RELAY = "relay";
}

// ============================================
// CORE DATA STRUCTURES
// ============================================

// ============================================
// PHASE 2: RUNTIME PROTECTION (Robustness)
// ============================================
struct RuntimeProtection {
  unsigned long max_runtime_ms = 3600000UL;  // 1h default (prevents continuous operation)
  bool timeout_enabled = true;               // Enable/disable timeout protection
  unsigned long activation_start_ms = 0;     // Timestamp when actuator was activated
};

struct ActuatorConfig {
  uint8_t gpio = 255;              // Primary hardware binding
  uint8_t aux_gpio = 255;          // Optional secondary pin (valves, H-bridges)
  String actuator_type = "";       // "pump", "valve", "pwm", "relay"
  String actuator_name = "";       // Human-readable label
  String subzone_id = "";          // Subzone assignment (optional, sensor/actuator level)
  bool active = false;             // Enabled flag
  bool critical = false;           // Safety priority (e.g. irrigation pump)

  // Runtime & driver specific metadata
  uint8_t pwm_channel = 255;       // Assigned PWM channel (for PWM/dimmer)
  bool inverted_logic = false;     // LOW = ON for some relays
  uint8_t default_pwm = 0;         // Desired PWM fallback (0-255)
  bool default_state = false;      // Failsafe state if config lost

  // AUT-66: Per-actuator fail-safe policy on MQTT disconnect.
  // When has_fail_safe_override=false, policy is derived from critical flag.
  bool fail_safe_on_disconnect = true;   // default: safe-off
  bool has_fail_safe_override  = false;  // false = no server override, derive from critical

  // Live state tracking (kept in RAM only, not persisted in Phase 5)
  bool current_state = false;      // Digital ON/OFF
  uint8_t current_pwm = 0;         // PWM duty
  unsigned long last_command_ts = 0;
  unsigned long accumulated_runtime_ms = 0; // For pumps/duty-cycle analysis

  // Phase 2: Runtime protection (timeout protection)
  RuntimeProtection runtime_protection;
};

struct ActuatorCommand {
  uint8_t gpio = 255;
  String command = "";        // "ON","OFF","PWM","TOGGLE","STOP"
  float value = 0.0f;         // 0.0 - 1.0 (PWM) or binary (>=0.5)
  uint32_t duration_s = 0;    // Optional hold duration
  unsigned long timestamp = 0;
  String correlation_id = ""; // End-to-end command tracking (UUID from server)
  String issued_by = "";      // Source context (e.g. user:robin, logic_engine)
};

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

struct ActuatorResponse {
  unsigned long timestamp = 0;
  String esp_id = "";
  uint8_t gpio = 255;
  String command = "";
  float value = 0.0f;
  bool success = false;
  String message = "";
  uint32_t duration_s = 0;
  EmergencyState emergency_state = EmergencyState::EMERGENCY_NORMAL;
};

struct ActuatorAlert {
  unsigned long timestamp = 0;
  uint8_t gpio = 255;
  String alert_type = "";   // e.g. "runtime_protection", "overcurrent"
  String message = "";
  String actuator_type = "";
};

struct RecoveryConfig {
  uint32_t inter_actuator_delay_ms = 2000;
  bool critical_first = true;
  uint32_t verification_timeout_ms = 5000;
  uint8_t max_retry_attempts = 3;
};

// ============================================
// UTILITY HELPERS
// ============================================

inline bool isBinaryActuatorType(const String& type) {
  return type == ActuatorTypeTokens::PUMP ||
         type == ActuatorTypeTokens::VALVE ||
         type == ActuatorTypeTokens::RELAY;
}

inline bool isPwmActuatorType(const String& type) {
  return type == ActuatorTypeTokens::PWM;
}

inline bool validateActuatorValue(const String& type, float value) {
  if (isPwmActuatorType(type)) {
    return value >= 0.0f && value <= 1.0f;
  }
  // Binary actuators treat >=0.5 as ON
  return value == 0.0f || value == 1.0f || (value >= 0.0f && value <= 1.0f);
}

inline const char* emergencyStateToString(EmergencyState state) {
  switch (state) {
    case EmergencyState::EMERGENCY_ACTIVE: return "active";
    case EmergencyState::EMERGENCY_CLEARING: return "clearing";
    case EmergencyState::EMERGENCY_RESUMING: return "resuming";
    case EmergencyState::EMERGENCY_NORMAL:
    default:
      return "normal";
  }
}

inline EmergencyState emergencyStateFromString(const String& state) {
  if (state == "active") return EmergencyState::EMERGENCY_ACTIVE;
  if (state == "clearing") return EmergencyState::EMERGENCY_CLEARING;
  if (state == "resuming") return EmergencyState::EMERGENCY_RESUMING;
  return EmergencyState::EMERGENCY_NORMAL;
}

#endif  // MODELS_ACTUATOR_TYPES_H

