#include "config_update_queue.h"
#include <cstring>
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_log.h>
#include "../utils/logger.h"
#include "../services/config/config_response.h"
#include "../services/config/config_manager.h"
#include "../services/communication/mqtt_client.h"
#include "../services/safety/offline_mode_manager.h"
#include "../models/system_types.h"
#include "../models/config_types.h"
#include "command_admission.h"

// ─── Forward declarations — defined in main.cpp ──────────────────────────────
// CP-F2: Handlers receive pre-parsed root JsonObject + correlationId.
// Eliminates 4x DynamicJsonDocument alloc/free cycle per Config-Push.
extern bool handleSensorConfig(JsonObject doc, const String& correlationId);
extern bool handleActuatorConfig(JsonObject doc, const String& correlationId);
extern bool handleOfflineRulesConfig(JsonObject doc, const String& correlationId);
extern bool evaluatePendingExit(const char* trigger_source);
extern SystemConfig g_system_config;

static const char* CFG_Q_TAG = "SYNC";
static bool s_pending_replay_done = false;
static const uint8_t CONFIG_PENDING_CAPACITY = 3;
static Preferences s_config_pending_prefs;
static const char* CONFIG_APPLIED_GENERATION_KEY = "applied_gen";
static const char* CONFIG_APPLIED_GENERATION_SENSOR_KEY = "applied_gen_sensor";
static const char* CONFIG_APPLIED_GENERATION_ACTUATOR_KEY = "applied_gen_act";
static const char* CONFIG_APPLIED_GENERATION_OFFLINE_KEY = "applied_gen_off";
extern QueueHandle_t g_config_update_queue;
extern SemaphoreHandle_t g_config_lane_mutex;

// CP-F2: Module-level static — allocated in BSS at program start.
// No heap fragmentation from repeated malloc/free across Config-Push cycles.
// .clear() before each use resets ArduinoJson internal state without deallocation.
// Thread-safety: processConfigUpdateQueue() runs exclusively on Core 1 Safety-Task;
// no concurrent access to s_configDoc is possible.
static StaticJsonDocument<CONFIG_JSON_DOC_SIZE> s_configDoc;

static bool beginPendingPrefs(bool read_only = false) {
    // Preferences emits noisy NOT_FOUND errors for absent namespaces. For cfg_pending
    // (best-effort replay queue) this is expected on fresh boots and should stay quiet.
    esp_log_level_set("Preferences", ESP_LOG_NONE);
    esp_log_level_set("Preferences.cpp", ESP_LOG_NONE);
    bool ok = s_config_pending_prefs.begin("cfg_pending", read_only);
    esp_log_level_set("Preferences", ESP_LOG_WARN);
    esp_log_level_set("Preferences.cpp", ESP_LOG_WARN);
    return ok;
}

static uint32_t loadAppliedGeneration() {
    if (!beginPendingPrefs(true)) {
        return 0;
    }
    uint32_t gen = s_config_pending_prefs.getUInt(CONFIG_APPLIED_GENERATION_KEY, 0);
    s_config_pending_prefs.end();
    return gen;
}

static void saveAppliedGeneration(uint32_t generation) {
    if (!beginPendingPrefs(false)) {
        LOG_E(CFG_Q_TAG, "[CONFIG] Failed to open cfg_pending for generation persist");
        return;
    }
    s_config_pending_prefs.putUInt(CONFIG_APPLIED_GENERATION_KEY, generation);
    s_config_pending_prefs.end();
}

static uint32_t loadScopeGeneration(const char* key) {
    if (key == nullptr || strlen(key) == 0) {
        return 0;
    }
    if (!beginPendingPrefs(true)) {
        return 0;
    }
    uint32_t gen = s_config_pending_prefs.getUInt(key, 0);
    s_config_pending_prefs.end();
    return gen;
}

