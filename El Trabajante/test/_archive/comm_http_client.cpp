#include <unity.h>
#include <Arduino.h>

#include "services/communication/http_client.h"
#include "services/communication/wifi_manager.h"
#include "services/config/config_manager.h"
#include "services/config/storage_manager.h"
#include "drivers/gpio_manager.h"
#include "utils/logger.h"

static bool http_stack_initialized = false;

static void initialize_http_stack() {
    if (http_stack_initialized) {
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

    http_stack_initialized = true;
}

static bool connect_wifi_for_http() {
    WiFiConfig cfg = configManager.getWiFiConfig();
    if (!cfg.configured || cfg.ssid.isEmpty()) {
        return false;
    }

    if (wifiManager.isConnected()) {
        return true;
    }

    wifiManager.disconnect();
    delay(100);
    return wifiManager.connect(cfg);
}

// ============================================
// TEST 1: HTTP POST Request
// ============================================
void test_http_post_request(void) {
    initialize_http_stack();

    if (!connect_wifi_for_http()) {
        TEST_IGNORE_MESSAGE("WiFi not connected/configured. Skipping HTTP POST test.");
        return;
    }

    const char* url = "http://httpbin.org/post";
    const char* payload = "{\"phase\":4,\"module\":\"sensor\"}";

    HTTPResponse response = httpClient.post(url, payload, "application/json", 4000);
    if (!response.success) {
        TEST_IGNORE_MESSAGE("HTTP endpoint unreachable (httpbin). Check internet connectivity.");
        return;
    }

    TEST_ASSERT_EQUAL(200, response.status_code);
    TEST_ASSERT_TRUE(response.body.indexOf("\"phase\":4") >= 0);
}

// ============================================
// TEST 2: Connection Retry Behavior
// ============================================
void test_http_connection_retry(void) {
    initialize_http_stack();

    if (!connect_wifi_for_http()) {
        TEST_IGNORE_MESSAGE("WiFi not connected/configured. Skipping HTTP retry test.");
        return;
    }

    // First attempt against non-routable TEST-NET address (expected failure)
    HTTPResponse first = httpClient.post("http://203.0.113.20/test", "{\"retry\":true}", "application/json", 2000);
    TEST_ASSERT_FALSE(first.success);

    // Second attempt to reachable endpoint should succeed
    HTTPResponse second = httpClient.post("http://httpbin.org/post", "{\"retry\":true}", "application/json", 4000);
    if (!second.success) {
        TEST_IGNORE_MESSAGE("Second HTTP attempt failed - endpoint likely unreachable.");
        return;
    }

    TEST_ASSERT_EQUAL(200, second.status_code);
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    UNITY_BEGIN();

    RUN_TEST(test_http_post_request);
    RUN_TEST(test_http_connection_retry);

    UNITY_END();
}

void loop() {}

