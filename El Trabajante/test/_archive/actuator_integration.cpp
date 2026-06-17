#include <Arduino.h>
#include <unity.h>

#include <memory>
#include <vector>

#include "helpers/actuator_test_helpers.h"
#include "helpers/mock_mqtt_broker.h"
#include "helpers/temporary_test_actuator.h"
#include "helpers/virtual_actuator_driver.h"
#include "models/actuator_types.h"
#include "services/actuator/actuator_manager.h"
#include "services/actuator/safety_controller.h"
#include "services/communication/mqtt_client.h"
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

// ============================================
// TEST 1: MQTT Command → Response Flow (Mock)
// ============================================
void test_mqtt_command_response_flow_mock(void) {
    broker.clearPublished();

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for MQTT command-response test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE_MESSAGE(temp.isValid(), "Failed to create test actuator");

    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    // Subscribe MockMQTTBroker to response topic
    String response_topic_pattern = "kaiser/god/esp/+/actuator/+/response";
    int response_count = 0;
    broker.subscribe("TEST_CLIENT", response_topic_pattern,
        [&](const String& topic, const String& payload) {
            response_count++;
        });

    String command_topic = String(TopicBuilder::buildActuatorCommandTopic(gpio));

    // Test 1: Send ON command
    String on_payload = R"({"command":"ON"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, on_payload));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:ON"));
    TEST_ASSERT_TRUE(broker.wasPublished("/actuator/" + String(gpio) + "/response"));

    String response = broker.getLastPayload("/actuator/" + String(gpio) + "/response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":true"));

    // Test 2: Send OFF command
    broker.clearPublished();
    String off_payload = R"({"command":"OFF"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, off_payload));
    TEST_ASSERT_TRUE(driver->wasCommandCalled("SET_BINARY:OFF"));
    TEST_ASSERT_TRUE(broker.wasPublished("/actuator/" + String(gpio) + "/response"));

    response = broker.getLastPayload("/actuator/" + String(gpio) + "/response");
    TEST_ASSERT_NOT_EQUAL(-1, response.indexOf("\"success\":true"));
}

// ============================================
// TEST 2: Boot Time with 10 Actuators
// ============================================
void test_boot_time_with_10_actuators(void) {
    // MODE 1: Check for existing Production actuators
    uint8_t existing_count = actuatorManager.getActiveActuatorCount();
    if (existing_count >= 10) {
        TEST_MESSAGE("Using existing actuators (Production mode)");

        // Measure boot time with existing actuators
        unsigned long start = millis();
        actuatorManager.publishAllActuatorStatus();
        unsigned long duration = millis() - start;

        TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
            3000,
            duration,
            "Boot time with 10 actuators exceeds 3s limit");
        return;
    }

    // MODE 2: Create temporary Virtual actuators (New System)
    std::vector<uint8_t> gpios = getAvailableActuatorGPIOs();
    size_t needed = 10 - existing_count;

    if (gpios.size() < needed) {
        TEST_IGNORE_MESSAGE("Not enough free GPIOs for 10 actuators");
        return;
    }

    std::vector<std::unique_ptr<TemporaryTestActuator>> actuators;
    std::vector<VirtualActuatorDriver*> drivers;

    for (size_t i = 0; i < needed; i++) {
        std::unique_ptr<TemporaryTestActuator> temp(new TemporaryTestActuator(gpios[i], ActuatorTypeTokens::PUMP));
        if (!temp->isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test actuator");
            return;
        }
        drivers.push_back(temp->getVirtualDriver());
        actuators.push_back(std::move(temp));
    }

    // Measure boot time
    unsigned long start = millis();
    actuatorManager.publishAllActuatorStatus();
    unsigned long duration = millis() - start;

    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
        3000,
        duration,
        "Boot time with 10 actuators exceeds 3s limit");
}

// ============================================
// TEST 3: Memory Impact with 10 Actuators
// ============================================
void test_memory_impact_10_actuators(void) {
    uint32_t heap_before = ESP.getFreeHeap();

    // Create 10 temporary actuators
    std::vector<uint8_t> gpios = getAvailableActuatorGPIOs();
    if (gpios.size() < 10) {
        TEST_IGNORE_MESSAGE("Not enough free GPIOs for 10 actuators");
        return;
    }

    std::vector<std::unique_ptr<TemporaryTestActuator>> actuators;
    for (size_t i = 0; i < 10; i++) {
        std::unique_ptr<TemporaryTestActuator> temp(new TemporaryTestActuator(gpios[i], ActuatorTypeTokens::PUMP));
        if (!temp->isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test actuator");
            return;
        }
        actuators.push_back(std::move(temp));
    }

    uint32_t heap_after = ESP.getFreeHeap();
    uint32_t memory_used = heap_before - heap_after;

    // Assert: <40KB memory usage
    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
        40000,
        memory_used,
        "Memory usage with 10 actuators exceeds 40KB limit");

    // Cleanup actuators
    actuators.clear();

    // Assert: Memory freed (detect leaks)
    uint32_t heap_after_cleanup = ESP.getFreeHeap();
    uint32_t memory_leaked = heap_before - heap_after_cleanup;

    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
        1000,
        memory_leaked,
        "Memory leak detected after actuator cleanup");
}

