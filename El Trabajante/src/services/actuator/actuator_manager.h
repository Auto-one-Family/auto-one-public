#ifndef SERVICES_ACTUATOR_ACTUATOR_MANAGER_H
#define SERVICES_ACTUATOR_ACTUATOR_MANAGER_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <memory>

#include "../../models/actuator_types.h"
#include "../../models/error_codes.h"
#include "actuator_drivers/iactuator_driver.h"

class GPIOManager;
class ActuatorManagerTestHelper;

// ============================================
// Actuator Manager - Phase 5 Implementation
// ============================================
class ActuatorManager {
public:
  static ActuatorManager& getInstance();

  ActuatorManager(const ActuatorManager&) = delete;
  ActuatorManager& operator=(const ActuatorManager&) = delete;
  ActuatorManager(ActuatorManager&&) = delete;
  ActuatorManager& operator=(ActuatorManager&&) = delete;

  bool begin();
  void end();

  // Registry management
  bool configureActuator(const ActuatorConfig& config);
  bool removeActuator(uint8_t gpio);
  bool hasActuatorOnGPIO(uint8_t gpio) const;
  ActuatorConfig getActuatorConfig(uint8_t gpio) const;
  uint8_t getActiveActuatorCount() const { return actuator_count_; }

  /** Count configured actuators whose subzone_id matches (Phase 9). */
  uint8_t countActuatorsWithSubzone(const String& subzone_id) const;

  // Control operations
  bool controlActuator(uint8_t gpio, float value);
  bool controlActuatorBinary(uint8_t gpio, bool state);

  // Safety operations
  bool emergencyStopAll();
  bool emergencyStopActuator(uint8_t gpio);
  bool clearEmergencyStop();
  bool clearEmergencyStopActuator(uint8_t gpio);
  bool getEmergencyStopStatus(uint8_t gpio) const;
  bool resumeOperation();
  void processActuatorLoops();
  // SAFETY-P1: Set all actuators to their configured default_state (called on disconnect/timeout)
  void setAllActuatorsToSafeState();
  // AUT-66: Force actuators without covering offline rule to default_state; leave covered ones for P4
  void setUncoveredActuatorsToSafeState();

  // MQTT integration
  bool handleActuatorCommand(const String& topic, const String& payload);
  // CP-F2: Accepts pre-parsed JsonArray from central Config-Push parse — no internal deserializeJson.
  bool handleActuatorConfig(JsonArray actuators, const String& correlation_id = "");
  void publishActuatorStatus(uint8_t gpio);
  void publishAllActuatorStatus();
  void publishActuatorResponse(const ActuatorCommand& command, bool success, const String& message);
  void publishActuatorAlert(uint8_t gpio, const String& alert_type, const String& message);

  bool isInitialized() const { return initialized_; }

private:
  friend class ActuatorManagerTestHelper;
  struct RegisteredActuator {
    bool in_use = false;
    uint8_t gpio = 255;
    std::unique_ptr<IActuatorDriver> driver;
    ActuatorConfig config;
    bool emergency_stopped = false;
    unsigned long command_duration_end_ms = 0;  // F1: Auto-Off timer (0 = inactive)
    String last_command_source = "";
  };

  #ifndef MAX_ACTUATORS
    #define MAX_ACTUATORS 12  // Default fallback for ESP32 Dev
  #endif

  ActuatorManager();
  ~ActuatorManager() = default;

  RegisteredActuator* findActuator(uint8_t gpio);
  const RegisteredActuator* findActuator(uint8_t gpio) const;
  RegisteredActuator* getFreeSlot();

  bool validateActuatorConfig(const ActuatorConfig& config) const;
  std::unique_ptr<IActuatorDriver> createDriver(const String& actuator_type) const;
  uint8_t extractGPIOFromTopic(const String& topic) const;
  bool parseActuatorDefinition(const JsonObjectConst& obj,
                               ActuatorConfig& config,
                               String& error_message,
                               ConfigErrorCode& error_code) const;
  String buildStatusPayload(const ActuatorStatus& status, const ActuatorConfig& config) const;
  String buildResponsePayload(const ActuatorCommand& command, bool success, const String& message) const;
  static void preserveSoftPolicyFromRegistered(ActuatorConfig& merged, const ActuatorConfig& policy);
  static void syncRegisteredConfigFromDriver(RegisteredActuator& slot);
  static void syncDriverSoftPolicyFromRegistered(RegisteredActuator& slot);
  // AUT-117: QoS 0 telemetry for disconnect latch decisions
  void publishLatchedOffline(uint8_t gpio, const char* reason, bool pre_disconnect_state) const;

  RegisteredActuator actuators_[MAX_ACTUATORS];
  uint8_t actuator_count_;
  bool initialized_;
  GPIOManager* gpio_manager_;
};

extern ActuatorManager& actuatorManager;

#endif  // SERVICES_ACTUATOR_ACTUATOR_MANAGER_H
