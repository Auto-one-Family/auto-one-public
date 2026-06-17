# ESP32 Testing Guide - Server-Orchestrated Tests

> **Dokumentation für server-orchestrierte ESP32-Tests via MQTT**

**Version:** 1.1
**Datum:** 2025-12-03
**Status:** ✅ Implementiert & Erweitert

> **Letzte Änderungen (2025-12-03):**
> - 34 neue Integration-Tests für Handler hinzugefügt
> - Bug-Fixes durch Tests entdeckt und dokumentiert
> - Test-Location: `tests/integration/test_server_esp32_integration.py`

---

## Überblick

ESP32-Tests werden vom God-Kaiser Server via MQTT-Commands orchestriert. Dies ermöglicht:

- ✅ **Hardware-unabhängige Tests** (MockESP32Client)
- ✅ **CI/CD-Integration** (pytest ohne physische ESPs)
- ✅ **Real-Hardware Integration-Tests** (via MQTT an echte ESPs)
- ✅ **Schneller Feedback-Loop** (keine PlatformIO Build-Wartezeit)

---

## Architektur

```
┌─────────────────────────────────────────┐
│ God-Kaiser Server (pytest)              │
│ ├── MockESP32Client (Hardware-Mock)     │
│ ├── RealESP32Client (MQTT zu Hardware)  │
│ └── Test Suites (~140 Tests)            │
└─────────────────────────────────────────┘
            ↕ MQTT Test Commands
┌─────────────────────────────────────────┐
│ ESP32 Device (El Trabajante)            │
│ ├── Test Command Handler (optional)     │
│ ├── Production MQTT Topics (existing)   │
│ └── Actuators, Sensors, Config          │
└─────────────────────────────────────────┘
```

**Kern-Konzept:**
- Server sendet Test-Commands via MQTT
- ESP32 (Mock oder Real) führt Commands aus
- Server verifiziert Responses und State

---

## Warum echte MQTT-Topics für Tests?

**Design-Entscheidung:** Tests verwenden die IDENTISCHE MQTT-Topic-Struktur wie Production.

**Vorteile:**
1. **Real-Hardware-Tests:** Tests laufen unverändert gegen echte ESPs
2. **Pre-Production-Validation:** Exakte Produktionsumgebung testbar
3. **Cross-ESP-Szenarien:** Mehrere ESPs können orchestriert werden
4. **Keine Topic-Duplikation:** Ein Protokoll für Mock + Real
5. **CI/CD → Staging → Production:** Nahtloser Übergang

**Alternative (abgelehnt):** Separate Test-Topics (`test/command`, `test/response`)
- ❌ Erfordert doppelte Topic-Struktur auf ESP32
- ❌ Tests validieren nicht die echte Message-Routing-Logik
- ❌ Keine Real-Hardware-Tests ohne Code-Änderung

**Topic-Struktur** (identisch zu Production):
```
kaiser/god/esp/{esp_id}/actuator/{gpio}/command
kaiser/god/esp/{esp_id}/actuator/{gpio}/status
kaiser/god/esp/{esp_id}/sensor/{gpio}/data
kaiser/god/esp/{esp_id}/config
kaiser/broadcast/emergency
```

Siehe: [`El Trabajante/docs/Mqtt_Protocoll.md`](../../El Trabajante/docs/Mqtt_Protocoll.md)

---

## Test-Kategorien

### 1. Communication Tests (`test_communication.py`)

**Zweck:** MQTT-Connectivity und Command-Response-Cycle

**Test-Klassen:**
- `TestMQTTConnectivity` - Ping/Pong, Response-Zeit
- `TestCommandResponseCycle` - Command-Response für alle Commands
- `TestErrorHandling` - Fehlerbehandlung
- `TestMQTTPublishing` - MQTT-Message-Publishing
- `TestResponseFormat` - Response-Format-Validierung
- `TestConcurrentCommands` - Mehrfache Commands

**Beispiel:**
```python
def test_mqtt_ping(mock_esp32):
    response = mock_esp32.handle_command("ping", {})

    assert response["status"] == "ok"
    assert response["command"] == "pong"
    assert "esp_id" in response
```

---

### 2. Infrastructure Tests (`test_infrastructure.py`)

**Zweck:** Konfiguration, Topics, System-Status

