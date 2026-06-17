#include "actuator_manager.h"

#include <memory>

#include "../../tasks/rtos_globals.h"  // SAFETY-RTOS M4: g_actuator_mutex
#include "../../tasks/publish_queue.h"
#include "../../tasks/publish_queue_policy.h"
#include "../../drivers/gpio_manager.h"
#include "../../error_handling/error_tracker.h"
#include "../../models/config_types.h"
#include "../../models/error_codes.h"
#include "../../services/communication/mqtt_client.h"
#include "../../services/config/config_manager.h"
#include "../../services/config/config_response.h"
#include "../../services/safety/offline_mode_manager.h"
#include "../../services/sensor/sensor_manager.h"
#include "../../utils/json_helpers.h"
#include "../../utils/logger.h"
#include "../../utils/topic_builder.h"
#include "../../utils/time_manager.h"
#include "actuator_drivers/pump_actuator.h"
#include "actuator_drivers/pwm_actuator.h"
#include "actuator_drivers/valve_actuator.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "ACTUATOR";

ActuatorManager& actuatorManager = ActuatorManager::getInstance();

namespace {

String extractJSONString(const String& json, const String& key) {
  String pattern = "\"" + key + "\":";
  int key_pos = json.indexOf(pattern);
  if (key_pos == -1) {
    return "";
  }
  key_pos += pattern.length();

  // Skip optional quotes or whitespace
  while (key_pos < json.length() && (json[key_pos] == ' ' || json[key_pos] == '\"')) {
    if (json[key_pos] == '\"') {
      key_pos++;
      int end_quote = json.indexOf('\"', key_pos);
      if (end_quote == -1) {
        return "";
      }
      return json.substring(key_pos, end_quote);
    }
    key_pos++;
  }

  int value_end = json.indexOf(',', key_pos);
  if (value_end == -1) {
    value_end = json.indexOf('}', key_pos);
  }
  if (value_end == -1) {
    value_end = json.length();
  }

  String value = json.substring(key_pos, value_end);
  value.trim();
  value.replace("\"", "");
  return value;
}

float extractJSONFloat(const String& json, const String& key, float default_value = 0.0f) {
  String value = extractJSONString(json, key);
  return value.length() ? value.toFloat() : default_value;
}

uint32_t extractJSONUInt32(const String& json, const String& key, uint32_t default_value = 0) {
  String value = extractJSONString(json, key);
  return value.length() ? static_cast<uint32_t>(value.toInt()) : default_value;
}

bool extractJSONBool(const String& json, const String& key, bool default_value = false) {
  String value = extractJSONString(json, key);
  value.toLowerCase();
  if (value == "true" || value == "1") {
    return true;
  }
  if (value == "false" || value == "0") {
    return false;
  }
  return default_value;
}

}  // namespace

void ActuatorManager::preserveSoftPolicyFromRegistered(ActuatorConfig& merged,
                                                       const ActuatorConfig& policy) {
  merged.fail_safe_on_disconnect = policy.fail_safe_on_disconnect;
  merged.has_fail_safe_override  = policy.has_fail_safe_override;
  merged.critical                = policy.critical;
  merged.actuator_name           = policy.actuator_name;
  merged.subzone_id              = policy.subzone_id;
  merged.inverted_logic          = policy.inverted_logic;
  merged.default_state           = policy.default_state;
  merged.default_pwm             = policy.default_pwm;
  merged.runtime_protection.max_runtime_ms = policy.runtime_protection.max_runtime_ms;
  merged.runtime_protection.timeout_enabled = policy.runtime_protection.timeout_enabled;
}

void ActuatorManager::syncRegisteredConfigFromDriver(RegisteredActuator& slot) {
  if (!slot.driver) {
    return;
  }
  const ActuatorConfig policy = slot.config;
  slot.config = slot.driver->getConfig();
  preserveSoftPolicyFromRegistered(slot.config, policy);
}

void ActuatorManager::syncDriverSoftPolicyFromRegistered(RegisteredActuator& slot) {
  if (!slot.driver) {
    return;
  }
  if (slot.config.actuator_type == String(ActuatorTypeTokens::PUMP) ||
      slot.config.actuator_type == String(ActuatorTypeTokens::RELAY)) {
    static_cast<PumpActuator*>(slot.driver.get())
        ->syncRuntimeLimitsFromConfig(slot.config);
  }
}

ActuatorManager& ActuatorManager::getInstance() {
  static ActuatorManager instance;
  return instance;
}

ActuatorManager::ActuatorManager()
    : actuator_count_(0),
      initialized_(false),
      gpio_manager_(&GPIOManager::getInstance()) {}

bool ActuatorManager::begin() {
  if (initialized_) {
    LOG_W(TAG, "ActuatorManager already initialized");
    return true;
  }

  actuator_count_ = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    actuators_[i] = RegisteredActuator();
  }

  initialized_ = true;
  LOG_I(TAG, "ActuatorManager initialized");
  return true;
}

void ActuatorManager::end() {
  if (!initialized_) {
    return;
  }

  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use && actuators_[i].driver) {
      actuators_[i].driver->end();
      actuators_[i].driver.reset();
    }
    actuators_[i].in_use = false;
  }

  actuator_count_ = 0;
  initialized_ = false;
  LOG_I(TAG, "ActuatorManager shutdown complete");
}

ActuatorManager::RegisteredActuator* ActuatorManager::getFreeSlot() {
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (!actuators_[i].in_use) {
      return &actuators_[i];
    }
  }
  return nullptr;
}

ActuatorManager::RegisteredActuator* ActuatorManager::findActuator(uint8_t gpio) {
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use && actuators_[i].gpio == gpio) {
      return &actuators_[i];
    }
  }
  return nullptr;
}

const ActuatorManager::RegisteredActuator* ActuatorManager::findActuator(uint8_t gpio) const {
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use && actuators_[i].gpio == gpio) {
      return &actuators_[i];
    }
  }
  return nullptr;
}

