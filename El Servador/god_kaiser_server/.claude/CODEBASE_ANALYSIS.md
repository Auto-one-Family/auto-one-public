# AutomationOne Server - Codebase Analysis

> **Analyse-Datum:** 2025-12-26 (Verifiziert)
> **Analyst:** Claude Code (Opus 4.5)
> **Scope:** El Servador/god_kaiser_server - Server-Architektur, Mock-ESP Integration, Library-Flow, Test-Engine
> **Status:** ✅ VERIFIZIERT - Alle Sections mit Code abgeglichen

---

## 1. Server-Architektur

### 1.1 Startup-Sequenz (main.py)

**Lifespan-based Initialization** (Lines 70-275):

```
┌─────────────────────────────────────────────────────────────┐
│ STARTUP SEQUENCE                                            │
├─────────────────────────────────────────────────────────────┤
│ Step 0: Security Validation (Lines 85-113)                  │
│    ├─ JWT Secret Key Check                                  │
│    └─ MQTT TLS Warning                                      │
│                                                             │
│ Step 1: Database Initialization (Lines 115-123)             │
│    ├─ init_db()                                             │
│    └─ get_engine()                                          │
│                                                             │
│ Step 2: MQTT Client Setup (Lines 125-133)                   │
│    ├─ MQTTClient.get_instance()                             │
│    └─ connect() with error handling                         │
│                                                             │
│ Step 3: MQTT Handler Registration (Lines 135-202)           │
│    └─ 9 Handlers registered via Subscriber                  │
│                                                             │
│ Step 3.5: MockESPManager Integration (Lines 191-197)        │
│    └─ mock_esp_manager.set_mqtt_client(mqtt_client)         │
│                                                             │
│ Step 4: Topic Subscription (Lines 199-202)                  │
│    └─ _subscriber_instance.subscribe_all()                  │
│                                                             │
│ Step 5: WebSocket Manager (Lines 204-209)                   │
│    ├─ WebSocketManager.get_instance()                       │
│    └─ initialize()                                          │
│                                                             │
│ Step 6: Services & Logic Engine (Lines 211-265)             │
│    ├─ Safety Service                                        │
│    ├─ Actuator Service                                      │
│    ├─ Condition Evaluators (sensor, time, compound)         │
│    ├─ Action Executors (actuator, delay, notification)      │
│    ├─ LogicEngine                                           │
│    └─ LogicScheduler                                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 MQTT Handler Registry

**9 Handler registriert** (Lines 148-187):

| Handler | Topic Pattern | File |
|---------|---------------|------|
| `sensor_handler.handle_sensor_data` | `kaiser/{kaiser_id}/esp/+/sensor/+/data` | `mqtt/handlers/sensor_handler.py` |
| `actuator_handler.handle_actuator_status` | `kaiser/{kaiser_id}/esp/+/actuator/+/status` | `mqtt/handlers/actuator_handler.py` |
| `actuator_response_handler.handle_actuator_response` | `kaiser/{kaiser_id}/esp/+/actuator/+/response` | `mqtt/handlers/actuator_response_handler.py` |
| `actuator_alert_handler.handle_actuator_alert` | `kaiser/{kaiser_id}/esp/+/actuator/+/alert` | `mqtt/handlers/actuator_alert_handler.py` |
| `heartbeat_handler.handle_heartbeat` | `kaiser/{kaiser_id}/esp/+/system/heartbeat` | `mqtt/handlers/heartbeat_handler.py` |
| `discovery_handler.handle_discovery` | `kaiser/{kaiser_id}/discovery/esp32_nodes` | `mqtt/handlers/discovery_handler.py` |
| `config_handler.handle_config_ack` | `kaiser/{kaiser_id}/esp/+/config_response` | `mqtt/handlers/config_handler.py` |
| `zone_ack_handler.handle_zone_ack` | `kaiser/{kaiser_id}/esp/+/zone/ack` | `mqtt/handlers/zone_ack_handler.py` |
| `subzone_ack_handler.handle_subzone_ack` | `kaiser/{kaiser_id}/esp/+/subzone/ack` | `mqtt/handlers/subzone_ack_handler.py` |

**Hinweis:** `kaiser_id` default ist `"god"` aus Settings

### 1.3 MockESPManager Integration

**Kritische Integration** (main.py:194-197):
```python
# Connect MockESPManager to MQTT client
mock_esp_manager = MockESPManager.get_instance()
if mqtt_client:
    mock_esp_manager.set_mqtt_client(mqtt_client)
