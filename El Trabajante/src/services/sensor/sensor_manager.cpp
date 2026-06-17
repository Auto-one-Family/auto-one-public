#include "sensor_manager.h"
#include "../../tasks/rtos_globals.h"
#include "../../tasks/safety_task.h"
#include "../communication/mqtt_client.h"
// AUT-714: Spool offline readings to LittleFS
#include "../spool/spool_manager.h"
#include "../config/config_manager.h"
#include "../../drivers/gpio_manager.h"
#include <cmath>   // NAN, isnan — used by SAFETY-P4 value cache
#include <cstring> // memset, strncmp, strncpy — used by value cache
#include <WiFi.h>  // For ADC2/WiFi conflict detection
#include "../../drivers/i2c_bus.h"
#include "../../drivers/i2c_sensor_protocol.h"
#include "../../drivers/onewire_bus.h"
#include "../../drivers/mhz19_uart.h"
#include "../../utils/topic_builder.h"
#include "../../utils/logger.h"
#include "../../utils/time_manager.h"
#include "../../utils/onewire_utils.h"  // For OneWire ROM-Code conversion
#include "../../error_handling/error_tracker.h"
#include "../../models/error_codes.h"
#include "../../models/watchdog_types.h"
#include "../../models/sensor_types.h"
#include "../../models/sensor_registry.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ESP-IDF TAG convention for structured logging
static const char* TAG = "SENSOR";

static const unsigned long MHZ19_WARMUP_MS = 180000;

static bool hasValidUartPinConfig(const SensorConfig& config) {
    return config.uart_rx_pin != 255 && config.uart_tx_pin != 255 &&
           config.uart_rx_pin != 0 && config.uart_tx_pin != 0;
}

static void mergeUartPinsFromPrevious(SensorConfig& incoming, const SensorConfig& previous) {
    if (hasValidUartPinConfig(incoming)) {
        return;
    }
    if (!hasValidUartPinConfig(previous)) {
        return;
    }
    incoming.uart_rx_pin = previous.uart_rx_pin;
    incoming.uart_tx_pin = previous.uart_tx_pin;
    incoming.uart_baud = previous.uart_baud;
    if (incoming.interface_type.length() == 0) {
        incoming.interface_type = previous.interface_type;
    }
}

static bool uartHardwareConfigChanged(const SensorConfig& a, const SensorConfig& b) {
    return a.uart_rx_pin != b.uart_rx_pin ||
           a.uart_tx_pin != b.uart_tx_pin ||
           a.uart_baud != b.uart_baud;
}

static bool isUartSensorConfig(const SensorConfig& config, const SensorCapability* capability) {
    if (capability && capability->is_uart) {
        return true;
    }
    if (config.interface_type.equalsIgnoreCase("UART")) {
        return true;
    }
    return hasValidUartPinConfig(config);
}

static bool reserveUartSensorPins(GPIOManager* gpio_manager, const SensorConfig& config) {
    if (!gpio_manager) {
        return false;
    }
    if (!gpio_manager->isPinAvailable(config.uart_rx_pin)) {
        LOG_E(TAG, "Sensor Manager: UART RX GPIO " + String(config.uart_rx_pin) + " not available");
        return false;
    }
    if (!gpio_manager->requestPin(config.uart_rx_pin, "sensor", "co2_uart_rx")) {
        LOG_E(TAG, "Sensor Manager: Failed to reserve UART RX GPIO " + String(config.uart_rx_pin));
        return false;
    }
    if (!gpio_manager->isPinAvailable(config.uart_tx_pin)) {
        gpio_manager->releasePin(config.uart_rx_pin);
        LOG_E(TAG, "Sensor Manager: UART TX GPIO " + String(config.uart_tx_pin) + " not available");
        return false;
    }
    if (!gpio_manager->requestPin(config.uart_tx_pin, "sensor", "co2_uart_tx")) {
        gpio_manager->releasePin(config.uart_rx_pin);
        LOG_E(TAG, "Sensor Manager: Failed to reserve UART TX GPIO " + String(config.uart_tx_pin));
        return false;
    }
    if (config.gpio != config.uart_rx_pin && config.gpio != config.uart_tx_pin &&
        gpio_manager->isPinAvailable(config.gpio)) {
        gpio_manager->requestPin(config.gpio, "sensor", config.sensor_name.c_str());
    }
    return true;
}

static void releaseUartSensorPinsIfUnused(GPIOManager* gpio_manager,
                                          const SensorConfig* removed,
                                          const SensorConfig* sensors,
                                          uint8_t sensor_count) {
    if (!gpio_manager || !removed) {
        return;
    }
    auto pinStillUsed = [&](uint8_t pin) {
        for (uint8_t i = 0; i < sensor_count; i++) {
            if (&sensors[i] == removed) {
                continue;
            }
            if (!sensors[i].active) {
                continue;
            }
            if (sensors[i].uart_rx_pin == pin || sensors[i].uart_tx_pin == pin ||
                sensors[i].gpio == pin) {
                return true;
            }
        }
        return false;
    };
    if (!pinStillUsed(removed->uart_rx_pin)) {
        gpio_manager->releasePin(removed->uart_rx_pin);
    }
    if (!pinStillUsed(removed->uart_tx_pin)) {
        gpio_manager->releasePin(removed->uart_tx_pin);
    }
    if (removed->gpio != removed->uart_rx_pin && removed->gpio != removed->uart_tx_pin &&
        !pinStillUsed(removed->gpio)) {
        gpio_manager->releasePin(removed->gpio);
    }
}

// SAFETY-RTOS M4: serialize manual vs autonomous measurement (same as performAllMeasurements).
namespace {
class SensorArrayMutexLock {
public:
    SensorArrayMutexLock() = default;
    bool tryTake(uint32_t wait_ms) {
        if (xSemaphoreTake(g_sensor_mutex, pdMS_TO_TICKS(wait_ms)) == pdTRUE) {
            held_ = true;
            return true;
        }
        return false;
    }
    void give() {
        if (held_) {
            xSemaphoreGive(g_sensor_mutex);
            held_ = false;
        }
    }
    ~SensorArrayMutexLock() { give(); }

    SensorArrayMutexLock(const SensorArrayMutexLock&) = delete;
    SensorArrayMutexLock& operator=(const SensorArrayMutexLock&) = delete;

private:
    bool held_ = false;
};

static constexpr uint32_t kManualSensorMutexWaitMs = 10000;  // bounded wait vs portMAX_DELAY in autonomous path

bool isAnalogProbeSensorType(const String& sensor_type) {
    String lower = sensor_type;
    lower.toLowerCase();
    return lower.indexOf("ph") >= 0 ||
           lower.indexOf("ec") >= 0 ||
           lower.indexOf("moisture") >= 0 ||
           lower.indexOf("soil") >= 0;
}

bool isHighPrecisionAnalogProbe(const String& sensor_type) {
    String lower = sensor_type;
    lower.toLowerCase();
    return lower.indexOf("ph") >= 0 || lower.indexOf("ec") >= 0;
}

void resolveAnalogProbeSampleParams(const String& sensor_type, uint8_t& sample_count,
                                    uint16_t& sample_delay_ms) {
    if (sample_count == 0) {
        sample_count = isHighPrecisionAnalogProbe(sensor_type) ? 30 : 3;
    }
    if (sample_delay_ms == 0) {
        sample_delay_ms = isHighPrecisionAnalogProbe(sensor_type) ? 100 : 200;
    }
}

float computePopulationStdDev(const uint32_t* values, uint8_t count) {
    if (count < 2) {
        return 0.0f;
    }
    float sum = 0.0f;
    for (uint8_t i = 0; i < count; i++) {
        sum += static_cast<float>(values[i]);
    }
    const float mean = sum / static_cast<float>(count);
    float variance_sum = 0.0f;
    for (uint8_t i = 0; i < count; i++) {
        const float diff = static_cast<float>(values[i]) - mean;
        variance_sum += diff * diff;
    }
    return sqrtf(variance_sum / static_cast<float>(count));
}

static constexpr uint16_t kSafetyCooperativeDelayStepMs = 10;

void delayWithSafetyCooperation(uint16_t delay_ms) {
    if (delay_ms == 0) {
        return;
    }
    uint32_t remaining = delay_ms;
    while (remaining > 0) {
        const uint16_t chunk_ms = remaining > kSafetyCooperativeDelayStepMs
                                      ? kSafetyCooperativeDelayStepMs
                                      : static_cast<uint16_t>(remaining);
        vTaskDelay(pdMS_TO_TICKS(chunk_ms));
        remaining -= chunk_ms;
        runSafetyCooperativeSlice();
    }
}
}  // namespace

// ============================================
// PULSE SENSOR ISR (Flow sensors: FS300A, YFS-201 and compatible)
// ============================================
// IRAM_ATTR is mandatory: ISR must reside in IRAM so it can be called even when
// the instruction cache is busy fetching from Flash (WiFi interrupts, SPI, etc.).
// Without IRAM_ATTR the ISR risks a cache exception (illegal instruction crash).
#define MAX_PULSE_SENSORS 8
static volatile uint32_t s_pulse_counts[MAX_PULSE_SENSORS];
static uint8_t           s_pulse_gpios[MAX_PULSE_SENSORS];
static unsigned long     s_pulse_last_read_ms[MAX_PULSE_SENSORS];
static uint8_t           s_pulse_sensor_count = 0;

static void IRAM_ATTR pulseSensorISR(void* arg) {
    uint8_t idx = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(arg));
    s_pulse_counts[idx]++;
}

// ============================================
// DS18B20 SPECIAL VALUE DETECTION (Defense-in-Depth)
// ============================================
// RAW = Temperature × 16 (12-bit resolution)
// -127°C = -2032 RAW: Sensor disconnected, CRC failure, or bus error
// +85°C = +1360 RAW: Power-on reset value (factory default before first conversion)
constexpr int16_t DS18B20_RAW_SENSOR_FAULT = -2032;   // -127°C: Disconnected/CRC fail
constexpr int16_t DS18B20_RAW_POWER_ON_RESET = 1360;  // +85°C: Factory default
constexpr int16_t DS18B20_RAW_MIN_VALID = -880;       // -55°C: Datasheet minimum
constexpr int16_t DS18B20_RAW_MAX_VALID = 2000;       // +125°C: Datasheet maximum

// Track first readings per DS18B20 without heap allocations.
// std::map<String,...> can allocate in the safety task and abort on low memory.
struct Ds18b20ReadingCounter {
    bool used = false;
    uint8_t gpio = 255;
    char onewire_address[24] = {0};
    uint32_t count = 0;
};

static constexpr uint8_t MAX_DS18B20_READING_COUNTERS = 16;
static Ds18b20ReadingCounter ds18b20_reading_counters[MAX_DS18B20_READING_COUNTERS];

static uint32_t getAndIncrementDs18b20ReadingCount(uint8_t gpio, const String& onewire_address) {
    int free_idx = -1;
    for (uint8_t i = 0; i < MAX_DS18B20_READING_COUNTERS; ++i) {
        if (!ds18b20_reading_counters[i].used) {
            if (free_idx < 0) {
                free_idx = i;
            }
            continue;
        }

        if (ds18b20_reading_counters[i].gpio == gpio &&
            strncmp(ds18b20_reading_counters[i].onewire_address,
                    onewire_address.c_str(),
                    sizeof(ds18b20_reading_counters[i].onewire_address)) == 0) {
            uint32_t previous = ds18b20_reading_counters[i].count;
            ds18b20_reading_counters[i].count++;
            return previous;
        }
    }

    if (free_idx >= 0) {
        Ds18b20ReadingCounter& entry = ds18b20_reading_counters[free_idx];
        entry.used = true;
        entry.gpio = gpio;
        strncpy(entry.onewire_address, onewire_address.c_str(), sizeof(entry.onewire_address) - 1);
        entry.onewire_address[sizeof(entry.onewire_address) - 1] = '\0';
        entry.count = 1;
        return 0;
    }

    // Defensive fallback: if counter table is full, behave as "not first reading"
    // to avoid false-positive power-on-reset filtering.
    LOG_W(TAG, "DS18B20 reading counter table full - using fallback count");
    return 1;
}

// ============================================
// SENSOR CIRCUIT BREAKER CONSTANTS
// ============================================
static constexpr uint8_t  CB_MAX_CONSECUTIVE_FAILURES = 10;
static constexpr uint32_t CB_PROBE_INTERVAL_MS = 300000;  // 5 minutes

// ============================================
// LOCAL PREVIEW CONVERSION (Direct MQTT Flow)
// ============================================
// Standard conversion formulas for known sensor types.
// Provides human-readable preview values in the MQTT payload.
// The server re-processes the raw value with its full sensor library
// (calibration, quality assessment, range validation) — this is only a preview.
struct LocalConversion {
    float value;
    const char* unit;
    bool converted;  // true if known type, false if raw passthrough
};

static LocalConversion applyLocalConversion(const String& sensor_type, uint32_t raw_value) {
    // SHT31 Temperature: T(°C) = -45 + 175 × (raw / 65535)
    if (sensor_type == "sht31_temp") {
        return { -45.0f + 175.0f * ((float)raw_value / 65535.0f), "°C", true };
    }
    // SHT31 Humidity: H(%) = 100 × (raw / 65535)
    if (sensor_type == "sht31_humidity") {
        return { 100.0f * ((float)raw_value / 65535.0f), "%", true };
    }
    // DS18B20 Temperature: T(°C) = raw × 0.0625 (12-bit resolution)
    if (sensor_type == "ds18b20") {
        return { (float)((int32_t)raw_value) * 0.0625f, "°C", true };
    }
    // BMP280/BME280 Temperature: raw is centidegrees
    if (sensor_type == "bmp280_temp" || sensor_type == "bme280_temp") {
        return { (float)raw_value / 100.0f, "°C", true };
    }
    // BMP280/BME280 Pressure: raw is centipascals
    if (sensor_type == "bmp280_pressure" || sensor_type == "bme280_pressure") {
        return { (float)raw_value / 100.0f, "hPa", true };
    }
    // BME280 Humidity: raw is 1024ths of percent
    if (sensor_type == "bme280_humidity") {
        return { (float)raw_value / 1024.0f, "%", true };
    }
    // CO2 (UART MH-Z19): raw PPM passthrough
    if (sensor_type == "co2") {
        return { (float)raw_value, "ppm", true };
    }
    // Digital level switch: value already Active-Low converted (0 or 1), no unit
    if (sensor_type == "liquid_level") {
        return { (float)raw_value, "", true };
    }
    // Unknown → raw passthrough (server handles conversion)
    return { (float)raw_value, "raw", false };
}

