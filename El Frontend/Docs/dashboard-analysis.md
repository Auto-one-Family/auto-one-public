# Dashboard Live Data Integration Analysis

> Generated: 2026-01-27 | Research-only analysis of `DashboardView.vue` and related components.

---

## 1. Dashboard Widgets/Sections

The dashboard is composed of these major sections:

| # | Widget/Section | Component | File Path |
|---|----------------|-----------|-----------|
| 1 | **ActionBar** | `ActionBar.vue` | `El Frontend/src/components/dashboard/ActionBar.vue` |
| 2 | **Zone Groups** (main content) | `ZoneGroup.vue` + `ESPOrbitalLayout.vue` | `El Frontend/src/components/zones/ZoneGroup.vue`, `El Frontend/src/components/esp/ESPOrbitalLayout.vue` |
| 3 | **Cross-ESP Connection Overlay** | `CrossEspConnectionOverlay.vue` | `El Frontend/src/components/dashboard/CrossEspConnectionOverlay.vue` |
| 4 | **Component Sidebar** (right) | `ComponentSidebar.vue` | `El Frontend/src/components/dashboard/ComponentSidebar.vue` |
| 5 | **Unassigned Drop Bar** (bottom) | `UnassignedDropBar.vue` | `El Frontend/src/components/dashboard/UnassignedDropBar.vue` |
| 6 | **Pending Devices Panel** | `PendingDevicesPanel.vue` | `El Frontend/src/components/esp/PendingDevicesPanel.vue` |
| 7 | **ESP Settings Popover** | `ESPSettingsPopover.vue` | `El Frontend/src/components/esp/ESPSettingsPopover.vue` |
| 8 | **Create Mock ESP Modal** | `CreateMockEspModal.vue` | `El Frontend/src/components/modals/CreateMockEspModal.vue` |
| 9 | **Loading/Empty States** | `LoadingState`, `EmptyState` | `El Frontend/src/components/common/` |

### ActionBar (Line 382-400 in DashboardView.vue)
- Status filter pills: Online, Offline, Warning, Safe Mode counts
- Type filter buttons: All / Mock / Real with counts
- Problem warning banner (amber) when devices have errors
- Action buttons: Pending Devices, Create Mock ESP, Settings

### Zone Groups (Line 449-476)
- Devices grouped by zone using `groupDevicesByZone()` composable
- Each zone rendered as a collapsible `ZoneGroup` with drag-and-drop
- Inside each zone, devices rendered via `ESPOrbitalLayout` (compact mode)
- Unassigned devices excluded from main area (shown in bottom bar)

### Component Sidebar (Line 493)
- Static list of draggable sensor types (DS18B20, SHT31, BME280, pH, EC, moisture, light, co2, flow, level)
- Static list of draggable actuator types
- Drag-and-drop onto ESP devices to add sensors/actuators
- No live data -- purely a palette of available component types

### Cross-ESP Connection Overlay (Line 437-439)
- SVG overlay drawing bezier curves between sensor/actuator satellites on different ESPs
- Data from `logicStore.crossEspConnections`
- Toggleable via floating button (Line 480-489)
- Live execution feedback via CSS animation when rules fire

### Unassigned Drop Bar (Line 497)
- Fixed bottom bar showing devices without zone assignment
- Drop target for removing devices from zones
- Reads `espStore.devices.filter(d => !d.zone_id)` reactively

---

## 2. Data Sources Per Widget

### Initial Load (REST API)

All initial data fetching happens in `DashboardView.vue` `onMounted()` (Lines 60-66):

```typescript
onMounted(() => {
  espStore.fetchAll()              // GET /api/v1/esp/devices
  espStore.fetchPendingDevices()   // GET /api/v1/esp/pending
  logicStore.fetchRules()          // GET /api/v1/logic/rules
  logicStore.subscribeToWebSocket()
})
```

| Widget | REST API Call | Endpoint |
|--------|--------------|----------|
| All device data | `espStore.fetchAll()` | `GET /api/v1/esp/devices` |
| Pending devices | `espStore.fetchPendingDevices()` | `GET /api/v1/esp/pending` |
| Cross-ESP rules | `logicStore.fetchRules()` | `GET /api/v1/logic/rules` |
| Component Sidebar | None (static config) | N/A |

### Live Updates (WebSocket)

