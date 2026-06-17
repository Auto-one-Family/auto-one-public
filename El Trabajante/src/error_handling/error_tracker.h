#ifndef ERROR_HANDLING_ERROR_TRACKER_H
#define ERROR_HANDLING_ERROR_TRACKER_H

#include <Arduino.h>

// ============================================
// ERROR CATEGORIES (Guide-konform: 1000-4999)
// ============================================
enum ErrorCategory {
  ERROR_HARDWARE = 1000,       // GPIO, I2C, PWM
  ERROR_SERVICE = 2000,        // Sensor, Actuator, Config
  ERROR_COMMUNICATION = 3000,  // MQTT, HTTP, WiFi
  ERROR_APPLICATION = 4000     // State, Memory, System
};

// ============================================
// ERROR SEVERITY LEVELS
// ============================================
enum ErrorSeverity {
  ERROR_SEVERITY_WARNING = 1,  // Recoverable warning
  ERROR_SEVERITY_ERROR = 2,    // Error but system can continue
  ERROR_SEVERITY_CRITICAL = 3  // Critical error, system unstable
};

// ============================================
// ERROR ENTRY STRUCTURE (Guide-konform: fixed size)
// ============================================
struct ErrorEntry {
  unsigned long timestamp;
  uint16_t error_code;
  ErrorSeverity severity;
  char message[128];
  uint8_t occurrence_count;  // Duplicate tracking
  
  ErrorEntry() 
    : timestamp(0), error_code(0),
      severity(ERROR_SEVERITY_ERROR),
      occurrence_count(0) {
    message[0] = '\0';
  }
};

struct ErrorMqttContext {
  const char* topic = nullptr;
  const char* sensor_type = nullptr;
  const char* reason_class = nullptr;
  int32_t gpio = -1;
  bool has_gpio = false;
};

// ============================================
// MQTT PUBLISH CALLBACK TYPE
// ============================================
// Fire-and-forget callback for publishing errors to MQTT
// Parameters: topic, payload
// Note: Must NOT call errorTracker methods (recursion prevention!)
typedef void (*MqttErrorPublishCallback)(const char* topic, const char* payload);

// ============================================
// ERROR TRACKER CLASS
// ============================================
class ErrorTracker {
public:
  // Singleton Instance
  static ErrorTracker& getInstance();
  
  // Initialization (Guide-konform)
  void begin();
  
  // Primary API: const char* (Guide-konform)
  void trackError(uint16_t error_code, ErrorSeverity severity, const char* message);
  void trackError(uint16_t error_code, const char* message);  // Default severity: ERROR
  void trackErrorWithContext(uint16_t error_code,
                             ErrorSeverity severity,
                             const char* message,
                             const ErrorMqttContext& context);
  
  // Convenience Methods — pass full codes from models/error_codes.h when available; small
  // numeric offsets still map via category base + code when outside the band (bands use
  // fixed 1000–1999 / 2000–2999 / 3000–3999 / 4000–4999 per models/error_codes.h).
  void logHardwareError(uint16_t code, const char* message);
  void logServiceError(uint16_t code, const char* message);
  void logCommunicationError(uint16_t code, const char* message);
  void logApplicationError(uint16_t code, const char* message);
  
  // Error Retrieval
  String getErrorHistory(uint8_t max_entries = 20) const;
  String getErrorsByCategory(ErrorCategory category, uint8_t max_entries = 10) const;
  size_t getErrorCount() const;
  size_t getErrorCountByCategory(ErrorCategory category) const;
  
  // Error Status
  bool hasActiveErrors() const;
  bool hasCriticalErrors() const;
  void clearErrors();
  
  // ============================================
  // MQTT PUBLISHING (Observability - Phase 1-3)
  // ============================================
  /**
   * @brief Set MQTT publish callback for error observability
   *
   * When set, errors will be published to MQTT topic for server logging.
   * Callback is fire-and-forget - no error handling to prevent recursion.
   *
   * @param callback Function pointer to publish errors
   * @param esp_id ESP ID for topic building
   *
   * Topic format: kaiser/{kaiser_id}/esp/{esp_id}/system/error
   *
   * Payload format (Server-compatible):
   * {
   *   "error_code": 1020,
   *   "severity": 2,
   *   "category": "HARDWARE",
   *   "message": "Sensor read failed",
   *   "context": {"esp_id": "ESP_12AB34", "uptime_ms": 123456},
   *   "ts": 1735818000
   * }
   *
   * Note: ts=0 if NTP not synced (server uses server-time as fallback)
   */
  void setMqttPublishCallback(MqttErrorPublishCallback callback, const String& esp_id);
  
  /**
   * @brief Disable MQTT publishing (e.g., when MQTT disconnects)
   */
  void clearMqttPublishCallback();
  
  // Utilities
  static const char* getCategoryString(uint16_t error_code);
  static ErrorCategory getCategory(uint16_t error_code);
  
private:
  ErrorTracker();  // Private Constructor (Singleton)
  ~ErrorTracker() = default;
  ErrorTracker(const ErrorTracker&) = delete;
  ErrorTracker& operator=(const ErrorTracker&) = delete;
  
  // Fixed Array Circular Buffer (Guide-konform)
  // Reduced from 50 to 30 entries — saves 2800 bytes BSS (MEM-OPT-2)
  static const size_t MAX_ERROR_ENTRIES = 30;
  ErrorEntry error_buffer_[MAX_ERROR_ENTRIES];
  size_t error_buffer_index_;
  size_t error_count_;
  
  // MQTT Publishing (Observability)
  MqttErrorPublishCallback mqtt_callback_;
  String mqtt_esp_id_;
  bool mqtt_publishing_enabled_;
  bool mqtt_publish_in_progress_;  // Recursion guard
  
  // Helper methods
  void addToBuffer(uint16_t error_code, ErrorSeverity severity, const char* message);
  void logErrorToLogger(uint16_t error_code, ErrorSeverity severity, const char* message);
  void publishErrorToMqtt(uint16_t error_code,
                          ErrorSeverity severity,
                          const char* message,
                          const ErrorMqttContext* context = nullptr);
};

// ============================================
// GLOBAL ERROR TRACKER INSTANCE
// ============================================
extern ErrorTracker& errorTracker;

#endif

