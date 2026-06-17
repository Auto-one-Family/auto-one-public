# Intent-Orchestrierung: `command_intents.orchestration_state`

Support-Kurzreferenz (Epic 1-05). Terminalität des Befehls selbst steht in **`command_outcomes`**, nicht in dieser Spalte.

**Hinweis:** `GET /api/v1/intent-outcomes` ist nur Auslese-API (persistierte Zeilen), kein Blocking-Command — siehe `../finalitaet-http-mqtt-ws.md`.

## Erlaubte Werte

| Wert | Bedeutung | Wer setzt es? |
|------|-----------|----------------|
| **`sent`** | Der Broker hat die **Server→ESP**-MQTT-Nachricht akzeptiert (Publish erfolgreich). Es liegt noch **kein** eingehendes `intent_outcome` vor. | `CommandContractRepository.record_intent_publish_sent` nach erfolgreichem Publish (z. B. `ActuatorService.send_command`, Emergency-Stop pro GPIO). |
| **`accepted`** | Eingehendes `intent_outcome` mit kanonischem Outcome **`accepted`**. | `upsert_intent` im `intent_outcome_handler`. |
| **`ack_pending`** | Eingehendes `intent_outcome` mit jedem **anderen** Outcome in diesem Event (z. B. `applied`, Zwischenzustände) — Verarbeitung/Terminalität weiter in `command_outcomes`. | `upsert_intent` im `intent_outcome_handler`. |

## Typischer Aktor-Befehl

1. Server published `…/actuator/{gpio}/command` mit `correlation_id` und **`intent_id`** (gleicher Wert wie `correlation_id`).
2. DB: `orchestration_state` → **`sent`**.
3. ESP sendet `intent_outcome` → **`accepted`** oder **`ack_pending`** je nach Outcome-String.

## „Intent hängt in ack_pending — was bedeutet das?“

**Kein Lieferproblem allein:** `ack_pending` heißt hier: der letzte verarbeitete **`intent_outcome`**-Event war **nicht** das kanonische „accepted“, sondern ein anderer Outcome-Typ in derselben MQTT-Nachricht (z. B. Fortschritt oder bereits `applied`). Die **finale** Bewertung (persisted / failed / …) steht in **`command_outcomes`** und in Audit/WS für das Outcome.

Wenn **gar kein** `intent_outcome` ankommt, bleibt die Zeile bei **`sent`** (sofern der Publish-Pfad sie geschrieben hat) — dann Broker/ESP/Netz prüfen, nicht die Spalte `ack_pending` interpretieren.

## MQTT-Duplikate (Stale)

Wenn derselbe `intent_outcome` erneut eintrifft und als **stale** verworfen wird, bestätigt der Handler die MQTT-Nachricht trotzdem, schreibt aber **keinen** zweiten Audit-Eintrag und **kein** WebSocket-Event (siehe Modul-Docstring `intent_outcome_handler`).
