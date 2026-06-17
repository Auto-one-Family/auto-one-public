#include "pwm_actuator.h"

#include "../../../drivers/pwm_controller.h"
#include "../../../error_handling/error_tracker.h"
#include "../../../models/error_codes.h"
#include "../../../utils/logger.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "PWMACT";

PWMActuator::PWMActuator()
    : initialized_(false),
      emergency_stopped_(false),
      pwm_channel_(255),
      pwm_value_(0) {}

PWMActuator::~PWMActuator() {
  end();
}

bool PWMActuator::begin(const ActuatorConfig& config) {
  if (initialized_) {
    return true;
  }

  if (config.gpio == 255) {
    LOG_E(TAG, "PWMActuator: invalid GPIO");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "PWMActuator invalid GPIO");
    return false;
  }

  if (!pwmController.isInitialized()) {
    LOG_E(TAG, "PWMActuator: PWM controller not initialized");
    errorTracker.trackError(ERROR_PWM_INIT_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "PWM controller not ready");
    return false;
  }

  config_ = config;
  uint8_t channel = 255;
  if (!pwmController.attachChannel(config_.gpio, channel)) {
    LOG_E(TAG, "PWMActuator: attach channel failed for GPIO " + String(config_.gpio));
    return false;
  }

  pwm_channel_ = channel;
  pwm_value_ = 0;
  pwmController.write(channel, 0);

  config_.current_state = false;
  config_.current_pwm = 0;
  config_.last_command_ts = millis();
  initialized_ = true;
  emergency_stopped_ = false;

  LOG_I(TAG, "PWMActuator initialized on GPIO " + String(config_.gpio) + " (channel " + String(channel) + ")");
  return true;
}

void PWMActuator::end() {
  if (!initialized_) {
    return;
  }

  if (pwm_channel_ != 255) {
    pwmController.detachChannel(pwm_channel_);
  }

  pwm_channel_ = 255;
  initialized_ = false;
  emergency_stopped_ = false;
}

bool PWMActuator::setValue(float normalized_value) {
  if (!initialized_) {
    LOG_E(TAG, "PWMActuator::setValue before init");
    return false;
  }

  if (emergency_stopped_) {
    LOG_W(TAG, "PWMActuator command ignored, emergency active");
    return false;
  }

  if (!validateActuatorValue(ActuatorTypeTokens::PWM, normalized_value)) {
    LOG_E(TAG, "PWMActuator: invalid value " + String(normalized_value));
    errorTracker.trackError(ERROR_COMMAND_INVALID,
                            ERROR_SEVERITY_ERROR,
                            "PWMActuator value invalid");
    return false;
  }

  normalized_value = constrain(normalized_value, 0.0f, 1.0f);
  uint8_t pwm_value = static_cast<uint8_t>(normalized_value * 255.0f);
  return applyValue(pwm_value);
}

bool PWMActuator::setBinary(bool state) {
  return setValue(state ? 1.0f : 0.0f);
}

bool PWMActuator::applyValue(uint8_t pwm_value, bool force_publish) {
  if (!initialized_ || pwm_channel_ == 255) {
    return false;
  }

  float percent = (pwm_value / 255.0f) * 100.0f;
  if (!pwmController.writePercent(pwm_channel_, percent)) {
    LOG_E(TAG, "PWMActuator: writePercent failed on channel " + String(pwm_channel_));
    errorTracker.trackError(ERROR_PWM_SET_FAILED,
                            ERROR_SEVERITY_ERROR,
                            "PWMActuator write failed");
    return false;
  }

  pwm_value_ = pwm_value;
  config_.current_pwm = pwm_value;
  config_.current_state = pwm_value > 0;
  if (force_publish) {
    config_.last_command_ts = millis();
  }

  LOG_I(TAG, "PWMActuator channel " + String(pwm_channel_) +
           " value set to " + String(pwm_value));
  return true;
}

bool PWMActuator::emergencyStop(const String& reason) {
  LOG_W(TAG, "PWMActuator emergency stop (" + reason + ")");
  emergency_stopped_ = true;
  return applyValue(0, false);
}

bool PWMActuator::clearEmergency() {
  emergency_stopped_ = false;
  return true;
}

ActuatorStatus PWMActuator::getStatus() const {
  ActuatorStatus status;
  status.gpio = config_.gpio;
  status.actuator_type = ActuatorTypeTokens::PWM;
  status.current_state = config_.current_state;
  status.current_pwm = pwm_value_;
  status.runtime_ms = config_.accumulated_runtime_ms;
  status.error_state = false;
  status.error_message = "";
  status.emergency_state = emergency_stopped_
                               ? EmergencyState::EMERGENCY_ACTIVE
                               : EmergencyState::EMERGENCY_NORMAL;
  return status;
}

