#include "i2c_sensor_protocol.h"

// ============================================
// I2C SENSOR PROTOCOL REGISTRY
// ============================================
// Industrial-Grade Protocol Definitions
// Reference: Manufacturer datasheets
//
// SHT31: Sensirion Datasheet Version 6, March 2020
// BMP280: Bosch Datasheet BST-BMP280-DS001-26
// BME280: Bosch Datasheet BST-BME280-DS002-15

// ============================================
// SHT31 - Sensirion Temperature & Humidity Sensor
// ============================================
// Protocol: Command-based (no register address on read)
// Command 0x2400: Single Shot, High Repeatability, Clock Stretch Disabled
// Response: 6 bytes [Temp_MSB, Temp_LSB, Temp_CRC, Hum_MSB, Hum_LSB, Hum_CRC]
// CRC: Polynomial 0x31, Init 0xFF (Sensirion standard)
// Timing: Max 15.5ms for high repeatability mode
static const I2CSensorProtocol SHT31_PROTOCOL PROGMEM = {
    .sensor_type = "sht31",
    .protocol_type = I2CProtocolType::COMMAND_BASED,
    .command_bytes = {0x24, 0x00},     // High repeatability, no clock stretch
    .command_length = 2,
    .data_register = 0x00,             // Not used for command-based
    .conversion_time_ms = 20,          // 15.5ms max + 4.5ms safety margin
    .expected_bytes = 6,               // Temp(2) + CRC(1) + Hum(2) + CRC(1)
    .crc = {
        .polynomial = 0x31,            // Sensirion CRC-8 polynomial
        .init_value = 0xFF,            // Sensirion CRC-8 init
        .interleaved = true,           // CRC after each 2-byte value
        .data_bytes = 2,               // 2 data bytes per CRC
    },
    .values = {
        {
            .value_type = "sht31_temp",
            .byte_offset = 0,          // Bytes 0-1
            .byte_count = 2,
            .big_endian = true,        // MSB first
            .crc_offset = 2,           // CRC at byte 2
        },
        {
            .value_type = "sht31_humidity",
            .byte_offset = 3,          // Bytes 3-4
            .byte_count = 2,
            .big_endian = true,
            .crc_offset = 5,           // CRC at byte 5
        },
        { nullptr, 0, 0, false, 0xFF },
        { nullptr, 0, 0, false, 0xFF },
    },
    .value_count = 2,
    .default_i2c_address = 0x44,       // ADDR pin to GND
    .alternate_i2c_address = 0x45,     // ADDR pin to VDD
};

// ============================================
// BMP280 - Bosch Pressure & Temperature Sensor
// ============================================
// Protocol: Register-based
// Data registers: 0xF7-0xFC (6 bytes: press[3], temp[3])
// Requires initial configuration write (ctrl_meas 0xF4)
// No per-reading CRC (burst read validation)
// Note: Sensor must be pre-configured via separate init sequence
static const I2CSensorProtocol BMP280_PROTOCOL PROGMEM = {
    .sensor_type = "bmp280",
    .protocol_type = I2CProtocolType::REGISTER_BASED,
    .command_bytes = {0x00, 0x00},     // Not used for register-based
    .command_length = 0,
    .data_register = 0xF7,             // Burst read start (press_msb)
    .conversion_time_ms = 0,           // No wait needed (sensor auto-converts)
    .expected_bytes = 6,               // Press(3) + Temp(3)
    .crc = {
        .polynomial = 0x00,
        .init_value = 0x00,
        .interleaved = false,          // No CRC in data
        .data_bytes = 0,
    },
    .values = {
        {
            .value_type = "bmp280_pressure",
            .byte_offset = 0,          // Bytes 0-2 (20-bit, MSB aligned)
            .byte_count = 3,
            .big_endian = true,
            .crc_offset = 0xFF,        // No CRC
        },
        {
            .value_type = "bmp280_temp",
            .byte_offset = 3,          // Bytes 3-5 (20-bit, MSB aligned)
            .byte_count = 3,
            .big_endian = true,
            .crc_offset = 0xFF,
        },
        { nullptr, 0, 0, false, 0xFF },
        { nullptr, 0, 0, false, 0xFF },
    },
    .value_count = 2,
    .default_i2c_address = 0x76,       // SDO to GND
    .alternate_i2c_address = 0x77,     // SDO to VDD
};

