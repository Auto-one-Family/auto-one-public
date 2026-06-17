#include <unity.h>

#include "services/config/runtime_readiness_policy.h"
#include "tasks/command_admission.h"

void setUp(void) {}
void tearDown(void) {}

void test_runtime_readiness_ready_when_offline_rules_missing() {
    RuntimeReadinessSnapshot snapshot{1, 1, 0};
    RuntimeReadinessDecision decision =
        evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());
    TEST_ASSERT_TRUE(decision.ready);
    TEST_ASSERT_EQUAL_STRING("CONFIG_PENDING_EXIT_READY", decision.decision_code);
}

void test_runtime_readiness_ready_when_basis_complete() {
    RuntimeReadinessSnapshot snapshot{1, 2, 1};
    RuntimeReadinessDecision decision =
        evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());
    TEST_ASSERT_TRUE(decision.ready);
    TEST_ASSERT_EQUAL_STRING("CONFIG_PENDING_EXIT_READY", decision.decision_code);
}

void test_runtime_readiness_auto_exit_offline_rules_only() {
    RuntimeReadinessSnapshot snapshot{0, 0, 3};
    RuntimeReadinessDecision decision =
        evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());
    TEST_ASSERT_TRUE(decision.ready);
    TEST_ASSERT_EQUAL_STRING("OFFLINE_RULES_ONLY_AUTO_EXIT", decision.decision_code);
}

void test_runtime_readiness_auto_exit_offline_rules_with_sensors() {
    RuntimeReadinessSnapshot snapshot{2, 0, 1};
    RuntimeReadinessDecision decision =
        evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());
    TEST_ASSERT_TRUE(decision.ready);
    TEST_ASSERT_EQUAL_STRING("OFFLINE_RULES_ONLY_AUTO_EXIT", decision.decision_code);
}

void test_runtime_readiness_blocked_without_offline_rules_no_actuators() {
    RuntimeReadinessSnapshot snapshot{1, 0, 0};
    RuntimeReadinessDecision decision =
        evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());
    TEST_ASSERT_FALSE(decision.ready);
    TEST_ASSERT_EQUAL_STRING("MISSING_ACTUATORS", decision.decision_code);
}

void test_system_command_rejected_in_pending_when_not_allowlisted() {
    CommandAdmissionContext context{
        true,
        true,
        true,
        false,
        false,
        "factory_reset"
    };
    CommandAdmissionDecision decision = shouldAcceptCommand(CommandSubtype::SYSTEM, context);
    TEST_ASSERT_FALSE(decision.accepted);
    TEST_ASSERT_EQUAL_STRING("CONFIG_PENDING_BLOCKED", decision.code);
    TEST_ASSERT_EQUAL_STRING("CONFIG_PENDING_AFTER_RESET", decision.reason_code);
}

void test_system_command_allowed_in_pending_by_allowlist() {
    CommandAdmissionContext context{
        true,
        true,
        true,
        false,
        false,
        "status"
    };
    CommandAdmissionDecision decision = shouldAcceptCommand(CommandSubtype::SYSTEM, context);
    TEST_ASSERT_TRUE(decision.accepted);
    TEST_ASSERT_EQUAL_STRING("PENDING_ALLOWLIST_ACCEPTED", decision.code);
}

void test_actuator_command_rejected_in_pending_without_recovery() {
    CommandAdmissionContext context{
        true,
        true,
        true,
        false,
        false,
        nullptr
    };
    CommandAdmissionDecision decision = shouldAcceptCommand(CommandSubtype::ACTUATOR, context);
    TEST_ASSERT_FALSE(decision.accepted);
    TEST_ASSERT_EQUAL_STRING("CONFIG_PENDING_BLOCKED", decision.code);
}

void test_sensor_command_registration_pending() {
    CommandAdmissionContext context{
        false,
        false,
        false,
        false,
        false,
        nullptr
    };
    CommandAdmissionDecision decision = shouldAcceptCommand(CommandSubtype::SENSOR, context);
    TEST_ASSERT_FALSE(decision.accepted);
    TEST_ASSERT_EQUAL_STRING("REGISTRATION_PENDING", decision.code);
}

#ifdef NATIVE_TEST
int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
#else
void setup() {
    delay(2000);
#endif
    UNITY_BEGIN();
    RUN_TEST(test_runtime_readiness_ready_when_offline_rules_missing);
    RUN_TEST(test_runtime_readiness_ready_when_basis_complete);
    RUN_TEST(test_runtime_readiness_auto_exit_offline_rules_only);
    RUN_TEST(test_runtime_readiness_auto_exit_offline_rules_with_sensors);
    RUN_TEST(test_runtime_readiness_blocked_without_offline_rules_no_actuators);
    RUN_TEST(test_system_command_rejected_in_pending_when_not_allowlisted);
    RUN_TEST(test_system_command_allowed_in_pending_by_allowlist);
    RUN_TEST(test_actuator_command_rejected_in_pending_without_recovery);
    RUN_TEST(test_sensor_command_registration_pending);
    UNITY_END();
#ifdef NATIVE_TEST
    return 0;
#endif
}

#ifndef NATIVE_TEST
void loop() {}
#endif
