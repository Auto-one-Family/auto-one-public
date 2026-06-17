#ifndef DRIVERS_MHZ19_UART_H
#define DRIVERS_MHZ19_UART_H

#include <Arduino.h>

// MH-Z19 / SEN0220 UART CO2 reader (Serial2, config-driven pins)
// Server-Centric: returns raw PPM only — no calibration on ESP32

class Mhz19UartReader {
public:
    static Mhz19UartReader& getInstance() {
        static Mhz19UartReader instance;
        return instance;
    }

    Mhz19UartReader(const Mhz19UartReader&) = delete;
    Mhz19UartReader& operator=(const Mhz19UartReader&) = delete;
    Mhz19UartReader(Mhz19UartReader&&) = delete;
    Mhz19UartReader& operator=(Mhz19UartReader&&) = delete;

    bool begin(uint8_t rx_pin, uint8_t tx_pin, uint32_t baud = 9600);
    void end();
    bool isInitialized() const { return initialized_; }

    // Read raw CO2 PPM (0-50000). Frame-sync + readBytes(), 2s timeout.
    bool readRawPpm(uint16_t& ppm_out);

private:
    Mhz19UartReader();

    bool initialized_;
    uint8_t rx_pin_;
    uint8_t tx_pin_;
    uint32_t baud_;
    bool abc_disabled_;  // ABC disable sent after first successful read

    static bool validateChecksum(const uint8_t* frame, size_t len);
};

extern Mhz19UartReader& mhz19UartReader;

#endif  // DRIVERS_MHZ19_UART_H
