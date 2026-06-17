#include "intent_contract.h"

#include <ArduinoJson.h>
#include <Preferences.h>
#include <atomic>
#include <cstring>
#include <esp_log.h>
#include <freertos/portmacro.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include "../services/communication/mqtt_client.h"
#include "../utils/logger.h"
#include "../utils/time_manager.h"
#include "../utils/topic_builder.h"
#ifndef MQTT_USE_PUBSUBCLIENT
#include "publish_queue.h"
#endif

static const char* IC_TAG = "INTENT";
static std::atomic<uint32_t> s_intent_fallback_counter{0};
static std::atomic<uint32_t> s_corr_fallback_counter{0};
static std::atomic<uint32_t> s_safety_epoch{0};
// AUT-347: chain-stage lifecycle publish could not be enqueued (COMM backpressure / full queue).
static std::atomic<uint32_t> s_chain_stage_enqueue_fail_count{0};
static constexpr uint8_t INTENT_FINAL_STORE_CAPACITY = 24;
// Reduced from 32→24 (2026-06-14) to reclaim 704 B DRAM for pulse-ISR additions (AUT-848).
// 24 slots cover normal bursts; critical terminals (written first) are preserved.
static constexpr uint8_t OUTCOME_OUTBOX_CAPACITY = 48;
static constexpr uint8_t OUTCOME_OUTBOX_RETRY_LIMIT = 5;
static Preferences s_outcome_outbox_prefs;
static bool s_outbox_stats_loaded = false;
static bool s_outbox_storage_degraded = false;
static unsigned long s_outbox_storage_backoff_until_ms = 0;
static unsigned long s_replay_backoff_until_ms = 0;
static const char* s_replay_backoff_reason = "none";
static uint32_t s_outcome_retry_count = 0;
static uint32_t s_outcome_recovered_count = 0;
static uint32_t s_outcome_drop_count_critical = 0;
static uint32_t s_outcome_final_confirmed_count = 0;
static const char* kOutboxStatRetryTotalKey = "retry_total";
static const char* kOutboxStatRecoveredTotalKey = "recovered_total";
static const char* kOutboxStatDropTotalKey = "drop_total";
// NVS keys are limited in length, keep this short.
static const char* kOutboxStatFinalConfirmedTotalKey = "fin_ok_total";
static SemaphoreHandle_t s_outbox_mutex = nullptr;
static portMUX_TYPE s_outbox_mutex_init_mux = portMUX_INITIALIZER_UNLOCKED;

struct IntentFinalEntry {
    char intent_id[INTENT_ID_MAX_LEN];
    char final_outcome[16];
    uint32_t final_ts;
    bool valid;
};

static IntentFinalEntry s_intent_final_store[INTENT_FINAL_STORE_CAPACITY] = {};
static uint8_t s_intent_final_write_index = 0;
static portMUX_TYPE s_intent_final_mux = portMUX_INITIALIZER_UNLOCKED;

struct PendingOutcomeEntry {
    char flow[16];
    IntentMetadata metadata;
    char outcome[16];
    char code[64];
    char reason[160];
    bool retryable;
    uint8_t attempt;
};

static bool isTerminalOutcome(const char* outcome) {
    if (outcome == nullptr) {
        return true;
    }
    return strcmp(outcome, "accepted") != 0 && strcmp(outcome, "processing") != 0;
}

static bool isCriticalOutcomeClass(const char* flow, const char* outcome) {
    if (isTerminalOutcome(outcome)) {
        return true;
    }
    if (flow != nullptr && strcmp(flow, "publish") == 0) {
        return true;
    }
    return flow != nullptr && strcmp(flow, "command") == 0 &&
           outcome != nullptr && strcmp(outcome, "applied") == 0;
}

static int findFinalIntentEntry(const char* intent_id) {
    if (intent_id == nullptr || strlen(intent_id) == 0) {
        return -1;
    }
    for (uint8_t i = 0; i < INTENT_FINAL_STORE_CAPACITY; i++) {
        if (!s_intent_final_store[i].valid) {
            continue;
        }
        if (strcmp(s_intent_final_store[i].intent_id, intent_id) == 0) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

static const char* mapLegacyStatus(const char* normalized_outcome) {
    if (normalized_outcome == nullptr) {
        return "failed";
    }
    if (strcmp(normalized_outcome, "persisted") == 0) {
        return "success";
    }
    if (strcmp(normalized_outcome, "accepted") == 0 || strcmp(normalized_outcome, "applied") == 0) {
        return "processing";
    }
    return normalized_outcome;
}

static String buildFallbackId(const char* prefix, std::atomic<uint32_t>& counter_ref) {
    uint32_t idx = counter_ref.fetch_add(1) + 1;
    // [FIX1-VERIFY] snprintf on a stack buffer — zero heap allocs before String(buf).
    // Previous 4-concat chain (String(prefix) + "_" + String(millis()) + ...) could
    // allocate-fail under OUTBOX pressure, leaving buffer=nullptr → LoadProhibited crash.
    char buf[64];
    snprintf(buf, sizeof(buf), "%s_%lu_%u",
             prefix != nullptr ? prefix : "fw",
             (unsigned long)millis(), (unsigned int)idx);
    buf[sizeof(buf) - 1] = '\0';
    uint32_t heap = ESP.getFreeHeap();
    char log_msg[96];
    snprintf(log_msg, sizeof(log_msg),
             "[FIX1-VERIFY] buildFallbackId: id=%s heap=%u", buf, heap);
    if (heap < 30000) {
        LOG_W(IC_TAG, log_msg);
    } else {
        LOG_D(IC_TAG, log_msg);
    }
    return String(buf);
}

static SemaphoreHandle_t getOutboxMutex() {
    if (s_outbox_mutex != nullptr) {
        return s_outbox_mutex;
    }
    portENTER_CRITICAL(&s_outbox_mutex_init_mux);
    if (s_outbox_mutex == nullptr) {
        s_outbox_mutex = xSemaphoreCreateMutex();
    }
    portEXIT_CRITICAL(&s_outbox_mutex_init_mux);
    return s_outbox_mutex;
}

static bool acquireOutboxLock(TickType_t wait_ticks = pdMS_TO_TICKS(200)) {
    if (xTaskGetSchedulerState() == taskSCHEDULER_NOT_STARTED) {
        // setup()-Phase: single-threaded path, no mutex required.
        return true;
    }
    SemaphoreHandle_t mutex = getOutboxMutex();
    if (mutex == nullptr) {
        return false;
    }
    return xSemaphoreTake(mutex, wait_ticks) == pdTRUE;
}

static void releaseOutboxLock() {
    if (xTaskGetSchedulerState() == taskSCHEDULER_NOT_STARTED) {
        return;
    }
    if (s_outbox_mutex != nullptr) {
        xSemaphoreGive(s_outbox_mutex);
    }
}

class OutboxLockGuard {
public:
    explicit OutboxLockGuard(const char* owner, TickType_t wait_ticks = pdMS_TO_TICKS(200))
        : owner_(owner != nullptr ? owner : "unknown"),
          wait_ticks_(wait_ticks),
          acquire_started_ms_(millis()),
          lock_acquired_ms_(0),
          locked_(acquireOutboxLock(wait_ticks)) {
        if (locked_) {
            lock_acquired_ms_ = millis();
        } else {
            // #region agent log
            LOG_W(IC_TAG, String("[DBG5126ae] outbox lock acquire timeout owner=") + owner_ +
                              " wait_ms=" + String(pdTICKS_TO_MS(wait_ticks_)) +
                              " uptime_ms=" + String(acquire_started_ms_));
            // #endregion
        }
    }
    ~OutboxLockGuard() {
        if (locked_) {
            const unsigned long held_ms = millis() - lock_acquired_ms_;
            if (held_ms >= 80UL) {
                // #region agent log
                LOG_W(IC_TAG, String("[DBG5126ae] outbox lock hold owner=") + owner_ +
                                  " held_ms=" + String(held_ms) +
                                  " wait_ms=" + String(pdTICKS_TO_MS(wait_ticks_)));
                // #endregion
            }
            releaseOutboxLock();
        }
    }
    bool locked() const { return locked_; }

private:
    const char* owner_;
    TickType_t wait_ticks_;
    unsigned long acquire_started_ms_;
    unsigned long lock_acquired_ms_;
    bool locked_;
};

static bool beginOutcomeOutboxPrefs(bool read_only) {
    esp_log_level_set("Preferences", ESP_LOG_NONE);
    esp_log_level_set("Preferences.cpp", ESP_LOG_NONE);
    bool ok = s_outcome_outbox_prefs.begin("io_outbox", read_only);
    esp_log_level_set("Preferences", ESP_LOG_WARN);
    esp_log_level_set("Preferences.cpp", ESP_LOG_WARN);
    return ok;
}

static bool putOutboxUCharChecked(const char* key, uint8_t value) {
    return key != nullptr && s_outcome_outbox_prefs.putUChar(key, value) > 0;
}

static bool putOutboxUIntChecked(const char* key, uint32_t value) {
    return key != nullptr && s_outcome_outbox_prefs.putUInt(key, value) > 0;
}

static bool putOutboxBoolChecked(const char* key, bool value) {
    return key != nullptr && s_outcome_outbox_prefs.putBool(key, value) > 0;
}

static bool putOutboxStringChecked(const char* key, const String& value) {
    if (key == nullptr) {
        return false;
    }
    return s_outcome_outbox_prefs.putString(key, value) > 0;
}

static void markOutboxStorageDegraded(const char* owner, const char* key) {
    s_outbox_storage_degraded = true;
    s_outbox_storage_backoff_until_ms = millis() + 15000UL;
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] outbox storage degraded owner=") +
                   String(owner != nullptr ? owner : "unknown") +
                   " key=" + String(key != nullptr ? key : "unknown") +
                   " backoff_until=" + String(s_outbox_storage_backoff_until_ms));
    // #endregion
}

