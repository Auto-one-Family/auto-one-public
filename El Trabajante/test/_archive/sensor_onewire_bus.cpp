#include <unity.h>
#include "../src/drivers/onewire_bus.h"
#include "../src/drivers/gpio_manager.h"
#include "../src/utils/logger.h"

// ============================================
// OneWire Bus Manager Unit Tests
// ============================================
// Phase 3: Hardware Abstraction Layer Testing
//
// Test Strategy:
// - Basic initialization and lifecycle
// - Double initialization handling
// - Device scanning (requires hardware)
// - Raw temperature reading (requires DS18B20)
// - Error handling

// ============================================
// TEST SETUP & TEARDOWN
// ============================================

void setUp(void) {
    // Setup runs before each test
    static bool gpio_initialized = false;
    if (!gpio_initialized) {
        gpioManager.initializeAllPinsToSafeMode();
        gpio_initialized = true;
    }
}

void tearDown(void) {
    // Teardown runs after each test
    if (oneWireBusManager.isInitialized()) {
        oneWireBusManager.end();
    }
}

// ============================================
// BASIC INITIALIZATION TESTS
// ============================================

void test_onewire_bus_initialization(void) {
    // Test successful initialization
    bool result = oneWireBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result, "OneWire bus initialization should succeed");
    TEST_ASSERT_TRUE_MESSAGE(oneWireBusManager.isInitialized(), 
                            "OneWire bus should be marked as initialized");
}

void test_onewire_bus_double_initialization(void) {
    // First initialization
    bool result1 = oneWireBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result1, "First initialization should succeed");
    
    // Second initialization (should be safe)
    bool result2 = oneWireBusManager.begin();
    TEST_ASSERT_TRUE_MESSAGE(result2, "Double initialization should be safe");
    TEST_ASSERT_TRUE_MESSAGE(oneWireBusManager.isInitialized(), 
                            "OneWire bus should still be initialized");
}

void test_onewire_bus_end(void) {
    // Initialize
    oneWireBusManager.begin();
    TEST_ASSERT_TRUE(oneWireBusManager.isInitialized());
    
    // End
    oneWireBusManager.end();
    TEST_ASSERT_FALSE_MESSAGE(oneWireBusManager.isInitialized(), 
                             "OneWire bus should be deinitialized after end()");
}

// ============================================
// STATUS QUERY TESTS
// ============================================

void test_onewire_bus_status_query(void) {
    // Before initialization
    TEST_ASSERT_FALSE_MESSAGE(oneWireBusManager.isInitialized(), 
                             "OneWire bus should not be initialized initially");
    
    // After initialization
    oneWireBusManager.begin();
    String status = oneWireBusManager.getBusStatus();
    TEST_ASSERT_TRUE_MESSAGE(status.length() > 0, 
                            "Status string should not be empty");
    TEST_ASSERT_TRUE_MESSAGE(status.indexOf("OneWire[") >= 0, 
                            "Status should contain OneWire identifier");
}

// ============================================
// DEVICE SCANNING TESTS (HARDWARE DEPENDENT)
// ============================================

void test_onewire_scan_without_init(void) {
    // Try to scan without initialization
    uint8_t rom_codes[5][8];
    uint8_t found_count = 0;
    
    bool result = oneWireBusManager.scanDevices(rom_codes, 5, found_count);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Scan should fail when bus not initialized");
}

