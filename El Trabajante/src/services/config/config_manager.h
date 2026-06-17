#ifndef SERVICES_CONFIG_CONFIG_MANAGER_H
#define SERVICES_CONFIG_CONFIG_MANAGER_H

#include <Arduino.h>
#include "../../models/system_types.h"
#include "../../models/sensor_types.h"
#include "../../models/actuator_types.h"

// ============================================
// CONFIG MANAGER CLASS (Phase 1 - Server-Centric)
// ============================================
class ConfigManager {
public:
  // Singleton Instance
  static ConfigManager& getInstance();
  
  // Initialization + Orchestrierung (Guide-konform)
  bool begin();
  bool loadAllConfigs();
  
  // WiFi Configuration
  bool loadWiFiConfig(WiFiConfig& config);
  bool saveWiFiConfig(const WiFiConfig& config);
  bool validateWiFiConfig(const WiFiConfig& config) const;
  void resetWiFiConfig();
  
  // Zone Configuration
  bool loadZoneConfig(KaiserZone& kaiser, MasterZone& master);
  bool saveZoneConfig(const KaiserZone& kaiser, const MasterZone& master);
  bool validateZoneConfig(const KaiserZone& kaiser) const;
  // Phase 7: Dynamic Zone Assignment
  bool updateZoneAssignment(const String& zone_id, const String& master_zone_id, 
                            const String& zone_name, const String& kaiser_id);
  
  // Subzone Configuration (Phase 9)
  bool saveSubzoneConfig(const SubzoneConfig& config);
  bool loadSubzoneConfig(const String& subzone_id, SubzoneConfig& config);
  bool loadAllSubzoneConfigs(SubzoneConfig configs[], uint8_t max_configs, uint8_t& loaded_count);
  bool removeSubzoneConfig(const String& subzone_id);
  bool validateSubzoneConfig(const SubzoneConfig& config) const;
  uint8_t getSubzoneCount() const;  // Returns count of configured subzones
  
  // System Configuration (NEU für Phase 1)
  bool loadSystemConfig(SystemConfig& config);
  bool saveSystemConfig(const SystemConfig& config);

  // ============================================
  // DEVICE APPROVAL STATUS (Phase 1: Pending Approval)
  // ============================================
  /**
   * @brief Check if device has been approved by server
   * @return true if device was approved, false if pending or rejected
   */
  bool isDeviceApproved() const;

  /**
   * @brief Set device approval status
   * @param approved true if approved, false if rejected/pending
   * @param timestamp Unix timestamp of approval decision (0 if pending)
   */
  void setDeviceApproved(bool approved, time_t timestamp = 0);

  /**
   * @brief Get approval timestamp
   * @return Unix timestamp when approval was granted (0 if not approved)
   */
  time_t getApprovalTimestamp() const;
  
  // ============================================
  // SENSOR CONFIGURATION (PHASE 4)
  // ============================================
  // Save single sensor config
  bool saveSensorConfig(const SensorConfig& config);
  
  // Save array of sensor configs
  bool saveSensorConfig(const SensorConfig* sensors, uint8_t count);
  
  // Load all sensor configs
  bool loadSensorConfig(SensorConfig sensors[], uint8_t max_sensors, uint8_t& loaded_count);
  
  // Remove sensor config (address-based for multi-sensor GPIOs)
  bool removeSensorConfig(uint8_t gpio, const String& onewire_address = "",
                          const String& sensor_type = "");
  
  // Validate sensor config
  bool validateSensorConfig(const SensorConfig& config) const;
  
  // Actuator configuration (Phase 5+)
  bool loadActuatorConfig(ActuatorConfig actuators[], uint8_t max_actuators, uint8_t& loaded_count);
  bool saveActuatorConfig(const ActuatorConfig actuators[], uint8_t actuator_count);
  bool validateActuatorConfig(const ActuatorConfig& config) const;
  
  // Configuration Status (Guide-konform)
  bool isConfigurationComplete() const;
  void printConfigurationStatus() const;
  
  // ============================================
  // DIAGNOSTICS (Observability - Phase 1-3 Integration)
  // ============================================
  /**
   * @brief Get configuration diagnostics as JSON string
   * 
   * Returns ESP status and configuration summary for server observability.
   * Used by Heartbeat to expose ESP state without direct hardware access.
   * 
   * @return JSON string with config_status fields
   * 
   * Example output:
   * {
   *   "wifi_configured": true,
   *   "zone_assigned": true,
   *   "sensor_count": 3,
   *   "actuator_count": 1,
   *   "subzone_count": 2,
   *   "nvs_errors": 0,
   *   "boot_count": 5
   * }
   */
  String getDiagnosticsJSON() const;
  
