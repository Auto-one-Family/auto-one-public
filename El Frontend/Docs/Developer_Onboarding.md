# AutomationOne Frontend - Entwickler-Einweisung

> **Zielgruppe:** Neue Entwickler, die am Frontend/Debug-Tool arbeiten
> **Voraussetzung:** Grundkenntnisse in Vue 3, TypeScript, Python/FastAPI
> **Letzte Aktualisierung:** Dezember 2025

---

## 0. Schnelleinstieg - Wo finde ich was?

### Dokumentations-Hierarchie

```
Auto-one/                           # Projekt-Root
├── .claude/
│   ├── CLAUDE.md                   # ⭐ HAUPTEINSTIEG - ESP32 + Systemübersicht
│   ├── CLAUDE_SERVER.md            # Server-spezifische Dokumentation
│   └── CLAUDE_FRONTEND.md          # Frontend-spezifische Dokumentation
├── Hierarchie.md                   # System-Architektur, alle Models, Flows
├── El Frontend/
│   └── Docs/
│       ├── DEBUG_ARCHITECTURE.md   # Debug-Tool Architektur + Startup-Anleitung
│       ├── APIs.md                 # Alle REST-Endpoints
│       ├── Bugs_Found.md           # Bekannte Bugs + Lösungen
│       ├── Admin_oder_user_erstellen...md  # Auth-Flow Dokumentation
│       └── Developer_Onboarding.md # ⭐ DIESES DOKUMENT
├── El Servador/                    # Backend (FastAPI)
└── El Trabajante/                  # ESP32 Firmware
```

### Quick Reference - Was suche ich?

| Aufgabe | Primäre Quelle | Code-Location |
|---------|----------------|---------------|
| **System starten** | `El Frontend/Docs/DEBUG_ARCHITECTURE.md` Section 0 | - |
| **Frontend-Komponente bauen** | Diese Datei + bestehende Views als Pattern | `El Frontend/src/views/` |
| **API-Endpoint verstehen** | `El Frontend/Docs/APIs.md` | `El Frontend/src/api/` |
| **Backend-Endpoint bauen** | `.claude/CLAUDE_SERVER.md` | `El Servador/.../src/api/v1/` |
| **Datenbank-Models** | `Hierarchie.md` Section 2.1 | `El Servador/.../src/db/models/` |
| **Auth-Flow verstehen** | `El Frontend/Docs/Admin_oder_user...md` | `El Frontend/src/stores/auth.ts` |
| **MQTT-Protokoll** | `El Trabajante/docs/Mqtt_Protocoll.md` | - |
| **Mock ESP Zone-Sync verstehen** | Section 8 | Server + Frontend Code |

---

## 1. System-Architektur Überblick

### 1.1 Die 4-Layer-Hierarchie

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: God (KI/Analytics) - OPTIONAL, nicht implementiert            │
└─────────────────────────────────────────────────────────────────────────┘
                            ↕ HTTP REST (geplant)
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: God-Kaiser Server (Raspberry Pi 5)                             │
│                                                                         │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│ │   FastAPI    │  │     MQTT     │  │  PostgreSQL/ │  │   Frontend  │  │
│ │   REST API   │  │    Broker    │  │    SQLite    │  │  (Vue 3)    │  │
│ └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │
│                                                                         │
│ Code: El Servador/god_kaiser_server/src/                                │
│ Doku: .claude/CLAUDE_SERVER.md                                          │
└─────────────────────────────────────────────────────────────────────────┘
                            ↕ MQTT (TLS, Port 8883)
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: Kaiser-Nodes (Pi Zero) - OPTIONAL, nicht implementiert         │
└─────────────────────────────────────────────────────────────────────────┘
                            ↕ MQTT
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 4: ESP32-Agenten ("El Trabajante")                                │
│                                                                         │
│ Rolle: Sensor-Auslesung, Aktor-Steuerung, RAW-Daten senden              │
│ Code: El Trabajante/src/                                                │
│ Doku: .claude/CLAUDE.md                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Kern-Prinzip: Server-Centric

**WICHTIG:** Das System ist server-zentrisch. ESP32-Geräte sind "dumm" - sie senden nur RAW-Daten.

```
ESP32 sendet:     analogRead(GPIO) = 2847        (RAW ADC-Wert)
Server empfängt:  MQTT: kaiser/god/esp/ESP_001/sensor/4/data
Server verarbeitet: Python pH-Library → 6.8 pH
Server speichert: sensor_data Tabelle (raw_value=2847, processed_value=6.8)
Server sendet zurück: Optional processed-Wert an ESP
```

### 1.3 Mock-ESP ↔ Echte ESP Koexistenz

**Kritisch zu verstehen:** Mock-ESPs durchlaufen die **identische Pipeline** wie echte ESPs:

```
Mock-ESP  → MockESPManager → MQTT Client → Handlers → Logic Engine → Database
Real-ESP  → MQTT Broker    → MQTT Client → Handlers → Logic Engine → Database
```

**Kennzeichnung:** Mock-ESPs haben `hardware_type = "MOCK_ESP32"` (nicht "ESP32-WROOM-32").

**Code-Referenz:** `El Servador/god_kaiser_server/src/services/mock_esp_manager.py`

---

## 2. Frontend-Architektur

### 2.1 Technologie-Stack

