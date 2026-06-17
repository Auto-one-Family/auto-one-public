#include "offline_mode_manager.h"
#include <Arduino.h>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <nvs.h>
#include "../../utils/logger.h"
#include "../../services/config/storage_manager.h"
#include "../../services/sensor/sensor_manager.h"
#include "../../services/actuator/actuator_manager.h"
#include "../../utils/time_manager.h"
#include "../../tasks/intent_contract.h"

static const char* TAG = "SAFETY-P4";
static constexpr unsigned long ADOPTION_SETTLE_MS = 2000UL;
static constexpr uint8_t OFFLINE_WARMUP_VALID_SAMPLES = 3;

static void logAuthorityCounters(OfflineModeManager* mgr,
                                 uint32_t offline_enter_count,
                                 uint32_t adopting_enter_count,
                                 uint32_t adoption_noop_count,
                                 uint32_t adoption_delta_count,
                                 uint32_t handover_abort_count,
                                 uint32_t handover_contract_reject_count,
                                 uint32_t active_handover_epoch,
                                 uint32_t handover_completed_epoch) {
    (void)mgr;
    LOG_I(TAG, String("[SAFETY-P4] counters: schema=") +
               String(OfflineModeManager::OFFLINE_AUTHORITY_METRICS_SCHEMA_VERSION) +
               " offline_enter=" + String(offline_enter_count) +
               " adopting_enter=" + String(adopting_enter_count) +
               " adoption_noop=" + String(adoption_noop_count) +
               " adoption_delta=" + String(adoption_delta_count) +
               " handover_abort=" + String(handover_abort_count) +
               " handover_contract_reject=" + String(handover_contract_reject_count) +
               " active_epoch=" + String(active_handover_epoch) +
               " completed_epoch=" + String(handover_completed_epoch));
}

// One-shot / edge flags for evaluateOfflineRules — reset when server pushes new offline_rules
static bool     s_offline_first_eval        = true;
static uint8_t  s_eval_disabled_logged      = 0;
static uint8_t  s_eval_override_logged      = 0;
static uint8_t  s_eval_cal_inactive_logged  = 0;
static uint8_t  s_eval_time_skip_logged     = 0;
static bool     s_eval_prev_nan[MAX_OFFLINE_RULES] = {false};
static uint16_t s_rule_max_on_seconds[MAX_OFFLINE_RULES] = {0};
static unsigned long s_timewindow_on_deadline_ms[MAX_OFFLINE_RULES] = {0};
static bool          s_timewindow_fired_in_window[MAX_OFFLINE_RULES] = {false};
// s_timewindow_on_deadline_ms[i] is dual-purpose (mutual exclusion per slot):
//   __twindow_on rules: ON-deadline timestamp (millis() + max_on_s * 1000), 0 = not-yet-set.
//   sensor rules:       last-activation timestamp (millis() at last ON), 0 = never activated.
// Both interpretations treat 0 as "not set / never activated" — memset-to-zero is correct for both.

static void resetOfflineEvalLogState() {
    s_offline_first_eval       = true;
    s_eval_disabled_logged     = 0;
    s_eval_override_logged     = 0;
    s_eval_cal_inactive_logged = 0;
    s_eval_time_skip_logged    = 0;
    memset(s_eval_prev_nan, 0, sizeof(s_eval_prev_nan));
    memset(s_timewindow_on_deadline_ms, 0, sizeof(s_timewindow_on_deadline_ms));
    memset(s_timewindow_fired_in_window, 0, sizeof(s_timewindow_fired_in_window));
}

// CRC-8/SMBUS — no lookup table to conserve Flash
static uint8_t crc8(const uint8_t* data, size_t len) {
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            if (crc & 0x80) crc = (crc << 1) ^ 0x07;
            else            crc <<= 1;
        }
    }
    return crc;
}

// Legacy v1/v2 NVS blob layout (without timezone_mode).
// Keep field order identical to OfflineRule prefix for safe memcpy migration.
struct OfflineRuleBlobV2 {
    bool    enabled;
    uint8_t actuator_gpio;
    uint8_t sensor_gpio;
    char    sensor_value_type[24];
    float   activate_below;
    float   deactivate_above;
    float   activate_above;
    float   deactivate_below;
    bool    is_active;
    bool    server_override;
    bool    time_filter_enabled;
    uint8_t start_hour;
    uint8_t start_minute;
    uint8_t end_hour;
    uint8_t end_minute;
    uint8_t days_of_week_mask;
};

static_assert(sizeof(OfflineRuleBlobV2) == 52, "OfflineRuleBlobV2 on-disk size check");

// v3/v4 NVS blob layout (sensor_value_type[24], 1 padding before float, sizeof==56).
// Keep field order identical to v4 OfflineRule for safe memcpy migration.
struct OfflineRuleBlobV4 {
    bool     enabled;
    uint8_t  actuator_gpio;
    uint8_t  sensor_gpio;
    char     sensor_value_type[24];   // v4: 24 bytes; 1 implicit padding byte follows
    float    activate_below;
    float    deactivate_above;
    float    activate_above;
    float    deactivate_below;
    bool     is_active;
    bool     server_override;
    bool     time_filter_enabled;
    uint8_t  start_hour;
    uint8_t  start_minute;
    uint8_t  end_hour;
    uint8_t  end_minute;
    uint8_t  days_of_week_mask;
    uint8_t  timezone_mode;           // 1 implicit padding byte follows
    uint16_t max_on_seconds;
    // no cooldown_seconds (v5 only)
};
static_assert(sizeof(OfflineRuleBlobV4) == 56,
              "OfflineRuleBlobV4 must be 56 bytes");

// Per-rule byte size in NVS blob v3/v4 (sensor_value_type[24], float at offset 28).
// sizeof(OfflineRule) is also 56 in v5, but the internal layout differs — do not conflate.
static constexpr size_t OFFLINE_RULE_BLOB_V4_RULE_SIZE = 56;

static const char* timezoneModeLabel(uint8_t timezone_mode) {
    return (timezone_mode == static_cast<uint8_t>(OfflineRuleTimezone::EUROPE_BERLIN))
               ? "Europe/Berlin"
               : "UTC";
}

static uint8_t parseTimezoneMode(const char* timezone_name) {
    if (timezone_name == nullptr || strlen(timezone_name) == 0 || strcmp(timezone_name, "UTC") == 0) {
        return static_cast<uint8_t>(OfflineRuleTimezone::UTC);
    }
    if (strcmp(timezone_name, "Europe/Berlin") == 0 ||
        strcmp(timezone_name, "CET") == 0 ||
        strcmp(timezone_name, "CEST") == 0) {
        return static_cast<uint8_t>(OfflineRuleTimezone::EUROPE_BERLIN);
    }
    return static_cast<uint8_t>(OfflineRuleTimezone::UTC);
}

static bool isLeapYear(int year) {
    return (year % 4 == 0) && ((year % 100 != 0) || (year % 400 == 0));
}

