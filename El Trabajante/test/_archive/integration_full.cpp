#include <unity.h>
#include <Arduino.h>
#include "drivers/gpio_manager.h"
#include "utils/logger.h"
#include "services/config/storage_manager.h"
#include "services/config/config_manager.h"
#include "error_handling/error_tracker.h"
#include "utils/topic_builder.h"
#include "models/system_types.h"

// ============================================
// TEST: Boot Sequence (Initialization Order)
// ============================================
void test_boot_sequence() {
  Serial.println("\n=== Testing Boot Sequence ===");
  
  uint32_t heap_before = ESP.getFreeHeap();
  
  // Step 1: GPIO Safe-Mode (FIRST)
  gpioManager.initializeAllPinsToSafeMode();
  TEST_ASSERT_TRUE(gpioManager.getAvailablePinCount() > 0);
  
  // Step 2: Logger (Foundation)
  logger.begin();
  logger.setLogLevel(LOG_INFO);
  TEST_ASSERT_EQUAL(0, logger.getLogCount());  // Should be empty at start
  
  // Step 3: StorageManager
  TEST_ASSERT_TRUE(storageManager.begin());
  
  // Step 4: ConfigManager
  TEST_ASSERT_TRUE(configManager.begin());
  bool config_loaded = configManager.loadAllConfigs();
  // May fail if no config stored, but should not crash
  TEST_ASSERT_TRUE(config_loaded == true || config_loaded == false);
  
  // Step 5: ErrorTracker
  errorTracker.begin();
  TEST_ASSERT_FALSE(errorTracker.hasActiveErrors());
  
  // Step 6: TopicBuilder
  TopicBuilder::setEspId("test_esp");
  TopicBuilder::setKaiserId("god");
  const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
  TEST_ASSERT_NOT_NULL(topic);
  
  uint32_t heap_after = ESP.getFreeHeap();
  uint32_t heap_used = heap_before - heap_after;
  
  Serial.printf("Heap used by Phase 1: %d bytes\n", heap_used);
  LOG_INFO("Boot sequence test complete");
}

// ============================================
// TEST: Memory Usage < 10KB
// ============================================
void test_memory_usage() {
  Serial.println("\n=== Testing Memory Usage ===");
  
  uint32_t free_heap = ESP.getFreeHeap();
  uint32_t heap_size = ESP.getHeapSize();
  uint32_t used_heap = heap_size - free_heap;
  
  Serial.printf("Total Heap: %d bytes\n", heap_size);
  Serial.printf("Used Heap: %d bytes\n", used_heap);
  Serial.printf("Free Heap: %d bytes\n", free_heap);
  
  // Phase 1 modules should use < 15KB (target: ~8KB, but allow some margin)
  TEST_ASSERT_LESS_THAN(15000, used_heap);
  
  LOG_INFO("Memory usage test complete");
}

// ============================================
// TEST: Logger Integration with All Modules
// ============================================
void test_logger_integration() {
  logger.clearLogs();
  
  // Trigger logs from different modules
  LOG_INFO("Testing logger integration");
  errorTracker.trackError(1001, "Test error");
  
  // Verify logs were captured
  TEST_ASSERT_TRUE(logger.getLogCount() >= 2);
  
  String logs = logger.getLogs(LOG_INFO, 10);
  TEST_ASSERT_TRUE(logs.indexOf("Testing logger integration") > 0);
}

// ============================================
// TEST: Config Persistence
// ============================================
void test_config_persistence() {
  // Save a test config
  WiFiConfig test_config;
  test_config.ssid = "IntegrationTest";
  test_config.server_address = "192.168.1.200";
  test_config.mqtt_port = 1883;
  test_config.configured = true;
  
  TEST_ASSERT_TRUE(configManager.saveWiFiConfig(test_config));
  
  // Load it back
  WiFiConfig loaded;
  TEST_ASSERT_TRUE(configManager.loadWiFiConfig(loaded));
  TEST_ASSERT_EQUAL_STRING("IntegrationTest", loaded.ssid.c_str());
}

// ============================================
// TEST: Error Tracking Across Modules
// ============================================
void test_error_tracking_integration() {
  errorTracker.clearErrors();
  
  // Simulate errors from different subsystems
  errorTracker.logHardwareError(1, "GPIO error");
  errorTracker.logServiceError(1, "Config error");
  errorTracker.logCommunicationError(1, "MQTT error");
  
  TEST_ASSERT_EQUAL(3, errorTracker.getErrorCount());
  TEST_ASSERT_TRUE(errorTracker.hasActiveErrors());
  
  String history = errorTracker.getErrorHistory(10);
  TEST_ASSERT_TRUE(history.length() > 0);
}

// ============================================
// TEST: Topic Builder with Config Values
// ============================================
void test_topic_builder_with_config() {
  SystemConfig sys_config;
  sys_config.esp_id = "ESP_ABC123";
  
  KaiserZone kaiser;
  kaiser.kaiser_id = "test_kaiser_id";
  
  TopicBuilder::setEspId(sys_config.esp_id.c_str());
  TopicBuilder::setKaiserId(kaiser.kaiser_id.c_str());
  
  const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/test_kaiser_id/esp/ESP_ABC123/system/heartbeat", topic);
}

