#include "health_monitor.h"
#include "../utils/logger.h"
#include "../services/communication/wifi_manager.h"
#include "../services/communication/mqtt_client.h"
#include "../services/sensor/sensor_manager.h"
#include "../services/actuator/actuator_manager.h"
#include "../services/safety/offline_mode_manager.h"
#include "../services/config/storage_manager.h"
#include "../error_handling/error_tracker.h"
#include "../utils/topic_builder.h"
#include "../utils/time_manager.h"
#include "../models/error_codes.h"
#include "../models/watchdog_types.h"
#include "../utils/watchdog_storage.h"
#include <esp_system.h>

// ESP-IDF TAG convention for structured logging
static const char* TAG = "HEALTH";

// ============================================
// EXTERNAL GLOBAL VARIABLES (from main.cpp)
// ============================================
extern SystemConfig g_system_config;
extern KaiserZone g_kaiser;
extern WatchdogConfig g_watchdog_config;
extern WatchdogDiagnostics g_watchdog_diagnostics;
extern volatile bool g_watchdog_timeout_flag;

static String g_diag_boot_sequence_id;
static uint8_t g_diag_reset_reason = 0;
static unsigned long g_diag_segment_start_ts = 0;

static const char* resetReasonToString(uint8_t reason) {
    switch (reason) {
        case ESP_RST_POWERON: return "POWERON";
        case ESP_RST_EXT: return "EXT";
        case ESP_RST_SW: return "SW";
        case ESP_RST_PANIC: return "PANIC";
        case ESP_RST_INT_WDT: return "INT_WDT";
        case ESP_RST_TASK_WDT: return "TASK_WDT";
        case ESP_RST_WDT: return "WDT";
        case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
        case ESP_RST_BROWNOUT: return "BROWNOUT";
        case ESP_RST_SDIO: return "SDIO";
        default: return "UNKNOWN";
    }
}

static void ensureDiagnosticsBootTelemetryInitialized() {
    if (g_diag_boot_sequence_id.length() == 0) {
        g_diag_reset_reason = static_cast<uint8_t>(esp_reset_reason());
        g_diag_boot_sequence_id =
            g_system_config.esp_id + "-b" + String(g_system_config.boot_count) + "-r" + String(g_diag_reset_reason);
    }

    if (g_diag_segment_start_ts == 0) {
        time_t unix_timestamp = timeManager.getUnixTimestamp();
        bool time_valid = timeManager.isSynchronized();
        if (time_valid && unix_timestamp > 0) {
            g_diag_segment_start_ts = static_cast<unsigned long>(unix_timestamp);
        }
    }
}

// ============================================
// GLOBAL HEALTH MONITOR INSTANCE
// ============================================
HealthMonitor& healthMonitor = HealthMonitor::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
HealthMonitor& HealthMonitor::getInstance() {
    static HealthMonitor instance;
    return instance;
}

// ============================================
// CONSTRUCTOR
// ============================================
HealthMonitor::HealthMonitor()
    : change_detection_enabled_(true),
      publish_interval_ms_(60000),  // Default: 60 seconds
      last_publish_time_(0),
      initialized_(false) {
    // Initialize last_published_snapshot_ to zero
    memset(&last_published_snapshot_, 0, sizeof(HealthSnapshot));
}

// ============================================
// INITIALIZATION
// ============================================
bool HealthMonitor::begin() {
    if (initialized_) {
        LOG_W(TAG, "HealthMonitor already initialized");
        return true;
    }
    
    // Reset snapshot
    memset(&last_published_snapshot_, 0, sizeof(HealthSnapshot));
    last_publish_time_ = 0;
    
    initialized_ = true;
    LOG_I(TAG, "HealthMonitor: Initialized");
    
    return true;
}