  // Accessors (cached in memory)
  const WiFiConfig& getWiFiConfig() const { return wifi_config_; }
  const KaiserZone& getKaiser() const { return kaiser_; }
  const MasterZone& getMasterZone() const { return master_; }
  const SystemConfig& getSystemConfig() const { return system_config_; }
  
  // Quick Access (cached values for TopicBuilder)
  String getKaiserId() const { return kaiser_.kaiser_id; }
  String getESPId() const { return system_config_.esp_id; }
  
private:
  ConfigManager();  // Private Constructor (Singleton)
  ~ConfigManager() = default;
  ConfigManager(const ConfigManager&) = delete;
  ConfigManager& operator=(const ConfigManager&) = delete;
  
  // Cached configurations (Phase 1 only)
  WiFiConfig wifi_config_;
  KaiserZone kaiser_;
  MasterZone master_;
  SystemConfig system_config_;
  
  // Status flags
  bool wifi_config_loaded_;
  bool zone_config_loaded_;
  bool system_config_loaded_;

  // ============================================
  // SUBZONE COUNT CACHE (BUG-005 FIX)
  // ============================================
  // Cached subzone count to avoid NVS access on every heartbeat (60s).
  // The ESP32 Preferences library logs ERROR when opening a non-existent
  // namespace in read-only mode, even though it's expected behavior for
  // new devices without subzones. Caching eliminates this repeated error.
  mutable uint8_t subzone_count_cache_;
  mutable bool subzone_count_initialized_;

  // Helper Methods
  void generateESPIdIfMissing();
  
  // ============================================
  // NVS MIGRATION HELPERS (2026-01-15 Refactoring)
  // ============================================
  // These methods transparently migrate legacy NVS keys (>15 chars) to
  // new compact keys (≤15 chars) for ESP32 NVS compatibility.
  // Migration happens automatically on first read.
  
  /**
   * @brief Reads NVS string with automatic migration from legacy key
   * @param new_key New short key name (≤15 chars)
   * @param old_key Old long key name (legacy, may be >15 chars)
   * @param default_value Default if both keys missing
   * @return String value (from new key, old key, or default)
   */
  String migrateReadString(const char* new_key, const char* old_key, 
                           const String& default_value);
  
  /**
   * @brief Reads bool with migration support
   */
  bool migrateReadBool(const char* new_key, const char* old_key, 
                       bool default_value);
  
  /**
   * @brief Reads uint8_t with migration support
   */
  uint8_t migrateReadUInt8(const char* new_key, const char* old_key, 
                           uint8_t default_value);
  
  /**
   * @brief Reads uint32_t with migration support
   */
  uint32_t migrateReadUInt32(const char* new_key, const char* old_key, 
                             uint32_t default_value);
  
  // ============================================
  // SUBZONE INDEX-MAP HELPERS (2026-01-15 Phase 1E-C)
  // ============================================
  // These methods manage the index-map for variable-length subzone IDs.
  // Pattern: "A:0,irr_A:1,climate_1:2" maps subzone IDs to numeric indices.
  
  /**
   * @brief Get index for subzone ID from index map
   * @param subzone_id Subzone ID to look up
   * @param index_map Current index map string
   * @return Index (0-99) or -1 if not found
   */
  int8_t getSubzoneIndex(const String& subzone_id, const String& index_map);
  
  /**
   * @brief Add subzone ID to index map
   * @param subzone_id Subzone ID to add
   * @param index_map Current index map (will be modified)
   * @return Assigned index or -1 if failed
   */
  int8_t addSubzoneToIndexMap(const String& subzone_id, String& index_map);
  
  /**
   * @brief Remove subzone ID from index map
   * @param subzone_id Subzone ID to remove
   * @param index_map Current index map (will be modified)
   * @return true if removed, false if not found
   */
  bool removeSubzoneFromIndexMap(const String& subzone_id, String& index_map);
};

// ============================================
// GLOBAL CONFIG MANAGER INSTANCE
// ============================================
extern ConfigManager& configManager;

#endif
