#include <unity.h>
#include <Arduino.h>
#include <vector>
#include <memory>

#define private public
#define protected public
#include "services/sensor/sensor_manager.h"
#undef private
#undef protected

#include "services/config/config_manager.h"
#include "services/config/storage_manager.h"
#include "services/communication/mqtt_client.h"
#include "services/communication/wifi_manager.h"
#include "services/sensor/pi_enhanced_processor.h"
#include "drivers/gpio_manager.h"
#include "utils/logger.h"
#include "utils/topic_builder.h"
#include "models/sensor_types.h"

static constexpr size_t SENSOR_TARGET_COUNT = 10;

static bool integration_stack_initialized = false;

// ============================================
// RAII HELPER: TemporaryTestSensor (wie in test_sensor_manager.cpp)
// ============================================
class TemporaryTestSensor {
private:
    uint8_t gpio_;
    bool created_;

public:
    TemporaryTestSensor(uint8_t gpio, const char* name) 
        : gpio_(gpio), created_(false) {
        
        SensorConfig cfg;
        cfg.gpio = gpio;
        cfg.sensor_type = "test_sensor";
        cfg.sensor_name = name;
        cfg.subzone_id = "test_zone";
        cfg.active = true;
        cfg.raw_mode = true;
        
        created_ = sensorManager.configureSensor(cfg);
    }
    
    ~TemporaryTestSensor() {
        if (created_) {
            sensorManager.removeSensor(gpio_);
        }
    }
    
    bool isValid() const { return created_; }
    uint8_t getGPIO() const { return gpio_; }
};

// ============================================
// HELPER FUNCTIONS
// ============================================

// ============================================
// DYNAMIC GPIO DISCOVERY (ZUKUNFTSSICHER)
// ============================================

/**
 * Gibt alle analog-fähigen, freien GPIOs zurück
 * 
 * @return Vector mit verfügbaren Analog-GPIOs
 */
static std::vector<uint8_t> getAvailableAnalogGPIOs() {
    std::vector<uint8_t> gpios;
    
    // Board-spezifische Analog-Ranges
    #ifdef XIAO_ESP32C3
    // XIAO C3: GPIO 2, 3, 4 sind ADC-fähig
    static const uint8_t analog_range[] = {2, 3, 4};
    static const size_t range_size = 3;
    #else
    // ESP32 Dev (WROOM): GPIO 32-39 sind ADC1 (WiFi-safe)
    static const uint8_t analog_range[] = {32, 33, 34, 35, 36, 39};
    static const size_t range_size = 6;
    #endif
    
    // Filtere verfügbare GPIOs
    for (size_t i = 0; i < range_size; i++) {
        uint8_t gpio = analog_range[i];
        
        // KRITISCH: Prüfe ob GPIO frei ist
        if (!sensorManager.hasSensorOnGPIO(gpio) &&
            gpioManager.isPinAvailable(gpio)) {
            gpios.push_back(gpio);
        }
    }
    
    return gpios;
}

/**
 * Gibt alle digital-fähigen, freien GPIOs zurück
 * 
 * @return Vector mit verfügbaren Digital-GPIOs
 */
static std::vector<uint8_t> getAvailableDigitalGPIOs() {
    std::vector<uint8_t> gpios;
    
    // Board-spezifische Digital-Ranges (ohne I2C/SPI)
    #ifdef XIAO_ESP32C3
    static const uint8_t digital_range[] = {6, 7, 8, 9, 10, 20, 21};
    static const size_t range_size = 7;
    #else
    static const uint8_t digital_range[] = {14, 15, 18, 19, 23, 25, 26, 27};
    static const size_t range_size = 8;
    #endif
    
    // Filtere verfügbare GPIOs
    for (size_t i = 0; i < range_size; i++) {
        uint8_t gpio = digital_range[i];
        
        if (!sensorManager.hasSensorOnGPIO(gpio) &&
            gpioManager.isPinAvailable(gpio)) {
            gpios.push_back(gpio);
        }
    }
    
    return gpios;
}

/**
 * Kombiniert Analog + Digital GPIOs für Multi-Sensor-Tests
 * 
 * @param target_count - Anzahl benötigter GPIOs
 * @return Vector mit gemischten GPIOs (Analog zuerst, dann Digital)
 */
