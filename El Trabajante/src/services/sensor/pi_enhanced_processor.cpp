#include "pi_enhanced_processor.h"
#include "../communication/http_client.h"
#include "../config/config_manager.h"
#include "../../utils/logger.h"
#include "../../error_handling/error_tracker.h"
#include "../../models/error_codes.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "PIENH";

// ============================================
// GLOBAL PI ENHANCED PROCESSOR INSTANCE
// ============================================
PiEnhancedProcessor& piEnhancedProcessor = PiEnhancedProcessor::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
PiEnhancedProcessor& PiEnhancedProcessor::getInstance() {
    static PiEnhancedProcessor instance;
    return instance;
}

// ============================================
// PRIVATE CONSTRUCTOR
// ============================================
PiEnhancedProcessor::PiEnhancedProcessor()
    : http_client_(nullptr),
      pi_server_address_(""),
      pi_server_port_(8000),
      last_response_time_(0),
      circuit_breaker_("PiServer", 5, 60000, 10000) {
  // Circuit Breaker configured (Phase 6+):
  // - 5 failures → OPEN (like MQTT)
  // - 60s recovery timeout
  // - 10s half-open test timeout
}

PiEnhancedProcessor::~PiEnhancedProcessor() {
    end();
}

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool PiEnhancedProcessor::begin() {
    LOG_I(TAG, "PiEnhancedProcessor: Initializing...");
    
    // Get HTTP client instance
    http_client_ = &HTTPClient::getInstance();
    
    if (!http_client_->isInitialized()) {
        if (!http_client_->begin()) {
            LOG_E(TAG, "PiEnhancedProcessor: HTTPClient initialization failed");
            errorTracker.trackError(ERROR_HTTP_INIT_FAILED, ERROR_SEVERITY_ERROR,
                                   "HTTPClient initialization failed");
            return false;
        }
    }
    
    // Load server address from ConfigManager
    ConfigManager& config = ConfigManager::getInstance();
    WiFiConfig wifi_config = config.getWiFiConfig();
    
    if (wifi_config.server_address.length() > 0) {
        pi_server_address_ = wifi_config.server_address;
    } else {
        // Fallback to default
        pi_server_address_ = "192.168.1.100";
        LOG_W(TAG, "PiEnhancedProcessor: Using default server address: " + pi_server_address_);
    }
    
    LOG_I(TAG, "PiEnhancedProcessor: Initialized - Server: " + pi_server_address_ + 
             ":" + String(pi_server_port_));
    
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void PiEnhancedProcessor::end() {
    LOG_I(TAG, "PiEnhancedProcessor: Deinitialized");
}

// ============================================
// SEND RAW DATA TO SERVER (with Circuit Breaker - Phase 6+)
// ============================================
bool PiEnhancedProcessor::sendRawData(const RawSensorData& data, ProcessedSensorData& processed_out) {
    // Initialize processed_out
    processed_out.valid = false;
    processed_out.value = 0.0;
    processed_out.unit = "";
    processed_out.quality = "";
    processed_out.timestamp = 0;
    processed_out.error_message = "";
    
    // ============================================
    // CIRCUIT BREAKER CHECK (Phase 6+)
    // ============================================
    if (!circuit_breaker_.allowRequest()) {
        LOG_W(TAG, "PiEnhancedProcessor: Circuit breaker blocked request (Service DOWN)");
        LOG_D(TAG, "  Circuit State: " + String(circuit_breaker_.isOpen() ? "OPEN" : "HALF_OPEN"));

        // ═══════════════════════════════════════════════════
        // PHASE 2: HTTP-FALLBACK-MODE (Robustness)
        // ═══════════════════════════════════════════════════
        // Server unavailable → use local fallback with conversion
        bool converted = applyLocalConversion(data.sensor_type, data.raw_value, processed_out);
        processed_out.quality = "fair";               // Medium quality (not calibrated)
        processed_out.timestamp = data.timestamp;
        processed_out.valid = true;

        if (converted) {
            LOG_I(TAG, "Using local fallback processing - converted " + data.sensor_type + 
                     " raw=" + String(data.raw_value) + " → " + String(processed_out.value) + " " + processed_out.unit);
            processed_out.error_message = "Local fallback (converted) - server unavailable";
        } else {
            LOG_I(TAG, "Using local fallback processing - returning raw values (unknown type: " + data.sensor_type + ")");
            processed_out.error_message = "Local fallback (raw) - server unavailable, unknown sensor type";
        }

        return true;  // Success with fallback data
    }
    
    // ============================================
    // HTTP CLIENT CHECK
    // ============================================
    if (!http_client_ || !http_client_->isInitialized()) {
        LOG_E(TAG, "PiEnhancedProcessor: HTTPClient not initialized");
        processed_out.error_message = "HTTPClient not initialized";
        circuit_breaker_.recordFailure();  // ✅ Count as failure
        return false;
    }
    
    // ============================================
    // BUILD & SEND REQUEST
    // ============================================
    String url = buildRequestUrl();
    String payload = buildRequestPayload(data);

    LOG_I(TAG, "PiEnhancedProcessor: HTTP POST START url=" + url);
    LOG_I(TAG, "PiEnhancedProcessor: HTTP POST payload=" + payload.substring(0, 100));

    // FIX #3: Timeout 5000ms → 2500ms (LAN-realistisch, CB ist primärer Schutz)
    unsigned long http_start = millis();
    HTTPResponse response = http_client_->post(url.c_str(), payload.c_str(),
                                               "application/json", 2500);
    unsigned long http_duration = millis() - http_start;
    LOG_I(TAG, "PiEnhancedProcessor: HTTP POST END duration=" + String(http_duration) + "ms success=" + String(response.success ? "YES" : "NO"));
    
    // ============================================
    // HANDLE RESPONSE
    // ============================================
    if (!response.success) {
        // ❌ HTTP REQUEST FAILED
        circuit_breaker_.recordFailure();
        LOG_E(TAG, "PiEnhancedProcessor: HTTP request failed - " + String(response.error_message));
        processed_out.error_message = response.error_message;
        
        // Check if Circuit Breaker opened
        if (circuit_breaker_.isOpen()) {
            LOG_W(TAG, "PiEnhancedProcessor: Circuit Breaker OPENED after failures");
            LOG_W(TAG, "  Will retry in 60 seconds");
        }
        
        return false;
    }
    
    // ============================================
    // PARSE RESPONSE
    // ============================================
    if (!parseResponse(response.body, processed_out)) {
        // ❌ PARSE FAILED
        circuit_breaker_.recordFailure();
        LOG_E(TAG, "PiEnhancedProcessor: Failed to parse response");
        LOG_D(TAG, "  Response: " + response.body.substring(0, 100));
        processed_out.error_message = "JSON parse error";
        return false;
    }
    
    // ✅ SUCCESS
    circuit_breaker_.recordSuccess();
    last_response_time_ = millis();
    
    LOG_D(TAG, "PiEnhancedProcessor: Request successful - Value: " + 
              String(processed_out.value) + " " + processed_out.unit);
    
    return true;
}

// ============================================
// BUILD REQUEST URL
// ============================================
String PiEnhancedProcessor::buildRequestUrl() const {
    String url;
    url.reserve(128);
    url = "http://";
    url += pi_server_address_;
    url += ":";
    url += String(pi_server_port_);
    url += "/api/v1/sensors/process";
    return url;
}

// ============================================
// BUILD REQUEST PAYLOAD
// ============================================
String PiEnhancedProcessor::buildRequestPayload(const RawSensorData& data) const {
    String payload;
    payload.reserve(256);
    
    // Get ESP ID from ConfigManager
    ConfigManager& config = ConfigManager::getInstance();
    String esp_id = config.getESPId();
    
    // Build JSON payload
    payload = "{";
    payload += "\"esp_id\":\"";
    payload += esp_id;
    payload += "\",";
    payload += "\"gpio\":";
    payload += String(data.gpio);
    payload += ",";
    payload += "\"sensor_type\":\"";
    payload += data.sensor_type;
    payload += "\",";
    payload += "\"raw_value\":";
    payload += String(data.raw_value);
    payload += ",";
    payload += "\"timestamp\":";
    payload += String(data.timestamp);
    
    if (data.metadata.length() > 0) {
        payload += ",\"metadata\":";
        payload += data.metadata;
    } else {
        payload += ",\"metadata\":{}";
    }
    
    payload += "}";
    
    return payload;
}

// ============================================
// PARSE JSON RESPONSE
// ============================================
bool PiEnhancedProcessor::parseResponse(const String& json_response, ProcessedSensorData& processed_out) {
    // Simple JSON parsing (no external library)
    // Expected format: {"processed_value": 7.2, "unit": "pH", "quality": "good", "timestamp": 1735818000}
    
    processed_out.valid = false;
    
    // Find processed_value
    int value_start = json_response.indexOf("\"processed_value\":");
    if (value_start == -1) {
        return false;
    }
    value_start += 18;  // Length of "processed_value":
    int value_end = json_response.indexOf(",", value_start);
    if (value_end == -1) {
        value_end = json_response.indexOf("}", value_start);
    }
    if (value_end == -1) {
        return false;
    }
    String value_str = json_response.substring(value_start, value_end);
    value_str.trim();
    processed_out.value = value_str.toFloat();
    
    // Find unit
    int unit_start = json_response.indexOf("\"unit\":\"");
    if (unit_start != -1) {
        unit_start += 8;  // Length of "unit":""
        int unit_end = json_response.indexOf("\"", unit_start);
        if (unit_end != -1) {
            processed_out.unit = json_response.substring(unit_start, unit_end);
        }
    }
    
    // Find quality
    int quality_start = json_response.indexOf("\"quality\":\"");
    if (quality_start != -1) {
        quality_start += 11;  // Length of "quality":""
        int quality_end = json_response.indexOf("\"", quality_start);
        if (quality_end != -1) {
            processed_out.quality = json_response.substring(quality_start, quality_end);
        }
    }
    
    // Find timestamp
    int ts_start = json_response.indexOf("\"timestamp\":");
    if (ts_start != -1) {
        ts_start += 12;  // Length of "timestamp":
        int ts_end = json_response.indexOf(",", ts_start);
        if (ts_end == -1) {
            ts_end = json_response.indexOf("}", ts_start);
        }
        if (ts_end != -1) {
            String ts_str = json_response.substring(ts_start, ts_end);
            ts_str.trim();
            processed_out.timestamp = ts_str.toInt();
        }
    } else {
        processed_out.timestamp = millis();
    }
    
    processed_out.valid = true;
    return true;
}

// ============================================
// CIRCUIT BREAKER METHODS (Phase 6+)
// ============================================
// Note: updateCircuitBreaker() and checkCircuitBreakerReset() removed
// Replaced by circuit_breaker_.recordSuccess/Failure() and allowRequest()

// ============================================
// SERVER STATUS QUERIES (Phase 6+)
// ============================================
bool PiEnhancedProcessor::isPiAvailable() const {
    return !circuit_breaker_.isOpen();
}

String PiEnhancedProcessor::getPiServerAddress() const {
    return pi_server_address_;
}

uint16_t PiEnhancedProcessor::getPiServerPort() const {
    return pi_server_port_;
}

unsigned long PiEnhancedProcessor::getLastResponseTime() const {
    return last_response_time_;
}

bool PiEnhancedProcessor::isCircuitOpen() const {
    return circuit_breaker_.isOpen();
}

void PiEnhancedProcessor::resetCircuitBreaker() {
    circuit_breaker_.reset();
    LOG_I(TAG, "PiEnhancedProcessor: Circuit breaker manually RESET");
}

uint8_t PiEnhancedProcessor::getConsecutiveFailures() const {
    return circuit_breaker_.getFailureCount();
}

CircuitState PiEnhancedProcessor::getCircuitState() const {
    return circuit_breaker_.getState();
}

// ============================================
// LOCAL FALLBACK CONVERSION (Circuit Breaker OPEN)
// ============================================
// Standard conversion formulas for known sensor types.
// Used when server is unreachable to provide approximately
// correct physical values instead of raw register data.
bool PiEnhancedProcessor::applyLocalConversion(
    const String& sensor_type, uint32_t raw_value,
    ProcessedSensorData& processed_out) {
    
    // SHT31 Temperature: T(°C) = -45 + 175 × (raw / 65535)
    if (sensor_type == "sht31_temp") {
        processed_out.value = -45.0f + 175.0f * ((float)raw_value / 65535.0f);
        processed_out.unit = "°C";
        return true;
    }
    
    // SHT31 Humidity: H(%) = 100 × (raw / 65535)
    if (sensor_type == "sht31_humidity") {
        processed_out.value = 100.0f * ((float)raw_value / 65535.0f);
        processed_out.unit = "%";
        return true;
    }
    
    // DS18B20 Temperature: T(°C) = raw × 0.0625 (12-bit resolution)
    if (sensor_type == "ds18b20") {
        processed_out.value = (float)raw_value * 0.0625f;
        processed_out.unit = "°C";
        return true;
    }
    
    // BMP280/BME280 Temperature: raw is centidegrees
    if (sensor_type == "bmp280_temp" || sensor_type == "bme280_temp") {
        processed_out.value = (float)raw_value / 100.0f;
        processed_out.unit = "°C";
        return true;
    }
    
    // BMP280/BME280 Pressure: raw is centipascals
    if (sensor_type == "bmp280_pressure" || sensor_type == "bme280_pressure") {
        processed_out.value = (float)raw_value / 100.0f;
        processed_out.unit = "hPa";
        return true;
    }
    
    // BME280 Humidity: raw is 1024ths of percent
    if (sensor_type == "bme280_humidity") {
        processed_out.value = (float)raw_value / 1024.0f;
        processed_out.unit = "%";
        return true;
    }
    
    // Unknown sensor type → return raw value
    processed_out.value = (float)raw_value;
    processed_out.unit = "raw";
    return false;
}