// ============================================
// GLOBAL INSTANCE
// ============================================
SensorManager& sensorManager = SensorManager::getInstance();

// ============================================
// CONSTRUCTOR / DESTRUCTOR
// ============================================
SensorManager::SensorManager()
    : sensor_count_(0),
      initialized_(false),
      mqtt_client_(nullptr),
      i2c_bus_(nullptr),
      onewire_bus_(nullptr),
      gpio_manager_(nullptr),
      last_measurement_time_(0),
      measurement_interval_(30000),  // 30s default interval
      value_cache_count_(0) {
    // Zero-initialize value cache
    memset(value_cache_, 0, sizeof(value_cache_));
}

SensorManager::~SensorManager() {
    end();
}

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool SensorManager::begin() {
    if (initialized_) {
        LOG_W(TAG, "Sensor Manager already initialized");
        return true;
    }

    LOG_I(TAG, "Sensor Manager initialization started (Phase 4)");
    
    // Get component references
    mqtt_client_ = &MQTTClient::getInstance();
    i2c_bus_ = &I2CBusManager::getInstance();
    onewire_bus_ = &OneWireBusManager::getInstance();
    gpio_manager_ = &GPIOManager::getInstance();
    
    // Reset sensor registry
    sensor_count_ = 0;
    for (uint8_t i = 0; i < MAX_SENSORS; i++) {
        sensors_[i].gpio = 255;
        sensors_[i].active = false;
    }
    memset(analog_warmup_count_, 0, sizeof(analog_warmup_count_));
    analog_settle_start_ms_ = millis();  // AUT-738: start of boot-settling window

    initialized_ = true;
    last_measurement_time_ = 0;
    
    LOG_I(TAG, "Sensor Manager initialized (Phase 4)");
    
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void SensorManager::end() {
    if (!initialized_) {
        LOG_W(TAG, "Sensor Manager not initialized");
        return;
    }

    // Release GPIO pins for non-I2C sensors only
    // I2C sensor GPIOs are managed by I2CBusManager
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].active && sensors_[i].gpio != 255) {
            // Check if this is an I2C sensor
            const SensorCapability* capability = findSensorCapability(sensors_[i].sensor_type);
            bool is_i2c_sensor = (capability != nullptr && capability->is_i2c);

            if (!is_i2c_sensor) {
                gpio_manager_->releasePin(sensors_[i].gpio);
            }
        }
    }

    sensor_count_ = 0;
    initialized_ = false;

    LOG_I(TAG, "Sensor Manager shutdown");
}

// ============================================
// RAW I2C MEASUREMENT (PHASE 3 PREPARATION)
// ============================================
bool SensorManager::performI2CMeasurement(uint8_t device_address, uint8_t reg,
                                          uint8_t* buffer, size_t len) {
    if (!initialized_) {
        LOG_E(TAG, "Sensor Manager not initialized");
        return false;
    }
    
    // Direct pass-through to I2C Bus Manager
    // Phase 4: Add sensor-specific processing
    return i2cBusManager.readRaw(device_address, reg, buffer, len);
}

// ============================================
// RAW ONEWIRE MEASUREMENT (PHASE 3 PREPARATION)
// ============================================
bool SensorManager::performOneWireMeasurement(const uint8_t rom[8], int16_t& raw_value) {
    if (!initialized_) {
        LOG_E(TAG, "Sensor Manager not initialized");
        return false;
    }
    
    // Direct pass-through to OneWire Bus Manager
    // Phase 4: Add sensor-specific processing
    return oneWireBusManager.readRawTemperature(rom, raw_value);
}