**Test-Klassen:**
- `TestConfigManagement` - Config Get/Set
- `TestTopicFormats` - MQTT-Topic-Validierung
- `TestSystemStatus` - System-Info, Uptime
- `TestErrorHandling` - Error-Responses
- `TestConfigPersistence` - Config-Persistenz
- `TestResetFunctionality` - Reset-Command
- `TestWiFiConfiguration` - WiFi-Config
- `TestZoneConfiguration` - Zone-Config

**Beispiel:**
```python
def test_config_get_all(mock_esp32):
    response = mock_esp32.handle_command("config_get", {})

    config = response["data"]["config"]
    assert "wifi" in config
    assert "zone" in config
    assert "system" in config
```

---

### 3. Actuator Tests (`test_actuator.py`)

**Zweck:** Actuator-Control (Digital, PWM, Emergency Stop)

**Test-Klassen:**
- `TestDigitalActuatorControl` - ON/OFF Control
- `TestPWMActuatorControl` - PWM (0.0-1.0)
- `TestEmergencyStop` - Emergency Stop (SAFETY!)
- `TestActuatorStatePersistence` - State-Persistenz
- `TestMQTTStatusPublishing` - Status-Messages
- `TestActuatorTypes` - Pump, Valve, PWM Motor
- `TestActuatorErrors` - Error-Handling
- `TestActuatorConcurrency` - Concurrent Operations

**Beispiel:**
```python
def test_emergency_stop_all_actuators(mock_esp32_with_actuators):
    # Turn all actuators ON
    for gpio in [5, 6, 7]:
        mock_esp32_with_actuators.handle_command("actuator_set", {
            "gpio": gpio, "value": 1, "mode": "digital"
        })

    # Emergency stop
    response = mock_esp32_with_actuators.handle_command("emergency_stop", {})

    # Verify ALL stopped
    for gpio in [5, 6, 7]:
        actuator = mock_esp32_with_actuators.get_actuator_state(gpio)
        assert actuator.state is False
```

---

### 4. Sensor Tests (`test_sensor.py`)

**Zweck:** Sensor-Reading, Pi-Enhanced Processing

**Test-Klassen:**
- `TestSensorReading` - RAW-Value Reading
- `TestSensorDataPublishing` - MQTT Data Publishing
- `TestPiEnhancedProcessing` - Server-side Processing
- `TestMultipleSensors` - Multiple Sensor Operations
- `TestSensorTimestamps` - Timestamp-Tracking
- `TestSensorTypes` - Analog, Digital, I2C, OneWire
- `TestSensorValueChanges` - Value Simulation
- `TestSensorIntegration` - Integration with Actuators

**Beispiel:**
```python
def test_sensor_read_analog(mock_esp32_with_sensors):
    # GPIO 34 ist analog sensor (moisture)
    response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})

    assert response["status"] == "ok"
    assert response["data"]["type"] == "analog"
    assert "raw_value" in response["data"]
```

---

### 5. Integration Tests (`test_integration.py`)

**Zweck:** Full-System-Workflows, End-to-End

**Test-Klassen:**
- `TestCompleteSensorActuatorFlow` - Sensor → Actuator
- `TestMQTTOrchestration` - MQTT Message Flow
- `TestEmergencyScenarios` - Emergency Stop Workflows
- `TestSystemConfiguration` - Complete System Status
- `TestPiEnhancedFlow` - RAW → Server → Processed
- `TestSystemReset` - Reset Functionality
- `TestConcurrentOperations` - Concurrent Sensor+Actuator
- `TestSystemHealth` - Health Monitoring
- `TestErrorRecovery` - Error Recovery
- `TestFullSystemWorkflow` - Greenhouse Automation Scenario

**Beispiel:**
```python
def test_greenhouse_automation_scenario(mock_esp32_with_sensors):
    # 1. Read soil moisture
    moisture_response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
    moisture = moisture_response["data"]["raw_value"]

    # 2. Control irrigation
    if moisture < 2000:
        pump_response = mock_esp32_with_sensors.handle_command("actuator_set", {
            "gpio": 5, "value": 1, "mode": "digital"
        })
        assert pump_response["status"] == "ok"
```

---

### 6. Server Handler Integration Tests (`test_server_esp32_integration.py`) - NEU

**Zweck:** Testen der Server-Handler mit echten ESP32-Payloads

**Location:** `tests/integration/test_server_esp32_integration.py`

