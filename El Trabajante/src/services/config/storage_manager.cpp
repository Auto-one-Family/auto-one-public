#include "storage_manager.h"
#include "../../utils/logger.h"
#include <nvs_flash.h>
#include <esp_log.h>

// ESP-IDF TAG convention for structured logging
static const char* TAG = "NVS";

#ifdef CONFIG_ENABLE_THREAD_SAFETY
namespace {
class StorageLockGuard {
 public:
  explicit StorageLockGuard(SemaphoreHandle_t mutex) : mutex_(mutex), locked_(false) {
    if (mutex_) {
      locked_ = xSemaphoreTakeRecursive(mutex_, portMAX_DELAY) == pdTRUE;
      if (!locked_) {
        LOG_E(TAG, "StorageManager: Failed to acquire mutex");
      }
    } else {
      locked_ = true;
    }
  }

  ~StorageLockGuard() {
    if (mutex_ && locked_) {
      xSemaphoreGiveRecursive(mutex_);
    }
  }

  bool locked() const { return locked_; }

 private:
  SemaphoreHandle_t mutex_;
  bool locked_;
};
}  // namespace
#endif

// ============================================
// STATIC MEMBER INITIALIZATION
// ============================================
char StorageManager::string_buffer_[256];

// ============================================
// GLOBAL STORAGE MANAGER INSTANCE
// ============================================
StorageManager& storageManager = StorageManager::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
StorageManager& StorageManager::getInstance() {
  static StorageManager instance;
  return instance;
}

StorageManager::StorageManager()
  : namespace_open_(false)
  , transaction_active_(false)
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  , nvs_mutex_(nullptr)
  , namespace_owner_task_(nullptr)
#endif
  , namespace_conflict_count_(0)
  , no_session_access_count_(0)
{
  current_namespace_[0] = '\0';
}

// ============================================
// INITIALIZATION (Guide-konform)
// ============================================
bool StorageManager::begin() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (nvs_mutex_ == nullptr) {
    nvs_mutex_ = xSemaphoreCreateRecursiveMutex();
    if (nvs_mutex_ == nullptr) {
      LOG_E(TAG, "StorageManager: Failed to create mutex");
      return false;
    }
    LOG_I(TAG, "StorageManager: Thread-safety enabled (mutex created)");
  }
#endif
  namespace_open_ = false;
  transaction_active_ = false;
  current_namespace_[0] = '\0';
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  namespace_owner_task_ = nullptr;
#endif
  namespace_conflict_count_ = 0;
  no_session_access_count_ = 0;
  LOG_I(TAG, "StorageManager: Initialized");
  return true;
}

bool StorageManager::beginTransaction() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (nvs_mutex_ == nullptr) {
    return false;
  }
  if (xSemaphoreTakeRecursive(nvs_mutex_, pdMS_TO_TICKS(250)) != pdTRUE) {
    LOG_E(TAG, "StorageManager: beginTransaction lock timeout");
    return false;
  }
  namespace_owner_task_ = xTaskGetCurrentTaskHandle();
#endif
  transaction_active_ = true;
  return true;
}

void StorageManager::endTransaction() {
  if (namespace_open_) {
    preferences_.end();
    namespace_open_ = false;
    current_namespace_[0] = '\0';
#ifdef CONFIG_ENABLE_THREAD_SAFETY
    namespace_owner_task_ = nullptr;
    if (nvs_mutex_ != nullptr) {
      // Release namespace-level lock first; transaction lock is released below.
      xSemaphoreGiveRecursive(nvs_mutex_);
    }
#endif
  }

#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (transaction_active_ && nvs_mutex_ != nullptr) {
    xSemaphoreGiveRecursive(nvs_mutex_);
  }
#endif
  transaction_active_ = false;
}

bool StorageManager::isTransactionActive() const {
  return transaction_active_;
}

bool StorageManager::isSessionActive() const {
  return namespace_open_;
}

uint32_t StorageManager::getNamespaceConflictCount() const {
  return namespace_conflict_count_;
}

