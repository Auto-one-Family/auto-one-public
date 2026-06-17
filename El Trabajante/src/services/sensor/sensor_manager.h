#ifndef SERVICES_SENSOR_SENSOR_MANAGER_H
#define SERVICES_SENSOR_SENSOR_MANAGER_H

#include <Arduino.h>
#include "../../models/sensor_types.h"

// ============================================
// Sensor Manager - Phase 4 Foundation
// ============================================
// Architecture: Server-Centric (MQTT Raw-Mode)
//
// Purpose: Raw sensor data acquisition with local preview conversion
// - Coordinate I2C and OneWire sensor readings
// - Apply local conversion formulas for human-readable MQTT payloads
// - Server is Single Source of Truth (raw_mode=true, server re-processes)

// ============================================
// SENSOR MANAGER CLASS
// ============================================
// Singleton class managing sensor operations
struct ManualMeasurementResult {
    bool measurement_ok = false;
    bool publish_ok = false;
    bool timeout_reached = false;
    String reason_code = "UNKNOWN";
    String quality = "unknown";
    int32_t raw_value = 0;
    String sensor_type;
    uint8_t sample_count = 0;
    float adc_stddev = 0.0f;
    bool stable = false;
    bool has_sampling_stats = false;
};

class SensorManager {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static SensorManager& getInstance() {
        static SensorManager instance;
        return instance;
    }

    // Prevent copy and move operations
    SensorManager(const SensorManager&) = delete;
    SensorManager& operator=(const SensorManager&) = delete;
    SensorManager(SensorManager&&) = delete;
    SensorManager& operator=(SensorManager&&) = delete;

    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize sensor manager
    bool begin();

    // Deinitialize sensor manager
    void end();

    // ============================================
    // RAW DATA READING (PHASE 3 PREPARATION)
    // ============================================
    // These methods will be fully implemented in Phase 4
    // Currently serve as API skeleton for Phase 3 integration
    
    // Perform I2C measurement and return raw bytes
    // Will be implemented in Phase 4 with full sensor driver support
    bool performI2CMeasurement(uint8_t device_address, uint8_t reg, 
                               uint8_t* buffer, size_t len);
    
    // Perform OneWire temperature measurement and return raw value
    // Will be implemented in Phase 4 with full sensor driver support
    bool performOneWireMeasurement(const uint8_t rom[8], int16_t& raw_value);

    // ============================================
    // SENSOR CONFIGURATION (PHASE 4)
    // ============================================
    // Configure a sensor
    bool configureSensor(const SensorConfig& config);
    
    // Remove a sensor (address-based for multi-sensor GPIOs)
    bool removeSensor(uint8_t gpio, const String& onewire_address = "",
                      uint8_t i2c_address = 0);
    
    // Get sensor configuration
    SensorConfig getSensorConfig(uint8_t gpio) const;
    
    // Check if sensor exists on GPIO
    bool hasSensorOnGPIO(uint8_t gpio) const;
    
    // Get active sensor count
    uint8_t getActiveSensorCount() const;

    /** Count configured sensors whose subzone_id matches (Phase 9). */
    uint8_t countSensorsWithSubzone(const String& subzone_id) const;

    // ============================================
    // SENSOR READING (PHASE 4)
    // ============================================
    // Perform measurement for a specific GPIO-based sensor
    bool performMeasurement(uint8_t gpio, SensorReading& reading_out);

    // Perform multi-value measurement (for sensors that provide multiple values)
    // Returns number of readings created, or 0 if failed
    uint8_t performMultiValueMeasurement(uint8_t gpio, SensorReading* readings_out, uint8_t max_readings);

    // Perform measurements for all active sensors
    // Publishes results via MQTT automatically
    void performAllMeasurements();

    // Set measurement interval (Phase 2: Robustness)
    void setMeasurementInterval(unsigned long interval_ms);

    // ✅ Phase 2C: Trigger manual measurement for on-demand sensors
    // Returns full outcome contract projection for queue-worker mapping.
    // timeout_ms: Max duration before aborting (E-P3 Timeout-Guard, default 5s)
    ManualMeasurementResult triggerManualMeasurement(uint8_t gpio, uint32_t timeout_ms = 5000,
                                                     uint8_t sample_count = 0,
                                                     uint16_t sample_delay_ms = 0);

    // ============================================
    // RAW DATA READING METHODS (PHASE 4)
    // ============================================
    // Read raw analog value
    uint32_t readRawAnalog(uint8_t gpio);

    // Acquire a RAW analog-probe value for the given sensor, dispatching on
    // adc_source: "internal" -> readRawAnalog(gpio) (0..4095); "ads1115" ->
    // external 16-bit I2C ADC via I2CBusManager (0..32767). Returns 0 on failure
    // (the median path then treats it as a disconnect and keeps the last value).
    uint32_t acquireProbeRaw(SensorConfig* config);

    // E-P2: ADC Validation — checks raw analog value for plausibility
    // Returns quality string: "good", "suspect" (rail/noise), or "error" (invalid)
    // Detects: ADC rail (0 or adc_max), near-rail, disconnected sensor heuristics.
    // adc_max selects the scale: 4095 (internal 12-bit) or 32767 (ADS1115 16-bit).
    static const char* validateAdcReading(uint32_t raw, uint8_t gpio, uint32_t adc_max = 4095);
    
    // Read raw digital value
    uint32_t readRawDigital(uint8_t gpio);
    
    // Read raw I2C data
    bool readRawI2C(uint8_t gpio, uint8_t device_address, 
                    uint8_t reg, uint8_t* buffer, size_t len);
    
