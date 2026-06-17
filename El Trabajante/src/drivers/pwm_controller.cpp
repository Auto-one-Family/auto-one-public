#include "pwm_controller.h"
#include "../utils/logger.h"
#include "../drivers/gpio_manager.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"

// ESP32 LEDC (PWM) library
#include "driver/ledc.h"

// ============================================
// CONDITIONAL HARDWARE CONFIGURATION INCLUDES
// ============================================
#ifdef XIAO_ESP32C3
    #include "../config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "../config/hardware/esp32_s3_devkit.h"
#else
    #include "../config/hardware/esp32_dev.h"
#endif

// ESP-IDF TAG convention for structured logging
static const char* TAG = "PWM";

// ============================================
// GLOBAL INSTANCE
// ============================================
PWMController& pwmController = PWMController::getInstance();

// ============================================
// LIFECYCLE: INITIALIZATION
// ============================================
bool PWMController::begin() {
    // Prevent double initialization
    if (initialized_) {
        LOG_W(TAG, "PWM Controller already initialized");
        return true;
    }

    LOG_I(TAG, "PWM Controller initialization started");
    
    // Load hardware-specific configuration
    max_channels_ = HardwareConfig::PWM_CHANNELS;
    default_frequency_ = HardwareConfig::PWM_FREQUENCY;
    default_resolution_ = HardwareConfig::PWM_RESOLUTION;
    
    LOG_D(TAG, "PWM Config: Channels=" + String(max_channels_) + 
              ", Freq=" + String(default_frequency_) + "Hz" +
              ", Resolution=" + String(default_resolution_) + " bits");
    
    // Initialize all channels with default settings (but not attached to GPIOs)
    for (uint8_t channel = 0; channel < max_channels_; channel++) {
        // Configure LEDC timer and channel
        ledcSetup(channel, default_frequency_, default_resolution_);
        
        // Initialize channel info
        channels_[channel].attached = false;
        channels_[channel].gpio = 255;
        channels_[channel].frequency = default_frequency_;
        channels_[channel].resolution = default_resolution_;
        
        LOG_D(TAG, "PWM Channel " + String(channel) + " configured (not attached)");
    }
    
    initialized_ = true;
    
    LOG_I(TAG, "PWM Controller initialized successfully");
    LOG_I(TAG, "  Board: " + String(BOARD_TYPE));
    LOG_I(TAG, "  Channels: " + String(max_channels_));
    LOG_I(TAG, "  Default Frequency: " + String(default_frequency_) + " Hz");
    LOG_I(TAG, "  Default Resolution: " + String(default_resolution_) + " bits");
    
    return true;
}

// ============================================
// LIFECYCLE: DEINITIALIZATION
// ============================================
void PWMController::end() {
    if (!initialized_) {
        LOG_W(TAG, "PWM Controller not initialized, nothing to end");
        return;
    }
    
    LOG_I(TAG, "PWM Controller shutdown initiated");
    
    // Detach all channels
    for (uint8_t channel = 0; channel < max_channels_; channel++) {
        if (channels_[channel].attached) {
            detachChannel(channel);
        }
    }
    
    initialized_ = false;
    
    LOG_I(TAG, "PWM Controller shutdown complete");
}

