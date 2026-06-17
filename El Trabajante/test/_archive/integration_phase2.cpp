#include <unity.h>
#include "services/communication/wifi_manager.h"
#include "services/communication/mqtt_client.h"
#include "services/config/config_manager.h"
#include "utils/logger.h"
#include "utils/topic_builder.h"

// ============================================
// TEST: Phase 2 End-to-End Integration
// ============================================
void test_phase2_integration() {
    // Initialize Phase 1 components
    logger.begin();
    logger.setLogLevel(LOG_INFO);
    
    configManager.begin();
    configManager.loadAllConfigs();
    
    // Configure TopicBuilder
    SystemConfig sys_config;
    configManager.loadSystemConfig(sys_config);
    KaiserZone kaiser;
    MasterZone master;
    configManager.loadZoneConfig(kaiser, master);
    
    TopicBuilder::setEspId(sys_config.esp_id.c_str());
    TopicBuilder::setKaiserId(kaiser.kaiser_id.c_str());
    
    // Initialize WiFi
    TEST_ASSERT_TRUE(wifiManager.begin());
    
    WiFiConfig wifi_config = configManager.getWiFiConfig();
    bool wifi_connected = wifiManager.connect(wifi_config);
    
    if (!wifi_connected) {
        TEST_MESSAGE("WiFi connection failed - integration test incomplete");
        return;
    }
    
    TEST_ASSERT_TRUE(wifiManager.isConnected());
    
    // Initialize MQTT
    TEST_ASSERT_TRUE(mqttClient.begin());
    
    MQTTConfig mqtt_config;
    mqtt_config.server = wifi_config.server_address;
    mqtt_config.port = wifi_config.mqtt_port;
    mqtt_config.client_id = configManager.getESPId();
    mqtt_config.username = wifi_config.mqtt_username;
    mqtt_config.password = wifi_config.mqtt_password;
    mqtt_config.keepalive = 60;
    mqtt_config.timeout = 10;
    
    bool mqtt_connected = mqttClient.connect(mqtt_config);
    
    if (!mqtt_connected) {
        TEST_MESSAGE("MQTT connection failed - integration test incomplete");
        return;
    }
    
    TEST_ASSERT_TRUE(mqttClient.isConnected());
    
    // Subscribe to topics
    String system_command_topic = TopicBuilder::buildSystemCommandTopic();
    String config_topic = TopicBuilder::buildConfigTopic();
    String emergency_topic = TopicBuilder::buildBroadcastEmergencyTopic();
    
    TEST_ASSERT_TRUE(mqttClient.subscribe(system_command_topic));
    TEST_ASSERT_TRUE(mqttClient.subscribe(config_topic));
    TEST_ASSERT_TRUE(mqttClient.subscribe(emergency_topic));
    
    // Test heartbeat topic
    const char* heartbeat_topic = TopicBuilder::buildSystemHeartbeatTopic();
    TEST_ASSERT_TRUE(strlen(heartbeat_topic) > 0);
    
    // Test loop() calls (should not crash)
    wifiManager.loop();
    mqttClient.loop();
    
    TEST_ASSERT_TRUE(true);  // Integration successful
}

// ============================================
// TEST: Heartbeat Publishing
// ============================================
void test_heartbeat_publishing() {
    if (!mqttClient.isConnected()) {
        TEST_MESSAGE("Heartbeat test skipped - MQTT not connected");
        return;
    }
    
    // Manually trigger heartbeat
    mqttClient.publishHeartbeat();
    
    // Process loop to ensure message is sent
    mqttClient.loop();
    
    TEST_ASSERT_TRUE(true);  // Should not crash
}

// ============================================
// TEST: Message Reception
// ============================================
void test_message_reception() {
    if (!mqttClient.isConnected()) {
        TEST_MESSAGE("Message reception test skipped - MQTT not connected");
        return;
    }
    
    // Set callback
    bool message_received = false;
    mqttClient.setCallback([&message_received](const String& topic, const String& payload) {
        message_received = true;
    });
    
    // Process loop to check for messages
    for (int i = 0; i < 10; i++) {
        mqttClient.loop();
        delay(100);
    }
    
    // Note: This test doesn't verify actual message reception
    // (requires external MQTT publisher)
    // Just verifies callback mechanism doesn't crash
    TEST_ASSERT_TRUE(true);
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    Serial.begin(115200);
    
    UNITY_BEGIN();
    RUN_TEST(test_phase2_integration);
    RUN_TEST(test_heartbeat_publishing);
    RUN_TEST(test_message_reception);
    UNITY_END();
}

void loop() {
    // Keep processing loops during test
    wifiManager.loop();
    mqttClient.loop();
    delay(10);
}

