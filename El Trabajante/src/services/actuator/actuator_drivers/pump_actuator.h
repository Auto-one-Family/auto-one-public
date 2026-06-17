#ifndef SERVICES_ACTUATOR_DRIVERS_PUMP_ACTUATOR_H
#define SERVICES_ACTUATOR_DRIVERS_PUMP_ACTUATOR_H

#include "iactuator_driver.h"

class GPIOManager;

class PumpActuator : public IActuatorDriver {
public:
  struct RuntimeProtection {
    unsigned long max_runtime_ms = 3600000UL;      // 1h continuous runtime cap
    unsigned long cooldown_ms = 30000UL;           // 30s cooldown after cutoff
  };

  PumpActuator();
  ~PumpActuator() override;

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
  String getType() const override { return String(ActuatorTypeTokens::PUMP); }

  void setRuntimeProtection(const RuntimeProtection& protection);
  /** Copy max_runtime (and related) from ActuatorConfig after soft-reconfig (R20-P11). */
  void syncRuntimeLimitsFromConfig(const ActuatorConfig& cfg);
  bool canActivate() const;
  bool isRunning() const { return running_; }

private:
  bool applyState(bool state, bool force);

  ActuatorConfig config_;
  uint8_t gpio_;
  bool initialized_;
  bool running_;
  bool emergency_stopped_;

  unsigned long activation_start_ms_;
  unsigned long last_stop_ms_;
  unsigned long accumulated_runtime_ms_;
  unsigned long last_cycle_runtime_ms_;

  // AUT-737: Boot-safe gate — default_state not applied until ACTUATOR_BOOT_SETTLE_MS elapsed.
  // Prevents ~27s uncontrolled pump run when default_state=true and suppresses ESP32 GPIO transient HIGH.
  static constexpr uint32_t ACTUATOR_BOOT_SETTLE_MS = 5000U;
  unsigned long boot_settle_start_ms_;

  RuntimeProtection protection_;
  GPIOManager* gpio_manager_;
};

#endif  // SERVICES_ACTUATOR_DRIVERS_PUMP_ACTUATOR_H