// ============================================
// BME280 - Bosch Environmental Sensor
// ============================================
// Protocol: Register-based (same as BMP280, adds humidity)
// Data registers: 0xF7-0xFE (8 bytes: press[3], temp[3], hum[2])
static const I2CSensorProtocol BME280_PROTOCOL PROGMEM = {
    .sensor_type = "bme280",
    .protocol_type = I2CProtocolType::REGISTER_BASED,
    .command_bytes = {0x00, 0x00},
    .command_length = 0,
    .data_register = 0xF7,             // Burst read start
    .conversion_time_ms = 0,
    .expected_bytes = 8,               // Press(3) + Temp(3) + Hum(2)
    .crc = {
        .polynomial = 0x00,
        .init_value = 0x00,
        .interleaved = false,
        .data_bytes = 0,
    },
    .values = {
        {
            .value_type = "bme280_pressure",
            .byte_offset = 0,
            .byte_count = 3,
            .big_endian = true,
            .crc_offset = 0xFF,
        },
        {
            .value_type = "bme280_temp",
            .byte_offset = 3,
            .byte_count = 3,
            .big_endian = true,
            .crc_offset = 0xFF,
        },
        {
            .value_type = "bme280_humidity",
            .byte_offset = 6,
            .byte_count = 2,
            .big_endian = true,
            .crc_offset = 0xFF,
        },
        { nullptr, 0, 0, false, 0xFF },
    },
    .value_count = 3,
    .default_i2c_address = 0x76,
    .alternate_i2c_address = 0x77,
};

// ============================================
// PROTOCOL REGISTRY TABLE
// ============================================
// Null-terminated array of protocol pointers
// Add new protocols here when supporting additional sensors
static const I2CSensorProtocol* const I2C_SENSOR_PROTOCOLS[] = {
    &SHT31_PROTOCOL,
    &BMP280_PROTOCOL,
    &BME280_PROTOCOL,
    nullptr  // End marker
};

// ============================================
// REGISTRY ACCESS IMPLEMENTATIONS
// ============================================

const I2CSensorProtocol* findI2CSensorProtocol(const String& sensor_type) {
    if (sensor_type.length() == 0) {
        return nullptr;
    }

    String lower_type = sensor_type;
    lower_type.toLowerCase();

    for (uint8_t i = 0; I2C_SENSOR_PROTOCOLS[i] != nullptr; i++) {
        const I2CSensorProtocol* proto = I2C_SENSOR_PROTOCOLS[i];
        if (lower_type == String(proto->sensor_type)) {
            return proto;
        }
    }

    return nullptr;
}

bool isI2CSensorTypeSupported(const String& sensor_type) {
    return findI2CSensorProtocol(sensor_type) != nullptr;
}

uint8_t getDefaultI2CAddress(const String& sensor_type, uint8_t fallback) {
    const I2CSensorProtocol* proto = findI2CSensorProtocol(sensor_type);
    if (proto) {
        return proto->default_i2c_address;
    }
    return fallback;
}

// ============================================
// VALUE EXTRACTION IMPLEMENTATION
// ============================================
// Replaces hardcoded extraction in sensor_manager.cpp:960-967

uint32_t extractRawValue(const String& sensor_type,
                         const String& value_type,
                         const uint8_t* buffer,
                         size_t buffer_len) {
    // Find protocol
    const I2CSensorProtocol* proto = findI2CSensorProtocol(sensor_type);
    if (!proto) {
        return 0;
    }

    // Find matching value extraction
    for (uint8_t i = 0; i < proto->value_count; i++) {
        const I2CValueExtraction* ve = &proto->values[i];

        // Skip null entries
        if (ve->value_type == nullptr) {
            continue;
        }

        // Check for match
        if (String(ve->value_type) == value_type) {
            // Boundary check
            if (ve->byte_offset + ve->byte_count > buffer_len) {
                return 0;
            }

            // Extract bytes according to endianness
            uint32_t raw = 0;

            if (ve->big_endian) {
                // MSB first (e.g., SHT31, BMP280)
                for (uint8_t b = 0; b < ve->byte_count; b++) {
                    raw = (raw << 8) | buffer[ve->byte_offset + b];
                }
            } else {
                // LSB first
                for (int8_t b = ve->byte_count - 1; b >= 0; b--) {
                    raw = (raw << 8) | buffer[ve->byte_offset + b];
                }
            }

            return raw;
        }
    }

    // Value type not found
    return 0;
}
