#pragma once
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ============================================
// SAFETY-RTOS M3: Communication Task (Core 0)
// ============================================
// Replaces loop(). Handles all network I/O:
//   WiFi management, MQTT loop, portal/provisioning,
//   publish-queue drain, heartbeat (via mqttClient.loop()),
//   actuator-status periodic publish, timer debounce.
//
// Setup order (AFTER safety task and publish queue):
//   initPublishQueue();
//   createSafetyTask();
//   esp_task_wdt_delete(xTaskGetCurrentTaskHandle());
//   createCommunicationTask();
// ============================================

// Create and pin Communication-Task to Core 0, Priority 3.
// Returns false when the task could not be created so caller can keep legacy loop fallback active.
bool createCommunicationTask();

// Task function (runs endlessly on Core 0).
void communicationTaskFunction(void* param);
