#include "mhz19_uart.h"
#include "../utils/logger.h"
#include "../error_handling/error_tracker.h"
#include "../models/error_codes.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

static const char* TAG = "MHZ19";

// MH-Z19 warmup after power-on (~3 min per datasheet)
static const unsigned long MHZ19_WARMUP_MS = 180000;
// Serial2 rx buffer pre-allocated before begin() (must precede Serial2.begin())
static const uint16_t MHZ19_RX_BUFFER_SIZE = 512;
// setTimeout passed to Serial2 — covers sensor response latency + 9-byte frame at 9600 baud
static const uint16_t MHZ19_SERIAL_TIMEOUT_MS = 2000;
// Window to seek the 0xFF start byte after write+flush
static const uint16_t MHZ19_FRAMESYNC_TIMEOUT_MS = 2000;
// Max CO2 ppm for SEN0220 / MH-Z16 (0-50000 ppm range, NOT 5000 ppm)
static const uint16_t MHZ19_MAX_PPM = 50000;

static const uint8_t MHZ19_CMD_READ_PPM[9] = {
    0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79
};

// ABC (Auto-Baseline-Calibration) disable command — send once after first successful read.
// Required for cannabis grow / greenhouse: ABC would re-calibrate 800-1500 ppm CO2 as 400 ppm.
static const uint8_t MHZ19_CMD_ABC_OFF[9] = {
    0xFF, 0x01, 0x79, 0x00, 0x00, 0x00, 0x00, 0x00, 0x86
};

Mhz19UartReader& mhz19UartReader = Mhz19UartReader::getInstance();

Mhz19UartReader::Mhz19UartReader()
    : initialized_(false), rx_pin_(255), tx_pin_(255), baud_(9600),
      abc_disabled_(false) {}

bool Mhz19UartReader::begin(uint8_t rx_pin, uint8_t tx_pin, uint32_t baud) {
    if (rx_pin == 255 || tx_pin == 255 || rx_pin == 0 || tx_pin == 0 || baud == 0) {
        LOG_E(TAG, "Mhz19Uart: invalid pins rx=" + String(rx_pin) +
                   " tx=" + String(tx_pin) + " baud=" + String(baud));
        errorTracker.trackError(ERROR_UART_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "Invalid UART pin/baud for CO2");
        return false;
    }

    if (initialized_ && rx_pin_ == rx_pin && tx_pin_ == tx_pin && baud_ == baud) {
        LOG_D(TAG, "Mhz19Uart: already on Serial2 rx=" + String(rx_pin_) +
                   " tx=" + String(tx_pin_));
        return true;
    }

    if (initialized_) {
        Serial2.end();
        initialized_ = false;
    }

    rx_pin_ = rx_pin;
    tx_pin_ = tx_pin;
    baud_ = baud;

    // setRxBufferSize MUST be called before begin() — has no effect afterwards
    Serial2.setRxBufferSize(MHZ19_RX_BUFFER_SIZE);
    Serial2.begin(baud_, SERIAL_8N1, rx_pin_, tx_pin_);
    Serial2.setTimeout(MHZ19_SERIAL_TIMEOUT_MS);

    // Flush any startup noise from the sensor before marking as ready
    while (Serial2.available() > 0) {
        Serial2.read();
    }

    initialized_ = true;
    abc_disabled_ = false;
    LOG_I(TAG, "Mhz19Uart: Serial2 begin baud=" + String(baud_) +
              " rx=" + String(rx_pin_) + " tx=" + String(tx_pin_) +
              " rxbuf=" + String(MHZ19_RX_BUFFER_SIZE) +
              " timeout=" + String(MHZ19_SERIAL_TIMEOUT_MS) + "ms");
    return true;
}

void Mhz19UartReader::end() {
    if (initialized_) {
        Serial2.end();
        initialized_ = false;
        rx_pin_ = 255;
        tx_pin_ = 255;
        abc_disabled_ = false;
    }
}

bool Mhz19UartReader::validateChecksum(const uint8_t* frame, size_t len) {
    if (frame == nullptr || len < 9) {
        return false;
    }
    uint8_t sum = 0;
    for (size_t i = 1; i < 8; i++) {
        sum = static_cast<uint8_t>(sum + frame[i]);
    }
    sum = static_cast<uint8_t>((~sum) + 1);
    return sum == frame[8];
}

