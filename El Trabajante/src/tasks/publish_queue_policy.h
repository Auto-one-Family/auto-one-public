#pragma once

#include <stdint.h>

#include "publish_queue_constants.h"

// AUT-481 P3: Pure policy helpers (native-testable, no FreeRTOS/MQTT deps).

constexpr uint8_t PUBLISH_DRAIN_BUDGET_DEFAULT = 1;
constexpr uint8_t PUBLISH_DRAIN_BUDGET_BOOSTED = 2;
constexpr uint8_t PUBLISH_DRAIN_BOOST_FILL_MIN = 3;

inline uint8_t computeAdaptivePublishDrainBudget(uint8_t fill_level,
                                                bool transport_write_timeout_active,
                                                bool circuit_breaker_allows,
                                                bool queue_paused) {
    if (queue_paused || !circuit_breaker_allows || transport_write_timeout_active) {
        return PUBLISH_DRAIN_BUDGET_DEFAULT;
    }
    if (fill_level >= PUBLISH_DRAIN_BOOST_FILL_MIN) {
        return PUBLISH_DRAIN_BUDGET_BOOSTED;
    }
    return PUBLISH_DRAIN_BUDGET_DEFAULT;
}

inline bool shouldDeferActuatorStatusPublish(uint8_t fill_level) {
    if (PUBLISH_QUEUE_SHED_WATERMARK == 0) {
        return false;
    }
    return fill_level >= static_cast<uint8_t>(PUBLISH_QUEUE_SHED_WATERMARK - 1U);
}

inline uint8_t publishQueuePressureRecoveredThreshold() {
    // Hysteresis dead band: ENTER at SHED_WATERMARK, RECOVER below this (exclusive).
    if (PUBLISH_QUEUE_SHED_WATERMARK <= 1) {
        return 0;
    }
    return static_cast<uint8_t>(PUBLISH_QUEUE_SHED_WATERMARK - 1U);
}
