# Finalität: HTTP, MQTT und WebSocket (AutomationOne Server)

**Stand:** 2026-04-05 — konsolidiert mit dem Code unter `El Servador/god_kaiser_server/` und der Analyse
`docs/analyse/report-server-epic1-ist-vertrag-korrelation-verdrahtung-2026-04-05.md` (Epic 1).

Diese Seite beschreibt, **was ein HTTP-2xx serverseitig garantiert** und **wo** Geräte- oder Protokoll-Finalität nachzulesen ist. Detaillierte Fehlercodes: `.claude/reference/errors/ERROR_CODES.md`.

---

## Matrix (SOLL-Doku, AP-G)

| Pfad | HTTP 2xx bedeutet (serverseitig) | „Gerät bestätigt“ belegbar über | Asynchroner Kanal |
|------|----------------------------------|-----------------------------------|-------------------|
| **Actuator REST** `POST .../command` | Validierung + ggf. MQTT-Publish (oder No-Op ohne Publish); **kein** Warten auf ESP | MQTT `.../actuator/.../response`, History, `command_outcomes` (terminal authority), WS `actuator_response` | MQTT Response |
| **Actuator DELETE** `.../{esp}/{gpio}` | Config entfernt nach MQTT-OFF (Publish **ohne** explizite `correlation_id` im Aufruf — Publisher-Default) | wie normaler Aktor-Pfad | MQTT / WS |
| **Zone assign/remove REST** | DB-Update committed; bei echtem ESP oft **Warten** bis `zone/ack` oder Timeout (`MQTTCommandBridge`) | Response-Felder `mqtt_sent`, `ack_received`; danach `esp_devices.zone_id` / Handler; WS `zone_assignment` | MQTT `zone/ack` |
| **Subzone REST assign/remove/safe-mode** | DB nach erfolgreichem Publish; **kein** Bridge-Wait auf `subzone/ack` | MQTT `subzone/ack`, `SubzoneService.handle_subzone_ack`, WS `subzone_assignment` | MQTT `subzone/ack` |
| **Emergency** `POST .../emergency_stop` | Safety-Blockade + GPIO-Publishes + Broadcast; pro GPIO deterministische `correlation_id` im Command-Payload | Kein dedizierter Emergency-ACK; normale `actuator_response` möglich; Antwort enthält **`incident_correlation_id`** zur Korrelation mit Audit/WS/Broadcast | MQTT Broadcast + GPIO-Topics |
| **Clear emergency** `POST .../clear_emergency` | Bei `success=true`: Clear an alle Ziel-ESPs publiziert und Blockade gelöst | MQTT/Monitor/WS (kein HTTP-ACK-Wait) | MQTT `actuator/emergency` |

---

## Bedeutung zentraler Flags

| Stelle | Flag / Feld | Semantik |
|--------|-------------|----------|
| `ActuatorCommandResponse.command_sent` | Publish-Versuch an den Broker bzw. bewusster Verzicht (No-Op-Delta) | Kein Nachweis der Ausführung auf dem ESP |
| `ActuatorCommandResponse.acknowledged` | In REST **immer `false`** | ESP-Bestätigung nur asynchron |
| `ActuatorCommandResponse.correlation_id` | UUID des Versuchs | Gleich in WS `actuator_command` / `actuator_command_failed` und im MQTT-Command-Payload (wenn gesendet) |
| `EmergencyStopResponse.incident_correlation_id` | UUID pro Not-Aus-Request | Verknüpft Audit, WS `actuator_alert`, `kaiser/broadcast/emergency` und abgeleitete GPIO-`correlation_id` |
| `ZoneAssignResponse` / `ZoneRemoveResponse` | `mqtt_sent`, `ack_received` | Broker vs. Bridge-Ergebnis (`zone/ack`); `ack_received=None` wenn kein Warten (z. B. Mock) |
| `SubzoneAssignResponse` / `SubzoneRemoveResponse` | `mqtt_sent` only | Kein synchrones ACK in HTTP |

---

## `GET /v1/intent-outcomes`

**Nur Auslese-API:** liefert persistierte Zeilen zu Intent/Outcome für Observability und Paritätschecks. **Kein** Blocking-Command und **kein** Ersatz für Aktuator-, Zonen- oder Subzonen-Finalität.

---

## Abweichung / Aktualisierung gegenüber Epic-1-Ist-Bericht (Fußnote)

Der Bericht vom 2026-04-05 listet an einer Stelle, dass `correlation_id` **nicht** in der REST-Antwort des normalen Actuator-Commands enthalten sei. **Im aktuellen Code** ist `correlation_id` im `ActuatorCommandResponse` **pflichtig** — die OpenAPI und diese Matrix sind an den **Code** gebunden.

---

## Verweise

- MQTT-Topic-Übersicht: `.claude/reference/api/MQTT_TOPICS.md`
- WebSocket-Events: `.claude/reference/api/WEBSOCKET_EVENTS.md`
- Zone-ACK / Bridge: `src/services/mqtt_command_bridge.py`, `src/services/zone_service.py`
- Subzone ohne Bridge: `src/services/subzone_service.py`
