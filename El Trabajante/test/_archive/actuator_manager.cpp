#include <Arduino.h>
#include <unity.h>

#include "helpers/actuator_test_helpers.h"
#include "helpers/mock_mqtt_broker.h"
#include "helpers/temporary_test_actuator.h"
#include "helpers/virtual_actuator_driver.h"
#include "models/actuator_types.h"
#include "models/sensor_types.h"
#include "services/actuator/actuator_manager.h"
#include "services/actuator/safety_controller.h"
#include "services/communication/mqtt_client.h"
#include "services/sensor/sensor_manager.h"
#include "utils/topic_builder.h"

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

}  // namespace

void setUp(void) {
    ensure_actuator_stack_initialized();
    attachBroker();
}

void tearDown(void) {
    actuator_test_teardown(&broker);
    detachBroker();
}

void test_dual_mode_digital_control(void) {
    uint8_t gpio = findExistingActuator(ActuatorTypeTokens::PUMP);
    if (gpio != 255) {
        TEST_MESSAGE("Using existing actuator (Production mode)");
        if (actuatorManager.getEmergencyStopStatus(gpio)) {
            TEST_IGNORE_MESSAGE("Actuator in emergency – clear first");
            return;
        }
        ActuatorConfig cfg = actuatorManager.getActuatorConfig(gpio);
        TEST_ASSERT_EQUAL_UINT8(gpio, cfg.gpio);
        return;
    }

    gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for virtual actuator");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE_MESSAGE(temp.isValid(), "Temporary actuator creation failed");

    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    TEST_ASSERT_TRUE(actuatorManager.controlActuatorBinary(gpio, true));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:ON"));

    TEST_ASSERT_TRUE(actuatorManager.controlActuatorBinary(gpio, false));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:OFF"));
}

void test_pwm_percentage_control(void) {
    uint8_t gpio = findFreeTestGPIO("pwm");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free PWM GPIO available");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PWM);
    TEST_ASSERT_TRUE_MESSAGE(temp.isValid(), "Failed to create PWM actuator");

    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    TEST_ASSERT_TRUE(actuatorManager.controlActuator(gpio, 0.0f));
    TEST_ASSERT_EQUAL_UINT8(0, driver->getStatus().current_pwm);

    TEST_ASSERT_TRUE(actuatorManager.controlActuator(gpio, 0.5f));
    TEST_ASSERT_EQUAL_UINT8(128, driver->getStatus().current_pwm);

    TEST_ASSERT_TRUE(actuatorManager.controlActuator(gpio, 1.5f));
    TEST_ASSERT_EQUAL_UINT8(255, driver->getStatus().current_pwm);
}

void test_mqtt_command_handling(void) {
    broker.clearPublished();

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for MQTT command test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());
    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    String command_topic = String(TopicBuilder::buildActuatorCommandTopic(gpio));

    String on_payload = R"({"command":"ON"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, on_payload));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:ON"));
    TEST_ASSERT_TRUE(broker.wasPublished("/actuator/" + String(gpio) + "/response"));

    String off_payload = R"({"command":"OFF"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, off_payload));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:OFF"));

    String pwm_payload = R"({"command":"PWM","value":0.25})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, pwm_payload));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_VALUE:0.250"));

    String toggle_payload = R"({"command":"TOGGLE"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, toggle_payload));

    broker.clearPublished();
    String bad_payload = R"({"command":"UNKNOWN"})";
    TEST_ASSERT_FALSE(actuatorManager.handleActuatorCommand(command_topic, bad_payload));
    String response = broker.getLastPayload("/actuator/" + String(gpio) + "/response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":false"));
}

void test_gpio_conflict_detection(void) {
    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for conflict test");
        return;
    }

    SensorConfig sensor_cfg;
    sensor_cfg.gpio = gpio;
    sensor_cfg.sensor_type = "test_sensor";
    sensor_cfg.sensor_name = "ConflictSensor";
    sensor_cfg.subzone_id = "test_zone";
    sensor_cfg.active = true;
    TEST_ASSERT_TRUE(sensorManager.configureSensor(sensor_cfg));

    ActuatorConfig actuator_cfg;
    actuator_cfg.gpio = gpio;
    actuator_cfg.actuator_type = ActuatorTypeTokens::PUMP;
    actuator_cfg.actuator_name = "ConflictActuator";
    actuator_cfg.active = true;

    TEST_ASSERT_FALSE(actuatorManager.configureActuator(actuator_cfg));
    TEST_ASSERT_FALSE(broker.wasPublished("/actuator/" + String(gpio) + "/alert"));

    sensorManager.removeSensor(gpio);
}

void test_emergency_stop_propagation(void) {
    broker.clearPublished();

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for emergency test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());
    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    TEST_ASSERT_TRUE(actuatorManager.controlActuatorBinary(gpio, true));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:ON"));

    TEST_ASSERT_TRUE(actuatorManager.emergencyStopActuator(gpio));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("EMERGENCY_STOP"));
    TEST_ASSERT_TRUE(broker.wasPublished("/actuator/" + String(gpio) + "/alert"));

    TEST_ASSERT_FALSE(actuatorManager.controlActuatorBinary(gpio, true));
    TEST_ASSERT_TRUE(actuatorManager.clearEmergencyStopActuator(gpio));
    TEST_ASSERT_TRUE(actuatorManager.controlActuatorBinary(gpio, false));
}

void test_status_publishing_contract(void) {
    broker.clearPublished();

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for status publishing test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());
    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    TEST_ASSERT_TRUE(actuatorManager.controlActuatorBinary(gpio, true));
    driver->clearCommandLog();

    actuatorManager.publishActuatorStatus(gpio);
    String status_topic = String(TopicBuilder::buildActuatorStatusTopic(gpio));
    TEST_ASSERT_TRUE(broker.wasPublished(status_topic));

    String payload = broker.getLastPayload("/actuator/" + String(gpio) + "/status");
    TEST_ASSERT_NOT_EQUAL(-1, payload.indexOf("\"gpio\":" + String(gpio)));
    TEST_ASSERT_NOT_EQUAL(-1, payload.indexOf("\"type\":\"pump\""));
    TEST_ASSERT_NOT_EQUAL(-1, payload.indexOf("\"state\":true"));
    TEST_ASSERT_NOT_EQUAL(-1, payload.indexOf("\"pwm\":0"));
    TEST_ASSERT_NOT_EQUAL(-1, payload.indexOf("\"emergency\""));
}

void setup() {
    delay(2000);
    UNITY_BEGIN();
    RUN_TEST(test_dual_mode_digital_control);
    RUN_TEST(test_pwm_percentage_control);
    RUN_TEST(test_mqtt_command_handling);
    RUN_TEST(test_gpio_conflict_detection);
    RUN_TEST(test_emergency_stop_propagation);
    RUN_TEST(test_status_publishing_contract);
    UNITY_END();
}

void loop() {}

