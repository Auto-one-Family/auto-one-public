# God-Kaiser Pi Server (El Servador)

FastAPI-basiertes Backend für AutomationOne IoT-Framework.

> **Für KI-Agenten:** Siehe `.claude/commands/CLAUDE_SERVER.md` für vollständige Server-Dokumentation und Orientierung im Code.

## Features
- REST API (FastAPI) mit vollständiger Test-Suite
- WebSocket Real-time Communication
- MQTT Integration (Mosquitto)
- Dynamic Sensor Library Loading
- Cross-ESP Automation Logic (UUID-basiert)
- PostgreSQL Database (SQLAlchemy Async)
- God AI Integration
- **Comprehensive ESP32 Testing Framework** (140+ Tests)
- **API Integration Tests** (13+ Logic Tests)
- **MQTT/Logic konfigurierbar:** Worker-Pool (`MQTT_SUBSCRIBER_MAX_WORKERS`) und Logic-Scheduler-Intervall (`LOGIC_SCHEDULER_INTERVAL_SECONDS`) per Settings steuerbar
- **DB-aggregierte Sensor-Statistiken:** min/max/avg/stddev + Qualitätsverteilung ohne Voll-Load ins RAM
- **Notifications erweitert:** WebSocket + SMTP (optional) + Webhook mit Timeout/Status-Checks

## Setup
```bash
poetry install
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

---

## USB Device Detection (AUT-765)

`GET /api/v1/flash/devices` — erkennt angeschlossene ESP32-Boards via USB VID/PID.
Benötigt Operator-JWT. Grundlage für den Flash-Workflow (FC-08a-5).

### VID/PID-Unterstützung

| VID:PID | Chip | Board |
|---|---|---|
| 0x1A86:0x7523 | CH340 | ESP32 WROOM-32 (Standard Dev-Board) |
| 0x10C4:0xEA60 | CP2102 | ESP32 WROOM-32 (Silabs-Variante) |
| 0x303A:0x1001 | ESP32-S3 | Seeed XIAO ESP32-S3 (built-in USB) |
| 0x303A:0x0002 | ESP32-S3 | DevKitC-1 (JTAG/OTA) |
| 0x303A:0x4001 | ESP32-C3 | C3-DevKit (CDC/JTAG) |
| alle anderen | – | `chip_family="unknown"` (wird gelistet, nicht gefiltert) |

### Platform-Pfade

**Raspberry Pi (Linux, Docker):**

Serielle Devices in den Container durchreichen via `docker-compose.override.yml`:

```yaml
services:
  el-servador:
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
      - /dev/ttyUSB1:/dev/ttyUSB1
      - /dev/ttyACM0:/dev/ttyACM0
      - /dev/ttyACM1:/dev/ttyACM1
```

Sobald die Devices gemountet sind, erkennt der Scanner sie automatisch (keine zusätzliche Env-Variable nötig).

**Windows nativ (uvicorn ohne Docker):**

pyserial sieht COM-Ports direkt — kein Setup nötig:
```bash
cd El\ Servador/god_kaiser_server
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

**Windows Docker (dev-local Standard):**

Docker-Container (Linux) sieht keine Windows COM-Ports. Der Endpoint gibt **503** mit Error-Code `3101` zurück:
```json
{
  "error_code": 3101,
  "detail": "USB serial scanning is not available...",
  "platform_note": "docker-windows-degraded"
}
```