bool Mhz19UartReader::readRawPpm(uint16_t& ppm_out) {
    ppm_out = 0;
    if (!initialized_) {
        LOG_E(TAG, "Mhz19Uart: read without begin()");
        errorTracker.trackError(ERROR_UART_INIT_FAILED, ERROR_SEVERITY_ERROR,
                               "UART CO2 not initialized");
        return false;
    }

    // Flush stale RX bytes before sending command
    while (Serial2.available() > 0) {
        Serial2.read();
    }

    const size_t written = Serial2.write(MHZ19_CMD_READ_PPM, sizeof(MHZ19_CMD_READ_PPM));
    if (written != sizeof(MHZ19_CMD_READ_PPM)) {
        LOG_E(TAG, "Mhz19Uart: write failed written=" + String(written));
        errorTracker.trackError(ERROR_UART_READ_TIMEOUT, ERROR_SEVERITY_ERROR,
                               "UART CO2 write failed");
        return false;
    }
    // Wait for TX buffer to drain before listening for response
    Serial2.flush();

    // Frame-sync: seek 0xFF start byte within timeout window.
    // Spurious bytes or partial frames from prior reads are discarded here.
    uint8_t response[9] = {0};
    const unsigned long sync_deadline = millis() + MHZ19_FRAMESYNC_TIMEOUT_MS;
    bool start_found = false;
    while (static_cast<long>(millis() - sync_deadline) < 0) {
        if (Serial2.available() > 0) {
            const uint8_t b = static_cast<uint8_t>(Serial2.read());
            if (b == 0xFF) {
                response[0] = 0xFF;
                start_found = true;
                break;
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(1));
        }
    }
    if (!start_found) {
        LOG_W(TAG, "Mhz19Uart: timeout seeking 0xFF start byte rx=" +
                   String(rx_pin_) + " tx=" + String(tx_pin_));
        errorTracker.trackError(ERROR_UART_READ_TIMEOUT, ERROR_SEVERITY_WARNING,
                               "UART CO2 read timeout");
        return false;
    }

    // Read remaining 8 bytes using readBytes() — respects Serial2.setTimeout()
    const size_t received = Serial2.readBytes(response + 1, 8);
    if (received < 8) {
        LOG_W(TAG, "Mhz19Uart: short frame bytes=" + String(received + 1) +
                   "/9 rx=" + String(rx_pin_));
        errorTracker.trackError(ERROR_UART_READ_TIMEOUT, ERROR_SEVERITY_WARNING,
                               "UART CO2 short frame");
        return false;
    }

    if (!validateChecksum(response, sizeof(response))) {
        LOG_W(TAG, "Mhz19Uart: checksum mismatch");
        errorTracker.trackError(ERROR_UART_CHECKSUM_FAILED, ERROR_SEVERITY_WARNING,
                               "UART CO2 checksum failed");
        return false;
    }

    const uint16_t ppm = static_cast<uint16_t>(
        (static_cast<uint16_t>(response[2]) << 8) | response[3]);

    if (ppm > MHZ19_MAX_PPM) {
        LOG_W(TAG, "Mhz19Uart: PPM out of range: " + String(ppm));
        errorTracker.trackError(ERROR_UART_INVALID_PPM, ERROR_SEVERITY_WARNING,
                               "UART CO2 PPM out of range");
        return false;
    }

    // Disable ABC once after first successful read (idempotent: sensor stores in flash).
    // ABC re-calibrates the lowest measured CO2 as 400 ppm — wrong in grow environments.
    if (!abc_disabled_) {
        Serial2.write(MHZ19_CMD_ABC_OFF, sizeof(MHZ19_CMD_ABC_OFF));
        Serial2.flush();
        while (Serial2.available() > 0) {
            Serial2.read();
        }
        abc_disabled_ = true;
        LOG_I(TAG, "Mhz19Uart: ABC-mode disabled (one-time)");
    }

    ppm_out = ppm;
    return true;
}
