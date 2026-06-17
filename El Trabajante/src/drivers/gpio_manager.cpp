#include "gpio_manager.h"
#include "../utils/logger.h"
#include <algorithm>

// HAL Interface and Wrapper (Phase 2: Unit Testing)
#include "hal/igpio_hal.h"
#ifndef UNIT_TEST
    #include "hal/esp32_gpio_hal.h"
#endif

// ============================================
// CONDITIONAL HARDWARE CONFIGURATION INCLUDES
// ============================================
// Include board-specific configuration based on build flags

#ifdef XIAO_ESP32C3
    #include "../config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "../config/hardware/esp32_s3_devkit.h"
#else
    #include "../config/hardware/esp32_dev.h"
#endif

// ESP-IDF TAG convention for structured logging
static const char* TAG = "GPIO";

// ============================================
// PRODUCTION HAL INSTANCE (Static)
// ============================================
#ifndef UNIT_TEST
ESP32GPIOHal GPIOManager::production_gpio_hal_;
#endif

// ============================================
// CONSTRUCTOR
// ============================================
GPIOManager::GPIOManager() {
    #ifndef UNIT_TEST
    // Production: HAL pointer points to static production instance
    gpio_hal_ = &production_gpio_hal_;
    #else
    // Unit Test: HAL pointer is nullptr (will be injected via TestHelper)
    gpio_hal_ = nullptr;
    #endif
}

// ============================================
// toGPIOMode CONVERSION
// ============================================
GPIOMode GPIOManager::toGPIOMode(uint8_t arduino_mode) {
    switch (arduino_mode) {
        case INPUT:          return GPIOMode::GPIO_INPUT;
        case OUTPUT:         return GPIOMode::GPIO_OUTPUT;
        case INPUT_PULLUP:   return GPIOMode::GPIO_INPUT_PULLUP;
        case INPUT_PULLDOWN: return GPIOMode::GPIO_INPUT_PULLDOWN;
        default:             return GPIOMode::GPIO_INPUT_PULLUP;  // Safe fallback
    }
}

// ============================================
// GLOBAL INSTANCE
// ============================================
GPIOManager& gpioManager = GPIOManager::getInstance();

// ============================================
// CRITICAL: SAFE-MODE INITIALIZATION
// ============================================
// Source: ZZZ.md lines 1930-1950
// THIS FUNCTION MUST BE CALLED AS THE FIRST ACTION IN setup()!
//
// Why this is critical:
// - Prevents undefined GPIO states that could damage hardware
// - Ensures no actuators are accidentally triggered on boot
// - Sets all safe pins to INPUT_PULLUP (high-impedance safe state)

