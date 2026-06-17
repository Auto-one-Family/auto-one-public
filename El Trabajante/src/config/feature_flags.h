#ifndef CONFIG_FEATURE_FLAGS_H
#define CONFIG_FEATURE_FLAGS_H

// ============================================
// FEATURE FLAGS
// ============================================
// Enable/Disable optional features at compile-time

// ============================================
// MQTT AGENT DEBUG LOGS
// ============================================
// Enables detailed JSON debug output via Serial.println() in mqtt_client.cpp
// Each debug log is a single snprintf()+println() call — safe for ser2net/Promtail
// Output format: [DEBUG]{...json...}\n (one complete JSON object per line)
// DEFAULT: Disabled (production)
// #define ENABLE_AGENT_DEBUG_LOGS

// ============================================
// HEARTBEAT METRICS SPLIT (AUT-121)
// ============================================
// Separates telemetry counters from core heartbeat into a dedicated
// .../system/heartbeat_metrics topic (QoS 0, delta/freshness gated).
// Core heartbeat retains ACK/validation/config/zone/handover fields.
// Kanonische Schaltstelle: nur hier toggeln (auskommentieren = aus, AUT-293).
// Repo-Default: an (#define unten); Doku-SSOT fuer Verhalten: Mqtt_Protocoll.md §3a + MQTT_TOPICS.md (AUT-361).
// Pi-/Legacy-Builds: bei Bedarf auskommentieren (voller Legacy-Heartbeat ohne heartbeat_metrics).
#ifndef ENABLE_METRICS_SPLIT
#define ENABLE_METRICS_SPLIT
#endif

// ============================================
// CORE-QUEUE SAFETY CONTRACT (R0-R4)
// ============================================
// Keep these flags enabled for the hardened queue/safety contract.
// Rollback path: disable the highest enabled phase first.
#define ENABLE_INTENT_OUTCOME_CONTRACT
#define ENABLE_COMMAND_ADMISSION_NACK
#define ENABLE_CRITICAL_PUBLISH_LANE
#define ENABLE_EMERGENCY_EPOCH_BARRIER
#define ENABLE_CONFIG_PENDING_REPLAY
#define ENABLE_LEGACY_FALLBACK_DEGRADE

#endif
