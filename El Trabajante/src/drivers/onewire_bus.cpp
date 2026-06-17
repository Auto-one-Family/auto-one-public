#include "onewire_bus.h"
#include "../utils/logger.h"
#include "../drivers/gpio_manager.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"
#include "../tasks/rtos_globals.h"  // SAFETY-RTOS M4.3: g_onewire_mutex (scan on Core 0 vs read on Core 1)
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

// ============================================
// CONDITIONAL HARDWARE CONFIGURATION INCLUDES
// ============================================
#ifdef XIAO_ESP32C3
    #include "../config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "../config/hardware/esp32_s3_devkit.h"
#else
    #include "../config/hardware/esp32_dev.h"
#endif

// ESP-IDF TAG convention for structured logging
static const char* TAG = "ONEWIRE";

// ============================================
// GLOBAL INSTANCE
// ============================================
OneWireBusManager& oneWireBusManager = OneWireBusManager::getInstance();

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool OneWireBusManager::begin(uint8_t pin) {
    // ============================================
    // PIN SELECTION: Override oder Default (BEFORE init check!)
    // ============================================
    uint8_t requested_pin;
    if (pin != 0 && pin <= 39) {  // ESP32 hat GPIO 0-39
        requested_pin = pin;
    } else {
        requested_pin = HardwareConfig::DEFAULT_ONEWIRE_PIN;
    }

    // ============================================
    // DOUBLE-INIT CHECK: Same pin OK, different pin ERROR
    // ============================================
    if (initialized_) {
        // Same pin → OK, bus already active
        if (requested_pin == pin_) {
            LOG_D(TAG, "OneWire: Already initialized on GPIO " + String(pin_) + ", reusing bus");
            return true;
        }
        
        // Different pin → ERROR (Single-Bus-Design!)
        // Cannot switch OneWire bus to different pin without calling end() first
        LOG_E(TAG, "OneWire: Bus active on GPIO " + String(pin_) + 
                 ", cannot switch to GPIO " + String(requested_pin) + 
                 " (Single-Bus-Design - call end() first if pin change needed)");
        errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED,
                               ERROR_SEVERITY_ERROR,
                               ("Pin conflict: active=" + String(pin_) + ", requested=" + String(requested_pin)).c_str());
        return false;
    }

    LOG_I(TAG, "OneWire Bus Manager initialization started");

    if (xSemaphoreTake(g_onewire_mutex, portMAX_DELAY) != pdTRUE) {
        LOG_W(TAG, "OneWire: Mutex unavailable — init aborted");
        return false;
    }

    // ============================================
    // PIN ASSIGNMENT
    // ============================================
    pin_ = requested_pin;
    if (pin != 0 && pin <= 39) {
        LOG_I(TAG, "OneWireBus: Using configured pin GPIO " + String(pin_));
    } else {
        LOG_I(TAG, "OneWireBus: Using hardware default pin GPIO " + String(pin_));
        #ifdef WOKWI_SIMULATION
            LOG_D(TAG, "  (Wokwi mode - using diagram.json pin configuration)");
        #endif
    }

    LOG_D(TAG, "OneWire Config: Pin=" + String(pin_));

    // ============================================
    // GPIO SAFETY VALIDATION
    // ============================================
    // Use bus-sharing owner format: "bus/onewire/{pin}"
    // This allows SensorManager to recognize the pin as a shared OneWire bus
    String bus_owner = "bus/onewire/" + String(pin_);
    if (!gpioManager.requestPin(pin_, bus_owner.c_str(), "OneWireBus")) {
        LOG_E(TAG, "Failed to reserve OneWire pin " + String(pin_));
        errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED,
                               ERROR_SEVERITY_CRITICAL,
                               ("Pin reservation failed: GPIO " + String(pin_)).c_str());
        xSemaphoreGive(g_onewire_mutex);
        return false;
    }
    
    // Initialize OneWire library
    onewire_ = new OneWire(pin_);
    
    if (onewire_ == nullptr) {
        LOG_E(TAG, "OneWire object allocation failed");
        errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED,
                               ERROR_SEVERITY_CRITICAL,
                               "Memory allocation failed");
        gpioManager.releasePin(pin_);
        xSemaphoreGive(g_onewire_mutex);
        return false;
    }
    
    // Verify bus is functional by attempting a reset
    if (!onewire_->reset()) {
        LOG_W(TAG, "OneWire bus reset failed - no devices present or bus error");
        // This is not necessarily an error - just means no devices connected yet
    }
    
    initialized_ = true;
    
    LOG_I(TAG, "OneWire Bus Manager initialized successfully");
    LOG_I(TAG, "  Board: " + String(BOARD_TYPE));
    LOG_I(TAG, "  Pin: GPIO " + String(pin_));

    xSemaphoreGive(g_onewire_mutex);
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void OneWireBusManager::end() {
    if (!initialized_) {
        LOG_W(TAG, "OneWire bus not initialized, nothing to end");
        return;
    }

    if (xSemaphoreTake(g_onewire_mutex, portMAX_DELAY) != pdTRUE) {
        LOG_W(TAG, "OneWire: Mutex unavailable — end() skipped");
        return;
    }
    
    LOG_I(TAG, "OneWire Bus Manager shutdown initiated");
    
    // Delete OneWire object
    if (onewire_ != nullptr) {
        delete onewire_;
        onewire_ = nullptr;
    }
    
    // Release GPIO pin (return to safe mode)
    gpioManager.releasePin(pin_);
    
    initialized_ = false;
    
    LOG_I(TAG, "OneWire Bus Manager shutdown complete");
    xSemaphoreGive(g_onewire_mutex);
}

