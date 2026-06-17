#include <unity.h>
#include "services/config/storage_manager.h"
#include "utils/logger.h"

// ============================================
// TEST: StorageManager Initialization
// ============================================
void test_storage_manager_initialization() {
  TEST_ASSERT_TRUE(storageManager.begin());
}

// ============================================
// TEST: Namespace Isolation
// ============================================
void test_storage_manager_namespace_isolation() {
  // Write to namespace1
  storageManager.beginNamespace("ns1", false);
  storageManager.putString("key", "value1");
  storageManager.endNamespace();
  
  // Write to namespace2
  storageManager.beginNamespace("ns2", false);
  storageManager.putString("key", "value2");
  storageManager.endNamespace();
  
  // Read from namespace1 (should be "value1")
  storageManager.beginNamespace("ns1", true);
  String val1 = storageManager.getStringObj("key", "");
  storageManager.endNamespace();
  TEST_ASSERT_EQUAL_STRING("value1", val1.c_str());
  
  // Read from namespace2 (should be "value2")
  storageManager.beginNamespace("ns2", true);
  String val2 = storageManager.getStringObj("key", "");
  storageManager.endNamespace();
  TEST_ASSERT_EQUAL_STRING("value2", val2.c_str());
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  
  logger.begin();
  logger.setLogLevel(LOG_INFO);
  
  UNITY_BEGIN();
  
  RUN_TEST(test_storage_manager_initialization);
  RUN_TEST(test_storage_manager_namespace_isolation);
  
  UNITY_END();
}

void loop() {}


