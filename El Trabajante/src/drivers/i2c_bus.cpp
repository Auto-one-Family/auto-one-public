#include "i2c_bus.h"
#include "i2c_sensor_protocol.h"
#include <cstring>
#include "../utils/logger.h"
#include "../drivers/gpio_manager.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"
#include "../tasks/rtos_globals.h"  // SAFETY-RTOS M4: g_i2c_mutex

// ============================================
// I2C BUS RECOVERY CONFIGURATION
// ============================================
// Maximum recovery attempts within cooldown period
constexpr uint8_t I2C_MAX_RECOVERY_ATTEMPTS = 3;
// Reset recovery counter after this time (ms)
constexpr unsigned long I2C_RECOVERY_COOLDOWN_MS = 60000;  // 1 minute

// Recovery state tracking (persistent across calls)
static uint8_t i2c_recovery_attempt_count = 0;
static unsigned long i2c_last_recovery_time = 0;

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
static const char* TAG = "I2C";

// ============================================
// GLOBAL INSTANCE
// ============================================
I2CBusManager& i2cBusManager = I2CBusManager::getInstance();

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool I2CBusManager::begin() {
    // Prevent double initialization
    if (initialized_) {
        LOG_W(TAG, "I2C bus already initialized");
        return true;
    }

    LOG_I(TAG, "I2C Bus Manager initialization started");
    
    // Load hardware-specific configuration
    sda_pin_ = HardwareConfig::I2C_SDA_PIN;
    scl_pin_ = HardwareConfig::I2C_SCL_PIN;
    frequency_ = HardwareConfig::I2C_FREQUENCY;
    
    LOG_D(TAG, "I2C Config: SDA=" + String(sda_pin_) + 
              ", SCL=" + String(scl_pin_) + 
              ", Freq=" + String(frequency_) + "Hz");
    
    auto ensure_system_reservation = [&](uint8_t pin, const char* component_label) -> bool {
        GPIOPinInfo info = gpioManager.getPinInfo(pin);
        if (info.pin == 255) {
            String msg = "GPIO " + String(pin) + " not tracked by GPIOManager";
            LOG_E(TAG, "I2C pin verification failed: " + msg);
            errorTracker.trackError(ERROR_I2C_INIT_FAILED,
                                    ERROR_SEVERITY_CRITICAL,
                                    msg.c_str());
            return false;
        }

        bool owned_by_system = (strncmp(info.owner, "system", sizeof(info.owner)) == 0) &&
                               (strncmp(info.component_name, component_label,
                                        sizeof(info.component_name)) == 0);

        if (!owned_by_system) {
            if (info.owner[0] == '\0') {
                if (!gpioManager.requestPin(pin, "system", component_label)) {
                    String msg = "GPIO " + String(pin) + " reservation failed";
                    LOG_E(TAG, "I2C pin reservation failed: " + msg);
                    errorTracker.trackError(ERROR_I2C_INIT_FAILED,
                                            ERROR_SEVERITY_CRITICAL,
                                            msg.c_str());
                    return false;
                }
            } else {
                String msg = "GPIO " + String(pin) + " owned by " +
                             String(info.owner) + "/" + String(info.component_name);
                LOG_E(TAG, "I2C pin conflict: " + msg);
                errorTracker.trackError(ERROR_I2C_INIT_FAILED,
                                        ERROR_SEVERITY_CRITICAL,
                                        msg.c_str());
                return false;
            }
        }
        return true;
    };

    if (!ensure_system_reservation(sda_pin_, "I2C_SDA") ||
        !ensure_system_reservation(scl_pin_, "I2C_SCL")) {
        return false;
    }
    
    // Initialize I2C hardware
    bool wire_init = Wire.begin(sda_pin_, scl_pin_, frequency_);
    
    if (!wire_init) {
        LOG_E(TAG, "I2C Wire.begin() failed");
        errorTracker.trackError(ERROR_I2C_INIT_FAILED,
                               ERROR_SEVERITY_CRITICAL,
                               "Wire.begin() returned false");
        return false;
    }

    // Set Wire timeout to prevent indefinite blocking on unresponsive sensors
    Wire.setTimeOut(100);  // 100ms timeout for Wire operations

    // Verify I2C bus is functional by attempting a quick scan
    Wire.beginTransmission(0x00);  // General call address
    uint8_t error = Wire.endTransmission();
    
    // Error code 2 is expected (NACK on general call) - bus is functional
    // Error code 4 would indicate bus failure
    if (error == 4) {
        LOG_E(TAG, "I2C bus error: Bus not functional");
        errorTracker.trackError(ERROR_I2C_BUS_ERROR, 
                               ERROR_SEVERITY_CRITICAL,
                               "I2C bus verification failed");
        Wire.end();
        return false;
    }
    
    initialized_ = true;
    
    LOG_I(TAG, "I2C Bus Manager initialized successfully");
    LOG_I(TAG, "  Board: " + String(BOARD_TYPE));
    LOG_I(TAG, "  SDA: GPIO " + String(sda_pin_));
    LOG_I(TAG, "  SCL: GPIO " + String(scl_pin_));
    LOG_I(TAG, "  Frequency: " + String(frequency_ / 1000) + " kHz");
    
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void I2CBusManager::end() {
    if (!initialized_) {
        LOG_W(TAG, "I2C bus not initialized, nothing to end");
        return;
    }
    
    LOG_I(TAG, "I2C Bus Manager shutdown initiated");
    
    // Deinitialize Wire library
    Wire.end();
    
    // Release GPIO pins (return to safe mode)
    gpioManager.releasePin(sda_pin_);
    gpioManager.releasePin(scl_pin_);
    
    initialized_ = false;
    
    LOG_I(TAG, "I2C Bus Manager shutdown complete");
}

// ============================================
// BUS SCANNING
// ============================================
bool I2CBusManager::scanBus(uint8_t addresses[], uint8_t max_addresses, uint8_t& found_count) {
    if (!initialized_) {
        LOG_E(TAG, "I2C bus not initialized");
        return false;
    }

    if (addresses == nullptr) {
        LOG_E(TAG, "I2C bus scan requires a valid address buffer");
        return false;
    }

    if (max_addresses == 0) {
        LOG_E(TAG, "I2C bus scan called with max_addresses = 0");
        return false;
    }

    LOG_I(TAG, "I2C bus scan started (0x08-0x77)");

    // SAFETY-RTOS M4: Wire is not thread-safe — hold mutex for entire scan.
    if (xSemaphoreTake(g_i2c_mutex, pdMS_TO_TICKS(250)) != pdTRUE) {
        LOG_W(TAG, "I2C: Mutex timeout — skipping bus scan");
        return false;
    }

    found_count = 0;
    uint8_t detected = 0;

    // Scan I2C address range (0x08-0x77)
    // Addresses 0x00-0x07 and 0x78-0x7F are reserved
    for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
        Wire.beginTransmission(addr);
        uint8_t error = Wire.endTransmission();

        if (error == 0) {
            // Device found
            detected++;
            if (found_count < max_addresses) {
                addresses[found_count++] = addr;
                LOG_I(TAG, "  Found device at 0x" + String(addr, HEX));
            } else {
                LOG_W(TAG, "  Device at 0x" + String(addr, HEX) + " ignored (buffer full)");
            }
        } else if (error == 4 || error == 5) {
            LOG_W(TAG, "  Bus error while probing 0x" + String(addr, HEX) + " (code " + String(error) + ")");
        }

        delay(1);  // Small delay between scans
    }

    xSemaphoreGive(g_i2c_mutex);

    if (detected > found_count) {
        LOG_W(TAG, "I2C bus scan truncated results (" + String(detected) + " detected, " +
                    String(found_count) + " stored)");
    } else {
        LOG_I(TAG, "I2C bus scan complete: " + String(found_count) + " devices found");
    }

    return true;
}

