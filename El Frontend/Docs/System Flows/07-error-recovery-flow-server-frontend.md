# Error Recovery Flow - Server & Frontend Perspektive

## Overview

Wie Server und Frontend auf Fehler, Verbindungsabbrüche, ESP-Offline-Szenarien und Recovery-Mechanismen reagieren. Diese Dokumentation beschreibt die zentralen Error-Recovery-Mechanismen aus Server- und Frontend-Perspektive.

**Korrespondiert mit:** `El Trabajante/docs/system-flows/07-error-recovery-flow.md`

> **ESP32-Seite:** Für ESP32-interne Error-Recovery (Circuit Breaker, WiFi/MQTT Reconnection,
> Safe-Mode, Error Tracking) siehe die korrespondierende ESP32-Dokumentation.

---

## Voraussetzungen

- [ ] Server läuft (`localhost:8000`)
- [ ] Frontend läuft (`localhost:5173`)
- [ ] MQTT Broker erreichbar (Mosquitto auf Port 1883)
- [ ] WebSocket-Endpoint aktiv (`/api/v1/ws/realtime`)
- [ ] Mindestens ein ESP32 registriert

---

## Teil 1: Heartbeat-System & ESP Offline Detection

### 1.1 ESP32 Heartbeat-Verhalten

**Konfiguration (aus ESP32-Code):**

| Parameter | Wert | Code-Location |
|-----------|------|---------------|
| **Intervall** | 60 Sekunden | `mqtt_client.h:108` - `HEARTBEAT_INTERVAL_MS = 60000` |
| **QoS** | 0 | Heartbeat benötigt keine garantierte Zustellung |
| **Topic** | `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` | `topic_builder.cpp:108-111` |

**Heartbeat Payload (ESP32 → Server):**

```json
{
  "esp_id": "ESP_12AB34CD",
  "zone_id": "zone_main",
  "master_zone_id": "master",
  "zone_assigned": true,
  "ts": 1735818000,
  "uptime": 123456,
  "heap_free": 45000,
  "wifi_rssi": -45,
  "sensor_count": 3,
  "actuator_count": 2
}
```

**Felder:**
| Feld | Typ | Required | Beschreibung |
|------|-----|----------|--------------|
| `esp_id` | string | Optional | ESP-ID (auch im Topic enthalten) |
| `ts` | int | **Required** | Unix-Timestamp (Sekunden oder Millisekunden - automatisch erkannt) |
| `uptime` | int | **Required** | Betriebszeit in Sekunden |
| `heap_free` | int | **Required** | Freier Heap-Speicher in Bytes |
| `wifi_rssi` | int | **Required** | WiFi-Signalstärke in dBm |
| `sensor_count` | int | Optional | Anzahl aktiver Sensoren |
| `actuator_count` | int | Optional | Anzahl aktiver Aktoren |
| `zone_id` | string | Optional | Zone-ID |
| `zone_assigned` | bool | Optional | Zone zugewiesen? |

> **Kompatibilität:** Server akzeptiert sowohl `heap_free` (ESP32 v4.0+) als auch `free_heap` (Legacy).

---

### 1.2 Server Heartbeat-Empfang

**Code-Location:** `src/mqtt/handlers/heartbeat_handler.py`

**Heartbeat-Handler Flow:**

```
┌─────────────────────────────────────────────────────────────┐
│                  Heartbeat Handler Flow                      │
└─────────────────────────────────────────────────────────────┘

ESP32                          Server                    Database
  │                              │                          │
  │──── Heartbeat ─────────────►│                          │
  │     (alle 60s)               │                          │
  │                              │                          │
  │                              │── Step 1: Parse Topic ───│
  │                              │   TopicBuilder.parse_    │
  │                              │   heartbeat_topic()      │
  │                              │   → esp_id extrahieren   │
  │                              │                          │
  │                              │── Step 2: Validate ──────│
  │                              │   Payload                │
  │                              │   - ts (required)        │
  │                              │   - uptime (required)    │
  │                              │   - heap_free (required) │
  │                              │   - wifi_rssi (required) │
  │                              │                          │
  │                              │── Step 3: ESP Lookup ───►│
  │                              │   esp_repo.get_by_       │
  │                              │   device_id()            │
  │                              │                          │
  │                              │◄── ESP Found/Not Found ──│
  │                              │                          │
  │                    ┌─────────┴─────────┐                │
  │                    │                   │                │
  │             ESP Found            ESP Not Found          │
  │                    │                   │                │
  │                    ▼                   ▼                │
  │           ┌───────────────┐  ┌─────────────────────┐   │
  │           │ Step 5: Update│  │ REJECT: Unknown ESP │   │
  │           │ - status=     │  │ Log warning +       │   │
  │           │   "online"    │  │ return False        │   │
  │           │ - last_seen=  │  │ (Auto-Discovery     │   │
  │           │   now()       │  │  deaktiviert)       │   │
  │           └───────┬───────┘  └─────────────────────┘   │
  │                   │                                     │
  │                   ▼                                     │
  │           ┌───────────────┐                            │
  │           │ Step 6: Update│                            │
  │           │ Metadata      │                            │
  │           │ - zone_id     │                            │
  │           │ - health data │                            │
  │           └───────┬───────┘                            │
  │                   │                                     │
  │                   ▼                                     │
  │           ┌───────────────┐                            │
  │           │ Step 7: Log   │                            │
  │           │ Health Metrics│                            │
  │           │ - Low memory? │                            │
  │           │ - Weak WiFi?  │                            │
  │           └───────┬───────┘                            │
  │                   │                                     │
  │                   ▼                                     │
  │           ┌───────────────────────────────────────┐    │
  │           │ Step 8: WebSocket Broadcast           │    │
  │           │ ws_manager.broadcast("esp_health",    │───►│ Frontend
  │           │   {esp_id, status, heap_free, ...})   │    │
  │           └───────────────────────────────────────┘    │
```

**Wichtige Code-Stellen:**

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `handle_heartbeat()` | 55-177 | Hauptlogik |
| `_validate_payload()` | 303-376 | Payload-Validierung |
| `_update_esp_metadata()` | 258-301 | Metadata-Update |
| `_log_health_metrics()` | 449-489 | Health-Logging mit Warnungen |
| `_detect_device_source()` | 378-447 | Device-Source-Detection für Logging |
| `check_device_timeouts()` | 491-540 | Periodic Timeout-Check |