void GPIOManager::initializeAllPinsToSafeMode() {
    // Re-entrancy guard (safety net for circular HAL calls)
    static bool initializing_ = false;
    if (initializing_) return;
    initializing_ = true;

    Serial.println("\n=== GPIO SAFE-MODE INITIALIZATION ===");
    Serial.printf("Board Type: %s\n", BOARD_TYPE);

    // HAL availability check - in production always set, nullptr only in unit tests
    if (!gpio_hal_) {
        Serial.println("[CRITICAL] GPIOManager: HAL not initialized! Hardware operations will be skipped.");
    }

    // Notify HAL (Mock uses this to set initialized flag)
    if (gpio_hal_) {
        gpio_hal_->initializeAllPinsToSafeMode();
    }

    // Clear any existing pin information
    pins_.clear();
    pins_.reserve(HardwareConfig::SAFE_PIN_COUNT);

    uint8_t warning_count = 0;  // Track failed verifications

    // Initialize all safe GPIO pins to safe state
    for (uint8_t i = 0; i < HardwareConfig::SAFE_PIN_COUNT; i++) {
        uint8_t pin = HardwareConfig::SAFE_GPIO_PINS[i];

        // Input-only pins (34-39) have no internal pull-ups, use INPUT mode
        bool input_only = isInputOnlyPin(pin);
        GPIOMode safe_mode = input_only ? GPIOMode::GPIO_INPUT : GPIOMode::GPIO_INPUT_PULLUP;
        uint8_t arduino_mode = input_only ? INPUT : INPUT_PULLUP;

        // Set hardware pin mode via HAL
        if (gpio_hal_) {
            gpio_hal_->pinMode(pin, safe_mode);
        }

        // Verify pin state
        if (!verifyPinState(pin, arduino_mode)) {
            LOG_W(TAG, "GPIO " + String(pin) + " may not be in safe state!");
            warning_count++;
        }

        // Register pin in tracking system
        GPIOPinInfo info;
        info.pin = pin;
        info.owner[0] = '\0';
        info.component_name[0] = '\0';
        info.mode = arduino_mode;
        info.in_safe_mode = true;
        pins_.push_back(info);

        LOG_D(TAG, "GPIO " + String(pin) + ": Safe-Mode (" + String(input_only ? "INPUT" : "INPUT_PULLUP") + ")");
    }

    // Auto-reserve I2C pins for system use (skip in unit tests)
    #ifndef UNIT_TEST
    bool i2c_sda = requestPin(HardwareConfig::I2C_SDA_PIN, "system", "I2C_SDA");
    bool i2c_scl = requestPin(HardwareConfig::I2C_SCL_PIN, "system", "I2C_SCL");

    if (i2c_sda && i2c_scl) {
        LOG_I(TAG, "I2C pins auto-reserved (SDA: GPIO " + String(HardwareConfig::I2C_SDA_PIN) +
                 ", SCL: GPIO " + String(HardwareConfig::I2C_SCL_PIN) + ")");
    } else {
        LOG_W(TAG, "GPIOManager: I2C pin auto-reservation failed");
    }
    #endif

    // Log initialization summary
    if (warning_count > 0) {
        LOG_W(TAG, "GPIOManager: " + String(warning_count) + " pins failed safe-mode verification");
    } else {
        LOG_I(TAG, "All pins successfully set to Safe-Mode");
    }
    LOG_I(TAG, "Board: " + String(BOARD_TYPE));
    LOG_I(TAG, "Available Pins: " + String(HardwareConfig::SAFE_PIN_COUNT));
    LOG_I(TAG, "Reserved Pins: " + String(HardwareConfig::RESERVED_PIN_COUNT));

    LOG_I(TAG, "GPIOManager: Safe-Mode initialization complete");

    initializing_ = false;
}

// ============================================
// PIN REQUEST (WITH CONFLICT DETECTION)
// ============================================
// Source: PROJECT_ANALYSIS_REPORT.md Block 6
// Implements comprehensive validation and conflict detection

bool GPIOManager::requestPin(uint8_t gpio, const char* owner, const char* component_name) {
    if (owner == nullptr || owner[0] == '\0') {
        LOG_E(TAG, "GPIOManager: requestPin rejected (owner missing) for GPIO " + String(gpio));
        return false;
    }
    if (component_name == nullptr) {
        component_name = "";
    }

    // VALIDATION 1: Check if pin is reserved
    if (isReservedPin(gpio)) {
        LOG_E(TAG, "GPIOManager: Attempted to request reserved pin " + String(gpio));
        return false;
    }

    // VALIDATION 2: Check if pin is already in use
    for (auto& pin_info : pins_) {
        if (pin_info.pin == gpio && pin_info.owner[0] != '\0') {
            // ============================================
            // BUS-SHARING CHECK: Allow compatible bus users
            // ============================================
            // Pins owned by a bus (owner starts with "bus/") can be shared
            // by sensors/components that use the same bus type.
            // Example: "bus/onewire/4" allows DS18B20 sensors to share GPIO 4
            // Uses C-string operations for native test compatibility
            const char* existing_owner = pin_info.owner;
            const char* new_owner_str = owner;
            const size_t BUS_PREFIX_LEN = 4;  // strlen("bus/")

            if (strncmp(existing_owner, "bus/", BUS_PREFIX_LEN) == 0 &&
                strncmp(new_owner_str, "bus/", BUS_PREFIX_LEN) == 0) {
                // Both are bus owners - allow if same bus type
                // Extract bus type: "bus/onewire/4" -> "onewire"
                const char* existing_bus_start = existing_owner + BUS_PREFIX_LEN;
                const char* new_bus_start = new_owner_str + BUS_PREFIX_LEN;

                // Find end of bus type (next '/' or end of string)
                const char* existing_bus_end = strchr(existing_bus_start, '/');
                const char* new_bus_end = strchr(new_bus_start, '/');

                size_t existing_bus_len = existing_bus_end ?
                    (size_t)(existing_bus_end - existing_bus_start) : strlen(existing_bus_start);
                size_t new_bus_len = new_bus_end ?
                    (size_t)(new_bus_end - new_bus_start) : strlen(new_bus_start);

                if (existing_bus_len == new_bus_len &&
                    strncmp(existing_bus_start, new_bus_start, existing_bus_len) == 0) {
                    LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " bus-sharing allowed (" +
                             String(existing_owner) + " + " + String(new_owner_str) + ")");
                    return true;  // Same bus type - sharing OK
                }
            }

            LOG_E(TAG, "GPIOManager: Pin " + String(gpio) + " conflict - already owned by " + String(existing_owner));
            return false;
        }
    }

    // Notify HAL (Mock tracks reservations)
    if (gpio_hal_) {
        gpio_hal_->requestPin(gpio, String(owner), String(component_name));
    }

    // ALLOCATION: Reserve the pin in internal tracking
    for (auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
            strncpy(pin_info.owner, owner, sizeof(pin_info.owner) - 1);
            pin_info.owner[sizeof(pin_info.owner) - 1] = '\0';
            strncpy(pin_info.component_name, component_name, sizeof(pin_info.component_name) - 1);
            pin_info.component_name[sizeof(pin_info.component_name) - 1] = '\0';
            pin_info.in_safe_mode = false;

            LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " allocated to " + String(component_name));
            return true;
        }
    }

    // Pin not found in safe pins array
    LOG_E(TAG, "GPIOManager: Pin " + String(gpio) + " not in safe pins list");
    return false;
}

