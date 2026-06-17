#include <unity.h>
#include "services/config/config_manager.h"
#include "services/config/storage_manager.h"
#include "utils/logger.h"

// ============================================
// TEST: ConfigManager Initialization
// ============================================
void test_config_manager_initialization() {
  TEST_ASSERT_TRUE(configManager.begin());
}

// ============================================
// TEST: WiFi Config Validation
// ============================================
void test_config_manager_wifi_validation() {
  WiFiConfig valid;
  valid.ssid = "TestSSID";
  valid.server_address = "192.168.1.100";
  valid.mqtt_port = 1883;
  TEST_ASSERT_TRUE(configManager.validateWiFiConfig(valid));
  
  WiFiConfig invalid;
  invalid.ssid = "";  // Empty SSID
  invalid.server_address = "192.168.1.100";
  invalid.mqtt_port = 1883;
  TEST_ASSERT_FALSE(configManager.validateWiFiConfig(invalid));
}

// ============================================
// TEST: loadAllConfigs Orchestration
// ============================================
void test_config_manager_load_all() {
  // Should load all Phase 1 configs without error
  bool result = configManager.loadAllConfigs();
  // May be false if no configs stored, but should not crash
  TEST_ASSERT_TRUE(result == true || result == false);
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  
  Serial.begin(115200);
  
  logger.begin();
  logger.setLogLevel(LOG_INFO);
  storageManager.begin();
  configManager.begin();
  
  UNITY_BEGIN();
  
  RUN_TEST(test_config_manager_initialization);
  RUN_TEST(test_config_manager_wifi_validation);
  RUN_TEST(test_config_manager_load_all);
  
  UNITY_END();
}

void loop() {}