uint32_t StorageManager::getNoSessionAccessCount() const {
  return no_session_access_count_;
}

// ============================================
// NAMESPACE MANAGEMENT
// ============================================
bool StorageManager::beginNamespace(const char* namespace_name, bool read_only) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (nvs_mutex_ == nullptr) {
    LOG_E(TAG, "StorageManager: Mutex not initialized");
    return false;
  }
  if (xSemaphoreTakeRecursive(nvs_mutex_, pdMS_TO_TICKS(250)) != pdTRUE) {
    LOG_E(TAG, "StorageManager: beginNamespace lock timeout");
    return false;
  }
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
#endif
  if (namespace_open_) {
    recordNamespaceConflict();
    LOG_E(
        TAG,
        "StorageManager: Session conflict - namespace '" + String(current_namespace_) +
            "' still open; beginNamespace(" + String(namespace_name) + ") denied"
    );
#ifdef CONFIG_ENABLE_THREAD_SAFETY
    xSemaphoreGiveRecursive(nvs_mutex_);
#endif
    return false;
  }
  
  // The Arduino Preferences library calls log_e() internally when nvs_open fails,
  // even for expected NOT_FOUND cases on a new device. Suppress that noise for
  // read-only opens; write failures are real errors and must stay visible.
  // Both "Preferences" and "Preferences.cpp" are used as log tag depending on
  // Arduino ESP32 version (older versions use filename, newer use component name).
  if (read_only) {
    esp_log_level_set("Preferences", ESP_LOG_NONE);
    esp_log_level_set("Preferences.cpp", ESP_LOG_NONE);
  }
  bool ns_result = preferences_.begin(namespace_name, read_only);
  if (read_only) {
    esp_log_level_set("Preferences", ESP_LOG_WARN);
    esp_log_level_set("Preferences.cpp", ESP_LOG_WARN);
  }

  if (!ns_result) {
    if (read_only) {
      LOG_D(TAG, "StorageManager: Namespace not found (expected for new device): " + String(namespace_name));
    } else {
      LOG_E(TAG, "StorageManager: Failed to open namespace for write: " + String(namespace_name));
    }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
    xSemaphoreGiveRecursive(nvs_mutex_);
#endif
    return false;
  }
  
  namespace_open_ = true;
  strncpy(current_namespace_, namespace_name, sizeof(current_namespace_) - 1);
  current_namespace_[sizeof(current_namespace_) - 1] = '\0';
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  namespace_owner_task_ = current_task;
#endif
  
  LOG_D(TAG, "StorageManager: Opened namespace: " + String(namespace_name));
  return true;
}

void StorageManager::endNamespace() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  if (nvs_mutex_ == nullptr) {
    return;
  }
#endif
  if (namespace_open_) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
    TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
    if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
      LOG_W(
          TAG,
          "StorageManager: Task attempted to close namespace owned by another task: " +
              String(current_namespace_)
      );
      return;
    }
#endif
    preferences_.end();
    namespace_open_ = false;
    LOG_D(TAG, "StorageManager: Closed namespace: " + String(current_namespace_));
    current_namespace_[0] = '\0';
#ifdef CONFIG_ENABLE_THREAD_SAFETY
    namespace_owner_task_ = nullptr;
    xSemaphoreGiveRecursive(nvs_mutex_);
#endif
  }
}

bool StorageManager::ensureActiveSession(const char* operation, bool count_no_session) {
  if (!namespace_open_) {
    if (count_no_session) {
      recordNoSessionAccess();
    }
    LOG_E(TAG, "StorageManager: No active session for " + String(operation));
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    recordNamespaceConflict();
    LOG_W(TAG, "StorageManager: " + String(operation) + " denied, namespace owned by another task");
    return false;
  }
#endif
  return true;
}

void StorageManager::recordNamespaceConflict() {
  namespace_conflict_count_++;
}

void StorageManager::recordNoSessionAccess() {
  no_session_access_count_++;
}

