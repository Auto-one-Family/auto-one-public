#include <unity.h>
#include "utils/logger.h"

// ============================================
// TEST: Circular Buffer Overflow
// ============================================
void test_logger_circular_buffer() {
  logger.clearLogs();
  logger.setLogLevel(LOG_DEBUG);
  
  // Add more than MAX_LOG_ENTRIES (50)
  for (int i = 0; i < 60; i++) {
    logger.info("Message " + String(i));
  }
  
  // Should have exactly 50 (MAX_LOG_ENTRIES)
  TEST_ASSERT_EQUAL(50, logger.getLogCount());
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  UNITY_BEGIN();
  
  RUN_TEST(test_logger_circular_buffer);
  
  UNITY_END();
}

void loop() {}


