#include "topic_builder.h"

// ============================================
// NATIVE TEST COMPATIBILITY (Phase 1)
// ============================================
// Logger depends on Arduino.h which is not available in native tests.
// These guards disable logging in native tests (error paths are not tested in Phase 1).
//
// TO REMOVE: Delete this entire comment block and the guards below when:
//   - Phase 2 HAL-Mocks are implemented, OR
//   - Logger is refactored to be hardware-independent
//
// Search for: "NATIVE_TEST_GUARD" to find all related code
//
#ifndef NATIVE_TEST
    #include "logger.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "TOPIC";
// LOG_E from logger.h (do not redefine — avoids macro redefinition vs. logger)
#else
    // Native test mode: Logging disabled
    #define LOG_E(tag, msg) ((void)0)
#endif
// END NATIVE_TEST_GUARD
// ============================================

// ============================================
// STATIC MEMBER INITIALIZATION
// ============================================
char TopicBuilder::topic_buffer_[256];
char TopicBuilder::esp_id_[32] = "unknown";
char TopicBuilder::kaiser_id_[64] = "god";

// ============================================
// CONFIGURATION
// ============================================
void TopicBuilder::setEspId(const char* esp_id) {
  strncpy(esp_id_, esp_id, sizeof(esp_id_) - 1);
  esp_id_[sizeof(esp_id_) - 1] = '\0';
}

void TopicBuilder::setKaiserId(const char* kaiser_id) {
  strncpy(kaiser_id_, kaiser_id, sizeof(kaiser_id_) - 1);
  kaiser_id_[sizeof(kaiser_id_) - 1] = '\0';
}

// ============================================
// BUFFER VALIDATION HELPER
// ============================================
// Validates snprintf result for encoding errors and truncation
// Returns empty string on error for safe error handling
const char* TopicBuilder::validateTopicBuffer(int snprintf_result) {
  // ✅ Check 1: Encoding error (snprintf returned negative)
  if (snprintf_result < 0) {
    // NATIVE_TEST_GUARD: LOG_ERROR macro is no-op in native tests
    LOG_E(TAG, "TopicBuilder: snprintf encoding error!");
    return "";
  }

  // ✅ Check 2: Buffer overflow (truncation occurred)
  if (snprintf_result >= (int)sizeof(topic_buffer_)) {
    // NATIVE_TEST_GUARD: LOG_ERROR macro is no-op in native tests
    #ifndef NATIVE_TEST
        char truncation_msg[96];
        snprintf(truncation_msg, sizeof(truncation_msg),
                 "Topic truncated! Required: %d bytes, buffer: %d bytes",
                 snprintf_result, (int)sizeof(topic_buffer_));
        LOG_E(TAG, truncation_msg);
    #else
        // Native test: String concatenation not available, skip detailed error
        LOG_E(TAG, "TopicBuilder: Topic truncated!");
    #endif
    return "";
  }

  // ✅ Success: Return buffer pointer
  return topic_buffer_;
}

// ============================================
// PHASE 1: 8 CRITICAL TOPIC PATTERNS
// ============================================

// Pattern 1: kaiser/god/esp/{esp_id}/sensor/{gpio}/data
const char* TopicBuilder::buildSensorDataTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/sensor/%d/data",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// AUT-715 offline spool replay — server: sensor_batch_handler.py
// Pattern 2: kaiser/god/esp/{esp_id}/sensor/batch
const char* TopicBuilder::buildSensorBatchTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/sensor/batch",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// ✅ Phase 2C: Sensor Command Topic (for on-demand measurements)
// Pattern: kaiser/god/esp/{esp_id}/sensor/{gpio}/command
const char* TopicBuilder::buildSensorCommandTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/sensor/%d/command",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// ✅ Phase 2C: Sensor Response Topic (for on-demand measurement responses)
// Pattern: kaiser/god/esp/{esp_id}/sensor/{gpio}/response
const char* TopicBuilder::buildSensorResponseTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/sensor/%d/response",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// Pattern 3: kaiser/god/esp/{esp_id}/actuator/{gpio}/command
const char* TopicBuilder::buildActuatorCommandTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/actuator/%d/command",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// Pattern 4: kaiser/god/esp/{esp_id}/actuator/{gpio}/status
const char* TopicBuilder::buildActuatorStatusTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/actuator/%d/status",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// Phase 5: kaiser/god/esp/{esp_id}/actuator/{gpio}/response
const char* TopicBuilder::buildActuatorResponseTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/%d/response",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// Phase 5: kaiser/god/esp/{esp_id}/actuator/{gpio}/alert
const char* TopicBuilder::buildActuatorAlertTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/%d/alert",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// ORPHANED - Redundant to actuator/{gpio}/alert. See Mqtt_Protocoll.md inventory.
// Phase 5: kaiser/god/esp/{esp_id}/actuator/emergency
const char* TopicBuilder::buildActuatorEmergencyTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/emergency",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// AUT-118: kaiser/{kaiser_id}/esp/{esp_id}/actuator/emergency/ack (ESP → Server)
const char* TopicBuilder::buildEmergencyAckTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/emergency/ack",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// AUT-118: kaiser/{kaiser_id}/esp/{esp_id}/actuator/recovery_confirm (ESP → Server)
const char* TopicBuilder::buildRecoveryConfirmTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/recovery_confirm",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// AUT-117: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/latched_offline (ESP → Server)
const char* TopicBuilder::buildActuatorLatchedOfflineTopic(uint8_t gpio) {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/actuator/%d/latched_offline",
                         kaiser_id_, esp_id_, gpio);
  return validateTopicBuffer(written);
}

