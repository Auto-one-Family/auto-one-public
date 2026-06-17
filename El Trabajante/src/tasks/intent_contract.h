#pragma once

#include <Arduino.h>
#include <stdint.h>

static const size_t INTENT_ID_MAX_LEN = 64;
static const size_t CORRELATION_ID_MAX_LEN = 64;

struct IntentMetadata {
    char intent_id[INTENT_ID_MAX_LEN];
    char correlation_id[CORRELATION_ID_MAX_LEN];
    uint32_t generation;
    uint32_t created_at_ms;
    uint32_t ttl_ms;
    uint32_t epoch_at_accept;
};

struct IntentChainCounters {
    uint32_t ingress_seen;
    uint32_t admission_accept;
    uint32_t admission_reject;
    uint32_t queue_enqueued;
    uint32_t execute_started;
    uint32_t execute_finished;
    uint32_t outcome_publish_attempted;
    uint32_t outcome_publish_ok;
    uint32_t outcome_publish_failed;
    uint32_t observer_seen;
};

enum class IntentInvalidationReason : uint8_t {
    NONE = 0,
    SAFETY_EPOCH_INVALIDATED = 1,
    TTL_EXPIRED = 2
};

void initIntentMetadata(IntentMetadata* metadata);
IntentMetadata extractIntentMetadataFromPayload(const char* payload, const char* fallback_prefix);
IntentMetadata extractIntentMetadataFromPayloadNoCorrelationFallback(const char* payload,
                                                                     const char* fallback_prefix);
/** Config-only: strstr wire copy when filter-parse missed correlation (no heap). */
void tryWireFillIntentCorrelation(IntentMetadata* metadata, const char* payload);
bool isIntentExpired(const IntentMetadata& metadata, uint32_t current_epoch);
IntentInvalidationReason getIntentInvalidationReason(const IntentMetadata& metadata, uint32_t current_epoch);
bool isRecoveryIntentAllowed(const char* topic, const char* payload);
void recordIntentChainStage(const IntentMetadata& metadata,
                            const char* stage,
                            const char* flow = "command",
                            const char* code = nullptr,
                            const char* detail = nullptr);

bool publishIntentOutcome(const char* flow,
                          const IntentMetadata& metadata,
                          const char* outcome,
                          const char* code,
                          const String& reason,
                          bool retryable);
void processIntentOutcomeOutbox();
void processDeferredOutboxStatsPersist();

uint32_t getSafetyEpoch();
uint32_t bumpSafetyEpoch(const char* reason);

// NVS-backed counter (loaded lazily) — same semantics as intent_outcome payload field
// outcome_drop_count_critical; exposed for heartbeat telemetry.
uint32_t getCriticalOutcomeDropCountTelemetry();

// AUT-347: lifecycle chain-stage telemetry failed to enter COMM publish-queue (explicit marker).
uint32_t getIntentChainStageEnqueueFailCount();
