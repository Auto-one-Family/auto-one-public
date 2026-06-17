#ifndef CONFIG_FIRMWARE_VERSION_H
#define CONFIG_FIRMWARE_VERSION_H

/**
 * Single source of truth for human-readable firmware version on the ESP32.
 * Override per environment in platformio.ini, e.g.:
 *   '-DKAISER_FIRMWARE_VERSION_STRING=\"4.0.0\"'
 */
#ifndef KAISER_FIRMWARE_VERSION_STRING
#define KAISER_FIRMWARE_VERSION_STRING "4.0.0"
#endif

#endif