static uint8_t daysInMonth(int year, uint8_t month) {
    static const uint8_t DAYS_PER_MONTH[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (month == 2) {
        return isLeapYear(year) ? 29 : 28;
    }
    return DAYS_PER_MONTH[month - 1];
}

static uint8_t lastSundayOfMonth(int year, uint8_t month) {
    struct tm t = {};
    t.tm_year = year - 1900;
    t.tm_mon = month - 1;
    t.tm_mday = daysInMonth(year, month);
    t.tm_hour = 12;  // avoid edge-cases near DST switches
    time_t epoch = mktime(&t);  // TimeManager configures TZ=UTC0 globally
    struct tm last_day_tm;
    gmtime_r(&epoch, &last_day_tm);
    return static_cast<uint8_t>(last_day_tm.tm_mday - last_day_tm.tm_wday);
}

static bool isEuropeBerlinDstUtc(const struct tm& utc_tm) {
    int year = utc_tm.tm_year + 1900;
    int month = utc_tm.tm_mon + 1;
    int day = utc_tm.tm_mday;
    int hour = utc_tm.tm_hour;

    if (month < 3 || month > 10) {
        return false;
    }
    if (month > 3 && month < 10) {
        return true;
    }

    uint8_t switch_day = lastSundayOfMonth(year, static_cast<uint8_t>(month));
    if (month == 3) {
        if (day > switch_day) return true;
        if (day < switch_day) return false;
        return hour >= 1;  // starts 01:00 UTC
    }
    // month == 10
    if (day < switch_day) return true;
    if (day > switch_day) return false;
    return hour < 1;  // ends 01:00 UTC
}

static bool getRuleLocalClock(const OfflineRule& rule, time_t now_unix,
                              uint8_t* out_hour, uint8_t* out_minute, uint8_t* out_wday) {
    if (now_unix <= 0) {
        return false;
    }

    struct tm utc_tm;
    gmtime_r(&now_unix, &utc_tm);
    struct tm local_tm = utc_tm;

    if (rule.timezone_mode == static_cast<uint8_t>(OfflineRuleTimezone::EUROPE_BERLIN)) {
        int32_t offset_seconds = 3600;  // CET
        if (isEuropeBerlinDstUtc(utc_tm)) {
            offset_seconds = 7200;  // CEST
        }
        time_t local_epoch = now_unix + offset_seconds;
        gmtime_r(&local_epoch, &local_tm);
    }

    *out_hour = static_cast<uint8_t>(local_tm.tm_hour);
    *out_minute = static_cast<uint8_t>(local_tm.tm_min);
    *out_wday = static_cast<uint8_t>(local_tm.tm_wday);
    return true;
}

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
OfflineModeManager& OfflineModeManager::getInstance() {
    static OfflineModeManager instance;
    return instance;
}

OfflineModeManager& offlineModeManager = OfflineModeManager::getInstance();

void OfflineModeManager::setPersistenceDrift(const char* reason) {
    persistence_drift_active_ = true;
    persistence_drift_count_++;
    const char* safe_reason = (reason != nullptr && strlen(reason) > 0) ? reason : "UNKNOWN";
    strncpy(last_persistence_drift_reason_, safe_reason, sizeof(last_persistence_drift_reason_) - 1);
    last_persistence_drift_reason_[sizeof(last_persistence_drift_reason_) - 1] = '\0';

    IntentMetadata metadata;
    initIntentMetadata(&metadata);
    String intent_id = String("offline_drift_") + String(millis());
    strncpy(metadata.intent_id, intent_id.c_str(), sizeof(metadata.intent_id) - 1);
    metadata.intent_id[sizeof(metadata.intent_id) - 1] = '\0';

    publishIntentOutcome("offline_rules",
                         metadata,
                         "failed",
                         "PERSISTENCE_DRIFT",
                         String("Offline rules persistence drift: ") + String(last_persistence_drift_reason_),
                         true);
}

void OfflineModeManager::clearPersistenceDrift() {
    if (!persistence_drift_active_) {
        return;
    }
    persistence_drift_active_ = false;

    IntentMetadata metadata;
    initIntentMetadata(&metadata);
    String intent_id = String("offline_drift_recover_") + String(millis());
    strncpy(metadata.intent_id, intent_id.c_str(), sizeof(metadata.intent_id) - 1);
    metadata.intent_id[sizeof(metadata.intent_id) - 1] = '\0';

    publishIntentOutcome("offline_rules",
                         metadata,
                         "persisted",
                         "NONE",
                         "Offline rules persistence drift recovered",
                         false);
}

// ============================================
// STATE-MACHINE HOOKS
// ============================================

void OfflineModeManager::onDisconnect() {
    if (loadMode() == OfflineMode::ONLINE) {
        storeMode(OfflineMode::DISCONNECTED);
        disconnect_timestamp_ms_ = millis();
        adoption_started_ms_ = 0;
        LOG_W(TAG, String("[SAFETY-P4] Disconnect — 30s grace timer started (t_ms=") +
                       String(millis()) + ")");
    } else if (loadMode() == OfflineMode::RECONNECTING) {
        // Reconnect handover failed before ACK: return immediately to local autonomy.
        storeMode(OfflineMode::OFFLINE_ACTIVE);
        disconnect_timestamp_ms_ = 0;
        adoption_started_ms_ = 0;
        handover_abort_count_++;
        LOG_W(TAG, "[SAFETY-P4] Disconnect during RECONNECTING — returning to OFFLINE_ACTIVE");
        logAuthorityCounters(this,
                             offline_enter_count_,
                             adopting_enter_count_,
                             adoption_noop_count_,
                             adoption_delta_count_,
                             handover_abort_count_,
                             handover_contract_reject_count_,
                             active_handover_epoch_,
                             handover_completed_epoch_);
    } else if (loadMode() == OfflineMode::ADOPTING) {
        // Adoption interrupted by new transport loss: restart the offline timer.
        storeMode(OfflineMode::DISCONNECTED);
        disconnect_timestamp_ms_ = millis();
        adoption_started_ms_ = 0;
        handover_abort_count_++;
        LOG_W(TAG, "[SAFETY-P4] Disconnect during ADOPTING — restarting grace timer");
        logAuthorityCounters(this,
                             offline_enter_count_,
                             adopting_enter_count_,
                             adoption_noop_count_,
                             adoption_delta_count_,
                             handover_abort_count_,
                             handover_contract_reject_count_,
                             active_handover_epoch_,
                             handover_completed_epoch_);
    }
}

void OfflineModeManager::onReconnect() {
    if (loadMode() == OfflineMode::OFFLINE_ACTIVE) {
        storeMode(OfflineMode::RECONNECTING);
        active_handover_epoch_++;
        LOG_I(TAG, String("[SAFETY-P4] Reconnected - waiting for server ACK to return ONLINE (epoch=") +
                   String(active_handover_epoch_) + ")");
    } else if (loadMode() == OfflineMode::DISCONNECTED) {
        // Reconnected before grace period expired — no rules were active
        storeMode(OfflineMode::ONLINE);
        disconnect_timestamp_ms_ = 0;
        LOG_I(TAG, "[SAFETY-P4] Reconnected during grace period - back ONLINE");
    }
}

bool OfflineModeManager::validateServerAckContract(uint32_t incoming_handover_epoch, const char** reject_code) const {
    if (incoming_handover_epoch == 0) {
        if (reject_code != nullptr) {
            *reject_code = "INVALID_HANDOVER_EPOCH";
        }
        return false;
    }

    OfflineMode mode = loadMode();

    if (mode == OfflineMode::ONLINE) {
        return true;
    }

    if (mode == OfflineMode::DISCONNECTED) {
        // Grace-cancel ACK: epoch matching is irrelevant in this state.
        return true;
    }

    if (mode == OfflineMode::RECONNECTING ||
        mode == OfflineMode::OFFLINE_ACTIVE ||
        mode == OfflineMode::ADOPTING) {
        if (active_handover_epoch_ == 0) {
            if (reject_code != nullptr) {
                *reject_code = "MISSING_ACTIVE_SESSION_EPOCH";
            }
            return false;
        }

        if (incoming_handover_epoch != active_handover_epoch_) {
            if (reject_code != nullptr) {
                *reject_code = "HANDOVER_EPOCH_MISMATCH";
            }
            return false;
        }
        return true;
    }

    if (reject_code != nullptr) {
        *reject_code = "MODE_UNSUPPORTED";
    }
    return false;
}

void OfflineModeManager::onServerAckReceived(uint32_t incoming_handover_epoch) {
    OfflineMode mode = loadMode();

    if (mode == OfflineMode::RECONNECTING || mode == OfflineMode::OFFLINE_ACTIVE) {
        if (incoming_handover_epoch == 0) {
            onServerAckContractMismatch("MISSING_HANDOVER_EPOCH");
            return;
        }
        uint32_t expected_epoch = active_handover_epoch_;
        uint32_t effective_incoming_epoch = incoming_handover_epoch;

        if (effective_incoming_epoch != expected_epoch) {
            adoption_noop_count_++;
            LOG_W(TAG, String("[SAFETY-P4] Stale/foreign ACK ignored: incoming_epoch=") +
                       String(effective_incoming_epoch) +
                       " active_epoch=" + String(expected_epoch));
            logAuthorityCounters(this,
                                 offline_enter_count_,
                                 adopting_enter_count_,
                                 adoption_noop_count_,
                                 adoption_delta_count_,
                                 handover_abort_count_,
                                 handover_contract_reject_count_,
                                 active_handover_epoch_,
                                 handover_completed_epoch_);
            return;
        }

        if (handover_completed_epoch_ == expected_epoch) {
            adoption_noop_count_++;
            LOG_D(TAG, String("[SAFETY-P4] Duplicate ACK for completed epoch ignored: ") + String(expected_epoch));
            logAuthorityCounters(this,
                                 offline_enter_count_,
                                 adopting_enter_count_,
                                 adoption_noop_count_,
                                 adoption_delta_count_,
                                 handover_abort_count_,
                                 handover_contract_reject_count_,
                                 active_handover_epoch_,
                                 handover_completed_epoch_);
            return;
        }

        handover_completed_epoch_ = expected_epoch;
        adoption_delta_count_++;
        enterAdoptingMode();
    } else if (mode == OfflineMode::ADOPTING) {
        // Duplicate ACK during adoption window: ignore but keep it observable.
        adoption_noop_count_++;
        LOG_D(TAG, "[SAFETY-P4] Duplicate server ACK while ADOPTING");
        logAuthorityCounters(this,
                             offline_enter_count_,
                             adopting_enter_count_,
                             adoption_noop_count_,
                             adoption_delta_count_,
                             handover_abort_count_,
                             handover_contract_reject_count_,
                             active_handover_epoch_,
                             handover_completed_epoch_);
    } else if (mode == OfflineMode::DISCONNECTED) {
        // ACK received before grace period — cancel timer
        storeMode(OfflineMode::ONLINE);
        disconnect_timestamp_ms_ = 0;
        adoption_started_ms_ = 0;
        LOG_D(TAG, "[SAFETY-P4] Server ACK during grace period - timer cancelled");
    }
}

void OfflineModeManager::onServerAckContractMismatch(const char* reject_code) {
    handover_contract_reject_count_++;
    adoption_noop_count_++;
    const char* code = (reject_code != nullptr && strlen(reject_code) > 0) ? reject_code : "UNKNOWN";
    strncpy(last_handover_contract_reject_code_, code, sizeof(last_handover_contract_reject_code_) - 1);
    last_handover_contract_reject_code_[sizeof(last_handover_contract_reject_code_) - 1] = '\0';
    LOG_W(TAG, String("[SAFETY-P4] ACK contract reject: code=") +
               String(code));
    logAuthorityCounters(this,
                         offline_enter_count_,
                         adopting_enter_count_,
                         adoption_noop_count_,
                         adoption_delta_count_,
                         handover_abort_count_,
                         handover_contract_reject_count_,
                         active_handover_epoch_,
                         handover_completed_epoch_);
}

void OfflineModeManager::onEmergencyStop() {
    LOG_W(TAG, "[SAFETY-P4] Emergency stop - offline mode cleared");
    storeMode(OfflineMode::ONLINE);
    disconnect_timestamp_ms_ = 0;
    adoption_started_ms_ = 0;
    active_handover_epoch_ = 0;
    handover_completed_epoch_ = 0;
    strncpy(last_handover_contract_reject_code_, "NONE", sizeof(last_handover_contract_reject_code_) - 1);
    last_handover_contract_reject_code_[sizeof(last_handover_contract_reject_code_) - 1] = '\0';

    // Reset all rule states
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        offline_rules_[i].is_active      = false;
        offline_rules_[i].server_override = false;
    }
}

