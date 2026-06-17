#include <unity.h>
#include <Arduino.h>

#define private public
#define protected public
#include "services/sensor/pi_enhanced_processor.h"
#undef private
#undef protected

#include "services/config/config_manager.h"
#include "services/config/storage_manager.h"
#include "services/communication/wifi_manager.h"
#include "services/communication/http_client.h"
#include "services/communication/mqtt_client.h"
#include "utils/logger.h"
#include "drivers/gpio_manager.h"

static bool pi_stack_initialized = false;

static void initialize_pi_stack() {
    if (pi_stack_initialized) {
        return;
    }

    Serial.begin(115200);
    delay(200);

    logger.begin();
    logger.setLogLevel(LOG_INFO);
    gpioManager.initializeAllPinsToSafeMode();
    storageManager.begin();
    configManager.begin();
    configManager.loadAllConfigs();

    wifiManager.begin();
    httpClient.begin();
    pi_stack_initialized = true;
}

static bool ensure_wifi_connected() {
    WiFiConfig wifi_config = configManager.getWiFiConfig();
    if (!wifi_config.configured || wifi_config.ssid.isEmpty()) {
        return false;
    }

    if (wifiManager.isConnected()) {
        return true;
    }

    wifiManager.disconnect();
    delay(100);
    return wifiManager.connect(wifi_config);
}

static RawSensorData makeRawPayload(uint8_t gpio = 4, uint32_t raw = 2048) {
    RawSensorData data;
    data.gpio = gpio;
    data.sensor_type = "test_sensor";
    data.raw_value = raw;
    data.timestamp = millis();
    data.metadata = "{}";
    return data;
}

// ============================================
// TEST 1: HTTP POST Successful Flow
// ============================================
void test_http_post_raw_data(void) {
    initialize_pi_stack();

    if (!ensure_wifi_connected()) {
        TEST_IGNORE_MESSAGE("WiFi not connected/configured. Skipping Pi HTTP test.");
        return;
    }

    PiEnhancedProcessor& piProcessor = PiEnhancedProcessor::getInstance();
    TEST_ASSERT_TRUE(piProcessor.begin());

    RawSensorData raw = makeRawPayload();
    ProcessedSensorData processed;

    bool success = piProcessor.sendRawData(raw, processed);
    if (!success) {
        TEST_IGNORE_MESSAGE("Pi server unreachable. Ensure server_address is reachable.");
        return;
    }

    TEST_ASSERT_TRUE(processed.valid);
    TEST_ASSERT_TRUE(processed.unit.length() > 0);
}

// ============================================
// TEST 2: HTTP Timeout Handling
// ============================================
void test_http_timeout_handling(void) {
    initialize_pi_stack();

    if (!ensure_wifi_connected()) {
        TEST_IGNORE_MESSAGE("WiFi not connected/configured. Skipping timeout test.");
        return;
    }

    PiEnhancedProcessor& piProcessor = PiEnhancedProcessor::getInstance();
    TEST_ASSERT_TRUE(piProcessor.begin());

    String original_address = piProcessor.pi_server_address_;
    piProcessor.pi_server_address_ = "203.0.113.10";  // TEST-NET-3, non-routable

    RawSensorData raw = makeRawPayload(5, 1234);
    ProcessedSensorData processed;

    bool success = piProcessor.sendRawData(raw, processed);
    TEST_ASSERT_FALSE(success);
    TEST_ASSERT_FALSE(processed.valid);
    TEST_ASSERT_TRUE(piProcessor.getConsecutiveFailures() >= 1);

    piProcessor.pi_server_address_ = original_address;
    piProcessor.resetCircuitBreaker();
}

// ============================================
// TEST 3: HTTP Failure Fallback Placeholder
// ============================================
void test_http_failure_sets_error(void) {
    initialize_pi_stack();

    PiEnhancedProcessor& piProcessor = PiEnhancedProcessor::getInstance();
    TEST_ASSERT_TRUE(piProcessor.begin());

    // Force failure by clearing WiFi connection
    wifiManager.disconnect();
    delay(100);

    RawSensorData raw = makeRawPayload(6, 512);
    ProcessedSensorData processed;

    bool success = piProcessor.sendRawData(raw, processed);
    TEST_ASSERT_FALSE(success);
    TEST_ASSERT_FALSE(processed.valid);

    // TODO: Phase 5 - Verify MQTT raw publish fallback once implemented.
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    UNITY_BEGIN();

    RUN_TEST(test_http_post_raw_data);
    RUN_TEST(test_http_timeout_handling);
    RUN_TEST(test_http_failure_sets_error);

    UNITY_END();
}

void loop() {}

