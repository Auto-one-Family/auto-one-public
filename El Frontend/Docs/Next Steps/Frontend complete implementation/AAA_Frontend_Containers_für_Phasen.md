# 🤖 KI-AGENTEN NAVIGATION

> **LIES DIESEN ABSCHNITT ZUERST** - Du wirst einen spezifischen Container bearbeiten.

## Schnell-Navigation

**Du bekommst eine Container-Nummer (1-13). So findest du alles:**

1. **Container-Liste** (direkt nach dieser Sektion): Zeigt alle Dateien pro Container
2. **Container X: [Name]** (in TEIL B): Vollständige technische Dokumentation

## Dokument-Struktur

| Abschnitt | Was findest du dort? |
|-----------|---------------------|
| **Container-Liste** | Frontend-Dateien mit Pfaden pro Container |
| **TEIL A: Systemübersicht** | Architektur, MQTT-Topics, Error-Codes, Quality-System |
| **TEIL B: Container 1-13** | Pro Container: Dateien, Datenfluss, REST API, WebSocket Events, TypeScript-Interfaces |
| **TEIL C: Konstanten** | ESP-ID Format, Timestamps, PWM-Werte |
| **TEIL D: Quick Reference** | REST vs WebSocket Übersicht |

## Dein Workflow
```
1. Container-Nummer erhalten (z.B. "Container 5")
2. → Container-Liste checken → Welche Dateien sind beteiligt?
3. → "Container 5: ..." in TEIL B suchen → Alle technischen Details
4. → Bei Bedarf: TEIL A für Systemkontext (Error-Codes, MQTT-Schema)
```

## Container-Übersicht

| # | Name | Fokus |
|---|------|-------|
| 1 | ESP Orbital Layout | ESP-Cards, Sensor/Aktor-Satellites |
| 2 | Zonen & Drag-Drop | Zone-Zuweisung, Drag&Drop |
| 3 | Sensor/Actuator hinzufügen | GPIO-Konfiguration, Validierung |
| 4 | ActionBar & Filter | Status-Übersicht, Cross-ESP Logic |
| 5 | Tab Ereignisse | Audit-Log, Event-Typen |
| 6 | Tab Server Logs | Log-Viewer |
| 7 | Tab Health | Fleet-Health, Heartbeat |
| 8 | Tab MQTT Traffic | Live MQTT Viewer |
| 9 | Tab Datenbank | DB-Explorer |
| 10 | Cleanup/Retention | Audit-Bereinigung |
| 11 | Toast-System | Benachrichtigungen |
| 12 | WebSocket-Service | Live-Updates |
| 13 | Navigation & Layout | Routing, Header, Sidebar |

---



Container-Liste Frontend

1. Dashboard - ESP Orbital Layout
Das visuelle ESP-Card-System mit Sensor/Actuator-Satellites.

src/components/esp/ESPOrbitalLayout.vue      # Haupt-Komponente (~1100 Zeilen)
src/components/esp/ESPCard.vue               # Basis-Karte
src/components/esp/SensorSatellite.vue       # Sensor-Kreis um ESP
src/components/esp/ActuatorSatellite.vue     # Aktor-Kreis um ESP
src/components/esp/ESPSettingsPopover.vue    # Settings-Panel
src/components/esp/PendingDevicesPanel.vue   # Discovery/Approval
src/stores/esp.ts                            # ESP-State (Pinia)
src/api/esp.ts                               # ESP REST-API

2. Dashboard - Zonen & Drag-Drop
Zonen-Gruppierung und Drag&Drop zwischen Zonen.

src/views/DashboardView.vue                  # Haupt-View
src/components/zones/ZoneGroup.vue           # Zonen-Container
src/components/zones/ZoneAssignmentPanel.vue # Zone-Zuweisung UI
src/components/dashboard/UnassignedDropBar.vue # Untere Leiste
src/composables/useZoneDragDrop.ts           # D&D-Logik, API-Calls
src/stores/dragState.ts                      # Drag-State (global)
src/api/zones.ts                             # Zone REST-API

3. Dashboard - Sensor/Actuator hinzufügen
Panels zum Hinzufügen/Konfigurieren von Sensoren und Aktoren.

src/components/esp/AddSensorPanel.vue        # Sensor hinzufügen
src/components/esp/AddActuatorPanel.vue      # Aktor hinzufügen
src/components/esp/SensorConfigPanel.vue     # Sensor-Einstellungen
src/components/esp/ActuatorConfigPanel.vue   # Aktor-Einstellungen
src/api/sensors.ts                           # Sensor REST-API
src/api/actuators.ts                         # Actuator REST-API
src/utils/sensorDefaults.ts                  # Sensor-Type-Defaults

4. Dashboard - ActionBar & Filter
Status-Übersicht, Filter, Quick-Actions.

src/components/dashboard/ActionBar.vue       # Status-Pills, Filter
src/components/dashboard/ComponentSidebar.vue # Rechte Sidebar
src/components/dashboard/CrossEspConnectionOverlay.vue # Logic-Verbindungen
src/stores/logic.ts                          # Logic-Rules State

5. System Monitor - Tab Ereignisse
Live-Event-Liste mit Filtern.

src/views/SystemMonitorView.vue              # Haupt-View (~2500 Zeilen)
src/components/system-monitor/EventsTab.vue  # Tab-Content
src/components/system-monitor/UnifiedEventList.vue # Virtual-Scroll Liste
src/components/system-monitor/EventDetailsPanel.vue # Event-Details
src/components/system-monitor/DataSourceSelector.vue # Quellen-Filter
src/components/system-monitor/HealthSummaryBar.vue # Device-Health oben
src/api/audit.ts                             # Events REST-API
src/types/websocket-events.ts                # Event-Types
src/utils/eventGrouper.ts                    # Event-Gruppierung

6. System Monitor - Tab Server Logs
Server-Log-Viewer mit Request-ID Correlation.

src/components/system-monitor/ServerLogsTab.vue
src/components/system-monitor/LogManagementPanel.vue
src/api/logs.ts

7. System Monitor - Tab Health
Fleet-Health-Übersicht.

src/components/system-monitor/HealthTab.vue
src/components/system-monitor/HealthProblemChip.vue
src/api/health.ts

8. System Monitor - Tab MQTT Traffic
Live MQTT Message Viewer.

src/components/system-monitor/MqttTrafficTab.vue

9. System Monitor - Tab Datenbank
Datenbank-Explorer.