| Technologie | Version | Zweck |
|-------------|---------|-------|
| Vue 3 | 3.x | UI Framework (Composition API) |
| TypeScript | 5.x | Type Safety |
| Pinia | 2.x | State Management |
| Vue Router | 4.x | Routing |
| Tailwind CSS | 3.x | Styling (Dark Theme) |
| Axios | 1.x | HTTP Client |
| Vite | 5.x | Build Tool |

### 2.2 Verzeichnisstruktur

```
El Frontend/src/
├── api/                    # REST API Layer
│   ├── index.ts            # Axios-Instanz, Interceptors
│   ├── auth.ts             # Auth-Endpoints
│   ├── debug.ts            # Mock-ESP Debug-Endpoints
│   ├── database.ts         # Database Explorer API
│   ├── logs.ts             # Log Viewer API
│   ├── users.ts            # User Management API
│   ├── config.ts           # System Config API
│   └── loadtest.ts         # Load Testing API
│
├── stores/                 # Pinia Stores
│   ├── auth.ts             # Auth State (User, Tokens)
│   ├── mockEsp.ts          # Mock-ESP State
│   └── database.ts         # Database Explorer State
│
├── views/                  # Seiten-Komponenten
│   ├── LoginView.vue       # Login-Seite
│   ├── SetupView.vue       # First-Run Admin-Setup
│   ├── DashboardView.vue   # Haupt-Dashboard
│   ├── MockEspView.vue     # Mock-ESP Übersicht
│   ├── MockEspDetailView.vue # Mock-ESP Details
│   ├── MqttLogView.vue     # MQTT Live-Log
│   ├── SensorsView.vue     # Sensor-Übersicht
│   ├── ActuatorsView.vue   # Actuator-Übersicht
│   ├── LogicView.vue       # Automation Rules
│   ├── DatabaseExplorerView.vue  # ⭐ NEU: DB Explorer
│   ├── LogViewerView.vue   # ⭐ NEU: Server Logs
│   ├── UserManagementView.vue    # ⭐ NEU: User CRUD
│   ├── SystemConfigView.vue      # ⭐ NEU: Config Editor
│   └── LoadTestView.vue    # ⭐ NEU: Load Testing
│
├── components/             # Wiederverwendbare Komponenten
│   ├── database/           # Database Explorer Komponenten
│   │   ├── TableSelector.vue
│   │   ├── SchemaInfoPanel.vue
│   │   ├── FilterPanel.vue
│   │   ├── DataTable.vue
│   │   ├── Pagination.vue
│   │   └── RecordDetailModal.vue
│   └── ...
│
├── router/
│   └── index.ts            # Route-Definitionen + Guards
│
├── types/
│   └── index.ts            # TypeScript Interfaces
│
└── style.css               # Tailwind Config + Custom Styles
```

### 2.3 Routing-Struktur

| Route | View | Auth | Admin | Beschreibung |
|-------|------|------|-------|--------------|
| `/login` | LoginView | ❌ | - | Login-Formular |
| `/setup` | SetupView | ❌ | - | First-Run Admin-Setup |
| `/` | DashboardView | ✅ | ❌ | Haupt-Dashboard |
| `/mock-esp` | MockEspView | ✅ | ✅ | Mock-ESP Übersicht |
| `/mock-esp/:id` | MockEspDetailView | ✅ | ✅ | Mock-ESP Details |
| `/mqtt-log` | MqttLogView | ✅ | ✅ | MQTT Live-Log |
| `/sensors` | SensorsView | ✅ | ❌ | Alle Sensoren |
| `/actuators` | ActuatorsView | ✅ | ❌ | Alle Aktoren |
| `/logic` | LogicView | ✅ | ❌ | Automation Rules |
| `/database` | DatabaseExplorerView | ✅ | ✅ | DB Explorer |
| `/logs` | LogViewerView | ✅ | ✅ | Server Logs |
| `/users` | UserManagementView | ✅ | ✅ | User CRUD |
| `/system-config` | SystemConfigView | ✅ | ✅ | Config Editor |
| `/load-test` | LoadTestView | ✅ | ✅ | Load Testing |

**Guards-Logik:** Siehe `El Frontend/src/router/index.ts`
- `requiresAuth`: Redirect zu `/login` wenn nicht authentifiziert
- `requiresAdmin`: Redirect zu `/` wenn Rolle ≠ admin
- Setup-Zwang: Wenn `setup_required=true`, immer zu `/setup`

---

## 3. Backend-Architektur

### 3.1 Verzeichnisstruktur

