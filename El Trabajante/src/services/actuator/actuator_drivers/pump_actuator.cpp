#include "pump_actuator.h"

#include "../../../drivers/gpio_manager.h"
#include "../../../error_handling/error_tracker.h"
#include "../../../models/error_codes.h"
#include "../../../utils/logger.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "PUMP";

PumpActuator::PumpActuator()
    : gpio_(255),
      initialized_(false),
      running_(false),
      emergency_stopped_(false),
      activation_start_ms_(0),
      last_stop_ms_(0),
      accumulated_runtime_ms_(0),
      last_cycle_runtime_ms_(0),
      boot_settle_start_ms_(0),
      gpio_manager_(&GPIOManager::getInstance()) {}

PumpActuator::~PumpActuator() {
  end();
}

bool PumpActuator::begin(const ActuatorConfig& config) {
  if (initialized_) {
    return true;
  }

  if (config.gpio == 255) {
    LOG_E(TAG, "PumpActuator: invalid GPIO");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "PumpActuator invalid GPIO");
    return false;
  }

  config_ = config;
  gpio_ = config.gpio;

  // R20-P11: protection_ is the member canActivate() actually enforces (separate from
  // config_.runtime_protection). Without this sync, every newly-registered or structurally
  // reconfigured actuator silently keeps the compiled defaults (30s cooldown, 1h max runtime)
  // until a later soft-update calls syncRuntimeLimitsFromConfig() — same 2-line pattern as there.
  protection_.max_runtime_ms = config.runtime_protection.max_runtime_ms;
  protection_.cooldown_ms    = config.runtime_protection.cooldown_ms;

  if (!gpio_manager_->requestPin(gpio_, "actuator", config_.actuator_name.c_str())) {
    LOG_E(TAG, "PumpActuator: failed to reserve GPIO " + String(gpio_));
    errorTracker.trackError(ERROR_GPIO_RESERVED,
                            ERROR_SEVERITY_ERROR,
                            ("Pump GPIO busy: " + String(gpio_)).c_str());
    return false;
  }

  if (!gpio_manager_->configurePinMode(gpio_, OUTPUT)) {
    LOG_E(TAG, "PumpActuator: pinMode failed for GPIO " + String(gpio_));
    errorTracker.trackError(ERROR_GPIO_INVALID_MODE,
                            ERROR_SEVERITY_ERROR,
                            ("pump pinMode failed: " + String(gpio_)).c_str());
    gpio_manager_->releasePin(gpio_);
    return false;
  }

  // AUT-737: Boot to physical OFF state, inverted_logic-aware.
  // For active-low relays (inverted_logic=true) LOW = relay ON = pump runs; physical OFF requires HIGH.
  // AUT-734 F: original LOW write caused ~5s unintended pump run on every reset with inverted relay.
  // default_state is still deferred until ACTUATOR_BOOT_SETTLE_MS (protects default_state=true transient).
  int boot_off_level = config_.inverted_logic ? HIGH : LOW;
  digitalWrite(gpio_, boot_off_level);
  running_ = false;
  config_.current_state = false;
  config_.current_pwm = 0;
  config_.last_command_ts = millis();
  boot_settle_start_ms_ = millis();

  accumulated_runtime_ms_ = config_.accumulated_runtime_ms;
  last_stop_ms_ = millis();

  initialized_ = true;
  emergency_stopped_ = false;

  LOG_I(TAG, "PumpActuator initialized on GPIO " + String(gpio_));
  // AUT-734 C4 / AUT-737: log default_state but mark as deferred, not applied immediately.
  LOG_I(TAG, "[AUT-737] GPIO " + String(gpio_) + ": boot gate active, default_state=" +
             String(config_.default_state ? 1 : 0) +
             " deferred " + String(ACTUATOR_BOOT_SETTLE_MS) + "ms");
  return true;
}