src/components/system-monitor/DatabaseTab.vue
src/api/database.ts
10. System Monitor - Cleanup/Retention (Admin)

Audit-Log Bereinigung und Backups.

src/components/system-monitor/CleanupPanel.vue
src/components/system-monitor/CleanupPreview.vue
src/components/system-monitor/AutoCleanupStatusBanner.vue
11. Toast-System

Globale Benachrichtigungen.

src/composables/useToast.ts                  # Singleton-Logic
src/components/common/ToastContainer.vue     # Render-Komponente
12. WebSocket-Service

Zentrale WebSocket-Verbindung.

src/services/websocket.ts                    # Singleton-Service
src/composables/useWebSocket.ts              # Composable-Wrapper
src/types/websocket-events.ts                # Event-Definitionen

13. Navigation & Layout
Header, Sidebar, Routing.

src/components/layout/MainLayout.vue
src/components/layout/AppHeader.vue
src/components/layout/AppSidebar.vue
src/router/index.ts

# Frontend-Entwickler Referenz: Vollständige System-Integration

**Erstellt:** 2026-01-29  
**Für:** Frontend-Entwickler (Vue 3 + TypeScript)  
**Zweck:** Backend/ESP32-Referenz für perfekte UI/UX-Implementierung  
**Phase 1 Status:** ✅ Abgeschlossen

---

# TEIL A: SYSTEMÜBERSICHT

## Architektur-Prinzip: Server-Centric

```
┌─────────────────────────────────────────────────────────────────┐
│  ESP32 "El Trabajante" (Dummer Agent)                           │
│  • Sendet RAW-Daten (analogRead = 2048, DS18B20 RAW = 400)     │
│  • Empfängt Commands (Aktor ON/OFF, PWM 0-100%)                │
│  • Heartbeat alle 60 Sekunden                                   │
│  • Code: El Trabajante/src/                                     │
└─────────────────────────────────────────────────────────────────┘
                              │ MQTT
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOD-KAISER SERVER (Intelligenz)                                │
│  • Python/FastAPI + PostgreSQL                                  │
│  • REST API: /api/v1/*                                          │
│  • WebSocket: /api/v1/websocket                                 │
│  • MQTT Broker (Mosquitto)                                      │
│  • Verarbeitet RAW → Processed (z.B. 2048 → pH 7.2)            │
│  • Code: El Servador/god_kaiser_server/src/                     │
└─────────────────────────────────────────────────────────────────┘
                              │ WebSocket + REST
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (Vue 3 + TypeScript + Pinia)                          │
│  • WebSocket für Live-Updates                                   │
│  • REST für CRUD-Operationen                                    │
│  • Code: El Frontend/src/                                       │
└─────────────────────────────────────────────────────────────────┘
```

## MQTT-Topic-Schema (KRITISCH)

```
# ESP → Server (Publish)
kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data       # Sensor-Daten
kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status   # Aktor-Status
kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response # Command-Response
kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert    # Aktor-Alerts
kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat         # Heartbeat (60s)
kaiser/{kaiser_id}/esp/{esp_id}/system/error             # Error-Reports
kaiser/{kaiser_id}/esp/{esp_id}/config_response          # Config-ACK
kaiser/{kaiser_id}/esp/{esp_id}/zone/ack                 # Zone-ACK

# Server → ESP (Subscribe)
kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command  # Aktor-Befehle
kaiser/{kaiser_id}/esp/{esp_id}/config                   # Config-Updates
kaiser/{kaiser_id}/esp/{esp_id}/zone/assign              # Zone-Zuweisung
kaiser/broadcast/emergency                               # Emergency-Stop (alle)

# Default kaiser_id: "god"
```

---

## Phase 1 Implementation (Sensor-Fehlerwert-Handling)

### Neue Error-Codes

```typescript
// I2C Bus-Recovery (1015-1018)
const I2C_ERRORS = {
  1015: { code: "ERROR_I2C_BUS_STUCK", message: "I2C-Bus hängt", severity: "warning" },
  1016: { code: "ERROR_I2C_BUS_RECOVERY_STARTED", message: "I2C-Recovery gestartet", severity: "info" },
  1017: { code: "ERROR_I2C_BUS_RECOVERY_FAILED", message: "I2C-Recovery fehlgeschlagen", severity: "error" },
  1018: { code: "ERROR_I2C_BUS_RECOVERED", message: "I2C-Bus wiederhergestellt", severity: "success" },
};

// DS18B20 Temperatursensor (1060-1063)
const DS18B20_ERRORS = {
  1060: { code: "ERROR_DS18B20_SENSOR_FAULT", message: "Sensor defekt oder nicht angeschlossen (-127°C)", severity: "error" },
  1061: { code: "ERROR_DS18B20_POWER_ON_RESET", message: "Sensor initialisiert sich (85°C)", severity: "warning" },
  1062: { code: "ERROR_DS18B20_OUT_OF_RANGE", message: "Temperatur außerhalb gültiger Bereich", severity: "warning" },
  1063: { code: "ERROR_DS18B20_DISCONNECTED_RUNTIME", message: "Sensor während Betrieb getrennt", severity: "error" },
};
```

### Sensor Quality-System

```typescript
type SensorQuality = "good" | "fair" | "poor" | "suspect" | "error" | "unknown";

// UI-Mapping für Quality
const QUALITY_UI = {
  good:    { label: "Gut",        color: "emerald", bgClass: "bg-emerald-500/20", textClass: "text-emerald-400" },
  fair:    { label: "Akzeptabel", color: "yellow",  bgClass: "bg-yellow-500/20",  textClass: "text-yellow-400" },
  poor:    { label: "Schlecht",   color: "orange",  bgClass: "bg-orange-500/20",  textClass: "text-orange-400" },
  suspect: { label: "Verdächtig", color: "amber",   bgClass: "bg-amber-500/20",   textClass: "text-amber-400" },
  error:   { label: "Fehler",     color: "red",     bgClass: "bg-red-500/20",     textClass: "text-red-400" },
  unknown: { label: "Unbekannt",  color: "gray",    bgClass: "bg-gray-500/20",    textClass: "text-gray-400" },
};

// Wann welche Quality:
// - "good": Normaler Messwert im erwarteten Bereich
// - "fair": Leichte Abweichung, noch verwendbar
// - "poor": Starke Abweichung, mit Vorsicht verwenden
// - "suspect": Verdächtig (z.B. plötzlicher Sprung), sollte geprüft werden
// - "error": Ungültiger Messwert, NICHT verwenden (z.B. -127°C, 85°C Power-On)
// - "unknown": Keine Qualitätsbewertung möglich
```