static bool resetOutboxStorageUnsafe(const char* owner) {
    if (!s_outcome_outbox_prefs.clear()) {
        markOutboxStorageDegraded(owner, "clear");
        return false;
    }
    bool ok = true;
    ok = putOutboxUCharChecked("head", 0) && ok;
    ok = putOutboxUCharChecked("count", 0) && ok;
    ok = putOutboxUIntChecked(kOutboxStatRetryTotalKey, s_outcome_retry_count) && ok;
    ok = putOutboxUIntChecked(kOutboxStatRecoveredTotalKey, s_outcome_recovered_count) && ok;
    ok = putOutboxUIntChecked(kOutboxStatDropTotalKey, s_outcome_drop_count_critical) && ok;
    ok = putOutboxUIntChecked(kOutboxStatFinalConfirmedTotalKey, s_outcome_final_confirmed_count) && ok;
    if (!ok) {
        markOutboxStorageDegraded(owner, "reset_head_count");
        return false;
    }
    s_outbox_storage_degraded = false;
    s_outbox_storage_backoff_until_ms = 0;
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] outbox storage reset owner=") +
                   String(owner != nullptr ? owner : "unknown"));
    // #endregion
    return true;
}

static void scheduleReplayBackoffMs(const char* reason, unsigned long delay_ms) {
    const unsigned long now = millis();
    const unsigned long bounded_delay = (delay_ms > 5000UL) ? 5000UL : delay_ms;
    s_replay_backoff_until_ms = now + bounded_delay;
    s_replay_backoff_reason = reason != nullptr ? reason : "unknown";
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] replay backoff scheduled reason=") +
                   String(s_replay_backoff_reason) +
                   " delay_ms=" + String(bounded_delay) +
                   " until=" + String(s_replay_backoff_until_ms));
    // #endregion
}

static String outboxKey(uint8_t idx, const char* suffix) {
    return "s" + String(idx) + "_" + String(suffix);
}

static void loadOutboxStatsLocked() {
    const unsigned long stats_started_ms = millis();
    if (s_outbox_stats_loaded) {
        return;
    }
    if (!beginOutcomeOutboxPrefs(true)) {
        s_outbox_stats_loaded = true;
        return;
    }
    s_outcome_retry_count = s_outcome_outbox_prefs.getUInt(kOutboxStatRetryTotalKey, 0);
    s_outcome_recovered_count = s_outcome_outbox_prefs.getUInt(kOutboxStatRecoveredTotalKey, 0);
    s_outcome_drop_count_critical = s_outcome_outbox_prefs.getUInt(kOutboxStatDropTotalKey, 0);
    s_outcome_final_confirmed_count =
        s_outcome_outbox_prefs.getUInt(kOutboxStatFinalConfirmedTotalKey, 0);
    s_outcome_outbox_prefs.end();
    s_outbox_stats_loaded = true;
    const unsigned long stats_duration_ms = millis() - stats_started_ms;
    if (stats_duration_ms > 50UL) {
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] outbox stats load cost duration_ms=") +
                       String(stats_duration_ms) +
                       " retry_total=" + String(s_outcome_retry_count) +
                       " recovered_total=" + String(s_outcome_recovered_count) +
                       " drop_total=" + String(s_outcome_drop_count_critical));
        // #endregion
    }
}

static void loadOutboxStatsIfNeeded() {
    OutboxLockGuard guard("load_stats");
    if (!guard.locked()) {
        LOG_W(IC_TAG, "Outbox stats lock timeout (load)");
        return;
    }
    loadOutboxStatsLocked();
}

static bool s_outbox_stats_dirty = false;

static void persistOutboxStatsLocked() {
    if (!beginOutcomeOutboxPrefs(false)) {
        return;
    }
    bool ok = true;
    ok = putOutboxUIntChecked(kOutboxStatRetryTotalKey, s_outcome_retry_count) && ok;
    ok = putOutboxUIntChecked(kOutboxStatRecoveredTotalKey, s_outcome_recovered_count) && ok;
    ok = putOutboxUIntChecked(kOutboxStatDropTotalKey, s_outcome_drop_count_critical) && ok;
    ok = putOutboxUIntChecked(kOutboxStatFinalConfirmedTotalKey,
                              s_outcome_final_confirmed_count) && ok;
    if (!ok) {
        markOutboxStorageDegraded("persist_stats", "stats");
    }
    s_outcome_outbox_prefs.end();
}

static void persistOutboxStats() {
    OutboxLockGuard guard("persist_stats");
    if (!guard.locked()) {
        LOG_W(IC_TAG, "Outbox stats lock timeout (persist)");
        return;
    }
    persistOutboxStatsLocked();
}

static void requestPersistOutboxStats() {
    s_outbox_stats_dirty = true;
}

void processDeferredOutboxStatsPersist() {
    if (!s_outbox_stats_dirty) {
        return;
    }
    const PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
    if (pq_stats.fill_level >= PUBLISH_QUEUE_SHED_WATERMARK) {
        return;
    }
    s_outbox_stats_dirty = false;
    persistOutboxStats();
}

