# Emergency-Stop: MQTT-Korrelation (Incident → GPIO)

**Kontext:** `POST /api/v1/actuators/emergency_stop`

Pro GPIO wird ein MQTT-Befehl `OFF` mit **`correlation_id`** gesendet. Der Wert ist deterministisch aus dem **Incident** und dem Ziel abgeleitet:

- **`incident_correlation_id`:** eine UUID pro Emergency-Request (Audit, WebSocket `actuator_alert`, Broadcast `kaiser/broadcast/emergency`).
- **Pro GPIO:** `correlation_id` im MQTT-Payload =  
  `build_emergency_actuator_correlation_id(incident_correlation_id, esp_id, gpio)`  
  → Format `{incident_uuid}:{esp_id}:{gpio}` (Doppelpunkte, JSON-sicher).

Die **Actuator-History** (`command_metadata`) speichert dieselbe Zeichenkette unter **`correlation_id`** und **`mqtt_correlation_id`** sowie **`incident_correlation_id`**, damit Support und E2E-Auswertung ohne Heuristik vom gesendeten MQTT zum Incident kommen. Antworten der Firmware auf `actuator/.../response` sind nur dann über dieselbe ID zuordenbar, wenn die Firmware `correlation_id` zurückspiegelt (optional; serverseitig reicht die gesendete ID für den Sendepfad).

**Code:** `src/api/v1/actuators.py` (`emergency_stop`), `src/core/request_context.py` (`build_emergency_actuator_correlation_id`), `src/mqtt/publisher.py` (`publish_actuator_command`).

**Analyse:** `docs/analyse/report-server-epic1-ist-vertrag-korrelation-verdrahtung-2026-04-05.md` (Abschnitt AP-B).