// ============================================
// LOOP-INTEGRATION
// ============================================

void OfflineModeManager::checkDelayTimer() {
    if (loadMode() == OfflineMode::ADOPTING) {
        if (adoption_started_ms_ > 0 &&
            (millis() - adoption_started_ms_) >= ADOPTION_SETTLE_MS) {
            finalizeAdoptingMode();
        }
        return;
    }

    if (loadMode() != OfflineMode::DISCONNECTED) {
        return;
    }

    if (disconnect_timestamp_ms_ == 0) {
        return;
    }

    if (millis() - disconnect_timestamp_ms_ >= OFFLINE_ACTIVATION_DELAY_MS) {
        activateOfflineMode();
    }
}

// Defense-in-Depth guard: calibration-required sensors store only ADC raw values
// (0-4095) in the ValueCache — applyLocalConversion() returns (float)raw_value for
// these types. Offline rule thresholds are in physical units (pH, mS/cm, %).
// Comparing ADC raw vs. physical threshold is meaningless and potentially dangerous.
// Server-side filter (config_builder.py) is the primary defense; this guard handles
// stale NVS data, manual config manipulation, or server-side bugs.
static bool requiresCalibration(const char* sensor_value_type) {
    // Canonical types — server normalizes aliases before building the config push,
    // but stale NVS data from pre-normalization firmware may still carry alias strings
    // such as "soil_moisture". Include all known aliases as defense-in-depth.
    return (strcmp(sensor_value_type, "ph") == 0 ||
            strcmp(sensor_value_type, "ec") == 0 ||
            strcmp(sensor_value_type, "moisture") == 0 ||
            strncmp(sensor_value_type, "soil", 4) == 0);
}

static bool isTimeWindowOnlyRule(const OfflineRule& rule) {
    return strcmp(rule.sensor_value_type, "__twindow_on") == 0 ||
           strcmp(rule.sensor_value_type, "__twindow_off") == 0;
}

static bool getTimeWindowTargetState(const OfflineRule& rule) {
    return strcmp(rule.sensor_value_type, "__twindow_on") == 0;
}

bool OfflineModeManager::isInsideTimeWindow(uint8_t now_h, uint8_t now_m,
                                             uint8_t start_h, uint8_t start_m,
                                             uint8_t end_h,   uint8_t end_m) {
    uint16_t now_mins   = (uint16_t)now_h * 60 + now_m;
    uint16_t start_mins = (uint16_t)start_h * 60 + start_m;
    uint16_t end_mins   = (uint16_t)end_h * 60 + end_m;
    if (start_mins <= end_mins) {
        return (now_mins >= start_mins && now_mins < end_mins);
    } else {
        return (now_mins >= start_mins || now_mins < end_mins);
    }
}

static String formatGpioUi(uint8_t g) {
    if (g == 255) {
        return String("255 (INVALID)");
    }
    return String(g);
}

static String formatOfflineRuleDetail(uint8_t idx, const OfflineRule& r) {
    bool heat = (r.activate_below != 0.0f || r.deactivate_above != 0.0f);
    bool cool = (r.activate_above != 0.0f || r.deactivate_below != 0.0f);
    const char* mode = "NONE";
    if (heat && cool) {
        mode = "HEAT+COOL";
    } else if (heat) {
        mode = "HEATING";
    } else if (cool) {
        mode = "COOLING";
    }
    char tf_buf[48];
    if (r.time_filter_enabled) {
        snprintf(tf_buf, sizeof(tf_buf), "%02d:%02d-%02d:%02d %s",
                 r.start_hour, r.start_minute, r.end_hour, r.end_minute,
                 timezoneModeLabel(r.timezone_mode));
    } else {
        strcpy(tf_buf, "off");
    }
    // Pure time-window offline rules use sensor_gpio=255 as server-side sentinel (no physical sensor).
    String sensor_part;
    if (isTimeWindowOnlyRule(r) && r.sensor_gpio == 255) {
        sensor_part = "time-window only (sensor_gpio=255 placeholder)";
    } else {
        sensor_part = String("sensor GPIO ") + formatGpioUi(r.sensor_gpio);
    }
    return String("[CONFIG] Rule ") + String(idx) + ": " + String(r.sensor_value_type) +
           " (" + sensor_part + ") → actuator GPIO " + formatGpioUi(r.actuator_gpio) + " | " + mode +
           " | heat: below=" + String(r.activate_below, 2) + " above=" + String(r.deactivate_above, 2) +
           " | cool: above=" + String(r.activate_above, 2) + " below=" + String(r.deactivate_below, 2) +
           " | max_on_s=" + String(s_rule_max_on_seconds[idx]) +
           " cooldown_s=" + String(r.cooldown_seconds) +
           " | tf=" + tf_buf + " days_mask=0x" + String(r.days_of_week_mask, HEX) +
           " | enabled=" + String(r.enabled ? "1" : "0") +
           " is_active=" + String(r.is_active ? "1" : "0");
}