// ============================================
// DEVICE PRESENCE CHECK
// ============================================
bool I2CBusManager::isDevicePresent(uint8_t address) {
    if (!initialized_) {
        LOG_E(TAG, "I2C bus not initialized");
        return false;
    }
    
    if (address < 0x08 || address > 0x77) {
        LOG_E(TAG, "Invalid I2C address: 0x" + String(address, HEX));
        return false;
    }

    // SAFETY-RTOS M4: Wire is not thread-safe.
    if (xSemaphoreTake(g_i2c_mutex, pdMS_TO_TICKS(250)) != pdTRUE) {
        LOG_W(TAG, "I2C: Mutex timeout — skipping isDevicePresent 0x" + String(address, HEX));
        return false;
    }
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    xSemaphoreGive(g_i2c_mutex);

    return (error == 0);
}

// ============================================
// RAW DATA READING
// ============================================
bool I2CBusManager::readRawLocked(uint8_t device_address, uint8_t register_address,
                                  uint8_t* buffer, size_t length) {
    // Preconditions: initialized_, valid buffer/address — checked by readRaw() or readSensorRaw().
    // g_i2c_mutex MUST be held (Wire is not thread-safe).

    Wire.beginTransmission(device_address);
    Wire.write(register_address);
    uint8_t error = Wire.endTransmission(false);  // false = repeated start

    if (error == 4 || error == 5) {
        LOG_W(TAG, "I2C bus error detected (code " + String(error) +
                    ") while addressing device 0x" + String(device_address, HEX));

        if (attemptRecoveryIfNeeded(error)) {
            LOG_D(TAG, "I2C: Retrying read after recovery...");

            Wire.beginTransmission(device_address);
            Wire.write(register_address);
            error = Wire.endTransmission(false);

            if (error == 0) {
                LOG_D(TAG, "I2C: Retry successful after recovery");
            } else {
                LOG_E(TAG, "I2C: Retry failed after recovery (error " + String(error) + ")");
                errorTracker.trackError(ERROR_I2C_BUS_ERROR, ERROR_SEVERITY_CRITICAL,
                                       ("I2C retry failed: device 0x" + String(device_address, HEX)).c_str());
                return false;
            }
        } else {
            LOG_E(TAG, "I2C: Recovery not possible or failed");
            errorTracker.trackError(ERROR_I2C_BUS_ERROR, ERROR_SEVERITY_CRITICAL,
                                   ("I2C bus error: device 0x" + String(device_address, HEX)).c_str());
            return false;
        }
    } else if (error != 0) {
        LOG_E(TAG, "I2C write register failed: device 0x" + String(device_address, HEX) +
                  ", error " + String(error));
        errorTracker.trackError(ERROR_I2C_DEVICE_NOT_FOUND, ERROR_SEVERITY_WARNING,
                               ("Device 0x" + String(device_address, HEX) + " not responding").c_str());
        return false;
    }

    LOG_D(TAG, "I2C: requestFrom START addr=0x" + String(device_address, HEX) + " bytes=" + String(length));
    size_t received = Wire.requestFrom(device_address, (uint8_t)length);
    LOG_D(TAG, "I2C: requestFrom END received=" + String(received));

    if (received != length) {
        LOG_E(TAG, "I2C read: Expected " + String(length) + " bytes, got " + String(received));
        String msg = "Incomplete read from 0x" + String(device_address, HEX);
        errorTracker.trackError(ERROR_I2C_READ_FAILED,
                               ERROR_SEVERITY_ERROR,
                               msg.c_str());
        return false;
    }

    for (size_t i = 0; i < length; i++) {
        buffer[i] = Wire.read();
    }

    LOG_D(TAG, "I2C read: " + String(length) + " bytes from 0x" +
              String(device_address, HEX) + " reg 0x" + String(register_address, HEX));

    return true;
}

