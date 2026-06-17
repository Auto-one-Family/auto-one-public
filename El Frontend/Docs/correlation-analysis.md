# Event Correlation Analysis - AutomationOne Frontend

> Research-only analysis of event correlation capabilities in `El Frontend/src/`

---

## 1. Currently Implemented Correlation Features

### 1.1 ESP-ID Based Filtering (Primary Correlation Key)

ESP-ID is the most widely used correlation mechanism. It appears in nearly every view and component as a filter key, allowing users to see all events related to a single device.

| Location | File | Line(s) | Mechanism |
|----------|------|---------|-----------|
| System Monitor | `src/views/SystemMonitorView.vue` | 222, 273-280 | `filterEspId` ref filters all unified events by `e.esp_id` |
| MQTT Traffic Tab | `src/components/system-monitor/MqttTrafficTab.vue` | 102, 124-128 | `filterEspId` ref with substring match on `m.esp_id` |
| Events Tab | `src/components/system-monitor/EventsTab.vue` | 46, 65, 85, 115 | Props-based `filterEspId` passed to child components |
| Sensors View | `src/views/SensorsView.vue` | 62, 130, 166 | `filterEspId` filters sensors and actuators |
| Query Filters composable | `src/composables/useQueryFilters.ts` | 28, 150-151, 291-294 | `setEspFilter()` for deep-linking from ESP cards |
| WebSocket service | `src/services/websocket.ts` | 410-413 | Client-side `esp_ids` filter on incoming WS messages |
| Audit API | `src/api/audit.ts` | 280, 315-320 | Server-side `esp_ids` query parameter for aggregated events |
| Monitor Filter Panel | `src/components/system-monitor/MonitorFilterPanel.vue` | 98-100 | UI control for ESP-ID filter input |

### 1.2 Event Type Categorization

Events are grouped into categories for visual styling, but this is classification, not correlation.

- File: `src/utils/eventTransformer.ts`, lines 83-115
- Categories: `esp-status`, `sensors`, `actuators`, `system`
- Used by: `EventDetailsPanel.vue`, `PreviewEventCard.vue`, `SystemMonitorView.vue`

### 1.3 Config Response Handling (Implicit Event Chain)

The `config_response` event type is handled in multiple places, creating an implicit link between config publishing and response:

- `src/composables/useConfigResponse.ts` (lines 36-37): Subscribes to WebSocket `config_response` events
- `src/stores/esp.ts` (lines 1676, 2004): `handleConfigResponse` handler updates ESP device state
- `src/views/SystemMonitorView.vue` (lines 487-488, 593, 711): Maps both `config_response` and `config_published` to `audit_log` data source

However, there is **no explicit linking** between a `config_published` event and its corresponding `config_response`. They are displayed as independent events.

### 1.4 Cross-ESP Logic Connections

The logic store provides ESP-to-ESP relationship tracking:

- File: `src/stores/logic.ts`, lines 90, 211, 218
- `crossEspConnections`: Filters connections where `isCrossEsp === true`
- `getConnectionsBySourceEsp(espId)`: Gets outgoing connections
- `getConnectionsByTargetEsp(espId)`: Gets incoming connections

This is the closest thing to actual event correlation -- linking actuator actions on one ESP to sensor triggers on another.

---

## 2. Backend correlation_id: Present but Unused

### 2.1 Backend Schema

The `AuditLog` database model has a `correlation_id` field:
- File: `El Servador/god_kaiser_server/src/db/models/audit_log.py`, line 156
- Type: `String(100)`, nullable, indexed
- Description: "Correlation ID for tracing related events"

### 2.2 API Exposure

The field is returned in API responses:
- File: `El Servador/god_kaiser_server/src/api/v1/audit.py`, lines 52, 362, 593, 630

### 2.3 Frontend Type Definition

- File: `src/api/audit.ts`, line 29: `correlation_id: string | null`
- File: `src/utils/databaseColumnTranslator.ts`, lines 761-765: Column labeled "Korrelations-ID" with description "ID zur Verknuepfung zusammenhaengender Ereignisse", `defaultVisible: false`

### 2.4 Critical Finding: Never Populated

Searching the entire server codebase for `AuditLog(` constructor calls reveals that **no code ever sets `correlation_id` when creating audit log entries**. The field exists in the schema and is returned via API, but it is always `null`.

The frontend type includes the field but never reads, displays, filters, or queries by it (beyond the database column translator definition which is hidden by default).

---

## 3. Missing Correlations

### 3.1 Config Publish -> Config Response Chain

When the server publishes a config to an ESP (`config_published`), and the ESP responds (`config_response`), these two events are not linked. A `correlation_id` (e.g., a UUID generated at publish time and included in the MQTT payload) would allow the frontend to show:
- "This config_response is the answer to config_published event X"
- Latency between publish and response
- Unacknowledged configs (publish without response)

