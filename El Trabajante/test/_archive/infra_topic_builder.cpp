#include <unity.h>
#include "utils/topic_builder.h"

// ============================================
// TEST: Sensor Data Topic (Pattern 1)
// ============================================
void test_topic_builder_sensor_data() {
  TopicBuilder::setEspId("esp32_001");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildSensorDataTopic(4);
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_001/sensor/4/data", topic);
}

// ============================================
// TEST: Sensor Batch Topic (Pattern 2)
// ============================================
void test_topic_builder_sensor_batch() {
  TopicBuilder::setEspId("esp32_002");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildSensorBatchTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_002/sensor/batch", topic);
}

// ============================================
// TEST: Actuator Command Topic (Pattern 3)
// ============================================
void test_topic_builder_actuator_command() {
  TopicBuilder::setEspId("esp32_003");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildActuatorCommandTopic(25);
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_003/actuator/25/command", topic);
}

// ============================================
// TEST: Actuator Status Topic (Pattern 4)
// ============================================
void test_topic_builder_actuator_status() {
  TopicBuilder::setEspId("esp32_004");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildActuatorStatusTopic(26);
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_004/actuator/26/status", topic);
}

// ============================================
// TEST: Actuator Response Topic (Phase 5)
// ============================================
void test_topic_builder_actuator_response() {
  TopicBuilder::setEspId("esp32_010");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildActuatorResponseTopic(12);
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_010/actuator/12/response", topic);
}

// ============================================
// TEST: Actuator Alert Topic (Phase 5)
// ============================================
void test_topic_builder_actuator_alert() {
  TopicBuilder::setEspId("esp32_011");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildActuatorAlertTopic(7);
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_011/actuator/7/alert", topic);
}

// ============================================
// TEST: Actuator Emergency Topic (Phase 5)
// ============================================
void test_topic_builder_actuator_emergency() {
  TopicBuilder::setEspId("esp32_012");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildActuatorEmergencyTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_012/actuator/emergency", topic);
}

// ============================================
// TEST: System Heartbeat Topic (Pattern 5)
// ============================================
void test_topic_builder_heartbeat() {
  TopicBuilder::setEspId("esp32_005");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildSystemHeartbeatTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_005/system/heartbeat", topic);
}

// ============================================
// TEST: System Command Topic (Pattern 6)
// ============================================
void test_topic_builder_system_command() {
  TopicBuilder::setEspId("esp32_006");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildSystemCommandTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_006/system/command", topic);
}

// ============================================
// TEST: Config Topic (Pattern 7)
// ============================================
void test_topic_builder_config() {
  TopicBuilder::setEspId("esp32_007");
  TopicBuilder::setKaiserId("god");
  
  const char* topic = TopicBuilder::buildConfigTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/god/esp/esp32_007/config", topic);
}

// ============================================
// TEST: Broadcast Emergency Topic (Pattern 8)
// ============================================
void test_topic_builder_broadcast_emergency() {
  const char* topic = TopicBuilder::buildBroadcastEmergencyTopic();
  TEST_ASSERT_EQUAL_STRING("kaiser/broadcast/emergency", topic);
}

// ============================================
// TEST: ESP ID and Kaiser ID Substitution
// ============================================
void test_topic_builder_id_substitution() {
  TopicBuilder::setEspId("custom_esp");
  TopicBuilder::setKaiserId("custom_kaiser");
  
  const char* topic = TopicBuilder::buildSensorDataTopic(10);
  TEST_ASSERT_EQUAL_STRING("kaiser/custom_kaiser/esp/custom_esp/sensor/10/data", topic);
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
  delay(2000);
  UNITY_BEGIN();
  
  RUN_TEST(test_topic_builder_sensor_data);
  RUN_TEST(test_topic_builder_sensor_batch);
  RUN_TEST(test_topic_builder_actuator_command);
  RUN_TEST(test_topic_builder_actuator_status);
  RUN_TEST(test_topic_builder_actuator_response);
  RUN_TEST(test_topic_builder_actuator_alert);
  RUN_TEST(test_topic_builder_actuator_emergency);
  RUN_TEST(test_topic_builder_heartbeat);
  RUN_TEST(test_topic_builder_system_command);
  RUN_TEST(test_topic_builder_config);
  RUN_TEST(test_topic_builder_broadcast_emergency);
  RUN_TEST(test_topic_builder_id_substitution);
  
  UNITY_END();
}

void loop() {}


