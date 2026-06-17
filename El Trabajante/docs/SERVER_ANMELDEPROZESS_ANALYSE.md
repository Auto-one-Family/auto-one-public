# Server-Seite: ESP32-Anmeldeprozess - Analyse

**Analysiert:** 2026-01-23
**Server-Version:** El Servador/god_kaiser_server (FastAPI)
**Analyst:** Claude Code (Opus 4.5)

---

## 1. Executive Summary

### Zusammenfassung des Server-Flows

Der Server implementiert einen **vollständigen Discovery-Approval-Workflow**:

1. **Discovery via Heartbeat:** Unbekannte ESPs werden automatisch als `pending_approval` registriert
2. **Bidirektionale Kommunikation:** Server sendet Heartbeat-ACK mit Status zurück
3. **Admin-Approval:** REST API für Approve/Reject mit WebSocket-Broadcast
4. **Audit-Trail:** 7 Event-Typen für vollständige Nachverfolgbarkeit
5. **Rejection-Cooldown:** 5 Minuten Sperrzeit nach Ablehnung

### Wichtigste Erkenntnisse

| Aspekt | Status | Details |
|--------|--------|---------|
| Auto-Discovery | ✅ Implementiert | Neue ESPs werden automatisch als `pending_approval` registriert |
| Heartbeat-ACK | ✅ Implementiert | QoS 0, Fire-and-Forget Pattern |
| Admin-Approval | ✅ Implementiert | REST API + WebSocket-Broadcast |
| Audit-Logging | ✅ Implementiert | Alle 7 Event-Typen vorhanden |
| Rate-Limiting | ✅ Implementiert | 10/min global, 5 min per-device cooldown |
| LWT-Handling | ✅ Implementiert | Sofortige Offline-Erkennung |

### Potenzielle Probleme/Lücken

1. **Kein Timeout für Pending-Devices:** ESPs in `pending_approval` werden nie automatisch aufgeräumt
2. **Heartbeat-ACK QoS 0:** Bei Netzwerkproblemen könnte ESP den Status verpassen (aber nächster Heartbeat löst neuen ACK aus)
3. **`config_available` immer False:** Placeholder für zukünftiges Config-Push-System

---

## 2. Heartbeat-Handler

**Datei:** [heartbeat_handler.py](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py)

### 2.1 Topic-Pattern

| Richtung | Topic | Format |
|----------|-------|--------|
| ESP → Server | `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat` | Aktuell |
| ESP → Server | `kaiser/{kaiser_id}/esp/{esp_id}/heartbeat` | Legacy (unterstützt) |
| Server → ESP | `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat/ack` | ACK |

**Default kaiser_id:** `god`

### 2.2 Payload-Validierung

**Validierungsmethode:** `_validate_payload()` ([heartbeat_handler.py:625-698](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L625-L698))

**Required Fields:**

| Feld | Typ | Beschreibung | Alternative |
|------|-----|--------------|-------------|
| `ts` | int | Unix Timestamp | - |
| `uptime` | int | Sekunden seit Boot | - |
| `heap_free` | int | Freier Heap (Bytes) | `free_heap` (legacy) |
| `wifi_rssi` | int | WiFi Signalstärke (dBm) | - |

**Optional Fields (werden gespeichert):**

| Feld | Beschreibung |
|------|--------------|
| `esp_id` | ESP-ID im Payload |
| `zone_id` | Zone-Zugehörigkeit |
| `master_zone_id` | Master-Zone |
| `zone_assigned` | Zone-Assignment-Status |
| `sensor_count` | Anzahl aktiver Sensoren |
| `actuator_count` | Anzahl aktiver Aktoren |
| `gpio_status` | GPIO-Pin-Status-Array |
| `gpio_reserved_count` | Anzahl reservierter Pins |

### 2.3 Branching-Logik (Status-basiert)