// ============================================
// SENSOR CONFIGURATION (PHASE 4)
// ============================================
bool SensorManager::configureSensor(const SensorConfig& config) {
    if (!initialized_) {
        LOG_E(TAG, "Sensor Manager not initialized");
        return false;
    }
    // SAFETY-RTOS M4: protect sensors_[] against performAllMeasurements (Core 1).
    xSemaphoreTake(g_sensor_mutex, portMAX_DELAY);

    // Validate GPIO
    if (config.gpio == 255) {
        LOG_E(TAG, "Sensor Manager: Invalid GPIO (255)");
        errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "Invalid GPIO for sensor");
        xSemaphoreGive(g_sensor_mutex);
        return false;
    }

    // Get sensor capability to determine interface type
    const SensorCapability* capability = findSensorCapability(config.sensor_type);
    bool is_i2c_sensor = (capability != nullptr && capability->is_i2c);

    // ADS1115-backed analog probes (pH/EC) also use gpio=0: the data arrives over
    // the I2C bus (ADS1115 module address), not a dedicated ESP32 ADC pin. They
    // keep their analog capability (RAW->voltage path unchanged) but must be
    // treated like I2C-bus sensors for the gpio=0 / no-GPIO-reservation rules.
    bool is_external_adc = (config.adc_source == AdcSourceCode::ADS1115);
    bool uses_i2c_bus = is_i2c_sensor || is_external_adc;

    // Guard: gpio=0 is the backend convention for "no dedicated GPIO" (I2C bus sensors).
    // Non-I2C sensors must NOT use gpio=0 — it is a boot strap pin and would trigger
    // analogRead(0) on ADC2, which fails when WiFi is active.
    if (config.gpio == 0 && !uses_i2c_bus) {
        LOG_E(TAG, "Sensor Manager: GPIO 0 rejected for non-I2C sensor '" +
              config.sensor_type + "' (boot strap pin, reserved for I2C bus convention)");
        errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "GPIO 0 invalid for non-I2C sensor");
        xSemaphoreGive(g_sensor_mutex);
        return false;
    }

    // Phase 7 + R20-P2: Address-based lookup for multi-sensor GPIOs
    // OneWire: match by ROM-Code, I2C: match by device address from config (payload)
    // Use config.i2c_address if provided (multi-device support), fall back to capability default.
    // This allows two SHT31 at 0x44 and 0x45 to be distinguished correctly.
    uint8_t effective_i2c_address = config.i2c_address;
    if (effective_i2c_address == 0 && capability != nullptr && capability->i2c_address != 0) {
        effective_i2c_address = capability->i2c_address;  // Fallback to registry default
    }
    // For I2C multi-value sensors (e.g. SHT31): pass sensor_type so that sht31_temp
    // and sht31_humidity (same GPIO + same I2C address) are matched independently.
    // For OneWire and ADC sensors sensor_type is omitted — ROM-Code already distinguishes
    // DS18B20 instances; passing sensor_type there would break update-in-place for type changes.
    // ADS1115 analog probes share gpio=0 + i2c_address and differ only by sensor_type
    // and adc_channel, so they are matched by sensor_type like I2C-bus sensors.
    SensorConfig* existing = findSensorConfig(config.gpio,
        config.onewire_address, effective_i2c_address,
        uses_i2c_bus ? config.sensor_type : String(""));

    // ADS1115: two probes of the SAME sensor_type on different channels of one
    // module are distinct sensors (mirrors the server's channel-aware uniqueness).
    // Don't update-in-place across channels — force a new entry instead.
    if (existing && is_external_adc && existing->adc_channel != config.adc_channel) {
        existing = nullptr;
    }

    if (!existing && is_i2c_sensor) {
        // No exact match found — check if a different value type of the same I2C device exists
        // (Multi-value sensors like SHT31 share GPIO + I2C address but have different sensor_types)
        // Use effective_i2c_address (from config payload) to correctly match the physical device.
        for (uint8_t k = 0; k < sensor_count_; k++) {
            if (sensors_[k].gpio != config.gpio) continue;
            const SensorCapability* existing_cap = findSensorCapability(sensors_[k].sensor_type);
            if (existing_cap && existing_cap->is_i2c &&
                sensors_[k].i2c_address == effective_i2c_address &&
                String(existing_cap->device_type) == String(capability->device_type) &&
                sensors_[k].sensor_type != config.sensor_type) {
                // Same I2C device (same address), different value type — multi-value add/update

                // Check if this sensor_type already exists in sensors_[] (prevent RAM duplicates)
                for (uint8_t m = 0; m < sensor_count_; m++) {
                    if (sensors_[m].gpio == config.gpio &&
                        sensors_[m].sensor_type == config.sensor_type &&
                        sensors_[m].i2c_address == effective_i2c_address) {
                        // Already exists — update in place instead of adding
                        sensors_[m] = config;
                        sensors_[m].active = true;
                        sensors_[m].i2c_address = effective_i2c_address;
                        if (!configManager.saveSensorConfig(config)) {
                            LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
                        } else {
                            LOG_I(TAG, "  ✅ Configuration persisted to NVS");
                        }
                        LOG_I(TAG, "Sensor Manager: Updated existing multi-value sensor '" +
                                   config.sensor_type + "' on GPIO " + String(config.gpio));
                        xSemaphoreGive(g_sensor_mutex);
                        return true;
                    }
                }

                // Not found — add as new sensor (multi-value support)
                if (sensor_count_ >= MAX_SENSORS) {
                    LOG_E(TAG, "Sensor Manager: Maximum sensor count reached");
                    xSemaphoreGive(g_sensor_mutex);
                    return false;
                }

                sensors_[sensor_count_] = config;
                sensors_[sensor_count_].active = true;
                sensors_[sensor_count_].i2c_address = effective_i2c_address;
                sensor_count_++;

                if (!configManager.saveSensorConfig(config)) {
                    LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
                } else {
                    LOG_I(TAG, "  ✅ Configuration persisted to NVS");
                }

                LOG_I(TAG, "Sensor Manager: Added multi-value sensor '" + config.sensor_type +
                         "' on GPIO " + String(config.gpio) + " (I2C 0x" +
                         String(effective_i2c_address, HEX) + ")");
                xSemaphoreGive(g_sensor_mutex);
                return true;
            }
        }
    }

    if (existing) {
        // Runtime reconfiguration: Update existing sensor
        LOG_I(TAG, "Sensor Manager: Updating existing sensor on GPIO " + String(config.gpio));

        // Check if sensor type changed
        bool type_changed = (existing->sensor_type != config.sensor_type);
        if (type_changed) {
            LOG_I(TAG, "  Sensor type changed: " + existing->sensor_type + " → " + config.sensor_type);
        }

        // F7: Log Circuit Breaker reset on config push
        if (existing->cb_state != SensorCBState::CLOSED) {
            LOG_I(TAG, "Sensor " + existing->sensor_type +
                       ": Circuit Breaker reset by config push");
        }

        SensorConfig merged = config;
        mergeUartPinsFromPrevious(merged, *existing);
        const unsigned long prev_warmup_ms = existing->uart_configured_at_ms;
        const bool uart_hw_changed = isUartSensorConfig(merged, capability) &&
                                     uartHardwareConfigChanged(merged, *existing);

        // Update configuration
        *existing = merged;
        existing->active = true;
        // F7: Explicit CB reset (config push = fresh start)
        existing->cb_state = SensorCBState::CLOSED;
        existing->consecutive_failures = 0;
        analog_warmup_count_[existing - sensors_] = 0;

        if (isUartSensorConfig(merged, capability)) {
            if (!hasValidUartPinConfig(*existing)) {
                LOG_E(TAG, "Sensor Manager: UART sensor missing uart_rx_pin/uart_tx_pin");
                errorTracker.trackError(ERROR_UART_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                       "UART CO2 pins missing on update");
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }
            if (!mhz19UartReader.begin(existing->uart_rx_pin, existing->uart_tx_pin,
                                       existing->uart_baud)) {
                errorTracker.trackError(ERROR_UART_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                       "UART CO2 begin failed on update");
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }
            // Only restart warmup when UART hardware mapping actually changed
            if (uart_hw_changed || prev_warmup_ms == 0) {
                existing->uart_configured_at_ms = millis();
            } else {
                existing->uart_configured_at_ms = prev_warmup_ms;
            }
        }

        // Phase 7: Persist to NVS immediately
        if (!configManager.saveSensorConfig(*existing)) {
            LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
        } else {
            LOG_I(TAG, "  ✅ Configuration persisted to NVS");
        }

        LOG_I(TAG, "Sensor Manager: Updated sensor on GPIO " + String(existing->gpio) +
                 " (" + existing->sensor_type + ")");
        xSemaphoreGive(g_sensor_mutex);
        return true;
    }

    // New sensor: Check if we have space
    if (sensor_count_ >= MAX_SENSORS) {
        LOG_E(TAG, "Sensor Manager: Maximum sensor count reached");
        errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "Maximum sensor count reached");
        xSemaphoreGive(g_sensor_mutex);
        return false;
    }

    // ============================================
    // INTERFACE-SPECIFIC CONFIGURATION
    // ============================================
    if (is_i2c_sensor) {
        // I2C Sensor: Use I2C bus, NO GPIO reservation needed
        // GPIO 21/22 are already reserved by I2CBusManager as "system"/"I2C_SDA"/"I2C_SCL"

        // Check 1: I2C bus must be initialized
        if (!i2c_bus_->isInitialized()) {
            LOG_E(TAG, "Sensor Manager: I2C bus not initialized");
            errorTracker.trackError(ERROR_I2C_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "I2C bus not initialized for I2C sensor");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        // Check 2: I2C address conflict detection
        // (Different device type on same I2C address = conflict)
        // Use effective_i2c_address (from config payload) to support multiple devices
        // of the same chip type at different addresses (e.g. SHT31 at 0x44 and 0x45).
        for (uint8_t i = 0; i < sensor_count_; i++) {
            if (!sensors_[i].active) continue;

            const SensorCapability* existing_cap = findSensorCapability(sensors_[i].sensor_type);
            if (existing_cap && existing_cap->is_i2c &&
                sensors_[i].i2c_address == effective_i2c_address) {
                // Same I2C address - check if same device type (allowed for multi-value)
                if (String(existing_cap->device_type) != String(capability->device_type)) {
                    LOG_E(TAG, "Sensor Manager: I2C address 0x" + String(effective_i2c_address, HEX) +
                              " already in use by different device type '" +
                              String(existing_cap->device_type) + "'");
                    errorTracker.trackError(ERROR_I2C_DEVICE_NOT_FOUND, ERROR_SEVERITY_ERROR,
                                           "I2C address conflict");
                    xSemaphoreGive(g_sensor_mutex);
                    return false;
                }
                // Same device type on same address is OK (multi-value sensor)
            }
        }

        // Optional: Check if I2C device is present (skip in simulation)
        if (!i2c_bus_->isDevicePresent(effective_i2c_address)) {
            LOG_W(TAG, "Sensor Manager: I2C device at 0x" + String(effective_i2c_address, HEX) +
                        " not responding (may be simulation mode)");
            // Don't fail - Wokwi simulation doesn't have real I2C devices
        }

        // BMP280/BME280: Write ctrl_meas register to exit sleep mode
        // BMP280 starts in sleep mode after power-on (datasheet BST-BMP280-DS001-26)
        // BME280 additionally needs ctrl_hum (0xF2) BEFORE ctrl_meas (0xF4)
        String device_type_str = String(capability->device_type);
        if (device_type_str == "bme280") {
            // BME280: ctrl_hum (0xF2) = 0x01 (humidity 1x oversampling)
            // MUST be written BEFORE ctrl_meas for changes to take effect
            Wire.beginTransmission(effective_i2c_address);
            Wire.write(0xF2);
            Wire.write(0x01);
            Wire.endTransmission();
            // BME280: ctrl_meas (0xF4) = 0x27 (temp 1x, press 1x, normal mode)
            Wire.beginTransmission(effective_i2c_address);
            Wire.write(0xF4);
            Wire.write(0x27);
            Wire.endTransmission();
            delay(10);
            LOG_I(TAG, "Sensor Manager: BME280 init sequence sent (ctrl_hum + ctrl_meas)");
        } else if (device_type_str == "bmp280") {
            // BMP280: ctrl_meas (0xF4) = 0x27 (temp 1x, press 1x, normal mode)
            Wire.beginTransmission(effective_i2c_address);
            Wire.write(0xF4);
            Wire.write(0x27);
            Wire.endTransmission();
            delay(10);
            LOG_I(TAG, "Sensor Manager: BMP280 init sequence sent (ctrl_meas)");
        }

        // Add I2C sensor (NO GPIO reservation!)
        // Store effective_i2c_address (from config payload) so that two devices of the
        // same chip type at different addresses (e.g. SHT31 at 0x44 and 0x45) are
        // tracked independently and each reads from the correct physical device.
        sensors_[sensor_count_] = config;
        sensors_[sensor_count_].active = true;
        sensors_[sensor_count_].i2c_address = effective_i2c_address;
        sensor_count_++;

        if (!configManager.saveSensorConfig(sensors_[sensor_count_ - 1])) {
            LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
        } else {
            LOG_I(TAG, "  ✅ Configuration persisted to NVS");
        }

        LOG_I(TAG, "Sensor Manager: Configured I2C sensor '" + config.sensor_type +
                 "' at address 0x" + String(effective_i2c_address, HEX) +
                 " (GPIO " + String(config.gpio) + " is I2C bus)" +
                 " [sensor_count=" + String(sensor_count_) + ", active=true]");

        xSemaphoreGive(g_sensor_mutex);
        return true;
    }

    bool is_uart_sensor = isUartSensorConfig(config, capability);

    if (is_uart_sensor) {
        if (!hasValidUartPinConfig(config)) {
            LOG_E(TAG, "Sensor Manager: UART sensor missing uart_rx_pin/uart_tx_pin");
            errorTracker.trackError(ERROR_UART_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "UART CO2 pins missing");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        if (!reserveUartSensorPins(gpio_manager_, config)) {
            errorTracker.trackError(ERROR_GPIO_CONFLICT, ERROR_SEVERITY_ERROR,
                                   "UART CO2 GPIO reservation failed");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        if (!mhz19UartReader.begin(config.uart_rx_pin, config.uart_tx_pin, config.uart_baud)) {
            gpio_manager_->releasePin(config.uart_rx_pin);
            gpio_manager_->releasePin(config.uart_tx_pin);
            if (config.gpio != config.uart_rx_pin && config.gpio != config.uart_tx_pin) {
                gpio_manager_->releasePin(config.gpio);
            }
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        sensors_[sensor_count_] = config;
        sensors_[sensor_count_].active = true;
        sensors_[sensor_count_].uart_configured_at_ms = millis();
        sensor_count_++;

        if (!configManager.saveSensorConfig(sensors_[sensor_count_ - 1])) {
            LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
        } else {
            LOG_I(TAG, "  ✅ Configuration persisted to NVS");
        }

        LOG_I(TAG, "Sensor Manager: Configured UART CO2 '" + config.sensor_type +
                 "' Serial2 rx=" + String(config.uart_rx_pin) +
                 " tx=" + String(config.uart_tx_pin) +
                 " baud=" + String(config.uart_baud) +
                 " (logical GPIO " + String(config.gpio) + ")");

        xSemaphoreGive(g_sensor_mutex);
        return true;
    }

    // Non-I2C sensor (Analog, Digital, OneWire): Standard GPIO reservation
    // Server-Centric Deviation (Hardware-Protection-Layer):
    // GPIO-Conflict-Check als Defense-in-Depth (siehe actuator_manager.cpp).
    
    // ============================================
    // ONEWIRE SENSOR HANDLING (DS18B20, DS18S20, DS1822)
    // ============================================
    // OneWire sensors share a single bus pin - special GPIO handling required
    // Defense-in-Depth: case-insensitive check (main entry points normalize,
    // but direct indexOf needs protection against mixed-case sensor_type)
    String lower_sensor_type = config.sensor_type;
    lower_sensor_type.toLowerCase();
    bool is_onewire = (capability && !capability->is_i2c &&
                       lower_sensor_type.indexOf("ds18b20") >= 0);
    
    if (is_onewire) {
        LOG_D(TAG, "SensorManager: OneWire sensor detected: " + config.sensor_type);
        
        // 1. Validate ROM-Code format (must be 16 hex chars)
        if (config.onewire_address.length() != 16) {
            LOG_E(TAG, "SensorManager: Invalid OneWire ROM-Code length (expected 16, got " +
                     String(config.onewire_address.length()) + ")");
            errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "Invalid OneWire ROM-Code length");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }
        
        // 2. Parse and validate ROM-Code
        uint8_t rom[8];
        if (!OneWireUtils::hexStringToRom(config.onewire_address, rom)) {
            LOG_E(TAG, "SensorManager: Failed to parse OneWire ROM-Code: " +
                     config.onewire_address);
            errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "Failed to parse OneWire ROM-Code");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }
        
        if (!OneWireUtils::isValidRom(rom)) {
            // CRC invalid - log as WARNING (may be transmission error) but continue
            // Server can do additional validation if needed
            LOG_W(TAG, "SensorManager: OneWire ROM-Code CRC invalid: " + 
                       config.onewire_address + " - continuing anyway (server will validate)");
            errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_CRC, ERROR_SEVERITY_WARNING,
                                   ("ROM CRC invalid: " + config.onewire_address).c_str());
            // Don't return false - CRC errors are warnings, not hard failures
        }
        
        // 2b. Duplicate ROM-Code Check (prevent same device being registered twice)
        for (uint8_t i = 0; i < sensor_count_; i++) {
            if (sensors_[i].onewire_address == config.onewire_address) {
                LOG_E(TAG, "SensorManager: OneWire ROM-Code already registered: " +
                         config.onewire_address + " on GPIO " + String(sensors_[i].gpio));
                errorTracker.trackError(ERROR_ONEWIRE_DUPLICATE_ROM, ERROR_SEVERITY_ERROR,
                                       ("Duplicate ROM: " + config.onewire_address).c_str());
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }
        }
        
        // 3. GPIO-Sharing Check (3 cases for shared OneWire bus)
        // Owner convention: "bus/onewire/{gpio}" for shared bus pins
        String owner = gpio_manager_->getPinOwner(config.gpio);

        if (owner.length() == 0) {
            // CASE A: Pin free → Bus will be initialized below (which reserves the pin)
            // No explicit reservation here - OneWireBusManager::begin() handles it
            LOG_D(TAG, "SensorManager: GPIO " + String(config.gpio) +
                     " is free, OneWire bus will reserve it");
        } else if (owner.startsWith("bus/onewire/")) {
            // CASE B: OneWire bus already exists → Sharing allowed
            // No new requestPin() needed - bus already owns the GPIO
            LOG_I(TAG, "SensorManager: Using existing OneWire bus on GPIO " + String(config.gpio) +
                    " (owner: " + owner + ")");
        } else {
            // CASE C: Pin used by something else → Conflict
            LOG_E(TAG, "SensorManager: GPIO " + String(config.gpio) +
                     " already in use by: " + owner +
                     " (expected: free or bus/onewire/" + String(config.gpio) + ")");
            errorTracker.trackError(ERROR_GPIO_CONFLICT, ERROR_SEVERITY_ERROR,
                                   "GPIO conflict for OneWire sensor");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }
        
        // 4. Single-Bus Check (architecture allows only one OneWire bus)
        if (onewire_bus_->isInitialized()) {
            uint8_t current_pin = onewire_bus_->getPin();
            if (current_pin != config.gpio) {
                LOG_E(TAG, "SensorManager: OneWire bus already active on GPIO " +
                         String(current_pin) + ", cannot use GPIO " + String(config.gpio) +
                         " (single-bus architecture)");
                errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                       "Single-bus conflict");
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }
            LOG_D(TAG, "SensorManager: OneWire bus already initialized on GPIO " + 
                     String(current_pin));
        } else {
            // First OneWire sensor → Initialize bus
            if (!onewire_bus_->begin(config.gpio)) {
                LOG_E(TAG, "SensorManager: Failed to initialize OneWire bus on GPIO " +
                         String(config.gpio));
                errorTracker.trackError(ERROR_ONEWIRE_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                       "OneWire bus init failed");
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }
            LOG_I(TAG, "SensorManager: OneWire bus initialized on GPIO " + String(config.gpio));
        }
        
        // 5. Verify device presence on bus
        if (!onewire_bus_->isDevicePresent(rom)) {
            LOG_E(TAG, "SensorManager: OneWire device " + config.onewire_address +
                     " not found on bus (GPIO " + String(config.gpio) + ")");
            errorTracker.trackError(ERROR_ONEWIRE_NO_DEVICES, ERROR_SEVERITY_ERROR,
                                   "OneWire device not found");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }
        
        LOG_I(TAG, "SensorManager: OneWire device " + config.onewire_address + 
                " verified on GPIO " + String(config.gpio) + 
                " (type: " + OneWireUtils::getDeviceType(rom) + ")");
                
        // Skip standard GPIO reservation (already handled above)
    } else if (is_external_adc) {
        // ============================================
        // EXTERNAL ADC ANALOG PROBE (ADS1115-backed pH/EC)
        // ============================================
        // Data arrives over the I2C bus (ADS1115 module address), NOT a dedicated
        // ESP32 ADC pin. gpio stays 0 and NO GPIO reservation happens. Verify the
        // I2C bus is up so the ADS1115 can be read.
        if (!i2c_bus_ || !i2c_bus_->isInitialized()) {
            LOG_E(TAG, "Sensor Manager: I2C bus not initialized for ADS1115 sensor '" +
                  config.sensor_type + "'");
            errorTracker.trackError(ERROR_I2C_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "I2C bus not initialized for ADS1115 sensor");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }
        if (!i2c_bus_->isDevicePresent(config.i2c_address)) {
            LOG_W(TAG, "Sensor Manager: ADS1115 at 0x" + String(config.i2c_address, HEX) +
                        " not responding (may be simulation mode)");
            // Don't fail — keep behaviour consistent with other I2C devices in sim.
        }
        LOG_I(TAG, "Sensor Manager: Configured ADS1115 analog probe '" + config.sensor_type +
                 "' at 0x" + String(config.i2c_address, HEX) + " ch" + String(config.adc_channel) +
                 " pga=" + String(ads1115PgaStringFromBits(config.pga_gain)) + " (no GPIO reservation)");
    } else {
        // ============================================
        // STANDARD GPIO SENSOR (Analog, Digital)
        // ============================================
        // Check GPIO availability
        if (!gpio_manager_->isPinAvailable(config.gpio)) {
            LOG_E(TAG, "Sensor Manager: GPIO " + String(config.gpio) + " not available");
            errorTracker.trackError(ERROR_GPIO_CONFLICT, ERROR_SEVERITY_ERROR,
                                   "GPIO conflict for sensor");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        // Reserve GPIO
        if (!gpio_manager_->requestPin(config.gpio, "sensor", config.sensor_name.c_str())) {
            LOG_E(TAG, "Sensor Manager: Failed to reserve GPIO " + String(config.gpio));
            errorTracker.trackError(ERROR_GPIO_RESERVED, ERROR_SEVERITY_ERROR,
                                   "Failed to reserve GPIO");
            xSemaphoreGive(g_sensor_mutex);
            return false;
        }

        // Pulse sensor (flow): register ISR for rising-edge pulse counting
        if (capability && capability->is_pulse) {
            if (s_pulse_sensor_count >= MAX_PULSE_SENSORS) {
                LOG_E(TAG, "Sensor Manager: Pulse sensor slot table full (max " +
                          String(MAX_PULSE_SENSORS) + ")");
                gpio_manager_->releasePin(config.gpio);
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }

            int interrupt_num = digitalPinToInterrupt(config.gpio);
            if (interrupt_num < 0 || interrupt_num == 255) {
                LOG_E(TAG, "Sensor Manager: GPIO " + String(config.gpio) +
                          " does not support hardware interrupts (digitalPinToInterrupt=" +
                          String(interrupt_num) + ") — pulse ISR NOT attached, flow sensor will read 0");
                gpio_manager_->releasePin(config.gpio);
                xSemaphoreGive(g_sensor_mutex);
                return false;
            }

            uint8_t slot = s_pulse_sensor_count;
            s_pulse_gpios[slot] = config.gpio;
            s_pulse_counts[slot]       = 0;
            s_pulse_last_read_ms[slot] = millis();
            s_pulse_sensor_count++;

            // INPUT_PULLUP: FS300A signal pin is open-drain/open-collector — needs pull-up
            // for reliable HIGH state between pulses. Without pull-up the pin floats and
            // RISING edges are never detected (symptom: always 0 pulses).
            pinMode(config.gpio, INPUT_PULLUP);
            attachInterruptArg(interrupt_num,
                               pulseSensorISR,
                               reinterpret_cast<void*>(static_cast<uintptr_t>(slot)),
                               RISING);

            int initial_state = digitalRead(config.gpio);
            LOG_I(TAG, "Sensor Manager: Pulse ISR attached GPIO=" + String(config.gpio) +
                      " interrupt=" + String(interrupt_num) +
                      " slot=" + String(slot) +
                      " initial_state=" + String(initial_state) +
                      (initial_state == LOW ? " [WARNING: LOW at config — check wiring/power]" : " [ok]"));
        }
    }

    // Add sensor
    sensors_[sensor_count_] = config;
    sensors_[sensor_count_].active = true;
    sensor_count_++;

    // Phase 7: Persist to NVS immediately
    if (!configManager.saveSensorConfig(config)) {
        LOG_E(TAG, "Sensor Manager: Failed to persist sensor config to NVS");
    } else {
        LOG_I(TAG, "  ✅ Configuration persisted to NVS");
    }

    LOG_I(TAG, "Sensor Manager: Configured " + String(is_onewire ? "OneWire" : "GPIO") +
             " sensor '" + config.sensor_type + "' on GPIO " + String(config.gpio));

    xSemaphoreGive(g_sensor_mutex);
    return true;
}

