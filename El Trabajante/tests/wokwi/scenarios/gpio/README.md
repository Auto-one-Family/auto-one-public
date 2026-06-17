# GPIO Manager Test Suite

> **Version:** 1.0
> **Erstellt:** 2026-01-28
> **Modul:** GPIO Manager (`drivers/gpio_manager.cpp`)
> **Prioritaet:** KRITISCH - Fundament aller Hardware-Operationen

---

## Uebersicht

Diese Test-Suite validiert den GPIO Manager - das sicherheitskritische Fundament
fuer alle Hardware-Operationen im AutomationOne ESP32-System.

### Testkategorien

| Kategorie | Anzahl | Beschreibung |
|-----------|--------|--------------|
| Boot & Initialisierung | 5 | Safe-Mode Initialization, I2C Auto-Reserve |
| Pin-Reservation | 7 | Konflikt-Erkennung, Validierung, Tracking |
| Safe-Mode-Operationen | 5 | Einzel-Pin, Emergency, Verifikation |
| Subzone-Management | 6 | Zuweisung, Isolation, Safe-Mode pro Subzone |
| Edge Cases | 5 | Grenzwerte, Mehrfach-Init, Fehlerbehandlung |
| Integration | 4 | Sensor/Actuator Manager, Heartbeat |

**Gesamt: 32 Tests**

---

## Hardware-Konfiguration (ESP32 WROOM)

### SAFE_GPIO_PINS (16 Pins - verfuegbar)
```
4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33
```

### RESERVED_GPIO_PINS (6 Pins - NIEMALS verwenden)
```
0  - Boot Button / Strapping Pin
1  - UART0 TX (USB Serial)
2  - Boot Strapping Pin
3  - UART0 RX (USB Serial)
12 - Flash Voltage Strapping Pin
13 - Flash Voltage Strapping Pin
```

### INPUT_ONLY_PINS (4 Pins - kein OUTPUT moeglich)
```
34, 35, 36, 39
```
**WICHTIG:** Diese Pins sind NICHT in SAFE_GPIO_PINS enthalten!

### I2C-Pins (automatisch reserviert)
```
SDA = GPIO 21
SCL = GPIO 22
```

---

## Test-Ausfuehrung

### Wokwi-Tests (Firmware-Simulation)
```bash
cd "El Trabajante"
wokwi-cli . --timeout 60000 --scenario tests/wokwi/scenarios/gpio/gpio_boot_first.yaml
```

### Alle GPIO-Tests ausfuehren
```bash
for scenario in tests/wokwi/scenarios/gpio/*.yaml; do
  echo "Running: $scenario"
  wokwi-cli . --timeout 60000 --scenario "$scenario"
done
```

---

## Akzeptanzkriterien

- [x] Alle 32 Tests implementiert
- [ ] Alle Tests PASS in Wokwi-Simulation
- [ ] Keine GPIO-Konflikte bei parallelen Reservierungen
- [ ] Emergency Safe-Mode < 10ms Reaktionszeit
- [ ] I2C-Pins korrekt auto-reserviert

---

## Dateien in diesem Verzeichnis

| Datei | Kategorie | Tests |
|-------|-----------|-------|
| gpio_boot_first.yaml | Boot | GPIO-BOOT-001 |
| gpio_boot_pin_count.yaml | Boot | GPIO-BOOT-002 |
| gpio_boot_i2c_auto.yaml | Boot | GPIO-BOOT-003 |
| gpio_boot_mode_verify.yaml | Boot | GPIO-BOOT-004, 005 |
| gpio_reservation_success.yaml | Reservation | GPIO-RES-001 |
| gpio_reservation_conflict.yaml | Reservation | GPIO-RES-002 |
| gpio_reservation_invalid.yaml | Reservation | GPIO-RES-003, 007 |
| gpio_reservation_release.yaml | Reservation | GPIO-RES-004, 005 |
| gpio_reservation_owner.yaml | Reservation | GPIO-RES-006 |
| gpio_safe_mode_single.yaml | Safe-Mode | GPIO-SAFE-001, 002 |
| gpio_safe_mode_emergency.yaml | Safe-Mode | GPIO-SAFE-003 |
| gpio_safe_mode_verify.yaml | Safe-Mode | GPIO-SAFE-004, 005 |
| gpio_subzone_assign.yaml | Subzone | GPIO-SUB-001, 002 |
| gpio_subzone_pins.yaml | Subzone | GPIO-SUB-003 |
| gpio_subzone_safe.yaml | Subzone | GPIO-SUB-004, 005 |
| gpio_subzone_conflict.yaml | Subzone | GPIO-SUB-006 |
| gpio_edge_max_pins.yaml | Edge | GPIO-EDGE-001 |
| gpio_edge_strings.yaml | Edge | GPIO-EDGE-002, 003 |
| gpio_edge_multi_init.yaml | Edge | GPIO-EDGE-004 |
| gpio_edge_invalid_pin.yaml | Edge | GPIO-EDGE-005 |
| gpio_integration_sensor.yaml | Integration | GPIO-INT-001 |
| gpio_integration_actuator.yaml | Integration | GPIO-INT-002 |
| gpio_integration_emergency.yaml | Integration | GPIO-INT-003 |
| gpio_integration_heartbeat.yaml | Integration | GPIO-INT-004 |

---

## Referenzen

- Implementierung: `El Trabajante/src/drivers/gpio_manager.cpp`
- Header: `El Trabajante/src/drivers/gpio_manager.h`
- Hardware-Config: `El Trabajante/src/config/hardware/esp32_dev.h`
- Boot-Sequenz: `El Trabajante/docs/system-flows/01-boot-sequence.md`