**Test-Klassen (34 Tests):**
- `TestTopicParsing` - MQTT Topic-Parser Validierung
- `TestSensorHandlerValidation` - Payload-Struktur-Validierung
- `TestSensorHandlerProcessing` - Vollständige Sensor-Datenverarbeitung
- `TestActuatorHandlerValidation` - Actuator-Payload-Validierung
- `TestActuatorHandlerProcessing` - Actuator-Status-Verarbeitung
- `TestFullMessageFlow` - End-to-End MQTT → DB Flows
- `TestEdgeCases` - Grenzfälle und Error-Handling
- `TestPerformance` - 100 schnelle Updates
- `TestHeartbeatHandlerValidation` - Heartbeat-Validierung
- `TestHeartbeatHandlerProcessing` - Heartbeat-Verarbeitung
- `TestPiEnhancedProcessing` - Pi-Enhanced Flow mit Library-Loader
- `TestCompleteWorkflows` - Multi-Sensor Batch-Verarbeitung

**Besonderheiten:**
- Nutzt SQLite In-Memory (kein PostgreSQL nötig)
- Payloads exakt wie ESP32 sie sendet (aus `Mqtt_Protocoll.md`)
- Handler werden direkt aufgerufen (keine MQTT-Verbindung)
- Bug-Dokumentation: `tests/integration/BUGS_FOUND.md`

**Beispiel:**
```python
@pytest.mark.asyncio
async def test_handle_sensor_data_success(test_session, sample_esp_device, sample_sensor_config):
    handler = SensorDataHandler()
    handler.publisher = MagicMock()
    
    topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
    payload = {
        "ts": int(time.time()),
        "esp_id": "ESP_12AB34CD",
        "gpio": 34,
        "sensor_type": "ph",
        "raw": 2150,
        "value": 0.0,
        "unit": "",
        "quality": "good",
        "raw_mode": False,
    }
    
    async def mock_get_session():
        yield test_session
    
    with patch('src.mqtt.handlers.sensor_handler.get_session', mock_get_session):
        result = await handler.handle_sensor_data(topic, payload)
    
    assert result is True
```

**Ausführung:**
```bash
cd "El Servador/god_kaiser_server"
python -m pytest tests/integration/test_server_esp32_integration.py -v --no-cov
```

---

## Test ausführen

### Alle Tests

```bash
cd "El Servador/god_kaiser_server"
python -m pytest tests/ --no-cov -q
```

### Spezifische Test-Kategorie

```bash
# Communication Tests
poetry run pytest god_kaiser_server/tests/esp32/test_communication.py -v

# Infrastructure Tests
poetry run pytest god_kaiser_server/tests/esp32/test_infrastructure.py -v

# Actuator Tests
poetry run pytest god_kaiser_server/tests/esp32/test_actuator.py -v

# Sensor Tests
poetry run pytest god_kaiser_server/tests/esp32/test_sensor.py -v

# Integration Tests
poetry run pytest god_kaiser_server/tests/esp32/test_integration.py -v
```

### Spezifischer Test

```bash
poetry run pytest god_kaiser_server/tests/esp32/test_communication.py::TestMQTTConnectivity::test_mqtt_ping -v
```

### Mit Coverage

```bash
poetry run pytest god_kaiser_server/tests/esp32/ --cov=god_kaiser_server/tests/esp32/mocks --cov-report=html
```

---

## Fixtures

### `mock_esp32`

Standard MockESP32Client ohne Pre-Configuration.

```python
def test_example(mock_esp32):
    response = mock_esp32.handle_command("ping", {})
    assert response["status"] == "ok"
```

### `mock_esp32_with_actuators`

Pre-configured mit 3 Actuators:
- GPIO 5: Pump (digital)
- GPIO 6: Valve (digital)
- GPIO 7: PWM Motor (pwm)

```python
def test_example(mock_esp32_with_actuators):
    response = mock_esp32_with_actuators.handle_command("actuator_get", {})
    assert len(response["data"]["actuators"]) == 3
```

### `mock_esp32_with_sensors`

Pre-configured mit 3 Sensors:
- GPIO 34: Analog (Moisture, 2048.0)
- GPIO 35: Analog (Temperature, 1500.0)
- GPIO 36: Digital (Flow, 1.0)

```python
def test_example(mock_esp32_with_sensors):
    response = mock_esp32_with_sensors.handle_command("sensor_read", {"gpio": 34})
    assert response["data"]["raw_value"] == 2048.0
```

### `mock_esp32_unconfigured`

Unprovisioned ESP32 ohne Zone-Konfiguration – ideal um Safety-Checks vor Anschluss
an Produktionszonen zu testen.