bool SensorManager::removeSensor(uint8_t gpio, const String& onewire_address,
                                 uint8_t i2c_address) {
    if (!initialized_) {
        LOG_E(TAG, "Sensor Manager not initialized");
        return false;
    }

    SensorConfig* config = findSensorConfig(gpio, onewire_address, i2c_address);
    if (!config) {
        LOG_W(TAG, "Sensor Manager: Sensor on GPIO " + String(gpio) + " not found");
        return false;
    }

    LOG_I(TAG, "Sensor Manager: Removing sensor on GPIO " + String(gpio) +
             (onewire_address.length() > 0 ? " OW:" + onewire_address : "") +
             (i2c_address > 0 ? " I2C:0x" + String(i2c_address, HEX) : ""));

    // Check if this is an I2C sensor (don't release GPIO - managed by I2CBusManager)
    const SensorCapability* capability = findSensorCapability(config->sensor_type);
    bool is_i2c_sensor = (capability != nullptr && capability->is_i2c);
    bool is_uart_sensor = isUartSensorConfig(*config, capability);

    // Capture sensor_type and UART pins before array shift invalidates the pointer
    String removed_sensor_type = config->sensor_type;
    uint8_t removed_uart_rx = config->uart_rx_pin;
    uint8_t removed_uart_tx = config->uart_tx_pin;

    // For pulse sensors: detach ISR and free the slot in the pulse table
    bool is_pulse_sensor = (capability != nullptr && capability->is_pulse);
    if (is_pulse_sensor) {
        detachInterrupt(digitalPinToInterrupt(gpio));
        // Free the slot so it can be reused by a newly configured pulse sensor
        for (uint8_t i = 0; i < s_pulse_sensor_count; i++) {
            if (s_pulse_gpios[i] == gpio) {
                // Compact the slot table: move last entry into this slot
                s_pulse_gpios[i]        = s_pulse_gpios[s_pulse_sensor_count - 1];
                s_pulse_counts[i]       = s_pulse_counts[s_pulse_sensor_count - 1];
                s_pulse_last_read_ms[i] = s_pulse_last_read_ms[s_pulse_sensor_count - 1];
                s_pulse_sensor_count--;
                LOG_I(TAG, "  Pulse ISR detached and slot freed for GPIO " + String(gpio));
                break;
            }
        }
    }

    // For UART sensors: release dedicated RX/TX pins (and logical slot if reserved)
    if (is_uart_sensor) {
        releaseUartSensorPinsIfUnused(gpio_manager_, config, sensors_, sensor_count_);
        LOG_I(TAG, "  ℹ️ UART sensor - released rx=" + String(removed_uart_rx) +
                 " tx=" + String(removed_uart_tx) + " if unused");
    } else if (!is_i2c_sensor) {
        // Check if another sensor shares this GPIO (OneWire bus sharing)
        bool other_on_gpio = false;
        for (uint8_t i = 0; i < sensor_count_; i++) {
            if (&sensors_[i] != config && sensors_[i].gpio == gpio) {
                other_on_gpio = true;
                break;
            }
        }
        if (!other_on_gpio) {
            gpio_manager_->releasePin(gpio);
            LOG_I(TAG, "  ✅ GPIO " + String(gpio) + " released (last sensor on pin)");
        } else {
            LOG_I(TAG, "  ℹ️ GPIO " + String(gpio) + " kept (other sensors still on bus)");
        }
    } else {
        LOG_I(TAG, "  ℹ️ I2C sensor - GPIO managed by I2C bus");
    }

    // Remove sensor (shift array) — match by pointer identity (found above)
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (&sensors_[i] == config) {
            // Shift remaining sensors
            for (uint8_t j = i; j < sensor_count_ - 1; j++) {
                sensors_[j] = sensors_[j + 1];
            }
            sensor_count_--;
            sensors_[sensor_count_].gpio = 255;
            sensors_[sensor_count_].active = false;
            break;
        }
    }

    // Phase 7: Persist removal to NVS immediately
    if (!configManager.removeSensorConfig(gpio, onewire_address, removed_sensor_type)) {
        LOG_E(TAG, "Sensor Manager: Failed to remove sensor config from NVS");
    } else {
        LOG_I(TAG, "  ✅ Configuration removed from NVS");
    }

    LOG_I(TAG, "Sensor Manager: Removed sensor on GPIO " + String(gpio));
    return true;
}

SensorConfig SensorManager::getSensorConfig(uint8_t gpio) const {
    SensorConfig empty_config;
    empty_config.gpio = 255;
    
    if (!initialized_) {
        return empty_config;
    }
    
    const SensorConfig* config = findSensorConfig(gpio);
    if (config) {
        return *config;
    }
    
    return empty_config;
}

bool SensorManager::hasSensorOnGPIO(uint8_t gpio) const {
    return findSensorConfig(gpio) != nullptr;
}

uint8_t SensorManager::getActiveSensorCount() const {
    if (!initialized_) {
        LOG_D(TAG, "getActiveSensorCount: NOT initialized, returning 0");
        return 0;
    }

    uint8_t count = 0;
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].active) {
            count++;
        }
    }
    LOG_D(TAG, "getActiveSensorCount: sensor_count_=" + String(sensor_count_) + ", active=" + String(count));
    return count;
}

uint8_t SensorManager::countSensorsWithSubzone(const String& subzone_id) const {
    if (!initialized_ || subzone_id.length() == 0) {
        return 0;
    }
    uint8_t n = 0;
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].active && sensors_[i].subzone_id == subzone_id) {
            n++;
        }
    }
    return n;
}

// ============================================
// SENSOR READING (PHASE 4)
// ============================================
bool SensorManager::performMeasurement(uint8_t gpio, SensorReading& reading_out) {
    if (!initialized_) {
        LOG_E(TAG, "Sensor Manager not initialized");
        return false;
    }

    // Find sensor config (GPIO-only lookup — correct for single-sensor-per-GPIO)
    SensorConfig* config = findSensorConfig(gpio);
    if (!config || !config->active) {
        LOG_W(TAG, "Sensor Manager: Sensor on GPIO " + String(gpio) + " not found or inactive");
        return false;
    }
    return performMeasurementForConfig(config, reading_out);
}

bool SensorManager::measureAnalogProbeMedian(SensorConfig* config, SensorReading& reading_out,
                                             uint8_t sample_count, uint16_t sample_delay_ms) {
    if (!initialized_ || !config) {
        reading_out.valid = false;
        reading_out.error_message = "Analog median measurement not possible";
        return false;
    }

    resolveAnalogProbeSampleParams(config->sensor_type, sample_count, sample_delay_ms);
    if (sample_count == 0) {
        reading_out.valid = false;
        reading_out.error_message = "Analog median measurement not possible";
        return false;
    }

    struct AnalogSample {
        uint32_t raw_value;
        const char* quality;
    };

    // Acquisition source: internal ESP32 ADC (0..4095) or external ADS1115 (0..32767).
    // Only the RAW source changes — sampling/median/stats wrap BOTH identically.
    const bool is_ads1115 = (config->adc_source == AdcSourceCode::ADS1115);
    const uint32_t adc_max = is_ads1115 ? 32767U : 4095U;

    // Keep bounded stack usage (firmware task stack is limited)
    static constexpr uint8_t MAX_ANALOG_MEDIAN_SAMPLES = 32;
    uint8_t bounded_count = sample_count > MAX_ANALOG_MEDIAN_SAMPLES ? MAX_ANALOG_MEDIAN_SAMPLES : sample_count;
    AnalogSample samples[MAX_ANALOG_MEDIAN_SAMPLES];
    uint32_t raw_values[MAX_ANALOG_MEDIAN_SAMPLES];

    for (uint8_t i = 0; i < bounded_count; i++) {
        if (i > 0 && sample_delay_ms > 0) {
            delayWithSafetyCooperation(sample_delay_ms);
        }
        uint32_t raw = acquireProbeRaw(config);
        samples[i].raw_value = raw;
        raw_values[i] = raw;
        samples[i].quality = validateAdcReading(raw, config->gpio, adc_max);
    }

    // Bubble-sort by raw value, then pick median.
    for (uint8_t i = 0; i < bounded_count - 1; i++) {
        for (uint8_t j = 0; j < bounded_count - 1 - i; j++) {
            if (samples[j].raw_value > samples[j + 1].raw_value) {
                AnalogSample tmp = samples[j];
                samples[j] = samples[j + 1];
                samples[j + 1] = tmp;
            }
        }
    }

    AnalogSample median = samples[bounded_count / 2];

    // AUT-726: Permanent per-read sanity check — NOT a warmup phase. raw==0 means
    // probe disconnected or short to GND. Distinct from boot transient raw=4095,
    // which is handled by analog_warmup_count_ gate (AUT-734 C2).
    // validateAdcReading() logs "suspect" but does NOT abort the publish path.
    if (median.raw_value == 0) {
        reading_out.valid = false;
        reading_out.error_message =
            "ADC raw=0: probe disconnected or short to GND "
            "(distinct from boot transient raw=4095; "
            "boot transient handled by analog_warmup_count_ gate)";
        reading_out.quality = "error";
        LOG_W(TAG, "SensorManager: Analog raw=0 on GPIO " + String(config->gpio) +
                   " (" + config->sensor_type + ") — skipping publish (AUT-726)");
        return false;
    }

    // AUT-734 C2: Analog probe warmup gate. raw_value != 0 is guaranteed by the
    // AUT-726 check above. Mirror of Ds18b20ReadingCounter: requires
    // ANALOG_WARMUP_MIN_SAMPLES (==OFFLINE_WARMUP_VALID_SAMPLES) consecutive
    // non-zero reads before populating ValueCache.
    // AUT-738 Fix A: Time settling gate added as AND condition. Both gates must
    // pass before the first value is published. The sample-count gate runs first;
    // if it passes, the time gate is checked next. Neither replaces the other.
    {
        ptrdiff_t slot = config - sensors_;
        if (slot >= 0 && static_cast<uint8_t>(slot) < MAX_SENSORS) {
            uint8_t s = static_cast<uint8_t>(slot);
            if (analog_warmup_count_[s] < ANALOG_WARMUP_MIN_SAMPLES) {
                analog_warmup_count_[s]++;
                if (analog_warmup_count_[s] < ANALOG_WARMUP_MIN_SAMPLES) {
                    LOG_I(TAG, "SensorManager: Analog warmup count=" +
                               String(analog_warmup_count_[s]) + "/" +
                               String(ANALOG_WARMUP_MIN_SAMPLES) + " GPIO " +
                               String(config->gpio) + " (" + config->sensor_type + ")");
                    reading_out.valid = false;
                    reading_out.error_message = "Analog warmup in progress";
                    return false;
                }
                LOG_I(TAG, "SensorManager: Analog warmup count=" +
                           String(ANALOG_WARMUP_MIN_SAMPLES) + "/" +
                           String(ANALOG_WARMUP_MIN_SAMPLES) +
                           " WARMUP COMPLETE GPIO " + String(config->gpio) +
                           " (" + config->sensor_type + ")");
            }
            // AUT-738 Fix A: Time gate — AND with sample-count gate above.
            unsigned long elapsed_ms = millis() - analog_settle_start_ms_;
            if (elapsed_ms < ANALOG_BOOT_SETTLE_MS) {
                LOG_I(TAG, "SensorManager: Analog boot-settle GPIO " + String(config->gpio) +
                           " (" + config->sensor_type + ") " +
                           String(elapsed_ms) + "/" + String(ANALOG_BOOT_SETTLE_MS) +
                           "ms — holding publish");
                reading_out.valid = false;
                reading_out.error_message = "Analog boot settling";
                return false;
            }
        }
    }

    // AUT-738 Fix B: Symmetric rail guard — sequentialized after the settling gate above.
    // raw<ANALOG_DISCONNECT_LOW_THRESHOLD: low-rail (extends AUT-726 raw==0, adds ADC tolerance).
    // raw>ANALOG_DISCONNECT_HIGH_THRESHOLD: high-rail (capacitive probe floating → positive rail).
    // Boot-Transient (raw≈4095) cannot reach this guard because the time gate above blocks it.
    // Rail-disconnect thresholds scale with the acquisition source resolution.
    // 16-bit ADS1115 values are ~8x the 12-bit counts, so the internal 50/4050
    // bounds are scaled to the 0..32767 range (≈400 / ≈32400).
    const uint32_t disconnect_low  = is_ads1115 ? 400U   : ANALOG_DISCONNECT_LOW_THRESHOLD;
    const uint32_t disconnect_high = is_ads1115 ? 32400U : ANALOG_DISCONNECT_HIGH_THRESHOLD;
    if (median.raw_value < disconnect_low ||
        median.raw_value > disconnect_high) {
        reading_out.valid = false;
        reading_out.error_message = "Rail disconnect: raw=" + String(median.raw_value);
        reading_out.quality = "error";
        LOG_W(TAG, "SensorManager: Analog rail disconnect GPIO " + String(config->gpio) +
                   " (" + config->sensor_type + ") raw=" + String(median.raw_value) +
                   " (AUT-738)");
        return false;
    }

    const float adc_stddev = computePopulationStdDev(raw_values, bounded_count);
    const float pct_threshold = static_cast<float>(median.raw_value) * 0.01f;
    const float stability_threshold = pct_threshold > 1.0f ? pct_threshold : 1.0f;
    const bool stable = adc_stddev <= stability_threshold;

    String server_sensor_type = getServerSensorType(config->sensor_type);
    LocalConversion conv = applyLocalConversion(server_sensor_type, median.raw_value);

    reading_out.gpio = config->gpio;
    reading_out.sensor_type = server_sensor_type;
    reading_out.subzone_id = config->subzone_id;
    reading_out.raw_value = median.raw_value;
    reading_out.processed_value = conv.value;
    reading_out.unit = conv.unit;
    reading_out.quality = String(median.quality);
    reading_out.timestamp = millis();
    reading_out.valid = true;
    reading_out.error_message = "";
    reading_out.i2c_address = config->i2c_address;
    reading_out.sample_count = bounded_count;
    reading_out.adc_stddev = adc_stddev;
    reading_out.stable = stable;
    reading_out.has_sampling_stats = bounded_count > 1;
    // Carry the acquisition source so the payload can report it as a diagnostic
    // discriminator (the server's authoritative source is the stored calibration).
    reading_out.adc_source = config->adc_source;
    reading_out.adc_channel = config->adc_channel;
    reading_out.pga_gain = config->pga_gain;

    config->last_raw_value = median.raw_value;
    config->last_reading = millis();

    LOG_I(TAG, "SensorManager: Analog median " + String(bounded_count) + " samples, raw=" +
               String(median.raw_value) + ", stddev=" + String(adc_stddev, 2) +
               ", stable=" + String(stable ? "true" : "false") +
               " (GPIO " + String(config->gpio) + ")");
    return true;
}