void OfflineModeManager::evaluateOfflineRules() {
    if (offline_rule_count_ == 0) {
        return;
    }

    // Current time snapshot — per rule converted to its configured timezone
    bool time_valid = timeManager.isSynchronized();
    time_t now_unix = 0;
    if (time_valid) {
        now_unix = timeManager.getUnixTimestamp();
        if (now_unix <= 0) {
            time_valid = false;
        }
    }

    // Boot-time summary: log once how many rules are filtered due to calibration requirement
    if (s_offline_first_eval) {
        s_offline_first_eval = false;
        uint8_t filtered = 0;
        String detail = "";
        for (uint8_t i = 0; i < offline_rule_count_; i++) {
            if (requiresCalibration(offline_rules_[i].sensor_value_type)) {
                filtered++;
                if (detail.length() > 0) {
                    detail += ", ";
                }
                detail += String(i) + ":" + String(offline_rules_[i].sensor_value_type);
            }
        }
        if (filtered > 0) {
            LOG_W(TAG, String("[SAFETY-P4] ") + String(filtered) + " of " +
                       String(offline_rule_count_) +
                       " rules filtered (calibration required) — " + detail +
                       " — actuators stay OFF.");
        }
    }

    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        OfflineRule& rule = offline_rules_[i];

        if (!rule.enabled) {
            if (!(s_eval_disabled_logged & (1u << i))) {
                s_eval_disabled_logged |= (1u << i);
                LOG_D(TAG, String("[SAFETY-P4] Rule ") + String(i) + ": SKIP (disabled)");
            }
            continue;
        }
        if (rule.server_override) {
            if (!(s_eval_override_logged & (1u << i))) {
                s_eval_override_logged |= (1u << i);
                LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": SKIP (server_override active, actuator GPIO " +
                           formatGpioUi(rule.actuator_gpio) + ")");
            }
            continue;
        }

        // Guard: ph/ec/moisture rules cannot be evaluated without server calibration.
        if (requiresCalibration(rule.sensor_value_type)) {
            if (!rule.is_active) {
                if (!(s_eval_cal_inactive_logged & (1u << i))) {
                    s_eval_cal_inactive_logged |= (1u << i);
                    LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) + ": SKIP (calibration required: " +
                                   String(rule.sensor_value_type) + ")");
                }
                continue;
            }
            bool off_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, false);
            if (!off_ok) {
                LOG_E(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": SAFETY - OFF failed for GPIO " + String(rule.actuator_gpio) +
                           " (actuator not in manager or control error). "
                           "No direct digitalWrite fallback due to unknown active-low state.");
            }
            rule.is_active = false;
            LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) + ": sensor '" +
                       String(rule.sensor_value_type) +
                       "' requires calibration - forcing actuator GPIO " +
                       String(rule.actuator_gpio) + " OFF (safe state)");
            continue;
        }

        // TIME FILTER: skip evaluation if outside active window
        if (rule.time_filter_enabled) {
            if (!time_valid) {
                if (!(s_eval_time_skip_logged & (1u << i))) {
                    s_eval_time_skip_logged |= (1u << i);
                    LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": time not synced — rule paused (time window cannot be verified)");
                }
                continue;  // NTP unknown: hold current state, do not activate or deactivate
            }

            uint8_t current_hour = 0;
            uint8_t current_minute = 0;
            uint8_t current_wday = 0;
            if (!getRuleLocalClock(rule, now_unix, &current_hour, &current_minute, &current_wday)) {
                if (!(s_eval_time_skip_logged & (1u << i))) {
                    s_eval_time_skip_logged |= (1u << i);
                    LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": invalid timestamp — rule paused (time window cannot be verified)");
                }
                continue;
            }

            uint8_t today_bit = (uint8_t)(1u << current_wday);
            if ((rule.days_of_week_mask & today_bit) == 0) {
                if (isTimeWindowOnlyRule(rule)) {
                    s_timewindow_fired_in_window[i] = false;
                    s_timewindow_on_deadline_ms[i] = 0;
                }
                if (rule.is_active) {
                    bool off_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, false);
                    if (!off_ok) {
                        LOG_E(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                                   ": SAFETY - weekday OFF failed for GPIO " +
                                   String(rule.actuator_gpio) +
                                   ". No direct digitalWrite fallback.");
                    }
                    rule.is_active = false;
                    saveOfflineRulesToNVS();
                }
                continue;
            }

            if (!isInsideTimeWindow(current_hour, current_minute,
                                            rule.start_hour, rule.start_minute,
                                            rule.end_hour, rule.end_minute)) {
                if (isTimeWindowOnlyRule(rule)) {
                    s_timewindow_fired_in_window[i] = false;
                    s_timewindow_on_deadline_ms[i] = 0;
                }
                if (rule.is_active) {
                    bool off_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, false);
                    if (!off_ok) {
                        LOG_E(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                                   ": SAFETY - time window OFF failed GPIO " +
                                   String(rule.actuator_gpio) +
                                   ". No direct digitalWrite fallback.");
                    }
                    rule.is_active = false;
                    saveOfflineRulesToNVS();
                    LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": time window inactive — GPIO " + String(rule.actuator_gpio) + " OFF");
                }
                continue;
            }
        }

        if (isTimeWindowOnlyRule(rule)) {
            bool desired_state = getTimeWindowTargetState(rule);
            uint16_t max_on_seconds = s_rule_max_on_seconds[i];
            if (!desired_state) {
                s_timewindow_fired_in_window[i] = false;
                s_timewindow_on_deadline_ms[i] = 0;
            }

            if (desired_state && max_on_seconds > 0) {
                if (rule.is_active) {
                    if (s_timewindow_on_deadline_ms[i] == 0) {
                        s_timewindow_on_deadline_ms[i] =
                            millis() + (static_cast<unsigned long>(max_on_seconds) * 1000UL);
                    }
                    if (millis() >= s_timewindow_on_deadline_ms[i]) {
                        bool off_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, false);
                        if (!off_ok) {
                            LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                                       ": max_on_seconds OFF failed for GPIO " +
                                       String(rule.actuator_gpio));
                            continue;
                        }
                        rule.is_active = false;
                        s_timewindow_on_deadline_ms[i] = 0;
                        s_timewindow_fired_in_window[i] = true;
                        if (!saveOfflineRulesToNVS()) {
                            LOG_E(TAG, String("[CONFIG] Rule ") + String(i) +
                                       ": failed to persist max_on_seconds OFF transition");
                        }
                        LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                                   ": max_on_seconds elapsed -> GPIO " +
                                   String(rule.actuator_gpio) + " OFF");
                    }
                    continue;
                }

                if (s_timewindow_fired_in_window[i]) {
                    continue;  // One-shot per active time window.
                }
            }

            if (desired_state != rule.is_active) {
                bool ctrl_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, desired_state);
                if (!ctrl_ok) {
                    LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": time-window-only control failed for GPIO " +
                               String(rule.actuator_gpio) + " (desired=" +
                               (desired_state ? "ON" : "OFF") + ")");
                    continue;
                }
                rule.is_active = desired_state;
                if (desired_state && max_on_seconds > 0) {
                    s_timewindow_on_deadline_ms[i] =
                        millis() + (static_cast<unsigned long>(max_on_seconds) * 1000UL);
                    s_timewindow_fired_in_window[i] = false;
                } else if (!desired_state) {
                    s_timewindow_on_deadline_ms[i] = 0;
                }
                if (!saveOfflineRulesToNVS()) {
                    LOG_E(TAG, String("[CONFIG] Rule ") + String(i) +
                               ": failed to persist time-window-only state in blob-v3");
                }
                LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": time-window-only -> GPIO " + String(rule.actuator_gpio) +
                           (desired_state ? " ON" : " OFF"));
            }
            continue;
        }

        float val = sensorManager.getSensorValue(rule.sensor_gpio, rule.sensor_value_type);

        if (isnan(val)) {
            warmup_valid_samples_[i] = 0;
            if (!s_eval_prev_nan[i]) {
                s_eval_prev_nan[i] = true;
                LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": SKIP (sensor value NaN/unavailable) — " + String(rule.sensor_value_type) +
                           " GPIO " + formatGpioUi(rule.sensor_gpio));
            }
            continue;
        }
        s_eval_prev_nan[i] = false;

        if (warmup_valid_samples_[i] < OFFLINE_WARMUP_VALID_SAMPLES) {
            // AUT-734 C3: val==0.0f guards against spurious zero readings from
            // getSensorValue(). Analog probes are already blocked upstream by
            // AUT-726 (raw==0→NaN) and requiresCalibration(); 0.0f here would
            // indicate a non-calibration sensor (e.g. DS18B20) reading exactly 0°C,
            // which is below greenhouse operating range and treated as suspect.
            if (!isnan(val) && val != 0.0f) warmup_valid_samples_[i]++;
            if (warmup_valid_samples_[i] < OFFLINE_WARMUP_VALID_SAMPLES) {
                LOG_D(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": warmup gate active (" + String(warmup_valid_samples_[i]) +
                           "/" + String(OFFLINE_WARMUP_VALID_SAMPLES) + ")");
                continue;
            }
            LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                       ": warmup gate passed (" + String(OFFLINE_WARMUP_VALID_SAMPLES) + " valid samples)");
        }

        bool new_state = rule.is_active;

        // Heating mode: activate_below / deactivate_above
        bool has_heating = (rule.activate_below != 0.0f || rule.deactivate_above != 0.0f);
        if (has_heating) {
            if (!rule.is_active && val < rule.activate_below) {
                new_state = true;
            }
            if (rule.is_active && val > rule.deactivate_above) {
                new_state = false;
            }
        }

        // Cooling mode: activate_above / deactivate_below
        bool has_cooling = (rule.activate_above != 0.0f || rule.deactivate_below != 0.0f);
        if (has_cooling) {
            if (!rule.is_active && val > rule.activate_above) {
                new_state = true;
            }
            if (rule.is_active && val < rule.deactivate_below) {
                new_state = false;
            }
        }

        const char* mode_lbl = "UNKNOWN";
        if (has_cooling && !has_heating) {
            mode_lbl = "COOLING";
        } else if (has_heating && !has_cooling) {
            mode_lbl = "HEATING";
        } else if (has_heating && has_cooling) {
            mode_lbl = "HEAT+COOL";
        }

        // max_on_seconds gate: force OFF if rule is currently ON and max runtime exceeded.
        // s_timewindow_on_deadline_ms[i] holds the last-activation timestamp for sensor rules.
        // Do NOT reset it here — cooldown gate reads it after the forced OFF.
        if (rule.is_active && s_rule_max_on_seconds[i] > 0) {
            unsigned long last_ms = s_timewindow_on_deadline_ms[i];
            if (last_ms != 0) {
                unsigned long elapsed_ms = millis() - last_ms;
                unsigned long max_on_ms = static_cast<unsigned long>(s_rule_max_on_seconds[i]) * 1000UL;
                if (elapsed_ms >= max_on_ms) {
                    LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": max_on_seconds elapsed (" + String(elapsed_ms / 1000) +
                               "s/" + String(s_rule_max_on_seconds[i]) + "s) → GPIO " +
                               formatGpioUi(rule.actuator_gpio) + " OFF");
                    new_state = false;
                }
            }
        }

        // Cooldown gate: block ON-transitions within the configured cooldown period.
        // 0 sentinel = never activated → first transition always allowed.
        // Uses s_timewindow_on_deadline_ms[i] (mutual exclusion: sensor rules never set deadline).
        if (new_state && !rule.is_active && rule.cooldown_seconds > 0) {
            unsigned long last_ms = s_timewindow_on_deadline_ms[i];
            if (last_ms != 0) {
                unsigned long elapsed_ms = millis() - last_ms;
                unsigned long cooldown_ms = static_cast<unsigned long>(rule.cooldown_seconds) * 1000UL;
                if (elapsed_ms < cooldown_ms) {
                    LOG_D(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                               ": cooldown active (" + String(elapsed_ms / 1000) +
                               "s/" + String(rule.cooldown_seconds) + "s)");
                    continue;
                }
            }
        }

        if (new_state != rule.is_active) {
            bool ctrl_ok = actuatorManager.controlActuatorBinary(rule.actuator_gpio, new_state);
            if (!ctrl_ok && !new_state) {
                LOG_E(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": SAFETY - binary OFF failed for GPIO " + String(rule.actuator_gpio) +
                           ". No direct digitalWrite fallback due to unknown active-low state.");
            }
            if (!ctrl_ok) {
                LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": could not set GPIO " + String(rule.actuator_gpio) +
                           " to " + (new_state ? "ON" : "OFF") +
                           " — keeping previous rule state");
                continue;
            }

            rule.is_active = new_state;
            if (new_state) {
                s_timewindow_on_deadline_ms[i] = millis();
            }
            LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) + " " +
                       (new_state ? "TRIGGERED" : "RELEASED") + " [" + mode_lbl + "]: " +
                       String(rule.sensor_value_type) + "=" + String(val, 2) + " → GPIO " +
                       formatGpioUi(rule.actuator_gpio) + " " + (new_state ? "ON" : "OFF") +
                       " | h:" + String(rule.activate_below, 1) + "/" + String(rule.deactivate_above, 1) +
                       " c:" + String(rule.activate_above, 1) + "/" + String(rule.deactivate_below, 1));

            // Persist state changes via the single blob-v5 schema.
            // This avoids mixed persistence paths (legacy key vs blob) after reboot.
            if (!saveOfflineRulesToNVS()) {
                LOG_E(TAG, String("[CONFIG] Rule ") + String(i) +
                           ": failed to persist is_active in blob-v5");
            }
        }
    }
}

