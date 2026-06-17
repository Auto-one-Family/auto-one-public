#ifndef UTILS_TOPIC_BUILDER_H
#define UTILS_TOPIC_BUILDER_H

#include <Arduino.h>

// ============================================
// TOPIC BUILDER STATIC CLASS (Phase 1 - Guide-konform)
// ============================================
class TopicBuilder {
public:
  // Configuration
  static void setEspId(const char* esp_id);
  static void setKaiserId(const char* kaiser_id);
  
  // Phase 1: 8 Critical Topic Patterns (Guide-konform)
  static const char* buildSensorDataTopic(uint8_t gpio);        // Pattern 1
  // ORPHANED - No server handler. See Mqtt_Protocoll.md inventory.
  static const char* buildSensorBatchTopic();                   // Pattern 2
  // ✅ Phase 2C: Sensor Command/Response Topics (On-Demand Measurement)
  static const char* buildSensorCommandTopic(uint8_t gpio);     // Phase 2C
  static const char* buildSensorResponseTopic(uint8_t gpio);    // Phase 2C
  static const char* buildActuatorCommandTopic(uint8_t gpio);   // Pattern 3
  static const char* buildActuatorStatusTopic(uint8_t gpio);    // Pattern 4
  static const char* buildActuatorResponseTopic(uint8_t gpio);  // Phase 5
  static const char* buildActuatorAlertTopic(uint8_t gpio);     // Phase 5
  // AUT-117: latch telemetry at disconnect (ESP → Server, QoS 0)
  static const char* buildActuatorLatchedOfflineTopic(uint8_t gpio);
  // ORPHANED - Redundant to actuator/{gpio}/alert. See Mqtt_Protocoll.md inventory.
  static const char* buildActuatorEmergencyTopic();             // Phase 5
  // AUT-118: Parallel application-level transport to intent_outcome (QoS 1)
  static const char* buildEmergencyAckTopic();
  static const char* buildRecoveryConfirmTopic();
  static const char* buildSystemHeartbeatTopic();               // Pattern 5
  static const char* buildSystemHeartbeatMetricsTopic();        // AUT-121: Extended telemetry (separate from core heartbeat)
  static const char* buildSystemHeartbeatAckTopic();            // Phase 2: Heartbeat-ACK (Server → ESP)
  static const char* buildServerStatusTopic();                  // SAFETY-P5: kaiser/{kaiser_id}/server/status
  static const char* buildSystemCommandTopic();                 // Pattern 6
  static const char* buildSystemDiagnosticsTopic();             // Phase 7
  static const char* buildSystemErrorTopic();                   // Phase 0 Bug-Fix
  static const char* buildConfigTopic();                        // Pattern 7
  static const char* buildConfigResponseTopic();
  static const char* buildIntentOutcomeTopic();                 // Unified intent outcome stream
  // CONFIG_PENDING / runtime lifecycle transitions (raw schema v1) — not mixed with kanonischem Outcome-JSON
  static const char* buildIntentOutcomeLifecycleTopic();
  // ORPHANED (GHOST) - Server->ESP but ESP never subscribes. See Mqtt_Protocoll.md inventory.
  static const char* buildBroadcastEmergencyTopic();            // Pattern 8
  
  // Phase 9: Subzone Management Topics
  static const char* buildSubzoneAssignTopic();      // kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign
  static const char* buildSubzoneRemoveTopic();      // kaiser/{kaiser_id}/esp/{esp_id}/subzone/remove
  static const char* buildSubzoneAckTopic();         // kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack
  // ORPHANED - No server handler. See Mqtt_Protocoll.md inventory.
  static const char* buildSubzoneStatusTopic();      // kaiser/{kaiser_id}/esp/{esp_id}/subzone/status
  static const char* buildSubzoneSafeTopic();        // kaiser/{kaiser_id}/esp/{esp_id}/subzone/safe

  // WP3: Zone Management Topics
  static const char* buildZoneAssignTopic();         // kaiser/{kaiser_id}/esp/{esp_id}/zone/assign
  static const char* buildZoneAckTopic();            // kaiser/{kaiser_id}/esp/{esp_id}/zone/ack

  // PKG-01a (INC-2026-04-20-offline-mode-observability-hardening): Publish-Queue backpressure events
  static const char* buildQueuePressureTopic();      // kaiser/{kaiser_id}/esp/{esp_id}/system/queue_pressure

private:
  static char topic_buffer_[256];
  static char esp_id_[32];
  static char kaiser_id_[64];
  // ✅ Buffer-Validation Helper (fix for buffer-overflow protection)
  static const char* validateTopicBuffer(int snprintf_result);
  
  TopicBuilder() = delete;  // Static class only
};

#endif
