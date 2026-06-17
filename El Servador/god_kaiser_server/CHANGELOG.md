# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **MQTTCommandBridge / Zone-ACK:** `resolve_ack` matches pending HTTP/MQTT waits **only** by `correlation_id` present in the ACK payload and registered in `_pending`. The previous **FIFO fallback** per `(esp_id, command_type)` is removed to avoid wrong pairing when multiple zone/subzone operations run in parallel. **Breaking for firmware:** if the ESP sends `zone/ack` or `subzone/ack` **without** echoing the server-issued `correlation_id` from the assign message, the REST caller will see **ACK timeout** (`mqtt_sent=false`, `ack_received=false`) even though the device may have applied the change. **Mitigation:** firmware must echo `correlation_id` on ACKs (see El Trabajante zone/subzone handlers). **Ops:** if assign/remove times out, verify ACK JSON includes `correlation_id` and broker delivery. Structured **WARNING** logs: `ACK dropped: no correlation match (...)` with `esp_id`, `command_type`, `pending_queue_len`.
- **`DELETE /api/v1/zone/devices/{id}/zone`:** `ZoneRemoveResponse` now includes optional **`ack_received`** and **`warning`** (same semantics as zone assign). Message **`Zone removed (ACK timeout)`** when the bridge times out waiting for `zone/ack` (instead of lumping with MQTT offline).
- **API:** `POST /api/v1/actuators/{esp_id}/{gpio}/command` response (`ActuatorCommandResponse`) now includes **`correlation_id`** (UUID, matches WebSocket `actuator_command` / `actuator_command_failed` and MQTT for the same attempt) and populates **`safety_warnings`** from `SafetyService` when `valid=True`. **`command_sent`** is `false` when the command is skipped as a no-op (desired state already equals current) while **`correlation_id`** is still returned for tracing.
- **`ActuatorService.send_command`** returns **`ActuatorSendCommandResult`** (success, correlation_id, command_sent, safety_warnings) instead of a bare `bool`; internal callers updated. DB work reuses the **injected repository session** when it is still active (typical REST request), otherwise **`get_session()`** (global LogicEngine instance after startup).
- Logic rule `priority`: OpenAPI field descriptions (`LogicRuleCreate` / `LogicRuleUpdate` / `LogicRuleResponse`) aligned with runtime semantics — lower numeric value means higher execution and conflict priority; E2E test comments for priority clarified accordingly.

### Added

- **`command_intents.orchestration_state = sent`:** After a successful actuator-command MQTT publish (with `correlation_id`), the server persists **`sent`** via `CommandContractRepository.record_intent_publish_sent`. `Publisher.publish_actuator_command` adds **`intent_id`** (same value as `correlation_id`) so firmware `IntentMetadata` matches the DB row. Emergency stop records **`sent`** per successful GPIO publish. Operator notes: `docs/support/intent_orchestration_state.md`.
- Emergency stop (`POST /v1/actuators/emergency_stop`): each per-GPIO MQTT OFF command includes a deterministic `correlation_id` derived from `incident_correlation_id`, `esp_id`, and GPIO; actuator command history stores the same value under **`correlation_id`** and **`mqtt_correlation_id`** in `command_metadata` for support queries. See `docs/emergency-stop-mqtt-correlation.md`. Integration test asserts `publish_actuator_command(..., correlation_id=…)` on the emergency path.
