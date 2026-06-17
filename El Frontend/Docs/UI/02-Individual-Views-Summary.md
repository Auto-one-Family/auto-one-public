# Individual Views - Detailübersicht

**Erstellt:** 2025-12-19
**Letztes Update:** 2026-01-04 (Dashboard Konsolidierung Phase 7)
**Status:** ✅ Schnellereferenz für alle 18 Views (inkl. 5 Redirects)

---

## ⚠️ WICHTIG: Dashboard Konsolidierung (04.01.2026)

Dashboard ist jetzt die **zentrale ESP-Übersicht**. Legacy Views wurden deprecated:

| View | Alte Route | Neuer Redirect | Grund |
|------|------------|---------------|-------|
| `DevicesView.vue` | `/devices` | → `/` | Dashboard ist ESP-Übersicht |
| `DeviceDetailView.vue` | `/devices/:espId` | → `/?openSettings={espId}` | ESPSettingsPopover übernimmt |
| `ActuatorsView.vue` | `/actuators` | → `/sensors?tab=actuators` | SensorsView hat Tabs |

**SensorsView** wurde zu **Komponenten-View** mit Tab-System erweitert:
- `/sensors` → Sensoren-Tab (default)
- `/sensors?tab=actuators` → Aktoren-Tab

---

## Übersicht aller Views

### 🔴 KRITISCH - Detailliert dokumentiert

| View | Route | Status | Detaildoku | Backend-Dateien |
|------|-------|--------|-----------|-----------------|
| **DashboardView** | `/` | ✅ Impl. | ➜ `DASHBOARD_PLAN.md` | `El Servador/.../api/v1/esp.py`, `zones.py` |
| **SensorsView** | `/sensors` | ✅ Impl. | ➜ Kombinierte Sensoren+Aktoren mit Tabs | `El Servador/.../api/v1/sensors.py`, `actuators.py` |
| ~~DevicesView~~ | `/devices` | ⚠️ DEPRECATED | Redirect zu `/` | - |
| ~~DeviceDetailView~~ | `/devices/:espId` | ⚠️ DEPRECATED | Redirect zu `/?openSettings={espId}` | - |
| ~~ActuatorsView~~ | `/actuators` | ⚠️ DEPRECATED | Redirect zu `/sensors?tab=actuators` | - |
| MqttLogView | `/mqtt-log` | ✅ Impl. | ➜ siehe unten | `El Servador/.../api/v1/websocket/realtime.py` |
| LogicView | `/logic` | ⚠️ **Placeholder (53 LOC)** | ➜ siehe unten | `El Servador/.../api/v1/logic.py` |

---

## 02. DeviceDetailView - Detailanalyse (ehem. MockEspDetailView)

**Datei:** `src/views/DeviceDetailView.vue`  
**Route:** `/devices/:espId`  
**Status:** ✅ Vollständig implementiert  
**Auth:** ✅ Login erforderlich (nicht mehr Admin-only)

### Zweck

Detail-View für **einzelnes Mock-ESP-Gerät**. Zeigt:
- ESP-Status (OPERATIONAL, SAFE_MODE, ERROR)
- Sensor-Übersicht mit Wert-Bearbeitung
- Aktor-Steuerung
- Zone-Zuweisung
- System-Diagnostik (Uptime, Heap, WiFi-Signal)

### UI-Layout (ASCII)

```
┌──────────────────────────────────────────────────────────────┐
│ [← Zurück] ESP_MOCK_A1B2C3 [MOCK] [✓ OPERATIONAL]          │
│ Subtext: ESP32 Geräte-Details · Zone: gewächshaus           │
│                            [❤️ Heartbeat] [🛡️ Safe-Mode] [🔴 E-Stop]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Status Cards (2x2 Grid):                                     │
│ ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐           │
│ │Status   │ │Uptime  │ │Heap Frei │ │WiFi Sig. │           │
│ │OPER.    │ │2h 15m  │ │145 KB    │ │-65 dBm   │           │
│ └─────────┘ └────────┘ └──────────┘ └──────────┘           │
│                                                              │
│ Zone Assignment Panel (Card):                               │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ Zone: [gewächshaus] [Change Zone]                       ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ Sensors Section (Card):                                     │
│ ┌──────────────────────────────────────────────────────────┐│
│ │🌡️ Sensoren (5)       [🔄 Batch Update] [➕ Sensor hinz.]││
│ ├──────────────────────────────────────────────────────────┤│
│ │                                                          ││
│ │ Sensor Row 1:                                           ││
│ │ 📊 Temperatur (DS18B20, GPIO 34)                        ││
│ │ Value: 25.5 °C [good] [Bearbeiten] [🗑️]               ││
│ │                                                          ││
│ │ Sensor Row 2: [similar structure]                       ││
│ │ ...                                                      ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ Actuators Section (Card):                                   │
│ ┌──────────────────────────────────────────────────────────┐│
│ │⚡ Aktoren (3)           [Notfall aufheben*] [➕ Aktor h.] ││
│ ├──────────────────────────────────────────────────────────┤│
│ │                                                          ││
│ │ Actuator Row 1:                                         ││
│ │ 💡 Pumpe (Pump, GPIO 25)                               ││
│ │ [Ein] [Ausschalten]                                     ││
│ │                                                          ││
│ │ *nur wenn emergency_stopped === true                    ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ [Modal: Add Sensor] [Modal: Batch Update] [Modal: Add Aktor]│
└──────────────────────────────────────────────────────────────┘
```