// ============================================
// NVS QUOTA CHECK HELPER (Private)
// ============================================
bool StorageManager::checkNVSQuota(const char* key) {
  if (!namespace_open_) {
    return true;  // Skip check if no namespace open
  }

  size_t free_entries = preferences_.freeEntries();
  if (free_entries == 0) {
    LOG_E(TAG, "╔════════════════════════════════════════╗");
    LOG_E(TAG, "║  NVS FULL - CANNOT SAVE DATA!         ║");
    LOG_E(TAG, "╚════════════════════════════════════════╝");
    LOG_E(TAG, "NVS namespace '" + String(current_namespace_) + "' has 0 free entries");
    LOG_E(TAG, "Cannot write key: " + String(key));
    return false;
  } else if (free_entries < 10) {
    LOG_W(TAG, "╔════════════════════════════════════════╗");
    LOG_W(TAG, "║  NVS NEARLY FULL - " + String(free_entries) + " entries left        ║");
    LOG_W(TAG, "╚════════════════════════════════════════╝");
    LOG_W(TAG, "NVS namespace '" + String(current_namespace_) + "' low on space");
  }
  return true;
}

// ============================================
// PRIMARY API: const char* (Guide-konform)
// ============================================

// String operations
bool StorageManager::putString(const char* key, const char* value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putString");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putString denied, namespace owned by another task");
    return false;
  }
#endif

  // Check NVS quota before write
  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putString(key, value);
  if (bytes == 0 && strlen(value) > 0) {
    LOG_E(TAG, "StorageManager: Failed to write string key: " + String(key));
    return false;
  }

  LOG_D(TAG, "StorageManager: Write " + String(key) + " = " + String(value));
  return true;
}

const char* StorageManager::getString(const char* key, const char* default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getString");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getString denied, namespace owned by another task");
    return default_value;
  }
#endif
  
  String value = preferences_.getString(key, default_value ? default_value : "");
  strncpy(string_buffer_, value.c_str(), sizeof(string_buffer_) - 1);
  string_buffer_[sizeof(string_buffer_) - 1] = '\0';
  
  LOG_D(TAG, "StorageManager: Read " + String(key) + " = " + value);
  return string_buffer_;
}

// Integer operations
bool StorageManager::putInt(const char* key, int value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putInt");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putInt denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putInt(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write int key: " + String(key));
    return false;
  }
  
  LOG_D(TAG, "StorageManager: Write " + String(key) + " = " + String(value));
  return true;
}

int StorageManager::getInt(const char* key, int default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getInt");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getInt denied, namespace owned by another task");
    return default_value;
  }
#endif
  
  int value = preferences_.getInt(key, default_value);
  LOG_D(TAG, "StorageManager: Read " + String(key) + " = " + String(value));
  return value;
}

// UInt8 operations
bool StorageManager::putUInt8(const char* key, uint8_t value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putUInt8");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putUInt8 denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putUChar(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write uint8 key: " + String(key));
    return false;
  }
  
  return true;
}

uint8_t StorageManager::getUInt8(const char* key, uint8_t default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getUInt8");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getUInt8 denied, namespace owned by another task");
    return default_value;
  }
#endif
  
  return preferences_.getUChar(key, default_value);
}

// UInt16 operations
bool StorageManager::putUInt16(const char* key, uint16_t value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putUInt16");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putUInt16 denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putUShort(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write uint16 key: " + String(key));
    return false;
  }
  
  return true;
}

uint16_t StorageManager::getUInt16(const char* key, uint16_t default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getUInt16");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getUInt16 denied, namespace owned by another task");
    return default_value;
  }
#endif
  
  return preferences_.getUShort(key, default_value);
}

// Boolean operations
bool StorageManager::putBool(const char* key, bool value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putBool");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putBool denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putBool(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write bool key: " + String(key));
    return false;
  }
  
  return true;
}

bool StorageManager::getBool(const char* key, bool default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getBool");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getBool denied, namespace owned by another task");
    return default_value;
  }
#endif

  return preferences_.getBool(key, default_value);
}