static void saveScopeGeneration(const char* key, uint32_t generation) {
    if (key == nullptr || strlen(key) == 0) {
        return;
    }
    if (!beginPendingPrefs(false)) {
        LOG_E(CFG_Q_TAG, "[CONFIG] Failed to open cfg_pending for scope generation persist");
        return;
    }
    s_config_pending_prefs.putUInt(key, generation);
    s_config_pending_prefs.end();
}

static String slotKey(uint8_t idx, const char* suffix) {
    return "s" + String(idx) + "_" + String(suffix);
}

// Arduino Preferences::remove() logs ERROR to serial when the key is absent; cleanup is idempotent.
static void prefsRemoveIfPresent(Preferences& prefs, const char* key) {
    if (key == nullptr || !prefs.isKey(key)) {
        return;
    }
    prefs.remove(key);
}

// NVS Preferences string values are capped (~4000 B). Larger cfg_pending payloads use blob + marker.
static const uint16_t CFG_PENDING_NVS_STRING_SAFE = 3900;

static void clearSlotPayloadKeys(uint8_t idx) {
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "payload").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "plb").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "plm").c_str());
}

static bool storeSlotPayload(uint8_t idx, const char* payload) {
    if (payload == nullptr) {
        return false;
    }
    size_t len = strlen(payload);
    if (len >= CONFIG_PAYLOAD_MAX_LEN) {
        return false;
    }
    clearSlotPayloadKeys(idx);
    String mkey = slotKey(idx, "plm");
    if (len <= CFG_PENDING_NVS_STRING_SAFE) {
        if (!s_config_pending_prefs.putString(slotKey(idx, "payload").c_str(), payload)) {
            return false;
        }
        s_config_pending_prefs.putUChar(mkey.c_str(), 0);
        return true;
    }
    size_t written = s_config_pending_prefs.putBytes(slotKey(idx, "plb").c_str(), payload, len);
    if (written != len) {
        LOG_E(CFG_Q_TAG, String("[CONFIG] cfg_pending putBytes failed len=") + String(len) +
                             " written=" + String(written));
        clearSlotPayloadKeys(idx);
        return false;
    }
    s_config_pending_prefs.putUChar(mkey.c_str(), 1);
    return true;
}

static bool loadSlotPayload(uint8_t idx, char* out, size_t out_cap) {
    if (out == nullptr || out_cap < 2) {
        return false;
    }
    out[0] = '\0';
    uint8_t mode = s_config_pending_prefs.getUChar(slotKey(idx, "plm").c_str(), 0);
    if (mode == 1) {
        String bkey = slotKey(idx, "plb");
        if (!s_config_pending_prefs.isKey(bkey.c_str())) {
            return false;
        }
        size_t max_read = out_cap - 1;
        size_t n = s_config_pending_prefs.getBytes(bkey.c_str(), out, max_read);
        if (n == 0) {
            return false;
        }
        out[n] = '\0';
        return true;
    }
    String pkey = slotKey(idx, "payload");
    if (!s_config_pending_prefs.isKey(pkey.c_str())) {
        return false;
    }
    String payload = s_config_pending_prefs.getString(pkey.c_str(), "");
    if (payload.length() == 0) {
        return false;
    }
    strncpy(out, payload.c_str(), out_cap - 1);
    out[out_cap - 1] = '\0';
    return true;
}

static bool hasSlotPayload(uint8_t idx) {
    if (s_config_pending_prefs.isKey(slotKey(idx, "payload").c_str())) {
        return true;
    }
    return s_config_pending_prefs.getUChar(slotKey(idx, "plm").c_str(), 0) == 1 &&
           s_config_pending_prefs.isKey(slotKey(idx, "plb").c_str());
}