static bool saveOutboxEntryAt(uint8_t idx,
                              const PendingOutcomeEntry& entry,
                              const char* owner = "unknown") {
    const unsigned long save_started_ms = millis();
    bool ok = true;
    ok = putOutboxStringChecked(outboxKey(idx, "flow").c_str(), String(entry.flow)) && ok;
    ok = putOutboxStringChecked(outboxKey(idx, "intent").c_str(), String(entry.metadata.intent_id)) && ok;
    ok = putOutboxStringChecked(outboxKey(idx, "corr").c_str(), String(entry.metadata.correlation_id)) && ok;
    ok = putOutboxUIntChecked(outboxKey(idx, "gen").c_str(), entry.metadata.generation) && ok;
    ok = putOutboxUIntChecked(outboxKey(idx, "created").c_str(), entry.metadata.created_at_ms) && ok;
    ok = putOutboxUIntChecked(outboxKey(idx, "ttl").c_str(), entry.metadata.ttl_ms) && ok;
    ok = putOutboxUIntChecked(outboxKey(idx, "epoch").c_str(), entry.metadata.epoch_at_accept) && ok;
    ok = putOutboxStringChecked(outboxKey(idx, "outcome").c_str(), String(entry.outcome)) && ok;
    ok = putOutboxStringChecked(outboxKey(idx, "code").c_str(), String(entry.code)) && ok;
    ok = putOutboxStringChecked(outboxKey(idx, "reason").c_str(), String(entry.reason)) && ok;
    ok = putOutboxBoolChecked(outboxKey(idx, "retryable").c_str(), entry.retryable) && ok;
    ok = putOutboxUCharChecked(outboxKey(idx, "attempt").c_str(), entry.attempt) && ok;
    if (!ok) {
        markOutboxStorageDegraded(owner, "save_entry");
    }
    const unsigned long save_duration_ms = millis() - save_started_ms;
    if (save_duration_ms > 50UL) {
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] outbox save entry cost owner=") +
                       String(owner != nullptr ? owner : "unknown") +
                       " idx=" + String(idx) +
                       " attempt=" + String(entry.attempt) +
                       " duration_ms=" + String(save_duration_ms));
        // #endregion
    }
    return ok;
}

static bool isSameOutboxEntryIdentity(const PendingOutcomeEntry& lhs, const PendingOutcomeEntry& rhs) {
    return strncmp(lhs.metadata.intent_id, rhs.metadata.intent_id, sizeof(lhs.metadata.intent_id)) == 0 &&
           strncmp(lhs.metadata.correlation_id, rhs.metadata.correlation_id, sizeof(lhs.metadata.correlation_id)) == 0 &&
           lhs.metadata.created_at_ms == rhs.metadata.created_at_ms &&
           lhs.metadata.generation == rhs.metadata.generation &&
           strncmp(lhs.code, rhs.code, sizeof(lhs.code)) == 0 &&
           strncmp(lhs.flow, rhs.flow, sizeof(lhs.flow)) == 0;
}

static void copyStringFieldSafe(char* dest,
                                size_t dest_len,
                                const String& src,
                                const char* field_name,
                                uint8_t idx) {
    if (dest == nullptr || dest_len == 0) {
        return;
    }
    const char* src_ptr = src.c_str();
    if (src_ptr == nullptr) {
        dest[0] = '\0';
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] outbox null string field field=") +
                       String(field_name != nullptr ? field_name : "unknown") +
                       " idx=" + String(idx));
        // #endregion
        return;
    }
    strncpy(dest, src_ptr, dest_len - 1);
    dest[dest_len - 1] = '\0';
}

static bool loadOutboxEntryAt(uint8_t idx, PendingOutcomeEntry* entry_out) {
    if (entry_out == nullptr) {
        return false;
    }
    String intent = s_outcome_outbox_prefs.getString(outboxKey(idx, "intent").c_str(), "");
    if (intent.length() == 0) {
        return false;
    }
    memset(entry_out, 0, sizeof(PendingOutcomeEntry));
    String flow = s_outcome_outbox_prefs.getString(outboxKey(idx, "flow").c_str(), "unknown");
    String corr = s_outcome_outbox_prefs.getString(outboxKey(idx, "corr").c_str(), "");
    String outcome = s_outcome_outbox_prefs.getString(outboxKey(idx, "outcome").c_str(), "failed");
    String code = s_outcome_outbox_prefs.getString(outboxKey(idx, "code").c_str(), "EXECUTE_FAIL");
    String reason = s_outcome_outbox_prefs.getString(outboxKey(idx, "reason").c_str(), "Pending outcome replay");

    copyStringFieldSafe(entry_out->flow, sizeof(entry_out->flow), flow, "flow", idx);
    copyStringFieldSafe(entry_out->metadata.intent_id,
                        sizeof(entry_out->metadata.intent_id),
                        intent,
                        "intent",
                        idx);
    copyStringFieldSafe(entry_out->metadata.correlation_id,
                        sizeof(entry_out->metadata.correlation_id),
                        corr,
                        "corr",
                        idx);
    entry_out->metadata.generation = s_outcome_outbox_prefs.getUInt(outboxKey(idx, "gen").c_str(), 0);
    entry_out->metadata.created_at_ms = s_outcome_outbox_prefs.getUInt(outboxKey(idx, "created").c_str(), millis());
    entry_out->metadata.ttl_ms = s_outcome_outbox_prefs.getUInt(outboxKey(idx, "ttl").c_str(), 0);
    entry_out->metadata.epoch_at_accept = s_outcome_outbox_prefs.getUInt(outboxKey(idx, "epoch").c_str(), 0);
    copyStringFieldSafe(entry_out->outcome, sizeof(entry_out->outcome), outcome, "outcome", idx);
    copyStringFieldSafe(entry_out->code, sizeof(entry_out->code), code, "code", idx);
    copyStringFieldSafe(entry_out->reason, sizeof(entry_out->reason), reason, "reason", idx);
    entry_out->retryable = s_outcome_outbox_prefs.getBool(outboxKey(idx, "retryable").c_str(), true);
    entry_out->attempt = s_outcome_outbox_prefs.getUChar(outboxKey(idx, "attempt").c_str(), 1);
    return true;
}

static bool clearOutboxEntryAt(uint8_t idx, const char* owner = "unknown") {
    const unsigned long clear_started_ms = millis();
    // Soft-clear for NVS cost control:
    // loadOutboxEntryAt() treats empty "intent" as empty slot and returns false early.
    // Keeping other keys avoids expensive remove/isKey scans (12 keys) in lock scope.
    // Next saveOutboxEntryAt() overwrite fully replaces stale fields at this index.
    bool ok = true;
    ok = putOutboxStringChecked(outboxKey(idx, "intent").c_str(), "") && ok;
    ok = putOutboxUCharChecked(outboxKey(idx, "attempt").c_str(), 0) && ok;
    if (!ok) {
        markOutboxStorageDegraded(owner, "clear_entry");
    }
    const unsigned long clear_duration_ms = millis() - clear_started_ms;
    if (clear_duration_ms > 50UL) {
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] outbox clear entry cost owner=") +
                       String(owner != nullptr ? owner : "unknown") +
                       " idx=" + String(idx) +
                       " duration_ms=" + String(clear_duration_ms));
        // #endregion
    }
    return ok;
}

