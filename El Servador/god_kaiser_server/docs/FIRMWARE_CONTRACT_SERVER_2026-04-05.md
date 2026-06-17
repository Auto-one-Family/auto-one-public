# Server: Firmware-Vertrag April 2026 (Kurzchangelog)

**Datum:** 2026-04-05

El Servador wurde an die aktuelle El-Trabajante-Spezifikation angeglichen: zusätzliche Intent-Flows (`zone`, `subzone_*`, `offline_rules`), verschachtelte Intent-Metadaten unter `data.*`, separates MQTT-Topic `system/intent_outcome/lifecycle` für CONFIG_PENDING-Transitions (Persistenz in `audit_logs`, WebSocket-Event `intent_outcome_lifecycle`). Heartbeat-spezifische Telemetrie (z. B. `persistence_degraded`, `network_degraded`, Outbox-/Critical-Drop-Zähler) wird in `esp_heartbeat_logs.runtime_telemetry` (JSONB/JSON je Dialekt) gespeichert und in `esp_health`-Broadcasts mit ausgeliefert. Zone- und Subzone-ACKs werten optional `reason_code` aus (Metrik `mqtt_ack_reason_code_total`, Bridge-Daten, WS-Payload).

**Frontend/Ops:** Neue WS-Events bzw. Felder möglich (`intent_outcome_lifecycle`, `reason_code` bei Zone/Subzone, erweiterte `esp_health`-Felder). Prometheus: u. a. `intent_outcome_firmware_code_total`, `intent_outcome_lifecycle_total`, `heartbeat_firmware_flag_total`.

**Migration:** `esp_hb_runtime_telemetry` (Spalte `runtime_telemetry` auf `esp_heartbeat_logs`).