**Neue Features:**
- **Auto-Discovery DISABLED:** Sicherheit - ESPs müssen manuell registriert werden
- **Device Source Detection:** Erkennt Mock/Test/Production Devices für Logging
- **Structured Error Codes:** Detaillierte Fehlerklassifizierung

**Health-Warnungen:**
- `heap_free < 10000`: Low memory warning
- `wifi_rssi < -70`: Weak WiFi signal warning
- `error_count > 0`: Device reported errors

---

### 1.3 Offline-Detection

**Server Offline-Threshold Konfiguration:**

| Parameter | Wert | Code-Location |
|-----------|------|---------------|
| **Heartbeat Timeout** | 300 Sekunden (5 Minuten) | `heartbeat_handler.py:37` - `HEARTBEAT_TIMEOUT_SECONDS = 300` |
| **Check Device Status Threshold** | 120 Sekunden (Default) | `esp_service.py:213` - `offline_threshold_seconds: int = 120` |
| **Konfigurierbar via Config** | Ja | `core/config.py:194` - `heartbeat_timeout: int = Field(default=120)` |

**ESP Service `check_device_status()` (Zeilen 211-250):**

```python
async def check_device_status(
    self,
    offline_threshold_seconds: int = 120,
) -> Dict[str, List[str]]:
    """
    Check all device statuses and mark offline devices.

    Args:
        offline_threshold_seconds: Seconds since last_seen to mark offline (default: 120)

    Returns:
        {
            "online": ["ESP_12AB34CD", ...],
            "offline": ["ESP_DEADBEEF", ...],
            "newly_offline": ["ESP_DEADBEEF", ...]  # Status changed this check
        }
    """
```

**Logik:**
1. Hole alle ESPs aus der Datenbank
2. Für jedes ESP: Prüfe `(now - last_seen) < threshold`
3. Falls `last_seen` älter als Threshold:
   - Setze `status = "offline"`
   - Füge zu `newly_offline` Liste hinzu (falls vorher "online")
   - Log warning
4. Returniere Status-Listen

---

### 1.4 Heartbeat Timeout Check

**Code-Location:** `heartbeat_handler.py:415-464`

```python
async def check_device_timeouts(self) -> dict:
    """
    Check for devices that haven't sent heartbeat recently.
    Marks devices as offline if last_seen > HEARTBEAT_TIMEOUT_SECONDS (300s).

    Returns:
        {
            "checked": int,      # Anzahl geprüfter Online-Devices
            "timed_out": int,    # Anzahl neu-offline markierter Devices
            "offline_devices": [str]  # Liste der offline ESP-IDs
        }
    """
```

**⚠️ LÜCKE: Periodic Health-Check Task**

**Problem:** Es existiert kein Background-Task, der `check_device_timeouts()` periodisch aufruft.

**Impact:**
- ESP-Offline-Status wird nur bei explizitem API-Aufruf aktualisiert
- Frontend muss Polling verwenden für aktuellen Status

**Vorgeschlagene Implementierung:**

In `main.py` nach WebSocket-Initialisierung (nach Zeile 188) hinzufügen:

```python
# Start periodic health check task
import asyncio

async def periodic_health_check():
    """Background task to check ESP device timeouts every 30 seconds."""
    from .mqtt.handlers.heartbeat_handler import get_heartbeat_handler
    handler = get_heartbeat_handler()

    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        try:
            result = await handler.check_device_timeouts()
            if result["timed_out"] > 0:
                logger.warning(f"Devices timed out: {result['offline_devices']}")

                # Broadcast status change to frontend
                ws_manager = await WebSocketManager.get_instance()
                for esp_id in result["offline_devices"]:
                    await ws_manager.broadcast("esp_health", {
                        "esp_id": esp_id,
                        "status": "offline",
                        "reason": "heartbeat_timeout"
                    })
        except Exception as e:
            logger.error(f"Health check error: {e}")

# Create background task
asyncio.create_task(periodic_health_check())
```

**Geschätzter Aufwand:** 1 Stunde

---

## Teil 2: Server MQTT Connection Recovery

### 2.1 MQTT Client Architektur

**Code-Location:** `src/mqtt/client.py`

**Architektur:**

```
┌─────────────────────────────────────────────────────────────┐
│                    MQTTClient (Singleton)                    │
├─────────────────────────────────────────────────────────────┤
│ Features:                                                    │
│ - Paho-MQTT Wrapper                                         │
│ - TLS/SSL Support                                           │
│ - Auto-Reconnect mit Exponential Backoff                    │
│ - Connection State Management                               │
│ - Thread-safe Operations                                    │
│ - Circuit Breaker Integration (Resilienz)                  │
│ - Offline Buffer (Graceful Degradation)                     │
│ - Rate-Limiting für Disconnect Logs                         │
├─────────────────────────────────────────────────────────────┤
│ Instanz holen:                                              │
│   client = MQTTClient.get_instance()                        │
│   client.connect()                                          │
│   client.subscribe("topic/pattern", callback)               │
│   client.publish("topic", payload, qos=1)                   │
└─────────────────────────────────────────────────────────────┘
```

**Wichtige Attribute:**

| Attribut | Typ | Default | Beschreibung |
|----------|-----|---------|--------------|
| `connected` | bool | False | Aktueller Verbindungsstatus |
| `reconnect_delay` | int | 1 | Aktuelle Reconnect-Verzögerung (Sekunden) |
| `max_reconnect_delay` | int | 60 | Maximale Reconnect-Verzögerung |
| `_circuit_breaker` | CircuitBreaker | None | Circuit Breaker für MQTT-Operationen |
| `_offline_buffer` | MQTTOfflineBuffer | None | Buffer für Offline-Nachrichten |

**Neue Resilience-Features:**

- **Circuit Breaker:** Verhindert MQTT-Publishes bei anhaltenden Fehlern, aktiviert Offline-Buffer
- **Offline Buffer:** Speichert Nachrichten bei Verbindungsunterbrechung für späteren Versand
- **Rate-Limiting:** Begrenzt Disconnect-Log-Spam auf max. 1 Meldung pro 60 Sekunden

---

### 2.2 Auto-Reconnect Mechanismus

**Konfiguration (Zeilen 133-136):**

