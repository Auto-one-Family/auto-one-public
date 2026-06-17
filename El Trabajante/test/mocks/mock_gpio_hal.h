#ifndef TEST_MOCKS_MOCK_GPIO_HAL_H
#define TEST_MOCKS_MOCK_GPIO_HAL_H

#ifdef NATIVE_TEST

#include "../../src/drivers/hal/igpio_hal.h"
#include "../../src/drivers/gpio_manager.h"  // For GPIOPinInfo struct
#include <map>
#include <set>
#include <string>

// ============================================
// Mock GPIO HAL - Test Implementation
// ============================================
// Mock implementation of IGPIOHal for unit tests
// Tracks GPIO state in-memory without hardware access
//
// Purpose: Enable testing of GPIO-dependent managers (SensorManager, ActuatorManager)
// Features:
// - In-memory pin state tracking (modes, values, reservations)
// - Test helper methods for state inspection
// - Configurable behavior (simulate failures, reserved pins)
//
// Used in: Native unit tests only (test/unit/managers/*)
// NOT used in: Production code

class MockGPIOHal : public IGPIOHal {
public:
    // ============================================
    // CONSTRUCTOR
    // ============================================
    MockGPIOHal() {
        reset();
    }

    // ============================================
    // TEST HELPER - RESET STATE
    // ============================================
    // Reset all mock state to initial conditions
    // Call in setUp() before each test
    void reset() {
        pin_modes_.clear();
        pin_values_.clear();
        reserved_pins_.clear();
        safe_mode_initialized_ = false;
        fail_next_request_ = false;
        fail_next_pinMode_ = false;
        fail_next_digitalWrite_ = false;

        // Simulate ESP32 hardware-reserved pins
        // GPIO 0, 1, 3 (Boot/UART), 6-11 (Flash), 12 (Boot-fail)
        hardware_reserved_pins_ = {0, 1, 3, 6, 7, 8, 9, 10, 11, 12};
    }

    // ============================================
    // LIFECYCLE
    // ============================================
    bool initializeAllPinsToSafeMode() override {
        safe_mode_initialized_ = true;

        // Initialize all pins to INPUT_PULLUP (safe mode)
        for (uint8_t pin = 0; pin < 40; ++pin) {
            if (hardware_reserved_pins_.find(pin) == hardware_reserved_pins_.end()) {
                pin_modes_[pin] = GPIOMode::GPIO_INPUT_PULLUP;
                pin_values_[pin] = true;  // Pulled high
            }
        }

        return true;
    }

    // ============================================
    // PIN MANAGEMENT
    // ============================================
    bool requestPin(uint8_t gpio, const String& owner, const String& component_name) override {
        if (fail_next_request_) {
            fail_next_request_ = false;
            return false;
        }

        // Check if pin is hardware-reserved
        if (isPinReserved(gpio)) {
            return false;
        }

        // Check if pin is already reserved
        if (reserved_pins_.find(gpio) != reserved_pins_.end()) {
            return false;
        }

        // Reserve pin
        PinReservation reservation;
        reservation.owner = owner.c_str();
        reservation.component_name = component_name.c_str();
        reserved_pins_[gpio] = reservation;

        return true;
    }

    bool releasePin(uint8_t gpio) override {
        // Check if pin is reserved
        if (reserved_pins_.find(gpio) == reserved_pins_.end()) {
            return false;
        }

        // Release pin and return to safe mode
        reserved_pins_.erase(gpio);
        pin_modes_[gpio] = GPIOMode::GPIO_INPUT_PULLUP;
        pin_values_[gpio] = true;

        return true;
    }

    // ============================================
    // PIN QUERIES
    // ============================================
    bool isPinAvailable(uint8_t gpio) const override {
        // Not available if hardware-reserved or already reserved
        if (isPinReserved(gpio)) {
            return false;
        }
        return reserved_pins_.find(gpio) == reserved_pins_.end();
    }

    bool isPinReserved(uint8_t gpio) const override {
        return hardware_reserved_pins_.find(gpio) != hardware_reserved_pins_.end();
    }

    bool isPinInSafeMode(uint8_t gpio) const override {
        // Pin is in safe mode if mode is INPUT_PULLUP and NOT reserved
        auto mode_it = pin_modes_.find(gpio);
        if (mode_it == pin_modes_.end()) {
            return true;  // Uninitialized = safe mode
        }

        bool is_reserved = reserved_pins_.find(gpio) != reserved_pins_.end();
        return (mode_it->second == GPIOMode::GPIO_INPUT_PULLUP) && !is_reserved;
    }

    // ============================================
    // GPIO OPERATIONS
    // ============================================
    bool pinMode(uint8_t gpio, GPIOMode mode) override {
        if (fail_next_pinMode_) {
            fail_next_pinMode_ = false;
            return false;
        }

        pin_modes_[gpio] = mode;
        return true;
    }

    bool digitalWrite(uint8_t gpio, bool value) override {
        if (fail_next_digitalWrite_) {
            fail_next_digitalWrite_ = false;
            return false;
        }

        pin_values_[gpio] = value;
        return true;
    }

    bool digitalRead(uint8_t gpio) override {
        auto it = pin_values_.find(gpio);
        if (it == pin_values_.end()) {
            return false;  // Default LOW if not set
        }
        return it->second;
    }