---

# TEIL B: CONTAINER-REFERENZEN

---

# Container 1: Dashboard - ESP Orbital Layout

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| ESPOrbitalLayout.vue | `components/esp/ESPOrbitalLayout.vue` | Haupt-Komponente, Kreis-Layout |
| ESPCard.vue | `components/esp/ESPCard.vue` | Zentrale ESP-Karte |
| SensorSatellite.vue | `components/esp/SensorSatellite.vue` | Sensor-Kreis um ESP |
| ActuatorSatellite.vue | `components/esp/ActuatorSatellite.vue` | Aktor-Kreis um ESP |
| esp.ts (Store) | `stores/esp.ts` | ESP-State (Pinia) |
| esp.ts (API) | `api/esp.ts` | REST-Client |

## Datenfluss

```
1. INITIAL LOAD
   App.mount() → espStore.fetchAll() → GET /api/v1/esp/devices
   Response → espStore.devices[] aktualisiert → UI rendert

2. LIVE UPDATES (WebSocket)
   Server empfängt MQTT Heartbeat → WebSocket broadcast 'esp_status'
   → espStore.updateDeviceStatus(esp_id, status)
   
   Server empfängt MQTT Sensor-Data → WebSocket broadcast 'sensor_data'
   → espStore.updateSensorValue(esp_id, gpio, value)

3. ORBITAL POSITIONING
   ESPOrbitalLayout berechnet: angle = (index / total) * 360°
   Sensor/Aktor werden im Kreis um ESP positioniert
```

## REST API

| Aktion | Method | Endpoint | Response |
|--------|--------|----------|----------|
| Alle ESPs | GET | `/api/v1/esp/devices` | `ESPDevice[]` |
| Ein ESP | GET | `/api/v1/esp/devices/{esp_id}` | `ESPDevice` |
| ESP aktualisieren | PATCH | `/api/v1/esp/devices/{esp_id}` | `ESPDevice` |
| ESP löschen | DELETE | `/api/v1/esp/devices/{esp_id}` | `204` |

## WebSocket Events

```typescript
// ESP Status Update
interface ESPStatusEvent {
  type: "esp_status";
  data: {
    esp_id: string;           // "ESP_12AB34CD"
    status: "online" | "offline" | "error";
    last_seen: string;        // ISO 8601
    heap_free: number;        // Bytes
    wifi_rssi: number;        // dBm (-30 bis -90)
  };
}

// Sensor Daten Update
interface SensorDataEvent {
  type: "sensor_data";
  data: {
    esp_id: string;
    gpio: number;
    sensor_type: string;
    raw: number;              // RAW-Wert
    value?: number;           // Verarbeiteter Wert (wenn pi_enhanced)
    unit?: string;            // "°C", "%", "pH"
    quality: SensorQuality;   // Phase 1: Kann "error" sein!
    error_code?: number;      // Phase 1: z.B. 1060
    timestamp: number;        // Unix-Sekunden
  };
}
```

## ESP-Status-Logik (Server-seitig)

```typescript
// Server: heartbeat_handler.py
// Online-Bestimmung basierend auf Heartbeat-Alter:

const HEARTBEAT_INTERVAL = 60;  // Sekunden
const OFFLINE_THRESHOLD = 180;  // 3 × Interval

function getESPStatus(last_heartbeat: Date): "online" | "offline" | "warning" {
  const age = (Date.now() - last_heartbeat.getTime()) / 1000;
  
  if (age < HEARTBEAT_INTERVAL * 2) return "online";    // < 120s
  if (age < OFFLINE_THRESHOLD) return "warning";         // 120-180s
  return "offline";                                       // > 180s
}
```

## Sensor-Typen (für Icons/Labels)

```typescript
// Server: sensor_type_registry.py
// Frontend: utils/sensorDefaults.ts

const SENSOR_TYPES: Record<string, SensorTypeConfig> = {
  // Temperatur
  "temp_ds18b20": { label: "Temperatur (DS18B20)", unit: "°C", icon: "Thermometer", min: -55, max: 125 },
  "temp_sht31":   { label: "Temperatur (SHT31)", unit: "°C", icon: "Thermometer", min: -40, max: 125 },
  "temp_dht22":   { label: "Temperatur (DHT22)", unit: "°C", icon: "Thermometer", min: -40, max: 80 },
  "temp_bmp280":  { label: "Temperatur (BMP280)", unit: "°C", icon: "Thermometer", min: -40, max: 85 },
  
  // Feuchtigkeit
  "humidity_sht31": { label: "Luftfeuchtigkeit (SHT31)", unit: "%", icon: "Droplet", min: 0, max: 100 },
  "humidity_dht22": { label: "Luftfeuchtigkeit (DHT22)", unit: "%", icon: "Droplet", min: 0, max: 100 },
  "soil_moisture":  { label: "Bodenfeuchtigkeit", unit: "%", icon: "Droplets", min: 0, max: 100 },
  
  // Umwelt
  "ph":       { label: "pH-Wert", unit: "pH", icon: "Flask", min: 0, max: 14 },
  "ec":       { label: "Leitfähigkeit", unit: "µS/cm", icon: "Zap", min: 0, max: 5000 },
  "light":    { label: "Lichtintensität", unit: "lux", icon: "Sun", min: 0, max: 100000 },
  "co2":      { label: "CO2", unit: "ppm", icon: "Wind", min: 400, max: 5000 },
  "pressure": { label: "Luftdruck", unit: "hPa", icon: "Gauge", min: 300, max: 1100 },
  
  // Wasser
  "water_level": { label: "Wasserstand", unit: "cm", icon: "Waves", min: 0, max: 200 },
  "water_flow":  { label: "Durchfluss", unit: "L/min", icon: "Activity", min: 0, max: 100 },
  "water_temp":  { label: "Wassertemperatur", unit: "°C", icon: "Thermometer", min: 0, max: 50 },
};
```

## Aktor-Typen