void PumpActuator::end() {
  if (!initialized_) {
    return;
  }

  applyState(false, true);
  // AUT-1006: pass the inverted_logic-aware OFF level so GPIOManager keeps the pin
  // actively driven instead of releasing to a high-impedance INPUT_PULLUP, which does
  // not guarantee OFF on active-low relay hardware (weak pull-up can be overridden).
  int safe_off_level = config_.inverted_logic ? HIGH : LOW;
  gpio_manager_->releasePin(gpio_, safe_off_level);
  gpio_ = 255;
  initialized_ = false;
  running_ = false;
  emergency_stopped_ = false;
  boot_settle_start_ms_ = 0;
}

bool PumpActuator::setValue(float normalized_value) {
  bool desired_state = normalized_value >= 0.5f;
  return setBinary(desired_state);
}

bool PumpActuator::setBinary(bool state) {
  return applyState(state, false);
}

// Safety-Feature (Emergency-Stop-Enforcement):
// ESP ignoriert Commands während Emergency (Safety-Critical per IEC 61508, ISO 13849).
// WICHTIG: ESP triggert NICHT selbst Emergency (nur bei Server-Command).
// Dokumentiert in: docs/ZZZ.md - "Server-Centric Pragmatic Deviations"
bool PumpActuator::applyState(bool state, bool force) {
  if (!initialized_) {
    LOG_E(TAG, "PumpActuator::applyState called before init");
    return false;
  }

  if (!force && emergency_stopped_) {
    LOG_W(TAG, "PumpActuator: command ignored, emergency active");
    return false;
  }

  if (state && !force && !canActivate()) {
    LOG_W(TAG, "PumpActuator: runtime protection prevented activation on GPIO " + String(gpio_));
    errorTracker.trackError(ERROR_ACTUATOR_SET_FAILED,
                            ERROR_SEVERITY_WARNING,
                            "Pump runtime protection triggered");
    return false;
  }

  int level = state ? HIGH : LOW;
  if (config_.inverted_logic) {
    level = (level == HIGH) ? LOW : HIGH;
  }

  // Always write GPIO — even if running_ matches state. External interference
  // (e.g. safe-mode setting pin to INPUT_PULLUP) can desync hardware from
  // running_ flag. Idempotent: repeated digitalWrite is safe.
  digitalWrite(gpio_, level);

  if (state == running_) {
    return true;
  }

  unsigned long now = millis();
  if (state) {
    activation_start_ms_ = now;
  } else if (activation_start_ms_ != 0) {
    last_cycle_runtime_ms_ = now - activation_start_ms_;
    accumulated_runtime_ms_ += last_cycle_runtime_ms_;
    config_.accumulated_runtime_ms = accumulated_runtime_ms_;
    activation_start_ms_ = 0;
    last_stop_ms_ = now;
  }

  running_ = state;
  config_.current_state = state;
  config_.current_pwm = state ? 255 : 0;
  config_.last_command_ts = now;

  LOG_I(TAG, "PumpActuator GPIO " + String(gpio_) + (state ? " ON" : " OFF"));
  return true;
}

// Hardware-Safety-Feature (Runtime-Protection):
// Schützt Pump vor Überhitzung/Verschleiß (wie Thermal-Shutdown in CPUs).
// Protection-Parameter werden vom Server konfiguriert (max_runtime, cooldown).
// WICHTIG: Dies ist NICHT Business-Logic (keine Priority-basierte Entscheidung).
// Dokumentiert in: docs/ZZZ.md - "Server-Centric Pragmatic Deviations"
bool PumpActuator::canActivate() {
  // AUT-1020: reset denial info before each check (member-approach, B3)
  last_denied_info_ = ActivationDeniedInfo{};

  if (!initialized_) {
    return false;
  }

  // Cooldown applies after EVERY stop, not just after a runtime-overrun.
  // Server schema: cooldown_ms = "Minimum time between activations".
  // cooldown_ms=0 disables this check entirely (no branching needed).
  if (last_stop_ms_ != 0 && protection_.cooldown_ms > 0) {
    unsigned long since_stop = millis() - last_stop_ms_;
    if (since_stop < protection_.cooldown_ms) {
      // AUT-1020: populate denial info for structured response in actuator_manager
      last_denied_info_.reason = "cooldown_active";
      last_denied_info_.limit_ms = protection_.cooldown_ms;
      last_denied_info_.remaining_ms = protection_.cooldown_ms - since_stop;
      last_denied_info_.error_code = ERROR_ACTUATOR_COOLDOWN_ACTIVE;
      return false;
    }
  }

  return true;
}

