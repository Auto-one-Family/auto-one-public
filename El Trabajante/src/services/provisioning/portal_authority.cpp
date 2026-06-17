#include "portal_authority.h"

bool mayOpenPortal(PortalOpenReason reason,
                   const PortalDecisionContext& context,
                   const char** out_code) {
    if (context.portal_already_open) {
        if (out_code != nullptr) {
            *out_code = "PORTAL_ALREADY_OPEN";
        }
        return false;
    }

    if (context.boot_force_offline_autonomy || context.has_valid_local_autonomy_config) {
        if (out_code != nullptr) {
            *out_code = "PORTAL_BLOCKED_OFFLINE_AUTONOMY";
        }
        return false;
    }

    if (reason == PortalOpenReason::WIFI_CONNECT_FAILURE ||
        reason == PortalOpenReason::MQTT_CONNECT_FAILURE ||
        reason == PortalOpenReason::DISCONNECT_DEBOUNCE ||
        reason == PortalOpenReason::MQTT_PERSISTENT_FAILURE) {
        if (out_code != nullptr) {
            *out_code = "PORTAL_ALLOWED";
        }
        return true;
    }

    if (out_code != nullptr) {
        *out_code = "PORTAL_BLOCKED_UNKNOWN_REASON";
    }
    return false;
}