### 3.2 Actuator Command -> Actuator Response Chain

Similarly, actuator commands sent via MQTT and the corresponding `actuator_response` events are not linked. The frontend shows them as independent entries.

### 3.3 Time-Window Grouping

There is no time-window grouping of events. Events within a short time window (e.g., a config push triggering multiple sensor reconfigurations) are displayed as a flat list with no visual grouping.

### 3.4 Log-to-Audit Cross-Reference

Server logs (`src/api/logs.ts` -- `LogEntry` type) and audit events (`src/api/audit.ts` -- `AuditLog` type) are completely separate data streams with no cross-referencing:
- Server logs have: `timestamp`, `level`, `logger`, `module`, `function`, `line`
- Audit events have: `event_type`, `severity`, `source_id`, `correlation_id`
- No shared identifier connects a server log line to an audit event

### 3.5 ESP Health -> Device Offline Correlation

When heartbeats stop and a `device_offline` event fires, there is no link back to the last `esp_health` heartbeat event for that device.

### 3.6 Emergency Stop Event Chain

An emergency stop affects multiple actuators across potentially multiple ESPs. The resulting `actuator_alert` events for each affected actuator are not grouped or linked to the triggering emergency stop event.

---

## 4. ESP-ID as Correlation Key -- Summary

ESP-ID is the **only actively used correlation key** in the frontend. It enables:

| Capability | Status |
|-----------|--------|
| Filter all event types by a single ESP | Implemented (SystemMonitorView, SensorsView, MqttTrafficTab) |
| Deep-link from ESP card to filtered view | Implemented (useQueryFilters.ts `setEspFilter`) |
| Server-side ESP filtering | Implemented (audit API `esp_ids` parameter) |
| WebSocket ESP filtering | Implemented (websocket.ts client-side filter) |
| Cross-ESP logic visualization | Implemented (logic store, CrossEspConnectionOverlay) |
| Group events by ESP in timeline | Not implemented |
| Show ESP event history in detail panel | Not implemented |

---

## 5. Whether correlation_id from Backend is Utilized

**No.** The `correlation_id` field flows through the system as follows:

1. Database model defines it (indexed) -- `audit_log.py:156`
2. API returns it in responses -- `audit.py:52,362,593,630`
3. Frontend type includes it -- `audit.ts:29`
4. Database column translator labels it -- `databaseColumnTranslator.ts:761-765`

But:
- The server **never sets** `correlation_id` when creating `AuditLog` entries
- The frontend **never reads** `correlation_id` from events
- The frontend **never queries** by `correlation_id`
- The frontend **never displays** `correlation_id` (hidden by default in DB table)
- No UI exists to "find related events by correlation_id"

The infrastructure is in place end-to-end, but the feature is entirely dormant.

---

## 6. Files Referenced

| File | Purpose |
|------|---------|
| `El Frontend/src/api/audit.ts` | Audit API client, `AuditLog` type with `correlation_id` |
| `El Frontend/src/api/logs.ts` | Server log API client (no correlation fields) |
| `El Frontend/src/utils/eventTransformer.ts` | Event categorization and message transformation |
| `El Frontend/src/utils/databaseColumnTranslator.ts` | `correlation_id` column definition (hidden) |
| `El Frontend/src/views/SystemMonitorView.vue` | Main monitor view with ESP-ID filtering |
| `El Frontend/src/views/SensorsView.vue` | Sensor/actuator view with ESP-ID filtering |
| `El Frontend/src/composables/useQueryFilters.ts` | Reusable ESP filter composable |
| `El Frontend/src/composables/useConfigResponse.ts` | Config response WebSocket handler |
| `El Frontend/src/services/websocket.ts` | WebSocket client with `esp_ids` filter |
| `El Frontend/src/stores/logic.ts` | Cross-ESP logic connection store |
| `El Frontend/src/stores/esp.ts` | ESP store with config_response handler |
| `El Frontend/src/components/system-monitor/EventDetailsPanel.vue` | Event detail panel (no correlation display) |
| `El Frontend/src/components/system-monitor/MqttTrafficTab.vue` | MQTT traffic with ESP-ID filter |
| `El Frontend/src/components/system-monitor/MonitorFilterPanel.vue` | Filter UI with ESP-ID input |
| `El Servador/god_kaiser_server/src/db/models/audit_log.py` | AuditLog model with `correlation_id` field |
| `El Servador/god_kaiser_server/src/api/v1/audit.py` | Audit API endpoints returning `correlation_id` |
| `El Servador/god_kaiser_server/src/services/audit_retention_service.py` | Audit cleanup (creates AuditLog without correlation_id) |

---

*Analysis date: 2026-01-27*
