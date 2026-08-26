# Test Mocks

## Purpose

Minimal Arduino API mocks for native x86_64 unit tests. Allows testing Pure-Logic modules (TopicBuilder, OneWireUtils, etc.) without ESP32 hardware.

## Contents

- **Arduino.h** - Mock Arduino API (String, millis, delay, Serial)
- **mock_arduino.cpp** - String constructor implementations

## Design Principles

1. **Minimal** - Only implements features actually used by firmware
2. **Compatible** - Provides same API as real Arduino.h
3. **No-op** - Hardware functions (delay, Serial) are no-ops
4. **STL-based** - Uses std::string internally for simplicity

## Usage

```cpp
#ifdef NATIVE_TEST
    #include "../mocks/Arduino.h"  // from test/<suite>/ — explicit path
#else
    #include <Arduino.h>  // Real Arduino API
#endif
```

Native builds need `gcc`/`g++` on `PATH` or under paths probed by `scripts/set_native_toolchain.py` (e.g. Git for Windows `mingw64`).

## Implemented Features

- String class (constructor, c_str, length, operators)
- millis() - always returns 0
- delay() - no-op
- Serial - no-op (minimal interface)

## NOT Implemented

- GPIO functions (pinMode, digitalWrite, digitalRead, analogRead)
- I2C/SPI/OneWire
- WiFi/Network
- File System
- EEPROM/NVS

These are hardware-dependent and tested via:
- **Pattern B/C/E** - HAL-Mocks (Phase 2)
- **Wokwi** - Full firmware simulation
- **Hardware Tests** - esp32dev_test environment

## Future Extensions

Phase 2 will add HAL-Interfaces for hardware abstraction:
- IGPIOHal
- II2CHal
- IOneWireHal
- INVSHal
- IWiFiHal
- IMQTTHal

See `.technical-manager/commands/pending/Unit_tests_esp32.md` Phase 2.
