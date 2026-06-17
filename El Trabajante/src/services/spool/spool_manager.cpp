// ============================================
// SpoolManager — AUT-714
// Persistent offline spool via LittleFS (JSONL).
// ============================================
#include "spool_manager.h"
#include "../../services/communication/mqtt_client.h"
#include "../../tasks/publish_queue.h"
#include "../../utils/time_manager.h"
#include "../../utils/topic_builder.h"
#include "../../utils/logger.h"

#include <ArduinoJson.h>
#include <LittleFS.h>

// ============================================
// Static TAG for ESP-IDF structured logging
// ============================================
static const char* SPOOL_TAG = "SPOOL";

// ============================================
// Global singleton reference
// (defined here, declared extern in header)
// ============================================
SpoolManager& spoolManager = SpoolManager::getInstance();

// ============================================
// begin() — called once after LittleFS.begin()
// ============================================
bool SpoolManager::begin() {
    ensureSpoolDir();
    // Count pre-existing lines (from previous session)
    pending_count_ = countLines();
    ESP_LOGI(SPOOL_TAG, "SpoolManager ready, pre-existing entries: %lu", (unsigned long)pending_count_);
    return true;
}

// ============================================
// ensureSpoolDir() — create /spool/ if missing
// ============================================
void SpoolManager::ensureSpoolDir() {
    if (!LittleFS.exists("/spool")) {
        LittleFS.mkdir("/spool");
        ESP_LOGI(SPOOL_TAG, "Created /spool directory");
    }
}

// ============================================
// buildJsonLine() — compact JSON for one reading
// ============================================
String SpoolManager::buildJsonLine(const SensorReading& reading) const {
    StaticJsonDocument<320> doc;
    doc["g"]  = reading.gpio;
    doc["t"]  = reading.sensor_type;
    doc["r"]  = reading.raw_value;
    doc["pv"] = reading.processed_value;
    doc["u"]  = reading.unit;
    doc["q"]  = reading.quality;
    doc["ts"] = reading.timestamp;
    doc["rm"] = reading.raw_mode ? 1 : 0;
    // AUT-863 Option B: boot-epoch anchor — server adds ts/1000 to recover wall-clock timestamp.
    // Guard: only include when time is NTP-synced (syncFromAuthoritativeUnix in main.cpp:2519).
    if (timeManager.isSynchronized()) {
        doc["be"] = (unsigned long)(time(nullptr) - millis() / 1000UL);
    }
    if (reading.onewire_address.length() > 0) {
        doc["ow"] = reading.onewire_address;
    }
    if (reading.subzone_id.length() > 0) {
        doc["sz"] = reading.subzone_id;
    }
    String line;
    serializeJson(doc, line);
    return line;
}

// ============================================
// countLines() — O(n) scan of the spool file
// ============================================
uint32_t SpoolManager::countLines() const {
    if (!spool_enabled_) return 0;
    if (!LittleFS.exists(kSpoolFilePath)) return 0;

    File f = LittleFS.open(kSpoolFilePath, "r");
    if (!f) return 0;

    uint32_t count = 0;
    while (f.available()) {
        String line = f.readStringUntil('\n');
        if (line.length() > 2) {  // Skip empty / whitespace-only lines
            count++;
        }
    }
    f.close();
    return count;
}

// ============================================
// dropOldestLine() — remove first line of JSONL
// Rewrites the whole file (LittleFS has no
// seek-to-byte-truncate for the front).
// ============================================
void SpoolManager::dropOldestLine() {
    if (!LittleFS.exists(kSpoolFilePath)) return;

    File src = LittleFS.open(kSpoolFilePath, "r");
    if (!src) return;

    // Skip first line
    src.readStringUntil('\n');

    // Buffer remainder — no pre-allocation to conserve DRAM
    String remainder;
    while (src.available()) {
        remainder += src.readStringUntil('\n');
        remainder += '\n';
        if (remainder.length() > kMaxSpoolBytes) {
            // Safety: truncate if somehow oversized
            break;
        }
    }
    src.close();

    // Rewrite without first line
    File dst = LittleFS.open(kSpoolFilePath, "w");
    if (dst) {
        dst.print(remainder);
        dst.close();
    }

    dropped_count_++;
    if (pending_count_ > 0) pending_count_--;

    ESP_LOGW(SPOOL_TAG, "Dropped oldest spool entry (fill threshold), total dropped: %lu",
             (unsigned long)dropped_count_);
}

// ============================================
// append() — write one reading to JSONL spool
// ============================================
bool SpoolManager::append(const SensorReading& reading) {
    if (!spool_enabled_) return false;

    // Enforce fill threshold — drop oldest when >90% full
    size_t total = LittleFS.totalBytes();
    size_t used  = LittleFS.usedBytes();
    if (total > 0 && used > 0) {
        float fill = static_cast<float>(used) / static_cast<float>(total);
        if (fill >= kSpoolFillDropThreshold) {
            dropOldestLine();
        }
    }

    // Enforce absolute byte limit
    if (LittleFS.exists(kSpoolFilePath)) {
        File check = LittleFS.open(kSpoolFilePath, "r");
        if (check) {
            size_t sz = check.size();
            check.close();
            if (sz >= kMaxSpoolBytes) {
                dropOldestLine();
            }
        }
    }

    ensureSpoolDir();
    File f = LittleFS.open(kSpoolFilePath, "a");
    if (!f) {
        ESP_LOGE(SPOOL_TAG, "Failed to open spool file for append");
        return false;
    }

    String line = buildJsonLine(reading);
    f.print(line);
    f.print('\n');
    f.close();

    pending_count_++;
    char spool_msg[96];
    snprintf(spool_msg, sizeof(spool_msg), "Spooled reading gpio=%d type=%s, total pending: %lu",
             reading.gpio, reading.sensor_type.c_str(), (unsigned long)pending_count_);
    LOG_I(SPOOL_TAG, spool_msg);
    return true;
}