### API-Endpoints

| Endpoint | Methode | Zweck |
|----------|---------|-------|
| `/debug/mock-esp` | GET | ESPs laden (onMounted) |
| `/debug/mock-esp/{espId}/sensor` | POST | Sensor hinzufügen |
| `/debug/mock-esp/{espId}/sensor/{gpio}` | PUT | Sensor-Wert aktualisieren |
| `/debug/mock-esp/{espId}/sensor/{gpio}` | DELETE | Sensor entfernen |
| `/debug/mock-esp/{espId}/sensors/batch` | PUT | Batch-Update aller Sensoren |
| `/debug/mock-esp/{espId}/actuator` | POST | Aktor hinzufügen |
| `/debug/mock-esp/{espId}/actuator/{gpio}` | PUT | Aktor-State toggen |
| `/debug/mock-esp/{espId}/heartbeat` | POST | Heartbeat auslösen |
| `/debug/mock-esp/{espId}/state` | PUT | System-State ändern (OPERATIONAL ↔ SAFE_MODE) |
| `/debug/mock-esp/{espId}/emergency-stop` | POST | Emergency-Stop auslösen |
| `/debug/mock-esp/{espId}/emergency-stop` | DELETE | Emergency-Stop aufheben |

### Komponenten

| Komponente | Zweck |
|------------|-------|
| `Badge` | Status-Badges (MOCK, REAL, OPERATIONAL, etc.) |
| `LoadingState` | Loading-Spinner |
| `EmptyState` | Keine Sensoren/Aktoren |
| `ZoneAssignmentPanel` | Zone-Zuweisung (Kind-Komponente) |

### User-Interaktionen

| Aktion | Element | Resultat |
|--------|---------|----------|
| **Mount** | (Auto) | ESPs laden wenn nicht vorhanden |
| **Klick [← Zurück]** | Button | Router.push('/mock-esp') |
| **Klick [❤️ Heartbeat]** | Button | `triggerHeartbeat()` → POST |
| **Klick [🛡️ Safe-Mode]** | Button | `toggleSafeMode()` → OPERATIONAL ↔ SAFE_MODE |
| **Klick [🔴 E-Stop]** | Button | `emergencyStop()` + Bestätigung |
| **Klick [➕ Sensor hinzufügen]** | Button | Modal öffnet sich |
| **Modal: Input GPIO, Type, Name, Value** | Form | `newSensor` Ref aktualisiert |
| **Modal: Klick [Hinzufügen]** | Button | `addSensor()` → POST |
| **Klick [Bearbeiten] auf Sensor** | Button | Edit-Mode aktiviert für Sensor |
| **Edit-Mode: Input Value, Quality, Publish** | Inputs | `editingSensor*` Refs aktualisiert |
| **Edit-Mode: Klick [Speichern]** | Button | `saveSensorValue()` → PUT |
| **Klick [🔄 Batch Update]** | Button | Batch-Modal öffnet sich mit allen Sensor-Werten |
| **Batch Modal: Input Values** | Inputs | `batchSensorValues` Objekt aktualisiert |
| **Batch Modal: Klick [Speichern]** | Button | `saveBatchSensorValues()` → PUT |
| **Klick [🗑️] auf Sensor** | Button | `removeSensor()` + Bestätigung → DELETE |
| **Toggle Aktor (Ein/Aus)** | Button | `toggleActuator()` → PUT |
| **Klick [Notfall aufheben]** | Button | `clearEmergency()` → DELETE |
| **Klick [➕ Aktor hinzufügen]** | Button | Modal öffnet sich |
| **Zone Panel: Klick [Change Zone]** | Button | Zone-Dialog (externe Komponente) |

### User kann vollständig einstellen:

#### ✅ **VOLLSTÄNDIG implementiert:**
- **ESP-System-State:** OPERATIONAL ↔ SAFE_MODE toggle mit Bestätigung
- **Heartbeat:** Manueller Trigger mit MQTT-Publish
- **Emergency-Stop:** Auslösen/Aufheben für gesamtes ESP
- **Zone-Zuweisung:** Zone ändern via ZoneAssignmentPanel
- **Sensor-Management:**
  - Sensor hinzufügen (GPIO, Type, Name, initialer Wert)
  - Einzelne Sensor-Werte bearbeiten (Value, Quality)
  - Sensor löschen mit Bestätigung
  - Batch-Update aller Sensor-Werte gleichzeitig
- **Aktor-Management:**
  - Aktor hinzufügen (GPIO, Type, Name, initialer State)
  - Aktor ein-/ausschalten
  - Emergency-Stop Status anzeigen