// ============================================
// CONFIG
// ============================================

bool OfflineModeManager::parseOfflineRules(JsonObject obj) {
    if (!obj.containsKey("offline_rules")) {
        // Field absent — keep existing rules
        return true;
    }

    JsonArray rules = obj["offline_rules"].as<JsonArray>();
    if (rules.isNull()) {
        return false;
    }

    if (rules.size() == 0) {
        // Explicit empty array → clear all rules
        offline_rule_count_ = 0;
        if (storageManager.beginNamespace("offline", false)) {
            storageManager.clearNamespace();
            storageManager.endNamespace();
        }
        resetOfflineEvalLogState();
        LOG_I(TAG, "[CONFIG] Received 0 offline rules — cleared NVS");
        return true;
    }

    if (rules.size() > MAX_OFFLINE_RULES) {
        LOG_W(TAG, String("[CONFIG] offline_rules: ") + String(rules.size()) +
                   " in payload, using first " + String(MAX_OFFLINE_RULES) + " (MAX_OFFLINE_RULES)");
    }

    memset(s_rule_max_on_seconds, 0, sizeof(s_rule_max_on_seconds));

    OfflineRule previous_rules[MAX_OFFLINE_RULES];
    uint8_t     previous_count = offline_rule_count_;
    memcpy(previous_rules, offline_rules_, sizeof(OfflineRule) * previous_count);

    uint8_t count = static_cast<uint8_t>(
        rules.size() < MAX_OFFLINE_RULES ? rules.size() : MAX_OFFLINE_RULES
    );

    for (uint8_t i = 0; i < count; i++) {
        JsonObject r = rules[i];
        offline_rules_[i].enabled        = true;
        offline_rules_[i].actuator_gpio  = r["actuator_gpio"] | static_cast<uint8_t>(255);
        offline_rules_[i].sensor_gpio    = r["sensor_gpio"] | static_cast<uint8_t>(255);
        const char* svt                  = r["sensor_value_type"] | "";
        strncpy(offline_rules_[i].sensor_value_type, svt, 20);
        offline_rules_[i].sensor_value_type[20] = '\0';
        if (strlen(svt) > 20) {
            LOG_W(TAG, String("[CONFIG] sensor_value_type truncated: '") + svt + "' -> '" +
                       String(offline_rules_[i].sensor_value_type) + "'");
            offline_rules_[i].enabled = false;
        }
        offline_rules_[i].activate_below    = r["activate_below"] | 0.0f;
        offline_rules_[i].deactivate_above  = r["deactivate_above"] | 0.0f;
        offline_rules_[i].activate_above    = r["activate_above"] | 0.0f;
        offline_rules_[i].deactivate_below  = r["deactivate_below"] | 0.0f;
        // is_active: use server-provided state if present, otherwise preserve existing
        // value (from NVS load at boot). Prevents config push from resetting a running
        // hysteresis cycle — especially important when server reconnects after a reboot.
        if (r.containsKey("current_state_active")) {
            offline_rules_[i].is_active = r["current_state_active"].as<bool>();
            LOG_D(TAG, String("[CONFIG] Rule ") + String(i) + ": is_active=" +
                       (offline_rules_[i].is_active ? "true" : "false") + " (from server push)");
        }
        // else: preserve existing value (NVS-loaded or false on first boot)
        offline_rules_[i].server_override   = false;

        // time_filter: default disabled (backward compat — old server has no time_filter field)
        offline_rules_[i].time_filter_enabled = false;
        offline_rules_[i].start_hour   = 0;
        offline_rules_[i].start_minute = 0;
        offline_rules_[i].end_hour     = 0;
        offline_rules_[i].end_minute   = 0;
        offline_rules_[i].days_of_week_mask = 0x7F;  // Backward compat: all days active
        offline_rules_[i].timezone_mode = static_cast<uint8_t>(OfflineRuleTimezone::UTC);
        s_rule_max_on_seconds[i] = 0;
        if (r.containsKey("time_filter")) {
            JsonObject tf = r["time_filter"];
            offline_rules_[i].time_filter_enabled = tf["enabled"] | false;
            if (offline_rules_[i].time_filter_enabled) {
                offline_rules_[i].start_hour   = tf["start_hour"]   | (uint8_t)0;
                offline_rules_[i].start_minute = tf["start_minute"] | (uint8_t)0;
                offline_rules_[i].end_hour     = tf["end_hour"]     | (uint8_t)0;
                offline_rules_[i].end_minute   = tf["end_minute"]   | (uint8_t)0;
                offline_rules_[i].days_of_week_mask = tf["days_of_week_mask"] | (uint8_t)0x7F;
                const char* timezone_name = tf["timezone"] | "UTC";
                offline_rules_[i].timezone_mode = parseTimezoneMode(timezone_name);
                if (offline_rules_[i].timezone_mode == static_cast<uint8_t>(OfflineRuleTimezone::UTC) &&
                    timezone_name != nullptr && strcmp(timezone_name, "UTC") != 0) {
                    LOG_W(TAG, String("[CONFIG] Rule ") + String(i) +
                               ": unsupported timezone '" + String(timezone_name) +
                               "' - fallback to UTC");
                }
            }
        }
        unsigned long max_on_raw = r["max_on_seconds"] | 0UL;
        if (max_on_raw > 65535UL) {
            max_on_raw = 65535UL;
        }
        s_rule_max_on_seconds[i] = static_cast<uint16_t>(max_on_raw);
        offline_rules_[i].max_on_seconds = static_cast<uint16_t>(max_on_raw);

        unsigned long cooldown_raw = r["cooldown_seconds"] | 0UL;
        if (cooldown_raw > 65535UL) {
            cooldown_raw = 65535UL;
        }
        offline_rules_[i].cooldown_seconds = static_cast<uint16_t>(cooldown_raw);
    }

    offline_rule_count_ = count;

    uint8_t changed = 0, unchanged = 0;
    for (uint8_t i = 0; i < count; i++) {
        if (i < previous_count &&
            memcmp(&previous_rules[i], &offline_rules_[i], sizeof(OfflineRule)) == 0) {
            unchanged++;
        } else {
            changed++;
        }
    }

    LOG_I(TAG, String("[CONFIG] Config push: ") + String(count) + " offline rules (changed: " +
               String(changed) + ", unchanged: " + String(unchanged) + ")");
    for (uint8_t i = 0; i < count; i++) {
        LOG_I(TAG, formatOfflineRuleDetail(i, offline_rules_[i]));
    }
    LOG_I(TAG, "[CONFIG] offline_rules config push applied");

    resetOfflineEvalLogState();
    return saveOfflineRulesToNVS();
}

