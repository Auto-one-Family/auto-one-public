// ============================================
// INCLUDES
// ============================================
#include <Arduino.h>
#include <cstring>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <ArduinoJson.h>
#include <esp_task_wdt.h>
#include <atomic>
#include "tasks/safety_task.h"
#include "tasks/actuator_command_queue.h"
#include "tasks/sensor_command_queue.h"
#include "tasks/publish_queue.h"         // SAFETY-RTOS M3
#include "tasks/communication_task.h"    // SAFETY-RTOS M3
#include "tasks/rtos_globals.h"          // SAFETY-RTOS M4: FreeRTOS mutexes
#include "tasks/config_update_queue.h"   // SAFETY-RTOS M4.6: Core 0→1 config queue
#include "tasks/intent_contract.h"
#include "tasks/command_admission.h"
#include "tasks/emergency_broadcast_contract.h"
#include "drivers/gpio_manager.h"
#include "utils/logger.h"
#include "services/config/storage_manager.h"
#include "services/config/config_manager.h"
#include "services/config/config_response.h"
#include "services/config/runtime_readiness_policy.h"
#include "error_handling/error_tracker.h"
#include "error_handling/health_monitor.h"
#include "models/config_types.h"
#include "models/error_codes.h"
#include "utils/topic_builder.h"
#include "utils/json_helpers.h"
#include "models/system_types.h"
#include "models/watchdog_types.h"
#include "services/communication/wifi_manager.h"
#include "services/communication/mqtt_client.h"

// Phase 3: Hardware Abstraction Layer
#include "drivers/i2c_bus.h"
#include "drivers/onewire_bus.h"
#include "drivers/pwm_controller.h"

// OneWire utilities for ROM-Code conversion (Phase 4: OneWire-Scan)
#include "utils/onewire_utils.h"

// ============================================
// CONDITIONAL HARDWARE CONFIGURATION INCLUDES
// ============================================
// Phase 4: Required for DEFAULT_ONEWIRE_PIN in OneWire-Scan command
#ifdef XIAO_ESP32C3
    #include "config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "config/hardware/esp32_s3_devkit.h"
#else
    #include "config/hardware/esp32_dev.h"
#endif

// Phase 4: Sensor System
#include "services/sensor/sensor_manager.h"
#include "models/sensor_types.h"

// AUT-714: Spool manager (LittleFS-backed offline buffer)
#include <LittleFS.h>
#include "services/spool/spool_manager.h"

// Phase 5: Actuator System
#include "services/actuator/actuator_manager.h"
#include "services/actuator/safety_controller.h"

// SAFETY-P4: Offline Hysteresis
#include "services/safety/offline_mode_manager.h"

// Phase 6: Provisioning System
#include "services/provisioning/provision_manager.h"
#include "services/provisioning/portal_authority.h"

// Phase 8: NTP Time Management
#include "utils/time_manager.h"
#include "utils/watchdog_storage.h"

// AUT-62: Compile-time default for emergency token policy.
// Prod builds override via -DEMERGENCY_TOKEN_REQUIRED=1 in platformio.ini.
#ifndef EMERGENCY_TOKEN_REQUIRED
#define EMERGENCY_TOKEN_REQUIRED 0
#endif

// ESP-IDF TAG convention for structured logging
static const char* TAG = "BOOT";

// ============================================
// CONSTANTS
// ============================================
// ✅ FIX #3+#4: LED pin for hardware safe-mode feedback
static const uint8_t LED_PIN = HardwareConfig::LED_PIN;
static const time_t APPROVAL_TS_PERSIST_INTERVAL_S = 24 * 60 * 60;  // AUT-61: max one approval-ts write/day

// ============================================
// GLOBAL VARIABLES
// ============================================
SystemConfig g_system_config;
WiFiConfig g_wifi_config;
KaiserZone g_kaiser;
MasterZone g_master;

// AUT-714: LittleFS spool gate — set in STEP 5.5 after LittleFS.begin()
bool g_spool_enabled = false;

// ============================================
// WATCHDOG GLOBALS (Industrial-Grade)
// ============================================
WatchdogConfig g_watchdog_config;
WatchdogDiagnostics g_watchdog_diagnostics;
volatile bool g_watchdog_timeout_flag = false;

// Portal bei MQTT-Disconnect: true = Portal wegen Server-Trennung geoeffnet
// Steuert parallelen Reconnect und Portal-Schliessen bei Erfolg.
// Non-static: accessed by Communication-Task (M3).
bool portal_open_due_to_disconnect_ = false;
bool g_boot_force_offline_autonomy = false;

// SAFETY-RTOS M3: gesetzt nach createCommunicationTask(). setup() kann frueher returnen
// (Provisioning / WiFi- oder MQTT-Fehler) — dann laufen keine Comm-/Safety-Tasks; loop()
// muss weiterhin Legacy-Provisioning ausfuehren.
static bool g_safety_rtos_tasks_created = false;

// ============================================
// SAFETY-P1: Server-ACK-Timeout Tracking (Mechanism D)
// ============================================
static const unsigned long SERVER_ACK_TIMEOUT_MS = 120000UL;  // 2 minutes
// SAFETY-P1 Race-Fix (Bug-2): g_last_server_ack_ms is no longer static so that
// mqtt_client.cpp can reset it atomically inside MQTT_EVENT_CONNECTED — before
// on_connect_callback_() is invoked. This closes the ~ms window where the Safety-Task
// (Core 1) could read mqttClient.isConnected()==true with a stale timestamp and
// incorrectly trigger the 120 s ACK-timeout path.
std::atomic<uint32_t> g_last_server_ack_ms{0};
static std::atomic<bool> g_server_timeout_triggered{false};
static std::atomic<uint32_t> g_last_mqtt_connect_ms{0};
// Counts reconnects after the initial MQTT connect in this boot session.
// Used to distinguish cold-boot connect from true reconnect handling.
static std::atomic<uint32_t> g_mqtt_reconnect_count{0};
static std::atomic<uint32_t> g_fw_correlation_fallback_counter{0};
static std::atomic<uint32_t> g_emergency_parse_error_count{0};
static std::atomic<uint32_t> g_emergency_contract_mismatch_count{0};
static std::atomic<uint32_t> g_emergency_malformed_count{0};
static std::atomic<uint32_t> g_emergency_unsupported_count{0};
static std::atomic<uint32_t> g_emergency_critical_unknown_count{0};
static std::atomic<uint32_t> g_emergency_failsafe_trigger_count{0};
static std::atomic<uint32_t> g_emergency_rejected_no_token_count{0};
static std::atomic<uint32_t> g_config_pending_enter_count{0};
static std::atomic<uint32_t> g_config_pending_exit_count{0};
static std::atomic<uint32_t> g_config_pending_exit_blocked_count{0};
static std::atomic<uint32_t> g_ack_timeout_transition_count{0};
static std::atomic<uint32_t> g_ack_restore_transition_count{0};
static std::atomic<uint32_t> g_ack_timeout_guard_skip_count{0};
static std::atomic<uint32_t> g_ack_restore_guard_skip_count{0};
SemaphoreHandle_t g_config_lane_mutex = nullptr;

// PKG-19 (2026-05): Post-reconnect actuator status was synchronous inside
// onMqttConnectCallback (MQTT task) — same fragile window as deferred bootstrap HB.
// Schedule sync for Communication-Task after a short delay (see ANALYSE-MQTT-Transport-…).
static std::atomic<bool> g_defer_post_reconnect_actuator_status{false};
static std::atomic<unsigned long> g_defer_post_reconnect_actuator_deadline_ms{0};
// AUT-733: Spool flush deferred to Comm-Task (LittleFS I/O must not run in MQTT event handler).
static std::atomic<bool> g_defer_spool_flush{false};
static std::atomic<unsigned long> g_defer_spool_flush_deadline_ms{0};
// g_mqtt_connected: defined in mqtt_client.cpp (SAFETY-RTOS M2, #ifndef MQTT_USE_PUBSUBCLIENT)
// Accessed via mqttClient.isConnected() which reads the atomic in the ESP-IDF path.

// ============================================
// FORWARD DECLARATIONS
// ============================================
void subscribeToAllTopics();
void onMqttConnectCallback();
// CP-F2: Handlers receive pre-parsed root JsonObject + correlationId from processConfigUpdateQueue.
bool handleSensorConfig(JsonObject doc, const String& correlationId);
bool parseAndConfigureSensor(const JsonObjectConst& sensor_obj);
// Phase 4: Version with failure output parameter for aggregated error reporting
bool parseAndConfigureSensorWithTracking(const JsonObjectConst& sensor_obj, ConfigFailureItem* failure_out);
bool handleActuatorConfig(JsonObject doc, const String& correlationId);
SensorCommandExecutionResult handleSensorCommand(const String& topic, const String& payload,
                                                 const IntentMetadata& metadata);  // Phase 2C
bool handleOfflineRulesConfig(JsonObject doc, const String& correlationId);  // SAFETY-P4
void checkServerAckTimeout();                                           // SAFETY-RTOS M1
bool evaluatePendingExit(const char* trigger_source);                   // CONFIG_PENDING_AFTER_RESET central exit gate
// M2: MQTT message router — called from ESP-IDF mqtt_event_handler (Core 0) and
//     PubSubClient staticCallback (Core 1). Dispatches to queues or direct handlers.
void routeIncomingMessage(const char* topic, const char* payload);
// PKG-19: Drain deferred post-reconnect actuator status sync (Comm-Task, Core 0).
void processDeferredPostReconnectActuatorStatusSync();

class ConfigLaneGuard {
public:
  ConfigLaneGuard() : locked_(false) {
    if (g_config_lane_mutex != nullptr) {
      // Allow config queue processing (sensor+actuator+offline rules) to finish
      // before we reject zone/subzone operations as "busy".
      locked_ = xSemaphoreTake(g_config_lane_mutex, pdMS_TO_TICKS(1200)) == pdTRUE;
    } else {
      locked_ = true;
    }
  }
  ~ConfigLaneGuard() {
    if (locked_ && g_config_lane_mutex != nullptr) {
      xSemaphoreGive(g_config_lane_mutex);
    }
  }
  bool locked() const { return locked_; }

private:
  bool locked_;
};

// ============================================
// HELPER FUNCTIONS
// ============================================

// Helper: ErrorTracker MQTT Publish Callback (Observability - Phase 1-3)
// Fire-and-forget - no error handling to prevent recursion
void errorTrackerMqttCallback(const char* topic, const char* payload) {
  if (mqttClient.isConnected()) {
    mqttClient.publish(topic, payload, 0);  // QoS 0 = fire-and-forget
  }
}

// Helper: Ensure correlation_id is always present on critical response channels.
static String ensureCorrelationId(const String& correlationId) {
  if (correlationId.length() > 0) {
    return correlationId;
  }
  uint32_t fallback_idx = g_fw_correlation_fallback_counter.fetch_add(1) + 1;
  return "fw_" + g_system_config.esp_id + "_" + String(millis()) + "_" + String(fallback_idx);
}

static int parseActuatorGpioFromCommandTopic(const String& topic) {
  String actuator_command_prefix = String(TopicBuilder::buildActuatorCommandTopic(0));
  actuator_command_prefix.replace("/0/command", "/");
  if (!topic.startsWith(actuator_command_prefix) || !topic.endsWith("/command")) {
    return -1;
  }

  int gpio_start = actuator_command_prefix.length();
  int gpio_end = topic.length() - String("/command").length();
  if (gpio_end <= gpio_start) {
    return -1;
  }

  String gpio_token = topic.substring(gpio_start, gpio_end);
  if (gpio_token.length() == 0) {
    return -1;
  }
  for (size_t i = 0; i < gpio_token.length(); ++i) {
    if (!isDigit(gpio_token.charAt(i))) {
      return -1;
    }
  }

  int gpio = gpio_token.toInt();
  if (gpio < 0 || gpio > 255) {
    return -1;
  }
  return gpio;
}

static void publishActuatorAdmissionRejectedResponse(const String& topic,
                                                     const String& payload,
                                                     const IntentMetadata& metadata,
                                                     const CommandAdmissionDecision& admission) {
  int gpio = parseActuatorGpioFromCommandTopic(topic);
  if (gpio < 0) {
    return;
  }

  DynamicJsonDocument command_doc(256);
  DeserializationError parse_error = deserializeJson(command_doc, payload);
  String command = "UNKNOWN";
  float value = 0.0f;
  uint32_t duration_s = 0;
  String issued_by;
  if (!parse_error) {
    command = command_doc["command"] | "UNKNOWN";
    value = command_doc["value"] | 0.0f;
    duration_s = command_doc["duration"] | 0;
    issued_by = command_doc["issued_by"] | "";
  }

  DynamicJsonDocument response_doc(512);
  response_doc["esp_id"] = g_system_config.esp_id;
  response_doc["seq"] = mqttClient.getNextSeq();
  response_doc["zone_id"] = g_kaiser.zone_id;
  response_doc["ts"] = static_cast<unsigned long>(timeManager.getUnixTimestamp());
  response_doc["gpio"] = gpio;
  response_doc["command"] = command;
  response_doc["value"] = value;
  response_doc["duration"] = duration_s;
  response_doc["success"] = false;
  response_doc["message"] = String("Rejected before execution (reason_code=") + admission.reason_code + ")";
  if (strlen(metadata.correlation_id) > 0) {
    response_doc["correlation_id"] = metadata.correlation_id;
  }
  if (issued_by.length() > 0) {
    response_doc["issued_by"] = issued_by;
  }

  String response_payload;
  if (serializeJson(response_doc, response_payload) == 0) {
    return;
  }
  mqttClient.safePublish(String(TopicBuilder::buildActuatorResponseTopic(static_cast<uint8_t>(gpio))),
                         response_payload,
                         0);
}

static bool hasRevocationDeleteHint(const String& raw_value) {
  if (raw_value.length() == 0) {
    return false;
  }
  String value = raw_value;
  value.toUpperCase();
  return value.indexOf("DELETE") >= 0 ||
         value.indexOf("REVOK") >= 0 ||
         value.indexOf("TOMBSTONE") >= 0 ||
         value.indexOf("UPSTREAM") >= 0;
}

enum class EmergencyParseClass : uint8_t {
    MALFORMED = 0,
    UNSUPPORTED,
    CRITICAL_UNKNOWN
};

static const char* emergencyParseClassToString(EmergencyParseClass cls) {
    switch (cls) {
        case EmergencyParseClass::MALFORMED:
            return "malformed";
        case EmergencyParseClass::UNSUPPORTED:
            return "unsupported";
        case EmergencyParseClass::CRITICAL_UNKNOWN:
            return "critical_unknown";
        default:
            return "unknown";
    }
}

static EmergencyParseClass classifyEmergencyContractMismatch(const char* detail_code) {
    if (detail_code == nullptr) {
        return EmergencyParseClass::CRITICAL_UNKNOWN;
    }
    if (strcmp(detail_code, "UNKNOWN_COMMAND_VALUE") == 0) {
        return EmergencyParseClass::UNSUPPORTED;
    }
    if (strcmp(detail_code, "MISSING_COMMAND_FIELD") == 0 ||
        strcmp(detail_code, "FIELD_TYPE_ACTION") == 0 ||
        strcmp(detail_code, "FIELD_TYPE_REASON") == 0 ||
        strcmp(detail_code, "FIELD_TYPE_ISSUED_BY") == 0 ||
        strcmp(detail_code, "FIELD_TYPE_TIMESTAMP") == 0) {
        return EmergencyParseClass::MALFORMED;
    }
    return EmergencyParseClass::CRITICAL_UNKNOWN;
}

static uint32_t incrementEmergencyParseClassCounter(EmergencyParseClass cls) {
    switch (cls) {
        case EmergencyParseClass::MALFORMED:
            return g_emergency_malformed_count.fetch_add(1) + 1;
        case EmergencyParseClass::UNSUPPORTED:
            return g_emergency_unsupported_count.fetch_add(1) + 1;
        case EmergencyParseClass::CRITICAL_UNKNOWN:
            return g_emergency_critical_unknown_count.fetch_add(1) + 1;
        default:
            return 0;
    }
}

uint32_t getEmergencyRejectedNoTokenCount() {
    return g_emergency_rejected_no_token_count.load();
}

static void triggerBroadcastEmergencyStop(const char* epoch_reason, const String& emergency_reason) {
#ifndef MQTT_USE_PUBSUBCLIENT
  if (g_safety_task_handle != NULL) {
    xTaskNotify(g_safety_task_handle, NOTIFY_EMERGENCY_STOP, eSetBits);
  }
#else
  flushActuatorCommandQueue();
  flushSensorCommandQueue();
  bumpSafetyEpoch(epoch_reason);
  safetyController.emergencyStopAll(emergency_reason);
#endif
}

// Helper: Send Subzone ACK with guaranteed correlation_id for ACK tracking.
// mqtt_reason_code: optional stable string for server (e.g. CONFIG_LANE_BUSY, JSON_PARSE_ERROR).
void sendSubzoneAck(const String& subzone_id,
                    const String& status,
                    const String& error_message,
                    const String& correlationId = "",
                    const char* mqtt_reason_code = nullptr) {
  String ack_topic = TopicBuilder::buildSubzoneAckTopic();
  DynamicJsonDocument ack_doc(512);
  String effectiveCorrelationId = ensureCorrelationId(correlationId);
  ack_doc["esp_id"] = g_system_config.esp_id;
  ack_doc["status"] = status;
  ack_doc["subzone_id"] = subzone_id;
  ack_doc["timestamp"] = (unsigned long)timeManager.getUnixTimestamp();

  if (status == "error" && error_message.length() > 0) {
    if (mqtt_reason_code != nullptr && strlen(mqtt_reason_code) > 0) {
      ack_doc["reason_code"] = mqtt_reason_code;
    } else {
      ack_doc["error_code"] = ERROR_SUBZONE_CONFIG_SAVE_FAILED;
    }
    ack_doc["message"] = error_message;
  } else if (mqtt_reason_code != nullptr && strlen(mqtt_reason_code) > 0) {
    ack_doc["reason_code"] = mqtt_reason_code;
  }

  ack_doc["seq"] = mqttClient.getNextSeq();
  ack_doc["correlation_id"] = effectiveCorrelationId;

  String ack_payload;
  size_t written = serializeJson(ack_doc, ack_payload);
  if (written == 0 || ack_payload.length() == 0) {
    LOG_E(TAG, "JSON serialization failed for Subzone ACK: " + subzone_id);
    // Fallback: Send minimal ACK with required fields
    ack_payload = "{\"esp_id\":\"" + g_system_config.esp_id +
                 "\",\"status\":\"error\",\"subzone_id\":\"" + subzone_id +
                 "\",\"message\":\"serialization_failed\",\"timestamp\":0}";
  }
  mqttClient.publish(ack_topic, ack_payload, 1);
}

static void publishZoneConfigLaneBusyAck(const char* payload_cstr) {
  IntentMetadata meta = extractIntentMetadataFromPayload(payload_cstr, "zone");
  String corr = ensureCorrelationId(String(meta.correlation_id));
  String ack_topic = TopicBuilder::buildZoneAckTopic();
  DynamicJsonDocument err_doc(384);
  err_doc["esp_id"] = g_system_config.esp_id;
  err_doc["status"] = "error";
  err_doc["reason_code"] = "CONFIG_LANE_BUSY";
  err_doc["message"] = "Config persistence lane busy; retry later";
  err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
  err_doc["seq"] = mqttClient.getNextSeq();
  err_doc["correlation_id"] = corr;
  String error_response;
  serializeJson(err_doc, error_response);
  mqttClient.publish(ack_topic, error_response, 1);
  publishIntentOutcome("zone",
                       meta,
                       "failed",
                       "CONFIG_LANE_BUSY",
                       "Zone intent blocked: config lane busy",
                       true);
}

static void publishSubzoneConfigLaneBusyAck(const char* payload_cstr, const char* flow_label) {
  IntentMetadata meta = extractIntentMetadataFromPayload(payload_cstr, "subz");
  String corr = ensureCorrelationId(String(meta.correlation_id));
  sendSubzoneAck("unknown",
                  "error",
                  "Config persistence lane busy; retry later",
                  corr,
                  "CONFIG_LANE_BUSY");
  publishIntentOutcome(flow_label,
                       meta,
                       "failed",
                       "CONFIG_LANE_BUSY",
                       "Subzone intent blocked: config lane busy",
                       true);
}

// AUT-118: QoS 1 transports parallel to intent_outcome (offline-gap mitigation).
static void publishEmergencyTransportAck(const IntentMetadata& meta, const char* command_label) {
  if (!mqttClient.isConnected()) {
    return;
  }
  const char* cmd = (command_label != nullptr && strlen(command_label) > 0) ? command_label : "emergency_stop";
  String corr = String(meta.correlation_id);
  corr.replace("\\", "\\\\");
  corr.replace("\"", "\\\"");
  uint8_t gpio_count = actuatorManager.isInitialized() ? actuatorManager.getActiveActuatorCount() : 0;
  String payload =
      String("{\"ts\":") + String(static_cast<unsigned long>(timeManager.getUnixTimestamp())) +
      ",\"esp_id\":\"" + g_system_config.esp_id + "\",\"correlation_id\":\"" + corr +
      "\",\"command\":\"" + String(cmd) +
      "\",\"gpio_count\":" + String(gpio_count) + ",\"outcome\":\"executed\",\"seq\":" +
      String(mqttClient.getNextSeq()) + "}";
  mqttClient.publish(String(TopicBuilder::buildEmergencyAckTopic()), payload, 1);
}

static void publishRecoveryTransportConfirm(const IntentMetadata& meta) {
  if (!mqttClient.isConnected()) {
    return;
  }
  String corr = String(meta.correlation_id);
  corr.replace("\\", "\\\\");
  corr.replace("\"", "\\\"");
  String payload = String("{\"ts\":") + String(static_cast<unsigned long>(timeManager.getUnixTimestamp())) +
                   ",\"esp_id\":\"" + g_system_config.esp_id + "\",\"correlation_id\":\"" + corr +
                   "\",\"command\":\"clear_emergency\",\"state\":\"cleared\",\"seq\":" +
                   String(mqttClient.getNextSeq()) + "}";
  mqttClient.publish(String(TopicBuilder::buildRecoveryConfirmTopic()), payload, 1);
}

static bool hasValidLocalAutonomyConfig() {
  WiFiConfig wifi_config = configManager.getWiFiConfig();
  if (!wifi_config.configured || wifi_config.ssid.length() == 0) {
    return false;
  }

  SensorConfig sensors[10];
  uint8_t sensor_count = 0;
  configManager.loadSensorConfig(sensors, 10, sensor_count);

  ActuatorConfig actuators[MAX_ACTUATORS];
  uint8_t actuator_count = 0;
  configManager.loadActuatorConfig(actuators, MAX_ACTUATORS, actuator_count);

  uint8_t offline_rule_count = 0;
  if (storageManager.beginNamespace("offline", true)) {
    offline_rule_count = storageManager.getUInt8("ofr_count", 0);
    storageManager.endNamespace();
  }

  bool has_valid = sensor_count > 0 && actuator_count > 0 && offline_rule_count > 0;
  if (!has_valid) {
    LOG_W(TAG, String("[BOOT] Local autonomy guard failed: sensors=") + String(sensor_count) +
               " actuators=" + String(actuator_count) +
               " offline_rules=" + String(offline_rule_count));
  }
  return has_valid;
}

static bool isConfigPendingAfterResetState() {
  return g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET;
}

static bool isRuntimeDegradedState() {
  switch (g_system_config.current_state) {
    case STATE_CONFIG_PENDING_AFTER_RESET:
    case STATE_SAFE_MODE:
    case STATE_SAFE_MODE_PROVISIONING:
    case STATE_ERROR:
    case STATE_LIBRARY_DOWNLOADING:
      return true;
    default:
      return false;
  }
}

static RuntimeReadinessSnapshot collectRuntimeReadinessSnapshot() {
  RuntimeReadinessSnapshot snapshot{};
  // Keep this path callback-safe: heartbeat ACK handling must avoid NVS reads.
  // Runtime readiness is derived from active in-memory managers + offline rule cache.
  snapshot.sensor_count = sensorManager.getActiveSensorCount();
  snapshot.actuator_count = actuatorManager.getActiveActuatorCount();
  snapshot.offline_rule_count = offlineModeManager.getOfflineRuleCount();
  return snapshot;
}

static const char* systemStateToString(SystemState state) {
  switch (state) {
    case STATE_BOOT: return "BOOT";
    case STATE_WIFI_SETUP: return "WIFI_SETUP";
    case STATE_WIFI_CONNECTED: return "WIFI_CONNECTED";
    case STATE_MQTT_CONNECTING: return "MQTT_CONNECTING";
    case STATE_MQTT_CONNECTED: return "MQTT_CONNECTED";
    case STATE_AWAITING_USER_CONFIG: return "AWAITING_USER_CONFIG";
    case STATE_ZONE_CONFIGURED: return "ZONE_CONFIGURED";
    case STATE_SENSORS_CONFIGURED: return "SENSORS_CONFIGURED";
    case STATE_CONFIG_PENDING_AFTER_RESET: return "CONFIG_PENDING_AFTER_RESET";
    case STATE_OPERATIONAL: return "OPERATIONAL";
    case STATE_PENDING_APPROVAL: return "PENDING_APPROVAL";
    case STATE_LIBRARY_DOWNLOADING: return "LIBRARY_DOWNLOADING";
    case STATE_SAFE_MODE: return "SAFE_MODE";
    case STATE_SAFE_MODE_PROVISIONING: return "SAFE_MODE_PROVISIONING";
    case STATE_ERROR: return "ERROR";
    default: return "UNKNOWN";
  }
}

