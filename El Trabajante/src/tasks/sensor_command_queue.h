#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "intent_contract.h"

static const uint8_t SENSOR_CMD_QUEUE_SIZE = 20;

struct SensorCommand {
    char topic[128];
    char payload[512];
    IntentMetadata metadata;
};

struct SensorCommandExecutionResult {
    bool ok;
    String outcome;
    String code;
    String reason;
    bool retryable;
};

extern QueueHandle_t g_sensor_cmd_queue;

void initSensorCommandQueue();
bool queueSensorCommand(const char* topic, const char* payload, const IntentMetadata* metadata = nullptr);
void flushSensorCommandQueue();
void processSensorCommandQueue(uint8_t max_items = 4);
uint32_t getSensorCommandQueueOverflowCount();