void OfflineModeManager::logOfflineRulesSummary(const char* source_label) {
    if (offline_rule_count_ == 0) {
        LOG_I(TAG, String("[CONFIG] ===== OFFLINE RULES (0 ") + source_label + ") =====");
        return;
    }
    LOG_I(TAG, String("[CONFIG] ===== OFFLINE RULES (") + String(offline_rule_count_) + " from " +
               source_label + ") =====");
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        LOG_I(TAG, formatOfflineRuleDetail(i, offline_rules_[i]));
    }
    LOG_I(TAG, "[CONFIG] ================================================");
}

void OfflineModeManager::loadOfflineRulesFromNVS() {
    memset(s_rule_max_on_seconds, 0, sizeof(s_rule_max_on_seconds));

    nvs_handle_t handle;
    esp_err_t err = nvs_open("offline", NVS_READONLY, &handle);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        offline_rule_count_ = 0;
        LOG_D(TAG, "[CONFIG] NVS namespace 'offline' not found - no rules loaded");
        return;
    }
    if (err != ESP_OK) {
        offline_rule_count_ = 0;
        LOG_E(TAG, "[CONFIG] nvs_open failed - no rules loaded");
        return;
    }

    uint8_t ver = 0;
    nvs_get_u8(handle, "ofr_ver", &ver);  // ESP_ERR_NVS_NOT_FOUND → ver stays 0
    nvs_close(handle);

    // ── MIGRATION PATH (ver == 0 or key absent) ──────────────────────────────
    if (ver == 0) {
        if (!storageManager.beginNamespace("offline", true)) {
            offline_rule_count_ = 0;
            LOG_D(TAG, "[CONFIG] NVS namespace 'offline' not readable - no rules loaded");
            return;
        }

        offline_rule_count_ = storageManager.getUInt8("ofr_count", 0);
        if (offline_rule_count_ > MAX_OFFLINE_RULES) offline_rule_count_ = MAX_OFFLINE_RULES;

        char key[16];
        for (uint8_t i = 0; i < offline_rule_count_; i++) {
            snprintf(key, sizeof(key), "ofr_%d_en", i);
            offline_rules_[i].enabled = storageManager.getUInt8(key, 0) != 0;

            snprintf(key, sizeof(key), "ofr_%d_agpio", i);
            offline_rules_[i].actuator_gpio = storageManager.getUInt8(key, 255);

            snprintf(key, sizeof(key), "ofr_%d_sgpio", i);
            offline_rules_[i].sensor_gpio = storageManager.getUInt8(key, 255);

            snprintf(key, sizeof(key), "ofr_%d_svtyp", i);
            String svtyp = storageManager.getStringObj(key, "");
            strncpy(offline_rules_[i].sensor_value_type, svtyp.c_str(), 20);
            offline_rules_[i].sensor_value_type[20] = '\0';
            if (svtyp.length() > 20) {
                LOG_W(TAG, String("[CONFIG] Migration: sensor_value_type truncated: '") + svtyp + "'");
                offline_rules_[i].enabled = false;
            }

            snprintf(key, sizeof(key), "ofr_%d_actb", i);
            offline_rules_[i].activate_below = storageManager.getFloat(key, 0.0f);

            snprintf(key, sizeof(key), "ofr_%d_deaa", i);
            offline_rules_[i].deactivate_above = storageManager.getFloat(key, 0.0f);

            snprintf(key, sizeof(key), "ofr_%d_acta", i);
            offline_rules_[i].activate_above = storageManager.getFloat(key, 0.0f);

            snprintf(key, sizeof(key), "ofr_%d_deab", i);
            offline_rules_[i].deactivate_below = storageManager.getFloat(key, 0.0f);

            snprintf(key, sizeof(key), "ofr_%d_state", i);
            offline_rules_[i].is_active = storageManager.keyExists(key) &&
                                           (storageManager.getUInt8(key, 0) != 0);
            offline_rules_[i].server_override   = false;
            offline_rules_[i].time_filter_enabled = false;
            offline_rules_[i].start_hour   = 0;
            offline_rules_[i].start_minute = 0;
            offline_rules_[i].end_hour     = 0;
            offline_rules_[i].end_minute   = 0;
            offline_rules_[i].days_of_week_mask = 0x7F;
            offline_rules_[i].timezone_mode = static_cast<uint8_t>(OfflineRuleTimezone::UTC);
        }
        storageManager.endNamespace();

        // Force blob write even if offline_rule_count_==0 (persists ofr_ver=3)
        shadow_rule_count_ = UINT8_MAX;
        saveOfflineRulesToNVS();
        _deleteOldIndividualKeys();
        LOG_I(TAG, String("[CONFIG] NVS migrated ") + String(offline_rule_count_) +
                   " rules from individual keys to blob format");
        logOfflineRulesSummary("NVS migration");
        return;
    }

    // ── BLOB LOAD PATH (ver == 1/2/3/4) ──────────────────────────────────────
    if (ver != 1 && ver != 2 && ver != 3 && ver != 4 && ver != 5) {
        offline_rule_count_ = 0;
        LOG_E(TAG, String("[CONFIG] Unsupported offline rule blob version: ") + String(ver));
        return;
    }

    nvs_handle_t h;
    err = nvs_open("offline", NVS_READONLY, &h);
    if (err != ESP_OK) {
        offline_rule_count_ = 0;
        LOG_E(TAG, "[CONFIG] nvs_open (blob load) failed - no rules loaded");
        return;
    }

    uint8_t stored_count = 0;
    nvs_get_u8(h, "ofr_count", &stored_count);
    if (stored_count > MAX_OFFLINE_RULES) stored_count = MAX_OFFLINE_RULES;

    const size_t stored_rule_size    = (ver >= 5) ? sizeof(OfflineRule)
                                   : (ver >= 3) ? OFFLINE_RULE_BLOB_V4_RULE_SIZE
                                   : sizeof(OfflineRuleBlobV2);
    const size_t rules_size          = stored_count * stored_rule_size;
    const size_t expected_blob_size  = rules_size + 1;
    size_t actual_size = 0;
    esp_err_t blob_err = nvs_get_blob(h, "ofr_blob", nullptr, &actual_size);

    if (blob_err != ESP_OK || actual_size != expected_blob_size) {
        nvs_close(h);
        offline_rule_count_ = 0;
        LOG_E(TAG, String("[CONFIG] NVS blob size mismatch: expected=") +
                   String(expected_blob_size) + " actual=" + String(actual_size) +
                   " - waiting for config push");
        return;
    }

    uint8_t blob[MAX_OFFLINE_RULES * sizeof(OfflineRule) + 1];
    blob_err = nvs_get_blob(h, "ofr_blob", blob, &actual_size);
    nvs_close(h);

    if (blob_err != ESP_OK) {
        offline_rule_count_ = 0;
        LOG_E(TAG, "[CONFIG] nvs_get_blob failed - waiting for config push");
        return;
    }

    // CRC8 integrity check
    const uint8_t stored_crc = blob[rules_size];
    const uint8_t calc_crc   = crc8(blob, rules_size);
    if (calc_crc != stored_crc) {
        offline_rule_count_ = 0;
        LOG_E(TAG, String("[CONFIG] NVS CRC8 mismatch (stored=") + String(stored_crc) +
                   " calc=" + String(calc_crc) + ") - waiting for config push");
        return;
    }

    memset(offline_rules_, 0, sizeof(offline_rules_));
    if (ver >= 5) {
        memcpy(offline_rules_, blob, rules_size);
    } else if (ver >= 3) {
        // v3/v4: sensor_value_type[24] with float at offset 28; v5 has [21] with float at offset 24.
        // Layouts differ despite equal sizeof (56) — field-by-field copy required.
        for (uint8_t i = 0; i < stored_count; i++) {
            OfflineRuleBlobV4 v4;
            memcpy(&v4, blob + i * sizeof(OfflineRuleBlobV4), sizeof(OfflineRuleBlobV4));
            offline_rules_[i].enabled            = v4.enabled;
            offline_rules_[i].actuator_gpio       = v4.actuator_gpio;
            offline_rules_[i].sensor_gpio         = v4.sensor_gpio;
            strncpy(offline_rules_[i].sensor_value_type, v4.sensor_value_type, 20);
            offline_rules_[i].sensor_value_type[20] = '\0';
            offline_rules_[i].activate_below      = v4.activate_below;
            offline_rules_[i].deactivate_above    = v4.deactivate_above;
            offline_rules_[i].activate_above      = v4.activate_above;
            offline_rules_[i].deactivate_below    = v4.deactivate_below;
            offline_rules_[i].is_active           = v4.is_active;
            offline_rules_[i].server_override     = false;
            offline_rules_[i].time_filter_enabled = v4.time_filter_enabled;
            offline_rules_[i].start_hour          = v4.start_hour;
            offline_rules_[i].start_minute        = v4.start_minute;
            offline_rules_[i].end_hour            = v4.end_hour;
            offline_rules_[i].end_minute          = v4.end_minute;
            offline_rules_[i].days_of_week_mask   = v4.days_of_week_mask;
            offline_rules_[i].timezone_mode       = v4.timezone_mode;
            offline_rules_[i].max_on_seconds      = v4.max_on_seconds;
            offline_rules_[i].cooldown_seconds    = 0;
        }
    } else {
        // v1/v2: sensor_value_type[24] with float at offset 28; field-by-field copy required.
        for (uint8_t i = 0; i < stored_count; i++) {
            OfflineRuleBlobV2 v2;
            memcpy(&v2, blob + i * sizeof(OfflineRuleBlobV2), sizeof(OfflineRuleBlobV2));
            offline_rules_[i].enabled            = v2.enabled;
            offline_rules_[i].actuator_gpio       = v2.actuator_gpio;
            offline_rules_[i].sensor_gpio         = v2.sensor_gpio;
            strncpy(offline_rules_[i].sensor_value_type, v2.sensor_value_type, 20);
            offline_rules_[i].sensor_value_type[20] = '\0';
            offline_rules_[i].activate_below      = v2.activate_below;
            offline_rules_[i].deactivate_above    = v2.deactivate_above;
            offline_rules_[i].activate_above      = v2.activate_above;
            offline_rules_[i].deactivate_below    = v2.deactivate_below;
            offline_rules_[i].is_active           = v2.is_active;
            offline_rules_[i].server_override     = false;
            offline_rules_[i].time_filter_enabled = v2.time_filter_enabled;
            offline_rules_[i].start_hour          = v2.start_hour;
            offline_rules_[i].start_minute        = v2.start_minute;
            offline_rules_[i].end_hour            = v2.end_hour;
            offline_rules_[i].end_minute          = v2.end_minute;
            offline_rules_[i].days_of_week_mask   = v2.days_of_week_mask;
            offline_rules_[i].timezone_mode       = static_cast<uint8_t>(OfflineRuleTimezone::UTC);
            offline_rules_[i].max_on_seconds      = 0;
            offline_rules_[i].cooldown_seconds    = 0;
        }
    }
    offline_rule_count_ = stored_count;

    // server_override is transient — never restore from NVS
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        offline_rules_[i].server_override = false;
    }

    // Restore max_on_seconds from the persisted struct (v4+).
    // For v1–v3 blobs the field was struct trailing padding (value 0) → correct default.
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        s_rule_max_on_seconds[i] = offline_rules_[i].max_on_seconds;
    }

    bool needs_resave = false;
    if (ver == 1) {
        // v1 used the same byte as _reserved (always 0 in previous firmware).
        // Without migration, all rules would silently have days mask 0x00 (= never active).
        for (uint8_t i = 0; i < offline_rule_count_; i++) {
            offline_rules_[i].days_of_week_mask = 0x7F;
        }
        needs_resave = true;
        LOG_I(TAG, "[CONFIG] Migrated offline rule blob v1: days_of_week_mask defaulted to 0x7F");
    }
    if (ver <= 2) {
        needs_resave = true;  // Persist timezone_mode (v3 schema)
    }
    if (ver <= 3) {
        needs_resave = true;  // Persist max_on_seconds (v4 schema)
    }
    if (ver <= 4) {
        needs_resave = true;  // Persist cooldown_seconds (v5 schema)
    }

    if (needs_resave) {
        shadow_rule_count_ = UINT8_MAX;  // force save with current schema
        saveOfflineRulesToNVS();
        LOG_I(TAG, String("[CONFIG] Migrated offline rule blob to v5 (cooldown_seconds persisted, was v") +
                   String(ver) + ")");
    }

    memcpy(offline_rules_shadow_, offline_rules_, offline_rule_count_ * sizeof(OfflineRule));
    shadow_rule_count_ = offline_rule_count_;

    logOfflineRulesSummary("NVS");
}