static bool loadPendingAt(uint8_t idx, ConfigUpdateRequest* req_out) {
    if (req_out == nullptr) {
        return false;
    }
    if (!hasSlotPayload(idx)) {
        return false;
    }
    req_out->type = ConfigUpdateRequest::CONFIG_PUSH;
    if (!loadSlotPayload(idx, req_out->json_payload, sizeof(req_out->json_payload))) {
        return false;
    }
    initIntentMetadata(&req_out->metadata);
    String intent = "";
    String corr = "";
    String intent_key = slotKey(idx, "intent");
    String corr_key = slotKey(idx, "corr");
    if (s_config_pending_prefs.isKey(intent_key.c_str())) {
        intent = s_config_pending_prefs.getString(intent_key.c_str(), "");
    }
    if (s_config_pending_prefs.isKey(corr_key.c_str())) {
        corr = s_config_pending_prefs.getString(corr_key.c_str(), "");
    }
    // Guard: NVS-key absent or empty (e.g. after firmware migration or NVS corruption).
    // Fall back to payload extraction so intent_id is never published as "".
    if (intent.length() == 0) {
        IntentMetadata extracted =
            extractIntentMetadataFromPayload(req_out->json_payload, "cfg_replay");
        strncpy(req_out->metadata.intent_id, extracted.intent_id,
                sizeof(req_out->metadata.intent_id) - 1);
        req_out->metadata.intent_id[sizeof(req_out->metadata.intent_id) - 1] = '\0';
    } else {
        strncpy(req_out->metadata.intent_id, intent.c_str(),
                sizeof(req_out->metadata.intent_id) - 1);
        req_out->metadata.intent_id[sizeof(req_out->metadata.intent_id) - 1] = '\0';
    }
    strncpy(req_out->metadata.correlation_id, corr.c_str(), sizeof(req_out->metadata.correlation_id) - 1);
    req_out->metadata.correlation_id[sizeof(req_out->metadata.correlation_id) - 1] = '\0';
    req_out->metadata.generation = s_config_pending_prefs.getUInt(slotKey(idx, "gen").c_str(), 0);
    req_out->metadata.created_at_ms = s_config_pending_prefs.getUInt(slotKey(idx, "created").c_str(), millis());
    req_out->metadata.ttl_ms = s_config_pending_prefs.getUInt(slotKey(idx, "ttl").c_str(), 0);
    req_out->metadata.epoch_at_accept = s_config_pending_prefs.getUInt(slotKey(idx, "epoch").c_str(), 0);
    return true;
}

static void clearPendingAt(uint8_t idx) {
    clearSlotPayloadKeys(idx);
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "intent").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "corr").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "gen").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "created").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "ttl").c_str());
    prefsRemoveIfPresent(s_config_pending_prefs, slotKey(idx, "epoch").c_str());
}

static void persistPendingIntent(const ConfigUpdateRequest& req) {
    if (!beginPendingPrefs(false)) {
        LOG_E(CFG_Q_TAG, "[CONFIG] Failed to open cfg_pending namespace for persist");
        return;
    }
    uint8_t head = s_config_pending_prefs.getUChar("head", 0);
    uint8_t count = s_config_pending_prefs.getUChar("count", 0);
    uint8_t insert = static_cast<uint8_t>((head + count) % CONFIG_PENDING_CAPACITY);

    if (count >= CONFIG_PENDING_CAPACITY) {
        // Bounded ring: overwrite oldest entry when full — terminal outcome for evicted intent (P0).
        static ConfigUpdateRequest evicted;
        if (loadPendingAt(head, &evicted)) {
            publishIntentOutcome("config",
                                 evicted.metadata,
                                 "failed",
                                 "PENDING_RING_EVICTION",
                                 "cfg_pending ring full — oldest intent superseded (retry recommended)",
                                 true);
        }
        clearPendingAt(head);
        head = static_cast<uint8_t>((head + 1) % CONFIG_PENDING_CAPACITY);
        count = CONFIG_PENDING_CAPACITY - 1;
        s_config_pending_prefs.putUChar("head", head);
    }

    if (!storeSlotPayload(insert, req.json_payload)) {
        LOG_E(CFG_Q_TAG, "[CONFIG] cfg_pending storeSlotPayload failed — replay may lose this intent");
    }
    s_config_pending_prefs.putString(slotKey(insert, "intent").c_str(), req.metadata.intent_id);
    s_config_pending_prefs.putString(slotKey(insert, "corr").c_str(), req.metadata.correlation_id);
    s_config_pending_prefs.putUInt(slotKey(insert, "gen").c_str(), req.metadata.generation);
    s_config_pending_prefs.putUInt(slotKey(insert, "created").c_str(), req.metadata.created_at_ms);
    s_config_pending_prefs.putUInt(slotKey(insert, "ttl").c_str(), req.metadata.ttl_ms);
    s_config_pending_prefs.putUInt(slotKey(insert, "epoch").c_str(), req.metadata.epoch_at_accept);

    s_config_pending_prefs.putUChar("count", static_cast<uint8_t>(count + 1));
    s_config_pending_prefs.end();
}