// ============================================
// PULSE COUNT MEASUREMENT (Flow sensors)
// ============================================
// Atomically reads and resets the ISR pulse counter for the given GPIO slot.
// raw_value = number of pulses accumulated since last publish.
// Server is responsible for converting pulse count to flow rate (L/min) using
// the configured pulses_per_liter factor. raw_mode = true (Server-Centric).
bool SensorManager::measurePulseCount(const SensorConfig* config, uint8_t slot_idx,
                                       SensorReading& reading_out) {
    // Resolve the ISR slot index for this GPIO
    uint8_t pulse_idx = 0xFF;
    for (uint8_t i = 0; i < s_pulse_sensor_count; i++) {
        if (s_pulse_gpios[i] == config->gpio) {
            pulse_idx = i;
            break;
        }
    }

    if (pulse_idx == 0xFF) {
        LOG_E(TAG, "SensorManager: No pulse ISR slot found for GPIO " + String(config->gpio) +
                  " (s_pulse_sensor_count=" + String(s_pulse_sensor_count) +
                  ") — ISR was never registered for this GPIO");
        reading_out.valid = false;
        reading_out.quality = "error";
        reading_out.error_message = "Pulse ISR slot not registered";
        return false;
    }

    // Atomically read and reset the pulse counter, recording the measurement window
    unsigned long now = millis();
    noInterrupts();
    uint32_t count                  = s_pulse_counts[pulse_idx];
    s_pulse_counts[pulse_idx]       = 0;
    unsigned long last_ms           = s_pulse_last_read_ms[pulse_idx];
    s_pulse_last_read_ms[pulse_idx] = now;
    interrupts();
    uint32_t window_ms = (uint32_t)(now - last_ms);

    String server_sensor_type = getServerSensorType(config->sensor_type);

    reading_out.gpio          = config->gpio;
    reading_out.sensor_type   = server_sensor_type.length() > 0 ? server_sensor_type : config->sensor_type;
    reading_out.subzone_id    = config->subzone_id;
    reading_out.raw_value     = count;
    reading_out.processed_value = static_cast<float>(count);
    reading_out.unit          = "pulses";
    reading_out.quality       = "good";
    reading_out.timestamp     = millis();
    reading_out.valid         = true;
    reading_out.error_message = "";
    reading_out.raw_mode      = true;
    reading_out.window_ms     = window_ms;
    reading_out.i2c_address   = 0;

    if (count == 0) {
        LOG_W(TAG, "SensorManager: Pulse count=0 GPIO=" + String(config->gpio) +
                  " slot=" + String(pulse_idx) +
                  " — no flow detected or ISR not firing (check wiring, pull-up, interrupt)");
    } else {
        LOG_I(TAG, "SensorManager: Pulse count=" + String(count) +
                  " GPIO=" + String(config->gpio) + " slot=" + String(pulse_idx));
    }
    return true;
}

// R20-P2: Internal measurement with known config (avoids GPIO-only re-lookup)
// Used by performAllMeasurements() which iterates sensors_[] directly
bool SensorManager::performMeasurementForConfig(SensorConfig* config, SensorReading& reading_out) {
    uint8_t gpio = config->gpio;

    // Read raw value based on sensor type (using registry for dynamic detection)
    uint32_t raw_value = 0;
    
    // Get sensor capability from registry
    const SensorCapability* capability = findSensorCapability(config->sensor_type);
    
    if (capability) {
        // Known sensor type - use capability information
        if (capability->is_i2c) {
            // I2C sensor - read from I2C bus
            uint8_t buffer[6] = {0};
            uint8_t device_addr = capability->i2c_address;
            
            // For SHT31, read 6 bytes (temp MSB, temp LSB, CRC, hum MSB, hum LSB, CRC)
            // For other I2C sensors, adjust buffer size as needed
            if (readRawI2C(gpio, device_addr, 0x00, buffer, 6)) {
                // Extract raw value based on sensor type
                // Defense-in-Depth: case-insensitive check
                String lower_type_check = config->sensor_type;
                lower_type_check.toLowerCase();
                if (lower_type_check.indexOf("sht31") >= 0) {
                    // SHT31: First 2 bytes are temperature (for temp sensor)
                    // For humidity, bytes 3-4 would be used (handled separately)
                    raw_value = (uint32_t)(buffer[0] << 8 | buffer[1]);
                } else {
                    // Generic I2C: Use first 2 bytes
                    raw_value = (uint32_t)(buffer[0] << 8 | buffer[1]);
                }
            } else {
                reading_out.valid = false;
                reading_out.error_message = "I2C read failed";
                return false;
            }
        } else if (capability->is_uart || isUartSensorConfig(*config, capability)) {
            if (config->uart_configured_at_ms != 0 &&
                (millis() - config->uart_configured_at_ms) < MHZ19_WARMUP_MS) {
                reading_out.valid = false;
                reading_out.error_message = "CO2 sensor warming up";
                reading_out.quality = "warming_up";
                LOG_D(TAG, "SensorManager: CO2 warmup (" +
                         String((MHZ19_WARMUP_MS - (millis() - config->uart_configured_at_ms)) / 1000) +
                         "s remaining)");
                return false;
            }
            if (!mhz19UartReader.begin(config->uart_rx_pin, config->uart_tx_pin, config->uart_baud)) {
                reading_out.valid = false;
                reading_out.error_message = "UART CO2 not initialized";
                return false;
            }
            uint16_t ppm = 0;
            if (!mhz19UartReader.readRawPpm(ppm)) {
                reading_out.valid = false;
                reading_out.error_message = "UART CO2 read failed";
                return false;
            }
            raw_value = static_cast<uint32_t>(ppm);
            reading_out.raw_mode = true;
            reading_out.quality = "good";
            LOG_D(TAG, "SensorManager: UART CO2 raw PPM=" + String(ppm) +
                     " (GPIO slot " + String(gpio) + ")");
        } else if (capability->is_digital) {
            uint32_t gpio_raw = readRawDigital(config->gpio);
            // Active-Low: LOW (0) = liquid detected → logical 1
            //             HIGH (1) = no liquid       → logical 0
            raw_value = (gpio_raw == 0) ? 1U : 0U;
            reading_out.raw_mode = true;
            reading_out.quality = "good";
            LOG_D(TAG, "SensorManager: Digital GPIO=" + String(config->gpio) +
                     " raw=" + String(gpio_raw) + " logical=" + String(raw_value));
        } else if (capability->is_pulse) {
            // Pulse-counting sensor (FS300A flow and compatible): delegate to dedicated method.
            ptrdiff_t slot_ptr = config - sensors_;
            uint8_t slot_idx = (slot_ptr >= 0 && slot_ptr < MAX_SENSORS)
                               ? static_cast<uint8_t>(slot_ptr)
                               : 0xFF;
            LOG_I(TAG, "SensorManager: Flow pulse measurement GPIO=" + String(config->gpio) +
                      " type=" + config->sensor_type +
                      " registered_pulse_sensors=" + String(s_pulse_sensor_count));
            return measurePulseCount(config, slot_idx, reading_out);
        } else {
            // Non-I2C sensor - check device type
            String device_type = String(capability->device_type);
            
            if (device_type == "ds18b20") {
                // ============================================
                // ONEWIRE SENSOR (DS18B20) - Enhanced with Retry + Sanity
                // ============================================
                
                // 1. Validate ROM-Code presence
                if (config->onewire_address.length() != 16) {
                    reading_out.valid = false;
                    reading_out.error_message = "OneWire ROM-Code missing or invalid length";
                    LOG_E(TAG, "SensorManager: DS18B20 ROM-Code missing for GPIO " + String(gpio));
                    errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_LENGTH, ERROR_SEVERITY_ERROR,
                                           "ROM-Code missing for measurement");
                    return false;
                }
                
                // 2. Parse ROM-Code
                uint8_t rom[8];
                if (!OneWireUtils::hexStringToRom(config->onewire_address, rom)) {
                    reading_out.valid = false;
                    reading_out.error_message = "OneWire ROM-Code parse failed";
                    LOG_E(TAG, "SensorManager: Failed to parse ROM-Code: " + config->onewire_address);
                    errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_FORMAT, ERROR_SEVERITY_ERROR,
                                           ("ROM parse failed: " + config->onewire_address).c_str());
                    return false;
                }
                
                // 3. Check OneWire bus status
                if (!onewire_bus_ || !onewire_bus_->isInitialized()) {
                    reading_out.valid = false;
                    reading_out.error_message = "OneWire bus not initialized";
                    LOG_E(TAG, "SensorManager: OneWire bus not ready for measurement");
                    errorTracker.trackError(ERROR_ONEWIRE_BUS_NOT_INITIALIZED, ERROR_SEVERITY_ERROR,
                                           "Bus not initialized for read");
                    return false;
                }
                
                // 4. Read RAW temperature with RETRY LOGIC (3 attempts, 100ms delay)
                int16_t raw_temp = 0;
                bool read_success = false;
                const uint8_t MAX_RETRIES = 3;
                const uint16_t RETRY_DELAY_MS = 100;
                
                for (uint8_t retry = 0; retry < MAX_RETRIES; retry++) {
                    if (readRawOneWire(gpio, rom, raw_temp)) {
                        read_success = true;
                        if (retry > 0) {
                            LOG_I(TAG, "SensorManager: OneWire read succeeded on attempt " + 
                                    String(retry + 1) + " for " + config->onewire_address);
                        }
                        break;
                    }
                    
                    if (retry < MAX_RETRIES - 1) {
                        LOG_W(TAG, "SensorManager: OneWire read attempt " + String(retry + 1) + 
                                   " failed for " + config->onewire_address + ", retrying...");
                        delay(RETRY_DELAY_MS);
                    }
                }
                
                if (!read_success) {
                    reading_out.valid = false;
                    reading_out.error_message = "OneWire read failed after " + String(MAX_RETRIES) + " attempts";
                    LOG_E(TAG, "SensorManager: OneWire read failed after " + String(MAX_RETRIES) +
                             " retries for device " + config->onewire_address + " on GPIO " + String(gpio));
                    errorTracker.trackError(ERROR_ONEWIRE_READ_TIMEOUT, ERROR_SEVERITY_ERROR,
                                           ("Read timeout: " + config->onewire_address).c_str());
                    return false;
                }

                // ============================================
                // 5. DS18B20 SPECIAL VALUE DETECTION (Defense-in-Depth)
                // ============================================
                // Track readings per sensor for power-on-reset detection
                uint32_t reading_count = getAndIncrementDs18b20ReadingCount(gpio, config->onewire_address);

                // 5a. SENSOR FAULT: -127°C (RAW = -2032)
                // This indicates: disconnected sensor, CRC failure, or bus error
                // CRITICAL: Do NOT publish this value - it's not a temperature!
                if (raw_temp == DS18B20_RAW_SENSOR_FAULT) {
                    LOG_E(TAG, "SensorManager: DS18B20 SENSOR FAULT detected: -127°C (GPIO " +
                              String(gpio) + ", ROM: " + config->onewire_address + ")");
                    LOG_E(TAG, "  → Possible causes: Sensor disconnected, CRC failure, bus wiring issue");

                    errorTracker.trackError(
                        ERROR_DS18B20_SENSOR_FAULT,
                        ERROR_SEVERITY_ERROR,
                        ("DS18B20 fault (-127°C) on GPIO " + String(gpio) +
                         " ROM " + config->onewire_address).c_str()
                    );

                    // Do NOT publish - error is reported via ErrorTracker (dedicated MQTT topic)
                    reading_out.valid = false;
                    reading_out.error_message = "DS18B20 sensor fault: -127°C (disconnected or CRC failure)";
                    reading_out.quality = "error";
                    return false;
                }

                // 5b. POWER-ON-RESET: 85°C (RAW = 1360) - ONLY on first reading
                // After power-up, DS18B20 reports 85°C until first conversion completes
                // CRITICAL: Only reject on FIRST reading; after that, 85°C could be real (fire!)
                if (raw_temp == DS18B20_RAW_POWER_ON_RESET && reading_count == 0) {
                    LOG_W(TAG, "SensorManager: DS18B20 power-on reset detected: 85°C (GPIO " +
                               String(gpio) + ", ROM: " + config->onewire_address + ")");
                    LOG_I(TAG, "  → First reading after boot - triggering retry with conversion delay...");

                    // Wait for conversion to complete (750ms for 12-bit resolution)
                    delay(100);  // Short delay, then retry

                    // Retry the read
                    int16_t retry_raw = 0;
                    if (readRawOneWire(gpio, rom, retry_raw)) {
                        if (retry_raw == DS18B20_RAW_POWER_ON_RESET) {
                            // Still 85°C after retry - accept it (could be fire or faulty sensor)
                            LOG_W(TAG, "SensorManager: DS18B20 still 85°C after retry - accepting as potentially valid");
                            raw_temp = retry_raw;
                            // Fall through to normal processing
                        } else if (retry_raw == DS18B20_RAW_SENSOR_FAULT) {
                            // Retry returned fault
                            LOG_E(TAG, "SensorManager: DS18B20 retry returned sensor fault (-127°C)");
                            errorTracker.trackError(
                                ERROR_DS18B20_SENSOR_FAULT,
                                ERROR_SEVERITY_ERROR,
                                ("DS18B20 fault after power-on retry on GPIO " + String(gpio)).c_str()
                            );
                            reading_out.valid = false;
                            reading_out.error_message = "DS18B20 sensor fault after power-on retry";
                            reading_out.quality = "error";
                            return false;
                        } else {
                            // Good value on retry
                            LOG_I(TAG, "SensorManager: DS18B20 retry successful: " +
                                    String(retry_raw * 0.0625) + "°C (was power-on 85°C)");
                            raw_temp = retry_raw;
                        }
                    } else {
                        // Retry read failed
                        LOG_E(TAG, "SensorManager: DS18B20 retry read failed after power-on reset");
                        errorTracker.trackError(
                            ERROR_DS18B20_POWER_ON_RESET,
                            ERROR_SEVERITY_WARNING,
                            ("DS18B20 power-on reset, retry failed on GPIO " + String(gpio)).c_str()
                        );
                        reading_out.valid = false;
                        reading_out.error_message = "DS18B20 retry failed after power-on reset";
                        reading_out.quality = "error";
                        return false;
                    }
                }

                // 5c. RANGE VALIDATION: Check datasheet limits (-55°C to +125°C)
                if (raw_temp < DS18B20_RAW_MIN_VALID || raw_temp > DS18B20_RAW_MAX_VALID) {
                    LOG_W(TAG, "SensorManager: DS18B20 raw value " + String(raw_temp) +
                               " (" + String(raw_temp * 0.0625) + "°C) out of datasheet range " +
                               "[" + String(DS18B20_RAW_MIN_VALID) + ", " + String(DS18B20_RAW_MAX_VALID) +
                               "] for " + config->onewire_address);

                    errorTracker.trackError(
                        ERROR_DS18B20_OUT_OF_RANGE,
                        ERROR_SEVERITY_WARNING,
                        ("DS18B20 out of range: " + String(raw_temp * 0.0625) + "°C").c_str()
                    );

                    reading_out.quality = "suspect";  // Server decides whether to use
                } else {
                    reading_out.quality = "good";
                }
                
                // 6. Store RAW value and metadata for MQTT payload
                raw_value = (uint32_t)raw_temp;
                reading_out.onewire_address = config->onewire_address;
                reading_out.raw_mode = true;  // Always true for DS18B20 (Server-Centric)
                
                LOG_D(TAG, "SensorManager: DS18B20 read: " + config->onewire_address + 
                         " = " + String(raw_temp) + " RAW (GPIO " + String(gpio) + 
                         ", quality=" + reading_out.quality + ")");
            } else {
                // Analog sensor (pH, EC, Moisture, etc.)
                if (isAnalogProbeSensorType(config->sensor_type)) {
                    return measureAnalogProbeMedian(config, reading_out);
                }
                raw_value = readRawAnalog(gpio);
                // E-P2: ADC quality check for analog sensors
                reading_out.quality = String(validateAdcReading(raw_value, gpio));
            }
        }
    } else {
        // Unknown sensor type - try to infer from sensor_type string
        String lower_type = config->sensor_type;
        lower_type.toLowerCase();
        
        if (lower_type.indexOf("ph") >= 0 || lower_type.indexOf("ec") >= 0 ||
            lower_type.indexOf("moisture") >= 0) {
            // Likely analog sensor
            if (isAnalogProbeSensorType(config->sensor_type)) {
                return measureAnalogProbeMedian(config, reading_out);
            }
            raw_value = readRawAnalog(gpio);
            // E-P2: ADC quality check
            reading_out.quality = String(validateAdcReading(raw_value, gpio));
        } else if (lower_type.indexOf("co2") >= 0 ||
                   config->interface_type.equalsIgnoreCase("UART")) {
            reading_out.valid = false;
            reading_out.error_message = "UART CO2 not configured";
            LOG_E(TAG, "SensorManager: CO2/UART sensor without UART config on GPIO " + String(gpio));
            return false;
        } else if (lower_type.indexOf("ds18b20") >= 0 || lower_type.indexOf("onewire") >= 0) {
            // Likely OneWire sensor - use ROM-Code from config
            if (config->onewire_address.length() != 16) {
                reading_out.valid = false;
                reading_out.error_message = "OneWire ROM-Code missing";
                LOG_E(TAG, "SensorManager: DS18B20 ROM-Code missing (fallback path)");
                return false;
            }
            
            uint8_t rom[8];
            if (!OneWireUtils::hexStringToRom(config->onewire_address, rom)) {
                reading_out.valid = false;
                reading_out.error_message = "OneWire ROM-Code parse failed";
                return false;
            }
            
            int16_t raw_temp = 0;
            if (readRawOneWire(gpio, rom, raw_temp)) {
                raw_value = (uint32_t)raw_temp;
                reading_out.onewire_address = config->onewire_address;
            } else {
                reading_out.valid = false;
                reading_out.error_message = "OneWire read failed";
                return false;
            }
        } else if (lower_type.indexOf("i2c") >= 0 || lower_type.indexOf("sht") >= 0 || 
                   lower_type.indexOf("bmp") >= 0) {
            // Likely I2C sensor - try default address
            uint8_t buffer[6] = {0};
            uint8_t device_addr = getI2CAddress(lower_type, 0x44);  // Default to SHT31 address
            if (readRawI2C(gpio, device_addr, 0x00, buffer, 6)) {
                raw_value = (uint32_t)(buffer[0] << 8 | buffer[1]);
            } else {
                reading_out.valid = false;
                reading_out.error_message = "I2C read failed";
                return false;
            }
        } else {
            // Fallback: try analog
            raw_value = readRawAnalog(gpio);
            // E-P2: ADC quality check
            reading_out.quality = String(validateAdcReading(raw_value, gpio));
        }
    }
    
    // Normalize sensor type for server (ESP32 → Server Processor)
    String server_sensor_type = getServerSensorType(config->sensor_type);

    // Apply local conversion for human-readable MQTT payload preview
    // Server re-processes the raw value with its full sensor library
    LocalConversion conv = applyLocalConversion(server_sensor_type, raw_value);

    LOG_D(TAG, "Local conversion: " + server_sensor_type + " raw=" +
              String(raw_value) + " → " + String(conv.value) + " " + conv.unit);

    // Fill reading output (use normalized sensor type)
    reading_out.gpio = gpio;
    reading_out.sensor_type = server_sensor_type;
    reading_out.subzone_id = config->subzone_id;
    reading_out.raw_value = raw_value;
    reading_out.processed_value = conv.value;
    reading_out.unit = conv.unit;
    // Keep quality from raw-path validators (e.g. ADC near-rail -> suspect).
    if (reading_out.quality.length() == 0) {
        reading_out.quality = "good";
    }
    reading_out.timestamp = millis();
    reading_out.valid = true;
    reading_out.error_message = "";
    reading_out.i2c_address = config->i2c_address;

    // Update config
    config->last_raw_value = raw_value;
    config->last_reading = millis();

    return true;
}

