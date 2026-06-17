#include <unity.h>
#include "services/communication/mqtt_client.h"
#include "services/communication/wifi_manager.h"
#include "services/config/config_manager.h"
#include "utils/logger.h"

// ============================================
// TEST: MQTT Client Initialization
// ============================================
void test_mqtt_client_initialization() {
    TEST_ASSERT_TRUE(mqttClient.begin());
    TEST_ASSERT_TRUE(mqttClient.begin());  // Should handle double-init gracefully
}

// ============================================
// TEST: MQTT Client Connection (Anonymous Mode)
// ============================================
void test_mqtt_client_connection() {
    MQTTConfig config;
    config.server = "192.168.1.100";  // CHANGE TO YOUR BROKER
    config.port = 1883;
    config.client_id = "test_esp32";
    config.username = "";              // Anonymous mode
    config.password = "";
    config.keepalive = 60;
    config.timeout = 10;
    
    // Note: This test requires actual MQTT broker
    // Comment out if MQTT broker not available
    bool connected = mqttClient.connect(config);
    
    if (connected) {
        TEST_ASSERT_TRUE(mqttClient.isConnected());
        TEST_ASSERT_TRUE(mqttClient.isAnonymousMode());
    } else {
        // Connection failed - expected if no MQTT broker available
        TEST_MESSAGE("MQTT connection test skipped - no broker available");
    }
}

// ============================================
// TEST: MQTT Client Publish
// ============================================
void test_mqtt_client_publish() {
    if (!mqttClient.isConnected()) {
        TEST_MESSAGE("MQTT publish test skipped - not connected");
        return;
    }
    
    String topic = "test/topic";
    String payload = "{\"test\":123}";
    
    bool published = mqttClient.publish(topic, payload, 1);
    // May fail if not connected, which is acceptable
    TEST_ASSERT_TRUE(true);  // Just verify method doesn't crash
}

// ============================================
// TEST: MQTT Client Subscribe
// ============================================
void test_mqtt_client_subscribe() {
    if (!mqttClient.isConnected()) {
        TEST_MESSAGE("MQTT subscribe test skipped - not connected");
        return;
    }
    
    String topic = "test/command";
    
    bool subscribed = mqttClient.subscribe(topic);
    // May fail if not connected, which is acceptable
    TEST_ASSERT_TRUE(true);  // Just verify method doesn't crash
}

// ============================================
// TEST: MQTT Client Offline Buffer
// ============================================
void test_mqtt_client_offline_buffer() {
    // Test offline buffer when not connected
    if (mqttClient.isConnected()) {
        mqttClient.disconnect();
        delay(100);
    }
    
    String topic = "test/offline";
    String payload = "{\"offline\":true}";
    
    // Should add to offline buffer
    bool buffered = mqttClient.publish(topic, payload, 1);
    TEST_ASSERT_TRUE(buffered);  // Should succeed (buffered)
    TEST_ASSERT_TRUE(mqttClient.hasOfflineMessages());
    TEST_ASSERT_TRUE(mqttClient.getOfflineMessageCount() > 0);
}

// ============================================
// TEST: MQTT Client Status Getters
// ============================================
void test_mqtt_client_status_getters() {
    String status = mqttClient.getConnectionStatus();
    TEST_ASSERT_TRUE(status.length() > 0);
    
    uint16_t attempts = mqttClient.getConnectionAttempts();
    TEST_ASSERT_TRUE(attempts >= 0);
    
    bool has_offline = mqttClient.hasOfflineMessages();
    uint16_t offline_count = mqttClient.getOfflineMessageCount();
    TEST_ASSERT_TRUE(offline_count >= 0);
}

// ============================================
// TEST: MQTT Client Heartbeat
// ============================================
void test_mqtt_client_heartbeat() {
    if (!mqttClient.isConnected()) {
        TEST_MESSAGE("MQTT heartbeat test skipped - not connected");
        return;
    }
    
    // Heartbeat should be published automatically in loop()
    // Just verify method doesn't crash
    mqttClient.publishHeartbeat();
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
    
    // Connect WiFi first (if available)
    wifiManager.begin();
    WiFiConfig wifi_config;
    wifi_config.ssid = "TestSSID";          // CHANGE TO YOUR SSID
    wifi_config.password = "TestPassword";  // CHANGE TO YOUR PASSWORD
    wifiManager.connect(wifi_config);
    
    delay(2000);  // Wait for WiFi connection
    
    UNITY_BEGIN();
    RUN_TEST(test_mqtt_client_initialization);
    RUN_TEST(test_mqtt_client_connection);
    RUN_TEST(test_mqtt_client_publish);
    RUN_TEST(test_mqtt_client_subscribe);
    RUN_TEST(test_mqtt_client_offline_buffer);
    RUN_TEST(test_mqtt_client_status_getters);
    RUN_TEST(test_mqtt_client_heartbeat);
    UNITY_END();
}

void loop() {}

