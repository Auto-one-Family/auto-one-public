#pragma once

#include <stdint.h>

enum class CommandSubtype : uint8_t {
    ACTUATOR = 0,
    SENSOR = 1,
    SYSTEM = 2,
    CONFIG = 3
};

struct CommandAdmissionContext {
    bool registration_confirmed;
    bool config_pending_after_reset;
    bool approval_pending;
    bool runtime_degraded;
    bool safety_locked;
    bool recovery_intent;
    const char* system_command;
};

struct CommandAdmissionDecision {
    bool accepted;
    const char* code;
    const char* reason_code;
};

bool isSystemCommandAllowedInPending(const char* command);
CommandAdmissionDecision shouldAcceptCommand(CommandSubtype subtype, const CommandAdmissionContext& context);