```python
# Configure auto-reconnect with exponential backoff
# Min delay: 1s, Max delay: 60s
self.client.reconnect_delay_set(min_delay=1, max_delay=60)
```

**Exponential Backoff Sequenz:**
- Versuch 1: 1s
- Versuch 2: 2s
- Versuch 3: 4s
- Versuch 4: 8s
- Versuch 5: 16s
- Versuch 6: 32s
- Versuch 7+: 60s (Maximum)

**Connection Timeout:** 10 Sekunden (Zeilen 145-156)

---

### 2.3 Connection Events

**`_on_connect` Callback (Zeilen 456-494):**

```python
def _on_connect(self, client, userdata, flags, rc):
    if rc == 0:
        self.connected = True
        self.reconnect_delay = 1  # Reset reconnect delay
        # Reset rate-limiting on successful connect
        with self._disconnect_lock:
            self._last_disconnect_log_time = 0.0
            self._disconnect_suppressed_count = 0
        logger.info(f"MQTT connected with result code: {rc}")

        # Reset circuit breaker on successful connection
        if self._circuit_breaker:
            self._circuit_breaker.reset()
            logger.info("[resilience] MQTT CircuitBreaker reset on connect")

        # Auto re-subscribe to all topics if this is a reconnection
        if self._subscriber and hasattr(self._subscriber, 'subscribe_all'):
            logger.info("Reconnected to MQTT broker - re-subscribing to all topics...")
            try:
                self._subscriber.subscribe_all()
                logger.info("Re-subscription complete")
            except Exception as e:
                logger.error(f"Failed to re-subscribe after reconnect: {e}", exc_info=True)

        # Flush offline buffer on reconnect
        if self._offline_buffer and not self._offline_buffer.is_empty:
            asyncio.create_task(self._flush_offline_buffer())
    else:
        self.connected = False
        # Error handling mit Reason-Codes
```

**Error-Codes bei Connection-Failure:**

| RC | Bedeutung |
|----|-----------|
| 0 | Erfolgreiche Verbindung |
| 1 | Connection refused - incorrect protocol version |
| 2 | Connection refused - invalid client identifier |
| 3 | Connection refused - server unavailable |
| 4 | Connection refused - bad username or password |
| 5 | Connection refused - not authorized |

**`_on_disconnect` Callback (Zeilen 321-350):**

```python
def _on_disconnect(self, client, userdata, rc):
    self.connected = False

    if rc == 0:
        logger.info("MQTT client disconnected: Clean disconnect")
    else:
        logger.warning(
            f"MQTT client disconnected unexpectedly: {reason}. "
            "Auto-reconnect will attempt to restore connection..."
        )
```

> **Wichtig:** Paho-MQTT handhabt Auto-Reconnect automatisch via `loop_start()`.
> Nach erfolgreichem Reconnect werden Subscriptions automatisch wiederhergestellt.

---

### 2.4 MQTT Reconnection Flow Diagramm

```
┌─────────────────────────────────────────────────────────────┐
│              MQTT Client Reconnection Flow                   │
└─────────────────────────────────────────────────────────────┘

     CONNECTED                    DISCONNECTED
         │                             │
         │◄──── on_disconnect ─────────┤ (rc != 0)
         │      Unexpected disconnect  │
         │                             │
         │                    ┌────────▼────────┐
         │                    │ Paho-MQTT       │
         │                    │ Auto-Reconnect  │
         │                    │ (loop_start)    │
         │                    └────────┬────────┘
         │                             │
         │                    ┌────────▼────────┐
         │                    │ Wait: min_delay │
         │                    │ (initial: 1s)   │
         │                    └────────┬────────┘
         │                             │
         │                    ┌────────▼────────┐
         │                    │ Reconnect       │
         │                    │ Attempt         │
         │                    └────────┬────────┘
         │                             │
         │              ┌──────────────┴──────────────┐
         │              │                              │
         │       Success│                       Failure│
         │              │                              │
         │              ▼                              ▼
         │     ┌────────────────┐           ┌────────────────┐
         │     │ on_connect     │           │ delay *= 2     │
         │     │ (rc = 0)       │           │ (max: 60s)     │
         │     │                │           └────────┬───────┘
         │     │ - connected =  │                    │
         │     │   True         │           ┌────────▼────────┐
         │◄────│   to 1s        │           │ Wait & Retry    │
         │     │ - Reset delay  │           │ (Exponential    │
         │     │   to 1s        │           │  Backoff)       │
         │     │ - Circuit      │           └─────────────────┘
         │     │   Breaker      │
         │     │   reset        │
         │     │ - Auto re-     │
         │     │   subscribe    │
         │     │ - Flush        │
         │     │   offline      │
         │     │   buffer       │
         │     └────────────────┘
```

---

## Teil 3: WebSocket Connection Management

### 3.1 WebSocket Manager Architektur

**Code-Location:** `src/websocket/manager.py`

**Architektur:**

```python
class WebSocketManager:
    """
    WebSocket Manager (Singleton).

    Manages WebSocket connections, broadcasts real-time updates.
    Thread-safe for MQTT callback invocations.
    """

    _instance: Optional["WebSocketManager"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}      # {client_id: WebSocket}
        self._subscriptions: Dict[str, Dict] = {}         # {client_id: {filters}}
        self._rate_limiter: Dict[str, deque] = {}         # Rate limiting
        self._lock = asyncio.Lock()                       # Thread-safe
        self._rate_limit_window = timedelta(seconds=1)    # 1 second window
        self._rate_limit_max = 10                         # Max 10 msg/sec
```

**Wichtige Methoden:**

| Methode | Zeilen | Beschreibung |
|---------|--------|--------------|
| `get_instance()` | 40-52 | Singleton-Getter (async) |
| `connect()` | 73-86 | WebSocket akzeptieren + registrieren |
| `disconnect()` | 88-106 | WebSocket schließen + aufräumen |
| `subscribe()` | 108-125 | Client für Message-Types registrieren |
| `broadcast()` | 156-217 | Nachricht an alle passenden Clients senden |
| `broadcast_threadsafe()` | 219-238 | Thread-safe für MQTT-Callbacks |

---

### 3.2 Connection Lifecycle

