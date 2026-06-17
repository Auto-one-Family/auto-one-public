#include <unity.h>
#include "../src/drivers/i2c_bus.h"
#include "../src/drivers/gpio_manager.h"
#include "../src/utils/logger.h"

// ============================================
// I2C Bus Manager Unit Tests
// ============================================
// Phase 3: Hardware Abstraction Layer Testing
//
// Test Strategy:
// - Basic initialization and lifecycle
// - Double initialization handling
// - Bus scanning (requires hardware or mocks)
// - Read/Write operations (requires hardware or mocks)
// - Error handling

// ============================================
// TEST SETUP & TEARDOWN
// ============================================

void setUp(void) {
    // Setup runs before each test
    // GPIO Manager must be initialized first
    static bool gpio_initialized = false;
    if (!gpio_initialized) {
        gpioManager.initializeAllPinsToSafeMode();
        gpio_initialized = true;
    }
}

void tearDown(void) {
    // Teardown runs after each test
    // Clean up I2C bus if initialized
    if (i2cBusManager.isInitialized()) {
        i2cBusManager.end();
    }
}

// ============================================
// BASIC INITIALIZATION TESTS
// ============================================

void test_i2c_bus_initialization(void) {
    // Test successful initialization
    bool result = i2cBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result, "I2C bus initialization should succeed");
    TEST_ASSERT_TRUE_MESSAGE(i2cBusManager.isInitialized(), 
                            "I2C bus should be marked as initialized");
}

void test_i2c_bus_double_initialization(void) {
    // First initialization
    bool result1 = i2cBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result1, "First initialization should succeed");
    
    // Second initialization (should be safe)
    bool result2 = i2cBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result2, "Double initialization should be safe");
    TEST_ASSERT_TRUE_MESSAGE(i2cBusManager.isInitialized(), 
                            "I2C bus should still be initialized");
}

void test_i2c_bus_end(void) {
    // Initialize
    i2cBusManager.begin();
    TEST_ASSERT_TRUE(i2cBusManager.isInitialized());
    
    // End
    i2cBusManager.end();
    TEST_ASSERT_FALSE_MESSAGE(i2cBusManager.isInitialized(), 
                             "I2C bus should be deinitialized after end()");
}

// ============================================
// STATUS QUERY TESTS
// ============================================

void test_i2c_bus_status_query(void) {
    // Before initialization
    TEST_ASSERT_FALSE_MESSAGE(i2cBusManager.isInitialized(), 
                             "I2C bus should not be initialized initially");
    
    // After initialization
    i2cBusManager.begin();
    String status = i2cBusManager.getBusStatus();
    TEST_ASSERT_TRUE_MESSAGE(status.length() > 0, 
                            "Status string should not be empty");
    TEST_ASSERT_TRUE_MESSAGE(status.indexOf("I2C[") >= 0, 
                            "Status should contain I2C identifier");
}

// ============================================
// BUS SCANNING TESTS (HARDWARE DEPENDENT)
// ============================================

void test_i2c_bus_scan_without_init(void) {
    // Try to scan without initialization
    uint8_t addresses[10];
    uint8_t found_count = 0;
    
    bool result = i2cBusManager.scanBus(addresses, 10, found_count);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Scan should fail when bus not initialized");
}

void test_i2c_bus_scan_with_init(void) {
    // Initialize bus
    i2cBusManager.begin();
    
    // Scan for devices
    uint8_t addresses[10];
    uint8_t found_count = 0;
    
    bool result = i2cBusManager.scanBus(addresses, 10, found_count);
    TEST_ASSERT_TRUE_MESSAGE(result, "Scan should succeed when initialized");
    
    // Note: found_count may be 0 if no devices connected
    TEST_MESSAGE("Found devices on I2C bus:");
    if (found_count == 0) {
        TEST_MESSAGE("  (No devices found - this is OK for testing)");
    } else {
        for (uint8_t i = 0; i < found_count; i++) {
            char msg[50];
            sprintf(msg, "  Device %d: 0x%02X", i, addresses[i]);
            TEST_MESSAGE(msg);
        }
    }
}

// ============================================
// DEVICE PRESENCE TESTS
// ============================================

void test_i2c_device_presence_without_init(void) {
    // Try to check device without initialization
    bool present = i2cBusManager.isDevicePresent(0x48);
    TEST_ASSERT_FALSE_MESSAGE(present, 
                             "Device check should fail when not initialized");
}

void test_i2c_device_presence_invalid_address(void) {
    // Initialize
    i2cBusManager.begin();
    
    // Check invalid address (outside 0x08-0x77)
    bool present = i2cBusManager.isDevicePresent(0x00);
    TEST_ASSERT_FALSE_MESSAGE(present, 
                             "Invalid address should return false");
}

// ============================================
// RAW DATA READING TESTS (HARDWARE DEPENDENT)
// ============================================

void test_i2c_read_without_init(void) {
    // Try to read without initialization
    uint8_t buffer[2];
    bool result = i2cBusManager.readRaw(0x48, 0x00, buffer, 2);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Read should fail when not initialized");
}

void test_i2c_read_null_buffer(void) {
    // Initialize
    i2cBusManager.begin();
    
    // Try to read with null buffer
    bool result = i2cBusManager.readRaw(0x48, 0x00, nullptr, 2);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Read should fail with null buffer");
}

void test_i2c_read_zero_length(void) {
    // Initialize
    i2cBusManager.begin();
    
    // Try to read zero bytes
    uint8_t buffer[2];
    bool result = i2cBusManager.readRaw(0x48, 0x00, buffer, 0);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Read should fail with zero length");
}

// ============================================
// RAW DATA WRITING TESTS (HARDWARE DEPENDENT)
// ============================================

void test_i2c_write_without_init(void) {
    // Try to write without initialization
    uint8_t data[2] = {0x01, 0x02};
    bool result = i2cBusManager.writeRaw(0x48, 0x00, data, 2);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Write should fail when not initialized");
}

void test_i2c_write_null_data(void) {
    // Initialize
    i2cBusManager.begin();
    
    // Try to write with null data
    bool result = i2cBusManager.writeRaw(0x48, 0x00, nullptr, 2);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Write should fail with null data");
}

// ============================================
// TEST RUNNER
// ============================================

void setup() {
    delay(2000);  // Wait for Serial
    
    UNITY_BEGIN();
    
    // Initialization Tests
    RUN_TEST(test_i2c_bus_initialization);
    RUN_TEST(test_i2c_bus_double_initialization);
    RUN_TEST(test_i2c_bus_end);
    
    // Status Tests
    RUN_TEST(test_i2c_bus_status_query);
    
    // Scanning Tests
    RUN_TEST(test_i2c_bus_scan_without_init);
    RUN_TEST(test_i2c_bus_scan_with_init);
    
    // Device Presence Tests
    RUN_TEST(test_i2c_device_presence_without_init);
    RUN_TEST(test_i2c_device_presence_invalid_address);
    
    // Raw Data Tests
    RUN_TEST(test_i2c_read_without_init);
    RUN_TEST(test_i2c_read_null_buffer);
    RUN_TEST(test_i2c_read_zero_length);
    RUN_TEST(test_i2c_write_without_init);
    RUN_TEST(test_i2c_write_null_data);
    
    UNITY_END();
}

void loop() {
    // Tests run once in setup()
}

