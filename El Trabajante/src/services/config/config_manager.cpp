#include "config_manager.h"
#include "storage_manager.h"
#include "../../utils/logger.h"
#include "../../utils/mqtt_broker_sanitize.h"
#include "../../utils/onewire_utils.h"  // For ROM-Code validation
#include "../../drivers/gpio_manager.h"
#include "../../error_handling/error_tracker.h"
#include "../../models/error_codes.h"
#include "../../models/sensor_registry.h"  // For I2C sensor detection
#include <WiFi.h>

// ESP-IDF TAG convention for structured logging
static const char* TAG = "CONFIG";

// ============================================
// GLOBAL CONFIG MANAGER INSTANCE
// ============================================
ConfigManager& configManager = ConfigManager::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
ConfigManager& ConfigManager::getInstance() {
  static ConfigManager instance;
  return instance;
}

ConfigManager::ConfigManager()
  : wifi_config_loaded_(false),
    zone_config_loaded_(false),
    system_config_loaded_(false),
    subzone_count_cache_(0),
    subzone_count_initialized_(true) {
}

// ============================================
// INITIALIZATION + ORCHESTRIERUNG (Guide-konform)
// ============================================
bool ConfigManager::begin() {
  wifi_config_loaded_ = false;
  zone_config_loaded_ = false;
  system_config_loaded_ = false;

  LOG_I(TAG, "ConfigManager: Initialized (Phase 1 - WiFi/Zone/System only)");
  return true;
}

bool ConfigManager::loadAllConfigs() {
  LOG_I(TAG, "ConfigManager: Loading Phase 1 configurations...");

  bool success = true;
  success &= loadWiFiConfig(wifi_config_);
  success &= loadZoneConfig(kaiser_, master_);
  success &= loadSystemConfig(system_config_);

  // Generate ESP ID if missing
  generateESPIdIfMissing();

  if (success) {
    LOG_I(TAG, "ConfigManager: All Phase 1 configurations loaded successfully");
  } else {
    LOG_W(TAG, "ConfigManager: Some configurations failed to load");
  }

  return success;
}

// ============================================
// WIFI CONFIGURATION
// ============================================
bool ConfigManager::loadWiFiConfig(WiFiConfig& config) {
  // ============================================
  // WOKWI SIMULATION MODE: Use compile-time credentials
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI_SIMULATION mode - using compile-time credentials");

    // WiFi credentials (Wokwi-GUEST is open network in Wokwi simulator)
    #ifdef WOKWI_WIFI_SSID
      config.ssid = WOKWI_WIFI_SSID;
    #else
      config.ssid = "Wokwi-GUEST";
    #endif

    #ifdef WOKWI_WIFI_PASSWORD
      config.password = WOKWI_WIFI_PASSWORD;
    #else
      config.password = "";
    #endif

    // MQTT broker (host.wokwi.internal routes to localhost or CI service)
    #ifdef WOKWI_MQTT_HOST
      config.server_address = WOKWI_MQTT_HOST;
    #else
      config.server_address = "host.wokwi.internal";
    #endif

    #ifdef WOKWI_MQTT_PORT
      config.mqtt_port = WOKWI_MQTT_PORT;
    #else
      config.mqtt_port = 1883;
    #endif

    // Anonymous MQTT mode for Wokwi
    config.mqtt_username = "";
    config.mqtt_password = "";
    config.configured = true;

    wifi_config_loaded_ = true;

    {
      const String addr_before = config.server_address;
      const uint16_t port_before = config.mqtt_port;
      sanitizeMqttBrokerHostAndPort(config.server_address, &config.mqtt_port);
      if (addr_before != config.server_address || port_before != config.mqtt_port) {
        LOG_W(TAG, "ConfigManager: WOKWI MQTT-Adresse normalisiert: " + addr_before + ":" +
                    String(port_before) + " -> " + config.server_address + ":" +
                    String(config.mqtt_port));
      }
    }

    LOG_I(TAG, "ConfigManager: Wokwi WiFi config - SSID: " + config.ssid +
             ", MQTT: " + config.server_address + ":" + String(config.mqtt_port));

    return true;
  #endif

  // ============================================
  // ONE-SHOT MQTT-ONLY (esp32_dev + ONESHOT_MQTT_HOST_ONLY=1): SSID/Pass aus NVS, nur Broker-IP
  // ============================================
  #ifdef ONESHOT_UPDATE_MQTT_ONLY
    if (!storageManager.beginNamespace("wifi_config", true)) {
      LOG_E(TAG, "ConfigManager: ONESHOT_UPDATE_MQTT_ONLY — wifi_config namespace failed");
      return false;
    }

    config.ssid = storageManager.getStringObj("ssid", "");
    config.password = storageManager.getStringObj("password", "");
    config.server_address = storageManager.getStringObj("server_address", "");
    config.mqtt_port = storageManager.getUInt16("mqtt_port", 1883);
    config.mqtt_username = storageManager.getStringObj("mqtt_username", "");
    config.mqtt_password = storageManager.getStringObj("mqtt_password", "");
    config.configured = storageManager.getBool("configured", false);
    storageManager.endNamespace();

    if (!config.configured || config.ssid.length() == 0) {
      LOG_E(TAG, "ConfigManager: ONESHOT_UPDATE_MQTT_ONLY — kein provisioniertes WiFi in NVS");
      return false;
    }

    const String old_server = config.server_address;
    const uint16_t old_port = config.mqtt_port;
    config.server_address = ONESHOT_MQTT_HOST;
    config.mqtt_port = ONESHOT_MQTT_PORT;

    sanitizeMqttBrokerHostAndPort(config.server_address, &config.mqtt_port);

    wifi_config_loaded_ = true;

    if (!saveWiFiConfig(config)) {
      LOG_W(TAG, "ConfigManager: ONESHOT_UPDATE_MQTT_ONLY — NVS persist fehlgeschlagen");
      return false;
    }

    LOG_I(TAG, "ConfigManager: ONESHOT_UPDATE_MQTT_ONLY — SSID unveraendert: " + config.ssid);
    LOG_I(TAG, "ConfigManager: ONESHOT_UPDATE_MQTT_ONLY — Broker: " + old_server + ":" +
             String(old_port) + " -> " + config.server_address + ":" + String(config.mqtt_port));

    return true;
  #endif

  // ============================================
  // ONE-SHOT FLASH (esp32_oneshot): Build-time WiFi + MQTT, then NVS persist
  // ============================================
  #ifdef ONESHOT_COMPILE_WIFI
    LOG_I(TAG, "ConfigManager: ONESHOT_COMPILE_WIFI — SSID/MQTT aus Build-Umgebung (Test/Flash-once)");

    config.ssid = ONESHOT_WIFI_SSID;
    config.password = ONESHOT_WIFI_PASSWORD;
    config.server_address = ONESHOT_MQTT_HOST;
    config.mqtt_port = ONESHOT_MQTT_PORT;
    config.mqtt_username = "";
    config.mqtt_password = "";
    config.configured = true;

    {
      const String addr_before = config.server_address;
      const uint16_t port_before = config.mqtt_port;
      sanitizeMqttBrokerHostAndPort(config.server_address, &config.mqtt_port);
      if (addr_before != config.server_address || port_before != config.mqtt_port) {
        LOG_W(TAG, "ConfigManager: ONESHOT MQTT-Adresse normalisiert: " + addr_before + ":" +
                    String(port_before) + " -> " + config.server_address + ":" +
                    String(config.mqtt_port));
      }
    }

    wifi_config_loaded_ = true;

    if (!saveWiFiConfig(config)) {
      LOG_W(TAG, "ONESHOT_COMPILE_WIFI: NVS persist (wifi_config) fehlgeschlagen");
    } else {
      LOG_I(TAG, "ONESHOT_COMPILE_WIFI: wifi_config in NVS gespeichert — weitere Builds nutzen esp32_dev");
    }

    return true;
  #endif

  // ============================================
  // NORMAL MODE: Load from NVS
  // ============================================
  if (!storageManager.beginNamespace("wifi_config", true)) {
    LOG_E(TAG, "ConfigManager: Failed to open wifi_config namespace");
    return false;
  }

  // Load WiFi settings
  config.ssid = storageManager.getStringObj("ssid", "");
  config.password = storageManager.getStringObj("password", "");

  // Load server settings
  config.server_address = storageManager.getStringObj("server_address", "192.168.0.198");
  config.mqtt_port = storageManager.getUInt16("mqtt_port", 8883);

  {
    const String addr_before = config.server_address;
    const uint16_t port_before = config.mqtt_port;
    sanitizeMqttBrokerHostAndPort(config.server_address, &config.mqtt_port);
    if (addr_before != config.server_address || port_before != config.mqtt_port) {
      LOG_W(TAG, "ConfigManager: NVS server_address normalisiert (MQTT-Transport): " + addr_before +
                  ":" + String(port_before) + " -> " + config.server_address + ":" +
                  String(config.mqtt_port));
    }
  }

  // Load credentials
  config.mqtt_username = storageManager.getStringObj("mqtt_username", "");
  config.mqtt_password = storageManager.getStringObj("mqtt_password", "");

  // Load status
  config.configured = storageManager.getBool("configured", false);

  storageManager.endNamespace();

  wifi_config_loaded_ = true;

  LOG_I(TAG, "ConfigManager: WiFi config loaded - SSID: " + config.ssid +
           ", Server: " + config.server_address);

  return true;
}

bool ConfigManager::saveWiFiConfig(const WiFiConfig& config) {
  LOG_I(TAG, "ConfigManager: Saving WiFi configuration...");

  if (!validateWiFiConfig(config)) {
    LOG_E(TAG, "ConfigManager: WiFi config validation failed, not saving");
    return false;
  }

  if (!storageManager.beginNamespace("wifi_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open wifi_config namespace for writing");
    return false;
  }

  bool success = true;
  // Save WiFi settings
  success &= storageManager.putString("ssid", config.ssid);
  success &= storageManager.putString("password", config.password);

  // Save server settings
  success &= storageManager.putString("server_address", config.server_address);
  success &= storageManager.putUInt16("mqtt_port", config.mqtt_port);

  // Save credentials
  success &= storageManager.putString("mqtt_username", config.mqtt_username);
  success &= storageManager.putString("mqtt_password", config.mqtt_password);

  // Save status
  success &= storageManager.putBool("configured", config.configured);

  storageManager.endNamespace();

  if (success) {
    wifi_config_ = config;
    LOG_I(TAG, "ConfigManager: WiFi configuration saved");
  } else {
    LOG_E(TAG, "ConfigManager: Failed to save WiFi configuration");
  }

  return success;
}

bool ConfigManager::validateWiFiConfig(const WiFiConfig& config) const {
  // SSID must not be empty
  if (config.ssid.length() == 0) {
    LOG_W(TAG, "ConfigManager: WiFi SSID is empty");
    return false;
  }

  // Server address must not be empty
  if (config.server_address.length() == 0) {
    LOG_W(TAG, "ConfigManager: Server address is empty");
    return false;
  }

  // MQTT port must be in valid range
  if (config.mqtt_port == 0 || config.mqtt_port > 65535) {
    LOG_W(TAG, "ConfigManager: Invalid MQTT port: " + String(config.mqtt_port));
    return false;
  }

  return true;
}

void ConfigManager::resetWiFiConfig() {
  LOG_I(TAG, "ConfigManager: Resetting WiFi configuration to defaults");

  if (!storageManager.beginNamespace("wifi_config", false)) {
    return;
  }

  storageManager.clearNamespace();
  storageManager.endNamespace();

  wifi_config_ = WiFiConfig();  // Reset to defaults
}

// ============================================
// NVS KEY DEFINITIONS - ZONE CONFIG
// ============================================
// 2026-01-15 Refactoring Phase 1E-D: All keys ≤15 chars for NVS compatibility
//
// New keys (compact, ≤15 chars):
// (Most zone keys were already OK, only legacy_* keys broken)
#define NVS_ZONE_ID             "zone_id"          // 7 chars ✅
#define NVS_ZONE_MASTER_ID      "master_zone_id"   // 14 chars ✅
#define NVS_ZONE_NAME           "zone_name"        // 9 chars ✅
#define NVS_ZONE_ASSIGNED       "zone_assigned"    // 13 chars ✅
#define NVS_ZONE_KAISER_ID      "kaiser_id"        // 9 chars ✅
#define NVS_ZONE_KAISER_NAME    "kaiser_name"      // 11 chars ✅
#define NVS_ZONE_CONNECTED      "connected"        // 9 chars ✅
#define NVS_ZONE_ID_GENERATED   "id_generated"     // 12 chars ✅
#define NVS_ZONE_IS_MASTER      "is_master_esp"    // 13 chars ✅

// Legacy keys - NEW COMPACT NAMES
#define NVS_ZONE_L_MZ_ID        "l_mz_id"          // 7 chars ✅ (NEW - was 21!)
#define NVS_ZONE_L_MZ_NAME      "l_mz_name"        // 9 chars ✅ (NEW - was 22!)

// Legacy keys (deprecated, >15 chars - kept for migration only)
#define NVS_ZONE_L_MZ_ID_OLD    "legacy_master_zone_id"    // 21 chars ❌ BROKEN
#define NVS_ZONE_L_MZ_NAME_OLD  "legacy_master_zone_name"  // 22 chars ❌ BROKEN

// NOTE: Legacy keys are deprecated (Phase 7 hierarchy migration).
// They are kept for backwards-compatibility with old firmware.
// l_mz = legacy_master_zone (shortened for NVS compatibility)
// These keys can be removed entirely in future firmware versions.

