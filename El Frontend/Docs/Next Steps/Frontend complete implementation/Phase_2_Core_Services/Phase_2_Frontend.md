# Phase 2 Core Services - Frontend-Entwickler-Referenz

**Version:** 1.0
**Erstelldatum:** 2026-01-30
**Scope:** SensorManager, ActuatorManager, SafetyController
**Zielgruppe:** Frontend-Entwickler (Vue 3 / TypeScript)

---

## 0. Quick Reference

| Ich will... | Springe zu |
|-------------|------------|
| Sensor-Werte live anzeigen | [Section 2.1: WebSocket sensor_data](#21-sensor_data) |
| Sensor-Config erstellen | [Section 3.1: POST /sensors](#311-sensor-erstellen) |
| Aktor steuern (ON/OFF/PWM) | [Section 3.2: POST /actuators/.../command](#321-befehl-senden) |
| Emergency-Stop auslösen | [Section 3.2: POST /actuators/emergency-stop](#324-emergency-stop-fleet-weit) |
| Error-Codes anzeigen | [Section 5: Error-Codes](#5-error-codes-für-ui) |
| Quality-Badge darstellen | [Section 6.1: Quality-System](#61-sensor-quality-system) |
| TypeScript Interfaces | [Section 7: TypeScript Interfaces](#7-typescript-interfaces) |

---

## 1. Architektur-Überblick für Frontend

### 1.1 Datenfluss-Prinzip

```
┌─────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Vue 3)                                                    │
│                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│  │ REST API    │     │ WebSocket   │     │ Stores      │          │
│  │ (Aktionen)  │     │ (Live-Data) │     │ (State)     │          │
│  └──────┬──────┘     └──────┬──────┘     └─────────────┘          │
│         │                   │                                      │
│         │ POST/PUT/DELETE   │ Events empfangen                     │
│         ▼                   ▼                                      │
└─────────┼───────────────────┼──────────────────────────────────────┘
          │                   │
          │ HTTP              │ WebSocket ws://
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SERVER (God-Kaiser)                                                 │
│                                                                     │
│  REST API ──► Services ──► MQTT Publisher ──► ESP32                │
│                   │                              │                  │
│                   └──► Database                  │                  │
│                   └──► WebSocket Broadcast ◄─────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Wichtige Prinzipien

| Prinzip | Bedeutung für Frontend |
|---------|------------------------|
| **Server-Centric** | Alle Daten kommen vom Server, niemals direkt vom ESP32 |
| **WebSocket für Live-Data** | Sensor-Werte, Aktor-Status kommen als Events |
| **REST für Aktionen** | Befehle, Config-Änderungen über REST API |
| **Safety-First** | Jeder Aktor-Befehl wird vom Server validiert |

---

## 2. WebSocket Events

**Connection:** `ws://localhost:8000/api/v1/ws`

### 2.1 sensor_data

**Trigger:** ESP32 sendet Messwert → Server verarbeitet → Broadcast

```typescript
interface SensorDataEvent {
  event: "sensor_data";
  data: {
    esp_id: string;           // "ESP_12AB34CD"
    device_id: string;        // Alias für esp_id
    gpio: number;             // 0-39
    sensor_type: string;      // "ds18b20", "dht22", "sht31", etc.
    raw_value: number;        // RAW-Wert vom Sensor
    processed_value: number;  // Verarbeiteter Wert (z.B. 23.5)
    unit: string;             // "°C", "%", "pH", etc.
    quality: SensorQuality;   // "good" | "fair" | "poor" | "suspect" | "error" | "unknown"
    timestamp: string;        // ISO 8601: "2026-01-30T12:00:00Z"
    zone_id?: string;         // Zone-Zuordnung
    subzone_id?: string;      // Subzone-Zuordnung
    onewire_address?: string; // OneWire ROM-Code (16 hex chars)
    error_code?: number;      // Falls Fehler aufgetreten
  };
}
```

**UI-Verwendung:**
- Live-Wert in Sensor-Kachel aktualisieren
- Quality-Badge anzeigen (siehe Section 6.1)
- Trend-Graph aktualisieren
- Bei `quality: "error"` → Warnung anzeigen

---

### 2.2 actuator_status

**Trigger:** ESP32 meldet Aktor-Zustand → Server speichert → Broadcast

```typescript
interface ActuatorStatusEvent {
  event: "actuator_status";
  data: {
    esp_id: string;           // "ESP_12AB34CD"
    gpio: number;             // GPIO-Pin
    actuator_type: string;    // "pump" | "valve" | "pwm" | "relay"
    state: ActuatorState;     // "idle" | "active" | "error" | "emergency_stop"
    current_value: number;    // 0.0-1.0 (PWM) oder 0/1 (binary)
    target_value?: number;    // Zielwert falls unterschiedlich
    runtime_ms: number;       // Laufzeit seit Aktivierung
    emergency: EmergencyState;// "normal" | "active" | "clearing" | "resuming"
    timestamp: string;        // ISO 8601
    zone_id?: string;
    subzone_id?: string;
    last_command?: string;    // Letzter Befehl
    error_message?: string;   // Falls state="error"
  };
}
```

**UI-Verwendung:**
- Aktor-Kachel: ON/OFF-Status, PWM-Slider-Position
- Runtime-Anzeige (z.B. "Läuft seit 00:15:32")
- Emergency-Banner wenn `emergency !== "normal"`
- Error-Toast wenn `state === "error"`

---

### 2.3 actuator_response

**Trigger:** ESP32 bestätigt Command-Ausführung

```typescript
interface ActuatorResponseEvent {
  event: "actuator_response";
  data: {
    esp_id: string;
    gpio: number;
    command: string;          // "ON" | "OFF" | "PWM" | "TOGGLE"
    value: number;            // Ausgeführter Wert
    success: boolean;         // true = erfolgreich
    message: string;          // "Command executed" oder Fehlergrund
    correlation_id: string;   // UUID zur Zuordnung
    timestamp: string;
  };
}
```

**UI-Verwendung:**
- Loading-Spinner beenden nach Matching `correlation_id`
- Success/Error-Toast anzeigen
- Bei `success: false` → Error-Message anzeigen

---

### 2.4 actuator_command

**Trigger:** Server hat Command an ESP32 gesendet

```typescript
interface ActuatorCommandEvent {
  event: "actuator_command";
  data: {
    esp_id: string;
    gpio: number;
    command: string;
    value: number;
    duration?: number;        // Optional: Auto-Stop nach X Sekunden
    issued_by: string;        // "user:123" | "logic:456" | "system"
    correlation_id: string;
    timestamp: string;
  };
}
```

**UI-Verwendung:**
- Activity-Log aktualisieren
- "Befehl gesendet" Indikator
- Warten auf `actuator_response` mit gleicher `correlation_id`

---

### 2.5 actuator_command_failed

**Trigger:** Safety-Check hat Command abgelehnt (VOR dem Senden)

```typescript
interface ActuatorCommandFailedEvent {
  event: "actuator_command_failed";
  data: {
    esp_id: string;
    gpio: number;
    command: string;
    value: number;
    error: string;            // Grund der Ablehnung
    error_code?: number;      // Optional: Error-Code
    correlation_id: string;
    timestamp: string;
  };
}
```

**UI-Verwendung:**
- Error-Toast mit `error` Message
- Typische Fehler:
  - "Emergency stop active" → Emergency-Banner zeigen
  - "Value out of range" → Input-Validierung fehlgeschlagen
  - "Actuator not found" → Config-Problem

---

### 2.6 actuator_alert

**Trigger:** ESP32 meldet kritisches Event (Emergency, Timeout)

```typescript
interface ActuatorAlertEvent {
  event: "actuator_alert";
  data: {
    esp_id: string;
    gpio: number;
    alert_type: AlertType;    // "emergency_stop" | "runtime_protection" | "timeout" | "error"
    message: string;          // Menschenlesbare Beschreibung
    severity: "warning" | "critical";
    timestamp: string;
    zone_id?: string;
    subzone_id?: string;
  };
}
```

**UI-Verwendung:**
- **critical:** Roter Banner, Alarm-Sound optional
- **warning:** Gelber Toast
- `runtime_protection` → "Aktor wurde nach 1h automatisch gestoppt"
- `emergency_stop` → "NOTAUS aktiv - alle Aktoren gestoppt"

---

### 2.7 Weitere Events (Vollständigkeit)

| Event | Beschreibung | UI-Aktion |
|-------|--------------|-----------|
| `esp_health` | ESP Online/Offline Status | Kachel grau bei offline |
| `config_response` | ESP hat Config bestätigt | Config-Status aktualisieren |
| `device_discovered` | Neues ESP gefunden | Pending-Devices aktualisieren |
| `device_approved` | ESP wurde freigegeben | Zu aktiven Devices hinzufügen |
| `zone_assignment` | Zone-Zuweisung geändert | Zone-View aktualisieren |

---

## 3. REST API Endpoints

**Base URL:** `http://localhost:8000/api/v1`

### 3.1 Sensor-Endpoints

#### 3.1.1 Sensor erstellen

```http
POST /sensors/{esp_id}
Content-Type: application/json

{
  "gpio": 34,
  "sensor_type": "ds18b20",
  "sensor_name": "Temperatur Zone A",
  "interface_type": "ONEWIRE",        // "I2C" | "ONEWIRE" | "ANALOG" | "DIGITAL"
  "onewire_address": "28FF641E8D3C0C79",  // Nur für OneWire
  "i2c_address": null,                // Nur für I2C (z.B. 0x44)
  "enabled": true,
  "pi_enhanced": true,                // Server-Verarbeitung aktivieren
  "sample_interval_ms": 5000,         // Messintervall
  "operating_mode": "continuous",     // "continuous" | "on_demand" | "scheduled" | "paused"
  "calibration_data": null,           // Optional: Kalibrierungspunkte
  "thresholds": {                     // Optional: Warngrenzen
    "min": 10.0,
    "max": 35.0,
    "critical_min": 5.0,
    "critical_max": 40.0
  }
}
```

**Response (201 Created):**
```json
{
  "id": "uuid-...",
  "esp_id": "uuid-...",
  "gpio": 34,
  "sensor_type": "ds18b20",
  "sensor_name": "Temperatur Zone A",
  "config_status": "pending",
  "created_at": "2026-01-30T12:00:00Z"
}
```

**Config-Status-Werte:**
| Status | Bedeutung | UI-Anzeige |
|--------|-----------|------------|
| `pending` | Warten auf ESP-Bestätigung | Gelber Punkt, Spinner |
| `confirmed` | ESP hat Config übernommen | Grüner Punkt |
| `failed` | ESP konnte nicht konfigurieren | Roter Punkt + Error |
| `partial` | Teilweise erfolgreich | Orange Punkt |

---

#### 3.1.2 Sensor abrufen

```http
GET /sensors/{esp_id}/{gpio}
```

**Response (200 OK):**
```json
{
  "id": "uuid-...",
  "esp_id": "uuid-...",
  "gpio": 34,
  "sensor_type": "ds18b20",
  "sensor_name": "Temperatur Zone A",
  "interface_type": "ONEWIRE",
  "onewire_address": "28FF641E8D3C0C79",
  "enabled": true,
  "pi_enhanced": true,
  "sample_interval_ms": 5000,
  "operating_mode": "continuous",
  "calibration_data": null,
  "thresholds": { "min": 10.0, "max": 35.0 },
  "config_status": "confirmed",
  "created_at": "2026-01-30T12:00:00Z",
  "updated_at": "2026-01-30T12:05:00Z"
}
```

---

#### 3.1.3 Alle Sensoren eines ESP

```http
GET /sensors/{esp_id}
```

**Response:** Array von Sensor-Configs

---

#### 3.1.4 Sensor aktualisieren

```http
PUT /sensors/{esp_id}/{gpio}
Content-Type: application/json

{
  "sensor_name": "Neuer Name",
  "sample_interval_ms": 10000,
  "operating_mode": "on_demand",
  "thresholds": { "min": 15.0, "max": 30.0 }
}
```

---

#### 3.1.5 Sensor löschen

```http
DELETE /sensors/{esp_id}/{gpio}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Sensor removed"
}
```

---

#### 3.1.6 Sensor-Daten abfragen

```http
GET /sensors/{esp_id}/{gpio}/data?start=2026-01-30T00:00:00Z&end=2026-01-30T23:59:59Z&limit=100
```

**Query-Parameter:**
| Parameter | Type | Default | Beschreibung |
|-----------|------|---------|--------------|
| `start` | ISO 8601 | 24h zurück | Startzeit |
| `end` | ISO 8601 | jetzt | Endzeit |
| `limit` | int | 100 | Max Datenpunkte |
| `aggregation` | string | none | "avg", "min", "max", "none" |
| `interval` | string | - | "1m", "5m", "1h" für Aggregation |

**Response:**
```json
{
  "data": [
    {
      "timestamp": "2026-01-30T12:00:00Z",
      "raw_value": 2350,
      "processed_value": 23.5,
      "unit": "°C",
      "quality": "good"
    }
  ],
  "count": 100,
  "has_more": true
}
```

---

#### 3.1.7 On-Demand Messung auslösen

```http
POST /sensors/{esp_id}/{gpio}/trigger
```

**Response (202 Accepted):**
```json
{
  "message": "Measurement triggered",
  "correlation_id": "uuid-..."
}
```

**Hinweis:** Ergebnis kommt über WebSocket `sensor_data`

---

#### 3.1.8 Kalibrierung

```http
POST /sensors/{esp_id}/{gpio}/calibrate
Content-Type: application/json

{
  "calibration_points": [
    { "raw": 1000, "reference": 4.0 },
    { "raw": 2000, "reference": 7.0 },
    { "raw": 3000, "reference": 10.0 }
  ],
  "method": "linear"  // "linear" | "polynomial" | "lookup"
}
```

**Response:**
```json
{
  "success": true,
  "calibration_data": {
    "method": "linear",
    "coefficients": [0.003, 1.0],
    "r_squared": 0.998
  }
}
```

---

### 3.2 Actuator-Endpoints

#### 3.2.1 Befehl senden

```http
POST /actuators/{esp_id}/{gpio}/command
Content-Type: application/json

{
  "command": "ON",           // "ON" | "OFF" | "PWM" | "TOGGLE"
  "value": 1.0,              // 0.0-1.0 für PWM, 0/1 für binary
  "duration": 3600           // Optional: Auto-Stop nach X Sekunden
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "correlation_id": "uuid-...",
  "message": "Command sent"
}
```

**Response (400 Bad Request) - Safety-Rejection:**
```json
{
  "success": false,
  "error": "Emergency stop active",
  "error_code": 2001,
  "correlation_id": "uuid-..."
}
```

**WICHTIG - PWM-Werte:**
- Frontend sendet: `0.0` bis `1.0`
- NICHT 0-255! Der Server validiert und lehnt ab.

---

#### 3.2.2 Aktor erstellen

```http
POST /actuators/{esp_id}
Content-Type: application/json

{
  "gpio": 25,
  "actuator_type": "pump",    // "pump" | "valve" | "pwm" | "relay"
  "actuator_name": "Pumpe Zone A",
  "enabled": true,
  "min_value": 0.0,
  "max_value": 1.0,
  "default_value": 0.0,
  "timeout_seconds": 3600,    // Max Laufzeit (1h)
  "safety_constraints": {
    "requires_sensor_active": true,
    "max_continuous_runtime": 7200
  }
}
```

---

#### 3.2.3 Aktor-Status abrufen

```http
GET /actuators/{esp_id}/{gpio}/status
```

**Response:**
```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 25,
  "actuator_type": "pump",
  "state": "active",
  "current_value": 1.0,
  "target_value": 1.0,
  "runtime_seconds": 1523,
  "last_command": "ON",
  "last_command_timestamp": "2026-01-30T11:34:27Z",
  "emergency": "normal",
  "error_message": null
}
```

---

#### 3.2.4 Emergency-Stop (Fleet-weit)

```http
POST /actuators/emergency-stop
Content-Type: application/json

{
  "reason": "Manueller Notaus durch Operator"
}
```

**Response:**
```json
{
  "success": true,
  "affected_devices": 5,
  "affected_actuators": 12,
  "message": "Emergency stop activated for all devices"
}
```

---

#### 3.2.5 Emergency-Stop (Einzelnes ESP)

```http
POST /actuators/{esp_id}/emergency-stop
Content-Type: application/json

{
  "reason": "Sensor-Fehler Zone A"
}
```

---

#### 3.2.6 Emergency-Stop aufheben

```http
POST /actuators/clear-emergency
Content-Type: application/json

{
  "esp_id": "ESP_12AB34CD"  // Optional: ohne = alle
}
```

**Response:**
```json
{
  "success": true,
  "message": "Emergency stop cleared",
  "recovery_in_progress": true
}
```

**Hinweis:** Nach Clear dauert Recovery ~2-5 Sekunden (gestaffelte Reaktivierung)

---

#### 3.2.7 Emergency-Status abfragen

```http
GET /actuators/emergency-status
```

**Response:**
```json
{
  "global_emergency": false,
  "esp_specific": {
    "ESP_12AB34CD": {
      "active": true,
      "reason": "Sensor-Fehler",
      "timestamp": "2026-01-30T11:00:00Z"
    }
  }
}
```

---

## 4. Sensor-Typen und Einheiten

### 4.1 Verfügbare Sensor-Typen

| sensor_type | Interface | Unit | Typischer Bereich | Multi-Value |
|-------------|-----------|------|-------------------|-------------|
| `ds18b20` | ONEWIRE | °C | -55 bis +125 | Nein |
| `dht22` | DIGITAL | °C, % | -40 bis +80 / 0-100% | Ja (temp, humidity) |
| `sht31` | I2C (0x44) | °C, % | -40 bis +125 / 0-100% | Ja |
| `bme280` | I2C (0x76) | °C, %, hPa | Multi | Ja (temp, humidity, pressure) |
| `ph` | ANALOG | pH | 0-14 | Nein |
| `ec` | ANALOG | mS/cm | 0-20 | Nein |
| `moisture` | ANALOG | % | 0-100 | Nein |
| `light` | ANALOG | lux | 0-100000 | Nein |
| `co2` | I2C | ppm | 400-5000 | Nein |
| `flow` | DIGITAL | L/min | 0-60 | Nein |

### 4.2 Multi-Value Sensoren

Manche Sensoren liefern mehrere Werte gleichzeitig:

```typescript
// DHT22 liefert temperature UND humidity
// Im WebSocket kommen diese als separate Events:

// Event 1:
{ sensor_type: "dht22", gpio: 4, processed_value: 23.5, unit: "°C" }

// Event 2 (gleicher Timestamp):
{ sensor_type: "dht22_humidity", gpio: 4, processed_value: 65.2, unit: "%" }
```

**UI-Hinweis:** Multi-Value Sensoren gruppieren (eine Kachel mit mehreren Werten)

---

## 5. Error-Codes für UI

### 5.1 Sensor Error-Codes (1040-1069)

| Code | Konstante | UI-Anzeige | Aktion |
|------|-----------|------------|--------|
| 1040 | `SENSOR_READ_FAILED` | "Lesefehler" | Retry-Button anzeigen |
| 1041 | `SENSOR_INIT_FAILED` | "Initialisierung fehlgeschlagen" | Config prüfen |
| 1042 | `SENSOR_NOT_FOUND` | "Sensor nicht konfiguriert" | Config erstellen |
| 1043 | `SENSOR_TIMEOUT` | "Timeout beim Lesen" | Verbindung prüfen |
| 1060 | `DS18B20_SENSOR_FAULT` | "Sensor getrennt (-127°C)" | Verkabelung prüfen |
| 1061 | `DS18B20_POWER_ON_RESET` | "Sensor-Reset (85°C)" | Warten auf nächste Messung |
| 1062 | `DS18B20_OUT_OF_RANGE` | "Wert außerhalb Bereich" | Sensor prüfen |
| 1063 | `DS18B20_DISCONNECTED` | "Sensor verloren" | Verkabelung prüfen |

### 5.2 OneWire Error-Codes (1020-1029)

| Code | Konstante | UI-Anzeige |
|------|-----------|------------|
| 1020 | `ONEWIRE_INIT_FAILED` | "Bus-Initialisierung fehlgeschlagen" |
| 1021 | `ONEWIRE_NO_DEVICES` | "Keine Geräte gefunden" |
| 1022 | `ONEWIRE_READ_FAILED` | "Bus-Lesefehler" |
| 1023 | `ONEWIRE_INVALID_ROM_LENGTH` | "Ungültige ROM-Länge" |
| 1024 | `ONEWIRE_INVALID_ROM_FORMAT` | "Ungültiges ROM-Format" |
| 1025 | `ONEWIRE_INVALID_ROM_CRC` | "ROM CRC-Fehler" |
| 1026 | `ONEWIRE_DEVICE_NOT_FOUND` | "Gerät nicht gefunden" |
| 1029 | `ONEWIRE_DUPLICATE_ROM` | "ROM bereits registriert" |

### 5.3 Actuator Error-Codes (1050-1059)

| Code | Konstante | UI-Anzeige | Aktion |
|------|-----------|------------|--------|
| 1050 | `ACTUATOR_SET_FAILED` | "Setzen fehlgeschlagen" | Retry |
| 1051 | `ACTUATOR_INIT_FAILED` | "Initialisierung fehlgeschlagen" | Config prüfen |
| 1052 | `ACTUATOR_NOT_FOUND` | "Aktor nicht konfiguriert" | Config erstellen |
| 1053 | `ACTUATOR_CONFLICT` | "GPIO-Konflikt mit Sensor" | GPIO ändern |

### 5.4 Safety Error-Codes (2000-2099)

| Code | Konstante | UI-Anzeige | Aktion |
|------|-----------|------------|--------|
| 2001 | `EMERGENCY_STOP_ACTIVE` | "NOTAUS aktiv" | Clear-Button anzeigen |
| 2002 | `VALUE_OUT_OF_RANGE` | "Wert außerhalb 0.0-1.0" | Input-Validierung |
| 2003 | `ACTUATOR_DISABLED` | "Aktor deaktiviert" | Config prüfen |
| 2004 | `RUNTIME_EXCEEDED` | "Max. Laufzeit überschritten" | Timeout-Protection aktiv |

---

## 6. Status-Darstellung

### 6.1 Sensor Quality-System

| Quality | Farbe | Icon | Beschreibung |
|---------|-------|------|--------------|
| `good` | Grün (#22c55e) | ✓ | Wert innerhalb Datasheet-Grenzen |
| `fair` | Gelb (#eab308) | ~ | Leichte Abweichungen |
| `poor` | Orange (#f97316) | ! | Signifikante Abweichungen |
| `suspect` | Rot (#ef4444) | ? | Verdächtig (z.B. DS18B20 out-of-range) |
| `error` | Rot (#dc2626) | ✗ | Lesefehler, -127°C, Hardware-Problem |
| `unknown` | Grau (#6b7280) | - | Keine Validierung möglich |

**CSS-Klassen-Vorschlag:**
```css
.quality-good { color: #22c55e; }
.quality-fair { color: #eab308; }
.quality-poor { color: #f97316; }
.quality-suspect { color: #ef4444; }
.quality-error { color: #dc2626; background: #fef2f2; }
.quality-unknown { color: #6b7280; }
```

---

### 6.2 Actuator States

| State | Farbe | Icon | Beschreibung |
|-------|-------|------|--------------|
| `idle` | Grau (#6b7280) | ○ | Aus, inaktiv |
| `active` | Grün (#22c55e) | ● | Läuft |
| `error` | Rot (#dc2626) | ✗ | Fehler aufgetreten |
| `emergency_stop` | Rot (#dc2626) | ⛔ | NOTAUS aktiv |

---

### 6.3 Emergency States

| Emergency | UI-Darstellung |
|-----------|----------------|
| `normal` | Keine Anzeige |
| `active` | Roter Banner: "🚨 NOTAUS AKTIV" |
| `clearing` | Gelber Banner: "⏳ NOTAUS wird aufgehoben..." |
| `resuming` | Gelber Banner: "⏳ Systeme werden reaktiviert..." |

---

### 6.4 Operating Modes (Sensoren)

| Mode | Icon | Beschreibung | UI-Element |
|------|------|--------------|------------|
| `continuous` | 🔄 | Automatische Messung | Intervall-Anzeige |
| `on_demand` | 👆 | Nur bei Anfrage | "Messen"-Button |
| `scheduled` | 📅 | Server-gesteuert | Schedule-Anzeige |
| `paused` | ⏸️ | Pausiert | "Fortsetzen"-Button |

---

## 7. TypeScript Interfaces

```typescript
// ============================================
// SENSOR INTERFACES
// ============================================

type SensorQuality = "good" | "fair" | "poor" | "suspect" | "error" | "unknown";
type InterfaceType = "I2C" | "ONEWIRE" | "ANALOG" | "DIGITAL";
type OperatingMode = "continuous" | "on_demand" | "scheduled" | "paused";
type ConfigStatus = "pending" | "confirmed" | "failed" | "partial";

interface SensorConfig {
  id: string;
  esp_id: string;
  gpio: number;
  sensor_type: string;
  sensor_name: string;
  interface_type: InterfaceType;
  i2c_address?: number;
  onewire_address?: string;
  enabled: boolean;
  pi_enhanced: boolean;
  sample_interval_ms: number;
  operating_mode: OperatingMode;
  calibration_data?: CalibrationData;
  thresholds?: SensorThresholds;
  config_status: ConfigStatus;
  config_error?: string;
  created_at: string;
  updated_at: string;
}

interface SensorThresholds {
  min?: number;
  max?: number;
  critical_min?: number;
  critical_max?: number;
}

interface CalibrationData {
  method: "linear" | "polynomial" | "lookup";
  coefficients?: number[];
  lookup_table?: { raw: number; reference: number }[];
  r_squared?: number;
}

interface SensorReading {
  esp_id: string;
  gpio: number;
  sensor_type: string;
  raw_value: number;
  processed_value: number;
  unit: string;
  quality: SensorQuality;
  timestamp: string;
  error_code?: number;
}

interface SensorCreateRequest {
  gpio: number;
  sensor_type: string;
  sensor_name: string;
  interface_type: InterfaceType;
  i2c_address?: number;
  onewire_address?: string;
  enabled?: boolean;
  pi_enhanced?: boolean;
  sample_interval_ms?: number;
  operating_mode?: OperatingMode;
  thresholds?: SensorThresholds;
}

// ============================================
// ACTUATOR INTERFACES
// ============================================

type ActuatorType = "pump" | "valve" | "pwm" | "relay";
type ActuatorState = "idle" | "active" | "error" | "emergency_stop";
type EmergencyState = "normal" | "active" | "clearing" | "resuming";
type ActuatorCommand = "ON" | "OFF" | "PWM" | "TOGGLE";

interface ActuatorConfig {
  id: string;
  esp_id: string;
  gpio: number;
  actuator_type: ActuatorType;
  actuator_name: string;
  enabled: boolean;
  min_value: number;
  max_value: number;
  default_value: number;
  timeout_seconds?: number;
  safety_constraints?: SafetyConstraints;
  config_status: ConfigStatus;
  config_error?: string;
  created_at: string;
  updated_at: string;
}

interface SafetyConstraints {
  requires_sensor_active?: boolean;
  max_continuous_runtime?: number;
  linked_sensor_gpio?: number;
}

interface ActuatorStatus {
  esp_id: string;
  gpio: number;
  actuator_type: ActuatorType;
  state: ActuatorState;
  current_value: number;
  target_value?: number;
  runtime_seconds: number;
  last_command?: string;
  last_command_timestamp?: string;
  emergency: EmergencyState;
  error_message?: string;
}

interface ActuatorCommandRequest {
  command: ActuatorCommand;
  value: number;           // 0.0 - 1.0
  duration?: number;       // Auto-stop in seconds
}

interface ActuatorCommandResponse {
  success: boolean;
  correlation_id: string;
  message: string;
  error?: string;
  error_code?: number;
}

interface ActuatorCreateRequest {
  gpio: number;
  actuator_type: ActuatorType;
  actuator_name: string;
  enabled?: boolean;
  min_value?: number;
  max_value?: number;
  default_value?: number;
  timeout_seconds?: number;
  safety_constraints?: SafetyConstraints;
}

// ============================================
// EMERGENCY INTERFACES
// ============================================

interface EmergencyStopRequest {
  esp_id?: string;         // Optional: ohne = fleet-weit
  reason: string;
}

interface EmergencyStopResponse {
  success: boolean;
  affected_devices: number;
  affected_actuators: number;
  message: string;
}

interface EmergencyStatus {
  global_emergency: boolean;
  esp_specific: {
    [esp_id: string]: {
      active: boolean;
      reason: string;
      timestamp: string;
    };
  };
}

// ============================================
// WEBSOCKET EVENT INTERFACES
// ============================================

interface WebSocketMessage<T = unknown> {
  event: string;
  data: T;
}

interface SensorDataEventData {
  esp_id: string;
  device_id: string;
  gpio: number;
  sensor_type: string;
  raw_value: number;
  processed_value: number;
  unit: string;
  quality: SensorQuality;
  timestamp: string;
  zone_id?: string;
  subzone_id?: string;
  onewire_address?: string;
  error_code?: number;
}

interface ActuatorStatusEventData {
  esp_id: string;
  gpio: number;
  actuator_type: ActuatorType;
  state: ActuatorState;
  current_value: number;
  target_value?: number;
  runtime_ms: number;
  emergency: EmergencyState;
  timestamp: string;
  zone_id?: string;
  subzone_id?: string;
  last_command?: string;
  error_message?: string;
}

interface ActuatorResponseEventData {
  esp_id: string;
  gpio: number;
  command: ActuatorCommand;
  value: number;
  success: boolean;
  message: string;
  correlation_id: string;
  timestamp: string;
}

interface ActuatorAlertEventData {
  esp_id: string;
  gpio: number;
  alert_type: "emergency_stop" | "runtime_protection" | "timeout" | "error";
  message: string;
  severity: "warning" | "critical";
  timestamp: string;
  zone_id?: string;
  subzone_id?: string;
}

// ============================================
// API RESPONSE WRAPPERS
// ============================================

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  error_code?: number;
}

interface PaginatedResponse<T> {
  data: T[];
  count: number;
  has_more: boolean;
  next_cursor?: string;
}
```

---

## 8. UI-Komponenten-Empfehlungen

### 8.1 Sensor-Kachel

```
┌─────────────────────────────────────┐
│ 🌡️ Temperatur Zone A          [●]  │  ← Quality-Indikator
│                                     │
│         23.5 °C                     │  ← Großer Wert
│                                     │
│ ─────────────────────────────────── │  ← Sparkline (letzte 24h)
│                                     │
│ GPIO: 34  │  DS18B20  │  🔄 5s     │  ← Metadata
└─────────────────────────────────────┘
```

### 8.2 Aktor-Kachel

```
┌─────────────────────────────────────┐
│ 💧 Pumpe Zone A               [●]   │  ← State-Indikator
│                                     │
│     ┌─────────────────────────┐     │
│     │ [OFF]      ████ [ON]    │     │  ← Toggle oder PWM-Slider
│     └─────────────────────────┘     │
│                                     │
│ Laufzeit: 00:15:32  │  Max: 01:00  │  ← Runtime-Anzeige
└─────────────────────────────────────┘
```

### 8.3 Emergency-Banner

```
┌─────────────────────────────────────────────────────────────────┐
│ 🚨 NOTAUS AKTIV                                                 │
│                                                                 │
│ Grund: Manueller Notaus durch Operator                         │
│ Seit: 30.01.2026 11:00:00                                      │
│ Betroffene Geräte: 5 ESPs, 12 Aktoren                          │
│                                                                 │
│                      [NOTAUS AUFHEBEN]                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. Häufige Szenarien

### 9.1 Sensor hinzufügen

1. User wählt ESP und GPIO
2. `POST /sensors/{esp_id}` mit Config
3. Response mit `config_status: "pending"`
4. Warten auf WebSocket `config_response` mit `status: "confirmed"`
5. UI aktualisieren

### 9.2 Aktor steuern

1. User klickt ON-Button
2. `POST /actuators/{esp_id}/{gpio}/command` mit `{ command: "ON", value: 1.0 }`
3. Response mit `correlation_id`
4. Loading-Spinner anzeigen
5. Warten auf WebSocket `actuator_response` mit matching `correlation_id`
6. Bei `success: true` → Success-Toast
7. Bei `success: false` → Error-Toast mit `message`

### 9.3 Emergency-Stop

1. User klickt NOTAUS-Button
2. Confirmation-Dialog: "Alle Aktoren werden gestoppt!"
3. `POST /actuators/emergency-stop` mit `{ reason: "Manueller Notaus" }`
4. Response: `affected_devices`, `affected_actuators`
5. Emergency-Banner anzeigen
6. Alle Aktor-Kacheln zeigen `emergency_stop` State
7. Alle Steuerungselemente deaktivieren

### 9.4 DS18B20 -127°C Error

1. WebSocket `sensor_data` mit:
   - `raw_value: -2032` (RAW für -127°C)
   - `processed_value: -127`
   - `quality: "error"`
   - `error_code: 1060`
2. Sensor-Kachel:
   - Wert in Rot anzeigen
   - Quality-Badge: ✗ error
   - Tooltip: "Sensor getrennt - Verkabelung prüfen"

---

## 10. Checkliste für Frontend-Entwickler

### 10.1 Muss implementiert sein

- [ ] WebSocket-Connection mit Reconnect-Logic
- [ ] Alle 6 WebSocket-Event-Handler
- [ ] REST API Client für alle Endpoints
- [ ] Loading-States für async Operations
- [ ] Error-Handling für alle API-Calls
- [ ] `correlation_id` Tracking für Commands
- [ ] Quality-Badge-Komponente
- [ ] State-Indikator-Komponente
- [ ] Emergency-Banner-Komponente
- [ ] PWM-Slider mit 0.0-1.0 Validierung


### 10.2 Kritische Validierungen

- [ ] PWM-Werte: `0.0 <= value <= 1.0` (NICHT 0-255!)
- [ ] GPIO: `0 <= gpio <= 39` (ESP32 Bereich)
- [ ] OneWire ROM-Code: 16 Hex-Zeichen
- [ ] I2C-Adresse: 7-Bit (0x00-0x7F)
- [ ] Timestamp: ISO 8601 Format

---

**Ende der Frontend-Entwickler-Referenz**

*Basiert auf Phase 2 Backend-Analyse vom 2026-01-29*
*Erstellt am 2026-01-30*