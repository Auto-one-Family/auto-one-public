#include "sensor_command_queue.h"
#include <cstring>

#include "../utils/logger.h"
#include "../services/communication/mqtt_client.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"
#include "../models/system_types.h"
#include "command_admission.h"

static const char* SENS_Q_TAG = "SYNC";

// Forward declaration — defined in main.cpp
// Runs on Core 1 (Safety-Task context) after being queued from Core 0 (ESP-IDF MQTT task).
extern SensorCommandExecutionResult handleSensorCommand(const String& topic, const String& payload,
                                                        const IntentMetadata& metadata);

QueueHandle_t g_sensor_cmd_queue = NULL;
extern SystemConfig g_system_config;

// Sensor command queue overflow counter (cumulative, never reset)
static uint32_t g_sensor_cmd_queue_overflow_count = 0;

static void logSensorQueueCorrelation(const char* stage,
                                      const SensorCommand& cmd,
                                      const char* reason_code) {
    LOG_I(SENS_Q_TAG, String("[CORR] sensor_queue stage=") +
                      (stage != nullptr ? stage : "unknown") +
                      ", topic=" + String(cmd.topic) +
                      ", intent_id=" + String(cmd.metadata.intent_id) +
                      ", correlation_id=" + String(cmd.metadata.correlation_id) +
                      ", epoch=" + String(cmd.metadata.epoch_at_accept) +
                      ", reason_code=" + (reason_code != nullptr ? reason_code : "NONE"));
}

void initSensorCommandQueue() {
    g_sensor_cmd_queue = xQueueCreate(SENSOR_CMD_QUEUE_SIZE, sizeof(SensorCommand));
    if (g_sensor_cmd_queue == NULL) {
        LOG_E(SENS_Q_TAG, "[SYNC] Failed to create sensor command queue");
    }
}

bool queueSensorCommand(const char* topic, const char* payload, const IntentMetadata* metadata) {
    if (g_sensor_cmd_queue == NULL) return false;
    SensorCommand cmd;
    strncpy(cmd.topic, topic, sizeof(cmd.topic) - 1);
    cmd.topic[sizeof(cmd.topic) - 1] = '\0';
    strncpy(cmd.payload, payload, sizeof(cmd.payload) - 1);
    cmd.payload[sizeof(cmd.payload) - 1] = '\0';
    IntentMetadata fallback_meta = extractIntentMetadataFromPayload(payload, "sensor");
    cmd.metadata = fallback_meta;
    if (metadata != nullptr) {
        cmd.metadata = *metadata;
    }
    bool recovery_intent = isRecoveryIntentAllowed(topic, payload);
    BaseType_t queued = recovery_intent
                        ? xQueueSendToFront(g_sensor_cmd_queue, &cmd, pdMS_TO_TICKS(20))
                        : xQueueSend(g_sensor_cmd_queue, &cmd, 0);
    if (queued != pdTRUE) {
        LOG_W(SENS_Q_TAG, "[SYNC] Sensor command queue full — dropping: " + String(cmd.topic) +
                          ", intent_id=" + String(cmd.metadata.intent_id) +
                          ", correlation_id=" + String(cmd.metadata.correlation_id));
        errorTracker.logApplicationError(ERROR_TASK_QUEUE_FULL, "Sensor command queue full");
        g_sensor_cmd_queue_overflow_count++;
        return false;
    }
    recordIntentChainStage(cmd.metadata,
                           "queue_enqueued",
                           "command",
                           recovery_intent ? "RECOVERY_QUEUE_ENQUEUED" : "QUEUE_ENQUEUED",
                           "sensor command queued for core1 execution");
    logSensorQueueCorrelation("queue_enqueued",
                              cmd,
                              recovery_intent ? "RECOVERY_QUEUE_ENQUEUED" : "QUEUE_ENQUEUED");
    if (recovery_intent) {
        LOG_I(SENS_Q_TAG, "[SYNC] Recovery sensor intent prioritized to queue front");
    }
    return true;
}