// ============================================
// ZONE CONFIGURATION
// ============================================
bool ConfigManager::loadZoneConfig(KaiserZone& kaiser, MasterZone& master) {
  LOG_I(TAG, "ConfigManager: Loading Zone configuration...");

  // false = read/write mode for migration writes
  if (!storageManager.beginNamespace("zone_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open zone_config namespace");
    return false;
  }

  // Load Hierarchical Zone Info (Phase 7: Dynamic Zones)
  kaiser.zone_id = storageManager.getStringObj(NVS_ZONE_ID, "");
  kaiser.master_zone_id = storageManager.getStringObj(NVS_ZONE_MASTER_ID, "");
  kaiser.zone_name = storageManager.getStringObj(NVS_ZONE_NAME, "");
  kaiser.zone_assigned = storageManager.getBool(NVS_ZONE_ASSIGNED, false);

  // Load Kaiser zone (Existing)
  // Default to "god" if not set (required for MQTT topics)
  kaiser.kaiser_id = storageManager.getStringObj(NVS_ZONE_KAISER_ID, "god");
  kaiser.kaiser_name = storageManager.getStringObj(NVS_ZONE_KAISER_NAME, "");
  kaiser.connected = storageManager.getBool(NVS_ZONE_CONNECTED, false);
  kaiser.id_generated = storageManager.getBool(NVS_ZONE_ID_GENERATED, false);

  // Load Master zone (Legacy - kept for compatibility) - MIGRATION
  master.master_zone_id = migrateReadString(
      NVS_ZONE_L_MZ_ID,      // New: l_mz_id (7 chars)
      NVS_ZONE_L_MZ_ID_OLD,  // Old: legacy_master_zone_id (21 chars)
      ""                      // Default: empty
  );

  master.master_zone_name = migrateReadString(
      NVS_ZONE_L_MZ_NAME,      // New: l_mz_name (9 chars)
      NVS_ZONE_L_MZ_NAME_OLD,  // Old: legacy_master_zone_name (22 chars)
      ""                        // Default: empty
  );

  master.is_master_esp = storageManager.getBool(NVS_ZONE_IS_MASTER, false);

  storageManager.endNamespace();

  zone_config_loaded_ = true;

  LOG_I(TAG, "ConfigManager: Zone config loaded - Zone: " + kaiser.zone_id +
           ", Master: " + kaiser.master_zone_id +
           ", Kaiser: " + kaiser.kaiser_id);

  return true;
}

bool ConfigManager::saveZoneConfig(const KaiserZone& kaiser, const MasterZone& master) {
  LOG_I(TAG, "ConfigManager: Saving Zone configuration...");

  // ============================================
  // WOKWI MODE: Skip NVS, store in RAM only
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - zone config stored in RAM only (NVS not supported)");
    return true;  // ✅ Signalisiere Erfolg - RAM-Config ist aktiv
  #endif

  if (!storageManager.beginNamespace("zone_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open zone_config namespace for writing");
    return false;
  }

  // 2026-01-15 Phase 1E-D: Use new compact keys (≤15 chars)
  // NOTE: Only writes to NEW keys - old keys become orphaned but harmless
  bool success = true;

  // Save Hierarchical Zone Info (Phase 7: Dynamic Zones)
  success &= storageManager.putString(NVS_ZONE_ID, kaiser.zone_id);
  success &= storageManager.putString(NVS_ZONE_MASTER_ID, kaiser.master_zone_id);
  success &= storageManager.putString(NVS_ZONE_NAME, kaiser.zone_name);
  success &= storageManager.putBool(NVS_ZONE_ASSIGNED, kaiser.zone_assigned);

  // Save Kaiser zone (Existing)
  success &= storageManager.putString(NVS_ZONE_KAISER_ID, kaiser.kaiser_id);
  success &= storageManager.putString(NVS_ZONE_KAISER_NAME, kaiser.kaiser_name);
  success &= storageManager.putBool(NVS_ZONE_CONNECTED, kaiser.connected);
  success &= storageManager.putBool(NVS_ZONE_ID_GENERATED, kaiser.id_generated);

  // Save Master zone (Legacy - kept for compatibility) - NEW KEYS
  success &= storageManager.putString(NVS_ZONE_L_MZ_ID, master.master_zone_id);      // ✅ NEW KEY
  success &= storageManager.putString(NVS_ZONE_L_MZ_NAME, master.master_zone_name);  // ✅ NEW KEY
  success &= storageManager.putBool(NVS_ZONE_IS_MASTER, master.is_master_esp);

  storageManager.endNamespace();

  if (success) {
    kaiser_ = kaiser;
    master_ = master;
    LOG_I(TAG, "ConfigManager: Zone configuration saved (Zone: " +
             kaiser.zone_id + ", Master: " + kaiser.master_zone_id + ")");
  } else {
    LOG_E(TAG, "ConfigManager: Failed to save Zone configuration");
  }

  return success;
}

/**
 * Validate zone configuration.
 *
 * Checks:
 * - kaiser_id must be set and non-empty
 * - kaiser_id length must be within limits (1-63 chars, MQTT topic limit)
 * - If zone is assigned, zone_id must be set
 *
 * NOTE: Does NOT validate zone_id format (server-side responsibility)
 */
bool ConfigManager::validateZoneConfig(const KaiserZone& kaiser) const {
  // 1. Kaiser ID required
  if (kaiser.kaiser_id.length() == 0) {
    LOG_W(TAG, "ConfigManager: Kaiser ID is empty");
    return false;
  }

  // 2. Kaiser ID length check (MQTT topic limit)
  if (kaiser.kaiser_id.length() > 63) {
    LOG_W(TAG, "ConfigManager: Kaiser ID too long (max 63 chars)");
    return false;
  }

  // 3. If zone assigned, zone_id must be set
  if (kaiser.zone_assigned && kaiser.zone_id.length() == 0) {
    LOG_W(TAG, "ConfigManager: Zone assigned but zone_id is empty");
    return false;
  }

  // 4. Zone_id length check (if not empty)
  if (kaiser.zone_id.length() > 0 && kaiser.zone_id.length() > 32) {
    LOG_W(TAG, "ConfigManager: Zone ID too long (max 32 chars)");
    return false;
  }

  // 5. Master_zone_id length check (if not empty)
  if (kaiser.master_zone_id.length() > 0 && kaiser.master_zone_id.length() > 32) {
    LOG_W(TAG, "ConfigManager: Master Zone ID too long (max 32 chars)");
    return false;
  }

  // 6. Zone_name length check (if not empty)
  if (kaiser.zone_name.length() > 0 && kaiser.zone_name.length() > 64) {
    LOG_W(TAG, "ConfigManager: Zone Name too long (max 64 chars)");
    return false;
  }

  // 7. Zone_id character whitelist (alphanumeric + underscore + hyphen)
  if (kaiser.zone_id.length() > 0) {
    for (size_t i = 0; i < kaiser.zone_id.length(); i++) {
      char c = kaiser.zone_id.charAt(i);
      if (!isalnum(c) && c != '_' && c != '-') {
        LOG_W(TAG, "ConfigManager: Zone ID contains invalid character: " + String(c));
        return false;
      }
    }
  }

  return true;
}

/**
 * Update zone assignment for this ESP.
 *
 * ARCHITECTURE NOTES:
 * - Multiple ESPs can be assigned to the same zone_id
 * - SubZones are assigned at sensor/actuator level, not ESP level
 * - Kaiser_id identifies the parent Kaiser device (default: "god")
 *
 * @param zone_id Primary zone identifier (e.g., "greenhouse_zone_1")
 * @param master_zone_id Parent zone for hierarchy (e.g., "greenhouse")
 * @param zone_name Human-readable zone name
 * @param kaiser_id ID of Kaiser managing this ESP (default: "god")
 * @return true if zone assignment updated successfully
 */
bool ConfigManager::updateZoneAssignment(const String& zone_id, const String& master_zone_id,
                                        const String& zone_name, const String& kaiser_id) {
  LOG_I(TAG, "ConfigManager: Updating zone assignment...");
  LOG_I(TAG, "  Zone ID: " + zone_id);
  LOG_I(TAG, "  Master Zone: " + master_zone_id);
  LOG_I(TAG, "  Zone Name: " + zone_name);
  LOG_I(TAG, "  Kaiser ID: " + kaiser_id);

  // WP1: Empty zone_id means zone removal
  bool is_removal = (zone_id.length() == 0);

  // Save current state for rollback (WP5)
  KaiserZone previous_kaiser = kaiser_;
  MasterZone previous_master = master_;

  // Update kaiser_ structure
  kaiser_.zone_id = zone_id;
  kaiser_.master_zone_id = master_zone_id;
  kaiser_.zone_name = zone_name;
  kaiser_.zone_assigned = !is_removal;  // WP1: false if removal, true if assignment

  // Update kaiser_id if provided
  if (kaiser_id.length() > 0) {
    kaiser_.kaiser_id = kaiser_id;
  }

  // WP5: Persist to NVS FIRST, then update cache on success
  bool success = saveZoneConfig(kaiser_, master_);

  if (success) {
    LOG_I(TAG, "ConfigManager: Zone " + String(is_removal ? "removal" : "assignment") + " updated successfully");
  } else {
    LOG_E(TAG, "ConfigManager: Failed to update zone " + String(is_removal ? "removal" : "assignment"));
    // WP5: Rollback cache on NVS failure
    kaiser_ = previous_kaiser;
    master_ = previous_master;
  }

  return success;
}

// ============================================
// SUBZONE CONFIGURATION (Phase 9)
// ============================================

// ============================================
// NVS KEY DEFINITIONS - SUBZONE CONFIG (Phase 1E-C)
// ============================================
// 2026-01-15 Refactoring Phase 1E-C: Indexed pattern for variable-length IDs
//
// PROBLEM: Old pattern subzone_{id}_{field} breaks with long IDs:
//   - subzone_A_parent = 16 chars ❌
//   - subzone_A_safe_mode = 19 chars ❌
//   - subzone_irr_A_safe_mode = 23 chars ❌
//
// SOLUTION: Use numeric index pattern sz_{index}_{field}:
//   - sz_0_par = 8 chars ✅
//   - sz_0_safe = 9 chars ✅
//   - Index-Map: "A:0,irr_A:1,climate_1:2"

// New keys (indexed, ≤15 chars):
#define NVS_SZ_INDEX_MAP   "sz_idx_map"     // Index map: "id:idx,id:idx,..."  (10 chars ✅)
#define NVS_SZ_COUNT       "sz_count"       // Number of subzones (8 chars ✅)
#define NVS_SZ_ID          "sz_%d_id"       // sz_0_id = 7 chars ✅ (sz_99_id = 8)
#define NVS_SZ_NAME        "sz_%d_name"     // sz_0_name = 9 chars ✅
#define NVS_SZ_PARENT      "sz_%d_par"      // sz_0_par = 8 chars ✅
#define NVS_SZ_SAFE        "sz_%d_safe"     // sz_0_safe = 9 chars ✅
#define NVS_SZ_TS          "sz_%d_ts"       // sz_0_ts = 6 chars ✅
#define NVS_SZ_GPIO        "sz_%d_gpio"     // sz_0_gpio = 9 chars ✅
#define NVS_SZ_SEN         "sz_%d_sen"      // cached sensor count in subzone
#define NVS_SZ_ACT         "sz_%d_act"      // cached actuator count in subzone

// Legacy keys (deprecated, variable length >15 chars for most IDs)
#define NVS_SZ_IDS_OLD     "subzone_ids"    // 11 chars ✅ (but content unchanged)
// Note: Old keys were "subzone_{id}_{field}" - CANNOT define as macro due to variable {id}
// Migration must dynamically construct old key names from actual subzone IDs

// ============================================
// SUBZONE INDEX-MAP HELPERS (Phase 1E-C)
// ============================================

/**
 * @brief Get index for subzone ID from index map
 *
 * Index map format: "id1:idx1,id2:idx2,id3:idx3"
 * Example: "A:0,irr_A:1,climate_1:2"
 *
 * @param subzone_id Subzone ID to look up
 * @param index_map Current index map string
 * @return Index (0-99) or -1 if not found
 */
int8_t ConfigManager::getSubzoneIndex(const String& subzone_id, const String& index_map) {
    if (index_map.length() == 0 || subzone_id.length() == 0) {
        return -1;
    }

    int start_idx = 0;
    while (start_idx < (int)index_map.length()) {
        int comma_idx = index_map.indexOf(',', start_idx);
        if (comma_idx == -1) comma_idx = index_map.length();

        String entry = index_map.substring(start_idx, comma_idx);
        int colon_idx = entry.indexOf(':');

        if (colon_idx > 0) {
            String id = entry.substring(0, colon_idx);
            id.trim();

            if (id == subzone_id) {
                String idx_str = entry.substring(colon_idx + 1);
                idx_str.trim();
                return (int8_t)idx_str.toInt();
            }
        }

        start_idx = comma_idx + 1;
    }

    return -1;
}

/**
 * @brief Add subzone ID to index map
 *
 * @param subzone_id Subzone ID to add
 * @param index_map Current index map (will be modified)
 * @return Assigned index or -1 if failed
 */
int8_t ConfigManager::addSubzoneToIndexMap(const String& subzone_id, String& index_map) {
    // Check if already in map
    int8_t existing_idx = getSubzoneIndex(subzone_id, index_map);
    if (existing_idx >= 0) {
        return existing_idx;
    }

    // Find next available index
    int8_t next_idx = 0;
    if (index_map.length() > 0) {
        // Count existing entries
        int start_idx = 0;
        while (start_idx < (int)index_map.length()) {
            int comma_idx = index_map.indexOf(',', start_idx);
            if (comma_idx == -1) comma_idx = index_map.length();
            next_idx++;
            start_idx = comma_idx + 1;
        }
    }

    // Add to map
    if (index_map.length() > 0) {
        index_map += ",";
    }
    index_map += subzone_id + ":" + String(next_idx);

    return next_idx;
}

/**
 * @brief Remove subzone ID from index map
 *
 * @param subzone_id Subzone ID to remove
 * @param index_map Current index map (will be modified)
 * @return true if removed, false if not found
 */
bool ConfigManager::removeSubzoneFromIndexMap(const String& subzone_id, String& index_map) {
    if (index_map.length() == 0) {
        return false;
    }

    String new_map = "";
    bool found = false;

    int start_idx = 0;
    while (start_idx < (int)index_map.length()) {
        int comma_idx = index_map.indexOf(',', start_idx);
        if (comma_idx == -1) comma_idx = index_map.length();

        String entry = index_map.substring(start_idx, comma_idx);
        int colon_idx = entry.indexOf(':');

        if (colon_idx > 0) {
            String id = entry.substring(0, colon_idx);
            id.trim();

            if (id != subzone_id) {
                // Keep this entry
                if (new_map.length() > 0) {
                    new_map += ",";
                }
                new_map += entry;
            } else {
                found = true;
            }
        }

        start_idx = comma_idx + 1;
    }

    index_map = new_map;
    return found;
}

// ============================================
// SUBZONE SAVE/LOAD/REMOVE FUNCTIONS (Phase 1E-C Indexed)
// ============================================

