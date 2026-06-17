#ifndef CONFIG_HARDWARE_XIAO_ESP32C3_H
#define CONFIG_HARDWARE_XIAO_ESP32C3_H

#include <Arduino.h>

// ============================================
// XIAO ESP32-C3 Hardware Configuration
// ============================================
// Board: Seeed Studio XIAO ESP32-C3
// Chip: ESP32-C3 RISC-V Single-Core
// Documentation: ZZZ.md lines 1930-1950
// Migration: Phase 0 Hardware Safety Foundation

// Board Identifier
#define BOARD_TYPE "XIAO_ESP32C3"
#define MAX_GPIO_PINS 12  // XIAO has limited GPIO pins (0-21, but many reserved)

namespace HardwareConfig {

// Server-normalized hardware_type for MQTT heartbeat (matches El Servador constants)
constexpr char HEARTBEAT_HARDWARE_TYPE[] = "XIAO_ESP32_C3";

// ============================================
// RESERVED PINS (CRITICAL - DO NOT USE!)
// ============================================
// These pins are reserved for boot, UART, and USB functionality
// Using these pins can prevent the board from booting or communicating

const uint8_t RESERVED_GPIO_PINS[] = {
    0,  // Boot Button (GPIO0) - DO NOT USE
    1,  // UART0 TX (USB Serial) - DO NOT USE
    3   // UART0 RX (USB Serial) - DO NOT USE
};
const uint8_t RESERVED_PIN_COUNT = 3;

// ============================================
// SAFE GPIO PINS (AVAILABLE FOR USE)
// ============================================
// These pins are safe to use for sensors, actuators, and general I/O

const uint8_t SAFE_GPIO_PINS[] = {
    2, 4, 5, 6, 7, 8, 9, 10, 21
};
const uint8_t SAFE_PIN_COUNT = 9;

// ============================================
// I2C HARDWARE PINS
// ============================================
// Hardware I2C bus configuration
// Use these pins for I2C sensors (BMP280, SSD1306, etc.)

constexpr uint8_t I2C_SDA_PIN = 4;        // Hardware I2C SDA
constexpr uint8_t I2C_SCL_PIN = 5;        // Hardware I2C SCL
constexpr uint32_t I2C_FREQUENCY = 100000; // 100kHz (Standard Mode)

// ============================================
// ONEWIRE CONFIGURATION
// ============================================
// Recommended pin for OneWire devices (DS18B20 temperature sensors)

constexpr uint8_t DEFAULT_ONEWIRE_PIN = 6;

// ============================================
// PWM CONFIGURATION
// ============================================
// ESP32-C3 PWM (LEDC) specifications

constexpr uint8_t PWM_CHANNELS = 6;       // ESP32-C3 has 6 PWM channels
constexpr uint32_t PWM_FREQUENCY = 1000;  // 1kHz default frequency
constexpr uint8_t PWM_RESOLUTION = 12;    // 12-bit resolution (0-4095)

// ============================================
// BOARD-SPECIFIC FEATURES
// ============================================

constexpr uint8_t LED_PIN = 21;     // Built-in RGB LED (GPIO21)
constexpr uint8_t BUTTON_PIN = 0;   // Boot Button (GPIO0) - RESERVED!

// ============================================
// ANALOG INPUT CONFIGURATION
// ============================================
// ESP32-C3 has 6 ADC channels (GPIO0-5)
// ADC resolution: 12-bit (0-4095)

constexpr uint8_t ADC_RESOLUTION = 12;
constexpr uint16_t ADC_MAX_VALUE = 4095;

} // namespace HardwareConfig

#endif // CONFIG_HARDWARE_XIAO_ESP32C3_H