// ============================================
// MULTI-VALUE SENSOR MEASUREMENT (PHASE 5)
// ============================================
uint8_t SensorManager::performMultiValueMeasurement(uint8_t gpio, SensorReading* readings_out, uint8_t max_readings) {
    if (!initialized_ || readings_out == nullptr || max_readings == 0) {
        return 0;
    }
    
    // Find sensor config
    SensorConfig* config = findSensorConfig(gpio);
    if (!config || !config->active) {
        LOG_W(TAG, "Sensor Manager: Sensor on GPIO " + String(gpio) + " not found or inactive");
        return 0;
    }
    
    // Get sensor capability
    const SensorCapability* capability = findSensorCapability(config->sensor_type);
    if (!capability || !capability->is_multi_value) {
        LOG_W(TAG, "Sensor Manager: Sensor on GPIO " + String(gpio) + " is not a multi-value sensor");
        return 0;
    }
    
    // Get device type and all value types
    String device_type = String(capability->device_type);
    String value_types[4];
    uint8_t value_count = getMultiValueTypes(device_type, value_types, 4);
    
    if (value_count == 0 || value_count > max_readings) {
        LOG_E(TAG, "Sensor Manager: Invalid value count for multi-value sensor");
        return 0;
    }
    
    // Read raw data from sensor (I2C for SHT31/BMP280)
    if (!capability->is_i2c) {
        LOG_E(TAG, "Sensor Manager: Multi-value sensor must be I2C");
        return 0;
    }

    // ============================================
    // UNIFIED I2C MULTI-VALUE SENSOR READING
    // ============================================
    // Uses protocol-aware readSensorRaw() for all I2C sensors
    // Protocol selection is automatic based on device_type
    // One I2C read for ALL values (no duplicate transactions)
    uint8_t buffer[16] = {0};  // Buffer for multi-value sensors (up to 8 bytes for BME280)
    // Use config->i2c_address (stored at configure-time from MQTT payload) so that
    // two SHT31 sensors at 0x44 and 0x45 each read from their correct physical device.
    uint8_t device_addr = config->i2c_address;
    size_t bytes_read = 0;

    LOG_D(TAG, "SensorManager: I2C READ START for " + device_type + " addr=0x" + String(device_addr, HEX));
    if (!i2c_bus_->readSensorRaw(device_type, device_addr, buffer, sizeof(buffer), bytes_read)) {
        LOG_E(TAG, "Sensor Manager: I2C read failed for " + device_type);
        return 0;
    }
    LOG_D(TAG, "SensorManager: I2C READ COMPLETE, bytes=" + String(bytes_read));

    LOG_D(TAG, "Sensor Manager: " + device_type + " raw data (" + String(bytes_read) + " bytes): " +
              String(buffer[0], HEX) + " " + String(buffer[1], HEX) + " " +
              String(buffer[2], HEX) + " " + String(buffer[3], HEX) + " " +
              String(buffer[4], HEX) + " " + String(buffer[5], HEX));
    
    // Create readings for each value type
    uint8_t created_count = 0;
    
    for (uint8_t i = 0; i < value_count; i++) {
        SensorReading& reading = readings_out[created_count];
        
        // Extract raw value using protocol definition
        // This uses the I2CSensorProtocol registry to correctly parse
        // multi-value sensor responses based on byte offsets and endianness
        String value_type = value_types[i];
        uint32_t raw_value = extractRawValue(device_type, value_type, buffer, bytes_read);
        
        // Normalize sensor type
        String server_sensor_type = getServerSensorType(value_type);

        // Apply local conversion for human-readable MQTT payload preview
        LocalConversion conv = applyLocalConversion(server_sensor_type, raw_value);

        LOG_D(TAG, "Local conversion: " + server_sensor_type + " raw=" +
                  String(raw_value) + " → " + String(conv.value) + " " + conv.unit);

        // Fill reading output
        reading.gpio = gpio;
        reading.sensor_type = server_sensor_type;
        reading.subzone_id = config->subzone_id;
        reading.raw_value = raw_value;
        reading.processed_value = conv.value;
        reading.unit = conv.unit;
        reading.quality = "good";
        reading.timestamp = millis();
        reading.valid = true;
        reading.error_message = "";
        reading.i2c_address = config->i2c_address;

        bool success = true;
        if (success) {
            created_count++;

            // Publish reading via MQTT
            LOG_D(TAG, "SensorManager: MQTT PUBLISH for " + server_sensor_type);
            publishSensorReading(reading);
        } else {
            LOG_W(TAG, "SensorManager: Skipping publish for " + server_sensor_type);
        }
    }

    // Update config
    config->last_raw_value = readings_out[0].raw_value;  // Use first reading
    config->last_reading = millis();

    LOG_D(TAG, "SensorManager: MULTI-VALUE COMPLETE, created " + String(created_count) + " readings");

    return created_count;
}

