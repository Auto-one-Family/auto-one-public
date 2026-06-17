#include "error_tracker.h"
#include "../utils/logger.h"
#include "../utils/topic_builder.h"
#include "../utils/time_manager.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "ERRTRAK";

// Exclusive upper edges per models/error_codes.h — do not use the next enum enumerator
// as an upper bound (e.g. ERROR_APPLICATION auto-incrementing after ERROR_COMMUNICATION),
// which would mis-classify 3001–3999 and double-add the category base (INC-2026-04-10).
namespace {
constexpr uint16_t kErrHardwareBandEndExcl = 2000;
constexpr uint16_t kErrServiceBandEndExcl = 3000;
constexpr uint16_t kErrCommunicationBandEndExcl = 4000;
constexpr uint16_t kErrApplicationBandEndExcl = 5000;
constexpr uint16_t kErrApplicationBandBase = 4000;
}  // namespace

// ============================================
// ERROR RATE LIMITING (F8 — MQTT Flood Prevention)
// ============================================
// Per error_code max 1 MQTT publish per time window.
// Suppressed errors are counted and logged on next publish.
struct ErrorThrottle {
  uint32_t last_publish_ms = 0;
  uint16_t suppressed_count = 0;
};

static constexpr uint8_t  THROTTLE_SLOTS = 32;
static constexpr uint32_t THROTTLE_WINDOW_MS = 60000;  // 60s per error code

static ErrorThrottle throttle_table_[THROTTLE_SLOTS];

static bool shouldPublishError(uint16_t error_code) {
  uint32_t now = millis();
  uint8_t slot = error_code % THROTTLE_SLOTS;
  ErrorThrottle& t = throttle_table_[slot];

  if (now - t.last_publish_ms >= THROTTLE_WINDOW_MS) {
    if (t.suppressed_count > 0) {
      String msg = "Error " + String(error_code) + ": " +
                   String(t.suppressed_count) + " occurrences suppressed in last " +
                   String(THROTTLE_WINDOW_MS / 1000) + "s";
      logger.warning(TAG, msg.c_str());
    }
    t.last_publish_ms = now;
    t.suppressed_count = 0;
    return true;
  }

  t.suppressed_count++;
  return false;
}

// ============================================
// GLOBAL ERROR TRACKER INSTANCE
// ============================================
ErrorTracker& errorTracker = ErrorTracker::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
ErrorTracker& ErrorTracker::getInstance() {
  static ErrorTracker instance;
  return instance;
}

ErrorTracker::ErrorTracker()
  : error_buffer_index_(0),
    error_count_(0),
    mqtt_callback_(nullptr),
    mqtt_esp_id_(""),
    mqtt_publishing_enabled_(false),
    mqtt_publish_in_progress_(false) {
  // Initialize fixed buffer
  for (size_t i = 0; i < MAX_ERROR_ENTRIES; i++) {
    error_buffer_[i] = ErrorEntry();
  }
}

// ============================================
// INITIALIZATION (Guide-konform)
// ============================================
void ErrorTracker::begin() {
  error_buffer_index_ = 0;
  error_count_ = 0;
  
  for (size_t i = 0; i < MAX_ERROR_ENTRIES; i++) {
    error_buffer_[i] = ErrorEntry();
  }
  
  LOG_I(TAG, "ErrorTracker: Initialized");
}

// ============================================
// ERROR TRACKING (Primary API)
// ============================================
void ErrorTracker::trackError(uint16_t error_code, ErrorSeverity severity, const char* message) {
  // Log to Logger
  logErrorToLogger(error_code, severity, message);
  
  // Add to circular buffer
  addToBuffer(error_code, severity, message);
  
  // Publish to MQTT (if enabled and not recursing)
  publishErrorToMqtt(error_code, severity, message, nullptr);
}

void ErrorTracker::trackError(uint16_t error_code, const char* message) {
  trackError(error_code, ERROR_SEVERITY_ERROR, message);
}

void ErrorTracker::trackErrorWithContext(uint16_t error_code,
                                         ErrorSeverity severity,
                                         const char* message,
                                         const ErrorMqttContext& context) {
  logErrorToLogger(error_code, severity, message);
  addToBuffer(error_code, severity, message);
  publishErrorToMqtt(error_code, severity, message, &context);
}