```

**Bedeutung:**
- MockESPManager erhält Zugriff auf den echten MQTT-Client
- Ermöglicht Mock-ESPs, über echten Broker zu publishen
- Callback-basierte Integration via `_create_publish_callback()`

---

## 2. Mock-ESP System

### 2.1 Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                    Debug API (debug.py)                     │
│ POST /mock-esp → Creates Mock + DB Registration             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│               MockESPManager (Singleton)                    │
│ ├─ In-Memory Store: Dict[esp_id, MockESP32Client]           │
│ ├─ MQTT Client Reference (set via set_mqtt_client())        │
│ └─ Publish Callback Factory (_create_publish_callback())    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              MockESP32Client (1525 Lines)                   │
│ ├─ BrokerMode: DIRECT (in-memory) | MQTT (real broker)      │
│ ├─ on_publish Callback (Lines 379-380)                      │
│ ├─ Full ESP32 Simulation (sensors, actuators, state)        │
│ └─ _store_and_publish() → Triggers callback                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 MockESP32Client Details

**Datei:** `tests/esp32/mocks/mock_esp32_client.py` (1525 Lines)

**BrokerMode Enum:**
```python
class BrokerMode(Enum):
    DIRECT = "direct"    # In-Memory (kein echter Broker)
    MQTT = "mqtt"        # Echter MQTT Broker
```

**Callback-Integration** (Lines 379-380):
```python
# In _store_and_publish():
if self.on_publish:
    self.on_publish(topic, payload)
```

**Simulations-Features:**
- Sensor-Daten-Generierung mit konfigurierbaren Ranges
- Actuator-State-Management
- Heartbeat-Generation (60s Intervall)
- Zone-Assignment-Handling
- Emergency-Stop-Simulation

### 2.3 MockESPManager Details

**Datei:** `services/mock_esp_manager.py`

**Singleton-Pattern:**
```python
_instance: Optional["MockESPManager"] = None

@classmethod
def get_instance(cls) -> "MockESPManager":
    if cls._instance is None:
        cls._instance = cls()
    return cls._instance
```

**MQTT-Integration:**
```python
def set_mqtt_client(self, mqtt_client):
    """Connect to real MQTT broker for publishing."""
    self._mqtt_client = mqtt_client

def _create_publish_callback(self) -> Callable:
    """Create callback for MockESP32Client to publish via real broker."""
    async def publish_callback(topic: str, payload: dict):
        if self._mqtt_client:
            await self._mqtt_client.publish(topic, payload)
    return publish_callback
```

### 2.4 Dual-Storage-System

**Mock-ESPs existieren an zwei Stellen:**

1. **In-Memory Store** (MockESPManager):
   - `self._mock_esps: Dict[str, MockESP32Client]`
   - Schneller Zugriff für Simulation
   - Verloren bei Server-Neustart

2. **PostgreSQL** (ESPRepository):
   - ESP-Device-Registrierung in `esp_devices` Tabelle
   - Persistente Speicherung
   - Ermöglicht Zone-Assignment, Config-Updates

**Erstellung via Debug API** (debug.py:98-147):
```python
@router.post("/mock-esp")
async def create_mock_esp(...):
    # 1. Create MockESP32Client in memory
    mock_esp = MockESP32Client(...)
    manager.add_mock_esp(mock_esp)

    # 2. Register in database
    esp_repo = ESPRepository(db)
    await esp_repo.create_or_update(device_create_schema)
```

---

## 3. Data Source Detection

### 3.1 SensorHandler Detection (8 Prioritäten)

**Datei:** `mqtt/handlers/sensor_handler.py`
**Methode:** `_detect_data_source()` (Lines 379-432)

```python
def _detect_data_source(self, esp_device, payload: dict) -> str:
    """
    8-Priority Detection Logic:

    1. Explicit _test_mode flag (highest priority)
    2. Explicit _source field
    3. esp_device.hardware_type == "MOCK_ESP32"
    4. esp_device.capabilities.get("mock") == True
    5. esp_id prefix "MOCK_"
    6. esp_id prefix "TEST_"
    7. esp_id prefix "SIM_"
    8. Default → PRODUCTION
    """