```
Heartbeat empfangen
        │
        ▼
┌───────────────────┐
│ ESP in DB suchen  │
└───────────────────┘
        │
        ├──── NICHT GEFUNDEN ──────────────────────────────────────┐
        │                                                          │
        ▼                                                          ▼
┌───────────────────┐                               ┌──────────────────────────┐
│ status == ?       │                               │ _discover_new_device()   │
└───────────────────┘                               │ → Auto-Register          │
        │                                           │ → status = pending       │
        ├─── "rejected" ─────┐                      │ → ACK: pending_approval  │
        │                    ▼                      └──────────────────────────┘
        │    ┌──────────────────────────┐
        │    │ Cooldown abgelaufen?     │
        │    └──────────────────────────┘
        │           │         │
        │        JA ▼      NEIN ▼
        │    ┌────────┐  ┌────────────────┐
        │    │Rediscover│ │ACK: rejected  │
        │    │→pending  │ │(ignorieren)   │
        │    └────────┘  └────────────────┘
        │
        ├─── "pending_approval" ─────────────────────────────────┐
        │                                                         │
        │                                          ┌──────────────▼───────────┐
        │                                          │ heartbeat_count++        │
        │                                          │ ACK: pending_approval    │
        │                                          └──────────────────────────┘
        │
        ├─── "approved" ─────────────────────────────────────────┐
        │                                                         │
        │                                          ┌──────────────▼───────────┐
        │                                          │ status → "online"        │
        │                                          │ Audit: DEVICE_ONLINE     │
        │                                          │ ACK: online              │
        │                                          └──────────────────────────┘
        │
        └─── "online" ───────────────────────────────────────────┐
                                                                  │
                                               ┌──────────────────▼───────────┐
                                               │ Update: last_seen, metadata  │
                                               │ WebSocket: esp_health        │
                                               │ ACK: online                  │
                                               └──────────────────────────────┘
```

### 2.4 Code-Referenzen

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `handle_heartbeat()` | [60-284](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L60-L284) | Haupt-Entry-Point |
| `_discover_new_device()` | [361-412](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L361-L412) | Auto-Discovery |
| `_auto_register_esp()` | [286-355](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L286-L355) | DB-Eintrag erstellen |
| `_check_rejection_cooldown()` | [414-437](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L414-L437) | Cooldown-Prüfung |
| `_rediscover_device()` | [439-483](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L439-L483) | Re-Discovery |
| `_update_pending_heartbeat()` | [485-501](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L485-L501) | Pending-Update |
| `_send_heartbeat_ack()` | [877-935](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L877-L935) | ACK senden |
| `_validate_payload()` | [625-698](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L625-L698) | Payload-Validierung |
| `check_device_timeouts()` | [954-1045](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L954-L1045) | Timeout-Check |

### 2.5 Heartbeat-ACK Format

**Topic:** `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat/ack`

**Payload:**
```json
{
  "status": "pending_approval" | "approved" | "online" | "rejected",
  "config_available": false,
  "server_time": 1735818000
}
```

**QoS:** 0 (Fire-and-Forget)

**Wichtig:** ESP32 blockiert NICHT auf diesen ACK. Bei Verlust wird beim nächsten Heartbeat ein neuer ACK gesendet.

---

## 3. LWT-Handler

**Datei:** [lwt_handler.py](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/lwt_handler.py)

### 3.1 Topic-Pattern

| Richtung | Topic |
|----------|-------|
| Broker → Server | `kaiser/{kaiser_id}/esp/{esp_id}/system/will` |

### 3.2 Offline-Status-Logik

