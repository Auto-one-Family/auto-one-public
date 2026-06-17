#include <unity.h>

#include "tasks/publish_queue_constants.h"
#include "tasks/publish_queue_policy.h"

void setUp(void) {}
void tearDown(void) {}

void test_publish_queue_size_and_watermark_aut481_p3() {
    TEST_ASSERT_EQUAL_UINT8(10, PUBLISH_QUEUE_SIZE);
    TEST_ASSERT_EQUAL_UINT8(5, PUBLISH_QUEUE_SHED_WATERMARK);
    TEST_ASSERT_EQUAL_UINT8(4, publishQueuePressureRecoveredThreshold());
}

void test_adaptive_drain_budget_default_when_healthy() {
    TEST_ASSERT_EQUAL_UINT8(1, computeAdaptivePublishDrainBudget(0, false, true, false));
    TEST_ASSERT_EQUAL_UINT8(1, computeAdaptivePublishDrainBudget(2, false, true, false));
}

void test_adaptive_drain_budget_boost_when_fill_high_and_healthy() {
    TEST_ASSERT_EQUAL_UINT8(2, computeAdaptivePublishDrainBudget(3, false, true, false));
    TEST_ASSERT_EQUAL_UINT8(2, computeAdaptivePublishDrainBudget(8, false, true, false));
}

void test_adaptive_drain_budget_no_boost_when_degraded() {
    TEST_ASSERT_EQUAL_UINT8(1, computeAdaptivePublishDrainBudget(5, true, true, false));
    TEST_ASSERT_EQUAL_UINT8(1, computeAdaptivePublishDrainBudget(5, false, false, false));
    TEST_ASSERT_EQUAL_UINT8(1, computeAdaptivePublishDrainBudget(5, false, true, true));
}

void test_actuator_status_defer_at_watermark_minus_one() {
    TEST_ASSERT_FALSE(shouldDeferActuatorStatusPublish(3));
    TEST_ASSERT_TRUE(shouldDeferActuatorStatusPublish(4));
    TEST_ASSERT_TRUE(shouldDeferActuatorStatusPublish(5));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_publish_queue_size_and_watermark_aut481_p3);
    RUN_TEST(test_adaptive_drain_budget_default_when_healthy);
    RUN_TEST(test_adaptive_drain_budget_boost_when_fill_high_and_healthy);
    RUN_TEST(test_adaptive_drain_budget_no_boost_when_degraded);
    RUN_TEST(test_actuator_status_defer_at_watermark_minus_one);
    return UNITY_END();
}
