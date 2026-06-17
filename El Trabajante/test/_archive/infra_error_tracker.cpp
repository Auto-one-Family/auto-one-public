#include <unity.h>
#include "error_handling/error_tracker.h"
#include "utils/logger.h"

// ============================================
// TEST: ErrorTracker Initialization
// ============================================
void test_error_tracker_initialization() {
  errorTracker.begin();
  TEST_ASSERT_EQUAL(0, errorTracker.getErrorCount());
  TEST_ASSERT_FALSE(errorTracker.hasActiveErrors());
}

// ============================================
// TEST: Error Categories
// ============================================
void test_error_tracker_categories() {
  errorTracker.clearErrors();
  
  errorTracker.logHardwareError(1, "Hardware error");
  errorTracker.logServiceError(1, "Service error");
  errorTracker.logCommunicationError(1, "Communication error");
  errorTracker.logApplicationError(1, "Application error");
  
  TEST_ASSERT_EQUAL(4, errorTracker.getErrorCount());
  TEST_ASSERT_EQUAL(1, errorTracker.getErrorCountByCategory(ERROR_HARDWARE));
  TEST_ASSERT_EQUAL(1, errorTracker.getErrorCountByCategory(ERROR_SERVICE));
  TEST_ASSERT_EQUAL(1, errorTracker.getErrorCountByCategory(ERROR_COMMUNICATION));
  TEST_ASSERT_EQUAL(1, errorTracker.getErrorCountByCategory(ERROR_APPLICATION));
}

// ============================================
// TEST: Circular Buffer Overflow
// ============================================
void test_error_tracker_circular_buffer() {
  errorTracker.clearErrors();

  // Add more than MAX_ERROR_ENTRIES (50)
  for (int i = 0; i < 60; i++) {
    String msg = "Error " + String(i);
    errorTracker.trackError(1000 + i, msg.c_str());
  }

  // Should have exactly 50 entries (MAX_ERROR_ENTRIES)
  TEST_ASSERT_EQUAL(50, errorTracker.getErrorCount());
}

// ============================================
// TEST: Critical Errors Detection
// ============================================
void test_error_tracker_critical_errors() {
  errorTracker.clearErrors();
  
  errorTracker.trackError(1001, ERROR_SEVERITY_ERROR, "Normal error");
  TEST_ASSERT_FALSE(errorTracker.hasCriticalErrors());
  
  errorTracker.trackError(1002, ERROR_SEVERITY_CRITICAL, "Critical error");
  TEST_ASSERT_TRUE(errorTracker.hasCriticalErrors());
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  
  Serial.begin(115200);
  
  logger.begin();
  logger.setLogLevel(LOG_INFO);
  errorTracker.begin();
  
  UNITY_BEGIN();
  
  RUN_TEST(test_error_tracker_initialization);
  RUN_TEST(test_error_tracker_circular_buffer);
  RUN_TEST(test_error_tracker_critical_errors);
  RUN_TEST(test_error_tracker_categories);
  
  UNITY_END();
}

void loop() {}


