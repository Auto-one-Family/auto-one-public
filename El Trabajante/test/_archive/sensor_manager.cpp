#include <unity.h>
#include <Arduino.h>
#include <vector>
#include <memory>

// Access private members for testing
#define private public
#define protected public
#include "services/sensor/sensor_manager.h"
#undef private
#undef protected

#include "models/sensor_types.h"
#include "services/config/config_manager.h"
#include "services/config/storage_manager.h"
#include "drivers/gpio_manager.h"
#include "utils/logger.h"
#include "utils/topic_builder.h"

// ============================================
// BOARD-SPECIFIC GPIO CANDIDATES
// ============================================
#ifdef XIAO_ESP32C3
static const uint8_t ANALOG_CANDIDATES[] = {2, 3, 4};
static const uint8_t ANALOG_CANDIDATE_COUNT = 3;
static const uint8_t DIGITAL_CANDIDATES[] = {6, 7, 8, 9, 10, 20, 21};
static const uint8_t DIGITAL_CANDIDATE_COUNT = 7;
#else
static const uint8_t ANALOG_CANDIDATES[] = {32, 33, 34, 35, 36, 39};
static const uint8_t ANALOG_CANDIDATE_COUNT = 6;
static const uint8_t DIGITAL_CANDIDATES[] = {14, 15, 18, 19, 23, 25, 26, 27};
static const uint8_t DIGITAL_CANDIDATE_COUNT = 8;
#endif

static bool infrastructure_initialized = false;

// ============================================
// RAII HELPER: TemporaryTestSensor
// ============================================
/**
 * RAII-Pattern für temporäre Test-Sensoren
 * Sensor wird automatisch entfernt wenn Scope endet
 */
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
            sensorManager.removeSensor(gpio_);  // Auto-Cleanup!
        }
    }
    
    bool isValid() const { return created_; }
    uint8_t getGPIO() const { return gpio_; }
};

// ============================================
// HELPER FUNCTIONS
// ============================================

// Forward declarations
static std::vector<uint8_t> getAvailableAnalogGPIOs();
static std::vector<uint8_t> getAvailableDigitalGPIOs();

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

/**
 * Nutzt vorhandene Production-Sensoren für Tests
 * 
 * @param sensor_type - "analog" oder "digital"
 * @return GPIO des ersten gefundenen Sensors oder 255
 */
static uint8_t findExistingSensor(const char* sensor_type) {
    uint8_t sensor_count = sensorManager.getActiveSensorCount();

    // Access private sensors_ array (via #define private public)
    for (uint8_t i = 0; i < sensor_count && i < MAX_SENSORS; i++) {
        const SensorConfig& cfg = sensorManager.sensors_[i];
        
        if (!cfg.active || cfg.gpio == 255) {
            continue;
        }
        
        // Analog-Sensoren: ADC-fähiger GPIO
        if (strcmp(sensor_type, "analog") == 0) {
            #ifdef XIAO_ESP32C3
            if (cfg.gpio >= 2 && cfg.gpio <= 4) {  // XIAO ADC
                return cfg.gpio;
            }
            #else
            if (cfg.gpio >= 32 && cfg.gpio <= 39) {  // ESP32 Dev ADC1
                return cfg.gpio;
            }
            #endif
        }
        
        // Digital-Sensoren: Jeder GPIO
        if (strcmp(sensor_type, "digital") == 0) {
            return cfg.gpio;
        }
    }
    
    return 255;  // Kein passender Sensor gefunden
}

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
 * Prüft ob System neu ist (keine konfigurierten Sensoren)
 */
static bool isNewSystem() {
    return sensorManager.getActiveSensorCount() == 0;
}

/**
 * Prüft ob Production-System (vorhandene Sensoren)
 */
static bool isProductionSystem() {
    return sensorManager.getActiveSensorCount() > 0;
}

/**
 * Gibt alle aktiven Sensoren für Debugging aus
 */
