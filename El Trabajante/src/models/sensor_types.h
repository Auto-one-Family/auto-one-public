#ifndef MODELS_SENSOR_TYPES_H
#define MODELS_SENSOR_TYPES_H

#include <Arduino.h>

// ✅ Sensor Types (String-basiert für Server-Centric)
// Migration aus: main.cpp:131-146 (SensorType Enum)
// ABER: Als String statt Enum (Flexibilität für Server-definierte Typen)
// Beispiele: "ph_sensor", "temperature_ds18b20", "ec_sensor", etc.

// ============================================
// SENSOR CIRCUIT BREAKER STATE (per-sensor)
// ============================================
// Lightweight inline state for sensor-level circuit breaker.
// Consistent with CircuitState in error_handling/circuit_breaker.h
// but avoids heap allocation per sensor.
enum class SensorCBState : uint8_t {
    CLOSED = 0,     // Normal — sensor is measured
    OPEN = 1,       // Disabled — sensor is skipped
    HALF_OPEN = 2   // Probing — one attempt allowed
};

// ============================================
// EXTERNAL ADC SOURCE (ADS1115) — compact encodings
// ============================================
// Stored as uint8_t in SensorConfig/SensorReading to keep the static sensors_[]
// array small (Arduino String members would blow the DRAM budget — see firmware
// memory rules). The server speaks strings ("internal"/"ads1115", "4.096"); the
// helpers below translate at the JSON parse / payload-build boundaries.
namespace AdcSourceCode {
    constexpr uint8_t INTERNAL = 0;  // ESP32 internal 12-bit ADC (default)
    constexpr uint8_t ADS1115  = 1;  // External 16-bit I2C ADC
}

// ============================================
// DIGITAL SENSOR POLARITY (liquid_level) — compact encoding
// ============================================
// active_low  (default): NPN open-collector, LOW = detected → raw=1 (unchanged
//             behavior for existing liquid_level configs without this field).
// active_high: PNP, HIGH = detected → raw=1 (e.g. XKC-Y26S-PNP).
namespace SensorPolarityCode {
    constexpr uint8_t ACTIVE_LOW  = 0;  // NPN open-collector (default)
    constexpr uint8_t ACTIVE_HIGH = 1;  // PNP (e.g. XKC-Y26S-PNP)
}

// ADS1115 PGA full-scale range <-> config-register bits [11:9] (also our compact
// storage code). Default bits 1 = +-4.096V. Unknown strings fall back to default.
inline uint8_t ads1115PgaBitsFromString(const String& s) {
    if (s == "6.144") return 0;
    if (s == "4.096") return 1;
    if (s == "2.048") return 2;
    if (s == "1.024") return 3;
    if (s == "0.512") return 4;
    if (s == "0.256") return 5;
    return 1;
}

inline const char* ads1115PgaStringFromBits(uint8_t bits) {
    switch (bits) {
        case 0: return "6.144";
        case 1: return "4.096";
        case 2: return "2.048";
        case 3: return "1.024";
        case 4: return "0.512";
        case 5: return "0.256";
        default: return "4.096";
    }
}

// ============================================
// SENSOR CONFIGURATION - Server-Centric
// ============================================
// Migration aus: main.cpp:415-430 (SensorConfig Struct)
struct SensorConfig {
  uint8_t gpio = 255;                    // GPIO-Pin
  String sensor_type = "";               // String statt Enum (z.B. "ph_sensor", "ds18b20")
  String sensor_name = "";               // User-definierter Name
  String subzone_id = "";                // Subzone-Zuordnung
  bool active = false;                   // Sensor aktiv?