// ============================================
// CHANNEL MANAGEMENT: ATTACH
// ============================================
bool PWMController::attachChannel(uint8_t gpio, uint8_t& channel_out) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        errorTracker.trackError(ERROR_PWM_INIT_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Attach failed: controller not initialized");
        return false;
    }
    
    // Check if GPIO is already attached
    for (uint8_t ch = 0; ch < max_channels_; ch++) {
        if (channels_[ch].attached && channels_[ch].gpio == gpio) {
            LOG_W(TAG, "GPIO " + String(gpio) + " already attached to channel " + String(ch));
            channel_out = ch;
            return true;
        }
    }
    
    // Find free channel
    uint8_t free_channel = 255;
    for (uint8_t ch = 0; ch < max_channels_; ch++) {
        if (!channels_[ch].attached) {
            free_channel = ch;
            break;
        }
    }
    
    if (free_channel == 255) {
        LOG_E(TAG, "No free PWM channels available");
        errorTracker.trackError(ERROR_PWM_CHANNEL_FULL,
                               ERROR_SEVERITY_ERROR,
                               ("All " + String(max_channels_) + " channels in use").c_str());
        return false;
    }
    
    // Reserve GPIO pin
    if (!gpioManager.requestPin(gpio, "actuator", "PWM")) {
        LOG_E(TAG, "Failed to reserve GPIO " + String(gpio) + " for PWM");
        errorTracker.trackError(ERROR_PWM_INIT_FAILED,
                               ERROR_SEVERITY_ERROR,
                               ("GPIO reservation failed: " + String(gpio)).c_str());
        return false;
    }
    
    // Attach pin to LEDC channel
    ledcAttachPin(gpio, free_channel);
    
    // Update channel info
    channels_[free_channel].attached = true;
    channels_[free_channel].gpio = gpio;
    
    channel_out = free_channel;
    
    LOG_I(TAG, "PWM Channel " + String(free_channel) + " attached to GPIO " + String(gpio));
    
    return true;
}

// ============================================
// CHANNEL MANAGEMENT: DETACH
// ============================================
bool PWMController::detachChannel(uint8_t channel) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        return false;
    }
    
    if (channel >= max_channels_) {
        LOG_E(TAG, "Invalid channel: " + String(channel));
        return false;
    }
    
    if (!channels_[channel].attached) {
        LOG_W(TAG, "Channel " + String(channel) + " not attached");
        return false;
    }
    
    uint8_t gpio = channels_[channel].gpio;
    
    // Set PWM to 0 before detaching (safety)
    ledcWrite(channel, 0);
    
    // Detach pin from LEDC channel
    ledcDetachPin(gpio);
    
    // Release GPIO pin
    gpioManager.releasePin(gpio);
    
    // Update channel info
    channels_[channel].attached = false;
    channels_[channel].gpio = 255;
    
    LOG_I(TAG, "PWM Channel " + String(channel) + " detached from GPIO " + String(gpio));
    
    return true;
}

// ============================================
// PWM CONFIGURATION: FREQUENCY
// ============================================
bool PWMController::setFrequency(uint8_t channel, uint32_t frequency) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        return false;
    }
    
    if (channel >= max_channels_) {
        LOG_E(TAG, "Invalid channel: " + String(channel));
        return false;
    }
    
    if (!channels_[channel].attached) {
        LOG_E(TAG, "Channel " + String(channel) + " not attached");
        return false;
    }
    
    if (frequency == 0 || frequency > 40000000) {  // Max 40MHz
        LOG_E(TAG, "Invalid frequency: " + String(frequency) + " Hz");
        return false;
    }
    
    // Reconfigure LEDC channel with new frequency
    ledcSetup(channel, frequency, channels_[channel].resolution);
    
    // Reattach pin (necessary after ledcSetup)
    ledcAttachPin(channels_[channel].gpio, channel);
    
    channels_[channel].frequency = frequency;
    
    LOG_D(TAG, "PWM Channel " + String(channel) + " frequency set to " + String(frequency) + " Hz");
    
    return true;
}

// ============================================
// PWM CONFIGURATION: RESOLUTION
// ============================================
bool PWMController::setResolution(uint8_t channel, uint8_t resolution_bits) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        return false;
    }
    
    if (channel >= max_channels_) {
        LOG_E(TAG, "Invalid channel: " + String(channel));
        return false;
    }
    
    if (!channels_[channel].attached) {
        LOG_E(TAG, "Channel " + String(channel) + " not attached");
        return false;
    }
    
    if (resolution_bits == 0 || resolution_bits > 16) {
        LOG_E(TAG, "Invalid resolution: " + String(resolution_bits) + " bits (1-16)");
        return false;
    }
    
    // Reconfigure LEDC channel with new resolution
    ledcSetup(channel, channels_[channel].frequency, resolution_bits);
    
    // Reattach pin (necessary after ledcSetup)
    ledcAttachPin(channels_[channel].gpio, channel);
    
    channels_[channel].resolution = resolution_bits;
    
    LOG_D(TAG, "PWM Channel " + String(channel) + " resolution set to " + String(resolution_bits) + " bits");
    
    return true;
}