// ============================================
// PIN RELEASE
// ============================================
// Returns pin to safe mode (INPUT_PULLUP)

bool GPIOManager::releasePin(uint8_t gpio) {
    for (auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
            LOG_I(TAG, "Releasing GPIO " + String(gpio) + " (was: " + String(pin_info.owner) + "/" + String(pin_info.component_name) + ")");

            // Return hardware pin to safe state via HAL
            if (gpio_hal_) {
                gpio_hal_->releasePin(gpio);
            }

            // Verify safe mode
            if (!verifyPinState(gpio, INPUT_PULLUP)) {
                LOG_W(TAG, "Pin " + String(gpio) + " may not be in safe state after release");
            }

            // Update tracking information
            pin_info.owner[0] = '\0';
            pin_info.component_name[0] = '\0';
            pin_info.mode = INPUT_PULLUP;
            pin_info.in_safe_mode = true;

            LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " released to safe mode");
            return true;
        }
    }

    LOG_W(TAG, "GPIO " + String(gpio) + " not found for release");
    return false;
}

// ============================================
// EMERGENCY SAFE-MODE
// ============================================
// Source: ZZZ.md lines 1976-1994
// Used in error conditions to prevent hardware damage

void GPIOManager::enableSafeModeForAllPins() {
    LOG_C(TAG, "GPIOManager: Emergency safe-mode activated");

    // Notify HAL (Mock clears all state)
    if (gpio_hal_) {
        gpio_hal_->enableSafeModeForAllPins();
    }

    uint8_t warning_count = 0;
    uint8_t de_energized_count = 0;

    for (auto& pin_info : pins_) {
        // Enhanced safety - De-energize outputs BEFORE mode change
        if (pin_info.mode == OUTPUT) {
            if (gpio_hal_) {
                gpio_hal_->digitalWrite(pin_info.pin, false);
            }
            de_energized_count++;
            delayMicroseconds(10);            // Allow hardware to settle

            LOG_I(TAG, "Emergency: GPIO " + String(pin_info.pin) + " de-energized before safe-mode");
        }

        // Now safe to change mode via HAL
        if (gpio_hal_) {
            gpio_hal_->pinMode(pin_info.pin, GPIOMode::GPIO_INPUT_PULLUP);
        }

        // Verify emergency safe mode
        if (!verifyPinState(pin_info.pin, INPUT_PULLUP)) {
            LOG_W(TAG, "GPIO " + String(pin_info.pin) + " emergency safe-mode failed");
            warning_count++;
        }

        // Update tracking
        pin_info.in_safe_mode = true;
        pin_info.owner[0] = '\0';
        pin_info.component_name[0] = '\0';
        pin_info.mode = INPUT_PULLUP;
    }

    if (de_energized_count > 0) {
        LOG_I(TAG, "Emergency: " + String(de_energized_count) + " outputs de-energized");
    }

    if (warning_count > 0) {
        LOG_C(TAG, "Emergency safe-mode: " + String(warning_count) + " pins failed verification!");
    }

    LOG_I(TAG, "GPIOManager: All pins returned to safe mode");
}

