# Runtime-Mindestbasis und Profile

Diese Spezifikation definiert den verbindlichen Vertrag fuer den Exit aus `CONFIG_PENDING_AFTER_RESET`.

## Ziel

Nach Reset darf die Firmware den Pending-Zustand nur verlassen, wenn die Runtime-Basis laut Policy vollstaendig ist.

## Verbindliche Policy

- Default-Profil: `sensor_required`
- Aktoren: **optional** (`require_actuator = false` seit `runtime_readiness_policy.cpp:6`). Sensor-only Geraete koennen `CONFIG_PENDING_AFTER_RESET` verlassen ohne konfigurierten Aktor.
- Offline-Rules sind fuer Pending-Exit optional.
  - Bei `offline_rule_count == 0` bleibt Disconnect-Verhalten fail-safe:
    Aktoren werden sofort auf `default_state` gesetzt.
- Sensoren:
  - `sensor_required`: mindestens ein Sensor (`sensor_count > 0`)
  - `sensor_optional`: Sensoren sind optional (fuer spaetere profile-basierte Setups)

## Entscheidungscodes

- `CONFIG_PENDING_EXIT_READY`
- `MISSING_SENSORS`
- `MISSING_ACTUATORS` (nicht mehr als Blocker, nur als informativer Reason)
- `OFFLINE_RULES_ONLY_AUTO_EXIT` (Offline-Rules vorhanden, aber keine Aktoren)

## State-Transition-Regeln

- Enter: `entered_config_pending` bei partieller Runtime-Basis nach Boot.
- Heartbeat-ACK in `CONFIG_PENDING_AFTER_RESET` triggert keinen Pending-Exit mehr; die Pruefung ist auf `config_commit` verschoben.
- Blocked Exit: `exit_blocked_config_pending` mit reason:
  - `CONFIG_PENDING_EXIT_NOT_READY` (Policy nicht erfuellt)
- Erfolgreicher Exit: `exited_config_pending` mit reason `CONFIG_PENDING_EXIT_READY`.

## Telemetrie-Felder

Jedes Transition-Event enthaelt mindestens:

- `event_type`
- `reason_code`
- `sensor_count`
- `actuator_count`
- `offline_rule_count`
- `state_before`
- `state_after`

Zusaetzlich werden Counter transportiert:

- `config_pending_enter_count`
- `config_pending_exit_count`
- `config_pending_exit_blocked_count`

## MQTT-Transport (Firmware ab 2026-04)

Lifecycle-Transition-Events (`entered_config_pending`, `exit_blocked_config_pending`, `exited_config_pending`) werden **nicht** mehr auf dem kanonischen Topic `.../system/intent_outcome` veroeffentlicht (dort nur `buildOutcomePayload`-Outcomes), sondern auf:

- `kaiser/{kaiser_id}/esp/{esp_id}/system/intent_outcome/lifecycle`

Payload-Schema-Tag: `schema` = `config_pending_lifecycle_v1`. Zusaetzlich enthaelt jedes Event `boot_sequence_id` (Korrelation zum Heartbeat / Boot-Segment).

Server-Folgeauftrag: separater Handler/Subscription fuer `intent_outcome/lifecycle` oder Wildcard `.../intent_outcome/#`.