#### ❌ **KRITISCHE LÜCKEN - User kann NICHT einstellen:**
- **PWM-Kontrolle:** Aktoren haben nur ON/OFF - kein präziser 0.0-1.0 Slider
- **Sensor-Historie:** Keine Graphen oder historische Trends
- **Auto-Refresh:** Keine automatische Aktualisierung - nur manuelles Reload
- **Sensor-Simulation:** Keine Ramp/Sine-Wave/Noise Parameter für Mock-Sensoren
- **CSV-Export:** Keine Daten-Export Funktion
- **Sensor-Filter:** Keine Filter nach Zone/Subzone oder Wertbereich
- **Aktor-Gruppen:** Keine Möglichkeit, Aktoren zu gruppieren oder Sequenzen zu definieren

### Warum diese Lücken kritisch sind:

1. **PWM-Kontrolle:** Industrielle Aktoren brauchen präzise Kontrolle (z.B. Pumpe auf 75% Leistung)
2. **Historie:** User brauchen Kontext - "war der Sensor-Wert immer so?" oder "Trend-Analyse"
3. **Auto-Refresh:** Echtzeit-System sollte sich selbst aktualisieren
4. **Simulation:** Entwickler brauchen realistische Test-Szenarien
5. **Export:** Datenanalyse und Backup-Fehlerbehebung

### Priorität für Implementierung:

🟥 **KRITISCH - Sofort (User-Blockierer):**
- PWM-Slider für Aktoren (DeviceDetailView & ActuatorsView)

🟡 **HOCH - UX-Verbesserung:**
- Auto-Refresh konfigurieren (alle X Sekunden)
- Sensor-Historie/Graphen
- CSV-Export von Sensor-Daten

🟢 **MITTEL - Nice-to-have:**
- Advanced Sensor-Simulation (Ramp, Sine-Wave)
- Aktor-Gruppen und Sequenzen
- Zone/Subzone-Filter

---

## 03. MqttLogView - Detailanalyse

**Datei:** `src/views/MqttLogView.vue`
**Route:** `/mqtt-log`
**Status:** ✅ Vollständig implementiert
**Auth:** ✅ Beliebig (öffentlich lesbar)

### Zweck

**Real-time WebSocket Stream** von MQTT-Nachrichten. Zeigt:
- Live-Nachrichten-Stream (max 500 messages)
- **9 Message-Types:** sensor_data, actuator_status, actuator_response, actuator_alert, esp_health, config_response, zone_assignment, logic_execution, system_event
- Expandable Payload-Anzeige (JSON)
- Filter nach Type, ESP-ID, Topic
- Pause/Resume, Clear
- Auto-Reconnect (3s)

### WebSocket-Integration

```
┌─────────────────────────────────────────────────┐
│ Frontend (Vue Component)                         │
│ ┌───────────────────────────────────────────────┐│
│ │ onMounted: connect()                          ││
│ │ - Token refresh falls nötig                   ││
│ │ - WebSocket URL: ws://[API_HOST]/api/v1/...  ││
│ │ - Client-ID generieren                        ││
│ └───────────────────────────────────────────────┘│
│                                                 │
│ WebSocket Events:                               │
│ • onopen: Subscribe zu message-types            │
│ • onmessage: Nachrichten unshift() in array    │
│ • onclose: Auto-reconnect nach 3s              │
│ • onerror: Console-Fehler                      │
│                                                 │
│ onUnmounted: disconnect()                       │
└─────────────────────────────────────────────────┘
         ↕ WebSocket (Binär oder JSON)
┌─────────────────────────────────────────────────┐
│ Backend (God-Kaiser MQTT)                       │
│ - WebSocket Subscriber listening                │
│ - Messages an Frontend streamen                 │
└─────────────────────────────────────────────────┘
```

### UI-Layout