// ============================================
// PWM OUTPUT: ABSOLUTE DUTY CYCLE
// ============================================
bool PWMController::write(uint8_t channel, uint32_t duty_cycle) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        errorTracker.trackError(ERROR_PWM_SET_FAILED,
                               ERROR_SEVERITY_ERROR,
                               "Write failed: controller not initialized");
        return false;
    }
    
    if (channel >= max_channels_) {
        LOG_E(TAG, "Invalid channel: " + String(channel));
        return false;
    }
    
    if (!channels_[channel].attached) {
        LOG_E(TAG, "Channel " + String(channel) + " not attached");
        return false;
    }
    
    // Calculate max duty cycle for current resolution
    uint32_t max_duty = (1 << channels_[channel].resolution) - 1;
    
    if (duty_cycle > max_duty) {
        LOG_E(TAG, "Duty cycle " + String(duty_cycle) + " exceeds max " + String(max_duty));
        errorTracker.trackError(ERROR_PWM_SET_FAILED,
                               ERROR_SEVERITY_WARNING,
                               "Duty cycle out of range");
        return false;
    }
    
    // Write duty cycle to LEDC channel
    ledcWrite(channel, duty_cycle);
    
    LOG_D(TAG, "PWM Channel " + String(channel) + " duty set to " + String(duty_cycle) + 
              "/" + String(max_duty));
    
    return true;
}

// ============================================
// PWM OUTPUT: PERCENTAGE DUTY CYCLE
// ============================================
bool PWMController::writePercent(uint8_t channel, float percent) {
    if (!initialized_) {
        LOG_E(TAG, "PWM Controller not initialized");
        return false;
    }
    
    if (channel >= max_channels_) {
        LOG_E(TAG, "Invalid channel: " + String(channel));
        return false;
    }
    
    if (!channels_[channel].attached) {
        LOG_E(TAG, "Channel " + String(channel) + " not attached");
        return false;
    }
    
    if (percent < 0.0 || percent > 100.0) {
        LOG_E(TAG, "Invalid percentage: " + String(percent, 1) + "% (0-100)");
        return false;
    }
    
    // Calculate max duty cycle for current resolution
    uint32_t max_duty = (1 << channels_[channel].resolution) - 1;
    
    // Convert percentage to duty cycle
    uint32_t duty_cycle = (uint32_t)((percent / 100.0) * max_duty);
    
    // Write duty cycle
    ledcWrite(channel, duty_cycle);
    
    LOG_D(TAG, "PWM Channel " + String(channel) + " set to " + String(percent, 1) + 
              "% (" + String(duty_cycle) + "/" + String(max_duty) + ")");
    
    return true;
}

// ============================================
// STATUS QUERIES
// ============================================
bool PWMController::isChannelAttached(uint8_t channel) const {
    if (channel >= max_channels_) {
        return false;
    }
    return channels_[channel].attached;
}

uint8_t PWMController::getChannelForGPIO(uint8_t gpio) const {
    for (uint8_t ch = 0; ch < max_channels_; ch++) {
        if (channels_[ch].attached && channels_[ch].gpio == gpio) {
            return ch;
        }
    }
    return 255;  // Not found
}

String PWMController::getChannelStatus() const {
    String status = "PWM Controller Status:\n";
    status += "  Initialized: " + String(initialized_ ? "Yes" : "No") + "\n";
    status += "  Max Channels: " + String(max_channels_) + "\n";
    status += "  Attached Channels:\n";
    
    uint8_t attached_count = 0;
    for (uint8_t ch = 0; ch < max_channels_; ch++) {
        if (channels_[ch].attached) {
            attached_count++;
            status += "    Ch" + String(ch) + ": GPIO" + String(channels_[ch].gpio);
            status += " [" + String(channels_[ch].frequency) + "Hz, ";
            status += String(channels_[ch].resolution) + "bit]\n";
        }
    }
    
    if (attached_count == 0) {
        status += "    (None)\n";
    }

    return status;
}