```

**Prioritäts-Reihenfolge:**

| Prio | Check | Result |
|------|-------|--------|
| 1 | `payload.get("_test_mode")` | `DataSource.TEST` |
| 2 | `"_source" in payload` | Explicit source value |
| 3 | `esp_device.hardware_type == "MOCK_ESP32"` | `DataSource.MOCK` |
| 4 | `esp_device.capabilities.get("mock")` | `DataSource.MOCK` |
| 5 | `esp_id.startswith("MOCK_")` | `DataSource.MOCK` |
| 6 | `esp_id.startswith("TEST_")` | `DataSource.TEST` |
| 7 | `esp_id.startswith("SIM_")` | `DataSource.SIMULATION` |
| 8 | Default | `DataSource.PRODUCTION` |

### 3.2 HeartbeatHandler Detection (7 Prioritäten)

**Datei:** `mqtt/handlers/heartbeat_handler.py`
**Methode:** `_detect_device_source()` (Lines 378-424)

```python
def _detect_device_source(self, esp_device, payload: dict) -> str:
    """
    7-Priority Detection Logic:

    1. Explicit _source field
    2. esp_device.hardware_type == "MOCK_ESP32"
    3. esp_device.capabilities.get("mock")
    4. esp_id.startswith("MOCK_") OR esp_id.startswith("ESP_MOCK")
    5. esp_id.startswith("TEST_")
    6. esp_id.startswith("SIM_")
    7. Default → PRODUCTION
    """
```

**Unterschied zu SensorHandler:**
- Keine `_test_mode` Prüfung (nur _source)
- Zusätzlich `ESP_MOCK` prefix für MOCK-Erkennung
- Auto-Discovery ist DEAKTIVIERT (unbekannte Geräte werden abgelehnt)

### 3.3 DataSource Enum

**Datei:** `db/models/enums.py`

```python
class DataSource(str, Enum):
    PRODUCTION = "production"   # Real ESP32 devices
    MOCK = "mock"               # MockESP32Client / Debug API
    TEST = "test"               # Temporary test data
    SIMULATION = "simulation"   # Wokwi / Simulator

    @classmethod
    def is_test_data(cls, source: "DataSource") -> bool:
        """Check if eligible for cleanup."""
        return source in (cls.MOCK, cls.TEST, cls.SIMULATION)
```

**Verwendung für Cleanup:**
- `AuditRetentionService` verwendet `is_test_data()` für selektive Löschung
- Test-Daten können ohne Produktions-Daten gelöscht werden

---

## 4. Library-Flow (E2E)

### 4.1 Flow-Diagramm

```
┌─────────────────────────────────────────────────────────────┐
│ ESP32 / MockESP32Client                                     │
│ └─ Publishes: kaiser/{id}/esp/{esp}/sensor/{gpio}/data      │
│    Payload: { "raw_value": 2048, "raw_mode": true, ... }    │
└─────────────────────────────────────────────────────────────┘
                          │ MQTT
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ SensorDataHandler.handle()                                  │
│ ├─ Parse topic → esp_id, gpio                               │
│ ├─ Validate payload (raw_mode REQUIRED)                     │
│ ├─ _detect_data_source() → DataSource enum                  │
│ └─ Trigger Pi-Enhanced Processing (if configured)           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Pi-Enhanced Processing (Lines 151-191)                      │
│ ├─ Check: sensor_config.pi_enhanced == True                 │
│ ├─ Get processor: LibraryLoader.get_processor(sensor_type)  │
│ └─ Process: processor.process(raw_value, calibration, ...)  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ LibraryLoader (Singleton)                                   │
│ ├─ _discover_libraries() → Scans sensor_libraries/active/   │
│ ├─ _load_library(module) → importlib.import_module()        │
│ ├─ normalize_sensor_type() → ESP32 → Server mapping         │
│ └─ get_processor(type) → Returns BaseSensorProcessor        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ BaseSensorProcessor.process()                               │
│ ├─ Converts RAW → Physical value                            │
│ ├─ Applies calibration offsets                              │
│ └─ Returns: { "value": 6.8, "unit": "pH", "quality": ... }  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Publish Processed Result                                    │
│ └─ Topic: kaiser/{id}/esp/{esp}/sensor/{gpio}/processed     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 LibraryLoader Details

**Datei:** `sensors/library_loader.py`

**Singleton-Pattern:**
```python
_instance: Optional["LibraryLoader"] = None

@classmethod
def get_instance(cls) -> "LibraryLoader":
    if cls._instance is None:
        cls._instance = cls()
    return cls._instance
```