// ============================================
// CONVENIENCE METHODS
// ============================================
void ErrorTracker::logHardwareError(uint16_t code, const char* message) {
  if (code >= ERROR_HARDWARE && code < kErrHardwareBandEndExcl) {
    trackError(code, ERROR_SEVERITY_ERROR, message);
  } else {
    trackError(static_cast<uint16_t>(ERROR_HARDWARE + code), ERROR_SEVERITY_ERROR, message);
  }
}

void ErrorTracker::logServiceError(uint16_t code, const char* message) {
  if (code >= ERROR_SERVICE && code < kErrServiceBandEndExcl) {
    trackError(code, ERROR_SEVERITY_ERROR, message);
  } else {
    trackError(static_cast<uint16_t>(ERROR_SERVICE + code), ERROR_SEVERITY_ERROR, message);
  }
}

void ErrorTracker::logCommunicationError(uint16_t code, const char* message) {
  if (code >= ERROR_COMMUNICATION && code < kErrCommunicationBandEndExcl) {
    trackError(code, ERROR_SEVERITY_ERROR, message);
  } else {
    trackError(static_cast<uint16_t>(ERROR_COMMUNICATION + code), ERROR_SEVERITY_ERROR, message);
  }
}

void ErrorTracker::logApplicationError(uint16_t code, const char* message) {
  if (code >= kErrApplicationBandBase && code < kErrApplicationBandEndExcl) {
    trackError(code, ERROR_SEVERITY_ERROR, message);
  } else {
    trackError(static_cast<uint16_t>(kErrApplicationBandBase + code), ERROR_SEVERITY_ERROR, message);
  }
}

// ============================================
// ERROR RETRIEVAL
// ============================================
String ErrorTracker::getErrorHistory(uint8_t max_entries) const {
  String result = "";
  size_t entries_added = 0;
  
  // Start from oldest entry
  size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
  
  for (size_t i = 0; i < error_count_ && entries_added < max_entries; i++) {
    size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
    const ErrorEntry& entry = error_buffer_[index];
    
    result += "[" + String(entry.timestamp) + "] ";
    result += "[" + String(entry.error_code) + "] ";
    result += "[" + String(getCategoryString(entry.error_code)) + "] ";
    result += String(entry.message);
    if (entry.occurrence_count > 1) {
      result += " (x" + String(entry.occurrence_count) + ")";
    }
    result += "\n";
    entries_added++;
  }
  
  return result;
}

String ErrorTracker::getErrorsByCategory(ErrorCategory category, uint8_t max_entries) const {
  String result = "";
  size_t entries_added = 0;
  
  size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
  
  for (size_t i = 0; i < error_count_ && entries_added < max_entries; i++) {
    size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
    const ErrorEntry& entry = error_buffer_[index];
    
    if (getCategory(entry.error_code) == category) {
      result += "[" + String(entry.timestamp) + "] ";
      result += "[" + String(entry.error_code) + "] ";
      result += String(entry.message);
      if (entry.occurrence_count > 1) {
        result += " (x" + String(entry.occurrence_count) + ")";
      }
      result += "\n";
      entries_added++;
    }
  }
  
  return result;
}

size_t ErrorTracker::getErrorCount() const {
  return error_count_;
}

size_t ErrorTracker::getErrorCountByCategory(ErrorCategory category) const {
  size_t count = 0;
  
  size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
  
  for (size_t i = 0; i < error_count_; i++) {
    size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
    if (getCategory(error_buffer_[index].error_code) == category) {
      count++;
    }
  }
  
  return count;
}

// ============================================
// ERROR STATUS
// ============================================
bool ErrorTracker::hasActiveErrors() const {
  return error_count_ > 0;
}

bool ErrorTracker::hasCriticalErrors() const {
  size_t start_index = (error_count_ < MAX_ERROR_ENTRIES) ? 0 : error_buffer_index_;
  
  for (size_t i = 0; i < error_count_; i++) {
    size_t index = (start_index + i) % MAX_ERROR_ENTRIES;
    if (error_buffer_[index].severity == ERROR_SEVERITY_CRITICAL) {
      return true;
    }
  }
  
  return false;
}

void ErrorTracker::clearErrors() {
  error_buffer_index_ = 0;
  error_count_ = 0;
  LOG_I(TAG, "ErrorTracker: Error history cleared");
}

