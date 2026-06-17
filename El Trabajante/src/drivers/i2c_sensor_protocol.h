#ifndef DRIVERS_I2C_SENSOR_PROTOCOL_H
#define DRIVERS_I2C_SENSOR_PROTOCOL_H

#include <Arduino.h>

// ============================================
// I2C SENSOR PROTOCOL ABSTRACTION LAYER
// ============================================
// Phase 4: Protocol-Aware I2C Communication
// Purpose: Unified protocol handling for diverse I2C sensors
// Pattern Reference: OneWireBusManager::readRawTemperature()
//
// Supported Protocol Types:
// - COMMAND_BASED: Send command, wait, read directly (SHT31, HTU21D)
// - REGISTER_BASED: Write register, read data (BMP280, BME280)
// - BURST_READ: Direct multi-byte read without register (generic)
//
// Architecture: Server-Centric (raw data only, no local conversion)
// Note: sensor_type MUST match SensorCapability.device_type

// ============================================
// PROTOCOL TYPE ENUMERATION
// ============================================
enum class I2CProtocolType : uint8_t {
    REGISTER_BASED = 0,  // Traditional: Write register addr, then read
    COMMAND_BASED  = 1,  // Command sequence: Write cmd, wait, read directly
    BURST_READ     = 2,  // Direct read without register specification
};

// ============================================
// VALUE EXTRACTION INFO (für Multi-Value-Sensoren)
// ============================================
// Defines how to extract individual values from raw sensor buffer
// Used by extractRawValue() to parse multi-value sensor responses
struct I2CValueExtraction {
    const char* value_type;    // Value identifier (e.g., "sht31_temp", "sht31_humidity")
    uint8_t byte_offset;       // Start byte in buffer (0 for Temp, 3 for Humidity)
    uint8_t byte_count;        // Number of bytes (2 for 16-bit, 3 for 20-bit)
    bool big_endian;           // true = MSB first (SHT31), false = LSB first
    uint8_t crc_offset;        // CRC byte position (0xFF = no CRC for this value)
};

// ============================================
// CRC CONFIGURATION
// ============================================
// Defines CRC parameters for sensor data validation
struct I2CCRCConfig {
    uint8_t polynomial;        // CRC polynomial (0x31 for Sensirion, 0x07 generic)
    uint8_t init_value;        // Initial CRC value (0xFF for SHT31)
    bool interleaved;          // true: CRC after each value (SHT31 style)
    uint8_t data_bytes;        // Bytes per value before CRC (2 for SHT31)
};

// ============================================
// I2C SENSOR PROTOCOL STRUCTURE
// ============================================
// Complete protocol definition for I2C sensor communication
// Stored in PROGMEM for minimal RAM usage on ESP32
struct I2CSensorProtocol {
    // ---- Identification ----
    const char* sensor_type;           // Sensor identifier (MUST == SensorCapability.device_type)

    // ---- Protocol Configuration ----
    I2CProtocolType protocol_type;     // Communication pattern

    // ---- Command Bytes (COMMAND_BASED only) ----
    uint8_t command_bytes[2];          // Command bytes (e.g., {0x24, 0x00} for SHT31)
    uint8_t command_length;            // Number of command bytes (0, 1, or 2)

    // ---- Register Address (REGISTER_BASED only) ----
    uint8_t data_register;             // Register to read from (0xF7 for BMP280)

    // ---- Timing Configuration ----
    uint16_t conversion_time_ms;       // Wait time after command (0 if none)

    // ---- Data Configuration ----
    uint8_t expected_bytes;            // Number of bytes to read

    // ---- CRC Configuration ----
    I2CCRCConfig crc;                  // CRC validation parameters

    // ---- Value Extraction (Multi-Value) ----
    I2CValueExtraction values[4];      // Max 4 values per sensor
    uint8_t value_count;               // Number of values (2 for SHT31)

    // ---- Default Addresses ----
    uint8_t default_i2c_address;       // Factory default I2C address
    uint8_t alternate_i2c_address;     // Alternate address (0x00 if none)
};

// ============================================
// REGISTRY ACCESS FUNCTIONS
// ============================================

/**
 * Find protocol definition by sensor type
 *
 * @param sensor_type Sensor type identifier (e.g., "sht31", "bmp280")
 * @return Pointer to protocol definition, nullptr if not found
 *
 * Example:
 *   const I2CSensorProtocol* proto = findI2CSensorProtocol("sht31");
 *   if (proto && proto->protocol_type == I2CProtocolType::COMMAND_BASED) {
 *     // Use command-based protocol
 *   }
 */
const I2CSensorProtocol* findI2CSensorProtocol(const String& sensor_type);

/**
 * Check if sensor type has a registered protocol
 *
 * @param sensor_type Sensor type identifier
 * @return true if protocol exists, false otherwise
 */
bool isI2CSensorTypeSupported(const String& sensor_type);

/**
 * Get default I2C address for sensor type
 *
 * @param sensor_type Sensor type identifier
 * @param fallback Address to return if sensor not found
 * @return Default I2C address or fallback
 */
uint8_t getDefaultI2CAddress(const String& sensor_type, uint8_t fallback = 0x00);

// ============================================
// VALUE EXTRACTION HELPER
// ============================================

/**
 * Extract raw value from sensor buffer based on protocol definition
 *
 * This function replaces the hardcoded extraction logic previously in
 * sensor_manager.cpp:960-967. It uses the protocol's ValueExtraction
 * definitions to correctly parse multi-value sensor responses.
 *
 * @param sensor_type Device type identifier (e.g., "sht31")
 * @param value_type Value type identifier (e.g., "sht31_temp", "sht31_humidity")
 * @param buffer Raw data buffer from sensor
 * @param buffer_len Length of buffer
 * @return Extracted raw value, 0 if extraction fails
 *
 * Example:
 *   uint8_t buffer[6];  // SHT31 response: [temp_msb, temp_lsb, crc, hum_msb, hum_lsb, crc]
 *   uint32_t temp_raw = extractRawValue("sht31", "sht31_temp", buffer, 6);
 *   uint32_t hum_raw = extractRawValue("sht31", "sht31_humidity", buffer, 6);
 */
uint32_t extractRawValue(const String& sensor_type,
                         const String& value_type,
                         const uint8_t* buffer,
                         size_t buffer_len);

#endif // DRIVERS_I2C_SENSOR_PROTOCOL_H
