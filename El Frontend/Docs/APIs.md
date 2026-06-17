## Zweck
Vollständige Referenz aller im Frontend implementierten REST-API-Endpunkte und deren Code-Locations. Basis: `El Frontend` (Vue 3 + TypeScript + Tailwind) mit Backend `El Servador` (FastAPI, Prefix `/api/v1`).

## Axios-Basis
- **Datei:** `src/api/index.ts`
- **Konfiguration:**
  - `baseURL: '/api/v1'`, `timeout: 30000`
  - Request-Interceptor: setzt `Authorization: Bearer <accessToken>` aus `useAuthStore()`
  - Response-Interceptor: bei 401 + Refresh-Token → `authStore.refreshTokens()` → wiederholt Request, sonst Logout + Redirect `/login`
  - Exporte: `get/post/put/patch/del` Helper (lösen `res.data` automatisch auf)

## Auth-API (`src/api/auth.ts`)
**Verwendet in:** LoginView, SetupView, Router Guards

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/auth/status` | GET | – | `AuthStatusResponse { setup_required, user_count }` | System-Status prüfen |
| `/auth/setup` | POST | `SetupRequest { username, email, password, full_name? }` | `TokenResponse` | Ersten Admin erstellen |
| `/auth/login` | POST | `LoginRequest { username, password, remember_me? }` | `TokenResponse` | Login mit Tokens |
| `/auth/refresh` | POST | `{ refresh_token }` | `TokenResponse` | Access-Token erneuern |
| `/auth/me` | GET | – | `{ success, data: User }` | Aktuelle User-Info |
| `/auth/logout` | POST | `{ logout_all?: boolean }` | `void` | Logout (optional alle Sessions) |

**Datenstrukturen:** `User`, `LoginRequest`, `SetupRequest`, `TokenResponse`, `AuthStatusResponse`
**Storage:** LocalStorage Keys: `el_frontend_access_token`, `el_frontend_refresh_token`

## Debug/Mock-ESP-API (`src/api/debug.ts`)
**Verwendet in:** MockEspView, MockEspDetailView, MqttLogView

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/debug/mock-esp` | POST | `MockESPCreate` | `MockESP` | Mock-ESP erstellen |
| `/debug/mock-esp` | GET | – | `{ success, data: MockESP[], total }` | Alle Mock-ESPs auflisten |
| `/debug/mock-esp/{esp_id}` | GET | – | `MockESP` | Mock-ESP Details |
| `/debug/mock-esp/{esp_id}` | DELETE | – | `void` | Mock-ESP löschen |
| `/debug/mock-esp/{esp_id}/heartbeat` | POST | – | `HeartbeatResponse` | Heartbeat senden |
| `/debug/mock-esp/{esp_id}/state` | POST | `{ state, reason? }` | `CommandResponse` | System-Status setzen |
| `/debug/mock-esp/{esp_id}/auto-heartbeat` | POST | `{ enabled, interval_seconds }` | `CommandResponse` | Auto-Heartbeat ein/aus |
| `/debug/mock-esp/{esp_id}/sensors` | POST | `MockSensorConfig` | `CommandResponse` | Sensor hinzufügen |
| `/debug/mock-esp/{esp_id}/sensors/{gpio}` | POST | `{ raw_value, quality?, publish? }` | `CommandResponse` | Sensor-Wert setzen |
| `/debug/mock-esp/{esp_id}/sensors/batch` | POST | `{ values: Record<gpio,raw>, publish? }` | `CommandResponse` | Mehrere Sensor-Werte setzen |
| `/debug/mock-esp/{esp_id}/actuators` | POST | `MockActuatorConfig` | `CommandResponse` | Aktor hinzufügen |
| `/debug/mock-esp/{esp_id}/actuators/{gpio}` | POST | `{ state, pwm_value?, publish? }` | `CommandResponse` | Aktor-Status setzen |
| `/debug/mock-esp/{esp_id}/emergency-stop` | POST | `{ reason }` | `CommandResponse` | Emergency-Stop auslösen |
| `/debug/mock-esp/{esp_id}/clear-emergency` | POST | – | `CommandResponse` | Emergency-Stop zurücksetzen |
| `/debug/mock-esp/{esp_id}/messages` | GET | `{ limit }` | `{ success, esp_id, messages[] }` | MQTT-Message-Historie |
| `/debug/mock-esp/{esp_id}/messages` | DELETE | – | `void` | Message-Historie leeren |

**Datenstrukturen:** `MockESP`, `MockSensorConfig`, `MockActuatorConfig`, `CommandResponse`, `MqttMessageRecord`

