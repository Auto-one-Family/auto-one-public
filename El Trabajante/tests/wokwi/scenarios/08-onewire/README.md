# OneWire Bus Test Suite

> **Module:** OneWire Bus Driver (`drivers/onewire_bus.cpp`)
> **Phase:** 3 - Hardware Abstraction Layer
> **Priority:** HIGH - Critical for DS18B20 Temperature Sensors
> **Created:** 2026-01-28

---

## Overview

This test suite validates the OneWire Bus driver implementation for DS18B20 temperature sensors. The OneWire protocol enables multiple sensors on a single GPIO pin, making it essential for distributed temperature monitoring in greenhouse automation.

**Key Features Tested:**
- Single-wire protocol communication
- ROM-based device identification
- CRC-8 validation
- Raw temperature reading (Server-Centric architecture)
- GPIO sharing for multiple sensors

---

## Test Categories

### 1. Initialization Tests (OW-INIT)

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_init_success.yaml` | OW-INIT-001 | Successful bus initialization on GPIO 4 |
| `onewire_init_double_same_pin.yaml` | OW-INIT-002 | Reinitialization on same pin succeeds |
| `onewire_bus_reset.yaml` | OW-INIT-004 | Bus reset operation verification |
| `onewire_bus_end.yaml` | OW-INIT-005 | Bus deinitialization and cleanup |
| `onewire_parasitic_power.yaml` | OW-INIT-006 | Parasitic power mode detection |

### 2. Device Discovery Tests (OW-DISC)

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_discovery_single.yaml` | OW-DISC-001 | Single DS18B20 device discovery |
| `onewire_no_devices.yaml` | OW-DISC-002 | Empty bus handling |
| `onewire_device_presence.yaml` | OW-DISC-003 | Device presence verification |
| `onewire_family_code.yaml` | OW-DISC-005 | Family code recognition (0x28=DS18B20) |
| `onewire_mqtt_scan_command.yaml` | OW-DISC-006 | MQTT-triggered device scan |

### 3. Temperature Reading Tests (OW-TEMP)

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_temp_read_raw.yaml` | OW-TEMP-001 | Raw temperature value reading |
| `onewire_sensor_config_ds18b20.yaml` | OW-TEMP-002 | DS18B20 sensor configuration flow |
| `onewire_temperature_flow.yaml` | OW-TEMP-003 | Complete temp reading + MQTT publish |
| `onewire_conversion_time.yaml` | OW-TEMP-004 | 750ms conversion time handling |
| `onewire_scratchpad_read.yaml` | OW-TEMP-005 | 9-byte scratchpad reading |

### 4. Utility Function Tests (OW-UTIL)

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_rom_conversion.yaml` | OW-UTIL-001 | ROM to hex string conversion |
| `onewire_device_type_detection.yaml` | OW-UTIL-002 | Device type detection from family code |
| `onewire_bus_status.yaml` | OW-STATUS-001 | Status query methods |

### 5. Error Handling Tests (OW-ERR)

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_crc_validation.yaml` | OW-ERR-001 | CRC-8 validation during discovery |
| `onewire_gpio_conflict.yaml` | OW-ERR-002 | GPIO conflict detection |
| `onewire_rom_length_validation.yaml` | OW-ERR-003 | ROM code length validation (16 chars) |
| `onewire_duplicate_rom_detection.yaml` | OW-ERR-004 | Duplicate ROM code rejection |
| `onewire_read_timeout.yaml` | OW-ERR-005 | Read timeout handling |

### 6. Architecture Tests

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_single_bus_architecture.yaml` | OW-ARCH-001 | Single bus enforcement |
| `onewire_gpio_sharing.yaml` | OW-MULTI-001 | GPIO sharing for multiple sensors |

### 7. End-to-End Tests

| File | Test ID | Description |
|------|---------|-------------|
| `onewire_full_flow_ds18b20.yaml` | OW-E2E-001 | Complete DS18B20 lifecycle |

---

## Running Tests

### Prerequisites