The ESP store auto-initializes WebSocket on store creation (`esp.ts` Line 2041: `initWebSocket()`). Subscribed event types (Line 114-118):

| WebSocket Event | Handler | What It Updates | Store Location |
|-----------------|---------|-----------------|----------------|
| `esp_health` | `handleEspHealth()` (L1321) | Device status, uptime, heap, wifi_rssi, last_seen, offlineInfo | `devices[]` array element replacement |
| `sensor_data` | `handleSensorData()` (L1466) | Sensor raw_value, quality, unit, last_read, multi_values | `device.sensors[]` in-place mutation |
| `actuator_status` | `handleActuatorStatus()` (L1648) | Actuator state, pwm_value, last_command | `device.actuators[]` in-place mutation |
| `actuator_alert` | `handleActuatorAlert()` (L1424) | emergency_stopped flag, state=false | `device.actuators[]` in-place mutation |
| `config_response` | `handleConfigResponse()` (L1683) | Toast notifications, GPIO status refresh | Toast UI + `fetchGpioStatus()` |
| `zone_assignment` | `handleZoneAssignment()` (L1779) | Device zone_id, zone_name, master_zone_id | `devices[]` array element replacement |
| `sensor_health` | `handleSensorHealth()` (L1920) | Sensor is_stale, stale_reason, timeout info | `device.sensors[]` in-place mutation |
| `device_discovered` | `handleDeviceDiscovered()` (L1821) | Adds to pendingDevices list + toast | `pendingDevices[]` push |
| `device_approved` | `handleDeviceApproved()` (L1857) | Removes from pending, refreshes all devices | `pendingDevices[]` filter + `fetchAll()` |
| `device_rejected` | `handleDeviceRejected()` (L1882) | Removes from pending list + toast | `pendingDevices[]` filter |

Additionally, `logicStore.subscribeToWebSocket()` is called on mount (Line 65) for live logic execution updates displayed via the CrossEspConnectionOverlay.

### WebSocket Reconnect Behavior

On WebSocket reconnect, the store triggers a full REST refresh (`esp.ts` Lines 2013-2024):
```typescript
websocketService.onConnect(() => {
  fetchAll()  // Full refresh to sync state after reconnect
})
```

---

## 3. Status Indicators -- How Visualized

### ESPCard Status (Legacy, `ESPCard.vue`)

**Primary status badge** (Lines 676-685):
- **Online**: Green dot with pulse animation, label "Online", variant `success`
- **Offline**: Gray dot, label "Offline", variant `gray`
- **Error**: Red dot, label "Fehler", variant `danger`
- **Pending Approval**: Yellow dot, label "Wartet auf Freigabe", variant `warning`
- **Approved**: Blue dot, label "Freigegeben", variant `info`
- **Rejected**: Red dot, label "Abgelehnt", variant `danger`

**Left border status bar** (Lines 309-317):
- Purple (`--mock`) for online mock ESPs
- Cyan (`--real`) for online real ESPs
- Muted gray (`--offline`) for offline devices
- Yellow (`--warning`) for SAFE_MODE
- Red (`--error`) for ERROR state
- Pulsing red (`--emergency`) for emergency-stopped actuators
- Pulsing yellow (`--orphaned`) for orphaned mocks

**Secondary badges** (Lines 688-698):
- "Sicherheitsmodus" (warning) when `system_state === 'SAFE_MODE'`
- "Fehler" (danger) when `system_state === 'ERROR'`
- "Startet..." (info) for BOOT/WIFI_SETUP/MQTT_CONNECTING
- "E-STOP" (danger) when any actuator has `emergency_stopped`
- "Verwaist" (warning) for orphaned mock devices

**Offline card styling** (Line 991-993): `opacity: 0.7` on the entire card.

### ActionBar Status Pills (`ActionBar.vue`)

The ActionBar receives computed counts from DashboardView (Lines 107-131):
- `onlineCount`: `espStore.onlineDevices.length`
- `offlineCount`: `espStore.offlineDevices.length`
- `warningCount`: devices with `system_state === 'ERROR'` or any actuator `emergency_stopped`
- `safeModeCount`: devices with `system_state === 'SAFE_MODE'`
- `pendingCount`: `espStore.pendingCount` (pending approval devices)

Pills are clickable filters (multi-select via Set). Warning/SafeMode pills only appear when count > 0.

### Data Freshness Indicators (`ESPCard.vue` Lines 343-359)

