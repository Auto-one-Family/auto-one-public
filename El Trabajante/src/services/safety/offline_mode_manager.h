#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <atomic>
#include "../../models/offline_rule.h"

// ============================================
// SAFETY-P4: Offline Mode Manager
// ============================================
// TM-authorized exception to Server-Centric rule.
// Precedent: SAFETY-P1 setAllActuatorsToSafeState.
//
// Implements a 4-state state machine for connectivity-aware
// offline hysteresis control. Activates after 30s without
// server ACK and evaluates rules every 5s.

enum class OfflineMode : uint8_t {
    ONLINE         = 0,  // Normal operation — server connected
    DISCONNECTED   = 1,  // Connectivity lost — 30s grace timer running
    OFFLINE_ACTIVE = 2,  // Grace period expired — local rules active
    RECONNECTING   = 3,  // Transport back — waiting for authoritative server ACK
    ADOPTING       = 4   // Server ACK received — state adoption/delta window before ONLINE
};

// Grace period before offline rules activate after disconnect
static constexpr unsigned long OFFLINE_ACTIVATION_DELAY_MS = 30000UL;

class OfflineModeManager {
public:
    static constexpr uint8_t OFFLINE_AUTHORITY_METRICS_SCHEMA_VERSION = 1;
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static OfflineModeManager& getInstance();

    OfflineModeManager(const OfflineModeManager&) = delete;
    OfflineModeManager& operator=(const OfflineModeManager&) = delete;

    // ============================================
    // STATE-MACHINE HOOKS
    // ============================================
    // Called when MQTT disconnects (Mechanism B hook + P4 delay timer start)
    void onDisconnect();

    // Called when MQTT reconnects successfully
    void onReconnect();

    // Called when heartbeat ACK received from server.
    // Contract is strict: handover_epoch must be present and > 0.
    void onServerAckReceived(uint32_t incoming_handover_epoch = 0);
    void onServerAckContractMismatch(const char* reject_code);
    bool validateServerAckContract(uint32_t incoming_handover_epoch, const char** reject_code = nullptr) const;

    // Called on emergency stop — resets to ONLINE, clears all rule states
    void onEmergencyStop();

    // ============================================
    // LOOP-INTEGRATION
    // ============================================
    // Check whether 30s delay has elapsed → transition to OFFLINE_ACTIVE
    void checkDelayTimer();

    // Evaluate all enabled offline rules (call every 5s when isOfflineActive())
    void evaluateOfflineRules();

    // ============================================
    // CONFIG
    // ============================================
    // Parse "offline_rules" array from config-push payload
    bool parseOfflineRules(JsonObject obj);

    // Load persisted rules from NVS namespace "offline"
    void loadOfflineRulesFromNVS();

    // One-shot boot / NVS summary block (call after loadOfflineRulesFromNVS)
    void logOfflineRulesSummary(const char* source_label);

    // ============================================
    // SERVER-OVERRIDE
    // ============================================
    // Mark actuator as server-controlled while offline — skip rule for that actuator
    void setServerOverride(uint8_t actuator_gpio);

    // ============================================
    // STATUS
    // ============================================
    bool isOfflineActive() const {
        OfflineMode mode = loadMode();
        return mode == OfflineMode::OFFLINE_ACTIVE || mode == OfflineMode::RECONNECTING;
    }
    bool isAdopting() const { return loadMode() == OfflineMode::ADOPTING; }
    OfflineMode getMode() const { return loadMode(); }
    uint8_t getOfflineRuleCount() const { return offline_rule_count_; }

    // AUT-66: Check whether an enabled offline rule covers this actuator GPIO
    bool hasCoveringRule(uint8_t actuator_gpio) const;
    uint32_t getOfflineEnterCount() const { return offline_enter_count_; }
    uint32_t getAdoptingEnterCount() const { return adopting_enter_count_; }
    uint32_t getAdoptionNoopCount() const { return adoption_noop_count_; }
    uint32_t getAdoptionDeltaCount() const { return adoption_delta_count_; }
    uint32_t getHandoverAbortCount() const { return handover_abort_count_; }
    uint32_t getHandoverContractRejectCount() const { return handover_contract_reject_count_; }
    uint32_t getActiveHandoverEpoch() const { return active_handover_epoch_; }
    uint32_t getHandoverCompletedEpoch() const { return handover_completed_epoch_; }
    const char* getLastHandoverContractRejectCode() const { return last_handover_contract_reject_code_; }
    bool isPersistenceDriftActive() const { return persistence_drift_active_; }
    uint32_t getPersistenceDriftCount() const { return persistence_drift_count_; }
    const char* getLastPersistenceDriftReason() const { return last_persistence_drift_reason_; }

private:
    OfflineModeManager() = default;
    ~OfflineModeManager() = default;

    // NVS persistence helpers
    bool saveOfflineRulesToNVS();
    void _deleteOldIndividualKeys();  // One-shot migration: removes legacy ofr_{i}_* keys
    void activateOfflineMode();
    void enterAdoptingMode();
    void finalizeAdoptingMode();
    void deactivateOfflineMode();
    void setPersistenceDrift(const char* reason);
    void clearPersistenceDrift();
    OfflineMode loadMode() const {
        return static_cast<OfflineMode>(mode_.load(std::memory_order_acquire));
    }
    void storeMode(OfflineMode mode) {
        mode_.store(static_cast<uint8_t>(mode), std::memory_order_release);
    }
    static bool isInsideTimeWindow(uint8_t now_h, uint8_t now_m,
                                    uint8_t start_h, uint8_t start_m,
                                    uint8_t end_h,   uint8_t end_m);

    // State
    std::atomic<uint8_t> mode_            {static_cast<uint8_t>(OfflineMode::ONLINE)};
    unsigned long  disconnect_timestamp_ms_ = 0;
    unsigned long  adoption_started_ms_   = 0;
    uint32_t       active_handover_epoch_ = 0;
    uint32_t       handover_completed_epoch_ = 0;

    // E7 authority/handover telemetry counters
    uint32_t       offline_enter_count_   = 0;
    uint32_t       adopting_enter_count_  = 0;
    uint32_t       adoption_noop_count_   = 0;
    uint32_t       adoption_delta_count_  = 0;
    uint32_t       handover_abort_count_  = 0;
    uint32_t       handover_contract_reject_count_ = 0;
    char           last_handover_contract_reject_code_[32] = "NONE";
    bool           persistence_drift_active_ = false;
    uint32_t       persistence_drift_count_ = 0;
    char           last_persistence_drift_reason_[32] = "NONE";

    // Rules storage
    OfflineRule    offline_rules_[MAX_OFFLINE_RULES];
    OfflineRule    offline_rules_shadow_[MAX_OFFLINE_RULES];
    uint8_t        offline_rule_count_    = 0;
    uint8_t        shadow_rule_count_     = 0;
    uint8_t        warmup_valid_samples_[MAX_OFFLINE_RULES] = {0};
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
extern OfflineModeManager& offlineModeManager;
