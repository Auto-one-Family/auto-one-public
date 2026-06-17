#include <Arduino.h>
#include <unity.h>

#include "helpers/actuator_test_helpers.h"
#include "helpers/mock_mqtt_broker.h"
#include "models/actuator_types.h"
#include "models/sensor_types.h"
#include "services/actuator/actuator_manager.h"
#include "services/communication/mqtt_client.h"
#include "services/sensor/sensor_manager.h"

namespace {

MockMQTTBroker broker;

void attachBroker() {
    mqttClient.setTestPublishHook([](const String& topic, const String& payload) {
        broker.publish(topic, payload);
    });
}

void detachBroker() {
    mqttClient.clearTestPublishHook();
}

String buildConfigPayload(uint8_t gpio, const char* type, const char* name, bool active = true) {
    String payload = "{\"actuators\":[{";
    payload += "\"gpio\":" + String(gpio) + ",";
    payload += "\"type\":\"" + String(type) + "\",";
    payload += "\"name\":\"" + String(name) + "\",";
    payload += "\"active\":" + String(active ? "true" : "false");
    payload += "}]}";
    return payload;
}

}  // namespace

void setUp(void) {
    ensure_actuator_stack_initialized();
    attachBroker();
}

void tearDown(void) {
    actuator_test_teardown(&broker);
    detachBroker();
}

void test_user_adds_new_actuator_via_mqtt(void) {
    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for config test");
        return;
    }

    TEST_ASSERT_FALSE(actuatorManager.hasActuatorOnGPIO(gpio));

    String payload = buildConfigPayload(gpio, ActuatorTypeTokens::PUMP, "Test Pump");
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorConfig(payload));
    TEST_ASSERT_TRUE(actuatorManager.hasActuatorOnGPIO(gpio));
    TEST_ASSERT_TRUE(broker.wasPublished("/config_response"));

    String response = broker.getLastPayload("/config_response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":true"));
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"message\""));

    actuatorManager.removeActuator(gpio);
}

void test_gpio_conflict_rejection_via_config(void) {
    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for conflict config test");
        return;
    }

    SensorConfig sensor_cfg;
    sensor_cfg.gpio = gpio;
    sensor_cfg.sensor_type = "test_sensor";
    sensor_cfg.sensor_name = "ConfigConflictSensor";
    sensor_cfg.subzone_id = "test_zone";
    sensor_cfg.active = true;
    TEST_ASSERT_TRUE(sensorManager.configureSensor(sensor_cfg));

    String payload = buildConfigPayload(gpio, ActuatorTypeTokens::PUMP, "Conflict Pump");
    TEST_ASSERT_FALSE(actuatorManager.handleActuatorConfig(payload));
    TEST_ASSERT_FALSE(actuatorManager.hasActuatorOnGPIO(gpio));

    String response = broker.getLastPayload("/config_response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":false"));

    sensorManager.removeSensor(gpio);
}

void test_payload_validation_and_sanitization(void) {
    broker.clearPublished();

    String invalid_payload = "{\"actuator\":{}}";
    TEST_ASSERT_FALSE(actuatorManager.handleActuatorConfig(invalid_payload));
    TEST_ASSERT_TRUE(broker.wasPublished("/config_response"));
    TEST_ASSERT_TRUE(broker.wasPublished("/alert"));

    String response = broker.getLastPayload("/config_response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":false"));
}

void setup() {
    delay(2000);
    UNITY_BEGIN();
    RUN_TEST(test_user_adds_new_actuator_via_mqtt);
    RUN_TEST(test_gpio_conflict_rejection_via_config);
    RUN_TEST(test_payload_validation_and_sanitization);
    UNITY_END();
}

void loop() {}