```
El Servador/god_kaiser_server/src/
├── api/v1/                 # REST Endpoints
│   ├── auth.py             # Login, Setup, Refresh, Logout
│   ├── esp.py              # ESP-Registrierung, CRUD
│   ├── sensors.py          # Sensor-Config, Daten
│   ├── actuators.py        # Actuator-Config, Commands
│   ├── logic.py            # Automation Rules
│   ├── debug.py            # ⭐ Debug-Tool Endpoints (erweitert)
│   ├── users.py            # ⭐ NEU: User Management
│   ├── health.py           # System-Health
│   └── kaiser.py           # Kaiser-Node Management (Skeleton)
│
├── db/
│   ├── models/             # SQLAlchemy Models
│   │   ├── user.py         # User, TokenBlacklist
│   │   ├── esp.py          # ESPDevice, KaiserRegistry, ESPOwnership
│   │   ├── sensor.py       # SensorConfig, SensorData
│   │   ├── actuator.py     # ActuatorConfig, ActuatorState, ActuatorHistory
│   │   ├── logic.py        # CrossESPLogic, LogicExecutionHistory
│   │   └── system.py       # LibraryMetadata, SystemConfig, AIPredictions
│   ├── repositories/       # Repository Pattern
│   └── base.py             # Base Model, Session
│
├── services/               # Business Logic
│   ├── mock_esp_manager.py # ⭐ Mock-ESP Simulation
│   ├── sensor_service.py   # Sensor-Operationen
│   ├── actuator_service.py # Actuator-Operationen
│   ├── logic_engine.py     # ⭐ Automation Rule Engine
│   ├── esp_service.py      # ESP-Verwaltung
│   └── safety_service.py   # Safety-Checks
│
├── mqtt/
│   ├── client.py           # Paho MQTT Client
│   ├── subscriber.py       # Topic-Subscriptions
│   ├── publisher.py        # Message Publishing
│   ├── topics.py           # Topic-Builder
│   └── handlers/           # Message Handlers
│       ├── sensor_handler.py
│       ├── actuator_handler.py
│       └── heartbeat_handler.py
│
├── sensors/
│   └── sensor_libraries/   # Dynamisch ladbare Sensor-Verarbeitung
│       └── active/
│           ├── ph_processor.py
│           ├── temperature_processor.py
│           └── ...
│
├── schemas/                # Pydantic Schemas
│   ├── auth.py
│   ├── esp.py
│   ├── sensor.py
│   ├── debug_db.py         # ⭐ NEU: Database Explorer Schemas
│   └── user.py             # ⭐ NEU: User Management Schemas
│
├── core/
│   ├── config.py           # Settings (Environment)
│   ├── constants.py        # Konstanten, Topic-Patterns
│   ├── dependencies.py     # FastAPI Dependencies (Auth)
│   └── logging_config.py   # Logging-Konfiguration
│
├── websocket/
│   └── manager.py          # WebSocket für Real-time Updates
│
└── main.py                 # FastAPI App, Router Registration
```

### 3.2 Datenbank-Tabellen (16 Tabellen)

| Kategorie | Tabelle | Model | Beschreibung |
|-----------|---------|-------|--------------|
| **Auth** | `user_accounts` | `User` | Benutzer (username, email, password_hash, role) |
| **Auth** | `token_blacklist` | `TokenBlacklist` | Invalidierte JWT-Tokens |
| **Devices** | `esp_devices` | `ESPDevice` | Registrierte ESP32-Geräte |
| **Devices** | `kaiser_registry` | `KaiserRegistry` | Kaiser-Nodes (geplant) |
| **Devices** | `esp_ownership` | `ESPOwnership` | ESP-zu-Kaiser Zuordnung |
| **Sensors** | `sensor_configs` | `SensorConfig` | Sensor-Konfigurationen pro ESP/GPIO |
| **Sensors** | `sensor_data` | `SensorData` | ⚠️ Time-Series: Sensor-Messwerte |
| **Actuators** | `actuator_configs` | `ActuatorConfig` | Actuator-Konfigurationen |
| **Actuators** | `actuator_state` | `ActuatorState` | Aktueller Zustand |
| **Actuators** | `actuator_history` | `ActuatorHistory` | ⚠️ Time-Series: Änderungs-Log |
| **Automation** | `cross_esp_logic` | `CrossESPLogic` | Automation Rules |
| **Automation** | `logic_execution_history` | `LogicExecutionHistory` | ⚠️ Time-Series: Ausführungs-Log |
| **System** | `library_metadata` | `LibraryMetadata` | Sensor-Library-Versionen |
| **System** | `system_config` | `SystemConfig` | Key-Value Konfiguration |
| **KI** | `ai_predictions` | `AIPredictions` | KI-Vorhersagen (geplant) |

**⚠️ Time-Series Tabellen:** Diese können sehr groß werden. Im Database Explorer standardmäßig auf 24h begrenzt.

---

## 4. API-Referenz

### 4.1 Auth-Endpoints (`/api/v1/auth/`)

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/status` | GET | ❌ | System-Status (setup_required, user_count) |
| `/setup` | POST | ❌ | Ersten Admin erstellen |
| `/login` | POST | ❌ | Login → Tokens |
| `/refresh` | POST | ❌ | Token erneuern |
| `/me` | GET | ✅ | Aktueller User |
| `/logout` | POST | ✅ | Logout (optional: logout_all) |
| `/me/password` | PATCH | ✅ | Eigenes Passwort ändern |

### 4.2 Debug-Endpoints (`/api/v1/debug/`)

**Alle Debug-Endpoints erfordern Admin-Rolle.**

#### Mock-ESP Management

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/mock-esp` | POST | Mock-ESP erstellen |
| `/mock-esp` | GET | Liste aller Mock-ESPs |
| `/mock-esp/{esp_id}` | GET | Mock-ESP Details |
| `/mock-esp/{esp_id}` | DELETE | Mock-ESP löschen |
| `/mock-esp/{esp_id}/heartbeat` | POST | Heartbeat senden |
| `/mock-esp/{esp_id}/state` | POST | System-State setzen |
| `/mock-esp/{esp_id}/sensors` | POST | Sensor hinzufügen |
| `/mock-esp/{esp_id}/sensors/{gpio}` | POST | Sensor-Wert setzen |
| `/mock-esp/{esp_id}/actuators` | POST | Actuator hinzufügen |
| `/mock-esp/{esp_id}/actuators/{gpio}` | POST | Actuator-State setzen |
| `/mock-esp/{esp_id}/emergency-stop` | POST | Emergency-Stop |
| `/mock-esp/{esp_id}/messages` | GET | MQTT-Message-History |

