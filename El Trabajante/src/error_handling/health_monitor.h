#ifndef ERROR_HANDLING_HEALTH_MONITOR_H
#define ERROR_HANDLING_HEALTH_MONITOR_H

#include <Arduino.h>
#include "../models/system_types.h"
#include "../models/watchdog_types.h"
#include "../error_handling/circuit_breaker.h"

// ============================================
// HEALTH SNAPSHOT STRUCTURE
// ============================================
struct HealthSnapshot {
    unsigned long timestamp;
    uint32_t heap_free;
    uint32_t heap_min_free;
    uint8_t heap_fragmentation_percent;
    unsigned long uptime_seconds;
    size_t error_count;
    bool wifi_connected;
    int8_t wifi_rssi;
    bool mqtt_connected;
    uint8_t sensor_count;
    uint8_t actuator_count;
    SystemState system_state;

    // Boot reason (ESP-IDF esp_reset_reason_t mapped to uint8_t)
    uint8_t boot_reason;

    // MQTT Circuit Breaker status
    CircuitState mqtt_circuit_state;
    uint8_t mqtt_failure_count;

    // ─────────────────────────────────────────────────────
    // WATCHDOG STATUS (Industrial-Grade)
    // ─────────────────────────────────────────────────────
    WatchdogMode watchdog_mode;          // PROVISIONING / PRODUCTION / DISABLED
    unsigned long watchdog_timeout_ms;   // Current timeout value
    unsigned long last_watchdog_feed;    // Last feed timestamp
    const char* last_feed_component;     // Component ID
    uint32_t watchdog_feed_count;        // Total feeds since boot
    uint8_t watchdog_timeouts_24h;       // Timeouts in last 24h
    bool watchdog_timeout_pending;       // Timeout flag set?
};

// ============================================
// HEALTH MONITOR CLASS
// ============================================
class HealthMonitor {
public:
    // Singleton Instance
    static HealthMonitor& getInstance();
    
    // Initialization
    bool begin();
    
    // Health Snapshot Generation
    HealthSnapshot getCurrentSnapshot() const;
    String getSnapshotJSON() const;
    
    // Publishing (automatic via loop())
    void publishSnapshot();
    void publishSnapshotIfChanged();
    
    // Loop (call in main loop)
    void loop();
    
    // Configuration
    void setPublishInterval(unsigned long interval_ms);
    void setChangeDetectionEnabled(bool enabled);
    
    // Status Getters
    uint32_t getHeapFree() const;
    uint32_t getHeapMinFree() const;
    uint8_t getHeapFragmentation() const;
    unsigned long getUptimeSeconds() const;
    
private:
    HealthMonitor();
    ~HealthMonitor() = default;
    
    // Prevent copy
    HealthMonitor(const HealthMonitor&) = delete;
    HealthMonitor& operator=(const HealthMonitor&) = delete;
    
    // Change Detection
    HealthSnapshot last_published_snapshot_;
    bool change_detection_enabled_;
    
    // Publishing Configuration
    unsigned long publish_interval_ms_;
    unsigned long last_publish_time_;
    
    // Initialization flag
    bool initialized_;
    
    // Thresholds for Change Detection
    static const uint32_t HEAP_CHANGE_THRESHOLD_PERCENT = 20;
    static const int8_t RSSI_CHANGE_THRESHOLD_DBM = 10;
    
    // Helper methods
    bool hasSignificantChanges(const HealthSnapshot& current, const HealthSnapshot& last) const;
    String buildDiagnosticsTopic() const;
};

// Global Instance
extern HealthMonitor& healthMonitor;

#endif // ERROR_HANDLING_HEALTH_MONITOR_H






