static void removePendingIntentById(const char* intent_id) {
    if (intent_id == nullptr || strlen(intent_id) == 0) {
        return;
    }
    if (!beginPendingPrefs(false)) {
        return;
    }
    uint8_t head = s_config_pending_prefs.getUChar("head", 0);
    uint8_t count = s_config_pending_prefs.getUChar("count", 0);
    bool removed = false;

    for (uint8_t i = 0; i < count; i++) {
        uint8_t idx = static_cast<uint8_t>((head + i) % CONFIG_PENDING_CAPACITY);
        String stored = s_config_pending_prefs.getString(slotKey(idx, "intent").c_str(), "");
        if (stored == intent_id) {
            clearPendingAt(idx);
            removed = true;
            break;
        }
    }

    if (removed) {
        // static: avoids 3*4244=12732 B on Safety-Task stack (Core 1 only, no concurrent access)
        static ConfigUpdateRequest entries[CONFIG_PENDING_CAPACITY];
        uint8_t restored = 0;
        for (uint8_t idx = 0; idx < CONFIG_PENDING_CAPACITY; idx++) {
            if (loadPendingAt(idx, &entries[restored])) {
                clearPendingAt(idx);
                restored++;
            }
        }
        s_config_pending_prefs.putUChar("head", 0);
        s_config_pending_prefs.putUChar("count", 0);
        for (uint8_t i = 0; i < restored; i++) {
            if (!storeSlotPayload(i, entries[i].json_payload)) {
                LOG_E(CFG_Q_TAG, "[CONFIG] cfg_pending compaction storeSlotPayload failed at slot " + String(i));
            }
            s_config_pending_prefs.putString(slotKey(i, "intent").c_str(), entries[i].metadata.intent_id);
            s_config_pending_prefs.putString(slotKey(i, "corr").c_str(), entries[i].metadata.correlation_id);
            s_config_pending_prefs.putUInt(slotKey(i, "gen").c_str(), entries[i].metadata.generation);
            s_config_pending_prefs.putUInt(slotKey(i, "created").c_str(), entries[i].metadata.created_at_ms);
            s_config_pending_prefs.putUInt(slotKey(i, "ttl").c_str(), entries[i].metadata.ttl_ms);
            s_config_pending_prefs.putUInt(slotKey(i, "epoch").c_str(), entries[i].metadata.epoch_at_accept);
        }
        s_config_pending_prefs.putUChar("count", restored);
    }

    s_config_pending_prefs.end();
}

