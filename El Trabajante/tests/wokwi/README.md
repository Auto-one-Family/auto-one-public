# Wokwi ESP32 Test Framework

> **Purpose:** Comprehensive test suite for ESP32 firmware validation using Wokwi simulation

---

## Overview

This test framework enables testing the ESP32 firmware without physical hardware by using the Wokwi virtual environment. Tests validate boot sequences, MQTT communication, sensor reading, actuator control, zone management, and emergency handling.

**Key Difference from Server Tests:**
- Server tests (`El Servador/tests/esp32/`) = Python tests against Mock/Real ESPs
- Wokwi tests = Real C++ firmware running in virtual environment

---

## Directory Structure

```
tests/wokwi/
├── README.md                    # This file
├── boot_test.yaml               # Legacy: Basic boot test
├── mqtt_connection.yaml         # Legacy: MQTT connection test
│
├── scenarios/
│   ├── 01-boot/
│   │   ├── boot_full.yaml       # Complete 5-phase boot test
│   │   └── boot_safe_mode.yaml  # GPIO safe-mode test
│   │
│   ├── 02-sensor/
│   │   ├── sensor_heartbeat.yaml    # Heartbeat publishing test
│   │   └── sensor_ds18b20_read.yaml # DS18B20 sensor test
│   │
│   ├── 03-actuator/
│   │   ├── actuator_led_on.yaml          # LED ON command test
│   │   ├── actuator_pwm.yaml             # PWM control test
│   │   ├── actuator_status_publish.yaml  # Status publishing test
│   │   └── actuator_emergency_clear.yaml # Emergency stop/clear test
│   │
│   ├── 04-zone/
│   │   ├── zone_assignment.yaml      # Zone assignment test
│   │   └── subzone_assignment.yaml   # Subzone handling test
│   │
│   ├── 05-emergency/
│   │   ├── emergency_broadcast.yaml  # Broadcast emergency test
│   │   └── emergency_esp_stop.yaml   # ESP-specific emergency test
│   │
│   └── 06-config/
│       ├── config_sensor_add.yaml    # Sensor config via MQTT
│       └── config_actuator_add.yaml  # Actuator config via MQTT
│
├── helpers/
│   └── mqtt_inject.py          # MQTT message injection tool
│
└── diagrams/
    └── diagram_extended.json   # Extended hardware configuration
```

---

## Test Categories

### 1. Boot Tests (HIGH Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `boot_full.yaml` | Validates all 5 boot phases | 90s |
| `boot_safe_mode.yaml` | Validates GPIO safe-mode initialization | 45s |

### 2. Sensor Tests (HIGH Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `sensor_heartbeat.yaml` | Validates heartbeat publishing (every 60s) | 90s |
| `sensor_ds18b20_read.yaml` | Validates OneWire sensor initialization | 90s |

### 3. Actuator Tests (MEDIUM Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `actuator_led_on.yaml` | Validates ON command handling | 90s |
| `actuator_pwm.yaml` | Validates PWM control | 90s |
| `actuator_status_publish.yaml` | Validates periodic status publishing | 90s |
| `actuator_emergency_clear.yaml` | Validates emergency stop/clear mechanism | 90s |

### 4. Zone Tests (MEDIUM Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `zone_assignment.yaml` | Validates zone assignment via MQTT | 90s |
| `subzone_assignment.yaml` | Validates subzone handling | 90s |

### 5. Emergency Tests (MEDIUM Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `emergency_broadcast.yaml` | Validates broadcast emergency stop | 90s |
| `emergency_esp_stop.yaml` | Validates ESP-specific emergency stop | 90s |

### 6. Config Tests (HIGH Priority)
| File | Purpose | Timeout |
|------|---------|---------|
| `config_sensor_add.yaml` | Validates runtime sensor configuration | 90s |
| `config_actuator_add.yaml` | Validates runtime actuator configuration | 90s |

---

## Prerequisites

### 1. Build Firmware

```bash
cd "El Trabajante"
pio run -e wokwi_simulation
```

### 2. Install Wokwi CLI

```bash
curl -L https://wokwi.com/ci/install.sh | sh
export PATH="$HOME/.wokwi/bin:$PATH"
```

### 3. Get Wokwi CLI Token

1. Visit https://wokwi.com/dashboard/ci
2. Create a new token
3. Set environment variable: `export WOKWI_CLI_TOKEN=your_token`

### 4. Start MQTT Broker (for MQTT tests)

**Docker (Recommended):**
```bash
mkdir -p /tmp/mosquitto
echo -e "listener 1883\nallow_anonymous true" > /tmp/mosquitto/mosquitto.conf
docker run -d -p 1883:1883 -v /tmp/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto:2
```

**Windows:**
```powershell
net start mosquitto
```

---

## Running Tests

### Local Development

```bash
cd "El Trabajante"

# Boot sequence test (new)
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/01-boot/boot_full.yaml

# Heartbeat test
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/02-sensor/sensor_heartbeat.yaml

# Legacy tests (still work)
wokwi-cli . --timeout 90000 --scenario tests/wokwi/boot_test.yaml
wokwi-cli . --timeout 90000 --scenario tests/wokwi/mqtt_connection.yaml
```

