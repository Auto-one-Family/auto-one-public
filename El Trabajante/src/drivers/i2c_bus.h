#ifndef DRIVERS_I2C_BUS_H
#define DRIVERS_I2C_BUS_H

#include <Arduino.h>
#include <Wire.h>
#include "i2c_sensor_protocol.h"

// ============================================
// I2C Bus Manager - Hardware Abstraction Layer
// ============================================
// Phase 3: Hardware Abstraction Layer
// Documentation: Phase_3.md lines 151-235
// Architecture: Server-Centric (Pi-Enhanced Mode)
//
// Purpose: I2C bus control and raw data reading for sensors
// - Board-agnostic I2C initialization (XIAO ESP32-C3 / ESP32-WROOM-32)
// - Multi-device support with bus scanning
// - Raw data reading for Pi-Enhanced processing
// - GPIO Manager integration for pin safety

// ============================================
// I2C BUS MANAGER CLASS
// ============================================
// Singleton class managing I2C bus operations

class I2CBusManager {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static I2CBusManager& getInstance() {
        static I2CBusManager instance;
        return instance;
    }

    // Prevent copy and move operations
    I2CBusManager(const I2CBusManager&) = delete;
    I2CBusManager& operator=(const I2CBusManager&) = delete;
    I2CBusManager(I2CBusManager&&) = delete;
    I2CBusManager& operator=(I2CBusManager&&) = delete;

    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize I2C bus with hardware-specific pins
    // Loads pin configuration from HardwareConfig
    // Reserves pins via GPIOManager
    // Returns false if initialization fails
    bool begin();

    // Deinitialize I2C bus and release pins
    void end();

    // ============================================
    // BUS SCANNING
    // ============================================
    // Scan I2C bus for connected devices (0x08-0x77)
    // addresses: Array to store found device addresses
    // max_addresses: Maximum size of addresses array
    // found_count: Output parameter with number of found devices
    // Returns false if scan fails
    bool scanBus(uint8_t addresses[], uint8_t max_addresses, uint8_t& found_count);

    // Check if a specific I2C device is present at address
    bool isDevicePresent(uint8_t address);

    // ============================================
    // RAW DATA READING (PI-ENHANCED MODE)
    // ============================================
    // Read raw bytes from I2C device register
    // device_address: 7-bit I2C address (0x00-0x7F)
    // register_address: Register to read from
    // buffer: Output buffer for received data
    // length: Number of bytes to read
    // Returns false if device not found or read fails
    bool readRaw(uint8_t device_address, uint8_t register_address, 
                 uint8_t* buffer, size_t length);

    // Write raw bytes to I2C device register
    // device_address: 7-bit I2C address (0x00-0x7F)
    // register_address: Register to write to
    // data: Data to write
    // length: Number of bytes to write
    // Returns false if device not found or write fails
    bool writeRaw(uint8_t device_address, uint8_t register_address,
                  const uint8_t* data, size_t length);

    // ============================================
    // PROTOCOL-AWARE SENSOR READING (Phase 4)
    // ============================================
    // Read raw sensor data using protocol registry
    // Automatically selects correct communication pattern based on sensor type
    //
    // sensor_type: Device type identifier (e.g., "sht31", "bmp280")
    //              MUST match SensorCapability.device_type
    // i2c_address: Device address (0 = use protocol default)
    // buffer: Output buffer for raw data
    // buffer_size: Maximum buffer capacity
    // bytes_read: Output - actual bytes read
    //
    // Returns: true on success, false on error
    //          Error codes tracked via ErrorTracker
    //
    // Example:
    //   uint8_t buffer[8];
    //   size_t bytes_read;
    //   if (i2cBusManager.readSensorRaw("sht31", 0x44, buffer, 8, bytes_read)) {
    //     // buffer contains: [temp_msb, temp_lsb, temp_crc, hum_msb, hum_lsb, hum_crc]
    //   }
    bool readSensorRaw(const String& sensor_type, uint8_t i2c_address,
                       uint8_t* buffer, size_t buffer_size, size_t& bytes_read);