#### Database Explorer

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/db/tables` | GET | Liste aller Tabellen mit Schema |
| `/db/{table_name}` | GET | Paginierte Tabellen-Abfrage |
| `/db/{table_name}/schema` | GET | Detailliertes Tabellen-Schema |
| `/db/{table_name}/{record_id}` | GET | Einzelner Record |

**Query-Parameter für `/db/{table_name}`:**
- `page` (int): Seitennummer (1-indexed)
- `page_size` (int): Records pro Seite (default: 50, max: 500)
- `sort_by` (string): Column zum Sortieren
- `sort_order` (string): "asc" oder "desc"
- `filters` (JSON-string): Filter-Objekt

**Filter-Syntax:**
```json
{
  "esp_id": "ESP_MOCK_001",           // Exact match
  "created_at__gte": "2025-01-01",    // Greater than or equal
  "created_at__lte": "2025-01-31",    // Less than or equal
  "sensor_type__in": ["temperature", "humidity"],  // IN list
  "is_enabled": true                  // Boolean
}
```

#### Logs

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/logs` | GET | Paginierte Log-Abfrage |
| `/logs/files` | GET | Verfügbare Log-Files |

**Query-Parameter für `/logs`:**
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `module`: Logger-Name (z.B. "mqtt.handlers.sensor")
- `start_time`, `end_time`: ISO-Format
- `search`: Fulltext in Message
- `page`, `page_size`

#### System Config

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/config` | GET | Alle Config-Einträge |
| `/config` | PATCH | Config-Werte aktualisieren |

#### Load Testing

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/load-test/bulk-create` | POST | N Mock-ESPs erstellen |
| `/load-test/simulate` | POST | Sensor-Simulation starten |
| `/load-test/stop` | POST | Alle Simulationen stoppen |
| `/load-test/metrics` | GET | Performance-Metriken |

### 4.3 User Management (`/api/v1/users/`)

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/` | GET | Admin | Liste aller User |
| `/` | POST | Admin | Neuen User erstellen |
| `/{user_id}` | GET | Admin | User-Details |
| `/{user_id}` | PATCH | Admin | User bearbeiten |
| `/{user_id}` | DELETE | Admin | User löschen |
| `/{user_id}/reset-password` | POST | Admin | Passwort zurücksetzen |

---

## 5. Implementierungs-Patterns

### 5.1 API Layer Pattern

**Datei:** `El Frontend/src/api/[resource].ts`

```typescript
// Beispiel: src/api/database.ts

import { get, post, patch, del } from './index'

// 1. Types definieren
export interface TableSchema {
  table_name: string
  columns: ColumnSchema[]
  row_count: number
}

// 2. API-Funktionen als Objekt exportieren
export const databaseApi = {
  async listTables(): Promise<{ tables: TableSchema[] }> {
    return get('/debug/db/tables')
  },

  async queryTable(tableName: string, params: QueryParams): Promise<TableDataResponse> {
    const query = new URLSearchParams()
    // ... Parameter aufbauen
    return get(`/debug/db/${tableName}?${query.toString()}`)
  }
}

export default databaseApi
```

**Wichtig:**
- Nutze die Helpers aus `index.ts` (`get`, `post`, `patch`, `del`)
- Diese lösen automatisch `response.data` auf
- Auth-Token wird automatisch via Interceptor gesetzt
- 401 löst automatisch Token-Refresh aus

### 5.2 Pinia Store Pattern

**Datei:** `El Frontend/src/stores/[resource].ts`

```typescript
// Beispiel: src/stores/database.ts

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import databaseApi from '@/api/database'

export const useDatabaseStore = defineStore('database', () => {
  // 1. State als refs
  const tables = ref<TableSchema[]>([])
  const currentData = ref<TableDataResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 2. Computed Properties
  const tableNames = computed(() => tables.value.map(t => t.table_name))

  // 3. Actions als async functions
  async function loadTables() {
    loading.value = true
    error.value = null
    try {
      const response = await databaseApi.listTables()
      tables.value = response.tables
    } catch (e: any) {
      error.value = e.message || 'Failed to load'
      throw e  // Re-throw für View-Level Error Handling
    } finally {
      loading.value = false
    }
  }

  // 4. Reset-Funktion
  function reset() {
    tables.value = []
    currentData.value = null
    error.value = null
  }

  // 5. Return alles was extern gebraucht wird
  return {
    tables, currentData, loading, error,
    tableNames,
    loadTables, reset
  }
})
```

### 5.3 View Pattern

**Datei:** `El Frontend/src/views/[Resource]View.vue`

```vue
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDatabaseStore } from '@/stores/database'

// 1. Store initialisieren
const store = useDatabaseStore()
const router = useRouter()

// 2. Lokaler State (nur UI-bezogen)
const showModal = ref(false)
const selectedItem = ref(null)

// 3. Computed aus Store
const { tables, loading, error } = storeToRefs(store)

// 4. Lifecycle
onMounted(async () => {
  try {
    await store.loadTables()
  } catch (e) {
    // Error ist bereits in store.error
  }
})