Optional: USB-Passthrough via [usbipd-win](https://github.com/dorssel/usbipd-win) → WSL2-Durchreichung, dann `USB_SCANNING_AVAILABLE=true` setzen.

### Env-Variable Override

| Variable | Wert | Effekt |
|---|---|---|
| `USB_SCANNING_AVAILABLE` | `true` | Erzwingt Scanning (z.B. usbipd-win konfiguriert) |
| `USB_SCANNING_AVAILABLE` | `false` | Erzwingt Degraded-Mode (z.B. auf Pi ohne device-bind) |
| nicht gesetzt | – | Auto-Detection: Windows native = true; Linux mit `/dev/tty*` = true; sonst false |

## Architecture
Siehe `/docs/ARCHITECTURE.md`

---

## Konfiguration (Auszug)
- `MQTT_SUBSCRIBER_MAX_WORKERS` (default 10): Threadpool-Größe für MQTT-Handler
- `LOGIC_SCHEDULER_INTERVAL_SECONDS` (default 60): Intervall für zeitbasierte Rule-Evaluierung
- SMTP (optional): `SMTP_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM`
- Webhook: `WEBHOOK_TIMEOUT_SECONDS` (default 5)

---

## ESP32 Testing

### Test-Architektur

Tests verwenden **bewusst die echte MQTT-Struktur** (nicht separate Test-Topics).

**Warum?**
- Tests laufen gegen Mock-Clients UND echte Hardware
- Pre-Production-Validation mit identischer Topic-Struktur
- Cross-ESP-Orchestrierung möglich
- Seamless CI/CD → Staging → Production flow

**Test-Kategorien:**
- **Communication** (~20 Tests): MQTT connectivity, ping/pong, response times
- **Infrastructure** (~30 Tests): Config management, system status
- **Actuator** (~40 Tests): Digital/PWM control, emergency stop
- **Sensor** (~30 Tests): Reading, Pi-Enhanced processing
- **Integration** (~20 Tests): Full system workflows
- **Cross-ESP** (~15 Tests): Multi-device orchestration
- **Performance** (~15 Tests): Load testing, throughput
- **API Logic** (~13 Tests): Rules CRUD, toggle, test, execution history

**Total:** 150+ Tests

---

### Tests ausführen

**ESP32 Mock-Tests (keine Hardware nötig):**
```bash
# Alle ESP32-Tests außer Hardware-Tests (Standard)
poetry run pytest god_kaiser_server/tests/esp32/ -v

# Nur bestimmte Kategorie
poetry run pytest god_kaiser_server/tests/esp32/test_communication.py -v

# Performance-Tests
poetry run pytest god_kaiser_server/tests/esp32/ -m performance -v

# Cross-ESP-Tests
poetry run pytest god_kaiser_server/tests/esp32/test_cross_esp.py -v
```

**API Integration Tests:**
```bash
# Logic Rules API Tests
poetry run pytest god_kaiser_server/tests/integration/test_api_logic.py -v --no-cov

# Alle Integration Tests
poetry run pytest god_kaiser_server/tests/integration/ -v --no-cov
```

**Real-Hardware-Tests (benötigt ESP32):**
```bash
# Environment-Variablen setzen
export ESP32_TEST_DEVICE_ID=esp32-001
export MQTT_BROKER_HOST=localhost
export MQTT_BROKER_PORT=1883

# Hardware-Tests ausführen
poetry run pytest god_kaiser_server/tests/esp32/ -m hardware -v
```

**Mit Coverage:**
```bash
poetry run pytest god_kaiser_server/tests/esp32/ --cov --cov-report=html
# Coverage-Report: htmlcov/index.html
```

**Test-Marker:**
- `unit`: Unit tests (Mock only, fast)
- `integration`: Integration tests
- `hardware`: Real hardware tests (requires ESP32)
- `performance`: Performance/load tests
- `cross_esp`: Multi-device tests
- `slow`: Tests > 1 second

---

### Test-Dokumentation

**Vollständige Dokumentation:**
- [`docs/ESP32_TESTING.md`](docs/ESP32_TESTING.md) - Kompletter Testing-Guide
- [`docs/MQTT_TEST_PROTOCOL.md`](docs/MQTT_TEST_PROTOCOL.md) - MQTT Command-Spezifikation
- [`docs/TEST_COVERAGE_ANALYSIS.md`](docs/TEST_COVERAGE_ANALYSIS.md) - Coverage-Analyse

**API-Dokumentation:**
- MockESP32Client: [`tests/esp32/mocks/mock_esp32_client.py`](god_kaiser_server/tests/esp32/mocks/mock_esp32_client.py)
- RealESP32Client: [`tests/esp32/mocks/real_esp32_client.py`](god_kaiser_server/tests/esp32/mocks/real_esp32_client.py)

---

### CI/CD Integration

**GitHub Actions Workflow (Beispiel):**
```yaml
name: ESP32 Tests

on: [push, pull_request]

jobs:
  test-mock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install Poetry
        run: pip install poetry
      - name: Install dependencies
        run: poetry install
      - name: Run Mock Tests
        run: poetry run pytest god_kaiser_server/tests/esp32/ -m "not hardware" -v
```

---

### Beispiel-Tests

**Actuator Control:**
```python
def test_actuator_control(mock_esp32):
    # Turn pump ON
    response = mock_esp32.handle_command("actuator_set", {
        "gpio": 5, "value": 1, "mode": "digital"
    })
    assert response["status"] == "ok"
    assert response["state"] is True
```

**Cross-ESP Orchestration:**
```python
def test_cross_esp(multiple_mock_esp32):
    esps = multiple_mock_esp32
    
    # Read sensor on ESP-002
    sensor = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
    
    # Control actuator on ESP-001
    if sensor["data"]["raw_value"] < 2500:
        esps["esp1"].handle_command("actuator_set", {
            "gpio": 5, "value": 1, "mode": "digital"
        })
```

**Performance Test:**
```python
@pytest.mark.performance
def test_throughput(mock_esp32):
    start = time.time()
    for i in range(100):
        mock_esp32.handle_command("sensor_read", {"gpio": 34})
    elapsed = time.time() - start
    
    assert elapsed < 1.0  # < 1 second for 100 reads
```

---

### Troubleshooting

**Tests nicht gefunden:**
```bash
# Sicherstellen, dass du im richtigen Verzeichnis bist
cd El Servador
poetry run pytest god_kaiser_server/tests/esp32/ -v
```

**Import-Errors:**
```bash
# Dependencies installieren
poetry install
```

**Hardware-Tests skippen:**
```bash
# Default: Hardware-Tests werden automatisch geskippt
poetry run pytest god_kaiser_server/tests/esp32/ -v
```

---