```
LWT empfangen
        │
        ▼
┌───────────────────┐
│ ESP in DB suchen  │
└───────────────────┘
        │
        ├─── NICHT GEFUNDEN ────────────────────────────────────┐
        │                                                        │
        │                                         ┌──────────────▼───────────┐
        │                                         │ Warning loggen           │
        │                                         │ Return True (ACK)        │
        │                                         └──────────────────────────┘
        │
        ├─── status == "online" ─────────────────────────────────┐
        │                                                         │
        │                                          ┌──────────────▼───────────┐
        │                                          │ status → "offline"       │
        │                                          │ metadata.last_disconnect │
        │                                          │ Audit: LWT_RECEIVED      │
        │                                          │ WebSocket: esp_health    │
        │                                          └──────────────────────────┘
        │
        └─── status != "online" ─────────────────────────────────┐
                                                                  │
                                               ┌──────────────────▼───────────┐
                                               │ Debug-Log: "already offline" │
                                               │ (keine Aktion)               │
                                               └──────────────────────────────┘
```

### 3.3 Expected LWT Payload

**Payload (konfiguriert von ESP32):**
```json
{
  "status": "offline",
  "reason": "unexpected_disconnect",
  "timestamp": 1735818000
}
```

### 3.4 Code-Referenzen

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `handle_lwt()` | [50-183](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/lwt_handler.py#L50-L183) | Haupt-Handler |
| Audit-Event | [126-141](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/lwt_handler.py#L126-L141) | LWT_RECEIVED |
| WebSocket-Broadcast | [148-167](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/lwt_handler.py#L148-L167) | esp_health offline |

---

## 4. REST API Endpoints

**Datei:** [esp.py](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py)

### 4.1 GET /v1/esp/devices/pending

**Beschreibung:** Liste aller Pending-Devices

**Response:** `PendingDevicesListResponse`

```json
{
  "success": true,
  "devices": [
    {
      "device_id": "ESP_12AB34CD",
      "discovered_at": "2026-01-23T10:00:00Z",
      "last_seen": "2026-01-23T10:05:00Z",
      "zone_id": "zone_main",
      "heap_free": 45000,
      "wifi_rssi": -45,
      "sensor_count": 3,
      "actuator_count": 2,
      "heartbeat_count": 5
    }
  ],
  "count": 1
}
```

**Code-Referenz:** [esp.py:205-256](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py#L205-L256)

### 4.2 POST /v1/esp/devices/{esp_id}/approve

**Request:** `ESPApprovalRequest`

```json
{
  "name": "Gewächshaus ESP",
  "zone_id": "zone_greenhouse",
  "zone_name": "Gewächshaus"
}
```

**Response:** `ESPApprovalResponse`

```json
{
  "success": true,
  "message": "Device 'ESP_12AB34CD' approved successfully",
  "device_id": "ESP_12AB34CD",
  "status": "approved",
  "approved_by": "admin",
  "approved_at": "2026-01-23T10:10:00Z"
}
```

**Ablauf:**
1. ESP suchen
2. Status-Check: `pending_approval` oder `rejected`
3. Update: `status="approved"`, `approved_at`, `approved_by`
4. Audit-Event: `DEVICE_APPROVED`
5. WebSocket-Broadcast: `device_approved`

**Code-Referenz:** [esp.py:1139-1248](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py#L1139-L1248)

### 4.3 POST /v1/esp/devices/{esp_id}/reject

**Request:** `ESPRejectionRequest`

```json
{
  "reason": "Unbekanntes Gerät - nicht autorisiert"
}
```

**Response:** `ESPApprovalResponse`

```json
{
  "success": true,
  "message": "Device 'ESP_12AB34CD' rejected",
  "device_id": "ESP_12AB34CD",
  "status": "rejected",
  "rejection_reason": "Unbekanntes Gerät - nicht autorisiert"
}
```

**Ablauf:**
1. ESP suchen
2. Status-Check: `pending_approval`, `approved`, oder `online`
3. Update: `status="rejected"`, `rejection_reason`, `last_rejection_at`
4. Audit-Event: `DEVICE_REJECTED`
5. WebSocket-Broadcast: `device_rejected`

**Code-Referenz:** [esp.py:1251-1350](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py#L1251-L1350)

---

## 5. ESP Service

**Datei:** [esp_service.py](../../El%20Servador/god_kaiser_server/src/services/esp_service.py)

### 5.1 Discovery Rate Limiter

**Klasse:** `DiscoveryRateLimiter` ([esp_service.py:42-115](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L42-L115))

| Limit | Wert | Beschreibung |
|-------|------|--------------|
| Global | 10/min | Max 10 Discoveries pro Minute |
| Per-Device | 300s | 5 Minuten Cooldown pro Gerät |

### 5.2 Service-Methoden

| Methode | Zeilen | Beschreibung |
|---------|--------|--------------|
| `discover_device()` | [665-717](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L665-L717) | Create pending device |
| `approve_device()` | [719-763](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L719-L763) | Approve pending |
| `reject_device()` | [765-794](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L765-L794) | Reject pending |
| `get_pending_devices()` | [796-803](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L796-L803) | List pending |
| `check_rejection_cooldown()` | [805-835](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L805-L835) | Check cooldown |
| `rediscover_device()` | [837-868](../../El%20Servador/god_kaiser_server/src/services/esp_service.py#L837-L868) | Re-discover after cooldown |

### 5.3 Heartbeat-Timeout-Logik

**Konstante:** `HEARTBEAT_TIMEOUT_SECONDS = 300` (5 Minuten)

**Location:** [heartbeat_handler.py:43](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L43)

**Timeout-Check:** `check_device_timeouts()` ([heartbeat_handler.py:954-1045](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L954-L1045))

---

## 6. Database Model

**Datei:** [esp.py](../../El%20Servador/god_kaiser_server/src/db/models/esp.py)

### 6.1 ESPDevice Felder (Discovery/Approval-relevant)

| Feld | Typ | Nullable | Beschreibung | Zeilen |
|------|-----|----------|--------------|--------|
| `id` | UUID | No | Primary Key | 44-49 |
| `device_id` | String(50) | No | Unique Device ID (ESP_XXXXXXXX) | 52-58 |
| `status` | String(20) | No | online/offline/error/unknown/pending_approval/approved/rejected | 137-143 |
| `last_seen` | DateTime | Yes | Letzter Heartbeat | 145-150 |
| `discovered_at` | DateTime | Yes | Erster Heartbeat (Discovery) | 159-163 |
| `approved_at` | DateTime | Yes | Approval-Zeitpunkt | 165-169 |
| `approved_by` | String(100) | Yes | Admin-Username | 171-175 |
| `rejection_reason` | String(500) | Yes | Ablehnungsgrund | 177-180 |
| `last_rejection_at` | DateTime | Yes | Letzte Ablehnung (für Cooldown) | 182-187 |
| `device_metadata` | JSON | No | Metadaten (heartbeat_count, etc.) | 190-195 |

### 6.2 Status-Enum

| Status | Beschreibung | Übergang zu |
|--------|--------------|-------------|
| `pending_approval` | Neu entdeckt, wartet auf Admin | approved, rejected |
| `approved` | Admin hat genehmigt | online (nach Heartbeat) |
| `online` | Aktiv und verbunden | offline, rejected |
| `offline` | Keine Heartbeats (Timeout/LWT) | online |
| `rejected` | Admin hat abgelehnt | pending_approval (nach Cooldown) |
| `error` | Fehler-Status | - |
| `unknown` | Initial-Status | - |

### 6.3 device_metadata Struktur (für Pending/Discovery)

```json
{
  "discovery_source": "heartbeat",
  "initial_heartbeat": { ... },
  "heartbeat_count": 5,
  "zone_id": "zone_main",
  "master_zone_id": "master",
  "zone_assigned": true,
  "initial_heap_free": 45000,
  "initial_wifi_rssi": -45,
  "last_heartbeat": "2026-01-23T10:05:00Z",
  "rediscovered_at": "2026-01-23T11:00:00Z",
  "rediscovery_heartbeat": { ... }
}
```

---

## 7. Audit-Logging

**Datei:** [audit_log.py](../../El%20Servador/god_kaiser_server/src/db/models/audit_log.py)

### 7.1 ESP Lifecycle Event-Typen

| Event-Typ | Severity | Trigger | Location |
|-----------|----------|---------|----------|
| `DEVICE_DISCOVERED` | INFO | Neuer ESP erster Heartbeat | [heartbeat_handler.py:392-410](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L392-L410) |
| `DEVICE_APPROVED` | INFO | Admin genehmigt ESP | [esp.py:1205-1222](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py#L1205-L1222) |
| `DEVICE_REJECTED` | WARNING | Admin lehnt ESP ab | [esp.py:1309-1325](../../El%20Servador/god_kaiser_server/src/api/v1/esp.py#L1309-L1325) |
| `DEVICE_ONLINE` | INFO | ESP online nach Approval | [heartbeat_handler.py:186-202](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L186-L202) |
| `DEVICE_REDISCOVERED` | WARNING | Abgelehnter ESP nach Cooldown | [heartbeat_handler.py:466-483](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L466-L483) |
| `LWT_RECEIVED` | WARNING | Unexpected Disconnect | [lwt_handler.py:126-141](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/lwt_handler.py#L126-L141) |
| `DEVICE_OFFLINE` | WARNING | Heartbeat Timeout | [heartbeat_handler.py:993-1009](../../El%20Servador/god_kaiser_server/src/mqtt/handlers/heartbeat_handler.py#L993-L1009) |

### 7.2 Verifizierung

| Event-Typ | Implementiert | Location verifiziert |
|-----------|---------------|---------------------|
| `DEVICE_DISCOVERED` | ✅ | heartbeat_handler.py:392-410 |
| `DEVICE_APPROVED` | ✅ | esp.py:1205-1222 |
| `DEVICE_REJECTED` | ✅ | esp.py:1309-1325 |
| `DEVICE_ONLINE` | ✅ | heartbeat_handler.py:186-202 |
| `DEVICE_REDISCOVERED` | ✅ | heartbeat_handler.py:466-483 |
| `LWT_RECEIVED` | ✅ | lwt_handler.py:126-141 |
| `DEVICE_OFFLINE` | ✅ | heartbeat_handler.py:993-1009 |

---

## 8. Sequenzdiagramm (Server-Perspektive)

### 8.1 Neuer ESP Discovery + Approval

```
┌─────────┐          ┌─────────────┐          ┌────────────┐          ┌─────────┐
│  ESP32  │          │   MQTT      │          │   Server   │          │  Admin  │
│         │          │   Broker    │          │            │          │(Frontend│
└────┬────┘          └──────┬──────┘          └──────┬─────┘          └────┬────┘
     │                      │                        │                     │
     │ MQTT CONNECT         │                        │                     │
     │─────────────────────>│                        │                     │
     │                      │                        │                     │
     │ Heartbeat            │                        │                     │
     │─────────────────────>│ Forward               │                     │
     │                      │───────────────────────>│                     │
     │                      │                        │                     │
     │                      │                        │──┐ ESP not found    │
     │                      │                        │  │ Auto-Register    │
     │                      │                        │<─┘ status=pending   │
     │                      │                        │                     │
     │                      │                        │ Audit: DISCOVERED   │
     │                      │                        │──────────────────>  │
     │                      │                        │                     │
     │                      │                        │ WS: device_discovered
     │                      │                        │────────────────────>│
     │                      │                        │                     │
     │                      │      Heartbeat-ACK     │                     │
     │<─────────────────────│<───────────────────────│                     │
     │ status=pending_approval                       │                     │
     │                      │                        │                     │
     │                      │                        │   GET /devices/pending
     │                      │                        │<────────────────────│
     │                      │                        │                     │
     │                      │                        │ [ESP_12AB34CD, ...] │
     │                      │                        │────────────────────>│
     │                      │                        │                     │
     │                      │                        │ POST /{id}/approve  │
     │                      │                        │<────────────────────│
     │                      │                        │                     │
     │                      │                        │──┐ status=approved  │
     │                      │                        │<─┘ approved_at/by   │
     │                      │                        │                     │
     │                      │                        │ Audit: APPROVED     │
     │                      │                        │──────────────────>  │
     │                      │                        │                     │
     │                      │                        │ WS: device_approved │
     │                      │                        │────────────────────>│
     │                      │                        │                     │
     │ Next Heartbeat       │                        │                     │
     │─────────────────────>│───────────────────────>│                     │
     │                      │                        │                     │
     │                      │                        │──┐ status=online    │
     │                      │                        │<─┘ (approved→online)│
     │                      │                        │                     │
     │                      │                        │ Audit: ONLINE       │
     │                      │                        │──────────────────>  │
     │                      │                        │                     │
     │                      │      Heartbeat-ACK     │                     │
     │<─────────────────────│<───────────────────────│                     │
     │ status=online        │                        │                     │
     │                      │                        │                     │
     │ ESP → OPERATIONAL    │                        │                     │
     │                      │                        │                     │
```

### 8.2 LWT Disconnect

```
┌─────────┐          ┌─────────────┐          ┌────────────┐          ┌─────────┐
│  ESP32  │          │   MQTT      │          │   Server   │          │Frontend │
│         │          │   Broker    │          │            │          │         │
└────┬────┘          └──────┬──────┘          └──────┬─────┘          └────┬────┘
     │                      │                        │                     │
     │ X Connection Lost    │                        │                     │
     │ (Power/Network)      │                        │                     │
     │                      │                        │                     │
     │                      │ LWT Publish            │                     │
     │                      │ .../system/will        │                     │
     │                      │───────────────────────>│                     │
     │                      │                        │                     │
     │                      │                        │──┐ status=offline   │
     │                      │                        │<─┘ last_disconnect  │
     │                      │                        │                     │
     │                      │                        │ Audit: LWT_RECEIVED │
     │                      │                        │──────────────────>  │
     │                      │                        │                     │
     │                      │                        │ WS: esp_health      │
     │                      │                        │ {status: "offline", │
     │                      │                        │  source: "lwt"}     │
     │                      │                        │────────────────────>│
     │                      │                        │                     │
```

---

## 9. Server-Schnittstelle (für ESP32-Doku)

### 9.1 MQTT Topics

| Richtung | Topic | Payload | QoS |
|----------|-------|---------|-----|
| ESP → Server | `kaiser/god/esp/{esp_id}/system/heartbeat` | Heartbeat-Payload | 0 |
| ESP → Server | `kaiser/god/esp/{esp_id}/system/will` | LWT-Payload (vom Broker) | 0 |
| Server → ESP | `kaiser/god/esp/{esp_id}/system/heartbeat/ack` | ACK-Payload | 0 |

### 9.2 Heartbeat-Payload (ESP → Server)

```json
{
  "esp_id": "ESP_12AB34CD",
  "ts": 1735818000,
  "uptime": 123456,
  "heap_free": 45000,
  "wifi_rssi": -45,
  "zone_id": "zone_main",
  "master_zone_id": "master",
  "zone_assigned": true,
  "sensor_count": 3,
  "actuator_count": 2,
  "gpio_status": [...],
  "gpio_reserved_count": 5
}
```

### 9.3 Heartbeat-ACK-Payload (Server → ESP)

```json
{
  "status": "pending_approval" | "approved" | "online" | "rejected",
  "config_available": false,
  "server_time": 1735818000
}
```

### 9.4 LWT-Payload (ESP konfiguriert bei CONNECT)

```json
{
  "status": "offline",
  "reason": "unexpected_disconnect",
  "timestamp": 1735818000
}
```

---

## 10. Offene Fragen / Klärungsbedarf

### 10.1 Geklärt

- [x] **Wie werden Pending-Devices gefiltert?** → `status == "pending_approval"` Query
- [x] **Was passiert bei Approval?** → Status-Update, Audit-Log, WebSocket-Broadcast (KEIN sofortiger ACK - erst beim nächsten Heartbeat)
- [x] **Wie funktioniert Rejection-Cooldown?** → 5 Minuten, gespeichert in `last_rejection_at`

### 10.2 Offen

1. **Cleanup für alte Pending-Devices?**
   - Aktuell kein automatisches Aufräumen
   - ESPs in `pending_approval` bleiben ewig
   - **Empfehlung:** Maintenance-Job für Pending > 24h

2. **`config_available` immer False?**
   - Placeholder für zukünftiges Config-Push-System
   - ESP32 pollt Config separat via `/config` Topic

3. **Rate-Limiter Persistenz?**
   - Aktuell in-memory (verloren bei Server-Restart)
   - Bei Bedarf: Redis/DB für persistente Rate-Limits

---

## 11. Code-Referenz-Index

| Funktion | Datei | Zeilen | Beschreibung |
|----------|-------|--------|--------------|
| `handle_heartbeat()` | heartbeat_handler.py | 60-284 | Heartbeat Entry-Point |
| `_discover_new_device()` | heartbeat_handler.py | 361-412 | Auto-Discovery |
| `_auto_register_esp()` | heartbeat_handler.py | 286-355 | DB-Eintrag erstellen |
| `_check_rejection_cooldown()` | heartbeat_handler.py | 414-437 | Cooldown-Prüfung |
| `_rediscover_device()` | heartbeat_handler.py | 439-483 | Re-Discovery |
| `_send_heartbeat_ack()` | heartbeat_handler.py | 877-935 | ACK senden |
| `_validate_payload()` | heartbeat_handler.py | 625-698 | Payload-Validierung |
| `check_device_timeouts()` | heartbeat_handler.py | 954-1045 | Timeout-Check |
| `handle_lwt()` | lwt_handler.py | 50-183 | LWT Handler |
| `list_pending_devices()` | esp.py | 205-256 | GET /pending |
| `approve_device()` | esp.py | 1139-1248 | POST /approve |
| `reject_device()` | esp.py | 1251-1350 | POST /reject |
| `DiscoveryRateLimiter` | esp_service.py | 42-115 | Rate-Limiting |
| `ESPDevice` | db/models/esp.py | 16-240 | DB Model |
| `AuditEventType` | audit_log.py | 182-220 | Event-Konstanten |
| `TopicBuilder.parse_heartbeat_topic()` | topics.py | 426-452 | Topic-Parsing |
| `TopicBuilder.build_heartbeat_ack_topic()` | topics.py | 154-171 | ACK-Topic bauen |

---

## 12. Zusammenfassung für Frontend-Konsolidierung

### Was der Frontend-Entwickler wissen muss:

1. **WebSocket-Events für Live-Updates:**
   - `device_discovered` - Neuer ESP discovered
   - `device_approved` - ESP approved
   - `device_rejected` - ESP rejected
   - `device_rediscovered` - Abgelehnter ESP wieder entdeckt
   - `esp_health` - Status-Updates (online/offline)

2. **REST Endpoints:**
   - `GET /v1/esp/devices/pending` - Liste Pending
   - `POST /v1/esp/devices/{id}/approve` - Genehmigen
   - `POST /v1/esp/devices/{id}/reject` - Ablehnen

3. **Status-Flow für UI:**
   ```
   [Neu] → pending_approval → approved → online ↔ offline
                    ↓
                rejected → (5 min) → pending_approval
   ```

4. **Felder für Pending-Anzeige:**
   - `device_id`, `discovered_at`, `last_seen`
   - `zone_id`, `heap_free`, `wifi_rssi`
   - `sensor_count`, `actuator_count`, `heartbeat_count`

---

**Ende der Analyse**

*Dieses Dokument ergänzt die ESP32-Analyse und bildet zusammen das vollständige Bild des Anmeldeprozesses.*