static void replayPendingIntents() {
    if (s_pending_replay_done || g_config_update_queue == NULL) {
        return;
    }
    s_pending_replay_done = true;

    if (!beginPendingPrefs(false)) {
        return;
    }
    uint8_t head = s_config_pending_prefs.getUChar("head", 0);
    uint8_t count = s_config_pending_prefs.getUChar("count", 0);

    for (uint8_t i = 0; i < count; i++) {
        uint8_t idx = static_cast<uint8_t>((head + i) % CONFIG_PENDING_CAPACITY);
        // static: avoids 4244 B on Safety-Task stack (Core 1 only, no concurrent access)
        static ConfigUpdateRequest req;
        if (!loadPendingAt(idx, &req)) {
            continue;
        }
        if (strlen(req.metadata.correlation_id) == 0) {
            LOG_W(CFG_Q_TAG, "[SYNC] Dropping stale cfg_pending entry: no correlation_id (pre-AUT-586 artifact)");
            clearPendingAt(idx);
            continue;
        }
        BaseType_t queued = xQueueSendToFront(g_config_update_queue, &req, 0);
        if (queued == pdTRUE) {
            publishIntentOutcome("config",
                                 req.metadata,
                                 "accepted",
                                 "REPLAY",
                                 "Pending config replayed after reconnect/reboot",
                                 false);
        } else {
            String replay_corr = String(req.metadata.correlation_id);
            if (replay_corr.length() == 0) {
                ConfigResponseBuilder::publishError(
                    ConfigType::SYSTEM,
                    ConfigErrorCode::CONTRACT_MISSING_CORRELATION,
                    "Config replay rejected: required correlation_id missing",
                    JsonVariantConst());
                publishIntentOutcome("config",
                                     req.metadata,
                                     "failed",
                                     "CONTRACT_CORRELATION_MISSING",
                                     "Config replay rejected: required correlation_id missing",
                                     false);
            } else {
                ConfigResponseBuilder::publishError(
                    ConfigType::SYSTEM,
                    ConfigErrorCode::REPLAY_QUEUE_FULL,
                    "Pending config replay rejected: config queue full",
                    JsonVariantConst(),
                    replay_corr);
                publishIntentOutcome("config",
                                     req.metadata,
                                     "failed",
                                     "REPLAY_QUEUE_FULL",
                                     "Pending config replay rejected: config queue full",
                                     true);
            }
        }
    }
    s_config_pending_prefs.end();
}

QueueHandle_t g_config_update_queue = NULL;

void initConfigUpdateQueue() {
    g_config_update_queue = xQueueCreate(CONFIG_UPDATE_QUEUE_SIZE,
                                          sizeof(ConfigUpdateRequest));
    if (g_config_update_queue == NULL) {
        LOG_E(CFG_Q_TAG, "[SYNC] Failed to create config update queue");
    } else {
        LOG_I(CFG_Q_TAG, "[SYNC] Config update queue created (depth="
              + String(CONFIG_UPDATE_QUEUE_SIZE) + ", item="
              + String(sizeof(ConfigUpdateRequest)) + " B)");
    }
}

bool queueConfigUpdate(ConfigUpdateRequest::Type type, const char* json_payload) {
    IntentMetadata metadata = extractIntentMetadataFromPayloadNoCorrelationFallback(json_payload, "cfg");
    tryWireFillIntentCorrelation(&metadata, json_payload);
    return queueConfigUpdateWithMetadata(type, json_payload, &metadata);
}

