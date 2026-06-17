#include <unity.h>

#ifdef NATIVE_TEST
    #include "../mocks/Arduino.h"  // Mock
#else
    #include <Arduino.h>  // Echte Arduino-API
#endif

#include "../mocks/mock_gpio_hal.h"
#include "../helpers/gpio_manager_test_helper.h"
#include "../../src/drivers/gpio_manager.h"

// ============================================
// TEST FIXTURES
// ============================================
MockGPIOHal gpio_mock;

void setUp(void) {
    // Reset Mock
    gpio_mock.reset();

    // Get GPIOManager singleton and reset it
    GPIOManager& mgr = GPIOManager::getInstance();
    GPIOManagerTestHelper::reset(mgr);

    // Inject Mock HAL
    GPIOManagerTestHelper::injectHAL(mgr, &gpio_mock);
}

void tearDown(void) {
    // Cleanup
    GPIOManager& mgr = GPIOManager::getInstance();
    GPIOManagerTestHelper::reset(mgr);
}

// ============================================
// TEST CASES
// ============================================

// Test 1: Safe-Mode Initialization
void test_gpio_manager_safe_mode_initialization() {
    GPIOManager& mgr = GPIOManager::getInstance();

    // Act: Initialize all pins to safe mode
    mgr.initializeAllPinsToSafeMode();

    // Assert: Safe-mode was called on HAL
    TEST_ASSERT_TRUE(gpio_mock.wasSafeModeInitialized());
}

// Test 2: Pin Request Success
void test_gpio_manager_pin_request_success() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Act: Request a free pin (GPIO 4)
    bool ok = mgr.requestPin(4, "sensor", "DS18B20");

    // Assert: Request succeeded
    TEST_ASSERT_TRUE(ok);

    // Assert: Pin is now reserved in Mock
    TEST_ASSERT_EQUAL_STRING("sensor", gpio_mock.getPinOwner(4).c_str());
    TEST_ASSERT_EQUAL_STRING("DS18B20", gpio_mock.getPinComponent(4).c_str());
}

// Test 3: Pin Request on Reserved Pin Fails
void test_gpio_manager_pin_request_reserved_fails() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Mark GPIO 5 as hardware-reserved in Mock
    gpio_mock.addHardwareReservedPin(5);

    // Act: Try to request reserved pin
    bool ok = mgr.requestPin(5, "actuator", "Pump1");

    // Assert: Request failed
    TEST_ASSERT_FALSE(ok);
}

// Test 4: Pin Release Returns to Safe Mode
void test_gpio_manager_pin_release() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Request and reserve GPIO 4
    mgr.requestPin(4, "sensor", "DS18B20");
    TEST_ASSERT_FALSE(mgr.isPinInSafeMode(4));  // Confirm not in safe mode

    // Act: Release the pin
    bool ok = mgr.releasePin(4);

    // Assert: Release succeeded
    TEST_ASSERT_TRUE(ok);

    // Assert: Pin is back in safe mode
    TEST_ASSERT_TRUE(mgr.isPinInSafeMode(4));
    TEST_ASSERT_EQUAL(GPIOMode::GPIO_INPUT_PULLUP, gpio_mock.getPinMode(4));
}

// Test 5: Pin Availability Check
void test_gpio_manager_pin_availability() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve GPIO 4
    mgr.requestPin(4, "sensor", "DS18B20");

    // Assert: GPIO 4 is NOT available
    TEST_ASSERT_FALSE(mgr.isPinAvailable(4));

    // Assert: GPIO 13 (unreserved) IS available
    TEST_ASSERT_TRUE(mgr.isPinAvailable(13));

    // Assert: GPIO 0 (hardware-reserved) is NOT available
    TEST_ASSERT_FALSE(mgr.isPinAvailable(0));
}

// Test 6: Pin Mode Configuration
void test_gpio_manager_pin_mode_configuration() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve GPIO 21 for actuator
    mgr.requestPin(21, "actuator", "Pump1");

    // Act: Configure pin mode to OUTPUT
    bool ok = mgr.configurePinMode(21, OUTPUT);

    // Assert: Configuration succeeded
    TEST_ASSERT_TRUE(ok);

    // Assert: Pin mode was set in Mock
    TEST_ASSERT_EQUAL(GPIOMode::GPIO_OUTPUT, gpio_mock.getPinMode(21));
}

