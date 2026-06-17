#ifndef TEST_HELPERS_GPIO_MANAGER_TEST_HELPER_H
#define TEST_HELPERS_GPIO_MANAGER_TEST_HELPER_H

#ifdef NATIVE_TEST

#include "../../src/drivers/gpio_manager.h"
#include "../../src/drivers/hal/igpio_hal.h"

// ============================================
// GPIO Manager Test Helper
// ============================================
// Friend helper class for testing GPIOManager with HAL mocks
//
// Purpose: Enable unit testing of GPIOManager without hardware
// Pattern: Friend-Helper (analog zu ActuatorManagerTestHelper)
//
// Usage in tests:
// 1. Reset manager: GPIOManagerTestHelper::reset(mgr);
// 2. Inject mock: GPIOManagerTestHelper::injectHAL(mgr, &mock_hal);
// 3. Test operations
// 4. Inspect state: GPIOManagerTestHelper::getXXX(mgr);
//
// Note: Requires `friend class GPIOManagerTestHelper;` in GPIOManager

class GPIOManagerTestHelper {
public:
    // ============================================
    // MOCK INJECTION
    // ============================================
    // Inject a HAL mock into GPIOManager for testing
    // mgr: GPIOManager instance (use getInstance())
    // hal: Pointer to IGPIOHal implementation (e.g., MockGPIOHal)
    static void injectHAL(GPIOManager& mgr, IGPIOHal* hal) {
        // Direct access via friend - set HAL pointer
        mgr.gpio_hal_ = hal;
    }

    // ============================================
    // STATE RESET
    // ============================================
    // Reset GPIOManager to clean state between tests
    // Call in setUp() before each test
    static void reset(GPIOManager& mgr) {
        // Reset internal state
        mgr.pins_.clear();
        mgr.subzone_pin_map_.clear();

        // Reset HAL pointer to nullptr (will be injected by test)
        mgr.gpio_hal_ = nullptr;
    }

    // ============================================
    // TEST UTILITIES - STATE INSPECTION
    // ============================================
    // Get pin count (number of tracked pins)
    static size_t getPinCount(const GPIOManager& mgr) {
        return mgr.pins_.size();
    }

    // Check if a pin is tracked in pins_ vector
    static bool isPinTracked(const GPIOManager& mgr, uint8_t gpio) {
        for (const auto& pin_info : mgr.pins_) {
            if (pin_info.pin == gpio) {
                return true;
            }
        }
        return false;
    }

    // Get HAL pointer (for verifying injection)
    static IGPIOHal* getHAL(const GPIOManager& mgr) {
        return mgr.gpio_hal_;
    }
};

#endif  // NATIVE_TEST
#endif  // TEST_HELPERS_GPIO_MANAGER_TEST_HELPER_H