bool ConfigManager::saveSubzoneConfig(const SubzoneConfig& config) {
  LOG_I(TAG, "ConfigManager: Saving subzone config: " + config.subzone_id);

  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Failed to start subzone transaction");
    return false;
  }
  if (!storageManager.beginNamespace("subzone_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open subzone_config namespace");
    storageManager.endTransaction();
    return false;
  }

  // ============================================
  // PHASE 1E-C: Indexed Storage Pattern
  // Load index map and find/assign index for this subzone
  // ============================================
  String index_map = storageManager.getStringObj(NVS_SZ_INDEX_MAP, "");
  int8_t index = addSubzoneToIndexMap(config.subzone_id, index_map);

  if (index < 0 || index > 99) {
    LOG_E(TAG, "ConfigManager: Failed to assign index for subzone " + config.subzone_id);
    storageManager.endNamespace();
    storageManager.endTransaction();
    return false;
  }

  // Save updated index map
  bool success = storageManager.putString(NVS_SZ_INDEX_MAP, index_map);
  if (!success) {
    LOG_E(TAG, "ConfigManager: Failed to save subzone index map");
    storageManager.endNamespace();
    storageManager.endTransaction();
    return false;
  }

  LOG_D(TAG, "ConfigManager: Subzone " + config.subzone_id + " assigned index " + String(index));

  // Save subzone fields using index-based keys
  char key[16];

  // ID
  snprintf(key, sizeof(key), NVS_SZ_ID, index);
  success &= storageManager.putString(key, config.subzone_id);

  // Name
  snprintf(key, sizeof(key), NVS_SZ_NAME, index);
  success &= storageManager.putString(key, config.subzone_name);

  // Parent Zone
  snprintf(key, sizeof(key), NVS_SZ_PARENT, index);
  success &= storageManager.putString(key, config.parent_zone_id);

  // Safe Mode - CRITICAL!
  snprintf(key, sizeof(key), NVS_SZ_SAFE, index);
  success &= storageManager.putBool(key, config.safe_mode_active);

  // Timestamp
  snprintf(key, sizeof(key), NVS_SZ_TS, index);
  success &= storageManager.putULong(key, config.created_timestamp);

  // GPIO Array (comma-separated string)
  String gpio_string = "";
  for (size_t i = 0; i < config.assigned_gpios.size(); i++) {
    if (i > 0) gpio_string += ",";
    gpio_string += String(config.assigned_gpios[i]);
  }
  snprintf(key, sizeof(key), NVS_SZ_GPIO, index);
  success &= storageManager.putString(key, gpio_string);

  snprintf(key, sizeof(key), NVS_SZ_SEN, index);
  success &= storageManager.putUInt8(key, config.sensor_count);
  snprintf(key, sizeof(key), NVS_SZ_ACT, index);
  success &= storageManager.putUInt8(key, config.actuator_count);

  // Update count
  uint8_t count = 0;
  if (index_map.length() > 0) {
    count = 1;
    for (size_t i = 0; i < index_map.length(); i++) {
      if (index_map[i] == ',') count++;
    }
  }
  success &= storageManager.putUInt8(NVS_SZ_COUNT, count);

  // Also update legacy subzone_ids list for backwards compatibility
  String subzone_ids_str = storageManager.getStringObj(NVS_SZ_IDS_OLD, "");
  bool already_in_list = false;
  if (subzone_ids_str.length() > 0) {
    int start_idx = 0;
    while (start_idx < (int)subzone_ids_str.length()) {
      int comma_idx = subzone_ids_str.indexOf(',', start_idx);
      if (comma_idx == -1) comma_idx = subzone_ids_str.length();

      String existing_id = subzone_ids_str.substring(start_idx, comma_idx);
      existing_id.trim();

      if (existing_id == config.subzone_id) {
        already_in_list = true;
        break;
      }
      start_idx = comma_idx + 1;
    }
  }

  if (!already_in_list) {
    if (subzone_ids_str.length() > 0) {
      subzone_ids_str += ",";
    }
    subzone_ids_str += config.subzone_id;
    success &= storageManager.putString(NVS_SZ_IDS_OLD, subzone_ids_str);
  }

  storageManager.endNamespace();
  storageManager.endTransaction();

  if (success) {
    // BUG-005 FIX: Update cache after saving subzone
    subzone_count_cache_ = count;
    subzone_count_initialized_ = true;
    LOG_I(TAG, "ConfigManager: Subzone config saved successfully (index " + String(index) + ")");
  } else {
    LOG_E(TAG, "ConfigManager: Failed to save subzone config");
  }

  return success;
}

bool ConfigManager::loadSubzoneConfig(const String& subzone_id, SubzoneConfig& config) {
  // Open read-only — StorageManager suppressor silences NOT_FOUND noise when namespace
  // doesn't exist yet (new device or all subzones deleted). Migration path calls
  // saveSubzoneConfig() which opens the namespace separately with read/write.
  if (!storageManager.beginNamespace("subzone_config", true)) {
    return false;  // Namespace doesn't exist — no subzones configured
  }

  // ============================================
  // PHASE 1E-C: Indexed Pattern with Migration
  // Try new indexed pattern first, fallback to old pattern
  // ============================================

  // Try new indexed pattern
  String index_map = storageManager.getStringObj(NVS_SZ_INDEX_MAP, "");
  int8_t index = getSubzoneIndex(subzone_id, index_map);

  if (index >= 0) {
    // Load from new indexed keys
    char key[16];

    snprintf(key, sizeof(key), NVS_SZ_ID, index);
    config.subzone_id = storageManager.getStringObj(key, "");

    snprintf(key, sizeof(key), NVS_SZ_NAME, index);
    config.subzone_name = storageManager.getStringObj(key, "");

    snprintf(key, sizeof(key), NVS_SZ_PARENT, index);
    config.parent_zone_id = storageManager.getStringObj(key, "");

    snprintf(key, sizeof(key), NVS_SZ_SAFE, index);
    config.safe_mode_active = storageManager.getBool(key, true);

    snprintf(key, sizeof(key), NVS_SZ_TS, index);
    config.created_timestamp = storageManager.getULong(key, 0);

    snprintf(key, sizeof(key), NVS_SZ_GPIO, index);
    String gpio_string = storageManager.getStringObj(key, "");

    // Parse GPIO array
    config.assigned_gpios.clear();
    if (gpio_string.length() > 0) {
      int start_idx = 0;
      while (start_idx < (int)gpio_string.length()) {
        int comma_idx = gpio_string.indexOf(',', start_idx);
        if (comma_idx == -1) comma_idx = gpio_string.length();

        String gpio_str = gpio_string.substring(start_idx, comma_idx);
        gpio_str.trim();
        if (gpio_str.length() > 0) {
          config.assigned_gpios.push_back((uint8_t)gpio_str.toInt());
        }
        start_idx = comma_idx + 1;
      }
    }

    snprintf(key, sizeof(key), NVS_SZ_SEN, index);
    config.sensor_count = storageManager.getUInt8(key, 0);
    snprintf(key, sizeof(key), NVS_SZ_ACT, index);
    config.actuator_count = storageManager.getUInt8(key, 0);

    storageManager.endNamespace();
    return config.subzone_id.length() > 0;
  }

  // ============================================
  // MIGRATION: Try old pattern subzone_{id}_{field}
  // ============================================
  String key_base = "subzone_" + subzone_id;

  config.subzone_id = storageManager.getStringObj((key_base + "_id").c_str(), "");

  if (config.subzone_id.length() > 0) {
    // Old format found → MIGRATE
    LOG_I(TAG, "ConfigManager: Migrating subzone " + subzone_id + " to indexed pattern");

    config.subzone_name = storageManager.getStringObj((key_base + "_name").c_str(), "");
    config.parent_zone_id = storageManager.getStringObj((key_base + "_parent").c_str(), "");
    config.safe_mode_active = storageManager.getBool((key_base + "_safe_mode").c_str(), true);
    config.created_timestamp = storageManager.getULong((key_base + "_timestamp").c_str(), 0);

    // Parse GPIO array from old format
    String gpio_string = storageManager.getStringObj((key_base + "_gpios").c_str(), "");
    config.assigned_gpios.clear();
    if (gpio_string.length() > 0) {
      int start_idx = 0;
      while (start_idx < (int)gpio_string.length()) {
        int comma_idx = gpio_string.indexOf(',', start_idx);
        if (comma_idx == -1) comma_idx = gpio_string.length();

        String gpio_str = gpio_string.substring(start_idx, comma_idx);
        gpio_str.trim();
        if (gpio_str.length() > 0) {
          config.assigned_gpios.push_back((uint8_t)gpio_str.toInt());
        }
        start_idx = comma_idx + 1;
      }
    }

    storageManager.endNamespace();

    // Migrate to new format immediately
    saveSubzoneConfig(config);

    LOG_I(TAG, "ConfigManager: Subzone " + subzone_id + " migrated successfully");
    return true;
  }

  storageManager.endNamespace();
  return false;
}

bool ConfigManager::loadAllSubzoneConfigs(SubzoneConfig configs[], uint8_t max_configs, uint8_t& loaded_count) {
  loaded_count = 0;

  if (!storageManager.beginNamespace("subzone_config", true)) {
    LOG_W(TAG, "ConfigManager: No subzone_config namespace found");
    return false;
  }

  // ============================================
  // PHASE 1E-C: Try Index-Map first, then legacy list
  // ============================================

  // Try new index map pattern first
  String index_map = storageManager.getStringObj(NVS_SZ_INDEX_MAP, "");
  String subzone_ids_str = "";

  if (index_map.length() > 0) {
    // Extract IDs from index map format "id1:0,id2:1,id3:2"
    int start_idx = 0;
    while (start_idx < (int)index_map.length()) {
      int comma_idx = index_map.indexOf(',', start_idx);
      if (comma_idx == -1) comma_idx = index_map.length();

      String entry = index_map.substring(start_idx, comma_idx);
      int colon_idx = entry.indexOf(':');

      if (colon_idx > 0) {
        String id = entry.substring(0, colon_idx);
        id.trim();
        if (id.length() > 0) {
          if (subzone_ids_str.length() > 0) {
            subzone_ids_str += ",";
          }
          subzone_ids_str += id;
        }
      }
      start_idx = comma_idx + 1;
    }
    LOG_D(TAG, "ConfigManager: Using index map, found IDs: " + subzone_ids_str);
  }

  // Fallback to legacy subzone_ids list
  if (subzone_ids_str.length() == 0) {
    subzone_ids_str = storageManager.getStringObj(NVS_SZ_IDS_OLD, "");
    if (subzone_ids_str.length() > 0) {
      LOG_D(TAG, "ConfigManager: Using legacy subzone_ids list");
    }
  }

  storageManager.endNamespace();

  if (subzone_ids_str.length() == 0) {
    LOG_I(TAG, "ConfigManager: No subzones configured");
    return false;
  }

  // Parse comma-separated subzone ID list
  int start_idx = 0;
  while (start_idx < (int)subzone_ids_str.length() && loaded_count < max_configs) {
    int comma_idx = subzone_ids_str.indexOf(',', start_idx);
    if (comma_idx == -1) comma_idx = subzone_ids_str.length();

    String subzone_id = subzone_ids_str.substring(start_idx, comma_idx);
    subzone_id.trim();

    if (subzone_id.length() > 0) {
      SubzoneConfig config;
      if (loadSubzoneConfig(subzone_id, config) && config.subzone_id.length() > 0) {
        configs[loaded_count++] = config;
        LOG_D(TAG, "ConfigManager: Loaded subzone: " + subzone_id);
      }
    }

    start_idx = comma_idx + 1;
  }

  LOG_I(TAG, "ConfigManager: Loaded " + String(loaded_count) + " subzone configs");
  return loaded_count > 0;
}

bool ConfigManager::removeSubzoneConfig(const String& subzone_id) {
  LOG_I(TAG, "ConfigManager: Removing subzone config: " + subzone_id);

  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Failed to start subzone remove transaction");
    return false;
  }
  if (!storageManager.beginNamespace("subzone_config", false)) {
    storageManager.endTransaction();
    return false;
  }

  // ============================================
  // PHASE 1E-C: Indexed Pattern Removal
  // ============================================
  String index_map = storageManager.getStringObj(NVS_SZ_INDEX_MAP, "");
  int8_t index = getSubzoneIndex(subzone_id, index_map);
  uint8_t new_count = 0;  // remaining count after removal; updated in indexed path

  if (index >= 0) {
    // Clear indexed keys
    char key[16];

    snprintf(key, sizeof(key), NVS_SZ_ID, index);
    storageManager.putString(key, "");

    snprintf(key, sizeof(key), NVS_SZ_NAME, index);
    storageManager.putString(key, "");

    snprintf(key, sizeof(key), NVS_SZ_PARENT, index);
    storageManager.putString(key, "");

    snprintf(key, sizeof(key), NVS_SZ_SAFE, index);
    storageManager.putBool(key, true);

    snprintf(key, sizeof(key), NVS_SZ_TS, index);
    storageManager.putULong(key, 0);

    snprintf(key, sizeof(key), NVS_SZ_GPIO, index);
    storageManager.putString(key, "");

    snprintf(key, sizeof(key), NVS_SZ_SEN, index);
    storageManager.putUInt8(key, 0);
    snprintf(key, sizeof(key), NVS_SZ_ACT, index);
    storageManager.putUInt8(key, 0);

    // Remove from index map
    removeSubzoneFromIndexMap(subzone_id, index_map);
    storageManager.putString(NVS_SZ_INDEX_MAP, index_map);

    // Update count
    uint8_t count = 0;
    if (index_map.length() > 0) {
      count = 1;
      for (size_t i = 0; i < index_map.length(); i++) {
        if (index_map[i] == ',') count++;
      }
    }
    storageManager.putUInt8(NVS_SZ_COUNT, count);
    new_count = count;

    LOG_I(TAG, "ConfigManager: Subzone " + subzone_id + " removed (index " + String(index) + ")");
  } else {
    // Try old pattern cleanup
    String key_base = "subzone_" + subzone_id;
    storageManager.putString((key_base + "_id").c_str(), "");
    storageManager.putString((key_base + "_name").c_str(), "");
    storageManager.putString((key_base + "_parent").c_str(), "");
    storageManager.putString((key_base + "_gpios").c_str(), "");
    storageManager.putBool((key_base + "_safe_mode").c_str(), true);
    storageManager.putULong((key_base + "_timestamp").c_str(), 0);

    LOG_W(TAG, "ConfigManager: Subzone " + subzone_id + " not in index map, cleared old keys");
  }

  // Also remove from legacy subzone_ids list (for complete cleanup)
  String subzone_ids_str = storageManager.getStringObj(NVS_SZ_IDS_OLD, "");
  if (subzone_ids_str.length() > 0) {
    String new_ids_str = "";
    int start_idx = 0;

    while (start_idx < (int)subzone_ids_str.length()) {
      int comma_idx = subzone_ids_str.indexOf(',', start_idx);
      if (comma_idx == -1) comma_idx = subzone_ids_str.length();

      String existing_id = subzone_ids_str.substring(start_idx, comma_idx);
      existing_id.trim();

      if (existing_id.length() > 0 && existing_id != subzone_id) {
        if (new_ids_str.length() > 0) {
          new_ids_str += ",";
        }
        new_ids_str += existing_id;
      }

      start_idx = comma_idx + 1;
    }

    storageManager.putString(NVS_SZ_IDS_OLD, new_ids_str);
  }

  storageManager.endNamespace();
  storageManager.endTransaction();

  // Update in-memory cache directly — avoids NVS re-read on next getSubzoneCount() call.
  // new_count is 0 when the last subzone was removed or subzone_id was not in index map.
  subzone_count_cache_ = new_count;
  subzone_count_initialized_ = true;

  LOG_I(TAG, "ConfigManager: Subzone " + subzone_id + " removed");
  return true;
}