Three-tier freshness system based on `last_heartbeat` / `last_seen`:
- **Live** (green, Radio icon): < 30 seconds old
- **Recent** (blue, Clock icon): < 2 minutes old
- **Stale** (yellow, TimerOff icon): > 2 minutes old
- **Unknown** (muted): no heartbeat received

### Data Source Indicator (`ESPCard.vue` Lines 326-340)

- **Live-Speicher** (MemoryStick icon, green): Mock ESP data from debug store (in-memory)
- **Datenbank** (Database icon, blue): Real ESP or orphaned mock data from PostgreSQL

---

## 4. Error Visualization

| Error Type | Visual Treatment | Location |
|------------|-----------------|----------|
| **Emergency Stop** | Red pulsing left border bar + "E-STOP" danger badge + actuator satellite dots pulsing red | ESPCard Lines 296-298, 696-698, 1668 |
| **System ERROR state** | Red left border + "Fehler" danger badge | ESPCard Lines 314, 275-276 |
| **Orphaned Mock** | Yellow pulsing border + "Verwaist" warning badge + inline warning message | ESPCard Lines 666-674, 858-863 |
| **Offline device** | 70% opacity on entire card + gray status bar + offline info line with reason icon | ESPCard Lines 991-993, 713-724 |
| **Offline reason (LWT)** | Red Zap icon + "Verbindung verloren" text + timestamp | ESPCard Lines 505-518, 713-724 |
| **Offline reason (timeout)** | Orange Clock icon + "Keine Antwort" text | ESPCard Lines 505-518 |
| **Offline reason (shutdown)** | Blue Power icon + "Heruntergefahren" text | ESPCard Lines 505-518 |
| **Incomplete data** | Yellow AlertTriangle icon + "Unvollstandig" label | ESPCard Lines 747-753 |
| **Sensor stale** | Updated via `sensor_health` WebSocket event, `is_stale` flag set on sensor | esp.ts Lines 1920-1978 |
| **Sensor quality** | Satellite dots colored: green (good/excellent), yellow (fair), red (poor/bad/emergency), gray (unknown) | ESPCard Lines 389-395 |
| **Config failure** | Toast notifications: success (green), partial_success (yellow), error (red), with up to 3 detail toasts for individual GPIO failures | esp.ts Lines 1683-1763 |
| **ActionBar problem banner** | Amber warning banner with AlertTriangle icon showing problem count message | ActionBar Lines 62-68, 130-136 |

---

## 5. Links/Navigation from Dashboard to Detail Views

| Trigger | Navigation Target | Mechanism | Location |
|---------|-------------------|-----------|----------|
| Click ESP ID link | `/?openSettings=${espId}` | RouterLink | ESPCard Line 652-657 |
| Click "Details" button | `/?openSettings=${espId}` | RouterLink | ESPCard Lines 869-875 |
| Click "Logs" button | `/system-monitor?tab=events&esp=${espId}&timeRange=1h` | RouterLink | ESPCard Lines 878-892 |
| Click device in UnassignedDropBar | `/?openSettings=${espId}` | RouterLink | UnassignedDropBar Lines 202-208 |
| Click Settings on ESPOrbitalLayout | Opens ESPSettingsPopover (in-page) | Event handler → popover | DashboardView Lines 318-325, 513-523 |
| Query param `?openSettings=ESP_ID` | Auto-opens ESPSettingsPopover | Watch on route.query | DashboardView Lines 77-104 |
| Redirect from `/devices/:espId` | `/?openSettings=${espId}` | Router redirect (implied) | DashboardView Line 96 |

The dashboard does NOT navigate to separate detail views. Instead, it opens the `ESPSettingsPopover` as an overlay. The `/system-monitor` link is the only true navigation away from the dashboard.

---

## 6. How the ESP Store Feeds Data to Dashboard Components

### Data Flow Architecture

```
REST API (initial)  ──┐
                      ├──> espStore.devices (ref<ESPDevice[]>)
WebSocket (live)    ──┘           │
                                  ├──> DashboardView computed properties
                                  │      ├── filteredEsps (type + status filters)
                                  │      ├── zoneGroups (groupDevicesByZone)
                                  │      ├── onlineCount / offlineCount / warningCount / safeModeCount
                                  │      └── problemMessage
                                  │
                                  ├──> ActionBar (props: counts, filters)
                                  ├──> ZoneGroup (props: devices per zone)
                                  │      └── ESPOrbitalLayout (props: single device)
                                  ├──> UnassignedDropBar (reads espStore.devices directly)
                                  └──> ESPSettingsPopover (props: selected device)
```

