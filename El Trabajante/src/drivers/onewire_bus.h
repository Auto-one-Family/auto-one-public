#ifndef DRIVERS_ONEWIRE_BUS_H
#define DRIVERS_ONEWIRE_BUS_H

#include <Arduino.h>
#include <OneWire.h>

// ============================================
// OneWire Bus Manager - Hardware Abstraction Layer
// ============================================
// Phase 3: Hardware Abstraction Layer
// Documentation: Phase_3.md lines 237-321
// Architecture: Server-Centric (Pi-Enhanced Mode)
//
// Purpose: OneWire bus control for DS18B20 temperature sensors
// - Board-agnostic OneWire initialization
// - Device discovery (ROM codes)
// - Raw temperature reading for Pi-Enhanced processing
// - NO local temperature conversion (Server-Centric!)

// ============================================
// ONEWIRE BUS MANAGER CLASS
// ============================================
// Singleton class managing OneWire bus operations

class OneWireBusManager {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static OneWireBusManager& getInstance() {
        static OneWireBusManager instance;
        return instance;
    }

    // Prevent copy and move operations
    OneWireBusManager(const OneWireBusManager&) = delete;
    OneWireBusManager& operator=(const OneWireBusManager&) = delete;
    OneWireBusManager(OneWireBusManager&&) = delete;
    OneWireBusManager& operator=(OneWireBusManager&&) = delete;

    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize OneWire bus with optional pin override
    // pin: GPIO pin for OneWire bus (0 = use hardware default)
    // Reserves pin via GPIOManager
    // Returns false if initialization fails
    //
    // Pin Selection Priority:
    // 1. pin parameter (if != 0)
    // 2. HardwareConfig::DEFAULT_ONEWIRE_PIN
    //
    // Example:
    //   oneWireBusManager.begin();      // Use default pin (GPIO 4 on ESP32 Dev)
    //   oneWireBusManager.begin(21);    // Override to GPIO 21
    bool begin(uint8_t pin = 0);

    // Deinitialize OneWire bus and release pin
    void end();

    // ============================================
    // DEVICE DISCOVERY
    // ============================================
    // Scan OneWire bus for connected devices
    // rom_codes: Array of 8-byte ROM codes [max_devices][8]
    // max_devices: Maximum number of devices to scan
    // found_count: Output parameter with number of found devices
    // Returns false if scan fails
    bool scanDevices(uint8_t rom_codes[][8], uint8_t max_devices, uint8_t& found_count);

    // Check if a specific device is present on bus
    // rom_code: 8-byte ROM code of device
    // Returns true if device responds
    bool isDevicePresent(const uint8_t rom_code[8]);

    // ============================================
    // RAW TEMPERATURE READING (PI-ENHANCED MODE)
    // ============================================
    // Read raw temperature value from DS18B20
    // rom_code: 8-byte ROM code of device
    // raw_value: Output 12-bit signed temperature value
    //            Range: -550 to +1250 (represents -55.0°C to +125.0°C)
    //            Resolution: 0.0625°C per LSB
    // Returns false if device not found or read fails
    //
    // IMPORTANT: NO local conversion to °C!
    // Raw value is sent to God-Kaiser for processing
    bool readRawTemperature(const uint8_t rom_code[8], int16_t& raw_value);

    // ============================================
    // STATUS QUERIES
    // ============================================
    // Check if OneWire bus is initialized
    bool isInitialized() const { return initialized_; }

    // Get current OneWire pin (for debugging/verification)
    // Returns 0 if not initialized
    uint8_t getPin() const { return pin_; }

    // Get detailed bus status for debugging
    // Format: "OneWire[Pin:6,Init:true]"
    String getBusStatus() const;

private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    OneWireBusManager() 
        : onewire_(nullptr),
          initialized_(false), 
          pin_(0) {}
    
    ~OneWireBusManager() {
        if (onewire_ != nullptr) {
            delete onewire_;
        }
    }

    // ============================================
    // INTERNAL STATE
    // ============================================
    OneWire* onewire_;      // OneWire library instance
    bool initialized_;      // Bus initialization status
    uint8_t pin_;           // OneWire pin (from HardwareConfig)
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
extern OneWireBusManager& oneWireBusManager;

#endif // DRIVERS_ONEWIRE_BUS_H