bool ConfigManager::validateSubzoneConfig(const SubzoneConfig& config) const {
  // Validation 1: subzone_id Format (1-32 chars, alphanumeric + underscore)
  if (config.subzone_id.length() == 0 || config.subzone_id.length() > 32) {
    LOG_W(TAG, "ConfigManager: Invalid subzone_id length");
    return false;
  }

  // Validation 2: parent_zone_id muss mit ESP-Zone übereinstimmen
  if (config.parent_zone_id.length() > 0 && config.parent_zone_id != kaiser_.zone_id) {
    LOG_W(TAG, "ConfigManager: parent_zone_id doesn't match ESP zone");
    return false;
  }

  // Validation 3: GPIOs müssen in safe pins list sein
  // Externe GPIO-Manager-Referenz wird benötigt
  extern GPIOManager& gpioManager;
  for (uint8_t gpio : config.assigned_gpios) {
    // Prüfe ob Pin verfügbar oder reserviert ist (dann ist es gültig)
    if (!gpioManager.isPinAvailable(gpio) && !gpioManager.isPinReserved(gpio)) {
      // Prüfe ob Pin überhaupt existiert (in pins_ vector)
      GPIOPinInfo pin_info = gpioManager.getPinInfo(gpio);
      if (pin_info.pin == 255) {  // Invalid pin marker
        LOG_W(TAG, "ConfigManager: GPIO " + String(gpio) + " not in safe pins list");
        return false;
      }
    }
  }

  return true;
}

uint8_t ConfigManager::getSubzoneCount() const {
  // ============================================
  // BUG-005 FIX: Use cached count to avoid NVS access every heartbeat
  // ============================================
  // The ESP32 Preferences library logs an ERROR when opening a non-existent
  // namespace in read-only mode (expected for new devices without subzones).
  // By caching the count, we only access NVS once instead of every 60 seconds.

  // Return cached value if already initialized
  if (subzone_count_initialized_) {
    return subzone_count_cache_;
  }

  // First-time access: Query NVS and cache the result
  // Note: If namespace doesn't exist, beginNamespace returns false (expected for new devices)
  if (!storageManager.beginNamespace("subzone_config", true)) {
    // Namespace doesn't exist = 0 subzones (expected for new device)
    subzone_count_cache_ = 0;
    subzone_count_initialized_ = true;
    return 0;
  }

  // Try new indexed pattern first (uses NVS cached count)
  uint8_t count = storageManager.getUInt8(NVS_SZ_COUNT, 0);

  if (count > 0) {
    storageManager.endNamespace();
    subzone_count_cache_ = count;
    subzone_count_initialized_ = true;
    return count;
  }

  // Fallback: Parse index map
  String index_map = storageManager.getStringObj(NVS_SZ_INDEX_MAP, "");
  if (index_map.length() > 0) {
    count = 1;
    for (size_t i = 0; i < index_map.length(); i++) {
      if (index_map[i] == ',') count++;
    }
    storageManager.endNamespace();
    subzone_count_cache_ = count;
    subzone_count_initialized_ = true;
    return count;
  }

  // Legacy fallback: Count from old subzone_ids list
  String subzone_ids_str = storageManager.getStringObj(NVS_SZ_IDS_OLD, "");
  storageManager.endNamespace();

  if (subzone_ids_str.length() == 0) {
    subzone_count_cache_ = 0;
    subzone_count_initialized_ = true;
    return 0;
  }

  count = 1;
  for (size_t i = 0; i < subzone_ids_str.length(); i++) {
    if (subzone_ids_str[i] == ',') {
      count++;
    }
  }

  subzone_count_cache_ = count;
  subzone_count_initialized_ = true;
  return count;
}

// ============================================
// NVS KEY DEFINITIONS - SYSTEM CONFIG
// ============================================
// 2026-01-15 Refactoring Phase 1E-D: All keys ≤15 chars for NVS compatibility
//
// New keys (compact, ≤15 chars):
#define NVS_SYS_ESP_ID      "esp_id"        // 6 chars ✅ (was OK already)
#define NVS_SYS_DEV_NAME    "device_name"   // 11 chars ✅ (was OK already)
#define NVS_SYS_STATE       "current_state" // 13 chars ✅ (was OK already)
#define NVS_SYS_SFM_REASON  "sfm_reason"    // 10 chars ✅ (NEW - was 16!)
#define NVS_SYS_BOOT_COUNT  "boot_count"    // 10 chars ✅ (was OK already)

// Legacy keys (deprecated, >15 chars - kept for migration only)
#define NVS_SYS_SFM_REASON_OLD  "safe_mode_reason"  // 16 chars ❌ BROKEN

// NOTE: Only "safe_mode_reason" was broken (16 chars).
// Other system keys were already ≤15 chars and don't need migration.
// sfm = safe_mode (shortened for NVS compatibility)

// ============================================
// SYSTEM CONFIGURATION (NEU für Phase 1)
// ============================================
bool ConfigManager::loadSystemConfig(SystemConfig& config) {
  LOG_I(TAG, "ConfigManager: Loading System configuration...");

  // false = read/write mode for migration writes
  if (!storageManager.beginNamespace("system_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open system_config namespace");
    return false;
  }

  // ESP ID (was OK already)
  config.esp_id = storageManager.getStringObj(NVS_SYS_ESP_ID, "");

  // Device Name (was OK already)
  config.device_name = storageManager.getStringObj(NVS_SYS_DEV_NAME, "ESP32");

  // Current State (was OK already)
  config.current_state = (SystemState)storageManager.getUInt8(NVS_SYS_STATE, STATE_BOOT);

  // Safe Mode Reason - MIGRATION (was broken!)
  config.safe_mode_reason = migrateReadString(
      NVS_SYS_SFM_REASON,      // New: sfm_reason (10 chars)
      NVS_SYS_SFM_REASON_OLD,  // Old: safe_mode_reason (16 chars)
      ""                        // Default: empty
  );

  // Boot Count (was OK already)
  config.boot_count = storageManager.getUInt16(NVS_SYS_BOOT_COUNT, 0);

  storageManager.endNamespace();

  system_config_loaded_ = true;

  LOG_I(TAG, "ConfigManager: System config loaded - ESP ID: " + config.esp_id);

  return true;
}

bool ConfigManager::saveSystemConfig(const SystemConfig& config) {
  LOG_I(TAG, "ConfigManager: Saving System configuration...");

  // ============================================
  // WOKWI MODE: Skip NVS, store in RAM only
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - system config stored in RAM only (NVS not supported)");
    return true;  // ✅ Signalisiere Erfolg - RAM-Config ist aktiv
  #endif

  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Failed to start system_config transaction");
    return false;
  }
  if (!storageManager.beginNamespace("system_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open system_config namespace for writing");
    storageManager.endTransaction();
    return false;
  }

  // 2026-01-15 Phase 1E-D: Use new compact keys (≤15 chars)
  // NOTE: Only writes to NEW keys - old keys become orphaned but harmless
  bool success = true;
  success &= storageManager.putString(NVS_SYS_ESP_ID, config.esp_id);
  success &= storageManager.putString(NVS_SYS_DEV_NAME, config.device_name);
  success &= storageManager.putUInt8(NVS_SYS_STATE, (uint8_t)config.current_state);
  success &= storageManager.putString(NVS_SYS_SFM_REASON, config.safe_mode_reason);  // ✅ NEW KEY
  success &= storageManager.putUInt16(NVS_SYS_BOOT_COUNT, config.boot_count);

  storageManager.endNamespace();
  storageManager.endTransaction();

  if (success) {
    system_config_ = config;
    LOG_I(TAG, "ConfigManager: System configuration saved");
  } else {
    LOG_E(TAG, "ConfigManager: Failed to save System configuration");
  }

  return success;
}

// ============================================
// DEVICE APPROVAL STATUS (Phase 1: Pending Approval)
// ============================================
// NVS Keys (compact, ≤15 chars)
static const char* NVS_DEV_APPROVED = "dev_appr";      // bool: approved status
static const char* NVS_APPR_TS = "appr_ts";            // uint32: approval timestamp

bool ConfigManager::isDeviceApproved() const {
  // Use system_config namespace for approval status
  if (!storageManager.beginNamespace("system_config", true)) {
    LOG_W(TAG, "ConfigManager: Cannot read approval status - namespace error");
    return false;  // Default to not approved on error
  }

  bool approved = storageManager.getBool(NVS_DEV_APPROVED, false);
  storageManager.endNamespace();

  return approved;
}

void ConfigManager::setDeviceApproved(bool approved, time_t timestamp) {
  // ============================================
  // INC-2026-04-11-ea5484-mqtt-transport-keepalive (PKG-04)
  // ============================================
  // Heartbeat-ACKs (status=online/approved) landen im Sekundentakt hier. Ohne
  // Dedup schreibt jeder ACK NVS, obwohl sich weder approved-Flag noch der
  // Timestamp-Slot fachlich aendern. Resultat waren repetitive
  // "Device approval saved"-Logs pro ACK plus unnoetiger Flash-Wear.
  //
  // Idempotenz-Guard: lese aktuellen NVS-State und schreibe nur, wenn sich
  // entweder der bool-State aendert oder ein fachlich sinnvoller
  // Timestamp-Wechsel vorliegt. Approval-Recovery (false -> true) schreibt.
  // Revocation (true -> false) schreibt. Wiederholte Liveness-ACKs bei
  // unveraendertem State bleiben RAM-only.
  //
  // Akzeptanz: ACK-Contract (status/handover_epoch) bleibt unveraendert —
  // der Aufrufer (main.cpp Heartbeat-ACK Branch) ruft diesen Setter weiter
  // bei jedem ACK; der NVS-Write wird hier geguarded.
  bool current_approved = isDeviceApproved();
  time_t current_ts = getApprovalTimestamp();

  bool state_changed = (current_approved != approved);
  // Timestamp-Update ist nur relevant wenn approved=true UND ein neuer,
  // plausibler Timestamp vorliegt (timestamp > 0) UND sich vom gespeicherten
  // unterscheidet. approved=false ignoriert Timestamp (cleared state).
  bool ts_changed = approved && timestamp > 0 && (time_t)current_ts != timestamp;

  if (!state_changed && !ts_changed) {
    LOG_D(TAG, "ConfigManager: Device approval unchanged (approved=" +
              String(approved ? "true" : "false") +
              ", ts=" + String((unsigned long)timestamp) +
              ") - skipping NVS write");
    return;
  }

  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Cannot save approval status - transaction error");
    return;
  }
  if (!storageManager.beginNamespace("system_config", false)) {
    LOG_E(TAG, "ConfigManager: Cannot save approval status - namespace error");
    storageManager.endTransaction();
    return;
  }

  // Schreibe Bool nur bei echtem Zustandswechsel — spart NVS-Seitenumschreiben.
  if (state_changed) {
    storageManager.putBool(NVS_DEV_APPROVED, approved);
  }
  if (ts_changed) {
    storageManager.putULong(NVS_APPR_TS, (unsigned long)timestamp);
  }

  storageManager.endNamespace();
  storageManager.endTransaction();

  if (approved) {
    LOG_I(TAG, "ConfigManager: Device approval saved (approved=true, ts=" +
             String((unsigned long)timestamp) +
             ", state_changed=" + String(state_changed ? "true" : "false") +
             ", ts_changed=" + String(ts_changed ? "true" : "false") + ")");
  } else {
    LOG_I(TAG, "ConfigManager: Device approval cleared (pending/rejected)");
  }
}

time_t ConfigManager::getApprovalTimestamp() const {
  if (!storageManager.beginNamespace("system_config", true)) {
    return 0;
  }

  unsigned long ts = storageManager.getULong(NVS_APPR_TS, 0);
  storageManager.endNamespace();

  return (time_t)ts;
}

// ============================================
// CONFIGURATION STATUS (Guide-konform)
// ============================================
bool ConfigManager::isConfigurationComplete() const {
  return wifi_config_loaded_ &&
         zone_config_loaded_ &&
         system_config_loaded_ &&
         validateWiFiConfig(wifi_config_) &&
         validateZoneConfig(kaiser_);
}

void ConfigManager::printConfigurationStatus() const {
  LOG_I(TAG, "=== Configuration Status (Phase 1) ===");
  LOG_I(TAG, "WiFi Config: " + String(wifi_config_loaded_ ? "✅ Loaded" : "❌ Not loaded"));
  LOG_I(TAG, "Zone Config: " + String(zone_config_loaded_ ? "✅ Loaded" : "❌ Not loaded"));
  LOG_I(TAG, "System Config: " + String(system_config_loaded_ ? "✅ Loaded" : "❌ Not loaded"));
  LOG_I(TAG, "Sensor/Actuator Config: ⚠️  Deferred to Phase 3 (Server-Centric)");
  LOG_I(TAG, "Configuration Complete: " + String(isConfigurationComplete() ? "✅ YES" : "❌ NO"));
  LOG_I(TAG, "======================================");
}

