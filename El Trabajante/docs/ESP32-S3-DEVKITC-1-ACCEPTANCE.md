# ESP32-S3 DevKitC-1 N8R8 — Akzeptanzprotokoll

**Env:** `esp32-s3-devkitc-1` (Alias: `esp32_s3_dev`)  
**Hardware:** ESP32-S3 QFN56 rev v0.2, 8MB Flash, 8MB Embedded PSRAM, COM8 (303A:1001), MAC e0:72:a1:ae:ae:64  
**Datum:** 2026-05-27 (Build/Flash), 2026-05-28 (AUT-494/495 Runtime)

## Build / Flash (automatisiert)

| Schritt | Befehl | Ergebnis |
|---------|--------|----------|
| Regression classic | `pio run -e esp32_dev` | PASS |
| S3 Build | `pio run -e esp32-s3-devkitc-1` | PASS — Flash 44.9% (1501733 / 3342336 B OTA-Slot) |
| Upload COM8 | `pio run -e esp32-s3-devkitc-1 -t upload --upload-port COM8` | PASS (2026-05-28, AUT-494/495) |
| esptool Chip-Info | `Embedded PSRAM 8MB (AP_3v3)` bei Upload + `esptool.py run` | PASS (Kriterium B — Tooling) |
| Publish-Queue S3 | Serial: `Publish queue created (16 slots)` | PASS (AUT-495) |
| OUTBOX S3 | Serial: `[FIX2-VERIFY] ... OUTBOX=65536(sdkconfig) ...` | PASS (AUT-494) |

## Akzeptanz A–E (Runtime)

| ID | Kriterium | Status | Notiz |
|----|-----------|--------|-------|
| A | Serial-Boot, kein Crash-Loop | **PASS** | ESP32-S3 Boot, Application-Logs, kein Guru/WDT (COM8-Capture 2026-05-28) |
| B | PSRAM im Boot-Log | **PASS** | esptool: 8MB PSRAM; Runtime: `Free heap: ~163 KB` nach Queue-Init |
| C | WiFi connected + IP | **PASS** | `wifi_connected=1`, RSSI -40, MQTT-Subscriptions + Registration ACK (COM8 2026-05-28) |
| D | MQTT connected + Frontend sichtbar | **PASS** | `REGISTRATION CONFIRMED BY SERVER`, MQTT connected; nach Board-Restart erscheint ESP im Frontend normal (User-Bestätigung 2026-05-28) |
| E | Erste Sensor-MQTT-Message | **PASS** | CO2 UART (GPIO 18, AUT-527): Werte im Frontend sichtbar (User 2026-05-29); SHT31/DS18B20 weiterhin offen |

### Manuelle Verifikation (empfohlen)

```powershell
cd "El Trabajante"
pio device monitor -e esp32-s3-devkitc-1 --port COM8 --baud 115200
```

Erwartung: Chip `ESP32-S3`, Banner „ESP32 Sensor Network“, `Board Type: ESP32_S3_DEVKITC1`, WiFi/MQTT-Logs.

Bei Bootloop ohne CDC-Output: UART0 an GPIO43 TX mitschneiden.

## Troubleshooting: leerer Serial Monitor / kein Provisioning-AP

1. **Nur ein Programm darf COM8 offen haben** (PlatformIO Monitor, Arduino IDE, PuTTY — alles schliessen).
2. **Monitor mit S3-Env starten** (setzt `monitor_dtr/rts = 0`):
   ```powershell
   cd "El Trabajante"
   pio device monitor -e esp32-s3-devkitc-1 --port COM8
   ```
3. **RESET-Taste am Board** einmal druecken, wenn der Monitor laeuft.
4. Erwartete erste Zeile: `[BOOT] ESP32-S3 USB-CDC — oeffne Monitor auf COM8, 115200`
5. Danach: `NO CONFIG - STARTING PROVISIONING` und WLAN `AutoOne-ESP_…` / Passwort `provision`.
6. Wenn nur `waiting for download` erscheint: BOOT gedrueckt halten, RESET kurz, BOOT loslassen, erneut flashen.
7. Sauberer Stand: `pio run -e esp32-s3-devkitc-1 -t erase --upload-port COM8` dann `upload`.

Sensor-MQTT:

```bash
mosquitto_sub -h <broker> -t 'kaiser/+/esp/+/sensor/+/data' -v
```

## Konfigurationsreferenz

- PlatformIO: `board_build.arduino.memory_type = qio_opi`, `default_8MB.csv`, `BOARD_HAS_PSRAM`
- GPIO: `src/config/hardware/esp32_s3_devkit.h` — GPIO 26–37 (Octal Flash+PSRAM) reserviert

## AUT-527 — UART CO2 (SEN0220 / MH-Z19, ESP_AEAE64)

| Aspekt | Wert |
|--------|------|
| UART-Instanz | `Serial2` (config-getrieben, nicht hardcoded) |
| Pins (Robin) | RX=GPIO18, TX=GPIO17, 9600 8N1 |
| Logischer Slot | `gpio=18` (Sensor-ID espId:18:co2) — **kein ADC** |
| S3-Pinout | GPIO 17/18 in `SAFE_GPIO_PINS`, kein Konflikt I2C 8/9, USB 19/20, Flash 26–37 |
| Warmup | ~3 min nach `configureSensor` — Messungen bis dahin `quality=warming_up` |
| Driver | `src/drivers/mhz19_uart.cpp` — RAW ppm, `raw_mode: true` |
| Runtime | **PASS** (2026-05-29) — CO2-Werte im Frontend nach Warmup; Config `gpio=18`, `rx=18`, `tx=17` |

### Operator-UI (ein Pin reicht)

| UI-Feld | Wert S3 (ESP_AEAE64) | Bedeutung |
|---------|----------------------|-----------|
| GPIO (Dashboard) | **18** | Logischer Slot **und** `uart_rx_pin` (ESP empfängt ← Sensor TX) |
| `uart_tx_pin` | **17** (automatisch) | Server `config_builder` / MQTT-Fallback — **nicht** im UI einstellbar |

### Löschen / NVS-Geister (AUT-527)

| Problem | Ursache | Lösung |
|---------|---------|--------|
| GPIO 18 „belegt“ nach UI-Löschen | Alter CO₂-Slot in NVS auf GPIO **17** (reserviert 17+18) | CO₂ in UI **löschen** (Tombstone-Push) — Server sendet für `co2` **zwei** `active:false`-Einträge (GPIO 17 **und** 18) |
| Tombstone schlägt fehl (`UART sensor missing uart_rx_pin`) | Firmware validierte Lösch-Payload vor `active:false` | Behoben: `parseAndConfigureSensorWithTracking()` verarbeitet **`active:false` vor** `validateSensorConfig()`; CO₂-Fallback entfernt Slot 17/18 |

**Serial-Erfolg nach Löschen + Neu-Anlegen:**

```text
Configured UART CO2 … rx=18 tx=17
ConfigResponse … success=3 failed=0
```