static bool enqueueCriticalOutcome(const PendingOutcomeEntry& entry) {
    const unsigned long enqueue_started_ms = millis();
    uint8_t enqueue_write_ops = 0;
    const char* enqueue_action = "enqueue_ok";
    OutboxLockGuard guard("enqueue_critical");
    if (!guard.locked()) {
        enqueue_action = "lock_timeout";
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] enqueue critical cost action=") +
                       String(enqueue_action) +
                       " write_ops=" + String(enqueue_write_ops) +
                       " duration_ms=" + String(millis() - enqueue_started_ms));
        // #endregion
        LOG_E(IC_TAG, "Outbox lock timeout while enqueueing critical outcome");
        return false;
    }
    loadOutboxStatsLocked();
    if (!beginOutcomeOutboxPrefs(false)) {
        enqueue_action = "prefs_begin_fail";
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] enqueue critical cost action=") +
                       String(enqueue_action) +
                       " write_ops=" + String(enqueue_write_ops) +
                       " duration_ms=" + String(millis() - enqueue_started_ms));
        // #endregion
        return false;
    }
    uint8_t head = s_outcome_outbox_prefs.getUChar("head", 0);
    uint8_t count = s_outcome_outbox_prefs.getUChar("count", 0);

    // P0 Strategy A: NVS outcome outbox full → evict oldest pending replay slot so a new
    // critical outcome is never silently dropped. Superseded entry is counted in
    // outcome_drop_count_critical (heartbeat + outcome payload telemetry).
    if (count >= OUTCOME_OUTBOX_CAPACITY) {
        enqueue_action = "evict_oldest";
        if (!clearOutboxEntryAt(head, "enqueue_evict_oldest")) {
            enqueue_action = "evict_clear_fail";
            resetOutboxStorageUnsafe("enqueue_evict_oldest");
            s_outcome_outbox_prefs.end();
            return false;
        }
        enqueue_write_ops++;
        head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
        count--;
        s_outcome_drop_count_critical++;
        LOG_W(IC_TAG,
              "Critical outcome outbox full — evicted oldest NVS slot to enqueue new critical");
        if (!putOutboxUIntChecked(kOutboxStatDropTotalKey, s_outcome_drop_count_critical)) {
            markOutboxStorageDegraded("enqueue_critical", kOutboxStatDropTotalKey);
        }
        enqueue_write_ops++;
    }

    uint8_t idx = static_cast<uint8_t>((head + count) % OUTCOME_OUTBOX_CAPACITY);
    if (!saveOutboxEntryAt(idx, entry, "enqueue_critical")) {
        enqueue_action = "save_entry_fail";
        resetOutboxStorageUnsafe("enqueue_critical");
        s_outcome_outbox_prefs.end();
        return false;
    }
    enqueue_write_ops++;
    if (!putOutboxUCharChecked("head", head)) {
        enqueue_action = "head_write_fail";
        resetOutboxStorageUnsafe("enqueue_critical");
        s_outcome_outbox_prefs.end();
        return false;
    }
    enqueue_write_ops++;
    if (!putOutboxUCharChecked("count", static_cast<uint8_t>(count + 1))) {
        enqueue_action = "count_write_fail";
        resetOutboxStorageUnsafe("enqueue_critical");
        s_outcome_outbox_prefs.end();
        return false;
    }
    enqueue_write_ops++;
    s_outcome_outbox_prefs.end();
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] enqueue critical cost action=") +
                   String(enqueue_action) +
                   " write_ops=" + String(enqueue_write_ops) +
                   " duration_ms=" + String(millis() - enqueue_started_ms) +
                   " count_before=" + String(count));
    // #endregion
    return true;
}

static bool buildOutcomePayload(const char* flow,
                                const IntentMetadata& metadata,
                                const char* normalized_outcome,
                                const char* code,
                                const String& reason,
                                bool retryable,
                                bool critical,
                                uint8_t retry_count,
                                bool recovered,
                                String* payload_out) {
    if (payload_out == nullptr) {
        return false;
    }

    // 26 fields × 12 bytes/slot = 312, plus ~463 bytes for key+value strings.
    // Using 1024 gives a safe 250-byte margin against overflow-silent field drops.
    DynamicJsonDocument doc(1024);
    doc["seq"] = mqttClient.getNextSeq();
    doc["flow"] = flow != nullptr ? flow : "unknown";
    doc["intent_id"] = metadata.intent_id;
    doc["correlation_id"] = metadata.correlation_id;
    doc["generation"] = metadata.generation;
    doc["created_at_ms"] = metadata.created_at_ms;
    doc["ttl_ms"] = metadata.ttl_ms;
    doc["epoch"] = metadata.epoch_at_accept;
    doc["outcome"] = normalized_outcome;
    doc["contract_version"] = 2;
    doc["semantic_mode"] = "target";
    doc["legacy_status"] = mapLegacyStatus(normalized_outcome);
    doc["target_status"] = normalized_outcome;
    doc["code"] = code != nullptr ? code : "UNKNOWN_ERROR";
    doc["reason"] = reason;
    doc["retryable"] = retryable;
    doc["critical"] = critical;
    doc["retry_limit"] = OUTCOME_OUTBOX_RETRY_LIMIT;
    doc["retry_count"] = retry_count;
    doc["recovered"] = recovered;
    doc["delivery_mode"] = recovered ? "recovered" : "direct";
    doc["outcome_retry_count"] = s_outcome_retry_count;
    doc["outcome_recovered_count"] = s_outcome_recovered_count;
    doc["outcome_drop_count_critical"] = s_outcome_drop_count_critical;
    doc["outcome_final_confirmed_count"] = s_outcome_final_confirmed_count;
    doc["ts"] = static_cast<unsigned long>(timeManager.getUnixTimestamp());

    payload_out->clear();
    size_t written = serializeJson(doc, *payload_out);
    return written > 0 && payload_out->length() > 0;
}

