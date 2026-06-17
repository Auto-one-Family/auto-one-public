#pragma once

#include "publish_queue_constants.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "intent_contract.h"

// ============================================
// SAFETY-RTOS M3: Core 1 → Core 0 Publish Queue
// ============================================
// Safety-Task (Core 1) enqueues publish requests via queuePublish().
// Communication-Task (Core 0) drains the queue via MQTTClient::processPublishQueue().
// esp_mqtt_client_publish() is thread-safe, but routing all network I/O through
// Core 0 keeps Core 1 unblocked and makes debugging deterministic.
// ============================================

// Memory guard (ESP32 without PSRAM):
// 15 slots consumed ~33 KB heap and repeatedly prevented CommTask creation on real devices.
// Base sizing (AUT-481 P3): 10 slots (DEV/WROOM) / 16 slots (S3 N8R8) via publish_queue_constants.h.
// PUBLISH_QUEUE_SIZE and PUBLISH_QUEUE_SHED_WATERMARK are defined there (board-aware).
// (AUT-344: older docs may still say 15 — single queue `g_publish_queue`, depth is PUBLISH_QUEUE_SIZE.)
#ifdef ESP32_S3_DEVKIT_MODE
// S3 N8R8: larger PSRAM budget allows 2048 B payloads (AUT-495).
static const uint16_t PUBLISH_PAYLOAD_MAX_LEN = 2048;
#else
// Dev/WROOM: 1536 B payload max.
static const uint16_t PUBLISH_PAYLOAD_MAX_LEN = 1536;
#endif
static const uint16_t PUBLISH_TOPIC_MAX_LEN   = 128;
// AUT-134: Heartbeat payload can exceed 1KB during reconnect/config bursts.
// 1536 B (Dev) / 2048 B (S3) provides headroom without materially impacting heap safety.

// AUT-55: When queue fill >= watermark, non-critical messages are proactively shed
// to preserve slots for critical publishes (alerts, responses, intent_outcome).
//
// Why this matters for realtime actuator control:
// if the queue runs too hot, transport writes become bursty and can block long enough
// to delay actuator response/status feedback visible in frontend controls.
//
// Lower watermark = earlier pressure handling:
// - reduces risk of blocking publish bursts
// - favors control-path responsiveness over telemetry completeness under stress

struct PublishRequest {
    char    topic[PUBLISH_TOPIC_MAX_LEN];
    char    payload[PUBLISH_PAYLOAD_MAX_LEN];
    uint8_t qos;
    bool    retain;
    bool    critical;
    uint8_t attempt;
    uint8_t pressure_defer_count;  // Prevent infinite defer loops under sustained pressure.
    unsigned long next_retry_ms;  // For AUT-6: Backoff-aware retry scheduling
    IntentMetadata metadata;
};

// AUT-55: Telemetry snapshot for queue pressure reporting in heartbeat.
struct PublishQueuePressureStats {
    uint8_t  fill_level;     // Current queue occupancy (0..PUBLISH_QUEUE_SIZE)
    uint8_t  high_watermark; // Peak fill level observed since boot
    uint32_t shed_count;     // Non-critical messages proactively shed (backpressure)
    uint32_t drop_count;     // Messages dropped because queue was completely full
};

extern QueueHandle_t g_publish_queue;

// AUT-344: Distinguish proactive shed (backpressure) from hard enqueue failures so
// MQTTClient can avoid counting intentional telemetry drops as transport/CB failures.
enum class PublishQueueEnqueueResult : uint8_t {
    Enqueued = 0,
    ShedBackpressure = 1,
    Failed = 2,
};

// AUT-454: Canonical reason classes for queue enqueue outcomes.
// Returns nullptr for successful enqueue.
const char* publishQueueEnqueueReasonClass(PublishQueueEnqueueResult result);

// Create the publish queue — call in setup() BEFORE createSafetyTask().
void initPublishQueue();

// Enqueue a publish request from any task. Non-blocking: returns false if queue is full.
// AUT-55: When queue fill >= PUBLISH_QUEUE_SHED_WATERMARK and !critical, the message
// is proactively shed (returns false) to protect critical publish headroom.
PublishQueueEnqueueResult tryQueuePublish(const char* topic,
                                          const char* payload,
                                          uint8_t qos,
                                          bool retain = false,
                                          bool critical = false,
                                          const IntentMetadata* metadata = nullptr,
                                          unsigned long defer_ms = 0);

inline bool queuePublish(const char* topic,
                         const char* payload,
                         uint8_t qos,
                         bool retain = false,
                         bool critical = false,
                         const IntentMetadata* metadata = nullptr) {
    return tryQueuePublish(topic, payload, qos, retain, critical, metadata) ==
           PublishQueueEnqueueResult::Enqueued;
}

// AUT-55: Query current queue pressure stats for heartbeat telemetry.
PublishQueuePressureStats getPublishQueuePressureStats();

// AUT-69: pause queue draining until session/announce PUBACK or guard timeout.
void pauseForAnnounceAck(uint32_t guard_timeout_ms = 300);
void resumeAfterAnnounceAck(const char* reason);
bool isPublishQueuePaused();
