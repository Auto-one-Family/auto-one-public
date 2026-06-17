#ifndef SERVICES_ACTUATOR_DRIVERS_IACTUATOR_DRIVER_H
#define SERVICES_ACTUATOR_DRIVERS_IACTUATOR_DRIVER_H

#include <Arduino.h>
#include "../../../models/actuator_types.h"

// ============================================
// IActuatorDriver - Common interface used by ActuatorManager
// ============================================
class IActuatorDriver {
public:
  virtual ~IActuatorDriver() = default;

  // Lifecycle
  virtual bool begin(const ActuatorConfig& config) = 0;
  virtual void end() = 0;
  virtual bool isInitialized() const = 0;

  // Control operations
  virtual bool setValue(float normalized_value) = 0;  // 0.0 - 1.0
  virtual bool setBinary(bool state) = 0;             // true = ON/OPEN

  // Safety
  virtual bool emergencyStop(const String& reason) = 0;
  virtual bool clearEmergency() = 0;
  virtual void loop() = 0;  // Optional periodic processing

  // Status
  virtual ActuatorStatus getStatus() const = 0;
  virtual const ActuatorConfig& getConfig() const = 0;
  virtual String getType() const = 0;
};

#endif  // SERVICES_ACTUATOR_DRIVERS_IACTUATOR_DRIVER_H
