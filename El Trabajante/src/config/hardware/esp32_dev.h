#ifndef CONFIG_HARDWARE_ESP32_DEV_H
#define CONFIG_HARDWARE_ESP32_DEV_H

#include <Arduino.h>

// ============================================
// ESP32-WROOM-32 Dev Board Hardware Configuration
// ============================================
// Board: ESP32-WROOM-32 Development Board
// Chip: ESP32 Dual-Core Xtensa LX6
// Documentation: ZZZ.md lines 1930-1950
// Migration: Phase 0 Hardware Safety Foundation

// Board Identifier
#define BOARD_TYPE "ESP32_WROOM_32"
#define MAX_GPIO_PINS 24  // ESP32 WROOM has more GPIO pins available

namespace HardwareConfig {

// Server-normalized hardware_type for MQTT heartbeat (matches El Servador constants)
constexpr char HEARTBEAT_HARDWARE_TYPE[] = "ESP32_WROOM";

// ============================================
// RESERVED PINS (CRITICAL - DO NOT USE!)
// ============================================
// These pins are reserved for boot, UART, flash, and strapping
// Using these pins can prevent the board from booting or cause flash issues

const uint8_t RESERVED_GPIO_PINS[] = {
    0,   // Boot Button / Strapping Pin
    1,   // UART0 TX (USB Serial)
    2,   // Boot Strapping Pin (must be LOW during boot)
    3,   // UART0 RX (USB Serial)
    12,  // Flash Voltage Strapping Pin
    13   // Flash Voltage Strapping Pin
};
const uint8_t RESERVED_PIN_COUNT = 6;

// ============================================
// SAFE GPIO PINS (AVAILABLE FOR USE)
// ============================================
// These pins are safe to use for sensors, actuators, and general I/O

const uint8_t SAFE_GPIO_PINS[] = {
    4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33,
    34, 35, 36, 39  // Input-only ADC1 pins (no internal pull-ups, no output mode)
};
const uint8_t SAFE_PIN_COUNT = 20;

// ============================================
// INPUT-ONLY PINS (NO OUTPUT MODE!)
// ============================================
// These pins can ONLY be used as inputs - no internal pull-ups available
// Attempting to use pinMode(pin, OUTPUT) on these pins will fail

const uint8_t INPUT_ONLY_PINS[] = {
    34, 35, 36, 39
};
const uint8_t INPUT_ONLY_PIN_COUNT = 4;

// ============================================
// I2C HARDWARE PINS
// ============================================
// Hardware I2C bus configuration
// Use these pins for I2C sensors (BMP280, SSD1306, etc.)

constexpr uint8_t I2C_SDA_PIN = 21;        // Hardware I2C SDA
constexpr uint8_t I2C_SCL_PIN = 22;        // Hardware I2C SCL
constexpr uint32_t I2C_FREQUENCY = 100000; // 100kHz (Standard Mode)

// ============================================
// ONEWIRE CONFIGURATION
// ============================================
// Recommended pin for OneWire devices (DS18B20 temperature sensors)

constexpr uint8_t DEFAULT_ONEWIRE_PIN = 4;

// ============================================
// PWM CONFIGURATION
// ============================================
// ESP32 WROOM PWM (LEDC) specifications

constexpr uint8_t PWM_CHANNELS = 16;      // ESP32 has 16 PWM channels
constexpr uint32_t PWM_FREQUENCY = 1000;  // 1kHz default frequency
constexpr uint8_t PWM_RESOLUTION = 12;    // 12-bit resolution (0-4095)

// ============================================
// BOARD-SPECIFIC FEATURES
// ============================================

constexpr uint8_t LED_PIN = 5;      // Status LED (GPIO5, safe for all modes)
                                            // Note: GPIO2 is strapping pin, avoided for compatibility
constexpr uint8_t BUTTON_PIN = 0;   // Boot Button (GPIO0) - RESERVED!

// ============================================
// ANALOG INPUT CONFIGURATION
// ============================================
// ESP32 has 18 ADC channels (ADC1: GPIO32-39, ADC2: GPIO0-27)
// ADC resolution: 12-bit (0-4095)
// CRITICAL: ADC2 pins CANNOT be used when WiFi is active!

constexpr uint8_t ADC_RESOLUTION = 12;
constexpr uint16_t ADC_MAX_VALUE = 4095;

// ============================================
// ADC2 PINS (CONFLICT WITH WIFI!)
// ============================================
// These pins share the ADC2 peripheral with WiFi.
// analogRead() on these pins will return ESP_ERR_TIMEOUT when WiFi is active.
// Only ADC1 pins (GPIO32-39) are safe for analog reads with WiFi.

const uint8_t ADC2_GPIO_PINS[] = {
    0, 2, 4, 12, 13, 14, 15, 25, 26, 27
};
const uint8_t ADC2_PIN_COUNT = 10;

} // namespace HardwareConfig

#endif // CONFIG_HARDWARE_ESP32_DEV_H