bool PumpActuator::emergencyStop(const String& reason) {
  LOG_W(TAG, "PumpActuator emergency stop (" + reason + ") on GPIO " + String(gpio_));
  emergency_stopped_ = true;
  return applyState(false, true);
}

bool PumpActuator::clearEmergency() {
  emergency_stopped_ = false;
  return true;
}

void PumpActuator::loop() {
  // AUT-737: Release boot gate and apply deferred default_state after settle period.
  if (boot_settle_start_ms_ != 0 &&
      (millis() - boot_settle_start_ms_) >= ACTUATOR_BOOT_SETTLE_MS) {
    boot_settle_start_ms_ = 0;
    LOG_I(TAG, "[AUT-737] Boot gate released GPIO " + String(gpio_) +
               ", applying default_state=" + String(config_.default_state ? 1 : 0));
    applyState(config_.default_state, false);
  }

  if (running_ && activation_start_ms_ != 0) {
    unsigned long now = millis();
    config_.current_pwm = 255;
    config_.current_state = true;
    config_.accumulated_runtime_ms = accumulated_runtime_ms_ + (now - activation_start_ms_);
  }
}

ActuatorStatus PumpActuator::getStatus() const {
  ActuatorStatus status;
  status.gpio = gpio_;
  status.actuator_type = ActuatorTypeTokens::PUMP;
  status.current_state = running_;
  status.current_pwm = running_ ? 255 : 0;
  status.runtime_ms = running_ && activation_start_ms_ != 0
                          ? accumulated_runtime_ms_ + (millis() - activation_start_ms_)
                          : accumulated_runtime_ms_;
  status.error_state = false;
  status.error_message = "";
  status.emergency_state = emergency_stopped_ ? EmergencyState::EMERGENCY_ACTIVE
                                              : EmergencyState::EMERGENCY_NORMAL;
  return status;
}

void PumpActuator::setRuntimeProtection(const RuntimeProtection& protection) {
  protection_ = protection;
}

void PumpActuator::syncRuntimeLimitsFromConfig(const ActuatorConfig& cfg) {
  config_.runtime_protection = cfg.runtime_protection;
  protection_.max_runtime_ms = cfg.runtime_protection.max_runtime_ms;
  protection_.cooldown_ms    = cfg.runtime_protection.cooldown_ms;
  config_.fail_safe_on_disconnect = cfg.fail_safe_on_disconnect;
  config_.has_fail_safe_override  = cfg.has_fail_safe_override;
  config_.critical                = cfg.critical;
  config_.actuator_name           = cfg.actuator_name;
  config_.subzone_id              = cfg.subzone_id;

  // AUT-1008: inverted_logic flips the MEANING of the GPIO level already applied to
  // the pin. Unlike the other soft fields above (no immediate physical consequence),
  // a change here must re-apply the unchanged logical state so the physical pin
  // follows the new polarity — otherwise ON/OFF silently inverts with no command sent.
  bool inverted_logic_changed = (config_.inverted_logic != cfg.inverted_logic);
  config_.inverted_logic          = cfg.inverted_logic;
  config_.default_state           = cfg.default_state;
  config_.default_pwm             = cfg.default_pwm;

  if (inverted_logic_changed && initialized_) {
    applyState(running_, true);
  }
}