## Database Explorer API (`src/api/database.ts`)
**Verwendet in:** DatabaseExplorerView, TableSelector, DataTable

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/debug/db/tables` | GET | – | `{ tables: TableSchema[] }` | Alle Tabellen mit Schema |
| `/debug/db/{table}/schema` | GET | – | `TableSchema` | Detailliertes Tabellen-Schema |
| `/debug/db/{table}` | GET | Query-Params | `TableDataResponse` | Tabellen-Daten mit Filter/Pagination |
| `/debug/db/{table}/{id}` | GET | – | `RecordResponse` | Einzelner Record |

**Query-Parameter für `/debug/db/{table}`:**
- `page` (int): Seitennummer (1-indexed)
- `page_size` (int): Records pro Seite (max: 500)
- `sort_by` (string): Sortier-Spalte
- `sort_order` (string): "asc" oder "desc"
- `filters` (JSON-string): Filter-Objekt

**Filter-Syntax:**
```json
{
  "esp_id": "ESP_MOCK_001",
  "created_at__gte": "2025-01-01T00:00:00",
  "created_at__lte": "2025-01-31T23:59:59",
  "sensor_type__in": ["temperature", "humidity"],
  "is_enabled": true
}
```

**Datenstrukturen:** `TableSchema`, `ColumnSchema`, `TableDataResponse`, `RecordResponse`

## Logs API (`src/api/logs.ts`)
**Verwendet in:** LogViewerView

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/debug/logs` | GET | Query-Params | `LogsResponse` | Server-Logs mit Filter |
| `/debug/logs/files` | GET | – | `LogFilesResponse` | Verfügbare Log-Files |

**Query-Parameter für `/debug/logs`:**
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `module`: Logger-Name (z.B. "mqtt.handlers.sensor")
- `start_time`, `end_time`: ISO-Format
- `search`: Volltext-Suche in Messages
- `page`, `page_size`: Pagination

**Datenstrukturen:** `LogEntry`, `LogsResponse`, `LogFile`, `LogFilesResponse`

## User Management API (`src/api/users.ts`)
**Verwendet in:** UserManagementView (Admin-only)

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/users` | GET | – | `UserListResponse` | Alle User auflisten |
| `/users` | POST | `UserCreate` | `{ success, data: User }` | Neuen User erstellen |
| `/users/{user_id}` | GET | – | `{ success, data: User }` | User-Details |
| `/users/{user_id}` | PATCH | `UserUpdate` | `{ success, data: User }` | User bearbeiten |
| `/users/{user_id}` | DELETE | – | `void` | User löschen |
| `/users/{user_id}/reset-password` | POST | `PasswordReset` | `void` | Passwort zurücksetzen |

**Datenstrukturen:** `User`, `UserCreate`, `UserUpdate`, `UserListResponse`, `PasswordReset`
**Rollen:** `admin`, `operator`, `viewer`

## System Config API (`src/api/config.ts`)
**Verwendet in:** SystemConfigView (Admin-only)

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/debug/config` | GET | – | `ConfigResponse` | Alle Konfigurationseinträge |
| `/debug/config` | PATCH | `ConfigUpdate` | `ConfigResponse` | Konfiguration aktualisieren |

**Datenstrukturen:** `ConfigEntry`, `ConfigResponse`, `ConfigUpdate`

## Load Testing API (`src/api/loadtest.ts`)
**Verwendet in:** LoadTestView (Admin-only)

| Endpoint | Methode | Payload | Response | Beschreibung |
|----------|---------|---------|----------|--------------|
| `/debug/load-test/bulk-create` | POST | `{ count, prefix? }` | `BulkCreateResponse` | N Mock-ESPs erstellen |
| `/debug/load-test/simulate` | POST | `{ esp_ids, duration_seconds }` | `CommandResponse` | Sensor-Simulation starten |
| `/debug/load-test/stop` | POST | – | `CommandResponse` | Alle Simulationen stoppen |
| `/debug/load-test/metrics` | GET | – | `LoadTestMetrics` | Performance-Metriken |

**Datenstrukturen:** `BulkCreateResponse`, `LoadTestMetrics`

## Fehlerbehandlung & Retry-Logik
- **401 Unauthorized:** Automatischer Token-Refresh → Request wiederholen, bei Fehlschlag Logout
- **Timeout:** 30s global für alle Requests
- **Retry:** Bei Network-Fehlern automatisch 1 Retry
- **Error States:** Alle API-Calls haben definierte Error-Responses mit `success: false`

## Code-Locations
**API-Module:** `src/api/`
- `auth.ts` - Authentifizierung
- `debug.ts` - Mock-ESP Management
- `database.ts` - Database Explorer
- `logs.ts` - Log Viewer
- `users.ts` - User Management
- `config.ts` - System Config
- `loadtest.ts` - Load Testing

**Views:** `src/views/`
- Auth: `LoginView.vue`, `SetupView.vue`
- Debug: `MockEspView.vue`, `MockEspDetailView.vue`, `MqttLogView.vue`
- Database: `DatabaseExplorerView.vue`
- Logs: `LogViewerView.vue`
- Users: `UserManagementView.vue`
- Config: `SystemConfigView.vue`
- LoadTest: `LoadTestView.vue`

**Stores:** `src/stores/`
- `auth.ts` - Auth State & Token Management
- `mockEsp.ts` - Mock-ESP State
- `database.ts` - Database Explorer State

## Backend-API-Locations
**Server-Endpunkte:** `El Servador/god_kaiser_server/src/api/v1/`
- `auth.py` - Authentifizierung
- `debug.py` - Debug/Mock-ESP Endpunkte
- `users.py` - User Management
- `health.py` - System Health
- `esp.py` - ESP Device Management (noch nicht im Frontend)
- `sensors.py` - Sensor Management (noch nicht im Frontend)
- `actuators.py` - Actuator Management (noch nicht im Frontend)
- `logic.py` - Logic Rules (noch nicht im Frontend)

**Noch nicht implementierte Frontend-APIs:**
- ESP Device Management
- Sensor Configuration
- Actuator Configuration
- Logic Rules (Cross-ESP Automation)
- Health Monitoring