```typescript
// Server: actuator_types.h + schemas/actuator.py

const ACTUATOR_TYPES: Record<string, ActuatorTypeConfig> = {
  "pump":    { label: "Pumpe", icon: "Droplet", controlType: "toggle" },
  "valve":   { label: "Ventil", icon: "GitBranch", controlType: "toggle" },
  "fan":     { label: "Lüfter", icon: "Wind", controlType: "pwm" },
  "heater":  { label: "Heizung", icon: "Flame", controlType: "pwm" },
  "light":   { label: "Beleuchtung", icon: "Lightbulb", controlType: "pwm" },
  "motor":   { label: "Motor", icon: "Settings", controlType: "pwm" },
  "relay":   { label: "Relais", icon: "ToggleRight", controlType: "toggle" },
  "humidifier": { label: "Luftbefeuchter", icon: "CloudRain", controlType: "pwm" },
};

// PWM-Werte:
// - Frontend zeigt: 0-100%
// - API erwartet: 0.0-1.0 (Float)
// - ESP32 intern: 0-255 (8-bit)
// Konvertierung: frontend_percent / 100 = api_value
```

---

# Container 2: Dashboard - Zonen & Drag-Drop

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| DashboardView.vue | `views/DashboardView.vue` | Haupt-View |
| ZoneGroup.vue | `components/zones/ZoneGroup.vue` | Zone-Container mit Drop-Target |
| ZoneAssignmentPanel.vue | `components/zones/ZoneAssignmentPanel.vue` | Zone erstellen/bearbeiten |
| UnassignedDropBar.vue | `components/dashboard/UnassignedDropBar.vue` | "Nicht zugewiesen" Bereich |
| useZoneDragDrop.ts | `composables/useZoneDragDrop.ts` | Drag&Drop-Logik |
| dragState.ts | `stores/dragState.ts` | Globaler Drag-State |
| zones.ts (API) | `api/zones.ts` | Zone REST-Client |

## Datenfluss

```
1. DRAG START
   User greift ESP → dragState.startDrag({ type: "esp", data: esp })

2. DROP ON ZONE
   ZoneGroup @drop Event → useZoneDragDrop.handleDrop(zone_id, event)
   → POST /api/v1/zone/devices/{esp_id}/assign { zone_id, zone_name }

3. SERVER VERARBEITUNG
   Server speichert in DB (ESPDevice.master_zone_id)
   Server publiziert MQTT: kaiser/god/esp/{esp_id}/zone/assign
   ESP32 empfängt, speichert in NVS
   ESP32 antwortet: kaiser/god/esp/{esp_id}/zone/ack

4. UI UPDATE
   Server broadcastet WebSocket 'zone_assigned'
   → espStore.updateDeviceZone(esp_id, zone_id, zone_name)
```

## REST API

| Aktion | Method | Endpoint | Body |
|--------|--------|----------|------|
| Zone zuweisen | POST | `/api/v1/zone/devices/{esp_id}/assign` | `{ zone_id, zone_name }` |
| Zone entfernen | POST | `/api/v1/zone/devices/{esp_id}/remove` | - |
| Alle Zonen | GET | `/api/v1/zone/` | - |
| Zone erstellen | POST | `/api/v1/zone/` | `{ zone_id, zone_name }` |

## Zone-ID-Generierung

```typescript
// Frontend: ZoneAssignmentPanel.vue:130-140
// Server validiert: nur [a-z0-9_-] erlaubt

function generateZoneId(zoneName: string): string {
  return zoneName
    .toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

// Beispiele:
// "Gewächshaus Nord" → "gewaechshaus_nord"
// "Zelt 1" → "zelt_1"
// "Test-Zone 2024" → "test_zone_2024"
```

## MQTT-Flow bei Zone-Zuweisung

```
┌──────────┐     POST /assign    ┌──────────┐
│ Frontend │ ─────────────────▶ │  Server  │
└──────────┘                     └──────────┘
                                      │
                            MQTT Publish zone/assign
                                      │
                                      ▼
                                 ┌──────────┐
                                 │  ESP32   │
                                 └──────────┘
                                      │
                            MQTT Publish zone/ack
                                      │
                                      ▼
┌──────────┐   WebSocket 'zone_assigned'   ┌──────────┐
│ Frontend │ ◀──────────────────────────── │  Server  │
└──────────┘                               └──────────┘
```

---

# Container 3: Dashboard - Sensor/Actuator hinzufügen

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| SensorSidebar.vue | `components/dashboard/SensorSidebar.vue` | Sensor-Palette zum Draggen |
| AddSensorPanel.vue | `components/esp/AddSensorPanel.vue` | Sensor-Konfiguration |
| AddActuatorPanel.vue | `components/esp/AddActuatorPanel.vue` | Aktor-Konfiguration |
| SensorConfigPanel.vue | `components/esp/SensorConfigPanel.vue` | Sensor-Einstellungen |
| ActuatorConfigPanel.vue | `components/esp/ActuatorConfigPanel.vue` | Aktor-Einstellungen |
| sensors.ts (API) | `api/sensors.ts` | Sensor REST-Client |
| actuators.ts (API) | `api/actuators.ts` | Actuator REST-Client |
| sensorDefaults.ts | `utils/sensorDefaults.ts` | Sensor-Defaults |

## Datenfluss: Sensor hinzufügen

```
1. USER AKTION
   Drag Sensor aus Sidebar → Drop auf ESP-Card
   → Öffnet AddSensorPanel mit esp_id vorausgefüllt

2. KONFIGURATION
   User wählt: GPIO, Sensor-Typ, Name, Intervall, pi_enhanced
   
3. API CALL
   POST /api/v1/sensors/{esp_id}/{gpio}
   Body: { sensor_type, name, interface_type, interval_ms, ... }

4. SERVER VERARBEITUNG
   Server validiert GPIO (nicht belegt, gültiger Pin)
   Server speichert SensorConfig in DB
   Server publiziert MQTT: kaiser/god/esp/{esp_id}/config
   
5. ESP32 KONFIGURATION
   ESP empfängt Config, initialisiert Sensor
   ESP antwortet: kaiser/god/esp/{esp_id}/config_response
   
6. UI FEEDBACK
   WebSocket 'config_response' → Toast: "Sensor konfiguriert"
```

## REST API

| Aktion | Method | Endpoint | Body |
|--------|--------|----------|------|
| Sensor erstellen | POST | `/api/v1/sensors/{esp_id}/{gpio}` | `SensorCreateSchema` |
| Sensor löschen | DELETE | `/api/v1/sensors/{esp_id}/{gpio}` | - |
| Sensor aktualisieren | PATCH | `/api/v1/sensors/{esp_id}/{gpio}` | `SensorUpdateSchema` |
| Aktor erstellen | POST | `/api/v1/actuators/{esp_id}/{gpio}` | `ActuatorCreateSchema` |
| Aktor steuern | POST | `/api/v1/actuators/{esp_id}/{gpio}/command` | `{ value: number }` |
| Aktor löschen | DELETE | `/api/v1/actuators/{esp_id}/{gpio}` | - |