**Dynamic Loading:**
```python
def _load_library(self, module_name: str) -> list[BaseSensorProcessor]:
    import_paths = [
        f"src.sensors.sensor_libraries.active.{module_name}",
        f"sensors.sensor_libraries.active.{module_name}",
        f"god_kaiser_server.src.sensors.sensor_libraries.active.{module_name}",
    ]

    for path in import_paths:
        try:
            module = importlib.import_module(path)
            break
        except ImportError:
            continue
```

**Type Normalization:**
```python
from .sensor_type_registry import normalize_sensor_type

def get_processor(self, sensor_type: str) -> Optional[BaseSensorProcessor]:
    # ESP32 sends "temperature_sht31" → normalized to "sht31_temp"
    normalized_type = normalize_sensor_type(sensor_type)
    return self.processors.get(normalized_type)
```

### 4.3 Sensor Libraries Location

**Pfad:** `sensors/sensor_libraries/active/`

**Verfügbare Libraries:**
| Library | Processors |
|---------|------------|
| `ph_sensor.py` | PHProcessor |
| `temperature.py` | DS18B20Processor, SHT31TemperatureProcessor |
| `humidity.py` | SHT31HumidityProcessor |
| `ec_sensor.py` | ECProcessor |
| `moisture.py` | MoistureProcessor |
| `pressure.py` | PressureProcessor |
| `co2.py` | CO2Processor |
| `light.py` | LightProcessor |
| `flow.py` | FlowProcessor |

---

## 5. Database Schema (DataSource Integration)

### 5.1 Sensor Model

**Datei:** `db/models/sensor.py`

```python
class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(primary_key=True)
    esp_id: Mapped[str] = mapped_column(String(50))
    gpio: Mapped[int] = mapped_column(Integer)
    sensor_type: Mapped[str] = mapped_column(String(50))
    data_source: Mapped[DataSource] = mapped_column(
        SQLAlchemyEnum(DataSource),
        default=DataSource.PRODUCTION
    )
    # ...
```

### 5.2 SensorData Model (Time-Series)

**Datei:** `db/models/sensor.py`

```python
class SensorData(Base):
    __tablename__ = "sensor_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    esp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("esp_devices.id"))
    gpio: Mapped[int] = mapped_column(Integer)
    sensor_type: Mapped[str] = mapped_column(String(50))
    raw_value: Mapped[float] = mapped_column(Float)
    processed_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    processing_mode: Mapped[str] = mapped_column(String(20))  # pi_enhanced, local, raw
    quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    sensor_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    data_source: Mapped[str] = mapped_column(String(20), default=DataSource.PRODUCTION.value, index=True)

    # Time-Series Optimized Indices
    __table_args__ = (
        Index("idx_esp_gpio_timestamp", "esp_id", "gpio", "timestamp"),
        Index("idx_sensor_type_timestamp", "sensor_type", "timestamp"),
        Index("idx_timestamp_desc", "timestamp", postgresql_ops={"timestamp": "DESC"}),
        Index("idx_data_source_timestamp", "data_source", "timestamp"),
    )
```

### 5.3 AuditLog Model

**Datei:** `db/models/audit_log.py`

```python
class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)

    # Event Classification
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)

    # Source Identification
    source_type: Mapped[str] = mapped_column(String(30), index=True)  # esp32, user, system, api, mqtt
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Event Details
    status: Mapped[str] = mapped_column(String(20), index=True)  # success, failed, pending
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    # Error Information
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    error_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Request Context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Performance Indices
    __table_args__ = (
        Index('ix_audit_logs_created_at', 'created_at'),
        Index('ix_audit_logs_severity_created_at', 'severity', 'created_at'),
        Index('ix_audit_logs_source_created_at', 'source_type', 'source_id', 'created_at'),
    )
```

**Hinweis:** AuditLog hat KEIN `data_source` Feld - verwendet stattdessen `source_type`/`source_id`

---

## 6. Test-Engine Analyse

### 6.1 Fixture-Inventar

**Datei:** `tests/esp32/conftest.py` (790 Lines)

**Mock ESP Fixtures:**