// ============================================
// AUT-66: COVERING RULE QUERY
// ============================================

bool OfflineModeManager::hasCoveringRule(uint8_t actuator_gpio) const {
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        if (offline_rules_[i].enabled && offline_rules_[i].actuator_gpio == actuator_gpio) {
            return true;
        }
    }
    return false;
}

// ============================================
// SERVER-OVERRIDE
// ============================================

void OfflineModeManager::setServerOverride(uint8_t actuator_gpio) {
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        if (offline_rules_[i].actuator_gpio == actuator_gpio) {
            if (!offline_rules_[i].server_override) {  // Guard: log only on first override
                offline_rules_[i].server_override = true;
                LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": server_override (actuator GPIO " + formatGpioUi(actuator_gpio) + ")");
            }
        }
    }
}

// ============================================
// PRIVATE HELPERS
// ============================================

void OfflineModeManager::activateOfflineMode() {
    unsigned long grace_ms = millis() - disconnect_timestamp_ms_;
    LOG_W(TAG, String("[SAFETY-P4] Grace period elapsed (") + String(grace_ms) +
               "ms) → OFFLINE_ACTIVE");
    storeMode(OfflineMode::OFFLINE_ACTIVE);
    offline_enter_count_++;
    memset(warmup_valid_samples_, 0, sizeof(warmup_valid_samples_));

    // Current time snapshot — converted per rule timezone at offline entry
    bool time_valid = timeManager.isSynchronized();
    time_t now_unix = 0;
    if (time_valid) {
        now_unix = timeManager.getUnixTimestamp();
        if (now_unix <= 0) {
            time_valid = false;
        }
    }

    // Initialize is_active flags from actual hardware state.
    // Without this, all rules start at is_active=false regardless of the real actuator
    // state at the moment of broker disconnect. If the server had an actuator ON when
    // the broker disconnected, the first P4 evaluation cycle would see is_active=false,
    // evaluate both thresholds as "not yet active", and potentially command the actuator
    // to a wrong state before any sensor reading confirms the need.
    if (offline_rule_count_ > 0 && actuatorManager.isInitialized()) {
        for (uint8_t i = 0; i < offline_rule_count_; i++) {
            if (!offline_rules_[i].enabled || offline_rules_[i].actuator_gpio == 255) {
                continue;
            }
            ActuatorConfig cfg = actuatorManager.getActuatorConfig(offline_rules_[i].actuator_gpio);

            // Extended diagnostic: log all three state sources simultaneously.
            // Distinguishes root causes:
            //   Ursache A — cfg.current_state wrong (driver getConfig() bug)
            //   Ursache B — race condition (cfg.current_state has stale value)
            //   Ursache C — cfg.gpio==255 (GPIO mismatch, actuator not in ActuatorManager)
            LOG_D(TAG, String("[SAFETY-P4-DIAG] Rule ") + String(i) +
                       ": rule.actuator_gpio=" + String(offline_rules_[i].actuator_gpio) +
                       ", cfg.gpio=" + String(cfg.gpio) + " (255=not found)" +
                       ", cfg.current_state=" + (cfg.current_state ? "ON" : "OFF") +
                       ", cfg.default_state=" + (cfg.default_state ? "ON" : "OFF") +
                       ", digitalRead=" + String(digitalRead(offline_rules_[i].actuator_gpio)));

            bool current_hardware_state;
            if (cfg.gpio != 255) {
                current_hardware_state = cfg.current_state;
            } else {
                // Ursache C fallback: actuator GPIO not found in ActuatorManager.
                // Read hardware pin directly — physical pin state cannot lie.
                int pin_val = digitalRead(offline_rules_[i].actuator_gpio);
                current_hardware_state = (pin_val == HIGH);
                LOG_W(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                           ": actuator GPIO " + String(offline_rules_[i].actuator_gpio) +
                           " not found in ActuatorManager — digitalRead=" +
                           String(pin_val) + " used as fallback");
            }

            // TIME FILTER: if time window inactive at offline entry, force actuator OFF
            if (offline_rules_[i].time_filter_enabled && time_valid) {
                uint8_t current_hour = 0;
                uint8_t current_minute = 0;
                uint8_t ignored_wday = 0;
                if (getRuleLocalClock(offline_rules_[i], now_unix, &current_hour, &current_minute, &ignored_wday) &&
                    !isInsideTimeWindow(current_hour, current_minute,
                                        offline_rules_[i].start_hour, offline_rules_[i].start_minute,
                                        offline_rules_[i].end_hour, offline_rules_[i].end_minute)) {
                    offline_rules_[i].is_active = false;
                    if (current_hardware_state) {
                        actuatorManager.controlActuatorBinary(offline_rules_[i].actuator_gpio, false);
                        LOG_I(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                                   ": time window inactive at offline entry — GPIO " +
                                   String(offline_rules_[i].actuator_gpio) + " OFF");
                    }
                    continue;
                }
            }

            offline_rules_[i].is_active = current_hardware_state;
            LOG_D(TAG, String("[SAFETY-P4] Rule ") + String(i) +
                       ": actuator GPIO " + String(offline_rules_[i].actuator_gpio) +
                       " is_active initialized from hardware -> " +
                       (offline_rules_[i].is_active ? "ON" : "OFF"));
        }
    }

    String gpio_list = "";
    for (uint8_t gi = 0; gi < offline_rule_count_; gi++) {
        if (offline_rules_[gi].enabled && offline_rules_[gi].actuator_gpio != 255) {
            if (gpio_list.length() > 0) {
                gpio_list += ",";
            }
            gpio_list += String(offline_rules_[gi].actuator_gpio);
        }
    }
    LOG_W(TAG, String("[SAFETY-P4] Offline mode ACTIVE — rules=") + String(offline_rule_count_) +
               " actuators GPIO [" + gpio_list + "]");
    if (offline_rule_count_ == 0) {
        // Fix 1a/1b should already have set safe state on disconnect,
        // but confirm here as defense-in-depth.
        if (actuatorManager.isInitialized()) {
            actuatorManager.setAllActuatorsToSafeState();
        }
        LOG_W(TAG, "[SAFETY-P4] OFFLINE_ACTIVE with 0 rules — confirming safe state");
    }
    // If rules > 0: nothing — Safety-Task evaluates in <5s automatically
    logAuthorityCounters(this,
                         offline_enter_count_,
                         adopting_enter_count_,
                         adoption_noop_count_,
                         adoption_delta_count_,
                         handover_abort_count_,
                             handover_contract_reject_count_,
                         active_handover_epoch_,
                         handover_completed_epoch_);
}