// Server-Centric Deviation (Autonomous Measurement Pattern):
// ESP32 misst periodisch autonom (standard in Industrial IoT wie AWS Greengrass, Azure IoT Edge).
// Begründung: Minimiert MQTT-Traffic, Server-Control via measurement_interval Config.
// Dokumentiert in: docs/ZZZ.md - "Server-Centric Pragmatic Deviations"
void SensorManager::performAllMeasurements() {
    if (!initialized_) {
        return;
    }
    // SAFETY-RTOS M4: protect sensors_[] against configureSensor (Core 0 pre-M4.6 path)
    // and future callers. Both paths are on Core 1 after M4.6, mutex is defense-in-depth.
    xSemaphoreTake(g_sensor_mutex, portMAX_DELAY);

    // No sensors configured - nothing to do
    if (sensor_count_ == 0) {
        xSemaphoreGive(g_sensor_mutex);
        return;
    }

    LOG_D(TAG, "SensorManager::performAllMeasurements() ENTER, sensor_count=" + String(sensor_count_));

    unsigned long now = millis();

    // I2C multi-value dedup: Track already-measured I2C addresses per cycle.
    // Multi-value sensors (SHT31, BMP280, BME280) are stored as separate configs
    // (e.g. sht31_temp + sht31_humidity) but share one I2C address. Without dedup,
    // performMultiValueMeasurement() would be called once per config, causing
    // duplicate I2C reads and duplicate MQTT publishes.
    uint8_t measured_i2c_addrs[MAX_SENSORS];
    uint8_t measured_i2c_count = 0;

    // ✅ Phase 2C: Pro-Sensor Iteration with Mode-Check
    // (Removed global interval check - each sensor has its own interval)
    for (uint8_t i = 0; i < sensor_count_; i++) {
        LOG_D(TAG, "SensorManager: Processing sensor[" + String(i) + "] GPIO=" + String(sensors_[i].gpio) + " type=" + sensors_[i].sensor_type);
        // Check 1: Sensor must be active
        if (!sensors_[i].active) {
            continue;
        }

        // ✅ Phase 2C: Check 2: Operating Mode
        const String& mode = sensors_[i].operating_mode;

        if (mode == "paused") {
            // Paused sensors are never measured automatically
            continue;
        }

        if (mode == "on_demand") {
            // On-demand sensors are only measured via command
            continue;
        }

        if (mode == "scheduled") {
            // Scheduled sensors are measured via server command (Phase 2D)
            continue;
        }

        // ✅ F7: Circuit Breaker Guard — skip disabled sensors
        if (sensors_[i].cb_state == SensorCBState::OPEN) {
            uint32_t elapsed = now - sensors_[i].cb_open_since_ms;
            if (elapsed < CB_PROBE_INTERVAL_MS) {
                continue;  // Sensor disabled — skip
            }
            // Probe interval elapsed — transition to HALF_OPEN
            sensors_[i].cb_state = SensorCBState::HALF_OPEN;
            LOG_I(TAG, "Sensor " + sensors_[i].sensor_type +
                       ": Circuit Breaker HALF_OPEN — probing");
        }

        // ✅ Phase 2C: Check 3: Pro-Sensor Interval
        uint32_t sensor_interval = sensors_[i].measurement_interval_ms;
        if (sensor_interval == 0) {
            sensor_interval = measurement_interval_;  // Fallback to global interval
        }

        // Check if enough time has passed since last measurement.
        // AUT-676: boot stagger — sensor index i adds i*5s to required interval when
        // last_reading==0 (never measured). Spreads first-cycle publishes non-blockingly.
        // Self-cancelling: once last_reading is set (line 1733), stagger no longer applies.
        {
            uint32_t effective_interval = sensor_interval;
            if (sensors_[i].last_reading == 0) {
                effective_interval += (uint32_t)i * SENSOR_BOOT_STAGGER_MS;
            }
            if (now - sensors_[i].last_reading < effective_interval) {
                continue;
            }
        }

        // ✅ Continuous Mode: Perform measurement
        // Check if this is a multi-value sensor
        const SensorCapability* capability = findSensorCapability(sensors_[i].sensor_type);
        LOG_D(TAG, "SensorManager: sensor[" + String(i) + "] is_multi_value=" + String(capability && capability->is_multi_value ? "YES" : "NO"));

        // B1 FIX: Update last_reading BEFORE measurement attempt.
        // On failure, this prevents immediate retry (flood). The sensor
        // waits its full interval before the next attempt (backoff).
        sensors_[i].last_reading = now;

        bool measurement_ok = false;
        bool skip_cb_for_warmup = false;

        if (capability && capability->is_multi_value) {
            // I2C dedup: Skip if this exact I2C address was already measured this cycle.
            // Multi-value sensors (SHT31, BMP280, BME280) are stored as separate configs
            // (sht31_temp + sht31_humidity) but share one physical I2C address.
            // Use sensors_[i].i2c_address (stored at configure-time from MQTT payload)
            // so that two SHT31 at 0x44 and 0x45 are NOT considered duplicates of each other.
            uint8_t addr = sensors_[i].i2c_address;
            bool already_measured = false;
            for (uint8_t j = 0; j < measured_i2c_count; j++) {
                if (measured_i2c_addrs[j] == addr) {
                    already_measured = true;
                    break;
                }
            }

            if (already_measured) {
                LOG_D(TAG, "SensorManager: Skipping duplicate I2C 0x" +
                      String(addr, HEX) + " for " + sensors_[i].sensor_type +
                      " (already measured this cycle)");
                continue;  // last_reading already updated above
            }

            // Multi-value sensor - create multiple readings
            LOG_D(TAG, "SensorManager: MULTI-VALUE measurement START GPIO=" + String(sensors_[i].gpio));
            SensorReading readings[4];  // Max 4 values per sensor
            uint8_t count = performMultiValueMeasurement(sensors_[i].gpio, readings, 4);
            LOG_D(TAG, "SensorManager: MULTI-VALUE measurement END count=" + String(count));

            // Track this I2C address as measured
            measured_i2c_addrs[measured_i2c_count++] = addr;

            measurement_ok = (count > 0);
            if (!measurement_ok) {
                LOG_W(TAG, "Sensor Manager: Multi-value measurement failed for GPIO " + String(sensors_[i].gpio));
            }
        } else {
            // Single-value sensor - standard measurement
            // R20-P2: Use config-based method to avoid GPIO-only lookup (multi-sensor GPIO)
            LOG_D(TAG, "SensorManager: SINGLE-VALUE measurement START GPIO=" + String(sensors_[i].gpio));
            SensorReading reading;
            if (performMeasurementForConfig(&sensors_[i], reading)) {
                LOG_D(TAG, "SensorManager: SINGLE-VALUE measurement OK, publishing");
                publishSensorReading(reading);
                measurement_ok = true;
            } else {
                LOG_D(TAG, "SensorManager: SINGLE-VALUE measurement FAILED");
                if (reading.quality == "warming_up") {
                    skip_cb_for_warmup = true;
                }
            }
        }

        // ✅ F7: Circuit Breaker State Transitions
        if (measurement_ok) {
            if (sensors_[i].cb_state != SensorCBState::CLOSED) {
                LOG_I(TAG, "Sensor " + sensors_[i].sensor_type +
                           ": Circuit Breaker CLOSED — sensor recovered");
                sensors_[i].cb_state = SensorCBState::CLOSED;
            }
            sensors_[i].consecutive_failures = 0;
        } else if (!skip_cb_for_warmup) {
            sensors_[i].consecutive_failures++;

            if (sensors_[i].cb_state == SensorCBState::HALF_OPEN) {
                // Probe failed — back to OPEN
                sensors_[i].cb_state = SensorCBState::OPEN;
                sensors_[i].cb_open_since_ms = now;
                LOG_W(TAG, "Sensor " + sensors_[i].sensor_type +
                           ": Circuit Breaker OPEN — probe failed, retry in " +
                           String(CB_PROBE_INTERVAL_MS / 1000) + "s");
            } else if (sensors_[i].consecutive_failures >= CB_MAX_CONSECUTIVE_FAILURES) {
                // Threshold exceeded — transition to OPEN
                sensors_[i].cb_state = SensorCBState::OPEN;
                sensors_[i].cb_open_since_ms = now;
                LOG_W(TAG, "Sensor " + sensors_[i].sensor_type +
                           ": Circuit Breaker OPEN — " +
                           String(sensors_[i].consecutive_failures) +
                           " consecutive failures, retry in " +
                           String(CB_PROBE_INTERVAL_MS / 1000) + "s");
            }
        }

        // Cooperative safety slice between sensors (emergency + actuator queue).
        feedWatchdog("SENSOR_LOOP");
        runSafetyCooperativeSlice();
    }

    // Update global timestamp for compatibility
    last_measurement_time_ = now;
    LOG_D(TAG, "SensorManager::performAllMeasurements() EXIT");
    xSemaphoreGive(g_sensor_mutex);
}

// ============================================
// MEASUREMENT INTERVAL CONFIGURATION (PHASE 2)
// ============================================
void SensorManager::setMeasurementInterval(unsigned long interval_ms) {
    measurement_interval_ = interval_ms;
    LOG_I(TAG, "Measurement interval set to " + String(interval_ms) + " ms");
}

// ============================================
// MANUAL MEASUREMENT (PHASE 2C - On-Demand)
// ============================================
ManualMeasurementResult SensorManager::triggerManualMeasurement(uint8_t gpio, uint32_t timeout_ms,
                                                                uint8_t sample_count,
                                                                uint16_t sample_delay_ms) {
    ManualMeasurementResult result;
    result.reason_code = "UNKNOWN";

    if (!initialized_) {
        LOG_E(TAG, "SensorManager: Not initialized, cannot trigger manual measurement");
        result.reason_code = "NOT_INITIALIZED";
        return result;
    }

    // Find sensor configuration
    SensorConfig* config = findSensorConfig(gpio);
    if (!config) {
        LOG_E(TAG, "SensorManager: Sensor not found on GPIO " + String(gpio));
        result.reason_code = "SENSOR_NOT_FOUND";
        return result;
    }

    // Check if sensor is active
    if (!config->active) {
        LOG_W(TAG, "SensorManager: Cannot measure inactive sensor on GPIO " + String(gpio));
        result.reason_code = "SENSOR_INACTIVE";
        return result;
    }

    // AUT-303: Busy-flag guard — reject duplicate measure commands for the same GPIO
    // while a measurement is already in progress. Prevents publish-queue overflow
    // (8 slots) when the UI triggers multiple back-to-back measure requests.
    ptrdiff_t sensor_index = config - sensors_;
    if (manual_measure_busy_[sensor_index]) {
        LOG_W(TAG, "SensorManager: GPIO " + String(gpio) +
                       " already measuring — ignoring duplicate trigger (AUT-303)");
        result.reason_code = "SENSOR_BUSY";
        return result;
    }
    manual_measure_busy_[sensor_index] = true;

    // E-P3: Log Circuit-Breaker state for manual override awareness
    if (config->cb_state == SensorCBState::OPEN) {
        LOG_I(TAG, "SensorManager: Note: Sensor CB is OPEN on GPIO " + String(gpio) +
                 " but proceeding (manual override)");
    }

    LOG_I(TAG, "SensorManager: Manual measurement triggered for GPIO " + String(gpio) +
             " (mode: " + config->operating_mode + ", timeout: " + String(timeout_ms) + "ms)");
    result.sensor_type = config->sensor_type;

    {
        SensorArrayMutexLock sensor_lock;
        if (!sensor_lock.tryTake(kManualSensorMutexWaitMs)) {
            LOG_W(TAG, "SensorManager: g_sensor_mutex not acquired within " +
                           String(kManualSensorMutexWaitMs) + "ms — manual measurement aborted (GPIO " +
                           String(gpio) + ")");
            result.reason_code = "MUTEX_TIMEOUT";
            manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
            return result;
        }

        unsigned long start_ms = millis();

        // Check if this is a multi-value sensor
        const SensorCapability* capability = findSensorCapability(config->sensor_type);

        if (capability && capability->is_multi_value) {
            // Multi-value sensor - create multiple readings
            SensorReading readings[4];  // Max 4 values per sensor
            uint8_t count = performMultiValueMeasurement(gpio, readings, 4);

            // E-P3: Timeout-Guard — check elapsed time after measurement
            unsigned long elapsed = millis() - start_ms;
            if (elapsed > timeout_ms) {
                result.timeout_reached = true;
                LOG_W(TAG, "SensorManager: Manual measurement TIMEOUT on GPIO " + String(gpio) +
                         " (elapsed: " + String(elapsed) + "ms, limit: " + String(timeout_ms) + "ms)");
                errorTracker.trackError(ERROR_SENSOR_TIMEOUT, ERROR_SEVERITY_WARNING,
                                       "Manual measurement exceeded timeout");
            }

            if (count == 0) {
                LOG_E(TAG, "SensorManager: Manual multi-value measurement failed for GPIO " + String(gpio));
                result.reason_code = result.timeout_reached ? "MEASURE_TIMEOUT" : "MEASUREMENT_FAILED";
                result.measurement_ok = false;
                result.publish_ok = false;
                manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
                return result;
            }

            result.measurement_ok = true;
            result.publish_ok = mqtt_client_ && mqtt_client_->isConnected() && mqtt_client_->isRegistrationConfirmed();
            result.reason_code = result.timeout_reached ? "MEASURE_TIMEOUT" : (result.publish_ok ? "NONE" : "PUBLISH_SKIPPED");
            result.quality = "good";
            result.raw_value = static_cast<int32_t>(readings[0].raw_value);
            config->last_reading = start_ms;
            manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
            return result;
        }

        // Single-value sensor
        SensorReading reading;
        if (isAnalogProbeSensorType(config->sensor_type)) {
            // AUT-441: Continuous and manual paths share exactly one median implementation.
            if (!measureAnalogProbeMedian(config, reading, sample_count, sample_delay_ms)) {
                LOG_E(TAG, "SensorManager: Manual analog median measurement failed for GPIO " + String(gpio));
                result.reason_code = "MEASUREMENT_FAILED";
                manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
                return result;
            }
        } else {
            if (!performMeasurement(gpio, reading)) {
                LOG_E(TAG, "SensorManager: Manual measurement failed for GPIO " + String(gpio));
                result.reason_code = "MEASUREMENT_FAILED";
                manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
                return result;
            }
        }

        // E-P3: Timeout-Guard — check elapsed time after measurement
        unsigned long elapsed = millis() - start_ms;
        if (elapsed > timeout_ms) {
            result.timeout_reached = true;
            LOG_W(TAG, "SensorManager: Manual measurement TIMEOUT on GPIO " + String(gpio) +
                     " (elapsed: " + String(elapsed) + "ms, limit: " + String(timeout_ms) + "ms)");
            errorTracker.trackError(ERROR_SENSOR_TIMEOUT, ERROR_SEVERITY_WARNING,
                                   "Manual measurement exceeded timeout");
        }

        bool publish_ok = publishSensorReading(reading);
        result.measurement_ok = true;
        result.publish_ok = publish_ok;
        result.quality = reading.quality;
        result.raw_value = static_cast<int32_t>(reading.raw_value);
        result.sensor_type = reading.sensor_type;
        result.sample_count = reading.sample_count;
        result.adc_stddev = reading.adc_stddev;
        result.stable = reading.stable;
        result.has_sampling_stats = reading.has_sampling_stats;
        if (result.timeout_reached) {
            result.reason_code = "MEASURE_TIMEOUT";
        } else if (!publish_ok) {
            result.reason_code = "PUBLISH_SKIPPED";
        } else {
            result.reason_code = "NONE";
        }
        config->last_reading = start_ms;
        manual_measure_busy_[sensor_index] = false;  // AUT-303: release busy flag
        return result;
    }
}

// ============================================
// RAW DATA READING METHODS (PHASE 4)
// ============================================
// RAW DATA READING METHODS (PHASE 4)
// ============================================
uint32_t SensorManager::readRawAnalog(uint8_t gpio) {
    if (!initialized_) {
        return 0;
    }

    // Defense-in-depth: gpio=0 is the I2C bus convention, never a valid analog pin.
    // Catches sensors stored in NVS from before the configureSensor() guard was added.
    if (gpio == 0) {
        LOG_E(TAG, "readRawAnalog: GPIO 0 rejected (boot strap pin, I2C bus convention)");
        return 0;
    }

    // ADC2/WiFi conflict check: ADC2 pins cannot be used for analog reads when WiFi is active
    // ESP32 hardware limitation - ADC2 peripheral is shared with WiFi radio
    if (gpio_manager_->isADC2Pin(gpio)) {
        if (WiFi.isConnected() || WiFi.getMode() != WIFI_OFF) {
            LOG_E(TAG, "GPIO " + String(gpio) + " is on ADC2 - cannot read while WiFi is active! Use ADC1 pins (GPIO32-39) for analog sensors");
            return 0;
        }
    }

    // Configure pin as analog input if needed
    gpio_manager_->configurePinMode(gpio, INPUT);
    analogSetPinAttenuation(gpio, ADC_11db);  // Safety-Net: 100-3100mV range for all analog sensors

    // Read analog value (ESP32: 0-4095)
    return analogRead(gpio);
}

// E-P2: ADC Validation — classify raw ADC reading quality
// Returns "good", "suspect", or "error" quality string for MQTT payload.
// Server uses this to decide whether to accept the raw value for calibration.
// adc_max scales the rail/near-rail bounds: 4095 (internal 12-bit) or
// 32767 (ADS1115 16-bit external ADC).
const char* SensorManager::validateAdcReading(uint32_t raw, uint8_t gpio, uint32_t adc_max) {
    // Near-rail margin scales with resolution (~1.2% of full scale, matching the
    // 50/4095 internal heuristic ≈ 400/32767 for the ADS1115).
    const uint32_t near_margin = (adc_max > 4095) ? 400U : 50U;

    // Hard bounds: exact rail values indicate disconnected sensor or saturation
    if (raw == 0 || raw == adc_max) {
        LOG_W(TAG, "ADC rail on GPIO " + String(gpio) + ": raw=" + String(raw) + " (disconnected or saturated)");
        return "suspect";
    }

    // Near-rail zone (ADC noise floor / ceiling): flagged for operator awareness
    if (raw < near_margin || raw > (adc_max - near_margin)) {
        LOG_I(TAG, "ADC near-rail on GPIO " + String(gpio) + ": raw=" + String(raw) + " (close to ADC boundary)");
        return "suspect";
    }

    return "good";
}