  // AUT-555: QoS level used when publishing sensor readings to the MQTT broker.
  //
  // Background: AUT-54 switched ALL sensor publishes to QoS-0 because the IDF OUTBOX
  // would fill up under WiFi jitter, causing write-timeout disconnects (especially
  // with simultaneous actuator traffic). QoS-0 = fire-and-forget, no PUBACK
  // required, so stalled OUTBOX no longer blocks the send path.
  //
  // Problem: sensors referenced in a cross_esp_logic rule MUST deliver their reading for
  // the rule to fire. A lost QoS-0 reading means a missed trigger for e.g. humidity control
  // (rule sees no update → stays in last state even if threshold was crossed).
  //
  // Solution: per-sensor QoS decided server-side at config-push time.
  //   publish_qos = 1 → sensor is used in at least one enabled rule → PUBACK required
  //   publish_qos = 0 → pure monitoring sensor (no rule dependency) → fire-and-forget OK
  //
  // Set by: parseAndConfigureSensorWithTracking() in main.cpp, reading "publish_qos" from
  //         the server config payload.
  // Read by: SensorManager::publishSensorReading() in sensor_manager.cpp.
  // Server source: ConfigPayloadBuilder.build_combined_config() via
  //                LogicRepository.get_rule_gpio_set_for_esp().
  uint8_t publish_qos = 0;  // 0 = QoS-0 (telemetry default), 1 = QoS-1 (rule-active)

  // Phase 2C: Operating Mode Support
  // Modes: "continuous" (auto-measure), "on_demand" (command only),
  //        "paused" (no measure), "scheduled" (server-triggered)
  String operating_mode = "continuous";      // Betriebsmodus
  uint32_t measurement_interval_ms = 30000;  // Pro-Sensor Messintervall (ms)

  // Pi-Enhanced Mode (DEFAULT - 90% der Anwendungen):
  bool raw_mode = true;                  // IMMER true (Rohdaten-Modus)
  uint32_t last_raw_value = 0;           // Letzter Rohdaten-Wert (ADC 0-4095)
  unsigned long last_reading = 0;        // Timestamp der letzten Messung
  
  // ============================================
  // ONEWIRE SUPPORT (DS18B20, DS18S20, DS1822)
  // ============================================
  // ROM-Code for unique device identification on shared OneWire bus
  // Format: 16 Hex chars (e.g. "28FF641E8D3C0C79")
  // Empty for non-OneWire sensors (pH, EC, ADC-based, etc.)
  String onewire_address = "";

  // ============================================
  // I2C SUPPORT (SHT31, BMP280, etc.)
  // ============================================
  // I2C address for device identification (7-bit address, 0x00-0x7F)
  // 0 for non-I2C sensors (OneWire, Analog, Digital)
  uint8_t i2c_address = 0;

  // ============================================
  // EXTERNAL ADC SOURCE (ADS1115) — pH/EC acquisition source
  // ============================================
  // pH/EC can OPTIONALLY be read via an external 16-bit I2C ADC (ADS1115)
  // instead of the internal ESP32 12-bit ADC. Only the acquisition source
  // changes — the RAW value still flows unchanged through MQTT (raw_mode) to
  // the server, which performs the identical conversion/calibration.
  //   adc_source  = "internal" (default) | "ads1115"
  //   adc_channel = ADS1115 single-ended channel 0-3 (255 = unset/internal)
  //   pga_gain    = ADS1115 PGA full-scale range in volts, e.g. "4.096"
  // For ads1115 the i2c_address field carries the module address (0x48-0x4B)
  // and gpio stays 0 (same convention as other I2C sensors).
  // Compact uint8_t encodings (see AdcSourceCode / ads1115Pga* helpers above).
  uint8_t adc_source = AdcSourceCode::INTERNAL;  // 0=internal, 1=ads1115
  uint8_t adc_channel = 255;                     // ADS1115 channel 0-3 (255=unset)
  uint8_t pga_gain = 1;                          // ADS1115 PGA bits (0-5); 1 = +-4.096V

  // ============================================
  // DIGITAL SENSOR POLARITY (liquid_level)
  // ============================================
  // active_low (default) = NPN open-collector, LOW=detected → raw=1 (unchanged
  // behavior for pre-existing configs). active_high = PNP, HIGH=detected → raw=1
  // (e.g. XKC-Y26S-PNP). Also drives pin mode (see readRawDigital): active_high
  // uses INPUT (external pull-down assumed), active_low uses INPUT_PULLUP.
  uint8_t polarity = SensorPolarityCode::ACTIVE_LOW;

