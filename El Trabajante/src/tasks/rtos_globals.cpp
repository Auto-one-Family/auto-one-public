#include "rtos_globals.h"
#include "../utils/logger.h"

static const char* RTOS_TAG = "SYNC";

SemaphoreHandle_t g_actuator_mutex      = NULL;
SemaphoreHandle_t g_sensor_mutex        = NULL;
SemaphoreHandle_t g_i2c_mutex           = NULL;
SemaphoreHandle_t g_onewire_mutex     = NULL;
SemaphoreHandle_t g_gpio_registry_mutex = NULL;

void initRtosMutexes() {
    g_actuator_mutex      = xSemaphoreCreateMutex();
    g_sensor_mutex        = xSemaphoreCreateMutex();
    g_i2c_mutex           = xSemaphoreCreateMutex();
    g_onewire_mutex       = xSemaphoreCreateMutex();
    g_gpio_registry_mutex = xSemaphoreCreateMutex();

    if (g_actuator_mutex      == NULL ||
        g_sensor_mutex        == NULL ||
        g_i2c_mutex           == NULL ||
        g_onewire_mutex       == NULL ||
        g_gpio_registry_mutex == NULL) {
        LOG_E(RTOS_TAG, "[SYNC] CRITICAL: Failed to create RTOS mutexes — heap exhausted?");
        // Cannot continue safely without mutexes
    } else {
        LOG_I(RTOS_TAG, "[SYNC] RTOS mutexes created (actuator/sensor/i2c/onewire/gpio)");
    }
}
