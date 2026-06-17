#ifndef SERVICES_CONFIG_CONFIG_RESPONSE_H
#define SERVICES_CONFIG_CONFIG_RESPONSE_H

#include <Arduino.h>
#include <ArduinoJson.h>

#include "../../models/config_types.h"
#include "../../models/error_codes.h"
#include "../../services/communication/mqtt_client.h"
#include "../../utils/logger.h"
#include "../../utils/topic_builder.h"

/**
 * @brief Helper for publishing standardized configuration responses.
 * Phase 4: Extended with publishWithFailures() for detailed error reporting.
 */
class ConfigResponseBuilder {
public:
  static bool publishSuccess(ConfigType type, uint8_t count, const String& message,
                             const String& correlation_id = "");

  static bool publishError(ConfigType type,
                           ConfigErrorCode error_code,
                           const String& message,
                           JsonVariantConst failed_item = JsonVariantConst(),
                           const String& correlation_id = "");

  static bool publish(const ConfigResponsePayload& payload);

  /**
   * @brief Publish response with multiple failures (Phase 4).
   *
   * Automatically determines status based on counts:
   * - SUCCESS: fail_count == 0
   * - PARTIAL_SUCCESS: success_count > 0 && fail_count > 0
   * - ERROR: success_count == 0 && fail_count > 0
   *
   * @param type Configuration type (SENSOR or ACTUATOR)
   * @param success_count Number of successfully configured items
   * @param fail_count Number of failed items
   * @param failures Vector of failure details (max 10 items)
   * @return true if MQTT publish succeeded
   */
  static bool publishWithFailures(
      ConfigType type,
      uint8_t success_count,
      uint8_t fail_count,
      const std::vector<ConfigFailureItem>& failures,
      const String& correlation_id = "");

private:
  static String buildJsonPayload(const ConfigResponsePayload& payload);
  static String buildJsonPayloadWithFailures(
      ConfigType type,
      ConfigStatus status,
      uint8_t success_count,
      uint8_t fail_count,
      const std::vector<ConfigFailureItem>& failures,
      const String& correlation_id = "");
};

#endif  // SERVICES_CONFIG_CONFIG_RESPONSE_H