1. Build firmware for Wokwi simulation:
```bash
cd "El Trabajante"
pio run -e wokwi_simulation
```

2. Install Wokwi CLI and set token:
```bash
export WOKWI_CLI_TOKEN=your_token
```

### Execute Tests

```bash
cd "El Trabajante"

# Single test
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/08-onewire/onewire_init_success.yaml

# All OneWire tests (manual)
for f in tests/wokwi/scenarios/08-onewire/*.yaml; do
  echo "Running: $f"
  wokwi-cli . --timeout 90000 --scenario "$f"
done
```

---

## Hardware Configuration

### Wokwi diagram.json

The default `diagram.json` includes:
- ESP32 DevKit V1
- DS18B20 on GPIO 4 (data pin)
- 4.7kΩ pull-up resistor
- Temperature: 22.5°C (configurable)

```json
{
  "type": "wokwi-ds18b20",
  "id": "temp1",
  "attrs": {
    "temperature": "22.5"
  }
}
```

### Multi-Sensor Testing

For multi-sensor tests, extend `diagram.json`:
```json
{
  "type": "wokwi-ds18b20",
  "id": "temp2",
  "attrs": {
    "temperature": "25.0"
  }
}
```

Connect both to GPIO 4 (shared bus).

---

## API Reference

### OneWireBusManager (Singleton)

```cpp
// Initialization
bool begin(uint8_t pin = 0);  // 0 = use default GPIO 4
void end();

// Device Discovery
bool scanDevices(uint8_t rom_codes[][8], uint8_t max_devices, uint8_t& found_count);
bool isDevicePresent(const uint8_t rom_code[8]);

// Temperature Reading
bool readRawTemperature(const uint8_t rom_code[8], int16_t& raw_value);

// Status Queries
bool isInitialized() const;
uint8_t getPin() const;
String getBusStatus() const;
```

### OneWireUtils Namespace

```cpp
String romToHexString(const uint8_t rom[8]);
bool hexStringToRom(const String& hex, uint8_t rom[8]);
bool isValidRom(const uint8_t rom[8]);
String getDeviceType(const uint8_t rom[8]);
```

---

## Error Codes

| Code | Constant | Description |
|------|----------|-------------|
| 1020 | ERROR_ONEWIRE_INIT_FAILED | Bus initialization failed |
| 1021 | ERROR_ONEWIRE_NO_DEVICES | No devices found on bus |
| 1022 | ERROR_ONEWIRE_READ_FAILED | Temperature read failed |
| 1023 | ERROR_ONEWIRE_INVALID_ROM_LENGTH | ROM not 16 hex chars |
| 1024 | ERROR_ONEWIRE_INVALID_ROM_FORMAT | ROM contains invalid chars |
| 1025 | ERROR_ONEWIRE_INVALID_ROM_CRC | ROM CRC validation failed |
| 1026 | ERROR_ONEWIRE_DEVICE_NOT_FOUND | Device not present on bus |
| 1027 | ERROR_ONEWIRE_BUS_NOT_INITIALIZED | Bus not initialized |
| 1028 | ERROR_ONEWIRE_READ_TIMEOUT | Device read timeout |
| 1029 | ERROR_ONEWIRE_DUPLICATE_ROM | ROM already registered |

---

## Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Wokwi DS18B20 returns constant temp | Cannot test temp-based logic | Server tests cover this |
| Single sensor in diagram.json | Multi-sensor limited | Extend diagram.json |
| No CRC error injection | CRC error path untestable | Unit tests |
| 90s max timeout | Long conversion tests | Split tests |

---

## Related Documentation

- [OneWire Bus Implementation](../../src/drivers/onewire_bus.cpp)
- [OneWire Utils](../../src/utils/onewire_utils.cpp)
- [Sensor Manager](../../src/services/sensor/sensor_manager.cpp)
- [DS18B20 Datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf)
- [System Flow 02: Sensor Reading](../../docs/system-flows/02-sensor-reading-flow.md)

---

**Test Suite Version:** 1.0
**Last Updated:** 2026-01-28
