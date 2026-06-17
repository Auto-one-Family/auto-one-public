# WebSocket Event System Analysis

> Generated: 2026-01-27 | Research-only document

---

## 1. Architecture Overview

The WebSocket system follows a three-layer pattern:

```
Server (FastAPI WebSocket)
    |
WebSocketService (Singleton)         -- El Frontend/src/services/websocket.ts
    |
useWebSocket (Composable)            -- El Frontend/src/composables/useWebSocket.ts
    |
Pinia Stores / Vue Components        -- El Frontend/src/stores/esp.ts (primary consumer)
```

---

## 2. WebSocket Service (`El Frontend/src/services/websocket.ts`)

### 2.1 Connection Establishment

| Property | Value | Line Reference |
|----------|-------|----------------|
| **Pattern** | Singleton (`WebSocketService.getInstance()`) | L:42-79 |
| **Endpoint** | `ws[s]://{host}/api/v1/ws/realtime/{client_id}?token={jwt}` | L:114-115 |
| **Dev Host** | `localhost:8000` | L:112 |
| **Prod Host** | `window.location.host` | L:112 |
| **Client ID** | `client_{timestamp}_{random9chars}` | L:84-86 |
| **Auth** | JWT access token as query parameter | L:93-98, L:115 |

### 2.2 Reconnect Strategy

| Property | Value | Line Reference |
|----------|-------|----------------|
| **Max Attempts** | 10 | L:48 |
| **Base Delay** | 1000ms | L:49 |
| **Max Delay** | 30000ms | L:50 |
| **Algorithm** | Exponential backoff with +/-10% jitter | L:258-265 |
| **Formula** | `min(1000 * 2^(attempt-1), 30000) +/- 10% jitter` | L:259-264 |
| **Token Refresh** | Automatic before reconnect if token expires within 60s | L:121-147, L:270-276 |
| **Tab Visibility** | Reconnects when tab becomes visible; reduces attempt counter by 2 | L:286-328 |
| **Normal Close** | Code 1000 does NOT trigger reconnect | L:201 |

### 2.3 Message Distribution (Two Mechanisms)

**Mechanism A: Filter-based Subscriptions** (L:391-435)
- `subscribe(filters, callback)` returns a subscription ID
- Messages are routed to all subscriptions whose filters match
- Filters support: `types[]`, `esp_ids[]`, `sensor_types[]`, `topicPattern` (regex)
- Matching is AND logic across filter fields; empty/missing field = match all

**Mechanism B: Type-based Listeners** (L:357-361, L:473-490)
- `on(type, callback)` registers a listener for a specific message type
- Returns an unsubscribe function
- Stored in `listeners: Map<string, Set<callback>>`
- Both mechanisms fire for every incoming message (L:354-361)

### 2.4 Server-side Subscriptions

When subscribing, the service sends a JSON message to the server (L:495-508):
```json
{ "action": "subscribe", "filters": { "types": [...], "esp_ids": [...] } }
```

Unsubscribe sends (L:513-526):
```json
{ "action": "unsubscribe", "filters": null }
```

### 2.5 Additional Features

| Feature | Details | Line Reference |
|---------|---------|----------------|
| **Rate Limit Monitoring** | Warns at >10 msg/sec (client-side only, no throttling) | L:370-386 |
| **Message Queue** | Max 1000 messages queued while disconnected; processed on connect | L:556-570 |
| **Pending Subscriptions** | Subscriptions made during `connecting` state are queued and sent after open | L:60-61, L:449-453, L:540-551 |
| **onConnect Callbacks** | Stores can register callbacks fired on each successful connection | L:600-620 |
| **Resubscribe on Reconnect** | All active subscriptions are re-sent to server | L:180-181, L:531-535 |

### 2.6 Connection States

```
disconnected → connecting → connected
                    ↓            ↓
                  error     disconnected (onclose)
                               ↓
                          scheduleReconnect (if code !== 1000)
```

Type: `'disconnected' | 'connecting' | 'connected' | 'error'` (L:36)

---

## 3. useWebSocket Composable (`El Frontend/src/composables/useWebSocket.ts`)

### 3.1 Purpose