// ============================================
// HEALTH SNAPSHOT GENERATION
// ============================================
HealthSnapshot HealthMonitor::getCurrentSnapshot() const {
    HealthSnapshot snapshot;
    
    // Timestamp
    snapshot.timestamp = millis() / 1000;  // Convert to seconds
    
    // Heap information
    snapshot.heap_free = ESP.getFreeHeap();
    snapshot.heap_min_free = ESP.getMinFreeHeap();
    snapshot.heap_fragmentation_percent = getHeapFragmentation();
    
    // Uptime
    snapshot.uptime_seconds = getUptimeSeconds();
    
    // Error count
    snapshot.error_count = errorTracker.getErrorCount();
    
    // WiFi status
    snapshot.wifi_connected = wifiManager.isConnected();
    snapshot.wifi_rssi = wifiManager.getRSSI();
    
    // MQTT status
    snapshot.mqtt_connected = mqttClient.isConnected();
    
    // Sensor/Actuator counts
    snapshot.sensor_count = sensorManager.getActiveSensorCount();
    snapshot.actuator_count = actuatorManager.getActiveActuatorCount();
    
    // System state
    snapshot.system_state = g_system_config.current_state;

    // Boot reason
    snapshot.boot_reason = (uint8_t)esp_reset_reason();

    // MQTT Circuit Breaker status
    snapshot.mqtt_circuit_state = mqttClient.getCircuitBreakerState();
    snapshot.mqtt_failure_count = mqttClient.getCircuitBreakerFailureCount();

    // ─────────────────────────────────────────────────────
    // WATCHDOG STATUS
    // ─────────────────────────────────────────────────────
    snapshot.watchdog_mode = g_watchdog_config.mode;
    snapshot.watchdog_timeout_ms = g_watchdog_config.timeout_ms;
    snapshot.last_watchdog_feed = g_watchdog_diagnostics.last_feed_time;
    snapshot.last_feed_component = g_watchdog_diagnostics.last_feed_component;
    snapshot.watchdog_feed_count = g_watchdog_diagnostics.feed_count;
    snapshot.watchdog_timeouts_24h = getWatchdogCountLast24h();
    snapshot.watchdog_timeout_pending = g_watchdog_timeout_flag;
    
    return snapshot;
}

// ============================================
// HEAP FRAGMENTATION CALCULATION
// ============================================
uint8_t HealthMonitor::getHeapFragmentation() const {
    uint32_t free_heap = ESP.getFreeHeap();
    uint32_t min_free_heap = ESP.getMinFreeHeap();
    
    if (free_heap == 0) {
        return 100;
    }
    
    // Fragmentation = (free - min_free) / free * 100
    uint32_t fragmentation_bytes = free_heap - min_free_heap;
    return (fragmentation_bytes * 100) / free_heap;
}

// ============================================
// UPTIME CALCULATION
// ============================================
unsigned long HealthMonitor::getUptimeSeconds() const {
    return millis() / 1000;
}

// ============================================
// STATUS GETTERS
// ============================================
uint32_t HealthMonitor::getHeapFree() const {
    return ESP.getFreeHeap();
}

uint32_t HealthMonitor::getHeapMinFree() const {
    return ESP.getMinFreeHeap();
}

// ============================================
// CHANGE DETECTION
// ============================================
bool HealthMonitor::hasSignificantChanges(const HealthSnapshot& current, 
                                          const HealthSnapshot& last) const {
    // First snapshot (all zeros) - always publish
    if (last.timestamp == 0) {
        return true;
    }
    
    // Heap change > 20%
    if (last.heap_free > 0) {
        uint32_t heap_change = (current.heap_free > last.heap_free) ?
                              (current.heap_free - last.heap_free) :
                              (last.heap_free - current.heap_free);
        if ((heap_change * 100) / last.heap_free > HEAP_CHANGE_THRESHOLD_PERCENT) {
            return true;
        }
    }
    
    // RSSI change > 10 dBm
    if (abs(current.wifi_rssi - last.wifi_rssi) > RSSI_CHANGE_THRESHOLD_DBM) {
        return true;
    }
    
    // Connection status change
    if (current.wifi_connected != last.wifi_connected ||
        current.mqtt_connected != last.mqtt_connected) {
        return true;
    }
    
    // Sensor/Actuator count change
    if (current.sensor_count != last.sensor_count ||
        current.actuator_count != last.actuator_count) {
        return true;
    }
    
    // System state change
    if (current.system_state != last.system_state) {
        return true;
    }
    
    // Error count significant change (> 5 errors)
    if (abs((int)(current.error_count - last.error_count)) > 5) {
        return true;
    }
    
    return false;
}