**Connect (Zeilen 73-86):**
```python
async def connect(self, websocket: WebSocket, client_id: str) -> None:
    async with self._lock:
        await websocket.accept()
        self._connections[client_id] = websocket
        self._subscriptions[client_id] = {}
        self._rate_limiter[client_id] = deque()
        logger.info(f"WebSocket client connected: {client_id}")
```

**Disconnect (Zeilen 88-106):**
```python
async def disconnect(self, client_id: str) -> None:
    async with self._lock:
        if client_id in self._connections:
            websocket = self._connections[client_id]
            try:
                await websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket for {client_id}: {e}")

            del self._connections[client_id]
            self._subscriptions.pop(client_id, None)
            self._rate_limiter.pop(client_id, None)
```

---

### 3.3 Broadcast System

**`broadcast()` Methode (Zeilen 156-217):**

1. Erstellt Message mit Type, Timestamp, Data
2. Filtert Clients basierend auf Subscriptions:
   - `types`: Message-Typ-Filter
   - `esp_ids`: ESP-ID-Filter
   - `sensor_types`: Sensor-Typ-Filter
3. Prüft Rate-Limit pro Client (10 msg/sec)
4. Sendet an alle passenden Clients
5. Räumt disconnected Clients auf

**`broadcast_threadsafe()` Methode (Zeilen 219-238):**

```python
def broadcast_threadsafe(
    self, message_type: str, data: dict, filters: Optional[dict] = None
) -> None:
    """
    Thread-safe broadcast for MQTT callback invocations.
    Can be called from non-asyncio threads (e.g., MQTT callbacks).
    """
    if self._loop and self._loop.is_running():
        asyncio.run_coroutine_threadsafe(
            self.broadcast(message_type, data, filters),
            self._loop
        )
```

> **Wichtig:** MQTT-Handler verwenden `await ws_manager.broadcast()` direkt,
> da sie bereits in einem async Context laufen.

---

### 3.4 Event-Types & WebSocket Broadcasts

| Event-Type | Handler | Status | Payload-Struktur |
|------------|---------|--------|------------------|
| `sensor_data` | `sensor_handler.py` | ✅ Implementiert | `{esp_id, gpio, sensor_type, value, raw_value, unit, quality, ts}` |
| `actuator_status` | `actuator_handler.py` | ✅ Implementiert | `{esp_id, gpio, actuator_type, state, current_value, ts}` |
| `actuator_response` | `actuator_response_handler.py` | ✅ Implementiert | `{esp_id, gpio, command, success, message, ts}` |
| `actuator_alert` | `actuator_alert_handler.py:174-188` | ✅ Implementiert | `{esp_id, gpio, alert_type, severity, message, zone_id, ts}` |
| `esp_health` | `heartbeat_handler.py:148-163` | ✅ Implementiert | `{esp_id, status, heap_free, wifi_rssi, uptime, sensor_count, actuator_count, ts}` |
| `config_response` | `config_handler.py:154-177` | ✅ Implementiert | `{esp_id, config_type, status, count, message, error_code?, error_description?, failed_item?}` |

**Rate-Limiting (Zeilen 240-269):**

```python
def _check_rate_limit(self, client_id: str) -> bool:
    """
    Check if client exceeds rate limit (10 msg/sec).
    Uses sliding window algorithm with deque.
    """
    # Sliding window: Remove timestamps older than 1 second
    # Check if current count >= 10
    # Return False if exceeded
```

---

## Teil 4: Safety Service & Emergency Stop

### 4.1 Safety Service Integration

**Code-Location:** `src/services/safety_service.py`

**Architektur:**

```python
class SafetyService:
    """
    Safety validation for actuator commands.
    Validates commands before execution, handles emergency stops.
    Thread-safe for MQTT callback invocations.
    """

    def __init__(self, actuator_repo, esp_repo):
        self.actuator_repo = actuator_repo
        self.esp_repo = esp_repo
        self._emergency_stop_active: dict[str, bool] = {}  # {esp_id: bool}
        self._lock = asyncio.Lock()
```

**Emergency States (Zeilen 18-31):**

```python
class EmergencyState(Enum):
    """Matches ESP32 EmergencyState in actuator_types.h"""
    NORMAL = "normal"      # Normalbetrieb
    ACTIVE = "active"      # Emergency Stop aktiv
    CLEARING = "clearing"  # Emergency wird aufgehoben
    RESUMING = "resuming"  # Betrieb wird fortgesetzt
```

**Wichtige Methoden:**

| Methode | Zeilen | Beschreibung |
|---------|--------|--------------|
| `validate_actuator_command()` | 84-128 | Validiert Command vor Ausführung |
| `check_safety_constraints()` | 130-213 | Prüft Actuator-Constraints |
| `emergency_stop_all()` | 215-223 | Globaler Emergency-Stop |
| `emergency_stop_esp()` | 225-234 | ESP-spezifischer Emergency-Stop |
| `clear_emergency_stop()` | 236-251 | Emergency-Stop aufheben |
| `is_emergency_stop_active()` | 253-264 | Status abfragen |

---

### 4.2 Emergency Stop Flow

**REST API Endpoint:** `POST /api/v1/actuators/emergency_stop`

**Code-Location:** `src/api/v1/actuators.py:515-648` (Emergency Stop Endpoints)

**Flow Diagramm:**

```
┌─────────────────────────────────────────────────────────────┐
│                   Emergency Stop Flow                        │
└─────────────────────────────────────────────────────────────┘

[Trigger]                    Server                     ESP32
    │                          │                          │
    ├─► REST API ─────────────►│                          │
    │   POST /api/v1/          │                          │
    │   actuators/emergency_   │                          │
    │   stop                   │                          │
    │   {esp_id?, reason}      │                          │
    │                          │                          │
    │                          │── Validate Request ──────│
    │                          │                          │
    │                          │── SafetyService.         │
    │                          │   emergency_stop_all()   │
    │                          │   or emergency_stop_esp()│
    │                          │                          │
    │                          │── MQTT Publish ─────────►│
    │                          │   Topic varies:          │
    │                          │                          │
    │                          │   Global:                │
    │                          │   kaiser/broadcast/      │
    │                          │   emergency              │
    │                          │                          │
    │                          │   ESP-specific:          │
    │                          │   kaiser/{kaiser_id}/    │
    │                          │   esp/{esp_id}/actuator/ │
    │                          │   emergency              │
    │                          │                          │
    │                          │   Payload:               │
    │                          │   {"action": "stop",     │
    │                          │    "reason": "..."}      │
    │                          │                          │
    │                          │                     ┌────▼────┐
    │                          │                     │ ESP32:  │
    │                          │                     │ E-Stop  │
    │                          │                     │ All     │
    │                          │                     │Actuators│
    │                          │                     │→ STATE_ │
    │                          │                     │  OFF    │
    │                          │                     └────┬────┘
    │                          │                          │
    │                          │◄─── Alert ───────────────│
    │                          │     Topic:               │
    │                          │     kaiser/.../actuator/ │
    │                          │     {gpio}/alert         │
    │                          │                          │
    │                          │     {alert_type:         │
    │                          │      "emergency_stop",   │
    │                          │      message: "...",     │
    │                          │      gpio: 255}          │
    │                          │                          │
    │                          │── DB Update ─────────────│
    │                          │   actuator_state = OFF   │
    │                          │                          │
    │                          │── WebSocket Broadcast ──►│ (Frontend)
    │                          │   "actuator_alert"       │
    │                          │   severity: "critical"   │
```

