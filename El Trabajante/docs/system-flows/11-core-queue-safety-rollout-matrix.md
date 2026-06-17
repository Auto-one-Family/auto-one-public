# Core Queue Safety Rollout Matrix (R0-R4)

## Ziel
Verifizierbarer Rollout fuer den Intent-/Outcome-Vertrag auf den Core-Queues mit klaren Go/No-Go-Kriterien und Rollback-Regeln.

## R0 - Shadow-Messung
- Aktiv: `system/intent_outcome` Publish (accepted/rejected/applied/failed/expired).
- Aktiv: Korrelation (`intent_id`, `correlation_id`, `generation`, `epoch`).
- Verhalten: keine funktionale Blockade ausser bestehender Validierung.
- Gate (24h):
  - Unkorrelierbare Outcomes <= 0.1%.
  - Keine Abstuerze/Watchdog-Resets durch Outcome-Publish.

## R1 - Admission-Haertung
- Aktiv: sofortiges `rejected/QUEUE_FULL` fuer:
  - `queueActuatorCommand()`
  - `queueSensorCommand()`
  - `queueConfigUpdateWithMetadata()`
- Gate (24h):
  - Silent-Drop Command = 0.
  - Admission-Timeout/Queue-Full fuer Config < 0.5% p95.

## R2 - Emergency-Barrier
- Aktiv: `safety_epoch` Inkrement bei Emergency.
- Aktiv: Intent-Invalidierung bei Dequeue (`expired/SAFETY_EPOCH_INVALIDATED` oder `expired/TTL_EXPIRED`).
- Aktiv: Flush mit terminalem Outcome bei Emergency.
- Gate (24h):
  - Post-Emergency-Verstossereignisse = 0.
  - Alle pre-Epoch Intents terminieren deterministisch.

## R3 - Config-Reconciliation
- Aktiv: Persistenter Pending-Store (`cfg_pending`) mit Ring-Capacity.
- Aktiv: Replay auf Safety-Task-Start (`accepted` mit `REPLAY` Code).
- Aktiv: terminales Entfernen aus Pending-Store nach `applied/failed/expired`.
- Gate (24h):
  - Reconnect-Reconciliation p95 < 10s.
  - Reboot-Reconciliation p95 < 30s.

## R4 - Publish-Lanes und Fairness
- Aktiv: kritische Publish-Lane (`/response`, `/alert`, `/config_response`, `/system/error`, `/system/intent_outcome`).
- Aktiv: Retry fuer kritische Queue-Drains, terminales `failed` bei Endfehler.
- Aktiv: Budget-Drain fuer Fairness (Command/Sensor/Config).
- Gate (24h):
  - Verlust kritischer Publish-Events = 0.
  - E2E Latenz p95 kritische Pfade < 250ms.

## Rollback-Regel
- Jede Phase ist isoliert ruecknehmbar.
- Bei Gate-Verletzung: sofort auf vorherige Phase zurueck.
- Keine Promotion ohne 24h stabile Metrik-Einhaltung.
