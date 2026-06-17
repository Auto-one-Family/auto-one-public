#pragma once
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

// ============================================
// SAFETY-RTOS M4: Global RTOS Synchronization Primitives
// ============================================
// All mutexes created in initRtosMutexes() — called from setup() BEFORE
// createSafetyTask() / createCommunicationTask().
//
// Timeout policy:
//   g_actuator_mutex / g_sensor_mutex : portMAX_DELAY  — safety ops must not be skipped
//   g_i2c_mutex                       : 250 ms          — SHT31 ~15ms, recovery up to 200ms
//   g_onewire_mutex                   : portMAX_DELAY  — OneWire lib not thread-safe; MQTT
//                                                       onewire/scan (Core 0) vs DS18B20 read (Core 1)
//   g_gpio_registry_mutex             : portMAX_DELAY  — reserved for future GPIOManager use
//
// Core 0 holders  : Communication-Task (publishAllActuatorStatus, MQTT event handler)
// Core 1 holders  : Safety-Task (processActuatorLoops, performAllMeasurements, I2C reads)
// ============================================

// Protects actuators_[] in ActuatorManager.
// Held by: processActuatorLoops, handleActuatorCommand, setAllActuatorsToSafeState,
//          emergencyStopAll, publishAllActuatorStatus, handleActuatorConfig (Core 0→1 via queue).
extern SemaphoreHandle_t g_actuator_mutex;

// Protects sensors_[] / value_cache_[] in SensorManager.
// Held by: performAllMeasurements, configureSensor (Core 0→1 via queue).
extern SemaphoreHandle_t g_sensor_mutex;

// Protects Arduino Wire (I2C bus) — NOT thread-safe by itself.
// Held by all public I2CBusManager methods that call Wire (readRaw, writeRaw, scanBus,
// isDevicePresent, readSensorRaw).
// Timeout 250 ms to survive Config-Push + Sensor-Read overlap.
extern SemaphoreHandle_t g_i2c_mutex;

// Protects OneWire bus (Arduino OneWire is not thread-safe).
// Held by: begin/end/scanDevices/isDevicePresent/readRawTemperature.
extern SemaphoreHandle_t g_onewire_mutex;

// Protects GPIOManager pin registry.
// Reserved for future use when GPIOManager is accessed from multiple tasks.
extern SemaphoreHandle_t g_gpio_registry_mutex;

// Create all mutexes — call in setup() BEFORE createSafetyTask().
void initRtosMutexes();
