// ============================================
// SpoolManager — AUT-714
// Persistent offline spool via LittleFS (JSONL).
// ============================================
#include "spool_manager.h"
#include "../../services/communication/mqtt_client.h"
#include "../../services/config/storage_manager.h"  // AUT-882: persisted flush cursor
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

    // AUT-882: discard any orphaned compaction temp. compactDroppingPrefix() uses
    // an atomic rename, so a leftover temp means the rename never committed and the
    // original spool file is authoritative — drop the temp.
    if (LittleFS.exists(kSpoolTempPath)) {
        LittleFS.remove(kSpoolTempPath);
        LOG_W(SPOOL_TAG, "Removed orphaned spool temp file");
    }

    // AUT-882: restore the persisted flush cursor so a mid-drain reboot resumes
    // where it left off (no re-publish of the already-sent prefix, no duplicates).
    flush_offset_ = loadFlushOffset();

    if (!LittleFS.exists(kSpoolFilePath)) {
        if (flush_offset_ != 0) { flush_offset_ = 0; persistFlushOffset(); }
        pending_count_ = 0;
        LOG_I(SPOOL_TAG, "SpoolManager ready, no spool file");
        return true;
    }

    size_t file_size = 0;
    File f = LittleFS.open(kSpoolFilePath, "r");
    if (f) { file_size = f.size(); f.close(); }

    if (flush_offset_ > file_size) {
        // Cursor points past EOF (file shrank/replaced without cursor update):
        // reset and re-scan from the front (favours no-loss over no-duplicate).
        char sc_msg[96];
        snprintf(sc_msg, sizeof(sc_msg), "Stale flush cursor %lu > file %lu, resetting",
                 (unsigned long)flush_offset_, (unsigned long)file_size);
        LOG_W(SPOOL_TAG, sc_msg);
        flush_offset_ = 0;
        persistFlushOffset();
    }

    if (file_size > 0 && flush_offset_ == file_size) {
        // Fully drained before reboot but file not yet removed — clean up now.
        LittleFS.remove(kSpoolFilePath);
        flush_offset_ = 0;
        persistFlushOffset();
        pending_count_ = 0;
        LOG_I(SPOOL_TAG, "Spool fully drained pre-reboot, removed");
        return true;
    }

    // Count only the still-pending lines (from the cursor to EOF).
    pending_count_ = countLines(flush_offset_);
    char rdy_msg[96];
    snprintf(rdy_msg, sizeof(rdy_msg), "SpoolManager ready, pending: %lu (cursor %lu/%lu)",
             (unsigned long)pending_count_, (unsigned long)flush_offset_,
             (unsigned long)file_size);
    LOG_I(SPOOL_TAG, rdy_msg);
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
// countLines() — O(n) scan of the spool file from a byte offset (default 0)
// ============================================
uint32_t SpoolManager::countLines(size_t from_offset) const {
    if (!spool_enabled_) return 0;
    if (!LittleFS.exists(kSpoolFilePath)) return 0;

    File f = LittleFS.open(kSpoolFilePath, "r");
    if (!f) return 0;
    if (from_offset > 0 && !f.seek(from_offset)) {  // AUT-882: count only the pending tail
        f.close();
        return 0;
    }

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
// AUT-882: uses the shared streaming compaction path (no RAM String) and keeps
// the persisted flush cursor consistent with the shifted byte offsets.
// ============================================
void SpoolManager::dropOldestLine() {
    if (!LittleFS.exists(kSpoolFilePath)) return;

    // Byte length of the oldest (first) line incl. its '\n' delimiter.
    size_t drop_bytes = 0;
    size_t file_size  = 0;
    {
        File src = LittleFS.open(kSpoolFilePath, "r");
        if (!src) return;
        file_size = src.size();
        String first = src.readStringUntil('\n');   // bounded: one line only
        drop_bytes = first.length() + 1;            // +1 for the consumed '\n'
        src.close();
    }
    if (drop_bytes == 0) return;
    if (drop_bytes > file_size) drop_bytes = file_size;  // single line without trailing '\n'

    // Was the dropped line still pending? The cursor always sits on a line
    // boundary, so the first line is unpublished only when the cursor is at 0.
    const bool dropped_was_pending = (flush_offset_ == 0);

    // AUT-882: reuse the single shared streaming-compaction path (no RAM String).
    if (!compactDroppingPrefix(drop_bytes)) {
        ESP_LOGW(SPOOL_TAG, "dropOldestLine: compaction failed, file unchanged");
        return;  // cursor/counters untouched → NVS and file stay consistent
    }

    // Every byte offset shifted down by drop_bytes.
    flush_offset_ = (flush_offset_ >= drop_bytes) ? (flush_offset_ - drop_bytes) : 0;
    persistFlushOffset();

    if (dropped_was_pending) {
        // Genuine ring-buffer data loss (line never reached the server).
        dropped_count_++;
        if (pending_count_ > 0) pending_count_--;
    }
    // else: the dropped line was already published — pure compaction, not a loss.

    ESP_LOGW(SPOOL_TAG, "Dropped oldest spool entry (fill threshold), dropped_total: %lu, pending: %lu",
             (unsigned long)dropped_count_, (unsigned long)pending_count_);
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
        flush_offset_ = 0;
        return true;
    }
    // AUT-862 P1: gate on connectivity — let processDeferredSpoolFlush re-arm if not ready
    if (!mqtt.isConnected()) {
        return false;
    }
    // AUT-882: heap guard before any allocation — defer (re-arm) instead of OOM /
    // silent RAM-String truncation. Re-armed by processDeferredSpoolFlush (main.cpp:750-753).
    if (ESP.getFreeHeap() < kFlushHeapGuardBytes) {
        char hg_msg[80];
        snprintf(hg_msg, sizeof(hg_msg), "flush deferred: heap low (%lu B < %lu)",
                 (unsigned long)ESP.getFreeHeap(), (unsigned long)kFlushHeapGuardBytes);
        LOG_W(SPOOL_TAG, hg_msg);
        return false;
    }

    File f = LittleFS.open(kSpoolFilePath, "r");
    if (!f) {
        ESP_LOGE(SPOOL_TAG, "Failed to open spool file for flush");
        return false;
    }
    const size_t file_size = f.size();

    // AUT-882: validate the persisted cursor. A past-EOF cursor means the file was
    // replaced/shrunk — re-scan from the front (favour no-loss over no-duplicate).
    if (flush_offset_ > file_size) {
        char fsc_msg[80];
        snprintf(fsc_msg, sizeof(fsc_msg), "flush: stale cursor %lu > size %lu, resetting",
                 (unsigned long)flush_offset_, (unsigned long)file_size);
        LOG_W(SPOOL_TAG, fsc_msg);
        flush_offset_ = 0;
    }
    if (!f.seek(flush_offset_)) {
        f.close();
        ESP_LOGE(SPOOL_TAG, "flush: seek to %lu failed", (unsigned long)flush_offset_);
        return false;
    }

    // AUT-882: stream from the cursor; advance a byte offset per published line.
    // The file is NOT rewritten here — O(1) heap, O(N) flash over a full drain.
    uint32_t flushed = 0;
    size_t   cursor  = flush_offset_;

    while (f.available() && flushed < kBatchFlushSize) {
        // Per-line heap guard — pause mid-batch rather than risk an allocation OOM.
        if (ESP.getFreeHeap() < kFlushHeapGuardBytes) {
            char hgb_msg[64];
            snprintf(hgb_msg, sizeof(hgb_msg), "flush paused mid-batch: heap low (%lu B)",
                     (unsigned long)ESP.getFreeHeap());
            LOG_W(SPOOL_TAG, hgb_msg);
            break;
        }

        String line = f.readStringUntil('\n');
        const size_t consumed = line.length() + 1;  // include the consumed '\n' delimiter
        if (line.length() < 3) {                     // skip empty/short, still advance cursor
            cursor += consumed;
            continue;
        }

        // Parse and re-publish
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, line);
        if (err) {
            ESP_LOGW(SPOOL_TAG, "Skipping malformed spool line: %s", err.c_str());
            cursor += consumed;   // consume corrupt line — not worth retrying
            flushed++;
            if (pending_count_ > 0) pending_count_--;
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
        if (pq == PublishQueueEnqueueResult::Enqueued) {
            cursor += consumed;        // advance the cursor only on a successful enqueue
            flushed++;
            if (pending_count_ > 0) pending_count_--;
        } else {
            // Queue full / backpressure — stop. The cursor stays on this line so the
            // next (re-armed) flush retries it. No data loss, no file rewrite.
            break;
        }
    }
    const bool reached_eof = !f.available();
    f.close();

    // Persist the advanced cursor (one NVS write per tick; NVS skips no-op writes).
    if (cursor != flush_offset_) {
        flush_offset_ = cursor;
        persistFlushOffset();
    }

    char flush_msg[96];
    snprintf(flush_msg, sizeof(flush_msg),
             "Spool flush: sent=%lu, cursor=%lu/%lu, pending=%lu",
             (unsigned long)flushed, (unsigned long)cursor,
             (unsigned long)file_size, (unsigned long)pending_count_);
    LOG_I(SPOOL_TAG, flush_msg);

    // AUT-882: compact only when the drain is complete — "remove nur wenn
    // cursor == fileSize" (no new race window vs. the previous design).
    if (cursor >= file_size && reached_eof) {
        if (compactDroppingPrefix(file_size)) {   // removes the now fully-drained file
            flush_offset_ = 0;
            persistFlushOffset();
            pending_count_ = 0;
            return true;
        }
        // Removal failed (transient) — keep cursor at EOF and retry on next re-arm.
        flush_offset_ = file_size;
        persistFlushOffset();
        return false;
    }
    return false;   // more remain → processDeferredSpoolFlush re-arms (2000ms)
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

// ============================================
// compactDroppingPrefix() — AUT-882
// Single shared, heap-bounded compaction path used by BOTH flushPending()
// (full-drain removal) and dropOldestLine() (front-drop). Streams the bytes from
// `drop_before` to EOF via a small stack buffer (no RAM String) into a temp file
// and atomically renames it over the spool file. When nothing remains, the spool
// file is simply removed. Byte-faithful, so offsets after `drop_before` keep their
// position and the caller's cursor arithmetic stays valid.
// ============================================
bool SpoolManager::compactDroppingPrefix(size_t drop_before) {
    if (!LittleFS.exists(kSpoolFilePath)) return true;

    File src = LittleFS.open(kSpoolFilePath, "r");
    if (!src) {
        ESP_LOGE(SPOOL_TAG, "compact: open read failed");
        return false;
    }
    const size_t file_size = src.size();

    // Nothing remains after the dropped prefix → remove the spool file outright.
    if (drop_before >= file_size) {
        src.close();
        return LittleFS.remove(kSpoolFilePath);
    }

    if (!src.seek(drop_before)) {
        src.close();
        ESP_LOGE(SPOOL_TAG, "compact: seek to %lu failed", (unsigned long)drop_before);
        return false;
    }

    File dst = LittleFS.open(kSpoolTempPath, "w");
    if (!dst) {
        src.close();
        ESP_LOGE(SPOOL_TAG, "compact: open temp failed");
        return false;
    }

    // Faithful byte copy through a small stack buffer — heap-flat (no String),
    // so the surviving bytes keep their exact offsets.
    uint8_t buf[256];
    bool ok = true;
    while (true) {
        int n = src.read(buf, sizeof(buf));
        if (n <= 0) break;
        if (dst.write(buf, (size_t)n) != (size_t)n) {
            ESP_LOGE(SPOOL_TAG, "compact: write failed (disk full?)");
            ok = false;
            break;
        }
    }
    dst.close();
    src.close();

    if (!ok) {
        LittleFS.remove(kSpoolTempPath);   // discard partial temp — original intact
        return false;
    }

    // Atomic replace (lfs_rename overwrites the destination atomically).
    if (!LittleFS.rename(kSpoolTempPath, kSpoolFilePath)) {
        LittleFS.remove(kSpoolTempPath);
        ESP_LOGE(SPOOL_TAG, "compact: rename failed");
        return false;
    }
    return true;
}

// ============================================
// persistFlushOffset() / loadFlushOffset() — AUT-882
// Persist the byte cursor so a mid-drain reboot resumes exactly where it stopped
// (NVS namespace "spool", key "flush_off" == spool_flush_off).
// ============================================
void SpoolManager::persistFlushOffset() {
    if (storageManager.beginNamespace(kSpoolNvsNamespace, false)) {
        storageManager.putULong(kSpoolNvsCursorKey, (unsigned long)flush_offset_);
        storageManager.endNamespace();
    } else {
        // NVS busy this tick — the in-RAM cursor stays correct for the current
        // session; only a reboot within this window would re-scan from the front.
        ESP_LOGW(SPOOL_TAG, "persistFlushOffset: NVS namespace busy, cursor not saved");
    }
}

size_t SpoolManager::loadFlushOffset() {
    size_t off = 0;
    if (storageManager.beginNamespace(kSpoolNvsNamespace, true)) {
        off = (size_t)storageManager.getULong(kSpoolNvsCursorKey, 0);
        storageManager.endNamespace();
    }
    return off;
}
