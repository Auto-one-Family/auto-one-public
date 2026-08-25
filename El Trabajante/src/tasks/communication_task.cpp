// ============================================
// SAFETY-RTOS M3: Communication Task (Core 0)
// ============================================
// All network I/O formerly in loop() lives here.
// loop() is minimal after this phase (vTaskDelay only).
// ============================================

#include "communication_task.h"
#include "publish_queue.h"
#include "publish_queue_policy.h"

#include <Arduino.h>
#include <WiFi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/portmacro.h>

#include "../utils/logger.h"
#include "../utils/topic_builder.h"
#include "../utils/time_manager.h"
#include "../utils/watchdog_storage.h"
#include "../services/communication/wifi_manager.h"
#include "../services/communication/mqtt_client.h"
#include "../services/config/config_manager.h"
#include "../services/provisioning/provision_manager.h"
#include "../services/provisioning/portal_authority.h"
#include "../services/actuator/actuator_manager.h"
#include "../models/system_types.h"
#include "../models/config_types.h"
#include "../models/error_codes.h"
#include "../error_handling/circuit_breaker.h"
#include "../error_handling/error_tracker.h"
#include "intent_contract.h"

static const char* COMM_TAG = "COMM";

static TaskHandle_t s_comm_task_handle = NULL;

// FreeRTOS stack depth is in words, not bytes.
// Keep the intended 6 KB stack budget and convert explicitly.
static const uint32_t    COMM_TASK_STACK_BYTES = 10240;
static const uint32_t    COMM_TASK_STACK_SIZE = COMM_TASK_STACK_BYTES / sizeof(StackType_t);
static const UBaseType_t COMM_TASK_PRIORITY   = 3;    // Below Safety-Task (5)
static const BaseType_t  COMM_TASK_CORE       = 0;    // PRO_CPU (WiFi-Stack co-located)

static const unsigned long PORTAL_OPEN_DEBOUNCE_MS           = 30000;
static const unsigned long MQTT_PERSISTENT_FAILURE_TIMEOUT_MS = 300000;  // 5 minutes

// ─── External state from main.cpp ──────────────────────────────────────
extern SystemConfig g_system_config;
extern WiFiConfig   g_wifi_config;
extern bool         portal_open_due_to_disconnect_;
extern bool         g_boot_force_offline_autonomy;

// ─── External functions from main.cpp ──────────────────────────────────
extern void handleWatchdogTimeout();
extern void processDeferredPostReconnectActuatorStatusSync();
extern void processDeferredSpoolFlush();
static void enforceMqttDisconnectOnWifiLoss();

// ============================================
// STATIC HELPER: Provisioning Mode Handler
// ============================================
// Mirrors the STATE_SAFE_MODE_PROVISIONING branch that was in loop().
static void handleProvisioningState() {
    // Keep HTTP portal alive
    provisionManager.loop();

    // Portal open due to MQTT disconnect: run WiFi+MQTT, check for reconnect success
    if (portal_open_due_to_disconnect_) {
        wifiManager.loop();
        enforceMqttDisconnectOnWifiLoss();
        mqttClient.loop();
#ifndef MQTT_USE_PUBSUBCLIENT
        mqttClient.processPublishQueue();
        processDeferredPostReconnectActuatorStatusSync();
        processDeferredSpoolFlush();
#endif

        if (mqttClient.isConnected() && mqttClient.isRegistrationConfirmed()) {
            LOG_I(COMM_TAG, "Reconnect erfolgreich — Portal wird geschlossen");
            provisionManager.stop();
            portal_open_due_to_disconnect_ = false;
            WiFi.mode(WIFI_STA);  // Back to STA-only
            g_system_config.current_state = STATE_OPERATIONAL;
            g_system_config.safe_mode_reason = "";
            configManager.saveSystemConfig(g_system_config);
        }

        // AUT-744: portal has no timeout here (checkTimeouts() only in waitForConfig/boot path).
        if (provisionManager.isAPModeTimedOut()) {
            LOG_W(COMM_TAG, "[PORTAL] Reconfig-Portal timeout — schliesse, zurueck zu STA-only (AUT-744)");
            provisionManager.stop();
            portal_open_due_to_disconnect_ = false;
            WiFi.mode(WIFI_STA);
            g_system_config.current_state = STATE_OPERATIONAL;
            g_system_config.safe_mode_reason = "";
        }
    }

    // Config received via HTTP → reload + reboot
    if (provisionManager.isConfigReceived()) {
        LOG_I(COMM_TAG, "╔════════════════════════════════════════╗");
        LOG_I(COMM_TAG, "║  ✅ KONFIGURATION EMPFANGEN!          ║");
        LOG_I(COMM_TAG, "╚════════════════════════════════════════╝");
        configManager.loadWiFiConfig(g_wifi_config);
        LOG_I(COMM_TAG, "WiFi SSID: " + g_wifi_config.ssid);
        LOG_I(COMM_TAG, "Rebooting to apply configuration...");
        delay(2000);
        ESP.restart();
    }
}