// ============================================
// DEVICE DISCOVERY
// ============================================
bool OneWireBusManager::scanDevices(uint8_t rom_codes[][8], uint8_t max_devices, uint8_t& found_count) {
    if (!initialized_ || onewire_ == nullptr) {
        LOG_E(TAG, "OneWire bus not initialized");
        return false;
    }

    if (xSemaphoreTake(g_onewire_mutex, portMAX_DELAY) != pdTRUE) {
        LOG_W(TAG, "OneWire: Mutex unavailable — scan skipped");
        return false;
    }
    
    LOG_I(TAG, "OneWire bus scan started");
    
    found_count = 0;
    
    // Reset search
    onewire_->reset_search();
    
    // Search for devices
    uint8_t rom[8];
    while (onewire_->search(rom)) {
        // Check CRC
        if (OneWire::crc8(rom, 7) != rom[7]) {
            LOG_W(TAG, "OneWire CRC error - device ignored");
            continue;
        }
        
        // Store ROM code
        if (found_count < max_devices) {
            for (uint8_t i = 0; i < 8; i++) {
                rom_codes[found_count][i] = rom[i];
            }
            
            LOG_I(TAG, "  Found device: Family=0x" + String(rom[0], HEX) + 
                     " Serial=" + String((rom[6] << 8) | rom[5], HEX));
            
            found_count++;
        } else {
            LOG_W(TAG, "  Device found but buffer full - increase max_devices");
        }
    }
    
    if (found_count == 0) {
        LOG_W(TAG, "OneWire bus scan complete: No devices found");
        errorTracker.trackError(ERROR_ONEWIRE_NO_DEVICES,
                               ERROR_SEVERITY_WARNING,
                               "No devices found on bus");
    } else {
        LOG_I(TAG, "OneWire bus scan complete: " + String(found_count) + " devices found");
    }

    xSemaphoreGive(g_onewire_mutex);
    return true;
}

// ============================================
// DEVICE PRESENCE CHECK
// ============================================
bool OneWireBusManager::isDevicePresent(const uint8_t rom_code[8]) {
    if (!initialized_ || onewire_ == nullptr) {
        LOG_E(TAG, "OneWire bus not initialized");
        return false;
    }

    if (xSemaphoreTake(g_onewire_mutex, portMAX_DELAY) != pdTRUE) {
        LOG_W(TAG, "OneWire: Mutex unavailable — isDevicePresent skipped");
        return false;
    }
    
    // Reset search and try to find this specific device
    onewire_->reset_search();
    
    uint8_t rom[8];
    while (onewire_->search(rom)) {
        // Compare ROM codes
        bool match = true;
        for (uint8_t i = 0; i < 8; i++) {
            if (rom[i] != rom_code[i]) {
                match = false;
                break;
            }
        }
        
        if (match) {
            xSemaphoreGive(g_onewire_mutex);
            return true;
        }
    }

    xSemaphoreGive(g_onewire_mutex);
    return false;
}