void flushSensorCommandQueue() {
    if (g_sensor_cmd_queue == NULL) return;
    SensorCommand dropped;
    uint16_t dropped_count = 0;
    while (xQueueReceive(g_sensor_cmd_queue, &dropped, 0) == pdTRUE) {
        publishIntentOutcome("command",
                             dropped.metadata,
                             "expired",
                             "SAFETY_QUEUE_FLUSHED",
                             "Dropped during emergency queue flush",
                             false);
        dropped_count++;
    }
    if (dropped_count > 0) {
        LOG_W(SENS_Q_TAG, "[SYNC] Flushed sensor command queue after emergency (" +
                          String(dropped_count) + " dropped)");
    }
}

// M2: Processes all queued sensor commands on Core 1 (Safety-Task).
// Called from safetyTaskFunction() — same task that owns sensorManager.
void processSensorCommandQueue(uint8_t max_items) {
    if (g_sensor_cmd_queue == NULL) return;
    SensorCommand cmd;
    uint8_t processed = 0;
    uint32_t epoch = getSafetyEpoch();
    while (processed < max_items && xQueueReceive(g_sensor_cmd_queue, &cmd, 0) == pdTRUE) {
        IntentInvalidationReason invalidation_reason =
            getIntentInvalidationReason(cmd.metadata, epoch);
        if (invalidation_reason != IntentInvalidationReason::NONE &&
            !isRecoveryIntentAllowed(cmd.topic, cmd.payload)) {
            publishIntentOutcome("command",
                                 cmd.metadata,
                                 "expired",
                                 invalidation_reason == IntentInvalidationReason::SAFETY_EPOCH_INVALIDATED
                                     ? "SAFETY_EPOCH_INVALIDATED"
                                     : "TTL_EXPIRED",
                                 invalidation_reason == IntentInvalidationReason::SAFETY_EPOCH_INVALIDATED
                                     ? "Sensor command invalidated by safety epoch update"
                                     : "Sensor command TTL expired before execution",
                                 false);
            processed++;
            continue;
        }
        CommandAdmissionContext admission_context{
            mqttClient.isRegistrationConfirmed(),
            g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET,
            g_system_config.current_state == STATE_PENDING_APPROVAL,
            g_system_config.current_state == STATE_SAFE_MODE ||
                g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING ||
                g_system_config.current_state == STATE_ERROR,
            g_system_config.current_state == STATE_SAFE_MODE,
            isRecoveryIntentAllowed(cmd.topic, cmd.payload),
            nullptr
        };
        CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::SENSOR, admission_context);
        if (!admission.accepted) {
            logSensorQueueCorrelation("admission_reject", cmd, admission.reason_code);
            publishIntentOutcome("command",
                                 cmd.metadata,
                                 "rejected",
                                 admission.code,
                                 String("Sensor command blocked (reason_code=") + admission.reason_code + ")",
                                 false);
            processed++;
            continue;
        }
        logSensorQueueCorrelation("admission_accept", cmd, admission.reason_code);
        recordIntentChainStage(cmd.metadata,
                               "execute_started",
                               "command",
                               "EXECUTE_STARTED",
                               "sensor command execution started");
        SensorCommandExecutionResult result =
            handleSensorCommand(String(cmd.topic), String(cmd.payload), cmd.metadata);
        recordIntentChainStage(cmd.metadata,
                               "execute_finished",
                               "command",
                               result.code.length() > 0 ? result.code.c_str() : "EXECUTE_FINISHED",
                               "sensor command execution finished");
        const char* outcome = result.outcome.length() > 0 ? result.outcome.c_str() : "failed";
        const char* code = result.code.length() > 0 ? result.code.c_str() : "EXECUTE_FAIL";
        logSensorQueueCorrelation("execute_finished", cmd, code);
        publishIntentOutcome("command",
                             cmd.metadata,
                             outcome,
                             code,
                             result.reason.length() > 0
                                 ? result.reason
                                 : (result.ok ? "Sensor command applied" : "Sensor command execution failed"),
                             result.retryable);
        processed++;
    }
}

uint32_t getSensorCommandQueueOverflowCount() {
    return g_sensor_cmd_queue_overflow_count;
}