void processIntentOutcomeOutbox() {
    PendingOutcomeEntry candidate{};
    String replay_payload;
    String topic = TopicBuilder::buildIntentOutcomeTopic();
    bool has_candidate = false;

    {
        OutboxLockGuard guard("replay_prepare");
        if (!guard.locked()) {
            LOG_W(IC_TAG, "Outbox lock timeout during replay");
            return;
        }
        loadOutboxStatsLocked();
        if (!mqttClient.isConnected()) {
            return;
        }
        if (s_replay_backoff_until_ms > 0 && millis() < s_replay_backoff_until_ms) {
            static unsigned long s_last_replay_backoff_active_log_ms = 0;
            const unsigned long now = millis();
            if (s_last_replay_backoff_active_log_ms == 0UL ||
                (now - s_last_replay_backoff_active_log_ms) >= 1000UL) {
                s_last_replay_backoff_active_log_ms = now;
                // #region agent log
                LOG_W(IC_TAG, String("[DBG5126ae] replay backoff active reason=") +
                               String(s_replay_backoff_reason != nullptr ? s_replay_backoff_reason : "unknown") +
                               " now=" + String(now) +
                               " until=" + String(s_replay_backoff_until_ms));
                // #endregion
            }
            return;
        }
        if (s_outbox_storage_degraded && millis() < s_outbox_storage_backoff_until_ms) {
            return;
        }
        // AUT-56 hardening: do not consume replay attempts while registration gate is closed.
        if (!mqttClient.isRegistrationConfirmed()) {
            return;
        }
        if (!beginOutcomeOutboxPrefs(false)) {
            return;
        }

        uint8_t head = s_outcome_outbox_prefs.getUChar("head", 0);
        uint8_t count = s_outcome_outbox_prefs.getUChar("count", 0);
        if (count == 0) {
            s_outcome_outbox_prefs.end();
            return;
        }

        if (!loadOutboxEntryAt(head, &candidate)) {
            if (!clearOutboxEntryAt(head, "drain_replay_corrupt_drop")) {
                resetOutboxStorageUnsafe("drain_replay_corrupt_drop");
                s_outcome_outbox_prefs.end();
                return;
            }
            head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
            count--;
            if (!putOutboxUCharChecked("head", head) ||
                !putOutboxUCharChecked("count", count)) {
                resetOutboxStorageUnsafe("drain_replay_corrupt_drop");
                s_outcome_outbox_prefs.end();
                return;
            }
            s_outcome_outbox_prefs.end();
            return;
        }

        static unsigned long s_last_replay_prepare_log_ms = 0;
        const unsigned long now_prepare_ms = millis();
        if (s_last_replay_prepare_log_ms == 0UL ||
            (now_prepare_ms - s_last_replay_prepare_log_ms) >= 2000UL) {
            s_last_replay_prepare_log_ms = now_prepare_ms;
            // #region agent log
            LOG_W(IC_TAG, String("[DBG5126ae] replay prepare state head=") +
                           String(head) +
                           " count=" + String(count) +
                           " attempt=" + String(candidate.attempt) +
                           " mqtt_connected=" + String(mqttClient.isConnected() ? 1 : 0) +
                           " reg_confirmed=" + String(mqttClient.isRegistrationConfirmed() ? 1 : 0));
            // #endregion
        }

        {
            IntentInvalidationReason stale_reason =
                getIntentInvalidationReason(candidate.metadata, getSafetyEpoch());
            if (stale_reason != IntentInvalidationReason::NONE) {
                if (!clearOutboxEntryAt(head, "replay_stale_epoch_drop")) {
                    resetOutboxStorageUnsafe("replay_stale_epoch_drop");
                    s_outcome_outbox_prefs.end();
                    return;
                }
                head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
                count--;
                if (!putOutboxUCharChecked("head", head) ||
                    !putOutboxUCharChecked("count", count)) {
                    resetOutboxStorageUnsafe("replay_stale_epoch_drop");
                    s_outcome_outbox_prefs.end();
                    return;
                }
                s_outcome_outbox_prefs.end();
                return;
            }
        }

        if (!buildOutcomePayload(candidate.flow,
                                 candidate.metadata,
                                 candidate.outcome,
                                 candidate.code,
                                 String(candidate.reason),
                                 candidate.retryable,
                                 true,
                                 candidate.attempt,
                                 true,
                                 &replay_payload)) {
            if (!clearOutboxEntryAt(head, "drain_replay_stale_drop")) {
                resetOutboxStorageUnsafe("drain_replay_stale_drop");
                s_outcome_outbox_prefs.end();
                return;
            }
            head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
            count--;
            if (!putOutboxUCharChecked("head", head) ||
                !putOutboxUCharChecked("count", count)) {
                resetOutboxStorageUnsafe("drain_replay_stale_drop");
                s_outcome_outbox_prefs.end();
                return;
            }
            s_outcome_outbox_prefs.end();
            return;
        }

        has_candidate = true;
        s_outcome_outbox_prefs.end();
    }

    if (!has_candidate) {
        return;
    }

    const unsigned long replay_publish_started_ms = millis();
    const bool publish_ok = mqttClient.safePublish(topic, replay_payload, 0, 0);
    const unsigned long replay_publish_duration_ms = millis() - replay_publish_started_ms;
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] replay publish result ok=") +
                   String(publish_ok ? 1 : 0) +
                   " duration_ms=" + String(replay_publish_duration_ms) +
                   " attempt=" + String(candidate.attempt) +
                   " mqtt_connected_after=" + String(mqttClient.isConnected() ? 1 : 0));
    // #endregion

    const unsigned long commit_started_ms = millis();
    uint8_t commit_write_ops = 0;
    const char* commit_action = "noop";
    OutboxLockGuard guard("replay_commit");
    if (!guard.locked()) {
        commit_action = "lock_timeout";
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] replay commit cost action=") +
                       String(commit_action) +
                       " write_ops=" + String(commit_write_ops) +
                       " duration_ms=" + String(millis() - commit_started_ms));
        // #endregion
        LOG_W(IC_TAG, "Outbox lock timeout during replay");
        return;
    }
    loadOutboxStatsLocked();
    if (!beginOutcomeOutboxPrefs(false)) {
        commit_action = "prefs_begin_fail";
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] replay commit cost action=") +
                       String(commit_action) +
                       " write_ops=" + String(commit_write_ops) +
                       " duration_ms=" + String(millis() - commit_started_ms));
        // #endregion
        return;
    }

    uint8_t head = s_outcome_outbox_prefs.getUChar("head", 0);
    uint8_t count = s_outcome_outbox_prefs.getUChar("count", 0);
    bool changed = false;
    bool head_count_changed = false;
    bool retry_total_changed = false;
    bool recovered_total_changed = false;
    bool drop_total_changed = false;
    bool final_confirmed_total_changed = false;
    unsigned long phase_clear_ms = 0;
    unsigned long phase_head_count_ms = 0;
    unsigned long phase_retry_total_ms = 0;
    unsigned long phase_recovered_total_ms = 0;
    unsigned long phase_drop_total_ms = 0;
    unsigned long phase_final_confirmed_total_ms = 0;
    if (count == 0) {
        commit_action = "count_zero";
        s_outcome_outbox_prefs.end();
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] replay commit cost action=") +
                       String(commit_action) +
                       " write_ops=" + String(commit_write_ops) +
                       " duration_ms=" + String(millis() - commit_started_ms));
        // #endregion
        return;
    }

    PendingOutcomeEntry current_head{};
    if (!loadOutboxEntryAt(head, &current_head)) {
        commit_action = "head_corrupt_drop";
        if (!clearOutboxEntryAt(head, "replay_commit_corrupt_drop")) {
            resetOutboxStorageUnsafe("replay_commit_corrupt_drop");
            s_outcome_outbox_prefs.end();
            return;
        }
        commit_write_ops++;
        head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
        count--;
        changed = true;
        head_count_changed = true;
    } else if (isSameOutboxEntryIdentity(candidate, current_head)) {
        if (publish_ok) {
            commit_action = "publish_ok_clear";
            recordIntentChainStage(candidate.metadata,
                                   "outcome_publish_ok",
                                   candidate.flow,
                                   candidate.code,
                                   "[INC-EA5484] critical outcome replay delivered");
            const unsigned long clear_started_ms = millis();
            if (!clearOutboxEntryAt(head, "replay_publish_ok_clear")) {
                resetOutboxStorageUnsafe("replay_publish_ok_clear");
                s_outcome_outbox_prefs.end();
                return;
            }
            phase_clear_ms += millis() - clear_started_ms;
            commit_write_ops++;
            head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
            count--;
            s_outcome_recovered_count++;
            s_outcome_final_confirmed_count++;
            changed = true;
            head_count_changed = true;
            recovered_total_changed = true;
            final_confirmed_total_changed = true;
        } else {
            commit_action = "publish_fail_retry";
            s_outcome_retry_count++;
            retry_total_changed = true;
            if (current_head.attempt >= OUTCOME_OUTBOX_RETRY_LIMIT) {
                commit_action = "publish_fail_drop";
                s_outcome_drop_count_critical++;
                drop_total_changed = true;
                const unsigned long clear_started_ms = millis();
                if (!clearOutboxEntryAt(head, "replay_publish_fail_drop")) {
                    resetOutboxStorageUnsafe("replay_publish_fail_drop");
                    s_outcome_outbox_prefs.end();
                    return;
                }
                phase_clear_ms += millis() - clear_started_ms;
                commit_write_ops++;
                head = static_cast<uint8_t>((head + 1) % OUTCOME_OUTBOX_CAPACITY);
                count--;
                changed = true;
                head_count_changed = true;
            } else {
                current_head.attempt++;
                const unsigned long save_started_ms = millis();
                if (!saveOutboxEntryAt(head, current_head, "replay_publish_fail_retry")) {
                    resetOutboxStorageUnsafe("replay_publish_fail_retry");
                    s_outcome_outbox_prefs.end();
                    return;
                }
                phase_clear_ms += millis() - save_started_ms;
                commit_write_ops++;
                changed = true;
                scheduleReplayBackoffMs("publish_fail_retry", 250UL);
            }
        }
    } else {
        commit_action = "identity_mismatch";
        scheduleReplayBackoffMs("identity_mismatch", 300UL);
    }

    if (changed) {
        if (head_count_changed) {
            const unsigned long head_count_started_ms = millis();
            if (!putOutboxUCharChecked("head", head)) {
                resetOutboxStorageUnsafe("replay_commit_head");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            if (!putOutboxUCharChecked("count", count)) {
                resetOutboxStorageUnsafe("replay_commit_count");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            phase_head_count_ms = millis() - head_count_started_ms;
        }
        if (retry_total_changed) {
            const unsigned long retry_started_ms = millis();
            if (!putOutboxUIntChecked(kOutboxStatRetryTotalKey, s_outcome_retry_count)) {
                resetOutboxStorageUnsafe("replay_commit_retry_total");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            phase_retry_total_ms = millis() - retry_started_ms;
        }
        if (recovered_total_changed) {
            const unsigned long recovered_started_ms = millis();
            if (!putOutboxUIntChecked(kOutboxStatRecoveredTotalKey, s_outcome_recovered_count)) {
                resetOutboxStorageUnsafe("replay_commit_recovered_total");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            phase_recovered_total_ms = millis() - recovered_started_ms;
        }
        if (drop_total_changed) {
            const unsigned long drop_started_ms = millis();
            if (!putOutboxUIntChecked(kOutboxStatDropTotalKey, s_outcome_drop_count_critical)) {
                resetOutboxStorageUnsafe("replay_commit_drop_total");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            phase_drop_total_ms = millis() - drop_started_ms;
        }
        if (final_confirmed_total_changed) {
            const unsigned long final_started_ms = millis();
            if (!putOutboxUIntChecked(kOutboxStatFinalConfirmedTotalKey,
                                      s_outcome_final_confirmed_count)) {
                resetOutboxStorageUnsafe("replay_commit_final_total");
                s_outcome_outbox_prefs.end();
                return;
            }
            commit_write_ops++;
            phase_final_confirmed_total_ms = millis() - final_started_ms;
        }
    }
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] replay commit cost action=") +
                   String(commit_action) +
                   " write_ops=" + String(commit_write_ops) +
                   " duration_ms=" + String(millis() - commit_started_ms) +
                   " changed=" + String(changed ? 1 : 0) +
                   " publish_ok=" + String(publish_ok ? 1 : 0));
    // #endregion
    if ((phase_clear_ms + phase_head_count_ms + phase_retry_total_ms + phase_recovered_total_ms +
         phase_drop_total_ms + phase_final_confirmed_total_ms) > 80UL) {
        // #region agent log
        LOG_W(IC_TAG, String("[DBG5126ae] replay commit phase cost action=") +
                       String(commit_action) +
                       " clear_or_save_ms=" + String(phase_clear_ms) +
                       " head_count_ms=" + String(phase_head_count_ms) +
                       " retry_total_ms=" + String(phase_retry_total_ms) +
                       " recovered_total_ms=" + String(phase_recovered_total_ms) +
                       " drop_total_ms=" + String(phase_drop_total_ms) +
                       " final_confirmed_total_ms=" + String(phase_final_confirmed_total_ms));
        // #endregion
    }
    // #region agent log
    LOG_W(IC_TAG, String("[DBG5126ae] replay commit state changed=") +
                   String(changed ? 1 : 0) +
                   " publish_ok=" + String(publish_ok ? 1 : 0) +
                   " count_after=" + String(count));
    // #endregion
    s_outcome_outbox_prefs.end();
}

void initIntentMetadata(IntentMetadata* metadata) {
    if (metadata == nullptr) {
        return;
    }
    memset(metadata->intent_id, 0, sizeof(metadata->intent_id));
    memset(metadata->correlation_id, 0, sizeof(metadata->correlation_id));
    metadata->generation = 0;
    metadata->created_at_ms = millis();
    metadata->ttl_ms = 0;
    metadata->epoch_at_accept = getSafetyEpoch();
}

static IntentMetadata extractIntentMetadataFromPayloadInternal(const char* payload,
                                                               const char* fallback_prefix,
                                                               bool allow_correlation_fallback) {
    IntentMetadata metadata;
    initIntentMetadata(&metadata);

    // Contract: primary fields are top-level (intent_id, correlation_id, generation, …).
    // Optional nested mirror under "data" is supported when the server wraps metadata
    // (data.intent_id, data.correlation_id, …). Top-level wins if both are present.
    // 1024 B filter-parse: keep stack small on mqtt_task (actuator hot path).
    // Config-only wire fallback: tryWireFillIntentCorrelation() when parse misses fields.
    StaticJsonDocument<1024> doc;
    StaticJsonDocument<256> filter;
    filter["intent_id"] = true;
    filter["correlation_id"] = true;
    filter["generation"] = true;
    filter["created_at_ms"] = true;
    filter["ttl_ms"] = true;
    filter["data"]["intent_id"] = true;
    filter["data"]["correlation_id"] = true;
    filter["data"]["generation"] = true;
    filter["data"]["created_at_ms"] = true;
    filter["data"]["ttl_ms"] = true;
    bool parsed = false;
    if (payload != nullptr && strlen(payload) > 0) {
        DeserializationError err = deserializeJson(doc,
                                                   payload,
                                                   DeserializationOption::Filter(filter));
        parsed = !err;
    }

    if (parsed) {
        JsonObject data_obj = doc["data"].as<JsonObject>();
        String intent_id = doc["intent_id"] | "";
        if (intent_id.length() == 0 && !data_obj.isNull()) {
            intent_id = data_obj["intent_id"] | "";
        }
        String corr_id = doc["correlation_id"] | "";
        if (corr_id.length() == 0 && !data_obj.isNull()) {
            corr_id = data_obj["correlation_id"] | "";
        }
        metadata.generation = doc["generation"] | 0;
        if (metadata.generation == 0 && !data_obj.isNull()) {
            metadata.generation = data_obj["generation"] | 0;
        }
        {
            uint32_t default_now = static_cast<uint32_t>(millis());
            if (!doc["created_at_ms"].isNull()) {
                metadata.created_at_ms = doc["created_at_ms"].as<uint32_t>();
            } else if (!data_obj.isNull() && !data_obj["created_at_ms"].isNull()) {
                metadata.created_at_ms = data_obj["created_at_ms"].as<uint32_t>();
            } else {
                metadata.created_at_ms = default_now;
            }
        }
        metadata.ttl_ms = doc["ttl_ms"] | 0;
        if (metadata.ttl_ms == 0 && !data_obj.isNull()) {
            metadata.ttl_ms = data_obj["ttl_ms"] | 0;
        }

        if (intent_id.length() == 0) {
            intent_id = buildFallbackId(fallback_prefix, s_intent_fallback_counter);
        }
        if (allow_correlation_fallback && corr_id.length() == 0) {
            corr_id = buildFallbackId("corr", s_corr_fallback_counter);
        }

        strncpy(metadata.intent_id, intent_id.c_str(), sizeof(metadata.intent_id) - 1);
        metadata.intent_id[sizeof(metadata.intent_id) - 1] = '\0';
        strncpy(metadata.correlation_id, corr_id.c_str(), sizeof(metadata.correlation_id) - 1);
        metadata.correlation_id[sizeof(metadata.correlation_id) - 1] = '\0';
    } else {
        String intent_id = buildFallbackId(fallback_prefix, s_intent_fallback_counter);
        strncpy(metadata.intent_id, intent_id.c_str(), sizeof(metadata.intent_id) - 1);
        metadata.intent_id[sizeof(metadata.intent_id) - 1] = '\0';
        if (allow_correlation_fallback) {
            String corr_id = buildFallbackId("corr", s_corr_fallback_counter);
            strncpy(metadata.correlation_id, corr_id.c_str(), sizeof(metadata.correlation_id) - 1);
            metadata.correlation_id[sizeof(metadata.correlation_id) - 1] = '\0';
        }
    }

    metadata.epoch_at_accept = getSafetyEpoch();
    return metadata;
}

IntentMetadata extractIntentMetadataFromPayload(const char* payload, const char* fallback_prefix) {
    return extractIntentMetadataFromPayloadInternal(payload, fallback_prefix, true);
}

IntentMetadata extractIntentMetadataFromPayloadNoCorrelationFallback(const char* payload,
                                                                     const char* fallback_prefix) {
    return extractIntentMetadataFromPayloadInternal(payload, fallback_prefix, false);
}

static bool copyQuotedJsonField(const char* payload, const char* key, char* dest, size_t dest_len) {
    if (payload == nullptr || key == nullptr || dest == nullptr || dest_len < 2) {
        return false;
    }
    char needle[80];
    const int needle_len = snprintf(needle, sizeof(needle), "\"%s\":\"", key);
    if (needle_len <= 0 || static_cast<size_t>(needle_len) >= sizeof(needle)) {
        return false;
    }
    const char* value_start = strstr(payload, needle);
    if (value_start == nullptr) {
        return false;
    }
    value_start += static_cast<size_t>(needle_len);
    const char* value_end = strchr(value_start, '"');
    if (value_end == nullptr || value_end <= value_start) {
        return false;
    }
    size_t value_len = static_cast<size_t>(value_end - value_start);
    if (value_len >= dest_len) {
        value_len = dest_len - 1;
    }
    memcpy(dest, value_start, value_len);
    dest[value_len] = '\0';
    return value_len > 0;
}

void tryWireFillIntentCorrelation(IntentMetadata* metadata, const char* payload) {
    if (metadata == nullptr || payload == nullptr || strlen(payload) == 0) {
        return;
    }
    if (strlen(metadata->correlation_id) > 0) {
        return;
    }
    char wire_id[CORRELATION_ID_MAX_LEN];
    wire_id[0] = '\0';
    if (!copyQuotedJsonField(payload, "correlation_id", wire_id, sizeof(wire_id)) &&
        !copyQuotedJsonField(payload, "request_id", wire_id, sizeof(wire_id)) &&
        !copyQuotedJsonField(payload, "intent_id", wire_id, sizeof(wire_id))) {
        return;
    }
    strncpy(metadata->correlation_id, wire_id, sizeof(metadata->correlation_id) - 1);
    metadata->correlation_id[sizeof(metadata->correlation_id) - 1] = '\0';
    if (strlen(metadata->intent_id) == 0) {
        strncpy(metadata->intent_id, wire_id, sizeof(metadata->intent_id) - 1);
        metadata->intent_id[sizeof(metadata->intent_id) - 1] = '\0';
    }
}

IntentInvalidationReason getIntentInvalidationReason(const IntentMetadata& metadata, uint32_t current_epoch) {
    if (metadata.epoch_at_accept != current_epoch) {
        return IntentInvalidationReason::SAFETY_EPOCH_INVALIDATED;
    }
    if (metadata.ttl_ms == 0) {
        return IntentInvalidationReason::NONE;
    }
    uint32_t now = millis();
    if (now > metadata.created_at_ms && (now - metadata.created_at_ms) > metadata.ttl_ms) {
        return IntentInvalidationReason::TTL_EXPIRED;
    }
    return IntentInvalidationReason::NONE;
}

bool isIntentExpired(const IntentMetadata& metadata, uint32_t current_epoch) {
    return getIntentInvalidationReason(metadata, current_epoch) != IntentInvalidationReason::NONE;
}

bool isRecoveryIntentAllowed(const char* topic, const char* payload) {
    if (topic == nullptr || payload == nullptr) {
        return false;
    }
    String t(topic);
    if (t.indexOf("/actuator/emergency") == -1) {
        return false;
    }
    StaticJsonDocument<192> doc;
    if (deserializeJson(doc, payload)) {
        return false;
    }
    String cmd = doc["command"] | "";
    return cmd == "clear_emergency";
}

uint32_t getIntentChainStageEnqueueFailCount() {
    return s_chain_stage_enqueue_fail_count.load();
}

void recordIntentChainStage(const IntentMetadata& metadata,
                            const char* stage,
                            const char* flow,
                            const char* code,
                            const char* detail) {
    if (stage == nullptr || strlen(stage) == 0 || strlen(metadata.intent_id) == 0) {
        return;
    }

    DynamicJsonDocument event_doc(512);
    event_doc["seq"] = mqttClient.getNextSeq();
    event_doc["event_type"] = "intent_chain_stage";
    event_doc["schema"] = "intent_chain_stage_v1";
    event_doc["flow"] = flow != nullptr ? flow : "command";
    event_doc["stage"] = stage;
    event_doc["intent_id"] = metadata.intent_id;
    event_doc["correlation_id"] = metadata.correlation_id;
    event_doc["generation"] = metadata.generation;
    event_doc["epoch"] = metadata.epoch_at_accept;
    if (code != nullptr && strlen(code) > 0) {
        event_doc["code"] = code;
    }
    if (detail != nullptr && strlen(detail) > 0) {
        event_doc["detail"] = detail;
    }
    event_doc["ts"] = static_cast<unsigned long>(timeManager.getUnixTimestamp());

    String payload;
    if (serializeJson(event_doc, payload) > 0) {
#ifndef MQTT_USE_PUBSUBCLIENT
        // AUT-331: QoS 0 — lifecycle chain-stage events are observability telemetry only.
        // QoS 1 put these into the ESP-IDF MQTT OUTBOX (4+ per command cycle), causing
        // OUTBOX exhaustion under rapid ON+OFF (<2s) and cascading TCP write timeouts.
        // Delivery guarantee for critical failures lives in NVS-backed intent_outcome replay,
        // not in the lifecycle trace topic (QoS 0).
        const char* lifecycle_topic = TopicBuilder::buildIntentOutcomeLifecycleTopic();
        // AUT-344: default chain-stage telemetry is non-critical (AUT-55 shed under burst).
        // AUT-347: terminal outcome trace stages must survive queue pressure — same slot budget
        // as one critical publish (evict one non-critical) so observability matches delivered outcomes.
        const bool terminal_trace_stage =
            strcmp(stage, "outcome_publish_ok") == 0 || strcmp(stage, "outcome_publish_failed") == 0;
        const PublishQueueEnqueueResult pq = tryQueuePublish(lifecycle_topic,
                                                             payload.c_str(),
                                                             0,
                                                             false,
                                                             terminal_trace_stage,
                                                             &metadata);
        if (pq != PublishQueueEnqueueResult::Enqueued) {
            s_chain_stage_enqueue_fail_count.fetch_add(1);
            static unsigned long s_last_chain_stage_fail_log_ms = 0;
            const unsigned long now_ms = millis();
            if (s_last_chain_stage_fail_log_ms == 0UL ||
                (now_ms - s_last_chain_stage_fail_log_ms) >= 5000UL) {
                s_last_chain_stage_fail_log_ms = now_ms;
                LOG_W(IC_TAG,
                      String("AUT347 chain_stage_enqueue_failed stage=") + String(stage) +
                      " pq=" + String(static_cast<int>(pq)) +
                      " count=" + String(s_chain_stage_enqueue_fail_count.load()));
            }
        }
#else
        mqttClient.publish(TopicBuilder::buildIntentOutcomeLifecycleTopic(), payload, 0);
#endif
    }
}

bool publishIntentOutcome(const char* flow,
                          const IntentMetadata& metadata,
                          const char* outcome,
                          const char* code,
                          const String& reason,
                          bool retryable) {
    loadOutboxStatsIfNeeded();
    const char* normalized_outcome = outcome != nullptr ? outcome : "failed";
    const bool terminal_outcome = isTerminalOutcome(normalized_outcome);

    // Defensive guard: intent_id must never be empty in the published payload.
    // An empty intent_id (e.g. from NVS migration, corruption or missing field) causes
    // permanent server-side rejection ("Missing required field: intent_id").
    // Generate a fallback so the event is at least traceable rather than silently broken.
    IntentMetadata safe_metadata = metadata;
    if (strlen(safe_metadata.intent_id) == 0) {
        String fallback = buildFallbackId(flow != nullptr ? flow : "unknown",
                                         s_intent_fallback_counter);
        strncpy(safe_metadata.intent_id, fallback.c_str(), sizeof(safe_metadata.intent_id) - 1);
        safe_metadata.intent_id[sizeof(safe_metadata.intent_id) - 1] = '\0';
        LOG_W(IC_TAG, String("publishIntentOutcome: empty intent_id — generated fallback [") +
                      String(safe_metadata.intent_id) + "] flow=" +
                      String(flow != nullptr ? flow : "null") +
                      " outcome=" + String(normalized_outcome));
    }
    const IntentMetadata& active_metadata = safe_metadata;
    bool command_flow = flow != nullptr && strcmp(flow, "command") == 0;
    // Keep chain-stage chatter off the hot terminal path. This lowers per-command
    // burst volume during OFF storms while preserving non-terminal tracing.
    if (command_flow && !terminal_outcome) {
        recordIntentChainStage(active_metadata,
                               "outcome_publish_attempted",
                               flow,
                               code,
                               "attempting outcome publish");
    }
    bool critical = isCriticalOutcomeClass(flow, normalized_outcome);
    if (terminal_outcome) {
        bool allow_publish = true;
        bool regression_blocked = false;
        char previous_final_outcome[16] = {0};
        portENTER_CRITICAL(&s_intent_final_mux);
        int existing_idx = findFinalIntentEntry(active_metadata.intent_id);
        if (existing_idx >= 0) {
            if (strcmp(s_intent_final_store[existing_idx].final_outcome, normalized_outcome) == 0) {
                allow_publish = false;
            } else {
                allow_publish = false;
                regression_blocked = true;
                strncpy(previous_final_outcome,
                        s_intent_final_store[existing_idx].final_outcome,
                        sizeof(previous_final_outcome) - 1);
            }
        } else {
            IntentFinalEntry& slot = s_intent_final_store[s_intent_final_write_index];
            memset(&slot, 0, sizeof(slot));
            strncpy(slot.intent_id, active_metadata.intent_id, sizeof(slot.intent_id) - 1);
            strncpy(slot.final_outcome, normalized_outcome, sizeof(slot.final_outcome) - 1);
            slot.final_ts = millis();
            slot.valid = true;
            s_intent_final_write_index = static_cast<uint8_t>((s_intent_final_write_index + 1) % INTENT_FINAL_STORE_CAPACITY);
        }
        portEXIT_CRITICAL(&s_intent_final_mux);
        if (regression_blocked) {
            LOG_W(IC_TAG, "Intent final outcome regression blocked [" +
                          String(active_metadata.intent_id) + "] old=" +
                          String(previous_final_outcome) +
                          " new=" + String(normalized_outcome));
        }
        if (!allow_publish) {
            return !regression_blocked;
        }
    }

    String payload;
    if (!buildOutcomePayload(flow,
                             active_metadata,
                             normalized_outcome,
                             code,
                             reason,
                             retryable,
                             critical,
                             0,
                             false,
                             &payload)) {
        LOG_E(IC_TAG, "Failed to serialize intent outcome payload");
        return false;
    }

    // Replay pending critical outcomes first when broker is reachable.
    processIntentOutcomeOutbox();

    String topic = TopicBuilder::buildIntentOutcomeTopic();
    // Terminal command outcomes must be durable for end-to-end finality.
    // Keep non-terminal chatter at QoS 0, but elevate command terminal frames.
    const uint8_t outcome_qos = (command_flow && terminal_outcome) ? 1 : 0;
    uint8_t outcome_retries = 3;
#ifndef MQTT_USE_PUBSUBCLIENT
    const PublishQueuePressureStats pq_stats = getPublishQueuePressureStats();
    if (pq_stats.fill_level >= PUBLISH_QUEUE_SHED_WATERMARK) {
        // Under queue pressure, avoid retry storms and hand over to NVS replay path.
        outcome_retries = 0;
    }
#endif
    bool ok = mqttClient.safePublish(topic, payload, outcome_qos, outcome_retries);
    bool persisted_for_replay = false;
    if (ok) {
        if (command_flow && !terminal_outcome) {
            recordIntentChainStage(active_metadata,
                                   "outcome_publish_ok",
                                   flow,
                                   code,
                                   "outcome publish delivered");
        }
        s_outcome_final_confirmed_count++;
        requestPersistOutboxStats();
    }
    if (!ok) {
        if (command_flow && !terminal_outcome) {
            recordIntentChainStage(active_metadata,
                                   "outcome_publish_failed",
                                   flow,
                                   code,
                                   "outcome publish failed");
        }
        LOG_W(IC_TAG, "[INC-EA5484] Intent outcome publish failed [" + String(active_metadata.intent_id) + "]");
        if (critical) {
            PendingOutcomeEntry entry = {};
            strncpy(entry.flow, flow != nullptr ? flow : "unknown", sizeof(entry.flow) - 1);
            entry.metadata = active_metadata;
            strncpy(entry.outcome, normalized_outcome, sizeof(entry.outcome) - 1);
            strncpy(entry.code, code != nullptr ? code : "UNKNOWN_ERROR", sizeof(entry.code) - 1);
            strncpy(entry.reason, reason.c_str(), sizeof(entry.reason) - 1);
            entry.retryable = retryable;
            entry.attempt = 1;

            s_outcome_retry_count++;
            if (!enqueueCriticalOutcome(entry)) {
                s_outcome_drop_count_critical++;
                LOG_E(IC_TAG, "[INC-EA5484] Critical outcome NVS persist failed after eviction attempt [" +
                                  String(active_metadata.intent_id) + "]");
            } else {
                persisted_for_replay = true;
                LOG_W(IC_TAG, "[INC-EA5484] Critical outcome persisted for replay [" + String(active_metadata.intent_id) + "]");
            }
            requestPersistOutboxStats();
        }
    }
    return ok || persisted_for_replay;
}

uint32_t getSafetyEpoch() {
    return s_safety_epoch.load();
}

uint32_t bumpSafetyEpoch(const char* reason) {
    uint32_t next_epoch = s_safety_epoch.fetch_add(1) + 1;
    String msg = "Safety epoch incremented to " + String(next_epoch);
    if (reason != nullptr && strlen(reason) > 0) {
        msg += " reason=" + String(reason);
    }
    LOG_W(IC_TAG, msg);
    return next_epoch;
}

uint32_t getCriticalOutcomeDropCountTelemetry() {
    loadOutboxStatsIfNeeded();
    return s_outcome_drop_count_critical;
}
