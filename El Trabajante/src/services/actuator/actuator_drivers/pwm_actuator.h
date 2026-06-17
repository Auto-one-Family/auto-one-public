#ifndef SERVICES_ACTUATOR_DRIVERS_PWM_ACTUATOR_H
#define SERVICES_ACTUATOR_DRIVERS_PWM_ACTUATOR_H

#include "iactuator_driver.h"

class PWMActuator : public IActuatorDriver {
public:
  PWMActuator();
  ~PWMActuator() override;

  bool begin(const ActuatorConfig& config) override;
  void end() override;
  bool isInitialized() const override { return initialized_; }

  bool setValue(float normalized_value) override;
  bool setBinary(bool state) override;

  bool emergencyStop(const String& reason) override;
  bool clearEmergency() override;
  void loop() override {}

  ActuatorStatus getStatus() const override;
  const ActuatorConfig& getConfig() const override { return config_; }
  String getType() const override { return String(ActuatorTypeTokens::PWM); }

private:
  bool applyValue(uint8_t pwm_value, bool force_publish = true);

  ActuatorConfig config_;
  bool initialized_;
  bool emergency_stopped_;
  uint8_t pwm_channel_;
  uint8_t pwm_value_;
};

#endif  // SERVICES_ACTUATOR_DRIVERS_PWM_ACTUATOR_H