static void publishConfigPendingTransitionEvent(const char* event_type,
                                                const char* reason_code,
                                                const RuntimeReadinessDecision& readiness,
                                                SystemState state_before,
                                                SystemState state_after,
                                                const char* trigger_source) {
  DynamicJsonDocument event_doc(768);
  event_doc["seq"] = mqttClient.getNextSeq();
  event_doc["event_type"] = event_type;
  event_doc["reason_code"] = reason_code;
  event_doc["trigger_source"] = trigger_source != nullptr ? trigger_source : "unknown";
  event_doc["esp_id"] = g_system_config.esp_id;
  event_doc["state_before"] = systemStateToString(state_before);
  event_doc["state_after"] = systemStateToString(state_after);
  event_doc["sensor_count"] = readiness.snapshot.sensor_count;
  event_doc["actuator_count"] = readiness.snapshot.actuator_count;
  event_doc["offline_rule_count"] = readiness.snapshot.offline_rule_count;
  event_doc["runtime_profile"] = runtimeReadinessProfileName(readiness.policy.profile);
  event_doc["readiness_decision"] = readiness.decision_code;
  event_doc["config_pending_enter_count"] = g_config_pending_enter_count.load();
  event_doc["config_pending_exit_count"] = g_config_pending_exit_count.load();
  event_doc["config_pending_exit_blocked_count"] = g_config_pending_exit_blocked_count.load();
  event_doc["ts"] = static_cast<unsigned long>(timeManager.getUnixTimestamp());

  event_doc["boot_sequence_id"] = mqttClient.getBootTelemetrySequenceId();
  event_doc["schema"] = "config_pending_lifecycle_v1";

  String payload;
  if (serializeJson(event_doc, payload) > 0) {
#ifndef MQTT_USE_PUBSUBCLIENT
    // [INC-EA5484] AUT-56: Route lifecycle through publish queue for retry resilience.
    const char* lifecycle_topic = TopicBuilder::buildIntentOutcomeLifecycleTopic();
    // AUT-344: lifecycle is observability-only; must not consume critical publish-queue slots.
    IntentMetadata lifecycle_meta = {};
    initIntentMetadata(&lifecycle_meta);
    if (!queuePublish(lifecycle_topic, payload.c_str(), 0, false, false, &lifecycle_meta)) {
      LOG_W(TAG, "[INC-EA5484] Lifecycle transition enqueue failed: " + String(event_type));
    }
#else
    mqttClient.publish(TopicBuilder::buildIntentOutcomeLifecycleTopic(), payload, 0);
#endif
  }
}

bool evaluatePendingExit(const char* trigger_source) {
  if (!isConfigPendingAfterResetState()) {
    return false;
  }

  RuntimeReadinessSnapshot snapshot = collectRuntimeReadinessSnapshot();
  RuntimeReadinessDecision readiness =
      evaluateRuntimeReadiness(snapshot, defaultRuntimeReadinessPolicy());

  if (!readiness.ready) {
    g_config_pending_exit_blocked_count.fetch_add(1);
    publishConfigPendingTransitionEvent("exit_blocked_config_pending",
                                        "CONFIG_PENDING_EXIT_NOT_READY",
                                        readiness,
                                        STATE_CONFIG_PENDING_AFTER_RESET,
                                        STATE_CONFIG_PENDING_AFTER_RESET,
                                        trigger_source);
    LOG_W(TAG, String("[CONFIG] Pending exit blocked: ") + readiness.decision_code +
               " (sensors=" + String(snapshot.sensor_count) +
               ", actuators=" + String(snapshot.actuator_count) +
               ", offline_rules=" + String(snapshot.offline_rule_count) + ")");
    return false;
  }

  SystemState target_state = configManager.isDeviceApproved()
      ? STATE_OPERATIONAL
      : STATE_PENDING_APPROVAL;

  g_system_config.current_state = target_state;
  g_system_config.safe_mode_reason = "";
  configManager.saveSystemConfig(g_system_config);

  g_config_pending_exit_count.fetch_add(1);
  publishConfigPendingTransitionEvent("exited_config_pending",
                                      "CONFIG_PENDING_EXIT_READY",
                                      readiness,
                                      STATE_CONFIG_PENDING_AFTER_RESET,
                                      target_state,
                                      trigger_source);
  LOG_I(TAG, String("[CONFIG] Exit CONFIG_PENDING_AFTER_RESET -> ") +
             systemStateToString(target_state));
  return true;
}

// ============================================
// SAFETY-P1 Mechanism A: Centralized MQTT subscription (called on every connect + reconnect)
// ============================================
void subscribeToAllTopics() {
  // Queue in priority order to avoid post-connect subscribe bursts on weak TCP windows.
  // Critical control-plane topics come first.
  mqttClient.queueSubscribe(TopicBuilder::buildSystemHeartbeatAckTopic(), 1, true);
  // AUT-331 Fix#4: QoS 1 (was: 2). Server reduced QOS_CONFIG 2→1 (constants.py).
  // QoS 2 subscribe + retained QoS-2 config messages from before Fix#4 would still
  // generate PUBREC+PUBCOMP OUTBOX slots. QoS 1 subscribe caps delivery at QoS 1
  // regardless of retained message QoS, eliminating residual OUTBOX pressure.
  mqttClient.queueSubscribe(TopicBuilder::buildConfigTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildSystemCommandTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildBroadcastEmergencyTopic(), 2, true);  // kept: server publishes broadcast/emergency at QoS 2

  String actuator_wildcard = String(TopicBuilder::buildActuatorCommandTopic(0));
  actuator_wildcard.replace("/0/command", "/+/command");
  // AUT-331: QoS 1 (was: 2). Server also reduced to QoS 1 (constants.py QOS_ACTUATOR_COMMAND).
  // QoS 2 delivery binds two OUTBOX slots per command (PUBREC + PUBCOMP); under rapid
  // ON+OFF (<2s) this exhausts the 4096-byte OUTBOX alongside lifecycle publishes.
  mqttClient.queueSubscribe(actuator_wildcard, 1, true);

  mqttClient.queueSubscribe(TopicBuilder::buildActuatorEmergencyTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildZoneAssignTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildSubzoneAssignTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildSubzoneRemoveTopic(), 1, true);
  mqttClient.queueSubscribe(TopicBuilder::buildSubzoneSafeTopic(), 1, true);

  String sensor_wildcard = String(TopicBuilder::buildSensorCommandTopic(0));
  sensor_wildcard.replace("/0/command", "/+/command");
  mqttClient.queueSubscribe(sensor_wildcard, 1, false);  // AUT-331: QoS 1 (was: 2)

  mqttClient.queueSubscribe(TopicBuilder::buildServerStatusTopic(), 1, false);  // SAFETY-P5: Server LWT (QoS 1)

  LOG_I(TAG, "[SAFETY-P1] Subscription queue prepared (12 topics, staged dispatch)");
}

// ============================================
// PKG-19: Deferred post-reconnect actuator status (Comm-Task)
// ============================================
void processDeferredPostReconnectActuatorStatusSync() {
  if (!g_defer_post_reconnect_actuator_status.load(std::memory_order_acquire)) {
    return;
  }
  if (!mqttClient.isConnected()) {
    g_defer_post_reconnect_actuator_status.store(false, std::memory_order_release);
    return;
  }
  const unsigned long deadline =
      g_defer_post_reconnect_actuator_deadline_ms.load(std::memory_order_acquire);
  if (millis() < deadline) {
    return;
  }
  g_defer_post_reconnect_actuator_status.store(false, std::memory_order_release);
  if (actuatorManager.isInitialized()) {
    LOG_I(TAG, "[PKG-19] Post-reconnect actuator status sync (deferred, Comm-Task)");
    actuatorManager.publishAllActuatorStatus();
  }
}

// ============================================
// AUT-733: Deferred post-reconnect spool flush (Comm-Task, all connects)
// ============================================
void processDeferredSpoolFlush() {
  if (!g_defer_spool_flush.load(std::memory_order_acquire)) {
    return;
  }
  if (!mqttClient.isConnected()) {
    g_defer_spool_flush.store(false, std::memory_order_release);
    return;
  }
  const unsigned long deadline =
      g_defer_spool_flush_deadline_ms.load(std::memory_order_acquire);
  if (millis() < deadline) {
    return;
  }
  g_defer_spool_flush.store(false, std::memory_order_release);
  if (spoolManager.isEnabled() && spoolManager.pendingCount() > 0) {
    LOG_I(TAG, "[AUT-733] Post-reconnect spool flush (deferred, Comm-Task)");
    bool all_flushed = spoolManager.flushPending(mqttClient);
    if (!all_flushed) {
      // AUT-862 P1: re-arm for retry — publish queue was full or not ready
      g_defer_spool_flush_deadline_ms.store(millis() + 2000UL, std::memory_order_release);
      g_defer_spool_flush.store(true, std::memory_order_release);
    }
  }
}

// ============================================
// SAFETY-P1 on_connect callback (Mechanisms A + D + E + F)
// ============================================
void onMqttConnectCallback() {
  static bool is_first_connect = true;
  g_last_mqtt_connect_ms.store(millis());

  // Mechanism A: Re-subscribe on every connect (initial + reconnect)
  subscribeToAllTopics();

  // Mechanism D: Reset server ACK tracking on every connect
  g_last_server_ack_ms.store(millis());
  g_server_timeout_triggered.store(false);

  // Mechanism E: Reconnect-only actions (managers must be initialized)
  if (!is_first_connect) {
    g_mqtt_reconnect_count.fetch_add(1);
    // Mechanism E: State sync after reconnect — PKG-19: defer to Comm-Task to avoid
    // N× QoS1 publish burst inside MQTT_EVENT_CONNECTED (same window as staged subscribes).
    LOG_I(TAG, "[SAFETY-P1] MQTT reconnected — actuator status sync scheduled (PKG-19 defer)");
    if (actuatorManager.isInitialized()) {
      g_defer_post_reconnect_actuator_status.store(false, std::memory_order_release);  // reset before re-arm (PKG-19 stale-atomic)
      const unsigned long deadline = millis() + 250UL;
      g_defer_post_reconnect_actuator_deadline_ms.store(deadline, std::memory_order_release);
      g_defer_post_reconnect_actuator_status.store(true, std::memory_order_release);
    }
  }
  // SAFETY-P4: Always run — no-op when mode is ONLINE on a clean first boot.
  // Required when the first MQTT_EVENT_CONNECTED succeeds after boot-time transport
  // failures already moved P4 to DISCONNECTED/OFFLINE_ACTIVE (INC-EA5484): skipping
  // here left active_handover_epoch_=0 and caused MISSING_ACTIVE_SESSION_EPOCH ACK rejects.
  offlineModeManager.onReconnect();
  is_first_connect = false;

  // AUT-733: Arm spool flush for Comm-Task. Deadline 500 ms: after subscribe burst begins
  // draining and PKG-19 (250 ms) has fired. Fires on every connect (spool may contain
  // entries from a previous session or from the current disconnect window).
  g_defer_spool_flush.store(false, std::memory_order_release);
  g_defer_spool_flush_deadline_ms.store(millis() + 500UL, std::memory_order_release);
  g_defer_spool_flush.store(true, std::memory_order_release);

  // Send one bootstrap heartbeat only after heartbeat/ack topic was successfully subscribed.
  // This avoids write pressure exactly in the fragile post-connect subscribe window.
  mqttClient.requestBootstrapHeartbeatAfterAck();
  LOG_I(TAG, "[SAFETY-P1] Bootstrap heartbeat armed (after ACK subscribe)");
}

// ============================================
// M2: MQTT MESSAGE ROUTER
// ============================================
// Called from two paths:
//   ESP-IDF path (default, !MQTT_USE_PUBSUBCLIENT): mqtt_event_handler() on Core 0 (MQTT task)
//   PubSubClient path (MQTT_USE_PUBSUBCLIENT=1):   setCallback lambda on Core 1 (Arduino loop)
//
// Routing decisions:
//   Safety-critical (GPIO/actuator/emergency): via xTaskNotify or queue → Core 1
//   Config/zone/ack: direct execution (atomic or NVS-only, safe from any core)
//   Sensor commands: queueSensorCommand → Core 1 (sensorManager owner)
//   Actuator commands: queueActuatorCommand → Core 1 (actuatorManager owner)
//
// M3 will migrate remaining direct-call handlers (config, zone, subzone) to queues.
void routeIncomingMessage(const char* t, const char* p) {
    // Wrap raw char* to String — existing handler code uses String comparisons
    const String topic(t);
    const String payload(p);

    LOG_I(TAG, "MQTT message received: " + topic);
    LOG_D(TAG, "Payload: " + payload);

    // ─── Config (sensor / actuator / offline_rules) ─────────────────────────
    // SAFETY-RTOS M4.6: Queue to Core 1 — eliminates race on sensors_[]/actuators_[].
    // processConfigUpdateQueue() on Core 1 calls all three handlers with the same payload.
    String config_topic = String(TopicBuilder::buildConfigTopic());
    if (topic == config_topic) {
        IntentMetadata metadata = extractIntentMetadataFromPayloadNoCorrelationFallback(payload.c_str(), "cfg");
        tryWireFillIntentCorrelation(&metadata, payload.c_str());
        String corr_id = String(metadata.correlation_id);
        if (corr_id.length() == 0) {
            String fallback_corr_id = ensureCorrelationId(corr_id);
            const String reason = "Config contract violation: required correlation_id missing";
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::CONTRACT_MISSING_CORRELATION,
                reason,
                JsonVariantConst(),
                fallback_corr_id);
            publishIntentOutcome("config",
                                 metadata,
                                 "failed",
                                 "CONTRACT_CORRELATION_MISSING",
                                 reason,
                                 false);
            return;
        }
        CommandAdmissionContext admission_context{
            mqttClient.isRegistrationConfirmed(),
            isConfigPendingAfterResetState(),
            g_system_config.current_state == STATE_PENDING_APPROVAL,
            isRuntimeDegradedState(),
            false,
            isRecoveryIntentAllowed(topic.c_str(), payload.c_str()),
            nullptr
        };
        CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::CONFIG, admission_context);
        if (!admission.accepted) {
            publishIntentOutcome("config",
                                 metadata,
                                 "rejected",
                                 admission.code,
                                 String("Config update rejected (reason_code=") + admission.reason_code + ")",
                                 false);
            return;
        }
        // Config updates must remain possible when only the communication task failed.
        // In that case Safety-Task may still be alive and can drain config queue.
        if (!g_safety_rtos_tasks_created && g_safety_task_handle == NULL) {
            publishIntentOutcome("config",
                                 metadata,
                                 "rejected",
                                 "MODE_UNSUPPORTED",
                                 "Config update rejected in legacy fallback mode",
                                 true);
            return;
        }
        // CP-F4: Reject payload that exceeds queue buffer — truncation causes partial config.
        size_t payload_len = payload.length();
        if (payload_len >= CONFIG_PAYLOAD_MAX_LEN) {
            LOG_E(TAG, "[CONFIG] TRUNCATION: payload=" + String(payload_len) +
                       " bytes, max=" + String(CONFIG_PAYLOAD_MAX_LEN) + " — config REJECTED (CP-F4)");

            String msg = String("[CONFIG] Payload too large: ") + payload_len +
                         " bytes, max=" + CONFIG_PAYLOAD_MAX_LEN;
            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::PAYLOAD_TOO_LARGE,
                msg,
                JsonVariantConst(),
                corr_id);
            publishIntentOutcome("config",
                                 metadata,
                                 "rejected",
                                 "VALIDATION_FAIL",
                                 msg,
                                 false);
            return;
        }

        if (!queueConfigUpdateWithMetadata(ConfigUpdateRequest::CONFIG_PUSH, payload.c_str(), &metadata)) {
            LOG_E(TAG, "[CONFIG] Queue full/timeout — config push dropped");
            errorTracker.logApplicationError(ERROR_TASK_QUEUE_FULL, "Config update queue full/timeout");

            ConfigResponseBuilder::publishError(
                ConfigType::SYSTEM,
                ConfigErrorCode::QUEUE_FULL,
                "Config queue full/timeout - please retry",
                JsonVariantConst(),
                corr_id);
            publishIntentOutcome("config",
                                 metadata,
                                 "rejected",
                                 "QUEUE_FULL",
                                 "Config queue full/timeout",
                                 true);
        }
        return;
    }

    // ─── Actuator commands ───────────────────────────────────────────────────
    // Queue to Core 1 (actuatorManager owner) via existing M1 actuator command queue.
    String actuator_command_prefix = String(TopicBuilder::buildActuatorCommandTopic(0));
    actuator_command_prefix.replace("/0/command", "/");
    if (topic.startsWith(actuator_command_prefix) && topic.endsWith("/command")) {
        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "act");
        CommandAdmissionContext admission_context{
            mqttClient.isRegistrationConfirmed(),
            isConfigPendingAfterResetState(),
            g_system_config.current_state == STATE_PENDING_APPROVAL,
            isRuntimeDegradedState(),
            g_system_config.current_state == STATE_SAFE_MODE,
            isRecoveryIntentAllowed(topic.c_str(), payload.c_str()),
            nullptr
        };
        CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::ACTUATOR, admission_context);
        if (!admission.accepted) {
            LOG_W(TAG, String("[ADMISSION] Actuator command rejected: ") + admission.reason_code);
            if (admission.reason_code != nullptr &&
                strcmp(admission.reason_code, "CONFIG_PENDING_AFTER_RESET") == 0) {
              LOG_W(TAG, "[ADMISSION] Device is CONFIG_PENDING: need MQTT config commit that applies at least one "
                         "valid actuator (NVS empty/invalid after reset is common). Sensor-only pushes are not enough.");
            }
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 admission.code,
                                 String("Actuator command rejected (reason_code=") + admission.reason_code + ")",
                                 false);
            // Emit terminal actuator_response on admission reject so frontend does not timeout waiting.
            publishActuatorAdmissionRejectedResponse(topic, payload, metadata, admission);
            return;
        }
        if (!queueActuatorCommand(topic.c_str(), payload.c_str(), &metadata)) {
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "QUEUE_FULL",
                                 "Actuator command queue full",
                                 true);
        }
        return;
    }

    // ─── Sensor commands (on-demand measurement) ────────────────────────────
    // Queue to Core 1 (sensorManager owner) via existing M1 sensor command queue.
    String sensor_command_prefix = String(TopicBuilder::buildSensorCommandTopic(0));
    sensor_command_prefix.replace("/0/command", "/");
    if (topic.startsWith(sensor_command_prefix) && topic.endsWith("/command")) {
        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "sensor");
        recordIntentChainStage(metadata, "ingress_seen", "command", "INGRESS", "sensor command ingress");
        DynamicJsonDocument sensor_doc(384);
        DeserializationError sensor_parse_error = deserializeJson(sensor_doc, payload);
        if (sensor_parse_error) {
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "INVALID_JSON",
                                 "Sensor command payload is not valid JSON",
                                 false);
            return;
        }
        String sensor_command = sensor_doc["command"] | "";
        if (sensor_command != "measure") {
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "UNKNOWN_COMMAND",
                                 String("Unsupported sensor command: ") + sensor_command,
                                 false);
            return;
        }
        CommandAdmissionContext admission_context{
            mqttClient.isRegistrationConfirmed(),
            isConfigPendingAfterResetState(),
            g_system_config.current_state == STATE_PENDING_APPROVAL,
            isRuntimeDegradedState(),
            g_system_config.current_state == STATE_SAFE_MODE,
            isRecoveryIntentAllowed(topic.c_str(), payload.c_str()),
            nullptr
        };
        CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::SENSOR, admission_context);
        if (!admission.accepted) {
            recordIntentChainStage(metadata,
                                   "admission_reject",
                                   "command",
                                   admission.code,
                                   admission.reason_code);
            LOG_W(TAG, String("[ADMISSION] Sensor command rejected: ") + admission.reason_code);
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 admission.code,
                                 String("Sensor command rejected (reason_code=") + admission.reason_code + ")",
                                 false);
            return;
        }
        recordIntentChainStage(metadata,
                               "admission_accept",
                               "command",
                               admission.code,
                               admission.reason_code);
        if (!queueSensorCommand(topic.c_str(), payload.c_str(), &metadata)) {
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "QUEUE_FULL",
                                 "Sensor command queue full",
                                 true);
        }
        return;
    }

    // ─── ESP-specific emergency stop ─────────────────────────────────────────
    String esp_emergency_topic = String(TopicBuilder::buildActuatorEmergencyTopic());
    if (topic == esp_emergency_topic) {
        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "emergency");
        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, payload);

        if (!error) {
            String command = doc["command"].as<String>();
            String auth_token = doc["auth_token"].as<String>();

            // Validate auth_token — fail-open: if no token configured, accept any emergency
            String stored_token = "";
            if (storageManager.beginNamespace("system_config", true)) {
                stored_token = storageManager.getStringObj("emergency_auth", "");
                storageManager.endNamespace();
            }

            if (stored_token.length() > 0 && auth_token != stored_token) {
                LOG_E(TAG, "╔════════════════════════════════════════╗");
                LOG_E(TAG, "║  UNAUTHORIZED EMERGENCY-STOP ATTEMPT  ║");
                LOG_E(TAG, "╚════════════════════════════════════════╝");
                LOG_E(TAG, "[SECURITY] ESP emergency-stop rejected: invalid token");
                errorTracker.trackError(3500, ERROR_SEVERITY_CRITICAL,
                                       "ESP emergency-stop rejected: invalid auth_token");
                mqttClient.publish(esp_emergency_topic + "/error",
                                  "{\"error\":\"unauthorized\",\"message\":\"Invalid auth_token\",\"seq\":" + String(mqttClient.getNextSeq()) + "}");
                publishIntentOutcome("command",
                                     metadata,
                                     "rejected",
                                     "UNAUTHORIZED",
                                     "ESP emergency rejected: invalid auth_token",
                                     false);
                return;
            }

            if (stored_token.length() == 0) {
#if EMERGENCY_TOKEN_REQUIRED
                g_emergency_rejected_no_token_count.fetch_add(1);
                LOG_E(TAG, "[INC-EA5484] emergency rejected no_token (EMERGENCY_TOKEN_REQUIRED=1)");
                errorTracker.trackError(ERROR_EMERGENCY_REJECTED_NO_TOKEN, ERROR_SEVERITY_CRITICAL,
                                       "ESP emergency rejected: no token configured (fail-closed)");
                publishIntentOutcome("command",
                                     metadata,
                                     "rejected",
                                     "NO_TOKEN_CONFIGURED",
                                     "ESP emergency rejected: no token configured (prod fail-closed)",
                                     false);
                return;
#else
                LOG_W(TAG, "ESP emergency accepted (no token configured - fail-open)");
#endif
            }

            if (command == "emergency_stop") {
                LOG_W(TAG, "╔════════════════════════════════════════╗");
                LOG_W(TAG, "║  AUTHORIZED EMERGENCY-STOP TRIGGERED  ║");
                LOG_W(TAG, "╚════════════════════════════════════════╝");
                // M2: In ESP-IDF path (Core 0), notify Safety-Task on Core 1 (<1µs).
                // In PubSubClient path (Core 1), direct call is safe.
#ifndef MQTT_USE_PUBSUBCLIENT
                if (g_safety_task_handle != NULL) {
                    xTaskNotify(g_safety_task_handle, NOTIFY_EMERGENCY_STOP, eSetBits);
                }
#else
                flushActuatorCommandQueue();
                flushSensorCommandQueue();
                bumpSafetyEpoch("pubsub_emergency_stop");
                safetyController.emergencyStopAll("ESP emergency command (authenticated)");
#endif
                publishIntentOutcome("command",
                                     metadata,
                                     "applied",
                                     "EMERGENCY_STOP_TRIGGERED",
                                     "ESP emergency stop accepted and dispatched",
                                     false);
                publishEmergencyTransportAck(metadata, "emergency_stop");
            } else if (command == "clear_emergency") {
                LOG_I(TAG, "╔════════════════════════════════════════╗");
                LOG_I(TAG, "║  AUTHORIZED EMERGENCY-CLEAR TRIGGERED ║");
                LOG_I(TAG, "╚════════════════════════════════════════╝");
                bool success = safetyController.clearEmergencyStop();
                if (success) {
                    safetyController.resumeOperation();
                    mqttClient.publish(esp_emergency_topic + "/response",
                                      "{\"status\":\"emergency_cleared\",\"timestamp\":" + String(millis()) + ",\"seq\":" + String(mqttClient.getNextSeq()) + "}");
                    publishIntentOutcome("command",
                                         metadata,
                                         "applied",
                                         "EMERGENCY_CLEAR_APPLIED",
                                         "ESP emergency clear applied",
                                         false);
                    publishRecoveryTransportConfirm(metadata);
                } else {
                    mqttClient.publish(esp_emergency_topic + "/error",
                                      "{\"error\":\"clear_failed\",\"message\":\"Safety verification failed\",\"seq\":" + String(mqttClient.getNextSeq()) + "}");
                    publishIntentOutcome("command",
                                         metadata,
                                         "failed",
                                         "EMERGENCY_CLEAR_REJECTED",
                                         "ESP emergency clear rejected by safety verification",
                                         false);
                }
            } else {
                publishIntentOutcome("command",
                                     metadata,
                                     "rejected",
                                     "VALIDATION_FAIL",
                                     String("Unsupported emergency command: ") + command,
                                     false);
            }
        } else {
            LOG_E(TAG, "Failed to parse emergency command JSON");
            publishIntentOutcome("command",
                                 metadata,
                                 "failed",
                                 "EMERGENCY_PARSE_ERROR",
                                 String("Emergency command parse error: ") + String(error.c_str()),
                                 false);
        }
        return;
    }

    // ─── Broadcast emergency ─────────────────────────────────────────────────
    String broadcast_emergency_topic = String(TopicBuilder::buildBroadcastEmergencyTopic());
    if (topic == broadcast_emergency_topic) {
        // Server payload includes command, reason, issued_by, timestamp (ISO-string ~32 chars),
        // devices_stopped, actuators_stopped — minimum ~300 bytes; 512 gives safe headroom.
        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "emergency");
        DynamicJsonDocument doc(512);
        DeserializationError error = deserializeJson(doc, payload);

        if (error) {
            uint32_t parse_count = g_emergency_parse_error_count.fetch_add(1) + 1;
            uint32_t cls_count = incrementEmergencyParseClassCounter(EmergencyParseClass::MALFORMED);
            String reason = String("Broadcast emergency parse error: ") + String(error.c_str()) +
                            " (code=EMERGENCY_PARSE_ERROR, class=malformed, count=" +
                            String(parse_count) + ", class_count=" + String(cls_count) + ")";
            LOG_E(TAG, reason);
            errorTracker.logCommunicationError(ERROR_MQTT_PAYLOAD_INVALID, reason.c_str());
            publishIntentOutcome("command",
                                 metadata,
                                 "failed",
                                 "EMERGENCY_PARSE_ERROR",
                                 reason,
                                 false);
            LOG_W(TAG, "[SAFETY] Broadcast emergency rejected (class=malformed, policy=reject_no_stop)");
            return;
        }

        JsonObject root = doc.as<JsonObject>();
        BroadcastEmergencyContractInput contract_input{};
        contract_input.command_present = root.containsKey("command");
        contract_input.command_is_string = contract_input.command_present &&
                                           root["command"].is<const char*>();
        contract_input.command_value = contract_input.command_is_string
                                           ? root["command"].as<const char*>()
                                           : nullptr;
        contract_input.action_present = root.containsKey("action");
        contract_input.action_is_string = contract_input.action_present &&
                                          root["action"].is<const char*>();
        contract_input.action_value = contract_input.action_is_string
                                          ? root["action"].as<const char*>()
                                          : nullptr;
        contract_input.auth_token_present = root.containsKey("auth_token");
        contract_input.auth_token_is_string = contract_input.auth_token_present &&
                                              root["auth_token"].is<const char*>();
        contract_input.reason_present = root.containsKey("reason");
        contract_input.reason_is_string = contract_input.reason_present &&
                                          root["reason"].is<const char*>();
        contract_input.issued_by_present = root.containsKey("issued_by");
        contract_input.issued_by_is_string = contract_input.issued_by_present &&
                                             root["issued_by"].is<const char*>();
        contract_input.timestamp_present = root.containsKey("timestamp");
        contract_input.timestamp_is_string = contract_input.timestamp_present &&
                                             root["timestamp"].is<const char*>();

        BroadcastEmergencyContractResult contract_result =
            validateBroadcastEmergencyContract(contract_input);
        if (contract_result.status != BroadcastEmergencyContractStatus::VALID) {
            uint32_t mismatch_count = g_emergency_contract_mismatch_count.fetch_add(1) + 1;
            EmergencyParseClass parse_class =
                classifyEmergencyContractMismatch(contract_result.detail_code);
            uint32_t cls_count = incrementEmergencyParseClassCounter(parse_class);
            String reason = String("Broadcast emergency contract mismatch: detail=") +
                            contract_result.detail_code +
                            " (code=EMERGENCY_CONTRACT_MISMATCH, class=" +
                            emergencyParseClassToString(parse_class) + ", count=" +
                            String(mismatch_count) + ", class_count=" + String(cls_count) + ")";
            LOG_E(TAG, reason);
            errorTracker.logCommunicationError(ERROR_MQTT_PAYLOAD_INVALID, reason.c_str());
            publishIntentOutcome("command",
                                 metadata,
                                 "failed",
                                 "EMERGENCY_CONTRACT_MISMATCH",
                                 reason,
                                 false);
            if (parse_class == EmergencyParseClass::CRITICAL_UNKNOWN) {
                uint32_t failsafe_count = g_emergency_failsafe_trigger_count.fetch_add(1) + 1;
                LOG_E(TAG, "[SAFETY] Fail-safe emergency stop triggered (class=critical_unknown, count=" +
                           String(failsafe_count) + ")");
                triggerBroadcastEmergencyStop("pubsub_broadcast_emergency_contract_mismatch",
                                              "Broadcast emergency critical unknown contract state");
            } else {
                LOG_W(TAG, String("[SAFETY] Broadcast emergency rejected (class=") +
                           emergencyParseClassToString(parse_class) + ", policy=reject_no_stop)");
            }
            return;
        }

        String command = String(contract_result.normalized_command);
        String auth_token = contract_input.auth_token_is_string
                                ? String(root["auth_token"].as<const char*>())
                                : "";

        // Validate auth_token — fail-open
        String stored_broadcast_token = "";
        if (storageManager.beginNamespace("system_config", true)) {
            stored_broadcast_token = storageManager.getStringObj("broadcast_em_tok", "");
            storageManager.endNamespace();
        }

        if (stored_broadcast_token.length() > 0 && auth_token != stored_broadcast_token) {
            LOG_E(TAG, "╔════════════════════════════════════════╗");
            LOG_E(TAG, "║  [SECURITY] UNAUTHORIZED BROADCAST     ║");
            LOG_E(TAG, "║  EMERGENCY-STOP ATTEMPT REJECTED       ║");
            LOG_E(TAG, "╚════════════════════════════════════════╝");
            LOG_E(TAG, "[SECURITY] Broadcast emergency-stop rejected: invalid token");
            errorTracker.trackError(3500, ERROR_SEVERITY_CRITICAL,
                                   "Broadcast emergency-stop rejected: invalid auth_token");
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "UNAUTHORIZED",
                                 "Broadcast emergency rejected: invalid auth_token",
                                 false);
            return;
        }

        if (stored_broadcast_token.length() == 0) {
#if EMERGENCY_TOKEN_REQUIRED
            g_emergency_rejected_no_token_count.fetch_add(1);
            LOG_E(TAG, "[INC-EA5484] broadcast emergency rejected no_token (EMERGENCY_TOKEN_REQUIRED=1)");
            errorTracker.trackError(ERROR_EMERGENCY_REJECTED_NO_TOKEN, ERROR_SEVERITY_CRITICAL,
                                   "Broadcast emergency rejected: no token configured (fail-closed)");
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 "NO_TOKEN_CONFIGURED",
                                 "Broadcast emergency rejected: no token configured (prod fail-closed)",
                                 false);
            return;
