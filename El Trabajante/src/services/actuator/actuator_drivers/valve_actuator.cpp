#include "valve_actuator.h"

#include "../../../drivers/gpio_manager.h"
#include "../../../error_handling/error_tracker.h"
#include "../../../models/error_codes.h"
#include "../../../utils/logger.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "VALVE";

namespace {
constexpr uint8_t kMaxValvePosition = 2;
constexpr uint8_t kValveMidPosition = 1;
}

ValveActuator::ValveActuator()
    : direction_pin_(255),
      enable_pin_(255),
      current_position_(0),
      target_position_(0),
      is_moving_(false),
      initialized_(false),
      emergency_stopped_(false),
      transition_time_ms_(5000),
      move_start_ms_(0),
      move_duration_ms_(0),
      gpio_manager_(&GPIOManager::getInstance()) {}

ValveActuator::~ValveActuator() {
  end();
}

bool ValveActuator::begin(const ActuatorConfig& config) {
  if (initialized_) {
    return true;
  }

  if (config.gpio == 255) {
    LOG_E(TAG, "ValveActuator: invalid primary GPIO");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "ValveActuator invalid gpio");
    return false;
  }

  config_ = config;

  direction_pin_ = config_.gpio;
  enable_pin_ = (config_.aux_gpio != 255) ? config_.aux_gpio : static_cast<uint8_t>(config_.gpio + 1);

  if (enable_pin_ == 255) {
    LOG_E(TAG, "ValveActuator: missing enable pin");
    return false;
  }

  if (!gpio_manager_->requestPin(direction_pin_, "actuator", config_.actuator_name.c_str())) {
    LOG_E(TAG, "ValveActuator: failed to reserve direction pin " + String(direction_pin_));
    errorTracker.trackError(ERROR_GPIO_RESERVED,
                            ERROR_SEVERITY_ERROR,
                            "Valve direction GPIO busy");
    return false;
  }

  if (!gpio_manager_->requestPin(enable_pin_, "actuator", config_.actuator_name.c_str())) {
    LOG_E(TAG, "ValveActuator: failed to reserve enable pin " + String(enable_pin_));
    gpio_manager_->releasePin(direction_pin_);
    errorTracker.trackError(ERROR_GPIO_RESERVED,
                            ERROR_SEVERITY_ERROR,
                            "Valve enable GPIO busy");
    return false;
  }

  if (!gpio_manager_->configurePinMode(direction_pin_, OUTPUT) ||
      !gpio_manager_->configurePinMode(enable_pin_, OUTPUT)) {
    LOG_E(TAG, "ValveActuator: pinMode failed");
    gpio_manager_->releasePin(direction_pin_);
    gpio_manager_->releasePin(enable_pin_);
    errorTracker.trackError(ERROR_GPIO_INVALID_MODE,
                            ERROR_SEVERITY_ERROR,
                            "Valve pinMode failed");
    return false;
  }

  digitalWrite(direction_pin_, LOW);
  digitalWrite(enable_pin_, LOW);

  current_position_ = 0;
  target_position_ = 0;
  config_.current_state = false;
  config_.current_pwm = 0;
  config_.last_command_ts = millis();

  initialized_ = true;
  emergency_stopped_ = false;

  LOG_I(TAG, "ValveActuator initialized on pins dir=" + String(direction_pin_) +
           ", enable=" + String(enable_pin_));
  return true;
}

void ValveActuator::end() {
  if (!initialized_) {
    return;
  }

  stopMovement();
  gpio_manager_->releasePin(direction_pin_);
  gpio_manager_->releasePin(enable_pin_);
  direction_pin_ = 255;
  enable_pin_ = 255;
  initialized_ = false;
  emergency_stopped_ = false;
}

bool ValveActuator::setValue(float normalized_value) {
  if (!initialized_) {
    LOG_E(TAG, "ValveActuator::setValue before init");
    return false;
  }

  if (emergency_stopped_) {
    LOG_W(TAG, "ValveActuator: command ignored, emergency active");
    return false;
  }

  normalized_value = constrain(normalized_value, 0.0f, 1.0f);
  uint8_t target = 0;
  if (normalized_value >= 0.66f) {
    target = kMaxValvePosition;
  } else if (normalized_value >= 0.33f) {
    target = kValveMidPosition;
  }

  return moveToPosition(target);
}

bool ValveActuator::setBinary(bool state) {
  return moveToPosition(state ? kMaxValvePosition : 0);
}

bool ValveActuator::moveToPosition(uint8_t target_pos) {
  if (!initialized_) {
    return false;
  }

  if (target_pos > kMaxValvePosition) {
    target_pos = kMaxValvePosition;
  }

  if (target_pos == current_position_ && !is_moving_) {
    return true;
  }

  int8_t delta = static_cast<int8_t>(target_pos) - static_cast<int8_t>(current_position_);
  if (delta == 0) {
    target_position_ = target_pos;
    stopMovement();
    current_position_ = target_pos;
    config_.current_state = current_position_ > 0;
    config_.current_pwm = current_position_ * 127;
    return true;
  }

  uint32_t half_transition = transition_time_ms_ / 2;
  move_duration_ms_ = static_cast<uint32_t>(abs(delta)) * half_transition;
  if (move_duration_ms_ == 0) {
    move_duration_ms_ = half_transition;
  }

  applyDirection(delta);
  digitalWrite(enable_pin_, HIGH);
  is_moving_ = true;
  emergency_stopped_ = false;
  move_start_ms_ = millis();
  target_position_ = target_pos;

  LOG_I(TAG, "ValveActuator moving from " + String(current_position_) +
           " to " + String(target_position_) + " (" + String(move_duration_ms_) + "ms)");
  return true;
}

void ValveActuator::applyDirection(int8_t delta) {
  if (delta >= 0) {
    digitalWrite(direction_pin_, HIGH);
  } else {
    digitalWrite(direction_pin_, LOW);
  }
}

void ValveActuator::stopMovement() {
  digitalWrite(enable_pin_, LOW);
  is_moving_ = false;
  move_duration_ms_ = 0;
  move_start_ms_ = 0;
  current_position_ = target_position_;
  config_.current_state = current_position_ > 0;
  config_.current_pwm = current_position_ * 127;
  config_.last_command_ts = millis();
}

bool ValveActuator::emergencyStop(const String& reason) {
  LOG_W(TAG, "ValveActuator emergency stop (" + reason + ")");
  emergency_stopped_ = true;
  stopMovement();
  current_position_ = 0;
  target_position_ = 0;
  digitalWrite(direction_pin_, LOW);
  return true;
}

bool ValveActuator::clearEmergency() {
  emergency_stopped_ = false;
  return true;
}

void ValveActuator::loop() {
  if (!initialized_ || !is_moving_) {
    return;
  }

  if (millis() - move_start_ms_ >= move_duration_ms_) {
    stopMovement();
  }
}

ActuatorStatus ValveActuator::getStatus() const {
  ActuatorStatus status;
  status.gpio = config_.gpio;
  status.actuator_type = ActuatorTypeTokens::VALVE;
  status.current_state = current_position_ > 0;
  status.current_pwm = current_position_ * 127;
  status.runtime_ms = config_.accumulated_runtime_ms;
  status.error_state = false;
  status.error_message = "";
  status.emergency_state = emergency_stopped_
                               ? EmergencyState::EMERGENCY_ACTIVE
                               : EmergencyState::EMERGENCY_NORMAL;
  return status;
}

void ValveActuator::setTransitionTime(uint32_t transition_time_ms) {
  if (transition_time_ms == 0) {
    return;
  }
  transition_time_ms_ = transition_time_ms;
}