bool queueConfigUpdateWithMetadata(ConfigUpdateRequest::Type type,
                                   const char* json_payload,
                                   const IntentMetadata* metadata) {
    if (g_config_update_queue == NULL) return false;

    // static: moves sizeof(ConfigUpdateRequest) from mqtt_task stack to BSS.
    // Safe: queueConfigUpdate() is called exclusively from mqtt_task (main.cpp:290).
    // xQueueSend copies req into the queue's internal storage before returning,
    // so overwriting req on the next call cannot corrupt already-queued data.
    static ConfigUpdateRequest req;
    req.type = type;
    strncpy(req.json_payload, json_payload, sizeof(req.json_payload) - 1);
    req.json_payload[sizeof(req.json_payload) - 1] = '\0';
    initIntentMetadata(&req.metadata);
    if (metadata != nullptr) {
        req.metadata = *metadata;
    } else {
        req.metadata = extractIntentMetadataFromPayloadNoCorrelationFallback(json_payload, "cfg");
        tryWireFillIntentCorrelation(&req.metadata, json_payload);
    }
    if (strlen(req.metadata.correlation_id) == 0) {
        ConfigResponseBuilder::publishError(
            ConfigType::SYSTEM,
            ConfigErrorCode::CONTRACT_MISSING_CORRELATION,
            "Config contract violation: required correlation_id missing",
            JsonVariantConst());
        publishIntentOutcome("config",
                             req.metadata,
                             "failed",
                             "CONTRACT_CORRELATION_MISSING",
                             "Config contract violation: required correlation_id missing",
                             false);
        return false;
    }

    CommandAdmissionContext admission_context{
        mqttClient.isRegistrationConfirmed(),
        g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET,
        g_system_config.current_state == STATE_PENDING_APPROVAL,
        g_system_config.current_state == STATE_SAFE_MODE ||
            g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING ||
            g_system_config.current_state == STATE_ERROR,
        false,
        false,
        nullptr
    };
    CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::CONFIG, admission_context);
    if (!admission.accepted) {
        publishIntentOutcome("config",
                             req.metadata,
                             "rejected",
                             admission.code,
                             String("Config intent rejected (reason_code=") + admission.reason_code + ")",
                             false);
        return false;
    }

    BaseType_t result = xQueueSend(g_config_update_queue, &req, pdMS_TO_TICKS(100));
    if (result != pdTRUE) {
        LOG_W(CFG_Q_TAG, "[SYNC] Config update queue full — config push dropped");
        return false;
    }
    persistPendingIntent(req);
    publishIntentOutcome("config",
                         req.metadata,
                         "accepted",
                         admission.code,
                         "Config intent accepted for processing",
                         false);
    LOG_D(CFG_Q_TAG, "[SYNC] Config update enqueued (type=" + String((uint8_t)type) + ")");
    return true;
}