```python
def test_unconfigured_rejects_actuator(mock_esp32_unconfigured):
    response = mock_esp32_unconfigured.handle_command(
        "actuator_set", {"gpio": 5, "value": 1, "mode": "digital"}
    )
    assert response["status"] == "error"
```

### `real_esp32` (TODO)

Placeholder für Real-Hardware-Tests.

```python
@pytest.mark.skip(reason="Real ESP32 not implemented yet")
def test_example(real_esp32):
    if real_esp32 is None:
        pytest.skip("No real ESP32 available")

    response = real_esp32.send_command("ping", {})
    assert response["status"] == "ok"
```

### `mqtt_test_client`

Brokerloser, in-memory MQTT-Testclient für Publish/Subscribe-Flows ohne Hardware.

```python
def test_pub_sub(mqtt_test_client):
    mqtt_test_client.publish("kaiser/god/esp/test/command", {"cmd": "ping"})
    message = mqtt_test_client.wait_for_message("kaiser/god/esp/test/command")
    assert message["payload"]["cmd"] == "ping"
```

---

## MockESP32Client API

### Commands

**Ping:**
```python
response = mock.handle_command("ping", {})
# Response: {"status": "ok", "command": "pong", "esp_id": "...", "uptime": ...}
```

**Actuator Set:**
```python
response = mock.handle_command("actuator_set", {
    "gpio": 5, "value": 1, "mode": "digital"
})
# Response: {"status": "ok", "gpio": 5, "state": true, "pwm_value": 1.0}
```

**Actuator Get:**
```python
response = mock.handle_command("actuator_get", {"gpio": 5})
# Response: {"status": "ok", "data": {"gpio": 5, "type": "...", "state": ...}}
```

**Sensor Read:**
```python
response = mock.handle_command("sensor_read", {"gpio": 34})
# Response: {"status": "ok", "data": {"gpio": 34, "type": "...", "raw_value": ...}}
```

**Config Get:**
```python
response = mock.handle_command("config_get", {"key": "wifi"})
# Response: {"status": "ok", "data": {"key": "wifi", "value": {...}}}
```

**Emergency Stop:**
```python
response = mock.handle_command("emergency_stop", {})
# Response: {"status": "ok", "stopped_actuators": [5, 6, 7]}
```

**Reset:**
```python
response = mock.handle_command("reset", {})
# Response: {"status": "ok"}
```

### Test-Helpers

**Get Actuator State:**
```python
actuator = mock.get_actuator_state(5)
assert actuator.state is True
assert actuator.pwm_value == 1.0
```

**Set Sensor Value:**
```python
mock.set_sensor_value(gpio=40, raw_value=3000.0, sensor_type="analog")
```

**Get Published Messages:**
```python
messages = mock.get_published_messages()
for message in messages:
    print(message["topic"], message["payload"])
```

**Clear Published Messages:**
```python
mock.clear_published_messages()
```

**Reset Mock:**
```python
mock.reset()  # Clear all state
```

---

## Best Practices

### 1. Clear Messages Between Tests

```python
def test_example(mock_esp32):
    mock_esp32.clear_published_messages()

    # ... execute commands ...

    messages = mock_esp32.get_published_messages()
    assert len(messages) == 1
```

### 2. Verify MQTT Publishing

```python
def test_example(mock_esp32):
    mock_esp32.clear_published_messages()

    mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

    messages = mock_esp32.get_published_messages()
    assert messages[0]["topic"] == f"kaiser/god/esp/{mock_esp32.esp_id}/actuator/5/status"
```

### 3. Test Error Cases

```python
def test_example(mock_esp32):
    response = mock_esp32.handle_command("invalid_command", {})

    assert response["status"] == "error"
    assert "Unknown command" in response["error"]
```

### 4. Use Pre-Configured Fixtures

```python
# Instead of creating actuators manually:
def test_example(mock_esp32):
    mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
    # ...

# Use pre-configured fixture:
def test_example(mock_esp32_with_actuators):
    # Actuators already configured!
    response = mock_esp32_with_actuators.handle_command("actuator_get", {})
    # ...
```

---

## Troubleshooting

### Pytest Not Installed

```bash
cd "El Servador"
poetry install
```

### Import Errors

Ensure you're in the correct directory:
```bash
cd "El Servador"
poetry run pytest ...
```

### Tests Not Found

Check file naming:
- Files: `test_*.py`
- Functions: `test_*`
- Classes: `Test*`