// ============================================
// DIAGNOSTICS (Observability - Phase 1-3 Integration)
// ============================================
String ConfigManager::getDiagnosticsJSON() const {
  String json;
  json.reserve(256);

  json = "{";

  // Configuration status
  json += "\"wifi_configured\":";
  json += (wifi_config_loaded_ && wifi_config_.configured ? "true" : "false");
  json += ",";

  json += "\"zone_assigned\":";
  json += (zone_config_loaded_ && kaiser_.zone_assigned ? "true" : "false");
  json += ",";

  json += "\"system_configured\":";
  json += (system_config_loaded_ ? "true" : "false");
  json += ",";

  // Subzone count (using public method)
  json += "\"subzone_count\":";
  json += String(getSubzoneCount());
  json += ",";

  // Boot count (from system config)
  json += "\"boot_count\":";
  json += String(system_config_.boot_count);
  json += ",";

  // Current state
  json += "\"state\":";
  json += String(static_cast<int>(system_config_.current_state));

  json += "}";

  return json;
}

// ============================================
// HELPER METHODS
// ============================================
void ConfigManager::generateESPIdIfMissing() {
  if (system_config_.esp_id.length() == 0) {
    // ============================================
    // WOKWI SIMULATION MODE: Use compile-time ESP ID
    // ============================================
    #ifdef WOKWI_SIMULATION
      #ifdef WOKWI_ESP_ID
        system_config_.esp_id = WOKWI_ESP_ID;
        LOG_I(TAG, "ConfigManager: Using Wokwi ESP ID: " + system_config_.esp_id);
      #else
        system_config_.esp_id = "ESP_WOKWI001";
        LOG_I(TAG, "ConfigManager: Using default Wokwi ESP ID: " + system_config_.esp_id);
      #endif
      saveSystemConfig(system_config_);
      return;
    #endif

    // ============================================
    // NORMAL MODE: Generate from MAC address
    // ============================================
    LOG_W(TAG, "ConfigManager: ESP ID not configured - generating from MAC address");

    WiFi.mode(WIFI_STA);  // Must be before macAddress()
    uint8_t mac[6];
    WiFi.macAddress(mac);

    char esp_id[32];
    snprintf(esp_id, sizeof(esp_id), "ESP_%02X%02X%02X",
             mac[3], mac[4], mac[5]);

    system_config_.esp_id = String(esp_id);
    saveSystemConfig(system_config_);

    LOG_I(TAG, "ConfigManager: Generated ESP ID: " + system_config_.esp_id);
  }
}

// ============================================
// SENSOR CONFIGURATION (PHASE 4)
// ============================================
// Helper function to build sensor key
static void buildSensorKey(char* buffer, size_t buffer_size, uint8_t index, const char* field) {
  snprintf(buffer, buffer_size, "sensor_%d_%s", index, field);
}

static void buildActuatorKey(char* buffer, size_t buffer_size, uint8_t index, const char* field) {
  snprintf(buffer, buffer_size, "actuator_%d_%s", index, field);
}

// ============================================
// NVS KEY DEFINITIONS - ACTUATOR CONFIG
// ============================================
// 2026-01-15 Refactoring: All keys ≤15 chars for NVS compatibility
//
// New keys (compact, ≤15 chars):
#define NVS_ACT_COUNT      "act_count"       // 9 chars ✅
#define NVS_ACT_GPIO       "act_%d_gpio"     // act_0_gpio = 10 chars ✅
#define NVS_ACT_AUX        "act_%d_aux"      // act_0_aux = 9 chars ✅
#define NVS_ACT_TYPE       "act_%d_type"     // act_0_type = 10 chars ✅
#define NVS_ACT_NAME       "act_%d_name"     // act_0_name = 10 chars ✅
#define NVS_ACT_SZ         "act_%d_sz"       // act_0_sz = 8 chars ✅
#define NVS_ACT_ACTIVE     "act_%d_act"      // act_0_act = 9 chars ✅
#define NVS_ACT_CRIT       "act_%d_crit"     // act_0_crit = 10 chars ✅
#define NVS_ACT_INV        "act_%d_inv"      // act_0_inv = 9 chars ✅
#define NVS_ACT_DEF_ST     "act_%d_def_st"   // act_0_def_st = 12 chars ✅
#define NVS_ACT_DEF_PWM    "act_%d_def_pwm"  // act_0_def_pwm = 13 chars ✅
#define NVS_ACT_FSOD       "act_%d_fsod"    // max 15 chars NVS limit
#define NVS_ACT_FSOD_OVR   "act_%d_fsod_o"
#define NVS_ACT_MAXRT      "act_%d_maxrt"   // act_0_maxrt = 13 chars ✅ — AUT-727: max_runtime cap (seconds)

// Legacy keys (deprecated, some >15 chars - kept for migration only)
#define NVS_ACT_COUNT_OLD      "actuator_count"       // 14 chars ✅ (was OK)
#define NVS_ACT_GPIO_OLD       "actuator_%d_gpio"     // 15 chars ⚠️ (borderline)
#define NVS_ACT_AUX_OLD        "actuator_%d_aux_gpio" // 19 chars ❌ BROKEN
#define NVS_ACT_TYPE_OLD       "actuator_%d_type"     // 15 chars ⚠️
#define NVS_ACT_NAME_OLD       "actuator_%d_name"     // 15 chars ⚠️
#define NVS_ACT_SZ_OLD         "actuator_%d_subzone"  // 18 chars ❌ BROKEN
#define NVS_ACT_ACTIVE_OLD     "actuator_%d_active"   // 17 chars ❌ BROKEN
#define NVS_ACT_CRIT_OLD       "actuator_%d_critical" // 19 chars ❌ BROKEN
#define NVS_ACT_INV_OLD        "actuator_%d_inverted" // 19 chars ❌ BROKEN
#define NVS_ACT_DEF_ST_OLD     "actuator_%d_default_state" // 24 chars ❌ BROKEN
#define NVS_ACT_DEF_PWM_OLD    "actuator_%d_default_pwm"   // 22 chars ❌ BROKEN

// ============================================
// NVS KEY DEFINITIONS - SENSOR CONFIG
// ============================================
// 2026-01-15 Refactoring Phase 1E-B: All keys ≤15 chars for NVS compatibility
//
// New keys (compact, ≤15 chars):
#define NVS_SEN_COUNT      "sen_count"       // 9 chars ✅
#define NVS_SEN_GPIO       "sen_%d_gpio"     // sen_0_gpio = 11 chars ✅ (sen_99_gpio = 12)
#define NVS_SEN_TYPE       "sen_%d_type"     // sen_0_type = 11 chars ✅
#define NVS_SEN_NAME       "sen_%d_name"     // sen_0_name = 11 chars ✅
#define NVS_SEN_SZ         "sen_%d_sz"       // sen_0_sz = 9 chars ✅ (CRITICAL: was broken!)
#define NVS_SEN_ACTIVE     "sen_%d_act"      // sen_0_act = 10 chars ✅
#define NVS_SEN_RAW        "sen_%d_raw"      // sen_0_raw = 10 chars ✅ (CRITICAL: was broken!)
#define NVS_SEN_MODE       "sen_%d_mode"     // sen_0_mode = 11 chars ✅
#define NVS_SEN_INTERVAL   "sen_%d_int"      // sen_0_int = 10 chars ✅ (CRITICAL: was broken!)
#define NVS_SEN_OW         "sen_%d_ow"       // sen_0_ow = 9 chars ✅ (OneWire ROM-Code)
#define NVS_SEN_I2C        "sen_%d_i2c"      // sen_0_i2c = 10 chars ✅ (I2C device address)
#define NVS_SEN_IF         "sen_%d_if"       // interface_type (UART, I2C, ...)
#define NVS_SEN_UART_RX    "sen_%d_urx"      // UART RX pin
#define NVS_SEN_UART_TX    "sen_%d_utx"      // UART TX pin
#define NVS_SEN_UART_BAUD  "sen_%d_ubd"      // UART baud rate
#define NVS_SEN_QOS        "sen_%d_qos"      // AUT-576: publish_qos (0=QoS-0, 1=QoS-1); 10 chars ✅
#define NVS_SEN_ADCSRC     "sen_%d_adcsrc"   // ADS1115: adc_source string; sen_99_adcsrc = 13 chars ✅
#define NVS_SEN_ADCCH      "sen_%d_adcch"    // ADS1115: adc_channel 0-3 (255=unset); 13 chars ✅
#define NVS_SEN_PGA        "sen_%d_pga"      // ADS1115: pga_gain string; sen_99_pga = 11 chars ✅

// Legacy keys (deprecated, some >15 chars - kept for migration only)
// NOTE: Old keys "sensor_%d_*" were OK for small indices but:
//   - sensor_0_subzone = 16 chars ❌ (always broken)
//   - sensor_0_raw_mode = 17 chars ❌ (always broken)
//   - sensor_0_interval = 17 chars ❌ (always broken)
//   - sensor_10_active = 16 chars ❌ (breaks at double-digit indices)
// New "sen_%d_*" schema saves 5+ chars and works for indices 0-99.
#define NVS_SEN_COUNT_OLD      "sensor_count"       // 12 chars ✅ (OK but rename for consistency)
#define NVS_SEN_GPIO_OLD       "sensor_%d_gpio"     // 13 chars ✅ (OK but fragile at i=10+)
#define NVS_SEN_TYPE_OLD       "sensor_%d_type"     // 13 chars ✅
#define NVS_SEN_NAME_OLD       "sensor_%d_name"     // 13 chars ✅
#define NVS_SEN_SZ_OLD         "sensor_%d_subzone"  // 16 chars ❌ BROKEN
#define NVS_SEN_ACTIVE_OLD     "sensor_%d_active"   // 15 chars ⚠️ (OK at limit, breaks at i>=10)
#define NVS_SEN_RAW_OLD        "sensor_%d_raw_mode" // 17 chars ❌ BROKEN
#define NVS_SEN_MODE_OLD       "sensor_%d_mode"     // 13 chars ✅
#define NVS_SEN_INTERVAL_OLD   "sensor_%d_interval" // 17 chars ❌ BROKEN

// ============================================
// NVS MIGRATION HELPERS (2026-01-15 Refactoring)
// ============================================
/**
 * @brief Reads NVS string with automatic migration from legacy key
 *
 * Tries new key first, falls back to old key if empty.
 * If old key has value, migrates to new key automatically.
 *
 * @param new_key New short key name (≤15 chars)
 * @param old_key Old long key name (legacy, may be >15 chars)
 * @param default_value Default if both keys missing
 * @return String value (from new key, old key, or default)
 *
 * @note Thread-safe via StorageManager mutex
 * @note Logs migration when fallback occurs
 * @note Uses keyExists() before getString() to prevent IDF [E] log for missing keys
 */
String ConfigManager::migrateReadString(const char* new_key,
                                        const char* old_key,
                                        const String& default_value) {
    // Try new key first (keyExists prevents nvs_get_str [E] log for missing keys)
    if (storageManager.keyExists(new_key)) {
        return storageManager.getStringObj(new_key, default_value);
    }

    // Skip old key if none defined
    if (old_key == nullptr || old_key[0] == '\0') {
        return default_value;
    }

    // Try old key (migration path)
    if (storageManager.keyExists(old_key)) {
        String value = storageManager.getStringObj(old_key, default_value);
        bool write_success = storageManager.putString(new_key, value);
        if (write_success) {
            LOG_I(TAG, "ConfigManager: Migrated NVS key '" +
                     String(old_key) + "' → '" + String(new_key) + "'");
        } else {
            LOG_W(TAG, "ConfigManager: Migration failed for '" +
                        String(old_key) + "' → '" + String(new_key) + "'");
        }
        return value;
    }

    // Both keys missing, return default
    return default_value;
}

/**
 * @brief Reads bool with migration support
 * @note For bool migration we check keyExists since getBool(default) can't detect missing
 */
bool ConfigManager::migrateReadBool(const char* new_key,
                                    const char* old_key,
                                    bool default_value) {
    // Try new key first
    if (storageManager.keyExists(new_key)) {
        return storageManager.getBool(new_key, default_value);
    }

    // Try old key (migration path)
    if (storageManager.keyExists(old_key)) {
        bool value = storageManager.getBool(old_key, default_value);
        bool write_success = storageManager.putBool(new_key, value);
        if (write_success) {
            LOG_I(TAG, "ConfigManager: Migrated bool key '" +
                     String(old_key) + "' → '" + String(new_key) + "'");
        }
        return value;
    }

    return default_value;
}

/**
 * @brief Reads uint8_t with migration support
 * @note Uses keyExists to detect presence before reading
 */
uint8_t ConfigManager::migrateReadUInt8(const char* new_key,
                                        const char* old_key,
                                        uint8_t default_value) {
    // Try new key first
    if (storageManager.keyExists(new_key)) {
        return storageManager.getUInt8(new_key, default_value);
    }

    // Try old key (migration path)
    if (storageManager.keyExists(old_key)) {
        uint8_t value = storageManager.getUInt8(old_key, default_value);
        bool write_success = storageManager.putUInt8(new_key, value);
        if (write_success) {
            LOG_I(TAG, "ConfigManager: Migrated uint8 key '" +
                     String(old_key) + "' → '" + String(new_key) + "'");
        }
        return value;
    }

    return default_value;
}

/**
 * @brief Reads uint32_t with migration support
 */
uint32_t ConfigManager::migrateReadUInt32(const char* new_key,
                                          const char* old_key,
                                          uint32_t default_value) {
    // Try new key first
    if (storageManager.keyExists(new_key)) {
        return storageManager.getULong(new_key, default_value);
    }

    // Try old key (migration path)
    if (storageManager.keyExists(old_key)) {
        uint32_t value = storageManager.getULong(old_key, default_value);
        bool write_success = storageManager.putULong(new_key, value);
        if (write_success) {
            LOG_I(TAG, "ConfigManager: Migrated uint32 key '" +
                     String(old_key) + "' → '" + String(new_key) + "'");
        }
        return value;
    }

    return default_value;
}

