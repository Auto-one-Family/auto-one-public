#ifndef DRIVERS_GPIO_MANAGER_H
#define DRIVERS_GPIO_MANAGER_H

#include <Arduino.h>
#include <vector>
#include <map>

// Forward declaration of GPIOMode (defined in hal/igpio_hal.h)
enum class GPIOMode : uint8_t;

// ============================================
// GPIO Manager - Hardware Safety System
// ============================================
// Critical system for preventing hardware damage through GPIO misuse
// Documentation: ZZZ.md lines 1930-2012
// Migration: PROJECT_ANALYSIS_REPORT.md Block 6

// ============================================
// GPIO PIN INFO STRUCTURE
// ============================================
// Tracks the state and ownership of each GPIO pin

struct GPIOPinInfo {
    uint8_t pin;                // GPIO pin number
    char owner[32];             // Owner identifier ("sensor", "actuator", "system")
    char component_name[32];    // Component name ("DS18B20", "Pump1", etc.)
    uint8_t mode;               // Pin mode (INPUT, OUTPUT, INPUT_PULLUP)
    bool in_safe_mode;          // Pin is in safe mode (INPUT_PULLUP)
    
    // Constructor to ensure null-termination
    GPIOPinInfo() : pin(255), mode(INPUT), in_safe_mode(true) {
        owner[0] = '\0';
        component_name[0] = '\0';
    }
};

// ============================================
// GPIO MANAGER CLASS
// ============================================
// Singleton class managing all GPIO operations with safety checks

class GPIOManager {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    // Get the single instance of GPIOManager
    static GPIOManager& getInstance() {
        static GPIOManager instance;
        return instance;
    }

    // Prevent copy and move operations
    GPIOManager(const GPIOManager&) = delete;
    GPIOManager& operator=(const GPIOManager&) = delete;
    GPIOManager(GPIOManager&&) = delete;
    GPIOManager& operator=(GPIOManager&&) = delete;

    // ============================================
    // CRITICAL: SAFE-MODE INITIALIZATION
    // ============================================
    // MUST be called as the FIRST action in setup()!
    // Initializes all safe GPIO pins to INPUT_PULLUP to prevent hardware damage
    // This ensures no pins are in undefined states that could trigger actuators
    void initializeAllPinsToSafeMode();

    // ============================================
    // PIN MANAGEMENT
    // ============================================
    // Request exclusive use of a GPIO pin
    // Returns false if pin is reserved, already in use, or invalid
    // owner: Component type requesting the pin ("sensor", "actuator")
    // component_name: Specific component name for debugging
    bool requestPin(uint8_t gpio, const char* owner, const char* component_name);

    // Release a GPIO pin back to safe mode
    // Returns pin to INPUT_PULLUP state
    bool releasePin(uint8_t gpio);

    // Configure pin mode (INPUT, OUTPUT, INPUT_PULLUP)
    // Validates pin availability and hardware limitations
    bool configurePinMode(uint8_t gpio, uint8_t mode);

    // ============================================
    // PIN QUERIES
    // ============================================
    // Check if a pin is available for use
    bool isPinAvailable(uint8_t gpio) const;

    // Check if a pin is reserved (Boot/UART/etc.)
    bool isPinReserved(uint8_t gpio) const;

    // Check if a pin is on ADC2 (conflicts with WiFi on ESP32)
    // ADC2 pins cannot be used for analogRead() when WiFi is active
    bool isADC2Pin(uint8_t gpio) const;

    // Check if a pin is currently in safe mode
    bool isPinInSafeMode(uint8_t gpio) const;

    // ============================================
    // EMERGENCY SAFE-MODE
    // ============================================
    // Emergency function: Return ALL pins to safe mode
    // Used in error conditions to prevent hardware damage
    void enableSafeModeForAllPins();

    // ============================================
    // INFORMATION METHODS
    // ============================================
    // Get detailed information about a specific pin
    GPIOPinInfo getPinInfo(uint8_t gpio) const;

    /**
     * @brief Get owner of a reserved pin (Phase 4 - Config Feedback)
     * @param gpio GPIO pin number
     * @return Owner string ("sensor", "actuator", "system") or empty if not reserved
     */
    String getPinOwner(uint8_t gpio) const;

    /**
     * @brief Get component name of a reserved pin (Phase 4 - Config Feedback)
     * @param gpio GPIO pin number
     * @return Component name (e.g., "DS18B20", "Pump1") or empty if not reserved
     */
    String getPinComponent(uint8_t gpio) const;

    // Print status of all GPIO pins to Serial
    void printPinStatus() const;

    // Get count of available (unallocated) pins
    uint8_t getAvailablePinCount() const;

