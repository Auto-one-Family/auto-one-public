#include <Arduino.h>
#include <unity.h>

#include <vector>

#include "helpers/actuator_test_helpers.h"
#include "helpers/mock_mqtt_broker.h"
#include "helpers/temporary_test_actuator.h"
#include "helpers/virtual_actuator_driver.h"
#include "models/actuator_types.h"
#include "services/actuator/actuator_manager.h"
#include "services/actuator/safety_controller.h"
#include "services/communication/mqtt_client.h"

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

std::vector<std::unique_ptr<TemporaryTestActuator>> createVirtualActuators(const std::vector<const char*>& types,
                                                                           std::vector<VirtualActuatorDriver*>& drivers) {
    std::vector<std::unique_ptr<TemporaryTestActuator>> actuators;
    drivers.clear();
    for (const auto* type : types) {
        uint8_t gpio = findFreeTestGPIO(type);
        if (gpio == 255) {
            continue;
        }
        std::unique_ptr<TemporaryTestActuator> temp(new TemporaryTestActuator(gpio, type));
        if (!temp->isValid()) {
            continue;
        }
        VirtualActuatorDriver* driver = temp->getVirtualDriver();
        if (!driver) {
            continue;
        }
        actuators.push_back(std::move(temp));
        drivers.push_back(driver);
    }
    return actuators;
}

}  // namespace

void setUp(void) {
    ensure_actuator_stack_initialized();
    attachBroker();
    safetyController.begin();
    RecoveryConfig config;
    safetyController.setRecoveryConfig(config);
}

void tearDown(void) {
    actuator_test_teardown(&broker);
    detachBroker();
}

void test_emergency_stop_all(void) {
    broker.clearPublished();

    std::vector<VirtualActuatorDriver*> drivers;
    auto actuators = createVirtualActuators({ActuatorTypeTokens::PUMP, ActuatorTypeTokens::PUMP}, drivers);
    if (actuators.empty()) {
        TEST_IGNORE_MESSAGE("No actuators available for emergency test");
        return;
    }

    TEST_ASSERT_TRUE(safetyController.emergencyStopAll("test_all"));
    TEST_ASSERT_EQUAL_UINT8(static_cast<uint8_t>(EmergencyState::EMERGENCY_ACTIVE),
                            static_cast<uint8_t>(safetyController.getEmergencyState()));

    for (auto* driver : drivers) {
        TEST_ASSERT_TRUE(driver->wasCommandCalled("EMERGENCY_STOP"));
    }
    TEST_ASSERT_TRUE(broker.wasPublished("/alert"));
}

void test_emergency_stop_single(void) {
    std::vector<VirtualActuatorDriver*> drivers;
    auto actuators = createVirtualActuators({ActuatorTypeTokens::PUMP, ActuatorTypeTokens::VALVE}, drivers);
    if (actuators.size() < 2) {
        TEST_IGNORE_MESSAGE("Need two actuators for single emergency test");
        return;
    }

    uint8_t target_gpio = actuators.front()->getGPIO();
    TEST_ASSERT_TRUE(safetyController.emergencyStopActuator(target_gpio, "single"));

    TEST_ASSERT_TRUE(drivers.front()->wasCommandCalled("EMERGENCY_STOP"));
    TEST_ASSERT_FALSE(drivers.back()->wasCommandCalled("EMERGENCY_STOP"));
    TEST_ASSERT_TRUE(safetyController.isEmergencyActive());
    TEST_ASSERT_TRUE(safetyController.isEmergencyActive(target_gpio));
}

void test_clear_emergency_verification_failure(void) {
    broker.clearPublished();
    RecoveryConfig config;
    config.max_retry_attempts = 0;
    safetyController.setRecoveryConfig(config);

    std::vector<VirtualActuatorDriver*> drivers;
    auto actuators = createVirtualActuators({ActuatorTypeTokens::PUMP}, drivers);
    if (actuators.empty()) {
        TEST_IGNORE_MESSAGE("No actuator available for verification failure test");
        return;
    }

    TEST_ASSERT_TRUE(safetyController.emergencyStopAll("verify"));
    TEST_ASSERT_FALSE(safetyController.clearEmergencyStop());
    TEST_ASSERT_TRUE(broker.wasPublished("/alert"));

    String alert_payload = broker.getLastPayload("/alert");
    TEST_ASSERT_NOT_EQUAL(-1, alert_payload.indexOf("verification_failed"));
}

void test_resume_operation_sequencing(void) {
    broker.clearPublished();

    RecoveryConfig config;
    config.max_retry_attempts = 3;
    config.inter_actuator_delay_ms = 50;
    safetyController.setRecoveryConfig(config);

    std::vector<VirtualActuatorDriver*> drivers;
    auto actuators = createVirtualActuators({ActuatorTypeTokens::PUMP}, drivers);
    if (actuators.empty()) {
        TEST_IGNORE_MESSAGE("No actuator for resume test");
        return;
    }

    TEST_ASSERT_TRUE(safetyController.emergencyStopAll("resume"));
    TEST_ASSERT_TRUE(safetyController.clearEmergencyStop());

    unsigned long start = millis();
    TEST_ASSERT_TRUE(safetyController.resumeOperation());
    unsigned long duration = millis() - start;
    TEST_ASSERT_TRUE(duration >= config.inter_actuator_delay_ms);
    TEST_ASSERT_FALSE(safetyController.isEmergencyActive());
}

void setup() {
    delay(2000);
    UNITY_BEGIN();
    RUN_TEST(test_emergency_stop_all);
    RUN_TEST(test_emergency_stop_single);
    RUN_TEST(test_clear_emergency_verification_failure);
    RUN_TEST(test_resume_operation_sequencing);
    UNITY_END();
}

void loop() {}