// ============================================
// flushPending() — send batched readings via MQTT
// ============================================
bool SpoolManager::flushPending(MQTTClient& mqtt) {
    if (!spool_enabled_ || !LittleFS.exists(kSpoolFilePath)) {
        return true;
    }
    // AUT-862 P1: gate on connectivity — let processDeferredSpoolFlush re-arm if not ready
    if (!mqtt.isConnected()) {
        return false;
    }

    uint32_t flushed   = 0;
    uint32_t remaining = 0;
    String kept_lines;
    // AUT-862 P2: stop publishing after first failure but keep reading to preserve all lines.
    bool stop_flush = false;

    File f = LittleFS.open(kSpoolFilePath, "r");
    if (!f) {
        ESP_LOGE(SPOOL_TAG, "Failed to open spool file for flush");
        return false;
    }

    // Collect all lines
    while (f.available()) {
        String line = f.readStringUntil('\n');
        if (line.length() < 3) continue;  // skip empty

        if (!stop_flush && flushed < kBatchFlushSize) {
            // Parse and re-publish
            StaticJsonDocument<256> doc;
            DeserializationError err = deserializeJson(doc, line);
            if (err) {
                ESP_LOGW(SPOOL_TAG, "Skipping malformed spool line: %s", err.c_str());
                flushed++;  // Count as consumed — not worth retrying corrupt data
                continue;
            }

            // Build batch topic using TopicBuilder canonical function
            const char* topic = TopicBuilder::buildSensorBatchTopic();

            // Re-wrap as single-reading batch payload (server handler accepts list or dict)
            StaticJsonDocument<384> batch;
            JsonArray readings_arr = batch.createNestedArray("readings");
            JsonObject r = readings_arr.createNestedObject();
            r["gpio"]            = doc["g"];
            r["sensor_type"]     = doc["t"];
            r["raw_value"]       = doc["r"];
            r["processed_value"] = doc["pv"];
            r["unit"]            = doc["u"];
            r["quality"]         = doc["q"];
            r["timestamp"]       = doc["ts"];
            r["raw_mode"]        = doc["rm"];
            if (doc.containsKey("be")) r["be"] = doc["be"];  // AUT-863 P-TS: boot-epoch anchor
            if (doc.containsKey("ow")) r["onewire_address"] = doc["ow"];
            if (doc.containsKey("sz")) r["subzone_id"] = doc["sz"];

            String payload;
            serializeJson(batch, payload);

            // AUT-862 P1: route via publish queue instead of direct esp_mqtt_client_publish().
            // processPublishQueue() has write-timeout + circuit-breaker guards; the direct
            // Core-0 path in mqtt.publish() blocks up to ~1765ms on EAGAIN right after
            // reconnect and causes a self-inflicted second disconnect.
            PublishQueueEnqueueResult pq =
                tryQueuePublish(topic, payload.c_str(), 1, false, false);
            bool published = (pq == PublishQueueEnqueueResult::Enqueued);
            if (published) {
                flushed++;
            } else {
                // Queue full or backpressure — keep this line and stop publishing.
                // Continue reading to preserve all remaining lines (no data loss).
                kept_lines += line;
                kept_lines += '\n';
                remaining++;
                stop_flush = true;
            }
        } else {
            // Beyond batch limit or stop_flush set — keep for next flush cycle
            kept_lines += line;
            kept_lines += '\n';
            remaining++;
        }
    }
    f.close();

    if (flushed > 0 || remaining == 0) {
        // Rewrite file with only the kept (unflushed) lines
        if (remaining == 0) {
            LittleFS.remove(kSpoolFilePath);
            pending_count_ = 0;
        } else {
            File out = LittleFS.open(kSpoolFilePath, "w");
            if (out) {
                out.print(kept_lines);
                out.close();
            }
            pending_count_ = remaining;
        }
        char flush_msg[72];
        snprintf(flush_msg, sizeof(flush_msg), "Spool flush: sent=%lu, remaining=%lu",
                 (unsigned long)flushed, (unsigned long)remaining);
        LOG_I(SPOOL_TAG, flush_msg);
    }

    return (remaining == 0);
}

// ============================================
// State accessors
// ============================================
uint32_t SpoolManager::pendingCount() const {
    return pending_count_;
}

uint32_t SpoolManager::droppedCount() const {
    return dropped_count_;
}

bool SpoolManager::isEnabled() const {
    return spool_enabled_;
}

void SpoolManager::setEnabled(bool enabled) {
    spool_enabled_ = enabled;
}