### CI/CD (GitHub Actions)

Tests run automatically on push/PR to `El Trabajante/` directory.
See `.github/workflows/wokwi-tests.yml` for CI configuration.

---

## MQTT Injection Helper

For tests requiring MQTT message injection, use the helper script:

```bash
# Install paho-mqtt
pip install paho-mqtt

# Send actuator command
python tests/wokwi/helpers/mqtt_inject.py \
  --topic "kaiser/god/esp/ESP_SIM/actuator/5/command" \
  --payload '{"command":"ON","value":1.0}'

# Send zone assignment
python tests/wokwi/helpers/mqtt_inject.py \
  --topic "kaiser/god/esp/ESP_SIM/zone/assign" \
  --payload '{"zone_id":"test","master_zone_id":"master","zone_name":"Test","kaiser_id":"god"}'

# Send emergency stop
python tests/wokwi/helpers/mqtt_inject.py \
  --topic "kaiser/broadcast/emergency" \
  --payload '{"auth_token":"master_token"}'
```

---

## Hardware Configuration

### Default Hardware (diagram.json)
- ESP32 DevKit V1
- DS18B20 Temperature Sensor (GPIO 4)
- LED (GPIO 5, PWM-capable)

### Extended Hardware (diagrams/diagram_extended.json)
- ESP32 DevKit V1
- DS18B20 Temperature Sensor (GPIO 4)
- LED Green (GPIO 5)
- LED Red (GPIO 18)
- Boot Button (GPIO 0)
- DHT22 (GPIO 15)

---

## Expected Serial Output

### Boot Test Success

```
╔═══════════════════════════════════════════╗
║  ESP32 Sensor Network v4.0 (Phase 2)      ║
╚═══════════════════════════════════════════╝
Chip Model: ESP32
✅ Watchdog configured: 30s timeout, no panic

=== GPIO SAFE-MODE INITIALIZATION ===
Board Type: ESP32-WROOM-32
GPIOManager: Safe-Mode initialization complete

[INFO] Logger system initialized
║   Phase 1: Core Infrastructure READY  ║

[INFO] WiFi connected successfully
[INFO] MQTT connected successfully
║   Phase 2: Communication Layer READY  ║

║   Phase 3: Hardware Abstraction READY  ║
║   Phase 4: Sensor System READY         ║
║   Phase 5: Actuator System READY      ║
[INFO] Initial heartbeat sent for ESP registration
```

---

## Coverage Estimation

| System Flow | Coverage | Reason |
|-------------|----------|--------|
| Boot Sequence | 85% | Provisioning not testable |
| Sensor Reading | 50% | DS18B20 constant value |
| Actuator Command | 70% | LED PWM not measurable |
| Runtime Config | 60% | With MQTT injection |
| MQTT Routing | 65% | Serial verification only |
| Error Recovery | 30% | WiFi drop not simulable |
| Zone Assignment | 70% | With MQTT injection |
| Subzone Management | 60% | With MQTT injection |

**Overall realistic coverage: ~55-60%**

---

## Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| DS18B20 constant 22.5°C | Cannot test temp-based logic | Server tests cover this |
| LED brightness not measurable | PWM values not verifiable | Serial log verification |
| 90s max timeout | Long tests impossible | Split into multiple tests |
| No MQTT broker monitoring | Messages not verifiable | Serial confirmation |
| WiFi drop not simulable | Error recovery limited | Server mock tests |
| No button press in scenarios | Factory reset only via MQTT | Use MQTT alternative |

---

## Troubleshooting

### "WOKWI_CLI_TOKEN not set"
Set the environment variable or GitHub secret.

### "wokwi.toml not found"
Run from the `El Trabajante` directory. Use `.` as first argument:
```bash
wokwi-cli . --timeout 90000 --scenario tests/wokwi/boot_test.yaml
```

### "Invalid scenario step key: timeout"
Remove `timeout:` from YAML, use CLI `--timeout` instead.

### "Timeout waiting for serial"
1. Increase CLI `--timeout` value
2. Check if expected message matches actual output (case-sensitive)
3. Run simulation manually to see actual output

### Build Errors
```bash
cd "El Trabajante"
pio run -e wokwi_simulation -t clean
pio run -e wokwi_simulation
```

---

## Wokwi Configuration Files

| File | Purpose |
|------|---------|
| `wokwi.toml` | Wokwi CLI configuration (firmware path, network gateway) |
| `diagram.json` | Virtual hardware diagram (ESP32 + sensors) |
| `platformio.ini` | Build environment `[env:wokwi_simulation]` |

---

## Related Documentation

- [Wokwi CLI Documentation](https://docs.wokwi.com/wokwi-cli/getting-started)
- [Wokwi ESP32 Simulation](https://docs.wokwi.com/chips/esp32)
- [Server ESP32 Tests](../../El Servador/docs/ESP32_TESTING.md)
- [System Flows](../../docs/system-flows/)

---

**Last Updated:** 2026-01-05