// Test 7: Digital Operations (Write/Read)
void test_gpio_manager_digital_operations() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve and configure GPIO 21 as OUTPUT
    mgr.requestPin(21, "actuator", "Pump1");
    mgr.configurePinMode(21, OUTPUT);

    // Act: Write HIGH to pin (via HAL Mock)
    gpio_mock.digitalWrite(21, true);

    // Assert: Pin value is HIGH in Mock
    TEST_ASSERT_TRUE(gpio_mock.getPinValue(21));

    // Assert: digitalRead returns HIGH
    TEST_ASSERT_TRUE(gpio_mock.digitalRead(21));
}

// Test 8: Emergency Safe-Mode for All Pins
void test_gpio_manager_emergency_safe_mode() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve multiple pins
    mgr.requestPin(4, "sensor", "DS18B20");
    mgr.requestPin(21, "actuator", "Pump1");
    mgr.configurePinMode(21, OUTPUT);

    // Act: Enable emergency safe mode
    mgr.enableSafeModeForAllPins();

    // Assert: All pins returned to INPUT_PULLUP
    TEST_ASSERT_EQUAL(GPIOMode::GPIO_INPUT_PULLUP, gpio_mock.getPinMode(4));
    TEST_ASSERT_EQUAL(GPIOMode::GPIO_INPUT_PULLUP, gpio_mock.getPinMode(21));

    // Assert: All reservations cleared
    TEST_ASSERT_EQUAL(0, mgr.getReservedPinCount());
}

// Test 9: Pin Info Retrieval
void test_gpio_manager_pin_info() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve GPIO 4
    mgr.requestPin(4, "sensor", "DS18B20");

    // Act: Get pin info
    GPIOPinInfo info = mgr.getPinInfo(4);

    // Assert: Info matches reservation
    TEST_ASSERT_EQUAL(4, info.pin);
    TEST_ASSERT_EQUAL_STRING("sensor", info.owner);
    TEST_ASSERT_EQUAL_STRING("DS18B20", info.component_name);
    TEST_ASSERT_FALSE(info.in_safe_mode);
}

// Test 10: Reserved Pins List
void test_gpio_manager_reserved_pins_list() {
    GPIOManager& mgr = GPIOManager::getInstance();
    mgr.initializeAllPinsToSafeMode();

    // Arrange: Reserve 3 pins
    mgr.requestPin(4, "sensor", "DS18B20");
    mgr.requestPin(21, "actuator", "Pump1");
    mgr.requestPin(22, "actuator", "Valve1");

    // Act: Get reserved pins list
    std::vector<GPIOPinInfo> reserved_list = mgr.getReservedPinsList();

    // Assert: List contains 3 pins
    TEST_ASSERT_EQUAL(3, reserved_list.size());

    // Assert: Reserved pin count matches
    TEST_ASSERT_EQUAL(3, mgr.getReservedPinCount());
}

// ============================================
// UNITY TEST RUNNER
// ============================================
int runAllTests(void) {
    UNITY_BEGIN();

    RUN_TEST(test_gpio_manager_safe_mode_initialization);
    RUN_TEST(test_gpio_manager_pin_request_success);
    RUN_TEST(test_gpio_manager_pin_request_reserved_fails);
    RUN_TEST(test_gpio_manager_pin_release);
    RUN_TEST(test_gpio_manager_pin_availability);
    RUN_TEST(test_gpio_manager_pin_mode_configuration);
    RUN_TEST(test_gpio_manager_digital_operations);
    RUN_TEST(test_gpio_manager_emergency_safe_mode);
    RUN_TEST(test_gpio_manager_pin_info);
    RUN_TEST(test_gpio_manager_reserved_pins_list);

    return UNITY_END();
}

#if defined(ARDUINO) && ARDUINO > 0
void setup() {
    delay(2000);
    runAllTests();
}
void loop() {}
#else
int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    return runAllTests();
}
#endif