bool ActuatorManager::validateActuatorConfig(const ActuatorConfig& config) const {
  if (config.gpio == 255) {
    LOG_E(TAG, "Actuator config missing GPIO");
    return false;
  }
  // AUT-677: GPIO 0 is not a valid actuator GPIO (defense-in-depth for config path).
  if (config.gpio == 0) {
    LOG_E(TAG, "Actuator config invalid GPIO (0 is not a valid actuator GPIO)");
    return false;
  }
  if (config.actuator_type.length() == 0) {
    LOG_E(TAG, "Actuator config missing type");
    return false;
  }
  return true;
}

std::unique_ptr<IActuatorDriver> ActuatorManager::createDriver(const String& actuator_type) const {
  if (actuator_type == ActuatorTypeTokens::PUMP) {
    return std::unique_ptr<IActuatorDriver>(new PumpActuator());
  }
  if (actuator_type == ActuatorTypeTokens::PWM) {
    return std::unique_ptr<IActuatorDriver>(new PWMActuator());
  }
  if (actuator_type == ActuatorTypeTokens::VALVE) {
    return std::unique_ptr<IActuatorDriver>(new ValveActuator());
  }
  if (actuator_type == ActuatorTypeTokens::RELAY) {
    return std::unique_ptr<IActuatorDriver>(new PumpActuator());  // Relay handled like pump (binary)
  }
  LOG_E(TAG, "Unknown actuator type: " + actuator_type);
  return nullptr;
}

bool ActuatorManager::configureActuator(const ActuatorConfig& incoming_config) {
  if (!initialized_ && !begin()) {
    return false;
  }
  // SAFETY-RTOS M4: protect actuators_[] against publishAllActuatorStatus (Core 0).
  // begin() runs in setup() before tasks start — acquired after init guard to avoid
  // recursive acquisition if begin() ever calls configureActuator internally.
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);

  ActuatorConfig config = incoming_config;
  if (!validateActuatorConfig(config)) {
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  // Phase 7: Handle deactivation/removal
  if (!config.active) {
    LOG_I(TAG, "Actuator config deactivating GPIO " + String(config.gpio));
    removeActuator(config.gpio);
    xSemaphoreGive(g_actuator_mutex);
    return true;
  }

  // Server-Centric Deviation (Hardware-Protection-Layer):
  // GPIO-Conflict-Check als Defense-in-Depth gegen fehlerhafte Server-Configs.
  // Server sollte primär GPIO-Allokation verwalten, dies ist nur Fallback.
  // Dokumentiert in: docs/ZZZ.md - "Server-Centric Pragmatic Deviations"
  if (sensorManager.hasSensorOnGPIO(config.gpio)) {
    LOG_E(TAG, "GPIO " + String(config.gpio) + " already used by sensor");
    errorTracker.trackError(ERROR_GPIO_CONFLICT,
                            ERROR_SEVERITY_ERROR,
                            "GPIO conflict sensor vs actuator");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  // R20-P11: Skip-unchanged + soft-update optimization
  // Avoids GPIO glitches, NVS wear and log spam on repeated config pushes.
  bool is_reconfiguration = false;
  RegisteredActuator* existing = findActuator(config.gpio);
  if (existing) {
    is_reconfiguration = true;
    const ActuatorConfig& prev = existing->config;

    // Structural fields: require full remove + re-create (driver type, secondary pin)
    bool structural_changed = (prev.actuator_type != config.actuator_type) ||
                              (prev.aux_gpio      != config.aux_gpio);

    // Soft fields: can be applied in-place without touching GPIO or driver
    bool soft_changed = (prev.actuator_name   != config.actuator_name)   ||
                        (prev.subzone_id       != config.subzone_id)       ||
                        (prev.critical         != config.critical)         ||
                        (prev.inverted_logic   != config.inverted_logic)   ||
                        (prev.default_state    != config.default_state)    ||
                        (prev.default_pwm      != config.default_pwm)        ||
                        (prev.fail_safe_on_disconnect != config.fail_safe_on_disconnect) ||
                        (prev.has_fail_safe_override  != config.has_fail_safe_override)  ||
                        (prev.runtime_protection.max_runtime_ms !=
                            config.runtime_protection.max_runtime_ms)      ||
                        (prev.runtime_protection.timeout_enabled !=
                            config.runtime_protection.timeout_enabled);

    if (!structural_changed && !soft_changed) {
      // Fully identical config — nothing to do
      LOG_I(TAG, "Actuator Manager: GPIO " + String(config.gpio) +
                 " config unchanged, skipping");
      xSemaphoreGive(g_actuator_mutex);
      return true;
    }

    if (!structural_changed) {
      // Soft-only change: update fields in-place, persist NVS once, no GPIO touch
      LOG_I(TAG, "Actuator Manager: Soft update on GPIO " + String(config.gpio));
      existing->config.actuator_name  = config.actuator_name;
      existing->config.subzone_id      = config.subzone_id;
      existing->config.critical        = config.critical;
      existing->config.inverted_logic  = config.inverted_logic;
      existing->config.default_state   = config.default_state;
      existing->config.default_pwm     = config.default_pwm;
      existing->config.fail_safe_on_disconnect = config.fail_safe_on_disconnect;
      existing->config.has_fail_safe_override  = config.has_fail_safe_override;
      {
        unsigned long keep_activation = existing->config.runtime_protection.activation_start_ms;
        existing->config.runtime_protection.max_runtime_ms   =
            config.runtime_protection.max_runtime_ms;
        existing->config.runtime_protection.timeout_enabled  =
            config.runtime_protection.timeout_enabled;
        existing->config.runtime_protection.activation_start_ms = keep_activation;
      }
      syncDriverSoftPolicyFromRegistered(*existing);

      ActuatorConfig actuators[MAX_ACTUATORS];
      uint8_t count = 0;
      for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
        if (actuators_[i].in_use) {
          actuators[count++] = actuators_[i].config;
        }
      }
      if (!configManager.saveActuatorConfig(actuators, count)) {
        LOG_E(TAG, "Actuator Manager: Failed to persist soft update to NVS");
      } else {
        LOG_I(TAG, "  Soft update persisted to NVS");
      }
      publishActuatorStatus(config.gpio);
      xSemaphoreGive(g_actuator_mutex);
      return true;
    }

    // Structural change: full remove + re-create required
    LOG_I(TAG, "Actuator Manager: Structural reconfiguration on GPIO " + String(config.gpio));
    LOG_I(TAG, "  Type: " + prev.actuator_type + " -> " + config.actuator_type);
    // Emergency stop before tearing down the driver
    if (existing->driver) {
      existing->driver->setBinary(false);
    }
    removeActuator(config.gpio);
  }

  RegisteredActuator* slot = getFreeSlot();
  if (!slot) {
    LOG_E(TAG, "No actuator slots available");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "Actuator slots exhausted");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  auto driver = createDriver(config.actuator_type);
  if (!driver) {
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  if (!driver->begin(config)) {
    LOG_E(TAG, "Driver initialization failed for GPIO " + String(config.gpio));
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "Driver init failed");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  slot->driver = std::move(driver);
  slot->config = slot->driver->getConfig();
  slot->gpio = config.gpio;
  slot->in_use = true;
  slot->emergency_stopped = false;

  // Always increment: removeActuator() already decremented for reconfiguration,
  // and new actuators need the increment too
  actuator_count_++;

  // Phase 7: Persist to NVS immediately (save all actuators)
  ActuatorConfig actuators[MAX_ACTUATORS];
  uint8_t count = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use) {
      actuators[count++] = actuators_[i].config;
    }
  }
  if (!configManager.saveActuatorConfig(actuators, count)) {
    LOG_E(TAG, "Actuator Manager: Failed to persist config to NVS");
  } else {
    LOG_I(TAG, "  Configuration persisted to NVS");
  }

  LOG_I(TAG, "Actuator " + String(is_reconfiguration ? "reconfigured" : "configured") +
           " on GPIO " + String(config.gpio) + " type: " + config.actuator_type);
  publishActuatorStatus(config.gpio);
  xSemaphoreGive(g_actuator_mutex);
  return true;
}