| Fixture | BrokerMode | Description |
|---------|------------|-------------|
| `mock_esp32` | DIRECT | Basic Mock mit Zone-Config, keine Sensoren/Aktoren |
| `mock_esp32_unconfigured` | DIRECT | Mock ohne Zone (für Validation-Tests) |
| `mock_esp32_with_sensors` | DIRECT | Mock mit 3 Sensoren (GPIO 34, 35, 36) |
| `mock_esp32_with_actuators` | DIRECT | Mock mit 3 Aktoren (GPIO 5, 6, 7) |
| `mock_esp32_with_zones` | DIRECT | Mock mit Zone + Sensors + Actuators |
| `mock_esp32_with_sht31` | DIRECT | Mock mit Multi-Value SHT31 Sensor |
| `mock_esp32_greenhouse` | DIRECT | Vollständiges Greenhouse Setup |
| `mock_esp32_safe_mode` | DIRECT | Mock für Safe-Mode Testing |
| `mock_esp32_with_broker` | MQTT | Mock mit echtem MQTT Broker |
| `mock_esp32_broker_fallback` | MQTT/DIRECT | Automatischer Fallback |

**Multi-ESP Fixtures:**

| Fixture | Description |
|---------|-------------|
| `multiple_mock_esp32` | 3 ESPs: esp1 (Aktoren), esp2 (Sensoren), esp3 (Mixed) |
| `multiple_mock_esp32_with_zones` | 4 ESPs in 2 Zonen mit vollständiger Hierarchie |
| `multiple_mock_esp32_for_subzones` | ESPs für Subzone-Testing |

**Subzone Fixtures:**

| Fixture | Description |
|---------|-------------|
| `mock_esp32_with_zone_for_subzones` | ESP mit Zone für Subzone-Tests |
| `mock_esp32_no_zone_for_subzones` | ESP ohne Zone (Validation) |
| `mock_esp32_with_actuators_for_subzones` | ESP mit Aktoren für Subzone-Zuweisung |

**MQTT/Util Fixtures:**

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `mqtt_test_config` | session | MQTT-Konfiguration aus ENV |
| `mqtt_test_client` | function | In-Memory MQTT Test Client |
| `real_esp32` | function | Verbindung zu echtem ESP32 (optinal) |

### 6.2 Broker-Detection

**Helper-Funktion** (conftest.py):
```python
def is_mqtt_broker_available() -> bool:
    """Check if real MQTT broker is running."""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect("localhost", 1883, timeout=1)
        client.disconnect()
        return True
    except:
        return False
```

**Verwendung:**
```python
@pytest.fixture
def mock_esp32_with_broker():
    if not is_mqtt_broker_available():
        pytest.skip("MQTT broker not available")
    return MockESP32Client(broker_mode=BrokerMode.MQTT)
```

### 6.3 Test-Kategorien

**Integration Tests (tests/integration/):**

| Test File | Purpose |
|-----------|---------|
| `test_library_e2e_integration.py` | Library Processing Flow E2E |
| `test_modular_esp_integration.py` | Modular ESP Integration |
| `test_api_subzones.py` | Subzone API Endpoints |
| `test_websocket_auth.py` | WebSocket Authentication |

**Unit Tests (tests/unit/):**

| Test File | Purpose |
|-----------|---------|
| `test_mqtt_auth_service.py` | MQTT Authentication Logic |
| `test_subzone_service.py` | Subzone Business Logic |

**ESP32 Tests (tests/esp32/):**

| Test File | Purpose |
|-----------|---------|
| `test_production_accuracy.py` | Production vs Mock Accuracy |
| `test_subzone_management.py` | Subzone Assignment + Safe-Mode |

**Test Mocks (tests/esp32/mocks/):**

| File | Purpose |
|------|---------|
| `mock_esp32_client.py` | MockESP32Client (1525 Lines) |
| `in_memory_mqtt_client.py` | In-Memory MQTT für Offline-Tests |
| `real_esp32_client.py` | RealESP32Client für Hardware-Tests |

---

## 7. Frontend Settings (Identifiziert)

### 7.1 Debug API Endpoints

**Datei:** `api/v1/debug.py` (1896 Lines)