```
┌──────────────────────────────────────────────────────┐
│ MQTT Message Log                                     │
│ Real-time message stream from WebSocket              │
│                                [🟢 Connected] [⏸ Pause] [🔽 Filters] [🗑️ Clear]│
├──────────────────────────────────────────────────────┤
│ [Filters Panel - Collapsible]                        │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Message Types: [☑ sensor_data] [☑ actuator_status]│ │
│ │ ESP ID: [Input: ESP_12AB]                       │ │
│ │ Topic Contains: [Input: sensor]                 │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ Showing 47 of 500 messages (Paused)                 │
│                                                      │
│ Messages List (scrollable, max 600px height):       │
│ ┌──────────────────────────────────────────────────┐ │
│ │ [▶ 10:30:45] [sensor_data] ESP_12AB             │ │
│ │ kaiser/god/esp/12AB/sensor/34/data              │ │
│ │                                                  │ │
│ │ [▼ 10:30:42] [actuator_status] ESP_5678         │ │
│ │ kaiser/god/esp/5678/actuator/25/status          │ │
│ │ {                                                │ │
│ │   "gpio": 25,                                    │ │
│ │   "actuator_type": "pump",                       │ │
│ │   "state": true,                                 │ │
│ │   "timestamp": "2025-12-19T10:30:42Z"           │ │
│ │ }                                                │ │
│ │                                                  │ │
│ │ [▶ 10:30:41] [esp_health] ESP_5678             │ │
│ │ ...                                              │ │
│ └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Message-Types (9 Types - Server-definiert)

> **Stand:** 20.12.2025 - Verifiziert gegen Server-Handler

```json
{
  "sensor_data": {
    "esp_id": "ESP_12AB",
    "gpio": 34,
    "sensor_type": "DS18B20",
    "value": 25.5,
    "unit": "°C",
    "quality": "good",
    "timestamp": 1734690642
  },
  "actuator_status": {
    "esp_id": "ESP_5678",
    "gpio": 25,
    "actuator_type": "pump",
    "state": "on",
    "value": 0.8,
    "emergency": "normal",
    "timestamp": 1734690642
  },
  "actuator_response": {
    "esp_id": "ESP_5678",
    "gpio": 25,
    "command": "ON",
    "value": 1.0,
    "success": true,
    "message": "Command executed",
    "timestamp": 1734690642
  },
  "actuator_alert": {
    "esp_id": "ESP_5678",
    "gpio": 25,
    "alert_type": "emergency_stop",
    "severity": "critical",
    "message": "Manual emergency stop triggered",
    "zone_id": "greenhouse",
    "timestamp": 1734690642
  },
  "esp_health": {
    "esp_id": "ESP_12AB",
    "status": "online",
    "heap_free": 150000,
    "wifi_rssi": -65,
    "uptime": 3600,
    "sensor_count": 5,
    "actuator_count": 3,
    "timestamp": 1734690642
  },
  "config_response": {
    "esp_id": "ESP_12AB",
    "config_type": "sensor",
    "status": "success",
    "count": 3,
    "message": "Configured 3 sensor(s) successfully",
    "timestamp": 1734690642
  },
  "zone_assignment": {
    "esp_id": "ESP_12AB",
    "zone_id": "greenhouse",
    "status": "zone_assigned",
    "message": "Zone assigned successfully",
    "timestamp": 1734690642
  },
  "logic_execution": {
    "rule_id": "rule_123",
    "rule_name": "Temperature Control",
    "triggered_at": "2025-12-20T10:30:42Z",
    "conditions_met": true,
    "actions_executed": 2,
    "execution_time_ms": 15
  },
  "system_event": {
    "event_type": "ERROR",
    "message": "GPIO conflict on pin 25"
  }
}
```

### Features

✅ **Vollständig**:
- Real-time WebSocket-Streaming
- 500-Message Puffer
- Pause/Resume
- Filter nach Type, ESP-ID, Topic
- Expandable Payload-Anzeige (JSON)
- Auto-Reconnect (3s)
- Token-Refresh vor Connect
- Client-ID Generierung

❌ **Fehlt**:
- Persistent Storage (SessionStorage)
- Export (JSON, CSV)
- Search (Suche im Message-Puffer)
- Message-Timing Statistik
- Graph/Visualisierung von Sensor-Daten

---

## 04. LogicView - Placeholder Analysis

**Datei:** `src/views/LogicView.vue`
**Route:** `/logic`
**Status:** ⚠️ **PLACEHOLDER** - Nur Stub
**Auth:** ✅ Beliebig

### Aktueller Zustand

```vue
<script setup lang="ts">
import { GitBranch, Plus } from 'lucide-vue-next'

// Logic view is a placeholder for now - would connect to /v1/logic API
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-dark-100">Logic Rules</h1>
        <p class="text-dark-400 mt-1">Automation rules and conditions</p>
      </div>
      <button class="btn-primary">
        <Plus class="w-4 h-4 mr-2" />
        Create Rule
      </button>
    </div>

    <!-- Placeholder card -->
    <div class="card p-12 text-center">
      <GitBranch class="w-12 h-12 text-dark-600 mx-auto mb-4" />
      <h3 class="text-lg font-medium text-dark-200 mb-2">Logic Engine</h3>
      <p class="text-dark-400 mb-4">
        Create automation rules to control actuators based on sensor readings and schedules.
      </p>
      <p class="text-sm text-dark-500">
        Connect to the server's Logic API at <code class="text-blue-400">/v1/logic</code>
      </p>
    </div>

    <!-- Example Rule Card (static) -->
    <div class="card">
      <div class="card-header">
        <div>
          <p class="font-medium text-dark-100">Example: Temperature Control</p>
          <p class="text-xs text-dark-400">When temperature > 30°C, turn on fan</p>
        </div>
        <span class="badge badge-gray">Template</span>
      </div>
      <div class="card-body">
        <p><strong class="text-dark-200">Condition:</strong> sensor.temperature > 30</p>
        <p><strong class="text-dark-200">Action:</strong> actuator.fan = ON</p>
        <p><strong class="text-dark-200">Cooldown:</strong> 60 seconds</p>
      </div>
    </div>
  </div>