## Sensor-Konfiguration Schema

```typescript
interface SensorCreateSchema {
  sensor_type: string;           // "temp_ds18b20"
  name?: string;                 // "Temperatur Gewächshaus"
  interface_type: InterfaceType; // "ANALOG" | "I2C" | "ONEWIRE" | "DIGITAL"
  gpio?: number;                 // Bei I2C: optional (Bus-Sharing)
  i2c_address?: number;          // 0x44 für SHT31
  onewire_address?: string;      // "28FF123456789ABC" für DS18B20
  interval_ms?: number;          // 5000 (Standard: 5 Sekunden)
  pi_enhanced?: boolean;         // true = Server verarbeitet RAW-Daten
  enabled?: boolean;             // true
}

type InterfaceType = "ANALOG" | "I2C" | "ONEWIRE" | "DIGITAL";
```

## GPIO-Validierung (Server-Fehler)

```typescript
// Server: gpio_validation_service.py
// Mögliche Fehler-Responses:

interface GPIOValidationError {
  status: 400;
  detail: string;
}

// Beispiele:
// "GPIO 4 is already in use by sensor 'Temperatur'"
// "GPIO 35 is input-only (ESP32-WROOM), cannot be used for actuator"
// "I2C address 0x00 is reserved"
// "I2C address must be in range 0x08-0x77"
// "GPIO 6-11 are reserved for internal flash (ESP32-WROOM)"
```

## GPIO-Bereiche (ESP32)

```typescript
// ESP32-WROOM (Standard Dev Board)
const ESP32_WROOM = {
  available: [4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33],
  inputOnly: [34, 35, 36, 39],           // Nur für Sensoren!
  reserved: [0, 1, 2, 3, 6, 7, 8, 9, 10, 11], // Flash, Strapping
  i2cDefault: { sda: 21, scl: 22 },
};

// ESP32-C3 (XIAO)
const ESP32_C3 = {
  available: [2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21],
  inputOnly: [],
  reserved: [11, 12, 13, 14, 15, 16, 17, 18, 19], // USB, Flash
  i2cDefault: { sda: 6, scl: 7 },
};
```

---

# Container 4: Dashboard - ActionBar & Filter

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| ActionBar.vue | `components/dashboard/ActionBar.vue` | Status-Pills, Filter, Quick-Actions |
| ComponentSidebar.vue | `components/dashboard/ComponentSidebar.vue` | Rechte Sidebar |
| CrossEspConnectionOverlay.vue | `components/dashboard/CrossEspConnectionOverlay.vue` | Logic-Verbindungslinien |
| logic.ts (Store) | `stores/logic.ts` | Automation-Rules State |
| logic.ts (API) | `api/logic.ts` | Logic REST-Client |

## Status-Counts

```typescript
// ActionBar zeigt:
interface DashboardStats {
  total_esps: number;
  online: number;
  offline: number;
  pending: number;      // Warten auf Genehmigung
  error: number;        // Phase 1: ESPs mit Sensor-Errors
  
  total_sensors: number;
  active_sensors: number;
  error_sensors: number; // Phase 1: Sensoren mit quality="error"
  
  total_actuators: number;
  active_actuators: number;
}
```

## Cross-ESP Logic Visualisierung

```typescript
// ConnectionOverlay zeichnet Linien zwischen:
// - Trigger-Sensor (ESP A, GPIO X) → Target-Actuator (ESP B, GPIO Y)

interface LogicRule {
  id: number;
  name: string;
  enabled: boolean;
  trigger: {
    esp_id: string;
    gpio: number;
    sensor_type: string;
    operator: ">" | "<" | "==" | ">=" | "<=";
    value: number;
  };
  action: {
    esp_id: string;
    gpio: number;
    command: "ON" | "OFF" | "PWM";
    value: number;
  };
}

// Linie wird gezeichnet von:
// Position(trigger.esp_id).sensor[trigger.gpio]
// zu:
// Position(action.esp_id).actuator[action.gpio]
```

---

# Container 5: System Monitor - Tab Ereignisse (Audit Log)

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| SystemMonitorView.vue | `views/SystemMonitorView.vue` | Haupt-View mit Tabs |
| EventsTab.vue | `components/system-monitor/EventsTab.vue` | Tab-Content |
| UnifiedEventList.vue | `components/system-monitor/UnifiedEventList.vue` | Virtual-Scroll Liste |
| EventDetailsPanel.vue | `components/system-monitor/EventDetailsPanel.vue` | Event-Details Sidebar |
| DataSourceSelector.vue | `components/system-monitor/DataSourceSelector.vue` | Quellen-Filter |
| audit.ts (API) | `api/audit.ts` | Audit REST-Client |

## REST API

| Aktion | Method | Endpoint | Query-Params |
|--------|--------|----------|--------------|
| Logs laden | GET | `/api/v1/audit/logs` | `limit, offset, event_type, esp_id, start_date, end_date, severity` |
| Log-Details | GET | `/api/v1/audit/logs/{id}` | - |
| Statistiken | GET | `/api/v1/audit/stats` | - |

## Event-Typen (WICHTIG für Phase 1)

```typescript
type AuditEventType = 
  // System
  | "system_startup"
  | "system_shutdown"
  
  // ESP Lifecycle
  | "esp_registered"
  | "esp_approved"
  | "esp_rejected"
  | "esp_online"
  | "esp_offline"
  
  // Sensor (inkl. Phase 1 Errors)
  | "sensor_created"
  | "sensor_updated"
  | "sensor_deleted"
  | "sensor_data"           // Einzelne Messung (optional)
  | "sensor_error"          // ⭐ Phase 1: -127°C, 85°C, etc.
  
  // Actuator
  | "actuator_created"
  | "actuator_command"
  | "actuator_status"
  | "actuator_error"
  | "emergency_stop"
  
  // Zone
  | "zone_created"
  | "zone_assigned"
  | "zone_removed"
  
  // Config
  | "config_sent"
  | "config_ack"
  | "config_error"
  
  // Logic
  | "rule_created"
  | "rule_triggered"
  | "rule_executed"
  | "rule_error";
```

## Audit-Log Schema