void OfflineModeManager::enterAdoptingMode() {
    storeMode(OfflineMode::ADOPTING);
    disconnect_timestamp_ms_ = 0;
    adoption_started_ms_ = millis();
    adopting_enter_count_++;

    // Push local actuator IST state again right at ACK boundary so the server
    // can adopt without forcing a blind reset.
    if (actuatorManager.isInitialized()) {
        actuatorManager.publishAllActuatorStatus();
    }

    LOG_I(TAG, String("[SAFETY-P4] state RECONNECTING/OFFLINE_ACTIVE→ADOPTING (server ACK, epoch=") +
               String(active_handover_epoch_) + ")");
    logAuthorityCounters(this,
                         offline_enter_count_,
                         adopting_enter_count_,
                         adoption_noop_count_,
                         adoption_delta_count_,
                         handover_abort_count_,
                         handover_contract_reject_count_,
                         active_handover_epoch_,
                         handover_completed_epoch_);
}

void OfflineModeManager::finalizeAdoptingMode() {
    if (loadMode() != OfflineMode::ADOPTING) {
        return;
    }
    deactivateOfflineMode();
}

void OfflineModeManager::deactivateOfflineMode() {
    storeMode(OfflineMode::ONLINE);
    disconnect_timestamp_ms_ = 0;
    adoption_started_ms_ = 0;

    // Reset transient override state; keep physical actuator state untouched.
    // This prevents OFF intermezzo during reconnect adoption.
    for (uint8_t i = 0; i < offline_rule_count_; i++) {
        offline_rules_[i].server_override = false;
    }

    LOG_I(TAG, "[SAFETY-P4] state ADOPTING→ONLINE (adoption settled, no reconnect reset)");
}

bool OfflineModeManager::saveOfflineRulesToNVS() {
    // Change-detection: skip NVS write if nothing changed
    if (offline_rule_count_ == shadow_rule_count_ &&
        memcmp(offline_rules_, offline_rules_shadow_,
               offline_rule_count_ * sizeof(OfflineRule)) == 0) {
        LOG_D(TAG, "[CONFIG] NVS save skipped (offline rules unchanged)");
        return true;
    }

    // Build blob: raw rule bytes + CRC8 trailer
    const size_t rules_size = offline_rule_count_ * sizeof(OfflineRule);
    const size_t blob_size  = rules_size + 1;
    uint8_t blob[MAX_OFFLINE_RULES * sizeof(OfflineRule) + 1];
    memcpy(blob, offline_rules_, rules_size);
    blob[rules_size] = crc8(blob, rules_size);

    nvs_handle_t handle;
    esp_err_t err = nvs_open("offline", NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        LOG_E(TAG, String("[CONFIG] nvs_open failed for blob write: ") + esp_err_to_name(err));
        setPersistenceDrift("NVS_OPEN_FAILED");
        return false;
    }

    nvs_set_u8(handle, "ofr_count", offline_rule_count_);
    nvs_set_blob(handle, "ofr_blob", blob, blob_size);
    nvs_set_u8(handle, "ofr_ver", 5);

    err = nvs_commit(handle);
    nvs_close(handle);

    if (err != ESP_OK) {
        LOG_E(TAG, String("[CONFIG] nvs_commit failed: ") + esp_err_to_name(err));
        setPersistenceDrift("NVS_COMMIT_FAILED");
        return false;
    }

    memcpy(offline_rules_shadow_, offline_rules_, rules_size);
    shadow_rule_count_ = offline_rule_count_;
    clearPersistenceDrift();

    LOG_I(TAG, String("[CONFIG] Saved ") + String(offline_rule_count_) +
               " offline rules to NVS (blob v5, " + String(blob_size) + " bytes)");
    return true;
}

void OfflineModeManager::_deleteOldIndividualKeys() {
    if (!storageManager.beginNamespace("offline", false)) {
        LOG_W(TAG, "[CONFIG] _deleteOldIndividualKeys: cannot open namespace");
        return;
    }
    char key[16];
    static const char* const LEGACY_FIELDS[] = {
        "en", "agpio", "sgpio", "svtyp", "actb", "deaa", "acta", "deab", "state"
    };
    for (uint8_t i = 0; i < MAX_OFFLINE_RULES; i++) {
        for (const char* field : LEGACY_FIELDS) {
            snprintf(key, sizeof(key), "ofr_%d_%s", i, field);
            if (storageManager.keyExists(key)) {
                storageManager.eraseKey(key);
            }
        }
    }
    storageManager.endNamespace();
}