bool ActuatorManager::removeActuator(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator) {
    return false;
  }

  LOG_I(TAG, "Actuator Manager: Removing actuator on GPIO " + String(gpio));
  
  // Phase 7: Safety - stop actuator before removal
  if (actuator->driver) {
    LOG_I(TAG, "  Stopping actuator before removal");
    actuator->driver->setBinary(false);
    actuator->driver->end();
    actuator->driver.reset();
  }

  actuator->in_use = false;
  actuator->gpio = 255;
  actuator->config = ActuatorConfig();
  actuator->emergency_stopped = false;
  actuator_count_ = actuator_count_ > 0 ? actuator_count_ - 1 : 0;
  
  // Phase 7: Persist removal to NVS immediately (save remaining actuators)
  ActuatorConfig actuators[MAX_ACTUATORS];
  uint8_t count = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use) {
      actuators[count++] = actuators_[i].config;
    }
  }
  if (!configManager.saveActuatorConfig(actuators, count)) {
    LOG_E(TAG, "Actuator Manager: Failed to persist config to NVS");
  } else {
    LOG_I(TAG, "  ✅ Configuration persisted to NVS");
  }
  
  LOG_I(TAG, "Actuator removed from GPIO " + String(gpio));
  return true;
}

bool ActuatorManager::hasActuatorOnGPIO(uint8_t gpio) const {
  return findActuator(gpio) != nullptr;
}

ActuatorConfig ActuatorManager::getActuatorConfig(uint8_t gpio) const {
  const RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator) {
    return ActuatorConfig();
  }
  return actuator->config;
}

uint8_t ActuatorManager::countActuatorsWithSubzone(const String& subzone_id) const {
  if (subzone_id.length() == 0) {
    return 0;
  }
  uint8_t n = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    const RegisteredActuator& a = actuators_[i];
    if (a.in_use && a.config.subzone_id == subzone_id) {
      n++;
    }
  }
  return n;
}

bool ActuatorManager::controlActuator(uint8_t gpio, float value) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    LOG_E(TAG, "controlActuator: actuator not found on GPIO " + String(gpio));
    errorTracker.trackError(ERROR_ACTUATOR_NOT_FOUND,
                            ERROR_SEVERITY_ERROR,
                            "Actuator missing");
    return false;
  }

  if (actuator->emergency_stopped) {
    LOG_W(TAG, "Actuator GPIO " + String(gpio) + " is emergency stopped");
    return false;
  }

  float normalized_value = value;
  if (isPwmActuatorType(actuator->config.actuator_type)) {
    normalized_value = constrain(value, 0.0f, 1.0f);
  } else if (!validateActuatorValue(actuator->config.actuator_type, value)) {
    LOG_E(TAG, "Actuator value out of range for GPIO " + String(gpio));
    errorTracker.trackError(ERROR_COMMAND_INVALID,
                            ERROR_SEVERITY_ERROR,
                            "Actuator value invalid");
    return false;
  }

  bool success = actuator->driver->setValue(normalized_value);
  syncRegisteredConfigFromDriver(*actuator);

  // Phase 2: Runtime protection - track activation timestamp
  if (success) {
    if (actuator->config.current_state) {
      // Actuator activated - start timeout tracking
      actuator->config.runtime_protection.activation_start_ms = millis();
    } else {
      // Actuator deactivated - reset timeout tracking
      actuator->config.runtime_protection.activation_start_ms = 0;
    }

    publishActuatorStatus(gpio);
  }
  return success;
}