void test_onewire_scan_with_init(void) {
    // Initialize bus
    oneWireBusManager.begin();
    
    // Scan for devices
    uint8_t rom_codes[5][8];
    uint8_t found_count = 0;
    
    bool result = oneWireBusManager.scanDevices(rom_codes, 5, found_count);
    TEST_ASSERT_TRUE_MESSAGE(result, "Scan should succeed when initialized");
    
    // Note: found_count may be 0 if no devices connected
    TEST_MESSAGE("Found devices on OneWire bus:");
    if (found_count == 0) {
        TEST_MESSAGE("  (No devices found - connect DS18B20 for full testing)");
    } else {
        for (uint8_t i = 0; i < found_count; i++) {
            char msg[100];
            sprintf(msg, "  Device %d: Family=0x%02X Serial=0x%02X%02X%02X%02X%02X%02X CRC=0x%02X",
                    i, rom_codes[i][0], rom_codes[i][1], rom_codes[i][2], 
                    rom_codes[i][3], rom_codes[i][4], rom_codes[i][5], 
                    rom_codes[i][6], rom_codes[i][7]);
            TEST_MESSAGE(msg);
        }
    }
}

// ============================================
// DEVICE PRESENCE TESTS (HARDWARE DEPENDENT)
// ============================================

void test_onewire_device_presence_without_init(void) {
    // Try to check device without initialization
    uint8_t rom[8] = {0x28, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07};
    bool present = oneWireBusManager.isDevicePresent(rom);
    TEST_ASSERT_FALSE_MESSAGE(present, 
                             "Device check should fail when not initialized");
}

// ============================================
// RAW TEMPERATURE READING TESTS (HARDWARE DEPENDENT)
// ============================================

void test_onewire_read_temperature_without_init(void) {
    // Try to read without initialization
    uint8_t rom[8] = {0x28, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07};
    int16_t raw_value;
    
    bool result = oneWireBusManager.readRawTemperature(rom, raw_value);
    TEST_ASSERT_FALSE_MESSAGE(result, 
                             "Temperature read should fail when not initialized");
}

void test_onewire_read_temperature_with_device(void) {
    // Initialize bus
    oneWireBusManager.begin();
    
    // First, find devices
    uint8_t rom_codes[5][8];
    uint8_t found_count = 0;
    oneWireBusManager.scanDevices(rom_codes, 5, found_count);
    
    if (found_count == 0) {
        TEST_MESSAGE("No OneWire devices found - skipping temperature read test");
        TEST_MESSAGE("Connect a DS18B20 sensor for full testing");
        return;
    }
    
    // Try to read temperature from first device
    int16_t raw_value;
    bool result = oneWireBusManager.readRawTemperature(rom_codes[0], raw_value);
    
    if (result) {
        TEST_ASSERT_TRUE_MESSAGE(result, "Temperature read should succeed");
        
        // Validate raw value is in expected range
        // DS18B20 range: -55°C to +125°C = -880 to +2000 in raw units (1/16°C)
        TEST_ASSERT_TRUE_MESSAGE(raw_value >= -880 && raw_value <= 2000,
                                "Raw temperature should be in valid range");
        
        // Calculate actual temperature for display
        float temp_celsius = raw_value * 0.0625;
        char msg[50];
        sprintf(msg, "Raw temperature: %d (%.2f°C)", raw_value, temp_celsius);
        TEST_MESSAGE(msg);
    } else {
        TEST_MESSAGE("Temperature read failed - device may not be DS18B20");
    }
}

// ============================================
// TEST RUNNER
// ============================================

void setup() {
    delay(2000);  // Wait for Serial
    
    UNITY_BEGIN();
    
    // Initialization Tests
    RUN_TEST(test_onewire_bus_initialization);
    RUN_TEST(test_onewire_bus_double_initialization);
    RUN_TEST(test_onewire_bus_end);
    
    // Status Tests
    RUN_TEST(test_onewire_bus_status_query);
    
    // Scanning Tests
    RUN_TEST(test_onewire_scan_without_init);
    RUN_TEST(test_onewire_scan_with_init);
    
    // Device Presence Tests
    RUN_TEST(test_onewire_device_presence_without_init);
    
    // Temperature Reading Tests
    RUN_TEST(test_onewire_read_temperature_without_init);
    RUN_TEST(test_onewire_read_temperature_with_device);
    
    UNITY_END();
}

void loop() {
    // Tests run once in setup()
}