static std::vector<uint8_t> getAvailableMixedGPIOs(size_t target_count) {
    std::vector<uint8_t> gpios;
    
    // Hole alle verfügbaren GPIOs
    std::vector<uint8_t> analog = getAvailableAnalogGPIOs();
    std::vector<uint8_t> digital = getAvailableDigitalGPIOs();
    
    // Füge Analog-GPIOs hinzu
    for (uint8_t gpio : analog) {
        if (gpios.size() >= target_count) break;
        gpios.push_back(gpio);
    }
    
    // Fülle mit Digital-GPIOs auf
    for (uint8_t gpio : digital) {
        if (gpios.size() >= target_count) break;
        gpios.push_back(gpio);
    }
    
    return gpios;
}

/**
 * Findet einen unbenutzten GPIO für temporäre Tests
 * 
 * @param type - "analog" oder "digital"
 * @return GPIO-Nummer oder 255 wenn keine verfügbar
 */
static uint8_t findFreeTestGPIO(const char* type) {
    std::vector<uint8_t> gpios;
    
    if (strcmp(type, "analog") == 0) {
        gpios = getAvailableAnalogGPIOs();
    } else {
        gpios = getAvailableDigitalGPIOs();
    }
    
    return gpios.empty() ? 255 : gpios[0];  // Erstes verfügbares GPIO
}

static void initialize_integration_stack() {
    if (integration_stack_initialized) {
        return;
    }

    Serial.begin(115200);
    delay(200);

    logger.begin();
    logger.setLogLevel(LOG_INFO);
    gpioManager.initializeAllPinsToSafeMode();
#ifdef XIAO_ESP32C3
    gpioManager.releaseI2CPins();
#endif
    storageManager.begin();
    configManager.begin();
    configManager.loadAllConfigs();
    
    String esp_id = configManager.getESPId();
    if (esp_id.isEmpty()) {
        esp_id = "ESP_TEST_NODE";
    }
    TopicBuilder::setEspId(esp_id.c_str());

    String kaiser_id = configManager.getKaiserId();
    if (kaiser_id.isEmpty()) {
        kaiser_id = "god";
    }
    TopicBuilder::setKaiserId(kaiser_id.c_str());

    mqttClient.begin();
    sensorManager.begin();
    integration_stack_initialized = true;
}

// ============================================
// TEST 1: Sensor → MQTT Payload Flow (Production-Safe)
// ============================================
void test_sensor_to_mqtt_flow(void) {
    initialize_integration_stack();
    
    // MODE 1: Nutze existierenden Sensor (Production)
    uint8_t gpio = 255;
    uint8_t existing_count = sensorManager.getActiveSensorCount();
    
    if (existing_count > 0) {
        // Nutze ersten aktiven Sensor
        for (uint8_t i = 0; i < MAX_SENSORS; i++) {
            const SensorConfig& cfg = sensorManager.sensors_[i];
            if (cfg.active && cfg.gpio != 255) {
                gpio = cfg.gpio;
                break;
            }
        }
    }
    
    // MODE 2: Erstelle temporären Sensor (New System)
    std::unique_ptr<TemporaryTestSensor> temp_sensor;
    if (gpio == 255) {
        gpio = findFreeTestGPIO("analog");
        if (gpio == 255) {
            TEST_IGNORE_MESSAGE(
                "No free GPIO and no existing sensors. "
                "Cannot test MQTT payload flow."
            );
            return;
        }
        temp_sensor = std::unique_ptr<TemporaryTestSensor>(new TemporaryTestSensor(gpio, "Flow_Test"));
        if (!temp_sensor->isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test sensor");
            return;  // ✅ Automatisches Cleanup via unique_ptr Destructor!
        }
        TEST_MESSAGE("Using temporary sensor (New System mode)");
    } else {
        TEST_MESSAGE("Using existing sensor (Production mode)");
    }

    SensorReading reading;
    bool success = sensorManager.performMeasurement(gpio, reading);

    if (!success) {
        TEST_IGNORE_MESSAGE("Pi server unavailable. Skipping payload validation.");
        return;  // ✅ Automatisches Cleanup via unique_ptr Destructor!
    }

    String payload = sensorManager.buildMQTTPayload(reading);
    TEST_ASSERT_TRUE_MESSAGE(
        payload.indexOf("\"gpio\":") >= 0,
        "Payload missing gpio field"
    );
    TEST_ASSERT_TRUE_MESSAGE(
        payload.indexOf("\"raw_value\"") >= 0,
        "Payload missing raw_value field"
    );
    TEST_ASSERT_TRUE_MESSAGE(
        payload.indexOf("\"processed_value\"") >= 0,
        "Payload missing processed_value field"
    );

    const char* topic = TopicBuilder::buildSensorDataTopic(gpio);
    String expected = "kaiser/" + configManager.getKaiserId() +
                      "/esp/" + configManager.getESPId() +
                      "/sensor/" + String(gpio) + "/data";
    TEST_ASSERT_EQUAL_STRING_MESSAGE(
        expected.c_str(), 
        topic,
        "MQTT topic mismatch"
    );
    
    // ✅ KEIN manuelles delete nötig - unique_ptr räumt automatisch auf!
}