// ============================================
// HELPER METHODS
// ============================================
void ErrorTracker::addToBuffer(uint16_t error_code, ErrorSeverity severity, const char* message) {
  // PKG-16 (INC-2026-04-11-ea5484): Null-safety defensive under OOM.
  // Arduino String::c_str() can surface as nullptr when an upstream concat
  // failed to allocate (observed in field log as '[ERRTRAK] <null>' bursts
  // immediately preceding a LoadProhibited crash). strcmp/strncpy on NULL is
  // undefined and has been the smoking-gun crash candidate. Fall back to a
  // constant literal so dedup and buffer writes stay well-defined even when
  // the caller lost its message under heap pressure.
  const char* safe_message = (message != nullptr) ? message : "<oom-fallback>";

  // Check if this error already exists in recent entries (last 5) - occurrence counting
  for (int i = 0; i < 5 && i < (int)error_count_; i++) {
    int check_index = (error_buffer_index_ - 1 - i + MAX_ERROR_ENTRIES) % MAX_ERROR_ENTRIES;
    ErrorEntry& entry = error_buffer_[check_index];
    
    if (entry.error_code == error_code && strcmp(entry.message, safe_message) == 0) {
      entry.occurrence_count++;
      entry.timestamp = millis();  // Update timestamp
      return;  // Don't add duplicate
    }
  }
  
  // Add new entry
  size_t index = error_buffer_index_;
  error_buffer_[index].timestamp = millis();
  error_buffer_[index].error_code = error_code;
  error_buffer_[index].severity = severity;
  strncpy(error_buffer_[index].message, safe_message, sizeof(error_buffer_[index].message) - 1);
  error_buffer_[index].message[sizeof(error_buffer_[index].message) - 1] = '\0';
  error_buffer_[index].occurrence_count = 1;
  
  // Advance circular buffer index
  error_buffer_index_ = (error_buffer_index_ + 1) % MAX_ERROR_ENTRIES;
  
  // Track total count (up to MAX_ERROR_ENTRIES)
  if (error_count_ < MAX_ERROR_ENTRIES) {
    error_count_++;
  }
}

void ErrorTracker::logErrorToLogger(uint16_t error_code, ErrorSeverity severity, const char* message) {
  // PKG-16: defensive against callers that pass nullptr (e.g. reason.c_str()
  // after failed String concat under OOM). Logger itself also guards, but we
  // make intent explicit here to produce a searchable '<oom-fallback>' marker
  // instead of an empty tail.
  const char* safe_message = (message != nullptr) ? message : "<oom-fallback>";
  String log_msg = "[" + String(error_code) + "] [" +
                   String(getCategoryString(error_code)) + "] " +
                   String(safe_message);

  switch (severity) {
    case ERROR_SEVERITY_WARNING:
      LOG_W(TAG, log_msg.c_str());
      break;
    case ERROR_SEVERITY_ERROR:
      LOG_E(TAG, log_msg.c_str());
      break;
    case ERROR_SEVERITY_CRITICAL:
      LOG_C(TAG, log_msg.c_str());
      break;
  }
}

// ============================================
// UTILITIES
// ============================================
const char* ErrorTracker::getCategoryString(uint16_t error_code) {
  if (error_code >= ERROR_APPLICATION && error_code < 5000) {
    return "APPLICATION";
  } else if (error_code >= ERROR_COMMUNICATION && error_code < 4000) {
    return "COMMUNICATION";
  } else if (error_code >= ERROR_SERVICE && error_code < 3000) {
    return "SERVICE";
  } else if (error_code >= ERROR_HARDWARE && error_code < 2000) {
    return "HARDWARE";
  } else {
    return "UNKNOWN";
  }
}

ErrorCategory ErrorTracker::getCategory(uint16_t error_code) {
  if (error_code >= ERROR_APPLICATION && error_code < 5000) {
    return ERROR_APPLICATION;
  } else if (error_code >= ERROR_COMMUNICATION && error_code < 4000) {
    return ERROR_COMMUNICATION;
  } else if (error_code >= ERROR_SERVICE && error_code < 3000) {
    return ERROR_SERVICE;
  } else {
    return ERROR_HARDWARE;
  }
}