Vue composable wrapper around the singleton service. Provides:
- Reactive state (`isConnected`, `lastMessage`, `messageCount`)
- Vue lifecycle integration (`onMounted`/`onUnmounted` cleanup)
- Local message handler registry per composable instance
- Status polling every 1 second (L:210-218)

### 3.2 Options

```typescript
interface UseWebSocketOptions {
  autoConnect?: boolean    // default: true (L:32)
  autoReconnect?: boolean  // default: true (L:33)
  filters?: WebSocketFilters
}
```

### 3.3 Dual Handler Registration

The `on()` method (L:153-174) registers the callback in TWO places:
1. Local `messageHandlers` map (composable-scoped)
2. Service-level `listeners` via `websocketService.on()`

Both are cleaned up when the returned unsubscribe function is called.

### 3.4 Lifecycle

- On creation: if `autoConnect`, calls `connect()` and starts status monitor (L:242-245)
- `onMounted`: starts status monitor if not already running (L:249-254)
- `onUnmounted`: calls `cleanup()` which stops monitor, clears handlers, unsubscribes (L:256-262)
- Does NOT disconnect the singleton service on unmount (other consumers may need it)

---

## 4. ESP Store WebSocket Integration (`El Frontend/src/stores/esp.ts`)

### 4.1 Subscription Setup

The store subscribes to these event types on creation (L:110-120):

```typescript
const ws = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
  filters: {
    types: [
      'esp_health', 'sensor_data', 'actuator_status', 'actuator_alert',
      'config_response', 'zone_assignment', 'sensor_health',
      'device_discovered', 'device_approved', 'device_rejected'
    ]
  }
})
```

### 4.2 Handler Registration (L:1992-2027)

`initWebSocket()` is called automatically on store creation. It registers 10 type-specific handlers plus 1 onConnect callback:

| Event Type | Handler Function | Line | Purpose |
|------------|-----------------|------|---------|
| `esp_health` | `handleEspHealth` | L:1321-1418 | Update device status, last_seen, heap, RSSI, GPIO status, offline info |
| `sensor_data` | `handleSensorData` | L:1466-1500 | Update sensor values (single, known multi-value, dynamic multi-value) |
| `actuator_status` | `handleActuatorStatus` | L:1648-1673 | Update actuator state/PWM/emergency |
| `actuator_alert` | `handleActuatorAlert` | L:1424-1455 | Set emergency_stopped flag on safety violations |
| `config_response` | `handleConfigResponse` | L:1683-1763 | Toast notifications for config success/partial/error; refresh GPIO status |
| `zone_assignment` | `handleZoneAssignment` | L:1779-1811 | Update device zone_id/zone_name/master_zone_id |
| `sensor_health` | `handleSensorHealth` | L:1920-1979 | Update sensor stale status (timeout violations) |
| `device_discovered` | `handleDeviceDiscovered` | L:1821-1851 | Add to pending devices list; toast notification |
| `device_approved` | `handleDeviceApproved` | L:1857-1876 | Remove from pending; refresh device list |
| `device_rejected` | `handleDeviceRejected` | L:1882-1898 | Remove from pending; toast notification |
| *(onConnect)* | anonymous | L:2016-2023 | Refresh all ESP data via `fetchAll()` on every (re)connect |

### 4.3 Cleanup

`cleanupWebSocket()` (L:2033-2038) calls all stored unsubscribe functions and disconnects the composable.

---

## 5. All WebSocket Message Types and Payloads

### 5.1 Defined MessageType Union (`El Frontend/src/types/index.ts` L:356-375)

| MessageType | Server Source | Subscribed in ESP Store |
|-------------|---------------|------------------------|
| `sensor_data` | `sensor_handler.py` | Yes |
| `actuator_status` | `actuator_handler.py` | Yes |
| `actuator_response` | `actuator_response_handler.py` | No |
| `actuator_alert` | `actuator_alert_handler.py` | Yes |
| `esp_health` | `heartbeat_handler.py` | Yes |
| `sensor_health` | `maintenance/jobs/sensor_health.py` | Yes |
| `config_response` | `config_handler.py` | Yes |
| `zone_assignment` | `zone_ack_handler.py` | Yes |
| `device_discovered` | Discovery Phase | Yes |
| `device_approved` | Discovery Phase | Yes |
| `device_rejected` | Discovery Phase | Yes |
| `device_rediscovered` | Discovery Phase | No (defined but unused) |
| `logic_execution` | Logic Engine | No (future use) |
| `system_event` | System | No (future use) |