| Endpoint | Method | Purpose | Frontend-Relevant |
|----------|--------|---------|-------------------|
| `/debug/mock-esp` | POST | Create Mock ESP | ✅ ESP Management UI |
| `/debug/mock-esp/{id}` | GET | Get Mock Details | ✅ ESP Details View |
| `/debug/mock-esp/{id}` | DELETE | Remove Mock | ✅ ESP Management UI |
| `/debug/mock-esp/{id}/sensors/{gpio}` | POST | Add Sensor | ✅ Sensor Config UI |
| `/debug/mock-esp/{id}/actuators/{gpio}` | POST | Add Actuator | ✅ Actuator Config UI |
| `/debug/database/tables` | GET | List Tables | ✅ Database Explorer |
| `/debug/database/tables/{table}` | GET | Query Table | ✅ Database Explorer |
| `/debug/test-data/cleanup` | POST | Cleanup Test Data | ✅ Admin Settings |

### 7.2 Konfigurierbare Parameter

**Mock ESP Erstellung:**
```python
class MockESPCreateRequest(BaseModel):
    esp_id: Optional[str] = None  # Auto-generated if not provided
    kaiser_id: str = "god"
    zone_id: Optional[str] = None
    sensors: List[SensorConfig] = []
    actuators: List[ActuatorConfig] = []
    data_source: DataSource = DataSource.MOCK
```

**Test Data Cleanup:**
```python
class CleanupRequest(BaseModel):
    older_than_hours: int = 24
    data_sources: List[DataSource] = [DataSource.MOCK, DataSource.TEST]
    dry_run: bool = True  # Preview mode
```

### 7.3 Database Explorer Parameters

```python
class TableQueryParams(BaseModel):
    limit: int = 100
    offset: int = 0
    order_by: str = "id"
    order_dir: Literal["asc", "desc"] = "desc"
    filters: Dict[str, Any] = {}
```

---

## 8. Identifizierte Probleme

### 8.1 Dual-Storage Synchronisation

**Problem:** Mock-ESPs existieren in zwei Stores (In-Memory + DB), aber es gibt keinen automatischen Sync-Mechanismus.

**Auswirkung:**
- Bei Server-Neustart gehen In-Memory Mocks verloren
- DB-Einträge bleiben bestehen → Inkonsistenz

**Empfehlung:**
- Startup-Hook zur Rekonstruktion von In-Memory Mocks aus DB
- Oder: Nur DB-basierte Mock-Verwaltung

### 8.2 DataSource Detection Komplexität

**Problem:** 8-stufige Priority-Logik ist schwer zu debuggen.

**Empfehlung:**
- Logging bei jedem Detection-Schritt
- Debug-Endpoint zur Visualisierung der Detection-Logik

### 8.3 Library Reload ohne Hot-Reload

**Problem:** `LibraryLoader.reload_libraries()` existiert, aber kein API-Endpoint dafür.

**Empfehlung:**
- Debug-Endpoint: `POST /debug/libraries/reload`
- Ermöglicht Library-Updates ohne Server-Neustart

---

## 9. Offene Fragen

1. **Wokwi-Integration:** Wie werden Wokwi-Simulatoren erkannt? (DataSource.SIMULATION)
   - Aktuell nur manuell via `_source` Field möglich

2. **Kaiser-Hierarchie:** Wird der Kaiser-Layer (Raspberry Pi Zero) aktiv genutzt?
   - Topics unterstützen es, aber keine Handler-Implementierung gefunden

3. **OTA-Updates:** Wie funktioniert das OTA-Library-Update für ESP32s?
   - Feature-Flag existiert (`OTA_LIBRARY_ENABLED`), aber Server-seitige Implementation unklar

---

## 10. Empfehlungen

### 10.1 Kurzfristig (Quick Wins) - ✅ IMPLEMENTIERT

1. **Library Reload Endpoint** ✅ `POST /debug/libraries/reload`
2. **Library Info Endpoint** ✅ `GET /debug/libraries/info`
3. **DataSource Detection Logging** ✅ Debug-Logging in allen Handlern
4. **DataSource Detection Test Endpoint** ✅ `POST /debug/data-source/detect`
5. **Mock-ESP Sync Status** ✅ `GET /debug/mock-esp/sync-status`

### 10.2 Mittelfristig

1. **Unified Mock-Storage** - Nur DB, kein In-Memory (Optional - Sync-Status-Endpoint hilft)
2. **Wokwi-Detection** automatisieren (via `SIM_` Prefix bereits unterstützt)
3. **Test-Coverage Dashboard** für Frontend

### 10.3 Langfristig

1. **Kaiser-Layer Implementation** abschließen
2. **OTA-Library-System** dokumentieren
3. **Real-Time Library-Update** via WebSocket

