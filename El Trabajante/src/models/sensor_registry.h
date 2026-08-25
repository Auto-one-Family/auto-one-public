#ifndef MODELS_SENSOR_REGISTRY_H
#define MODELS_SENSOR_REGISTRY_H

#include <Arduino.h>

// ============================================
// SENSOR REGISTRY - Centralized Sensor Definitions
// ============================================
// Purpose: Dynamic sensor type recognition and multi-value sensor support
// - Maps ESP32 sensor types to server processor types
// - Provides I2C device address information
// - Identifies multi-value sensors (e.g., SHT31: temp + humidity)
//
// Architecture: Server-Centric
// - ESP32 only handles RAW data acquisition
// - Server handles all processing via Pi-Enhanced mode

// ============================================
// SENSOR CAPABILITY STRUCTURE
// ============================================
struct SensorCapability {
    const char* server_sensor_type;  // Server processor type (e.g., "sht31_temp")
    const char* device_type;         // Device identifier (e.g., "sht31", "bmp280")
    uint8_t i2c_address;            // I2C device address (0x00 if not I2C)
    bool is_multi_value;             // Provides multiple values?
    bool is_i2c;                     // Is I2C sensor?
    bool is_uart;                    // Is UART sensor (e.g. MH-Z19 CO2)?
    bool is_digital;                 // true = GPIO digitalRead (polarity-configurable, see SensorConfig.polarity), no ADC, no bus
    bool is_pulse;                   // true = pulse-counting via ISR (e.g. FS300A flow sensor)
};

// ============================================
// SENSOR REGISTRY FUNCTIONS
// ============================================

/**
 * Find sensor capability by ESP32 sensor type.
 * 
 * Maps ESP32 sensor type (e.g., "temperature_sht31") to server processor type
 * and provides device information.
 * 
 * @param sensor_type ESP32 sensor type string
 * @return Pointer to SensorCapability if found, nullptr otherwise
 * 
 * Example:
 *   const SensorCapability* cap = findSensorCapability("temperature_sht31");
 *   if (cap) {
 *     // cap->server_sensor_type = "sht31_temp"
 *     // cap->device_type = "sht31"
 *     // cap->i2c_address = 0x44
 *   }
 */
const SensorCapability* findSensorCapability(const String& sensor_type);

/**
 * Check if a device type is a multi-value sensor.
 * 
 * Multi-value sensors provide multiple measurements (e.g., SHT31: temp + humidity).
 * 
 * @param device_type Device type identifier (e.g., "sht31")
 * @return True if device provides multiple values, false otherwise
 * 
 * Example:
 *   if (isMultiValueDevice("sht31")) {
 *     // Handle multi-value sensor
 *   }
 */
bool isMultiValueDevice(const String& device_type);

/**
 * Get I2C address for a device type.
 * 
 * @param device_type Device type identifier (e.g., "sht31")
 * @param default_address Default address to return if device not found
 * @return I2C address if found, default_address otherwise
 * 
 * Example:
 *   uint8_t addr = getI2CAddress("sht31", 0x44);  // Returns 0x44
 */
uint8_t getI2CAddress(const String& device_type, uint8_t default_address = 0x00);

/**
 * Get server sensor type from ESP32 sensor type.
 * 
 * Normalizes ESP32 sensor type to server processor type.
 * 
 * @param esp32_sensor_type ESP32 sensor type (e.g., "temperature_sht31")
 * @return Server sensor type (e.g., "sht31_temp") or empty string if not found
 * 
 * Example:
 *   String server_type = getServerSensorType("temperature_sht31");
 *   // Returns "sht31_temp"
 */
String getServerSensorType(const String& esp32_sensor_type);

/**
 * Get all value types for a multi-value device.
 * 
 * Returns list of server sensor types provided by a multi-value sensor.
 * 
 * @param device_type Device type identifier (e.g., "sht31")
 * @param output Array to store sensor types
 * @param max_output Maximum number of sensor types to store
 * @return Number of sensor types found
 * 
 * Example:
 *   String types[4];
 *   uint8_t count = getMultiValueTypes("sht31", types, 4);
 *   // Returns 2, types[0] = "sht31_temp", types[1] = "sht31_humidity"
 */
uint8_t getMultiValueTypes(const String& device_type, String* output, uint8_t max_output);

#endif // MODELS_SENSOR_REGISTRY_H

























