# Hardware Foundation: Backend-Referenz für Frontend

> **Ziel:** Dieses Dokument enthält alle Informationen, die ein Frontend-Entwickler braucht, um die Hardware Foundation UI/UX ohne Rückfragen zu implementieren.

> **Version:** 2.0 (2026-01-29) - Review & Ergänzungen nach Code-Verifizierung
>
> **Geprüft gegen:**
> - ESP32: `El Trabajante/src/drivers/gpio_manager.h`, `i2c_bus.h`, `onewire_bus.h`, `pwm_controller.h`
> - Server: `El Servador/god_kaiser_server/src/api/v1/esp.py`, `schemas/esp.py`, `websocket/manager.py`
> - Error-Codes: `El Trabajante/src/models/error_codes.h`

---

## Inhaltsverzeichnis

1. [GPIO Manager](#1-gpio-manager)
2. [I2C Bus](#2-i2c-bus)
3. [OneWire Bus](#3-onewire-bus)
4. [PWM Controller](#4-pwm-controller)
5. [Storage Manager](#5-storage-manager)
6. [Hardware Config (Board-Typen)](#6-hardware-config-board-typen)
7. [Error-Code Referenz](#7-error-code-referenz)
8. [TypeScript Interfaces (Vollständig)](#8-typescript-interfaces-vollständig)
9. [REST API Endpoints (Vollständig)](#9-rest-api-endpoints-vollständig)
10. [WebSocket Events (Vollständig)](#10-websocket-events-vollständig)

---

## 1. GPIO Manager

### 1.1 Übersicht

Der GPIO Manager ist das zentrale Sicherheitssystem für alle GPIO-Operationen auf dem ESP32. Er verhindert Hardware-Schäden durch:
- **Safe-Mode:** Alle Pins initial auf INPUT_PULLUP (hochohmig, sicher)
- **Pin-Reservation:** Exklusive Zuweisung mit Owner-Tracking
- **Konflikt-Erkennung:** Verhindert doppelte Pin-Nutzung
- **Subzone-Unterstützung:** Gruppierung von Pins für Zone-basierte Steuerung

### 1.2 REST API Endpoints

#### GET /api/v1/esp/devices/{esp_id}/gpio-status

**Beschreibung:** Holt den vollständigen GPIO-Belegungsstatus eines ESP32.

**Response 200:**
```json
{
  "esp_id": "ESP_12AB34CD",
  "available": [4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27, 32, 33],
  "reserved": [
    {
      "gpio": 21,
      "owner": "system",
      "component": "I2C_SDA",
      "name": null,
      "id": null,
      "source": "static"
    },
    {
      "gpio": 22,
      "owner": "system",
      "component": "I2C_SCL",
      "name": null,
      "id": null,
      "source": "static"
    },
    {
      "gpio": 4,
      "owner": "sensor",
      "component": "DS18B20",
      "name": "Temperature Sensor 1",
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "source": "database"
    }
  ],
  "system": [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],
  "reserved_gpios": [4],
  "i2c_bus": {
    "sda_pin": 21,
    "scl_pin": 22,
    "is_available": true,
    "devices": [
      {
        "i2c_address": "0x44",
        "sensor_type": "SHT31",
        "sensor_name": "Humidity Sensor"
      }
    ]
  },
  "onewire_buses": [
    {
      "gpio": 4,
      "is_available": true,
      "devices": [
        {
          "onewire_address": "28FF123456789012",
          "sensor_type": "DS18B20",
          "sensor_name": "Temp 1"
        }
      ]
    }
  ],
  "hardware_type": "ESP32_WROOM",
  "last_esp_report": "2026-01-29T12:00:00Z"
}
```

**Response 404:**
```json
{
  "detail": "ESP device 'ESP_INVALID' not found"
}
```

### 1.3 WebSocket Events

#### Event: `esp_health`

**Wann:** Bei jedem Heartbeat (alle 60 Sekunden) oder Status-Änderung.

**Payload:**
```json
{
  "type": "esp_health",
  "timestamp": 1735818000,
  "data": {
    "esp_id": "ESP_12AB34CD",
    "status": "online",
    "message": "ESP_12AB34CD online (45KB frei, RSSI: -55dBm) | Uptime: 2h 30m",
    "heap_free": 46080,
    "wifi_rssi": -55,
    "uptime": 9000,
    "sensor_count": 3,
    "actuator_count": 2,
    "gpio_status": [
      {
        "gpio": 4,
        "owner": "sensor",
        "component": "DS18B20",
        "mode": 0,
        "safe": false
      },
      {
        "gpio": 21,
        "owner": "system",
        "component": "I2C_SDA",
        "mode": 0,
        "safe": false
      }
    ],
    "gpio_reserved_count": 2
  }
}
```

### 1.4 GPIO Status Item Schema

```typescript
interface GpioStatusItem {
  gpio: number;           // GPIO-Pin-Nummer (0-39 für ESP32-WROOM, 0-21 für XIAO)
  owner: "sensor" | "actuator" | "system";  // Wer den Pin reserviert hat
  component: string;      // Komponenten-Name (max 32 chars)
  mode: 0 | 1 | 2;       // Normalisierte Werte: 0=INPUT, 1=OUTPUT, 2=INPUT_PULLUP
  safe: boolean;         // true = Safe-Mode (INPUT_PULLUP, nicht aktiv genutzt)
}
```

**KRITISCH - Mode-Normalisierung (Code-Referenz: `schemas/esp.py:310-368`):**

Der Server normalisiert Arduino-Werte zu Protokoll-Werten automatisch:

| ESP32 sendet (Arduino) | Server normalisiert (Protokoll) | Bedeutung |
|------------------------|--------------------------------|-----------|
| `1` (0x01) | `0` | INPUT |
| `2` (0x02) | `1` | OUTPUT |
| `5` (0x05) | `2` | INPUT_PULLUP |

**Frontend erhält IMMER die normalisierten Werte (0, 1, 2)!**

```typescript
// Mapping für UI-Darstellung
const GPIO_MODE_LABELS: Record<number, string> = {
  0: "Input",
  1: "Output",
  2: "Input (Pull-Up)"
};
```

**Safe-Mode Bedeutung:**
- `safe: true` → Pin ist im sicheren Zustand (INPUT_PULLUP), nicht aktiv genutzt
- `safe: false` → Pin ist aktiv konfiguriert und in Verwendung

### 1.5 Error-Codes (GPIO)

| Code | Name | Beschreibung | UI-Darstellung |
|------|------|--------------|----------------|
| 1001 | GPIO_RESERVED | Pin ist System-reserviert | "GPIO {pin} ist für System reserviert" |
| 1002 | GPIO_CONFLICT | Pin bereits in Verwendung | "GPIO {pin} wird bereits von {owner}/{component} verwendet" |
| 1003 | GPIO_INIT_FAILED | Initialisierung fehlgeschlagen | "GPIO {pin} Initialisierung fehlgeschlagen" |
| 1004 | GPIO_INVALID_MODE | Ungültiger Pin-Modus | "Ungültiger Modus für GPIO {pin}" |
| 1005 | GPIO_READ_FAILED | Lesen fehlgeschlagen | "Fehler beim Lesen von GPIO {pin}" |
| 1006 | GPIO_WRITE_FAILED | Schreiben fehlgeschlagen | "Fehler beim Schreiben auf GPIO {pin}" |

### 1.6 UI-Anforderungen

1. **GPIO-Übersicht-Panel:**
   - Zeige alle GPIOs als Grid/Liste
   - Farbcodierung:
     - Grün = Verfügbar
     - Gelb = System-reserviert (nicht nutzbar)
     - Rot = In Verwendung (mit Tooltip wer)
   - Klick auf reservierten Pin zeigt Details (Owner, Component, Name)

2. **Pin-Reservation bei Sensor/Aktor hinzufügen:**
   - Dropdown zeigt nur `available` GPIOs
   - Warnung wenn GPIO bereits belegt
   - Info-Badge für I2C/OneWire-Bus-Pins ("Shared Bus")

3. **Safe-Mode-Anzeige:**
   - Icon wenn `safe: true` (z.B. Schild-Symbol)
   - Tooltip: "Pin im sicheren Zustand (INPUT_PULLUP)"

---

## 2. I2C Bus

### 2.1 Übersicht

Der I2C Bus Manager verwaltet die I2C-Kommunikation mit Sensoren wie SHT31, BMP280, etc.

**Eigenschaften:**
- **Shared Bus:** Alle I2C-Sensoren teilen sich einen Bus (keine GPIO-Exklusivität)
- **Adressierung:** Jedes Gerät hat eine eindeutige I2C-Adresse (0x08-0x77)
- **Frequenz:** 100kHz Standard-Mode
- **Recovery:** Automatische Bus-Wiederherstellung bei Stuck-Zustand (max 3 Versuche/Minute)

**WICHTIG - Board-spezifische I2C-Pins:**

| Board | SDA | SCL | Code-Referenz |
|-------|-----|-----|---------------|
| ESP32-WROOM | GPIO 21 | GPIO 22 | `esp32_dev.h:68-69` |
| XIAO ESP32-C3 | GPIO 4 | GPIO 5 | `xiao_esp32c3.h:54-55` |

**Frontend muss Board-Typ prüfen um korrekte I2C-Pins anzuzeigen!**

### 2.2 REST API

I2C-Status ist Teil von `GET /api/v1/esp/devices/{esp_id}/gpio-status`:

```json
{
  "i2c_bus": {
    "sda_pin": 21,
    "scl_pin": 22,
    "is_available": true,
    "devices": [
      {
        "i2c_address": "0x44",
        "sensor_type": "SHT31",
        "sensor_name": "Humidity Sensor"
      },
      {
        "i2c_address": "0x76",
        "sensor_type": "BMP280",
        "sensor_name": "Pressure Sensor"
      }
    ]
  }
}
```

### 2.3 Error-Codes (I2C)

| Code | Name | Beschreibung | UI-Darstellung |
|------|------|--------------|----------------|
| 1010 | I2C_INIT_FAILED | Bus-Initialisierung fehlgeschlagen | "I2C Bus konnte nicht initialisiert werden" |
| 1011 | I2C_DEVICE_NOT_FOUND | Gerät nicht gefunden | "I2C Gerät 0x{address} nicht gefunden" |
| 1012 | I2C_READ_FAILED | Lesen fehlgeschlagen | "I2C Lesefehler bei 0x{address}" |
| 1013 | I2C_WRITE_FAILED | Schreiben fehlgeschlagen | "I2C Schreibfehler bei 0x{address}" |
| 1014 | I2C_BUS_ERROR | Bus-Fehler | "I2C Bus-Fehler (SDA/SCL blockiert)" |
| 1015 | I2C_BUS_STUCK | Bus hängt | "I2C Bus blockiert (Recovery gestartet)" |
| 1016 | I2C_BUS_RECOVERY_STARTED | Recovery gestartet | "I2C Bus-Wiederherstellung..." |
| 1017 | I2C_BUS_RECOVERY_FAILED | Recovery fehlgeschlagen | "I2C Bus-Wiederherstellung fehlgeschlagen" |
| 1018 | I2C_BUS_RECOVERED | Recovery erfolgreich | "I2C Bus wiederhergestellt" |

### 2.4 UI-Anforderungen

1. **I2C-Bus-Status-Panel:**
   - Zeige `initialized: true/false` als Badge
   - Liste aller verbundenen Geräte mit Adresse
   - Status pro Gerät (responsive/nicht responsive)

2. **I2C-Sensor hinzufügen:**
   - Dropdown mit bekannten I2C-Adressen
   - Validierung: Adresse bereits belegt?
   - Info: "Teilt GPIO 21/22 mit anderen I2C-Sensoren"

3. **Recovery-Anzeige:**
   - Bei Code 1015-1018: Toast-Notification
   - Spinner während Recovery
   - Erfolgs-/Fehlermeldung nach Recovery

---

## 3. OneWire Bus

### 3.1 Übersicht

Der OneWire Bus Manager verwaltet DS18B20 Temperatursensoren.

**Eigenschaften:**
- **Shared Bus:** Ein GPIO-Pin für mehrere DS18B20-Sensoren (keine GPIO-Exklusivität)
- **Adressierung:** 64-bit ROM-Code (16 Hex-Zeichen, z.B. `28FF123456789012`)
- **Temperatur:** Rohdaten werden an Server gesendet (Pi-Enhanced Mode)
- **ROM-Validierung:** CRC8-Prüfung auf Server-Seite

**WICHTIG - Board-spezifische OneWire Default-Pins:**

| Board | Default Pin | Code-Referenz |
|-------|-------------|---------------|
| ESP32-WROOM | GPIO 4 | `esp32_dev.h:77` |
| XIAO ESP32-C3 | GPIO 6 | `xiao_esp32c3.h:63` |

**ROM-Code-Format:** `28` (Family Code DS18B20) + `FF123456789012` (Serial + CRC)

**Frontend muss Board-Typ prüfen um korrekten Default-Pin vorzuschlagen!**

### 3.2 REST API

OneWire-Status ist Teil von `GET /api/v1/esp/devices/{esp_id}/gpio-status`:

```json
{
  "onewire_buses": [
    {
      "gpio": 4,
      "is_available": true,
      "devices": [
        {
          "onewire_address": "28FF123456789012",
          "sensor_type": "DS18B20",
          "sensor_name": "Temperature Main"
        },
        {
          "onewire_address": "28FFAABBCCDD0001",
          "sensor_type": "DS18B20",
          "sensor_name": "Temperature Secondary"
        }
      ]
    }
  ]
}
```

### 3.3 Error-Codes (OneWire)

| Code | Name | Beschreibung | UI-Darstellung |
|------|------|--------------|----------------|
| 1020 | ONEWIRE_INIT_FAILED | Bus-Initialisierung fehlgeschlagen | "OneWire Bus konnte nicht initialisiert werden" |
| 1021 | ONEWIRE_NO_DEVICES | Keine Geräte gefunden | "Keine OneWire-Geräte gefunden" |
| 1022 | ONEWIRE_READ_FAILED | Lesen fehlgeschlagen | "OneWire Lesefehler" |
| 1023 | ONEWIRE_INVALID_ROM_LENGTH | ROM-Code falsche Länge | "ROM-Code muss 16 Zeichen haben" |
| 1024 | ONEWIRE_INVALID_ROM_FORMAT | ROM-Code ungültiges Format | "ROM-Code darf nur 0-9, A-F enthalten" |
| 1025 | ONEWIRE_INVALID_ROM_CRC | ROM-Code CRC-Fehler | "ROM-Code CRC ungültig" |
| 1026 | ONEWIRE_DEVICE_NOT_FOUND | Gerät nicht gefunden | "OneWire Gerät nicht angeschlossen" |
| 1027 | ONEWIRE_BUS_NOT_INITIALIZED | Bus nicht initialisiert | "OneWire Bus nicht initialisiert" |
| 1028 | ONEWIRE_READ_TIMEOUT | Lese-Timeout | "OneWire Gerät antwortet nicht" |
| 1029 | ONEWIRE_DUPLICATE_ROM | ROM-Code bereits registriert | "ROM-Code bereits einem anderen Sensor zugewiesen" |

### 3.4 DS18B20-spezifische Temperatur-Fehler

| Code | Name | Wert | Beschreibung | UI-Darstellung |
|------|------|------|--------------|----------------|
| 1060 | DS18B20_SENSOR_FAULT | -127.0°C | Sensor nicht verbunden | "Sensor getrennt oder defekt" |
| 1061 | DS18B20_POWER_ON_RESET | 85.0°C | Kein Messwert | "Sensor im Reset-Zustand" |
| 1062 | DS18B20_OUT_OF_RANGE | <-55 oder >125 | Außerhalb Messbereich | "Messwert außerhalb gültigem Bereich" |
| 1063 | DS18B20_DISCONNECTED_RUNTIME | - | Zur Laufzeit getrennt | "Sensor war verbunden, jetzt getrennt" |

### 3.5 UI-Anforderungen

1. **OneWire-Bus-Panel:**
   - Zeige Bus-GPIO und Status
   - Liste aller Geräte mit ROM-Code und Name
   - Discovery-Button für neuen Scan

2. **DS18B20-Sensor hinzufügen:**
   - ROM-Code Eingabefeld (16 Hex-Zeichen)
   - Format-Validierung in Echtzeit
   - Prüfung auf Duplikate

3. **Temperatur-Fehler-Anzeige:**
   - Bei -127°C: Rotes "Sensor getrennt" Badge
   - Bei 85°C beim Start: Gelbes "Warte auf Messung" Badge
   - Tooltip mit Fehlerbeschreibung

---

## 4. PWM Controller

### 4.1 Übersicht

Der PWM Controller steuert Aktoren wie Pumpen, Lüfter, LEDs mit variabler Leistung.

**Board-spezifische Channels:**

| Board | PWM Channels | Code-Referenz |
|-------|--------------|---------------|
| ESP32-WROOM | 16 | `esp32_dev.h:84` |
| XIAO ESP32-C3 | 6 | `xiao_esp32c3.h:70` |

**PWM-Spezifikationen:**
- **Frequenz:** 1000 Hz (Default, konfigurierbar)
- **Auflösung:** 12-bit (0-4095)
- **Duty Cycle API:** 0.0% - 100.0%

**KRITISCH - Wert-Konvertierung:**
```
Frontend (%)  →  Server (0.0-1.0)  →  ESP32 (0-4095)
   75%        →       0.75         →     3072
  100%        →       1.0          →     4095
```

**Frontend sendet Prozent, Server konvertiert zu 0.0-1.0, ESP32 konvertiert zu 0-4095!**

### 4.2 REST API

PWM-Steuerung erfolgt über Aktor-Endpoints:

#### POST /api/v1/actuators/{esp_id}/{gpio}/command

**Request:**
```json
{
  "command": "SET_VALUE",
  "value": 75.0,
  "duration_ms": 0
}
```

**Response:**
```json
{
  "success": true,
  "message": "Actuator command sent",
  "esp_id": "ESP_12AB34CD",
  "gpio": 25,
  "command": "SET_VALUE",
  "command_sent": true
}
```

### 4.3 Error-Codes (PWM)

| Code | Name | Beschreibung | UI-Darstellung |
|------|------|--------------|----------------|
| 1030 | PWM_INIT_FAILED | Controller nicht initialisiert | "PWM Controller Initialisierung fehlgeschlagen" |
| 1031 | PWM_CHANNEL_FULL | Alle Channels belegt | "Alle PWM-Kanäle in Verwendung" |
| 1032 | PWM_SET_FAILED | Wert setzen fehlgeschlagen | "PWM-Wert konnte nicht gesetzt werden" |

### 4.4 UI-Anforderungen

1. **PWM-Aktor-Card:**
   - Slider für Duty Cycle (0-100%)
   - Anzeige aktuelle Wert
   - An/Aus Toggle (0% / 100%)

2. **Channel-Übersicht:**
   - Zeige verfügbare/belegte Channels
   - Warnung bei Channel-Limit

---

## 5. Storage Manager

### 5.1 Übersicht

Der Storage Manager verwaltet persistenten Speicher (NVS) auf dem ESP32.

**Eigenschaften:**
- **NVS:** Non-Volatile Storage (Flash-basiert)
- **Namespaces:** Isolierte Speicherbereiche (wifi_config, zone_config, etc.)
- **Thread-Safety:** Mutex-geschützt für Multi-Task-Zugriff
- **Quota:** Begrenzte Einträge, Warnung bei fast voll

### 5.2 REST API

Storage-Status ist indirekt über ESP-Health verfügbar. Keine direkte API.

**Heartbeat-Payload enthält:**
```json
{
  "heap_free": 45000
}
```

### 5.3 Error-Codes (Storage/NVS)

| Code | Name | Beschreibung | UI-Darstellung |
|------|------|--------------|----------------|
| 2001 | NVS_INIT_FAILED | NVS nicht initialisiert | "Speicher konnte nicht initialisiert werden" |
| 2002 | NVS_READ_FAILED | Lesen fehlgeschlagen | "Speicher-Lesefehler" |
| 2003 | NVS_WRITE_FAILED | Schreiben fehlgeschlagen | "Speicher voll oder defekt" |
| 2004 | NVS_NAMESPACE_FAILED | Namespace-Fehler | "Speicher-Bereich nicht zugänglich" |
| 2005 | NVS_CLEAR_FAILED | Löschen fehlgeschlagen | "Speicher konnte nicht gelöscht werden" |

### 5.4 UI-Anforderungen

1. **Speicher-Warnung:**
   - Bei `heap_free < 10000`: Gelbe Warnung
   - Bei `heap_free < 5000`: Rote Warnung
   - Tooltip: "Wenig freier Speicher"

2. **Factory Reset:**
   - Bestätigungs-Dialog
   - Warnung: "Alle Einstellungen werden gelöscht"

---

## 6. Hardware Config (Board-Typen)

### 6.1 ESP32-WROOM-32

```typescript
const ESP32_WROOM_CONFIG = {
  boardType: "ESP32_WROOM_32",

  // Sichere GPIOs (frei nutzbar) - Code-Referenz: esp32_dev.h:46-49
  safeGpios: [4, 5, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33],

  // ESP32-seitig reserviert (Boot/UART/Strapping) - Code-Referenz: esp32_dev.h:31-39
  reservedGpiosEsp32: [0, 1, 2, 3, 12, 13],

  // Server-seitig reserviert (inkl. Flash-Pins) - Code-Referenz: gpio_validation_service.py:71-82
  // WICHTIG: Server prüft gegen diese erweiterte Liste!
  systemReservedPins: [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],

  // Nur Input (kein OUTPUT möglich) - Code-Referenz: esp32_dev.h:57-60
  inputOnlyGpios: [34, 35, 36, 39],

  // I2C Defaults - Code-Referenz: esp32_dev.h:68-70
  i2c: {
    sdaPin: 21,
    sclPin: 22,
    frequency: 100000
  },

  // OneWire Default - Code-Referenz: esp32_dev.h:77
  defaultOneWirePin: 4,

  // PWM - Code-Referenz: esp32_dev.h:84-86
  pwmChannels: 16,
  pwmFrequency: 1000,
  pwmResolution: 12,   // 0-4095

  // Limits
  maxSensors: 20,
  maxActuators: 12,

  // GPIO-Bereich - Code-Referenz: gpio_validation_service.py:167
  gpioMax: 39
};
```

### 6.2 XIAO ESP32-C3

```typescript
const XIAO_ESP32C3_CONFIG = {
  boardType: "XIAO_ESP32C3",

  // Sichere GPIOs (frei nutzbar) - Code-Referenz: xiao_esp32c3.h:43-46
  safeGpios: [2, 4, 5, 6, 7, 8, 9, 10, 21],

  // System-reserviert (NICHT nutzen!) - Code-Referenz: xiao_esp32c3.h:31-36
  reservedGpios: [0, 1, 3],  // Boot Button, UART TX/RX

  // Nur Input - XIAO hat KEINE Input-Only Pins
  inputOnlyGpios: [],

  // I2C Defaults - ACHTUNG: UNTERSCHIEDLICH von ESP32-WROOM!
  // Code-Referenz: xiao_esp32c3.h:54-56
  i2c: {
    sdaPin: 4,   // NICHT 21 wie bei WROOM!
    sclPin: 5,   // NICHT 22 wie bei WROOM!
    frequency: 100000
  },

  // OneWire Default - UNTERSCHIEDLICH von ESP32-WROOM!
  // Code-Referenz: xiao_esp32c3.h:63
  defaultOneWirePin: 6,  // NICHT 4 wie bei WROOM!

  // PWM - Code-Referenz: xiao_esp32c3.h:70-72
  pwmChannels: 6,      // WROOM hat 16!
  pwmFrequency: 1000,
  pwmResolution: 12,   // 0-4095

  // Limits
  maxSensors: 10,
  maxActuators: 6,

  // GPIO-Bereich - Code-Referenz: gpio_validation_service.py:174
  gpioMax: 21
};
```

**WICHTIG für Frontend-Entwickler:**
- Bei XIAO I2C-Sensor hinzufügen → GPIO 4/5 als Bus-Pins anzeigen
- Bei XIAO OneWire → GPIO 6 als Default vorschlagen
- GPIO-Validierung muss Board-spezifisch sein!
```

### 6.3 Validierungsregeln

| Validierung | Beschreibung | Fehlercode |
|-------------|--------------|------------|
| GPIO in reservedGpios | System-Pin, nicht nutzbar | 1001 |
| GPIO bereits in use | Konflikt mit anderem Sensor/Aktor | 1002 |
| GPIO in inputOnlyGpios + OUTPUT | Kann nicht als Output verwendet werden | 1004 |
| PWM-Channel voll | Alle Channels belegt | 1031 |
| I2C-Adresse belegt | Adresse bereits in Verwendung | 1011 |
| OneWire ROM bereits registriert | Duplikat | 1029 |

---

## 7. Error-Code Referenz

### 7.1 Error-Code-Bereiche

| Bereich | Range | Beschreibung |
|---------|-------|--------------|
| HARDWARE | 1000-1999 | GPIO, I2C, OneWire, PWM, Sensor, Actuator |
| SERVICE | 2000-2999 | NVS, Config, Logger, Storage, Subzone |
| COMMUNICATION | 3000-3999 | WiFi, MQTT, HTTP, Network |
| APPLICATION | 4000-4999 | State, Operation, Command, Watchdog |

### 7.2 Vollständige Error-Code-Tabelle

```typescript
const ERROR_CODES = {
  // GPIO (1001-1006)
  ERROR_GPIO_RESERVED: 1001,
  ERROR_GPIO_CONFLICT: 1002,
  ERROR_GPIO_INIT_FAILED: 1003,
  ERROR_GPIO_INVALID_MODE: 1004,
  ERROR_GPIO_READ_FAILED: 1005,
  ERROR_GPIO_WRITE_FAILED: 1006,

  // I2C (1010-1018)
  ERROR_I2C_INIT_FAILED: 1010,
  ERROR_I2C_DEVICE_NOT_FOUND: 1011,
  ERROR_I2C_READ_FAILED: 1012,
  ERROR_I2C_WRITE_FAILED: 1013,
  ERROR_I2C_BUS_ERROR: 1014,
  ERROR_I2C_BUS_STUCK: 1015,
  ERROR_I2C_BUS_RECOVERY_STARTED: 1016,
  ERROR_I2C_BUS_RECOVERY_FAILED: 1017,
  ERROR_I2C_BUS_RECOVERED: 1018,

  // OneWire (1020-1029)
  ERROR_ONEWIRE_INIT_FAILED: 1020,
  ERROR_ONEWIRE_NO_DEVICES: 1021,
  ERROR_ONEWIRE_READ_FAILED: 1022,
  ERROR_ONEWIRE_INVALID_ROM_LENGTH: 1023,
  ERROR_ONEWIRE_INVALID_ROM_FORMAT: 1024,
  ERROR_ONEWIRE_INVALID_ROM_CRC: 1025,
  ERROR_ONEWIRE_DEVICE_NOT_FOUND: 1026,
  ERROR_ONEWIRE_BUS_NOT_INITIALIZED: 1027,
  ERROR_ONEWIRE_READ_TIMEOUT: 1028,
  ERROR_ONEWIRE_DUPLICATE_ROM: 1029,

  // PWM (1030-1032)
  ERROR_PWM_INIT_FAILED: 1030,
  ERROR_PWM_CHANNEL_FULL: 1031,
  ERROR_PWM_SET_FAILED: 1032,

  // Sensor (1040-1043)
  ERROR_SENSOR_READ_FAILED: 1040,
  ERROR_SENSOR_INIT_FAILED: 1041,
  ERROR_SENSOR_NOT_FOUND: 1042,
  ERROR_SENSOR_TIMEOUT: 1043,

  // Actuator (1050-1053)
  ERROR_ACTUATOR_SET_FAILED: 1050,
  ERROR_ACTUATOR_INIT_FAILED: 1051,
  ERROR_ACTUATOR_NOT_FOUND: 1052,
  ERROR_ACTUATOR_CONFLICT: 1053,

  // DS18B20 Temperature (1060-1063)
  ERROR_DS18B20_SENSOR_FAULT: 1060,
  ERROR_DS18B20_POWER_ON_RESET: 1061,
  ERROR_DS18B20_OUT_OF_RANGE: 1062,
  ERROR_DS18B20_DISCONNECTED_RUNTIME: 1063,

  // NVS/Storage (2001-2005)
  ERROR_NVS_INIT_FAILED: 2001,
  ERROR_NVS_READ_FAILED: 2002,
  ERROR_NVS_WRITE_FAILED: 2003,
  ERROR_NVS_NAMESPACE_FAILED: 2004,
  ERROR_NVS_CLEAR_FAILED: 2005,

  // Config (2010-2014)
  ERROR_CONFIG_INVALID: 2010,
  ERROR_CONFIG_MISSING: 2011,
  ERROR_CONFIG_LOAD_FAILED: 2012,
  ERROR_CONFIG_SAVE_FAILED: 2013,
  ERROR_CONFIG_VALIDATION: 2014,

  // Subzone (2500-2506)
  ERROR_SUBZONE_INVALID_ID: 2500,
  ERROR_SUBZONE_GPIO_CONFLICT: 2501,
  ERROR_SUBZONE_PARENT_MISMATCH: 2502,
  ERROR_SUBZONE_NOT_FOUND: 2503,
  ERROR_SUBZONE_GPIO_INVALID: 2504,
  ERROR_SUBZONE_SAFE_MODE_FAILED: 2505,
  ERROR_SUBZONE_CONFIG_SAVE_FAILED: 2506,

  // WiFi (3001-3005)
  ERROR_WIFI_INIT_FAILED: 3001,
  ERROR_WIFI_CONNECT_TIMEOUT: 3002,
  ERROR_WIFI_CONNECT_FAILED: 3003,
  ERROR_WIFI_DISCONNECT: 3004,
  ERROR_WIFI_NO_SSID: 3005,

  // MQTT (3010-3016)
  ERROR_MQTT_INIT_FAILED: 3010,
  ERROR_MQTT_CONNECT_FAILED: 3011,
  ERROR_MQTT_PUBLISH_FAILED: 3012,
  ERROR_MQTT_SUBSCRIBE_FAILED: 3013,
  ERROR_MQTT_DISCONNECT: 3014,
  ERROR_MQTT_BUFFER_FULL: 3015,
  ERROR_MQTT_PAYLOAD_INVALID: 3016,

  // HTTP (3020-3023) - NEU
  ERROR_HTTP_INIT_FAILED: 3020,
  ERROR_HTTP_REQUEST_FAILED: 3021,
  ERROR_HTTP_RESPONSE_INVALID: 3022,
  ERROR_HTTP_TIMEOUT: 3023,

  // Network (3030-3032) - NEU
  ERROR_NETWORK_UNREACHABLE: 3030,
  ERROR_DNS_FAILED: 3031,
  ERROR_CONNECTION_LOST: 3032,

  // Logger (2020-2021) - NEU
  ERROR_LOGGER_INIT_FAILED: 2020,
  ERROR_LOGGER_BUFFER_FULL: 2021,

  // Storage (2030-2032) - NEU
  ERROR_STORAGE_INIT_FAILED: 2030,
  ERROR_STORAGE_READ_FAILED: 2031,
  ERROR_STORAGE_WRITE_FAILED: 2032,

  // Application/State (4001-4003) - NEU
  ERROR_STATE_INVALID: 4001,
  ERROR_STATE_TRANSITION: 4002,
  ERROR_STATE_MACHINE_STUCK: 4003,

  // Application/Operation (4010-4012) - NEU
  ERROR_OPERATION_TIMEOUT: 4010,
  ERROR_OPERATION_FAILED: 4011,
  ERROR_OPERATION_CANCELLED: 4012,

  // Application/Command (4020-4022) - NEU
  ERROR_COMMAND_INVALID: 4020,
  ERROR_COMMAND_PARSE_FAILED: 4021,
  ERROR_COMMAND_EXEC_FAILED: 4022,

  // Application/Payload (4030-4032) - NEU
  ERROR_PAYLOAD_INVALID: 4030,
  ERROR_PAYLOAD_TOO_LARGE: 4031,
  ERROR_PAYLOAD_PARSE_FAILED: 4032,

  // Watchdog (4070-4072) - NEU
  ERROR_WATCHDOG_TIMEOUT: 4070,
  ERROR_WATCHDOG_FEED_BLOCKED: 4071,
  ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL: 4072,

  // Device Approval (4200-4202) - NEU
  ERROR_DEVICE_REJECTED: 4200,
  ERROR_APPROVAL_TIMEOUT: 4201,
  ERROR_APPROVAL_REVOKED: 4202
} as const;
```

### 7.3 Error-Beschreibungs-Mapping

```typescript
function getErrorDescription(code: number): string {
  const descriptions: Record<number, string> = {
    1001: "GPIO-Pin ist für System reserviert",
    1002: "GPIO-Pin bereits von anderer Komponente verwendet",
    1003: "GPIO-Pin Initialisierung fehlgeschlagen",
    1004: "Ungültiger GPIO-Pin-Modus",
    1005: "GPIO-Pin Lesefehler",
    1006: "GPIO-Pin Schreibfehler",

    1010: "I2C-Bus Initialisierung fehlgeschlagen",
    1011: "I2C-Gerät nicht gefunden",
    1012: "I2C-Lesefehler",
    1013: "I2C-Schreibfehler",
    1014: "I2C-Bus-Fehler (SDA/SCL blockiert)",
    1015: "I2C-Bus hängt (Slave hält Leitung)",
    1016: "I2C-Bus Recovery gestartet",
    1017: "I2C-Bus Recovery fehlgeschlagen",
    1018: "I2C-Bus erfolgreich wiederhergestellt",

    1020: "OneWire-Bus Initialisierung fehlgeschlagen",
    1021: "Keine OneWire-Geräte gefunden",
    1022: "OneWire Lesefehler",
    1023: "ROM-Code muss 16 Hex-Zeichen haben",
    1024: "ROM-Code enthält ungültige Zeichen",
    1025: "ROM-Code CRC ungültig",
    1026: "OneWire-Gerät nicht angeschlossen",
    1027: "OneWire-Bus nicht initialisiert",
    1028: "OneWire Gerät antwortet nicht",
    1029: "ROM-Code bereits registriert",

    1030: "PWM-Controller nicht initialisiert",
    1031: "Alle PWM-Kanäle belegt",
    1032: "PWM-Wert setzen fehlgeschlagen",

    // Sensor (1040-1043)
    1040: "Sensor Lesefehler",
    1041: "Sensor Initialisierung fehlgeschlagen",
    1042: "Sensor nicht gefunden",
    1043: "Sensor Timeout",

    // Actuator (1050-1053)
    1050: "Aktor setzen fehlgeschlagen",
    1051: "Aktor Initialisierung fehlgeschlagen",
    1052: "Aktor nicht gefunden",
    1053: "Aktor GPIO-Konflikt",

    // DS18B20 (1060-1063)
    1060: "DS18B20: Sensor getrennt oder defekt (-127°C)",
    1061: "DS18B20: Power-On-Reset (85°C)",
    1062: "DS18B20: Temperatur außerhalb Messbereich",
    1063: "DS18B20: Sensor zur Laufzeit getrennt",

    // Logger (2020-2021)
    2020: "Logger Initialisierung fehlgeschlagen",
    2021: "Logger Buffer voll",

    // Storage (2030-2032)
    2030: "Storage Initialisierung fehlgeschlagen",
    2031: "Storage Lesefehler",
    2032: "Storage Schreibfehler",

    // HTTP (3020-3023)
    3020: "HTTP Client Initialisierung fehlgeschlagen",
    3021: "HTTP Anfrage fehlgeschlagen",
    3022: "HTTP Antwort ungültig",
    3023: "HTTP Timeout",

    // Network (3030-3032)
    3030: "Netzwerk nicht erreichbar",
    3031: "DNS Auflösung fehlgeschlagen",
    3032: "Verbindung verloren",

    // State (4001-4003)
    4001: "Ungültiger Systemzustand",
    4002: "Ungültige Zustandsänderung",
    4003: "Zustandsmaschine blockiert",

    // Operation (4010-4012)
    4010: "Operation Timeout",
    4011: "Operation fehlgeschlagen",
    4012: "Operation abgebrochen",

    // Command (4020-4022)
    4020: "Ungültiger Befehl",
    4021: "Befehl konnte nicht geparst werden",
    4022: "Befehlsausführung fehlgeschlagen",

    // Payload (4030-4032)
    4030: "Ungültiger Payload",
    4031: "Payload zu groß",
    4032: "Payload konnte nicht geparst werden",

    // Watchdog (4070-4072)
    4070: "Watchdog Timeout erkannt",
    4071: "Watchdog Feed blockiert (Circuit Breakers offen)",
    4072: "Watchdog Feed blockiert (kritische Fehler aktiv)",

    // Device Approval (4200-4202)
    4200: "Gerät wurde abgelehnt",
    4201: "Timeout bei Genehmigungsanfrage",
    4202: "Genehmigung wurde widerrufen"
  };

  return descriptions[code] || `Unbekannter Fehler (Code: ${code})`;
}
```

---

## 8. TypeScript Interfaces (Vollständig)

### 8.1 ESP Device Interfaces

```typescript
// ESP Device Response
interface ESPDeviceResponse {
  id: string;                           // UUID
  device_id: string;                    // ESP_XXXXXXXX
  name: string | null;
  zone_id: string | null;
  zone_name: string | null;
  is_zone_master: boolean;
  ip_address: string | null;
  mac_address: string | null;
  firmware_version: string | null;
  hardware_type: "ESP32_WROOM" | "XIAO_ESP32_C3" | "MOCK_ESP32";
  capabilities: Record<string, any> | null;
  status: "online" | "offline" | "error" | "unknown" | "pending_approval" | "approved" | "rejected";
  last_seen: string | null;             // ISO 8601
  metadata: Record<string, any> | null;
  sensor_count: number;
  actuator_count: number;
  auto_heartbeat: boolean | null;       // Nur Mock ESPs
  heartbeat_interval_seconds: number | null; // Nur Mock ESPs
  created_at: string;
  updated_at: string;
}

// ESP Device List Response
interface ESPDeviceListResponse {
  success: boolean;
  data: ESPDeviceResponse[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}
```

### 8.2 GPIO Status Interfaces

```typescript
// GPIO Status Item (vom ESP im Heartbeat)
interface GpioStatusItem {
  gpio: number;                         // 0-39
  owner: "sensor" | "actuator" | "system";
  component: string;                    // Max 32 chars
  mode: 0 | 1 | 2;                     // 0=INPUT, 1=OUTPUT, 2=INPUT_PULLUP
  safe: boolean;
}

// GPIO Usage Item (DB + ESP kombiniert)
interface GpioUsageItem {
  gpio: number;
  owner: "sensor" | "actuator" | "system";
  component: string;
  name: string | null;
  id: string | null;                    // UUID des Sensors/Aktors
  source: "database" | "esp_reported" | "static";
}

// I2C Bus Info
interface I2CBusInfo {
  sda_pin: number;
  scl_pin: number;
  is_available: boolean;
  devices: {
    i2c_address: string;                // "0xXX"
    sensor_type: string;
    sensor_name: string;
  }[];
}

// OneWire Bus Info
interface OneWireBusInfo {
  gpio: number;
  is_available: boolean;
  devices: {
    onewire_address: string;            // 16 Hex chars
    sensor_type: string;
    sensor_name: string;
  }[];
}

// Vollständiger GPIO Status Response
interface GpioStatusResponse {
  esp_id: string;
  available: number[];                  // Verfügbare GPIOs
  reserved: GpioUsageItem[];           // Belegte GPIOs (Analog/Digital)
  system: number[];                     // System-reserviert
  reserved_gpios: number[];             // Exklusiv reserviert (Analog/Digital)
  i2c_bus: I2CBusInfo | null;
  onewire_buses: OneWireBusInfo[];
  hardware_type: string;
  last_esp_report: string | null;       // ISO 8601
}
```

### 8.3 ESP Health Interfaces

```typescript
// Health Metrics
interface ESPHealthMetrics {
  uptime: number;                       // Sekunden seit Boot
  heap_free: number;                    // Bytes
  wifi_rssi: number;                    // dBm (typisch -100 bis 0)
  sensor_count: number;
  actuator_count: number;
  timestamp: number;                    // Unix Timestamp
}

// Health Response
interface ESPHealthResponse {
  success: boolean;
  device_id: string;
  status: string;
  metrics: ESPHealthMetrics | null;
  last_seen: string | null;
  uptime_formatted: string | null;      // "1d 2h 30m"
}

// WebSocket esp_health Event
interface ESPHealthEvent {
  type: "esp_health";
  timestamp: number;
  data: {
    esp_id: string;
    status: "online" | "offline";
    message: string;
    heap_free: number;
    wifi_rssi: number;
    uptime: number;
    sensor_count: number;
    actuator_count: number;
    timestamp: number;
    gpio_status: GpioStatusItem[];
    gpio_reserved_count: number;
  };
}
```

### 8.4 Discovery/Approval Interfaces

```typescript
// Pending Device
interface PendingESPDevice {
  device_id: string;
  discovered_at: string;                // ISO 8601
  last_seen: string | null;             // Für "vor X Zeit" Anzeige
  zone_id: string | null;
  heap_free: number | null;
  wifi_rssi: number | null;
  sensor_count: number;
  actuator_count: number;
  heartbeat_count: number;
}

// Pending Devices List Response
interface PendingDevicesListResponse {
  success: boolean;
  devices: PendingESPDevice[];
  count: number;
}

// Approval Request
interface ESPApprovalRequest {
  name?: string;
  zone_id?: string;
  zone_name?: string;
}

// Rejection Request
interface ESPRejectionRequest {
  reason: string;                       // Required
}

// Approval Response
interface ESPApprovalResponse {
  success: boolean;
  message: string;
  device_id: string;
  status: "approved" | "rejected";
  approved_by?: string;
  approved_at?: string;
  rejection_reason?: string;
}
```

### 8.5 Config Response Interfaces

```typescript
// Config Failure Item
interface ConfigFailureItem {
  type: "sensor" | "actuator";
  gpio: number;
  error_code: number;                   // Error-Code aus error_codes.h
  error: string;                        // "GPIO_CONFLICT", "MISSING_FIELD", etc.
  detail: string | null;                // Menschenlesbare Details
}

// Config Response Payload
interface ConfigResponsePayload {
  status: "success" | "partial_success" | "error" | "failed";
  type: "sensor" | "actuator" | "zone" | "system" | "wifi" | "unknown";
  count: number;                        // Erfolgreich konfiguriert
  failed_count: number;                 // Fehlgeschlagen
  message: string;
  error_code?: string;                  // Legacy (einzelner Fehler)
  failed_item?: Record<string, any>;    // Legacy
  failures: ConfigFailureItem[];        // Alle Fehler (Phase 4)
  failures_truncated?: boolean;
  total_failures?: number;
}
```

### 8.6 WebSocket Message Types

```typescript
// WebSocket Message Wrapper
interface WebSocketMessage<T> {
  type: string;
  timestamp: number;
  data: T;
}

// Event Types
type WebSocketEventType =
  | "esp_health"
  | "sensor_data"
  | "actuator_status"
  | "device_discovered"
  | "device_rediscovered"
  | "device_approved"
  | "device_rejected"
  | "config_response"
  | "system_event";

// Subscription Filters
interface WebSocketFilters {
  types?: WebSocketEventType[];
  esp_ids?: string[];
  sensor_types?: string[];
}
```

### 8.7 GPIO Validation Interfaces (NEU)

> **Code-Referenz:** `El Servador/god_kaiser_server/src/services/gpio_validation_service.py`

```typescript
// GPIO-Konflikt-Typen
type GpioConflictType = "none" | "system" | "sensor" | "actuator" | "esp_reserved";

// GPIO-Validierungsergebnis
interface GpioValidationResult {
  available: boolean;
  conflict_type?: GpioConflictType;
  conflict_component?: string;  // z.B. "DS18B20", "pump_1", "I2C_SDA"
  conflict_id?: string;         // UUID der konfliktierenden Komponente
  esp_reported_owner?: string;  // Was der ESP für diesen GPIO meldet
  message?: string;             // Menschenlesbare Fehlermeldung
}

// Board-spezifische Constraints
interface BoardConstraints {
  inputOnlyPins: number[];      // Können nur als Input verwendet werden
  i2cBusPins: number[];         // I2C-Bus-Pins (geteilt)
  gpioMax: number;              // Maximale GPIO-Nummer
}

// Board-Constraints für Frontend-Validierung
const BOARD_CONSTRAINTS: Record<string, BoardConstraints> = {
  "ESP32_WROOM": {
    inputOnlyPins: [34, 35, 36, 39],
    i2cBusPins: [21, 22],
    gpioMax: 39
  },
  "XIAO_ESP32_C3": {
    inputOnlyPins: [],
    i2cBusPins: [4, 5],
    gpioMax: 21
  }
};
```

### 8.8 Device Status Interfaces (NEU)

```typescript
// Alle möglichen Device-Status (Code-Referenz: schemas/esp.py:198-200)
type DeviceStatus =
  | "online"           // Aktiv, sendet Heartbeats
  | "offline"          // Keine Heartbeats seit 5 Minuten
  | "error"            // Fehler gemeldet
  | "unknown"          // Nie gesehen
  | "pending_approval" // Neu entdeckt, wartet auf Genehmigung
  | "approved"         // Genehmigt, wartet auf ersten Heartbeat danach
  | "rejected";        // Abgelehnt (5 Minuten Cooldown)

// Device-Status-Anzeige Mapping
const DEVICE_STATUS_UI: Record<DeviceStatus, { label: string; color: string; icon: string }> = {
  online: { label: "Online", color: "green", icon: "check-circle" },
  offline: { label: "Offline", color: "gray", icon: "minus-circle" },
  error: { label: "Fehler", color: "red", icon: "exclamation-circle" },
  unknown: { label: "Unbekannt", color: "gray", icon: "question-circle" },
  pending_approval: { label: "Wartet auf Genehmigung", color: "yellow", icon: "clock" },
  approved: { label: "Genehmigt", color: "blue", icon: "check" },
  rejected: { label: "Abgelehnt", color: "red", icon: "ban" }
};
```

### 8.9 Discovery Event Interfaces (NEU)

```typescript
// WebSocket device_discovered Event
interface DeviceDiscoveredEvent {
  type: "device_discovered";
  timestamp: number;
  data: {
    esp_id: string;
    device_id: string;             // Gleich wie esp_id (Frontend-Kompatibilität)
    discovered_at: string;         // ISO 8601
    zone_id: string | null;
    heap_free: number | null;
    wifi_rssi: number | null;
    sensor_count: number;
    actuator_count: number;
  };
}

// WebSocket device_approved Event
interface DeviceApprovedEvent {
  type: "device_approved";
  timestamp: number;
  data: {
    device_id: string;
    approved_by: string;
    approved_at: string;           // ISO 8601
    status: "approved";
  };
}

// WebSocket device_rejected Event
interface DeviceRejectedEvent {
  type: "device_rejected";
  timestamp: number;
  data: {
    device_id: string;
    rejection_reason: string;
    rejected_at: string;           // ISO 8601
    cooldown_until: string | null; // ISO 8601 oder null
  };
}
```

---

## 9. REST API Endpoints (Vollständig)

> **Code-Referenz:** `El Servador/god_kaiser_server/src/api/v1/esp.py`

### 9.1 Device Discovery & Approval (NEU)

Diese Endpoints fehlen im ursprünglichen Dokument, sind aber für die Device-Management UI essentiell.

#### GET /api/v1/esp/devices/pending

**Beschreibung:** Liste aller ESP-Geräte die auf Genehmigung warten.

**Requires:** Operator oder Admin Rolle

**Response 200:**
```json
{
  "success": true,
  "devices": [
    {
      "device_id": "ESP_12AB34CD",
      "discovered_at": "2026-01-29T10:00:00Z",
      "last_seen": "2026-01-29T10:30:00Z",
      "zone_id": null,
      "heap_free": 45000,
      "wifi_rssi": -55,
      "sensor_count": 0,
      "actuator_count": 0,
      "heartbeat_count": 5
    }
  ],
  "count": 1
}
```

#### POST /api/v1/esp/devices/{esp_id}/approve

**Beschreibung:** Genehmigt ein pending ESP-Gerät.

**Request:**
```json
{
  "name": "Greenhouse Sensor 1",
  "zone_id": "greenhouse-zone-a",
  "zone_name": "Greenhouse Zone A"
}
```

**Response 200:**
```json
{
  "success": true,
  "message": "Device 'ESP_12AB34CD' approved successfully",
  "device_id": "ESP_12AB34CD",
  "status": "approved",
  "approved_by": "admin",
  "approved_at": "2026-01-29T10:35:00Z"
}
```

#### POST /api/v1/esp/devices/{esp_id}/reject

**Beschreibung:** Lehnt ein ESP-Gerät ab. Nach 5 Minuten Cooldown kann es erneut entdeckt werden.

**Request:**
```json
{
  "reason": "Unknown device - not part of authorized hardware inventory"
}
```

**Response 200:**
```json
{
  "success": true,
  "message": "Device 'ESP_12AB34CD' rejected",
  "device_id": "ESP_12AB34CD",
  "status": "rejected",
  "rejection_reason": "Unknown device - not part of authorized hardware inventory"
}
```

#### DELETE /api/v1/esp/devices/{esp_id}

**Beschreibung:** Löscht ein ESP-Gerät inkl. aller Sensoren/Aktoren. Für verwaiste Mocks oder dekommissionierte Hardware.

**Response 204:** Kein Body (erfolgreiche Löschung)

### 9.2 Vollständige Endpoint-Übersicht

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/devices` | Liste alle ESPs | User |
| GET | `/devices/pending` | Liste pending ESPs | Operator |
| GET | `/devices/{esp_id}` | ESP Details | User |
| POST | `/devices` | Registriere ESP manuell | Operator |
| PATCH | `/devices/{esp_id}` | Update ESP | Operator |
| DELETE | `/devices/{esp_id}` | Lösche ESP | Operator |
| POST | `/devices/{esp_id}/approve` | Genehmige ESP | Operator |
| POST | `/devices/{esp_id}/reject` | Lehne ESP ab | Operator |
| POST | `/devices/{esp_id}/config` | Sende Config via MQTT | Operator |
| POST | `/devices/{esp_id}/restart` | Restart-Befehl | Operator |
| POST | `/devices/{esp_id}/reset` | Factory-Reset | Operator |
| GET | `/devices/{esp_id}/health` | Health-Metriken | User |
| GET | `/devices/{esp_id}/gpio-status` | GPIO-Belegung | User |
| POST | `/devices/{esp_id}/assign_kaiser` | Kaiser zuweisen | Operator |
| GET | `/discovery` | Network-Discovery | User |

---

## 10. WebSocket Events (Vollständig)

> **Code-Referenz:** `El Servador/god_kaiser_server/src/websocket/manager.py`
> **Code-Referenz:** `El Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py`

### 10.1 Alle Event-Typen

| Event | Wann gesendet | Frontend-Aktion |
|-------|---------------|-----------------|
| `esp_health` | Jeder Heartbeat (60s) | Device-Status aktualisieren |
| `device_discovered` | Neues Gerät entdeckt | Badge/Notification anzeigen |
| `device_rediscovered` | Abgelehntes Gerät nach Cooldown | Notification anzeigen |
| `device_approved` | Admin genehmigt Gerät | Device-Liste aktualisieren |
| `device_rejected` | Admin lehnt Gerät ab | Aus pending-Liste entfernen |
| `sensor_data` | Sensor-Daten empfangen | Echtzeit-Werte anzeigen |
| `actuator_status` | Aktor-Status geändert | Aktor-UI aktualisieren |
| `config_response` | ESP bestätigt Config | Config-Feedback anzeigen |
| `system_event` | System-Event | Notification/Log anzeigen |

### 10.2 Event-Payload-Details

#### device_discovered
```json
{
  "type": "device_discovered",
  "timestamp": 1735818000,
  "data": {
    "esp_id": "ESP_12AB34CD",
    "device_id": "ESP_12AB34CD",
    "discovered_at": "2026-01-29T10:00:00Z",
    "zone_id": null,
    "heap_free": 45000,
    "wifi_rssi": -55,
    "sensor_count": 0,
    "actuator_count": 0
  }
}
```

#### device_approved
```json
{
  "type": "device_approved",
  "timestamp": 1735818000,
  "data": {
    "device_id": "ESP_12AB34CD",
    "approved_by": "admin",
    "approved_at": "2026-01-29T10:35:00Z",
    "status": "approved"
  }
}
```

#### device_rejected
```json
{
  "type": "device_rejected",
  "timestamp": 1735818000,
  "data": {
    "device_id": "ESP_12AB34CD",
    "rejection_reason": "Unknown device",
    "rejected_at": "2026-01-29T10:35:00Z",
    "cooldown_until": null
  }
}
```

### 10.3 WebSocket Subscription Filter

Frontend kann Events filtern via:

```typescript
// Subscription-Nachricht an WebSocket senden
const subscribeMessage = {
  action: "subscribe",
  filters: {
    types: ["esp_health", "sensor_data"],  // Nur bestimmte Event-Typen
    esp_ids: ["ESP_12AB34CD"],             // Nur bestimmte ESPs
    sensor_types: ["DS18B20", "SHT31"]     // Nur bestimmte Sensor-Typen
  }
};
```

### 10.4 Rate-Limiting

- **Limit:** 10 Nachrichten pro Sekunde pro Client
- **Verhalten:** Überschüssige Nachrichten werden verworfen (kein Error)
- **Code-Referenz:** `websocket/manager.py:263-292`

---

## Anhang A: Sequenzdiagramme

### A.1 GPIO-Status-Abruf

```
Frontend                    Server                      ESP32
    |                          |                          |
    |-- GET /gpio-status ----->|                          |
    |                          |-- Query DB sensors ----->|
    |                          |<-- Sensor list ----------|
    |                          |                          |
    |                          |-- Query DB actuators --->|
    |                          |<-- Actuator list --------|
    |                          |                          |
    |                          |-- Check metadata ------->|
    |                          |   (gpio_status from HB)  |
    |                          |                          |
    |<-- GpioStatusResponse ---|                          |
```

### A.2 Heartbeat mit GPIO-Status

```
ESP32                       MQTT Broker                  Server                      Frontend (WS)
  |                              |                          |                              |
  |-- Publish heartbeat -------->|                          |                              |
  |   (mit gpio_status[])        |                          |                              |
  |                              |-- Deliver to handler --->|                              |
  |                              |                          |                              |
  |                              |                          |-- Update device --------->|  |
  |                              |                          |   status, last_seen       |  |
  |                              |                          |                           |  |
  |                              |                          |-- Store gpio_status ----->|  |
  |                              |                          |   in metadata             |  |
  |                              |                          |                           |  |
  |                              |                          |-- Broadcast esp_health ---|->|
  |                              |                          |   via WebSocket           |  |
  |                              |                          |                              |
  |<-- Heartbeat ACK ------------|<-------------------------|                              |
      (status, config_available) |                          |                              |
```

---

## Anhang B: Wichtige Code-Referenzen

| Komponente | ESP32 Datei | Server Datei |
|------------|-------------|--------------|
| GPIO Manager | `El Trabajante/src/drivers/gpio_manager.h/.cpp` | - |
| I2C Bus | `El Trabajante/src/drivers/i2c_bus.h/.cpp` | - |
| OneWire Bus | `El Trabajante/src/drivers/onewire_bus.h/.cpp` | - |
| PWM Controller | `El Trabajante/src/drivers/pwm_controller.h/.cpp` | - |
| Storage Manager | `El Trabajante/src/services/config/storage_manager.cpp` | - |
| Error Codes | `El Trabajante/src/models/error_codes.h` | `src/core/error_codes.py` |
| ESP API | - | `src/api/v1/esp.py` |
| GPIO Status Schema | - | `src/schemas/esp.py` |
| GPIO Validation | - | `src/services/gpio_validation_service.py` |
| Heartbeat Handler | - | `src/mqtt/handlers/heartbeat_handler.py` |
| WebSocket Manager | - | `src/websocket/manager.py` |
| Hardware Config ESP32 | `El Trabajante/src/config/hardware/esp32_dev.h` | - |
| Hardware Config XIAO | `El Trabajante/src/config/hardware/xiao_esp32c3.h` | - |

---

## Anhang C: Änderungshistorie

### Version 2.0 (2026-01-29) - Review & Ergänzungen

**Korrekturen:**
- GPIO Mode-Normalisierung: Arduino→Protokoll Mapping vollständig dokumentiert
- Hardware Config XIAO: I2C-Pins korrigiert (4/5 statt 21/22), OneWire-Pin korrigiert (6 statt 4)
- System-Reserved-Pins: Unterschied ESP32-seitig vs. Server-seitig dokumentiert

**Ergänzungen:**
- Section 9: REST API Endpoints vollständig (pending, approve, reject, delete)
- Section 10: WebSocket Events vollständig (device_discovered, approved, rejected)
- TypeScript Interfaces: GPIO Validation, Device Status, Discovery Events
- Error-Codes: 40+ zusätzliche Codes (HTTP, Network, State, Watchdog, Approval)
- Code-Referenzen zu allen Werten hinzugefügt

### Version 1.0 (2026-01-29) - Initiale Version

- Grundstruktur für Hardware Foundation
- GPIO, I2C, OneWire, PWM Dokumentation
- Basis-TypeScript-Interfaces

---

**Letzte Aktualisierung:** 2026-01-29
**Version:** 2.0

---

> **Für Frontend-Entwickler:** Dieses Dokument enthält alle Informationen, die Sie benötigen, um die Hardware Foundation UI vollständig zu implementieren. Bei Fragen, die hier nicht beantwortet werden, liegt möglicherweise ein Dokumentationsfehler vor.
>
> **Verifiziert gegen Code:** Alle Werte wurden gegen den aktuellen ESP32- und Server-Code geprüft.
> **Code-Referenzen:** Jede kritische Information enthält eine Code-Referenz zur Verifizierung.