// Dispatch a single RAW analog-probe read based on the sensor's acquisition
// source. Internal ADC stays the default; ADS1115 reuses the existing I2C bus.
uint32_t SensorManager::acquireProbeRaw(SensorConfig* config) {
    if (!config) {
        return 0;
    }
    if (config->adc_source == AdcSourceCode::ADS1115) {
        if (!i2c_bus_) {
            LOG_E(TAG, "acquireProbeRaw: ADS1115 requested but I2C bus unavailable");
            return 0;
        }
        uint16_t raw16 = 0;
        if (i2c_bus_->readAds1115SingleEnded(config->i2c_address, config->adc_channel,
                                             config->pga_gain, raw16)) {
            return static_cast<uint32_t>(raw16);
        }
        // Failure (NACK/timeout) -> 0 so the median path marks it suspect/disconnect
        // and the last valid value is retained (no crash/reboot).
        return 0;
    }
    return readRawAnalog(config->gpio);
}

uint32_t SensorManager::readRawDigital(uint8_t gpio) {
    if (!initialized_) {
        return 0;
    }
    
    // Configure pin as digital input if needed
    gpio_manager_->configurePinMode(gpio, INPUT_PULLUP);
    
    // Read digital value
    return digitalRead(gpio);
}

bool SensorManager::readRawI2C(uint8_t gpio, uint8_t device_address, 
                                uint8_t reg, uint8_t* buffer, size_t len) {
    if (!initialized_ || !i2c_bus_) {
        return false;
    }
    
    // Use I2C bus manager
    return i2c_bus_->readRaw(device_address, reg, buffer, len);
}

bool SensorManager::readRawOneWire(uint8_t gpio, const uint8_t rom[8], int16_t& raw_value) {
    if (!initialized_ || !onewire_bus_) {
        LOG_E(TAG, "SensorManager: Not initialized or OneWire bus missing");
        return false;
    }
    
    // Verify OneWire bus is initialized
    if (!onewire_bus_->isInitialized()) {
        LOG_E(TAG, "SensorManager: OneWire bus not initialized");
        return false;
    }
    
    // Verify GPIO matches bus pin (safety check)
    if (onewire_bus_->getPin() != gpio) {
        LOG_E(TAG, "SensorManager: OneWire bus on GPIO " + String(onewire_bus_->getPin()) + 
                 ", requested GPIO " + String(gpio));
        return false;
    }
    
    // Read RAW temperature from device
    if (!onewire_bus_->readRawTemperature(rom, raw_value)) {
        LOG_W(TAG, "SensorManager: Failed to read OneWire device " + 
                   OneWireUtils::romToHexString(rom));
        return false;
    }
    
    return true;
}

// ============================================
// STATUS QUERIES
// ============================================
String SensorManager::getSensorInfo(uint8_t gpio) const {
    const SensorConfig* config = findSensorConfig(gpio);
    if (!config) {
        return "Sensor not found";
    }
    
    String info;
    info.reserve(128);
    info = "GPIO: " + String(config->gpio) + ", Type: " + config->sensor_type + 
           ", Name: " + config->sensor_name + ", Active: " + String(config->active ? "Yes" : "No");
    return info;
}

// ============================================
// HELPER METHODS
// ============================================
SensorConfig* SensorManager::findSensorConfig(uint8_t gpio,
    const String& onewire_address, uint8_t i2c_address,
    const String& sensor_type) {
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].gpio != gpio) continue;

        // OneWire: additionally match ROM-Code
        if (onewire_address.length() > 0) {
            if (sensors_[i].onewire_address != onewire_address) continue;
        }

        // I2C: additionally match device address
        if (i2c_address > 0) {
            if (sensors_[i].i2c_address != i2c_address) continue;
        }

        // I2C multi-value sensors (e.g. SHT31): additionally match sensor_type so that
        // sht31_temp and sht31_humidity (same GPIO + same address) are not confused.
        if (sensor_type.length() > 0) {
            if (sensors_[i].sensor_type != sensor_type) continue;
        }

        return &sensors_[i];
    }
    return nullptr;
}

const SensorConfig* SensorManager::findSensorConfig(uint8_t gpio,
    const String& onewire_address, uint8_t i2c_address,
    const String& sensor_type) const {
    for (uint8_t i = 0; i < sensor_count_; i++) {
        if (sensors_[i].gpio != gpio) continue;

        // OneWire: additionally match ROM-Code
        if (onewire_address.length() > 0) {
            if (sensors_[i].onewire_address != onewire_address) continue;
        }

        // I2C: additionally match device address
        if (i2c_address > 0) {
            if (sensors_[i].i2c_address != i2c_address) continue;
        }

        // I2C multi-value sensors (e.g. SHT31): additionally match sensor_type so that
        // sht31_temp and sht31_humidity (same GPIO + same address) are not confused.
        if (sensor_type.length() > 0) {
            if (sensors_[i].sensor_type != sensor_type) continue;
        }

        return &sensors_[i];
    }
    return nullptr;
}

bool SensorManager::publishSensorReading(const SensorReading& reading) {
    // SAFETY-P4: Always update value cache regardless of MQTT connectivity
    updateValueCache(reading.gpio, reading.sensor_type.c_str(), reading.processed_value);

    // AUT-714: Spool reading when MQTT is not available
    if (spoolManager.isEnabled() && (!mqtt_client_ || !mqtt_client_->isConnected())) {
        spoolManager.append(reading);
    }

    if (!mqtt_client_ || !mqtt_client_->isConnected()) {
        LOG_W(TAG, "Sensor Manager: MQTT not connected, skipping publish");
        return false;
    }

    // Registration gate is intentionally fail-closed until heartbeat ACK arrives.
    // Before ACK, sensor publishes are expected to be blocked and should not be
    // treated as communication errors.
    if (!mqtt_client_->isRegistrationConfirmed()) {
        LOG_W(TAG, "Sensor Manager: Registration pending (no heartbeat ACK), skipping publish");
        return false;
    }

    // Copy topic immediately — topic_buffer_ is shared static; another task could
    // overwrite it between the build call and the publish call (FreeRTOS preemption).
    String topic = String(TopicBuilder::buildSensorDataTopic(reading.gpio));

    // Build payload
    String payload = buildMQTTPayload(reading);

    // AUT-555: QoS-adaptive publish.
    //
    // publish_qos is set per sensor in SensorConfig by the server at config-push time.
    // The server marks a sensor QoS-1 if it appears as a trigger in any enabled
    // cross_esp_logic rule. All other sensors stay QoS-0 (AUT-54: fire-and-forget,
    // tolerates loss because the next reading arrives within measurement_interval_ms).
    //
    // Why sensor_type in the lookup (not just gpio):
    //   I2C multi-value sensors like SHT31 produce two distinct readings on the same
    //   GPIO — sht31_temp and sht31_humidity — each stored as a separate SensorConfig
    //   entry. A rule might use humidity but not temperature. Passing sensor_type ensures
    //   we pick the correct SensorConfig and therefore the correct publish_qos.
    //   (findSensorConfig with sensor_type="" would return whichever entry was stored
    //    first, which may have a different publish_qos than the one we're publishing.)
    //
    // Fallback: if no SensorConfig is found for this GPIO+sensor_type (shouldn't happen
    //   in normal operation), we default to QoS-0 to avoid unexpected OUTBOX growth.
    const SensorConfig* sensor_cfg = findSensorConfig(reading.gpio, "", 0, reading.sensor_type);
    const uint8_t qos = (sensor_cfg != nullptr && sensor_cfg->publish_qos > 0) ? 1 : 0;
    if (!mqtt_client_->publish(topic, payload, qos)) {
        const char* reason_class = mqtt_client_->getLastPublishFailureReasonClassName();
        LOG_E(TAG, "Sensor Manager: Failed to publish sensor data for GPIO " +
                   String(reading.gpio) + " reason=" + String(reason_class));

        ErrorMqttContext context;
        context.topic = topic.c_str();
        context.gpio = static_cast<int32_t>(reading.gpio);
        context.has_gpio = true;
        context.sensor_type = reading.sensor_type.c_str();
        context.reason_class = reason_class;

        errorTracker.trackErrorWithContext(ERROR_MQTT_PUBLISH_FAILED,
                                           ERROR_SEVERITY_ERROR,
                                           "Failed to publish sensor data",
                                           context);
        return false;
    }
    return true;
}

String SensorManager::buildMQTTPayload(const SensorReading& reading) const {
    String payload;
    payload.reserve(384);  // Increased for zone info
    
    // Get ESP ID and Zone info from ConfigManager
    ConfigManager& config = ConfigManager::getInstance();
    String esp_id = config.getESPId();
    
    // Phase 7: Get zone information from global variables (extern from main.cpp)
    extern KaiserZone g_kaiser;
    
    // Phase 8: Use NTP-synchronized Unix timestamp
    time_t unix_ts = timeManager.getUnixTimestamp();
    
    // Build JSON payload with zone information and correlation seq
    payload = "{";
    payload += "\"esp_id\":\"";
    payload += esp_id;
    payload += "\",";
    payload += "\"seq\":";
    payload += String(mqtt_client_->getNextSeq());
    payload += ",";
    payload += "\"zone_id\":\"";
    payload += g_kaiser.zone_id;
    payload += "\",";
    payload += "\"subzone_id\":\"";
    payload += reading.subzone_id;  // From sensor config
    payload += "\",";
    payload += "\"gpio\":";
    payload += String(reading.gpio);
    payload += ",";
    payload += "\"sensor_type\":\"";
    payload += reading.sensor_type;
    payload += "\",";
    payload += "\"raw\":";
    payload += String((int32_t)reading.raw_value);  // Cast preserves sign for int16_t raw values (e.g. DS18B20)
    payload += ",";
    payload += "\"value\":";
    payload += String(reading.processed_value);
    payload += ",";
    payload += "\"unit\":\"";
    payload += reading.unit;
    payload += "\",";
    payload += "\"quality\":\"";
    payload += reading.quality;
    payload += "\",";
    payload += "\"ts\":";
    payload += String((unsigned long)unix_ts);
    payload += ",";
    payload += "\"time_valid\":";
    payload += (timeManager.isSynchronized() ? "true" : "false");
    payload += ",";

    // raw_mode from Reading (Server-Centric: true = server processes RAW data)
    payload += "\"raw_mode\":";
    payload += (reading.raw_mode ? "true" : "false");

    // Pulse-counting window — only present for flow sensors (window_ms > 0)
    if (reading.window_ms > 0) {
        payload += ",\"window_ms\":";
        payload += String(reading.window_ms);
    }

    if (reading.has_sampling_stats && reading.sample_count > 1) {
        payload += ",\"sample_count\":";
        payload += String(reading.sample_count);
        payload += ",\"adc_stddev\":";
        payload += String(reading.adc_stddev, 2);
        payload += ",\"stable\":";
        payload += (reading.stable ? "true" : "false");
    }
    
    // OneWire Address (for device identification on shared bus)
    if (!reading.onewire_address.isEmpty()) {
        payload += ",\"onewire_address\":\"";
        payload += reading.onewire_address;
        payload += "\"";
    }

    // I2C Address (only for actual I2C sensors — guard against stale NVS values on non-I2C sensors)
    const SensorCapability* cap = findSensorCapability(reading.sensor_type);
    if (reading.i2c_address != 0 && cap != nullptr && cap->is_i2c) {
        payload += ",\"i2c_address\":";
        payload += String(reading.i2c_address);
    }

    // External ADC source (ADS1115) — diagnostic discriminator, only for sensors
    // acquired via the external ADC. The server's authoritative RAW->voltage
    // discriminator is the stored calibration; these fields are informational.
    if (reading.adc_source == AdcSourceCode::ADS1115) {
        payload += ",\"adc_source\":\"ads1115\"";
        if (reading.adc_channel != 255) {
            payload += ",\"adc_channel\":";
            payload += String(reading.adc_channel);
        }
        payload += ",\"pga_gain\":\"";
        payload += ads1115PgaStringFromBits(reading.pga_gain);
        payload += "\"";
        // For ADS1115 the i2c_address carries the module address (0x48-0x4B);
        // emit it here since the analog capability above is not flagged is_i2c.
        if (reading.i2c_address != 0) {
            payload += ",\"i2c_address\":";
            payload += String(reading.i2c_address);
        }
    }

    payload += "}";

    return payload;
}

// ============================================
// SAFETY-P4: Value Cache Implementation
// ============================================

void SensorManager::updateValueCache(uint8_t gpio, const char* sensor_type, float value) {
    // Search for existing entry
    for (uint8_t i = 0; i < value_cache_count_; i++) {
        if (value_cache_[i].gpio == gpio &&
            strncmp(value_cache_[i].sensor_type, sensor_type, 23) == 0) {
            value_cache_[i].value        = value;
            value_cache_[i].timestamp_ms = millis();
            value_cache_[i].valid        = true;
            return;
        }
    }

    // New entry — insert if space available
    if (value_cache_count_ < MAX_VALUE_CACHE_ENTRIES) {
        ValueCacheEntry& entry  = value_cache_[value_cache_count_];
        entry.gpio              = gpio;
        strncpy(entry.sensor_type, sensor_type, 23);
        entry.sensor_type[23]   = '\0';
        entry.value             = value;
        entry.timestamp_ms      = millis();
        entry.valid             = true;
        value_cache_count_++;
    }
}

float SensorManager::getSensorValue(uint8_t gpio, const char* sensor_type) const {
    for (uint8_t i = 0; i < value_cache_count_; i++) {
        const ValueCacheEntry& entry = value_cache_[i];
        if (!entry.valid) {
            continue;
        }
        if (entry.gpio != gpio) {
            continue;
        }
        if (strncmp(entry.sensor_type, sensor_type, 23) != 0) {
            continue;
        }
        // Check stale timeout
        if (millis() - entry.timestamp_ms >= VALUE_CACHE_STALE_MS) {
            return NAN;
        }
        return entry.value;
    }
    return NAN;
}