</template>
```

### Geplante Implementierung

**Backend-API** (noch nicht implementiert):
```
GET    /api/v1/logic/rules              # Alle Rules auflisten
POST   /api/v1/logic/rules              # Neue Rule erstellen
GET    /api/v1/logic/rules/:ruleId      # Single Rule abrufen
PUT    /api/v1/logic/rules/:ruleId      # Rule aktualisieren
DELETE /api/v1/logic/rules/:ruleId      # Rule löschen
POST   /api/v1/logic/rules/:ruleId/test # Rule testen
```

**Frontend Components** (noch nicht erstellt):
- `RuleBuilder.vue` - Visual Editor für Conditions/Actions
- `ConditionPanel.vue` - Sensor-Bedingungen definieren
- `ActionPanel.vue` - Aktor-Aktionen definieren
- `RuleList.vue` - Übersicht aller Rules

**Datenstruktur**:
```json
{
  "rule_id": "rule_001",
  "name": "Temperature Control",
  "enabled": true,
  "conditions": [
    {
      "type": "sensor_threshold",
      "esp_id": "ESP_12AB",
      "sensor_gpio": 34,
      "operator": ">",
      "value": 30
    }
  ],
  "actions": [
    {
      "type": "actuator_set",
      "esp_id": "ESP_5678",
      "actuator_gpio": 25,
      "value": true
    }
  ],
  "cooldown_seconds": 60,
  "created_at": "2025-12-19T10:00:00Z"
}
```

### Priorität

🔴 **HIGH** - Logic Engine ist Kern-Feature für Automation

---

## 05. Weitere Views (Kompakt-Übersicht)

### DashboardView - KRITISCHE LÜCKE!

**Datei:** `src/views/DashboardView.vue`
**Route:** `/`
**Status:** ✅ Implementiert, aber **KEINE EINSTELLUNGEN!**

#### Was der User sieht:
- System-Status-Karten (ESP-Count, Sensor-Count, etc.)
- Kritische Alerts und Warnings
- Statische Übersicht ohne Interaktion

#### User kann einstellen:
❌ **NICHTS!** - Dashboard ist reine Anzeige

#### KRITISCHE LÜCKE:
**Dashboard hat NULL Einstellungen!** Das ist das Erste was User sehen - und sie können nichts anpassen:
- ❌ Keine Dashboard-Widgets konfigurieren (Layout ändern)
- ❌ Keine KPIs auswählen (welche Metriken anzeigen?)
- ❌ Keine Zeitbereiche filtern
- ❌ Keine Alert-Konfiguration (was ist kritisch?)
- ❌ Keine personalisierten Dashboards speichern

#### Warum das kritisch ist:
- **Erste User-Experience:** User kommen auf Dashboard - müssen es sofort anpassen können
- **Verschiedene Rollen:** Admin sieht andere KPIs als Operator
- **Skalierung:** Bei 100 ESPs braucht User fokussierte Dashboards
- **Personalisierung:** Jeder User hat andere Prioritäten

**Status:** 🟥 **KRITISCH - SOFORT beheben!**

---

| View | Route | Auth | Status | Kurzbeschreibung |
|------|-------|------|--------|------------------|
| **DashboardView** | `/` | ✅ | ✅ Impl. | System-Übersicht: Stats, Devices, Warnings |
| **SensorsView** | `/sensors` | ⚠️ | ✅ Impl. | **KRITISCH:** Nur Mock-ESPs! Echte ESPs fehlen komplett - FEHLT: Zone-Filter, Historie, Bulk-Updates |
| **ActuatorsView** | `/actuators` | ⚠️ | ✅ Impl. | **KRITISCH:** Nur Mock-ESPs! Echte ESPs fehlen komplett - FEHLT: PWM-Kontrolle, Bulk-Operationen, Gruppen |
| **DatabaseExplorerView** | `/database` | ✅ Admin | ✅ Impl. | Dynamic DB-Table Browser mit DataTable |
| **LogViewerView** | `/logs` | ✅ Admin | ✅ Impl. | Server-Logs streamen (SSH-ähnlich) |
| **UserManagementView** | `/users` | ✅ Admin | ✅ Impl. | User CRUD (Create, Read, Update, Delete) |
| **LoadTestView** | `/load-test` | ✅ Admin | ✅ Impl. | Lasttest-Runner (Mock-ESPs/Sensoren) |
| **SystemConfigView** | `/system-config` | ✅ Admin | ✅ Impl. | System-Konfiguration editieren |
| **AuditLogView** | `/audit` | ✅ | ✅ Impl. | Audit-Log mit Filterung und Stats |
| **SettingsView** | `/settings` | ✅ | ✅ Impl. | User-spezifische Einstellungen |

---

## 6. API-Zusammenfassung

### Auth-Endpoints
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/setup` - Initial-Setup (Admin-Konto erstellen)
- `POST /api/v1/auth/refresh` - Token-Refresh

### Debug-Endpoints (Admin-only) - Präfix: `/api/v1/debug`

**Mock-ESP CRUD:**
- `GET /v1/debug/mock-esp` - Liste aller Mock-ESPs
- `POST /v1/debug/mock-esp` - Mock-ESP erstellen
- `GET /v1/debug/mock-esp/{esp_id}` - Einzelnes ESP abrufen
- `DELETE /v1/debug/mock-esp/{esp_id}` - ESP löschen

**Heartbeat & State:**
- `POST /v1/debug/mock-esp/{esp_id}/heartbeat` - Heartbeat triggern
- `POST /v1/debug/mock-esp/{esp_id}/state` - System-State setzen (OPERATIONAL, SAFE_MODE, etc.)
- `POST /v1/debug/mock-esp/{esp_id}/auto-heartbeat` - Auto-Heartbeat konfigurieren