// 5. Event Handler
async function handleRefresh() {
  await store.loadTables()
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-white">Page Title</h1>
      <button @click="handleRefresh" class="btn-secondary">
        Refresh
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="text-center py-12">
      <div class="animate-spin h-8 w-8 border-4 border-blue-500 ..."></div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="bg-red-900/50 rounded-lg p-4">
      {{ error }}
    </div>

    <!-- Content -->
    <div v-else>
      <!-- ... -->
    </div>
  </div>
</template>
```

### 5.4 Styling Pattern (Tailwind Dark Theme)

**Konsistente Klassen verwenden:**

```css
/* Hintergrund */
bg-gray-900        /* Seiten-Hintergrund */
bg-gray-800        /* Cards, Panels */
bg-gray-700        /* Hover-States, Inputs */

/* Text */
text-white         /* Primärer Text */
text-gray-300      /* Sekundärer Text */
text-gray-400      /* Tertiärer Text, Labels */
text-gray-500      /* Disabled, Placeholder */

/* Akzente */
text-blue-400      /* Links, Primary Actions */
text-green-400     /* Success */
text-yellow-400    /* Warning */
text-red-400       /* Error, Danger */

/* Borders */
border-gray-700    /* Standard Border */
border-gray-600    /* Hover Border */

/* Buttons */
.btn-primary:      bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2
.btn-secondary:    bg-gray-700 hover:bg-gray-600 text-white rounded-lg px-4 py-2
.btn-danger:       bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2
```

---

## 6. Sensortyp-spezifische Logik

### 6.1 Sensor-Defaults (Wichtig!)

**Prinzip:** Wenn ein Benutzer einen Sensor-Typ auswählt, müssen die Defaults **sinnvoll** sein.

| Sensor-Typ | Default-Einheit | Default-Range | Kalibrierungs-Punkte |
|------------|-----------------|---------------|---------------------|
| `temperature` | °C | -40 bis 85 | 0°C (Eiswasser), 100°C (kochend) |
| `humidity` | % RH | 0 bis 100 | - |
| `ph` | pH | 0 bis 14 | pH 4.0, pH 7.0, pH 10.0 |
| `ec` | µS/cm | 0 bis 20000 | 1413 µS/cm Standard |
| `soil_moisture` | % | 0 bis 100 | Trocken, Nass |
| `light` | lux | 0 bis 100000 | - |
| `pressure` | hPa | 800 bis 1200 | - |
| `co2` | ppm | 0 bis 5000 | 400 ppm (Außenluft) |
| `flow` | L/min | 0 bis 100 | - |

### 6.2 Frontend-Implementation

**Bei Sensor-Typ-Auswahl im Formular:**

```typescript
// src/types/sensorDefaults.ts

export const SENSOR_DEFAULTS: Record<string, SensorDefaults> = {
  temperature: {
    unit: '°C',
    min_value: -40,
    max_value: 85,
    decimal_places: 1,
    alert_low: 0,
    alert_high: 35
  },
  ph: {
    unit: 'pH',  // NICHT '°C'!
    min_value: 0,
    max_value: 14,
    decimal_places: 2,
    alert_low: 5.5,
    alert_high: 7.5
  },
  // ...
}

// In der Komponente:
function onSensorTypeChange(type: string) {
  const defaults = SENSOR_DEFAULTS[type]
  if (defaults) {
    form.unit = defaults.unit
    form.min_value = defaults.min_value
    form.max_value = defaults.max_value
    // User kann überschreiben, aber Defaults sind sinnvoll
  }
}
```

### 6.3 Backend Sensor-Libraries

**Location:** `El Servador/god_kaiser_server/src/sensors/sensor_libraries/active/`

Jede Library hat:
- `process(raw_value, config)` → processed_value
- `get_unit()` → Default-Einheit
- `validate(raw_value)` → bool

---

## 7. Mock-ESP Deep Dive

### 7.1 Wie Mock-ESPs funktionieren

1. **Erstellung:** `POST /debug/mock-esp` erstellt Eintrag in `esp_devices` mit `hardware_type="MOCK_ESP32"`

2. **Heartbeat:** `POST /debug/mock-esp/{id}/heartbeat`
   - MockESPManager publisht MQTT-Message: `kaiser/god/esp/{id}/system/heartbeat`
   - HeartbeatHandler empfängt diese wie von echtem ESP
   - `esp_devices.last_heartbeat` wird aktualisiert

3. **Sensor-Daten:** `POST /debug/mock-esp/{id}/sensors/{gpio}` mit `{ raw_value: 2847 }`
   - MockESPManager publisht: `kaiser/god/esp/{id}/sensor/{gpio}/data`
   - SensorHandler empfängt, ruft Sensor-Library auf
   - Speichert in `sensor_data` (raw + processed)
   - Triggert Logic Engine!

4. **Logic Engine:** Prüft alle aktiven Rules
   - Findet Rule: "IF ESP_MOCK_001.sensor(4) > 7.0 pH THEN ESP_MOCK_002.actuator(5) = ON"
   - Sendet Actuator-Command via MQTT
   - Speichert in `logic_execution_history`

### 7.2 Auto-Heartbeat

```typescript
// Frontend: Auto-Heartbeat aktivieren
await debugApi.setAutoHeartbeat(espId, { enabled: true, interval_seconds: 60 })
```

**Backend:** MockESPManager startet Background-Task der alle X Sekunden Heartbeat sendet.

### 7.3 Batch-Sensor-Updates (für Load-Tests)

```typescript
// Alle Sensoren eines ESPs gleichzeitig setzen
await debugApi.setBatchSensorValues(espId, {
  values: {
    4: 2847,   // GPIO 4 → raw_value 2847
    5: 1234,   // GPIO 5 → raw_value 1234
    12: 3000   // GPIO 12 → raw_value 3000
  },
  publish: true  // Über MQTT senden
})
```

---

## 8. Mock ESP System & Zone-Sync Architektur

> **Kernkonzept:** Dieses Kapitel erklärt das Zusammenspiel zwischen Mock ESPs, Real ESPs und dem Server.
> Es ist essentiell für jeden Entwickler, der an Zone-Features oder ESP-Management arbeitet.

### 8.1 Das Grundprinzip: Server ist die einzige Wahrheit

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GOD-KAISER SERVER                                    │
│                    (PostgreSQL + In-Memory Stores)                          │
│                                                                             │
│   ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐  │
│   │   PostgreSQL    │       │ MockESPManager  │       │   MQTT Broker   │  │
│   │   (Persistenz)  │  <->  │  (In-Memory)    │       │   (Echtzeit)    │  │
│   └─────────────────┘       └─────────────────┘       └─────────────────┘  │
│          ↑                         ↑                         ↑             │
│          │                         │                         │             │
│   ═══════╪═════════════════════════╪═════════════════════════╪══════════   │
│          │      REST API           │                   MQTT Protocol       │
└──────────┼─────────────────────────┼─────────────────────────┼─────────────┘
           │                         │                         │
           ▼                         ▼                         ▼
    ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
    │  Frontend   │           │  Frontend   │           │   ESP32     │
    │  (Vue.js)   │           │  Debug API  │           │  (Hardware) │
    └─────────────┘           └─────────────┘           └─────────────┘
```

**Kernregel:** Das Frontend hat KEINE eigene Datenbank. Es fragt IMMER den Server.

### 8.2 Die zwei ESP-Typen: Real vs. Mock

**Real ESP32 (Hardware)**
| Eigenschaft | Wert |
|-------------|------|
| Speicherort | PostgreSQL (via Heartbeat-Handler registriert) |
| Kommunikation | MQTT (bidirektional) |
| Zone-Updates | Server → MQTT → ESP32 → ACK → Server → DB |
| Datenfluss | ESP32 sendet Sensor-Daten → Server verarbeitet → speichert in DB |

**Mock ESP32 (Simulation)**
| Eigenschaft | Wert |
|-------------|------|
| Speicherort | PostgreSQL + MockESPManager (In-Memory) ← **DUAL STORAGE!** |
| Kommunikation | REST API (kein echtes MQTT) |
| Zone-Updates | Server → DB + MockESPManager (synchron) |
| Datenfluss | Debug-API manipuliert Mock → publiziert via Server-MQTT |

**Warum Dual Storage für Mocks?**

| Speicher | Zweck | Daten |
|----------|-------|-------|
| PostgreSQL | Persistenz, Zone-APIs, Queries | zone_id, zone_name, status, device_id |
| MockESPManager | Simulation, Debug-Features | Sensoren, Aktoren, system_state, heap_free |

**Problem das wir gelöst haben:** Zone-Updates gingen nur an die DB, nicht an den MockESPManager.
Das Frontend lud Mock-Daten aus dem In-Memory-Store → alte Zonen wurden angezeigt.

### 8.3 Der Zone-Assignment Flow (Schritt für Schritt)

**Frontend: Drag & Drop**

```typescript
// El Frontend/src/composables/useZoneDragDrop.ts
async function handleDeviceDrop(event: ZoneDropEvent) {
    const { device, toZoneId } = event
    const deviceId = device.device_id || device.esp_id

    // 1. API-Call an Server
    const response = await zonesApi.assignZone(deviceId, {
        zone_id: toZoneId,
        zone_name: zoneIdToDisplayName(toZoneId)
    })

    // 2. Frontend refresht IMMER vom Server
    await espStore.fetchAll()  // ← Holt neue Daten vom Server
}
```

**Server: ZoneService**

```python
# El Servador/.../services/zone_service.py
async def assign_zone(self, device_id, zone_id, zone_name, master_zone_id):
    # 1. Device aus DB holen
    device = await self.esp_repo.get_by_device_id(device_id)

    # 2. DB aktualisieren (Source of Truth)
    device.zone_id = zone_id
    device.zone_name = zone_name
    device.master_zone_id = master_zone_id

    # 3. MQTT publizieren (für echte ESPs)
    mqtt_sent = self._publish_zone_assignment(topic, payload)

    # 4. NEU: MockESPManager synchronisieren (für Mock ESPs)
    if _is_mock_esp(device_id):
        await self._update_mock_esp_zone(device_id, zone_id, zone_name, master_zone_id)

    return ZoneAssignResponse(success=True, ...)
```

**Server: MockESPManager Update**

```python
# El Servador/.../services/mock_esp_manager.py
async def update_zone(self, esp_id, zone_id, zone_name, master_zone_id):
    mock = self._mock_esps.get(esp_id)
    if not mock:
        return False

    # In-Memory Zone aktualisieren
    if zone_id:
        mock.configure_zone(zone_id=zone_id, master_zone_id=master_zone_id)
        self._zone_names[esp_id] = zone_name
    else:
        mock.zone = None
        del self._zone_names[esp_id]

    return True
```

**Frontend: Daten laden**

```typescript
// El Frontend/src/api/esp.ts
async listDevices(): Promise<ESPDevice[]> {
    // Parallel: Mock ESPs + DB Devices holen
    const [mockEsps, dbDevices] = await Promise.all([
        debugApi.listMockEsps(),      // In-Memory (mit zone_id, zone_name)
        api.get('/esp/devices')        // PostgreSQL
    ])

    // Mocks haben Vorrang (reichere Daten: Sensoren, Aktoren, System-State)
    const mockEspIds = new Set(mockEsps.map(m => m.esp_id))

    // DB-Geräte filtern (keine Duplikate)
    const filteredDbDevices = dbDevices.filter(d => !mockEspIds.has(d.device_id))

    return [...normalizedMockEsps, ...filteredDbDevices]
}
```

### 8.4 Datenfluss-Diagramm: Wer fragt wen?

```
                        ┌───────────────────────────────────────┐
                        │           USER ACTION                 │
                        │    (Drag ESP to Zone "Zelt 1")        │
                        └───────────────────┬───────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Vue.js)                                                          │
│                                                                            │
│  1. useZoneDragDrop.handleDeviceDrop()                                     │
│     └─→ zonesApi.assignZone("ESP_MOCK_001", {zone_id: "zelt_1"})          │
│                                                                            │
│  2. Nach Erfolg: espStore.fetchAll()                                       │
│     └─→ Alle Geräte neu vom Server laden                                   │
└────────────────────────────────────────────────────────────────────────────┘
                                            │
                          POST /v1/zone/devices/ESP_MOCK_001/assign
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ SERVER (FastAPI)                                                           │
│                                                                            │
│  ZoneService.assign_zone()                                                 │
│  ├── 1. ESPRepository.get_by_device_id() → Device aus PostgreSQL          │
│  ├── 2. device.zone_id = "zelt_1"       → DB Update                       │
│  ├── 3. MQTT publish (für Real ESPs)    → mqtt_sent = False (Mock)        │
│  └── 4. MockESPManager.update_zone()    → In-Memory Update ✓              │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                                            │
                        HTTP 200 { success: true, zone_id: "zelt_1" }
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Vue.js) - REFRESH                                                │
│                                                                            │
│  espStore.fetchAll()                                                       │
│  ├── GET /v1/debug/mock-esp  → MockESPManager (zone_id = "zelt_1" ✓)      │
│  └── GET /v1/esp/devices     → PostgreSQL (zone_id = "zelt_1" ✓)          │
│                                                                            │
│  → UI zeigt jetzt korrekte Zone an                                         │
└────────────────────────────────────────────────────────────────────────────┘
```

### 8.5 Die goldenen Regeln für Entwickler

**Regel 1: Server ist IMMER die Wahrheit**
```
❌ FALSCH: Frontend speichert Zone lokal und zeigt sie an
✓ RICHTIG: Frontend ruft Server-API → wartet auf Erfolg → lädt neu vom Server
```

**Regel 2: Nach jeder Mutation → Refresh**
```typescript
// Nach CREATE, UPDATE, DELETE immer:
await espStore.fetchAll()  // oder fetchDevice(id)
```

**Regel 3: Mock ESP = Dual Storage**

Wenn du Mock-Daten änderst, musst du BEIDE aktualisieren:

| Änderung | PostgreSQL | MockESPManager |
|----------|------------|----------------|
| Zone zuweisen | ✓ ZoneService | ✓ _update_mock_esp_zone() |
| Sensor hinzufügen | ❌ (nicht in DB) | ✓ debug.py endpoint |
| Status ändern | ✓ esp_repo | ✓ MockESPManager.set_state() |

**Regel 4: API-Endpunkte kennen**

| Daten | Endpoint | Speicher |
|-------|----------|----------|
| Alle ESPs | GET /v1/esp/devices | PostgreSQL |
| Mock ESPs (reich) | GET /v1/debug/mock-esp | In-Memory |
| Zone zuweisen | POST /v1/zone/devices/{id}/assign | DB + In-Memory |
| Mock ESP erstellen | POST /v1/debug/mock-esp | DB + In-Memory |

### 8.6 Typische Fehler und ihre Ursachen

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Zone wird nicht angezeigt nach Drag & Drop | MockESPManager wurde nicht aktualisiert | ZoneService muss `_update_mock_esp_zone()` aufrufen (bereits implementiert) |
| Mock ESP verschwindet nach Server-Restart | MockESPManager ist In-Memory (nicht persistent) | Mock ESPs müssen nach Restart neu erstellt werden. DB-Eintrag bleibt (wird als "orphaned" markiert) |
| Frontend zeigt veraltete Daten | `fetchAll()` wurde nicht aufgerufen nach Mutation | IMMER nach API-Calls den Store refreshen |

### 8.7 Code-Locations Quick Reference

| Komponente | Pfad |
|------------|------|
| Zone API (Server) | `El Servador/god_kaiser_server/src/api/v1/zone.py` |
| Zone Service | `El Servador/god_kaiser_server/src/services/zone_service.py` |
| MockESPManager | `El Servador/god_kaiser_server/src/services/mock_esp_manager.py` |
| Debug API | `El Servador/god_kaiser_server/src/api/v1/debug.py` |
| Frontend Zone API | `El Frontend/src/api/zones.ts` |
| Frontend ESP API | `El Frontend/src/api/esp.ts` |
| ESP Store | `El Frontend/src/stores/esp.ts` |
| Drag & Drop | `El Frontend/src/composables/useZoneDragDrop.ts` |

### 8.8 Test-Checkliste für neue Features

Wenn du Features implementierst, die ESPs betreffen:

- [ ] Funktioniert es mit Real ESPs? (DB + MQTT)
- [ ] Funktioniert es mit Mock ESPs? (DB + MockESPManager)
- [ ] Wird das Frontend nach der Änderung refresht?
- [ ] Ist der Server die einzige Quelle der Wahrheit?
- [ ] Werden bei Mocks beide Speicher synchron gehalten?

---

## 9. WebSocket-Integration

### 9.1 MQTT Live-Log

**Endpoint:** `/ws/realtime/{client_id}?token={jwt}`

**Connection Flow:**
```typescript
// 1. Frischen Token holen
const token = authStore.accessToken

// 2. WebSocket öffnen
const ws = new WebSocket(`ws://localhost:8000/ws/realtime/${clientId}?token=${token}`)

// 3. Nach Connect: Subscribe
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'subscribe',
    filters: ['sensor_data', 'actuator_command', 'heartbeat', 'system']
  }))
}

