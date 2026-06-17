#ifndef SERVICES_SPOOL_SPOOL_MANAGER_H
#define SERVICES_SPOOL_SPOOL_MANAGER_H

// ============================================
// SpoolManager — AUT-714
// Persistent offline spool for sensor readings via LittleFS.
// Appends readings as JSONL during MQTT disconnect.
// Flushes on reconnect via processOfflineBuffer() in mqtt_client.cpp.
// ============================================

#include <Arduino.h>
#include <LittleFS.h>
#include "../../models/sensor_types.h"

// Forward declaration to avoid circular include with mqtt_client.h
class MQTTClient;

// ============================================
// SPOOL CONSTANTS
// ============================================

// LittleFS spool file path
static const char* kSpoolFilePath = "/spool/readings.jsonl";

// Drop when LittleFS is more than 90% full
static constexpr float kSpoolFillDropThreshold = 0.90f;

// Per-target batch and capacity limits
#ifdef ESP32_S3_DEVKIT_MODE
static constexpr uint8_t kBatchFlushSize   = 50;
static constexpr size_t  kMaxSpoolBytes    = 2UL * 1024UL * 1024UL;  // 2 MB (S3 has PSRAM)
#else
static constexpr uint8_t kBatchFlushSize   = 10;
static constexpr size_t  kMaxSpoolBytes    = 512UL * 1024UL;          // 512 KB (WROOM)
#endif


// ============================================
// SpoolManager CLASS
// ============================================
class SpoolManager {
public:
    // Singleton access
    static SpoolManager& getInstance() {
        static SpoolManager instance;
        return instance;
    }

    SpoolManager(const SpoolManager&) = delete;
    SpoolManager& operator=(const SpoolManager&) = delete;
    SpoolManager(SpoolManager&&) = delete;
    SpoolManager& operator=(SpoolManager&&) = delete;

    // ----------------------------------------
    // Initialise spool directory.
    // Called from setup() after LittleFS.begin().
    // ----------------------------------------
    bool begin();

    // ----------------------------------------
    // Append one reading to /spool/readings.jsonl.
    // Drops oldest line when fill-threshold exceeded.
    // Returns true on success.
    // ----------------------------------------
    bool append(const SensorReading& reading);

    // ----------------------------------------
    // Flush pending readings to MQTT in batches
    // of kBatchFlushSize. Returns true when
    // the spool file is empty after flushing.
    // ----------------------------------------
    bool flushPending(MQTTClient& mqtt);

    // ----------------------------------------
    // State accessors
    // ----------------------------------------
    uint32_t pendingCount() const;
    uint32_t droppedCount() const;
    bool isEnabled() const;

    // ----------------------------------------
    // Enable / disable at runtime (e.g. if
    // LittleFS.begin() failed in setup()).
    // ----------------------------------------
    void setEnabled(bool enabled);

private:
    SpoolManager() = default;
    ~SpoolManager() = default;

    bool     spool_enabled_  = false;
    uint32_t pending_count_  = 0;
    uint32_t dropped_count_  = 0;

    // Build compact JSON line for one SensorReading
    String buildJsonLine(const SensorReading& reading) const;

    // Estimate number of lines in spool file (O(n) scan)
    uint32_t countLines() const;

    // Drop the oldest line from the spool file.
    // Used to enforce kSpoolFillDropThreshold.
    void dropOldestLine();

    // Ensure /spool/ directory exists on LittleFS
    void ensureSpoolDir();
};

// ============================================
// Global singleton shortcut (matches
// pattern used in sensor_manager.cpp etc.)
// ============================================
extern SpoolManager& spoolManager;

#endif  // SERVICES_SPOOL_SPOOL_MANAGER_H
