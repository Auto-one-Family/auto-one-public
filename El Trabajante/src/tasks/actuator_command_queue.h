#pragma once
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "intent_contract.h"

static const uint8_t ACTUATOR_CMD_QUEUE_SIZE = 10;

/** Raw MQTT topic+payload for Core 0 → Safety-Task queue (distinct from models::ActuatorCommand). */
struct ActuatorMqttQueueItem {
    char topic[128];
    char payload[512];
    IntentMetadata metadata;
    unsigned long enqueued_ms;
};

extern QueueHandle_t g_actuator_cmd_queue;

void initActuatorCommandQueue();
bool queueActuatorCommand(const char* topic, const char* payload, const IntentMetadata* metadata = nullptr);
void flushActuatorCommandQueue();
void processActuatorCommandQueue(uint8_t max_items = 4);