---

### 4.3 Actuator Alert Handler

**Code-Location:** `src/mqtt/handlers/actuator_alert_handler.py`

**Alert Types (Zeilen 19-27):**

| Alert Type | Severity | Beschreibung |
|------------|----------|--------------|
| `emergency_stop` | **critical** | Manueller oder automatischer E-Stop |
| `runtime_protection` | warning | Actuator hat max. Laufzeit überschritten |
| `safety_violation` | **critical** | Safety-Constraint verletzt |
| `hardware_error` | error | Hardware-Fehlfunktion erkannt |

**Severity Mapping (Zeilen 44-49):**

```python
ALERT_SEVERITY = {
    "emergency_stop": "critical",
    "runtime_protection": "warning",
    "safety_violation": "critical",
    "hardware_error": "error",
}
```

**Handler Flow (Zeilen 66-197):**

1. Validate Payload (ts, esp_id, gpio, alert_type required)
2. Log mit entsprechendem Level (critical/error/warning)
3. Convert ESP32 Timestamp (auto-detect millis vs seconds)
4. Lookup ESP device
5. Log to command history
6. Update actuator state (if emergency/safety alert)
7. WebSocket broadcast to frontend

---

## Teil 5: Frontend Error Handling & Recovery

### 5.1 API Error Handling

**Code-Location:** `src/api/index.ts`

**Axios Interceptor Konfiguration:**

```typescript
// Request interceptor - add auth token (Zeilen 14-28)
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore()
    const token = authStore.accessToken
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  }
)

// Response interceptor - handle token refresh (Zeilen 31-71)
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    // Skip interceptor for auth endpoints (prevent infinite loop)
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/refresh') ||
                           originalRequest?.url?.includes('/auth/login') ||
                           originalRequest?.url?.includes('/auth/setup')

    // If 401 and not already retrying, try token refresh
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true
      try {
        await authStore.refreshTokens()
        // Retry original request with new token
        return api(originalRequest)
      } catch (refreshError) {
        // Refresh failed, logout user
        authStore.clearAuth()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  }
)
```

**Timeout:** 30 Sekunden (Zeile 7)

---

### 5.2 Auth Error Recovery

**Code-Location:** `src/stores/auth.ts`

**Token-Refresh-Mechanismus (Zeilen 104-119):**

```typescript
async function refreshTokens(): Promise<void> {
  if (!refreshToken.value) {
    throw new Error('No refresh token available')
  }

  try {
    const response = await authApi.refresh(refreshToken.value)
    setTokens(response.tokens.access_token, response.tokens.refresh_token)
    user.value = await authApi.me()
  } catch (err) {
    clearAuth()
    throw err
  }
}
```

**Auth-Check beim Start (Zeilen 24-63):**

```typescript
async function checkAuthStatus(): Promise<void> {
  // 1. Check if setup is required
  const status = await authApi.getStatus()
  setupRequired.value = status.setup_required

  if (status.setup_required) {
    clearAuth()  // Clear stale tokens
    return
  }

  // 2. If we have a token, try to get user info
  if (accessToken.value) {
    try {
      user.value = await authApi.me()
    } catch {
      // Token might be expired, try refresh ONCE
      if (refreshToken.value) {
        try {
          await refreshTokens()
        } catch {
          clearAuth()  // Refresh also failed
        }
      } else {
        clearAuth()
      }
    }
  }
}
```

---

### 5.3 WebSocket Error Handling

**⚠️ WICHTIGER HINWEIS:** Der `useRealTimeData` Composable ist **DEPRECATED**.
Er wurde ersetzt durch `useWebSocket` für bessere Performance und Ressourcen-Management.

**Neue Implementierung:** `src/composables/useWebSocket.ts`
**Alte Implementierung (deprecated):** `src/composables/useRealTimeData.ts`

**Connection Handling (Zeilen 182-246 - DEPRECATED IMPLEMENTIERUNG):**

```typescript
function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    console.log('[WebSocket] Already connected or connecting')
    return
  }

  try {
    const url = getWebSocketUrl()
    ws = new WebSocket(url)

    ws.onopen = () => {
      console.log('[WebSocket] Connected')
      isConnected.value = true
      reconnectAttempts.value = 0
    }

    ws.onclose = (event) => {
      console.log('[WebSocket] Disconnected:', event.code, event.reason)
      isConnected.value = false
      ws = null

      // Schedule reconnect if not intentional disconnect
      if (!event.wasClean) {
        scheduleReconnect()
      }
    }

    ws.onerror = (event) => {
      console.error('[WebSocket] Error:', event)
      isConnected.value = false
      eventHandlers.onError?.('WebSocket-Verbindungsfehler')
    }

    ws.onmessage = (event) => {
      handleMessage(event)
    }
  } catch (error) {
    console.error('[WebSocket] Connection error:', error)
  }
}
```

**Auto-Reconnect (Zeilen 269-280 - DEPRECATED IMPLEMENTIERUNG):**

```typescript
function scheduleReconnect() {
  if (maxReconnectAttempts && reconnectAttempts.value >= maxReconnectAttempts) {
    console.log('[WebSocket] Max reconnect attempts reached')
    return
  }

  reconnectAttempts.value++
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.value - 1), 30000)

  console.log(`[WebSocket] Scheduling reconnect attempt ${reconnectAttempts.value}`)

  reconnectTimer = setTimeout(() => {
    connect()
  }, delay)
}
```