// ============================================
// RAW TEMPERATURE READING (PI-ENHANCED MODE)
// ============================================
bool OneWireBusManager::readRawTemperature(const uint8_t rom_code[8], int16_t& raw_value) {
    if (!initialized_ || onewire_ == nullptr) {
        LOG_E(TAG, "OneWire bus not initialized");
        errorTracker.trackError(ERROR_ONEWIRE_READ_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Read failed: bus not initialized");
        return false;
    }

    if (xSemaphoreTake(g_onewire_mutex, portMAX_DELAY) != pdTRUE) {
        LOG_W(TAG, "OneWire: Mutex unavailable — read skipped");
        return false;
    }
    
    // Verify device is present
    if (!onewire_->reset()) {
        LOG_E(TAG, "OneWire reset failed - no devices on bus");
        errorTracker.trackError(ERROR_ONEWIRE_READ_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Bus reset failed");
        xSemaphoreGive(g_onewire_mutex);
        return false;
    }
    
    // Select device
    onewire_->select(rom_code);

    // Start temperature conversion (0x44)
    // External VCC: parasitic power bit = 0. Conversion time up to 750 ms @ 12-bit (datasheet).
    // Wokwi: the virtual DS18B20 updates the scratchpad only after conversion completes; a short
    // delay (e.g. 10 ms) reads stale/garbage bytes → scratchpad CRC8 check fails while ROM scan
    // still works. Match real timing here (same as non-Wokwi path, minus strong pullup).
    #ifdef WOKWI_SIMULATION
        onewire_->write(0x44, 0);
        delay(750);
    #else
        onewire_->write(0x44, 1);  // 1 = parasitic power (strong pullup after write)
        delay(750);
    #endif
    
    // Reset and select device again
    if (!onewire_->reset()) {
        LOG_E(TAG, "OneWire reset failed after conversion");
        errorTracker.trackError(ERROR_ONEWIRE_READ_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Bus reset failed after conversion");
        xSemaphoreGive(g_onewire_mutex);
        return false;
    }
    
    onewire_->select(rom_code);
    
    // Read scratchpad (0xBE)
    onewire_->write(0xBE);
    
    // Read 9 bytes (scratchpad)
    uint8_t scratchpad[9];
    for (uint8_t i = 0; i < 9; i++) {
        scratchpad[i] = onewire_->read();
    }
    
    // Verify CRC
    if (OneWire::crc8(scratchpad, 8) != scratchpad[8]) {
        LOG_E(TAG, "OneWire CRC error on temperature read");
        errorTracker.trackError(ERROR_ONEWIRE_READ_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "CRC validation failed");
        xSemaphoreGive(g_onewire_mutex);
        return false;
    }
    
    // Extract raw temperature value (12-bit signed)
    // Temp is in bytes 0 (LSB) and 1 (MSB)
    raw_value = (scratchpad[1] << 8) | scratchpad[0];
    
    // Raw value is in 1/16th degree units
    // Range: -550 to +1250 (-55.0°C to +125.0°C)
    // Conversion formula (done on server): temp_celsius = raw_value * 0.0625
    
    LOG_D(TAG, "OneWire raw temperature: " + String(raw_value) + 
              " (will be processed by God-Kaiser)");

    xSemaphoreGive(g_onewire_mutex);
    return true;
}

// ============================================
// STATUS QUERIES
// ============================================
String OneWireBusManager::getBusStatus() const {
    String status = "OneWire[";
    status += "Pin:" + String(pin_);
    status += ",Init:" + String(initialized_ ? "true" : "false");
    status += "]";
    return status;
}
