#ifndef MODELS_WATCHDOG_TYPES_H
#define MODELS_WATCHDOG_TYPES_H

#include <Arduino.h>
#include "../error_handling/circuit_breaker.h"
#include "system_types.h"

// ============================================
// WATCHDOG MODES (Industrial-Grade)
// ============================================
// Note: Avoid "DISABLED" - conflicts with ESP32 framework macro in esp32-hal-gpio.h
enum class WatchdogMode : uint8_t {
    WDT_DISABLED = 0,  // No watchdog (WOKWI simulation)
    PROVISIONING,      // Relaxed watchdog for setup (300s timeout, no panic)
    PRODUCTION,        // Strict watchdog for operation (60s timeout, panic=true)
    SAFE_MODE          // Extended timeout for recovery (120s timeout, no panic)
};

// ============================================
// WATCHDOG CONFIGURATION
// ============================================
struct WatchdogConfig {
    WatchdogMode mode;
    unsigned long timeout_ms;
    unsigned long feed_interval_ms;
    bool panic_enabled;

    WatchdogConfig()
        : mode(WatchdogMode::WDT_DISABLED),
          timeout_ms(0),
          feed_interval_ms(0),
          panic_enabled(false) {}
};

// ============================================
// WATCHDOG DIAGNOSTICS
// ============================================
struct WatchdogDiagnostics {
    // Runtime diagnostics (updated on each feed)
    unsigned long last_feed_time;
    const char* last_feed_component;
    uint32_t feed_count;

    // Extended diagnostics (saved to NVS on timeout)
    unsigned long timestamp;
    SystemState system_state;
    CircuitState wifi_breaker_state;
    CircuitState mqtt_breaker_state;
    size_t error_count;
    uint32_t heap_free;

    WatchdogDiagnostics()
        : last_feed_time(0),
          last_feed_component(""),
          feed_count(0),
          timestamp(0),
          system_state(STATE_BOOT),
          wifi_breaker_state(CircuitState::CLOSED),
          mqtt_breaker_state(CircuitState::CLOSED),
          error_count(0),
          heap_free(0) {}
};

// ============================================
// GLOBAL WATCHDOG STATE (extern, defined in main.cpp)
// ============================================
extern WatchdogConfig g_watchdog_config;
extern WatchdogDiagnostics g_watchdog_diagnostics;
extern volatile bool g_watchdog_timeout_flag;

// ============================================
// WATCHDOG API (implemented in main.cpp)
// ============================================
/**
 * @brief Feed Watchdog mit Kontext und Circuit-Breaker-Check
 * @param component_id ID der Komponente (für Diagnostics)
 * @return true wenn Feed erfolgreich, false wenn blockiert
 */
bool feedWatchdog(const char* component_id);

/**
 * @brief Handle Watchdog Timeout (wird in loop() aufgerufen)
 */
void handleWatchdogTimeout();

/**
 * @brief Get Watchdog timeout count in last 24 hours
 * @return Anzahl der Watchdog-Timeouts in letzten 24h
 */
uint8_t getWatchdogCountLast24h();

#endif // MODELS_WATCHDOG_TYPES_H