**Sensor Operations:**
- `POST /v1/debug/mock-esp/{esp_id}/sensors` - Sensor hinzufügen
- `POST /v1/debug/mock-esp/{esp_id}/sensors/{gpio}` - Sensor-Wert setzen
- `POST /v1/debug/mock-esp/{esp_id}/sensors/batch` - Batch-Update
- `DELETE /v1/debug/mock-esp/{esp_id}/sensors/{gpio}` - Sensor entfernen

**Actuator Operations:**
- `POST /v1/debug/mock-esp/{esp_id}/actuators` - Aktor hinzufügen
- `POST /v1/debug/mock-esp/{esp_id}/actuators/{gpio}` - Aktor-State setzen

**Emergency Stop:**
- `POST /v1/debug/mock-esp/{esp_id}/emergency-stop` - Emergency-Stop auslösen
- `POST /v1/debug/mock-esp/{esp_id}/clear-emergency` - Emergency aufheben

**Message History:**
- `GET /v1/debug/mock-esp/{esp_id}/messages` - Publizierte Nachrichten abrufen
- `DELETE /v1/debug/mock-esp/{esp_id}/messages` - Nachrichtenverlauf löschen

**Database Explorer:**
- `GET /v1/debug/db/tables` - Tabellen-Liste mit Schema
- `GET /v1/debug/db/{table_name}/schema` - Tabellen-Schema
- `GET /v1/debug/db/{table_name}` - Tabellen-Daten (mit Pagination/Filter)
- `GET /v1/debug/db/{table_name}/{record_id}` - Einzelner Record

**Log Viewer:**
- `GET /v1/debug/logs/files` - Log-Dateien auflisten
- `GET /v1/debug/logs` - Logs abfragen (mit Filter)

**System Config:**
- `GET /v1/debug/config` - Config-Einträge auflisten
- `PATCH /v1/debug/config/{config_key}` - Config-Wert aktualisieren

**Load Testing:**
- `POST /v1/debug/load-test/bulk-create` - Bulk-ESP-Erstellung
- `POST /v1/debug/load-test/simulate` - Simulation starten
- `POST /v1/debug/load-test/stop` - Simulation stoppen
- `GET /v1/debug/load-test/metrics` - Metriken abrufen

### WebSocket
- `ws://[API_HOST]/api/v1/ws/realtime/{clientId}?token={token}` - Real-time Messages

---

## 7. Next Steps

**Für Implementierung:**
1. ✅ MockEspView - Basis Mock-Management
2. ✅ MockEspDetailView - Detail-Konfiguration
3. ✅ MqttLogView - Debug-Fenster
4. ⏳ LogicView - Automation Rules
5. ⏳ SensorSimulation - Advanced (ramping, sine-wave, etc.)
6. ⏳ PerformanceOptimization - Pagination, Lazy-Loading

---

## 8. Server-Zusammenhänge (Backend-Referenz)

Diese Sektion erklärt, welche Server-Dateien für welche Frontend-Funktionalität zuständig sind.

### 8.1 Dateipfad-Basis
```
Backend-Basis: El Servador/god_kaiser_server/src/
```

### 8.2 API-Router → Service → Repository Pattern

| Komponente | Pfad | Beschreibung |
|------------|------|--------------|
| **API-Router** | `api/v1/*.py` | FastAPI-Endpoints, Request-Validierung |
| **Services** | `services/*.py` | Business-Logik, Orchestrierung |
| **Repositories** | `db/repositories/*.py` | Datenbank-Operationen (SQLAlchemy) |
| **Models** | `db/models/*.py` | Datenbank-Modelle (ORM) |
| **Schemas** | `schemas/*.py` | Pydantic-Schemas für Request/Response |

### 8.3 View → Server-Datei Mapping

#### DevicesView / DeviceDetailView (Unified ESP-Views)

> ⚠️ **Refactored:** Ehemals MockEspView/MockEspDetailView. Jetzt Unified für Mock+Real.

```
Frontend:
  - src/views/DevicesView.vue        # Unified Liste (Mock+Real)
  - src/views/DeviceDetailView.vue   # Unified Details (Mock+Real)
  - src/stores/esp.ts                # Unified Store (ersetzt mockEsp.ts)
  - src/api/esp.ts                   # Unified API Client
  - src/api/debug.ts                 # Mock-spezifische Debug-Endpoints

Komponenten (fertig, NICHT integriert):
  - src/components/esp/SensorSatellite.vue     # ✅ 271 LOC
  - src/components/esp/ActuatorSatellite.vue   # ✅ 289 LOC
  - src/components/esp/ConnectionLines.vue     # ✅ 268 LOC

Backend:
  - api/v1/debug.py              # Mock-ESP-Endpoints
  - api/v1/esp.py                # Real-ESP-Endpoints
  - services/mock_esp_manager.py # Mock-ESP-Logik, Heartbeat, Sensor-Werte
  - services/esp_service.py      # Real-ESP-Logik
  - schemas/debug.py             # Request/Response Schemas
  - mqtt/publisher.py            # MQTT-Nachrichtenpublizierung
```#### MqttLogView
```
Frontend:
  - src/views/MqttLogView.vue
  - (WebSocket direkt im View)

Backend:
  - api/v1/websocket/realtime.py  # WebSocket-Endpoint
  - websocket/manager.py          # Connection-Management
  - mqtt/handlers/*.py            # MQTT Message-Handler (subscribe/forward)
```#### DatabaseExplorerView
```
Frontend:
  - src/views/DatabaseExplorerView.vue
  - src/stores/database.ts
  - src/api/database.ts

Backend:
  - api/v1/debug.py               # DB-Explorer-Endpoints
  - schemas/debug_db.py           # Schema-Definitionen, Allowed-Tables
  - db/session.py                 # Async DB-Session
```