```typescript
interface AuditLog {
  id: number;
  timestamp: string;          // ISO 8601
  event_type: AuditEventType;
  esp_id?: string;
  gpio?: number;
  user_id?: number;
  severity: "info" | "warning" | "error" | "critical";
  details: Record<string, any>;
}

// Phase 1 Beispiel: sensor_error Event
{
  id: 12345,
  timestamp: "2026-01-29T10:30:00Z",
  event_type: "sensor_error",
  esp_id: "ESP_12AB34CD",
  gpio: 4,
  severity: "error",
  details: {
    error_code: 1060,
    error_message: "DS18B20 sensor fault (-127°C indicates disconnected or CRC failure)",
    sensor_type: "temp_ds18b20",
    raw_value: -2032,
    quality: "error"
  }
}
```

## WebSocket Live-Events

```typescript
// Neue Events werden via WebSocket gepusht:
interface AuditEventWS {
  type: "audit_event";
  data: AuditLog;
}

// Im Component:
ws.subscribe("audit_event", (event) => {
  events.value.unshift(event.data);  // Prepend to list
});
```

---

# Container 6: System Monitor - Tab Server Logs

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| ServerLogsTab.vue | `components/system-monitor/ServerLogsTab.vue` | Log-Viewer |
| LogManagementPanel.vue | `components/system-monitor/LogManagementPanel.vue` | Log-Verwaltung |
| logs.ts (API) | `api/logs.ts` | Log REST-Client |

## REST API

| Aktion | Method | Endpoint | Query-Params |
|--------|--------|----------|--------------|
| Logs laden | GET | `/api/v1/logs/server` | `level, limit, search` |
| Logs löschen | DELETE | `/api/v1/logs/server` | - |

## Log-Entry Schema

```typescript
interface LogEntry {
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  logger: string;           // "god_kaiser.mqtt.handlers.sensor_handler"
  message: string;
  request_id?: string;      // Für Request-Correlation
  extra?: Record<string, any>;
}

// Log-Level Farben:
const LOG_LEVEL_COLORS = {
  DEBUG: "text-gray-400",
  INFO: "text-blue-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-600 font-bold",
};
```

---

# Container 7: System Monitor - Tab Health

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| HealthTab.vue | `components/system-monitor/HealthTab.vue` | Fleet-Health |
| HealthProblemChip.vue | `components/system-monitor/HealthProblemChip.vue` | Problem-Badge |
| HealthSummaryBar.vue | `components/system-monitor/HealthSummaryBar.vue` | Zusammenfassung oben |
| health.ts (API) | `api/health.ts` | Health REST-Client |

## REST API

| Aktion | Method | Endpoint |
|--------|--------|----------|
| System-Health | GET | `/api/v1/health/` |
| ESP-Health | GET | `/api/v1/health/esp/{esp_id}` |
| Fleet-Overview | GET | `/api/v1/health/fleet` |

## Health-Response Schema

```typescript
interface SystemHealth {
  status: "healthy" | "degraded" | "unhealthy";
  components: {
    database: ComponentHealth;
    mqtt: ComponentHealth;
    websocket: ComponentHealth;
  };
  fleet: FleetHealth;
  metrics: SystemMetrics;
}

interface ComponentHealth {
  status: "healthy" | "degraded" | "unhealthy";
  latency_ms?: number;
  last_check: string;
  error?: string;
}

interface FleetHealth {
  total_esps: number;
  online: number;
  offline: number;
  pending: number;
  error: number;
}

interface SystemMetrics {
  sensor_readings_24h: number;
  actuator_commands_24h: number;
  errors_24h: number;
  avg_response_time_ms: number;
}
```

## ESP-Health Schema (inkl. Phase 1)

```typescript
interface ESPHealth {
  esp_id: string;
  name: string;
  status: "online" | "offline" | "error" | "warning";
  last_seen: string;
  uptime_seconds: number;
  
  // Hardware-Metriken
  heap_free: number;           // Bytes (Phase 1: <50KB = warning)
  wifi_rssi: number;           // dBm
  
  // Phase 1: Error-Tracking
  error_count_24h: number;
  last_error?: {
    code: number;
    message: string;
    timestamp: string;
  };
  
  // Sensor-Health
  sensors: SensorHealth[];
  
  // Actuator-Health
  actuators: ActuatorHealth[];
}

interface SensorHealth {
  gpio: number;
  sensor_type: string;
  name: string;
  last_reading: string;
  quality: SensorQuality;      // Phase 1: Kann "error" sein!
  error_count_24h: number;
  
  // Phase 1: Letzter Error
  last_error?: {
    code: number;              // 1060, 1061, etc.
    message: string;
    timestamp: string;
  };
}
```

## Heartbeat-Payload (ESP → Server)

```typescript
// ESP32 sendet alle 60 Sekunden:
interface HeartbeatPayload {
  ts: number;              // Unix-Timestamp
  uptime: number;          // Sekunden seit Boot
  heap_free: number;       // Freier Heap in Bytes
  wifi_rssi: number;       // WiFi-Signalstärke in dBm
  state: SystemState;      // "OPERATIONAL", "PENDING_APPROVAL", etc.
  error_count: number;     // Fehler seit letztem Heartbeat
  sensor_count: number;
  actuator_count: number;
}

type SystemState = 
  | "INITIALIZING"
  | "CONNECTING"
  | "PENDING_APPROVAL"
  | "OPERATIONAL"
  | "ERROR"
  | "MAINTENANCE"
  | "EMERGENCY_STOP";

// WiFi-Signalstärke interpretieren:
function getWifiQuality(rssi: number): { label: string; color: string } {
  if (rssi > -50) return { label: "Ausgezeichnet", color: "emerald" };
  if (rssi > -60) return { label: "Sehr gut", color: "green" };
  if (rssi > -70) return { label: "Gut", color: "lime" };
  if (rssi > -80) return { label: "Akzeptabel", color: "yellow" };
  return { label: "Schwach", color: "red" };
}
```

---

# Container 8: System Monitor - Tab MQTT Traffic

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| MqttTrafficTab.vue | `components/system-monitor/MqttTrafficTab.vue` | Live MQTT Viewer |

## WebSocket Events

```typescript
// Server broadcastet alle MQTT-Messages:
interface MQTTMessageEvent {
  type: "mqtt_message";
  data: {
    direction: "inbound" | "outbound";
    topic: string;
    payload: string;      // JSON-String
    timestamp: string;
    qos: 0 | 1 | 2;
  };
}
```

## Topic-Filter Patterns