// ============================================
// PIN CONFIGURATION
// ============================================
// Configure pin mode with validation

bool GPIOManager::configurePinMode(uint8_t gpio, uint8_t mode) {
    // VALIDATION 1: Pin reserved?
    if (isReservedPin(gpio)) {
        LOG_E(TAG, "GPIOManager: Attempted to configure reserved pin " + String(gpio));
        return false;
    }

    // VALIDATION 2: Input-Only Pin check (ESP32 WROOM specific)
    #ifndef XIAO_ESP32C3
    if (isInputOnlyPin(gpio) && mode == OUTPUT) {
        LOG_E(TAG, "GPIOManager: Attempted OUTPUT mode on input-only pin " + String(gpio));
        return false;
    }
    #endif

    // CONFIGURE: Set pin mode via HAL
    if (gpio_hal_) {
        gpio_hal_->pinMode(gpio, toGPIOMode(mode));
    }

    // Verify configuration (only for INPUT_PULLUP)
    if (mode == INPUT_PULLUP) {
        if (!verifyPinState(gpio, mode)) {
            LOG_W(TAG, "Pin " + String(gpio) + " configuration verification failed");
            // Don't return false - best effort
        }
    }

    // Update tracking information
    for (auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
            pin_info.mode = mode;
            pin_info.in_safe_mode = false;

            String mode_str = (mode == INPUT) ? "INPUT" :
                             (mode == OUTPUT) ? "OUTPUT" : "INPUT_PULLUP";
            LOG_D(TAG, "GPIOManager: Pin " + String(gpio) + " mode set to " + mode_str);
            return true;
        }
    }

    return false;
}

// ============================================
// PIN QUERIES
// ============================================

bool GPIOManager::isPinAvailable(uint8_t gpio) const {
    #ifdef UNIT_TEST
    // In tests: delegate to HAL mock for correct behavior
    if (gpio_hal_) {
        return gpio_hal_->isPinAvailable(gpio);
    }
    #endif

    // Production: Reserved pins are never available
    if (isReservedPin(gpio)) {
        return false;
    }

    // Check if pin is in safe pins list and not allocated
    for (const auto& pin_info : pins_) {
        if (pin_info.pin == gpio && pin_info.owner[0] == '\0') {
            return true;
        }
    }

    return false;
}

bool GPIOManager::isPinReserved(uint8_t gpio) const {
    return isReservedPin(gpio);
}

bool GPIOManager::isPinInSafeMode(uint8_t gpio) const {
    for (const auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
            return pin_info.in_safe_mode;
        }
    }
    return false;
}

// ============================================
// INFORMATION METHODS
// ============================================

GPIOPinInfo GPIOManager::getPinInfo(uint8_t gpio) const {
    for (const auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
            return pin_info;
        }
    }

    // Return empty info if pin not found
    GPIOPinInfo empty;
    empty.pin = 255;  // Invalid pin marker
    empty.owner[0] = '\0';
    empty.component_name[0] = '\0';
    empty.mode = INPUT_PULLUP;
    empty.in_safe_mode = true;
    return empty;
}

// ============================================
// PIN OWNER/COMPONENT QUERIES (Phase 4)
// ============================================
// Used for detailed error messages in config_response

String GPIOManager::getPinOwner(uint8_t gpio) const {
    for (const auto& pin_info : pins_) {
        if (pin_info.pin == gpio && pin_info.owner[0] != '\0') {
            return String(pin_info.owner);
        }
    }
    return "";
}

String GPIOManager::getPinComponent(uint8_t gpio) const {
    for (const auto& pin_info : pins_) {
        if (pin_info.pin == gpio && pin_info.component_name[0] != '\0') {
            return String(pin_info.component_name);
        }
    }
    return "";
}