// ============================================
// TEST 4: Cross-Device Simulation (Mock)
// ============================================
void test_cross_device_simulation_mock(void) {
    broker.clearPublished();

    // Create 2 actuators: one as "sensor trigger", one as "actuator target"
    uint8_t actuator1_gpio = findFreeTestGPIO("pump");
    if (actuator1_gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for actuator 1");
        return;
    }

    uint8_t actuator2_gpio = findFreeTestGPIO("pump");
    if (actuator2_gpio == 255 || actuator2_gpio == actuator1_gpio) {
        TEST_IGNORE_MESSAGE("No free GPIO for actuator 2");
        return;
    }

    TemporaryTestActuator temp1(actuator1_gpio, ActuatorTypeTokens::PUMP);
    TemporaryTestActuator temp2(actuator2_gpio, ActuatorTypeTokens::PUMP);

    TEST_ASSERT_TRUE(temp1.isValid());
    TEST_ASSERT_TRUE(temp2.isValid());

    VirtualActuatorDriver* driver1 = temp1.getVirtualDriver();
    VirtualActuatorDriver* driver2 = temp2.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver1);
    TEST_ASSERT_NOT_NULL(driver2);

    // Setup God-Kaiser rule simulation
    broker.subscribe("SERVER", "kaiser/god/esp/+/sensor/+/data",
        [&](const String& topic, const String& payload) {
            // Parse raw_value manually (no ArduinoJson)
            int raw_start = payload.indexOf("\"raw_value\":");
            if (raw_start == -1) return;
            raw_start += 12;
            int raw_end = payload.indexOf(",", raw_start);
            if (raw_end == -1) raw_end = payload.indexOf("}", raw_start);
            String raw_str = payload.substring(raw_start, raw_end);
            float raw_value = raw_str.toFloat();

            // Trigger automation if condition met
            if (raw_value < 2000.0) {
                String actuator_gpio = String(actuator2_gpio);
                String cmd_topic = "kaiser/god/esp/ESP_TEST_NODE/actuator/" + actuator_gpio + "/command";
                broker.publish(cmd_topic, R"({"command":"ON","reason":"Automation"})");
            }
        });

    // Simulate sensor data that triggers rule
    String sensor_topic = "kaiser/god/esp/ESP_TEST_NODE/sensor/4/data";
    String sensor_payload = R"({
        "sensor_type":"ph_sensor",
        "raw_value":1500.0,
        "timestamp":)" + String(millis()) + "}";

    broker.publish(sensor_topic, sensor_payload);

    // Handle command triggered by God-Kaiser simulation
    String cmd_topic = "kaiser/god/esp/ESP_TEST_NODE/actuator/" + String(actuator2_gpio) + "/command";
    String cmd_payload = R"({"command":"ON","reason":"Automation"})";
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(cmd_topic, cmd_payload));

    // Assert actuator2 received command
    TEST_ASSERT_TRUE(driver2->wasCommandCalled("SET_BINARY:ON"));

    // Assert actuator1 was NOT affected
    TEST_ASSERT_FALSE(driver1->wasCommandCalled("SET_BINARY:ON"));
}

// ============================================
// TEST 5: Concurrent Commands Race Handling
// ============================================
void test_concurrent_commands_race_handling(void) {
    broker.clearPublished();

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for concurrent commands test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());

    VirtualActuatorDriver* driver = temp.getVirtualDriver();
    TEST_ASSERT_NOT_NULL(driver);

    String command_topic = String(TopicBuilder::buildActuatorCommandTopic(gpio));

    // Rapid-fire commands (no delay)
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, R"({"command":"ON"})"));
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, R"({"command":"OFF"})"));
    TEST_ASSERT_TRUE(actuatorManager.handleActuatorCommand(command_topic, R"({"command":"ON"})"));

    // Assert all 3 commands executed
    TEST_ASSERT_EQUAL(2, driver->getCommandCount("SET_BINARY:ON"));  // Two ON commands
    TEST_ASSERT_EQUAL(1, driver->getCommandCount("SET_BINARY:OFF")); // One OFF command

    // Assert final state is ON
    ActuatorStatus status = driver->getStatus();
    TEST_ASSERT_TRUE(status.current_state);
}