---

## 11. Neue Debug-Endpoints (2025-12-26)

### 11.1 Library Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/libraries/reload` | POST | Hot-Reload Sensor Libraries ohne Server-Restart |
| `/debug/libraries/info` | GET | Verfügbare Sensor-Typen und Library-Pfad |

### 11.2 Mock-ESP Sync

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/mock-esp/sync-status` | GET | Sync-Status zwischen In-Memory und DB |

### 11.3 DataSource Detection

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/data-source/detect` | POST | DataSource Detection Logic testen |

**Beispiel-Request:**
```json
{
  "esp_id": "MOCK_TEST_001",
  "hardware_type": "MOCK_ESP32",
  "capabilities_mock": true,
  "payload_test_mode": false,
  "payload_source": null
}
```

**Beispiel-Response:**
```json
{
  "esp_id": "MOCK_TEST_001",
  "detected_source": "mock",
  "detection_reason": "esp_id prefix 'MOCK_'",
  "checks_performed": [
    {"priority": 1, "check": "payload._test_mode", "matched": false},
    {"priority": 2, "check": "payload._source", "matched": false},
    {"priority": 3, "check": "hardware_type='MOCK_ESP32'", "matched": true}
  ]
}
```

---

## Appendix A: Key File Locations

| Component | Path |
|-----------|------|
| Server Entry | `src/main.py` |
| MQTT Handlers | `src/mqtt/handlers/` |
| Sensor Handler | `src/mqtt/handlers/sensor_handler.py` |
| Heartbeat Handler | `src/mqtt/handlers/heartbeat_handler.py` |
| Mock ESP Manager | `src/services/mock_esp_manager.py` |
| Mock ESP Client | `tests/esp32/mocks/mock_esp32_client.py` |
| Debug API | `src/api/v1/debug.py` |
| Library Loader | `src/sensors/library_loader.py` |
| DataSource Enum | `src/db/models/enums.py` |
| Test Fixtures | `tests/esp32/conftest.py` |
| Sensor Libraries | `src/sensors/sensor_libraries/active/` |

---

## Appendix B: DataSource Flow Chart

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCE LIFECYCLE                    │
└─────────────────────────────────────────────────────────────┘

                    ┌───────────────┐
                    │   ESP/Mock    │
                    │   publishes   │
                    └───────┬───────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │   MQTT Handler receives       │
            │   _detect_data_source()       │
            └───────────────┬───────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │PRODUCTION│  │   MOCK   │  │   TEST   │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │             │             │
             ▼             ▼             ▼
        ┌──────────────────────────────────────┐
        │     Stored in DB with data_source    │
        │     (sensor_readings, audit_logs)    │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │   AuditRetentionService.cleanup()    │
        │   is_test_data() → Selective Delete  │
        └──────────────────────────────────────┘
```

---

**Letzte Aktualisierung:** 2025-12-26
**Version:** 1.2

> **Änderungen in v1.2 (Fixes & Neue Endpoints):**
> - **Library Management Endpoints:** `POST /debug/libraries/reload`, `GET /debug/libraries/info`
> - **Mock-ESP Sync Status:** `GET /debug/mock-esp/sync-status` mit Orphan-Detection
> - **DataSource Detection Test:** `POST /debug/data-source/detect` mit Check-Visualisierung
> - **DataSource Detection Logging:** Debug-Logging in sensor_handler, actuator_handler, heartbeat_handler
> - **MockESPManager Sync-Methoden:** `get_orphaned_mock_ids()`, `get_sync_status()`, `is_mock_in_memory()`
> - Section 11 hinzugefügt: Neue Debug-Endpoints

> **Änderungen in v1.1 (Verifizierung):**
> - Startup-Sequenz: Zeilennummern und Reihenfolge korrigiert (Step 0-6)
> - MQTT Handler Registry: Handler-Namen und Topic-Patterns korrigiert
> - DataSource Detection: Prioritäten korrigiert, SIM_ Prefix hinzugefügt
> - Sensor Libraries: 5 zusätzliche Libraries dokumentiert (moisture, pressure, co2, light, flow)
> - Database Schema: SensorReading → SensorData korrigiert, AuditLog vollständig dokumentiert
> - Test-Fixtures: Vollständige Liste mit 16+ Fixtures dokumentiert
> - Alle Zeilennummern-Referenzen verifiziert