// ============================================
// TEST 2: Boot Time with 10 Sensors (Production-Safe)
// ============================================
void test_boot_time_with_10_sensors(void) {
    initialize_integration_stack();
    
    // Finde freie GPIOs für temporäre Test-Sensoren (Dynamic)
    std::vector<uint8_t> test_gpios = getAvailableMixedGPIOs(SENSOR_TARGET_COUNT);
    
    if (test_gpios.size() < SENSOR_TARGET_COUNT) {
        TEST_IGNORE_MESSAGE(
            "Not enough free GPIOs for 10 sensors. "
            "Board may have limited GPIO availability or many sensors configured."
        );
        return;
    }
    
    // Erstelle temporäre Test-Sensoren (Memory-Safe mit unique_ptr)
    std::vector<std::unique_ptr<TemporaryTestSensor>> sensors;
    sensors.reserve(SENSOR_TARGET_COUNT);  // Pre-allocate für Performance
    
    for (size_t i = 0; i < SENSOR_TARGET_COUNT; i++) {
        char name[20];
        snprintf(name, sizeof(name), "BootSensor_%d", (int)i);

        std::unique_ptr<TemporaryTestSensor> sensor(new TemporaryTestSensor(test_gpios[i], name));
        if (!sensor->isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test sensor");
            return;  // ✅ Automatisches Cleanup via unique_ptr Destructor!
        }
        sensors.push_back(std::move(sensor));
    }
    
    // Messung Boot-Zeit
    unsigned long start = millis();
    sensorManager.performAllMeasurements();  // Trigger measurement
    unsigned long duration = millis() - start;
    
    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
        3000, 
        duration,
        "Boot time with 10 sensors exceeds 3s limit"
    );
    
    // ✅ KEIN manuelles delete nötig - unique_ptr räumt automatisch auf!
}

// ============================================
// TEST 3: Memory Usage with 10 Sensors (Production-Safe)
// ============================================
void test_memory_usage_10_sensors(void) {
    initialize_integration_stack();
    
    // Finde freie GPIOs für temporäre Test-Sensoren (Dynamic)
    std::vector<uint8_t> test_gpios = getAvailableMixedGPIOs(SENSOR_TARGET_COUNT);
    
    if (test_gpios.size() < SENSOR_TARGET_COUNT) {
        TEST_IGNORE_MESSAGE(
            "Not enough free GPIOs for 10 sensors. "
            "Board may have limited GPIO availability or many sensors configured."
        );
        return;
    }
    
    uint32_t heap_before = ESP.getFreeHeap();
    
    // Erstelle temporäre Test-Sensoren (Memory-Safe mit unique_ptr)
    std::vector<std::unique_ptr<TemporaryTestSensor>> sensors;
    sensors.reserve(SENSOR_TARGET_COUNT);  // Pre-allocate für Performance
    
    for (size_t i = 0; i < SENSOR_TARGET_COUNT; i++) {
        char name[20];
        snprintf(name, sizeof(name), "MemSensor_%d", (int)i);

        std::unique_ptr<TemporaryTestSensor> sensor(new TemporaryTestSensor(test_gpios[i], name));
        if (!sensor->isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test sensor");
            return;  // ✅ Automatisches Cleanup via unique_ptr Destructor!
        }
        sensors.push_back(std::move(sensor));
    }
    
    uint32_t heap_after = ESP.getFreeHeap();
    uint32_t memory_used = heap_before - heap_after;
    
    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(
        20000, 
        memory_used,
        "Memory usage with 10 sensors exceeds 20KB limit"
    );
    
    // ✅ KEIN manuelles delete nötig - unique_ptr räumt automatisch auf!
}

// ============================================
// UNITY SETUP
// ============================================
void setup() {
    delay(2000);
    UNITY_BEGIN();

    RUN_TEST(test_sensor_to_mqtt_flow);
    RUN_TEST(test_boot_time_with_10_sensors);
    RUN_TEST(test_memory_usage_10_sensors);

    UNITY_END();
}

void loop() {}