bool ConfigManager::saveSensorConfig(const SensorConfig& config) {
  // ============================================
  // VALIDATION FIRST (Security - auch für Wokwi!)
  // ============================================
  if (!validateSensorConfig(config)) {
    LOG_E(TAG, "ConfigManager: Sensor config validation failed");
    return false;
  }

  // ============================================
  // WOKWI MODE: Skip NVS, store in RAM only
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - sensor config stored in RAM only (NVS not supported)");
    LOG_D(TAG, "  Sensor: GPIO " + String(config.gpio) +
              ", Type: " + String(config.sensor_type) +
              ", Name: " + String(config.sensor_name));
    return true;  // ✅ Signalisiere Erfolg - RAM-Config ist aktiv
  #endif

  // ============================================
  // NORMAL MODE: Persist to NVS
  // 2026-01-15 Phase 1E-B: New key schema (≤15 chars) for NVS compatibility
  // NOTE: Only writes to NEW keys - old keys become orphaned but harmless
  // ============================================
  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Failed to start sensor_config transaction");
    return false;
  }
  if (!storageManager.beginNamespace("sensor_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open sensor_config namespace");
    storageManager.endTransaction();
    return false;
  }

  // Find index for this GPIO (or use next available)
  // Check new key first, then fallback to old key for migration scenario
  uint8_t sensor_count = storageManager.getUInt8(NVS_SEN_COUNT, 0);
  if (sensor_count == 0) {
    sensor_count = storageManager.getUInt8(NVS_SEN_COUNT_OLD, 0);
  }
  int8_t existing_index = -1;

  // Check if sensor already exists (match by GPIO + sensor_type for multi-value support)
  // Multi-value sensors (SHT31, BMP280, BME280) share the same GPIO/I2C address
  // but have different sensor_types (e.g. sht31_temp + sht31_humidity).
  // GPIO-only dedup would overwrite the first config with the second.
  char key[16];
  for (uint8_t i = 0; i < sensor_count; i++) {
    // Try new key first
    snprintf(key, sizeof(key), NVS_SEN_GPIO, i);
    uint8_t stored_gpio = storageManager.getUInt8(key, 255);
    if (stored_gpio == 255) {
      // Fallback to old key
      char old_key[32];
      snprintf(old_key, sizeof(old_key), NVS_SEN_GPIO_OLD, i);
      stored_gpio = storageManager.getUInt8(old_key, 255);
    }

    // Also check sensor_type to distinguish multi-value sensors on same GPIO
    snprintf(key, sizeof(key), NVS_SEN_TYPE, i);
    String stored_type;
    if (storageManager.keyExists(key)) {
      stored_type = storageManager.getString(key, "");
    } else {
      char old_key[32];
      snprintf(old_key, sizeof(old_key), NVS_SEN_TYPE_OLD, i);
      if (storageManager.keyExists(old_key)) {
        stored_type = storageManager.getString(old_key, "");
      }
    }

    if (stored_gpio == config.gpio && stored_type == config.sensor_type) {
      // R20-P2: For OneWire sensors, additionally match ROM-Code to distinguish
      // multiple sensors of same type on same GPIO (e.g. 2x DS18B20 on GPIO 4)
      if (config.onewire_address.length() > 0) {
        char owKey[16];
        snprintf(owKey, sizeof(owKey), NVS_SEN_OW, i);
        String stored_ow = storageManager.getString(owKey, "");
        if (stored_ow != config.onewire_address) {
          continue;  // Different sensor on same GPIO — skip
        }
      }
      // SHT31-FIX: For I2C sensors, additionally match i2c_address to distinguish
      // multiple devices of same type at different addresses (e.g. 2x SHT31 at 0x44 and 0x45).
      if (config.i2c_address != 0) {
        char i2cKey[16];
        snprintf(i2cKey, sizeof(i2cKey), NVS_SEN_I2C, i);
        uint8_t stored_i2c = storageManager.getUInt8(i2cKey, 0);
          if (stored_i2c != config.i2c_address) {
          continue;  // Different I2C device — skip
        }
      }
      existing_index = i;
      break;
    }
  }

  uint8_t index = (existing_index >= 0) ? existing_index : sensor_count;

  // Save sensor fields (ONLY to new keys!)
  bool success = true;

  // GPIO
  snprintf(key, sizeof(key), NVS_SEN_GPIO, index);
  success &= storageManager.putUInt8(key, config.gpio);

  // Sensor Type
  snprintf(key, sizeof(key), NVS_SEN_TYPE, index);
  success &= storageManager.putString(key, config.sensor_type);

  // Sensor Name
  snprintf(key, sizeof(key), NVS_SEN_NAME, index);
  success &= storageManager.putString(key, config.sensor_name);

  // Subzone ID
  snprintf(key, sizeof(key), NVS_SEN_SZ, index);
  success &= storageManager.putString(key, config.subzone_id);

  // Active Flag
  snprintf(key, sizeof(key), NVS_SEN_ACTIVE, index);
  success &= storageManager.putBool(key, config.active);

  // Raw Mode
  snprintf(key, sizeof(key), NVS_SEN_RAW, index);
  success &= storageManager.putBool(key, config.raw_mode);

  // Operating Mode
  snprintf(key, sizeof(key), NVS_SEN_MODE, index);
  success &= storageManager.putString(key, config.operating_mode);

  // Measurement Interval
  snprintf(key, sizeof(key), NVS_SEN_INTERVAL, index);
  success &= storageManager.putULong(key, config.measurement_interval_ms);

  // OneWire Address (if present - for DS18B20, DS18S20, DS1822)
  // Only save if non-empty to avoid wasting NVS space for non-OneWire sensors
  if (config.onewire_address.length() > 0) {
    // ============================================
    // ONEWIRE ROM-CODE VALIDATION (Phase 1-3 Integration)
    // ============================================
    // Defense-in-Depth: Validate before NVS write to prevent corrupt data

    // 1. Length validation (must be exactly 16 hex chars)
    if (config.onewire_address.length() != 16) {
      LOG_E(TAG, "ConfigManager: OneWire ROM-Code invalid length - expected 16, got " +
               String(config.onewire_address.length()) + " for sensor GPIO " + String(config.gpio));
      errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_LENGTH, ERROR_SEVERITY_ERROR,
                             ("ROM length " + String(config.onewire_address.length()) + " != 16").c_str());
      success = false;
      // Continue to save other fields - don't return early
    } else {
      // 2. Parse ROM-Code to validate hex format
      uint8_t rom[8];
      if (!OneWireUtils::hexStringToRom(config.onewire_address, rom)) {
        LOG_E(TAG, "ConfigManager: OneWire ROM-Code invalid format (non-hex chars): " +
                 config.onewire_address);
        errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_FORMAT, ERROR_SEVERITY_ERROR,
                               ("Invalid ROM format: " + config.onewire_address).c_str());
        success = false;
      } else {
        // 3. CRC validation (WARNING only - may be transmission error, let server decide)
        if (!OneWireUtils::isValidRom(rom)) {
          LOG_W(TAG, "ConfigManager: OneWire ROM-Code CRC invalid (may be fake/corrupted): " +
                     config.onewire_address + " - saving anyway for server validation");
          errorTracker.trackError(ERROR_ONEWIRE_INVALID_ROM_CRC, ERROR_SEVERITY_WARNING,
                                 ("ROM CRC invalid: " + config.onewire_address).c_str());
          // Don't set success=false - CRC errors are warnings, not hard failures
        }

        // 4. Save validated ROM-Code to NVS
        snprintf(key, sizeof(key), NVS_SEN_OW, index);
        if (!storageManager.putString(key, config.onewire_address)) {
          LOG_E(TAG, "ConfigManager: Failed to save OneWire ROM-Code to NVS");
          errorTracker.trackError(ERROR_NVS_WRITE_FAILED, ERROR_SEVERITY_ERROR,
                                 "OneWire ROM-Code NVS write failed");
          success = false;
        } else {
          LOG_D(TAG, "ConfigManager: Saved OneWire ROM-Code " + config.onewire_address +
                   " for sensor on GPIO " + String(config.gpio));
        }
      }
    }
  }

  // I2C Address: always write to NVS (including 0) to clear stale values pushed from server.
  // A config-push with i2c_address=0 (non-I2C sensor) must overwrite any stale NVS value
  // left from a previous I2C sensor on the same GPIO (e.g. SHT31 -> DS18B20 reconfiguration).
  snprintf(key, sizeof(key), NVS_SEN_I2C, index);
  success &= storageManager.putUInt8(key, config.i2c_address);

  // UART / interface fields (always write to clear stale NVS on reconfig)
  snprintf(key, sizeof(key), NVS_SEN_IF, index);
  success &= storageManager.putString(key, config.interface_type);

  snprintf(key, sizeof(key), NVS_SEN_UART_RX, index);
  success &= storageManager.putUInt8(key, config.uart_rx_pin);

  snprintf(key, sizeof(key), NVS_SEN_UART_TX, index);
  success &= storageManager.putUInt8(key, config.uart_tx_pin);

  snprintf(key, sizeof(key), NVS_SEN_UART_BAUD, index);
  success &= storageManager.putULong(key, config.uart_baud);

  // AUT-576: persist publish_qos so QoS-adaptive rule stays valid after reboot.
  // AUT-555 introduced publish_qos in SensorConfig but omitted NVS persistence;
  // after reboot loadSensorConfig() restored sensors with publish_qos=0 (default),
  // discarding the server-assigned QoS-1 for rule-trigger sensors.
  snprintf(key, sizeof(key), NVS_SEN_QOS, index);
  success &= storageManager.putUInt8(key, config.publish_qos);

  // ADS1115 external ADC fields (always write to clear stale NVS on reconfig).
  // A config-push reverting a sensor back to the internal ADC must overwrite any
  // stale ads1115 value left from a previous configuration. Stored as compact
  // uint8_t codes (adc_source 0/1, pga_gain = PGA bits 0-5).
  snprintf(key, sizeof(key), NVS_SEN_ADCSRC, index);
  success &= storageManager.putUInt8(key, config.adc_source);

  snprintf(key, sizeof(key), NVS_SEN_ADCCH, index);
  success &= storageManager.putUInt8(key, config.adc_channel);

  snprintf(key, sizeof(key), NVS_SEN_PGA, index);
  success &= storageManager.putUInt8(key, config.pga_gain);

  // Update count if new sensor (use new key only!)
  if (existing_index < 0) {
    success &= storageManager.putUInt8(NVS_SEN_COUNT, sensor_count + 1);
  }

  storageManager.endNamespace();
  storageManager.endTransaction();

  if (success) {
    LOG_I(TAG, "ConfigManager: Saved sensor config for GPIO " + String(config.gpio));
  } else {
    LOG_E(TAG, "ConfigManager: Failed to save sensor config");
  }

  return success;
}

bool ConfigManager::saveSensorConfig(const SensorConfig* sensors, uint8_t count) {
  // Input validation
  if (!sensors || count == 0) {
    return false;
  }

  // ============================================
  // WOKWI MODE: Save array in RAM only
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - saving " + String(count) +
             " sensor configs in RAM only (NVS not supported)");
    // Validate and log each sensor
    bool all_valid = true;
    for (uint8_t i = 0; i < count; i++) {
      if (!validateSensorConfig(sensors[i])) {
        LOG_W(TAG, "  Sensor " + String(i) + " validation failed, skipping");
        all_valid = false;
        continue;
      }
      LOG_D(TAG, "  [" + String(i) + "] GPIO " + String(sensors[i].gpio) +
                ": " + String(sensors[i].sensor_type));
    }
    return all_valid;  // ✅ RAM-Erfolg
  #endif

  // ============================================
  // NORMAL MODE: Loop and save via single-sensor method
  // ============================================
  bool success = true;
  for (uint8_t i = 0; i < count; i++) {
    success &= saveSensorConfig(sensors[i]);
  }

  return success;
}

