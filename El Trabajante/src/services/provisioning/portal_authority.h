#pragma once

#include <Arduino.h>

enum class PortalOpenReason : uint8_t {
    WIFI_CONNECT_FAILURE = 0,
    MQTT_CONNECT_FAILURE = 1,
    DISCONNECT_DEBOUNCE = 2,
    MQTT_PERSISTENT_FAILURE = 3
};

struct PortalDecisionContext {
    bool portal_already_open = false;
    bool boot_force_offline_autonomy = false;
    bool has_valid_local_autonomy_config = false;
};

bool mayOpenPortal(PortalOpenReason reason,
                   const PortalDecisionContext& context,
                   const char** out_code = nullptr);
