#ifndef CONFIG_HARDWARE_ESP32_S3_DEVKIT_H
#define CONFIG_HARDWARE_ESP32_S3_DEVKIT_H

#include <Arduino.h>

// ============================================
// ESP32-S3-DevKitC-1 N8R8 (8MB Flash, 8MB Octal PSRAM) — Hardware Configuration
// ============================================
// N8R8 (ESP32-S3R8): Octal Flash + Octal PSRAM — GPIO 26–37 sind SPI0/1 (IDF: nicht umkonfigurieren).
// DevKit-Header nutzbar: 1–18, 21, 39–42, 47 (siehe SAFE_GPIO_PINS).
// GPIO-Map: ESP32_S3_DEVKIT_MODE in platformio env esp32-s3-devkitc-1

#define BOARD_TYPE "ESP32_S3_DEVKITC1"
#define MAX_GPIO_PINS 40

namespace HardwareConfig {

// Server-normalized hardware_type for MQTT heartbeat (matches El Servador constants)
constexpr char HEARTBEAT_HARDWARE_TYPE[] = "ESP32_S3_DEVKITC1";

// Strapping, USB, Octal Flash/PSRAM (26–37), UART0, RGB-LED (v1.0 + v1.1)
const uint8_t RESERVED_GPIO_PINS[] = {
    0, 3,                                           // Strapping
    19, 20,                                         // USB Serial/JTAG (CDC)
    26, 27, 28, 29, 30, 31, 32,                   // SPI flash (Octal/Quad)
    33, 34, 35, 36, 37,                           // Octal SPIIO4–7 + SPIDQS
    38, 48,                                         // On-board RGB (v1.1 / v1.0)
    43, 44,                                         // UART0 TX/RX (Boot log vor CDC)
    45, 46                                          // Strapping / ROM debug
};
const uint8_t RESERVED_PIN_COUNT = 22;

// DevKit-Header-Pins ohne RESERVED-Konflikt (kein 26–37 — sonst TG1WDT beim Safe-Mode)
const uint8_t SAFE_GPIO_PINS[] = {
    1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21,
    39, 40, 41, 42, 47
};
const uint8_t SAFE_PIN_COUNT = 22;

// S3: keine WROOM input-only Pins 34–39
const uint8_t INPUT_ONLY_PINS[] = {};
const uint8_t INPUT_ONLY_PIN_COUNT = 0;

constexpr uint8_t I2C_SDA_PIN = 8;
constexpr uint8_t I2C_SCL_PIN = 9;
constexpr uint32_t I2C_FREQUENCY = 100000;

constexpr uint8_t DEFAULT_ONEWIRE_PIN = 4;

constexpr uint8_t PWM_CHANNELS = 8;
constexpr uint32_t PWM_FREQUENCY = 1000;
constexpr uint8_t PWM_RESOLUTION = 12;

// DevKitC-1 v1.1: RGB GPIO38; v1.0: GPIO48 (beide RESERVED)
constexpr uint8_t LED_PIN = 38;
constexpr uint8_t BUTTON_PIN = 0;

constexpr uint8_t ADC_RESOLUTION = 12;
constexpr uint16_t ADC_MAX_VALUE = 4095;

// ADC2 auf S3: GPIO11–20 — analogRead mit WiFi kann fehlschlagen
const uint8_t ADC2_GPIO_PINS[] = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 20
};
const uint8_t ADC2_PIN_COUNT = 10;

}  // namespace HardwareConfig

#endif  // CONFIG_HARDWARE_ESP32_S3_DEVKIT_H