bool ActuatorManager::controlActuatorBinary(uint8_t gpio, bool state) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    LOG_E(TAG, "controlActuatorBinary: actuator not found on GPIO " + String(gpio));
    errorTracker.trackError(ERROR_ACTUATOR_NOT_FOUND,
                            ERROR_SEVERITY_ERROR,
                            "Actuator missing (binary control)");
    return false;
  }

  if (actuator->emergency_stopped) {
    LOG_W(TAG, "Actuator GPIO " + String(gpio) + " is emergency stopped");
    return false;
  }

  // Adoption-compatible no-op: do not retrigger hardware if state is already correct.
  if (actuator->config.current_state == state) {
    LOG_D(TAG, "Actuator GPIO " + String(gpio) + " already " + (state ? "ON" : "OFF") +
               " — no-op");
    return true;
  }

  bool success = actuator->driver->setBinary(state);
  syncRegisteredConfigFromDriver(*actuator);

  // Phase 2: Runtime protection - track activation timestamp
  if (success) {
    if (actuator->config.current_state) {
      // Actuator activated - start timeout tracking
      actuator->config.runtime_protection.activation_start_ms = millis();
    } else {
      // Actuator deactivated - reset timeout tracking
      actuator->config.runtime_protection.activation_start_ms = 0;
    }

    publishActuatorStatus(gpio);
  }
  return success;
}

bool ActuatorManager::emergencyStopAll() {
  // SAFETY-RTOS M4: protect actuators_[] against publishAllActuatorStatus (Core 0).
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (!actuators_[i].in_use || !actuators_[i].driver) {
      continue;
    }
    actuators_[i].driver->emergencyStop("EmergencyStopAll");
    actuators_[i].emergency_stopped = true;
    publishActuatorAlert(actuators_[i].gpio, "emergency_stop", "Actuator stopped");
    // Push status immediately so frontend can reflect emergency state without heartbeat delay.
    publishActuatorStatus(actuators_[i].gpio);
  }
  xSemaphoreGive(g_actuator_mutex);
  return true;
}

bool ActuatorManager::emergencyStopActuator(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    return false;
  }

  actuator->driver->emergencyStop("EmergencyStop");
  actuator->emergency_stopped = true;
  publishActuatorAlert(gpio, "emergency_stop", "Actuator stopped");
  // Push status immediately so frontend can reflect emergency state without heartbeat delay.
  publishActuatorStatus(gpio);
  return true;
}

bool ActuatorManager::clearEmergencyStop() {
  bool success = true;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (!actuators_[i].in_use || !actuators_[i].driver) {
      continue;
    }
    if (!actuators_[i].driver->clearEmergency()) {
      success = false;
    } else {
      actuators_[i].emergency_stopped = false;
      syncRegisteredConfigFromDriver(actuators_[i]);
    }
  }
  return success;
}

bool ActuatorManager::clearEmergencyStopActuator(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    return false;
  }
  bool cleared = actuator->driver->clearEmergency();
  if (cleared) {
    actuator->emergency_stopped = false;
    syncRegisteredConfigFromDriver(*actuator);
    publishActuatorStatus(gpio);
  }
  return cleared;
}

bool ActuatorManager::getEmergencyStopStatus(uint8_t gpio) const {
  const RegisteredActuator* actuator = findActuator(gpio);
  return actuator ? actuator->emergency_stopped : false;
}

bool ActuatorManager::resumeOperation() {
  bool cleared = clearEmergencyStop();
  if (cleared) {
    publishAllActuatorStatus();
  }
  return cleared;
}

void ActuatorManager::setAllActuatorsToSafeState() {
  if (!initialized_) return;
  // SAFETY-RTOS M4: protect actuators_[] against publishAllActuatorStatus (Core 0)
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
  uint8_t count = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (actuators_[i].in_use && actuators_[i].driver) {
      controlActuatorBinary(actuators_[i].config.gpio, actuators_[i].config.default_state);
      count++;
    }
  }
  xSemaphoreGive(g_actuator_mutex);
  LOG_W(TAG, "[SAFETY] " + String(count) + " actuator(s) set to safe state (default_state)");
}

void ActuatorManager::setUncoveredActuatorsToSafeState() {
  if (!initialized_) return;
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
  uint8_t held = 0, forced = 0;
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (!actuators_[i].in_use || !actuators_[i].driver) continue;
    uint8_t gpio = actuators_[i].config.gpio;
    bool is_on = actuators_[i].config.current_state;

    if (offlineModeManager.hasCoveringRule(gpio)) {
      if (is_on) {
        held++;
        LOG_I(TAG, "[SAFETY] GPIO " + String(gpio) +
                   " offline_rule_hold (P4 coverage, critical=" +
                   String(actuators_[i].config.critical ? "true" : "false") + ")");
        publishActuatorAlert(gpio, "offline_rule_hold",
                             "Actuator held ON — offline rule coverage active");
        publishLatchedOffline(gpio, "offline_rule_hold", is_on);
      }
    } else {
      // AUT-66: Respect per-actuator fail_safe_on_disconnect policy.
      if (actuators_[i].config.fail_safe_on_disconnect) {
        controlActuatorBinary(gpio, actuators_[i].config.default_state);
        if (is_on) {
          forced++;
          LOG_W(TAG, "[SAFETY] GPIO " + String(gpio) +
                     " safety_forced_off (fail_safe=true, no P4 rule" +
                     String(actuators_[i].config.critical ? ", CRITICAL" : "") + ")");
          publishActuatorAlert(gpio, "safety_forced_off",
                               String("fail_safe=true, no offline rule"));
          publishLatchedOffline(gpio, "safety_forced_off", is_on);
        }
      } else {
        // fail_safe=false: keep last state
        if (is_on) {
          LOG_I(TAG, "[SAFETY] GPIO " + String(gpio) +
                     " fail_safe=false, keeping last state at disconnect");
          publishLatchedOffline(gpio, "offline_rule_hold", is_on);
        }
      }
    }
  }
  xSemaphoreGive(g_actuator_mutex);
  LOG_W(TAG, "[SAFETY] Disconnect+rules: held=" + String(held) +
             " forced=" + String(forced));
}