#### LogViewerView
```
Frontend:
  - src/views/LogViewerView.vue
  - src/api/logs.ts

Backend:
  - api/v1/debug.py               # Log-Viewer-Endpoints
  - core/logging_config.py        # Logging-Konfiguration
  - config/logging.yaml           # Log-Datei-Pfade
```#### UserManagementView
```
Frontend:
  - src/views/UserManagementView.vue
  - src/api/users.ts

Backend:
  - api/v1/users.py               # User-CRUD-Endpoints
  - db/repositories/user_repo.py  # User-Datenbank-Operationen
  - db/models/user.py             # User-Model
  - core/security.py              # Password-Hashing, JWT
```

#### AuditLogView
```
Frontend:
  - src/views/AuditLogView.vue
  - src/api/audit.ts

Backend:
  - api/v1/audit.py               # Audit-Endpoints
  - services/audit_retention_service.py  # Cleanup-Service
  - db/repositories/audit_repo.py        # Audit-DB-Operationen
  - db/models/audit_log.py               # Audit-Model
```

#### ActuatorsView - Aggregierte Aktor-Steuerung

**Datei:** `src/views/ActuatorsView.vue`
**Route:** `/actuators`
**Status:** ✅ Implementiert, aber **KRITISCHE LÜCKEN**

### Was der User sieht:
- Alle Aktoren aus allen ESPs in tabellarischer Übersicht
- Live-Status via WebSocket (actuator_status Events)
- Emergency-Stop Status pro Aktor### User kann einstellen:
✅ **VOLLSTÄNDIG:**
- Aktor ein-/ausschalten (ON/OFF Toggle)
- Emergency-Stop Status sehen

❌ **KRITISCHE LÜCKEN:**
- **KEINE PWM-Kontrolle!** Nur ON/OFF - kein 0.0-1.0 Slider
- Keine Bulk-Operationen (mehrere Aktoren gleichzeitig steuern)
- Keine Aktor-Gruppen oder Sequenzen
- Keine Filter nach Zone/Subzone
- Keine Timing/Timeout-Konfiguration

### Warum PWM-Kontrolle kritisch ist:
- Industrielle Aktoren brauchen präzise Kontrolle
- Beispiel: Pumpe auf 75% statt volle Leistung
- Beispiel: Ventil 30% öffnen statt ganz auf
- Beispiel: LED-Helligkeit dimmen**Status:** 🟥 **BLOCKIERT USER** - PWM-Kontrolle fehlt komplett!

---

#### LoadTestView
```
Frontend:
  - src/views/LoadTestView.vue
  - src/api/loadtest.ts

Backend:
  - api/v1/debug.py               # Load-Test-Endpoints (bulk-create, simulate, etc.)
  - services/mock_esp_manager.py  # Bulk-ESP-Erstellung
```

#### SystemConfigView
```
Frontend:
  - src/views/SystemConfigView.vue
  - src/api/config.ts

Backend:
  - api/v1/debug.py               # Config-Endpoints
  - db/models/system_config.py    # Config-Model (falls vorhanden)
```

#### LogicView (Placeholder)
```
Frontend:
  - src/views/LogicView.vue       # Nur Placeholder-UI

Backend:
  - api/v1/logic.py               # Logic-Engine-Endpoints
  - services/logic_service.py     # Rule-Management
  - services/logic_engine.py      # Rule-Execution
  - services/logic_scheduler.py   # Scheduled Rule-Execution
  - services/logic/actions/*.py   # Action-Implementierungen
  - services/logic/conditions/*.py # Condition-Implementierungen
  - db/repositories/logic_repo.py # Logic-DB-Operationen
```

---

## 🔍 **KRITISCHE CODEBASE-ANALYSE: ESP-Typ-Unterscheidung**

Basierend auf Hierarchie.md **FEHLT** die Unterscheidung zwischen echten ESPs und Mock-ESPs in der UI kritisch!

### 📊 **ESP-Typ-Matrix (aus Hierarchie.md)**