**Reconnect-Delay:** Exponential Backoff (1s → 2s → 4s → ... → 30s max)

---

### 5.4 UI-Patterns für Fehler

**Vorhandene Patterns:**

| Pattern | Location | Beschreibung |
|---------|----------|--------------|
| **ESP Status Badges** | `ESPCard.vue:96-98` | Online/Offline/Error Badges |
| **E-STOP Badges** | `ESPCard.vue:136-137` | Emergency-Stop Anzeige |
| **Emergency Alert Banner** | `DashboardView.vue:88-100` | Gelbes Warning-Banner |
| **Loading States** | Diverse Views | `isLoading` Refs |
| **Error State** | `mockEsp.ts:error` | Zentrale Error-Ref im Store |

**⚠️ LÜCKE: Globales Notification-System**

**Problem:** Kein einheitliches Toast/Snackbar-System für API-Fehler.

**Beobachtung:**
- `useToast` ist in `composables/index.ts:21` auskommentiert
- Kein aktives globales Notification-System

**Impact:**
- API-Fehler werden nur in Console geloggt
- User sieht keine direkten Fehlermeldungen bei API-Failures

**Vorgeschlagene Implementierung:**

1. **Composable erstellen:** `src/composables/useToast.ts`

```typescript
import { ref, readonly } from 'vue'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  timeout?: number
}

const toasts = ref<Toast[]>([])

export function useToast() {
  const showToast = (type: Toast['type'], message: string, timeout = 5000) => {
    const id = Date.now().toString()
    toasts.value.push({ id, type, message, timeout })

    if (timeout > 0) {
      setTimeout(() => removeToast(id), timeout)
    }
  }

  const showError = (message: string) => showToast('error', message)
  const showSuccess = (message: string) => showToast('success', message)
  const showWarning = (message: string) => showToast('warning', message)

  const removeToast = (id: string) => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return {
    toasts: readonly(toasts),
    showToast,
    showError,
    showSuccess,
    showWarning,
    removeToast
  }
}
```

2. **Toast-Container-Component erstellen:** `src/components/ToastContainer.vue`

3. **In API Interceptor integrieren:** `src/api/index.ts`

```typescript
import { useToast } from '@/composables/useToast'

api.interceptors.response.use(
  response => response,
  error => {
    const { showError } = useToast()

    if (error.response?.status === 500) {
      showError('Server-Fehler. Bitte versuchen Sie es später erneut.')
    } else if (error.response?.status === 403) {
      showError('Keine Berechtigung für diese Aktion.')
    }

    return Promise.reject(error)
  }
)
```

**Geschätzter Aufwand:** 2-3 Stunden

---

## Teil 6: User Experience bei Fehlern

| Szenario | Was User sieht | Technische Reaktion |
|----------|----------------|---------------------|
| **ESP geht offline** | Status-Badge wechselt zu "Offline" (grau), Dashboard zeigt Warnung | Server: Heartbeat-Timeout → status="offline" → WebSocket "esp_health" → Frontend aktualisiert Badge |
| **ESP kommt online** | Status-Badge wechselt zu "Online" (grün) | ESP: Heartbeat → Server: status="online" → WebSocket "esp_health" → Frontend aktualisiert Badge |
| **WebSocket disconnected** | Connection-Status im UI zeigt "Disconnected" | Frontend: onclose → isConnected=false → scheduleReconnect() mit Exponential Backoff |
| **WebSocket reconnected** | Connection-Status zeigt "Connected", Daten fließen wieder | Frontend: onopen → isConnected=true → reconnectAttempts reset |
| **API-Fehler (401)** | Automatischer Redirect zu Login | Interceptor: 401 → refreshTokens() → bei Failure: clearAuth() + redirect /login |
| **API-Fehler (500)** | Aktuell: Nur Console-Log (⚠️ LÜCKE) | Interceptor: 500 → Error wird rejected → Component muss selbst handlen |
| **Emergency Stop aktiv** | Rotes E-STOP Badge, Controls deaktiviert, gelbes Alert-Banner auf Dashboard | Server: E-Stop via API → MQTT broadcast → ESP stoppt → Alert zurück → WebSocket "actuator_alert" → Frontend zeigt Banner |
| **Emergency Stop aufgehoben** | E-STOP Badge verschwindet, Controls wieder aktiv | Server: Clear E-Stop → MQTT command → ESP resumed → Status update → Frontend aktualisiert |
| **MQTT Broker unavailable** | ESP-Status bleibt "stale", keine neuen Daten | Server: MQTT disconnect → Auto-reconnect mit Backoff → Nach Reconnect: Subscriptions wiederhergestellt |

---

## Teil 7: Komplette Error Recovery Timeline

**Szenario: ESP32 verliert WiFi-Verbindung und stellt sie wieder her**

```
Zeit    ESP32                         Server                       Frontend
────────────────────────────────────────────────────────────────────────────────────
t=0s    [Normal Operation]            [Receiving Heartbeats]       [Showing "Online"]
        │ Heartbeat alle 60s          │ last_seen aktualisiert     │ Badge: grün
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=30s   ❌ WiFi DISCONNECT            │                             │
        │ Circuit Breaker: Record     │                             │
        │   Failure                   │                             │
        │ Reconnect-Versuch #1        │                             │
        │   (blocked by CB)           │                             │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=60s   │ WiFi Reconnect-Versuch #2   │ Heartbeat erwartet aber    │
        │   (CB: 30s delay)           │   nicht erhalten           │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=120s  │ WiFi still down             │ Threshold überschritten    │ ⚠️ Status ändert
        │ CB: OPEN State              │ (120s seit last_seen)      │    sich zu "Offline"
        │ → 60s Recovery-Timeout      │                             │    (falls periodic
        │                             │ [Wenn periodic check        │     check läuft)
        │                             │  implementiert:]            │
        │                             │ → status = "offline"        │
        │                             │ → WebSocket broadcast       │
        │                             │   "esp_health":             │
        │                             │   {status: "offline"}       │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=180s  │ CB: HALF_OPEN State         │                             │
        │ → Test-Reconnect erlaubt    │                             │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=185s  ✅ WiFi RECONNECT SUCCESS     │                             │
        │ CB: recordSuccess()         │                             │
        │ → CB: CLOSED State          │                             │
        │                             │                             │
        │ MQTT Reconnect...           │                             │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=190s  │ MQTT Connected              │                             │
        │ Offline Buffer Processing   │                             │
        │   (falls Nachrichten        │                             │
        │    gebuffert)               │                             │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=200s  │ Heartbeat gesendet ────────►│ Heartbeat empfangen        │
        │                             │ → status = "online"         │
        │                             │ → last_seen = now()         │
        │                             │ → WebSocket broadcast ─────►│ ✅ Badge: grün
        │                             │   "esp_health":             │    "Online"
        │                             │   {status: "online",        │
        │                             │    heap_free: ...,          │
        │                             │    wifi_rssi: ...}          │
        │                             │                             │
────────────────────────────────────────────────────────────────────────────────────
t=260s  [Normal Operation Resumed]    [Receiving Heartbeats]       [Showing "Online"]
```