```typescript
// Für Filter-UI:
const TOPIC_PATTERNS = {
  "Sensor-Daten": "kaiser/god/esp/+/sensor/+/data",
  "Heartbeats": "kaiser/god/esp/+/system/heartbeat",
  "Aktor-Status": "kaiser/god/esp/+/actuator/+/status",
  "Aktor-Commands": "kaiser/god/esp/+/actuator/+/command",
  "Config": "kaiser/god/esp/+/config",
  "Zone": "kaiser/god/esp/+/zone/+",
  "Errors": "kaiser/god/esp/+/system/error",
};

// Wildcard-Matching:
// + = ein Level (z.B. esp_id, gpio)
// # = mehrere Level (am Ende)
```

---

# Container 9: System Monitor - Tab Datenbank

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| DatabaseTab.vue | `components/system-monitor/DatabaseTab.vue` | DB-Explorer |
| DataTable.vue | `components/database/DataTable.vue` | Tabellen-Ansicht |
| TableSelector.vue | `components/database/TableSelector.vue` | Tabellen-Auswahl |
| FilterPanel.vue | `components/database/FilterPanel.vue` | Filter |
| database.ts (API) | `api/database.ts` | Database REST-Client |

## REST API

| Aktion | Method | Endpoint | Query-Params |
|--------|--------|----------|--------------|
| Tabellen | GET | `/api/v1/database/tables` | - |
| Tabellen-Daten | GET | `/api/v1/database/tables/{name}` | `limit, offset, order_by, filters` |
| Query ausführen | POST | `/api/v1/database/query` | - |

## Haupt-Tabellen

```typescript
const DATABASE_TABLES = [
  { name: "esp_devices", label: "ESP-Geräte", icon: "Cpu" },
  { name: "sensor_configs", label: "Sensor-Konfigurationen", icon: "Activity" },
  { name: "sensor_data", label: "Sensor-Messwerte", icon: "BarChart2" },
  { name: "actuator_configs", label: "Aktor-Konfigurationen", icon: "Settings" },
  { name: "actuator_states", label: "Aktor-Zustände", icon: "ToggleRight" },
  { name: "actuator_history", label: "Aktor-Historie", icon: "History" },
  { name: "cross_esp_logic", label: "Automatisierungsregeln", icon: "GitBranch" },
  { name: "audit_logs", label: "Audit-Logs", icon: "FileText" },
  { name: "users", label: "Benutzer", icon: "Users" },
  { name: "subzone_configs", label: "Subzonen", icon: "Layers" },
];
```

---

# Container 10: System Monitor - Cleanup/Retention

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| CleanupPanel.vue | `components/system-monitor/CleanupPanel.vue` | Cleanup-UI |
| CleanupPreview.vue | `components/system-monitor/CleanupPreview.vue` | Vorschau |
| AutoCleanupStatusBanner.vue | `components/system-monitor/AutoCleanupStatusBanner.vue` | Status |

## REST API

| Aktion | Method | Endpoint | Body |
|--------|--------|----------|------|
| Cleanup-Vorschau | GET | `/api/v1/audit/cleanup/preview` | - |
| Cleanup ausführen | POST | `/api/v1/audit/cleanup` | `{ retention_days, dry_run }` |
| Retention-Settings | GET | `/api/v1/audit/retention` | - |
| Retention-Settings | PUT | `/api/v1/audit/retention` | `{ retention_days, auto_cleanup }` |

## Cleanup-Response

```typescript
interface CleanupPreview {
  records_to_delete: number;
  oldest_record: string;      // ISO 8601
  newest_record: string;
  estimated_space_mb: number;
  retention_days: number;
}

interface CleanupResult {
  deleted_count: number;
  freed_space_mb: number;
  duration_ms: number;
  success: boolean;
  error?: string;
}
```

---

# Container 11: Toast-System

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| useToast.ts | `composables/useToast.ts` | Singleton Composable |
| ToastContainer.vue | `components/common/ToastContainer.vue` | Render-Komponente |

## API

```typescript
// useToast.ts - Singleton
import { useToast } from '@/composables/useToast';

const toast = useToast();

// Basis-Methoden
toast.success("ESP erfolgreich genehmigt");
toast.error("Sensor-Konfiguration fehlgeschlagen");
toast.warning("ESP offline seit 5 Minuten");
toast.info("Neue Firmware verfügbar");

// Mit Optionen
toast.error("Sensor-Fehler: -127°C erkannt", {
  duration: 10000,        // ms (Standard: 5000)
  dismissible: true,
  action: {
    label: "Details",
    onClick: () => router.push("/system-monitor?tab=events")
  }
});
```

## Automatische Toast-Trigger (Phase 1)

```typescript
// In espStore oder WebSocket-Handler:

// Error-Events
ws.subscribe("sensor_error", (event) => {
  const { error_code, esp_id, gpio, sensor_type } = event.data;
  const errorInfo = ERROR_MESSAGES[error_code];
  
  toast.error(`${sensor_type} auf ${esp_id} GPIO ${gpio}: ${errorInfo?.message}`);
});

ws.subscribe("esp_offline", (event) => {
  toast.warning(`ESP ${event.data.esp_id} ist offline`);
});

// Success-Events
ws.subscribe("esp_approved", (event) => {
  toast.success(`ESP ${event.data.esp_id} genehmigt`);
});

ws.subscribe("config_ack", (event) => {
  toast.success("Konfiguration übernommen");
});

// Info-Events
ws.subscribe("esp_discovered", (event) => {
  toast.info(`Neuer ESP gefunden: ${event.data.esp_id}`, {
    action: {
      label: "Genehmigen",
      onClick: () => approveESP(event.data.esp_id)
    }
  });
});
```

## Error-Code-Mapping (Phase 1)

```typescript
// Für benutzerfreundliche Toast-Messages:
const ERROR_MESSAGES: Record<number, { message: string; severity: ToastType }> = {
  // I2C
  1015: { message: "I2C-Bus hängt - Recovery wird versucht", severity: "warning" },
  1016: { message: "I2C-Bus Recovery gestartet", severity: "info" },
  1017: { message: "I2C-Bus Recovery fehlgeschlagen", severity: "error" },
  1018: { message: "I2C-Bus wiederhergestellt", severity: "success" },
  
  // DS18B20
  1060: { message: "Temperatursensor defekt oder nicht angeschlossen (-127°C)", severity: "error" },
  1061: { message: "Sensor initialisiert sich (85°C Power-On)", severity: "warning" },
  1062: { message: "Temperatur außerhalb gültigen Bereichs", severity: "warning" },
  1063: { message: "Sensor während Betrieb getrennt", severity: "error" },
};
```

