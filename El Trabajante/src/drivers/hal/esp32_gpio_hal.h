#ifndef DRIVERS_HAL_ESP32_GPIO_HAL_H
#define DRIVERS_HAL_ESP32_GPIO_HAL_H

#include "igpio_hal.h"
#include "../gpio_manager.h"

// ============================================
// ESP32 GPIO HAL - Production Thin Wrapper
// ============================================
// Production implementation of IGPIOHal interface
// THIN WRAPPER: Only delegates LOW-LEVEL GPIO to Arduino API
//
// High-level operations (requestPin, releasePin tracking, etc.)
// are handled by GPIOManager internally. ESP32GPIOHal does NOT
// call back into GPIOManager for these to avoid circular recursion.
//
// Used in: Production code (main.cpp, all Managers)
// NOT used in: Unit tests (use MockGPIOHal instead)

class ESP32GPIOHal : public IGPIOHal {
public:
    // ============================================
    // CONSTRUCTOR
    // ============================================
    ESP32GPIOHal() : gpio_manager_(&GPIOManager::getInstance()) {}

    // ============================================
    // LIFECYCLE (No-op: GPIOManager handles internally)
    // ============================================
    bool initializeAllPinsToSafeMode() override {
        // No-op in production: GPIOManager handles all initialization internally
        // and calls gpio_hal_->pinMode() for each pin directly
        return true;
    }

    // ============================================
    // PIN MANAGEMENT (No-op: GPIOManager handles tracking)
    // ============================================
    bool requestPin(uint8_t gpio, const String& owner, const String& component_name) override {
        (void)gpio; (void)owner; (void)component_name;
        // No-op in production: GPIOManager handles all pin tracking internally
        return true;
    }

    bool releasePin(uint8_t gpio) override {
        // Hardware-only: return pin to safe state
        ::pinMode(gpio, INPUT_PULLUP);
        return true;
    }

    // ============================================
    // PIN QUERIES (Delegate to GPIOManager - read-only, no circular risk)
    // ============================================
    bool isPinAvailable(uint8_t gpio) const override {
        return gpio_manager_->isPinAvailable(gpio);
    }

    bool isPinReserved(uint8_t gpio) const override {
        return gpio_manager_->isPinReserved(gpio);
    }

    bool isPinInSafeMode(uint8_t gpio) const override {
        return gpio_manager_->isPinInSafeMode(gpio);
    }

    // ============================================
    // GPIO OPERATIONS (Hardware-only, no callbacks)
    // ============================================
    bool pinMode(uint8_t gpio, GPIOMode mode) override {
        // Convert GPIOMode enum to Arduino pin mode
        uint8_t arduino_mode;
        switch (mode) {
            case GPIOMode::GPIO_INPUT:
                arduino_mode = INPUT;
                break;
            case GPIOMode::GPIO_OUTPUT:
                arduino_mode = OUTPUT;
                break;
            case GPIOMode::GPIO_INPUT_PULLUP:
                arduino_mode = INPUT_PULLUP;
                break;
            case GPIOMode::GPIO_INPUT_PULLDOWN:
                arduino_mode = INPUT_PULLDOWN;
                break;
            default:
                return false;
        }

        // Hardware-only: set pin mode via Arduino API
        // NO callback to GPIOManager::configurePinMode (would cause circular call)
        ::pinMode(gpio, arduino_mode);
        return true;
    }

    bool digitalWrite(uint8_t gpio, bool value) override {
        ::digitalWrite(gpio, value ? HIGH : LOW);
        return true;
    }

    bool digitalRead(uint8_t gpio) override {
        return ::digitalRead(gpio) == HIGH;
    }

    uint16_t analogRead(uint8_t gpio) override {
        return ::analogRead(gpio);
    }

    // ============================================
    // EMERGENCY SAFE-MODE (No-op: GPIOManager handles internally)
    // ============================================
    void enableSafeModeForAllPins() override {
        // No-op in production: GPIOManager iterates pins and calls
        // gpio_hal_->digitalWrite() + gpio_hal_->pinMode() for each
    }

    // ============================================
    // INFORMATION METHODS (Delegate to GPIOManager - read-only)
    // ============================================
    GPIOPinInfo getPinInfo(uint8_t gpio) const override {
        return gpio_manager_->getPinInfo(gpio);
    }

    std::vector<GPIOPinInfo> getReservedPinsList() const override {
        return gpio_manager_->getReservedPinsList();
    }

    uint8_t getReservedPinCount() const override {
        return gpio_manager_->getReservedPinCount();
    }

    uint8_t getAvailablePinCount() const override {
        return gpio_manager_->getAvailablePinCount();
    }

    String getPinOwner(uint8_t gpio) const override {
        return gpio_manager_->getPinOwner(gpio);
    }

    String getPinComponent(uint8_t gpio) const override {
        return gpio_manager_->getPinComponent(gpio);
    }

private:
    GPIOManager* gpio_manager_;
};

#endif  // DRIVERS_HAL_ESP32_GPIO_HAL_H