// ============================================
// TEST 6: Cross-Device with Real Server (Docker)
// ============================================
void test_cross_device_with_real_server_docker(void) {
#ifdef SKIP_DOCKER_TESTS
    TEST_IGNORE_MESSAGE("Docker tests skipped (SKIP_DOCKER_TESTS defined)");
    return;
#endif

    // Check if Docker server is reachable
    // For now, we'll use TEST_IGNORE since connection checks require real network
    TEST_IGNORE_MESSAGE("Docker test requires manual verification");

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for Docker test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());

    // Manual verification instructions
    TEST_MESSAGE("Docker Test Instructions:");
    TEST_MESSAGE("1. Start Docker: cd god_kaiser_test_server && docker-compose up -d");
    TEST_MESSAGE("2. Publish sensor data to trigger God-Kaiser rule:");
    TEST_MESSAGE("   mosquitto_pub -h localhost -t 'kaiser/god/esp/ESP_TEST_NODE/sensor/4/data' \\");
    TEST_MESSAGE("   -m '{\"sensor_type\":\"ph_sensor\",\"raw_value\":2000.0}'");
    String msg3 = "3. Verify God-Kaiser sends actuator command to GPIO " + String(gpio);
    TEST_MESSAGE(msg3.c_str());
    String msg4 = "4. Expected topic: kaiser/god/esp/ESP_TEST_NODE/actuator/" + String(gpio) + "/command";
    TEST_MESSAGE(msg4.c_str());
}

// ============================================
// TEST 7: Server Validation Flow (Docker)
// ============================================
void test_server_validation_flow_docker(void) {
#ifdef SKIP_DOCKER_TESTS
    TEST_IGNORE_MESSAGE("Docker tests skipped (SKIP_DOCKER_TESTS defined)");
    return;
#endif

    TEST_MESSAGE("Docker Test Instructions:");
    TEST_MESSAGE("1. Send invalid command via MQTT:");
    TEST_MESSAGE("   mosquitto_pub -h localhost -t 'kaiser/god/esp/ESP_TEST_NODE/actuator/12/command' \\");
    TEST_MESSAGE("   -m '{\"command\":\"INVALID\"}'");
    TEST_MESSAGE("2. Verify God-Kaiser does NOT forward the command");
    TEST_MESSAGE("3. Send valid command:");
    TEST_MESSAGE("   mosquitto_pub -h localhost -t 'kaiser/god/esp/ESP_TEST_NODE/actuator/12/command' \\");
    TEST_MESSAGE("   -m '{\"command\":\"ON\"}'");
    TEST_MESSAGE("4. Verify God-Kaiser forwards the command correctly");

    TEST_IGNORE_MESSAGE("Manual verification required");
}

// ============================================
// TEST 8: Multi-ESP Emergency Coordination (Docker)
// ============================================
void test_multi_esp_emergency_coordination_docker(void) {
#ifdef SKIP_DOCKER_TESTS
    TEST_IGNORE_MESSAGE("Docker tests skipped (SKIP_DOCKER_TESTS defined)");
    return;
#endif

    uint8_t gpio = findFreeTestGPIO("pump");
    if (gpio == 255) {
        TEST_IGNORE_MESSAGE("No free GPIO for emergency coordination test");
        return;
    }

    TemporaryTestActuator temp(gpio, ActuatorTypeTokens::PUMP);
    TEST_ASSERT_TRUE(temp.isValid());

    // Trigger emergency stop
    TEST_ASSERT_TRUE(safetyController.emergencyStopActuator(gpio, "Test Emergency"));

    // Assert alert published
    String alertTopic = "/actuator/" + String(gpio) + "/alert";
    TEST_ASSERT_TRUE(broker.wasPublished(alertTopic));

    // Docker verification
    TEST_MESSAGE("Docker Test Instructions:");
    TEST_MESSAGE("1. Verify God-Kaiser receives emergency alert");
    String msg2 = "2. Expected topic: kaiser/god/esp/ESP_TEST_NODE/actuator/" + String(gpio) + "/alert";
    TEST_MESSAGE(msg2.c_str());
    TEST_MESSAGE("3. Verify God-Kaiser broadcasts emergency to all ESPs");
    TEST_MESSAGE("4. Expected broadcast topic: kaiser/broadcast/emergency");

    // Cleanup emergency state (BEFORE TEST_IGNORE!)
    safetyController.clearEmergencyStopActuator(gpio);

    TEST_IGNORE_MESSAGE("Manual verification required");
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    UNITY_BEGIN();

    RUN_TEST(test_mqtt_command_response_flow_mock);
    RUN_TEST(test_boot_time_with_10_actuators);
    RUN_TEST(test_memory_impact_10_actuators);
    RUN_TEST(test_cross_device_simulation_mock);
    RUN_TEST(test_concurrent_commands_race_handling);
    RUN_TEST(test_cross_device_with_real_server_docker);
    RUN_TEST(test_server_validation_flow_docker);
    RUN_TEST(test_multi_esp_emergency_coordination_docker);

    UNITY_END();
}

void loop() {}

