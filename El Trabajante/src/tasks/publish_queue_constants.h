#pragma once

#include <stdint.h>

// AUT-481 P3 queue sizing — shared by publish_queue.h and native policy tests.
// AUT-495: S3 N8R8 gets larger queue (PSRAM budget); DEV/WROOM uses smaller defaults.
#ifdef ESP32_S3_DEVKIT_MODE
static const uint8_t PUBLISH_QUEUE_SIZE           = 16;
static const uint8_t PUBLISH_QUEUE_SHED_WATERMARK = 8;
#else
static const uint8_t PUBLISH_QUEUE_SIZE           = 10;
static const uint8_t PUBLISH_QUEUE_SHED_WATERMARK = 5;
#endif
