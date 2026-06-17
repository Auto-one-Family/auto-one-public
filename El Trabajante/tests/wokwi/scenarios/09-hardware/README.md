# Hardware Configuration Tests

> **Erstellt:** 2026-01-28
> **Version:** 1.0
> **Kategorie:** 09-hardware

---

## Übersicht

Diese Test-Suite validiert die Hardware-Konfigurationen für verschiedene ESP32-Boards:
- **ESP32-WROOM-32** (`esp32_dev.h`)
- **XIAO ESP32-C3** (`xiao_esp32c3.h`)

Die Tests stellen sicher, dass board-spezifische Parameter korrekt definiert und angewendet werden.

---

## Test-Dateien

| Datei | Test-IDs | Beschreibung | Priorität |
|-------|----------|--------------|-----------|
| `hw_board_type.yaml` | HW-ID-001, HW-ID-004 | Board-Typ-Identifikation | Mittel |
| `hw_i2c_config.yaml` | HW-I2C-001-006 | I2C-Pin-Konfiguration | Mittel |
| `hw_input_only_reject.yaml` | HW-INPUT-001-002 | Input-Only-Pin-Schutz | Hoch |
| `hw_sensor_limit.yaml` | HW-LIM-003 | Sensor-Limit-Durchsetzung | Hoch |
| `hw_actuator_limit.yaml` | HW-LIM-004 | Actuator-Limit-Durchsetzung | Hoch |
| `hw_pwm_config.yaml` | HW-PWM-001-005 | PWM-Konfiguration | Mittel |
| `hw_safe_pins_verify.yaml` | HW-GPIO-001-002 | Safe-Pin-Liste Validierung | Hoch |
| `hw_reserved_pins.yaml` | HW-RES-001-005 | Reserved-Pin-Schutz | Kritisch |
| `hw_cross_board_constants.yaml` | HW-CROSS-001-003 | Board-übergreifende Konstanten | Mittel |

---

## Hardware-Konfigurationsvergleich

### Safe GPIO Pins

| Board | Pins | Count |
|-------|------|-------|
| ESP32-WROOM-32 | 4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33 | 16 |
| XIAO ESP32-C3 | 2, 4, 5, 6, 7, 8, 9, 10, 21 | 9 |

### Reserved GPIO Pins

| Board | Pins | Beschreibung |
|-------|------|--------------|
| ESP32-WROOM-32 | 0, 1, 2, 3, 12, 13 | Boot, UART, Strapping |
| XIAO ESP32-C3 | 0, 1, 3 | Boot, UART |

### I2C Konfiguration

| Board | SDA | SCL | Frequenz |
|-------|-----|-----|----------|
| ESP32-WROOM-32 | GPIO 21 | GPIO 22 | 100 kHz |
| XIAO ESP32-C3 | GPIO 4 | GPIO 5 | 100 kHz |

### PWM Konfiguration

| Board | Channels | Resolution | Frequenz |
|-------|----------|------------|----------|
| ESP32-WROOM-32 | 16 | 12-bit | 1000 Hz |
| XIAO ESP32-C3 | 6 | 12-bit | 1000 Hz |

### Resource Limits (platformio.ini)

| Board | MAX_SENSORS | MAX_ACTUATORS |
|-------|-------------|---------------|
| ESP32-WROOM-32 | 20 | 12 |
| XIAO ESP32-C3 | 10 | 6 |

---

## Test-Ausführung

### Einzeltest ausführen

```bash
cd "El Trabajante"
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/09-hardware/hw_board_type.yaml
```

### Alle Hardware-Tests

```bash
cd "El Trabajante"
for f in tests/wokwi/scenarios/09-hardware/*.yaml; do
    echo "Running: $f"
    wokwi-cli . --timeout 90000 --scenario "$f" || echo "FAILED: $f"
done
```

---

## Kritische Erkenntnisse

### 1. Input-Only Pins (GPIO 34-39)

**Wichtig:** Auf ESP32-WROOM-32 sind GPIO 34, 35, 36, 39 Input-Only Pins:
- Können nur als Eingänge verwendet werden
- **Sind NICHT in SAFE_GPIO_PINS!**
- Werden daher als "not in safe pins" abgelehnt
- Für Analog-Sensoren: Nur GPIO 32, 33 nutzbar

### 2. Flash-Pins (GPIO 6-11)

- Nicht explizit in `RESERVED_GPIO_PINS`
- Aber auch nicht in `SAFE_GPIO_PINS`
- Werden mit "not in safe pins" abgelehnt
- Nutzung würde ESP32 unbrauchbar machen

### 3. I2C-Pin Auto-Reservation

- I2C-Pins (21/22 auf WROOM, 4/5 auf XIAO) werden automatisch reserviert
- Versuch, diese für Sensoren/Aktoren zu nutzen, schlägt fehl
- Fehlermeldung: "already allocated for I2C"

---

## Referenzen

- `esp32_dev.h`: ESP32-WROOM-32 Hardware-Konfiguration
- `xiao_esp32c3.h`: XIAO ESP32-C3 Hardware-Konfiguration
- `gpio_manager.cpp`: GPIO-Verwaltung und Pin-Validierung
- `platformio.ini`: Build-Flags und Resource-Limits

---

## Test-ID Mapping

| Test-ID | Beschreibung | Status |
|---------|--------------|--------|
| HW-ID-001 | BOARD_TYPE definiert | Implementiert |
| HW-ID-004 | Board in Serial-Output | Implementiert |
| HW-GPIO-001 | SAFE_PIN_COUNT korrekt | Implementiert |
| HW-GPIO-002 | Safe-Pins nutzbar | Implementiert |
| HW-RES-001 | Boot-Pin (GPIO 0) reserviert | Implementiert |
| HW-RES-002 | UART-Pins reserviert | Implementiert |
| HW-RES-003 | Flash-Pins blockiert | Implementiert |
| HW-RES-004 | Sensor auf Reserved ablehnen | Implementiert |
| HW-RES-005 | Actuator auf Reserved ablehnen | Implementiert |
| HW-INPUT-001 | Input-Only als Sensor | Implementiert |
| HW-INPUT-002 | Input-Only als Actuator ablehnen | Implementiert |
| HW-I2C-001 | I2C-SDA definiert | Implementiert |
| HW-I2C-002 | I2C-SCL definiert | Implementiert |
| HW-I2C-004 | I2C-Pins in Safe-List | Implementiert |
| HW-I2C-006 | Board-spezifische I2C-Pins | Implementiert |
| HW-LIM-003 | Sensor-Limit durchgesetzt | Implementiert |
| HW-LIM-004 | Actuator-Limit durchgesetzt | Implementiert |
| HW-PWM-001 | PWM-Channels definiert | Implementiert |
| HW-PWM-003 | PWM-Resolution korrekt | Implementiert |
| HW-CROSS-001 | Gleiche Namespace-Struktur | Implementiert |
| HW-CROSS-003 | Gleiche Interface-Konstanten | Implementiert |

---

*Erstellt gemäß IEC 61508 Best Practices für funktionale Sicherheit.*
