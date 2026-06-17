#include "publish_queue.h"
#include "../utils/logger.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"
#include <cstring>
#include <atomic>

static const char* PQ_TAG = "SYNC";

QueueHandle_t g_publish_queue = NULL;

// AUT-55: Backpressure telemetry counters (atomic — written from Core 1, read from Core 0)
static std::atomic<uint32_t> g_pq_shed_count{0};   // Non-critical proactively shed
static std::atomic<uint32_t> g_pq_drop_count{0};   // Dropped because queue completely full
static std::atomic<uint8_t>  g_pq_high_watermark{0};
static std::atomic<bool>     g_pq_paused_for_announce_ack{false};
static std::atomic<uint32_t> g_pq_resume_guard_deadline_ms{0};
static std::atomic<uint32_t> g_pq_observability_shed_count{0};

static bool isRealtimeResponseTopic(const char* topic) {
    if (topic == nullptr) {
        return false;
    }
    return (strstr(topic, "/actuator/") != nullptr && strstr(topic, "/response") != nullptr) ||
           (strstr(topic, "/sensor/") != nullptr && strstr(topic, "/response") != nullptr) ||
           strstr(topic, "/config_response") != nullptr ||
           strstr(topic, "/zone/ack") != nullptr ||
           strstr(topic, "/subzone/ack") != nullptr ||
           strstr(topic, "/system/command/response") != nullptr;
}

static bool isReplayableCriticalTopic(const char* topic) {
    return topic != nullptr && strstr(topic, "/system/intent_outcome") != nullptr;
}

static bool isObservabilityOnlyTopic(const char* topic) {
    if (topic == nullptr) {
        return false;
    }
    return strstr(topic, "/system/queue_pressure") != nullptr ||
           strstr(topic, "/system/diagnostics") != nullptr;
}

// AUT-481 P2: sensor/data is high-frequency but operator-visible; shed only when queue is full.
static bool isSensorDataPublishTopic(const char* topic) {
    if (topic == nullptr) {
        return false;
    }
    return strstr(topic, "/sensor/") != nullptr && strstr(topic, "/data") != nullptr;
}

// Reserve one queue slot for critical publishes by evicting one queued
// non-critical message. Keeps terminal acknowledgements deliverable under load.
static bool reserveSlotForCriticalPublish(PublishRequest* critical_req) {
    if (critical_req == nullptr || g_publish_queue == NULL) {
        return false;
    }

    const UBaseType_t queued = uxQueueMessagesWaiting(g_publish_queue);
    if (queued == 0) {
        return false;
    }

    bool evicted_non_critical = false;
    const bool incoming_realtime = isRealtimeResponseTopic(critical_req->topic);
    PublishRequest item;

    for (UBaseType_t i = 0; i < queued; ++i) {
        if (xQueueReceive(g_publish_queue, &item, 0) != pdTRUE) {
            break;
        }

        const bool queued_realtime = isRealtimeResponseTopic(item.topic);
        const bool preempt_replayable_critical =
            incoming_realtime && !queued_realtime && isReplayableCriticalTopic(item.topic);
        const bool preempt_same_realtime_topic =
            incoming_realtime && queued_realtime &&
            strncmp(item.topic, critical_req->topic, sizeof(item.topic)) == 0;
        if (!evicted_non_critical &&
            (!item.critical || preempt_replayable_critical || preempt_same_realtime_topic)) {
            evicted_non_critical = true;
            if (item.critical) {
                g_pq_drop_count.fetch_add(1);
                if (preempt_same_realtime_topic) {
                    LOG_W(PQ_TAG, "[SYNC] Replaced stale realtime publish with newer payload: " +
                                  String(item.topic));
                } else {
                    LOG_W(PQ_TAG, "[SYNC] Preempted replayable critical publish for realtime lane: " +
                                  String(item.topic));
                }
            } else {
                g_pq_shed_count.fetch_add(1);
                LOG_W(PQ_TAG, "[SYNC] Evicted non-critical publish to protect critical lane: " +
                              String(item.topic));
            }
            continue;
        }

        if (xQueueSend(g_publish_queue, &item, 0) != pdTRUE) {
            g_pq_drop_count.fetch_add(1);
            LOG_W(PQ_TAG, "[SYNC] Queue restore dropped publish: " + String(item.topic));
        }
    }

    if (!evicted_non_critical) {
        return false;
    }

    if (xQueueSend(g_publish_queue, critical_req, 0) == pdTRUE) {
        return true;
    }

    return false;
}

// ============================================
// initPublishQueue
// ============================================
void initPublishQueue() {
    g_publish_queue = xQueueCreate(PUBLISH_QUEUE_SIZE, sizeof(PublishRequest));
    if (g_publish_queue == NULL) {
        LOG_E(PQ_TAG, "[SYNC] Failed to create publish queue — system unstable!");
    } else {
        LOG_I(PQ_TAG, "[SYNC] Publish queue created (" + String(PUBLISH_QUEUE_SIZE) + " slots)");
    }
}