---

## Siehe auch

- **MQTT Test Protocol:** `El Servador/docs/MQTT_TEST_PROTOCOL.md`
- **MQTT Protocol Spec:** `El Trabajante/docs/Mqtt_Protocoll.md`
- **Test Workflow:** `.claude/TEST_WORKFLOW.md`
- **MockESP32Client Source:** `El Servador/god_kaiser_server/tests/esp32/mocks/mock_esp32_client.py`

---

## CI/CD Integration (GitHub Actions)

### Relevante Workflows

| Workflow | Datei | Trigger | Beschreibung |
|----------|-------|---------|--------------|
| **ESP32 Tests** | `.github/workflows/esp32-tests.yml` | Push/PR auf `main`, `master`, `develop` | MockESP32 Tests mit Mosquitto-Service |
| **Server Tests** | `.github/workflows/server-tests.yml` | Push/PR auf `main`, `master`, `develop` | Unit + Integration Tests mit Coverage |

### ESP32-Tests Workflow Details

**Workflow:** `esp32-tests.yml`

**Trigger-Pfade:**
- `El Servador/god_kaiser_server/tests/esp32/**`
- `El Servador/god_kaiser_server/src/mqtt/**`
- `El Servador/god_kaiser_server/src/services/**`

**Umgebung:**
- Python 3.11, Poetry 1.7.1
- Mosquitto 2 als Docker-Service (Port 1883)
- SQLite In-Memory für Tests

**Artifacts:**
- `esp32-test-results` → `junit-esp32.xml`

### Server-Tests Workflow Details

**Workflow:** `server-tests.yml`

**Jobs:**
1. **lint** - Ruff + Black Format-Check
2. **unit-tests** - Unit Tests mit Coverage
3. **integration-tests** - Integration Tests mit Mosquitto
4. **test-summary** - Ergebnisse zusammenfassen + PR-Kommentar

**Artifacts:**
- `unit-test-results` → `junit-unit.xml`, `coverage-unit.xml`
- `integration-test-results` → `junit-integration.xml`, `coverage-integration.xml`

### GitHub CLI Log-Befehle

```bash
# ============================================
# Workflow-Runs auflisten
# ============================================

# ESP32 Tests - Letzte Runs
gh run list --workflow=esp32-tests.yml --limit=10

# Server Tests - Letzte Runs
gh run list --workflow=server-tests.yml --limit=10

# Nur fehlgeschlagene Runs
gh run list --workflow=esp32-tests.yml --status=failure

# ============================================
# Logs abrufen (Run-ID aus obiger Liste)
# ============================================

# Vollständige Logs eines Runs
gh run view <run-id> --log

# Nur fehlgeschlagene Job-Logs
gh run view <run-id> --log-failed

# Spezifischen Job anzeigen
gh run view <run-id> --job=<job-id>

# ============================================
# Artifacts herunterladen
# ============================================

# Alle Artifacts eines Runs
gh run download <run-id>

# Spezifisches Artifact
gh run download <run-id> --name=esp32-test-results
gh run download <run-id> --name=unit-test-results

# ============================================
# Workflow manuell starten
# ============================================

# ESP32 Tests manuell triggern
gh workflow run esp32-tests.yml

# Server Tests manuell triggern
gh workflow run server-tests.yml
```

### Typischer KI-Workflow bei CI-Fehlern

```bash
# 1. Fehlgeschlagenen Run finden
gh run list --workflow=esp32-tests.yml --status=failure --limit=5

# 2. Logs analysieren
gh run view <run-id> --log-failed

# 3. JUnit XML herunterladen für Details
gh run download <run-id> --name=esp32-test-results

# 4. XML parsen (zeigt fehlgeschlagene Tests)
cat junit-esp32.xml | grep -A 5 "<failure"
```

### CI-Umgebung vs. Lokale Tests

| Aspekt | CI (GitHub Actions) | Lokal |
|--------|---------------------|-------|
| Database | `sqlite+aiosqlite:///./test.db` | `.env` konfigurierbar |
| MQTT | Mosquitto Docker Service | Optional lokal |
| Python | 3.11 (fest) | Poetry-Env |
| Parallelität | `-x` (stop on first fail) | Beliebig |
| Coverage | XML Reports | HTML optional |

---

**Letzte Aktualisierung:** 2026-01-05
**Version:** 1.2
**Status:** ✅ Produktionsreif mit CI/CD-Integration