// ============================================
// JSON PAYLOAD GENERATION
// ============================================
String HealthMonitor::getSnapshotJSON() const {
    HealthSnapshot snapshot = getCurrentSnapshot();
    ensureDiagnosticsBootTelemetryInitialized();
    
    // Build JSON payload
    String json = "{";
    json += "\"ts\":" + String(snapshot.timestamp) + ",";
    json += "\"esp_id\":\"" + g_system_config.esp_id + "\",";
    json += "\"heap_free\":" + String(snapshot.heap_free) + ",";
    json += "\"heap_min_free\":" + String(snapshot.heap_min_free) + ",";
    json += "\"heap_fragmentation\":" + String(snapshot.heap_fragmentation_percent) + ",";
    json += "\"uptime_seconds\":" + String(snapshot.uptime_seconds) + ",";
    json += "\"error_count\":" + String(snapshot.error_count) + ",";
    json += "\"wifi_connected\":" + String(snapshot.wifi_connected ? "true" : "false") + ",";
    json += "\"wifi_rssi\":" + String(snapshot.wifi_rssi) + ",";
    json += "\"mqtt_connected\":" + String(snapshot.mqtt_connected ? "true" : "false") + ",";
    json += "\"sensor_count\":" + String(snapshot.sensor_count) + ",";
    json += "\"actuator_count\":" + String(snapshot.actuator_count) + ",";
    
    // System state as string
    String state_str = "UNKNOWN";
    switch (snapshot.system_state) {
        case STATE_BOOT: state_str = "BOOT"; break;
        case STATE_WIFI_SETUP: state_str = "WIFI_SETUP"; break;
        case STATE_WIFI_CONNECTED: state_str = "WIFI_CONNECTED"; break;
        case STATE_MQTT_CONNECTING: state_str = "MQTT_CONNECTING"; break;
        case STATE_MQTT_CONNECTED: state_str = "MQTT_CONNECTED"; break;
        case STATE_AWAITING_USER_CONFIG: state_str = "AWAITING_USER_CONFIG"; break;
        case STATE_ZONE_CONFIGURED: state_str = "ZONE_CONFIGURED"; break;
        case STATE_SENSORS_CONFIGURED: state_str = "SENSORS_CONFIGURED"; break;
        case STATE_CONFIG_PENDING_AFTER_RESET: state_str = "CONFIG_PENDING_AFTER_RESET"; break;
        case STATE_OPERATIONAL: state_str = "OPERATIONAL"; break;
        case STATE_PENDING_APPROVAL: state_str = "PENDING_APPROVAL"; break;
        case STATE_LIBRARY_DOWNLOADING: state_str = "LIBRARY_DOWNLOADING"; break;
        case STATE_SAFE_MODE: state_str = "SAFE_MODE"; break;
        case STATE_SAFE_MODE_PROVISIONING: state_str = "SAFE_MODE_PROVISIONING"; break;
        case STATE_ERROR: state_str = "ERROR"; break;
        default: state_str = "UNKNOWN"; break;
    }
    json += "\"system_state\":\"" + state_str + "\"";

    // Boot/Segment telemetry for long-run KPI segmentation across reboot boundaries.
    const char* reason_str = resetReasonToString(snapshot.boot_reason);
    json += ",\"boot_reason\":\"" + String(reason_str) + "\"";
    json += ",\"boot_sequence_id\":\"" + g_diag_boot_sequence_id + "\"";
    json += ",\"reset_reason\":\"" + String(reason_str) + "\"";
    json += ",\"segment_start_ts\":" + String(g_diag_segment_start_ts);

    // MQTT Circuit Breaker status
    const char* cb_states[] = {"CLOSED","OPEN","HALF_OPEN"};
    json += ",\"mqtt_cb_state\":\"" + String(cb_states[(uint8_t)snapshot.mqtt_circuit_state]) + "\"";
    json += ",\"mqtt_cb_failures\":" + String(snapshot.mqtt_failure_count);

    // Watchdog status (data already captured in snapshot, now serialized)
    const char* wdt_modes[] = {"DISABLED","PROVISIONING","PRODUCTION","SAFE_MODE"};
    json += ",\"wdt_mode\":\"" + String(wdt_modes[(uint8_t)snapshot.watchdog_mode]) + "\"";
    json += ",\"wdt_timeouts_24h\":" + String(snapshot.watchdog_timeouts_24h);
    json += ",\"wdt_timeout_pending\":" + String(snapshot.watchdog_timeout_pending ? "true" : "false");
    json += ",\"metrics_schema_version\":" +
            String(OfflineModeManager::OFFLINE_AUTHORITY_METRICS_SCHEMA_VERSION);
    json += ",\"storage_namespace_conflict_count\":" +
            String(storageManager.getNamespaceConflictCount());
    json += ",\"storage_no_session_access_count\":" +
            String(storageManager.getNoSessionAccessCount());
    json += ",\"hist_not_found_expected_count\":" +
            String(watchdogStorageGetHistNotFoundExpectedCount());
    json += ",\"hist_not_found_unexpected_count\":" +
            String(watchdogStorageGetHistNotFoundUnexpectedCount());

    json += "}";
    
    return json;
}

