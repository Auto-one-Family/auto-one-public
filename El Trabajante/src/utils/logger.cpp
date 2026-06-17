#include "logger.h"

// ============================================
// GLOBAL LOGGER INSTANCE
// ============================================
Logger& logger = Logger::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
Logger& Logger::getInstance() {
  static Logger instance;
  return instance;
}

Logger::Logger()
  : current_log_level_(LOG_INFO),
    serial_enabled_(true),
    log_buffer_index_(0),
    log_count_(0) {
  // Initialize fixed buffer
  for (size_t i = 0; i < MAX_LOG_ENTRIES; i++) {
    log_buffer_[i].timestamp = 0;
    log_buffer_[i].level = LOG_INFO;
    log_buffer_[i].tag[0] = '\0';
    log_buffer_[i].message[0] = '\0';
  }
}

// ============================================
// INITIALIZATION (Guide-konform)
// ============================================
void Logger::begin() {
  if (serial_enabled_) {
    Serial.println("\n=== Logger System Initialized ===");
    Serial.printf("Log Level: %s\n", getLogLevelString(current_log_level_));
    Serial.printf("Buffer Size: %d entries\n", MAX_LOG_ENTRIES);
    Serial.println("=================================\n");
  }
}

// ============================================
// CONFIGURATION
// ============================================
void Logger::setLogLevel(LogLevel level) {
  current_log_level_ = level;
  if (serial_enabled_) {
    Serial.printf("[%10lu] [INFO    ] [LOGGER  ] Log level changed to %s\n",
                  millis(), getLogLevelString(level));
  }
}

void Logger::setSerialEnabled(bool enabled) {
  serial_enabled_ = enabled;
}

// ============================================
// PRIMARY API with TAG (ESP-IDF convention)
// ============================================
void Logger::log(LogLevel level, const char* tag, const char* message) {
  if (!isLogLevelEnabled(level)) {
    return;
  }

  const char* safe_tag = (tag != nullptr && tag[0] != '\0') ? tag : "LOGGER";
  const char* safe_message = (message != nullptr) ? message : "<null>";

  if (serial_enabled_) {
    writeToSerial(level, safe_tag, safe_message);
  }

  addToBuffer(level, safe_tag, safe_message);
}

void Logger::debug(const char* tag, const char* message) {
  log(LOG_DEBUG, tag, message);
}

void Logger::info(const char* tag, const char* message) {
  log(LOG_INFO, tag, message);
}

void Logger::warning(const char* tag, const char* message) {
  log(LOG_WARNING, tag, message);
}

void Logger::error(const char* tag, const char* message) {
  log(LOG_ERROR, tag, message);
}

void Logger::critical(const char* tag, const char* message) {
  log(LOG_CRITICAL, tag, message);
}

// ============================================
// LOG MANAGEMENT
// ============================================
void Logger::clearLogs() {
  log_buffer_index_ = 0;
  log_count_ = 0;
  if (serial_enabled_) {
    Serial.println("[LOGGER  ] Log buffer cleared");
  }
}

String Logger::getLogs(LogLevel min_level, size_t max_entries) const {
  String result = "";
  size_t entries_added = 0;

  // Start from oldest entry
  size_t start_index = (log_count_ < MAX_LOG_ENTRIES) ? 0 : log_buffer_index_;

  for (size_t i = 0; i < log_count_ && entries_added < max_entries; i++) {
    size_t index = (start_index + i) % MAX_LOG_ENTRIES;
    const LogEntry& entry = log_buffer_[index];

    if (entry.level >= min_level) {
      result += "[" + String(entry.timestamp) + "] ";
      result += "[" + String(getLogLevelString(entry.level)) + "] ";
      result += "[" + String(entry.tag) + "] ";
      result += String(entry.message) + "\n";
      entries_added++;
    }
  }

  return result;
}

size_t Logger::getLogCount() const {
  return log_count_;
}

bool Logger::isLogLevelEnabled(LogLevel level) const {
  return level >= current_log_level_;
}

// ============================================
// UTILITIES
// ============================================
const char* Logger::getLogLevelString(LogLevel level) {
  switch (level) {
    case LOG_DEBUG: return "DEBUG";
    case LOG_INFO: return "INFO";
    case LOG_WARNING: return "WARNING";
    case LOG_ERROR: return "ERROR";
    case LOG_CRITICAL: return "CRITICAL";
    default: return "UNKNOWN";
  }
}

LogLevel Logger::getLogLevelFromString(const char* level_str) {
  if (strcmp(level_str, "DEBUG") == 0) return LOG_DEBUG;
  if (strcmp(level_str, "INFO") == 0) return LOG_INFO;
  if (strcmp(level_str, "WARNING") == 0) return LOG_WARNING;
  if (strcmp(level_str, "ERROR") == 0) return LOG_ERROR;
  if (strcmp(level_str, "CRITICAL") == 0) return LOG_CRITICAL;
  return LOG_INFO;  // Default
}

// ============================================
// HELPER METHODS
// ============================================
void Logger::writeToSerial(LogLevel level, const char* tag, const char* message) {
  unsigned long timestamp = millis();
  const char* level_str = getLogLevelString(level);
  const char* safe_level = (level_str != nullptr) ? level_str : "UNKNOWN";
  const char* safe_tag = (tag != nullptr && tag[0] != '\0') ? tag : "LOGGER";
  const char* safe_message = (message != nullptr) ? message : "<null>";

  // Format: [millis] [LEVEL   ] [TAG     ] message
  Serial.printf("[%10lu] [%-8s] [%-8s] %s\n", timestamp, safe_level, safe_tag, safe_message);
}

void Logger::addToBuffer(LogLevel level, const char* tag, const char* message) {
  size_t index = log_buffer_index_;
  const char* safe_tag = (tag != nullptr && tag[0] != '\0') ? tag : "LOGGER";
  const char* safe_message = (message != nullptr) ? message : "<null>";

  log_buffer_[index].timestamp = millis();
  log_buffer_[index].level = level;
  strncpy(log_buffer_[index].tag, safe_tag, sizeof(log_buffer_[index].tag) - 1);
  log_buffer_[index].tag[sizeof(log_buffer_[index].tag) - 1] = '\0';
  strncpy(log_buffer_[index].message, safe_message, sizeof(log_buffer_[index].message) - 1);
  log_buffer_[index].message[sizeof(log_buffer_[index].message) - 1] = '\0';

  log_buffer_index_ = (log_buffer_index_ + 1) % MAX_LOG_ENTRIES;

  if (log_count_ < MAX_LOG_ENTRIES) {
    log_count_++;
  }
}