### Key Reactive Chains

1. **Device list**: `espStore.devices` (ref) -> `filteredEsps` (computed, applies type + status filters) -> `zoneGroups` (computed, groups by zone_id) -> rendered as `ZoneGroup` components.

2. **Status counts**: `espStore.onlineDevices` / `espStore.offlineDevices` (computed getters in store) -> DashboardView local computeds (`onlineCount`, `offlineCount`) -> passed as props to ActionBar.

3. **Warning/SafeMode counts**: Computed in DashboardView (Lines 111-131), iterating `espStore.devices` checking `system_state` and `actuators[].emergency_stopped`.

4. **WebSocket updates trigger reactivity**: The `handleEspHealth()` handler (esp.ts Line 1391) replaces the entire device object in the array (`devices.value[deviceIndex] = { ...device, ...updates }`) to ensure Vue reactivity triggers. Sensor/actuator handlers mutate in-place on sub-objects.

5. **Pending devices**: Separate `pendingDevices` ref in store, updated via WebSocket `device_discovered/approved/rejected` events.

6. **Zone grouping**: `useZoneDragDrop()` composable provides `groupDevicesByZone()` which reads from the filtered device list and groups by `zone_id` / `zone_name`.

### Store Initialization

The ESP store auto-initializes WebSocket handlers on store creation (esp.ts Line 2041):
```typescript
// Auto-initialize WebSocket handlers on store creation
initWebSocket()
```

This means WebSocket handlers are active from the moment any component imports `useEspStore()`, regardless of which view is mounted.

---

## 7. Refresh/Polling Mechanisms

| Mechanism | Trigger | What Happens | Location |
|-----------|---------|-------------|----------|
| **Initial load** | `onMounted()` | `fetchAll()`, `fetchPendingDevices()`, `fetchRules()` | DashboardView Lines 60-66 |
| **WebSocket live updates** | Server broadcasts | Individual device fields updated in-place or via object replacement | esp.ts Lines 1321-1898 |
| **WebSocket reconnect** | Connection re-established | Full `fetchAll()` to sync state | esp.ts Lines 2013-2024 |
| **After device creation** | Mock ESP created | `espStore.fetchAll()` | DashboardView Line 165 |
| **After device deletion** | Delete confirmed | Local array filter (no re-fetch needed) | esp.ts Line 879 |
| **After zone drop** | Drag-and-drop | `handleDeviceDrop()` calls `fetchAll()` internally | DashboardView Line 234 |
| **After device approval** | Pending device approved | `fetchAll()` to show newly approved device | esp.ts Line 725 |
| **Unknown device online** | WebSocket `esp_health` for unknown device_id | `fetchAll()` to discover new device | esp.ts Lines 1340-1346 |
| **After heartbeat trigger** | Manual Mock ESP heartbeat | `fetchDevice(deviceId)` for single device refresh | esp.ts Lines 932-933 |

### What is NOT present:
- **No periodic polling / setInterval**: The dashboard does not poll on a timer. All updates come through WebSocket events or user actions.
- **No pull-to-refresh**: No manual refresh button on the dashboard itself.
- **No visibility-based refresh**: No `document.visibilitychange` listener to refresh on tab focus.

### WebSocket Filter Configuration (esp.ts Lines 113-119)

The store subscribes to these WebSocket event types:
```typescript
types: [
  'esp_health', 'sensor_data', 'actuator_status', 'actuator_alert',
  'config_response', 'zone_assignment', 'sensor_health',
  'device_discovered', 'device_approved', 'device_rejected'
]
```

The `autoConnect: true` and `autoReconnect: true` options ensure the WebSocket connection is maintained.

---

## Summary

The dashboard is a fully reactive, WebSocket-driven view with no polling. Initial state is loaded via REST API on mount, then all subsequent updates arrive through 10 WebSocket event types handled in the ESP store. The store uses Vue reactivity (full object replacement for device-level changes, in-place mutation for sensor/actuator sub-objects) to propagate updates to all dashboard components through computed properties and props. The ActionBar provides filtering (status pills + type buttons), while ZoneGroup organizes devices spatially. Navigation to device details happens via the in-page ESPSettingsPopover rather than separate routes.