// ============================================
// TOPIC BUILDING
// ============================================
String HealthMonitor::buildDiagnosticsTopic() const {
    // Use TopicBuilder for consistency
    return String(TopicBuilder::buildSystemDiagnosticsTopic());
}

// ============================================
// PUBLISHING
// ============================================
void HealthMonitor::publishSnapshot() {
    if (!initialized_) {
        return;
    }
    
    if (!mqttClient.isConnected()) {
        LOG_D(TAG, "HealthMonitor: MQTT not connected, skipping publish");
        return;
    }
    
    String topic = buildDiagnosticsTopic();
    String payload = getSnapshotJSON();
    
    if (mqttClient.publish(topic, payload, 0)) {  // QoS 0
        LOG_D(TAG, "HealthMonitor: Published diagnostics snapshot");
        last_published_snapshot_ = getCurrentSnapshot();
    } else {
        LOG_W(TAG, "HealthMonitor: Failed to publish diagnostics snapshot");
        errorTracker.trackError(ERROR_MQTT_PUBLISH_FAILED, ERROR_SEVERITY_WARNING,
                               "HealthMonitor publish failed");
    }
}

void HealthMonitor::publishSnapshotIfChanged() {
    if (!initialized_) {
        return;
    }
    
    HealthSnapshot current = getCurrentSnapshot();
    
    if (!change_detection_enabled_ || hasSignificantChanges(current, last_published_snapshot_)) {
        publishSnapshot();
    }
}

// ============================================
// LOOP (call in main loop)
// ============================================
void HealthMonitor::loop() {
    if (!initialized_) {
        return;
    }
    
    unsigned long current_time = millis();
    
    // Check if publish interval elapsed
    if (current_time - last_publish_time_ >= publish_interval_ms_) {
        last_publish_time_ = current_time;
        publishSnapshotIfChanged();
    }
}

// ============================================
// CONFIGURATION
// ============================================
void HealthMonitor::setPublishInterval(unsigned long interval_ms) {
    publish_interval_ms_ = interval_ms;
    LOG_I(TAG, "HealthMonitor: Publish interval set to " + String(interval_ms) + " ms");
}

void HealthMonitor::setChangeDetectionEnabled(bool enabled) {
    change_detection_enabled_ = enabled;
    LOG_I(TAG, "HealthMonitor: Change detection " + String(enabled ? "enabled" : "disabled"));
}

