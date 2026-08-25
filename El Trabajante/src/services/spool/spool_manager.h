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

// AUT-882: streaming compaction + persisted flush cursor (replaces the
// unbounded RAM-String compaction that silently truncated large spools).
static const char* kSpoolTempPath          = "/spool/readings.tmp";   // compaction scratch
static constexpr size_t kFlushHeapGuardBytes = 20UL * 1024UL;         // pause flush below this free heap
static const char* kSpoolNvsNamespace      = "spool";                 // NVS namespace
static const char* kSpoolNvsCursorKey      = "flush_off";             // persisted byte offset (spool_flush_off)


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

    // AUT-882: byte offset of the already-published prefix, persisted in NVS.
    // A mid-drain reboot resumes here instead of re-streaming (and truncating)
    // the whole file in a RAM String. Always sits on a line boundary.
    size_t   flush_offset_   = 0;

    // Build compact JSON line for one SensorReading
    String buildJsonLine(const SensorReading& reading) const;

    // Count JSONL lines from a byte offset to EOF (O(n) scan). Default 0 = whole file.
    uint32_t countLines(size_t from_offset = 0) const;

    // Drop the oldest line from the spool file.
    // Used to enforce kSpoolFillDropThreshold.
    void dropOldestLine();

    // AUT-882: single shared, heap-bounded compaction path. Streams the spool
    // file from byte `drop_before` to EOF into a temp file (one line at a time)
    // and atomically renames it over the spool file; removes the spool file when
    // nothing remains. Caller adjusts flush_offset_/counters relative to drop_before.
    bool compactDroppingPrefix(size_t drop_before);

    // AUT-882: persist / load the flush cursor (NVS namespace "spool", key "flush_off").
    void persistFlushOffset();
    size_t loadFlushOffset();

    // Ensure /spool/ directory exists on LittleFS
    void ensureSpoolDir();
};

// ============================================
// Global singleton shortcut (matches
// pattern used in sensor_manager.cpp etc.)
// ============================================
extern SpoolManager& spoolManager;

#endif  // SERVICES_SPOOL_SPOOL_MANAGER_H
