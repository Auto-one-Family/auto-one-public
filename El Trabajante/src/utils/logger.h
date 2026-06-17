#ifndef UTILS_LOGGER_H
#define UTILS_LOGGER_H

#include <Arduino.h>

// ============================================
// LOG LEVELS
// ============================================
enum LogLevel {
  LOG_DEBUG = 0,
  LOG_INFO = 1,
  LOG_WARNING = 2,
  LOG_ERROR = 3,
  LOG_CRITICAL = 4
};

// ============================================
// LOG ENTRY STRUCTURE (Guide-konform: fixed size)
// TAG field: 3-8 character module identifier (ESP-IDF convention)
// ============================================
struct LogEntry {
  unsigned long timestamp;
  LogLevel level;
  char tag[12];             // Module TAG (ESP-IDF convention, e.g. "SENSOR")
  char message[128];        // Fixed size (no heap allocation)
};

// ============================================
// LOGGER CLASS
// ============================================
class Logger {
public:
  // Singleton Instance
  static Logger& getInstance();

  // Initialization (Guide-konform)
  void begin();

  // Configuration
  void setLogLevel(LogLevel level);
  void setSerialEnabled(bool enabled);

  // Primary API with TAG (ESP-IDF convention)
  // Format: [millis] [LEVEL   ] [TAG     ] message
  void log(LogLevel level, const char* tag, const char* message);
  void debug(const char* tag, const char* message);
  void info(const char* tag, const char* message);
  void warning(const char* tag, const char* message);
  void error(const char* tag, const char* message);
  void critical(const char* tag, const char* message);

  // Convenience Wrapper: String (Kompatibilitaet)
  inline void log(LogLevel level, const char* tag, const String& message) {
    log(level, tag, message.c_str());
  }
  inline void debug(const char* tag, const String& message) { debug(tag, message.c_str()); }
  inline void info(const char* tag, const String& message) { info(tag, message.c_str()); }
  inline void warning(const char* tag, const String& message) { warning(tag, message.c_str()); }
  inline void error(const char* tag, const String& message) { error(tag, message.c_str()); }
  inline void critical(const char* tag, const String& message) { critical(tag, message.c_str()); }

  // Log Management
  void clearLogs();
  String getLogs(LogLevel min_level = LOG_DEBUG, size_t max_entries = 100) const;
  size_t getLogCount() const;
  bool isLogLevelEnabled(LogLevel level) const;

  // Utilities
  static const char* getLogLevelString(LogLevel level);
  static LogLevel getLogLevelFromString(const char* level_str);

private:
  Logger();  // Private Constructor (Singleton)
  ~Logger() = default;
  Logger(const Logger&) = delete;
  Logger& operator=(const Logger&) = delete;

  // Internal state
  LogLevel current_log_level_;
  bool serial_enabled_;

  // Fixed Array Circular Buffer (Guide-konform)
  // Reduced from 100 to 50 entries — saves 7400 bytes BSS (MEM-OPT-1)
  static const size_t MAX_LOG_ENTRIES = 50;
  LogEntry log_buffer_[MAX_LOG_ENTRIES];
  size_t log_buffer_index_;
  size_t log_count_;

  // Helper methods
  void writeToSerial(LogLevel level, const char* tag, const char* message);
  void addToBuffer(LogLevel level, const char* tag, const char* message);
};

// ============================================
// GLOBAL LOGGER INSTANCE
// ============================================
extern Logger& logger;

// ============================================
// CONVENIENCE MACROS (TAG-based, ESP-IDF convention)
// Usage: static const char* TAG = "SENSOR";
//        LOG_I(TAG, "Sensor initialized");
// ============================================
#define LOG_D(tag, msg) logger.debug(tag, msg)
#define LOG_I(tag, msg) logger.info(tag, msg)
#define LOG_W(tag, msg) logger.warning(tag, msg)
#define LOG_E(tag, msg) logger.error(tag, msg)
#define LOG_C(tag, msg) logger.critical(tag, msg)

// Legacy single-arg macros — backward compatible, use "SYSTEM" as default TAG.
// These ensure existing code compiles without changes.
// Prefer TAG-based LOG_D/LOG_I/LOG_W/LOG_E/LOG_C for new code.
#define LOG_DEBUG(msg) logger.debug("SYSTEM", msg)
#define LOG_INFO(msg) logger.info("SYSTEM", msg)
#define LOG_WARNING(msg) logger.warning("SYSTEM", msg)
#define LOG_ERROR(msg) logger.error("SYSTEM", msg)
#define LOG_CRITICAL(msg) logger.critical("SYSTEM", msg)

#endif
