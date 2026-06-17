#ifndef SERVICES_SENSOR_PI_ENHANCED_PROCESSOR_H
#define SERVICES_SENSOR_PI_ENHANCED_PROCESSOR_H

#include <Arduino.h>
#include "../../error_handling/circuit_breaker.h"

// ============================================
// PI ENHANCED PROCESSOR CLASS (Phase 4 - Server-Centric Core)
// ============================================
// Purpose: HTTP communication with God-Kaiser Server for sensor data processing
// - Send raw sensor data to server
// - Receive processed data from server
// - Circuit-Breaker pattern for server failure handling

// Forward declarations
class HTTPClient;
struct RawSensorData;
struct ProcessedSensorData;

// ============================================
// RAW SENSOR DATA STRUCTURE
// ============================================
struct RawSensorData {
    uint8_t gpio;
    String sensor_type;              // "ph_sensor", "temperature_ds18b20", etc.
    uint32_t raw_value;              // ADC-Wert (0-4095) oder OneWire-Raw
    unsigned long timestamp;
    String metadata;                 // Optional: JSON mit zusätzlichen Infos
};

// ============================================
// PROCESSED SENSOR DATA STRUCTURE
// ============================================
struct ProcessedSensorData {
    float value;                     // Verarbeiteter Wert (z.B. 7.2 pH)
    String unit;                     // "pH", "°C", "ppm", etc.
    String quality;                  // "excellent", "good", "fair", "poor", "bad", "stale"
    unsigned long timestamp;
    bool valid;
    String error_message;
};

// ============================================
// PI ENHANCED PROCESSOR CLASS
// ============================================
class PiEnhancedProcessor {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static PiEnhancedProcessor& getInstance();
    
    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize processor
    bool begin();
    
    // Deinitialize processor
    void end();
    
    // ============================================
    // RAW DATA PROCESSING
    // ============================================
    // Send raw data to God-Kaiser Server
    // Returns true if request successful, false otherwise
    bool sendRawData(const RawSensorData& data, ProcessedSensorData& processed_out);
    
    // ============================================
    // SERVER STATUS
    // ============================================
    bool isPiAvailable() const;
    String getPiServerAddress() const;
    uint16_t getPiServerPort() const;
    unsigned long getLastResponseTime() const;
    
    // ============================================
    // CIRCUIT-BREAKER-PATTERN (Phase 6+)
    // ============================================
    bool isCircuitOpen() const;          // Server nicht erreichbar
    void resetCircuitBreaker();          // Manual reset
    uint8_t getConsecutiveFailures() const;
    CircuitState getCircuitState() const;  // ✅ NEU: Get state (CLOSED/OPEN/HALF_OPEN)
    
private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    PiEnhancedProcessor();
    ~PiEnhancedProcessor();
    
    // Prevent copy
    PiEnhancedProcessor(const PiEnhancedProcessor&) = delete;
    PiEnhancedProcessor& operator=(const PiEnhancedProcessor&) = delete;
    
    // ============================================
    // PRIVATE MEMBERS
    // ============================================
    HTTPClient* http_client_;
    String pi_server_address_;
    uint16_t pi_server_port_;
    unsigned long last_response_time_;
    
    // Circuit Breaker (Phase 6+) - Shared implementation
    CircuitBreaker circuit_breaker_;
    
    // ============================================
    // HELPER METHODS
    // ============================================
    // Build request URL
    String buildRequestUrl() const;
    
    // Build JSON request payload
    String buildRequestPayload(const RawSensorData& data) const;
    
    // Parse JSON response
    bool parseResponse(const String& json_response, ProcessedSensorData& processed_out);
    
    // ============================================
    // LOCAL FALLBACK CONVERSION (Circuit Breaker OPEN)
    // ============================================
    // Apply local conversion formulas for known sensor types
    // when server is unavailable. Returns true if conversion was applied,
    // false if sensor type is unknown (raw value used as-is).
    bool applyLocalConversion(const String& sensor_type, uint32_t raw_value,
                              ProcessedSensorData& processed_out);
};

// ============================================
// GLOBAL PI ENHANCED PROCESSOR INSTANCE
// ============================================
extern PiEnhancedProcessor& piEnhancedProcessor;

#endif // SERVICES_SENSOR_PI_ENHANCED_PROCESSOR_H

