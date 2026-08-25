#include "safety_task.h"
#include <esp_task_wdt.h>
#include <freertos/portmacro.h>  // StackType_t — stack HWM in bytes
#include "../services/sensor/sensor_manager.h"
#include "../services/actuator/actuator_manager.h"
#include "../services/actuator/safety_controller.h"  // M2: emergencyStopAll() via xTaskNotify
#include "../services/safety/offline_mode_manager.h" // M3: SAFETY-P4 offline rules on Core 1
#include "../error_handling/health_monitor.h"
#include "actuator_command_queue.h"
#include "sensor_command_queue.h"
#include "config_update_queue.h"
#include "../utils/logger.h"

static const char* SAFETY_TAG = "SAFETY";

TaskHandle_t g_safety_task_handle = NULL;

// PUBLISH_PAYLOAD_MAX_LEN increased 1024→2048: PublishRequest on stack grew by 1024 bytes.
// Keep intended 12 KB stack budget (convert bytes -> FreeRTOS words explicitly).
static const uint32_t SAFETY_TASK_STACK_BYTES = 12288;
static const uint32_t SAFETY_TASK_STACK_SIZE = SAFETY_TASK_STACK_BYTES / sizeof(StackType_t);
static const UBaseType_t SAFETY_TASK_PRIORITY = 5;
static const BaseType_t SAFETY_TASK_CORE = 1;
static constexpr uint32_t kP4CooperativeIntervalMs = 500;

// Threshold below which slow cycles are not logged (raised from 250 ms to cover the expected
// cooperative delay of moisture/soil probes: 2 × 200 ms = 400 ms < 1000 ms).
// pH/EC probes still exceed this (29 × 100 ms = 2900 ms) and appear with cooperative_dominated=1.
static constexpr unsigned long kSafetySlowWarnMs    = 1000UL;
static constexpr unsigned long kSafetyLogDebounceMs = 2000UL;
// Fraction of cycle time (%) spent in performAllMeasurements above which the cycle is
// considered measurement-dominated (cooperative delay expected, not a real block).
static constexpr uint32_t kSafetyCycleMeasurePct = 80UL;

// Forward declaration — defined in main.cpp
extern void checkServerAckTimeout();

static void processSafetyTaskNotifications(uint32_t notified) {
    if (notified & NOTIFY_EMERGENCY_STOP) {
        LOG_W(SAFETY_TAG, "[SAFETY-M2] EMERGENCY_STOP received — stopping all actuators");
        bumpSafetyEpoch("emergency_notify");
        flushActuatorCommandQueue();
        flushSensorCommandQueue();
        safetyController.emergencyStopAll("MQTT emergency command (Core 0 notify)");
    }
    if (notified & NOTIFY_MQTT_DISCONNECTED) {
        if (offlineModeManager.getOfflineRuleCount() > 0) {
            LOG_W(SAFETY_TAG, "[SAFETY-M2] MQTT_DISCONNECTED — " +
                  String(offlineModeManager.getOfflineRuleCount()) +
                  " offline rules available, delegating covered actuators to P4");
            if (actuatorManager.isInitialized()) {
                actuatorManager.setUncoveredActuatorsToSafeState();
            }
        } else {
            if (actuatorManager.isInitialized()) {
                actuatorManager.setAllActuatorsToSafeState();
            }
            LOG_W(SAFETY_TAG, "[SAFETY-M2] MQTT_DISCONNECTED — no offline rules, setting actuators to safe state immediately");
        }
    }
    // NOTIFY_SUBZONE_SAFE: M3 — full GPIO routing via Core 1 queue (not yet implemented)
}

void runSafetyCooperativeSlice() {
    uint32_t notified = 0;
    xTaskNotifyWait(0, UINT32_MAX, &notified, 0);
    if (notified != 0) {
        processSafetyTaskNotifications(notified);
    }

    processActuatorCommandQueue();
    if (actuatorManager.isInitialized()) {
        actuatorManager.processActuatorLoops();
    }

    if (offlineModeManager.isOfflineActive()) {
        static uint32_t s_last_p4_cooperative_ms = 0;
        const uint32_t now_ms = static_cast<uint32_t>(millis());
        if (now_ms - s_last_p4_cooperative_ms >= kP4CooperativeIntervalMs) {
            s_last_p4_cooperative_ms = now_ms;
            offlineModeManager.evaluateOfflineRules();
        }
    }

    #ifndef WOKWI_SIMULATION
    esp_task_wdt_reset();
    #endif
}

