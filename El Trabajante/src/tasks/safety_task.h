#pragma once
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

extern TaskHandle_t g_safety_task_handle;

// ============================================
// SAFETY-RTOS M2: Task Notification Bits
// ============================================
// Used with xTaskNotify() from MQTT task (Core 0) to Safety-Task (Core 1).
// Bit-mask semantics: multiple bits can be set simultaneously in a single notify.
// Cleared atomically by xTaskNotifyWait(0, UINT32_MAX, &bits, 0) at top of Safety loop.
static const uint32_t NOTIFY_EMERGENCY_STOP    = 0x01;  // Emergency stop all actuators (<1µs latency)
static const uint32_t NOTIFY_MQTT_DISCONNECTED = 0x02;  // MQTT disconnect → setAllActuatorsToSafeState
static const uint32_t NOTIFY_SUBZONE_SAFE      = 0x04;  // Subzone safe-mode change (M3: full GPIO routing via Core 1)

bool createSafetyTask();
void safetyTaskFunction(void* param);

// Non-blocking safety path: notifications, actuator queue drain, runtime loops, WDT.
// Callable from Safety-Task loop and from long sensor reads (e.g. analog median delays).
void runSafetyCooperativeSlice();
