# ESP32 Legacy Tests - Archive

> **Status:** Archiviert - Tests wurden zu server-orchestrierten Tests migriert

**Datum:** 2025-11-26

---

## Warum archiviert?

Diese ESP32 Unity-Tests hatten ein fundamentales Architekturproblem:

**Problem:**
- PlatformIO Unity Framework linkt NUR Test-Dateien
- Production-Code (Logger, ConfigManager, etc.) wird NICHT automatisch gelinkt
- Result: `undefined reference` errors beim Build

**Lösung:**
- ✅ **Migration zu server-orchestrierten Tests (Option A)**
- Tests laufen jetzt auf God-Kaiser Server via MQTT
- Keine PlatformIO Unity Framework Limitations
- CI/CD-ready ohne ESP32-Hardware

---

## Neue Test-Architektur

**Location:** `El Servador/god_kaiser_server/tests/esp32/`

**Test Suites:**
- ✅ `test_communication.py` - ~20 Tests (MQTT connectivity)
- ✅ `test_infrastructure.py` - ~30 Tests (Config, Topics, System)
- ✅ `test_actuator.py` - ~40 Tests (Digital, PWM, Emergency Stop)
- ✅ `test_sensor.py` - ~30 Tests (Sensor reading, Pi-Enhanced)
- ✅ `test_integration.py` - ~20 Tests (Full system workflows)

**GESAMT: ~140 Tests**

**Tests ausführen:**
```bash
cd "El Servador"
poetry install
poetry run pytest god_kaiser_server/tests/esp32/ -v
```

**Dokumentation:**
- `El Servador/docs/ESP32_TESTING.md` - Vollständige Test-Dokumentation
- `El Servador/docs/MQTT_TEST_PROTOCOL.md` - MQTT Command-Spezifikation

---

## Archivierte Test-Dateien

Diese Dateien dienen als **Referenz für Test-Logik**:

### Communication Tests
- `comm_mqtt_client.cpp` → `test_communication.py` (MQTT ping, publish, subscribe)
- `comm_wifi_manager.cpp` → (Hardware-only, nicht migriert)
- `comm_http_client.cpp` → (Pi-Enhanced, in sensor tests)

### Infrastructure Tests
- `infra_config_manager.cpp` → `test_infrastructure.py` (Config get/set)
- `infra_topic_builder.cpp` → `test_infrastructure.py` (Topic formats)
- `infra_storage_manager.cpp` → (Internal, nicht testbar via MQTT)
- `infra_logger.cpp` → (Internal, nicht testbar via MQTT)
- `infra_error_tracker.cpp` → `test_infrastructure.py` (Error reporting)

### Actuator Tests
- `actuator_manager.cpp` → `test_actuator.py` (Digital, PWM control)
- `actuator_safety_controller.cpp` → `test_actuator.py` (Emergency stop)
- `actuator_pwm_controller.cpp` → `test_actuator.py` (PWM percentage)
- `actuator_integration.cpp` → `test_actuator.py` (MQTT integration)
- `actuator_config.cpp` → `test_actuator.py` (Actuator configuration)
- `actuator_models.cpp` → `test_actuator.py` (Actuator types)

### Sensor Tests
- `sensor_manager.cpp` → `test_sensor.py` (Sensor reading)
- `sensor_integration.cpp` → `test_sensor.py` (MQTT integration)
- `sensor_pi_enhanced.cpp` → `test_sensor.py` (Pi-Enhanced processing)
- `sensor_i2c_bus.cpp` → (Hardware-specific, nicht migriert)
- `sensor_onewire_bus.cpp` → (Hardware-specific, nicht migriert)

### Integration Tests
- `integration_full.cpp` → `test_integration.py` (Complete workflow)
- `integration_phase2.cpp` → `test_integration.py` (Pi-Enhanced flow)

---

## Helper-Dateien (Behalten)

**Location:** `El Trabajante/test/helpers/`

Diese Helper sind wertvoll und bleiben:
- `mock_mqtt_broker.h/cpp` - MQTT-Broker-Mock (Konzept übernommen in MockESP32Client)
- `virtual_actuator_driver.h` - Virtual-Actuator-Pattern (Konzept übernommen)
- `temporary_test_actuator.h` - RAII-Pattern für Tests (Best Practice)
- `actuator_test_helpers.h` - Test-Utilities (Referenz)

---

## Migration-Mapping

| ESP32 Test | Server Test | Status |
|------------|-------------|--------|
| `comm_mqtt_client.cpp` | `test_communication.py::TestMQTTConnectivity` | ✅ Migriert |
| `infra_config_manager.cpp` | `test_infrastructure.py::TestConfigManagement` | ✅ Migriert |
| `infra_topic_builder.cpp` | `test_infrastructure.py::TestTopicFormats` | ✅ Migriert |
| `actuator_manager.cpp` | `test_actuator.py::TestDigitalActuatorControl` | ✅ Migriert |
| `actuator_safety_controller.cpp` | `test_actuator.py::TestEmergencyStop` | ✅ Migriert |
| `actuator_pwm_controller.cpp` | `test_actuator.py::TestPWMActuatorControl` | ✅ Migriert |
| `sensor_manager.cpp` | `test_sensor.py::TestSensorReading` | ✅ Migriert |
| `sensor_integration.cpp` | `test_sensor.py::TestSensorIntegration` | ✅ Migriert |
| `integration_full.cpp` | `test_integration.py::TestCompleteSensorActuatorFlow` | ✅ Migriert |
| `integration_phase2.cpp` | `test_integration.py::TestPiEnhancedFlow` | ✅ Migriert |

---

## Warum diese Tests behalten?

**Als Referenz für:**
1. **Test-Logik** - Was sollte getestet werden
2. **Edge-Cases** - Welche Szenarien wurden bedacht
3. **Hardware-Details** - I2C, OneWire, GPIO-spezifische Implementierung
4. **Test-Patterns** - Dual-Mode, RAII, VirtualDriver-Konzepte

**NICHT zum Ausführen!**
Diese Tests können nicht mehr gebaut werden (undefined reference errors).

---

## Siehe auch

- **Neue Tests:** `El Servador/god_kaiser_server/tests/esp32/`
- **Test-Dokumentation:** `El Servador/docs/ESP32_TESTING.md`
- **MQTT Test Protocol:** `El Servador/docs/MQTT_TEST_PROTOCOL.md`
- **Migration-Status:** `.claude/TEST_WORKFLOW.md`
- **CLAUDE.md:** Section 7 (Test-Ausführung)

---

**Letzte Aktualisierung:** 2025-11-26
**Archiviert von:** PlatformIO Unity Tests
**Migriert zu:** Server-orchestrierte pytest Tests
