#ifndef DRIVERS_HAL_IGPIO_HAL_H
#define DRIVERS_HAL_IGPIO_HAL_H

#include <Arduino.h>
#include <vector>

// Forward declaration
struct GPIOPinInfo;

// ============================================
// GPIO HAL - Hardware Abstraction Layer Interface
// ============================================
// Pure virtual interface for GPIO operations
// Purpose: Enable unit testing of GPIO-dependent managers without hardware
//
// Pattern: Follows IActuatorDriver design (Pure Virtual, Lifecycle methods)
// Vorlage: src/services/actuator/actuator_drivers/iactuator_driver.h
//
// Implementation:
// - Production: ESP32GPIOHal (delegates to Arduino GPIO functions + GPIOManager)
// - Test: MockGPIOHal (in-memory state tracking for unit tests)

// ============================================
// GPIO MODE ENUM
// ============================================
// Note: Renamed from INPUT/OUTPUT to avoid conflicts with Arduino macros
enum class GPIOMode : uint8_t {
    GPIO_INPUT = 0x01,           // Standard input (Arduino: INPUT)
    GPIO_OUTPUT = 0x02,          // Standard output (Arduino: OUTPUT)
    GPIO_INPUT_PULLUP = 0x05,    // Input with internal pullup (Arduino: INPUT_PULLUP)
    GPIO_INPUT_PULLDOWN = 0x09   // Input with internal pulldown (ESP32-specific)
};

// ============================================
// IGPIO HAL INTERFACE
// ============================================
class IGPIOHal {
public:
    virtual ~IGPIOHal() = default;

    // ============================================
    // LIFECYCLE
    // ============================================
    // Initialize all GPIO pins to safe mode (INPUT_PULLUP)
    // MUST be called first to prevent hardware damage
    // Returns: true if successful
    virtual bool initializeAllPinsToSafeMode() = 0;

    // ============================================
    // PIN MANAGEMENT
    // ============================================
    // Request exclusive use of a GPIO pin
    // gpio: Pin number
    // owner: Component type requesting the pin ("sensor", "actuator")
    // component_name: Specific component name for debugging
    // Returns: true if pin successfully reserved, false if already in use or invalid
    virtual bool requestPin(uint8_t gpio, const String& owner, const String& component_name) = 0;

    // Release a GPIO pin back to safe mode (INPUT_PULLUP)
    // gpio: Pin number
    // Returns: true if successfully released
    virtual bool releasePin(uint8_t gpio) = 0;

    // ============================================
    // PIN QUERIES
    // ============================================
    // Check if a pin is available for use (not reserved or in use)
    // gpio: Pin number
    // Returns: true if pin is available
    virtual bool isPinAvailable(uint8_t gpio) const = 0;

    // Check if a pin is hardware-reserved (Boot, UART, Flash, etc.)
    // gpio: Pin number
    // Returns: true if pin is reserved by hardware
    virtual bool isPinReserved(uint8_t gpio) const = 0;

    // Check if a pin is currently in safe mode (INPUT_PULLUP)
    // gpio: Pin number
    // Returns: true if pin is in safe mode
    virtual bool isPinInSafeMode(uint8_t gpio) const = 0;

    // ============================================
    // GPIO OPERATIONS
    // ============================================
    // Configure pin mode (INPUT, OUTPUT, INPUT_PULLUP, INPUT_PULLDOWN)
    // gpio: Pin number
    // mode: Desired pin mode
    // Returns: true if mode successfully set
    virtual bool pinMode(uint8_t gpio, GPIOMode mode) = 0;

    // Set digital output state (HIGH/LOW)
    // gpio: Pin number
    // value: true = HIGH, false = LOW
    // Returns: true if successfully set
    virtual bool digitalWrite(uint8_t gpio, bool value) = 0;

    // Read digital input state
    // gpio: Pin number
    // Returns: true = HIGH, false = LOW
    virtual bool digitalRead(uint8_t gpio) = 0;

    // Read analog input value (ADC)
    // gpio: Pin number
    // Returns: ADC value (0-4095 for ESP32 12-bit ADC)
    virtual uint16_t analogRead(uint8_t gpio) = 0;

    // ============================================
    // EMERGENCY SAFE-MODE
    // ============================================
    // Emergency function: Return ALL pins to safe mode (INPUT_PULLUP)
    // Used in error conditions to prevent hardware damage
    virtual void enableSafeModeForAllPins() = 0;

    // ============================================
    // INFORMATION METHODS
    // ============================================
    // Get detailed information about a specific pin
    // gpio: Pin number
    // Returns: GPIOPinInfo structure (owner, mode, safe mode status)
    virtual GPIOPinInfo getPinInfo(uint8_t gpio) const = 0;

    // Get list of all reserved (non-safe-mode) pins
    // Returns: Vector of GPIOPinInfo for all reserved pins
    virtual std::vector<GPIOPinInfo> getReservedPinsList() const = 0;

    // Get count of reserved pins (not in safe mode)
    // Returns: Number of pins actively in use
    virtual uint8_t getReservedPinCount() const = 0;

    // Get count of available (unallocated) pins
    // Returns: Number of pins available for use
    virtual uint8_t getAvailablePinCount() const = 0;

    // Get owner of a reserved pin
    // gpio: Pin number
    // Returns: Owner string ("sensor", "actuator", "system") or empty if not reserved
    virtual String getPinOwner(uint8_t gpio) const = 0;

    // Get component name of a reserved pin
    // gpio: Pin number
    // Returns: Component name (e.g., "DS18B20", "Pump1") or empty if not reserved
    virtual String getPinComponent(uint8_t gpio) const = 0;
};

#endif  // DRIVERS_HAL_IGPIO_HAL_H