### 5.2 Payload Structures

**`esp_health`** (L:1321-1418)
```json
{
  "esp_id": "ESP_12AB34CD",
  "status": "online" | "offline",
  "timestamp": 1735818000,
  "last_seen": "2026-01-27T...",
  "uptime": 3600,
  "heap_free": 98304,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 2,
  "name": "My ESP",
  "source": "lwt" | "heartbeat_timeout" | "api",
  "reason": "shutdown" | "heartbeat_timeout",
  "gpio_status": [{ "gpio": 4, "owner": "sensor", "component": "DS18B20", "safe": false }]
}
```

**`sensor_data`** (L:1466-1500)
```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 34,
  "sensor_type": "temperature",
  "value": 25.4,
  "unit": "C",
  "quality": "good",
  "timestamp": 1735818000
}
```

**`actuator_status`** (L:1648-1673)
```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 12,
  "state": "on" | "off" | "pwm",
  "value": 0.75,
  "emergency": "normal" | "emergency_stop",
  "timestamp": 1735818000
}
```

**`actuator_alert`** (L:1424-1455)
```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 12,
  "alert_type": "emergency_stop" | "runtime_protection" | "safety_violation"
}
```

**`config_response`** (L:1683-1763)
```json
{
  "esp_id": "ESP_12AB34CD",
  "status": "success" | "partial_success" | "error",
  "config_type": "sensor",
  "count": 3,
  "failed_count": 1,
  "message": "...",
  "error_code": "CONFIG_ERROR",
  "failures": [{ "gpio": 4, "type": "sensor", "error": "...", "detail": "..." }],
  "failed_item": { "gpio": 4, "sensor_type": "..." }
}
```

**`zone_assignment`** (L:1779-1811)
```json
{
  "esp_id": "ESP_12AB34CD",
  "status": "zone_assigned" | "error",
  "zone_id": "zelt_1",
  "zone_name": "Zelt 1",
  "master_zone_id": "...",
  "timestamp": 1735818000,
  "message": "..."
}
```

**`sensor_health`** (L:1920-1979)
```json
{
  "esp_id": "ESP_12AB34CD",
  "gpio": 34,
  "sensor_type": "temperature",
  "sensor_name": "Temp 1",
  "is_stale": true,
  "stale_reason": "timeout_exceeded" | "no_data" | "sensor_error",
  "last_reading_at": "2026-01-27T...",
  "timeout_seconds": 180,
  "seconds_overdue": 42,
  "operating_mode": "continuous",
  "config_source": "...",
  "timestamp": 1735818000
}
```

**`device_discovered`** (L:1821-1851)
```json
{
  "device_id": "ESP_12AB34CD",
  "discovered_at": "2026-01-27T...",
  "ip_address": "192.168.1.100",
  "heap_free": 98304,
  "wifi_rssi": -45,
  "sensor_count": 0,
  "actuator_count": 0,
  "hardware_type": "esp32_dev"
}
```

**`device_approved`** (L:1857-1876)
```json
{
  "device_id": "ESP_12AB34CD",
  "approved_by": "admin"
}
```

**`device_rejected`** (L:1882-1898)
```json
{
  "device_id": "ESP_12AB34CD",
  "rejection_reason": "..."
}
```

---

## 6. Data Flow Summary

```
1. Server MQTT handler receives ESP32 message
2. Server broadcasts via WebSocket: { type, timestamp, data }
3. WebSocketService.handleMessage() parses JSON
4. Message routed via:
   a) routeMessage() → filter-matching subscriptions (callback)
   b) listeners.get(type) → type-specific listeners (callback)
5. ESP Store handler updates reactive Pinia state (devices[])
6. Vue components re-render via computed properties
```

Key design decision: The ESP store replaces entire device objects (spread + reassign to array index) rather than mutating properties directly, to ensure Vue reactivity triggers reliably (noted at L:1349-1350, L:1390-1404, L:1797-1804).