bool ConfigManager::loadSensorConfig(SensorConfig sensors[], uint8_t max_sensors, uint8_t& loaded_count) {
  loaded_count = 0;

  // Input validation
  if (!sensors || max_sensors == 0) {
    LOG_E(TAG, "ConfigManager: Invalid input to loadSensorConfig");
    return false;
  }

  // ============================================
  // WOKWI MODE: No persistent config to load
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - no sensor config to load (NVS not supported)");
    LOG_D(TAG, "  Sensors will be configured via MQTT during runtime");
    return false;  // ✅ false = keine persistenten Daten vorhanden (korrekt!)
  #endif

  // ============================================
  // NORMAL MODE: Load from NVS with Migration
  // 2026-01-15 Phase 1E-B: New key schema for NVS 15-char limit
  // ============================================
  LOG_I(TAG, "ConfigManager: Loading Sensor configurations...");

  // false = read/write mode for migration writes
  if (!storageManager.beginNamespace("sensor_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open sensor_config namespace");
    return false;
  }

  // Load sensor count with migration support
  uint8_t sensor_count = storageManager.getUInt8(NVS_SEN_COUNT, 0);
  if (sensor_count == 0) {
    // Try legacy key
    sensor_count = storageManager.getUInt8(NVS_SEN_COUNT_OLD, 0);
    if (sensor_count > 0) {
      // Migrate count key
      storageManager.putUInt8(NVS_SEN_COUNT, sensor_count);
      LOG_I(TAG, "ConfigManager: Migrated sensor_count → sen_count");
    }
  }

  LOG_I(TAG, "ConfigManager: Found " + String(sensor_count) + " sensor(s) in NVS");

  if (sensor_count == 0) {
    storageManager.endNamespace();
    return true;  // No sensors configured
  }

  // Limit to max_sensors
  if (sensor_count > max_sensors) {
    LOG_W(TAG, "ConfigManager: Sensor count " + String(sensor_count) +
                " exceeds max_sensors (" + String(max_sensors) +
                "), limiting");
    sensor_count = max_sensors;
  }

  // Key buffers for new (≤15 chars) and old (legacy) keys
  char new_key[16];   // Max 15 + null terminator
  char old_key[32];   // Legacy keys up to 17 chars

  for (uint8_t i = 0; i < sensor_count && loaded_count < max_sensors; i++) {
    SensorConfig& config = sensors[loaded_count];

    // GPIO
    snprintf(new_key, sizeof(new_key), NVS_SEN_GPIO, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_GPIO_OLD, i);
    config.gpio = migrateReadUInt8(new_key, old_key, 255);

    // Sensor Type
    snprintf(new_key, sizeof(new_key), NVS_SEN_TYPE, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_TYPE_OLD, i);
    config.sensor_type = migrateReadString(new_key, old_key, "");
    // Normalize sensor_type to lowercase (Defense-in-Depth)
    // Ensures consistent casing regardless of what was stored in NVS
    config.sensor_type.toLowerCase();

    // Sensor Name
    snprintf(new_key, sizeof(new_key), NVS_SEN_NAME, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_NAME_OLD, i);
    config.sensor_name = migrateReadString(new_key, old_key, "");

    // Subzone ID - CRITICAL (was broken! 16 chars)
    snprintf(new_key, sizeof(new_key), NVS_SEN_SZ, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_SZ_OLD, i);
    config.subzone_id = migrateReadString(new_key, old_key, "");

    // Active Flag (breaks at i>=10 with old key)
    // Default: true — if a config is stored in NVS, the device was active.
    // Old key >15 chars at i>=10 → unreadable → must not deactivate on migration failure.
    snprintf(new_key, sizeof(new_key), NVS_SEN_ACTIVE, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_ACTIVE_OLD, i);
    config.active = migrateReadBool(new_key, old_key, true);

    // Raw Mode - CRITICAL (was broken! 17 chars)
    snprintf(new_key, sizeof(new_key), NVS_SEN_RAW, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_RAW_OLD, i);
    config.raw_mode = migrateReadBool(new_key, old_key, true);  // Default: Pi-Enhanced

    // Operating Mode (continuous/on_demand/scheduled/paused)
    snprintf(new_key, sizeof(new_key), NVS_SEN_MODE, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_MODE_OLD, i);
    config.operating_mode = migrateReadString(new_key, old_key, "continuous");

    // Measurement Interval - CRITICAL (was broken! 17 chars)
    snprintf(new_key, sizeof(new_key), NVS_SEN_INTERVAL, i);
    snprintf(old_key, sizeof(old_key), NVS_SEN_INTERVAL_OLD, i);
    config.measurement_interval_ms = migrateReadUInt32(new_key, old_key, 30000);  // Default: 30s

    // OneWire Address — only for ds18b20 (OneWire bus sensors)
    // I2C sensors (sht31_*, bmp280_*, bme280_*) have no OW address — skip to avoid NVS [E] noise
    snprintf(new_key, sizeof(new_key), NVS_SEN_OW, i);
    if (config.sensor_type == "ds18b20") {
        config.onewire_address = migrateReadString(new_key, "", "");
    } else {
        config.onewire_address = "";
    }

    // I2C Address (SHT31-FIX: load persisted address for multi-device support)
    // No legacy key — new feature. Default 0 = no I2C address stored (pre-fix firmware).
    snprintf(new_key, sizeof(new_key), NVS_SEN_I2C, i);
    config.i2c_address = storageManager.getUInt8(new_key, 0);

    snprintf(new_key, sizeof(new_key), NVS_SEN_IF, i);
    config.interface_type = storageManager.getStringObj(new_key, "");

    snprintf(new_key, sizeof(new_key), NVS_SEN_UART_RX, i);
    config.uart_rx_pin = storageManager.getUInt8(new_key, 255);

    snprintf(new_key, sizeof(new_key), NVS_SEN_UART_TX, i);
    config.uart_tx_pin = storageManager.getUInt8(new_key, 255);

    snprintf(new_key, sizeof(new_key), NVS_SEN_UART_BAUD, i);
    config.uart_baud = storageManager.getULong(new_key, 9600);

    // AUT-576: restore publish_qos from NVS (default 0 = QoS-0 for pre-AUT-576 entries).
    // Without NVS persistence the AUT-555 QoS-adaptive rule was lost after every reboot.
    snprintf(new_key, sizeof(new_key), NVS_SEN_QOS, i);
    config.publish_qos = storageManager.getUInt8(new_key, 0);

    // ADS1115 external ADC fields (default = internal ESP32 ADC for pre-feature entries)
    snprintf(new_key, sizeof(new_key), NVS_SEN_ADCSRC, i);
    config.adc_source = storageManager.getUInt8(new_key, AdcSourceCode::INTERNAL);
    snprintf(new_key, sizeof(new_key), NVS_SEN_ADCCH, i);
    config.adc_channel = storageManager.getUInt8(new_key, 255);
    snprintf(new_key, sizeof(new_key), NVS_SEN_PGA, i);
    config.pga_gain = storageManager.getUInt8(new_key, 1);

    // Reset runtime fields
    config.last_raw_value = 0;
    config.last_reading = 0;
    config.uart_configured_at_ms = 0;

    // Validate & Store
    if (config.gpio != 255 && config.sensor_type.length() > 0) {
      LOG_D(TAG, "ConfigManager: Loaded sensor " + String(i) +
               " - GPIO: " + String(config.gpio) +
               ", Type: " + config.sensor_type +
               ", Subzone: " + (config.subzone_id.isEmpty() ? "none" : config.subzone_id) +
               ", Active: " + String(config.active ? "true" : "false") +
               ", Raw: " + String(config.raw_mode ? "true" : "false") +
               ", Interval: " + String(config.measurement_interval_ms) + "ms" +
               ", I2C: " + (config.i2c_address ? ("0x" + String(config.i2c_address, HEX)) : "n/a") +
               ", IF: " + (config.interface_type.length() ? config.interface_type : "n/a") +
               (config.uart_rx_pin != 255 ? (", UART rx=" + String(config.uart_rx_pin) +
                " tx=" + String(config.uart_tx_pin) + " @" + String(config.uart_baud)) : ""));
      loaded_count++;
    } else {
      LOG_W(TAG, "ConfigManager: Skipped invalid sensor " + String(i));
    }
  }

  storageManager.endNamespace();

  LOG_I(TAG, "ConfigManager: Loaded " + String(loaded_count) + " sensor configurations");
  return loaded_count > 0 || sensor_count == 0;
}

bool ConfigManager::removeSensorConfig(uint8_t gpio, const String& onewire_address,
                                       const String& sensor_type) {
  // ============================================
  // 2026-01-15 Phase 1E-B: Use new key schema (≤15 chars)
  // R20-P2: Address-based matching for multi-sensor GPIOs
  // ============================================
  if (!storageManager.beginNamespace("sensor_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open sensor_config namespace");
    return false;
  }

  // Get sensor count (prefer new key, fallback to old)
  uint8_t sensor_count = storageManager.getUInt8(NVS_SEN_COUNT, 0);
  if (sensor_count == 0) {
    sensor_count = storageManager.getUInt8(NVS_SEN_COUNT_OLD, 0);
  }
  int8_t found_index = -1;

  // Find sensor index (check both new and old keys for robustness)
  char key[16];
  for (uint8_t i = 0; i < sensor_count; i++) {
    snprintf(key, sizeof(key), NVS_SEN_GPIO, i);
    uint8_t stored_gpio = storageManager.getUInt8(key, 255);
    if (stored_gpio == 255) {
      // Fallback to old key
      char old_key[32];
      snprintf(old_key, sizeof(old_key), NVS_SEN_GPIO_OLD, i);
      stored_gpio = storageManager.getUInt8(old_key, 255);
    }
    if (stored_gpio != gpio) continue;

    // R20-P2: For OneWire sensors, additionally match ROM-Code
    if (onewire_address.length() > 0) {
      char owKey[16];
      snprintf(owKey, sizeof(owKey), NVS_SEN_OW, i);
      String stored_ow = storageManager.getString(owKey, "");
      if (stored_ow != onewire_address) continue;
    }

    // R20-P2: For multi-value sensors, additionally match sensor_type
    if (sensor_type.length() > 0) {
      snprintf(key, sizeof(key), NVS_SEN_TYPE, i);
      String stored_type = storageManager.getString(key, "");
      if (stored_type.isEmpty()) {
        char old_key[32];
        snprintf(old_key, sizeof(old_key), NVS_SEN_TYPE_OLD, i);
        stored_type = storageManager.getString(old_key, "");
      }
      if (stored_type != sensor_type) continue;
    }

    found_index = i;
    break;
  }

  if (found_index < 0) {
    storageManager.endNamespace();
    LOG_W(TAG, "ConfigManager: Sensor config for GPIO " + String(gpio) + " not found");
    return false;
  }

  // Remove sensor by shifting remaining sensors (using new keys only!)
  char next_key[16];
  for (uint8_t i = found_index; i < sensor_count - 1; i++) {
    // Read from next index
    snprintf(next_key, sizeof(next_key), NVS_SEN_GPIO, i + 1);
    uint8_t next_gpio = storageManager.getUInt8(next_key, 255);

    snprintf(next_key, sizeof(next_key), NVS_SEN_TYPE, i + 1);
    String next_type = storageManager.getStringObj(next_key, "");

    snprintf(next_key, sizeof(next_key), NVS_SEN_NAME, i + 1);
    String next_name = storageManager.getStringObj(next_key, "");

    snprintf(next_key, sizeof(next_key), NVS_SEN_SZ, i + 1);
    String next_subzone = storageManager.getStringObj(next_key, "");

    snprintf(next_key, sizeof(next_key), NVS_SEN_ACTIVE, i + 1);
    bool next_active = storageManager.getBool(next_key, false);

    snprintf(next_key, sizeof(next_key), NVS_SEN_RAW, i + 1);
    bool next_raw_mode = storageManager.getBool(next_key, true);

    snprintf(next_key, sizeof(next_key), NVS_SEN_MODE, i + 1);
    String next_mode = storageManager.getStringObj(next_key, "continuous");

    snprintf(next_key, sizeof(next_key), NVS_SEN_INTERVAL, i + 1);
    uint32_t next_interval = storageManager.getULong(next_key, 30000);

    snprintf(next_key, sizeof(next_key), NVS_SEN_OW, i + 1);
    String next_ow = storageManager.getStringObj(next_key, "");

    snprintf(next_key, sizeof(next_key), NVS_SEN_I2C, i + 1);
    uint8_t next_i2c = storageManager.getUInt8(next_key, 0);

    snprintf(next_key, sizeof(next_key), NVS_SEN_IF, i + 1);
    String next_if = storageManager.getStringObj(next_key, "");

    snprintf(next_key, sizeof(next_key), NVS_SEN_UART_RX, i + 1);
    uint8_t next_urx = storageManager.getUInt8(next_key, 255);

    snprintf(next_key, sizeof(next_key), NVS_SEN_UART_TX, i + 1);
    uint8_t next_utx = storageManager.getUInt8(next_key, 255);

    snprintf(next_key, sizeof(next_key), NVS_SEN_UART_BAUD, i + 1);
    uint32_t next_ubd = storageManager.getULong(next_key, 9600);

    // Write to current index (new keys only!)
    snprintf(key, sizeof(key), NVS_SEN_GPIO, i);
    storageManager.putUInt8(key, next_gpio);

    snprintf(key, sizeof(key), NVS_SEN_TYPE, i);
    storageManager.putString(key, next_type);

    snprintf(key, sizeof(key), NVS_SEN_NAME, i);
    storageManager.putString(key, next_name);

    snprintf(key, sizeof(key), NVS_SEN_SZ, i);
    storageManager.putString(key, next_subzone);

    snprintf(key, sizeof(key), NVS_SEN_ACTIVE, i);
    storageManager.putBool(key, next_active);

    snprintf(key, sizeof(key), NVS_SEN_RAW, i);
    storageManager.putBool(key, next_raw_mode);

    snprintf(key, sizeof(key), NVS_SEN_MODE, i);
    storageManager.putString(key, next_mode);

    snprintf(key, sizeof(key), NVS_SEN_INTERVAL, i);
    storageManager.putULong(key, next_interval);

    snprintf(key, sizeof(key), NVS_SEN_OW, i);
    storageManager.putString(key, next_ow);

    snprintf(key, sizeof(key), NVS_SEN_I2C, i);
    storageManager.putUInt8(key, next_i2c);

    snprintf(key, sizeof(key), NVS_SEN_IF, i);
    storageManager.putString(key, next_if);

    snprintf(key, sizeof(key), NVS_SEN_UART_RX, i);
    storageManager.putUInt8(key, next_urx);

    snprintf(key, sizeof(key), NVS_SEN_UART_TX, i);
    storageManager.putUInt8(key, next_utx);

    snprintf(key, sizeof(key), NVS_SEN_UART_BAUD, i);
    storageManager.putULong(key, next_ubd);
  }

  // Clear last sensor (new keys only!)
  uint8_t last_idx = sensor_count - 1;

  snprintf(key, sizeof(key), NVS_SEN_GPIO, last_idx);
  storageManager.putUInt8(key, 255);

  snprintf(key, sizeof(key), NVS_SEN_TYPE, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_NAME, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_SZ, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_ACTIVE, last_idx);
  storageManager.putBool(key, false);

  snprintf(key, sizeof(key), NVS_SEN_RAW, last_idx);
  storageManager.putBool(key, true);

  snprintf(key, sizeof(key), NVS_SEN_MODE, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_INTERVAL, last_idx);
  storageManager.putULong(key, 30000);

  snprintf(key, sizeof(key), NVS_SEN_OW, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_I2C, last_idx);
  storageManager.putUInt8(key, 0);

  snprintf(key, sizeof(key), NVS_SEN_IF, last_idx);
  storageManager.putString(key, "");

  snprintf(key, sizeof(key), NVS_SEN_UART_RX, last_idx);
  storageManager.putUInt8(key, 255);

  snprintf(key, sizeof(key), NVS_SEN_UART_TX, last_idx);
  storageManager.putUInt8(key, 255);

  snprintf(key, sizeof(key), NVS_SEN_UART_BAUD, last_idx);
  storageManager.putULong(key, 9600);

  // Update count (new key only!)
  storageManager.putUInt8(NVS_SEN_COUNT, sensor_count - 1);

  storageManager.endNamespace();

  LOG_I(TAG, "ConfigManager: Removed sensor config for GPIO " + String(gpio));
  return true;
}

