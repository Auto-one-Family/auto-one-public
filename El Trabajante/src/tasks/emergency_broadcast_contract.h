#pragma once

#include <cstring>
#include <stdint.h>

struct BroadcastEmergencyContractInput {
    bool command_present;
    bool command_is_string;
    const char* command_value;

    bool action_present;
    bool action_is_string;
    const char* action_value;

    bool auth_token_present;
    bool auth_token_is_string;

    bool reason_present;
    bool reason_is_string;

    bool issued_by_present;
    bool issued_by_is_string;

    bool timestamp_present;
    bool timestamp_is_string;
};

enum class BroadcastEmergencyContractStatus : uint8_t {
    VALID = 0,
    CONTRACT_MISMATCH
};

struct BroadcastEmergencyContractResult {
    BroadcastEmergencyContractStatus status;
    const char* reject_code;
    const char* detail_code;
    const char* normalized_command;
};

inline bool isSupportedBroadcastEmergencyCommand(const char* command_value) {
    if (command_value == nullptr) {
        return false;
    }
    return strcmp(command_value, "stop_all") == 0 ||
           strcmp(command_value, "emergency_stop") == 0;
}

inline BroadcastEmergencyContractResult validateBroadcastEmergencyContract(
    const BroadcastEmergencyContractInput& input) {
    if (input.command_present && !input.command_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_COMMAND",
                nullptr};
    }
    if (input.action_present && !input.action_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_ACTION",
                nullptr};
    }
    if (input.auth_token_present && !input.auth_token_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_AUTH_TOKEN",
                nullptr};
    }
    if (input.reason_present && !input.reason_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_REASON",
                nullptr};
    }
    if (input.issued_by_present && !input.issued_by_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_ISSUED_BY",
                nullptr};
    }
    if (input.timestamp_present && !input.timestamp_is_string) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "FIELD_TYPE_TIMESTAMP",
                nullptr};
    }

    const char* command = nullptr;
    if (input.command_present && input.command_is_string) {
        command = input.command_value;
    }
    if (input.action_present && input.action_is_string) {
        if (command != nullptr && strcmp(command, input.action_value) != 0) {
            return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                    "EMERGENCY_CONTRACT_MISMATCH",
                    "CONFLICTING_COMMAND_FIELDS",
                    nullptr};
        }
        if (command == nullptr) {
            command = input.action_value;  // Legacy alias support
        }
    }

    if (command == nullptr || strlen(command) == 0) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "MISSING_COMMAND_FIELD",
                nullptr};
    }
    if (!isSupportedBroadcastEmergencyCommand(command)) {
        return {BroadcastEmergencyContractStatus::CONTRACT_MISMATCH,
                "EMERGENCY_CONTRACT_MISMATCH",
                "UNKNOWN_COMMAND_VALUE",
                nullptr};
    }

    return {BroadcastEmergencyContractStatus::VALID, "NONE", "NONE", command};
}
