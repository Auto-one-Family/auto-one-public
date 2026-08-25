#pragma once
#include <cstdint>
#include <cmath>

// ============================================
// SAFETY-P4: Offline Hysteresis Rules
// ============================================
// TM-authorized exception to Server-Centric rule.
// Precedent: SAFETY-P1 setAllActuatorsToSafeState.
//
// These rules activate ONLY when server connectivity is lost
// and a 30s grace period has elapsed. Binary actuator control
// only — no PWM, no business logic.

// AUT-1143 S3: board-budgeted (S0/D6 beleg, docs/analysen/aut-1139-s0-...).
// ESP32-S3: RAM/NVS-Headroom trivial (~161 KB) -> 16. WROOM-32: DRAM
// .dram0.bss-Headroom nur ~232 B (AUT-602-Praezedenzfall: +96 B kippten den
// Build) -> bleibt beim historischen 8, kein Wachstum. 16 ist zugleich die
// Obergrenze, die der uint16_t-Debounce-Bitmask-Fix unten (offline_mode_manager.cpp)
// ohne weiteren uint32_t-Schritt traegt.
#ifdef ESP32_S3_DEVKIT_MODE
static const uint8_t MAX_OFFLINE_RULES = 16;
#else
static const uint8_t MAX_OFFLINE_RULES = 8;
#endif

enum class OfflineRuleTimezone : uint8_t {
    UTC = 0,
    EUROPE_BERLIN = 1,
};

struct OfflineRule {
    // --- Existing fields (DO NOT REORDER — NVS blob byte layout) ---
    bool    enabled;
    uint8_t actuator_gpio;
    uint8_t sensor_gpio;
    char    sensor_value_type[21];  // max 20 chars + NUL; longest known: "bme280_humidity" (15)
    float   activate_below;         // Heating mode: activate when val < threshold
    float   deactivate_above;       // Heating mode: deactivate when val > threshold
    float   activate_above;         // Cooling mode: activate when val > threshold
    float   deactivate_below;       // Cooling mode: deactivate when val < threshold
    bool    is_active;              // Current actuator state driven by this rule
    bool    server_override;        // Server commanded while offline → skip rule

    // --- New fields (NVS blob v1+, APPEND ONLY - do not insert before this line) ---
    bool    time_filter_enabled;    // Has this rule a time window?
    uint8_t start_hour;             // 0-23 in rule timezone
    uint8_t start_minute;           // 0–59
    uint8_t end_hour;               // 0-24 (24 = midnight exclusive)
    uint8_t end_minute;             // 0–59
    uint8_t days_of_week_mask;      // Bitmask: bit0=Sun .. bit6=Sat (0x7F=all days)
    uint8_t timezone_mode;          // OfflineRuleTimezone
    uint16_t max_on_seconds;        // Max ON duration in seconds (0 = unlimited). Blob v4+.
    uint16_t cooldown_seconds;      // Min seconds between ON-transitions (0 = no cooldown). Blob v5+.
};

static_assert(sizeof(OfflineRule) == 56, "OfflineRule v5 must be exactly 56 bytes (sensor_value_type[21] + cooldown_seconds)");