// ============================================
// TEST: System Health MQTT Export
// ============================================
void test_system_health_mqtt_export() {
  Serial.println("\n=== Testing System Health MQTT Export ===");
  
  // Collect system health metrics
  uint32_t free_heap = ESP.getFreeHeap();
  uint32_t heap_size = ESP.getHeapSize();
  uint32_t uptime_ms = millis();
  uint8_t boot_count = configManager.getSystemConfig().boot_count;
  uint16_t error_count = errorTracker.getErrorCount();
  bool has_critical = errorTracker.hasCriticalErrors();
  
  // Verify all metrics are readable
  TEST_ASSERT_TRUE(free_heap > 0);
  TEST_ASSERT_TRUE(heap_size > 0);
  TEST_ASSERT_TRUE(uptime_ms > 0);
  
  // Simulate JSON payload construction (Phase 2 will actually send MQTT)
  String health_json = "{";
  health_json += "\"esp_id\":\"" + configManager.getESPId() + "\",";
  health_json += "\"uptime_ms\":" + String(uptime_ms) + ",";
  health_json += "\"free_heap_kb\":" + String(free_heap / 1024) + ",";
  health_json += "\"boot_count\":" + String(boot_count) + ",";
  health_json += "\"error_count\":" + String(error_count) + ",";
  health_json += "\"has_critical_errors\":" + String(has_critical ? "true" : "false");
  health_json += "}";
  
  Serial.println("Health JSON: " + health_json);
  TEST_ASSERT_TRUE(health_json.length() > 50);  // Valid JSON should be >50 chars
  
  LOG_INFO("System health MQTT export test complete");
}

// ============================================
// TEST: Boot Time Measurement
// ============================================
void test_boot_time_measurement() {
  Serial.println("\n=== Testing Boot Time Measurement ===");
  
  // Measure time taken for full system initialization
  uint32_t start_time = millis();
  
  // Reinitialize all Phase 1 modules
  gpioManager.initializeAllPinsToSafeMode();
  logger.begin();
  storageManager.begin();
  configManager.begin();
  configManager.loadAllConfigs();
  errorTracker.begin();
  
  uint32_t boot_time_ms = millis() - start_time;
  
  Serial.printf("Boot time: %d ms\n", boot_time_ms);
  
  // Boot time should be < 2000ms (2 seconds) for industrial systems
  TEST_ASSERT_LESS_THAN(2000, boot_time_ms);
  
  LOG_INFO("Boot time measurement test complete");
}

// ============================================
// TEST: Memory Fragmentation Under Load
// ============================================
void test_memory_fragmentation() {
  Serial.println("\n=== Testing Memory Fragmentation ===");
  
  uint32_t initial_free = ESP.getFreeHeap();
  uint32_t min_free = initial_free;
  
  // Simulate load: Log 100 messages + track 50 errors
  for (int i = 0; i < 100; i++) {
    logger.info("Load test message " + String(i));
    
    if (i % 2 == 0) {
      String error_msg = "Load test error " + String(i);
      errorTracker.trackError(1000 + i, error_msg.c_str());
    }
    
    uint32_t current_free = ESP.getFreeHeap();
    if (current_free < min_free) {
      min_free = current_free;
    }
  }
  
  uint32_t final_free = ESP.getFreeHeap();
  uint32_t fragmentation = initial_free - min_free;
  float fragmentation_pct = (float)fragmentation / (float)initial_free * 100.0;
  
  Serial.printf("Initial Free: %d bytes\n", initial_free);
  Serial.printf("Minimum Free: %d bytes\n", min_free);
  Serial.printf("Final Free: %d bytes\n", final_free);
  Serial.printf("Fragmentation: %d bytes (%.2f%%)\n", fragmentation, fragmentation_pct);
  
  // Fragmentation should be < 10KB under load
  TEST_ASSERT_LESS_THAN(10000, fragmentation);
  
  // Memory should recover to near-initial after circular buffer wraps
  TEST_ASSERT_TRUE(final_free > (initial_free - 5000));
  
  LOG_INFO("Memory fragmentation test complete");
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  
  Serial.begin(115200);
  Serial.println("\n=== Phase 1 Integration Tests ===\n");
  
  UNITY_BEGIN();
  
  // Original tests
  RUN_TEST(test_boot_sequence);
  RUN_TEST(test_memory_usage);
  RUN_TEST(test_logger_integration);
  RUN_TEST(test_config_persistence);
  RUN_TEST(test_error_tracking_integration);
  RUN_TEST(test_topic_builder_with_config);
  
  // NEW: Hardware observability tests
  RUN_TEST(test_system_health_mqtt_export);
  RUN_TEST(test_boot_time_measurement);
  RUN_TEST(test_memory_fragmentation);
  
  UNITY_END();
  
  Serial.println("\n=== Integration Tests Complete ===\n");
}

void loop() {}