bool ConfigManager::validateSensorConfig(const SensorConfig& config) const {
  // Sensor type must not be empty (check first - needed for I2C lookup)
  if (config.sensor_type.length() == 0) {
    LOG_W(TAG, "ConfigManager: Sensor type is empty");
    return false;
  }

  // Check if it's an I2C sensor using SensorCapability Registry
  const SensorCapability* capability = findSensorCapability(config.sensor_type);
  bool is_i2c_sensor = (capability != nullptr && capability->is_i2c);
  bool is_uart_sensor = (capability != nullptr && capability->is_uart)
                        || config.interface_type.equalsIgnoreCase("UART")
                        || (config.uart_rx_pin != 255 && config.uart_tx_pin != 255
                            && config.uart_rx_pin != 0 && config.uart_tx_pin != 0);

  // For I2C sensors: Skip GPIO validation (they use shared I2C bus GPIO 21/22)
  if (is_i2c_sensor) {
    LOG_I(TAG, "ConfigManager: I2C sensor '" + config.sensor_type +
             "' - GPIO validation skipped (uses I2C bus)");
    return true;
  }

  // UART sensors: validate UART pins (gpio is logical slot only — no ADC)
  if (is_uart_sensor) {
    if (config.uart_rx_pin == 255 || config.uart_tx_pin == 255 ||
        config.uart_rx_pin == 0 || config.uart_tx_pin == 0) {
      LOG_W(TAG, "ConfigManager: UART sensor missing uart_rx_pin/uart_tx_pin");
      return false;
    }
    if (config.uart_baud < 9600 || config.uart_baud > 115200) {
      LOG_W(TAG, "ConfigManager: UART baud out of range: " + String(config.uart_baud));
      return false;
    }
    GPIOManager& gpio_mgr = GPIOManager::getInstance();
    if (gpio_mgr.isPinReserved(config.uart_rx_pin) || gpio_mgr.isPinReserved(config.uart_tx_pin)) {
      LOG_W(TAG, "ConfigManager: UART pins reserved (rx=" + String(config.uart_rx_pin) +
                   " tx=" + String(config.uart_tx_pin) + ")");
      return false;
    }
    LOG_I(TAG, "ConfigManager: UART sensor '" + config.sensor_type +
             "' rx=" + String(config.uart_rx_pin) + " tx=" + String(config.uart_tx_pin) +
             " baud=" + String(config.uart_baud));
    return true;
  }

  // For non-I2C sensors: Standard GPIO validation
  if (config.gpio == 255) {
    LOG_W(TAG, "ConfigManager: Invalid GPIO (255)");
    return false;
  }

  // GPIO must be in valid range (0-39 for ESP32)
  if (config.gpio > 39) {
    LOG_W(TAG, "ConfigManager: GPIO out of range: " + String(config.gpio));
    return false;
  }

  return true;
}

bool ConfigManager::saveActuatorConfig(const ActuatorConfig actuators[], uint8_t actuator_count) {
  LOG_I(TAG, "ConfigManager: Saving Actuator configurations...");

  // ============================================
  // WOKWI MODE: Save in RAM only
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - actuator config stored in RAM only (NVS not supported)");
    // Validate and log each actuator
    bool all_valid = true;
    for (uint8_t i = 0; i < actuator_count; i++) {
      const ActuatorConfig& config = actuators[i];
      if (!validateActuatorConfig(config)) {
        LOG_W(TAG, "  Actuator " + String(i) + " validation failed, skipping");
        all_valid = false;
        continue;
      }
      LOG_D(TAG, "  [" + String(i) + "] GPIO " + String(config.gpio) +
                ", Type: " + String(config.actuator_type) +
                ", Name: " + String(config.actuator_name));
    }
    return all_valid;  // ✅ RAM-Erfolg
  #endif

  // ============================================
  // NORMAL MODE: Persist to NVS
  // 2026-01-15: New key schema (≤15 chars) for NVS compatibility
  // NOTE: Only writes to NEW keys - old keys become orphaned but harmless
  // ============================================
  if (!storageManager.beginTransaction()) {
    LOG_E(TAG, "ConfigManager: Failed to start actuator_config transaction");
    return false;
  }
  if (!storageManager.beginNamespace("actuator_config", false)) {
    LOG_E(TAG, "ConfigManager: Failed to open actuator_config namespace for writing");
    storageManager.endTransaction();
    return false;
  }

  // Save count with new key
  bool success = storageManager.putUInt8(NVS_ACT_COUNT, actuator_count);

  if (!success) {
    LOG_E(TAG, "ConfigManager: Failed to save actuator count");
    storageManager.endNamespace();
    storageManager.endTransaction();
    return false;
  }

  // Key buffer for new keys only (≤15 chars)
  char key[16];

  for (uint8_t i = 0; i < actuator_count; i++) {
    const ActuatorConfig& config = actuators[i];

    if (!validateActuatorConfig(config)) {
      LOG_W(TAG, "ConfigManager: Skipping invalid actuator " + String(i));
      continue;
    }

    // GPIO (Primary Pin)
    snprintf(key, sizeof(key), NVS_ACT_GPIO, i);
    success &= storageManager.putUInt8(key, config.gpio);

    // Aux GPIO (H-Bridge, Valves)
    snprintf(key, sizeof(key), NVS_ACT_AUX, i);
    success &= storageManager.putUInt8(key, config.aux_gpio);

    // Actuator Type
    snprintf(key, sizeof(key), NVS_ACT_TYPE, i);
    success &= storageManager.putString(key, config.actuator_type);

    // Actuator Name
    snprintf(key, sizeof(key), NVS_ACT_NAME, i);
    success &= storageManager.putString(key, config.actuator_name);

    // Subzone ID
    snprintf(key, sizeof(key), NVS_ACT_SZ, i);
    success &= storageManager.putString(key, config.subzone_id);

    // Active Flag
    snprintf(key, sizeof(key), NVS_ACT_ACTIVE, i);
    success &= storageManager.putBool(key, config.active);

    // Critical Flag (Safety!)
    snprintf(key, sizeof(key), NVS_ACT_CRIT, i);
    success &= storageManager.putBool(key, config.critical);

    // Inverted Logic
    snprintf(key, sizeof(key), NVS_ACT_INV, i);
    success &= storageManager.putBool(key, config.inverted_logic);

    // Default State (Boot behavior)
    snprintf(key, sizeof(key), NVS_ACT_DEF_ST, i);
    success &= storageManager.putBool(key, config.default_state);

    // Default PWM
    snprintf(key, sizeof(key), NVS_ACT_DEF_PWM, i);
    success &= storageManager.putUInt8(key, config.default_pwm);

    // AUT-66: fail_safe_on_disconnect policy
    snprintf(key, sizeof(key), NVS_ACT_FSOD, i);
    success &= storageManager.putBool(key, config.fail_safe_on_disconnect);
    snprintf(key, sizeof(key), NVS_ACT_FSOD_OVR, i);
    success &= storageManager.putBool(key, config.has_fail_safe_override);

    // AUT-727: persist max_runtime cap in seconds (0 = use struct default 1h on load)
    snprintf(key, sizeof(key), NVS_ACT_MAXRT, i);
    success &= storageManager.putULong(key,
        static_cast<unsigned long>(config.runtime_protection.max_runtime_ms / 1000UL));

    if (!success) {
      LOG_E(TAG, "ConfigManager: Failed to save actuator " + String(i));
    }
  }

  storageManager.endNamespace();
  storageManager.endTransaction();

  if (success) {
    LOG_I(TAG, "ConfigManager: Actuator configurations saved successfully (" +
             String(actuator_count) + " actuators)");
  } else {
    LOG_E(TAG, "ConfigManager: Some actuator configurations failed to save");
  }

  return success;
}

bool ConfigManager::loadActuatorConfig(ActuatorConfig actuators[], uint8_t max_actuators, uint8_t& loaded_count) {
  loaded_count = 0;

  // Input validation
  if (!actuators || max_actuators == 0) {
    LOG_E(TAG, "ConfigManager: Invalid input to loadActuatorConfig");
    return false;
  }

  // ============================================
  // WOKWI MODE: No persistent config to load
  // ============================================
  #ifdef WOKWI_SIMULATION
    LOG_I(TAG, "ConfigManager: WOKWI mode - no actuator config to load (NVS not supported)");
    LOG_D(TAG, "  Actuators will be configured via MQTT during runtime");
    return false;  // ✅ Keine persistenten Daten
  #endif

  // ============================================
  // NORMAL MODE: Load from NVS with Migration
  // 2026-01-15: New key schema for NVS 15-char limit
  // ============================================
  LOG_I(TAG, "ConfigManager: Loading Actuator configurations...");

  if (!storageManager.beginNamespace("actuator_config", false)) {  // false = read/write for migration
    LOG_W(TAG, "ConfigManager: actuator_config namespace not found");
    return false;
  }

  // Load actuator count with migration support
  uint8_t stored_count = storageManager.getUInt8(NVS_ACT_COUNT, 0);
  if (stored_count == 0) {
    // Try legacy key
    stored_count = storageManager.getUInt8(NVS_ACT_COUNT_OLD, 0);
    if (stored_count > 0) {
      // Migrate count key
      storageManager.putUInt8(NVS_ACT_COUNT, stored_count);
      LOG_I(TAG, "ConfigManager: Migrated actuator_count → act_count");
    }
  }

  LOG_I(TAG, "ConfigManager: Found " + String(stored_count) + " actuator(s) in NVS");

  if (stored_count > max_actuators) {
    LOG_W(TAG, "ConfigManager: Actuator count " + String(stored_count) +
                " exceeds max_actuators (" + String(max_actuators) +
                "), limiting");
    stored_count = max_actuators;
  }

  // Key buffers for new (≤15 chars) and old (legacy) keys
  char new_key[16];   // Max 15 + null terminator
  char old_key[32];   // Legacy keys up to 24 chars

  for (uint8_t i = 0; i < stored_count && loaded_count < max_actuators; i++) {
    ActuatorConfig config;

    // GPIO (Primary Pin)
    snprintf(new_key, sizeof(new_key), NVS_ACT_GPIO, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_GPIO_OLD, i);
    config.gpio = migrateReadUInt8(new_key, old_key, 255);

    // Aux GPIO (H-Bridge, Valves) - CRITICAL for hardware safety!
    snprintf(new_key, sizeof(new_key), NVS_ACT_AUX, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_AUX_OLD, i);
    config.aux_gpio = migrateReadUInt8(new_key, old_key, 255);

    // Actuator Type
    snprintf(new_key, sizeof(new_key), NVS_ACT_TYPE, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_TYPE_OLD, i);
    config.actuator_type = migrateReadString(new_key, old_key, "");

    // Actuator Name
    snprintf(new_key, sizeof(new_key), NVS_ACT_NAME, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_NAME_OLD, i);
    config.actuator_name = migrateReadString(new_key, old_key, "");
    if (config.actuator_name.isEmpty()) {
        config.actuator_name = "Actuator_" + String(config.gpio);
    }

    // Subzone ID - CRITICAL for zone assignment!
    snprintf(new_key, sizeof(new_key), NVS_ACT_SZ, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_SZ_OLD, i);
    config.subzone_id = migrateReadString(new_key, old_key, "");

    // Active Flag - CRITICAL for actuator enable/disable!
    // Default: true — if a config is stored in NVS, the actuator was active.
    // Old key "actuator_%d_active" = 17 chars > NVS limit → unreadable → must not deactivate.
    snprintf(new_key, sizeof(new_key), NVS_ACT_ACTIVE, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_ACTIVE_OLD, i);
    config.active = migrateReadBool(new_key, old_key, true);

    // Critical Flag - SAFETY CRITICAL! Emergency stop depends on this!
    snprintf(new_key, sizeof(new_key), NVS_ACT_CRIT, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_CRIT_OLD, i);
    config.critical = migrateReadBool(new_key, old_key, false);

    // Inverted Logic
    snprintf(new_key, sizeof(new_key), NVS_ACT_INV, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_INV_OLD, i);
    config.inverted_logic = migrateReadBool(new_key, old_key, false);

    // Default State - BOOT CRITICAL! Defines safe boot behavior!
    snprintf(new_key, sizeof(new_key), NVS_ACT_DEF_ST, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_DEF_ST_OLD, i);
    config.default_state = migrateReadBool(new_key, old_key, false);

    // Default PWM
    snprintf(new_key, sizeof(new_key), NVS_ACT_DEF_PWM, i);
    snprintf(old_key, sizeof(old_key), NVS_ACT_DEF_PWM_OLD, i);
    config.default_pwm = migrateReadUInt8(new_key, old_key, 0);

    // AUT-66: fail_safe_on_disconnect — default derives from critical flag if not persisted
    snprintf(new_key, sizeof(new_key), NVS_ACT_FSOD, i);
    config.fail_safe_on_disconnect = storageManager.getBool(new_key, config.critical);
    snprintf(new_key, sizeof(new_key), NVS_ACT_FSOD_OVR, i);
    config.has_fail_safe_override = storageManager.getBool(new_key, false);

    // AUT-727: restore max_runtime cap; 0 = key absent → keep struct default (3600000UL = 1h)
    snprintf(new_key, sizeof(new_key), NVS_ACT_MAXRT, i);
    unsigned long maxrt_s = storageManager.getULong(new_key, 0UL);
    if (maxrt_s > 0UL) {
      config.runtime_protection.max_runtime_ms = maxrt_s * 1000UL;
    }

    // Validate & Store
    if (validateActuatorConfig(config)) {
      actuators[loaded_count++] = config;
      LOG_D(TAG, "ConfigManager: Loaded actuator " + String(i) +
               " - GPIO: " + String(config.gpio) +
               ", Type: " + config.actuator_type +
               ", Active: " + String(config.active ? "true" : "false") +
               ", Critical: " + String(config.critical ? "true" : "false"));
    } else {
      LOG_W(TAG, "ConfigManager: Skipped invalid actuator " + String(i));
    }
  }

  // After flash or NVS corruption, act_count may claim slots while every GPIO reads 255.
  // Reset the persisted count so logs/state match reality and the next MQTT actuator scope can apply cleanly.
  if (loaded_count == 0 && stored_count > 0) {
    LOG_W(TAG, "ConfigManager: NVS had act_count=" + String(stored_count) +
               " but no valid actuators — resetting act_count (server must push actuators to exit CONFIG_PENDING)");
    storageManager.putUInt8(NVS_ACT_COUNT, 0);
    storageManager.putUInt8(NVS_ACT_COUNT_OLD, 0);
  }

  storageManager.endNamespace();

  LOG_I(TAG, "ConfigManager: Loaded " + String(loaded_count) + " actuator configurations");
  return loaded_count > 0;
}

bool ConfigManager::validateActuatorConfig(const ActuatorConfig& config) const {
  if (config.gpio == 255 || config.gpio > 39) {
    LOG_W(TAG, "ConfigManager: Invalid actuator GPIO " + String(config.gpio));
    return false;
  }
  if (config.actuator_type.length() == 0) {
    LOG_W(TAG, "ConfigManager: Actuator type is empty");
    return false;
  }
  return true;
}