---

## Teil 8: Troubleshooting

### 8.1 Server-seitige Fehler

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| "MQTT client not connected" in Logs | MQTT Broker nicht erreichbar | 1. Prüfe ob Mosquitto läuft: `systemctl status mosquitto`<br>2. Prüfe Firewall Port 1883<br>3. Prüfe `MQTT_BROKER_HOST` in .env |
| ESP-Heartbeats werden rejected | ESP nicht registriert (Auto-Discovery deaktiviert) | Registriere ESP via REST API: `POST /api/v1/esp/register` |
| "Invalid heartbeat payload" | Fehlende Required-Felder | Prüfe ESP-Firmware: ts, uptime, heap_free, wifi_rssi sind Required |
| WebSocket broadcasts nicht empfangen | WebSocket Manager nicht initialisiert | Prüfe Server-Startup-Logs auf "WebSocket Manager initialized" |
| "Failed to parse heartbeat topic" | Falsches Topic-Format | Topic muss sein: `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` |
| ESP-Status bleibt "online" obwohl offline | Periodic Health-Check fehlt (⚠️ LÜCKE) | Implementiere Background-Task für `check_device_timeouts()` |
| Database-Lock Errors | Concurrent writes | Prüfe SQLite vs PostgreSQL, nutze Connection-Pooling |
| "Rate limit exceeded" in WebSocket | > 10 msg/sec an einen Client | Normal bei vielen Sensoren, Frontend sollte Messages aggregieren |

### 8.2 Frontend-seitige Fehler

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| Automatischer Logout | Token expired + Refresh failed | 1. Prüfe ob Server läuft<br>2. Prüfe JWT Secret Key<br>3. Manuell neu einloggen |
| WebSocket verbindet nicht | CORS oder falscher Endpoint | 1. Prüfe Vite Proxy-Config<br>2. Prüfe `/api/v1/ws/realtime` Endpoint |
| "WebSocket error" in Console | Server nicht erreichbar oder Auth-Fehler | 1. Token im Request prüfen<br>2. Server-Logs prüfen |
| ESP-Status aktualisiert nicht | WebSocket nicht verbunden | 1. Prüfe `isConnected` State<br>2. Prüfe Browser DevTools → Network → WS |
| E-STOP Button funktioniert nicht | API-Call schlägt fehl | 1. Prüfe Network Tab für Fehler<br>2. Prüfe User-Berechtigung |
| Leere ESP-Liste | API-Fehler oder keine ESPs registriert | 1. Prüfe `/api/v1/esp/devices` Response<br>2. Registriere Test-ESPs |

### 8.3 Kommunikations-Fehler

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| ESP-Daten kommen nicht an | MQTT-Verbindung unterbrochen | 1. Prüfe ESP Serial Monitor für MQTT-Status<br>2. Prüfe Broker-Logs |
| Actuator-Commands werden nicht ausgeführt | Emergency-Stop aktiv ODER ESP offline | 1. Prüfe E-Stop Status im Frontend<br>2. Prüfe ESP Online-Status |
| Hohe Latenz bei Sensor-Daten | Netzwerk-Probleme oder Rate-Limiting | 1. Prüfe WiFi-Signalstärke (RSSI)<br>2. Reduziere Sensor-Intervall |
| Duplicate Messages | QoS-Level zu hoch oder Reconnect-Issues | 1. Nutze QoS 0 für Sensor-Daten<br>2. Prüfe Client-ID-Konflikte |

---

## Teil 9: Code-Locations Referenz

| Komponente | Pfad | Relevante Funktionen/Zeilen |
|------------|------|----------------------------|
| **Server MQTT Client** | `El Servador/.../mqtt/client.py` | `connect()` (77-160), `_on_connect()` (303-319), `_on_disconnect()` (321-350) |
| **Server Heartbeat Handler** | `El Servador/.../mqtt/handlers/heartbeat_handler.py` | `handle_heartbeat()` (54-175), `check_device_timeouts()` (415-464), `HEARTBEAT_TIMEOUT_SECONDS` (37) |
| **Server ESP Service** | `El Servador/.../services/esp_service.py` | `check_device_status()` (211-250), `update_health()` (160-209) |
| **Server Safety Service** | `El Servador/.../services/safety_service.py` | `validate_actuator_command()` (84-128), `emergency_stop_all()` (215-223), `emergency_stop_esp()` (225-234) |
| **Server Actuator Alert Handler** | `El Servador/.../mqtt/handlers/actuator_alert_handler.py` | `handle_actuator_alert()` (66-197), `ALERT_SEVERITY` (44-49) |
| **Server Config Handler** | `El Servador/.../mqtt/handlers/config_handler.py` | `handle_config_ack()` (66-183), WebSocket broadcast (154-177) |
| **Server WebSocket Manager** | `El Servador/.../websocket/manager.py` | `broadcast()` (156-217), `broadcast_threadsafe()` (219-238), Rate-Limiting (240-269) |
| **Server Config** | `El Servador/.../core/config.py` | `heartbeat_timeout` (194) |
| **Frontend API Interceptor** | `El Frontend/src/api/index.ts` | Request interceptor (14-28), Response interceptor (31-71) |
| **Frontend Auth Store** | `El Frontend/src/stores/auth.ts` | `refreshTokens()` (104-119), `checkAuthStatus()` (24-63), `clearAuth()` (141-147) |
| **Frontend Real-Time Data** | `El Frontend/src/composables/useRealTimeData.ts` | `connect()` (125-175), `scheduleReconnect()` (197-210), `handleMessage()` (213-260) |
| **Frontend E-Stop UI** | `El Frontend/src/views/ActuatorsView.vue` | `emergencyStopAll()` (119-124), E-Stop button (153-156), E-Stop stats (82-84) |
| **Frontend Dashboard Alert** | `El Frontend/src/views/DashboardView.vue` | Emergency alert (88-100), `emergencyCount` (60-65) |
| **ESP32 Error Recovery** | `El Trabajante/docs/system-flows/07-error-recovery-flow.md` | Vollständige ESP32-seitige Dokumentation |
| **ESP32 Heartbeat** | `El Trabajante/src/services/communication/mqtt_client.cpp` | `publishHeartbeat()` (433-483), `HEARTBEAT_INTERVAL_MS` (h:108) |