void GPIOManager::printPinStatus() const {
    LOG_I(TAG, "=== GPIO PIN STATUS ===");
    LOG_I(TAG, "Board: " + String(BOARD_TYPE));
    LOG_I(TAG, "Total Managed Pins: " + String((int)pins_.size()));

    for (const auto& pin_info : pins_) {
        String status = "GPIO " + String(pin_info.pin) + ": ";

        if (pin_info.in_safe_mode) {
            status += "SAFE-MODE (available)";
        } else if (pin_info.owner[0] == '\0') {
            status += "AVAILABLE";
        } else {
            status += "USED by " + String(pin_info.owner) + " (" + String(pin_info.component_name) + ")";
        }

        LOG_I(TAG, status);
    }

    LOG_I(TAG, "=======================");
}

uint8_t GPIOManager::getAvailablePinCount() const {
    uint8_t count = 0;
    for (const auto& pin_info : pins_) {
        if (pin_info.owner[0] == '\0') {
            count++;
        }
    }
    return count;
}

// ============================================
// GPIO STATUS REPORTING (Phase 1)
// ============================================

std::vector<GPIOPinInfo> GPIOManager::getReservedPinsList() const {
    std::vector<GPIOPinInfo> reserved;

    try {
        // Pre-allocate close to actual upper bound to avoid intermediate reallocations.
        // Must stay inside try: reserve() may throw on allocation failure.
        reserved.reserve(pins_.size());

        for (const auto& pin_info : pins_) {
            // Nur Pins die NICHT in Safe-Mode sind (also aktiv reserviert)
            // UND einen Owner haben (doppelte Sicherheit)
            if (!pin_info.in_safe_mode && pin_info.owner[0] != '\0') {
                reserved.push_back(pin_info);
            }
        }
    } catch (const std::bad_alloc&) {
        // Keep error logging allocation-free in low-memory scenarios.
        LOG_E(TAG, "GPIOManager::getReservedPinsList() failed: std::bad_alloc");
        // Return empty list on error - don't crash the heartbeat
        return std::vector<GPIOPinInfo>();
    } catch (const std::exception&) {
        LOG_E(TAG, "GPIOManager::getReservedPinsList() failed: std::exception");
        // Return empty list on error - don't crash the heartbeat
        return std::vector<GPIOPinInfo>();
    } catch (...) {
        LOG_E(TAG, "GPIOManager::getReservedPinsList() unknown exception");
        return std::vector<GPIOPinInfo>();
    }

    LOG_D(TAG, "GPIOManager: " + String((int)reserved.size()) + " reserved pins for heartbeat");
    return reserved;
}

uint8_t GPIOManager::getReservedPinCount() const {
    uint8_t count = 0;

    try {
        for (const auto& pin_info : pins_) {
            if (!pin_info.in_safe_mode && pin_info.owner[0] != '\0') {
                count++;
            }
        }
    } catch (...) {
        LOG_E(TAG, "GPIOManager::getReservedPinCount() exception");
        return 0;
    }

    return count;
}

// ============================================
// I2C PIN MANAGEMENT
// ============================================

void GPIOManager::releaseI2CPins() {
    LOG_W(TAG, "GPIOManager: I2C pins released - I2C bus will not be available");

    releasePin(HardwareConfig::I2C_SDA_PIN);
    releasePin(HardwareConfig::I2C_SCL_PIN);

    LOG_I(TAG, "I2C pins released: SDA (GPIO " + String(HardwareConfig::I2C_SDA_PIN) +
             "), SCL (GPIO " + String(HardwareConfig::I2C_SCL_PIN) + ")");
    LOG_I(TAG, "GPIOManager: I2C pins now available for general GPIO use");
}

// ============================================
// HELPER METHODS (PRIVATE)
// ============================================

bool GPIOManager::isReservedPin(uint8_t gpio) const {
    #ifdef UNIT_TEST
    // In tests: delegate to HAL mock for configurable reserved pins
    if (gpio_hal_) {
        return gpio_hal_->isPinReserved(gpio);
    }
    #endif

    // Production: check HardwareConfig directly
    for (uint8_t i = 0; i < HardwareConfig::RESERVED_PIN_COUNT; i++) {
        if (HardwareConfig::RESERVED_GPIO_PINS[i] == gpio) {
            return true;
        }
    }
    return false;
}