// ============================================
// AUT-55: getPublishQueuePressureStats
// ============================================
PublishQueuePressureStats getPublishQueuePressureStats() {
    PublishQueuePressureStats stats = {};
    if (g_publish_queue != NULL) {
        stats.fill_level = static_cast<uint8_t>(uxQueueMessagesWaiting(g_publish_queue));
    }
    stats.high_watermark = g_pq_high_watermark.load();
    stats.shed_count     = g_pq_shed_count.load();
    stats.drop_count     = g_pq_drop_count.load();
    return stats;
}

void pauseForAnnounceAck(uint32_t guard_timeout_ms) {
    const uint32_t now_ms = millis();
    g_pq_resume_guard_deadline_ms.store(now_ms + guard_timeout_ms);
    g_pq_paused_for_announce_ack.store(true);
}

void resumeAfterAnnounceAck(const char* reason) {
    const bool was_paused = g_pq_paused_for_announce_ack.exchange(false);
    // AUT-117-fix: PKG-18 settle deadline stays active after early ACK.
    // isPublishQueuePaused() enforces the deadline independently of this flag.
    // Evidence (run 20260515_143149): ACK at ~1021ms on a 2000ms guard caused
    // immediate drain resume → 2729ms blocking stall on the fresh TCP socket.
    if (was_paused) {
        const uint32_t deadline_ms = g_pq_resume_guard_deadline_ms.load();
        const uint32_t now_ms = millis();
        const int32_t remaining_ms = static_cast<int32_t>(deadline_ms - now_ms);
        LOG_I(PQ_TAG, String("[INC-EA5484] queue ack received (reason=") +
              String(reason != nullptr ? reason : "unknown") +
              ") settle_remaining_ms=" + String(remaining_ms > 0 ? remaining_ms : 0));
    }
}

bool isPublishQueuePaused() {
    const uint32_t deadline_ms = g_pq_resume_guard_deadline_ms.load();
    if (deadline_ms != 0) {
        const uint32_t now_ms = millis();
        if (static_cast<int32_t>(now_ms - deadline_ms) < 0) {
            return true;
        }
        g_pq_resume_guard_deadline_ms.store(0);
        g_pq_paused_for_announce_ack.store(false);
        LOG_I(PQ_TAG, "[INC-EA5484] queue resumed (settle guard expired)");
        return false;
    }
    return g_pq_paused_for_announce_ack.load();
}

// Helper: update high-watermark atomically (lock-free CAS loop)
static void updateHighWatermark(uint8_t current_fill) {
    uint8_t prev = g_pq_high_watermark.load();
    while (current_fill > prev) {
        if (g_pq_high_watermark.compare_exchange_weak(prev, current_fill)) break;
    }
}

const char* publishQueueEnqueueReasonClass(PublishQueueEnqueueResult result) {
    switch (result) {
        case PublishQueueEnqueueResult::ShedBackpressure:
            return "queue_shed";
        case PublishQueueEnqueueResult::Failed:
            return "transport_error";
        case PublishQueueEnqueueResult::Enqueued:
        default:
            return nullptr;
    }
}