    uint16_t analogRead(uint8_t gpio) override {
        // Return simulated ADC value (0-4095 for 12-bit ESP32 ADC)
        auto it = analog_values_.find(gpio);
        if (it == analog_values_.end()) {
            return 0;  // Default 0V if not set
        }
        return it->second;
    }

    // ============================================
    // EMERGENCY SAFE-MODE
    // ============================================
    void enableSafeModeForAllPins() override {
        // Return all pins to safe mode
        for (auto& pair : pin_modes_) {
            pair.second = GPIOMode::GPIO_INPUT_PULLUP;
        }
        for (auto& pair : pin_values_) {
            pair.second = true;  // Pulled high
        }
        reserved_pins_.clear();
    }

    // ============================================
    // INFORMATION METHODS
    // ============================================
    GPIOPinInfo getPinInfo(uint8_t gpio) const override {
        GPIOPinInfo info;
        info.pin = gpio;

        // Check if reserved
        auto res_it = reserved_pins_.find(gpio);
        if (res_it != reserved_pins_.end()) {
            strncpy(info.owner, res_it->second.owner.c_str(), 31);
            strncpy(info.component_name, res_it->second.component_name.c_str(), 31);
            info.owner[31] = '\0';
            info.component_name[31] = '\0';
        } else {
            info.owner[0] = '\0';
            info.component_name[0] = '\0';
        }

        // Get mode
        auto mode_it = pin_modes_.find(gpio);
        if (mode_it != pin_modes_.end()) {
            info.mode = static_cast<uint8_t>(mode_it->second);
        } else {
            info.mode = static_cast<uint8_t>(GPIOMode::GPIO_INPUT_PULLUP);
        }

        info.in_safe_mode = isPinInSafeMode(gpio);

        return info;
    }

    std::vector<GPIOPinInfo> getReservedPinsList() const override {
        std::vector<GPIOPinInfo> list;
        for (const auto& pair : reserved_pins_) {
            list.push_back(getPinInfo(pair.first));
        }
        return list;
    }

    uint8_t getReservedPinCount() const override {
        return reserved_pins_.size();
    }

    uint8_t getAvailablePinCount() const override {
        uint8_t count = 0;
        for (uint8_t pin = 0; pin < 40; ++pin) {
            if (isPinAvailable(pin)) {
                ++count;
            }
        }
        return count;
    }

    String getPinOwner(uint8_t gpio) const override {
        auto it = reserved_pins_.find(gpio);
        if (it == reserved_pins_.end()) {
            return String("");
        }
        return String(it->second.owner.c_str());
    }

    String getPinComponent(uint8_t gpio) const override {
        auto it = reserved_pins_.find(gpio);
        if (it == reserved_pins_.end()) {
            return String("");
        }
        return String(it->second.component_name.c_str());
    }

    // ============================================
    // TEST HELPERS - STATE INSPECTION
    // ============================================
    // Get pin mode (for test assertions)
    GPIOMode getPinMode(uint8_t gpio) const {
        auto it = pin_modes_.find(gpio);
        if (it == pin_modes_.end()) {
            return GPIOMode::GPIO_INPUT_PULLUP;  // Default safe mode
        }
        return it->second;
    }

    // Get pin digital value (for test assertions)
    bool getPinValue(uint8_t gpio) const {
        auto it = pin_values_.find(gpio);
        if (it == pin_values_.end()) {
            return false;
        }
        return it->second;
    }

    // Check if safe-mode initialization was called
    bool wasSafeModeInitialized() const {
        return safe_mode_initialized_;
    }

    // Check if pin availability was checked (for test assertions)
    bool wasPinAvailabilityChecked(uint8_t gpio) const {
        // Simplified: Just check if pin exists in any map
        return pin_modes_.find(gpio) != pin_modes_.end() ||
               reserved_pins_.find(gpio) != reserved_pins_.end();
    }

    // ============================================
    // TEST HELPERS - BEHAVIOR CONFIGURATION
    // ============================================
    // Simulate failure on next requestPin call
    void setFailNextRequest(bool fail) {
        fail_next_request_ = fail;
    }

    // Simulate failure on next pinMode call
    void setFailNextPinMode(bool fail) {
        fail_next_pinMode_ = fail;
    }

    // Simulate failure on next digitalWrite call
    void setFailNextDigitalWrite(bool fail) {
        fail_next_digitalWrite_ = fail;
    }

    // Set simulated analog value for a pin (ADC value 0-4095)
    void setAnalogValue(uint8_t gpio, uint16_t value) {
        analog_values_[gpio] = value;
    }

    // Add a custom hardware-reserved pin (for testing reservation logic)
    void addHardwareReservedPin(uint8_t gpio) {
        hardware_reserved_pins_.insert(gpio);
    }

private:
    // ============================================
    // INTERNAL STATE
    // ============================================
    struct PinReservation {
        std::string owner;
        std::string component_name;
    };

    std::map<uint8_t, GPIOMode> pin_modes_;
    std::map<uint8_t, bool> pin_values_;
    std::map<uint8_t, uint16_t> analog_values_;
    std::map<uint8_t, PinReservation> reserved_pins_;
    std::set<uint8_t> hardware_reserved_pins_;

    bool safe_mode_initialized_;
    bool fail_next_request_;
    bool fail_next_pinMode_;
    bool fail_next_digitalWrite_;
};

#endif  // NATIVE_TEST
#endif  // TEST_MOCKS_MOCK_GPIO_HAL_H
