#include "config_response.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "CFGRESP";

bool ConfigResponseBuilder::publishSuccess(ConfigType type,
                                           uint8_t count,
                                           const String& message,
                                           const String& correlation_id) {
  ConfigResponsePayload payload;
  payload.status = ConfigStatus::SUCCESS;
  payload.type = type;
  payload.count = count;
  payload.message = message;
  payload.error_code = "NONE";
  payload.failed_item.clear();
  payload.correlation_id = correlation_id;
  return publish(payload);
}

bool ConfigResponseBuilder::publishError(ConfigType type,
                                         ConfigErrorCode error_code,
                                         const String& message,
                                         JsonVariantConst failed_item,
                                         const String& correlation_id) {
  ConfigResponsePayload payload;
  payload.status = ConfigStatus::ERROR;
  payload.type = type;
  payload.count = 0;
  payload.message = message;
  payload.error_code = String(configErrorCodeToString(error_code));
  payload.failed_item.clear();
  payload.correlation_id = correlation_id;

  if (!failed_item.isNull()) {
    payload.failed_item.set(failed_item);
  }

  return publish(payload);
}

bool ConfigResponseBuilder::publish(const ConfigResponsePayload& payload) {
  String json_payload = buildJsonPayload(payload);
  String topic = String(TopicBuilder::buildConfigResponseTopic());

  bool published = mqttClient.safePublish(topic, json_payload, 1);
  if (published) {
    const char* type_str = configTypeToString(payload.type);
    const char* status_str = configStatusToString(payload.status);
    if (type_str == nullptr) type_str = "unknown";
    if (status_str == nullptr) status_str = "unknown";

    char log_buf[128];
    snprintf(log_buf, sizeof(log_buf), "ConfigResponse published [%s] status=%s", type_str, status_str);
    LOG_I(TAG, log_buf);
  } else {
    LOG_E(TAG, "ConfigResponse publish failed for topic: " + topic);
  }

  return published;
}

String ConfigResponseBuilder::buildJsonPayload(const ConfigResponsePayload& payload) {
  DynamicJsonDocument doc(512);
  doc["seq"] = mqttClient.getNextSeq();
  doc["status"] = configStatusToString(payload.status);
  doc["type"] = configTypeToString(payload.type);
  doc["count"] = payload.count;
  if (payload.message.length() > 0) {
    doc["message"] = payload.message;
  } else {
    doc["message"] = payload.status == ConfigStatus::SUCCESS ? "ok" : "error";
  }

  if (payload.status == ConfigStatus::ERROR) {
    const String code = payload.error_code.length() > 0 ? payload.error_code : "UNKNOWN_ERROR";
    doc["error_code"] = code;
    if (payload.failed_item.size() > 0 && payload.failed_item.is<JsonObject>()) {
      doc["failed_item"] = payload.failed_item.as<JsonObjectConst>();
    }
  }

  // Phase 3: Include correlation_id for event tracking
  if (payload.correlation_id.length() > 0) {
    doc["correlation_id"] = payload.correlation_id;
  }

  String json;
  size_t written = serializeJson(doc, json);
  if (written == 0 || json.length() == 0) {
    LOG_E(TAG, "JSON serialization failed in buildJsonPayload (type=" +
              String(configTypeToString(payload.type)) + ")");
    // Return minimal valid JSON with required type field
    return String("{\"status\":\"error\",\"type\":\"") +
           configTypeToString(payload.type) +
           "\",\"message\":\"serialization_failed\"}";
  }
  return json;
}

// ============================================
// PHASE 4: PUBLISH WITH FAILURES
// ============================================

bool ConfigResponseBuilder::publishWithFailures(
    ConfigType type,
    uint8_t success_count,
    uint8_t fail_count,
    const std::vector<ConfigFailureItem>& failures,
    const String& correlation_id) {

  // Determine status based on counts
  ConfigStatus status;
  if (fail_count == 0) {
    status = ConfigStatus::SUCCESS;
  } else if (success_count > 0) {
    status = ConfigStatus::PARTIAL_SUCCESS;
  } else {
    status = ConfigStatus::ERROR;
  }

  String json_payload = buildJsonPayloadWithFailures(type, status, success_count, fail_count, failures, correlation_id);
  String topic = String(TopicBuilder::buildConfigResponseTopic());

  bool published = mqttClient.safePublish(topic, json_payload, 1);
  if (published) {
    const char* type_str = configTypeToString(type);
    const char* status_str = configStatusToString(status);
    if (type_str == nullptr) type_str = "unknown";
    if (status_str == nullptr) status_str = "unknown";

    char log_buf[160];
    snprintf(log_buf, sizeof(log_buf),
             "ConfigResponse published [%s] status=%s success=%u failed=%u",
             type_str, status_str, success_count, fail_count);
    LOG_I(TAG, log_buf);
  } else {
    LOG_E(TAG, "ConfigResponse publish failed for topic: " + topic);
  }

  return published;
}

String ConfigResponseBuilder::buildJsonPayloadWithFailures(
    ConfigType type,
    ConfigStatus status,
    uint8_t success_count,
    uint8_t fail_count,
    const std::vector<ConfigFailureItem>& failures,
    const String& correlation_id) {

  // Calculate document size: base + failures array
  // Base: ~200 bytes, each failure: ~100 bytes
  size_t doc_size = 256 + (failures.size() * 128);
  if (doc_size > 2048) doc_size = 2048;  // Cap at 2KB

  DynamicJsonDocument doc(doc_size);
  doc["seq"] = mqttClient.getNextSeq();

  // Status
  doc["status"] = configStatusToString(status);
  doc["type"] = configTypeToString(type);
  doc["count"] = success_count;
  doc["failed_count"] = fail_count;

  // Generate message based on status
  String message;
  if (status == ConfigStatus::SUCCESS) {
    message = "Configured " + String(success_count) + " item(s) successfully";
  } else if (status == ConfigStatus::PARTIAL_SUCCESS) {
    message = String(success_count) + " configured, " + String(fail_count) + " failed";
  } else {
    message = "All " + String(fail_count) + " item(s) failed to configure";
  }
  doc["message"] = message;

  // Add failures array (limit to MAX_CONFIG_FAILURES)
  if (!failures.empty()) {
    JsonArray arr = doc.createNestedArray("failures");
    size_t max_failures = min(failures.size(), (size_t)MAX_CONFIG_FAILURES);

    for (size_t i = 0; i < max_failures; i++) {
      const auto& f = failures[i];
      JsonObject obj = arr.createNestedObject();
      obj["type"] = f.type;
      obj["gpio"] = f.gpio;
      obj["error_code"] = f.error_code;
      obj["error"] = f.error_name;
      if (f.detail.length() > 0) {
        obj["detail"] = f.detail;
      }
    }

    // If there were more failures than we could store, add a note
    if (failures.size() > MAX_CONFIG_FAILURES) {
      doc["failures_truncated"] = true;
      doc["total_failures"] = failures.size();
    }
  }

  // Phase 3: Include correlation_id for event tracking
  if (correlation_id.length() > 0) {
    doc["correlation_id"] = correlation_id;
  }

  String json;
  size_t written = serializeJson(doc, json);
  if (written == 0 || json.length() == 0) {
    LOG_E(TAG, "JSON serialization failed in buildJsonPayloadWithFailures (type=" +
              String(configTypeToString(type)) + ", failures=" + String(failures.size()) + ")");
    // Return minimal valid JSON with required type field
    return String("{\"status\":\"error\",\"type\":\"") +
           configTypeToString(type) +
           "\",\"message\":\"serialization_failed\"}";
  }
  return json;
}

