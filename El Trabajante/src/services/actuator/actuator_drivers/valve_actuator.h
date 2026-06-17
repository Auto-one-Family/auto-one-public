#ifndef SERVICES_ACTUATOR_DRIVERS_VALVE_ACTUATOR_H
#define SERVICES_ACTUATOR_DRIVERS_VALVE_ACTUATOR_H

#include "iactuator_driver.h"

class GPIOManager;

class ValveActuator : public IActuatorDriver {
public:
  ValveActuator();
  ~ValveActuator() override;

  bool begin(const ActuatorConfig& config) override;
  void end() override;
  bool isInitialized() const override { return initialized_; }

  bool setValue(float normalized_value) override;
  bool setBinary(bool state) override;

  bool emergencyStop(const String& reason) override;
  bool clearEmergency() override;
  void loop() override;

  ActuatorStatus getStatus() const override;
  const ActuatorConfig& getConfig() const override { return config_; }
  String getType() const override { return String(ActuatorTypeTokens::VALVE); }

  void setTransitionTime(uint32_t transition_time_ms);
  uint8_t getCurrentPosition() const { return current_position_; }
  bool isMoving() const { return is_moving_; }

private:
  bool moveToPosition(uint8_t target_pos);
  void stopMovement();
  void applyDirection(int8_t delta);

  ActuatorConfig config_;
  uint8_t direction_pin_;
  uint8_t enable_pin_;

  uint8_t current_position_;
  uint8_t target_position_;
  bool is_moving_;
  bool initialized_;
  bool emergency_stopped_;

  uint32_t transition_time_ms_;
  unsigned long move_start_ms_;
  uint32_t move_duration_ms_;

  GPIOManager* gpio_manager_;
};

#endif  // SERVICES_ACTUATOR_DRIVERS_VALVE_ACTUATOR_H