// ============================================
// tryQueuePublish
// ============================================
PublishQueueEnqueueResult tryQueuePublish(const char* topic,
                                          const char* payload,
                                          uint8_t qos,
                                          bool retain,
                                          bool critical,
                                          const IntentMetadata* metadata,
                                          unsigned long defer_ms) {
    if (g_publish_queue == NULL) {
        LOG_W(PQ_TAG, "Publish queue not initialised, dropping: " + String(topic != nullptr ? topic : "<null-topic>"));
        return PublishQueueEnqueueResult::Failed;
    }

    // PKG-16 (INC-2026-04-11-ea5484): Null-safety defensive. Under OOM the
    // Arduino String backing an upstream c_str() can collapse to nullptr,
    // and strlen(NULL) is a LoadProhibited crash. Drop explicitly and count
    // into the application error path instead of trusting the caller.
    if (topic == nullptr || payload == nullptr) {
        g_pq_drop_count.fetch_add(1);
        LOG_W(PQ_TAG, "[SYNC] Publish rejected (null topic/payload) — likely upstream OOM");
        errorTracker.logApplicationError(ERROR_TASK_QUEUE_FULL, "Publish null topic/payload (OOM)");
        return PublishQueueEnqueueResult::Failed;
    }

    size_t topic_len = strlen(topic);
    size_t payload_len = strlen(payload);
    if (topic_len >= PUBLISH_TOPIC_MAX_LEN || payload_len >= PUBLISH_PAYLOAD_MAX_LEN) {
        LOG_E(PQ_TAG, "[SYNC] Publish rejected (oversize) topic_len=" + String((uint32_t)topic_len) +
              " payload_len=" + String((uint32_t)payload_len));
        IntentMetadata oversize_meta = extractIntentMetadataFromPayload(payload, "pub");
        if (metadata != nullptr) {
            oversize_meta = *metadata;
        }
        if (critical) {
            publishIntentOutcome("publish",
                                 oversize_meta,
                                 "failed",
                                 "PAYLOAD_TOO_LARGE",
                                 "Critical publish payload exceeds queue envelope",
                                 true);
        }
        return PublishQueueEnqueueResult::Failed;
    }

    // AUT-55: Check queue fill level for backpressure shedding
    uint8_t fill = static_cast<uint8_t>(uxQueueMessagesWaiting(g_publish_queue));
    updateHighWatermark(fill);

    // FP1 tuning (2026-05-15): shed observability earlier at 60% fill so
    // queue pressure telemetry does not compete with command/response traffic.
    const uint8_t observability_shed_watermark =
        static_cast<uint8_t>((PUBLISH_QUEUE_SIZE * 60U) / 100U);
    if (fill >= observability_shed_watermark && isObservabilityOnlyTopic(topic)) {
        g_pq_observability_shed_count.fetch_add(1);
        g_pq_shed_count.fetch_add(1);
        static unsigned long s_last_observability_shed_log_ms = 0UL;
        const unsigned long now_ms = millis();
        if (s_last_observability_shed_log_ms == 0UL ||
            (now_ms - s_last_observability_shed_log_ms) >= 2000UL) {
            s_last_observability_shed_log_ms = now_ms;
            LOG_W(PQ_TAG, String("[PQ] shed observability payload reason=queue_pressure ") +
                          "fill=" + String(fill) +
                          " shed_obs_total=" + String(g_pq_observability_shed_count.load()) +
                          " topic=" + String(topic));
        }
        return PublishQueueEnqueueResult::ShedBackpressure;
    }

    if (!critical && fill >= PUBLISH_QUEUE_SHED_WATERMARK) {
        // Keep live sensor telemetry flowing under actuator bursts until the queue is full.
        if (isSensorDataPublishTopic(topic) && fill < PUBLISH_QUEUE_SIZE) {
            // fall through to enqueue
        } else {
            g_pq_shed_count.fetch_add(1);
            LOG_D(PQ_TAG, "[SYNC] Backpressure shed (fill=" + String(fill) +
                  "/" + String(PUBLISH_QUEUE_SIZE) + "): " + String(topic));
            return PublishQueueEnqueueResult::ShedBackpressure;
        }
    }

    PublishRequest req;
    strncpy(req.topic, topic, sizeof(req.topic) - 1);
    req.topic[sizeof(req.topic) - 1] = '\0';
    strncpy(req.payload, payload, sizeof(req.payload) - 1);
    req.payload[sizeof(req.payload) - 1] = '\0';
    req.qos    = qos;
    req.retain = retain;
    req.critical = critical;
    req.attempt = 0;
    req.pressure_defer_count = 0;
    req.next_retry_ms = (defer_ms > 0) ? (millis() + defer_ms) : 0UL;
    if (metadata != nullptr) {
        req.metadata = *metadata;
    } else {
        req.metadata = extractIntentMetadataFromPayload(payload, "pub");
    }

    TickType_t wait_ticks = critical ? pdMS_TO_TICKS(20) : 0;
    if (xQueueSend(g_publish_queue, &req, wait_ticks) != pdTRUE) {
        if (critical && reserveSlotForCriticalPublish(&req)) {
            return PublishQueueEnqueueResult::Enqueued;
        }

        g_pq_drop_count.fetch_add(1);
        const bool in_safety_context = xPortGetCoreID() == 1;
        if (!in_safety_context) {
            LOG_W(PQ_TAG, "[SYNC] Publish queue full — dropping");
        }
        const bool is_intent_outcome_topic = strstr(req.topic, "/system/intent_outcome") != nullptr;
        const bool is_system_error_topic = strstr(req.topic, "/system/error") != nullptr;
        // Prevent recursive error-on-error publish storms when ERRTRAK itself cannot enqueue.
        if (!is_system_error_topic) {
            errorTracker.logApplicationError(ERROR_TASK_QUEUE_FULL, "Publish queue full");
        } else if (!in_safety_context) {
            LOG_W(PQ_TAG, "[SYNC] queue-full on /system/error — suppressing recursive ErrorTracker MQTT publish");
        }
        if (critical) {
            if (!in_safety_context && !is_intent_outcome_topic && !is_system_error_topic) {
                publishIntentOutcome("publish",
                                     req.metadata,
                                     "failed",
                                     "QUEUE_FULL",
                                     "Critical publish queue full",
                                     true);
            } else if (!in_safety_context) {
                LOG_W(PQ_TAG,
                      "[SYNC] recursive-critical queue-full drop — skipping recursive failure outcome");
            }
        }
        return PublishQueueEnqueueResult::Failed;
    }

    // Update HWM after successful enqueue (fill is now +1)
    updateHighWatermark(fill + 1);
    return PublishQueueEnqueueResult::Enqueued;
}
