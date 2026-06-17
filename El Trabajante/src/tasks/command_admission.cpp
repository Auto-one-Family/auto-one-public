#include "command_admission.h"

#include <cstring>

bool isSystemCommandAllowedInPending(const char* command) {
    if (command == nullptr || strlen(command) == 0) {
        return false;
    }

    static const char* ALLOWED_SYSTEM_COMMANDS[] = {
        "status",
        "diagnostics",
        "get_config",
        "set_log_level",
        "safe_mode"
    };

    for (const char* allowed : ALLOWED_SYSTEM_COMMANDS) {
        if (strcmp(command, allowed) == 0) {
            return true;
        }
    }
    return false;
}

CommandAdmissionDecision shouldAcceptCommand(CommandSubtype subtype, const CommandAdmissionContext& context) {
    if (context.safety_locked && subtype != CommandSubtype::SYSTEM) {
        return {false, "SAFETY_LOCKED", "SAFETY_LOCKED"};
    }

    if (!context.registration_confirmed && !context.recovery_intent) {
        return {false, "REGISTRATION_PENDING", "REGISTRATION_PENDING"};
    }

    if (context.config_pending_after_reset) {
        bool allowed_in_pending = context.recovery_intent || subtype == CommandSubtype::CONFIG;
        if (!allowed_in_pending && subtype == CommandSubtype::SYSTEM) {
            allowed_in_pending = isSystemCommandAllowedInPending(context.system_command);
        }

        if (!allowed_in_pending) {
            return {false, "CONFIG_PENDING_BLOCKED", "CONFIG_PENDING_AFTER_RESET"};
        }

        if (context.recovery_intent) {
            return {true, "RECOVERY_ACCEPTED", "RECOVERY_ACCEPTED"};
        }
        if (subtype == CommandSubtype::CONFIG) {
            return {true, "CONFIG_PENDING_CONFIG_ACCEPTED", "CONFIG_PENDING_CONFIG_ACCEPTED"};
        }
        return {true, "PENDING_ALLOWLIST_ACCEPTED", "PENDING_ALLOWLIST_ACCEPTED"};
    }

    if (context.approval_pending) {
        bool allowed_in_pending = context.recovery_intent || subtype == CommandSubtype::CONFIG;
        if (!allowed_in_pending && subtype == CommandSubtype::SYSTEM) {
            allowed_in_pending = isSystemCommandAllowedInPending(context.system_command);
        }
        if (!allowed_in_pending) {
            return {false, "PENDING_APPROVAL_BLOCKED", "PENDING_APPROVAL"};
        }
        if (context.recovery_intent) {
            return {true, "RECOVERY_ACCEPTED", "RECOVERY_ACCEPTED"};
        }
        if (subtype == CommandSubtype::CONFIG) {
            return {true, "PENDING_APPROVAL_CONFIG_ACCEPTED", "PENDING_APPROVAL_CONFIG_ACCEPTED"};
        }
        return {true, "PENDING_APPROVAL_ALLOWLIST_ACCEPTED", "PENDING_APPROVAL_ALLOWLIST_ACCEPTED"};
    }

    if (context.runtime_degraded) {
        bool allowed_in_degraded = context.recovery_intent || subtype == CommandSubtype::CONFIG;
        if (!allowed_in_degraded && subtype == CommandSubtype::SYSTEM) {
            allowed_in_degraded = isSystemCommandAllowedInPending(context.system_command);
        }
        if (!allowed_in_degraded) {
            return {false, "DEGRADED_MODE_BLOCKED", "RUNTIME_DEGRADED"};
        }
        if (context.recovery_intent) {
            return {true, "RECOVERY_ACCEPTED", "RECOVERY_ACCEPTED"};
        }
        if (subtype == CommandSubtype::CONFIG) {
            return {true, "DEGRADED_CONFIG_ACCEPTED", "DEGRADED_CONFIG_ACCEPTED"};
        }
        return {true, "DEGRADED_ALLOWLIST_ACCEPTED", "DEGRADED_ALLOWLIST_ACCEPTED"};
    }

    return {true, "COMMAND_ACCEPTED", "COMMAND_ACCEPTED"};
}
