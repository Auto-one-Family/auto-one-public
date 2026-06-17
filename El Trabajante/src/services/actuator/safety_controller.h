#ifndef SERVICES_ACTUATOR_SAFETY_CONTROLLER_H
#define SERVICES_ACTUATOR_SAFETY_CONTROLLER_H

#include <Arduino.h>
#include "../../models/actuator_types.h"

class SafetyController {
public:
  static SafetyController& getInstance();

  bool begin();
  void end();

  bool emergencyStopAll(const String& reason);
  bool emergencyStopActuator(uint8_t gpio, const String& reason);

  // Subzone Emergency Isolation (Phase 9)
  bool isolateSubzone(const String& subzone_id, const String& reason);

  bool clearEmergencyStop();
  bool clearEmergencyStopActuator(uint8_t gpio);
  bool resumeOperation();

  bool isEmergencyActive() const;
  bool isEmergencyActive(uint8_t gpio) const;
  EmergencyState getEmergencyState() const { return emergency_state_; }

  void setRecoveryConfig(const RecoveryConfig& config);
  RecoveryConfig getRecoveryConfig() const { return recovery_config_; }

  String getEmergencyReason() const { return emergency_reason_; }
  String getRecoveryProgress() const;

private:
  SafetyController();
  ~SafetyController() = default;
  SafetyController(const SafetyController&) = delete;
  SafetyController& operator=(const SafetyController&) = delete;

  bool verifySystemSafety() const;
  bool verifyActuatorSafety(uint8_t gpio) const;
  void logEmergencyEvent(const String& reason, uint8_t gpio);

  EmergencyState emergency_state_;
  String emergency_reason_;
  unsigned long emergency_timestamp_;
  RecoveryConfig recovery_config_;
  bool initialized_;
};

extern SafetyController& safetyController;

#endif  // SERVICES_ACTUATOR_SAFETY_CONTROLLER_H