// Pattern 5: kaiser/god/esp/{esp_id}/system/heartbeat
const char* TopicBuilder::buildSystemHeartbeatTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/heartbeat",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// AUT-121: kaiser/god/esp/{esp_id}/system/heartbeat_metrics
const char* TopicBuilder::buildSystemHeartbeatMetricsTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/heartbeat_metrics",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Phase 2: kaiser/god/esp/{esp_id}/system/heartbeat/ack
// Server → ESP: Acknowledgment mit Device-Status (approved/pending/rejected)
const char* TopicBuilder::buildSystemHeartbeatAckTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/heartbeat/ack",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// SAFETY-P5: kaiser/god/server/status (Server LWT + online/offline events)
// Server publishes "online"/"offline" here. ESP subscribes to detect server
// crashes faster than the 120s P1 ACK timeout.
const char* TopicBuilder::buildServerStatusTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/server/status",
                         kaiser_id_);
  return validateTopicBuffer(written);
}

// Pattern 6: kaiser/god/esp/{esp_id}/system/command
const char* TopicBuilder::buildSystemCommandTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/system/command",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Phase 7: kaiser/god/esp/{esp_id}/system/diagnostics
const char* TopicBuilder::buildSystemDiagnosticsTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/diagnostics",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Phase 0 Bug-Fix: kaiser/god/esp/{esp_id}/system/error
const char* TopicBuilder::buildSystemErrorTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/error",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Pattern 7: kaiser/god/esp/{esp_id}/config
const char* TopicBuilder::buildConfigTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/%s/esp/%s/config",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Config response: kaiser/god/esp/{esp_id}/config_response
const char* TopicBuilder::buildConfigResponseTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/config_response",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Unified intent outcome stream: kaiser/god/esp/{esp_id}/system/intent_outcome
const char* TopicBuilder::buildIntentOutcomeTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/intent_outcome",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// Lifecycle telemetry (CONFIG_PENDING enter/exit/blocked) — schema: config_pending_lifecycle_v1
const char* TopicBuilder::buildIntentOutcomeLifecycleTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/intent_outcome/lifecycle",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// ORPHANED (GHOST) - Server->ESP but ESP never subscribes. See Mqtt_Protocoll.md inventory.
// Pattern 8: kaiser/broadcast/emergency
const char* TopicBuilder::buildBroadcastEmergencyTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_), 
                         "kaiser/broadcast/emergency");
  return validateTopicBuffer(written);
}

// Phase 9: Subzone Management Topics

const char* TopicBuilder::buildSubzoneAssignTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/subzone/assign",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

const char* TopicBuilder::buildSubzoneRemoveTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/subzone/remove",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

const char* TopicBuilder::buildSubzoneAckTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/subzone/ack",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// ORPHANED - No server handler. See Mqtt_Protocoll.md inventory.
const char* TopicBuilder::buildSubzoneStatusTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/subzone/status",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

const char* TopicBuilder::buildSubzoneSafeTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/subzone/safe",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// WP3: Zone Management Topics

const char* TopicBuilder::buildZoneAssignTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/zone/assign",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

const char* TopicBuilder::buildZoneAckTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/zone/ack",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}

// PKG-01a: kaiser/{kaiser_id}/esp/{esp_id}/system/queue_pressure
// Emitted on hysteresis transitions (ENTER/RECOVERED) of the Core 1 → Core 0
// publish queue. Server handler: see PKG-01b (topics.parse_queue_pressure_topic).
const char* TopicBuilder::buildQueuePressureTopic() {
  int written = snprintf(topic_buffer_, sizeof(topic_buffer_),
                         "kaiser/%s/esp/%s/system/queue_pressure",
                         kaiser_id_, esp_id_);
  return validateTopicBuffer(written);
}