  // ============================================
  // UART SUPPORT (MH-Z19 / SEN0220 CO2, etc.)
  // ============================================
  // interface_type from server (e.g. "UART"); gpio is logical sensor slot only
  String interface_type = "";
  uint8_t uart_rx_pin = 255;   // ESP RX ← sensor TX (255 = unset)
  uint8_t uart_tx_pin = 255;   // ESP TX → sensor RX
  uint32_t uart_baud = 9600;
  unsigned long uart_configured_at_ms = 0;  // Runtime warmup gate (not NVS)

  // ============================================
  // CIRCUIT BREAKER STATE (per-sensor runtime)
  // ============================================
  // Prevents endless retries on defective/disconnected sensors.
  // OPEN after CB_MAX_CONSECUTIVE_FAILURES, probes every CB_PROBE_INTERVAL_MS.
  // Config-push from server resets to CLOSED.
  SensorCBState cb_state = SensorCBState::CLOSED;
  uint32_t cb_open_since_ms = 0;       // millis() when entering OPEN
  uint8_t consecutive_failures = 0;    // Consecutive measurement failures

  // ❌ NICHT NÖTIG in Server-Centric Architektur:
  // - float last_value (Server verarbeitet)
  // - void* library_handle (keine lokalen Libraries)
  // - bool library_loaded (keine lokalen Libraries)
  // - String library_name (Server-side)
  // - String library_version (Server-side)
};

// ============================================
// SENSOR READING RESULT (für MQTT-Payload)
// ============================================
struct SensorReading {
  uint8_t gpio;
  String sensor_type;
  String subzone_id;                     // Subzone-Zuordnung (aus SensorConfig)
  uint32_t raw_value;                    // ADC-Wert / RAW 12-bit für OneWire
  float processed_value;                 // Vom Server zurückgegeben
  String unit;                           // Vom Server zurückgegeben
  String quality;                        // Vom Server zurückgegeben
  unsigned long timestamp;
  bool valid;
  String error_message;
  
  // ============================================
  // RAW MODE FLAG (Server-Centric Architecture)
  // ============================================
  // Indicates whether raw_value is RAW data (true) or already converted (false)
  // - true: Server must apply conversion formula (e.g. raw * 0.0625 for DS18B20)
  // - false: Value already converted to final unit (legacy support)
  // Default: true (Pi-Enhanced Mode - 90% of use cases)
  bool raw_mode = true;
  
  // ============================================
  // ONEWIRE SUPPORT (for MQTT payload identification)
  // ============================================
  // Copied from SensorConfig - Server uses this to identify
  // which DS18B20 on a shared bus sent this reading
  // Format: 16 Hex chars (e.g. "28FF641E8D3C0C79")
  String onewire_address = "";

  // ============================================
  // I2C SUPPORT (for MQTT payload identification)
  // ============================================
  // Copied from SensorConfig - Server uses this to identify
  // which I2C sensor at a specific address sent this reading
  // 0 for non-I2C sensors
  uint8_t i2c_address = 0;

  // ============================================
  // EXTERNAL ADC SOURCE (ADS1115) — diagnostic discriminator
  // ============================================
  // Copied from SensorConfig. Reported in the MQTT payload ONLY when the sensor
  // is read via an external ADS1115 (adc_source="ads1115"), so the server has a
  // diagnostic record of the acquisition source / PGA alongside the calibration.
  // The authoritative RAW->voltage discriminator on the server is the stored
  // calibration (adc_source/pga_gain); these payload fields are informational.
  // Compact uint8_t encodings (see AdcSourceCode / ads1115Pga* helpers above).
  uint8_t adc_source = AdcSourceCode::INTERNAL;  // 0=internal, 1=ads1115
  uint8_t adc_channel = 255;                     // ADS1115 channel 0-3 (255=unset)
  uint8_t pga_gain = 1;                          // ADS1115 PGA bits (0-5); 1 = +-4.096V

  // ============================================
  // ANALOG PROBE SAMPLING STATS (EC/pH stabilization)
  // ============================================
  uint8_t sample_count = 0;       // Number of ADC samples aggregated (0 = single/legacy)
  float adc_stddev = 0.0f;        // Population stddev of raw ADC samples
  bool stable = false;            // true when adc_stddev <= ~1% of median ADC
  bool has_sampling_stats = false;
  uint32_t window_ms = 0;         // Pulse-counting window duration in ms (0 = non-pulse sensor)
};

#endif