---

# Container 12: WebSocket-Service

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| websocket.ts | `services/websocket.ts` | Singleton-Service |
| useWebSocket.ts | `composables/useWebSocket.ts` | Composable-Wrapper |
| websocket-events.ts | `types/websocket-events.ts` | Event-Type-Definitionen |

## Alle WebSocket Events

```typescript
type WebSocketEventType =
  // ESP
  | "esp_status"        // Online/Offline/Error
  | "esp_discovered"    // Neuer ESP wartet auf Genehmigung
  | "esp_approved"      // ESP wurde genehmigt
  | "esp_rejected"      // ESP wurde abgelehnt
  
  // Sensor
  | "sensor_data"       // Neue Sensor-Messung
  | "sensor_error"      // Phase 1: Sensor-Fehler
  
  // Actuator
  | "actuator_status"   // Aktor-Status-Update
  | "actuator_command"  // Command wurde gesendet
  | "actuator_error"    // Aktor-Fehler
  
  // Zone
  | "zone_assigned"     // ESP wurde Zone zugewiesen
  | "zone_removed"      // ESP wurde aus Zone entfernt
  
  // Config
  | "config_response"   // Config-ACK von ESP
  
  // System
  | "audit_event"       // Neuer Audit-Log-Eintrag
  | "mqtt_message"      // Live MQTT Traffic
  | "system_event"      // System-weite Events
  | "error"             // Allgemeine Fehler
  | "heartbeat";        // WebSocket-Heartbeat
```

## Verwendung

```typescript
// In Component:
import { useWebSocket } from '@/composables/useWebSocket';

const ws = useWebSocket();

// Subscribe mit Cleanup
const unsubscribe = ws.subscribe('sensor_data', (event) => {
  console.log('Sensor:', event.data.esp_id, event.data.value);
});

onUnmounted(() => {
  unsubscribe();
});

// Mehrere Events gleichzeitig
const unsubs = [
  ws.subscribe('esp_status', handleESPStatus),
  ws.subscribe('sensor_data', handleSensorData),
  ws.subscribe('sensor_error', handleSensorError),
];

onUnmounted(() => {
  unsubs.forEach(unsub => unsub());
});
```

## Connection-Management

```typescript
// services/websocket.ts
class WebSocketService {
  private static instance: WebSocketService;
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  
  static getInstance(): WebSocketService { ... }
  
  connect(): void {
    const token = authStore.accessToken;
    this.ws = new WebSocket(`ws://localhost:8000/api/v1/websocket?token=${token}`);
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };
    
    this.ws.onclose = () => {
      this.scheduleReconnect();
    };
  }
  
  disconnect(): void { ... }
  
  subscribe(type: string, callback: Function): () => void { ... }
}
```

---

# Container 13: Navigation & Layout

## Dateien

| Datei | Pfad | Funktion |
|-------|------|----------|
| MainLayout.vue | `components/layout/MainLayout.vue` | Haupt-Layout |
| AppHeader.vue | `components/layout/AppHeader.vue` | Top Header |
| AppSidebar.vue | `components/layout/AppSidebar.vue` | Seitenleiste |
| index.ts (Router) | `router/index.ts` | Vue Router |

## Routes

```typescript
const routes = [
  { path: "/", name: "Dashboard", component: DashboardView },
  { path: "/sensors", name: "Sensors", component: SensorsView },
  { path: "/logic", name: "Logic", component: LogicView },
  { path: "/system-monitor", name: "SystemMonitor", component: SystemMonitorView },
  { path: "/database", name: "Database", component: DatabaseExplorerView },
  { path: "/maintenance", name: "Maintenance", component: MaintenanceView },
  { path: "/system-config", name: "SystemConfig", component: SystemConfigView },
  { path: "/users", name: "Users", component: UserManagementView },
  { path: "/settings", name: "Settings", component: SettingsView },
  { path: "/login", name: "Login", component: LoginView, meta: { public: true } },
  { path: "/setup", name: "Setup", component: SetupView, meta: { public: true } },
];
```

---

# TEIL C: WICHTIGE KONSTANTEN

## ESP-ID Format

```typescript
// Regex: /^ESP_[A-Z0-9]{8}$/
// Beispiele: "ESP_12AB34CD", "ESP_00000001", "ESP_AABBCCDD"
```

## Timestamps

```typescript
// MQTT/Server: Unix-Sekunden (NICHT Millisekunden!)
// Frontend/API: ISO 8601 Strings

// Konvertierung:
const unixToISO = (ts: number) => new Date(ts * 1000).toISOString();
const isoToUnix = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);
```

## PWM-Werte

```typescript
// Drei verschiedene Darstellungen:
// Frontend UI:  0-100 (Prozent)
// REST API:     0.0-1.0 (Float)
// ESP32 intern: 0-255 (8-bit PWM)

// Frontend → API
const frontendToApi = (percent: number) => percent / 100;

// API → Frontend
const apiToFrontend = (value: number) => Math.round(value * 100);
```

## Kaiser-ID

```typescript
// Aktuell immer "god" (God-Kaiser Server)
// Zukunft: "kaiser_01", "kaiser_02" für Skalierung
const DEFAULT_KAISER_ID = "god";
```

---

# TEIL D: QUICK REFERENCE

## Was macht was?

| Ich will... | REST API | WebSocket Event |
|-------------|----------|-----------------|
| ESPs laden | `GET /esp/devices` | - |
| ESP-Status live | - | `esp_status` |
| Sensor-Werte live | - | `sensor_data` |
| Sensor hinzufügen | `POST /sensors/{esp}/{gpio}` | `config_response` |
| Aktor steuern | `POST /actuators/{esp}/{gpio}/command` | `actuator_status` |
| Zone zuweisen | `POST /zone/devices/{esp}/assign` | `zone_assigned` |
| Audit-Logs | `GET /audit/logs` | `audit_event` |
| Health-Status | `GET /health/fleet` | `esp_status` |

## Error-Handling

```typescript
// Phase 1: Alle Error-Codes
const ERROR_CODE_RANGES = {
  HARDWARE: { start: 1000, end: 1999 },
  SERVICE: { start: 2000, end: 2999 },
  COMMUNICATION: { start: 3000, end: 3999 },
  APPLICATION: { start: 4000, end: 4999 },
};

// Phase 1: Neue spezifische Codes
const PHASE1_ERROR_CODES = [1015, 1016, 1017, 1018, 1060, 1061, 1062, 1063];
```

---

**Ende des Dokuments**


