#include <unity.h>
#include "../src/models/actuator_types.h"

void test_validate_actuator_value_binary() {
  TEST_ASSERT_TRUE(validateActuatorValue(ActuatorTypeTokens::PUMP, 0.0f));
  TEST_ASSERT_TRUE(validateActuatorValue(ActuatorTypeTokens::PUMP, 1.0f));
  TEST_ASSERT_TRUE(validateActuatorValue(ActuatorTypeTokens::RELAY, 0.5f));
  TEST_ASSERT_FALSE(validateActuatorValue(ActuatorTypeTokens::PUMP, 1.5f));
}

void test_validate_actuator_value_pwm() {
  TEST_ASSERT_TRUE(validateActuatorValue(ActuatorTypeTokens::PWM, 0.0f));
  TEST_ASSERT_TRUE(validateActuatorValue(ActuatorTypeTokens::PWM, 0.75f));
  TEST_ASSERT_FALSE(validateActuatorValue(ActuatorTypeTokens::PWM, -0.1f));
  TEST_ASSERT_FALSE(validateActuatorValue(ActuatorTypeTokens::PWM, 1.1f));
}

void test_emergency_state_conversion() {
  TEST_ASSERT_EQUAL_STRING("normal", emergencyStateToString(EmergencyState::EMERGENCY_NORMAL));
  TEST_ASSERT_EQUAL_STRING("active", emergencyStateToString(EmergencyState::EMERGENCY_ACTIVE));
  TEST_ASSERT_EQUAL(EmergencyState::EMERGENCY_NORMAL, emergencyStateFromString("normal"));
  TEST_ASSERT_EQUAL(EmergencyState::EMERGENCY_ACTIVE, emergencyStateFromString("active"));
  TEST_ASSERT_EQUAL(EmergencyState::EMERGENCY_CLEARING, emergencyStateFromString("clearing"));
  TEST_ASSERT_EQUAL(EmergencyState::EMERGENCY_RESUMING, emergencyStateFromString("resuming"));
}

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_validate_actuator_value_binary);
  RUN_TEST(test_validate_actuator_value_pwm);
  RUN_TEST(test_emergency_state_conversion);
  UNITY_END();
}

void loop() {}