    // Read raw OneWire data
    bool readRawOneWire(uint8_t gpio, const uint8_t rom[8], int16_t& raw_value);
    
    // ============================================
    // SAFETY-P4: Value Cache
    // ============================================
    // Returns last known processed value for a sensor type on a given GPIO.
    // Returns NAN if no valid cache entry exists or entry is older than
    // VALUE_CACHE_STALE_MS (5 minutes).
    float getSensorValue(uint8_t gpio, const char* sensor_type) const;

    // ============================================
    // STATUS QUERIES
    // ============================================
    bool isInitialized() const { return initialized_; }
    
    // Get sensor info string
    String getSensorInfo(uint8_t gpio) const;

private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    SensorManager();
    ~SensorManager();

    // ============================================
    // INTERNAL STATE
    // ============================================
    #ifndef MAX_SENSORS
      #define MAX_SENSORS 10  // Default fallback if not defined in platformio.ini
    #endif
    SensorConfig sensors_[MAX_SENSORS];
    uint8_t sensor_count_;
    // AUT-303: reject duplicate on-demand measure while one is in progress (per slot)
    bool manual_measure_busy_[MAX_SENSORS] = {};

    // AUT-734 C2: Analog probe warmup gate — mirrors Ds18b20ReadingCounter pattern.
    // Requires ANALOG_WARMUP_MIN_SAMPLES consecutive non-zero reads before populating ValueCache.
    // Matches OFFLINE_WARMUP_VALID_SAMPLES so SensorManager release and OMM rule-gate are synchronous.
    static constexpr uint8_t ANALOG_WARMUP_MIN_SAMPLES = 3U;
    uint8_t analog_warmup_count_[MAX_SENSORS] = {};

    // AUT-738: Boot settling constants for capacitive analog sensors.
    // RC circuit charges at power-on (~1-2s to stabilize, up to 35s to discharge
    // air→substrate; Cave Pearl Project). 5s covers the RC charge transient.
    // ANALOG_BOOT_SETTLE_MS is semantically distinct from SENSOR_BOOT_STAGGER_MS
    // (inter-sensor stagger) — kept separate despite equal value.
    static constexpr uint32_t ANALOG_BOOT_SETTLE_MS           = 5000U;
    static constexpr uint16_t ANALOG_DISCONNECT_LOW_THRESHOLD  = 50U;
    static constexpr uint16_t ANALOG_DISCONNECT_HIGH_THRESHOLD = 4050U;
    unsigned long analog_settle_start_ms_ = 0;

    bool initialized_;

    // ============================================
    // SAFETY-P4: Value Cache
    // ============================================
    // Stores last processed_value per (gpio, sensor_type) pair.
    // Used by OfflineModeManager to evaluate hysteresis rules without
    // triggering a new measurement.
    static constexpr unsigned long VALUE_CACHE_STALE_MS = 300000UL;  // 5 minutes
    static const uint8_t MAX_VALUE_CACHE_ENTRIES = 20;

    // AUT-676/AUT-590: initial stagger between sensors on first boot measurement.
    // Non-blocking: extends required interval for last_reading==0 sensors by i*5s.
    static constexpr uint32_t SENSOR_BOOT_STAGGER_MS = 5000U;

    struct ValueCacheEntry {
        uint8_t       gpio;
        char          sensor_type[24];
        float         value;
        unsigned long timestamp_ms;
        bool          valid;
    };

    ValueCacheEntry value_cache_[MAX_VALUE_CACHE_ENTRIES];
    uint8_t         value_cache_count_ = 0;

    // Update or insert a cache entry (called from publishSensorReading)
    void updateValueCache(uint8_t gpio, const char* sensor_type, float value);
    
    // Component references
    class MQTTClient* mqtt_client_;
    class I2CBusManager* i2c_bus_;
    class OneWireBusManager* onewire_bus_;
    class GPIOManager* gpio_manager_;
    
    // Measurement timing
    unsigned long last_measurement_time_;
    unsigned long measurement_interval_;  // 30s default
    
    // ============================================
    // HELPER METHODS
    // ============================================
    // Find sensor config by GPIO (+ optional address for multi-sensor GPIOs)
    // sensor_type: when non-empty, additionally matches sensor_type — used for I2C
    // multi-value sensors (e.g. SHT31 sht31_temp vs. sht31_humidity share GPIO+address).
    SensorConfig* findSensorConfig(uint8_t gpio,
        const String& onewire_address = "", uint8_t i2c_address = 0,
        const String& sensor_type = "");
    const SensorConfig* findSensorConfig(uint8_t gpio,
        const String& onewire_address = "", uint8_t i2c_address = 0,
        const String& sensor_type = "") const;

    // Internal: measurement with known config (avoids GPIO-only re-lookup for multi-sensor GPIOs)
    bool performMeasurementForConfig(SensorConfig* config, SensorReading& reading_out);

    // AUT-441: Canonical median-based analog probe measurement (shared by continuous + manual paths)
    bool measureAnalogProbeMedian(SensorConfig* config, SensorReading& reading_out,
                                  uint8_t sample_count = 0, uint16_t sample_delay_ms = 0);

    // Pulse-counting measurement for flow sensors (FS300A and compatible).
    // Reads the ISR-maintained counter atomically and resets it (publish-and-reset).
    bool measurePulseCount(const SensorConfig* config, uint8_t slot_idx, SensorReading& reading_out);
    
    // Publish sensor reading via MQTT
    bool publishSensorReading(const SensorReading& reading);
    
    // Build MQTT payload from sensor reading
    String buildMQTTPayload(const SensorReading& reading) const;
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
extern SensorManager& sensorManager;

#endif // SERVICES_SENSOR_SENSOR_MANAGER_H
