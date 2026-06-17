#ifndef SERVICES_CONFIG_STORAGE_MANAGER_H
#define SERVICES_CONFIG_STORAGE_MANAGER_H

#include <Arduino.h>
#include <Preferences.h>

#ifdef CONFIG_ENABLE_THREAD_SAFETY
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#endif

// ============================================
// STORAGE MANAGER CLASS (Guide-konform)
// ============================================
class StorageManager {
public:
  // Singleton Instance
  static StorageManager& getInstance();
  
  // Initialization (Guide-konform)
  bool begin();
  
  // Namespace Management (const char* für API-Konsistenz)
  bool beginNamespace(const char* namespace_name, bool read_only = false);
  void endNamespace();
  bool beginTransaction();
  void endTransaction();
  bool isTransactionActive() const;
  bool isSessionActive() const;
  uint32_t getNamespaceConflictCount() const;
  uint32_t getNoSessionAccessCount() const;
  
  // Primary API: const char* (Guide-konform, zero-copy)
  bool putString(const char* key, const char* value);
  const char* getString(const char* key, const char* default_value = nullptr);
  bool putInt(const char* key, int value);
  int getInt(const char* key, int default_value = 0);
  bool putUInt8(const char* key, uint8_t value);
  uint8_t getUInt8(const char* key, uint8_t default_value = 0);
  bool putUInt16(const char* key, uint16_t value);
  uint16_t getUInt16(const char* key, uint16_t default_value = 0);
  bool putBool(const char* key, bool value);
  bool getBool(const char* key, bool default_value = false);
  bool putFloat(const char* key, float value);
  float getFloat(const char* key, float default_value = 0.0f);
  bool putULong(const char* key, unsigned long value);
  unsigned long getULong(const char* key, unsigned long default_value = 0);
  
  // Convenience Wrapper: String (Kompatibilität)
  inline bool putString(const char* key, const String& value) {
    return putString(key, value.c_str());
  }
  inline String getStringObj(const char* key, const String& default_value = "") {
    const char* result = getString(key, default_value.c_str());
    return result ? String(result) : default_value;
  }
  
  // Namespace Utilities
  bool clearNamespace();
  bool eraseKey(const char* key);
  bool eraseAll();
  bool keyExists(const char* key);
  size_t getFreeEntries();
  
private:
  StorageManager();  // Private Constructor (Singleton)
  ~StorageManager() = default;
  StorageManager(const StorageManager&) = delete;
  StorageManager& operator=(const StorageManager&) = delete;
  
  Preferences preferences_;
  bool namespace_open_;
  char current_namespace_[16];
  bool transaction_active_;

  // Static buffer für getString (Guide-konform)
  static char string_buffer_[256];

  // NVS Quota Check Helper
  bool checkNVSQuota(const char* key);
  bool ensureActiveSession(const char* operation, bool count_no_session = true);
  void recordNamespaceConflict();
  void recordNoSessionAccess();

#ifdef CONFIG_ENABLE_THREAD_SAFETY
  SemaphoreHandle_t nvs_mutex_;
  TaskHandle_t namespace_owner_task_;
#endif
  uint32_t namespace_conflict_count_;
  uint32_t no_session_access_count_;
};

// ============================================
// GLOBAL STORAGE MANAGER INSTANCE
// ============================================
extern StorageManager& storageManager;

#endif