// ============================================
// STATIC HELPER: WiFi Disconnect Debounce
// ============================================
// Opens config portal after 30 s of continuous MQTT disconnect in OPERATIONAL state.
// Mirrors the debounce block that was in loop().
static void handleWifiDisconnectDebounce() {
    static unsigned long disconnect_start = 0;

    if (g_system_config.current_state == STATE_OPERATIONAL && !mqttClient.isConnected() && !WiFi.isConnected()) {
        if (disconnect_start == 0) {
            disconnect_start = millis();
        } else if (millis() - disconnect_start > PORTAL_OPEN_DEBOUNCE_MS
                   && !portal_open_due_to_disconnect_) {
            PortalDecisionContext decision_context;
            decision_context.portal_already_open = portal_open_due_to_disconnect_;
            decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
            decision_context.has_valid_local_autonomy_config = false;
            const char* decision_code = nullptr;
            if (!mayOpenPortal(PortalOpenReason::DISCONNECT_DEBOUNCE, decision_context, &decision_code)) {
                LOG_W(COMM_TAG, String("[PORTAL] skip opening on disconnect (code=") +
                               String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
                disconnect_start = 0;
                return;
            }
            LOG_I(COMM_TAG, "Config-Portal geoeffnet (Server getrennt), Reconnect laeuft im Hintergrund");
            g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
            g_system_config.safe_mode_reason =
                "MQTT disconnected (" + String(PORTAL_OPEN_DEBOUNCE_MS / 1000) + "s)";
            configManager.saveSystemConfig(g_system_config);
            if (provisionManager.startAPModeForReconfig()) {
                portal_open_due_to_disconnect_ = true;
            }
            disconnect_start = 0;
        }
    } else {
        disconnect_start = 0;
    }
}

// ============================================
// STATIC HELPER: MQTT Teardown on WiFi Loss
// ============================================
// During AP handovers we may observe a short window where WiFi is already gone
// but MQTT still appears connected. Force a local MQTT transport detach in this
// state so the broker does not keep a stale session for the same client_id.
static void enforceMqttDisconnectOnWifiLoss() {
    static unsigned long last_forced_disconnect_ms = 0;
    const bool wifi_connected = WiFi.isConnected();
    const bool mqtt_connected = mqttClient.isConnected();

    if (!wifi_connected && mqtt_connected) {
        const unsigned long now = millis();
        if (last_forced_disconnect_ms == 0UL || (now - last_forced_disconnect_ms) > 2000UL) {
            last_forced_disconnect_ms = now;
            // [AUT-745] rssi/wifi_status disambiguate this trigger (genuine WiFi drop,
            // caught within ~2s) from the two mqttClient.disconnect() call sites in
            // wifi_manager.cpp (planned handover / explicit WiFiManager::disconnect()) —
            // all three previously logged an identical generic message.
            LOG_W(COMM_TAG, String("[AUT-745] WiFi down while MQTT connected -> force MQTT transport detach") +
                             " wifi_status=" + String((int)WiFi.status()) +
                             " rssi_last=" + String(WiFi.RSSI()));
            mqttClient.disconnect();
        }
        return;
    }

    if (wifi_connected) {
        last_forced_disconnect_ms = 0;
    }
}

// ============================================
// STATIC HELPER: MQTT Persistent Failure (5 min)
// ============================================
// If MQTT Circuit Breaker stays OPEN for 5 minutes, open config portal as fallback.
// Mirrors the persistent-failure block that was in loop().
static void handleMqttPersistentFailure() {
    static unsigned long mqtt_failure_start = 0;

    if (!mqttClient.isConnected()
        && mqttClient.getCircuitBreakerState() == CircuitState::OPEN) {
        if (mqtt_failure_start == 0) {
            mqtt_failure_start = millis();
            LOG_W(COMM_TAG, "MQTT persistent failure timer started (5 min to recovery)");
        } else if (millis() - mqtt_failure_start > MQTT_PERSISTENT_FAILURE_TIMEOUT_MS) {
            if (WiFi.isConnected()) {  // AUT-678: STA still up — broker-only outage, skip Provisioning
                LOG_W(COMM_TAG, "MQTT persistent failure but STA up — skip Provisioning (AUT-678)");
                mqtt_failure_start = 0;
                return;
            }
            if (!portal_open_due_to_disconnect_) {
                PortalDecisionContext decision_context;
                decision_context.portal_already_open = portal_open_due_to_disconnect_;
                decision_context.boot_force_offline_autonomy = g_boot_force_offline_autonomy;
                decision_context.has_valid_local_autonomy_config = false;
                const char* decision_code = nullptr;
                if (!mayOpenPortal(PortalOpenReason::MQTT_PERSISTENT_FAILURE, decision_context, &decision_code)) {
                    LOG_W(COMM_TAG, String("[PORTAL] skip opening after persistent MQTT failure (code=") +
                                   String(decision_code != nullptr ? decision_code : "UNKNOWN") + ")");
                    mqtt_failure_start = 0;
                    return;
                }
                LOG_C(COMM_TAG, "╔════════════════════════════════════════╗");
                LOG_C(COMM_TAG, "║  MQTT PERSISTENT FAILURE (5 min)       ║");
                LOG_C(COMM_TAG, "║  Config-Portal oeffnen...              ║");
                LOG_C(COMM_TAG, "╚════════════════════════════════════════╝");
                g_system_config.current_state = STATE_SAFE_MODE_PROVISIONING;
                g_system_config.safe_mode_reason =
                    "MQTT persistent failure (5 min Circuit Breaker OPEN)";
                configManager.saveSystemConfig(g_system_config);
                if (!provisionManager.isInitialized() && !provisionManager.begin()) {
                    LOG_E(COMM_TAG, "ProvisionManager init failed — cannot open portal");
                    return;
                }
                if (provisionManager.startAPModeForReconfig()) {
                    portal_open_due_to_disconnect_ = true;
                }
            }
            mqtt_failure_start = 0;
        }
    } else {
        if (mqtt_failure_start != 0) {
            LOG_I(COMM_TAG, "MQTT recovered - persistent failure timer reset");
            mqtt_failure_start = 0;
        }
    }
}

// ============================================
// STATIC HELPER: Publish-Queue Pressure Hysteresis (PKG-01a)
// ============================================
// INC-2026-04-20-offline-mode-observability-hardening:
// Emits kaiser/{k}/esp/{id}/system/queue_pressure on hysteresis transitions of the
// Core 1 → Core 0 publish queue. ENTER when fill crosses the shed watermark upwards,
// RECOVERED when it falls back into the dead band.
//
//   Dead band: fill < publishQueuePressureRecoveredThreshold()  → RECOVERED region
//   Shed zone: fill >= PUBLISH_QUEUE_SHED_WATERMARK            → ENTER region
//   Saturated: fill == PUBLISH_QUEUE_SIZE                      → skip (defensive, avoid
//              adding recursive load when ESP-IDF outbox is likely also strained)
//
// The queue_pressure publish itself runs on Core 0 and goes directly through
// esp_mqtt_client_publish() (see MQTTClient::publish), so it does NOT consume a
// g_publish_queue slot. The saturation-skip is kept per the PKG-01a contract.
// Implemented only on the ESP-IDF MQTT path — PubSubClient builds have no
// Core 1 → Core 0 publish queue. Runs at 50 ms cadence (Comm-Task loop).
#ifndef MQTT_USE_PUBSUBCLIENT

static void handleQueuePressureHysteresis() {
    static bool     s_queue_pressure_entered = false;
    static uint32_t s_last_drop_count = 0;

    if (!mqttClient.isConnected()) {
        // Nothing publishable while disconnected. State stays as-is; once reconnected
        // the next transition will fire normally.
        return;
    }

    PublishQueuePressureStats stats = getPublishQueuePressureStats();

    // Defensive: never emit when queue is fully saturated. Keeps the Core 0 outbox
    // from being pushed further under load. PKG-01a explicit requirement.
    if (stats.fill_level >= PUBLISH_QUEUE_SIZE) {
        return;
    }

    // Observe drop_count rising edge and report through the error pipeline.
    // Local increment-only tracking — throttling handled by ErrorTracker.
    if (stats.drop_count > s_last_drop_count) {
        errorTracker.logApplicationError(ERROR_TASK_QUEUE_FULL,
                                         "Publish queue full: messages dropped");
        s_last_drop_count = stats.drop_count;
    }

    const char* event = nullptr;
    if (!s_queue_pressure_entered && stats.fill_level >= PUBLISH_QUEUE_SHED_WATERMARK) {
        s_queue_pressure_entered = true;
        event = "entered_pressure";
    } else if (s_queue_pressure_entered &&
               stats.fill_level < publishQueuePressureRecoveredThreshold()) {
        s_queue_pressure_entered = false;
        event = "recovered";
    }

    if (event == nullptr) {
        return;  // No transition — nothing to emit
    }

    const char* topic_cstr = TopicBuilder::buildQueuePressureTopic();
    if (topic_cstr == nullptr || topic_cstr[0] == '\0') {
        LOG_W(COMM_TAG, "[COMM] queue_pressure topic build failed, dropping event");
        return;
    }
    String topic(topic_cstr);

    String payload;
    payload.reserve(192);
    payload += "{\"event\":\"";
    payload += event;
    payload += "\",\"fill_level\":";
    payload += String(stats.fill_level);
    payload += ",\"high_watermark\":";
    payload += String(stats.high_watermark);
    payload += ",\"shed_count\":";
    payload += String(stats.shed_count);
    payload += ",\"drop_count\":";
    payload += String(stats.drop_count);
    payload += ",\"threshold\":";
    payload += String(PUBLISH_QUEUE_SHED_WATERMARK);
    payload += ",\"ts\":";
    payload += String((uint32_t)timeManager.getUnixTimestamp());
    payload += "}";

    if (!mqttClient.publish(topic, payload, 0)) {
        LOG_W(COMM_TAG, "[COMM] queue_pressure publish failed (event=" + String(event) +
              ", fill=" + String(stats.fill_level) + ")");
    } else {
        LOG_I(COMM_TAG, "[COMM] queue_pressure " + String(event) +
              " fill=" + String(stats.fill_level) +
              " hwm=" + String(stats.high_watermark) +
              " shed=" + String(stats.shed_count) +
              " drop=" + String(stats.drop_count));
    }
}
#endif  // MQTT_USE_PUBSUBCLIENT

// ============================================
// STATIC HELPER: Heap Monitoring (every 60 s)
// ============================================
// SAFETY-RTOS M4: Detect memory leaks from queue/mutex overhead or large config payloads.
static void handleHeapMonitoring() {
    static unsigned long last_heap_log = 0;
    static const unsigned long HEAP_LOG_INTERVAL_MS = 60000;
    if (millis() - last_heap_log > HEAP_LOG_INTERVAL_MS) {
        last_heap_log = millis();
        String extra;
        if (s_comm_task_handle != NULL) {
            UBaseType_t hwm = uxTaskGetStackHighWaterMark(s_comm_task_handle);
            extra = ", stack HWM=" + String((uint32_t)(hwm * (uint32_t)sizeof(StackType_t))) + " B";
        }
        LOG_I(COMM_TAG, "[COMM] Heap free=" + String(ESP.getFreeHeap()) +
              " B, min=" + String(ESP.getMinFreeHeap()) + " B" + extra);
    }
}

// ============================================
// STATIC HELPER: Boot Counter Reset (once after 60 s stable)
// ============================================
static void handleBootCounterReset() {
    static bool done = false;
    if (!done && millis() > 60000 && g_system_config.boot_count > 1) {
        g_system_config.boot_count    = 0;
        g_system_config.last_boot_time = 0;
        configManager.saveSystemConfig(g_system_config);
        done = true;
        LOG_I(COMM_TAG, "Boot counter reset - stable operation confirmed");
    }
}

// ============================================
// TASK FUNCTION
// ============================================
void communicationTaskFunction(void* param) {
    (void)param;
    LOG_I(COMM_TAG, "[COMM] Communication task running on core " + String(xPortGetCoreID()));
    unsigned long last_loop_ms = millis();
    static unsigned long s_last_comm_gap_log_ms = 0;
    static unsigned long s_last_mqtt_loop_slow_log_ms = 0;

    for (;;) {
        const unsigned long loop_now_ms = millis();
        const unsigned long loop_gap_ms = loop_now_ms - last_loop_ms;
        last_loop_ms = loop_now_ms;
        if (loop_gap_ms > 250UL) {
            if (s_last_comm_gap_log_ms == 0UL || (loop_now_ms - s_last_comm_gap_log_ms) >= 2000UL) {
                s_last_comm_gap_log_ms = loop_now_ms;
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm loop gap gap_ms=") + String(loop_gap_ms) +
                                " state=" + String(g_system_config.current_state) +
                                " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }

        // One-shot: finalise watchdog boot record after stable uptime
        watchdogStorageTryFinalizeBootRecord();

        // WDT timeout recovery (diagnostics snapshot + MQTT alert)
        handleWatchdogTimeout();

        // ── Provisioning Mode ──────────────────────────────────────────
        if (g_system_config.current_state == STATE_SAFE_MODE_PROVISIONING) {
            handleProvisioningState();
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        // ── Restricted Admission Mode ───────────────────────────────────
        // Keep only WiFi+MQTT alive while control planes stay blocked.
        if (g_system_config.current_state == STATE_PENDING_APPROVAL ||
            g_system_config.current_state == STATE_CONFIG_PENDING_AFTER_RESET) {
            wifiManager.loop();
            enforceMqttDisconnectOnWifiLoss();
            mqttClient.loop();
#ifndef MQTT_USE_PUBSUBCLIENT
            // Check registration gate timeout independently — no other publish() calls are
            // made in PENDING_APPROVAL, so the inline timeout in publish() would never fire.
            mqttClient.checkRegistrationTimeout();
            mqttClient.processPublishQueue();
            processDeferredPostReconnectActuatorStatusSync();
            processDeferredSpoolFlush();
#endif
            vTaskDelay(pdMS_TO_TICKS(100));  // Slower tick — no sensor/actuator work
            continue;
        }

        // ── Operational Mode ───────────────────────────────────────────
        const unsigned long op_cycle_start_ms = millis();
        wifiManager.loop();
        enforceMqttDisconnectOnWifiLoss();
        const unsigned long wifi_loop_duration_ms = millis() - op_cycle_start_ms;
        static unsigned long s_last_wifi_loop_slow_log_ms = 0;
        if (wifi_loop_duration_ms > 120UL) {
            if (s_last_wifi_loop_slow_log_ms == 0UL ||
                (millis() - s_last_wifi_loop_slow_log_ms) >= 2000UL) {
                s_last_wifi_loop_slow_log_ms = millis();
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm wifi loop slow duration_ms=") +
                                String(wifi_loop_duration_ms) +
                                " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }

        const unsigned long mqtt_loop_start_ms = millis();
        mqttClient.loop();  // ESP-IDF path: handles timeManager (NTP) + heartbeat publish
        const unsigned long mqtt_loop_duration_ms = millis() - mqtt_loop_start_ms;
        if (mqtt_loop_duration_ms > 120UL) {
            if (s_last_mqtt_loop_slow_log_ms == 0UL ||
                (millis() - s_last_mqtt_loop_slow_log_ms) >= 2000UL) {
                s_last_mqtt_loop_slow_log_ms = millis();
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm mqtt loop slow duration_ms=") +
                                String(mqtt_loop_duration_ms) +
                                " heap=" + String(ESP.getFreeHeap()) +
                                " wifi_connected=" + String(WiFi.isConnected() ? "true" : "false"));
                // #endregion
            }
        }
#ifndef MQTT_USE_PUBSUBCLIENT
        // Check registration gate timeout independently — fallback if no non-heartbeat
        // publish() call has been made yet (e.g. no sensor data during first 10 s).
        mqttClient.checkRegistrationTimeout();
        const unsigned long process_queue_start_ms = millis();
        mqttClient.processPublishQueue();  // Drain Core 1 → Core 0 publish queue
        const unsigned long process_queue_duration_ms = millis() - process_queue_start_ms;
        static unsigned long s_last_process_queue_slow_log_ms = 0;
        if (process_queue_duration_ms > 120UL) {
            if (s_last_process_queue_slow_log_ms == 0UL ||
                (millis() - s_last_process_queue_slow_log_ms) >= 2000UL) {
                s_last_process_queue_slow_log_ms = millis();
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm processPublishQueue slow duration_ms=") +
                                String(process_queue_duration_ms) +
                                " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }
        processDeferredPostReconnectActuatorStatusSync();
        processDeferredSpoolFlush();
        processDeferredOutboxStatsPersist();
#endif

        handleBootCounterReset();
        handleWifiDisconnectDebounce();
        handleMqttPersistentFailure();
        // AUT-592: Periodic 30s actuator status blast removed — caused MQTT flooding (AUT-590 §7 R3).
        // Post-reconnect sync is handled by processDeferredPostReconnectActuatorStatusSync() (PKG-19).
#ifndef MQTT_USE_PUBSUBCLIENT
        const unsigned long queue_hyst_start_ms = millis();
        handleQueuePressureHysteresis();  // PKG-01a: backpressure ENTER/RECOVERED events
        const unsigned long queue_hyst_duration_ms = millis() - queue_hyst_start_ms;
        static unsigned long s_last_queue_hyst_slow_log_ms = 0;
        if (queue_hyst_duration_ms > 120UL) {
            if (s_last_queue_hyst_slow_log_ms == 0UL ||
                (millis() - s_last_queue_hyst_slow_log_ms) >= 2000UL) {
                s_last_queue_hyst_slow_log_ms = millis();
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm queuePressureHysteresis slow duration_ms=") +
                                String(queue_hyst_duration_ms) +
                                " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }
#endif
        handleHeapMonitoring();
        const unsigned long op_cycle_duration_ms = millis() - op_cycle_start_ms;
        static unsigned long s_last_op_cycle_slow_log_ms = 0;
        if (op_cycle_duration_ms > 250UL) {
            if (s_last_op_cycle_slow_log_ms == 0UL ||
                (millis() - s_last_op_cycle_slow_log_ms) >= 2000UL) {
                s_last_op_cycle_slow_log_ms = millis();
                // #region agent log
                LOG_W(COMM_TAG, String("[DBG5126ae] comm op cycle slow duration_ms=") +
                                String(op_cycle_duration_ms) +
                                " wifi_ms=" + String(wifi_loop_duration_ms) +
                                " mqtt_ms=" + String(mqtt_loop_duration_ms) +
                                " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

// ============================================
// createCommunicationTask
// ============================================
bool createCommunicationTask() {
    // Robust boot behavior with safety floor:
    // never go below 8 KB for this task (network + MQTT + portal + logging).
    const uint32_t stack_candidates[] = {
        COMM_TASK_STACK_SIZE,
        9216 / sizeof(StackType_t),
        8192 / sizeof(StackType_t)
    };

    for (uint8_t i = 0; i < (sizeof(stack_candidates) / sizeof(stack_candidates[0])); ++i) {
        const uint32_t stack_depth = stack_candidates[i];
        s_comm_task_handle = NULL;
        BaseType_t created = xTaskCreatePinnedToCore(
            communicationTaskFunction,
            "CommTask",
            stack_depth,
            NULL,
            COMM_TASK_PRIORITY,
            &s_comm_task_handle,
            COMM_TASK_CORE
        );
        if (created == pdPASS && s_comm_task_handle != NULL) {
            LOG_I(COMM_TAG,
                  "[COMM] CommTask created (stack_depth=" +
                  String((uint32_t)stack_depth) + ", stack_bytes=" +
                  String((uint32_t)(stack_depth * sizeof(StackType_t))) +
                  ", free_heap=" + String(ESP.getFreeHeap()) +
                  ", min_free_heap=" + String(ESP.getMinFreeHeap()) + ")");
            return true;
        }

        LOG_W(COMM_TAG,
              "[COMM] Task create attempt failed (stack_depth=" +
              String((uint32_t)stack_depth) + ", stack_bytes=" +
              String((uint32_t)(stack_depth * sizeof(StackType_t))) +
              ", free_heap=" + String(ESP.getFreeHeap()) +
              ", min_free_heap=" + String(ESP.getMinFreeHeap()) +
              ", max_alloc=" + String(ESP.getMaxAllocHeap()) + ")");
        vTaskDelay(pdMS_TO_TICKS(20));
    }

    LOG_E(COMM_TAG, "[COMM] Failed to create communication task after retries");
    return false;
}