// ============================================
// MQTT PUBLISHING (Observability - Phase 1-3)
// ============================================
void ErrorTracker::setMqttPublishCallback(MqttErrorPublishCallback callback, const String& esp_id) {
  mqtt_callback_ = callback;
  mqtt_esp_id_ = esp_id;
  mqtt_publishing_enabled_ = (callback != nullptr && esp_id.length() > 0);
  
  if (mqtt_publishing_enabled_) {
    LOG_I(TAG, "ErrorTracker: MQTT error publishing enabled for ESP " + esp_id);
  }
}

void ErrorTracker::clearMqttPublishCallback() {
  mqtt_callback_ = nullptr;
  mqtt_esp_id_ = "";
  mqtt_publishing_enabled_ = false;
  LOG_D(TAG, "ErrorTracker: MQTT error publishing disabled");
}

void ErrorTracker::publishErrorToMqtt(uint16_t error_code,
                                      ErrorSeverity severity,
                                      const char* message,
                                      const ErrorMqttContext* context) {
  // Guard: Skip if disabled or already publishing (recursion prevention)
  if (!mqtt_publishing_enabled_ || mqtt_publish_in_progress_) {
    return;
  }

  // Guard: Must have callback
  if (mqtt_callback_ == nullptr) {
    return;
  }

  // Rate-Limiting: max 1 MQTT publish per error code per 60s (F8)
  if (!shouldPublishError(error_code)) {
    return;
  }

  // Set recursion guard
  mqtt_publish_in_progress_ = true;

  // ✅ Phase 0 Fix: Use TopicBuilder for consistent topic generation
  const char* topic = TopicBuilder::buildSystemErrorTopic();

  // ✅ Defensive: Skip publish if topic generation failed (buffer overflow/encoding error)
  if (topic == nullptr || topic[0] == '\0') {
    mqtt_publish_in_progress_ = false;
    return;
  }

  // ✅ Phase 0 Fix: Use Unix timestamp from TimeManager
  time_t unix_ts = timeManager.getUnixTimestamp();
  // Fallback to 0 if NTP not synced (server will use server-time)

  // Build payload (JSON) - Server-compatible format
  String payload;
  payload.reserve(256);
  payload = "{";
  payload += "\"error_code\":";
  payload += String(error_code);
  payload += ",\"severity\":";
  payload += String(static_cast<int>(severity));
  payload += ",\"category\":\"";
  payload += getCategoryString(error_code);
  payload += "\",\"message\":\"";
  // Escape quotes in message for valid JSON
  String escaped_msg = String(message);
  escaped_msg.replace("\"", "\\\"");
  escaped_msg.replace("\n", "\\n");
  payload += escaped_msg;
  // ✅ Phase 0 Fix: Add context field (extensible for per-error diagnostics)
  payload += "\",\"context\":{";
  payload += "\"esp_id\":\"";
  payload += mqtt_esp_id_;
  payload += "\",\"uptime_ms\":";
  payload += String(millis());
  if (context != nullptr) {
    if (context->topic != nullptr && context->topic[0] != '\0') {
      String escaped_topic = String(context->topic);
      escaped_topic.replace("\"", "\\\"");
      escaped_topic.replace("\n", "\\n");
      payload += ",\"topic\":\"";
      payload += escaped_topic;
      payload += "\"";
    }
    if (context->has_gpio) {
      payload += ",\"gpio\":";
      payload += String(context->gpio);
    }
    if (context->sensor_type != nullptr && context->sensor_type[0] != '\0') {
      String escaped_sensor_type = String(context->sensor_type);
      escaped_sensor_type.replace("\"", "\\\"");
      escaped_sensor_type.replace("\n", "\\n");
      payload += ",\"sensor_type\":\"";
      payload += escaped_sensor_type;
      payload += "\"";
    }
    if (context->reason_class != nullptr && context->reason_class[0] != '\0') {
      String escaped_reason = String(context->reason_class);
      escaped_reason.replace("\"", "\\\"");
      escaped_reason.replace("\n", "\\n");
      payload += ",\"reason_class\":\"";
      payload += escaped_reason;
      payload += "\"";
    }
  }
  payload += "}";
  payload += ",\"ts\":";
  payload += String((unsigned long)unix_ts);
  payload += "}";

  // Fire-and-forget publish (no error handling - prevent recursion!)
  mqtt_callback_(topic, payload.c_str());

  // Clear recursion guard
  mqtt_publish_in_progress_ = false;
}