    // ============================================
    // ADS1115 EXTERNAL ADC (single-shot, single-ended)
    // ============================================
    // Read one single-ended channel of an ADS1115 16-bit I2C ADC.
    //
    // Used as an OPTIONAL acquisition source for analog probes (pH/EC): the
    // RAW count (0..32767) replaces the internal ESP32 analogRead() value and
    // still flows unchanged through the server's conversion/calibration path.
    //
    // Conversion strategy: single-shot + OS-bit poll (non-blocking-cooperative,
    // bounded timeout). On NACK the write is retried once; on timeout the call
    // returns false so the caller can skip the sample and keep the last value.
    //
    // address:  ADS1115 I2C address (0x48-0x4B)
    // channel:  single-ended input channel (0-3 → AIN0..AIN3)
    // pga_bits: PGA config-register bits [11:9] (0-5); 1 = +-4.096V (default).
    //           See ads1115PgaBitsFromString() in sensor_types.h.
    // raw_out:  output RAW count (0..32767; negative readings clamped to 0)
    //
    // Returns: true on success, false on NACK/timeout/invalid args.
    bool readAds1115SingleEnded(uint8_t address, uint8_t channel,
                                uint8_t pga_bits, uint16_t& raw_out);

    // Check if sensor type has registered protocol
    bool isSensorTypeSupported(const String& sensor_type) const;

    // Get list of supported I2C sensor types (for server discovery)
    // types: Array to store supported sensor type names
    // max_count: Maximum number of entries to return
    // count: Output - actual number of entries
    void getSupportedI2CSensorTypes(String types[], uint8_t max_count, uint8_t& count) const;

    // ============================================
    // STATUS QUERIES
    // ============================================
    // Check if I2C bus is initialized
    bool isInitialized() const { return initialized_; }

    // Get detailed bus status for debugging
    // Format: "I2C[SDA:4,SCL:5,Freq:100kHz,Init:true,RecoveryAttempts:0]"
    String getBusStatus() const;

    // ============================================
    // I2C BUS RECOVERY
    // ============================================
    // Attempt to recover a stuck I2C bus by sending 9 clock pulses
    // and generating a STOP condition. Returns true if bus is functional.
    bool recoverBus();

    // Check if recovery is needed and attempt it (max 3 attempts per minute)
    // Returns true if recovery was successful, false otherwise
    bool attemptRecoveryIfNeeded(uint8_t error_code);

private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    I2CBusManager() 
        : initialized_(false), 
          sda_pin_(0), 
          scl_pin_(0), 
          frequency_(100000) {}
    
    ~I2CBusManager() {}

    // ============================================
    // INTERNAL STATE
    // ============================================
    bool initialized_;      // Bus initialization status
    uint8_t sda_pin_;       // SDA pin (from HardwareConfig)
    uint8_t scl_pin_;       // SCL pin (from HardwareConfig)
    uint32_t frequency_;    // Bus frequency in Hz (typically 100kHz)

    // ============================================
    // INTERNAL PROTOCOL EXECUTION
    // ============================================
    // Execute command-based protocol (SHT31 style)
    // 1. Write command bytes
    // 2. Wait for conversion
    // 3. Read data directly (no register)
    bool executeCommandBasedProtocol(const I2CSensorProtocol* protocol,
                                     uint8_t i2c_address,
                                     uint8_t* buffer,
                                     size_t buffer_size,
                                     size_t& bytes_read);

    // Execute register-based protocol (BMP280 style)
    // 1. Write register address
    // 2. Read data bytes
    bool executeRegisterBasedProtocol(const I2CSensorProtocol* protocol,
                                      uint8_t i2c_address,
                                      uint8_t* buffer,
                                      size_t buffer_size,
                                      size_t& bytes_read);

    // Validate all CRCs in buffer according to protocol
    bool validateInterleavedCRC(const I2CSensorProtocol* protocol,
                                const uint8_t* buffer,
                                size_t buffer_len);

    // Validate CRC8 with configurable polynomial
    // polynomial: CRC polynomial (0x31 for Sensirion)
    // init_value: Initial CRC value (0xFF for Sensirion)
    bool validateCRC8(const uint8_t* data, size_t data_len,
                      uint8_t expected_crc, uint8_t polynomial, uint8_t init_value);

    // Calculate CRC8 (table-based for 0x31, bit-by-bit for others)
    uint8_t calculateCRC8(const uint8_t* data, size_t len,
                          uint8_t polynomial, uint8_t init_value);

    // SAFETY-RTOS M4: Same as readRaw() but does NOT take g_i2c_mutex.
    // Caller MUST already hold g_i2c_mutex (e.g. readSensorRaw → executeRegisterBasedProtocol).
    bool readRawLocked(uint8_t device_address, uint8_t register_address,
                       uint8_t* buffer, size_t length);
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
extern I2CBusManager& i2cBusManager;

#endif // DRIVERS_I2C_BUS_H