| ESP-Typ | Hardware | Datenbank | UI-Badge | API-Prefix | Store-Nutzung | Status |
|---------|----------|-----------|----------|------------|---------------|--------|
| **Echte ESPs** | ESP32 WROOM/XIAO C3 | `hardware_type: null/ESP32` | 🟢 **REAL** | `/api/v1/esp/*` | `useEspStore` ✅ | ✅ DevicesView, DeviceDetailView |
| **Mock-ESPs** | Software-Simulation | `hardware_type: "MOCK_ESP32"` | 🔵 **MOCK** | `/api/v1/debug/mock-esp/*` | `useEspStore` ✅ + `useMockEspStore` ⚠️ | ⚠️ SensorsView, ActuatorsView (nur Mock) |

### 🟥 **KRITISCHE STORE-INKONSISTENZ**

**Problem:** Zwei Stores führen zu inkonsistenten Views!

#### `useEspStore` (esp.ts) - **REKOMMANDIERT**
- ✅ Unterstützt beide ESP-Typen
- ✅ Unified API-Calls
- ✅ Verwendet von: DevicesView, DeviceDetailView, DashboardView

#### `useMockEspStore` (mockEsp.ts) - **LEGACY-PROBLEM**
- ⚠️ Unterstützt NUR Mock-ESPs
- ⚠️ Verwendet von: SensorsView, ActuatorsView
- ❌ Blockiert echte ESP Integration

### 📋 **Betroffene Views - Migrations-Status**#### **SensorsView - KRITISCHE LÜCKE**
- **Aktuell:** Nutzt `useMockEspStore` → Zeigt NUR Mock-ESPs
- **Fehlt:** Echte ESP Sensoren komplett
- **Benötigt:** Migration zu `useEspStore`, ESP-Typ-Badges#### **ActuatorsView - KRITISCHE LÜCKE**
- **Aktuell:** Nutzt `useMockEspStore` → Zeigt NUR Mock-ESPs
- **Fehlt:** Echte ESP Aktoren komplett
- **Benötigt:** Migration zu `useEspStore`, PWM-Kontrolle

#### **DeviceDetailView - ✅ TEILWEISE KORREKT**
- **Aktuell:** Nutzt `useEspStore` ✅ → Zeigt beide Typen
- **Problem:** API-Routing unterschiedlich je nach Typ
- **Benötigt:** Unified API-Endpoints

### 🔧 **Sofort-Handlungsempfehlungen**

1. **SensorsView & ActuatorsView migrieren** zu `useEspStore`
2. **ESP-Typ-Badges implementieren** (🟢 REAL, 🔵 MOCK)
3. **Unified API-Endpoints** für beide ESP-Typen
4. **PWM-Kontrolle erweitern** auf echte ESPs### 📈 **Business Impact**

**Ohne Behebung:** User können echte ESPs nicht in Aggregations-Views sehen
**Mit Behebung:** Vollständige ESP-Übersicht, konsistente UX

**Status:** 🟥 **KRITISCH - Verhindert unified ESP-Management in Production!**

#### Auth (LoginView, SetupView)
```
Frontend:
  - src/views/LoginView.vue
  - src/views/SetupView.vue
  - src/stores/auth.ts
  - src/api/auth.ts

Backend:
  - api/v1/auth.py                # Login, Setup, Refresh-Endpoints
  - core/security.py              # JWT-Token-Generierung, Password-Hashing
  - db/repositories/user_repo.py  # User-Abfragen
  - db/models/token_blacklist.py  # Token-Invalidierung
```### 8.4 MQTT-Integration

```
Pfad: El Servador/god_kaiser_server/src/mqtt/

├── client.py          # MQTT-Client-Singleton
├── publisher.py       # Publish-Funktionen
├── subscriber.py      # Subscribe-Funktionen
├── topics.py          # Topic-Patterns (kaiser/god/esp/+/...)
└── handlers/          # Message-Handler
    ├── sensor_handler.py      # Sensor-Daten verarbeiten
    ├── actuator_handler.py    # Aktor-Commands verarbeiten
    ├── heartbeat_handler.py   # Heartbeat verarbeiten
    └── ...
```

**Topic-Pattern:**
```
kaiser/god/esp/{esp_id}/sensor/{gpio}/data    # Sensor-Daten
kaiser/god/esp/{esp_id}/actuator/{gpio}/cmd   # Aktor-Commands
kaiser/god/esp/{esp_id}/system/heartbeat      # Heartbeat
kaiser/god/esp/{esp_id}/system/state          # State-Changes
```

### 8.5 Datenbank-Modelle

```
Pfad: El Servador/god_kaiser_server/src/db/models/├── user.py           # User, Roles
├── esp_device.py     # ESP-Geräte (echte)
├── sensor.py         # Sensor-Definitionen
├── actuator.py       # Aktor-Definitionen
├── sensor_data.py    # Sensor-Messwerte (Timeseries)
├── actuator_state.py # Aktor-Status-Historie
├── zone.py           # Zonen
├── subzone.py        # Subzonen
├── logic_rule.py     # Logic-Rules
├── audit_log.py      # Audit-Log
└── ...
```

### 8.6 Wichtige Konfigurationsdateien

| Datei | Zweck |
|-------|-------|
| `core/config.py` | Haupt-Settings (aus ENV/YAML) |
| `config/logging.yaml` | Logging-Konfiguration |
| `alembic/` | Datenbank-Migrationen |
| `pyproject.toml` | Python-Dependencies (Poetry) |