#pragma once

#include <stdint.h>

enum class RuntimeReadinessProfile : uint8_t {
    SENSOR_REQUIRED = 0,
    SENSOR_OPTIONAL = 1
};

struct RuntimeReadinessSnapshot {
    uint8_t sensor_count;
    uint8_t actuator_count;
    uint8_t offline_rule_count;
};

struct RuntimeReadinessPolicy {
    RuntimeReadinessProfile profile;
    bool require_actuator;
    bool require_offline_rules;
};

struct RuntimeReadinessDecision {
    bool ready;
    const char* decision_code;
    RuntimeReadinessPolicy policy;
    RuntimeReadinessSnapshot snapshot;
};

RuntimeReadinessPolicy defaultRuntimeReadinessPolicy();
const char* runtimeReadinessProfileName(RuntimeReadinessProfile profile);
RuntimeReadinessDecision evaluateRuntimeReadiness(const RuntimeReadinessSnapshot& snapshot,
                                                  const RuntimeReadinessPolicy& policy);