bool I2CBusManager::readRaw(uint8_t device_address, uint8_t register_address,
                            uint8_t* buffer, size_t length) {
    if (!initialized_) {
        LOG_E(TAG, "I2C bus not initialized");
        errorTracker.trackError(ERROR_I2C_READ_FAILED, 
                               ERROR_SEVERITY_ERROR,
                               "Read failed: bus not initialized");
        return false;
    }
    
    if (buffer == nullptr || length == 0) {
        LOG_E(TAG, "I2C read: Invalid buffer or length");
        return false;
    }

    if (device_address < 0x08 || device_address > 0x77) {
        LOG_E(TAG, "I2C read: Invalid address 0x" + String(device_address, HEX));
        return false;
    }
    
    // SAFETY-RTOS M4: Wire is not thread-safe.
    if (xSemaphoreTake(g_i2c_mutex, pdMS_TO_TICKS(250)) != pdTRUE) {
        LOG_W(TAG, "I2C: Mutex timeout — skipping read from 0x" + String(device_address, HEX));
        return false;
    }

    bool ok = readRawLocked(device_address, register_address, buffer, length);
    xSemaphoreGive(g_i2c_mutex);
    return ok;
}

// ============================================
// RAW DATA WRITING
// ============================================
bool I2CBusManager::writeRaw(uint8_t device_address, uint8_t register_address,
                             const uint8_t* data, size_t length) {
    if (!initialized_) {
        LOG_E(TAG, "I2C bus not initialized");
        errorTracker.trackError(ERROR_I2C_WRITE_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Write failed: bus not initialized");
        return false;
    }
    
    if (data == nullptr || length == 0) {
        LOG_E(TAG, "I2C write: Invalid data or length");
        return false;
    }

    if (device_address < 0x08 || device_address > 0x77) {
        LOG_E(TAG, "I2C write: Invalid address 0x" + String(device_address, HEX));
        return false;
    }

    // SAFETY-RTOS M4: Wire is not thread-safe.
    if (xSemaphoreTake(g_i2c_mutex, pdMS_TO_TICKS(250)) != pdTRUE) {
        LOG_W(TAG, "I2C: Mutex timeout — skipping write to 0x" + String(device_address, HEX));
        return false;
    }

    // Begin transmission
    Wire.beginTransmission(device_address);

    // Write register address
    Wire.write(register_address);

    // Write data bytes
    size_t written = Wire.write(data, length);

    if (written != length) {
        LOG_E(TAG, "I2C write: Expected to write " + String(length) + " bytes, wrote " + String(written));
        String msg = "Incomplete write to 0x" + String(device_address, HEX);
        errorTracker.trackError(ERROR_I2C_WRITE_FAILED,
                               ERROR_SEVERITY_ERROR,
                               msg.c_str());
        Wire.endTransmission();
        xSemaphoreGive(g_i2c_mutex);
        return false;
    }

    // End transmission
    uint8_t error = Wire.endTransmission();

    if (error != 0) {
        LOG_E(TAG, "I2C write failed: device 0x" + String(device_address, HEX) +
                  ", error " + String(error));
        uint16_t code = (error == 2 || error == 3) ? ERROR_I2C_DEVICE_NOT_FOUND :
                         (error == 4 || error == 5) ? ERROR_I2C_BUS_ERROR : ERROR_I2C_WRITE_FAILED;
        String msg = "Write error " + String(error) + " to 0x" + String(device_address, HEX);
        errorTracker.trackError(code,
                               (code == ERROR_I2C_BUS_ERROR) ? ERROR_SEVERITY_CRITICAL : ERROR_SEVERITY_ERROR,
                               msg.c_str());
        xSemaphoreGive(g_i2c_mutex);
        return false;
    }

    xSemaphoreGive(g_i2c_mutex);

    LOG_D(TAG, "I2C write: " + String(length) + " bytes to 0x" +
              String(device_address, HEX) + " reg 0x" + String(register_address, HEX));

    return true;
}

// ============================================
// ADS1115 EXTERNAL ADC (single-shot, single-ended)
// ============================================
bool I2CBusManager::readAds1115SingleEnded(uint8_t address, uint8_t channel,
                                           uint8_t pga_bits, uint16_t& raw_out) {
    raw_out = 0;

    if (!initialized_) {
        LOG_E(TAG, "ADS1115: I2C bus not initialized");
        return false;
    }
    if (channel > 3) {
        LOG_E(TAG, "ADS1115: invalid channel " + String(channel) + " (must be 0-3)");
        return false;
    }
    if (address < 0x48 || address > 0x4B) {
        LOG_W(TAG, "ADS1115: address 0x" + String(address, HEX) +
                   " outside expected range 0x48-0x4B");
    }

    // ADS1115 register pointers
    static constexpr uint8_t ADS1115_REG_CONVERSION = 0x00;
    static constexpr uint8_t ADS1115_REG_CONFIG     = 0x01;

    // Build config word:
    //  OS[15]=1 (start single-shot) · MUX[14:12]=100..111 (single-ended AIN0..AIN3)
    //  PGA[11:9]=gain bits · MODE[8]=1 (single-shot) · DR[7:5]=100 (128 SPS)
    //  COMP_QUE[1:0]=11 (comparator disabled). Example AIN0/+-4.096V => 0xC383.
    const uint16_t mux = static_cast<uint16_t>(0b100u + channel);
    const uint16_t pga = static_cast<uint16_t>(pga_bits > 5 ? 1 : pga_bits);
    const uint16_t config = static_cast<uint16_t>(
        (1u << 15) | (mux << 12) | (pga << 9) |
        (1u << 8)  | (0b100u << 5) | 0b00000011u);

    const uint8_t cfg_bytes[2] = {
        static_cast<uint8_t>((config >> 8) & 0xFF),
        static_cast<uint8_t>(config & 0xFF),
    };

    // Start conversion (write config). On NACK retry once before giving up.
    if (!writeRaw(address, ADS1115_REG_CONFIG, cfg_bytes, 2)) {
        LOG_W(TAG, "ADS1115: config write NACK at 0x" + String(address, HEX) + " — retrying once");
        if (!writeRaw(address, ADS1115_REG_CONFIG, cfg_bytes, 2)) {
            LOG_E(TAG, "ADS1115: config write failed at 0x" + String(address, HEX));
            return false;
        }
    }

    // Poll OS bit (config[15]) until conversion done. 128 SPS ~ 7.8 ms; the
    // bounded timeout never blocks indefinitely, and delay(1) yields to the
    // RTOS (feeds the idle watchdog) — far below the inter-sample delay used by
    // the analog median sampler, so the safety regulation path is not starved.
    static constexpr uint32_t ADS1115_CONVERSION_TIMEOUT_MS = 25;
    uint8_t cfg_read[2] = {0, 0};
    const uint32_t start_ms = millis();
    bool ready = false;
    while ((millis() - start_ms) < ADS1115_CONVERSION_TIMEOUT_MS) {
        if (readRaw(address, ADS1115_REG_CONFIG, cfg_read, 2)) {
            if (cfg_read[0] & 0x80) {  // OS bit set -> conversion complete
                ready = true;
                break;
            }
        }
        delay(1);
    }
    if (!ready) {
        LOG_W(TAG, "ADS1115: conversion timeout at 0x" + String(address, HEX) +
                   " ch" + String(channel) + " — skipping sample");
        return false;
    }

    // Read conversion register (2 bytes, MSB first).
    uint8_t conv[2] = {0, 0};
    if (!readRaw(address, ADS1115_REG_CONVERSION, conv, 2)) {
        LOG_E(TAG, "ADS1115: conversion read failed at 0x" + String(address, HEX));
        return false;
    }

    const int16_t signed_raw = static_cast<int16_t>((conv[0] << 8) | conv[1]);
    // Single-ended positive range is 0..32767; negative codes are noise -> clamp.
    raw_out = signed_raw < 0 ? 0 : static_cast<uint16_t>(signed_raw);

    LOG_D(TAG, "ADS1115: 0x" + String(address, HEX) + " ch" + String(channel) +
              " pgabits=" + String(pga_bits) + " raw=" + String(raw_out));
    return true;
}

// ============================================
// I2C BUS RECOVERY
// ============================================
bool I2CBusManager::recoverBus() {
    LOG_W(TAG, "I2C: Bus recovery initiated (attempt " +
                String(i2c_recovery_attempt_count + 1) + "/" +
                String(I2C_MAX_RECOVERY_ATTEMPTS) + ")");

    errorTracker.trackError(
        ERROR_I2C_BUS_RECOVERY_STARTED,
        ERROR_SEVERITY_WARNING,
        "I2C bus recovery initiated"
    );

    // Step 1: End current I2C session
    Wire.end();
    delay(10);

    // Step 2: Manual clock pulse to release stuck slaves
    // If a slave is holding SDA low, clocking SCL can release it
    // This is the standard I2C bus recovery procedure (9 clock pulses)
    pinMode(scl_pin_, OUTPUT);
    pinMode(sda_pin_, INPUT_PULLUP);  // Let SDA float with pull-up

    for (int i = 0; i < 9; i++) {
        digitalWrite(scl_pin_, LOW);
        delayMicroseconds(5);
        digitalWrite(scl_pin_, HIGH);
        delayMicroseconds(5);

        // Check if SDA is released
        if (digitalRead(sda_pin_) == HIGH) {
            LOG_D(TAG, "I2C: SDA released after " + String(i + 1) + " clock pulses");
            break;
        }
    }

    // Step 3: Generate STOP condition to reset all slaves
    // STOP = SDA rising while SCL is high
    pinMode(sda_pin_, OUTPUT);
    digitalWrite(sda_pin_, LOW);
    delayMicroseconds(5);
    digitalWrite(scl_pin_, HIGH);
    delayMicroseconds(5);
    digitalWrite(sda_pin_, HIGH);  // SDA high while SCL high = STOP
    delayMicroseconds(10);

    // Step 4: Re-initialize I2C
    if (!Wire.begin(sda_pin_, scl_pin_, frequency_)) {
        LOG_E(TAG, "I2C: Bus recovery failed - could not reinitialize");
        errorTracker.trackError(
            ERROR_I2C_BUS_RECOVERY_FAILED,
            ERROR_SEVERITY_ERROR,
            "I2C bus recovery failed: Wire.begin() returned false"
        );
        return false;
    }

    // Step 5: Verify bus is functional
    Wire.beginTransmission(0x00);  // General call address
    uint8_t error = Wire.endTransmission();

    // Error 2 (NACK) is expected, Error 4 means bus still broken
    if (error == 4) {
        LOG_E(TAG, "I2C: Bus still stuck after recovery attempt");
        errorTracker.trackError(
            ERROR_I2C_BUS_RECOVERY_FAILED,
            ERROR_SEVERITY_ERROR,
            "I2C bus still stuck after recovery"
        );
        return false;
    }

    LOG_I(TAG, "I2C: Bus recovery successful");
    errorTracker.trackError(
        ERROR_I2C_BUS_RECOVERED,
        ERROR_SEVERITY_WARNING,  // Warning level for visibility in logs
        "I2C bus recovered successfully"
    );

    return true;
}

bool I2CBusManager::attemptRecoveryIfNeeded(uint8_t error_code) {
    // Only attempt recovery for bus errors (4) and timeouts (5)
    if (error_code != 4 && error_code != 5) {
        return false;  // Not a recoverable error
    }

    LOG_W(TAG, "I2C: Bus error detected (code " + String(error_code) + "), checking recovery eligibility");

    // Check cooldown period - reset counter after 1 minute of no errors
    unsigned long now = millis();
    if (now - i2c_last_recovery_time > I2C_RECOVERY_COOLDOWN_MS) {
        i2c_recovery_attempt_count = 0;  // Reset counter
        LOG_D(TAG, "I2C: Recovery counter reset (cooldown expired)");
    }

    // Check if we've exceeded max attempts
    if (i2c_recovery_attempt_count >= I2C_MAX_RECOVERY_ATTEMPTS) {
        LOG_E(TAG, "I2C: Max recovery attempts (" + String(I2C_MAX_RECOVERY_ATTEMPTS) +
                  ") reached - bus disabled until cooldown");
        errorTracker.trackError(
            ERROR_I2C_BUS_ERROR,
            ERROR_SEVERITY_CRITICAL,
            "I2C bus permanently failed after max recovery attempts"
        );
        return false;
    }

    // Attempt recovery
    i2c_recovery_attempt_count++;
    i2c_last_recovery_time = now;

    return recoverBus();
}

// ============================================
// STATUS QUERIES
// ============================================
String I2CBusManager::getBusStatus() const {
    String status = "I2C[";
    status += "SDA:" + String(sda_pin_);
    status += ",SCL:" + String(scl_pin_);
    status += ",Freq:" + String(frequency_ / 1000) + "kHz";
    status += ",Init:" + String(initialized_ ? "true" : "false");
    status += ",RecoveryAttempts:" + String(i2c_recovery_attempt_count);
    status += "]";
    return status;
}

// ============================================
// CRC-8 LOOKUP TABLE (SENSIRION STANDARD)
// ============================================
// Polynomial: x^8 + x^5 + x^4 + 1 (0x31)
// Used by: SHT31, SHTC3, SHT4x, and other Sensirion sensors
// Reference: Sensirion Application Note
static const uint8_t CRC8_POLY31_TABLE[256] PROGMEM = {
    0x00, 0x31, 0x62, 0x53, 0xC4, 0xF5, 0xA6, 0x97,
    0xB9, 0x88, 0xDB, 0xEA, 0x7D, 0x4C, 0x1F, 0x2E,
    0x43, 0x72, 0x21, 0x10, 0x87, 0xB6, 0xE5, 0xD4,
    0xFA, 0xCB, 0x98, 0xA9, 0x3E, 0x0F, 0x5C, 0x6D,
    0x86, 0xB7, 0xE4, 0xD5, 0x42, 0x73, 0x20, 0x11,
    0x3F, 0x0E, 0x5D, 0x6C, 0xFB, 0xCA, 0x99, 0xA8,
    0xC5, 0xF4, 0xA7, 0x96, 0x01, 0x30, 0x63, 0x52,
    0x7C, 0x4D, 0x1E, 0x2F, 0xB8, 0x89, 0xDA, 0xEB,
    0x3D, 0x0C, 0x5F, 0x6E, 0xF9, 0xC8, 0x9B, 0xAA,
    0x84, 0xB5, 0xE6, 0xD7, 0x40, 0x71, 0x22, 0x13,
    0x7E, 0x4F, 0x1C, 0x2D, 0xBA, 0x8B, 0xD8, 0xE9,
    0xC7, 0xF6, 0xA5, 0x94, 0x03, 0x32, 0x61, 0x50,
    0xBB, 0x8A, 0xD9, 0xE8, 0x7F, 0x4E, 0x1D, 0x2C,
    0x02, 0x33, 0x60, 0x51, 0xC6, 0xF7, 0xA4, 0x95,
    0xF8, 0xC9, 0x9A, 0xAB, 0x3C, 0x0D, 0x5E, 0x6F,
    0x41, 0x70, 0x23, 0x12, 0x85, 0xB4, 0xE7, 0xD6,
    0x7A, 0x4B, 0x18, 0x29, 0xBE, 0x8F, 0xDC, 0xED,
    0xC3, 0xF2, 0xA1, 0x90, 0x07, 0x36, 0x65, 0x54,
    0x39, 0x08, 0x5B, 0x6A, 0xFD, 0xCC, 0x9F, 0xAE,
    0x80, 0xB1, 0xE2, 0xD3, 0x44, 0x75, 0x26, 0x17,
    0xFC, 0xCD, 0x9E, 0xAF, 0x38, 0x09, 0x5A, 0x6B,
    0x45, 0x74, 0x27, 0x16, 0x81, 0xB0, 0xE3, 0xD2,
    0xBF, 0x8E, 0xDD, 0xEC, 0x7B, 0x4A, 0x19, 0x28,
    0x06, 0x37, 0x64, 0x55, 0xC2, 0xF3, 0xA0, 0x91,
    0x47, 0x76, 0x25, 0x14, 0x83, 0xB2, 0xE1, 0xD0,
    0xFE, 0xCF, 0x9C, 0xAD, 0x3A, 0x0B, 0x58, 0x69,
    0x04, 0x35, 0x66, 0x57, 0xC0, 0xF1, 0xA2, 0x93,
    0xBD, 0x8C, 0xDF, 0xEE, 0x79, 0x48, 0x1B, 0x2A,
    0xC1, 0xF0, 0xA3, 0x92, 0x05, 0x34, 0x67, 0x56,
    0x78, 0x49, 0x1A, 0x2B, 0xBC, 0x8D, 0xDE, 0xEF,
    0x82, 0xB3, 0xE0, 0xD1, 0x46, 0x77, 0x24, 0x15,
    0x3B, 0x0A, 0x59, 0x68, 0xFF, 0xCE, 0x9D, 0xAC
};

// ============================================
// CRC-8 CALCULATION
// ============================================
uint8_t I2CBusManager::calculateCRC8(const uint8_t* data, size_t len,
                                      uint8_t polynomial, uint8_t init_value) {
    uint8_t crc = init_value;

    if (polynomial == 0x31) {
        // Table-based calculation for Sensirion polynomial (fast)
        for (size_t i = 0; i < len; i++) {
            crc = pgm_read_byte(&CRC8_POLY31_TABLE[crc ^ data[i]]);
        }
    } else {
        // Bit-by-bit calculation for other polynomials
        for (size_t i = 0; i < len; i++) {
            crc ^= data[i];
            for (uint8_t bit = 0; bit < 8; bit++) {
                if (crc & 0x80) {
                    crc = (crc << 1) ^ polynomial;
                } else {
                    crc <<= 1;
                }
            }
        }
    }

    return crc;
}

bool I2CBusManager::validateCRC8(const uint8_t* data, size_t data_len,
                                  uint8_t expected_crc, uint8_t polynomial,
                                  uint8_t init_value) {
    uint8_t calculated = calculateCRC8(data, data_len, polynomial, init_value);
    return (calculated == expected_crc);
}

// ============================================
// INTERLEAVED CRC VALIDATION
// ============================================
bool I2CBusManager::validateInterleavedCRC(const I2CSensorProtocol* protocol,
                                            const uint8_t* buffer,
                                            size_t buffer_len) {
    // Validate CRC for each value that has one
    for (uint8_t i = 0; i < protocol->value_count; i++) {
        const I2CValueExtraction* ve = &protocol->values[i];

        // Skip if no CRC for this value
        if (ve->crc_offset == 0xFF) {
            continue;
        }

        // Skip if CRC offset is out of bounds
        if (ve->crc_offset >= buffer_len) {
            continue;
        }

        // Skip if value bytes are out of bounds
        if (ve->byte_offset + ve->byte_count > buffer_len) {
            continue;
        }

        uint8_t expected_crc = buffer[ve->crc_offset];

        uint8_t calculated_crc = calculateCRC8(
            &buffer[ve->byte_offset], ve->byte_count,
            protocol->crc.polynomial, protocol->crc.init_value);

        if (calculated_crc != expected_crc) {
            char err[96];
            snprintf(err, sizeof(err),
                "I2C: CRC failed for %s (calc=0x%02X exp=0x%02X data=[%02X,%02X])",
                ve->value_type, calculated_crc, expected_crc,
                buffer[ve->byte_offset], buffer[ve->byte_offset + 1]);
            LOG_E(TAG, err);
            errorTracker.trackError(ERROR_I2C_CRC_FAILED, ERROR_SEVERITY_ERROR,
                                   ("CRC failed: " + String(ve->value_type)).c_str());
            return false;
        }
    }

    return true;
}

// ============================================
// PROTOCOL-AWARE SENSOR READING
// ============================================
bool I2CBusManager::readSensorRaw(const String& sensor_type, uint8_t i2c_address,
                                   uint8_t* buffer, size_t buffer_size,
                                   size_t& bytes_read) {
    bytes_read = 0;

    // Validation: Bus initialized
    if (!initialized_) {
        LOG_E(TAG, "I2C: Bus not initialized for sensor read");
        errorTracker.trackError(ERROR_I2C_READ_FAILED, ERROR_SEVERITY_ERROR,
                               "Bus not initialized for sensor read");
        return false;
    }

    // Validation: Buffer
    if (buffer == nullptr || buffer_size == 0) {
        LOG_E(TAG, "I2C: Invalid buffer for sensor read");
        return false;
    }

    // Find protocol
    const I2CSensorProtocol* protocol = findI2CSensorProtocol(sensor_type);
    if (protocol == nullptr) {
        LOG_E(TAG, "I2C: Unsupported sensor type: " + sensor_type);
        errorTracker.trackError(ERROR_I2C_PROTOCOL_UNSUPPORTED, ERROR_SEVERITY_ERROR,
                               ("Unsupported sensor: " + sensor_type).c_str());
        return false;
    }

    // Resolve address (use provided or default)
    uint8_t addr = (i2c_address != 0) ? i2c_address : protocol->default_i2c_address;

    // Validate address range
    if (addr < 0x08 || addr > 0x77) {
        LOG_E(TAG, "I2C: Invalid address 0x" + String(addr, HEX) + " for " + sensor_type);
        errorTracker.trackError(ERROR_I2C_DEVICE_NOT_FOUND, ERROR_SEVERITY_ERROR,
                               ("Invalid address 0x" + String(addr, HEX)).c_str());
        return false;
    }

    // Log if non-default address
    if (addr != protocol->default_i2c_address) {
        LOG_D(TAG, "I2C: Using non-default address 0x" + String(addr, HEX) +
                  " for " + sensor_type + " (default: 0x" +
                  String(protocol->default_i2c_address, HEX) + ")");
    }

    // Check buffer size
    if (buffer_size < protocol->expected_bytes) {
        LOG_E(TAG, "I2C: Buffer too small for " + sensor_type +
                  " (need " + String(protocol->expected_bytes) +
                  ", have " + String(buffer_size) + ")");
        return false;
    }

    LOG_D(TAG, "I2C: Reading " + sensor_type + " at 0x" + String(addr, HEX) +
              " (protocol: " + String((uint8_t)protocol->protocol_type) + ")");

    // SAFETY-RTOS M4: Wire is not thread-safe.
    // executeCommandBasedProtocol / executeRegisterBasedProtocol and their internal
    // attemptRecoveryIfNeeded calls are all within this mutex scope.
    if (xSemaphoreTake(g_i2c_mutex, pdMS_TO_TICKS(250)) != pdTRUE) {
        LOG_W(TAG, "I2C: Mutex timeout — skipping readSensorRaw for " + sensor_type);
        return false;
    }

    // Execute protocol based on type
    bool success = false;
    switch (protocol->protocol_type) {
        case I2CProtocolType::COMMAND_BASED:
            success = executeCommandBasedProtocol(protocol, addr, buffer,
                                                   buffer_size, bytes_read);
            break;

        case I2CProtocolType::REGISTER_BASED:
            success = executeRegisterBasedProtocol(protocol, addr, buffer,
                                                    buffer_size, bytes_read);
            break;

        case I2CProtocolType::BURST_READ:
            // Direct read without register - use requestFrom directly
            {
                size_t received = Wire.requestFrom(addr, (uint8_t)protocol->expected_bytes);
                if (received == protocol->expected_bytes) {
                    for (size_t i = 0; i < received; i++) {
                        buffer[i] = Wire.read();
                    }
                    bytes_read = received;
                    success = true;
                } else {
                    LOG_E(TAG, "I2C: Burst read failed for " + sensor_type);
                    errorTracker.trackError(ERROR_I2C_READ_FAILED, ERROR_SEVERITY_ERROR,
                                           ("Burst read failed: " + sensor_type).c_str());
                }
            }
            break;

        default:
            LOG_E(TAG, "I2C: Unknown protocol type for " + sensor_type);
            errorTracker.trackError(ERROR_I2C_PROTOCOL_UNSUPPORTED, ERROR_SEVERITY_ERROR,
                                   "Unknown protocol type");
            xSemaphoreGive(g_i2c_mutex);
            return false;
    }

    xSemaphoreGive(g_i2c_mutex);

    // Validate CRC if configured and read succeeded (no Wire access — outside mutex)
    if (success && protocol->crc.interleaved) {
        if (!validateInterleavedCRC(protocol, buffer, bytes_read)) {
            // Error already tracked in validateInterleavedCRC
            return false;
        }
    }

    if (success) {
        LOG_D(TAG, "I2C: " + sensor_type + " read successful (" +
                  String(bytes_read) + " bytes)");
    }

    return success;
}

// ============================================
// COMMAND-BASED PROTOCOL EXECUTION (SHT31)
// ============================================
bool I2CBusManager::executeCommandBasedProtocol(const I2CSensorProtocol* protocol,
                                                 uint8_t i2c_address,
                                                 uint8_t* buffer,
                                                 size_t buffer_size,
                                                 size_t& bytes_read) {
    // Step 1: Send command bytes
    Wire.beginTransmission(i2c_address);

    for (uint8_t i = 0; i < protocol->command_length; i++) {
        Wire.write(protocol->command_bytes[i]);
    }

    uint8_t error = Wire.endTransmission();

    if (error != 0) {
        // Handle bus errors with recovery
        if (error == 4 || error == 5) {
            if (attemptRecoveryIfNeeded(error)) {
                // Retry command after recovery
                LOG_D(TAG, "I2C: Retrying command after recovery...");
                Wire.beginTransmission(i2c_address);
                for (uint8_t i = 0; i < protocol->command_length; i++) {
                    Wire.write(protocol->command_bytes[i]);
                }
                error = Wire.endTransmission();

                if (error != 0) {
                    LOG_E(TAG, "I2C: Command retry failed for " + String(protocol->sensor_type));
                    errorTracker.trackError(ERROR_I2C_WRITE_FAILED, ERROR_SEVERITY_ERROR,
                                           ("Command retry failed: " + String(protocol->sensor_type)).c_str());
                    return false;
                }
            } else {
                LOG_E(TAG, "I2C: Bus error sending command to " + String(protocol->sensor_type));
                errorTracker.trackError(ERROR_I2C_BUS_ERROR, ERROR_SEVERITY_CRITICAL,
                                       ("Bus error: " + String(protocol->sensor_type)).c_str());
                return false;
            }
        } else {
            LOG_E(TAG, "I2C: Command failed for " + String(protocol->sensor_type) +
                      " (error " + String(error) + ")");
            errorTracker.trackError(ERROR_I2C_DEVICE_NOT_FOUND, ERROR_SEVERITY_WARNING,
                                   (String(protocol->sensor_type) + " not responding").c_str());
            return false;
        }
    }

    // Step 2: Wait for conversion
    if (protocol->conversion_time_ms > 0) {
        delay(protocol->conversion_time_ms);
        yield();  // Feed watchdog after blocking delay
    }

    // Step 3: Read data directly (no register address)
    // requestFrom() is blocking on ESP32 (ESP-IDF I2C driver) —
    // bytes are either in buffer after return or the transaction failed.
    // No Wire.available() polling needed (bytes don't arrive "later").
    uint8_t expected = protocol->expected_bytes;
    LOG_D(TAG, "I2C CMD: requestFrom START addr=0x" + String(i2c_address, HEX) + " bytes=" + String(expected));
    uint8_t received = Wire.requestFrom(i2c_address, expected);
    LOG_D(TAG, "I2C CMD: requestFrom END received=" + String(received));

    if (received != expected) {
        LOG_E(TAG, "I2C: requestFrom(0x" + String(i2c_address, HEX) + ", " +
                  String(expected) + ") returned " + String(received) + " bytes");
        errorTracker.trackError(ERROR_I2C_TIMEOUT, ERROR_SEVERITY_ERROR,
                               (String(protocol->sensor_type) + " read timeout").c_str());
        return false;
    }

    // Bytes are immediately available — read into buffer
    LOG_D(TAG, "I2C CMD: Reading " + String(received) + " bytes from buffer...");
    for (uint8_t i = 0; i < received; i++) {
        buffer[i] = Wire.read();
    }
    bytes_read = received;
    LOG_D(TAG, "I2C CMD: Read complete, bytes_read=" + String(bytes_read));

    return true;
}

// ============================================
// REGISTER-BASED PROTOCOL EXECUTION (BMP280)
// ============================================
bool I2CBusManager::executeRegisterBasedProtocol(const I2CSensorProtocol* protocol,
                                                  uint8_t i2c_address,
                                                  uint8_t* buffer,
                                                  size_t buffer_size,
                                                  size_t& bytes_read) {
    // readSensorRaw() already holds g_i2c_mutex — use readRawLocked to avoid deadlock.
    if (readRawLocked(i2c_address, protocol->data_register, buffer, protocol->expected_bytes)) {
        bytes_read = protocol->expected_bytes;
        return true;
    }
    return false;
}

// ============================================
// PROTOCOL QUERY METHODS
// ============================================
bool I2CBusManager::isSensorTypeSupported(const String& sensor_type) const {
    return isI2CSensorTypeSupported(sensor_type);
}

void I2CBusManager::getSupportedI2CSensorTypes(String types[], uint8_t max_count,
                                                uint8_t& count) const {
    count = 0;

    // Iterate through protocol registry
    const I2CSensorProtocol* proto;
    uint8_t i = 0;

    while (count < max_count) {
        // Check each known sensor type
        const char* known_types[] = {"sht31", "bmp280", "bme280", nullptr};

        if (known_types[i] == nullptr) {
            break;
        }

        proto = findI2CSensorProtocol(String(known_types[i]));
        if (proto != nullptr) {
            types[count++] = String(proto->sensor_type);
        }
        i++;
    }
}