bool GPIOManager::isInputOnlyPin(uint8_t gpio) const {
    #ifndef XIAO_ESP32C3
    // ESP32 WROOM has input-only pins (GPIO 34-39)
    for (uint8_t i = 0; i < HardwareConfig::INPUT_ONLY_PIN_COUNT; i++) {
        if (HardwareConfig::INPUT_ONLY_PINS[i] == gpio) {
            return true;
        }
    }
    #endif
    return false;
}

bool GPIOManager::isADC2Pin(uint8_t gpio) const {
    #ifndef XIAO_ESP32C3
    for (uint8_t i = 0; i < HardwareConfig::ADC2_PIN_COUNT; i++) {
        if (HardwareConfig::ADC2_GPIO_PINS[i] == gpio) {
            return true;
        }
    }
    #endif
    return false;
}

bool GPIOManager::verifyPinState(uint8_t pin, uint8_t expected_mode) {
    delay(1);  // Allow pin to stabilize (1ms is sufficient)

    if (expected_mode == INPUT_PULLUP) {
        // For INPUT_PULLUP, pin should read HIGH (pulled up)
        bool state = false;
        if (gpio_hal_) {
            state = gpio_hal_->digitalRead(pin);
        }
        if (!state) {
            LOG_W(TAG, "Pin " + String(pin) + " verification failed - expected HIGH, got LOW");
            return false;
        }
    }
    // For OUTPUT mode, we can't verify without external hardware
    // (reading pin value doesn't tell us if OUTPUT is working)

    return true;  // Verification passed or not applicable
}

// ============================================
// SUBZONE MANAGEMENT IMPLEMENTATION (Phase 9)
// ============================================

bool GPIOManager::assignPinToSubzone(uint8_t gpio, const String& subzone_id) {
  // Validation 1: Pin muss verfügbar oder bereits dieser Subzone zugewiesen sein
  if (isReservedPin(gpio)) {
    LOG_E(TAG, "GPIOManager: Cannot assign reserved pin " + String(gpio) + " to subzone");
    return false;
  }

  // Validation 2: Pin muss in safe pins list sein
  bool pin_in_safe_list = false;
  for (const auto& pin_info : pins_) {
    if (pin_info.pin == gpio) {
      pin_in_safe_list = true;
      break;
    }
  }
  if (!pin_in_safe_list) {
    LOG_E(TAG, "GPIOManager: Pin " + String(gpio) + " not in safe pins list");
    return false;
  }

  // Validation 3: Prüfe ob Pin bereits anderer Subzone zugewiesen (gleiche Subzone ist OK für Updates)
  for (const auto& entry : subzone_pin_map_) {
    if (entry.first != subzone_id) {
      // Prüfe ob Pin bereits einer anderen Subzone zugewiesen ist
      for (uint8_t assigned_gpio : entry.second) {
        if (assigned_gpio == gpio) {
          LOG_E(TAG, "GPIOManager: Pin " + String(gpio) + " already assigned to subzone " + entry.first);
          return false;
        }
      }
    } else {
      // Gleiche Subzone: Prüfe ob Pin bereits zugewiesen (Update ist OK)
      for (uint8_t assigned_gpio : entry.second) {
        if (assigned_gpio == gpio) {
          LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " already assigned to subzone " + subzone_id + " (update)");
          return true;  // Bereits zugewiesen, kein Fehler
        }
      }
    }
  }

  // Assignment: Pin zu Subzone hinzufügen
  subzone_pin_map_[subzone_id].push_back(gpio);

  // Update pin_info component_name für Tracking
  for (auto& pin_info : pins_) {
    if (pin_info.pin == gpio) {
      strncpy(pin_info.component_name, subzone_id.c_str(), sizeof(pin_info.component_name) - 1);
      pin_info.component_name[sizeof(pin_info.component_name) - 1] = '\0';
      break;
    }
  }

  LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " assigned to subzone: " + subzone_id);
  return true;
}

bool GPIOManager::removePinFromSubzone(uint8_t gpio) {
  // Finde Subzone die diesen Pin hat
  for (auto& entry : subzone_pin_map_) {
    auto& gpios = entry.second;
    auto it = std::find(gpios.begin(), gpios.end(), gpio);
    if (it != gpios.end()) {
      gpios.erase(it);
      LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " removed from subzone: " + entry.first);

      // Wenn Subzone leer ist, entferne sie aus Map
      if (gpios.empty()) {
        subzone_pin_map_.erase(entry.first);
      }

      // Update pin_info
      for (auto& pin_info : pins_) {
        if (pin_info.pin == gpio) {
          pin_info.component_name[0] = '\0';
          break;
        }
      }

      return true;
    }
  }

  LOG_W(TAG, "GPIOManager: Pin " + String(gpio) + " not found in any subzone");
  return false;
}