// 4. Messages empfangen
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  // { type: 'sensor_data', topic: '...', payload: {...}, timestamp: '...' }
}
```

**Referenz-Implementation:** `El Frontend/src/views/MqttLogView.vue`

### 9.2 Log-Stream (optional)

**Endpoint:** `/ws/logs?token={jwt}&level={min_level}`

Gleicher Connection Flow, aber für Server-Logs statt MQTT.

---

## 10. Typische Aufgaben

### 10.1 Neue View hinzufügen

1. **View erstellen:** `src/views/NewFeatureView.vue`
2. **Route registrieren:** `src/router/index.ts`
   ```typescript
   {
     path: '/new-feature',
     name: 'new-feature',
     component: () => import('@/views/NewFeatureView.vue'),
     meta: { requiresAuth: true, requiresAdmin: true }
   }
   ```
3. **Navigation hinzufügen:** In Sidebar-Komponente

### 10.2 Neuen API-Endpoint anbinden

1. **API-Modul:** `src/api/newfeature.ts` erstellen
2. **Types:** In `src/types/index.ts` oder eigene Datei
3. **Store (optional):** `src/stores/newfeature.ts` wenn State-Management nötig
4. **View:** Store/API in View importieren und nutzen

### 10.3 Backend-Endpoint erweitern

1. **Schema:** `src/schemas/[resource].py`
2. **Router:** `src/api/v1/[resource].py`
3. **Service (optional):** `src/services/[resource]_service.py`
4. **Tests:** `tests/api/test_[resource].py`

---

## 11. Debugging & Troubleshooting

### 11.1 System starten

```bash
# Terminal 1: Backend
cd "El Servador/god_kaiser_server"
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd "El Frontend"
npm run dev