void ActuatorManager::processActuatorLoops() {
  // SAFETY-RTOS M4: protect actuators_[] against publishAllActuatorStatus (Core 0).
  // controlActuatorBinary / emergencyStopActuator called within are NOT mutex owners.
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    if (!actuators_[i].in_use || !actuators_[i].driver) {
      continue;
    }

    // ═══════════════════════════════════════════════════
    // F1: COMMAND DURATION AUTO-OFF (from MQTT payload "duration")
    // ═══════════════════════════════════════════════════
    if (actuators_[i].command_duration_end_ms > 0 &&
        actuators_[i].config.current_state &&
        millis() >= actuators_[i].command_duration_end_ms) {
      LOG_I(TAG, "Actuator duration elapsed: GPIO " + String(actuators_[i].config.gpio) +
                  " auto-OFF after command duration");
      actuators_[i].command_duration_end_ms = 0;
      actuators_[i].last_command_source = "firmware:auto_duration";
      controlActuatorBinary(actuators_[i].config.gpio, false);
      // controlActuatorBinary already calls publishActuatorStatus on state change — no second call.
      syncRegisteredConfigFromDriver(actuators_[i]);
      continue;  // Skip further processing this iteration
    }

    // ═══════════════════════════════════════════════════
    // PHASE 2: TIMEOUT-PROTECTION (Robustness)
    // ═══════════════════════════════════════════════════
    // Check for actuator timeout (prevents continuous operation)
    if (actuators_[i].config.runtime_protection.timeout_enabled &&
        actuators_[i].config.current_state) {

      // Only check if activation_start_ms is set (non-zero)
      if (actuators_[i].config.runtime_protection.activation_start_ms > 0) {
        unsigned long runtime = millis() - actuators_[i].config.runtime_protection.activation_start_ms;

        if (runtime > actuators_[i].config.runtime_protection.max_runtime_ms) {
          LOG_W(TAG, "Actuator timeout: GPIO " + String(actuators_[i].config.gpio) +
                      " runtime " + String(runtime / 1000) + "s exceeded limit " +
                      String(actuators_[i].config.runtime_protection.max_runtime_ms / 1000) + "s");

          // Emergency stop this actuator
          emergencyStopActuator(actuators_[i].config.gpio);

          // Publish timeout alert
          publishActuatorAlert(actuators_[i].config.gpio, "runtime_protection",
                               "Actuator exceeded max runtime - emergency stopped");

          // Reset activation timestamp
          actuators_[i].config.runtime_protection.activation_start_ms = 0;
        }
      }
    }

    // Regular driver loop processing
    bool state_before = actuators_[i].config.current_state;
    actuators_[i].driver->loop();
    syncRegisteredConfigFromDriver(actuators_[i]);
    if (actuators_[i].config.current_state != state_before) {
      publishActuatorStatus(actuators_[i].gpio);
    }
  }
  xSemaphoreGive(g_actuator_mutex);
}

uint8_t ActuatorManager::extractGPIOFromTopic(const String& topic) const {
  int actuator_idx = topic.indexOf("/actuator/");
  if (actuator_idx == -1) {
    return 255;
  }
  int gpio_start = actuator_idx + 10;
  int gpio_end = topic.indexOf('/', gpio_start);
  if (gpio_end == -1) {
    return 255;
  }
  String gpio_str = topic.substring(gpio_start, gpio_end);
  gpio_str.trim();
  if (gpio_str.length() == 0) {
    return 255;
  }
  return static_cast<uint8_t>(gpio_str.toInt());
}