    // ============================================
    // GPIO STATUS REPORTING (Phase 1)
    // ============================================
    /**
     * Returns list of all reserved (non-safe-mode) pins with details.
     * Used by MQTTClient to include GPIO status in heartbeat payload.
     * Only returns pins that are NOT in safe mode (i.e., actively used).
     * @return Vector of GPIOPinInfo for all reserved pins
     */
    std::vector<GPIOPinInfo> getReservedPinsList() const;

    /**
     * Returns total count of reserved pins (not in safe mode).
     * @return Number of pins actively in use
     */
    uint8_t getReservedPinCount() const;

    // ============================================
    // I2C PIN MANAGEMENT
    // ============================================
    // Release I2C pins if I2C bus is not being used
    // WARNING: Only call if you're certain I2C will never be used!
    void releaseI2CPins();

    // ============================================
    // SUBZONE MANAGEMENT (Phase 9)
    // ============================================

    /**
     * Weist einen GPIO-Pin einer Subzone zu
     * @param gpio GPIO-Pin Nummer
     * @param subzone_id Ziel-Subzone
     * @return true bei Erfolg, false bei Konflikt oder Fehler
     */
    bool assignPinToSubzone(uint8_t gpio, const String& subzone_id);

    /**
     * Entfernt einen GPIO-Pin aus seiner Subzone
     * @param gpio GPIO-Pin Nummer
     * @return true bei Erfolg
     */
    bool removePinFromSubzone(uint8_t gpio);

    /**
     * Gibt alle GPIO-Pins einer Subzone zurück
     * @param subzone_id Subzone-Identifier
     * @return Vector mit GPIO-Pin Nummern
     */
    std::vector<uint8_t> getSubzonePins(const String& subzone_id) const;

    /**
     * Prüft ob ein Pin einer Subzone zugewiesen ist
     * @param gpio GPIO-Pin Nummer
     * @param subzone_id Subzone-Identifier (optional, wenn leer: prüft ob Pin überhaupt zugewiesen)
     * @return true wenn Pin der Subzone zugewiesen ist
     */
    bool isPinAssignedToSubzone(uint8_t gpio, const String& subzone_id = "") const;

    /**
     * Prüft ob eine Subzone im Safe-Mode ist
     * @param subzone_id Subzone-Identifier
     * @return true wenn alle Pins der Subzone im Safe-Mode sind
     */
    bool isSubzoneSafe(const String& subzone_id) const;

    /**
     * Aktiviert Safe-Mode für alle Pins einer Subzone
     * @param subzone_id Subzone-Identifier
     * @return true bei Erfolg
     */
    bool enableSafeModeForSubzone(const String& subzone_id);

    /**
     * Deaktiviert Safe-Mode für eine Subzone (Pins werden freigegeben)
     * @param subzone_id Subzone-Identifier
     * @return true bei Erfolg
     */
    bool disableSafeModeForSubzone(const String& subzone_id);

private:
    // ============================================
    // FRIEND DECLARATION (Test Helper)
    // ============================================
    friend class GPIOManagerTestHelper;

    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    GPIOManager();
    ~GPIOManager() {}

    // ============================================
    // INTERNAL STATE
    // ============================================
    // Vector storing information about all GPIO pins
    std::vector<GPIOPinInfo> pins_;

    // Subzone-Pin-Mapping: subzone_id → vector<gpio>
    std::map<String, std::vector<uint8_t>> subzone_pin_map_;

    // ============================================
    // HAL ABSTRACTION (Phase 2: Unit Testing)
    // ============================================
    // HAL pointer for hardware abstraction
    // - Production: Points to production_gpio_hal_ (ESP32GPIOHal)
    // - Tests: Injected via GPIOManagerTestHelper (MockGPIOHal)
    class IGPIOHal* gpio_hal_;

    // Production HAL instance (only in non-test builds)
    #ifndef UNIT_TEST
    static class ESP32GPIOHal production_gpio_hal_;
    #endif

    // ============================================
    // HELPER METHODS
    // ============================================
    // Check if pin is in reserved pins array (board-specific)
    bool isReservedPin(uint8_t gpio) const;

    // Check if pin is input-only (ESP32 WROOM specific)
    bool isInputOnlyPin(uint8_t gpio) const;

    // Verify that a pin is in the expected state after pinMode()
    bool verifyPinState(uint8_t pin, uint8_t expected_mode);

    // Convert Arduino uint8_t pin mode to GPIOMode enum
    static GPIOMode toGPIOMode(uint8_t arduino_mode);
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
// Convenient global reference to the singleton instance
extern GPIOManager& gpioManager;

#endif // DRIVERS_GPIO_MANAGER_H