#else
            LOG_W(TAG, "Broadcast emergency accepted (no token configured - fail-open)");
#endif
        }

        LOG_W(TAG, "╔════════════════════════════════════════╗");
        LOG_W(TAG, "║  BROADCAST EMERGENCY-STOP RECEIVED    ║");
        LOG_W(TAG, "╚════════════════════════════════════════╝");
        publishIntentOutcome("command",
                             metadata,
                             "applied",
                             "BROADCAST_EMERGENCY_STOP_TRIGGERED",
                             String("Broadcast emergency accepted and dispatched: command=") + command,
                             false);
        triggerBroadcastEmergencyStop("pubsub_broadcast_emergency",
                                      "Broadcast emergency (God-Kaiser)");
        return;
    }

    // ─── System commands (factory_reset, onewire/scan, status, …) ───────────
    // M3-TODO: Queue complex commands (GPIO-touching) to Core 1
    String system_command_topic = String(TopicBuilder::buildSystemCommandTopic());

    if (topic == system_command_topic) {
        LOG_I(TAG, "Topic matched! Parsing JSON payload...");
        LOG_I(TAG, "Payload: " + payload);

        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, payload);

        if (error) {
            LOG_E(TAG, "JSON parse error: " + String(error.c_str()));
            LOG_E(TAG, "Raw payload: " + payload);
            IntentMetadata meta = extractIntentMetadataFromPayload(payload.c_str(), "sys");
            DynamicJsonDocument err_doc(320);
            err_doc["command"] = "";
            err_doc["success"] = false;
            err_doc["esp_id"] = g_system_config.esp_id;
            err_doc["error"] = "JSON_PARSE_ERROR";
            err_doc["message"] = String("System command JSON parse failed: ") + error.c_str();
            err_doc["reason_code"] = "JSON_PARSE_ERROR";
            err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            err_doc["seq"] = mqttClient.getNextSeq();
            err_doc["correlation_id"] = ensureCorrelationId(String(meta.correlation_id));
            String err_payload;
            serializeJson(err_doc, err_payload);
            mqttClient.publish(String(TopicBuilder::buildSystemCommandTopic()) + "/response", err_payload, 1);
            publishIntentOutcome("command",
                                 meta,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("System command JSON parse failed: ") + error.c_str(),
                                 true);
            return;
        }

        String command = doc["command"].as<String>();
        bool confirm = doc["confirm"] | false;
        LOG_I(TAG, "Command parsed: '" + command + "'");

        IntentMetadata metadata = extractIntentMetadataFromPayload(payload.c_str(), "sys");
        CommandAdmissionContext admission_context{
            mqttClient.isRegistrationConfirmed(),
            isConfigPendingAfterResetState(),
            g_system_config.current_state == STATE_PENDING_APPROVAL,
            isRuntimeDegradedState(),
            false,
            isRecoveryIntentAllowed(topic.c_str(), payload.c_str()),
            command.c_str()
        };
        CommandAdmissionDecision admission = shouldAcceptCommand(CommandSubtype::SYSTEM, admission_context);
        if (!admission.accepted) {
            LOG_W(TAG, String("[ADMISSION] System command rejected: ") + admission.reason_code +
                       " command=" + command);
            publishIntentOutcome("command",
                                 metadata,
                                 "rejected",
                                 admission.code,
                                 String("System command rejected: ") + command +
                                     " (reason_code=" + admission.reason_code + ")",
                                 false);
            DynamicJsonDocument response_doc(320);
            response_doc["command"] = command;
            response_doc["success"] = false;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["error"] = admission.code;
            response_doc["reason_code"] = admission.reason_code;
            response_doc["state"] = "CONFIG_PENDING_AFTER_RESET";
            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();
            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            return;
        }
        if (strcmp(admission.code, "PENDING_ALLOWLIST_ACCEPTED") == 0 ||
            strcmp(admission.code, "DEGRADED_ALLOWLIST_ACCEPTED") == 0 ||
            strcmp(admission.code, "RECOVERY_ACCEPTED") == 0) {
            publishIntentOutcome("command",
                                 metadata,
                                 "accepted",
                                 admission.code,
                                 String("System command accepted via pending allowlist: ") + command,
                                 false);
        }

        if (command == "factory_reset" && confirm) {
            LOG_W(TAG, "╔════════════════════════════════════════╗");
            LOG_W(TAG, "║  FACTORY RESET via MQTT               ║");
            LOG_W(TAG, "╚════════════════════════════════════════╝");

            String response = "{\"status\":\"factory_reset_initiated\",\"esp_id\":\"" +
                            configManager.getESPId() + "\",\"seq\":" + String(mqttClient.getNextSeq()) + "}";
            mqttClient.publish(system_command_topic + "/response", response);

            configManager.resetWiFiConfig();
            KaiserZone kaiser;
            MasterZone master;
            configManager.saveZoneConfig(kaiser, master);

            LOG_I(TAG, "✅ Configuration cleared via MQTT");
            LOG_I(TAG, "Rebooting in 3 seconds...");
            delay(3000);
            ESP.restart();
        }
        // ─── OneWire Scan ────────────────────────────────────────────────────
        else if (command == "onewire/scan") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  ONEWIRE SCAN COMMAND RECEIVED        ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            uint8_t pin = HardwareConfig::DEFAULT_ONEWIRE_PIN;
            if (doc["params"].containsKey("pin")) {
                pin = doc["params"]["pin"].as<uint8_t>();
            } else if (doc.containsKey("pin")) {
                pin = doc["pin"].as<uint8_t>();
            }
            LOG_I(TAG, "OneWire scan on GPIO " + String(pin));

            if (!oneWireBusManager.isInitialized()) {
                LOG_I(TAG, "Initializing OneWire bus on GPIO " + String(pin));
                if (!oneWireBusManager.begin(pin)) {
                    LOG_E(TAG, "Failed to initialize OneWire bus on GPIO " + String(pin));
                    String error_response = "{\"error\":\"Failed to initialize OneWire bus\",\"pin\":" +
                                           String(pin) + ",\"seq\":" + String(mqttClient.getNextSeq()) + "}";
                    mqttClient.publish(system_command_topic + "/response", error_response);
                    return;
                }
            } else {
                uint8_t current_pin = oneWireBusManager.getPin();
                if (current_pin != pin) {
                    LOG_I(TAG, "OneWire bus switching from GPIO " + String(current_pin) +
                               " to GPIO " + String(pin));
                    oneWireBusManager.end();
                    if (!oneWireBusManager.begin(pin)) {
                        LOG_E(TAG, "Failed to switch OneWire bus to GPIO " + String(pin));
                        oneWireBusManager.begin(current_pin);
                        String error_response = "{\"error\":\"Failed to switch OneWire bus\",\"requested_pin\":" +
                                               String(pin) + ",\"active_pin\":" + String(current_pin) + ",\"seq\":" + String(mqttClient.getNextSeq()) + "}";
                        mqttClient.publish(system_command_topic + "/response", error_response);
                        return;
                    }
                }
            }

            uint8_t rom_codes[10][8];
            uint8_t found_count = 0;

            LOG_I(TAG, "Scanning OneWire bus...");
            if (!oneWireBusManager.scanDevices(rom_codes, 10, found_count)) {
                LOG_E(TAG, "OneWire bus scan failed");
                String error_response = "{\"error\":\"OneWire scan failed\",\"pin\":" + String(pin) + ",\"seq\":" + String(mqttClient.getNextSeq()) + "}";
                mqttClient.publish(system_command_topic + "/response", error_response);
                return;
            }

            LOG_I(TAG, "OneWire scan complete: " + String(found_count) + " devices found");

            String response = "{\"devices\":[";
            for (uint8_t i = 0; i < found_count; i++) {
                if (i > 0) response += ",";
                response += "{";
                response += "\"rom_code\":\"";
                response += OneWireUtils::romToHexString(rom_codes[i]);
                response += "\",";
                response += "\"device_type\":\"";
                response += OneWireUtils::getDeviceType(rom_codes[i]);
                response += "\",";
                response += "\"pin\":";
                response += String(pin);
                response += "}";
            }
            response += "],\"found_count\":";
            response += String(found_count);
            response += ",\"seq\":";
            response += String(mqttClient.getNextSeq());
            response += "}";

            String scan_result_topic = "kaiser/god/esp/" + g_system_config.esp_id + "/onewire/scan_result";
            LOG_I(TAG, "Publishing scan result to: " + scan_result_topic);
            mqttClient.publish(scan_result_topic, response);

            String ack_response = "{\"command\":\"onewire/scan\",\"status\":\"ok\",\"found_count\":";
            ack_response += String(found_count);
            ack_response += ",\"pin\":";
            ack_response += String(pin);
            ack_response += ",\"seq\":";
            ack_response += String(mqttClient.getNextSeq());
            ack_response += "}";
            mqttClient.publish(system_command_topic + "/response", ack_response);

            LOG_I(TAG, "OneWire scan result published");
        }
        // ─── Status ──────────────────────────────────────────────────────────
        else if (command == "status") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  STATUS COMMAND RECEIVED              ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            time_t unix_timestamp = timeManager.getUnixTimestamp();

            DynamicJsonDocument response_doc(1024);
            response_doc["command"] = "status";
            response_doc["success"] = true;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["state"] = static_cast<int>(g_system_config.current_state);
            response_doc["uptime"] = millis() / 1000;
            response_doc["heap_free"] = ESP.getFreeHeap();
            response_doc["wifi_rssi"] = WiFi.RSSI();
            response_doc["sensor_count"] = sensorManager.getActiveSensorCount();
            response_doc["actuator_count"] = actuatorManager.getActiveActuatorCount();
            response_doc["zone_id"] = g_kaiser.zone_id;
            response_doc["zone_assigned"] = g_kaiser.zone_assigned;
            response_doc["ts"] = (unsigned long)unix_timestamp;
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_I(TAG, "Status command response sent");
        }
        // ─── Diagnostics ─────────────────────────────────────────────────────
        else if (command == "diagnostics") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  DIAGNOSTICS COMMAND RECEIVED         ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            time_t unix_timestamp = timeManager.getUnixTimestamp();

            DynamicJsonDocument response_doc(2048);
            response_doc["command"] = "diagnostics";
            response_doc["success"] = true;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["state"] = static_cast<int>(g_system_config.current_state);
            response_doc["uptime"] = millis() / 1000;
            response_doc["heap_free"] = ESP.getFreeHeap();
            response_doc["heap_min"] = ESP.getMinFreeHeap();
            response_doc["chip_model"] = ESP.getChipModel();
            response_doc["chip_revision"] = ESP.getChipRevision();
            response_doc["flash_size"] = ESP.getFlashChipSize();
            response_doc["sdk_version"] = ESP.getSdkVersion();
            response_doc["wifi_rssi"] = WiFi.RSSI();
            response_doc["wifi_ssid"] = WiFi.SSID();
            response_doc["wifi_ip"] = WiFi.localIP().toString();
            response_doc["wifi_mac"] = WiFi.macAddress();
            response_doc["zone_id"] = g_kaiser.zone_id;
            response_doc["master_zone_id"] = g_kaiser.master_zone_id;
            response_doc["kaiser_id"] = g_kaiser.kaiser_id;
            response_doc["zone_assigned"] = g_kaiser.zone_assigned;
            response_doc["sensor_count"] = sensorManager.getActiveSensorCount();
            response_doc["actuator_count"] = actuatorManager.getActiveActuatorCount();
            response_doc["boot_count"] = g_system_config.boot_count;
            response_doc["config_status"] = serialized(configManager.getDiagnosticsJSON());
            response_doc["ts"] = (unsigned long)unix_timestamp;
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_I(TAG, "Diagnostics command response sent");
        }
        // ─── Get Config ──────────────────────────────────────────────────────
        else if (command == "get_config") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  GET_CONFIG COMMAND RECEIVED          ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            DynamicJsonDocument response_doc(2048);
            response_doc["command"] = "get_config";
            response_doc["success"] = true;
            response_doc["esp_id"] = g_system_config.esp_id;

            JsonObject zone = response_doc.createNestedObject("zone");
            zone["zone_id"] = g_kaiser.zone_id;
            zone["master_zone_id"] = g_kaiser.master_zone_id;
            zone["zone_name"] = g_kaiser.zone_name;
            zone["kaiser_id"] = g_kaiser.kaiser_id;
            zone["zone_assigned"] = g_kaiser.zone_assigned;

            JsonArray sensors = response_doc.createNestedArray("sensors");
            uint8_t sensor_count = sensorManager.getActiveSensorCount();
            for (uint8_t i = 0; i < sensor_count && i < 20; i++) {
                // Get sensor info via manager (simplified — count only)
            }
            response_doc["sensor_count"] = sensor_count;

            JsonArray actuators = response_doc.createNestedArray("actuators");
            uint8_t actuator_count = actuatorManager.getActiveActuatorCount();
            response_doc["actuator_count"] = actuator_count;

            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_I(TAG, "Get_config command response sent");
        }
        // ─── Safe Mode ───────────────────────────────────────────────────────
        else if (command == "safe_mode") {
            LOG_W(TAG, "╔════════════════════════════════════════╗");
            LOG_W(TAG, "║  SAFE_MODE COMMAND RECEIVED           ║");
            LOG_W(TAG, "╚════════════════════════════════════════╝");

#ifndef MQTT_USE_PUBSUBCLIENT
            if (g_safety_task_handle != NULL) {
                xTaskNotify(g_safety_task_handle, NOTIFY_EMERGENCY_STOP, eSetBits);
            }
#else
            flushActuatorCommandQueue();
            flushSensorCommandQueue();
            safetyController.emergencyStopAll("Safe mode activated via MQTT command");
#endif

            DynamicJsonDocument response_doc(256);
            response_doc["command"] = "safe_mode";
            response_doc["success"] = true;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["message"] = "Safe mode activated - all actuators stopped";
            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_W(TAG, "Safe mode activated via command");
        }
        // ─── Exit Safe Mode ──────────────────────────────────────────────────
        else if (command == "exit_safe_mode") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  EXIT_SAFE_MODE COMMAND RECEIVED      ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            safetyController.clearEmergencyStop();

            DynamicJsonDocument response_doc(256);
            response_doc["command"] = "exit_safe_mode";
            response_doc["success"] = true;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["message"] = "Safe mode deactivated - actuators can be controlled";
            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_I(TAG, "Safe mode deactivated via command");
        }
        // ─── Force Safe State ─────────────────────────────────────────────────────
        // AUT-66: Manual-Recovery — forces all actuators to safe state regardless of
        // offline rules or fail_safe_on_disconnect policy.
        else if (command == "force_safe_state") {
            LOG_W(TAG, "=== FORCE_SAFE_STATE COMMAND RECEIVED ===");
            if (actuatorManager.isInitialized()) {
                actuatorManager.setAllActuatorsToSafeState();
            }
            DynamicJsonDocument response_doc(256);
            response_doc["command"] = "force_safe_state";
            response_doc["success"] = true;
            response_doc["esp_id"]  = g_system_config.esp_id;
            response_doc["ts"]      = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"]     = mqttClient.getNextSeq();
            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
            LOG_W(TAG, "force_safe_state: all actuators set to safe state");
        }
        // ─── Set Log Level ───────────────────────────────────────────────────
        else if (command == "set_log_level") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  SET_LOG_LEVEL COMMAND RECEIVED       ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            String level;
            if (doc.containsKey("level")) {
                level = doc["level"].as<String>();
            } else if (doc.containsKey("params") && doc["params"].containsKey("level")) {
                level = doc["params"]["level"].as<String>();
            }
            level.toUpperCase();
            LOG_I(TAG, "Requested log level: " + level);

            LogLevel new_level = Logger::getLogLevelFromString(level.c_str());

            bool valid = (level.length() > 0 &&
                         (level == "DEBUG" || level == "INFO" || level == "WARNING" ||
                          level == "ERROR" || level == "CRITICAL"));

            DynamicJsonDocument response_doc(256);
            response_doc["command"] = "set_log_level";
            response_doc["esp_id"] = g_system_config.esp_id;

            if (valid) {
                logger.setLogLevel(new_level);

                if (storageManager.beginNamespace("system_config", false)) {
                    storageManager.putUInt8("log_level", (uint8_t)new_level);
                    storageManager.endNamespace();
                }

                response_doc["success"] = true;
                response_doc["level"] = level;
                response_doc["message"] = "Log level changed to " + level;
                response_doc["persisted"] = true;
                response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();

                LOG_I(TAG, "✅ Log level changed to " + level + " (persisted to NVS)");
            } else {
                response_doc["success"] = false;
                response_doc["error"] = "Invalid log level";
                response_doc["message"] = "Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL";
                response_doc["requested_level"] = level;
                response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();

                LOG_E(TAG, "❌ Invalid log level: " + level);
            }

            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
        }
        // ─── Set Emergency Token ─────────────────────────────────────────────
        else if (command == "set_emergency_token") {
            LOG_I(TAG, "╔════════════════════════════════════════╗");
            LOG_I(TAG, "║  SET_EMERGENCY_TOKEN COMMAND RECEIVED  ║");
            LOG_I(TAG, "╚════════════════════════════════════════╝");

            String token_type = doc["token_type"] | "esp";
            String token_value = doc["token"].as<String>();

            DynamicJsonDocument response_doc(256);
            response_doc["command"] = "set_emergency_token";
            response_doc["esp_id"] = g_system_config.esp_id;

            if (token_value.length() == 0 || token_value.length() > 64) {
                response_doc["success"] = false;
                response_doc["error"] = "Token must be 1-64 characters";
            } else if (token_type == "broadcast") {
                bool saved = false;
                if (storageManager.beginNamespace("system_config", false)) {
                    saved = storageManager.putString("broadcast_em_tok", token_value);
                    storageManager.endNamespace();
                }
                response_doc["success"] = saved;
                response_doc["token_type"] = "broadcast";
                response_doc["message"] = saved ? "Broadcast emergency token updated"
                                                : "Failed to persist broadcast token";
                if (saved) {
                    LOG_I(TAG, "Broadcast emergency token updated (persisted to NVS)");
                } else {
                    LOG_E(TAG, "Failed to persist broadcast emergency token to NVS");
                }
            } else {
                bool saved = false;
                if (storageManager.beginNamespace("system_config", false)) {
                    saved = storageManager.putString("emergency_auth", token_value);
                    storageManager.endNamespace();
                }
                response_doc["success"] = saved;
                response_doc["token_type"] = "esp";
                response_doc["message"] = saved ? "ESP emergency token updated"
                                                : "Failed to persist ESP token";
                if (saved) {
                    LOG_I(TAG, "ESP emergency token updated (persisted to NVS)");
                } else {
                    LOG_E(TAG, "Failed to persist ESP emergency token to NVS");
                }
            }

            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
        }
        // ─── Unknown command ─────────────────────────────────────────────────
        else {
            LOG_W(TAG, "Unknown system command: '" + command + "'");

            DynamicJsonDocument response_doc(256);
            response_doc["command"] = command;
            response_doc["success"] = false;
            response_doc["esp_id"] = g_system_config.esp_id;
            response_doc["error"] = "Unknown command";
            response_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            response_doc["seq"] = mqttClient.getNextSeq();

            String response;
            serializeJson(response_doc, response);
            mqttClient.publish(system_command_topic + "/response", response);
        }
        return;
    }

    // ─── Zone Assignment ─────────────────────────────────────────────────────
    // M3-TODO: Queue to Core 1 (indirect NVS write + config state update)
    String zone_assign_topic = TopicBuilder::buildZoneAssignTopic();

    if (topic == zone_assign_topic) {
        ConfigLaneGuard config_lane_guard;
        if (!config_lane_guard.locked()) {
            LOG_W(TAG, "Zone assignment dropped: config lane busy");
            publishZoneConfigLaneBusyAck(p);
            return;
        }
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  ZONE ASSIGNMENT RECEIVED             ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");

        DynamicJsonDocument doc(512);
        DeserializationError error = deserializeJson(doc, payload);

        if (!error) {
            // .as<String>() returns literal "null" when JSON field is null — sanitize early
            String zone_id = doc["zone_id"].as<String>();
            if (zone_id == "null") zone_id = "";
            String master_zone_id = doc["master_zone_id"].as<String>();
            if (master_zone_id == "null") master_zone_id = "";
            String zone_name = doc["zone_name"].as<String>();
            if (zone_name == "null") zone_name = "";
            String kaiser_id = doc["kaiser_id"].as<String>();
            if (kaiser_id == "null") kaiser_id = "";

            String correlationId = "";
            if (doc.containsKey("correlation_id")) {
                correlationId = doc["correlation_id"].as<String>();
            }
            correlationId = ensureCorrelationId(correlationId);

            // WP1: Empty zone_id = Zone Removal
            if (zone_id.length() == 0) {
                LOG_I(TAG, "╔════════════════════════════════════════╗");
                LOG_I(TAG, "║  ZONE REMOVAL DETECTED                ║");
                LOG_I(TAG, "╚════════════════════════════════════════╝");

                SubzoneConfig subzone_configs[8];
                uint8_t loaded_count = 0;
                configManager.loadAllSubzoneConfigs(subzone_configs, 8, loaded_count);

                for (uint8_t i = 0; i < loaded_count; i++) {
                    for (uint8_t gpio : subzone_configs[i].assigned_gpios) {
                        gpioManager.removePinFromSubzone(gpio);
                    }
                    configManager.removeSubzoneConfig(subzone_configs[i].subzone_id);
                    LOG_I(TAG, "  Cascade-removed subzone: " + subzone_configs[i].subzone_id);
                }

                if (loaded_count > 0) {
                    LOG_I(TAG, "✅ Cascade-removed " + String(loaded_count) + " subzone(s)");
                }

                if (configManager.updateZoneAssignment("", "", "", kaiser_id.length() > 0 ? kaiser_id : "god")) {
                    g_kaiser.zone_id = "";
                    g_kaiser.master_zone_id = "";
                    g_kaiser.zone_name = "";
                    g_kaiser.zone_assigned = false;

                    String ack_topic = TopicBuilder::buildZoneAckTopic();
                    DynamicJsonDocument ack_doc(384);
                    ack_doc["esp_id"] = g_system_config.esp_id;
                    ack_doc["status"] = "zone_removed";
                    ack_doc["zone_id"] = "";
                    ack_doc["master_zone_id"] = "";
                    ack_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
                    ack_doc["seq"] = mqttClient.getNextSeq();
                    ack_doc["correlation_id"] = correlationId;

                    String ack_payload;
                    size_t written = serializeJson(ack_doc, ack_payload);
                    if (written == 0 || ack_payload.length() == 0) {
                        LOG_E(TAG, "JSON serialization failed for Zone Removal ACK");
                        ack_payload = "{\"esp_id\":\"" + g_system_config.esp_id +
                                     "\",\"status\":\"error\",\"message\":\"serialization_failed\",\"ts\":0}";
                    }
                    mqttClient.publish(ack_topic, ack_payload);

                    LOG_I(TAG, "✅ Zone removed successfully");

                    g_system_config.current_state = STATE_PENDING_APPROVAL;
                    configManager.saveSystemConfig(g_system_config);
                } else {
                    LOG_E(TAG, "❌ Failed to remove zone configuration");

                    String ack_topic = TopicBuilder::buildZoneAckTopic();
                    DynamicJsonDocument err_doc(384);
                    err_doc["esp_id"] = g_system_config.esp_id;
                    err_doc["status"] = "error";
                    err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
                    err_doc["seq"] = mqttClient.getNextSeq();
                    err_doc["message"] = "Failed to remove zone config";
                    err_doc["correlation_id"] = correlationId;
                    String error_response;
                    serializeJson(err_doc, error_response);
                    mqttClient.publish(ack_topic, error_response);
                }
                return;
            }

            // Zone Assignment (zone_id not empty)
            // ArduinoJSON parses JSON null as the string "null" via .as<String>()
            if (kaiser_id.length() == 0 || kaiser_id == "null") {
                LOG_W(TAG, "Kaiser_id invalid ('" + kaiser_id + "'), using default 'god'");
                kaiser_id = "god";
            }

            LOG_I(TAG, "Zone ID: " + zone_id);
            LOG_I(TAG, "Master Zone: " + master_zone_id);
            LOG_I(TAG, "Zone Name: " + zone_name);
            LOG_I(TAG, "Kaiser ID: " + kaiser_id);

            KaiserZone temp_kaiser;
            temp_kaiser.zone_id = zone_id;
            temp_kaiser.master_zone_id = master_zone_id;
            temp_kaiser.zone_name = zone_name;
            temp_kaiser.kaiser_id = kaiser_id;
            temp_kaiser.zone_assigned = true;

            if (!configManager.validateZoneConfig(temp_kaiser)) {
                LOG_E(TAG, "❌ Zone configuration validation failed");

                String ack_topic = TopicBuilder::buildZoneAckTopic();
                DynamicJsonDocument err_doc(384);
                err_doc["esp_id"] = g_system_config.esp_id;
                err_doc["status"] = "error";
                err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
                err_doc["seq"] = mqttClient.getNextSeq();
                err_doc["message"] = "Zone validation failed";
                err_doc["correlation_id"] = correlationId;
                String error_response;
                serializeJson(err_doc, error_response);
                mqttClient.publish(ack_topic, error_response);
                return;
            }

            if (configManager.updateZoneAssignment(zone_id, master_zone_id, zone_name, kaiser_id)) {
                g_kaiser.zone_id = zone_id;
                g_kaiser.master_zone_id = master_zone_id;
                g_kaiser.zone_name = zone_name;
                g_kaiser.zone_assigned = true;
                if (kaiser_id.length() > 0 && kaiser_id != g_kaiser.kaiser_id) {
                    String old_kaiser_id = g_kaiser.kaiser_id;

                    // WP3: Unsubscribe from old kaiser_id topics to prevent duplicate messages
                    String old_zone_assign = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/zone/assign";
                    String old_sensor_cmd = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/sensor/+/command";
                    String old_subzone_assign = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/subzone/assign";
                    String old_subzone_remove = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/subzone/remove";
                    String old_subzone_safe = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/subzone/safe";
                    String old_actuator_cmd = "kaiser/" + old_kaiser_id + "/esp/" + g_system_config.esp_id + "/actuator/+/command";
                    String old_heartbeat_ack = "kaiser/" + old_kaiser_id + "/esp/" +
                                               g_system_config.esp_id + "/system/heartbeat/ack";

                    mqttClient.unsubscribe(old_zone_assign);
                    mqttClient.unsubscribe(old_sensor_cmd);
                    mqttClient.unsubscribe(old_subzone_assign);
                    mqttClient.unsubscribe(old_subzone_remove);
                    mqttClient.unsubscribe(old_subzone_safe);
                    mqttClient.unsubscribe(old_actuator_cmd);
                    mqttClient.unsubscribe(old_heartbeat_ack);

                    LOG_I(TAG, "Unsubscribed from old kaiser_id topics: " + old_kaiser_id);

                    g_kaiser.kaiser_id = kaiser_id;
                    TopicBuilder::setKaiserId(kaiser_id.c_str());

                    LOG_I(TAG, "Kaiser ID changed - re-subscribing to topics...");

                    mqttClient.subscribe(TopicBuilder::buildZoneAssignTopic(), 1);

                    String sensor_cmd_wildcard = String(TopicBuilder::buildSensorCommandTopic(0));
                    sensor_cmd_wildcard.replace("/0/command", "/+/command");
                    mqttClient.subscribe(sensor_cmd_wildcard, 1);

                    mqttClient.subscribe(TopicBuilder::buildSubzoneAssignTopic(), 1);
                    mqttClient.subscribe(TopicBuilder::buildSubzoneRemoveTopic(), 1);

                    String actuator_cmd_wildcard = String(TopicBuilder::buildActuatorCommandTopic(0));
                    actuator_cmd_wildcard.replace("/0/command", "/+/command");
                    mqttClient.subscribe(actuator_cmd_wildcard, 1);

                    mqttClient.subscribe(TopicBuilder::buildSystemHeartbeatAckTopic());

                    LOG_I(TAG, "Topics re-subscribed with new kaiser_id: " + kaiser_id);
                }

                String ack_topic = TopicBuilder::buildZoneAckTopic();
                DynamicJsonDocument ack_doc(384);
                ack_doc["esp_id"] = g_system_config.esp_id;
                ack_doc["status"] = "zone_assigned";
                ack_doc["zone_id"] = zone_id;
                ack_doc["master_zone_id"] = master_zone_id;
                ack_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
                ack_doc["seq"] = mqttClient.getNextSeq();
                ack_doc["correlation_id"] = correlationId;

                String ack_payload;
                size_t written = serializeJson(ack_doc, ack_payload);
                if (written == 0 || ack_payload.length() == 0) {
                    LOG_E(TAG, "JSON serialization failed for Zone ACK");
                    ack_payload = "{\"esp_id\":\"" + g_system_config.esp_id +
                                 "\",\"status\":\"error\",\"message\":\"serialization_failed\",\"ts\":0}";
                }
                mqttClient.publish(ack_topic, ack_payload);

                LOG_I(TAG, "✅ Zone assignment successful");
                LOG_I(TAG, "ESP is now part of zone: " + zone_id);

                g_system_config.current_state = STATE_ZONE_CONFIGURED;
                configManager.saveSystemConfig(g_system_config);
            } else {
                LOG_E(TAG, "❌ Failed to save zone configuration");

                String ack_topic = TopicBuilder::buildZoneAckTopic();
                DynamicJsonDocument err_doc(384);
                err_doc["esp_id"] = g_system_config.esp_id;
                err_doc["status"] = "error";
                err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
                err_doc["seq"] = mqttClient.getNextSeq();
                err_doc["message"] = "Failed to save zone config";
                err_doc["correlation_id"] = correlationId;
                String error_response;
                serializeJson(err_doc, error_response);
                mqttClient.publish(ack_topic, error_response);
            }
        } else {
            LOG_E(TAG, "Failed to parse zone assignment JSON");
            IntentMetadata zm = extractIntentMetadataFromPayload(p, "zone");
            String corr = ensureCorrelationId(String(zm.correlation_id));
            String ack_topic = TopicBuilder::buildZoneAckTopic();
            DynamicJsonDocument err_doc(384);
            err_doc["esp_id"] = g_system_config.esp_id;
            err_doc["status"] = "error";
            err_doc["reason_code"] = "JSON_PARSE_ERROR";
            err_doc["message"] = String("Zone JSON parse failed: ") + error.c_str();
            err_doc["ts"] = (unsigned long)timeManager.getUnixTimestamp();
            err_doc["seq"] = mqttClient.getNextSeq();
            err_doc["correlation_id"] = corr;
            String error_response;
            serializeJson(err_doc, error_response);
            mqttClient.publish(ack_topic, error_response, 1);
            publishIntentOutcome("zone",
                                 zm,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("Zone assignment JSON parse failed: ") + error.c_str(),
                                 true);
        }
        return;
    }

    // ─── Subzone Assignment ──────────────────────────────────────────────────
    // M3-TODO: Queue to Core 1 (GPIOManager touches GPIO)
    String subzone_assign_topic = TopicBuilder::buildSubzoneAssignTopic();
    if (topic == subzone_assign_topic) {
        ConfigLaneGuard config_lane_guard;
        if (!config_lane_guard.locked()) {
            LOG_W(TAG, "Subzone assignment dropped: config lane busy");
            publishSubzoneConfigLaneBusyAck(p, "subzone_assign");
            return;
        }
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  SUBZONE ASSIGNMENT RECEIVED          ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");

        DynamicJsonDocument doc(1024);
        DeserializationError error = deserializeJson(doc, payload);

        if (!error) {
            String subzone_id = doc["subzone_id"].as<String>();
            String subzone_name = doc["subzone_name"].as<String>();
            String parent_zone_id = doc["parent_zone_id"].as<String>();
            JsonArray gpios_array = doc["assigned_gpios"];
            bool safe_mode_active = doc["safe_mode_active"] | true;

            String correlationId = "";
            if (doc.containsKey("correlation_id")) {
                correlationId = doc["correlation_id"].as<String>();
            }
            correlationId = ensureCorrelationId(correlationId);

            if (subzone_id.length() == 0) {
                LOG_E(TAG, "Subzone assignment failed: subzone_id is empty");
                sendSubzoneAck(subzone_id, "error", "subzone_id is required", correlationId);
                return;
            }

            if (parent_zone_id.length() > 0 && parent_zone_id != g_kaiser.zone_id) {
                LOG_E(TAG, "Subzone assignment failed: parent_zone_id doesn't match ESP zone");
                sendSubzoneAck(subzone_id, "error", "parent_zone_id mismatch", correlationId);
                return;
            }

            if (!g_kaiser.zone_assigned) {
                LOG_E(TAG, "Subzone assignment failed: ESP zone not assigned");
                sendSubzoneAck(subzone_id, "error", "ESP zone not assigned", correlationId);
                return;
            }

            SubzoneConfig subzone_config;
            subzone_config.subzone_id = subzone_id;
            subzone_config.subzone_name = subzone_name;
            subzone_config.parent_zone_id = parent_zone_id.length() > 0 ? parent_zone_id : g_kaiser.zone_id;
            subzone_config.safe_mode_active = safe_mode_active;
            subzone_config.created_timestamp = doc["timestamp"] | millis() / 1000;

            for (JsonVariant gpio_value : gpios_array) {
                uint8_t gpio = gpio_value.as<uint8_t>();
                subzone_config.assigned_gpios.push_back(gpio);
            }

            if (!configManager.validateSubzoneConfig(subzone_config)) {
                LOG_E(TAG, "Subzone assignment failed: validation failed");
                sendSubzoneAck(subzone_id, "error", "subzone config validation failed", correlationId);
                return;
            }

            bool all_assigned = true;
            for (uint8_t gpio : subzone_config.assigned_gpios) {
                if (!gpioManager.assignPinToSubzone(gpio, subzone_id)) {
                    LOG_E(TAG, "Failed to assign GPIO " + String(gpio) + " to subzone");
                    all_assigned = false;
                    for (uint8_t assigned_gpio : subzone_config.assigned_gpios) {
                        if (assigned_gpio != gpio) {
                            gpioManager.removePinFromSubzone(assigned_gpio);
                        }
                    }
                    break;
                }
            }

            if (!all_assigned) {
                sendSubzoneAck(subzone_id, "error", "GPIO assignment failed", correlationId);
                return;
            }

            if (safe_mode_active) {
                if (!gpioManager.enableSafeModeForSubzone(subzone_id)) {
                    LOG_W(TAG, "Failed to enable safe-mode for subzone, but assignment continues");
                }
            }

            subzone_config.sensor_count = sensorManager.countSensorsWithSubzone(subzone_id);
            subzone_config.actuator_count = actuatorManager.countActuatorsWithSubzone(subzone_id);

            if (!configManager.saveSubzoneConfig(subzone_config)) {
                LOG_E(TAG, "Failed to save subzone config to NVS");
                sendSubzoneAck(subzone_id, "error", "NVS save failed", correlationId);
                return;
            }

            sendSubzoneAck(subzone_id, "subzone_assigned", "", correlationId);
            LOG_I(TAG, "✅ Subzone assignment successful: " + subzone_id);
        } else {
            LOG_E(TAG, "Failed to parse subzone assignment JSON");
            IntentMetadata sm = extractIntentMetadataFromPayload(p, "subz");
            String sc = ensureCorrelationId(String(sm.correlation_id));
            sendSubzoneAck("unknown",
                           "error",
                           String("JSON parse failed: ") + error.c_str(),
                           sc,
                           "JSON_PARSE_ERROR");
            publishIntentOutcome("subzone_assign",
                                 sm,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("Subzone assign JSON parse failed: ") + error.c_str(),
                                 true);
        }
        return;
    }

    // ─── Subzone Removal ─────────────────────────────────────────────────────
    String subzone_remove_topic = TopicBuilder::buildSubzoneRemoveTopic();
    if (topic == subzone_remove_topic) {
        ConfigLaneGuard config_lane_guard;
        if (!config_lane_guard.locked()) {
            LOG_W(TAG, "Subzone removal dropped: config lane busy");
            publishSubzoneConfigLaneBusyAck(p, "subzone_remove");
            return;
        }
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  SUBZONE REMOVAL RECEIVED             ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");

        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, payload);

        if (!error) {
            String subzone_id = doc["subzone_id"].as<String>();

            String correlationId = "";
            if (doc.containsKey("correlation_id")) {
                correlationId = doc["correlation_id"].as<String>();
            }

            correlationId = ensureCorrelationId(correlationId);

            if (subzone_id.length() == 0) {
                LOG_E(TAG, "Subzone removal failed: subzone_id is empty");
                sendSubzoneAck("unknown",
                               "error",
                               "subzone_id is required",
                               correlationId,
                               "VALIDATION_ERROR");
                return;
            }

            SubzoneConfig config;
            if (!configManager.loadSubzoneConfig(subzone_id, config)) {
                LOG_W(TAG, "Subzone " + subzone_id + " not found for removal");
                sendSubzoneAck(subzone_id,
                               "error",
                               "subzone not found",
                               correlationId,
                               "SUBZONE_NOT_FOUND");
                return;
            }

            for (uint8_t gpio : config.assigned_gpios) {
                gpioManager.removePinFromSubzone(gpio);
            }

            configManager.removeSubzoneConfig(subzone_id);
            sendSubzoneAck(subzone_id, "subzone_removed", "", correlationId);
            LOG_I(TAG, "✅ Subzone removed: " + subzone_id);
        } else {
            IntentMetadata rm = extractIntentMetadataFromPayload(p, "subz");
            String rc = ensureCorrelationId(String(rm.correlation_id));
            sendSubzoneAck("unknown",
                           "error",
                           String("JSON parse failed: ") + error.c_str(),
                           rc,
                           "JSON_PARSE_ERROR");
            publishIntentOutcome("subzone_remove",
                                 rm,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("Subzone remove JSON parse failed: ") + error.c_str(),
                                 true);
        }
        return;
    }

    // ─── Subzone Safe-Mode ───────────────────────────────────────────────────
    String subzone_safe_topic = TopicBuilder::buildSubzoneSafeTopic();
    if (topic == subzone_safe_topic) {
        ConfigLaneGuard config_lane_guard;
        if (!config_lane_guard.locked()) {
            LOG_W(TAG, "Subzone safe-mode dropped: config lane busy");
            publishSubzoneConfigLaneBusyAck(p, "subzone_safe");
            return;
        }
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  SUBZONE SAFE-MODE RECEIVED           ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");

        DynamicJsonDocument doc(512);
        DeserializationError error = deserializeJson(doc, payload);

        if (!error) {
            String subzone_id = doc["subzone_id"].as<String>();
            String action = doc["action"].as<String>();
            bool safe_mode = doc["safe_mode"] | (action == "enable");

            String safe_corr = "";
            if (doc.containsKey("correlation_id")) {
                safe_corr = doc["correlation_id"].as<String>();
            }
            safe_corr = ensureCorrelationId(safe_corr);

            if (subzone_id.length() == 0) {
                LOG_E(TAG, "Subzone safe-mode failed: subzone_id is empty");
                sendSubzoneAck("unknown",
                               "error",
                               "subzone_id is required",
                               safe_corr,
                               "VALIDATION_ERROR");
                return;
            }

            SubzoneConfig config;
            if (!configManager.loadSubzoneConfig(subzone_id, config)) {
                LOG_W(TAG, "Subzone " + subzone_id + " not found for safe-mode");
                sendSubzoneAck(subzone_id,
                               "error",
                               "subzone not found",
                               safe_corr,
                               "SUBZONE_NOT_FOUND");
                return;
            }

            if (action == "enable" || safe_mode) {
                if (gpioManager.enableSafeModeForSubzone(subzone_id)) {
                    config.safe_mode_active = true;
                    configManager.saveSubzoneConfig(config);
                    LOG_I(TAG, "✅ Safe-mode ENABLED for subzone: " + subzone_id);
                } else {
                    LOG_E(TAG, "Failed to enable safe-mode for subzone: " + subzone_id);
                }
            } else if (action == "disable" || !safe_mode) {
                if (gpioManager.disableSafeModeForSubzone(subzone_id)) {
                    config.safe_mode_active = false;
                    configManager.saveSubzoneConfig(config);
                    LOG_I(TAG, "✅ Safe-mode DISABLED for subzone: " + subzone_id);
                } else {
                    LOG_E(TAG, "Failed to disable safe-mode for subzone: " + subzone_id);
                }
            }
        } else {
            LOG_E(TAG, "Failed to parse subzone safe-mode JSON");
            IntentMetadata fm = extractIntentMetadataFromPayload(p, "subz");
            String fc = ensureCorrelationId(String(fm.correlation_id));
            sendSubzoneAck("unknown",
                           "error",
                           String("JSON parse failed: ") + error.c_str(),
                           fc,
                           "JSON_PARSE_ERROR");
            publishIntentOutcome("subzone_safe",
                                 fm,
                                 "failed",
                                 "JSON_PARSE_ERROR",
                                 String("Subzone safe JSON parse failed: ") + error.c_str(),
                                 true);
        }
        return;
    }

    // ─── Server Status (LWT) — SAFETY-P5 ─────────────────────────────────────
    // Handles both: server crashes (broker publishes LWT) and graceful shutdowns
    // (server publishes "offline" before disconnect).
    // IMPORTANT precedence rule:
    // - server/status = liveness hint only
    // - heartbeat/ack = authoritative recovery + registration source
    if (topic.indexOf("/server/status") >= 0) {
        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, payload);
        if (error) {
            LOG_W(TAG, "[SAFETY-P5] server/status parse error: " + String(error.c_str()));
            return;
        }

        const char* status = doc["status"] | "unknown";

        if (strcmp(status, "offline") == 0) {
            const char* reason = doc["reason"] | "unknown";
            unsigned long since_connect_ms = millis() - g_last_mqtt_connect_ms.load();
            bool after_reconnect = g_mqtt_reconnect_count.load() > 0;
            bool likely_stale_retain =
                (strcmp(reason, "unexpected_disconnect") == 0) &&
                after_reconnect &&
                (since_connect_ms < 15000UL) &&
                !mqttClient.isRegistrationConfirmed();

            // SAFETY-P5 hardening:
            // Ignore retained "offline/unexpected_disconnect" hints right after reconnect.
            // Authoritative recovery is heartbeat ACK; stale retained LWT can otherwise
            // force unnecessary offline transitions although transport is already back.
            if (likely_stale_retain) {
                LOG_W(
                    TAG,
                    "[SAFETY-P5] Ignoring stale server OFFLINE hint right after reconnect "
                    "(reason=unexpected_disconnect, age_ms=" + String(since_connect_ms) + ")"
                );
                return;
            }
            LOG_W(TAG, String("[SAFETY-P5] Server OFFLINE (reason: ") + reason + ")");

            if (offlineModeManager.getOfflineRuleCount() > 0) {
                LOG_W(TAG, String("[SAFETY-P5] ") +
                      String(offlineModeManager.getOfflineRuleCount()) +
                      " offline rules — delegating to P4");
            } else {
                actuatorManager.setAllActuatorsToSafeState();
                LOG_W(TAG, "[SAFETY-P5] No offline rules — safe state immediately");
            }
            LOG_W(TAG, "[SAFETY-P4] disconnect notified (path=P5)");
            offlineModeManager.onDisconnect();

        } else if (strcmp(status, "online") == 0) {
            // SAFETY-P4 bridge for server-only restarts:
            // If broker transport stayed connected, onMqttConnectCallback() is not triggered.
            // Handle both relevant states explicitly:
            // - OFFLINE_ACTIVE: arm handover (RECONNECTING + epoch++)
            // - DISCONNECTED: cancel grace timer and return ONLINE
            //   (prevents false OFFLINE_ACTIVE transition when ONLINE hint arrives during grace)
            OfflineMode mode = offlineModeManager.getMode();
            if (mode == OfflineMode::OFFLINE_ACTIVE || mode == OfflineMode::DISCONNECTED) {
                offlineModeManager.onReconnect();
                if (mode == OfflineMode::OFFLINE_ACTIVE) {
                    LOG_I(TAG, "[SAFETY-P5] Server ONLINE hint received — P4 handover armed (waiting for authoritative heartbeat ACK)");
                } else {
                    LOG_I(TAG, "[SAFETY-P5] Server ONLINE hint received during grace period — timer cancelled");
                }
            } else {
                LOG_I(TAG, "[SAFETY-P5] Server ONLINE hint received — waiting for heartbeat ACK as authoritative recovery");
            }
        }
        return;
    }

    // ─── Heartbeat ACK ───────────────────────────────────────────────────────
    // Runs directly — only touches atomics and configManager (NVS). Safe from any core.
    String heartbeat_ack_topic = TopicBuilder::buildSystemHeartbeatAckTopic();
    if (topic == heartbeat_ack_topic) {
        LOG_D(TAG, "Heartbeat ACK received");

        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, payload);

        if (error) {
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] heartbeat ack rejected code=PARSE_ERROR err=") + String(error.c_str()));
            // #endregion
            LOG_W(TAG, "Heartbeat ACK parse error: " + String(error.c_str()));
            return;
        }

        if (!doc.containsKey("status")) {
            // #region agent log
            LOG_W(TAG, "[DBG5126ae] heartbeat ack rejected code=MISSING_ACK_STATUS");
            // #endregion
            offlineModeManager.onServerAckContractMismatch("MISSING_ACK_STATUS");
            LOG_W(TAG, "[SAFETY-P4] Heartbeat ACK missing status — reject (fail-closed)");
            return;
        }

        if (!doc.containsKey("handover_epoch")) {
            // #region agent log
            LOG_W(TAG, "[DBG5126ae] heartbeat ack rejected code=MISSING_HANDOVER_EPOCH");
            // #endregion
            offlineModeManager.onServerAckContractMismatch("MISSING_HANDOVER_EPOCH");
            LOG_W(TAG, "[SAFETY-P4] Heartbeat ACK missing handover_epoch — reject (fail-closed)");
            return;
        }

        JsonVariant epoch_variant = doc["handover_epoch"];
        if (!epoch_variant.is<uint32_t>()) {
            // #region agent log
            LOG_W(TAG, "[DBG5126ae] heartbeat ack rejected code=INVALID_HANDOVER_EPOCH_TYPE");
            // #endregion
            offlineModeManager.onServerAckContractMismatch("INVALID_HANDOVER_EPOCH_TYPE");
            LOG_W(TAG, "[SAFETY-P4] Heartbeat ACK with non-numeric handover_epoch — reject (fail-closed)");
            return;
        }

        uint32_t handover_epoch = epoch_variant.as<uint32_t>();
        if (handover_epoch == 0) {
            // #region agent log
            LOG_W(TAG, "[DBG5126ae] heartbeat ack rejected code=INVALID_HANDOVER_EPOCH");
            // #endregion
            offlineModeManager.onServerAckContractMismatch("INVALID_HANDOVER_EPOCH");
            LOG_W(TAG, "[SAFETY-P4] Heartbeat ACK with invalid handover_epoch=0 — reject (fail-closed)");
            return;
        }

        const char* reject_code = nullptr;
        if (!offlineModeManager.validateServerAckContract(handover_epoch, &reject_code)) {
            // #region agent log
            LOG_W(TAG, String("[DBG5126ae] heartbeat ack rejected code=") +
                       String(reject_code != nullptr ? reject_code : "ACK_CONTRACT_MISMATCH"));
            // #endregion
            offlineModeManager.onServerAckContractMismatch(reject_code != nullptr ? reject_code : "ACK_CONTRACT_MISMATCH");
            LOG_W(TAG, String("[SAFETY-P4] Heartbeat ACK contract mismatch — reject code=") +
                       String(reject_code != nullptr ? reject_code : "ACK_CONTRACT_MISMATCH"));
            return;
        }

        // Registration Gate: confirm only after full ACK contract validation.
        mqttClient.confirmRegistration();
        // #region agent log
        LOG_W(TAG, String("[DBG5126ae] heartbeat ack accepted epoch=") + String(handover_epoch) +
                   " ack_age_before_ms=" + String(
                       g_last_server_ack_ms.load() > 0
                           ? (millis() - g_last_server_ack_ms.load())
                           : 0UL));
        // #endregion
        // SAFETY-P1 Mechanism D: Track server ACK timestamp only for valid contract ACK.
        g_last_server_ack_ms.store(millis());
        offlineModeManager.onServerAckReceived(handover_epoch);  // SAFETY-P4
        if (g_server_timeout_triggered.load()) {
            g_server_timeout_triggered.store(false);
            uint32_t restore_count = g_ack_restore_transition_count.fetch_add(1) + 1;
            LOG_I(TAG, "[SAFETY-P1] Server ACK restored — normal operation resumed (reason_code=ACK_RESTORE_VALID, transition_count=" +
                       String(restore_count) + ")");
        } else {
            uint32_t guard_skip_count = g_ack_restore_guard_skip_count.fetch_add(1) + 1;
            LOG_D(TAG, "[SAFETY-P1] ACK restore guard: timeout not active (reason_code=ACK_RESTORE_GUARD_SKIP, guard_skip_count=" +
                       String(guard_skip_count) + ")");
        }

        IntentMetadata ack_metadata = extractIntentMetadataFromPayload(payload.c_str(), "hb_ack");
        const char* status = doc["status"] | "unknown";
        String ack_reason_code = doc["reason_code"] | "";
        String ack_revocation_source = doc["revocation_source"] | "";
        String ack_correlation_id = doc["correlation_id"] | "";
        bool ack_upstream_deleted = doc["upstream_deleted"] | false;
        bool ack_delete_intent = doc["delete_intent"] | false;
        if (ack_correlation_id.length() == 0 && strlen(ack_metadata.correlation_id) > 0) {
            ack_correlation_id = ack_metadata.correlation_id;
        }
        bool config_available = doc["config_available"] | false;
        unsigned long server_time = doc["server_time"] | 0;

        // NTP can still be pending during early boot; adopt authoritative server time
        // from heartbeat ACK to avoid prolonged ts=0 windows.
        if (server_time > 0 && !timeManager.isSynchronized()) {
            timeManager.syncFromAuthoritativeUnix(static_cast<time_t>(server_time), "heartbeat_ack");
        }

        LOG_D(TAG, "  Status: " + String(status) + ", Config available: " +
                  String(config_available ? "yes" : "no"));

        if (strcmp(status, "approved") == 0 || strcmp(status, "online") == 0) {
            time_t approval_ts = server_time > 0 ? (time_t)server_time : timeManager.getUnixTimestamp();
            const bool already_approved = configManager.isDeviceApproved();
            const time_t persisted_approval_ts = configManager.getApprovalTimestamp();
            bool should_persist_approval = !already_approved;

            if (!should_persist_approval) {
                const bool missing_persisted_ts = persisted_approval_ts <= 0;
                const bool refresh_due = approval_ts > persisted_approval_ts &&
                                         (approval_ts - persisted_approval_ts) >= APPROVAL_TS_PERSIST_INTERVAL_S;
                should_persist_approval = missing_persisted_ts || refresh_due;

                if (!should_persist_approval) {
                    const long next_refresh_in = static_cast<long>(APPROVAL_TS_PERSIST_INTERVAL_S) -
                                                 static_cast<long>(approval_ts - persisted_approval_ts);
                    LOG_D(TAG, "Approval ACK dedup at call-site: skip NVS write (persisted_ts=" +
                              String(static_cast<unsigned long>(persisted_approval_ts)) +
                              ", incoming_ts=" + String(static_cast<unsigned long>(approval_ts)) +
                              ", next_refresh_in_s=" + String(next_refresh_in > 0 ? next_refresh_in : 0) + ")");
                }
            }

            if (should_persist_approval) {
                configManager.setDeviceApproved(true, approval_ts);
            }

            if (isConfigPendingAfterResetState()) {
                // Do not evaluate pending-exit on every heartbeat ACK.
                // Pending-exit is evaluated on config_commit in config_update_queue, where
                // configuration changes actually happen. This keeps MQTT callback load low.
                LOG_D(TAG, "[CONFIG] Pending-exit check deferred (trigger=heartbeat_ack, reason=AWAITING_CONFIG_COMMIT)");
                return;
            }

            if (g_system_config.current_state == STATE_PENDING_APPROVAL ||
                g_system_config.current_state == STATE_ERROR) {
                LOG_I(TAG, "╔════════════════════════════════════════╗");
                LOG_I(TAG, "║   DEVICE APPROVED BY SERVER            ║");
                LOG_I(TAG, "╚════════════════════════════════════════╝");
                if (g_system_config.current_state == STATE_ERROR) {
                    LOG_W(TAG, "Recovering from ERROR state after valid approval ACK");
                }
                LOG_I(TAG, "Transitioning to OPERATIONAL");

                g_system_config.current_state = STATE_OPERATIONAL;
                g_system_config.safe_mode_reason = "";
                configManager.saveSystemConfig(g_system_config);

                LOG_I(TAG, "  → Sensors/Actuators now ENABLED");
                LOG_I(TAG, "  → Full operational mode active");

                if (config_available) {
                    LOG_I(TAG, "  → Server has config available - awaiting config push");
                }
            }
        } else if (strcmp(status, "pending_approval") == 0) {
            configManager.setDeviceApproved(false, 0);
            if (isConfigPendingAfterResetState()) {
                // Same as approved/online branch: keep callback path lightweight and
                // avoid repeated pending-exit churn on periodic ACKs.
                LOG_D(TAG, "[CONFIG] Pending-exit check deferred (trigger=heartbeat_ack, status=pending_approval)");
                return;
            }
            if (g_system_config.current_state != STATE_PENDING_APPROVAL) {
                LOG_I(TAG, "Server reports: PENDING APPROVAL - entering limited mode");
                g_system_config.current_state = STATE_PENDING_APPROVAL;
            }
        } else if (strcmp(status, "rejected") == 0) {
            bool upstream_delete_reject = ack_upstream_deleted ||
                                          ack_delete_intent ||
                                          hasRevocationDeleteHint(ack_reason_code) ||
                                          hasRevocationDeleteHint(ack_revocation_source);
            LOG_W(TAG, "╔════════════════════════════════════════╗");
            LOG_W(TAG, "║   DEVICE REJECTED BY SERVER            ║");
            LOG_W(TAG, "╚════════════════════════════════════════╝");
            LOG_W(TAG, String("[ADMISSION] heartbeat_ack rejected: reason_code=") +
                       (ack_reason_code.length() > 0 ? ack_reason_code : "NONE") +
                       ", revocation_source=" +
                       (ack_revocation_source.length() > 0 ? ack_revocation_source : "NONE") +
                       ", upstream_deleted=" + String(ack_upstream_deleted ? "true" : "false") +
                       ", delete_intent=" + String(ack_delete_intent ? "true" : "false") +
                       ", intent_id=" + String(ack_metadata.intent_id) +
                       ", correlation_id=" +
                       (ack_correlation_id.length() > 0 ? ack_correlation_id : String("NONE")));

            String rejection_reason = upstream_delete_reject
                                          ? String("Heartbeat rejected via upstream delete/revocation path")
                                          : String("Heartbeat rejected by server administrator");
            rejection_reason += " (reason_code=" +
                                (ack_reason_code.length() > 0 ? ack_reason_code : String("NONE")) +
                                ", revocation_source=" +
                                (ack_revocation_source.length() > 0 ? ack_revocation_source : String("NONE")) +
                                ", correlation_id=" +
                                (ack_correlation_id.length() > 0 ? ack_correlation_id : String("NONE")) + ")";
            publishIntentOutcome("heartbeat",
                                 ack_metadata,
                                 "rejected",
                                 upstream_delete_reject ? "UPSTREAM_DELETE_REVOKED" : "HEARTBEAT_REJECTED",
                                 rejection_reason,
                                 false);

            errorTracker.trackError(ERROR_DEVICE_REJECTED, ERROR_SEVERITY_ERROR,
                                   rejection_reason.c_str());

            configManager.setDeviceApproved(false, 0);
            g_system_config.current_state = STATE_ERROR;
            configManager.saveSystemConfig(g_system_config);

            LOG_W(TAG, "  → Device in ERROR state");
            LOG_W(TAG, "  → Manual intervention required");
        } else if (strcmp(status, "error") == 0) {
            // SAFETY-P5 Fix-4: Error ACK — server alive, heartbeat had a problem
            // P1 timer was already reset above (unconditional). Only log the error.
            const char* error_msg = doc["error"] | "unknown";
            LOG_W(TAG, String("[HEARTBEAT] Server ACK with error: ") + error_msg);
            // P1 timer already reset — no action needed
        } else {
            LOG_D(TAG, "Unknown heartbeat ACK status: " + String(status));
        }
        return;
    }

    // ─── Unmatched topic ─────────────────────────────────────────────────────
    LOG_D(TAG, "No handler matched for topic: " + topic);
}