bool createSafetyTask() {
    BaseType_t created = xTaskCreatePinnedToCore(
        safetyTaskFunction,
        "SafetyTask",
        SAFETY_TASK_STACK_SIZE,
        NULL,
        SAFETY_TASK_PRIORITY,
        &g_safety_task_handle,
        SAFETY_TASK_CORE
    );
    if (created != pdPASS || g_safety_task_handle == NULL) {
        LOG_E(SAFETY_TAG,
              "[SAFETY] Failed to create safety task (stack_words=" +
              String((uint32_t)SAFETY_TASK_STACK_SIZE) +
              ", stack_bytes=" + String((uint32_t)SAFETY_TASK_STACK_BYTES) +
              ", free_heap=" + String(ESP.getFreeHeap()) +
              ", min_free_heap=" + String(ESP.getMinFreeHeap()) +
              ", max_alloc=" + String(ESP.getMaxAllocHeap()) + ")");
        return false;
    }
    return true;
}

void safetyTaskFunction(void* param) {
    (void)param;
    #ifndef WOKWI_SIMULATION
    esp_task_wdt_add(NULL);
    #endif

    LOG_I(SAFETY_TAG, "[SAFETY] Safety task running on core " + String(xPortGetCoreID()));

    static uint32_t stack_log_counter = 0;
    unsigned long last_loop_ms = millis();
    static unsigned long s_last_safety_gap_log_ms = 0;
    static unsigned long s_last_safety_cycle_slow_log_ms = 0;

    for (;;) {
        const unsigned long safety_now_ms = millis();
        const unsigned long safety_loop_gap_ms = safety_now_ms - last_loop_ms;
        last_loop_ms = safety_now_ms;
        if (safety_loop_gap_ms > kSafetySlowWarnMs) {
            if (s_last_safety_gap_log_ms == 0UL ||
                (safety_now_ms - s_last_safety_gap_log_ms) >= kSafetyLogDebounceMs) {
                s_last_safety_gap_log_ms = safety_now_ms;
                // #region agent log
                LOG_W(SAFETY_TAG, String("[DBG5126ae] safety loop gap gap_ms=") +
                                  String(safety_loop_gap_ms) +
                                  " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }
        const unsigned long safety_cycle_start_ms = millis();

        // Notifications + actuator queue + runtime loops before blocking sensor work.
        runSafetyCooperativeSlice();

        const unsigned long measurement_start_ms = millis();
        sensorManager.performAllMeasurements();
        const unsigned long measurement_elapsed_ms = millis() - measurement_start_ms;

        // Drain commands that arrived during measurement (cooperative slices run inside reads).
        runSafetyCooperativeSlice();

        checkServerAckTimeout();
        processSensorCommandQueue();
        processConfigUpdateQueue();  // SAFETY-RTOS M4.6: drain Core 0→1 config queue
        healthMonitor.loop();

        // ============================================
        // M3: SAFETY-P4 Offline Hysteresis (Core 1)
        // ============================================
        // checkDelayTimer: transition DISCONNECTING → OFFLINE_ACTIVE after 30 s grace period.
        // evaluateOfflineRules: apply local actuator rules every 5 s when offline.
        // Runs on Core 1 because offline rules directly control GPIO/actuators.
        offlineModeManager.checkDelayTimer();
        // evaluateOfflineRules is driven by runSafetyCooperativeSlice (500 ms guard, kP4CooperativeIntervalMs).
        // The former 5 s main-loop path was redundant after AUT-955 and has been removed.

        // Log stack highwater mark every ~60s (6000 * 10ms = 60s)
        // uxTaskGetStackHighWaterMark returns free stack in words; Xtensa word = 4 bytes.
        stack_log_counter++;
        if (stack_log_counter >= 6000) {
            stack_log_counter = 0;
            UBaseType_t hwm = uxTaskGetStackHighWaterMark(g_safety_task_handle);
            LOG_D(SAFETY_TAG, "[SAFETY] Stack HWM: " +
                  String((uint32_t)(hwm * (uint32_t)sizeof(StackType_t))) + " bytes free");
        }

        const unsigned long safety_cycle_duration_ms = millis() - safety_cycle_start_ms;
        if (safety_cycle_duration_ms > kSafetySlowWarnMs) {
            if (s_last_safety_cycle_slow_log_ms == 0UL ||
                (millis() - s_last_safety_cycle_slow_log_ms) >= kSafetyLogDebounceMs) {
                s_last_safety_cycle_slow_log_ms = millis();
                const bool cooperative_dominated =
                    (measurement_elapsed_ms * 100UL / safety_cycle_duration_ms) >= kSafetyCycleMeasurePct;
                // #region agent log
                LOG_W(SAFETY_TAG, String("[DBG5126ae] safety op cycle slow duration_ms=") +
                                  String(safety_cycle_duration_ms) +
                                  " measurement_ms=" + String(measurement_elapsed_ms) +
                                  " cooperative_dominated=" + String(cooperative_dominated ? 1 : 0) +
                                  " heap=" + String(ESP.getFreeHeap()));
                // #endregion
            }
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