// Float operations
bool StorageManager::putFloat(const char* key, float value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putFloat");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putFloat denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putFloat(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write float key: " + String(key));
    return false;
  }

  LOG_D(TAG, "StorageManager: Write " + String(key) + " = " + String(value, 4));
  return true;
}

float StorageManager::getFloat(const char* key, float default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getFloat");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getFloat denied, namespace owned by another task");
    return default_value;
  }
#endif

  float value = preferences_.getFloat(key, default_value);
  LOG_D(TAG, "StorageManager: Read " + String(key) + " = " + String(value, 4));
  return value;
}

// Unsigned long operations
bool StorageManager::putULong(const char* key, unsigned long value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for putULong");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: putULong denied, namespace owned by another task");
    return false;
  }
#endif

  if (!checkNVSQuota(key)) {
    return false;
  }

  size_t bytes = preferences_.putULong(key, value);
  if (bytes == 0) {
    LOG_E(TAG, "StorageManager: Failed to write ulong key: " + String(key));
    return false;
  }
  
  return true;
}

unsigned long StorageManager::getULong(const char* key, unsigned long default_value) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return default_value;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for getULong");
    return default_value;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: getULong denied, namespace owned by another task");
    return default_value;
  }
#endif
  
  return preferences_.getULong(key, default_value);
}

// ============================================
// NAMESPACE UTILITIES
// ============================================
bool StorageManager::clearNamespace() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for clear");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: clearNamespace denied, namespace owned by another task");
    return false;
  }
#endif
  
  bool success = preferences_.clear();
  if (success) {
    LOG_I(TAG, "StorageManager: Cleared namespace: " + String(current_namespace_));
  } else {
    LOG_E(TAG, "StorageManager: Failed to clear namespace: " + String(current_namespace_));
  }
  
  return success;
}

bool StorageManager::eraseKey(const char* key) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    LOG_E(TAG, "StorageManager: No namespace open for eraseKey");
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    LOG_W(TAG, "StorageManager: eraseKey denied, namespace owned by another task");
    return false;
  }
#endif

  bool success = preferences_.remove(key);
  if (success) {
    LOG_I(TAG, "StorageManager: Erased key: " + String(key));
  } else {
    // remove() returns false if key didn't exist, which is acceptable
    LOG_D(TAG, "StorageManager: Key not found or already erased: " + String(key));
  }

  // Return true even if key didn't exist (idempotent operation)
  return true;
}

bool StorageManager::eraseAll() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif

  LOG_W(TAG, "StorageManager: FACTORY RESET - Erasing ALL NVS data!");

  // Close any open namespace first
  if (namespace_open_) {
    preferences_.end();
    namespace_open_ = false;
    LOG_D(TAG, "StorageManager: Closed namespace before erase: " + String(current_namespace_));
    current_namespace_[0] = '\0';
  }

  // Erase entire NVS partition
  esp_err_t err = nvs_flash_erase();
  if (err != ESP_OK) {
    LOG_E(TAG, "StorageManager: Failed to erase NVS flash, error: " + String(err));
    return false;
  }

  // Re-initialize NVS after erase
  err = nvs_flash_init();
  if (err != ESP_OK) {
    LOG_E(TAG, "StorageManager: Failed to re-initialize NVS flash, error: " + String(err));
    return false;
  }

  LOG_I(TAG, "StorageManager: Factory reset complete - NVS erased and re-initialized");
  return true;
}

bool StorageManager::keyExists(const char* key) {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return false;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    return false;
  }
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  TaskHandle_t current_task = xTaskGetCurrentTaskHandle();
  if (namespace_owner_task_ != nullptr && namespace_owner_task_ != current_task) {
    return false;
  }
#endif
  
  return preferences_.isKey(key);
}

size_t StorageManager::getFreeEntries() {
#ifdef CONFIG_ENABLE_THREAD_SAFETY
  StorageLockGuard guard(nvs_mutex_);
  if (!guard.locked()) {
    return 0;
  }
#endif
  if (!namespace_open_) {
    recordNoSessionAccess();
    return 0;
  }
  
  return preferences_.freeEntries();
}