// ============================================
// SETUP - INITIALIZATION ORDER (Guide-konform)
// ============================================
void setup() {
  // ============================================
  // STEP 1: HARDWARE INITIALIZATION
  // ============================================
  Serial.begin(115200);

  // NOTE: Wokwi simulation needs longer delay for virtual UART initialization
  // On real hardware 100ms is sufficient, but Wokwi's virtual serial is slower
  #ifdef WOKWI_SIMULATION
  delay(500);  // Wokwi needs more time for UART
  Serial.println("[WOKWI] Serial initialized - simulation mode active");
  Serial.flush();  // Ensure output is sent before continuing
  delay(100);
  #elif defined(ESP32_S3_DEVKIT_MODE)
  // USB-CDC: nicht blockieren — Output auch wenn der Monitor erst spaeter geoeffnet wird
  Serial.setTxTimeoutMs(0);
  Serial.println("[BOOT] ESP32-S3 USB-CDC — oeffne Monitor auf COM8, 115200");
  Serial.flush();
  delay(300);
  #else
  delay(100);  // Allow Serial to stabilize on real hardware
  #endif

  // ============================================
  // STEP 2: BOOT BANNER (before Logger exists)
  // ============================================
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║  ESP32 Sensor Network v4.0 (Phase 2)  ║");
  Serial.println("╚════════════════════════════════════════╝");
  Serial.printf("Build: %s %s\n", __DATE__, __TIME__);
  Serial.printf("Chip Model: %s\n", ESP.getChipModel());
  Serial.printf("CPU Frequency: %d MHz\n", ESP.getCpuFreqMHz());
  Serial.printf("Free Heap: %d bytes\n\n", ESP.getFreeHeap());

  // ============================================
  // STEP 2.1: RTOS MUTEXES (MUST be before any configureSensor/Actuator calls)
  // ============================================
  // g_sensor_mutex / g_actuator_mutex are used in Phase 4/5 when loading NVS configs.
  // Creating them here (before Phase 1) prevents NULL-mutex assert crashes.
  initRtosMutexes();

  // ============================================
  // STEP 2.3: WATCHDOG CONFIGURATION (INDUSTRIAL-GRADE)
  // ============================================
  // Watchdog initialization is CONDITIONAL based on provisioning status
  // See STEP 6.5 below for conditional watchdog initialization
  //
  // NOTE: Skipped in Wokwi simulation because:
  // - esp_task_wdt_* functions may not be fully supported in Wokwi's virtual environment
  // - Watchdog behavior in simulation differs from real hardware
  // - Avoids potential early crash before any serial output
  #ifdef WOKWI_SIMULATION
  Serial.println("[WOKWI] Watchdog skipped (not supported in simulation)");
  g_watchdog_config.mode = WatchdogMode::WDT_DISABLED;
  #endif

  // ============================================
  // STEP 2.5: BOOT-BUTTON FACTORY RESET CHECK (Before GPIO init!)
  // ============================================
  // Check if Boot button (GPIO 0) is pressed for Factory Reset
  // This MUST be before gpioManager.initializeAllPinsToSafeMode()
  //
  // NOTE: Skipped in Wokwi simulation because:
  // - GPIO 0 is not connected to a physical button in diagram.json
  // - GPIO 0 may float LOW in simulation, triggering false factory resets
  // - Factory reset is not meaningful in CI/CD environment
  #ifndef WOKWI_SIMULATION
  const uint8_t BOOT_BUTTON_PIN = 0;  // GPIO 0 on ESP32
  const unsigned long HOLD_TIME_MS = 10000;  // 10 seconds

  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  delay(50);  // Strapping/Glitch abklingen lassen (besonders ESP32-S3)

  if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
    Serial.println("╔════════════════════════════════════════╗");
    Serial.println("║  ⚠️  BOOT BUTTON PRESSED              ║");
    Serial.println("║  Hold for 10 seconds for Factory Reset║");
    Serial.println("╚════════════════════════════════════════╝");

    unsigned long start_time = millis();
    bool held_for_10s = true;
    uint8_t last_second = 0;

    while (millis() - start_time < HOLD_TIME_MS) {
      if (digitalRead(BOOT_BUTTON_PIN) == HIGH) {
        held_for_10s = false;
        Serial.println("\nButton released - Factory Reset cancelled");
        break;
      }

      // Progress indicator (every second)
      uint8_t current_second = (millis() - start_time) / 1000;
      if (current_second > last_second) {
        Serial.print(".");
        last_second = current_second;
      }

      delay(100);
    }

    if (held_for_10s) {
      Serial.println("\n╔════════════════════════════════════════╗");
      Serial.println("║  🔥 FACTORY RESET TRIGGERED           ║");
      Serial.println("╚════════════════════════════════════════╝");

      // Initialize minimal systems for NVS access
      storageManager.begin();
      configManager.begin();

      // Clear WiFi config
      configManager.resetWiFiConfig();
      Serial.println("✅ WiFi configuration cleared");

      // Clear zone config
      KaiserZone kaiser;
      MasterZone master;
      configManager.saveZoneConfig(kaiser, master);
      Serial.println("✅ Zone configuration cleared");

      Serial.println("\n╔════════════════════════════════════════╗");
      Serial.println("║  ✅ FACTORY RESET COMPLETE            ║");
      Serial.println("╚════════════════════════════════════════╝");
      Serial.println("Rebooting in 2 seconds...");
      delay(2000);
      ESP.restart();
    }
  }
  #else
  // Wokwi simulation: Skip boot button check, log for debugging
  Serial.println("[WOKWI] Boot button check skipped (no physical button in simulation)");
  #endif // WOKWI_SIMULATION

  // ============================================
  // STEP 3: GPIO SAFE-MODE (CRITICAL - FIRST!)
  // ============================================
  // MUST be first to prevent hardware damage from undefined GPIO states
  gpioManager.initializeAllPinsToSafeMode();

  // ============================================
  // STEP 4: LOGGER (Foundation for all modules)
  // ============================================
  logger.begin();
  logger.setLogLevel(LOG_INFO);
  LOG_I(TAG, "Logger system initialized");

  // ============================================
  // STEP 5: STORAGE MANAGER (NVS access layer)
  // ============================================
  if (!storageManager.begin()) {
    LOG_E(TAG, "StorageManager initialization failed!");
    // Continue anyway (can work without persistence)
  }

  watchdogStorageInitEarly();

  // ============================================
  // STEP 5.1: RESTORE LOG LEVEL FROM NVS
  // ============================================
  // Log-Level persists across reboots (set via MQTT set_log_level command)
  if (storageManager.beginNamespace("system_config", true)) {
    uint8_t saved_level = storageManager.getUInt8("log_level", LOG_INFO);
    if (saved_level <= LOG_CRITICAL) {
      logger.setLogLevel((LogLevel)saved_level);
      // Use Serial.printf directly — LOG_INFO would be invisible if restored level > INFO
      Serial.printf("[NVS] Log level restored from NVS: %s\n", Logger::getLogLevelString((LogLevel)saved_level));
    }
    storageManager.endNamespace();
  }

  // ============================================
  // STEP 5.5: LittleFS (Spool-Backend für AUT-714)
  // ============================================
  if (!LittleFS.begin(true)) {
    ESP_LOGE("SETUP", "LittleFS mount failed — spool disabled");
    g_spool_enabled = false;
    spoolManager.setEnabled(false);
  } else {
    ESP_LOGI("SETUP", "LittleFS mounted, free: %lu KB",
             (unsigned long)(LittleFS.totalBytes() - LittleFS.usedBytes()) / 1024);
    g_spool_enabled = true;
    spoolManager.setEnabled(true);
    spoolManager.begin();
  }

  // ============================================
  // STEP 6: CONFIG MANAGER (Load configurations)
  // ============================================
  configManager.begin();
  if (!configManager.loadAllConfigs()) {
    LOG_W(TAG, "Some configurations failed to load - using defaults");
  }

  // Use cached values already loaded by loadAllConfigs() — avoid double NVS read
  g_wifi_config = configManager.getWiFiConfig();
  g_kaiser = configManager.getKaiser();
  g_master = configManager.getMasterZone();
  g_system_config = configManager.getSystemConfig();

  // ============================================
  // FIX: Use generated ESP ID when NVS read returns empty
  // In WOKWI mode, saveSystemConfig() is a no-op so the ESP ID
  // generated by generateESPIdIfMissing() never reaches NVS.
  // Fallback to the internal configManager state which already has it.
  // ============================================
  if (g_system_config.esp_id.length() == 0) {
    g_system_config.esp_id = configManager.getESPId();
    LOG_W(TAG, "ESP ID was empty after NVS load - using generated: " + g_system_config.esp_id);
  }

  configManager.printConfigurationStatus();

  // ═══════════════════════════════════════════════════════════════════════════
  // DEFENSIVE FIX: Detect and repair inconsistent state after provisioning
  // ═══════════════════════════════════════════════════════════════════════════
  // Problem: If STATE_SAFE_MODE_PROVISIONING is persisted but valid WiFi config
  // exists, ESP enters infinite reboot loop. This can happen if:
  //   1. Power loss during state transition
  //   2. Bug in provisioning flow (now fixed in provision_manager.cpp)
  //   3. Manual NVS manipulation
  //
  // Solution: If we have valid config but are in provisioning safe-mode,
  // reset state and attempt normal WiFi connection.
  // ═══════════════════════════════════════════════════════════════════════════
  if (g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING &&
      g_wifi_config.configured &&
      g_wifi_config.ssid.length() > 0) {
    LOG_W(TAG, "╔════════════════════════════════════════╗");
    LOG_W(TAG, "║  INCONSISTENT STATE DETECTED          ║");
    LOG_W(TAG, "╚════════════════════════════════════════╝");
    LOG_W(TAG, "State: STATE_SAFE_MODE_PROVISIONING but valid config exists");
    LOG_W(TAG, "SSID: " + g_wifi_config.ssid);
    LOG_W(TAG, "Repairing: Resetting state to STATE_BOOT");

    g_system_config.current_state = STATE_BOOT;
    g_system_config.safe_mode_reason = "";
    g_system_config.boot_count = 0;  // Reset boot counter to prevent false boot-loop detection
    bool repairPersisted = configManager.saveSystemConfig(g_system_config);
    if (!repairPersisted) {
      LOG_E(TAG, "State repair persist failed - switching to fail-closed provisioning mode");
      g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
      g_system_config.safe_mode_reason = "State repair persist failed";
      LOG_E(TAG, "Operator action required: Re-run provisioning after NVS/storage check");
      LOG_W(TAG, "State repair incomplete - continuing in STATE_SAFE_MODE_PROVISIONING");
    } else {
      LOG_I(TAG, "State repaired - proceeding with normal boot flow");
    }
  }

  // ═══════════════════════════════════════════════════
  // PHASE 2: BOOT-LOOP-DETECTION (Robustness + Overflow-Safe)
  // ═══════════════════════════════════════════════════
  // Calculate time since last boot (handles millis() overflow after 49.7 days)
  unsigned long now = millis();
  unsigned long time_since_last_boot = 0;

  if (g_system_config.last_boot_time > 0) {
    // Handle millis() overflow gracefully
    if (now >= g_system_config.last_boot_time) {
      time_since_last_boot = now - g_system_config.last_boot_time;
    } else {
      // Overflow occurred - treat as > 60s (boot is valid)
      time_since_last_boot = 60001;
    }
  } else {
    // First boot ever - treat as > 60s (boot is valid)
    time_since_last_boot = 60001;
  }

  // Increment boot counter and update timestamp
  g_system_config.boot_count++;
  g_system_config.last_boot_time = now;
  configManager.saveSystemConfig(g_system_config);

  LOG_I(TAG, "Boot count: " + String(g_system_config.boot_count) +
           " (last boot " + String(time_since_last_boot / 1000) + "s ago)");

  // Boot-Loop-Detection: 5 boots in <60s triggers Safe-Mode
  if (g_system_config.boot_count > 5 && time_since_last_boot < 60000) {
    LOG_C(TAG, "╔════════════════════════════════════════╗");
    LOG_C(TAG, "║  BOOT LOOP DETECTED - SAFE MODE       ║");
    LOG_C(TAG, "╚════════════════════════════════════════╝");
    LOG_C(TAG, "Booted " + String(g_system_config.boot_count) + " times in <60s");
    LOG_C(TAG, "System entering Safe-Mode (no WiFi/MQTT)");
    LOG_C(TAG, "Reset required to exit Safe-Mode");

    // Enter Safe-Mode: Disable WiFi/MQTT, only Serial log available
    g_system_config.current_state = STATE_SAFE_MODE;
    g_system_config.safe_mode_reason = "Boot loop detected (" + String(g_system_config.boot_count) + " boots)";
    configManager.saveSystemConfig(g_system_config);

    // Infinite loop - only watchdog can reset
    while(true) {
      delay(1000);
      LOG_W(TAG, "SAFE MODE - Boot count: " + String(g_system_config.boot_count));
    }
  }

  // ═══════════════════════════════════════════════════
  // STEP 6.5: CONDITIONAL WATCHDOG INITIALIZATION (Industrial-Grade)
  // ═══════════════════════════════════════════════════
  // Check if provisioning needed BEFORE watchdog init
  bool provisioning_needed = !g_wifi_config.configured ||
                             g_wifi_config.ssid.length() == 0;

  #ifndef WOKWI_SIMULATION
  if (provisioning_needed) {
    // PROVISIONING MODE WATCHDOG
    LOG_I(TAG, "╔════════════════════════════════════════╗");
    LOG_I(TAG, "║   PROVISIONING MODE WATCHDOG          ║");
    LOG_I(TAG, "╚════════════════════════════════════════╝");

    esp_task_wdt_init(300, false);  // 300s timeout, no panic
    esp_task_wdt_add(NULL);

    LOG_I(TAG, "✅ Watchdog: 300s timeout, error-log only");
    LOG_I(TAG, "   Feed requirement: Every 60s");
    LOG_I(TAG, "   Purpose: Detect firmware hangs during setup");
    LOG_I(TAG, "   Recovery: Manual reset button available");

    g_watchdog_config.mode = WatchdogMode::PROVISIONING;
    g_watchdog_config.timeout_ms = 300000;
    g_watchdog_config.feed_interval_ms = 60000;
    g_watchdog_config.panic_enabled = false;

  } else {
    // PRODUCTION MODE WATCHDOG
    LOG_I(TAG, "╔════════════════════════════════════════╗");
    LOG_I(TAG, "║   PRODUCTION MODE WATCHDOG            ║");
    LOG_I(TAG, "╚════════════════════════════════════════╝");

    esp_task_wdt_init(60, true);  // 60s timeout, panic=true
    esp_task_wdt_add(NULL);

    LOG_I(TAG, "✅ Watchdog: 60s timeout, auto-reboot enabled");
    LOG_I(TAG, "   Feed requirement: Every 10s");
    LOG_I(TAG, "   Purpose: Automatic recovery from firmware hangs");
    LOG_I(TAG, "   Recovery: Hard reset → clean boot");

    g_watchdog_config.mode = WatchdogMode::PRODUCTION;
    g_watchdog_config.timeout_ms = 60000;
    g_watchdog_config.feed_interval_ms = 10000;
    g_watchdog_config.panic_enabled = true;
  }
  #endif

  // Initialize watchdog diagnostics
  g_watchdog_diagnostics = WatchdogDiagnostics();
  g_watchdog_timeout_flag = false;

  // Check if last reboot was due to watchdog timeout
  if (esp_reset_reason() == ESP_RST_TASK_WDT) {
    LOG_W(TAG, "==============================================");
    LOG_W(TAG, "ESP REBOOTED DUE TO WATCHDOG TIMEOUT");
    LOG_W(TAG, "==============================================");

    watchdogStorageLogLastSnapshotIfAny();
    // Rolling 24h history + 3× threshold: finalized after NTP (watchdogStorageTryFinalizeBootRecord)
  }

  // ═══════════════════════════════════════════════════
  // STEP 6.6: PROVISIONING CHECK (Phase 6)
  // ═══════════════════════════════════════════════════
  // Check if ESP needs provisioning (no config or empty SSID)
  if (provisioning_needed) {
    LOG_I(TAG, "╔════════════════════════════════════════╗");
    LOG_I(TAG, "║   NO CONFIG - STARTING PROVISIONING   ║");
    LOG_I(TAG, "╚════════════════════════════════════════╝");
    LOG_I(TAG, "ESP is not provisioned. Starting AP-Mode...");

    // Initialize Provision Manager
    if (!provisionManager.begin()) {
      // ✅ FIX #3: CRITICAL FAILURE - Hardware Safe-Mode
      LOG_C(TAG, "╔════════════════════════════════════════╗");
      LOG_C(TAG, "║  ❌ PROVISION MANAGER INIT FAILED     ║");
      LOG_C(TAG, "╚════════════════════════════════════════╝");
      LOG_C(TAG, "ProvisionManager.begin() returned false");
      LOG_C(TAG, "Possible causes:");
      LOG_C(TAG, "  1. Storage/NVS initialization failed");
      LOG_C(TAG, "  2. Memory allocation failed");
      LOG_C(TAG, "  3. Hardware issue");
      LOG_C(TAG, "");
      LOG_C(TAG, "Entering HARDWARE SAFE-MODE (LED blink pattern)");
      LOG_C(TAG, "Action: Check hardware, flash firmware again");

      // ✅ Fallback: Continuous LED blink (industrial-grade feedback)
      pinMode(LED_PIN, OUTPUT);
      while (true) {
        // Blink pattern: 3× schnell (Error-Code)
        for (int i = 0; i < 3; i++) {
          digitalWrite(LED_PIN, HIGH);
          delay(200);
          digitalWrite(LED_PIN, LOW);
          delay(200);
        }
        delay(2000);  // Pause between patterns
      }
      // ❌ NIEMALS return - ESP bleibt im Safe-Mode sichtbar!
    }

    // Start AP-Mode
    if (provisionManager.startAPMode()) {
      LOG_I(TAG, "╔════════════════════════════════════════╗");
      LOG_I(TAG, "║  ACCESS POINT MODE ACTIVE             ║");
      LOG_I(TAG, "╚════════════════════════════════════════╝");
      LOG_I(TAG, "Connect to: AutoOne-" + g_system_config.esp_id);
      LOG_I(TAG, "Password: provision");
      LOG_I(TAG, "Open browser: http://192.168.4.1");
      LOG_I(TAG, "");
      LOG_I(TAG, "Waiting for configuration (timeout: 10 minutes)...");

      // Block until config received (or timeout: 10 minutes)
      if (provisionManager.waitForConfig(600000)) {
        // ✅ SUCCESS: Config received
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  ✅ PROVISIONING SUCCESSFUL           ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");
        LOG_I(TAG, "Configuration saved to NVS");
        LOG_I(TAG, "Rebooting in 2 seconds...");
        delay(2000);
        ESP.restart();  // Reboot to apply config
      } else {
        // ❌ TIMEOUT: No config received
        LOG_E(TAG, "╔════════════════════════════════════════╗");
        LOG_E(TAG, "║  ❌ PROVISIONING TIMEOUT              ║");
        LOG_E(TAG, "╚════════════════════════════════════════╝");
        LOG_E(TAG, "No configuration received within 10 minutes");
        LOG_E(TAG, "ESP will enter Safe-Mode with active Provisioning");
        LOG_E(TAG, "Please check:");
        LOG_E(TAG, "  1. WiFi connection to ESP AP");
        LOG_E(TAG, "  2. God-Kaiser server status");
        LOG_E(TAG, "  3. Network connectivity");

        // ✅ FIX #1: provision_manager.cpp hat bereits enterSafeMode() gecallt!
        // → STATE_SAFE_MODE_PROVISIONING ist gesetzt
        // → AP-Mode bleibt aktiv, HTTP-Server läuft weiter
        // → setup() darf NICHT abbrechen, damit loop() laufen kann
        LOG_I(TAG, "ProvisionManager.enterSafeMode() bereits ausgeführt");
        LOG_I(TAG, "State: STATE_SAFE_MODE_PROVISIONING");
        LOG_I(TAG, "AP-Mode bleibt aktiv - Warte auf Konfiguration...");

        // ✅ setup() läuft weiter OHNE WiFi/MQTT zu initialisieren
        // → loop() wird STATE_SAFE_MODE_PROVISIONING behandeln
      }
    } else {
      // ✅ FIX #4: CRITICAL FAILURE - Hardware Safe-Mode
      LOG_C(TAG, "╔════════════════════════════════════════╗");
      LOG_C(TAG, "║  ❌ AP-MODE START FAILED              ║");
      LOG_C(TAG, "╚════════════════════════════════════════╝");
      LOG_C(TAG, "ProvisionManager.startAPMode() returned false");
      LOG_C(TAG, "Possible causes:");
      LOG_C(TAG, "  1. WiFi hardware initialization failed");
      LOG_C(TAG, "  2. AP configuration invalid");
      LOG_C(TAG, "  3. Memory allocation failed");
      LOG_C(TAG, "  4. Hardware issue (WiFi chip)");
      LOG_C(TAG, "");
      LOG_C(TAG, "Entering HARDWARE SAFE-MODE (LED blink pattern)");
      LOG_C(TAG, "Action: Check hardware, flash firmware again");

      // ✅ Fallback: Continuous LED blink (industrial-grade feedback)
      pinMode(LED_PIN, OUTPUT);
      while (true) {
        // Blink pattern: 4× schnell (Error-Code für AP-Mode-Fehler)
        for (int i = 0; i < 4; i++) {
          digitalWrite(LED_PIN, HIGH);
          delay(200);
          digitalWrite(LED_PIN, LOW);
          delay(200);
        }
        delay(2000);  // Pause between patterns
      }
      // ❌ NIEMALS return - ESP bleibt im Safe-Mode sichtbar!
    }
  }

  // ═══════════════════════════════════════════════════
  // NORMAL FLOW: Config vorhanden
  // ═══════════════════════════════════════════════════

  // ✅ FIX #1: Skip WiFi/MQTT initialization when in provisioning safe-mode
  if (g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING) {
    LOG_I(TAG, "╔════════════════════════════════════════╗");
    LOG_I(TAG, "║  STATE_SAFE_MODE_PROVISIONING         ║");
    LOG_I(TAG, "╚════════════════════════════════════════╝");
    LOG_I(TAG, "Skipping WiFi/MQTT initialization");
    LOG_I(TAG, "AP-Mode bleibt aktiv - HTTP-Server läuft");
    LOG_I(TAG, "Warte auf Konfiguration via Provisioning-API...");
    LOG_I(TAG, "setup() abgeschlossen - loop() wird provisionManager.loop() ausführen");
    return;  // ✅ ERLAUBT: setup() endet, aber loop() wird aufgerufen!
  }

  LOG_I(TAG, "Configuration found - starting normal flow");

  // ============================================
  // STEP 7: ERROR TRACKER (Error history)
  // ============================================
  errorTracker.begin();

  // ============================================
  // STEP 8: TOPIC BUILDER (MQTT topics)
  // ============================================
  TopicBuilder::setEspId(g_system_config.esp_id.c_str());
  TopicBuilder::setKaiserId(g_kaiser.kaiser_id.c_str());

  LOG_I(TAG, "TopicBuilder configured with ESP ID: " + g_system_config.esp_id);

  // ============================================
  // STEP 9: PHASE 1 COMPLETE
  // ============================================
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 1: Core Infrastructure READY  ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Modules Initialized:");
  LOG_I(TAG, "  ✅ GPIO Manager (Safe-Mode)");
  LOG_I(TAG, "  ✅ Logger System");
  LOG_I(TAG, "  ✅ Storage Manager");
  LOG_I(TAG, "  ✅ Config Manager");
  LOG_I(TAG, "  ✅ Error Tracker");
  LOG_I(TAG, "  ✅ Topic Builder");

  // Print memory stats
  LOG_I(TAG, "=== Memory Status (Phase 1) ===");
  LOG_I(TAG, "Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
  LOG_I(TAG, "Min Free Heap: " + String(ESP.getMinFreeHeap()) + " bytes");
  LOG_I(TAG, "Heap Size: " + String(ESP.getHeapSize()) + " bytes");
  LOG_I(TAG, "=====================");

  // ============================================
  // STEP 10: PHASE 2 - COMMUNICATION LAYER (with Circuit Breaker - Phase 6+)
  // ============================================
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 2: Communication Layer         ║");
  LOG_I(TAG, "║   (with Circuit Breaker Protection)    ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  // WiFi Manager (Circuit Breaker: 10 failures → 60s timeout)
  if (!wifiManager.begin()) {
    LOG_E(TAG, "WiFiManager initialization failed!");
    return;
  }

  WiFiConfig wifi_config = configManager.getWiFiConfig();
  if (!wifiManager.connect(wifi_config)) {
    LOG_E(TAG, "WiFi connection failed");

    bool has_valid_local_config = hasValidLocalAutonomyConfig();
    if (has_valid_local_config) {
      g_boot_force_offline_autonomy = true;
      g_system_config.current_state = STATE_OPERATIONAL;
      g_system_config.safe_mode_reason = "Booted in local offline autonomy (WiFi unavailable)";
      configManager.saveSystemConfig(g_system_config);
      LOG_W(TAG, "[BOOT] WiFi unavailable, local config valid -> continue with offline autonomy runtime");
    } else {
      PortalDecisionContext decision_context;
      decision_context.portal_already_open = portal_open_due_to_disconnect_;
      decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
      decision_context.has_valid_local_autonomy_config = has_valid_local_config;
      const char* decision_code = nullptr;
      if (!mayOpenPortal(PortalOpenReason::WIFI_CONNECT_FAILURE, decision_context, &decision_code)) {
        LOG_W(TAG, String("[PORTAL] WiFi-failure portal blocked (code=") +
                   String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
        g_system_config.current_state = STATE_OPERATIONAL;
        g_system_config.safe_mode_reason = "Portal blocked by authority guard";
        configManager.saveSystemConfig(g_system_config);
        g_boot_force_offline_autonomy = true;
        LOG_W(TAG, "[BOOT] Falling back to local offline autonomy due to portal block");
      } else {

      // ═══════════════════════════════════════════════════
      // NEW: WiFi failure triggers Provisioning Portal
      // ═══════════════════════════════════════════════════
      LOG_C(TAG, "╔════════════════════════════════════════╗");
      LOG_C(TAG, "║  WIFI CONNECTION FAILED               ║");
      LOG_C(TAG, "║  Opening Provisioning Portal...       ║");
      LOG_C(TAG, "╚════════════════════════════════════════╝");

      // Update system state
      g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
      g_system_config.safe_mode_reason = "WiFi connection to '" + wifi_config.ssid + "' failed";
      configManager.saveSystemConfig(g_system_config);

      // Initialize and start Provisioning Manager
      if (!provisionManager.begin()) {
        LOG_C(TAG, "ProvisionManager initialization failed!");
        // LED blink pattern for hardware failure
        pinMode(LED_PIN, OUTPUT);
        while (true) {
          for (int i = 0; i < 5; i++) {
            digitalWrite(LED_PIN, HIGH);
            delay(200);
            digitalWrite(LED_PIN, LOW);
            delay(200);
          }
          delay(2000);
        }
      }

      if (provisionManager.startAPMode()) {
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  PROVISIONING PORTAL ACTIVE           ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");
        LOG_I(TAG, "Connect to: AutoOne-" + g_system_config.esp_id);
        LOG_I(TAG, "Password: provision");
        LOG_I(TAG, "Open browser: http://192.168.4.1");
        LOG_I(TAG, "");
        LOG_I(TAG, "Correct your WiFi credentials in the form.");
        LOG_I(TAG, "setup() complete - loop() will handle provisioning");
        return;  // Exit setup() early - loop() will handle provisioning
      } else {
        LOG_C(TAG, "Failed to start AP Mode!");
        // LED blink pattern for AP failure
        pinMode(LED_PIN, OUTPUT);
        while (true) {
          for (int i = 0; i < 4; i++) {
            digitalWrite(LED_PIN, HIGH);
            delay(200);
            digitalWrite(LED_PIN, LOW);
            delay(200);
          }
          delay(2000);
        }
      }
      }
    }
  } else {
    LOG_I(TAG, "WiFi connected successfully");
  }

  // MQTT Client (Circuit Breaker: 5 failures → 30s timeout)
  if (!mqttClient.begin()) {
    LOG_E(TAG, "MQTTClient initialization failed!");
    return;
  }

  // SAFETY-RTOS M3: Publish queue MUST exist before MQTT_EVENT_CONNECTED / on_connect.
  // Previously init ran after Phase 5; early connect callback could publish from Core 1
  // before g_publish_queue existed (drops + spurious CircuitBreaker failure).
  initPublishQueue();

  // SAFETY-P1 Mechanism A: Register connect callback before first connect
  mqttClient.setOnConnectCallback(onMqttConnectCallback);

  MQTTConfig mqtt_config;
  mqtt_config.server = wifi_config.server_address;
  mqtt_config.port = wifi_config.mqtt_port;
  mqtt_config.client_id = configManager.getESPId();
  mqtt_config.username = wifi_config.mqtt_username;  // Can be empty (Anonymous)
  mqtt_config.password = wifi_config.mqtt_password;  // Can be empty (Anonymous)
  // AUT-539 Fix 3: 90s -> 60s. FritzBox-NAT-Timeout typ. 300s.
  // k=60 -> 5 PINGREQ/5min Marge; k=90 wuerde nur 3 erlauben.
  mqtt_config.keepalive = 60;
  mqtt_config.timeout = 10;

  if (!mqttClient.connect(mqtt_config)) {
    LOG_E(TAG, "MQTT connection failed");

    bool has_valid_local_config = hasValidLocalAutonomyConfig();
    if (has_valid_local_config) {
      g_boot_force_offline_autonomy = true;
      g_system_config.current_state = STATE_OPERATIONAL;
      g_system_config.safe_mode_reason = "Booted in local offline autonomy (MQTT unavailable)";
      configManager.saveSystemConfig(g_system_config);
      LOG_W(TAG, "[BOOT] MQTT unavailable, local config valid -> continue with offline autonomy runtime");
    } else {
      PortalDecisionContext decision_context;
      decision_context.portal_already_open = portal_open_due_to_disconnect_;
      decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
      decision_context.has_valid_local_autonomy_config = has_valid_local_config;
      const char* decision_code = nullptr;
      if (!mayOpenPortal(PortalOpenReason::MQTT_CONNECT_FAILURE, decision_context, &decision_code)) {
        LOG_W(TAG, String("[PORTAL] MQTT-failure portal blocked (code=") +
                   String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
        g_system_config.current_state = STATE_OPERATIONAL;
        g_system_config.safe_mode_reason = "Portal blocked by authority guard";
        configManager.saveSystemConfig(g_system_config);
        g_boot_force_offline_autonomy = true;
        LOG_W(TAG, "[BOOT] Falling back to local offline autonomy due to portal block");
      } else {

      // ═══════════════════════════════════════════════════
      // MQTT FAILURE → PROVISIONING PORTAL RECOVERY
      // ═══════════════════════════════════════════════════
      // Same pattern as WiFi failure recovery (see STEP 10 above).
      // If MQTT broker is unreachable, the server IP or MQTT port
      // in the user's config is likely wrong. Re-open the portal
      // so the user can correct the configuration.
      LOG_C(TAG, "╔════════════════════════════════════════╗");
      LOG_C(TAG, "║  MQTT CONNECTION FAILED                ║");
      LOG_C(TAG, "║  Opening Provisioning Portal...        ║");
      LOG_C(TAG, "╚════════════════════════════════════════╝");
      LOG_C(TAG, "Server: " + mqtt_config.server + ":" + String(mqtt_config.port));
      LOG_C(TAG, "Possible causes:");
      LOG_C(TAG, "  1. Wrong MQTT port in configuration");
      LOG_C(TAG, "  2. Server IP not reachable");
      LOG_C(TAG, "  3. MQTT broker not running");

      // Update system state
      g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
      g_system_config.safe_mode_reason = "MQTT connection to '" + mqtt_config.server +
                                         ":" + String(mqtt_config.port) + "' failed";
      configManager.saveSystemConfig(g_system_config);

      // Config NICHT loeschen — Portal mit vorausgefuellter Config oeffnen
      portal_open_due_to_disconnect_ = true;

      // Initialize and start Provisioning Manager
      if (!provisionManager.begin()) {
        LOG_C(TAG, "ProvisionManager initialization failed!");
        pinMode(LED_PIN, OUTPUT);
        while (true) {
          for (int i = 0; i < 6; i++) {  // 6x blink = MQTT failure code
            digitalWrite(LED_PIN, HIGH);
            delay(200);
            digitalWrite(LED_PIN, LOW);
            delay(200);
          }
          delay(2000);
        }
      }

      if (provisionManager.startAPModeForReconfig()) {
        LOG_I(TAG, "╔════════════════════════════════════════╗");
        LOG_I(TAG, "║  PROVISIONING PORTAL ACTIVE            ║");
        LOG_I(TAG, "║  Config vorausgefuellt, Reconnect OK   ║");
        LOG_I(TAG, "╚════════════════════════════════════════╝");
        LOG_I(TAG, "Connect to: AutoOne-" + g_system_config.esp_id);
        LOG_I(TAG, "Password: provision");
        LOG_I(TAG, "Open browser: http://192.168.4.1");
        LOG_I(TAG, "Correct Server IP / MQTT Port if needed. Reconnect laeuft im Hintergrund.");
        return;  // Exit setup() early - loop() will handle provisioning + reconnect
      } else {
        LOG_C(TAG, "Failed to start AP+STA Mode after MQTT failure!");
        pinMode(LED_PIN, OUTPUT);
        while (true) {
          for (int i = 0; i < 4; i++) {
            digitalWrite(LED_PIN, HIGH);
            delay(200);
            digitalWrite(LED_PIN, LOW);
            delay(200);
          }
          delay(2000);
        }
      }
      }
    }
  } else {
#ifndef MQTT_USE_PUBSUBCLIENT
    LOG_I(TAG, "MQTT client started — broker connect runs in background (non-blocking)");
#else
    LOG_I(TAG, "MQTT connected successfully");
#endif

    // ============================================
    // ENABLE ERRORTRACKER MQTT PUBLISHING (Observability)
    // ============================================
    // Now that MQTT is connected, enable error publishing to server
    errorTracker.setMqttPublishCallback(errorTrackerMqttCallback, g_system_config.esp_id);
    LOG_I(TAG, "ErrorTracker MQTT publishing enabled");

    // Phase 7: Heartbeat is now sent in onMqttConnectCallback() (Mechanism F) — AFTER MQTT
    // is connected. In the ESP-IDF non-blocking path, calling publishHeartbeat() here fires
    // before MQTT_EVENT_CONNECTED and gets silently dropped (QoS-0 dropped when not connected).
    LOG_I(TAG, "MQTT connected — heartbeat will be sent via on_connect callback (Mechanism F)");

    // SAFETY-P1 Mechanism A: Subscriptions handled by onMqttConnectCallback (already called during connect)
    LOG_I(TAG, "MQTT subscriptions established via on_connect_callback");

    // PubSubClient path only — ESP-IDF: routeIncomingMessage() in mqtt_event_handler (Core 0).
#ifdef MQTT_USE_PUBSUBCLIENT
    mqttClient.setCallback([](const String& t, const String& p) {
      routeIncomingMessage(t.c_str(), p.c_str());
    });
#endif

    // ============================================
    // PHASE 1E: INITIAL APPROVAL CHECK
    // ============================================
    // After MQTT subscriptions are complete, check if device is approved.
    // If not approved → enter PENDING_APPROVAL state (limited operation)
    // If approved → continue to OPERATIONAL state (normal operation)
    if (!configManager.isDeviceApproved()) {
      // New device or not yet approved → Limited operation mode
      g_system_config.current_state = STATE_PENDING_APPROVAL;
      LOG_I(TAG, "Device not yet approved - entering PENDING_APPROVAL state");
      LOG_I(TAG, "  → WiFi/MQTT active (heartbeats + diagnostics)");
      LOG_I(TAG, "  → Sensors/Actuators DISABLED until approval");
    } else {
      // Previously approved → Normal operation
      g_system_config.current_state = STATE_OPERATIONAL;
      LOG_I(TAG, "Device previously approved - continuing normal operation");
    }
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 2: Communication Layer READY  ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Modules Initialized:");
  LOG_I(TAG, "  ✅ WiFi Manager");
  LOG_I(TAG, "  ✅ MQTT Client");
  LOG_I(TAG, "");

  // Print memory stats
  LOG_I(TAG, "=== Memory Status (Phase 2) ===");
  LOG_I(TAG, "Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
  LOG_I(TAG, "Min Free Heap: " + String(ESP.getMinFreeHeap()) + " bytes");
  LOG_I(TAG, "Heap Size: " + String(ESP.getHeapSize()) + " bytes");
  LOG_I(TAG, "=====================");

  // ============================================
  // STEP 10.5: PHASE 7 - HEALTH MONITOR
  // ============================================
  if (!healthMonitor.begin()) {
    LOG_E(TAG, "HealthMonitor initialization failed!");
    errorTracker.trackError(ERROR_SYSTEM_INIT_FAILED, ERROR_SEVERITY_ERROR,
                           "HealthMonitor begin() failed");
  } else {
    LOG_I(TAG, "Health Monitor initialized");
    healthMonitor.setPublishInterval(60000);  // 60 seconds
    healthMonitor.setChangeDetectionEnabled(true);
  }

  // ============================================
  // STEP 11: PHASE 3 - HARDWARE ABSTRACTION LAYER
  // ============================================
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 3: Hardware Abstraction Layer  ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  // I2C Bus Manager
  if (!i2cBusManager.begin()) {
    LOG_E(TAG, "I2C Bus Manager initialization failed!");
    errorTracker.trackError(ERROR_I2C_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "I2C begin() failed");
  } else {
    LOG_I(TAG, "I2C Bus Manager initialized");
  }

  // OneWire Bus Manager — lazy init (on-demand when DS18B20 sensor is configured)
  // SensorManager.configureSensor() calls oneWireBusManager.begin(gpio) when needed.
  // Skipping unconditional init avoids reserving GPIO 4 on non-OneWire ESPs.
  LOG_I(TAG, "OneWire Bus Manager: deferred (on-demand init)");

  // PWM Controller
  if (!pwmController.begin()) {
    LOG_E(TAG, "PWM Controller initialization failed!");
    errorTracker.trackError(ERROR_PWM_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "PWM begin() failed");
  } else {
    LOG_I(TAG, "PWM Controller initialized");
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 3: Hardware Abstraction READY  ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Modules Initialized:");
  LOG_I(TAG, "  ✅ I2C Bus Manager");
  LOG_I(TAG, "  ⏳ OneWire Bus Manager (on-demand)");
  LOG_I(TAG, "  ✅ PWM Controller");
  LOG_I(TAG, "");

  // Print memory stats
  LOG_I(TAG, "=== Memory Status (Phase 3) ===");
  LOG_I(TAG, "Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
  LOG_I(TAG, "Min Free Heap: " + String(ESP.getMinFreeHeap()) + " bytes");
  LOG_I(TAG, "Heap Size: " + String(ESP.getHeapSize()) + " bytes");
  LOG_I(TAG, "=====================");

  // ============================================
  // STEP 12: PHASE 4 - SENSOR SYSTEM
  // ============================================
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 4: Sensor System               ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  uint8_t runtime_sensor_count = 0;
  uint8_t runtime_actuator_count = 0;

  // Sensor Manager
  if (!sensorManager.begin()) {
    LOG_E(TAG, "Sensor Manager initialization failed!");
    errorTracker.trackError(ERROR_SENSOR_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "SensorManager begin() failed");
  } else {
    LOG_I(TAG, "Sensor Manager initialized");

    // Phase 2: Configure measurement interval (5 seconds)
    sensorManager.setMeasurementInterval(5000);

    // Load sensor configs from NVS
    SensorConfig sensors[10];
    uint8_t loaded_count = 0;
    if (configManager.loadSensorConfig(sensors, 10, loaded_count)) {
      runtime_sensor_count = loaded_count;
      LOG_I(TAG, "Loaded " + String(loaded_count) + " sensor configs from NVS");
      for (uint8_t i = 0; i < loaded_count; i++) {
        sensorManager.configureSensor(sensors[i]);
      }
    }
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 4: Sensor System READY         ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Modules Initialized:");
  LOG_I(TAG, "  ✅ Sensor Manager");
  LOG_I(TAG, "");

  // Print memory stats
  LOG_I(TAG, "=== Memory Status (Phase 4) ===");
  LOG_I(TAG, "Free Heap: " + String(ESP.getFreeHeap()) + " bytes");
  LOG_I(TAG, "Min Free Heap: " + String(ESP.getMinFreeHeap()) + " bytes");
  LOG_I(TAG, "Heap Size: " + String(ESP.getHeapSize()) + " bytes");
  LOG_I(TAG, "=====================");

  // ============================================
  // STEP 13: PHASE 5 - ACTUATOR SYSTEM
  // ============================================
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 5: Actuator System            ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  if (!safetyController.begin()) {
    LOG_E(TAG, "Safety Controller initialization failed!");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_CRITICAL,
                            "SafetyController begin() failed");
  } else {
    LOG_I(TAG, "Safety Controller initialized");
  }

  if (!actuatorManager.begin()) {
    LOG_E(TAG, "Actuator Manager initialization failed!");
    errorTracker.trackError(ERROR_ACTUATOR_INIT_FAILED,
                            ERROR_SEVERITY_CRITICAL,
                            "ActuatorManager begin() failed");
  } else {
    LOG_I(TAG, "Actuator Manager initialized");

    // Load actuator configs from NVS (analog to sensor loading above)
    ActuatorConfig actuators[MAX_ACTUATORS];
    uint8_t loaded_actuator_count = 0;
    if (configManager.loadActuatorConfig(actuators, MAX_ACTUATORS, loaded_actuator_count)) {
      runtime_actuator_count = loaded_actuator_count;
      LOG_I(TAG, "Loaded " + String(loaded_actuator_count) + " actuator configs from NVS");
      for (uint8_t i = 0; i < loaded_actuator_count; i++) {
        actuatorManager.configureActuator(actuators[i]);
      }
    } else {
      LOG_I(TAG, "No actuator configs in NVS");
    }
  }

  // SAFETY-P4: Load persisted offline rules from NVS
  offlineModeManager.loadOfflineRulesFromNVS();
  uint8_t offline_rule_count = offlineModeManager.getOfflineRuleCount();
  bool runtime_has_any_config =
      (runtime_sensor_count > 0) || (runtime_actuator_count > 0) || (offline_rule_count > 0);
  RuntimeReadinessSnapshot boot_snapshot{
      runtime_sensor_count,
      runtime_actuator_count,
      offline_rule_count
  };
  RuntimeReadinessDecision boot_readiness =
      evaluateRuntimeReadiness(boot_snapshot, defaultRuntimeReadinessPolicy());
  bool runtime_complete = boot_readiness.ready;
  // AUT-59: Log when orphaned offline rules trigger auto-exit instead of pending dead-end
  if (runtime_complete && offline_rule_count > 0 && runtime_actuator_count == 0) {
    LOG_W(TAG, String("[BOOT] AUT-59: Orphaned offline rules (count=") +
               String(offline_rule_count) + ", actuators=0) — auto-exit, rules are inert");
  }
  if (runtime_has_any_config && !runtime_complete &&
      g_system_config.current_state != STATE_SAFE_MODE &&
      g_system_config.current_state != STATE_SAFE_MODE_PROVISIONING &&
      g_system_config.current_state != STATE_ERROR) {
    SystemState before_state = g_system_config.current_state;
    LOG_W(TAG, String("[BOOT] Runtime config partial after reset: sensors=") + String(runtime_sensor_count) +
               ", actuators=" + String(runtime_actuator_count) +
               ", offline_rules=" + String(offline_rule_count) +
               ", policy_decision=" + String(boot_readiness.decision_code));
    g_system_config.current_state = STATE_CONFIG_PENDING_AFTER_RESET;
    g_system_config.safe_mode_reason = "CONFIG_PENDING_AFTER_RESET";
    configManager.saveSystemConfig(g_system_config);
    g_config_pending_enter_count.fetch_add(1);
    publishConfigPendingTransitionEvent("entered_config_pending",
                                        "CONFIG_PENDING_AFTER_RESET",
                                        boot_readiness,
                                        before_state,
                                        STATE_CONFIG_PENDING_AFTER_RESET,
                                        "boot_runtime_partial");
  }
  if (g_boot_force_offline_autonomy) {
    LOG_W(TAG, "[BOOT] Entering local offline autonomy at startup (network unavailable)");
    offlineModeManager.onDisconnect();
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║   Phase 5: Actuator System READY      ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  // ============================================
  // SAFETY-RTOS M4: Config-Queue (BEFORE tasks; mutexes already created in STEP 2.1)
  // ============================================
  if (g_config_lane_mutex == nullptr) {
    g_config_lane_mutex = xSemaphoreCreateMutex();
    if (g_config_lane_mutex == nullptr) {
      LOG_C(TAG, "[SYNC] Failed to create config lane mutex");
    }
  }
  initConfigUpdateQueue(); // Core 0→1 config push queue (5 slots × 2049 B ≈ 10 KB)

  // ============================================
  // SAFETY-RTOS M1+M3: Queues + Tasks
  // ============================================
  // Queues MUST be created before tasks — tasks read from queues immediately on start.
  initActuatorCommandQueue();
  initSensorCommandQueue();
  // initPublishQueue: moved to Phase 2 (immediately after mqttClient.begin)

  bool safety_task_created = createSafetyTask();   // Core 1, Priority 5 — Safety/Sensor/Actuator
  if (safety_task_created) {
    // Deregister Arduino loopTask from WDT — Safety-Task takes over WDT feeding
    #ifndef WOKWI_SIMULATION
    esp_task_wdt_delete(xTaskGetCurrentTaskHandle());
    #endif
    LOG_I(TAG, "[SAFETY-RTOS M1] Safety task created, loopTask deregistered from WDT");
  } else {
    LOG_C(TAG, "[SAFETY-RTOS M1] Safety task creation failed — keeping loopTask on WDT");
  }

  bool comm_task_created = createCommunicationTask();  // M3: Core 0, Priority 3 — WiFi/MQTT/Portal/Timers
  g_safety_rtos_tasks_created = safety_task_created && comm_task_created;
  if (comm_task_created) {
    LOG_I(TAG, "[SAFETY-RTOS M3] Communication task created on Core 0");
  } else {
    LOG_C(TAG, "[SAFETY-RTOS M3] Communication task creation failed — staying in legacy loop fallback");
  }

  // === DIAGNOSTIK: System State nach Setup ===
  LOG_I(TAG, "=== POST-SETUP DIAGNOSTICS ===");
  LOG_I(TAG, "System State: " + String(g_system_config.current_state));
  LOG_I(TAG, "Critical Errors: " + String(errorTracker.hasCriticalErrors() ? "YES" : "NO"));
  LOG_I(TAG, "WiFi CB State: " + String(static_cast<int>(wifiManager.getCircuitBreakerState())));
  LOG_I(TAG, "Active Sensors: " + String(sensorManager.getActiveSensorCount()));
  LOG_I(TAG, "==============================");
}

// ============================================
// WATCHDOG FUNCTIONS (Industrial-Grade)
// ============================================

/**
 * @brief Feed Watchdog mit Kontext und Circuit-Breaker-Check
 * @param component_id ID der Komponente (für Diagnostics)
 * @return true wenn Feed erfolgreich, false wenn blockiert
 */
bool feedWatchdog(const char* component_id) {
  // ─────────────────────────────────────────────────────
  // 1. Circuit Breaker Check (nur in Production Mode)
  // ─────────────────────────────────────────────────────
  if (g_watchdog_config.mode == WatchdogMode::PRODUCTION) {
    // ✅ FIX (2026-03-10): WiFi CB blockiert Watchdog NICHT mehr!
    // Root-Cause fuer Reboot-Loop: WiFi-Signal kurz weg → CB OPEN →
    // Watchdog-Feed blockiert → 60s WDT Timeout → Reboot → wieder WiFi weg → Loop.
    // Reboot hilft nicht bei schwachem Signal. WiFi CB regelt Reconnect bereits.
    if (wifiManager.getCircuitBreakerState() == CircuitState::OPEN) {
      static unsigned long last_wifi_cb_warning = 0;
      if (millis() - last_wifi_cb_warning > 10000) {
        last_wifi_cb_warning = millis();
        LOG_W(TAG, "WiFi Circuit Breaker OPEN - running in degraded mode");
      }
      // Continue with watchdog feed - don't block!
    }

    // MQTT Circuit Breaker OPEN?
    // ✅ FIX (2026-01-20): MQTT CB blockiert Watchdog NICHT mehr!
    // Grund: ESP kann lokal weiterarbeiten (Sensoren, Aktoren) auch wenn MQTT down ist.
    // MQTT-Ausfall ist "degraded mode", nicht "critical failure".
    // Nur WiFi CB bleibt kritisch (ohne WiFi kann ESP nichts tun).
    if (mqttClient.getCircuitBreakerState() == CircuitState::OPEN) {
      // Rate-limited warning (max once per 10 seconds)
      static unsigned long last_mqtt_cb_warning = 0;
      if (millis() - last_mqtt_cb_warning > 10000) {
        last_mqtt_cb_warning = millis();
        LOG_W(TAG, "MQTT Circuit Breaker OPEN - running in degraded mode");
      }
      // Continue with watchdog feed - don't block!
    }

    // Critical Errors?
    if (errorTracker.hasCriticalErrors()) {
      errorTracker.logApplicationError(
        ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL,
        "Watchdog feed blocked: Critical errors active"
      );
      return false;
    }

    // System State Check
    if (g_system_config.current_state == STATE_ERROR) {
      LOG_W(TAG, "Watchdog feed BLOCKED: System in STATE_ERROR");
      return false;  // Error-State → Watchdog-Feed blockiert
    }
  }

  // ─────────────────────────────────────────────────────
  // 2. Feed Watchdog
  // ─────────────────────────────────────────────────────
  #ifndef WOKWI_SIMULATION
  esp_task_wdt_reset();
  #endif

  // ─────────────────────────────────────────────────────
  // 3. Update Diagnostics
  // ─────────────────────────────────────────────────────
  g_watchdog_diagnostics.last_feed_time = millis();
  g_watchdog_diagnostics.last_feed_component = component_id;
  g_watchdog_diagnostics.feed_count++;

  return true;
}

/**
 * @brief Handle Watchdog Timeout (wird in loop() aufgerufen)
 */
void handleWatchdogTimeout() {
  if (!g_watchdog_timeout_flag) return;

  // ─────────────────────────────────────────────────────
  // 1. Track Critical Error
  // ─────────────────────────────────────────────────────
  errorTracker.trackError(
    ERROR_WATCHDOG_TIMEOUT,
    ERROR_SEVERITY_CRITICAL,
    "Watchdog timeout detected"
  );

  // ─────────────────────────────────────────────────────
  // 2. Sammle Diagnostic Info
  // ─────────────────────────────────────────────────────
  WatchdogDiagnostics diag;
  diag.timestamp = millis();
  diag.system_state = g_system_config.current_state;
  diag.last_feed_component = g_watchdog_diagnostics.last_feed_component;
  diag.last_feed_time = g_watchdog_diagnostics.last_feed_time;
  diag.wifi_breaker_state = wifiManager.getCircuitBreakerState();
  diag.mqtt_breaker_state = mqttClient.getCircuitBreakerState();
  diag.error_count = errorTracker.getErrorCount();
  diag.heap_free = ESP.getFreeHeap();

  // ─────────────────────────────────────────────────────
  // 3. Speichere in NVS (für Post-Reboot-Analyse)
  // ─────────────────────────────────────────────────────
  watchdogStorageSaveDiagnosticsSnapshot(diag);

  // ─────────────────────────────────────────────────────
  // 4. Health Snapshot (MQTT-Publish wenn möglich)
  // ─────────────────────────────────────────────────────
  if (mqttClient.isConnected()) {
    healthMonitor.publishSnapshot();
  }

  // ─────────────────────────────────────────────────────
  // 5. Mode-Specific Action
  // ─────────────────────────────────────────────────────
  if (g_watchdog_config.mode == WatchdogMode::PRODUCTION) {
    // Production: Panic wird automatisch triggern (panic=true)
    LOG_C(TAG, "Production Mode Watchdog Timeout → ESP will reset");
  } else {
    // Provisioning: Kein Panic, nur Log
    LOG_W(TAG, "Provisioning Mode Watchdog Timeout → Manual reset available");

    // Blinke LED als Signal
    for (int i = 0; i < 5; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(100);
      digitalWrite(LED_PIN, LOW);
      delay(100);
    }
  }

  g_watchdog_timeout_flag = false;
}

/**
 * @brief SAFETY-P1 Mechanism D: Check server ACK timeout and set actuators to safe state.
 *        Called from Safety-Task (core 1). Atomic read/write for cross-core safety.
 */
void checkServerAckTimeout() {
  if (mqttClient.isConnected() && g_last_server_ack_ms.load() > 0) {
    if (g_server_timeout_triggered.load()) {
      uint32_t guard_skip_count = g_ack_timeout_guard_skip_count.fetch_add(1) + 1;
      LOG_D(TAG, "[SAFETY-P1] ACK timeout guard: already timed out (reason_code=ACK_TIMEOUT_GUARD_ALREADY_TRIGGERED, guard_skip_count=" +
                 String(guard_skip_count) + ")");
      return;
    }

    if (millis() - g_last_server_ack_ms.load() > SERVER_ACK_TIMEOUT_MS) {
      g_server_timeout_triggered.store(true);
      uint32_t timeout_count = g_ack_timeout_transition_count.fetch_add(1) + 1;
      if (offlineModeManager.getOfflineRuleCount() > 0) {
        LOG_W(TAG, "[SAFETY-P1] Server ACK timeout (" + String(SERVER_ACK_TIMEOUT_MS / 1000) +
                   "s) — delegating to P4 (" +
                   String(offlineModeManager.getOfflineRuleCount()) +
                   " rules, reason_code=ACK_TIMEOUT_TO_P4, transition_count=" +
                   String(timeout_count) + ")");
      } else {
        if (actuatorManager.isInitialized()) {
          actuatorManager.setAllActuatorsToSafeState();
        }
        LOG_W(TAG, "[SAFETY-P1] Server ACK timeout (" + String(SERVER_ACK_TIMEOUT_MS / 1000) +
                   "s) — no offline rules, safe state immediately (reason_code=ACK_TIMEOUT_SAFE_STATE, transition_count=" +
                   String(timeout_count) + ")");
      }
      LOG_W(TAG, "[SAFETY-P4] disconnect notified (path=P1)");
      offlineModeManager.onDisconnect();  // ALWAYS — starts P4 state machine
    }
  }
}

/**
 * @brief Get Watchdog timeout count in last 24 hours
 * @return Anzahl der Watchdog-Timeouts in letzten 24h
 */
uint8_t getWatchdogCountLast24h() {
  return watchdogStorageGetCountLast24h();
}

// ============================================
// LOOP (SAFETY-RTOS M3)
// ============================================
// Nach vollem setup(): WiFi/MQTT/Timer/Publish-Queue laufen im Communication-Task (Core 0);
// Sensoren/Aktoren/Watchdog im Safety-Task (Core 1). loop() bleibt minimal.
//
// setup() kann VOR Erstellung der Tasks returnen (Provisioning, WiFi-/MQTT-Fehler ohne
// Sensor/Aktor-Init) — dann gibt es keinen Comm-Task; diese Legacy-Schleife uebernimmt
// Provisioning und ggf. MQTT-Reconnect wie frueher in loop().
// ============================================
static void loopLegacySingleThreadedWhenNoRtosTasks() {
  watchdogStorageTryFinalizeBootRecord();
  const bool safety_task_active = (g_safety_task_handle != NULL);

  static bool first_loop_logged = false;
  if (!first_loop_logged) {
    LOG_I(TAG, "=== FIRST LOOP ITERATION (legacy path, RTOS fallback) ===");
    LOG_W(TAG, "[SAFETY-RTOS] Legacy single-thread fallback active: core-isolation guarantees are NOT active");
    if (safety_task_active) {
      LOG_W(TAG, "[SAFETY-RTOS] Safety task is active while comm task is missing — legacy loop runs network/control-plane only");
    }
    LOG_I(TAG, "System State: " + String(g_system_config.current_state));
    LOG_I(TAG, "Critical Errors: " + String(errorTracker.hasCriticalErrors() ? "YES" : "NO"));
    first_loop_logged = true;
  }

  static uint32_t loop_count = 0;
  loop_count++;
  LOG_D(TAG, "LOOP[legacy " + String(loop_count) + "] START");

  handleWatchdogTimeout();
  LOG_D(TAG, "LOOP[legacy " + String(loop_count) + "] WATCHDOG_TIMEOUT_HANDLER OK");

  if (g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING) {
    provisionManager.loop();

    if (portal_open_due_to_disconnect_) {
      wifiManager.loop();
      mqttClient.loop();
#ifndef MQTT_USE_PUBSUBCLIENT
      mqttClient.processPublishQueue();
#endif

      if (mqttClient.isConnected() && mqttClient.isRegistrationConfirmed()) {
        LOG_I(TAG, "Reconnect erfolgreich — Portal wird geschlossen");
        provisionManager.stop();
        portal_open_due_to_disconnect_ = false;
        WiFi.mode(WIFI_STA);
        g_system_config.current_state = STATE_OPERATIONAL;
        g_system_config.safe_mode_reason = "";
        configManager.saveSystemConfig(g_system_config);
        delay(10);
        return;
      }
    }

    if (provisionManager.isConfigReceived()) {
      LOG_I(TAG, "╔════════════════════════════════════════╗");
      LOG_I(TAG, "║  ✅ KONFIGURATION EMPFANGEN!          ║");
      LOG_I(TAG, "╚════════════════════════════════════════╝");
      configManager.loadWiFiConfig(g_wifi_config);
      LOG_I(TAG, "WiFi SSID: " + g_wifi_config.ssid);
      LOG_I(TAG, "Rebooting to apply configuration...");
      delay(2000);
      ESP.restart();
    }

    delay(10);
    return;
  }

  if (g_system_config.current_state == STATE_PENDING_APPROVAL ||
      g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET) {
    wifiManager.loop();
    mqttClient.loop();
#ifndef MQTT_USE_PUBSUBCLIENT
    // Legacy fallback (no Comm-Task): still process config lane so CONFIG_PENDING can recover.
    // If Safety-Task is active, Core 1 already drains this queue.
    if (!safety_task_active) {
      processConfigUpdateQueue();
    }
    mqttClient.processPublishQueue();
#endif
    delay(100);
    return;
  }

  static bool boot_count_reset = false;
  if (!boot_count_reset && millis() > 60000 && g_system_config.boot_count > 1) {
    g_system_config.boot_count = 0;
    g_system_config.last_boot_time = 0;
    configManager.saveSystemConfig(g_system_config);
    boot_count_reset = true;
    LOG_I(TAG, "Boot counter reset - stable operation confirmed");
  }

  LOG_D(TAG, "LOOP[legacy " + String(loop_count) + "] WIFI_START");
  wifiManager.loop();
  LOG_D(TAG, "LOOP[legacy " + String(loop_count) + "] MQTT_START");
  mqttClient.loop();
#ifndef MQTT_USE_PUBSUBCLIENT
  mqttClient.processPublishQueue();
#endif
  // Legacy fallback: drain queues only in pure single-thread mode.
  // When Safety-Task exists but Comm-Task is missing, queue consumers run on Core 1.
  if (!safety_task_active) {
    processActuatorCommandQueue();
    processSensorCommandQueue();
    processConfigUpdateQueue();
  }

  {
    static const unsigned long PORTAL_OPEN_DEBOUNCE_MS = 30000;
    static unsigned long disconnect_start = 0;

    if (g_system_config.current_state == STATE_OPERATIONAL && !mqttClient.isConnected() && !WiFi.isConnected()) {
      if (disconnect_start == 0) {
        disconnect_start = millis();
      } else if (millis() - disconnect_start > PORTAL_OPEN_DEBOUNCE_MS &&
                 !portal_open_due_to_disconnect_) {
        PortalDecisionContext decision_context;
        decision_context.portal_already_open = portal_open_due_to_disconnect_;
        decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
        decision_context.has_valid_local_autonomy_config = false;
        const char* decision_code = nullptr;
        bool portal_allowed = mayOpenPortal(PortalOpenReason::DISCONNECT_DEBOUNCE, decision_context, &decision_code);
        if (!portal_allowed) {
          LOG_W(TAG, String("[PORTAL] legacy disconnect portal blocked (code=") +
                     String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
          disconnect_start = 0;
          // Keep running in operational degraded mode; no portal escalation.
        } else {
          LOG_I(TAG, "Config-Portal geoeffnet (Server getrennt), Reconnect laeuft im Hintergrund");
          g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
          g_system_config.safe_mode_reason = "MQTT disconnected (" + String(PORTAL_OPEN_DEBOUNCE_MS / 1000) + "s)";
          configManager.saveSystemConfig(g_system_config);
          if (provisionManager.startAPModeForReconfig()) {
            portal_open_due_to_disconnect_ = true;
          }
          disconnect_start = 0;
        }
      }
    } else {
      disconnect_start = 0;
    }
  }

  {
    static const unsigned long MQTT_PERSISTENT_FAILURE_TIMEOUT_MS = 300000;
    static unsigned long mqtt_failure_start = 0;

    if (!mqttClient.isConnected() && mqttClient.getCircuitBreakerState() == CircuitState::OPEN) {
      if (mqtt_failure_start == 0) {
        mqtt_failure_start = millis();
        LOG_W(TAG, "MQTT persistent failure timer started (5 min to recovery)");
      } else if (millis() - mqtt_failure_start > MQTT_PERSISTENT_FAILURE_TIMEOUT_MS) {
        if (WiFi.isConnected()) {  // AUT-678: STA still up — broker-only outage, skip Provisioning
          LOG_W(TAG, "MQTT persistent failure but STA up — skip Provisioning (AUT-678)");
          mqtt_failure_start = 0;
          return;
        }
        if (!portal_open_due_to_disconnect_) {
          PortalDecisionContext decision_context;
          decision_context.portal_already_open = portal_open_due_to_disconnect_;
          decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
          decision_context.has_valid_local_autonomy_config = false;
          const char* decision_code = nullptr;
          bool portal_allowed = mayOpenPortal(PortalOpenReason::MQTT_PERSISTENT_FAILURE, decision_context, &decision_code);
          if (!portal_allowed) {
            LOG_W(TAG, String("[PORTAL] legacy persistent-failure portal blocked (code=") +
                       String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
            mqtt_failure_start = 0;
            // Keep running in operational degraded mode; no portal escalation.
          } else {
            LOG_C(TAG, "╔════════════════════════════════════════╗");
            LOG_C(TAG, "║  MQTT PERSISTENT FAILURE (5 min)       ║");
            LOG_C(TAG, "║  Config-Portal oeffnen...              ║");
            LOG_C(TAG, "╚════════════════════════════════════════╝");
            g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
            g_system_config.safe_mode_reason = "MQTT persistent failure (5 min Circuit Breaker OPEN)";
            configManager.saveSystemConfig(g_system_config);
            if (!provisionManager.isInitialized() && !provisionManager.begin()) {
              LOG_E(TAG, "ProvisionManager init failed — cannot open portal");
            } else if (provisionManager.startAPModeForReconfig()) {
              portal_open_due_to_disconnect_ = true;
            }
            mqtt_failure_start = 0;
          }
        }
      }
    } else {
      if (mqtt_failure_start != 0) {
        LOG_I(TAG, "MQTT recovered - persistent failure timer reset");
        mqtt_failure_start = 0;
      }
    }
  }

  // AUT-592: Periodic 30s actuator status blast removed — caused MQTT flooding (AUT-590 §7 R3).

  offlineModeManager.checkDelayTimer();
  static unsigned long last_offline_eval = 0;
  if (!safety_task_active && offlineModeManager.isOfflineActive()) {
    if (millis() - last_offline_eval > 5000) {
      last_offline_eval = millis();
      offlineModeManager.evaluateOfflineRules();
    }
  }

  LOG_D(TAG, "LOOP[legacy " + String(loop_count) + "] END");
  delay(10);
}

void loop() {
  if (!g_safety_rtos_tasks_created) {
    loopLegacySingleThreadedWhenNoRtosTasks();
    return;
  }
  vTaskDelay(pdMS_TO_TICKS(1000));
}

// ============================================
// MQTT MESSAGE HANDLERS (PHASE 4)
// ============================================
bool handleSensorConfig(JsonObject doc, const String& correlationId) {
  LOG_I(TAG, "Handling sensor configuration from MQTT");

  // CP-F2: doc is pre-parsed by processConfigUpdateQueue — no local deserializeJson.
  // Skip silently if payload has no 'sensors' key (actuator-only config)
  if (!doc.containsKey("sensors")) {
    LOG_D(TAG, "No 'sensors' key in payload — skipping (actuator-only config)");
    return true;
  }

  JsonArray sensors = doc["sensors"].as<JsonArray>();
  if (sensors.isNull()) {
    String message = "Sensor config 'sensors' field is not an array";
    LOG_E(TAG, message);
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR, ConfigErrorCode::MISSING_FIELD, message,
        JsonVariantConst(), correlationId);
    return false;
  }

  size_t total = sensors.size();
  if (total == 0) {
    // Empty sensor array is valid for actuator-only ESPs
    LOG_I(TAG, "No sensors configured (actuator-only device)");
    ConfigResponseBuilder::publishSuccess(ConfigType::SENSOR, 0,
                                          "No sensors configured",
                                          correlationId);
    return true;
  }

  // Phase 4: Collect failures for aggregated response
  std::vector<ConfigFailureItem> failures;
  failures.reserve(min(total, (size_t)MAX_CONFIG_FAILURES));
  uint8_t success_count = 0;

  for (JsonObject sensorObj : sensors) {
    ConfigFailureItem failure;
    if (parseAndConfigureSensorWithTracking(sensorObj, &failure)) {
      success_count++;
    } else {
      // Only store up to MAX_CONFIG_FAILURES
      if (failures.size() < MAX_CONFIG_FAILURES) {
        failures.push_back(failure);
      }
    }
  }

  // Phase 4: Use publishWithFailures for aggregated response
  uint8_t fail_count = static_cast<uint8_t>(total - success_count);
  ConfigResponseBuilder::publishWithFailures(
      ConfigType::SENSOR,
      success_count,
      fail_count,
      failures,
      correlationId);
  return fail_count == 0;
}

// ============================================
// PHASE 4: SENSOR PARSING WITH FAILURE TRACKING
// ============================================
// New version that fills failure details instead of publishing immediately
bool parseAndConfigureSensorWithTracking(const JsonObjectConst& sensor_obj, ConfigFailureItem* failure_out) {
  SensorConfig config;

  // Helper macro to set failure and return false
  #define SET_FAILURE_AND_RETURN(gpio_val, err_code, err_name, detail_msg) \
    if (failure_out) { \
      failure_out->type = "sensor"; \
      failure_out->gpio = gpio_val; \
      failure_out->error_code = err_code; \
      failure_out->error_name = err_name; \
      failure_out->detail = detail_msg; \
    } \
    return false;

  if (!sensor_obj.containsKey("gpio")) {
    LOG_E(TAG, "Sensor config missing required field 'gpio'");
    SET_FAILURE_AND_RETURN(0, ERROR_CONFIG_MISSING, "MISSING_FIELD", "Missing required field 'gpio'");
  }

  int gpio_value = 255;
  if (!JsonHelpers::extractInt(sensor_obj, "gpio", gpio_value)) {
    LOG_E(TAG, "Sensor field 'gpio' must be an integer");
    SET_FAILURE_AND_RETURN(0, ERROR_CONFIG_INVALID, "TYPE_MISMATCH", "Field 'gpio' must be an integer");
  }
  config.gpio = static_cast<uint8_t>(gpio_value);

  if (!sensor_obj.containsKey("sensor_type")) {
    LOG_E(TAG, "Sensor config missing required field 'sensor_type'");
    SET_FAILURE_AND_RETURN(config.gpio, ERROR_CONFIG_MISSING, "MISSING_FIELD", "Missing required field 'sensor_type'");
  }
  if (!JsonHelpers::extractString(sensor_obj, "sensor_type", config.sensor_type)) {
    LOG_E(TAG, "Sensor field 'sensor_type' must be a string");
    SET_FAILURE_AND_RETURN(config.gpio, ERROR_CONFIG_INVALID, "TYPE_MISMATCH", "Field 'sensor_type' must be a string");
  }
  // Normalize sensor_type to lowercase (Defense-in-Depth)
  // Server may send "DS18B20" or "SHT31" - direct indexOf() checks need lowercase
  config.sensor_type.toLowerCase();

  if (!sensor_obj.containsKey("sensor_name")) {
    LOG_E(TAG, "Sensor config missing required field 'sensor_name'");
    SET_FAILURE_AND_RETURN(config.gpio, ERROR_CONFIG_MISSING, "MISSING_FIELD", "Missing required field 'sensor_name'");
  }
  if (!JsonHelpers::extractString(sensor_obj, "sensor_name", config.sensor_name)) {
    LOG_E(TAG, "Sensor field 'sensor_name' must be a string");
    SET_FAILURE_AND_RETURN(config.gpio, ERROR_CONFIG_INVALID, "TYPE_MISMATCH", "Field 'sensor_name' must be a string");
  }

  JsonHelpers::extractString(sensor_obj, "subzone_id", config.subzone_id, "");

  // BUG-ONEWIRE-CONFIG-001 FIX: Extract OneWire ROM-Code for OneWire sensors
  // Server sends 16 hex chars (e.g. "28FF641E8D3C0C79") for DS18B20
  // Empty string for non-OneWire sensors is valid (analog, I2C, etc.)
  JsonHelpers::extractString(sensor_obj, "onewire_address", config.onewire_address, "");

  // R20-P2: Extract I2C address for multi-device I2C support (e.g. 2x SHT31 at 0x44 + 0x45)
  int i2c_addr_int = 0;
  if (JsonHelpers::extractInt(sensor_obj, "i2c_address", i2c_addr_int, 0)) {
    config.i2c_address = static_cast<uint8_t>(i2c_addr_int);
  }

  JsonHelpers::extractString(sensor_obj, "interface_type", config.interface_type, "");

  // External ADC source (ADS1115) — per-sensor acquisition source for pH/EC.
  // Default "internal" keeps the unchanged ESP32 12-bit ADC path. For "ads1115"
  // the i2c_address field carries the module address (0x48-0x4B) and gpio stays 0.
  // Stored compactly as uint8_t codes (see AdcSourceCode / ads1115Pga* helpers).
  String adc_source_str;
  JsonHelpers::extractString(sensor_obj, "adc_source", adc_source_str, "internal");
  adc_source_str.toLowerCase();
  config.adc_source = (adc_source_str == "ads1115") ? AdcSourceCode::ADS1115
                                                     : AdcSourceCode::INTERNAL;
  int adc_channel_int = 255;
  if (JsonHelpers::extractInt(sensor_obj, "adc_channel", adc_channel_int, 255)) {
    config.adc_channel = static_cast<uint8_t>(adc_channel_int);
  }
  String pga_gain_str;
  JsonHelpers::extractString(sensor_obj, "pga_gain", pga_gain_str, "4.096");
  config.pga_gain = ads1115PgaBitsFromString(pga_gain_str);

  // Digital sensor polarity (liquid_level): "active_high" (PNP) or "active_low" (NPN, default)
  String polarity_str;
  JsonHelpers::extractString(sensor_obj, "polarity", polarity_str, "active_low");
  polarity_str.toLowerCase();
  config.polarity = (polarity_str == "active_high") ? SensorPolarityCode::ACTIVE_HIGH
                                                     : SensorPolarityCode::ACTIVE_LOW;

  int uart_rx = 255;
  int uart_tx = 255;
  int uart_baud = 9600;
  JsonHelpers::extractInt(sensor_obj, "uart_rx_pin", uart_rx, 255);
  JsonHelpers::extractInt(sensor_obj, "uart_tx_pin", uart_tx, 255);
  JsonHelpers::extractInt(sensor_obj, "uart_baud", uart_baud, 9600);
  config.uart_rx_pin = static_cast<uint8_t>(uart_rx);
  config.uart_tx_pin = static_cast<uint8_t>(uart_tx);
  config.uart_baud = static_cast<uint32_t>(uart_baud);

  bool bool_value = true;
  if (JsonHelpers::extractBool(sensor_obj, "active", bool_value, true)) {
    config.active = bool_value;
  } else {
    config.active = true;
  }

  // AUT-555: QoS-adaptive publish.
  //
  // The server injects "publish_qos" (0 or 1) into each sensor's config payload.
  // It queries cross_esp_logic to find which GPIOs are trigger-sensors for enabled
  // rules. Sensors in a rule get 1, pure telemetry sensors get 0.
  //
  // We clamp to 0/1 defensively (any value > 0 → 1) so a future server that sends
  // higher QoS values doesn't accidentally use QoS-2 on a sensor-data topic.
  //
  // Default 0 ensures backward-compatibility: if the field is absent (older server
  // firmware or initial boot before first config push) we stay on the AUT-54 default
  // of QoS-0 for all sensors rather than accidentally enabling QoS-1 everywhere.
  int publish_qos_val = 0;
  if (JsonHelpers::extractInt(sensor_obj, "publish_qos", publish_qos_val, 0)) {
    config.publish_qos = (publish_qos_val > 0) ? 1 : 0;
  } else {
    config.publish_qos = 0;
  }

  if (JsonHelpers::extractBool(sensor_obj, "raw_mode", bool_value, true)) {
    config.raw_mode = bool_value;
  } else {
    config.raw_mode = true;
  }

  // ✅ Phase 2C: Operating Mode Parsing
  String mode_str;
  if (JsonHelpers::extractString(sensor_obj, "operating_mode", mode_str, "continuous")) {
    if (mode_str == "continuous" || mode_str == "on_demand" ||
        mode_str == "paused" || mode_str == "scheduled") {
      config.operating_mode = mode_str;
    } else {
      LOG_W(TAG, "Invalid operating_mode '" + mode_str + "', defaulting to 'continuous'");
      config.operating_mode = "continuous";
    }
  } else {
    config.operating_mode = "continuous";
  }

  // ✅ Phase 2C: Measurement Interval Parsing
  int interval_seconds = 30;
  if (JsonHelpers::extractInt(sensor_obj, "measurement_interval_seconds", interval_seconds, 30)) {
    if (interval_seconds < 1) {
      LOG_W(TAG, "measurement_interval_seconds too low, using minimum 1s");
      interval_seconds = 1;
    } else if (interval_seconds > 300) {
      LOG_W(TAG, "measurement_interval_seconds too high, using maximum 300s");
      interval_seconds = 300;
    }
  }
  config.measurement_interval_ms = static_cast<uint32_t>(interval_seconds) * 1000;

  LOG_D(TAG, "Sensor GPIO " + String(config.gpio) + " config: mode=" +
            config.operating_mode + ", interval=" + String(interval_seconds) + "s");

  // Tombstone deletes (active=false) must run before validateSensorConfig().
  // UART tombstones often omit uart_rx/tx pins; validation would also reject
  // reserved pins that the delete is meant to release (AUT-527 CO2 GPIO 17/18).
  if (!config.active) {
    bool removed = sensorManager.removeSensor(config.gpio, config.onewire_address,
                                             config.i2c_address);
    if (!removed && config.sensor_type == "co2") {
      if (config.gpio != 17) {
        removed = sensorManager.removeSensor(17, "", 0);
      }
      if (!removed && config.gpio != 18) {
        removed = sensorManager.removeSensor(18, "", 0);
      }
    }
    if (!removed) {
      LOG_W(TAG, "Sensor removal requested, but no sensor on GPIO " + String(config.gpio));
    }
    LOG_I(TAG, "Sensor removed: GPIO " + String(config.gpio));
    return true;
  }

  if (!configManager.validateSensorConfig(config)) {
    LOG_E(TAG, "Sensor validation failed for GPIO " + String(config.gpio));
    // Check if it's a GPIO conflict using GPIOManager
    // Bus-sharing owners (e.g. "bus/onewire/4") are NOT conflicts for compatible sensors
    String pin_owner = gpioManager.getPinOwner(config.gpio);
    String pin_component = gpioManager.getPinComponent(config.gpio);
    String detail;
    if (pin_owner.length() > 0 && !pin_owner.startsWith("bus/")) {
      // Exclusive conflict: Pin owned by non-bus component (sensor, actuator, system)
      detail = "GPIO " + String(config.gpio) + " reserved by " + pin_owner;
      if (pin_component.length() > 0) {
        detail += " (" + pin_component + ")";
      }
      SET_FAILURE_AND_RETURN(config.gpio, ERROR_GPIO_CONFLICT, "GPIO_CONFLICT", detail);
    } else {
      SET_FAILURE_AND_RETURN(config.gpio, ERROR_CONFIG_INVALID, "VALIDATION_FAILED",
                             "Sensor validation failed for GPIO " + String(config.gpio));
    }
  }

  if (!sensorManager.configureSensor(config)) {
    LOG_E(TAG, "Failed to configure sensor on GPIO " + String(config.gpio));
    // Check for GPIO conflict (distinguish exclusive vs bus-sharing conflicts)
    String pin_owner = gpioManager.getPinOwner(config.gpio);
    String pin_component = gpioManager.getPinComponent(config.gpio);
    if (pin_owner.length() > 0 && !pin_owner.startsWith("bus/")) {
      // Exclusive conflict: Pin owned by non-bus component (sensor, actuator, system)
      String detail = "GPIO " + String(config.gpio) + " already used by " + pin_owner;
      if (pin_component.length() > 0) {
        detail += " (" + pin_component + ")";
      }
      SET_FAILURE_AND_RETURN(config.gpio, ERROR_GPIO_CONFLICT, "GPIO_CONFLICT", detail);
    } else {
      // Either no owner or bus owner (bus-sharing scenario) - report actual config failure
      SET_FAILURE_AND_RETURN(config.gpio, ERROR_SENSOR_INIT_FAILED, "CONFIG_FAILED",
                             "Failed to configure sensor on GPIO " + String(config.gpio));
    }
  }

  if (!configManager.saveSensorConfig(config)) {
    LOG_E(TAG, "Failed to save sensor config to NVS for GPIO " + String(config.gpio));
    SET_FAILURE_AND_RETURN(config.gpio, ERROR_NVS_WRITE_FAILED, "NVS_WRITE_FAILED",
                           "Failed to save sensor config to NVS");
  }

  LOG_I(TAG, "Sensor configured: GPIO " + String(config.gpio) + " (" + config.sensor_type + ")");

  #undef SET_FAILURE_AND_RETURN
  return true;
}

// Legacy version for backward compatibility (calls new version)
bool parseAndConfigureSensor(const JsonObjectConst& sensor_obj) {
  ConfigFailureItem failure;
  bool success = parseAndConfigureSensorWithTracking(sensor_obj, &failure);

  // For backward compatibility: publish individual error if failed
  if (!success) {
    ConfigResponseBuilder::publishError(
        ConfigType::SENSOR,
        static_cast<ConfigErrorCode>(failure.error_code),
        failure.detail);
  }

  return success;
}

bool handleActuatorConfig(JsonObject doc, const String& correlationId) {
  LOG_I(TAG, "Handling actuator configuration from MQTT");
  // CP-F2: Pass pre-parsed actuators array — no local deserializeJson.
  return actuatorManager.handleActuatorConfig(doc["actuators"].as<JsonArray>(), correlationId);
}

// ============================================
// SAFETY-P4: Offline Rules Config Handler
// ============================================
bool handleOfflineRulesConfig(JsonObject doc, const String& correlationId) {
  if (offlineModeManager.isAdopting()) {
    LOG_W(TAG, String("[CONFIG] Offline-rules update deferred during ADOPTING (correlation_id=") +
               correlationId + ")");
    return true;
  }
  // CP-F2: Pass pre-parsed root doc — parseOfflineRules extracts "offline_rules" key internally.
  return offlineModeManager.parseOfflineRules(doc);
}

// ============================================
// SENSOR COMMAND HANDLER (PHASE 2C - On-Demand)
// ============================================
/**
 * Handles sensor commands (e.g., manual measurement trigger)
 *
 * Topic: kaiser/{id}/esp/{esp_id}/sensor/{gpio}/command
 * Payload: {"command": "measure", "request_id": "req_12345"}
 */
SensorCommandExecutionResult handleSensorCommand(const String& topic, const String& payload,
                                                 const IntentMetadata& metadata) {
  SensorCommandExecutionResult result{false, "failed", "EXECUTE_FAIL", "Sensor command execution failed", true};
  LOG_I(TAG, "Sensor command received: " + topic);

  // Extract GPIO from topic
  // Format: kaiser/{id}/esp/{esp_id}/sensor/{gpio}/command
  int sensor_pos = topic.indexOf("/sensor/");
  int command_pos = topic.lastIndexOf("/command");

  if (sensor_pos < 0 || command_pos < 0 || sensor_pos >= command_pos) {
    LOG_E(TAG, "Invalid sensor command topic format: " + topic);
    result.code = "INVALID_TOPIC";
    result.reason = "Invalid sensor command topic format";
    return result;
  }

  // Extract GPIO string between "/sensor/" and "/command"
  String gpio_str = topic.substring(sensor_pos + 8, command_pos);
  uint8_t gpio = static_cast<uint8_t>(gpio_str.toInt());

  if (gpio == 0 && gpio_str != "0") {
    LOG_E(TAG, "Failed to parse GPIO from topic: " + topic);
    result.code = "INVALID_GPIO";
    result.reason = "Failed to parse GPIO from topic";
    return result;
  }

  // Parse JSON payload
  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, payload);

  if (error) {
    LOG_E(TAG, "Failed to parse sensor command JSON: " + String(error.c_str()));
    result.code = "INVALID_JSON";
    result.reason = "Failed to parse sensor command JSON";
    return result;
  }

  String command = doc["command"] | "";
  String request_id = doc["request_id"] | "";

  if (command == "measure") {
    uint32_t timeout_ms = 5000;
    if (!doc["timeout_ms"].isNull()) {
      uint32_t requested_timeout = doc["timeout_ms"].as<uint32_t>();
      // Keep runtime deterministic and prevent pathological long blocking calls.
      if (requested_timeout < 1) {
        timeout_ms = 1;
      } else if (requested_timeout > 60000) {
        timeout_ms = 60000;
      } else {
        timeout_ms = requested_timeout;
      }
    }

    uint8_t sample_count = 0;
    if (!doc["sample_count"].isNull()) {
      uint32_t requested_samples = doc["sample_count"].as<uint32_t>();
      if (requested_samples > 32) {
        sample_count = 32;
      } else {
        sample_count = static_cast<uint8_t>(requested_samples);
      }
    }

    uint16_t sample_delay_ms = 0;
    if (!doc["sample_delay_ms"].isNull()) {
      uint32_t requested_delay = doc["sample_delay_ms"].as<uint32_t>();
      if (requested_delay > 1000) {
        sample_delay_ms = 1000;
      } else {
        sample_delay_ms = static_cast<uint16_t>(requested_delay);
      }
    }

    // AUT-1013 (B3): optional command discriminators for ADS1115 multi-sensor gpio=0.
    // Additive/optional — absent for legacy callers/servers. Follows the same optional-field
    // pattern as sample_count/sample_delay_ms/timeout_ms above. Empty sensor_type + channel<0
    // means "no discriminator": firmware then applies the legacy single-slot fallback for a
    // unique gpio, or returns AMBIGUOUS_SENSOR when the gpio is shared (see triggerManualMeasurement).
    String sensor_type = doc["sensor_type"] | "";
    int adc_channel = -1;
    if (!doc["adc_channel"].isNull()) {
      int requested_channel = doc["adc_channel"].as<int>();
      // ADS1115 single-ended channels are 0-3; anything else is treated as unset.
      if (requested_channel >= 0 && requested_channel <= 3) {
        adc_channel = requested_channel;
      }
    }

    LOG_I(TAG, "Manual measurement requested for GPIO " + String(gpio) +
                   " (timeout_ms=" + String(timeout_ms) +
                   ", sample_count=" + String(sample_count) +
                   ", sample_delay_ms=" + String(sample_delay_ms) +
                   ", sensor_type=" + (sensor_type.length() > 0 ? sensor_type : String("<none>")) +
                   ", adc_channel=" + (adc_channel >= 0 ? String(adc_channel) : String("<none>")) + ")");

    ManualMeasurementResult measurement =
        sensorManager.triggerManualMeasurement(gpio, timeout_ms, sample_count, sample_delay_ms,
                                               sensor_type, adc_channel);
    bool success = measurement.measurement_ok && measurement.publish_ok && !measurement.timeout_reached;

    // Send response with request_id and intent metadata (E-P4)
    if (request_id.length() > 0) {
      String response_topic = String(TopicBuilder::buildSensorResponseTopic(gpio));
      DynamicJsonDocument response(512);
      response["request_id"] = request_id;
      response["gpio"] = gpio;
      response["command"] = "measure";
      response["success"] = success;
      response["measurement_ok"] = measurement.measurement_ok;
      response["publish_ok"] = measurement.publish_ok;
      response["timeout"] = measurement.timeout_reached;
      response["reason_code"] = measurement.reason_code;
      response["quality"] = measurement.quality;
      response["sensor_type"] = measurement.sensor_type;
      // AUT-1013: report the physical ADS1115 channel that was measured (255 = unset/internal
      // ADC → omit) so the server return-path can confirm the correct channel was addressed.
      if (measurement.adc_channel != 255) {
        response["adc_channel"] = measurement.adc_channel;
      }
      response["raw"] = measurement.raw_value;
      response["ts"] = timeManager.getUnixTimestamp();
      response["seq"] = mqttClient.getNextSeq();
      if (measurement.has_sampling_stats && measurement.sample_count > 1) {
        response["sample_count"] = measurement.sample_count;
        response["adc_stddev"] = measurement.adc_stddev;
        response["stable"] = measurement.stable;
      }

      // E-P4: Include intent metadata for server-side correlation
      if (strlen(metadata.intent_id) > 0) {
        response["intent_id"] = metadata.intent_id;
      }
      if (strlen(metadata.correlation_id) > 0) {
        response["correlation_id"] = metadata.correlation_id;
      }
      response["ttl_ms"] = metadata.ttl_ms;

      String response_payload;
      serializeJson(response, response_payload);
      // Under publish pressure, give Core 0 a brief drain window so command responses
      // are less likely to collide with sensor-data bursts.
#ifndef MQTT_USE_PUBSUBCLIENT
      if (g_publish_queue != NULL) {
        for (uint8_t wait_cycles = 0;
             wait_cycles < 5 &&
             uxQueueMessagesWaiting(g_publish_queue) >= PUBLISH_QUEUE_SHED_WATERMARK;
             ++wait_cycles) {
          vTaskDelay(pdMS_TO_TICKS(20));
        }
      }
#endif
      mqttClient.safePublish(response_topic, response_payload, 0, 2);

      LOG_D(TAG, "Sensor command response sent: " + response_payload);
    }

    if (success) {
      LOG_I(TAG, "Manual measurement completed for GPIO " + String(gpio));
      result.ok = true;
      result.outcome = "applied";
      result.code = "NONE";
      result.reason = "Sensor measurement delivered";
      result.retryable = false;
      return result;
    } else {
      LOG_W(TAG, "Manual measurement failed for GPIO " + String(gpio));
      if (measurement.timeout_reached) {
        result.ok = false;
        result.outcome = "expired";
        result.code = "MEASURE_TIMEOUT";
        result.reason = "Manual measurement exceeded timeout";
        result.retryable = true;
        return result;
      }
      result.ok = false;
      result.outcome = "failed";
      result.code = measurement.reason_code.length() > 0 ? measurement.reason_code : "EXECUTE_FAIL";
      result.reason = "Manual measurement failed before durable delivery";
      result.retryable = true;
      return result;
    }
  } else {
    LOG_W(TAG, "Unknown sensor command: " + command);
    result.code = "UNKNOWN_COMMAND";
    result.reason = "Unknown sensor command";
    return result;
  }
}