void processConfigUpdateQueue(uint8_t max_items) {
    if (g_config_update_queue == NULL) return;
    replayPendingIntents();

    // static: avoids 4244 B on Safety-Task stack (Core 1 only, no concurrent access).
    // xQueueReceive overwrites req before use; no stale-data risk.
    static ConfigUpdateRequest req;
    uint8_t processed = 0;
    uint32_t current_epoch = getSafetyEpoch();
    while (processed < max_items && xQueueReceive(g_config_update_queue, &req, 0) == pdTRUE) {
        LOG_I(CFG_Q_TAG, "[SYNC] Processing config update on Core " + String(xPortGetCoreID()));

        IntentInvalidationReason invalidation_reason =
            getIntentInvalidationReason(req.metadata, current_epoch);
        if (invalidation_reason != IntentInvalidationReason::NONE) {
            publishIntentOutcome("config",
                                 req.metadata,
                                 "expired",
                                 invalidation_reason == IntentInvalidationReason::SAFETY_EPOCH_INVALIDATED
                                     ? "SAFETY_EPOCH_INVALIDATED"
                                     : "TTL_EXPIRED",
                                 invalidation_reason == IntentInvalidationReason::SAFETY_EPOCH_INVALIDATED
                                     ? "Config intent invalidated by safety epoch update"
                                     : "Config intent TTL expired before apply",
                                 false);
            removePendingIntentById(req.metadata.intent_id);
            processed++;
            continue;
        }

        String correlationId = String(req.metadata.correlation_id);
        if (correlationId.length() == 0) {
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::CONTRACT_MISSING_CORRELATION,
                "Config contract violation: required correlation_id missing",
                JsonVariantConst());
            publishIntentOutcome("config",
                                 req.metadata,
                                 "failed",
                                 "CONTRACT_CORRELATION_MISSING",
                                 "Config contract violation: required correlation_id missing",
                                 false);
            removePendingIntentById(req.metadata.intent_id);
            processed++;
            continue;
        }

        // CP-F4: Guard against empty payload (e.g. queue corruption)
        if (strlen(req.json_payload) == 0) {
            LOG_E(CFG_Q_TAG, "[CONFIG] Empty payload received — skipping");
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::VALIDATION_FAILED,
                "Config payload empty - apply aborted",
                JsonVariantConst(),
                correlationId);
            publishIntentOutcome("config",
                                 req.metadata,
                                 "failed",
                                 "VALIDATION_FAILED",
                                 "Config payload empty",
                                 false);
            removePendingIntentById(req.metadata.intent_id);
            processed++;
            continue;
        }

        // CP-F2: Parse once into module-level static doc — eliminates 4x DynamicJsonDocument
        // alloc/free cycle (was: 2048+256+2048+2048 = 6400 B per Config-Push, causing heap
        // fragmentation and intermittent NoMemory failures on repeated pushes).
        s_configDoc.clear();
        DeserializationError err = deserializeJson(s_configDoc, req.json_payload);
        if (err) {
            LOG_E(CFG_Q_TAG, "[CONFIG] JSON parse failed: " + String(err.c_str()) +
                  " (payload len=" + String(strlen(req.json_payload)) +
                  ", max_alloc=" + String(ESP.getMaxAllocHeap()) + " B)");
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::JSON_PARSE_ERROR,
                String("Config JSON parse failed: ") + String(err.c_str()),
                JsonVariantConst(),
                correlationId);
            publishIntentOutcome("config",
                                 req.metadata,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("Config JSON parse failed: ") + String(err.c_str()),
                                 false);
            removePendingIntentById(req.metadata.intent_id);
            processed++;
            continue;
        }

        JsonObject root = s_configDoc.as<JsonObject>();
        uint32_t incoming_generation = req.metadata.generation;
        if (incoming_generation == 0) {
            incoming_generation = root["generation"] | 0;
        }
        uint32_t applied_generation = loadAppliedGeneration();
        bool has_sensor_scope = root.containsKey("sensors");
        bool has_actuator_scope = root.containsKey("actuators");
        bool has_offline_scope = root.containsKey("offline_rules");
        bool reject_sensor_scope = false;
        bool reject_actuator_scope = false;
        bool reject_offline_scope = false;

        if (incoming_generation > 0) {
            uint32_t sensor_applied_generation = loadScopeGeneration(CONFIG_APPLIED_GENERATION_SENSOR_KEY);
            uint32_t actuator_applied_generation = loadScopeGeneration(CONFIG_APPLIED_GENERATION_ACTUATOR_KEY);
            uint32_t offline_applied_generation = loadScopeGeneration(CONFIG_APPLIED_GENERATION_OFFLINE_KEY);

            reject_sensor_scope = has_sensor_scope && incoming_generation <= sensor_applied_generation;
            reject_actuator_scope = has_actuator_scope && incoming_generation <= actuator_applied_generation;
            reject_offline_scope = has_offline_scope && incoming_generation <= offline_applied_generation;

            bool all_present_scopes_rejected =
                (!has_sensor_scope || reject_sensor_scope) &&
                (!has_actuator_scope || reject_actuator_scope) &&
                (!has_offline_scope || reject_offline_scope);

            if (all_present_scopes_rejected && incoming_generation <= applied_generation) {
                String reason = String("Config generation rejected: incoming=") + String(incoming_generation) +
                                " applied=" + String(applied_generation);
                publishIntentOutcome("config",
                                     req.metadata,
                                     "rejected",
                                     "STALE_SCOPE",
                                     reason,
                                     false);
                ConfigResponseBuilder::publishError(
                    ConfigType::SYSTEM,
                    ConfigErrorCode::STALE_SCOPE,
                    reason,
                    JsonVariantConst(),
                    correlationId);
                removePendingIntentById(req.metadata.intent_id);
                processed++;
                continue;
            }
        }

        bool sensors_ok = false;
        bool actuators_ok = false;
        bool offline_ok = false;
        if (g_config_lane_mutex != nullptr &&
            xSemaphoreTake(g_config_lane_mutex, pdMS_TO_TICKS(500)) != pdTRUE) {
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::WRITE_TIMEOUT,
                "Config lane lock timeout",
                JsonVariantConst(),
                correlationId);
            publishIntentOutcome("config",
                                 req.metadata,
                                 "failed",
                                 "WRITE_TIMEOUT",
                                 "Config lane lock timeout",
                                 true);
            removePendingIntentById(req.metadata.intent_id);
            processed++;
            continue;
        }
        if (reject_sensor_scope) {
            LOG_W(CFG_Q_TAG, String("[CONFIG] Sensor scope rejected by generation guard: incoming=") +
                             String(incoming_generation) + " applied=" +
                             String(loadScopeGeneration(CONFIG_APPLIED_GENERATION_SENSOR_KEY)));
            publishIntentOutcome("config",
                                 req.metadata,
                                 "rejected",
                                 "STALE_SENSOR_SCOPE",
                                 "Sensor scope rejected by generation guard",
                                 false);
            sensors_ok = true;
        } else {
            sensors_ok = handleSensorConfig(root, correlationId);
        }

        if (reject_actuator_scope) {
            LOG_W(CFG_Q_TAG, String("[CONFIG] Actuator scope rejected by generation guard: incoming=") +
                             String(incoming_generation) + " applied=" +
                             String(loadScopeGeneration(CONFIG_APPLIED_GENERATION_ACTUATOR_KEY)));
            publishIntentOutcome("config",
                                 req.metadata,
                                 "rejected",
                                 "STALE_ACTUATOR_SCOPE",
                                 "Actuator scope rejected by generation guard",
                                 false);
            actuators_ok = true;
        } else {
            actuators_ok = handleActuatorConfig(root, correlationId);
        }

        if (reject_offline_scope) {
            LOG_W(CFG_Q_TAG, String("[CONFIG] Offline-rules scope rejected by generation guard: incoming=") +
                             String(incoming_generation) + " applied=" +
                             String(loadScopeGeneration(CONFIG_APPLIED_GENERATION_OFFLINE_KEY)));
            publishIntentOutcome("config",
                                 req.metadata,
                                 "rejected",
                                 "STALE_OFFLINE_SCOPE",
                                 "Offline-rules scope rejected by generation guard",
                                 false);
            offline_ok = true;
        } else {
            offline_ok = handleOfflineRulesConfig(root, correlationId);
        }
        if (g_config_lane_mutex != nullptr) {
            xSemaphoreGive(g_config_lane_mutex);
        }
        bool persisted = sensors_ok && actuators_ok && offline_ok;
        if (!persisted) {
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::COMMIT_FAILED,
                "Config apply/persist failed",
                JsonVariantConst(),
                correlationId);
        }
        publishIntentOutcome("config",
                             req.metadata,
                             persisted ? "persisted" : "failed",
                             persisted ? "NONE" : "COMMIT_FAILED",
                             persisted ? "Config committed and persisted"
                                       : "Config apply/persist failed",
                             !persisted);
        if (persisted && incoming_generation > 0) {
            saveAppliedGeneration(incoming_generation);
            if (has_sensor_scope && !reject_sensor_scope) {
                saveScopeGeneration(CONFIG_APPLIED_GENERATION_SENSOR_KEY, incoming_generation);
            }
            if (has_actuator_scope && !reject_actuator_scope) {
                saveScopeGeneration(CONFIG_APPLIED_GENERATION_ACTUATOR_KEY, incoming_generation);
            }
            if (has_offline_scope && !reject_offline_scope) {
                saveScopeGeneration(CONFIG_APPLIED_GENERATION_OFFLINE_KEY, incoming_generation);
            }
        }
        if (persisted && g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET) {
            if (!evaluatePendingExit("config_commit")) {
                LOG_W(CFG_Q_TAG, "[CONFIG] Runtime config still partial - staying in CONFIG_PENDING_AFTER_RESET");
            }
        }
        removePendingIntentById(req.metadata.intent_id);
        processed++;
    }
}