---

## Verifizierungscheckliste

### Server-Seite

- [x] `src/mqtt/client.py` - Reconnection-Logic mit Exponential Backoff (Zeilen 243-246)
- [x] `src/mqtt/client.py` - Circuit Breaker Integration (Zeilen 140-164)
- [x] `src/mqtt/client.py` - Offline Buffer für Graceful Degradation (Zeilen 165-173)
- [x] `src/mqtt/client.py` - Rate-Limiting für Disconnect Logs (Zeilen 33-81)
- [x] `src/mqtt/client.py` - Auto Re-subscription bei Reconnect (Zeilen 472-479)
- [x] `src/mqtt/client.py` - `is_connected()` Methode (Zeilen 446-453)
- [x] `src/mqtt/client.py` - `on_connect` / `on_disconnect` Callbacks (Zeilen 456-568)
- [x] `src/services/esp_service.py` - `check_device_status()` - Vollständige Logik (Zeilen 211-250)
- [x] `src/services/esp_service.py` - `update_health()` - Vollständige Logik (Zeilen 160-209)
- [x] `src/services/esp_service.py` - Offline-Threshold-Wert: 120s (Default), konfigurierbar als Parameter
- [x] `src/mqtt/handlers/heartbeat_handler.py` - Vollständiger Flow (Zeilen 55-177)
- [x] `src/mqtt/handlers/heartbeat_handler.py` - Auto-Discovery DISABLED (Zeilen 113-126)
- [x] `src/mqtt/handlers/heartbeat_handler.py` - Device Source Detection (Zeilen 378-447)
- [x] `src/mqtt/handlers/heartbeat_handler.py` - WebSocket Broadcast vorhanden: **JA** (Zeilen 153-168)
- [x] `src/mqtt/handlers/actuator_alert_handler.py` - Alert-Types und Severity (Zeilen 44-49)
- [x] `src/mqtt/handlers/config_handler.py` - WebSocket Broadcast vorhanden: **JA** (Zeilen 154-177)
- [x] `src/services/safety_service.py` - Emergency-Stop-Integration (Zeilen 215-234)
- [x] `src/websocket/manager.py` - `broadcast_threadsafe()` Methode (Zeilen 237-256)
- [x] `src/websocket/manager.py` - Rate-Limiting-Implementierung: 10 msg/sec (Zeilen 258-287)

### Frontend-Seite

- [x] `src/api/index.ts` - Error-Interceptor vollständig analysiert (Zeilen 31-71)
- [x] `src/stores/auth.ts` - Token-Refresh-Logic vollständig analysiert (Zeilen 104-119)
- [x] `src/composables/useRealTimeData.ts` - DEPRECATED (Zeilen 1-5), ersetzt durch `useWebSocket`
- [x] `src/composables/useRealTimeData.ts` - WebSocket onclose/onerror Handler (Zeilen 213-246)
- [x] Notification-System vorhanden: **NEIN** (⚠️ LÜCKE - `useToast` auskommentiert)
- [x] ESP-Status-Badges vorhanden: **JA** - `ESPCard.vue:96-98`
- [x] Connection-Status-Indicator vorhanden: **JA** - `isConnected` in useRealTimeData (deprecated)
- [x] Emergency-Stop-UI vorhanden: **JA** - `ActuatorsView.vue`, `DashboardView.vue`, `ESPCard.vue`

### Cross-System

- [x] ESP32 Heartbeat-Intervall: **60 Sekunden** (`mqtt_client.h:108`)
- [x] ESP32 Heartbeat-Intervall konfigurierbar: **NEIN** (Compile-Time Konstante)
- [x] Server Offline-Threshold: **120s (Default)**, **300s (Heartbeat Handler)**
- [x] Server Offline-Threshold konfigurierbar: **JA** - als Parameter in `check_device_status()` und via `core/config.py:194`
- [x] Periodic Health-Check-Task vorhanden: **NEIN** (⚠️ LÜCKE)
- [x] MQTT Circuit Breaker Integration: **JA** - mit Offline Buffer (Zeilen 379-424)
- [x] WebSocket Composable Migration: **AUSSTEHEND** (⚠️ LÜCKE - `useRealTimeData` deprecated)

---

## Implementierungs-Roadmap (Identifizierte Lücken)

### Phase 1: Kritische Lücken (High Priority)

| Lücke | Beschreibung | Geschätzter Aufwand |
|-------|--------------|---------------------|
| **Periodic Health-Check Task** | Background-Task für `check_device_timeouts()` | 1 Stunde |

### Phase 2: Wichtige Lücken (Medium Priority)

| Lücke | Beschreibung | Geschätzter Aufwand |
|-------|--------------|---------------------|
| **Globales Notification-System** | Toast/Snackbar für API-Fehler | 2-3 Stunden |
| **WebSocket Composable Migration** | `useRealTimeData` → `useWebSocket` Migration | 4-6 Stunden |

### Phase 3: Nice-to-have

| Verbesserung | Beschreibung | Geschätzter Aufwand |
|--------------|--------------|---------------------|
| **Konfigurierares ESP32 Heartbeat-Intervall** | Via MQTT Config statt Compile-Time | 2 Stunden (ESP32 + Server) |
| **WebSocket Reconnect-Indicator im UI** | Visuelles Feedback während Reconnect | 1 Stunde |

---

**Letzte Verifizierung:** 2025-12-27
**Verifiziert gegen Code-Version:** Git master branch