bool ActuatorManager::handleActuatorCommand(const String& topic, const String& payload) {
  // SAFETY-RTOS M4: protect actuators_[] against publishAllActuatorStatus (Core 0).
  xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
  uint8_t gpio = extractGPIOFromTopic(topic);
  if (gpio == 255) {
    LOG_E(TAG, "Invalid actuator command topic: " + topic);
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }
  // AUT-677: GPIO 0 is never a valid actuator GPIO (boot-strap pin; I2C-bus convention for sensors).
  if (gpio == 0) {
    LOG_W(TAG, "GPIO 0 rejected for actuator command — not a valid actuator GPIO");
    errorTracker.trackError(ERROR_COMMAND_INVALID, ERROR_SEVERITY_WARNING,
                            "GPIO 0 is not a valid actuator GPIO");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  ActuatorCommand command;
  command.gpio = gpio;
  command.command = extractJSONString(payload, "command");
  command.value = extractJSONFloat(payload, "value", 0.0f);
  command.duration_s = extractJSONUInt32(payload, "duration", 0);
  command.timestamp = millis();
  command.correlation_id = extractJSONString(payload, "correlation_id");
  command.issued_by = extractJSONString(payload, "issued_by");
  if (command.issued_by.length() == 0) {
    command.issued_by = "system:unknown";
  }

  // BUG-008 Fix: Check if actuator exists before processing command
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    LOG_E(TAG, "╔════════════════════════════════════════╗");
    LOG_E(TAG, "║  ACTUATOR COMMAND FAILED               ║");
    LOG_E(TAG, "╚════════════════════════════════════════╝");
    LOG_E(TAG, "No actuator configured on GPIO " + String(gpio));
    LOG_E(TAG, "Hint: Send config first via kaiser/{id}/esp/{esp_id}/config");

    String errorMessage = "Actuator not configured on GPIO " + String(gpio) +
                          ". Configure via API first.";
    publishActuatorResponse(command, false, errorMessage);
    errorTracker.trackError(ERROR_ACTUATOR_NOT_FOUND,
                            ERROR_SEVERITY_ERROR,
                            "Command received for unconfigured actuator");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  // Check emergency stop state
  if (actuator->emergency_stopped) {
    LOG_W(TAG, "Actuator GPIO " + String(gpio) + " is emergency stopped");
    // Re-publish alert + status so server/frontend state converges immediately
    // even if an earlier emergency event was missed in transit.
    publishActuatorAlert(gpio, "emergency_stop",
                         "Actuator in emergency stop state. Clear emergency first.");
    publishActuatorStatus(gpio);
    publishActuatorResponse(command, false,
                            "Actuator in emergency stop state. Clear emergency first.");
    xSemaphoreGive(g_actuator_mutex);
    return false;
  }

  // F1: Clear any pending duration timer on OFF/PWM/TOGGLE
  actuator->command_duration_end_ms = 0;

  // SAFETY-P4: Server commanded while offline → mark override so rule is skipped
  if (offlineModeManager.getMode() == OfflineMode::OFFLINE_ACTIVE) {
    offlineModeManager.setServerOverride(gpio);
  }

  bool success = false;
  String resultMessage = "Command executed";
  // Avoid duplicate actuator status publishes:
  // controlActuator/controlActuatorBinary already publish status on effective changes.
  // We only force a publish from this handler when command is a binary no-op
  // (already ON/OFF), because the control helper short-circuits in that case.
  bool expect_internal_status_publish = true;

  // Make command_source visible in the first status frame emitted by control helpers.
  actuator->last_command_source = command.issued_by;

  if (command.command.equalsIgnoreCase("ON")) {
    expect_internal_status_publish = !actuator->config.current_state;
    success = controlActuatorBinary(gpio, true);
    if (success && command.duration_s > 0) {
      actuator->command_duration_end_ms = millis() + (static_cast<unsigned long>(command.duration_s) * 1000UL);
      LOG_I(TAG, "Actuator GPIO " + String(gpio) + " ON with duration " +
                  String(command.duration_s) + "s (auto-OFF scheduled)");
    }
    if (!success) resultMessage = "Failed to turn actuator ON";
  } else if (command.command.equalsIgnoreCase("OFF")) {
    expect_internal_status_publish = actuator->config.current_state;
    success = controlActuatorBinary(gpio, false);
    if (!success) resultMessage = "Failed to turn actuator OFF";
  } else if (command.command.equalsIgnoreCase("PWM")) {
    expect_internal_status_publish = true;
    success = controlActuator(gpio, command.value);
    if (!success) resultMessage = "Failed to set PWM value";
  } else if (command.command.equalsIgnoreCase("TOGGLE")) {
    expect_internal_status_publish = true;
    success = controlActuatorBinary(gpio, !actuator->config.current_state);
    if (!success) resultMessage = "Failed to toggle actuator";
  } else {
    LOG_E(TAG, "Unknown actuator command: " + command.command);
    resultMessage = "Unknown command: " + command.command;
  }

  publishActuatorResponse(command, success, resultMessage);
  if (success) {
    LOG_I(TAG, "Actuator command executed: GPIO " + String(gpio) +
             " " + command.command + " = " + String(command.value));
    if (!expect_internal_status_publish) {
      publishActuatorStatus(gpio);
    }
  }

  xSemaphoreGive(g_actuator_mutex);
  return success;
}

bool ActuatorManager::parseActuatorDefinition(const JsonObjectConst& obj,
                                              ActuatorConfig& config,
                                              String& error_message,
                                              ConfigErrorCode& error_code) const {
  config = ActuatorConfig();
  error_message = "";
  error_code = ConfigErrorCode::NONE;

  if (!obj.containsKey("gpio")) {
    error_message = "Actuator config missing required field 'gpio'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  int gpio_value = 255;
  if (!JsonHelpers::extractInt(obj, "gpio", gpio_value)) {
    error_message = "Actuator field 'gpio' must be an integer";
    error_code = ConfigErrorCode::TYPE_MISMATCH;
    return false;
  }
  config.gpio = static_cast<uint8_t>(gpio_value);

  int aux_gpio_value = 255;
  if (JsonHelpers::extractInt(obj, "aux_gpio", aux_gpio_value)) {
    config.aux_gpio = static_cast<uint8_t>(aux_gpio_value);
  }

  if (obj.containsKey("actuator_type")) {
    if (!JsonHelpers::extractString(obj, "actuator_type", config.actuator_type)) {
      error_message = "Actuator field 'actuator_type' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else if (obj.containsKey("type")) {
    if (!JsonHelpers::extractString(obj, "type", config.actuator_type)) {
      error_message = "Actuator field 'type' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else {
    error_message = "Actuator config missing required field 'actuator_type'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  if (config.actuator_type.length() == 0) {
    error_message = "Actuator type cannot be empty";
    error_code = ConfigErrorCode::VALIDATION_FAILED;
    return false;
  }

  if (obj.containsKey("actuator_name")) {
    if (!JsonHelpers::extractString(obj, "actuator_name", config.actuator_name)) {
      error_message = "Actuator field 'actuator_name' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else if (obj.containsKey("name")) {
    if (!JsonHelpers::extractString(obj, "name", config.actuator_name)) {
      error_message = "Actuator field 'name' must be a string";
      error_code = ConfigErrorCode::TYPE_MISMATCH;
      return false;
    }
  } else {
    error_message = "Actuator config missing required field 'actuator_name'";
    error_code = ConfigErrorCode::MISSING_FIELD;
    return false;
  }

  JsonHelpers::extractString(obj, "subzone_id", config.subzone_id, "");

  bool bool_value = false;
  if (JsonHelpers::extractBool(obj, "active", bool_value, true)) {
    config.active = bool_value;
  } else {
    config.active = true;
  }

  if (JsonHelpers::extractBool(obj, "critical", bool_value, false)) {
    config.critical = bool_value;
  }

  if (JsonHelpers::extractBool(obj, "inverted_logic", bool_value, false)) {
    config.inverted_logic = bool_value;
  } else if (JsonHelpers::extractBool(obj, "inverted", bool_value, false)) {
    config.inverted_logic = bool_value;
  }

  if (JsonHelpers::extractBool(obj, "default_state", bool_value, false)) {
    config.default_state = bool_value;
  }

  // AUT-66: Server-configurable fail-safe policy on MQTT disconnect.
  if (obj.containsKey("fail_safe_on_disconnect")) {
    if (JsonHelpers::extractBool(obj, "fail_safe_on_disconnect", bool_value, true)) {
      config.fail_safe_on_disconnect = bool_value;
      config.has_fail_safe_override  = true;
    }
  } else {
    // No server override: critical actuators → fail-safe; non-critical → hold
    config.fail_safe_on_disconnect = config.critical;
    config.has_fail_safe_override  = false;
  }

  int default_pwm_value = 0;
  if (JsonHelpers::extractInt(obj, "default_pwm", default_pwm_value)) {
    default_pwm_value = constrain(default_pwm_value, 0, 255);
    config.default_pwm = static_cast<uint8_t>(default_pwm_value);
  }

  // SAFETY-P1 Mechanism C: max_runtime_ms configurable via Config-Push (default: 3600000ms)
  int max_runtime_value = 0;
  if (JsonHelpers::extractInt(obj, "max_runtime_ms", max_runtime_value) && max_runtime_value > 0) {
    config.runtime_protection.max_runtime_ms = static_cast<unsigned long>(max_runtime_value);
  }

  return true;
}

bool ActuatorManager::handleActuatorConfig(JsonArray actuators, const String& correlation_id) {
  LOG_I(TAG, "Handling actuator configuration from MQTT");

  // CP-F2: Caller passes pre-parsed JsonArray from central Config-Push parse.
  // Null array means 'actuators' key was absent or wrong type (sensor-only config).
  if (actuators.isNull()) {
    LOG_D(TAG, "No 'actuators' key in payload — skipping (sensor-only config)");
    return true;
  }

  size_t total = actuators.size();
  if (total == 0) {
    // Empty actuator array is valid for sensor-only ESPs
    LOG_I(TAG, "No actuators configured (sensor-only device)");
    ConfigResponseBuilder::publishSuccess(ConfigType::ACTUATOR, 0,
                                          "No actuators configured",
                                          correlation_id);
    return true;
  }
  uint8_t configured = 0;
  for (JsonObject actuatorObj : actuators) {
    ActuatorConfig config;
    String parse_error;
    ConfigErrorCode error_code = ConfigErrorCode::NONE;
    JsonVariantConst failed_variant = actuatorObj;
    JsonObjectConst actuatorObjConst = actuatorObj;

    if (!parseActuatorDefinition(actuatorObjConst, config, parse_error, error_code)) {
      if (parse_error.isEmpty()) {
        parse_error = "Invalid actuator definition";
      }
      if (error_code == ConfigErrorCode::NONE) {
        error_code = ConfigErrorCode::VALIDATION_FAILED;
      }
      ConfigResponseBuilder::publishError(
          ConfigType::ACTUATOR, error_code, parse_error, failed_variant,
          correlation_id);
      continue;
    }

    if (!configureActuator(config)) {
      String message = "Failed to configure actuator on GPIO " + String(config.gpio) +
                       " type=" + config.actuator_type +
                       " name=" + config.actuator_name +
                       " heap=" + String(ESP.getFreeHeap());
      LOG_E(TAG, message);
      ConfigResponseBuilder::publishError(
          ConfigType::ACTUATOR, ConfigErrorCode::UNKNOWN_ERROR, message, failed_variant,
          correlation_id);
      continue;
    }

    configured++;
  }

  if (configured == total) {
    String message = "Configured " + String(configured) + " actuator(s) successfully";
    ConfigResponseBuilder::publishSuccess(ConfigType::ACTUATOR, configured, message,
                                          correlation_id);
    return true;
  }

  return false;
}

String ActuatorManager::buildStatusPayload(const ActuatorStatus& status, const ActuatorConfig& config) const {
  // Phase 7: Get zone information from global variables (extern from main.cpp)
  extern KaiserZone g_kaiser;
  extern SystemConfig g_system_config;
  
  // Phase 8: Use NTP-synchronized Unix timestamp
  time_t unix_ts = timeManager.getUnixTimestamp();
  
  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"seq\":" + String(mqttClient.getNextSeq()) + ",";
  payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
  payload += "\"subzone_id\":\"" + config.subzone_id + "\",";
  payload += "\"ts\":" + String((unsigned long)unix_ts) + ",";
  payload += "\"gpio\":" + String(status.gpio) + ",";
  payload += "\"type\":\"" + config.actuator_type + "\",";
  payload += "\"state\":" + String(status.current_state ? "true" : "false") + ",";
  payload += "\"pwm\":" + String(status.current_pwm) + ",";
  payload += "\"runtime_ms\":" + String(status.runtime_ms) + ",";
  payload += "\"emergency\":\"" + String(emergencyStateToString(status.emergency_state)) + "\"";
  const RegisteredActuator* registered = findActuator(status.gpio);
  if (registered && registered->last_command_source.length() > 0) {
    payload += ",\"command_source\":\"" + registered->last_command_source + "\"";
  }
  payload += "}";
  return payload;
}

void ActuatorManager::publishActuatorStatus(uint8_t gpio) {
  RegisteredActuator* actuator = findActuator(gpio);
  if (!actuator || !actuator->driver) {
    return;
  }

  const PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
  if (shouldDeferActuatorStatusPublish(pq_stats.fill_level)) {
    LOG_D(TAG, "[AUT-481] Deferring actuator status publish (fill=" +
              String(pq_stats.fill_level) + "/" + String(PUBLISH_QUEUE_SIZE) +
              " gpio=" + String(gpio) + ")");
    return;
  }

  ActuatorStatus status = actuator->driver->getStatus();
  syncRegisteredConfigFromDriver(*actuator);
  String payload = buildStatusPayload(status, actuator->config);
  // AUT-654: copy immediately — TopicBuilder reuses a shared static buffer.
  String topic = String(TopicBuilder::buildActuatorStatusTopic(gpio));
  // AUT-326: QoS 0 — actuator status is supplementary telemetry, not a safety signal.
  // AUT-54: Command execution is acknowledged on actuator/response + system/intent_outcome
  // at QoS 0 (best-effort); critical failures still use NVS-backed intent_outcome replay.
  // QoS 0 keeps status + outcome traffic out of the IDF QoS-1 OUTBOX (PUBACK expiry path).
  mqttClient.publish(topic, payload, 0);
}

void ActuatorManager::publishAllActuatorStatus() {
  // SAFETY-RTOS M4/AUT-590 F2: Mutex per-iteration — Safety-Task (Core 1, Prio 5)
  // can run actuator commands between staggered publishes. 50 ms stagger spreads
  // the reconnect burst across time instead of loading all N slots simultaneously.
  for (uint8_t i = 0; i < MAX_ACTUATORS; i++) {
    xSemaphoreTake(g_actuator_mutex, portMAX_DELAY);
    const bool in_use = actuators_[i].in_use;
    if (in_use) {
      publishActuatorStatus(actuators_[i].gpio);
    }
    xSemaphoreGive(g_actuator_mutex);
    if (in_use) {
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
}

String ActuatorManager::buildResponsePayload(const ActuatorCommand& command,
                                             bool success,
                                             const String& message) const {
  // Phase 7: Get zone information from global variables
  extern KaiserZone g_kaiser;
  extern SystemConfig g_system_config;
  
  // Phase 8: Use NTP-synchronized Unix timestamp
  time_t unix_ts = timeManager.getUnixTimestamp();
  
  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"seq\":" + String(mqttClient.getNextSeq()) + ",";
  payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
  payload += "\"ts\":" + String((unsigned long)unix_ts) + ",";
  payload += "\"gpio\":" + String(command.gpio) + ",";
  payload += "\"command\":\"" + command.command + "\",";
  payload += "\"value\":" + String(command.value, 3) + ",";
  payload += "\"duration\":" + String(command.duration_s) + ",";
  payload += "\"success\":" + String(success ? "true" : "false") + ",";
  payload += "\"message\":\"" + message + "\"";
  if (command.correlation_id.length() > 0) {
    payload += ",\"correlation_id\":\"" + command.correlation_id + "\"";
  }
  if (command.issued_by.length() > 0) {
    payload += ",\"issued_by\":\"" + command.issued_by + "\"";
  }
  payload += "}";
  return payload;
}

void ActuatorManager::publishActuatorResponse(const ActuatorCommand& command,
                                              bool success,
                                              const String& message) {
  // AUT-654: copy topic immediately — TopicBuilder reuses a shared static buffer;
  // a concurrent MQTT callback (main.cpp:881) can call buildActuatorCommandTopic(0)
  // and overwrite the buffer before the delayed String(topic) conversion below.
  String topic = String(TopicBuilder::buildActuatorResponseTopic(command.gpio));
  String payload = buildResponsePayload(command, success, message);
  // AUT-54: QoS 0 — response is telemetry; QoS-1 OUTBOX + OUTBOX-expiry caused transport
  // disconnects under slow PUBACK (field: ~11s after last command, AAAAA.md).
  mqttClient.safePublish(topic, payload, 0);
}

void ActuatorManager::publishActuatorAlert(uint8_t gpio,
                                           const String& alert_type,
                                           const String& message) {
  // Phase 8: Use NTP-synchronized Unix timestamp
  time_t unix_ts = timeManager.getUnixTimestamp();
  
  // Phase 7: Get zone information from global variables
  extern KaiserZone g_kaiser;
  extern SystemConfig g_system_config;
  
  // AUT-654: copy immediately — TopicBuilder reuses a shared static buffer.
  String topic = String(TopicBuilder::buildActuatorAlertTopic(gpio));
  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"seq\":" + String(mqttClient.getNextSeq()) + ",";
  payload += "\"zone_id\":\"" + g_kaiser.zone_id + "\",";
  payload += "\"ts\":" + String((unsigned long)unix_ts) + ",";
  payload += "\"gpio\":" + String(gpio) + ",";
  payload += "\"alert_type\":\"" + alert_type + "\",";
  payload += "\"message\":\"" + message + "\"";
  payload += "}";
  // AUT-54: QoS 0 — same OUTBOX/backpressure rationale as actuator/response.
  mqttClient.safePublish(topic, payload, 0);
}

// QoS 0 — telemetry is best-effort: actuator state authority remains
// `actuator/{gpio}/status` (QoS 1) and `actuator_history` (server-side).
void ActuatorManager::publishLatchedOffline(uint8_t gpio,
                                            const char* reason,
                                            bool pre_disconnect_state) const {
  if (reason == nullptr) {
    return;
  }
  extern SystemConfig g_system_config;

  time_t unix_ts = timeManager.getUnixTimestamp();
  uint8_t offline_rule_count = offlineModeManager.getOfflineRuleCount();

  // AUT-677: copy immediately — TopicBuilder reuses a shared static buffer (same race as AUT-654).
  const char* raw_topic = TopicBuilder::buildActuatorLatchedOfflineTopic(gpio);
  if (raw_topic == nullptr || raw_topic[0] == '\0') {
    return;
  }
  String topic = String(raw_topic);

  String payload = "{";
  payload += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
  payload += "\"gpio\":" + String(gpio) + ",";
  payload += "\"ts\":" + String((unsigned long)unix_ts) + ",";
  payload += "\"reason\":\"" + String(reason) + "\",";
  payload += "\"actuator_state\":\"" + String(pre_disconnect_state ? "on" : "off") + "\",";
  payload += "\"offline_rule_count\":" + String(offline_rule_count);
  payload += "}";

  mqttClient.safePublish(topic, payload, 0);
}
