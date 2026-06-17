#ifndef DRIVERS_PWM_CONTROLLER_H
#define DRIVERS_PWM_CONTROLLER_H

#include <Arduino.h>

// ============================================
// PWM Controller - Hardware Abstraction Layer
// ============================================
// Phase 3: Hardware Abstraction Layer
// Documentation: Phase_3.md lines 323-421
// Architecture: Actuator Control (Phase 5)
//
// Purpose: PWM signal generation for actuators
// - Board-agnostic PWM initialization (XIAO: 6 channels, WROOM: 16 channels)
// - Channel management with GPIO reservation
// - Frequency and resolution control
// - Duty cycle control (absolute or percentage)

// ============================================
// PWM CHANNEL INFO STRUCTURE
// ============================================
struct PWMChannelInfo {
    bool attached;          // Channel is in use
    uint8_t gpio;           // GPIO pin attached to channel
    uint32_t frequency;     // PWM frequency in Hz
    uint8_t resolution;     // PWM resolution in bits (1-16)
    
    PWMChannelInfo() 
        : attached(false), 
          gpio(255), 
          frequency(1000), 
          resolution(12) {}
};

// ============================================
// PWM CONTROLLER CLASS
// ============================================
// Singleton class managing PWM operations

class PWMController {
public:
    // ============================================
    // SINGLETON PATTERN
    // ============================================
    static PWMController& getInstance() {
        static PWMController instance;
        return instance;
    }

    // Prevent copy and move operations
    PWMController(const PWMController&) = delete;
    PWMController& operator=(const PWMController&) = delete;
    PWMController(PWMController&&) = delete;
    PWMController& operator=(PWMController&&) = delete;

    // ============================================
    // LIFECYCLE MANAGEMENT
    // ============================================
    // Initialize PWM system with hardware-specific defaults
    // Loads configuration from HardwareConfig
    // Configures all channels with default frequency/resolution
    // Returns false if initialization fails
    bool begin();

    // Deinitialize PWM system and release all channels
    void end();

    // ============================================
    // CHANNEL MANAGEMENT
    // ============================================
    // Attach a GPIO pin to a PWM channel
    // gpio: GPIO pin to attach
    // channel_out: Output parameter with assigned channel number
    // Returns false if no channels available or GPIO invalid
    bool attachChannel(uint8_t gpio, uint8_t& channel_out);

    // Detach a PWM channel and release GPIO pin
    // channel: Channel to detach (0-15)
    // Returns false if channel not attached
    bool detachChannel(uint8_t channel);

    // ============================================
    // PWM CONFIGURATION
    // ============================================
    // Set PWM frequency for a channel
    // channel: Channel number (0-15)
    // frequency: Frequency in Hz (1 Hz - 40 MHz)
    // Returns false if channel not attached or frequency invalid
    bool setFrequency(uint8_t channel, uint32_t frequency);

    // Set PWM resolution for a channel
    // channel: Channel number (0-15)
    // resolution_bits: Resolution in bits (1-16)
    //                  Higher resolution = lower max frequency
    // Returns false if channel not attached or resolution invalid
    bool setResolution(uint8_t channel, uint8_t resolution_bits);

    // ============================================
    // PWM OUTPUT CONTROL
    // ============================================
    // Set PWM duty cycle (absolute value)
    // channel: Channel number (0-15)
    // duty_cycle: Duty cycle value (0 to 2^resolution - 1)
    //            Example: For 12-bit, range is 0-4095
    // Returns false if channel not attached or value out of range
    bool write(uint8_t channel, uint32_t duty_cycle);

    // Set PWM duty cycle (percentage)
    // channel: Channel number (0-15)
    // percent: Duty cycle percentage (0.0 - 100.0)
    // Returns false if channel not attached or value out of range
    bool writePercent(uint8_t channel, float percent);

    // ============================================
    // STATUS QUERIES
    // ============================================
    // Check if PWM controller is initialized
    bool isInitialized() const { return initialized_; }

    // Check if a specific channel is attached
    bool isChannelAttached(uint8_t channel) const;

    // Get channel number for a GPIO pin
    // Returns 255 if GPIO not attached to any channel
    uint8_t getChannelForGPIO(uint8_t gpio) const;

    // Get detailed status of all channels
    String getChannelStatus() const;

private:
    // ============================================
    // PRIVATE CONSTRUCTOR (SINGLETON)
    // ============================================
    PWMController() 
        : initialized_(false),
          max_channels_(16),
          default_frequency_(1000),
          default_resolution_(12) {
        // Initialize channel array
        for (uint8_t i = 0; i < 16; i++) {
            channels_[i] = PWMChannelInfo();
        }
    }
    
    ~PWMController() {}

    // ============================================
    // INTERNAL STATE
    // ============================================
    bool initialized_;              // Controller initialization status
    uint8_t max_channels_;          // Max PWM channels (6 for XIAO, 16 for WROOM)
    uint32_t default_frequency_;    // Default frequency in Hz
    uint8_t default_resolution_;    // Default resolution in bits
    PWMChannelInfo channels_[16];   // Channel information array (max 16)
};

// ============================================
// GLOBAL INSTANCE ACCESS
// ============================================
extern PWMController& pwmController;

#endif // DRIVERS_PWM_CONTROLLER_H
