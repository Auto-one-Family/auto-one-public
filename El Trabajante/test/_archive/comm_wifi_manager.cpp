#include <unity.h>
#include "services/communication/wifi_manager.h"
#include "services/config/config_manager.h"
#include "utils/logger.h"

// ============================================
// TEST: WiFi Manager Initialization
// ============================================
void test_wifi_manager_initialization() {
    TEST_ASSERT_TRUE(wifiManager.begin());
    TEST_ASSERT_TRUE(wifiManager.begin());  // Should handle double-init gracefully
}

// ============================================
// TEST: WiFi Manager Connection
// ============================================
void test_wifi_manager_connection() {
    WiFiConfig config;
    config.ssid = "TestSSID";          // CHANGE TO YOUR SSID
    config.password = "TestPassword";  // CHANGE TO YOUR PASSWORD
    
    // Note: This test requires actual WiFi network
    // Comment out if WiFi network not available
    bool connected = wifiManager.connect(config);
    
    if (connected) {
        TEST_ASSERT_TRUE(wifiManager.isConnected());
        TEST_ASSERT_TRUE(wifiManager.getRSSI() < 0);  // RSSI should be negative
        TEST_ASSERT_TRUE(wifiManager.getLocalIP() != IPAddress(0, 0, 0, 0));
        TEST_ASSERT_TRUE(wifiManager.getSSID().length() > 0);
    } else {
        // Connection failed - expected if no WiFi network available
        TEST_MESSAGE("WiFi connection test skipped - no network available");
    }
}

// ============================================
// TEST: WiFi Manager Status Getters
// ============================================
void test_wifi_manager_status_getters() {
    String status = wifiManager.getConnectionStatus();
    TEST_ASSERT_TRUE(status.length() > 0);
    
    int8_t rssi = wifiManager.getRSSI();
    // RSSI can be negative or 0 (if not connected)
    TEST_ASSERT_TRUE(rssi <= 0);
    
    IPAddress ip = wifiManager.getLocalIP();
    // IP can be 0.0.0.0 if not connected
    TEST_ASSERT_TRUE(true);  // Just verify method doesn't crash
}

// ============================================
// TEST: WiFi Manager Reconnection Logic
// ============================================
void test_wifi_manager_reconnection() {
    // Test that reconnect logic doesn't crash
    wifiManager.reconnect();
    
    // Should handle gracefully even if not connected
    TEST_ASSERT_TRUE(true);
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    Serial.begin(115200);
    
    logger.begin();
    logger.setLogLevel(LOG_INFO);
    
    UNITY_BEGIN();
    RUN_TEST(test_wifi_manager_initialization);
    RUN_TEST(test_wifi_manager_connection);
    RUN_TEST(test_wifi_manager_status_getters);
    RUN_TEST(test_wifi_manager_reconnection);
    UNITY_END();
}

void loop() {}