std::vector<uint8_t> GPIOManager::getSubzonePins(const String& subzone_id) const {
  auto it = subzone_pin_map_.find(subzone_id);
  if (it != subzone_pin_map_.end()) {
    return it->second;
  }
  return std::vector<uint8_t>();  // Empty vector
}

bool GPIOManager::isPinAssignedToSubzone(uint8_t gpio, const String& subzone_id) const {
  if (subzone_id.length() == 0) {
    // Prüfe ob Pin überhaupt einer Subzone zugewiesen ist
    for (const auto& entry : subzone_pin_map_) {
      for (uint8_t assigned_gpio : entry.second) {
        if (assigned_gpio == gpio) {
          return true;
        }
      }
    }
    return false;
  }

  // Prüfe spezifische Subzone
  auto it = subzone_pin_map_.find(subzone_id);
  if (it != subzone_pin_map_.end()) {
    for (uint8_t assigned_gpio : it->second) {
      if (assigned_gpio == gpio) {
        return true;
      }
    }
  }
  return false;
}

bool GPIOManager::isSubzoneSafe(const String& subzone_id) const {
  auto pins = getSubzonePins(subzone_id);
  if (pins.empty()) {
    return true;  // Leere Subzone ist "safe"
  }

  for (uint8_t gpio : pins) {
    if (!isPinInSafeMode(gpio)) {
      return false;
    }
  }
  return true;
}

bool GPIOManager::enableSafeModeForSubzone(const String& subzone_id) {
  auto pins = getSubzonePins(subzone_id);
  if (pins.empty()) {
    LOG_W(TAG, "GPIOManager: Subzone " + subzone_id + " has no pins");
    return false;
  }

  bool success = true;
  for (uint8_t gpio : pins) {
    // Skip pins owned by actuators — safe-mode must not interfere with
    // actuator OUTPUT state. Actuator pins are managed by ActuatorManager.
    String owner = getPinOwner(gpio);
    if (owner == "actuator") {
      LOG_I(TAG, "GPIOManager: Pin " + String(gpio) + " owned by actuator, skipping safe-mode");
      continue;
    }

    // De-energize outputs BEFORE mode change
    for (auto& pin_info : pins_) {
      if (pin_info.pin == gpio && pin_info.mode == OUTPUT) {
        if (gpio_hal_) {
            gpio_hal_->digitalWrite(gpio, false);
        }
        delayMicroseconds(10);
      }
    }

    // Set to safe mode via HAL
    if (gpio_hal_) {
        gpio_hal_->pinMode(gpio, GPIOMode::GPIO_INPUT_PULLUP);
    }

    // Update tracking
    for (auto& pin_info : pins_) {
      if (pin_info.pin == gpio) {
        pin_info.in_safe_mode = true;
        pin_info.mode = INPUT_PULLUP;
        if (!verifyPinState(gpio, INPUT_PULLUP)) {
          LOG_W(TAG, "GPIOManager: Pin " + String(gpio) + " safe-mode verification failed");
          success = false;
        }
      }
    }
  }

  if (success) {
    LOG_I(TAG, "GPIOManager: Safe-Mode activated for subzone: " + subzone_id);
  }
  return success;
}

bool GPIOManager::disableSafeModeForSubzone(const String& subzone_id) {
  // Disable safe-mode bedeutet nur Tracking-Update, nicht automatische Pin-Freigabe
  // Pins bleiben in Subzone-Zuweisung, aber safe_mode Flag wird entfernt
  auto pins = getSubzonePins(subzone_id);
  if (pins.empty()) {
    return false;
  }

  for (uint8_t gpio : pins) {
    for (auto& pin_info : pins_) {
      if (pin_info.pin == gpio) {
        pin_info.in_safe_mode = false;
      }
    }
  }

  LOG_I(TAG, "GPIOManager: Safe-Mode disabled for subzone: " + subzone_id);
  return true;
}