# Optional Terminal 3: MQTT Broker
mosquitto -v
```

### 11.2 Häufige Probleme

| Problem | Ursache | Lösung |
|---------|---------|--------|
| 401 Endlos-Loop | Token korrupt | LocalStorage leeren, neu einloggen |
| MQTT nicht verbunden | Broker nicht gestartet | `mosquitto -v` starten |
| Mock-ESP sendet nicht | MQTT Client nicht connected | Server-Logs prüfen |
| Sensor-Wert nicht verarbeitet | Library fehlt | `sensor_libraries/active/` prüfen |
| Logic Rule triggert nicht | Cooldown aktiv | `logic_execution_history` prüfen |

### 11.3 Wichtige Logs

**Server-Logs prüfen:**
```bash
# Live-Logs im Terminal (während Server läuft)
# Oder: Log-Dateien in konfigurierten Log-Verzeichnis

# Wichtige Logger:
# - mqtt.handlers.sensor
# - mqtt.handlers.actuator
# - services.logic_engine
# - services.mock_esp_manager
```

**Frontend DevTools:**
- Network Tab: API-Calls prüfen
- Console: JavaScript-Errors
- Vue DevTools: Pinia State inspizieren

---

## 12. Code-Qualitäts-Standards

### 12.1 TypeScript

- **Immer typisieren:** Keine `any` außer wenn unvermeidbar
- **Interfaces vor Types:** `interface User {}` statt `type User = {}`
- **Enums für feste Werte:** `enum UserRole { ADMIN = 'admin', ... }`

### 12.2 Vue Components

- **Composition API:** Kein Options API
- **`<script setup>`:** Immer verwenden
- **Props typisieren:** `defineProps<{ userId: number }>()`
- **Emits typisieren:** `defineEmits<{ (e: 'select', id: number): void }>()`

### 12.3 Python/FastAPI

- **Pydantic für alles:** Request/Response Bodies
- **Type Hints:** Alle Funktionen typisieren
- **Async:** Alle DB-Operationen async
- **Dependency Injection:** `Depends()` für Auth, DB-Session

### 12.4 Commits

- **Präfix:** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- **Scope:** `feat(frontend):`, `fix(api):`
- **Beschreibend:** Was wurde geändert und warum

---

## 13. Nächste Schritte nach Onboarding

1. **System lokal starten** (Section 11.1)
2. **Mit Setup-Flow vertraut machen** (ersten Admin erstellen)
3. **Mock-ESP erstellen und testen**
4. **Database Explorer durchklicken**
5. **Bestehende Views studieren** (MockEspDetailView als Referenz)
6. **Erste kleine Änderung machen** (z.B. neues Feld in einer View)

---

**Bei Fragen:** Zuerst in der Dokumentation suchen (CLAUDE.md → weitere .md Dateien), dann fragen.

**Dokumentation aktualisieren:** Wenn du etwas lernst das nicht dokumentiert ist, füge es hinzu!




