static void printActiveSensors() {
    uint8_t count = sensorManager.getActiveSensorCount();
    Serial.printf("\n[Test Info] Active sensors: %d\n", count);
    
    if (count == 0) {
        Serial.println("  - No sensors configured (New System mode)");
        return;
    }
    
    for (uint8_t i = 0; i < count && i < MAX_SENSORS; i++) {
        const SensorConfig& cfg = sensorManager.sensors_[i];
        if (cfg.active && cfg.gpio != 255) {
            Serial.printf("  - GPIO %d: %s (%s)\n",
                          cfg.gpio,
                          cfg.sensor_name.c_str(),
                          cfg.sensor_type.c_str());
        }
    }
}

// ============================================
// INFRASTRUCTURE INITIALIZATION
// ============================================
static void initialize_sensor_stack() {
    if (infrastructure_initialized) {
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

    TEST_ASSERT_TRUE_MESSAGE(sensorManager.begin(), "SensorManager failed to initialize");
    infrastructure_initialized = true;
}

// ============================================
// TEST SETUP & TEARDOWN
// ============================================
void setUp(void) {
    initialize_sensor_stack();
    printActiveSensors();  // Debug-Info
}

void tearDown(void) {
    // Nichts zu tun - TemporaryTestSensor räumt automatisch auf
}

// ============================================
// TEST 1: Analog Sensor Raw Reading (Production-Safe)
// ============================================
/**
 * Helper-Funktion für Analog-Sensor-Test (für beide Modi)
 */
static void test_analog_sensor_on_gpio(uint8_t gpio) {
    SensorReading reading;
    bool success = sensorManager.performMeasurement(gpio, reading);
    
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(
        gpio, 
        reading.gpio,
        "GPIO mismatch in reading"
    );
    TEST_ASSERT_TRUE_MESSAGE(
        reading.raw_value <= 4095,
        "ADC value exceeds 12-bit maximum"
    );
    TEST_ASSERT_TRUE_MESSAGE(
        reading.raw_value >= 0,
        "ADC value is negative (impossible)"
    );
    
    // OPTIONAL: Processed-Value-Check (nur wenn Pi verfügbar)
    if (success && reading.valid) {
        TEST_ASSERT_TRUE_MESSAGE(
            reading.unit.length() > 0,
            "Processed data should include unit"
        );
        TEST_ASSERT_TRUE_MESSAGE(
            reading.quality.length() > 0,
            "Processed data should include quality"
        );
    } else if (!success) {
        TEST_IGNORE_MESSAGE(
            "Pi server/WiFi unavailable. Skipping processed-value assertions."
        );
    }
}

/**
 * TEST 1: Analog Sensor Raw Reading (ADC 0-4095)
 * 
 * MODE 1 (New System): Nutzt temporären Test-Sensor auf freiem GPIO
 * MODE 2 (Production): Nutzt vorhandenen Analog-Sensor
 * 
 * ERFOLG: Raw-Wert im gültigen Bereich (0-4095)
 */
void test_analog_sensor_raw_reading(void) {
    // MODE 2: Suche existierenden Analog-Sensor
    uint8_t gpio = findExistingSensor("analog");
    bool using_existing = (gpio != 255);
    
    // MODE 1: Kein existierender Sensor → Erstelle temporären
    if (!using_existing) {
        gpio = findFreeTestGPIO("analog");
        if (gpio == 255) {
            TEST_IGNORE_MESSAGE(
                "No free analog GPIO and no existing analog sensors. "
                "Connect analog sensor (pH, EC, etc.) to test."
            );
            return;
        }
        
        TemporaryTestSensor temp_sensor(gpio, "AnalogTest");
        if (!temp_sensor.isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test sensor");
            return;
        }
        
        TEST_MESSAGE("Using temporary analog sensor (New System mode)");
        
        // Test mit temporärem Sensor
        test_analog_sensor_on_gpio(gpio);
        
        // temp_sensor wird automatisch entfernt (Destructor)
        return;
    }
    
    // MODE 2: Test mit existierendem Production-Sensor
    char msg[100];
    snprintf(msg, sizeof(msg), 
             "Using existing analog sensor on GPIO %d (Production mode)", gpio);
    TEST_MESSAGE(msg);
    
    test_analog_sensor_on_gpio(gpio);
}

// ============================================
// TEST 2: Digital Sensor Plausibility (Automatisiert)
// ============================================
/**
 * Helper-Funktion für Digital-Sensor-Test (für beide Modi)
 */
static void test_digital_sensor_on_gpio(uint8_t gpio) {
    // Lese 5 Samples (Stabilität prüfen)
    uint32_t samples[5];
    for (int i = 0; i < 5; i++) {
        samples[i] = sensorManager.readRawDigital(gpio);
        delay(10);
    }
    
    // Validierung: Alle Werte müssen 0 oder 1 sein
    for (int i = 0; i < 5; i++) {
        TEST_ASSERT_TRUE_MESSAGE(
            samples[i] == 0 || samples[i] == 1,
            "Digital GPIO returned invalid value (not 0 or 1)"
        );
    }
    
    // OPTIONAL: Stabilität prüfen (alle Samples gleich?)
    bool stable = true;
    for (int i = 1; i < 5; i++) {
        if (samples[i] != samples[0]) {
            stable = false;
            break;
        }
    }
    
    if (stable) {
        char msg[50];
        snprintf(msg, sizeof(msg), 
                 "Digital GPIO stable at %d", (int)samples[0]);
        TEST_MESSAGE(msg);
    } else {
        TEST_MESSAGE("Digital GPIO unstable (toggling) - may be active sensor");
    }
}

/**
 * TEST 2: Digital Sensor Plausibility Check
 * 
 * WICHTIG: Testet NICHT spezifischen Zustand (HIGH/LOW),
 *          sondern nur ob Lesung funktioniert und plausibel ist!
 * 
 * MODE 1 (New System): Nutzt temporären Test-Sensor
 * MODE 2 (Production): Nutzt vorhandenen Digital-Sensor
 * 
 * ERFOLG: GPIO liefert 0 oder 1 (keine Fehler)
 */
void test_digital_sensor_plausibility(void) {
    // MODE 2: Suche existierenden Digital-Sensor
    uint8_t gpio = findExistingSensor("digital");
    bool using_existing = (gpio != 255);
    
    // MODE 1: Kein existierender Sensor → Erstelle temporären
    if (!using_existing) {
        gpio = findFreeTestGPIO("digital");
        if (gpio == 255) {
            TEST_IGNORE_MESSAGE(
                "No free digital GPIO and no existing digital sensors. "
                "System has no digital I/O available for testing."
            );
            return;
        }
        
        TemporaryTestSensor temp_sensor(gpio, "DigitalTest");
        if (!temp_sensor.isValid()) {
            TEST_FAIL_MESSAGE("Failed to create temporary test sensor");
            return;
        }
        
        TEST_MESSAGE("Using temporary digital sensor (New System mode)");
        
        test_digital_sensor_on_gpio(gpio);
        return;
    }
    
    // MODE 2: Test mit existierendem Production-Sensor
    char msg[100];
    snprintf(msg, sizeof(msg), 
             "Using existing digital sensor on GPIO %d (Production mode)", gpio);
    TEST_MESSAGE(msg);
    
    test_digital_sensor_on_gpio(gpio);
}

// ============================================
// TEST 3: MQTT Topic Generation (Hardware-unabhängig)
// ============================================
/**
 * TEST 3: MQTT Topic Generation
 * 
 * Testet korrekte Topic-Generierung gemäß Mqtt_Protocoll.md
 * 
 * ERFOLG: Topic entspricht Pattern: kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data
 */
void test_mqtt_topic_generation(void) {
    // Verwende beliebigen GPIO (4 ist Standard-Test-GPIO)
    const uint8_t test_gpio = 4;
    
    // Hole ESP/Kaiser IDs aus Config
    String esp_id = configManager.getESPId();
    String kaiser_id = configManager.getKaiserId();

    // Fallback für uninitialisierte Config
    if (esp_id.isEmpty()) {
        esp_id = "ESP_TEST_NODE";
        TopicBuilder::setEspId(esp_id.c_str());
    }
    if (kaiser_id.isEmpty()) {
        kaiser_id = "god";
        TopicBuilder::setKaiserId(kaiser_id.c_str());
    }
    
    // Generiere Topic
    const char* topic = TopicBuilder::buildSensorDataTopic(test_gpio);
    
    // Erwartetes Pattern
    String expected = "kaiser/" + kaiser_id + 
                      "/esp/" + esp_id + 
                      "/sensor/" + String(test_gpio) + "/data";
    
    // Validierung
    TEST_ASSERT_EQUAL_STRING_MESSAGE(
        expected.c_str(), 
        topic,
        "MQTT topic does not match protocol specification"
    );
    
    // Zusätzliche Validierung: Topic-Länge plausibel?
    size_t topic_len = strlen(topic);
    TEST_ASSERT_TRUE_MESSAGE(
        topic_len > 20 && topic_len < 256,
        "MQTT topic length implausible"
    );
}

// ============================================
// TEST 4: Measurement Interval Enforcement (Production-Safe)
// ============================================
/**
 * TEST 4: Measurement Interval Enforcement
 * 
 * Testet ob 30s Standard-Intervall eingehalten wird
 * (Test-Modus: 1s für schnellere Ausführung)
 * 
 * WARNUNG: Modifiziert temporär measurement_interval_!
 *          Wird nach Test zurückgesetzt!
 * 
 * ERFOLG: Intervall-Gating funktioniert korrekt
 */
void test_sensor_measurement_interval(void) {
    // Backup original interval
    unsigned long original_interval = sensorManager.measurement_interval_;
    
    // Test-Modus: 1s Intervall (statt 30s)
    sensorManager.measurement_interval_ = 1000;
    sensorManager.last_measurement_time_ = 0;  // Reset timestamp
    
    // ERSTE Messung (sollte durchgeführt werden)
    sensorManager.performAllMeasurements();
    unsigned long first_timestamp = sensorManager.last_measurement_time_;
    
    TEST_ASSERT_TRUE_MESSAGE(
        first_timestamp > 0,
        "First measurement timestamp not recorded"
    );
    
    // ZWEITE Messung (zu früh → sollte blockiert werden)
    delay(500);  // Nur 0.5s warten (< 1s Intervall)
    sensorManager.performAllMeasurements();
    unsigned long second_timestamp = sensorManager.last_measurement_time_;
    
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(
        first_timestamp,
        second_timestamp,
        "Measurement interval gating failed (premature measurement)"
    );
    
    // DRITTE Messung (nach Intervall → sollte durchgeführt werden)
    delay(600);  // Insgesamt 1.1s (> 1s Intervall)
    sensorManager.performAllMeasurements();
    unsigned long third_timestamp = sensorManager.last_measurement_time_;
    
    TEST_ASSERT_TRUE_MESSAGE(
        third_timestamp > first_timestamp,
        "Measurement did not trigger after interval elapsed"
    );
    
    // Restore original interval (KRITISCH!)
    sensorManager.measurement_interval_ = original_interval;
    
    TEST_MESSAGE("Measurement interval enforcement validated");
}

// ============================================
// UNITY RUNNER
// ============================================
void setup() {
    delay(2000);
    UNITY_BEGIN();
    
    RUN_TEST(test_analog_sensor_raw_reading);
    RUN_TEST(test_digital_sensor_plausibility);
    RUN_TEST(test_mqtt_topic_generation);
    RUN_TEST(test_sensor_measurement_interval);
    
    UNITY_END();
}

void loop() {}
