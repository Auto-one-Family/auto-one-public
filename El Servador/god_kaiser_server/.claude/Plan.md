Bitte beachte Doku unter Auto-One/Claude

# Mock-ESP Simulation System - Refactoring Guide

**Projekt:** AutomationOne Framework  
**Dokument-Version:** 1.0  
**Erstellt:** 2025-12-26  
**Zielgruppe:** Backend-Entwickler  
**Geschätzter Aufwand:** 5-7 Arbeitstage  

---

## Inhaltsverzeichnis

1. [System-Überblick](#1-system-überblick)
2. [Aktuelle Architektur verstehen](#2-aktuelle-architektur-verstehen)
3. [Identifizierte Probleme](#3-identifizierte-probleme)
4. [Problem 1: Dual-Storage Anti-Pattern](#4-problem-1-dual-storage-anti-pattern)
5. [Problem 2: Task-per-Mock Skalierungsproblem](#5-problem-2-task-per-mock-skalierungsproblem)
6. [Problem 3: Singleton Anti-Pattern](#6-problem-3-singleton-anti-pattern)
7. [Problem 4: Fehlende Resilience-Patterns](#7-problem-4-fehlende-resilience-patterns)
8. [Problem 5: Graceful Shutdown fehlt](#8-problem-5-graceful-shutdown-fehlt)
9. [Implementierungs-Reihenfolge](#9-implementierungs-reihenfolge)
10. [Verifikations-Checkliste](#10-verifikations-checkliste)

---

## 1. System-Überblick

### 1.1 Was ist das Mock-ESP System?

Das Mock-ESP System simuliert echte ESP32-Mikrocontroller für Testzwecke. Es ermöglicht Benutzern:

- Mock-ESPs über das Frontend zu erstellen
- Sensoren und Aktoren hinzuzufügen
- Periodische Daten zu generieren (wie echte Hardware)
- Das gesamte System ohne physische Hardware zu testen

### 1.2 Warum ist das wichtig?

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUKTIONS-FLOW                         │
│                                                             │
│   Echter ESP32  →  MQTT Broker  →  Server Handler           │
│                                         ↓                   │
│                                    Database                 │
│                                         ↓                   │
│                                    WebSocket                │
│                                         ↓                   │
│                                    Frontend                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    MOCK-FLOW (identisch!)                   │
│                                                             │
│   Mock-ESP      →  MQTT Broker  →  Server Handler           │
│   (Software)                            ↓                   │
│                                    Database                 │
│                                         ↓                   │
│                                    WebSocket                │
│                                         ↓                   │
│                                    Frontend                 │
└─────────────────────────────────────────────────────────────┘
```

**Kritisch:** Mock-ESPs MÜSSEN exakt denselben Datenfluss nutzen wie echte ESPs. Keine Sonderwege, keine Abkürzungen.

### 1.3 Kern-Komponenten

| Komponente | Datei | Verantwortung |
|------------|-------|---------------|
| MockESP32Client | `tests/esp32/mocks/mock_esp32_client.py` | Simuliert einzelnen ESP32 |
| MockESPManager | `src/services/mock_esp_manager.py` | Verwaltet alle Mock-ESPs |
| Debug API | `src/api/v1/debug.py` | REST-Endpoints für Frontend |
| MQTT Handlers | `src/mqtt/handlers/*.py` | Verarbeiten MQTT-Messages |
| WebSocket Manager | `src/websocket/manager.py` | Broadcasts an Frontend |

---

## 2. Aktuelle Architektur verstehen

### 2.1 Codebase-Analyse durchführen

**ANWEISUNG AN ENTWICKLER:**

Bevor du Änderungen vornimmst, musst du die folgenden Dateien vollständig lesen und verstehen. Erstelle für jede Datei eine kurze Zusammenfassung (max. 5 Sätze).

#### Pflicht-Lektüre:

```
Reihenfolge ist wichtig!

1. src/core/constants.py
   → Verstehe: DEFAULT_KAISER_ID, MQTT Topic-Patterns
   
2. src/mqtt/topics.py
   → Verstehe: Wie Topics gebaut werden
   
3. src/mqtt/handlers/heartbeat_handler.py (Zeilen 54-175)
   → Verstehe: Wie Heartbeats verarbeitet werden
   
4. src/mqtt/handlers/sensor_handler.py (Zeilen 1-250)
   → Verstehe: Wie Sensor-Daten verarbeitet werden
   
5. src/services/mock_esp_manager.py (komplett)
   → Verstehe: Aktuelle Manager-Implementierung
   
6. tests/esp32/mocks/mock_esp32_client.py (Zeilen 1-400)
   → Verstehe: MockESP32Client Struktur
   
7. src/api/v1/debug.py (Zeilen 1-300)
   → Verstehe: Bestehende Debug-Endpoints
   
8. src/main.py (Zeilen 70-275)
   → Verstehe: Startup-Sequenz, Handler-Registration
```

#### Dokumentations-Lektüre:

```
1. .claude/CLAUDE_SERVER.md
   → Server-Architektur-Referenz
   
2. Hierarchie.md (im Projekt-Root)
   → System-Hierarchie verstehen
   
3. Codebase_Analysis_Server.md
   → Detaillierte Code-Analyse
```

---

### ✅ 2.1.1 Datei-Zusammenfassungen (Codebase-Analyse)

> **Analysiert am:** 2025-12-26
> **Basierend auf:** Tatsächlichem Code, nicht Annahmen

#### 1. `src/core/constants.py` (330 Zeilen)
**Kernfunktion:** Zentrale Konfigurationskonstanten für das gesamte System.

**Wichtige Inhalte:**
- **MQTT Topic Templates:** `MQTT_TOPIC_ESP_SENSOR_DATA`, `MQTT_TOPIC_ESP_HEARTBEAT`, etc. mit `{kaiser_id}` Placeholder
- **DEFAULT_KAISER_ID:** `"god"` - Standard Kaiser-ID
- **Helper:** `get_topic_with_kaiser_id(topic_template, **kwargs)` für dynamisches Topic-Building
- **GPIO Ranges:** `GPIO_SAFE_ESP32_WROOM`, `GPIO_SAFE_XIAO_ESP32C3`
- **Timeouts:** `TIMEOUT_ESP_HEARTBEAT = 120000` (2 Min), `TIMEOUT_SENSOR_PROCESSING = 5000`
- **Error Codes:** Hardware (1000-1999), Service (2000-2999), Communication (3000-3999)
- **QOS Levels:** `QOS_SENSOR_DATA = 1`, `QOS_ACTUATOR_COMMAND = 2`

**Relevanz für Refactoring:** Zeigt, dass Topic-Building bereits zentralisiert ist. Mock-ESPs müssen dieselben Konstanten verwenden.

---

#### 2. `src/mqtt/topics.py` (656 Zeilen)
**Kernfunktion:** `TopicBuilder` Klasse für MQTT Topic-Konstruktion und -Parsing.

**Wichtige Methoden:**
```python
# BUILD (Server → ESP):
TopicBuilder.build_actuator_command_topic(esp_id, gpio)  # → kaiser/god/esp/{esp_id}/actuator/{gpio}/command
TopicBuilder.build_zone_assign_topic(esp_id)             # → kaiser/god/esp/{esp_id}/zone/assign
TopicBuilder.build_subzone_assign_topic(esp_id)          # → kaiser/god/esp/{esp_id}/subzone/assign

# PARSE (ESP → Server):
TopicBuilder.parse_sensor_data_topic(topic)    # Returns: {esp_id, gpio, type: "sensor_data"}
TopicBuilder.parse_heartbeat_topic(topic)      # Returns: {esp_id, type: "heartbeat"}
TopicBuilder.parse_zone_ack_topic(topic)       # Returns: {esp_id, type: "zone_ack"}
```

**Relevanz für Refactoring:** Mock-ESPs MÜSSEN TopicBuilder für konsistente Topics verwenden. Der aktuelle `mock_esp32_client.py` baut Topics manuell - **Inkonsistenz-Risiko!**

---

#### 3. `src/mqtt/handlers/heartbeat_handler.py` (Zeilen 54-175)
**Kernfunktion:** Verarbeitet ESP32 Heartbeat-Nachrichten, aktualisiert Online-Status.

**Flow:**
1. `TopicBuilder.parse_heartbeat_topic(topic)` → extrahiert `esp_id`
2. Payload-Validierung (erwartet: `ts`, `uptime`, `heap_free`, `wifi_rssi`)
3. **Auto-Discovery DEAKTIVIERT** (Zeile 117-126): Unbekannte ESPs werden abgelehnt!
4. `ESPRepository.update_status(esp_id, "online", last_seen)` → DB Update
5. WebSocket Broadcast: `ws_manager.broadcast("esp_health", {...})`

**Kritischer Code (Zeile 113-126):**
```python
esp_device = await esp_repo.get_by_device_id(esp_id_str)

if not esp_device:
    # REJECT: Unknown ESP device - not registered
    logger.warning(f"❌ Heartbeat rejected: Unknown device {esp_id_str}")
    return False
```

**Relevanz für Refactoring:** Mock-ESPs MÜSSEN in der Datenbank existieren BEVOR sie Heartbeats senden. Der aktuelle `create_mock_esp()` registriert in DB UND In-Memory - das ist korrekt.

---

#### 4. `src/mqtt/handlers/sensor_handler.py` (Zeilen 1-250)
**Kernfunktion:** Verarbeitet Sensor-Daten, triggert Pi-Enhanced Processing.

**Flow:**
1. `TopicBuilder.parse_sensor_data_topic(topic)` → extrahiert `esp_id`, `gpio`
2. Payload-Validierung (erwartet: `ts`, `raw`/`raw_value`, `sensor_type`, `quality`, `raw_mode`)
3. `ESPRepository.get_by_device_id()` → ESP-Lookup
4. `SensorRepository.get_by_esp_and_gpio()` → Sensor-Config-Lookup
5. Wenn `sensor_config.pi_enhanced == True`: Pi-Enhanced Processing triggern
6. `sensor_repo.save_reading()` → DB-Speicherung
7. WebSocket Broadcast: `ws_manager.broadcast("sensor_data", {...})`

**Kritischer Code (Zeile 117-125):**
```python
esp_device = await esp_repo.get_by_device_id(esp_id_str)
if not esp_device:
    logger.error(f"ESP device not found: {esp_id_str}")
    return False
```

**Relevanz für Refactoring:** Identisch zu Heartbeat - ESP muss in DB existieren. Sensor-Config ist optional (Zeile 131-135).

---

#### 5. `src/services/mock_esp_manager.py` (681 Zeilen)
**Kernfunktion:** Singleton-Manager für Mock-ESP32 Instanzen.

**Aktuelle Architektur (IST):**
```python
class MockESPManager:
    _instance: Optional["MockESPManager"] = None  # Singleton
    _mock_esps: Dict[str, MockESP32Client] = {}   # In-Memory Store ← PROBLEM 1
    _heartbeat_tasks: Dict[str, asyncio.Task] = {} # Task per Mock ← PROBLEM 2
    _mqtt_client: Optional[MQTTClient] = None

    @classmethod
    async def get_instance(cls) -> "MockESPManager":  # ← PROBLEM 3: Singleton
        async with cls._lock:
            if cls._instance is None:
                cls._instance = MockESPManager()
            return cls._instance
```

**Wichtige Methoden:**
- `create_mock_esp(config)`: Erstellt Mock, speichert in `_mock_esps`, startet Heartbeat-Task
- `_create_publish_callback(esp_id)`: Callback für MQTT Publishing
- `get_sync_status(db_mock_ids)`: Vergleicht In-Memory vs DB (Dual-Storage Awareness!)
- `get_orphaned_mock_ids(db_mock_ids)`: Findet verwaiste DB-Einträge

**Relevanz für Refactoring:** Der Code hat BEREITS `get_sync_status()` und `get_orphaned_mock_ids()` - das zeigt, dass das Dual-Storage-Problem bekannt war. Die Lösung sollte diese Methoden eliminieren, nicht erweitern.

---

#### 6. `tests/esp32/mocks/mock_esp32_client.py` (Zeilen 1-400+)
**Kernfunktion:** Simuliert einzelnen ESP32 mit komplettem Verhalten.

**Wichtige Klassen:**
```python
class BrokerMode(str, Enum):
    DIRECT = "direct"  # In-Memory only (für Unit-Tests)
    MQTT = "mqtt"      # Publish via echtem MQTT Broker

class SystemState(Enum):
    BOOT = 0, WIFI_SETUP = 1, MQTT_CONNECT = 2, ..., OPERATIONAL = 6, SAFE_MODE = 10, ERROR = 11
```

**MockESP32Client Struktur:**
```python
class MockESP32Client:
    sensors: Dict[int, SensorState]      # GPIO → SensorState
    actuators: Dict[int, ActuatorState]  # GPIO → ActuatorState
    zone: Optional[ZoneConfig]           # Zone-Zugehörigkeit
    system_state: SystemState            # Aktueller Status
    on_publish: Callable                 # Callback für MQTT
    published_messages: List[dict]       # Message-History

    def handle_command(self, cmd: str, params: dict): # Command-Dispatcher
    def _publish_to_broker(self, topic, payload):     # MQTT Publishing
```

**Kritischer Code - Topic Building (Zeile ~200):**
```python
def _build_sensor_topic(self, gpio: int) -> str:
    return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/sensor/{gpio}/data"  # ← MANUELL!
```

**Relevanz für Refactoring:** Topics werden MANUELL gebaut statt `TopicBuilder` zu verwenden. Dies ist ein Konsistenz-Risiko. Der neue Code sollte `TopicBuilder` importieren.

---

#### 7. `src/api/v1/debug.py` (Zeilen 1-300+)
**Kernfunktion:** REST-API Endpoints für Mock-ESP Management.

**Dependency Injection:**
```python
async def get_mock_esp_manager() -> MockESPManager:
    return await MockESPManager.get_instance()
```

**Wichtige Endpoints:**
- `POST /debug/mock-esp`: Erstellt Mock-ESP (In-Memory + DB)
- `DELETE /debug/mock-esp/{esp_id}`: Löscht Mock-ESP
- `POST /debug/mock-esp/{esp_id}/heartbeat`: Triggert Heartbeat
- `POST /debug/mock-esp/{esp_id}/sensor/{gpio}/value`: Setzt Sensor-Wert
- `GET /debug/mock-esp/sync-status`: Zeigt Dual-Storage Sync-Status

**Kritischer Code - Dual-Storage (Zeilen ~130-160):**
```python
async def create_mock_esp(...):
    # 1. In-Memory erstellen
    response = await manager.create_mock_esp(config)

    # 2. DB-Eintrag erstellen (Duplikat!)
    async for session in get_session():
        esp_repo = ESPRepository(session)
        await esp_repo.create_or_update(ESPDevice(
            device_id=config.esp_id,
            hardware_type="MOCK_ESP32",
            ...
        ))
```

**Relevanz für Refactoring:** Zeigt klar das Dual-Storage Problem. Die Lösung muss diese Duplizierung eliminieren.

---

#### 8. `src/main.py` (Zeilen 70-275)
**Kernfunktion:** FastAPI Lifespan mit Startup/Shutdown-Sequenz.

**Startup-Sequenz (Zeilen 84-275):**
1. Security Validation (JWT Secret Check)
2. Database Init (`await init_db()`)
3. MQTT Client Connect
4. Handler Registration via `Subscriber`:
   ```python
   _subscriber_instance.register_handler(
       f"kaiser/{kaiser_id}/esp/+/sensor/+/data",
       sensor_handler.handle_sensor_data
   )
   ```
5. **MockESPManager MQTT Integration (Zeile 194-197):**
   ```python
   mock_esp_manager = await MockESPManager.get_instance()
   mock_esp_manager.set_mqtt_client(mqtt_client)
   ```
6. WebSocket Manager Init
7. Logic Engine + Scheduler Init

**Shutdown-Sequenz (Zeilen 286-327):**
1. Logic Scheduler Stop
2. Logic Engine Stop
3. WebSocket Manager Shutdown
4. **MQTT Subscriber Shutdown** (mit Timeout!)
5. MQTT Client Disconnect
6. Database Engine Dispose

**Kritischer Code - Graceful Shutdown (Zeilen 306-309):**
```python
if _subscriber_instance:
    logger.info("Shutting down MQTT subscriber thread pool...")
    _subscriber_instance.shutdown(wait=True, timeout=30.0)
```

**Relevanz für Refactoring:** MockESPManager hat KEINEN Eintrag in der Shutdown-Sequenz! Das ist **Problem 5: Graceful Shutdown fehlt**. Mock-ESP Tasks werden nicht sauber beendet.

---

### ✅ 2.1.2 Identifizierte Patterns (Echte Codebase)

#### Pattern 1: Repository Pattern ✅
```python
# Beispiel aus ESPRepository (esp_repo.py)
class ESPRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_device_id(self, device_id: str) -> Optional[ESPDevice]:
        query = select(ESPDevice).where(ESPDevice.device_id == device_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
```
**Regel:** Alle DB-Zugriffe durch Repositories. Mock-ESPs sollten das gleiche Pattern nutzen.

#### Pattern 2: Singleton via AsyncIO Lock ⚠️
```python
# MockESPManager (aktuell)
class MockESPManager:
    _instance: Optional["MockESPManager"] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "MockESPManager":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = MockESPManager()
            return cls._instance
```
**Problem:** Erschwert Testing, versteckt Abhängigkeiten. Sollte zu DI migriert werden.

#### Pattern 3: Handler-Registrierung via Subscriber
```python
# main.py:148-151
_subscriber_instance.register_handler(
    f"kaiser/{kaiser_id}/esp/+/sensor/+/data",
    sensor_handler.handle_sensor_data
)
```
**Regel:** Handler sind stateless, werden via Topic-Pattern registriert.

#### Pattern 4: WebSocket Broadcast für Frontend
```python
# heartbeat_handler.py:153-167
ws_manager = await WebSocketManager.get_instance()
await ws_manager.broadcast("esp_health", {
    "esp_id": esp_id_str,
    "status": "online",
    ...
})
```
**Regel:** Alle Frontend-relevanten Events via `ws_manager.broadcast()`.

#### Pattern 5: Callback-basiertes MQTT Publishing
```python
# mock_esp_manager.py:547-557
def _create_publish_callback(self, esp_id: str):
    def callback(topic: str, payload: Dict[str, Any], qos: int = 1):
        if self._mqtt_client and self._mqtt_client.is_connected():
            self._mqtt_client.publish(topic, json.dumps(payload), qos=qos)
    return callback
```
**Regel:** Mock-ESPs nutzen Callback für MQTT, nicht direkte Client-Referenz.

---

### 2.2 Aktueller Datenfluss (IST-Zustand)

```
┌─────────────────────────────────────────────────────────────┐
│ SCHRITT 1: Mock-ESP Erstellung                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Frontend                                                  │
│      │                                                      │
│      │ POST /debug/mock-esp                                 │
│      ▼                                                      │
│   debug.py:create_mock_esp()                                │
│      │                                                      │
│      ├──► MockESPManager.add_mock_esp()                     │
│      │       │                                              │
│      │       └──► In-Memory Dict speichern ◄── PROBLEM 1    │
│      │                                                      │
│      └──► ESPRepository.create_or_update()                  │
│              │                                              │
│              └──► PostgreSQL speichern                      │
│                                                             │
│   ERGEBNIS: Mock existiert an ZWEI Stellen (Inkonsistenz!)  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SCHRITT 2: Simulation starten                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   MockESP32Client.start_simulation()                        │
│      │                                                      │
│      └──► asyncio.create_task(_simulation_loop) ◄── PROB 2  │
│              │                                              │
│              └──► Endlos-Loop mit 100ms Sleep               │
│                      │                                      │
│                      ├── Heartbeat Check (jede Iteration)   │
│                      └── Sensor Check (jede Iteration)      │
│                                                             │
│   ERGEBNIS: Ein Task PRO Mock-ESP (skaliert nicht!)         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SCHRITT 3: MQTT Publishing                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   MockESP32Client._publish_to_broker()                      │
│      │                                                      │
│      └──► self.on_publish(topic, payload)                   │
│              │                                              │
│              │ (Callback von MockESPManager gesetzt)        │
│              ▼                                              │
│          MQTTClient.publish()                               │
│              │                                              │
│              └──► Mosquitto Broker                          │
│                      │                                      │
│                      └──► Handler (sensor_handler, etc.)    │
│                              │                              │
│                              ├──► Database                  │
│                              └──► WebSocket Broadcast       │
│                                                             │
│   ERGEBNIS: Dieser Teil funktioniert korrekt!               │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Bestehende Patterns identifizieren

**ANWEISUNG AN ENTWICKLER:**

Identifiziere und dokumentiere folgende Patterns aus der Codebase:

#### Pattern 1: Repository Pattern
```python
# Beispiel aus src/db/repositories/esp_repo.py
class ESPRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_device_id(self, device_id: str) -> Optional[ESPDevice]:
        ...
```
**Regel:** Alle DB-Zugriffe gehen durch Repositories. Niemals direkte Session-Queries in Services.

#### Pattern 2: Handler Pattern
```python
# Beispiel aus src/mqtt/handlers/sensor_handler.py
class SensorDataHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def handle(self, topic: str, payload: dict) -> None:
        ...
```
**Regel:** Handler sind stateless. Keine Instanz-Variablen für Daten.

#### Pattern 3: WebSocket Broadcast Pattern
```python
# Beispiel aus src/mqtt/handlers/sensor_handler.py:207-221
await ws_manager.broadcast("sensor_data", {
    "esp_id": esp_id_str,
    "gpio": gpio,
    ...
})
```
**Regel:** Alle Frontend-relevanten Events via `ws_manager.broadcast()`.

#### Pattern 4: Async Session Factory
```python
# Beispiel aus src/db/session.py
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```
**Regel:** Sessions werden per-Request erstellt, nicht global gehalten.

---

## 3. Identifizierte Probleme

### Übersicht

| # | Problem | Schweregrad | Aufwand | Priorität |
|---|---------|-------------|---------|-----------|
| 1 | Dual-Storage (In-Memory + DB) | HOCH | 1-2 Tage | 1 |
| 2 | Task-per-Mock (Skalierung) | MITTEL | 1 Tag | 2 |
| 3 | Singleton Pattern | MITTEL | 0.5 Tage | 3 |
| 4 | Fehlende Resilience | NIEDRIG | 0.5 Tage | 4 |
| 5 | Graceful Shutdown fehlt | MITTEL | 0.5 Tage | 5 |

---

## 4. Problem 1: Dual-Storage Anti-Pattern

### 4.1 Problem-Beschreibung

**IST-Zustand:**
```python
# MockESPManager hält Mock-ESPs in zwei Stores:

# Store 1: In-Memory (verloren bei Restart)
self._mock_esps: Dict[str, MockESP32Client] = {}

# Store 2: PostgreSQL (persistent)
await esp_repo.create_or_update(device)
```

**Probleme:**
1. Nach Server-Restart: DB hat Einträge, In-Memory ist leer
2. Kein automatischer Sync
3. `get_mock_esp()` findet nichts, obwohl DB-Eintrag existiert
4. Orphaned Records in DB

### 4.2 SOLL-Zustand

**Prinzip: Single Source of Truth = Database**

```
┌─────────────────────────────────────────────────────────────┐
│                    NEUE ARCHITEKTUR                         │
│                                                             │
│   PostgreSQL (esp_devices Tabelle)                          │
│        │                                                    │
│        │  hardware_type = 'MOCK_ESP32'                      │
│        │  simulation_config = JSON (Sensoren, Intervalle)   │
│        │  simulation_state = 'running' | 'stopped'          │
│        │                                                    │
│        ▼                                                    │
│   MockESPManager (stateless, nur Koordination)              │
│        │                                                    │
│        │  _active_tasks: Dict[str, asyncio.Task]            │
│        │  (nur für laufende Simulations-Tasks)              │
│        │                                                    │
│        ▼                                                    │
│   Bei Bedarf: MockESP32Client aus DB rekonstruieren         │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Entwickler-Anweisungen

#### Schritt 1: Database Schema erweitern

**Datei:** `src/db/models/esp.py`

**Änderungen:**

```python
# NACH der bestehenden ESPDevice Klasse hinzufügen:

from sqlalchemy import JSON, Enum as SQLEnum
from enum import Enum

class SimulationState(str, Enum):
    """Status der Mock-ESP Simulation."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


# In ESPDevice Klasse folgende Felder hinzufügen:

class ESPDevice(Base):
    # ... bestehende Felder ...
    
    # NEU: Simulation-spezifische Felder
    simulation_state: Mapped[Optional[str]] = mapped_column(
        String(20), 
        default=None,
        nullable=True,
        comment="Simulation state for mock devices: stopped, running, paused, error"
    )
    
    simulation_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        comment="JSON config for mock simulation: sensors, actuators, intervals"
    )
    
    heartbeat_interval: Mapped[Optional[float]] = mapped_column(
        Float,
        default=60.0,
        nullable=True,
        comment="Heartbeat interval in seconds for mock devices"
    )
```

**Migration erstellen:**

```bash
cd "El Servador/god_kaiser_server"
poetry run alembic revision --autogenerate -m "add_simulation_fields_to_esp_device"
poetry run alembic upgrade head
```

#### Schritt 2: Simulation Config Schema definieren

**Neue Datei:** `src/schemas/simulation.py`

```python
"""
Schemas für Mock-ESP Simulation.

Diese Schemas definieren die Struktur der simulation_config JSON-Spalte
in der esp_devices Tabelle.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum


class VariationPattern(str, Enum):
    """Patterns für Sensor-Wert-Variation."""
    CONSTANT = "constant"
    RANDOM = "random"
    DRIFT = "drift"


class SensorSimulationSchema(BaseModel):
    """Schema für einen simulierten Sensor."""
    gpio: int = Field(..., ge=0, le=39, description="GPIO Pin Nummer")
    sensor_type: str = Field(..., description="Sensor-Typ (z.B. DS18B20, SHT31)")
    base_value: float = Field(..., description="Basis-Wert für Simulation")
    unit: str = Field(default="", description="Einheit (z.B. °C, %)")
    interval_seconds: float = Field(
        default=30.0, 
        ge=1.0, 
        le=3600.0,
        description="Publish-Intervall in Sekunden"
    )
    variation_pattern: VariationPattern = Field(
        default=VariationPattern.RANDOM,
        description="Variations-Pattern"
    )
    variation_range: float = Field(
        default=0.5, 
        ge=0.0,
        description="Variations-Bereich (±X bei RANDOM, +X/min bei DRIFT)"
    )
    min_value: Optional[float] = Field(default=None, description="Untere Grenze")
    max_value: Optional[float] = Field(default=None, description="Obere Grenze")
    quality: str = Field(default="good", description="Daten-Qualität")

    class Config:
        use_enum_values = True


class ActuatorSimulationSchema(BaseModel):
    """Schema für einen simulierten Actuator."""
    gpio: int = Field(..., ge=0, le=39, description="GPIO Pin Nummer")
    actuator_type: str = Field(..., description="Actuator-Typ (z.B. relay, pump)")
    initial_state: bool = Field(default=False, description="Initialer Zustand")
    pwm_value: float = Field(default=0.0, ge=0.0, le=1.0, description="PWM Wert")


class SimulationConfigSchema(BaseModel):
    """
    Vollständige Simulation-Konfiguration.
    
    Wird als JSON in esp_devices.simulation_config gespeichert.
    """
    sensors: Dict[int, SensorSimulationSchema] = Field(
        default_factory=dict,
        description="Sensoren nach GPIO indexiert"
    )
    actuators: Dict[int, ActuatorSimulationSchema] = Field(
        default_factory=dict,
        description="Aktoren nach GPIO indexiert"
    )
    
    # Runtime-State (wird regelmäßig aktualisiert)
    manual_overrides: Dict[int, float] = Field(
        default_factory=dict,
        description="Manuelle Override-Werte nach GPIO"
    )
    
    class Config:
        use_enum_values = True

    def add_sensor(self, sensor: SensorSimulationSchema) -> None:
        """Fügt Sensor hinzu oder aktualisiert existierenden."""
        self.sensors[sensor.gpio] = sensor
    
    def remove_sensor(self, gpio: int) -> bool:
        """Entfernt Sensor. Gibt False zurück wenn nicht vorhanden."""
        if gpio in self.sensors:
            del self.sensors[gpio]
            self.manual_overrides.pop(gpio, None)
            return True
        return False
    
    def add_actuator(self, actuator: ActuatorSimulationSchema) -> None:
        """Fügt Actuator hinzu oder aktualisiert existierenden."""
        self.actuators[actuator.gpio] = actuator
    
    def remove_actuator(self, gpio: int) -> bool:
        """Entfernt Actuator. Gibt False zurück wenn nicht vorhanden."""
        if gpio in self.actuators:
            del self.actuators[gpio]
            return True
        return False


class CreateMockESPRequest(BaseModel):
    """Request-Schema für Mock-ESP Erstellung."""
    esp_id: Optional[str] = Field(
        default=None, 
        description="ESP-ID (auto-generiert wenn nicht angegeben)"
    )
    kaiser_id: str = Field(default="god", description="Kaiser-ID")
    zone_id: Optional[str] = Field(default=None, description="Zone-ID")
    zone_name: Optional[str] = Field(default=None, description="Zone-Name")
    auto_start: bool = Field(
        default=True, 
        description="Simulation automatisch starten"
    )
    heartbeat_interval: float = Field(
        default=60.0, 
        ge=5.0, 
        le=3600.0,
        description="Heartbeat-Intervall in Sekunden"
    )
    sensors: List[SensorSimulationSchema] = Field(
        default_factory=list,
        description="Initiale Sensoren"
    )
    actuators: List[ActuatorSimulationSchema] = Field(
        default_factory=list,
        description="Initiale Aktoren"
    )


class SimulationStatusResponse(BaseModel):
    """Response-Schema für Simulation-Status."""
    esp_id: str
    simulation_state: str
    heartbeat_interval: float
    sensor_count: int
    actuator_count: int
    sensors: Dict[int, dict]
    actuators: Dict[int, dict]
    uptime_seconds: Optional[float] = None
```

#### Schritt 3: ESPRepository erweitern

**Datei:** `src/db/repositories/esp_repo.py`

**Hinzufügen:**

```python
from src.schemas.simulation import SimulationConfigSchema
from typing import List

class ESPRepository:
    # ... bestehende Methoden ...
    
    # ================================================================
    # MOCK-ESP SPEZIFISCHE METHODEN
    # ================================================================
    
    async def get_all_mock_devices(self) -> List[ESPDevice]:
        """
        Gibt alle Mock-ESPs zurück (hardware_type='MOCK_ESP32').
        
        Returns:
            Liste aller Mock-ESP Devices
        """
        query = select(ESPDevice).where(
            ESPDevice.hardware_type == "MOCK_ESP32"
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_running_mock_devices(self) -> List[ESPDevice]:
        """
        Gibt alle Mock-ESPs mit laufender Simulation zurück.
        
        Returns:
            Liste der Mock-ESPs mit simulation_state='running'
        """
        query = select(ESPDevice).where(
            ESPDevice.hardware_type == "MOCK_ESP32",
            ESPDevice.simulation_state == "running"
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_simulation_state(
        self, 
        device_id: str, 
        state: str
    ) -> bool:
        """
        Aktualisiert den Simulation-Status eines Mock-ESP.
        
        Args:
            device_id: ESP Device ID
            state: Neuer Status ('stopped', 'running', 'paused', 'error')
            
        Returns:
            True wenn erfolgreich
        """
        query = (
            update(ESPDevice)
            .where(ESPDevice.device_id == device_id)
            .values(simulation_state=state, updated_at=func.now())
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.rowcount > 0
    
    async def update_simulation_config(
        self, 
        device_id: str, 
        config: SimulationConfigSchema
    ) -> bool:
        """
        Aktualisiert die Simulation-Konfiguration.
        
        Args:
            device_id: ESP Device ID
            config: Neue Konfiguration
            
        Returns:
            True wenn erfolgreich
        """
        query = (
            update(ESPDevice)
            .where(ESPDevice.device_id == device_id)
            .values(
                simulation_config=config.model_dump(),
                updated_at=func.now()
            )
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.rowcount > 0
    
    async def get_simulation_config(
        self, 
        device_id: str
    ) -> Optional[SimulationConfigSchema]:
        """
        Lädt die Simulation-Konfiguration aus der DB.
        
        Args:
            device_id: ESP Device ID
            
        Returns:
            SimulationConfigSchema oder None
        """
        device = await self.get_by_device_id(device_id)
        if device and device.simulation_config:
            return SimulationConfigSchema(**device.simulation_config)
        return SimulationConfigSchema()  # Leere Config als Default
    
    async def delete_mock_device(self, device_id: str) -> bool:
        """
        Löscht Mock-ESP aus Datenbank.
        
        WICHTIG: Nur für Mock-ESPs verwenden!
        
        Args:
            device_id: ESP Device ID
            
        Returns:
            True wenn erfolgreich
        """
        # Sicherheitscheck: Nur Mock-ESPs löschen
        device = await self.get_by_device_id(device_id)
        if not device or device.hardware_type != "MOCK_ESP32":
            return False
        
        query = delete(ESPDevice).where(ESPDevice.device_id == device_id)
        result = await self.session.execute(query)
        await self.session.commit()
        return result.rowcount > 0
```

#### Schritt 4: MockESPManager refactoren

**Datei:** `src/services/mock_esp_manager.py`

**KOMPLETT NEU SCHREIBEN:**

```python
"""
Mock-ESP Manager - Refactored Version.

Prinzipien:
1. Database ist Single Source of Truth
2. In-Memory nur für aktive Tasks (nicht für State)
3. Stateless Design - kann jederzeit neu gestartet werden
4. Dependency Injection statt Singleton
"""

import asyncio
import logging
import time
import random
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.esp_repo import ESPRepository
from src.schemas.simulation import (
    SimulationConfigSchema,
    SensorSimulationSchema,
    VariationPattern,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulationRuntime:
    """
    Runtime-Informationen für eine laufende Simulation.
    
    Wird NICHT in DB gespeichert - nur für aktive Simulations-Tasks.
    """
    esp_id: str
    task: asyncio.Task
    start_time: float = field(default_factory=time.time)
    last_heartbeat: float = 0.0
    last_sensor_publish: Dict[int, float] = field(default_factory=dict)
    
    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time


class MockESPManager:
    """
    Verwaltet Mock-ESP Simulationen.
    
    ARCHITEKTUR:
    - State (Konfiguration) liegt in PostgreSQL
    - Manager hält nur Referenzen auf aktive asyncio.Tasks
    - Bei Server-Restart können Simulationen aus DB rekonstruiert werden
    
    VERWENDUNG:
    - Nicht als Singleton! Nutze FastAPI Dependency Injection.
    - Instanz wird pro-Request oder als shared instance erstellt.
    """
    
    def __init__(self, mqtt_publish_callback: Optional[Callable] = None):
        """
        Initialisiert den Manager.
        
        Args:
            mqtt_publish_callback: Callback für MQTT Publishing
                                   Signatur: async def callback(topic: str, payload: dict)
        """
        self._active_simulations: Dict[str, SimulationRuntime] = {}
        self._mqtt_publish = mqtt_publish_callback
        self._shutdown_event = asyncio.Event()
    
    def set_mqtt_callback(self, callback: Callable) -> None:
        """Setzt den MQTT Publish Callback."""
        self._mqtt_publish = callback
    
    # ================================================================
    # SIMULATION LIFECYCLE
    # ================================================================
    
    async def start_simulation(
        self,
        session: AsyncSession,
        esp_id: str
    ) -> bool:
        """
        Startet Simulation für einen Mock-ESP.
        
        Liest Konfiguration aus DB und startet Background-Task.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            
        Returns:
            True wenn erfolgreich gestartet
        """
        # Prüfe ob bereits läuft
        if esp_id in self._active_simulations:
            logger.warning(f"Simulation for {esp_id} already running")
            return False
        
        # Lade Device aus DB
        repo = ESPRepository(session)
        device = await repo.get_by_device_id(esp_id)
        
        if not device:
            logger.error(f"Device {esp_id} not found in database")
            return False
        
        if device.hardware_type != "MOCK_ESP32":
            logger.error(f"Device {esp_id} is not a mock device")
            return False
        
        # Lade Konfiguration
        config = await repo.get_simulation_config(esp_id)
        heartbeat_interval = device.heartbeat_interval or 60.0
        kaiser_id = device.kaiser_id or "god"
        zone_id = device.zone_id or ""
        
        # Erstelle und starte Task
        task = asyncio.create_task(
            self._simulation_loop(
                esp_id=esp_id,
                kaiser_id=kaiser_id,
                zone_id=zone_id,
                heartbeat_interval=heartbeat_interval,
                config=config,
                session_factory=self._get_session_factory(session)
            ),
            name=f"mock_sim_{esp_id}"
        )
        
        self._active_simulations[esp_id] = SimulationRuntime(
            esp_id=esp_id,
            task=task
        )
        
        # Update DB Status
        await repo.update_simulation_state(esp_id, "running")
        
        logger.info(f"Started simulation for {esp_id}")
        return True
    
    async def stop_simulation(
        self,
        session: AsyncSession,
        esp_id: str
    ) -> bool:
        """
        Stoppt Simulation für einen Mock-ESP.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            
        Returns:
            True wenn erfolgreich gestoppt
        """
        runtime = self._active_simulations.get(esp_id)
        if not runtime:
            logger.warning(f"No active simulation for {esp_id}")
            return False
        
        # Cancel Task
        runtime.task.cancel()
        try:
            await runtime.task
        except asyncio.CancelledError:
            pass
        
        # Entferne aus aktiven Simulationen
        del self._active_simulations[esp_id]
        
        # Update DB Status
        repo = ESPRepository(session)
        await repo.update_simulation_state(esp_id, "stopped")
        
        logger.info(f"Stopped simulation for {esp_id}")
        return True
    
    async def stop_all_simulations(self, session: AsyncSession) -> int:
        """
        Stoppt alle laufenden Simulationen.
        
        Wird bei Server-Shutdown aufgerufen.
        
        Returns:
            Anzahl gestoppter Simulationen
        """
        count = 0
        for esp_id in list(self._active_simulations.keys()):
            if await self.stop_simulation(session, esp_id):
                count += 1
        return count
    
    async def recover_simulations(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Rekonstruiert Simulationen aus Datenbank.
        
        Wird bei Server-Startup aufgerufen. Startet alle Simulationen
        die in DB als 'running' markiert sind.
        
        Returns:
            {"recovered": int, "failed": int, "details": [...]}
        """
        repo = ESPRepository(session)
        running_devices = await repo.get_running_mock_devices()
        
        results = {"recovered": 0, "failed": 0, "details": []}
        
        for device in running_devices:
            try:
                success = await self.start_simulation(session, device.device_id)
                if success:
                    results["recovered"] += 1
                    results["details"].append({
                        "esp_id": device.device_id,
                        "status": "recovered"
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "esp_id": device.device_id,
                        "status": "failed",
                        "error": "start_simulation returned False"
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "esp_id": device.device_id,
                    "status": "failed",
                    "error": str(e)
                })
        
        logger.info(
            f"Recovery complete: {results['recovered']} recovered, "
            f"{results['failed']} failed"
        )
        return results
    
    # ================================================================
    # SIMULATION LOOP
    # ================================================================
    
    async def _simulation_loop(
        self,
        esp_id: str,
        kaiser_id: str,
        zone_id: str,
        heartbeat_interval: float,
        config: SimulationConfigSchema,
        session_factory: Callable
    ) -> None:
        """
        Haupt-Simulations-Loop.
        
        Läuft bis Task gecancelt wird. Publiziert Heartbeats und
        Sensor-Daten gemäß Konfiguration.
        """
        runtime = self._active_simulations.get(esp_id)
        if not runtime:
            return
        
        # Sofort ersten Heartbeat senden
        await self._publish_heartbeat(esp_id, kaiser_id, zone_id, config)
        runtime.last_heartbeat = time.time()
        
        # Drift-State für DRIFT-Pattern Sensoren
        drift_values: Dict[int, float] = {}
        drift_directions: Dict[int, int] = {}
        
        for gpio, sensor in config.sensors.items():
            drift_values[gpio] = sensor.base_value
            drift_directions[gpio] = 1
        
        while True:
            try:
                current_time = time.time()
                
                # Heartbeat Check
                if current_time - runtime.last_heartbeat >= heartbeat_interval:
                    # Config neu laden (könnte sich geändert haben)
                    async with session_factory() as session:
                        repo = ESPRepository(session)
                        config = await repo.get_simulation_config(esp_id)
                    
                    await self._publish_heartbeat(esp_id, kaiser_id, zone_id, config)
                    runtime.last_heartbeat = current_time
                
                # Sensor Checks
                for gpio, sensor in config.sensors.items():
                    last_publish = runtime.last_sensor_publish.get(gpio, 0.0)
                    
                    if current_time - last_publish >= sensor.interval_seconds:
                        value = self._calculate_sensor_value(
                            sensor, 
                            config.manual_overrides.get(gpio),
                            drift_values,
                            drift_directions
                        )
                        
                        await self._publish_sensor_data(
                            esp_id, kaiser_id, gpio, sensor, value
                        )
                        runtime.last_sensor_publish[gpio] = current_time
                
                # Sleep - nicht zu kurz (CPU), nicht zu lang (Reaktivität)
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                logger.debug(f"Simulation loop cancelled for {esp_id}")
                break
            except Exception as e:
                logger.error(f"Error in simulation loop for {esp_id}: {e}")
                await asyncio.sleep(1.0)  # Backoff bei Fehler
    
    def _calculate_sensor_value(
        self,
        sensor: SensorSimulationSchema,
        manual_override: Optional[float],
        drift_values: Dict[int, float],
        drift_directions: Dict[int, int]
    ) -> float:
        """Berechnet den nächsten Sensor-Wert."""
        # Manual Override hat höchste Priorität
        if manual_override is not None:
            return manual_override
        
        gpio = sensor.gpio
        
        if sensor.variation_pattern == VariationPattern.CONSTANT:
            value = sensor.base_value
            
        elif sensor.variation_pattern == VariationPattern.RANDOM:
            variation = random.uniform(
                -sensor.variation_range, 
                sensor.variation_range
            )
            value = sensor.base_value + variation
            
        elif sensor.variation_pattern == VariationPattern.DRIFT:
            # Drift: Kontinuierliche Veränderung
            drift_values[gpio] += (
                sensor.variation_range * 
                drift_directions[gpio] * 
                0.1
            )
            
            # Richtung umkehren an Grenzen
            if sensor.max_value and drift_values[gpio] >= sensor.max_value:
                drift_directions[gpio] = -1
            elif sensor.min_value and drift_values[gpio] <= sensor.min_value:
                drift_directions[gpio] = 1
            
            value = drift_values[gpio]
        else:
            value = sensor.base_value
        
        # Clamp zu min/max
        if sensor.min_value is not None:
            value = max(value, sensor.min_value)
        if sensor.max_value is not None:
            value = min(value, sensor.max_value)
        
        return round(value, 2)
    
    async def _publish_heartbeat(
        self,
        esp_id: str,
        kaiser_id: str,
        zone_id: str,
        config: SimulationConfigSchema
    ) -> None:
        """Publiziert Heartbeat wie echter ESP32."""
        if not self._mqtt_publish:
            logger.warning("No MQTT callback configured")
            return
        
        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat"
        
        runtime = self._active_simulations.get(esp_id)
        uptime = int(runtime.uptime_seconds) if runtime else 0
        
        payload = {
            "esp_id": esp_id,
            "zone_id": zone_id,
            "master_zone_id": zone_id,  # Für Kompatibilität
            "zone_assigned": bool(zone_id),
            "ts": int(time.time() * 1000),
            "uptime": uptime,
            "heap_free": random.randint(40000, 50000),
            "wifi_rssi": random.randint(-60, -40),
            "sensor_count": len(config.sensors),
            "actuator_count": len(config.actuators),
        }
        
        try:
            result = self._mqtt_publish(topic, payload)
            if asyncio.iscoroutine(result):
                await result
            logger.debug(f"[{esp_id}] Heartbeat published")
        except Exception as e:
            logger.error(f"[{esp_id}] Heartbeat publish failed: {e}")
    
    async def _publish_sensor_data(
        self,
        esp_id: str,
        kaiser_id: str,
        gpio: int,
        sensor: SensorSimulationSchema,
        value: float
    ) -> None:
        """Publiziert Sensor-Daten wie echter ESP32."""
        if not self._mqtt_publish:
            return
        
        topic = f"kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data"
        
        payload = {
            "ts": int(time.time() * 1000),
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": sensor.sensor_type,
            "raw": int(value * 100),  # Simulierter RAW-Wert
            "raw_value": value,
            "raw_mode": True,
            "value": value,
            "unit": sensor.unit,
            "quality": sensor.quality,
        }
        
        try:
            result = self._mqtt_publish(topic, payload)
            if asyncio.iscoroutine(result):
                await result
            logger.debug(f"[{esp_id}] Sensor {gpio}: {value}")
        except Exception as e:
            logger.error(f"[{esp_id}] Sensor publish failed: {e}")
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _get_session_factory(self, session: AsyncSession) -> Callable:
        """
        Erstellt Session Factory aus bestehender Session.
        
        HINWEIS: In Production sollte die echte Session Factory
        aus src/db/session.py verwendet werden.
        """
        from src.db.session import async_session_maker
        return async_session_maker
    
    def get_simulation_status(self, esp_id: str) -> Optional[Dict[str, Any]]:
        """
        Gibt Runtime-Status einer Simulation zurück.
        
        Returns:
            Status-Dict oder None wenn nicht aktiv
        """
        runtime = self._active_simulations.get(esp_id)
        if not runtime:
            return None
        
        return {
            "esp_id": esp_id,
            "running": True,
            "uptime_seconds": runtime.uptime_seconds,
            "last_heartbeat": runtime.last_heartbeat,
            "last_sensor_publish": runtime.last_sensor_publish,
        }
    
    def get_active_simulation_ids(self) -> list:
        """Gibt Liste aller aktiven Simulation-IDs zurück."""
        return list(self._active_simulations.keys())
    
    def is_simulation_active(self, esp_id: str) -> bool:
        """Prüft ob Simulation aktiv ist."""
        return esp_id in self._active_simulations


# ================================================================
# DEPENDENCY INJECTION SETUP
# ================================================================

# Shared Instance für FastAPI (nicht Singleton!)
_manager_instance: Optional[MockESPManager] = None


def get_mock_esp_manager() -> MockESPManager:
    """
    FastAPI Dependency für MockESPManager.
    
    Verwendung:
        @router.post("/mock-esp")
        async def create_mock(
            manager: MockESPManager = Depends(get_mock_esp_manager)
        ):
            ...
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MockESPManager()
    return _manager_instance


def init_mock_esp_manager(mqtt_callback: Callable) -> MockESPManager:
    """
    Initialisiert den Manager mit MQTT Callback.
    
    Wird in main.py während Startup aufgerufen.
    """
    global _manager_instance
    _manager_instance = MockESPManager(mqtt_publish_callback=mqtt_callback)
    return _manager_instance
```

#### Schritt 5: main.py Integration anpassen

**Datei:** `src/main.py`

**In der Startup-Sektion (nach MQTT Client Setup, ~Zeile 191-197):**

```python
# ERSETZEN:
# mock_esp_manager = MockESPManager.get_instance()
# if mqtt_client:
#     mock_esp_manager.set_mqtt_client(mqtt_client)

# DURCH:
from src.services.mock_esp_manager import init_mock_esp_manager, get_mock_esp_manager

# Initialize MockESPManager with MQTT callback
def create_mqtt_publish_callback(client):
    """Creates publish callback for MockESPManager."""
    async def publish(topic: str, payload: dict):
        if client and client.is_connected():
            await client.publish(topic, payload, qos=1)
    return publish

mock_esp_manager = init_mock_esp_manager(
    mqtt_callback=create_mqtt_publish_callback(mqtt_client)
)

# Recover simulations from database
async with async_session_maker() as session:
    recovery_result = await mock_esp_manager.recover_simulations(session)
    logger.info(f"Mock ESP recovery: {recovery_result}")
```

**In der Shutdown-Sektion (am Ende von lifespan, vor `yield`):**

```python
# VOR dem yield block hinzufügen:
try:
    yield
finally:
    # Graceful shutdown
    logger.info("Shutting down Mock ESP simulations...")
    manager = get_mock_esp_manager()
    async with async_session_maker() as session:
        stopped = await manager.stop_all_simulations(session)
        logger.info(f"Stopped {stopped} mock simulations")
```

### 4.4 Verifikation

**Checkliste nach Implementierung:**

- [ ] Migration erfolgreich (`alembic upgrade head`)
- [ ] `esp_devices` Tabelle hat neue Spalten
- [ ] Mock-ESP kann erstellt werden (POST /debug/mock-esp)
- [ ] Simulation startet automatisch
- [ ] Server-Restart: Simulation wird recovered
- [ ] Kein In-Memory State außer aktive Tasks

**Test-Szenario:**

```bash
# 1. Mock erstellen
curl -X POST http://localhost:8000/debug/mock-esp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "test", "heartbeat_interval": 10}'

# 2. Server neustarten
# Ctrl+C, dann neu starten

# 3. Prüfen ob Simulation recovered wurde
curl http://localhost:8000/debug/mock-esp/sync-status \
  -H "Authorization: Bearer $TOKEN"

# Erwartet: Mock ist wieder aktiv
```

---

## 5. Problem 2: Task-per-Mock Skalierungsproblem

### 5.1 Problem-Beschreibung

**IST-Zustand:**
```python
# Jeder Mock-ESP hat eigenen asyncio.Task
self._simulation_loop_task = asyncio.create_task(self._simulation_loop())

# Bei 100 Mocks = 100 Tasks mit je eigenem 100ms Loop
while self._simulation.running:
    # ... checks ...
    await asyncio.sleep(0.1)  # 100ms
```

**Probleme:**
- 100 Tasks = 100 * 10 = 1000 Wakeups pro Sekunde
- CPU-Last steigt linear mit Mock-Anzahl
- asyncio Event Loop wird belastet

### 5.2 SOLL-Zustand

**Prinzip: Ein Scheduler für alle Jobs**

```
┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER-ARCHITEKTUR                    │
│                                                             │
│   APScheduler (AsyncIOScheduler)                            │
│        │                                                    │
│        ├── Job: mock_1_heartbeat (interval: 60s)            │
│        ├── Job: mock_1_sensor_4 (interval: 30s)             │
│        ├── Job: mock_1_sensor_5 (interval: 15s)             │
│        ├── Job: mock_2_heartbeat (interval: 60s)            │
│        ├── Job: mock_2_sensor_4 (interval: 30s)             │
│        └── ... (beliebig viele Jobs)                        │
│                                                             │
│   VORTEILE:                                                 │
│   - Effizientes Time-Wheel (O(1) pro Tick)                  │
│   - Ein Event Loop Wakeup für alle fälligen Jobs            │
│   - Jobs können pausiert/resumed werden                     │
│   - Übersicht über alle geplanten Jobs                      │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Entwickler-Anweisungen

#### Schritt 1: APScheduler installieren

**Datei:** `pyproject.toml`

```toml
[tool.poetry.dependencies]
# ... bestehende dependencies ...
apscheduler = "^3.10.4"
```

```bash
cd "El Servador/god_kaiser_server"
poetry add apscheduler
```

#### Schritt 2: Simulation Scheduler erstellen

**Neue Datei:** `src/services/simulation_scheduler.py`

```python
"""
Simulation Scheduler für Mock-ESPs.

Verwendet APScheduler für effizientes Job-Management.
Ein Scheduler für alle Mock-ESP Simulationen.
"""

import logging
import asyncio
import time
import random
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.interval import IntervalTrigger

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.esp_repo import ESPRepository
from src.schemas.simulation import (
    SimulationConfigSchema,
    SensorSimulationSchema,
    VariationPattern,
)

logger = logging.getLogger(__name__)


@dataclass
class MockESPRuntime:
    """Runtime-State für einen Mock-ESP."""
    esp_id: str
    kaiser_id: str
    zone_id: str
    start_time: float = field(default_factory=time.time)
    drift_values: Dict[int, float] = field(default_factory=dict)
    drift_directions: Dict[int, int] = field(default_factory=dict)
    
    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time


class SimulationScheduler:
    """
    Zentraler Scheduler für alle Mock-ESP Simulationen.
    
    ARCHITEKTUR:
    - Ein APScheduler für alle Mock-ESPs
    - Jobs werden dynamisch hinzugefügt/entfernt
    - State (Drift-Values etc.) in _runtimes Dict
    - Config wird aus DB geladen
    
    JOB-NAMING:
    - Heartbeat: "{esp_id}_heartbeat"
    - Sensor: "{esp_id}_sensor_{gpio}"
    - Actuator: "{esp_id}_actuator_{gpio}"
    """
    
    def __init__(self, mqtt_publish_callback: Optional[Callable] = None):
        """
        Initialisiert den Scheduler.
        
        Args:
            mqtt_publish_callback: Callback für MQTT Publishing
        """
        self._mqtt_publish = mqtt_publish_callback
        self._runtimes: Dict[str, MockESPRuntime] = {}
        self._session_factory: Optional[Callable] = None
        
        # APScheduler Setup
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # Verpasste Jobs zusammenfassen
            'max_instances': 1,  # Nur eine Instanz pro Job
            'misfire_grace_time': 30  # 30s Toleranz
        }
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )
    
    def set_session_factory(self, factory: Callable) -> None:
        """Setzt die Session Factory für DB-Zugriffe."""
        self._session_factory = factory
    
    def set_mqtt_callback(self, callback: Callable) -> None:
        """Setzt den MQTT Publish Callback."""
        self._mqtt_publish = callback
    
    def start(self) -> None:
        """Startet den Scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Simulation scheduler started")
    
    def shutdown(self, wait: bool = True) -> None:
        """Stoppt den Scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Simulation scheduler stopped")
    
    # ================================================================
    # SIMULATION MANAGEMENT
    # ================================================================
    
    async def start_mock_simulation(
        self,
        session: AsyncSession,
        esp_id: str
    ) -> bool:
        """
        Startet Simulation für einen Mock-ESP.
        
        Erstellt Jobs für Heartbeat und alle konfigurierten Sensoren.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            
        Returns:
            True wenn erfolgreich
        """
        # Prüfe ob bereits aktiv
        if esp_id in self._runtimes:
            logger.warning(f"Simulation for {esp_id} already active")
            return False
        
        # Lade Device und Config aus DB
        repo = ESPRepository(session)
        device = await repo.get_by_device_id(esp_id)
        
        if not device or device.hardware_type != "MOCK_ESP32":
            logger.error(f"Device {esp_id} not found or not a mock")
            return False
        
        config = await repo.get_simulation_config(esp_id)
        heartbeat_interval = device.heartbeat_interval or 60.0
        kaiser_id = device.kaiser_id or "god"
        zone_id = device.zone_id or ""
        
        # Runtime State erstellen
        runtime = MockESPRuntime(
            esp_id=esp_id,
            kaiser_id=kaiser_id,
            zone_id=zone_id
        )
        
        # Drift-State initialisieren
        for gpio, sensor in config.sensors.items():
            runtime.drift_values[gpio] = sensor.base_value
            runtime.drift_directions[gpio] = 1
        
        self._runtimes[esp_id] = runtime
        
        # Heartbeat Job erstellen
        self._scheduler.add_job(
            self._heartbeat_job,
            trigger=IntervalTrigger(seconds=heartbeat_interval),
            id=f"{esp_id}_heartbeat",
            args=[esp_id],
            replace_existing=True,
            next_run_time=None  # Sofort starten
        )
        
        # Sofort ersten Heartbeat senden
        await self._heartbeat_job(esp_id)
        
        # Sensor Jobs erstellen
        for gpio, sensor in config.sensors.items():
            self._scheduler.add_job(
                self._sensor_job,
                trigger=IntervalTrigger(seconds=sensor.interval_seconds),
                id=f"{esp_id}_sensor_{gpio}",
                args=[esp_id, gpio],
                replace_existing=True
            )
        
        # DB Status aktualisieren
        await repo.update_simulation_state(esp_id, "running")
        
        logger.info(
            f"Started simulation for {esp_id}: "
            f"heartbeat={heartbeat_interval}s, sensors={len(config.sensors)}"
        )
        return True
    
    async def stop_mock_simulation(
        self,
        session: AsyncSession,
        esp_id: str
    ) -> bool:
        """
        Stoppt Simulation für einen Mock-ESP.
        
        Entfernt alle zugehörigen Jobs.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            
        Returns:
            True wenn erfolgreich
        """
        if esp_id not in self._runtimes:
            logger.warning(f"No active simulation for {esp_id}")
            return False
        
        # Alle Jobs für diesen ESP entfernen
        jobs_removed = 0
        for job in self._scheduler.get_jobs():
            if job.id.startswith(f"{esp_id}_"):
                self._scheduler.remove_job(job.id)
                jobs_removed += 1
        
        # Runtime entfernen
        del self._runtimes[esp_id]
        
        # DB Status aktualisieren
        repo = ESPRepository(session)
        await repo.update_simulation_state(esp_id, "stopped")
        
        logger.info(f"Stopped simulation for {esp_id} ({jobs_removed} jobs removed)")
        return True
    
    async def stop_all_simulations(self, session: AsyncSession) -> int:
        """
        Stoppt alle laufenden Simulationen.
        
        Returns:
            Anzahl gestoppter Simulationen
        """
        count = 0
        for esp_id in list(self._runtimes.keys()):
            if await self.stop_mock_simulation(session, esp_id):
                count += 1
        return count
    
    # ================================================================
    # SENSOR MANAGEMENT (zur Laufzeit)
    # ================================================================
    
    async def add_sensor_to_simulation(
        self,
        session: AsyncSession,
        esp_id: str,
        sensor: SensorSimulationSchema
    ) -> bool:
        """
        Fügt Sensor zu laufender Simulation hinzu.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            sensor: Sensor-Konfiguration
            
        Returns:
            True wenn erfolgreich
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            logger.error(f"No active simulation for {esp_id}")
            return False
        
        gpio = sensor.gpio
        job_id = f"{esp_id}_sensor_{gpio}"
        
        # Prüfe ob Job bereits existiert
        if self._scheduler.get_job(job_id):
            logger.warning(f"Sensor job {job_id} already exists")
            return False
        
        # Drift-State initialisieren
        runtime.drift_values[gpio] = sensor.base_value
        runtime.drift_directions[gpio] = 1
        
        # Config in DB aktualisieren
        repo = ESPRepository(session)
        config = await repo.get_simulation_config(esp_id)
        config.add_sensor(sensor)
        await repo.update_simulation_config(esp_id, config)
        
        # Job erstellen
        self._scheduler.add_job(
            self._sensor_job,
            trigger=IntervalTrigger(seconds=sensor.interval_seconds),
            id=job_id,
            args=[esp_id, gpio],
            replace_existing=True
        )
        
        logger.info(f"Added sensor {gpio} to {esp_id} simulation")
        return True
    
    async def remove_sensor_from_simulation(
        self,
        session: AsyncSession,
        esp_id: str,
        gpio: int
    ) -> bool:
        """
        Entfernt Sensor aus laufender Simulation.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            gpio: GPIO Pin
            
        Returns:
            True wenn erfolgreich
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return False
        
        job_id = f"{esp_id}_sensor_{gpio}"
        
        # Job entfernen
        job = self._scheduler.get_job(job_id)
        if job:
            self._scheduler.remove_job(job_id)
        
        # Drift-State entfernen
        runtime.drift_values.pop(gpio, None)
        runtime.drift_directions.pop(gpio, None)
        
        # Config in DB aktualisieren
        repo = ESPRepository(session)
        config = await repo.get_simulation_config(esp_id)
        config.remove_sensor(gpio)
        await repo.update_simulation_config(esp_id, config)
        
        logger.info(f"Removed sensor {gpio} from {esp_id} simulation")
        return True
    
    async def update_sensor_interval(
        self,
        session: AsyncSession,
        esp_id: str,
        gpio: int,
        new_interval: float
    ) -> bool:
        """
        Aktualisiert das Intervall eines Sensors.
        
        Args:
            session: Database Session
            esp_id: ESP Device ID
            gpio: GPIO Pin
            new_interval: Neues Intervall in Sekunden
            
        Returns:
            True wenn erfolgreich
        """
        job_id = f"{esp_id}_sensor_{gpio}"
        job = self._scheduler.get_job(job_id)
        
        if not job:
            return False
        
        # Job mit neuem Intervall neu planen
        self._scheduler.reschedule_job(
            job_id,
            trigger=IntervalTrigger(seconds=new_interval)
        )
        
        # Config in DB aktualisieren
        repo = ESPRepository(session)
        config = await repo.get_simulation_config(esp_id)
        if gpio in config.sensors:
            config.sensors[gpio].interval_seconds = new_interval
            await repo.update_simulation_config(esp_id, config)
        
        logger.info(f"Updated sensor {gpio} interval to {new_interval}s")
        return True
    
    # ================================================================
    # JOB IMPLEMENTATIONS
    # ================================================================
    
    async def _heartbeat_job(self, esp_id: str) -> None:
        """
        Heartbeat Job - wird vom Scheduler aufgerufen.
        
        Args:
            esp_id: ESP Device ID
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return
        
        # Config aus DB laden (für aktuelle Sensor/Actuator Counts)
        sensor_count = 0
        actuator_count = 0
        
        if self._session_factory:
            try:
                async with self._session_factory() as session:
                    repo = ESPRepository(session)
                    config = await repo.get_simulation_config(esp_id)
                    sensor_count = len(config.sensors)
                    actuator_count = len(config.actuators)
            except Exception as e:
                logger.error(f"Failed to load config for heartbeat: {e}")
        
        topic = f"kaiser/{runtime.kaiser_id}/esp/{esp_id}/system/heartbeat"
        
        payload = {
            "esp_id": esp_id,
            "zone_id": runtime.zone_id,
            "master_zone_id": runtime.zone_id,
            "zone_assigned": bool(runtime.zone_id),
            "ts": int(time.time() * 1000),
            "uptime": int(runtime.uptime_seconds),
            "heap_free": random.randint(40000, 50000),
            "wifi_rssi": random.randint(-60, -40),
            "sensor_count": sensor_count,
            "actuator_count": actuator_count,
        }
        
        await self._publish(topic, payload)
        logger.debug(f"[{esp_id}] Heartbeat")
    
    async def _sensor_job(self, esp_id: str, gpio: int) -> None:
        """
        Sensor Job - wird vom Scheduler aufgerufen.
        
        Args:
            esp_id: ESP Device ID
            gpio: GPIO Pin
        """
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return
        
        # Config aus DB laden
        if not self._session_factory:
            return
        
        try:
            async with self._session_factory() as session:
                repo = ESPRepository(session)
                config = await repo.get_simulation_config(esp_id)
        except Exception as e:
            logger.error(f"Failed to load sensor config: {e}")
            return
        
        sensor = config.sensors.get(gpio)
        if not sensor:
            return
        
        # Wert berechnen
        value = self._calculate_sensor_value(
            sensor=sensor,
            manual_override=config.manual_overrides.get(gpio),
            drift_values=runtime.drift_values,
            drift_directions=runtime.drift_directions
        )
        
        topic = f"kaiser/{runtime.kaiser_id}/esp/{esp_id}/sensor/{gpio}/data"
        
        payload = {
            "ts": int(time.time() * 1000),
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": sensor.sensor_type,
            "raw": int(value * 100),
            "raw_value": value,
            "raw_mode": True,
            "value": value,
            "unit": sensor.unit,
            "quality": sensor.quality,
        }
        
        await self._publish(topic, payload)
        logger.debug(f"[{esp_id}] Sensor {gpio}: {value}")
    
    def _calculate_sensor_value(
        self,
        sensor: SensorSimulationSchema,
        manual_override: Optional[float],
        drift_values: Dict[int, float],
        drift_directions: Dict[int, int]
    ) -> float:
        """Berechnet Sensor-Wert (identisch zu MockESPManager)."""
        if manual_override is not None:
            return manual_override
        
        gpio = sensor.gpio
        
        if sensor.variation_pattern == VariationPattern.CONSTANT:
            value = sensor.base_value
        elif sensor.variation_pattern == VariationPattern.RANDOM:
            variation = random.uniform(
                -sensor.variation_range,
                sensor.variation_range
            )
            value = sensor.base_value + variation
        elif sensor.variation_pattern == VariationPattern.DRIFT:
            drift_values[gpio] += (
                sensor.variation_range *
                drift_directions[gpio] *
                0.1
            )
            if sensor.max_value and drift_values[gpio] >= sensor.max_value:
                drift_directions[gpio] = -1
            elif sensor.min_value and drift_values[gpio] <= sensor.min_value:
                drift_directions[gpio] = 1
            value = drift_values[gpio]
        else:
            value = sensor.base_value
        
        if sensor.min_value is not None:
            value = max(value, sensor.min_value)
        if sensor.max_value is not None:
            value = min(value, sensor.max_value)
        
        return round(value, 2)
    
    async def _publish(self, topic: str, payload: dict) -> None:
        """Publiziert zum MQTT Broker."""
        if not self._mqtt_publish:
            return
        
        try:
            result = self._mqtt_publish(topic, payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"MQTT publish failed: {e}")
    
    # ================================================================
    # STATUS & INFO
    # ================================================================
    
    def get_all_jobs(self) -> list:
        """Gibt alle geplanten Jobs zurück."""
        return [
            {
                "id": job.id,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]
    
    def get_mock_jobs(self, esp_id: str) -> list:
        """Gibt alle Jobs für einen Mock-ESP zurück."""
        return [
            job for job in self.get_all_jobs()
            if job["id"].startswith(f"{esp_id}_")
        ]
    
    def get_active_mock_ids(self) -> list:
        """Gibt IDs aller aktiven Mock-ESPs zurück."""
        return list(self._runtimes.keys())
    
    def is_mock_active(self, esp_id: str) -> bool:
        """Prüft ob Mock-ESP aktiv ist."""
        return esp_id in self._runtimes
    
    def get_runtime_status(self, esp_id: str) -> Optional[dict]:
        """Gibt Runtime-Status eines Mock-ESPs zurück."""
        runtime = self._runtimes.get(esp_id)
        if not runtime:
            return None
        
        return {
            "esp_id": esp_id,
            "kaiser_id": runtime.kaiser_id,
            "zone_id": runtime.zone_id,
            "uptime_seconds": runtime.uptime_seconds,
            "jobs": self.get_mock_jobs(esp_id),
        }


# ================================================================
# DEPENDENCY INJECTION
# ================================================================

_scheduler_instance: Optional[SimulationScheduler] = None


def get_simulation_scheduler() -> SimulationScheduler:
    """FastAPI Dependency für SimulationScheduler."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SimulationScheduler()
    return _scheduler_instance


def init_simulation_scheduler(
    mqtt_callback: Callable,
    session_factory: Callable
) -> SimulationScheduler:
    """
    Initialisiert den Scheduler.
    
    Wird in main.py während Startup aufgerufen.
    """
    global _scheduler_instance
    _scheduler_instance = SimulationScheduler(mqtt_publish_callback=mqtt_callback)
    _scheduler_instance.set_session_factory(session_factory)
    _scheduler_instance.start()
    return _scheduler_instance
```

#### Schritt 3: main.py für Scheduler anpassen

**Datei:** `src/main.py`

**In Startup-Sektion hinzufügen:**

```python
from src.services.simulation_scheduler import (
    init_simulation_scheduler,
    get_simulation_scheduler
)

# Nach MQTT Client Setup:
simulation_scheduler = init_simulation_scheduler(
    mqtt_callback=create_mqtt_publish_callback(mqtt_client),
    session_factory=async_session_maker
)

# Recovery (statt MockESPManager Recovery):
async with async_session_maker() as session:
    repo = ESPRepository(session)
    running_mocks = await repo.get_running_mock_devices()
    
    for device in running_mocks:
        try:
            await simulation_scheduler.start_mock_simulation(session, device.device_id)
        except Exception as e:
            logger.error(f"Failed to recover {device.device_id}: {e}")
```

**In Shutdown-Sektion:**

```python
finally:
    # Graceful shutdown
    scheduler = get_simulation_scheduler()
    async with async_session_maker() as session:
        await scheduler.stop_all_simulations(session)
    scheduler.shutdown(wait=True)
```

### 5.4 Verifikation

**Performance-Test:**

```python
# tests/performance/test_scheduler_scaling.py

import pytest
import asyncio
import time

@pytest.mark.asyncio
async def test_100_mocks_cpu_usage():
    """Testet CPU-Auslastung mit 100 Mock-ESPs."""
    scheduler = SimulationScheduler()
    scheduler.start()
    
    # 100 Mocks mit je 3 Sensoren = 400 Jobs
    for i in range(100):
        esp_id = f"MOCK_PERF_{i:03d}"
        # Simuliere Job-Erstellung...
    
    # CPU messen
    start_time = time.time()
    await asyncio.sleep(60)  # 1 Minute laufen lassen
    
    # Erwartung: CPU < 5% auf durchschnittlichem System
    scheduler.shutdown()
```

---

## 6. Problem 3: Singleton Anti-Pattern

### 6.1 Problem-Beschreibung

**IST-Zustand:**
```python
class MockESPManager:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

**Probleme:**
- Globaler State erschwert Tests
- Keine Dependency Injection möglich
- Versteckte Abhängigkeiten
- Mehrere Instanzen für Tests nicht möglich

### 6.2 SOLL-Zustand

**Prinzip: FastAPI Dependency Injection**

```python
# Statt:
manager = MockESPManager.get_instance()

# Verwende:
@router.post("/mock-esp")
async def create_mock(
    manager: MockESPManager = Depends(get_mock_esp_manager)
):
    ...
```

### 6.3 Entwickler-Anweisungen

**Die Lösung ist bereits in Problem 1 und 2 enthalten:**

1. `get_mock_esp_manager()` Dependency in `src/services/mock_esp_manager.py`
2. `get_simulation_scheduler()` Dependency in `src/services/simulation_scheduler.py`

**Zusätzlich: Alle bestehenden Singletons refactoren**

**Suche in Codebase nach:**
```bash
grep -r "get_instance\|_instance = None" src/
```

**Jeder Fund muss refactored werden zu:**

```python
# VORHER (Singleton)
class SomeService:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

# NACHHER (Dependency Injection)
_some_service_instance: Optional[SomeService] = None

def get_some_service() -> SomeService:
    """FastAPI Dependency."""
    global _some_service_instance
    if _some_service_instance is None:
        _some_service_instance = SomeService()
    return _some_service_instance

def init_some_service(...) -> SomeService:
    """Initialisierung in main.py."""
    global _some_service_instance
    _some_service_instance = SomeService(...)
    return _some_service_instance
```

### 6.4 Test-Verbesserung

**Neue Datei:** `tests/conftest.py` (ergänzen)

```python
import pytest
from src.services.mock_esp_manager import MockESPManager
from src.services.simulation_scheduler import SimulationScheduler

@pytest.fixture
def mock_esp_manager():
    """Frische Manager-Instanz für jeden Test."""
    return MockESPManager()

@pytest.fixture
def simulation_scheduler():
    """Frischer Scheduler für jeden Test."""
    scheduler = SimulationScheduler()
    scheduler.start()
    yield scheduler
    scheduler.shutdown(wait=False)

@pytest.fixture
def override_dependencies(mock_esp_manager, simulation_scheduler):
    """Override FastAPI Dependencies für Tests."""
    from src.main import app
    from src.services.mock_esp_manager import get_mock_esp_manager
    from src.services.simulation_scheduler import get_simulation_scheduler
    
    app.dependency_overrides[get_mock_esp_manager] = lambda: mock_esp_manager
    app.dependency_overrides[get_simulation_scheduler] = lambda: simulation_scheduler
    
    yield
    
    app.dependency_overrides.clear()
```

---

## 7. Problem 4: Fehlende Resilience-Patterns

### 7.1 Problem-Beschreibung

**IST-Zustand:**
```python
async def _publish_to_broker(self, topic: str, payload: dict):
    if self.on_publish:
        await self.on_publish(topic, payload)  # Keine Fehlerbehandlung
```

**Probleme:**
- MQTT Broker nicht erreichbar → Exception
- Kein Retry
- Kein Circuit Breaker
- Ein Fehler stoppt gesamte Simulation

### 7.2 SOLL-Zustand

**Prinzip: Graceful Degradation mit Circuit Breaker**

```
┌─────────────────────────────────────────────────────────────┐
│                    RESILIENCE PATTERN                       │
│                                                             │
│   Publish Request                                           │
│        │                                                    │
│        ▼                                                    │
│   Circuit Breaker Check                                     │
│        │                                                    │
│   ┌────┴────┐                                               │
│   │ CLOSED  │──► Versuche Publish                           │
│   └────┬────┘         │                                     │
│        │         ┌────┴────┐                                │
│        │         │ Success │──► Reset Failure Count         │
│        │         └─────────┘                                │
│        │         ┌────┴────┐                                │
│        │         │ Failure │──► Increment Failure Count     │
│        │         └────┬────┘                                │
│        │              │                                     │
│        │         Failures >= 5?                             │
│        │              │                                     │
│        │         ┌────┴────┐                                │
│   ┌────┴────┐    │  OPEN   │──► Reject (30s Cooldown)       │
│   │HALF-OPEN│◄───┴─────────┘                                │
│   └────┬────┘                                               │
│        │                                                    │
│   Test Request                                              │
│        │                                                    │
│   Success? ──► CLOSED                                       │
│   Failure? ──► OPEN                                         │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Entwickler-Anweisungen

#### Schritt 1: tenacity und circuitbreaker installieren

```bash
poetry add tenacity
```

#### Schritt 2: Resilience Utilities erstellen

**Neue Datei:** `src/utils/resilience.py`

```python
"""
Resilience Utilities für fehlertolerante Operationen.
"""

import asyncio
import logging
import time
from typing import Callable, Any, Optional
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Konfiguration für Circuit Breaker."""
    failure_threshold: int = 5          # Fehler bis OPEN
    recovery_timeout: float = 30.0      # Sekunden bis HALF_OPEN
    half_open_max_calls: int = 3        # Test-Calls in HALF_OPEN


@dataclass
class CircuitBreaker:
    """
    Async Circuit Breaker Implementation.
    
    Verhindert wiederholte Aufrufe zu einem fehlerhaften Service.
    """
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    
    @property
    def state(self) -> CircuitState:
        """Aktueller State mit automatischem Timeout-Check."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
        return self._state
    
    def record_success(self) -> None:
        """Aufzeichnung eines erfolgreichen Calls."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0
    
    def record_failure(self) -> None:
        """Aufzeichnung eines fehlgeschlagenen Calls."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN")
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: CLOSED -> OPEN (failures: {self._failure_count})")
    
    def allow_request(self) -> bool:
        """Prüft ob Request erlaubt ist."""
        state = self.state  # Triggert Timeout-Check
        
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.config.half_open_max_calls
        else:  # OPEN
            return False


def with_circuit_breaker(circuit: CircuitBreaker):
    """
    Decorator für Circuit Breaker Pattern.
    
    Usage:
        mqtt_circuit = CircuitBreaker("mqtt")
        
        @with_circuit_breaker(mqtt_circuit)
        async def publish(topic, payload):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not circuit.allow_request():
                logger.warning(f"Circuit {circuit.name} is OPEN, rejecting request")
                return None
            
            try:
                result = await func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception as e:
                circuit.record_failure()
                raise
        
        return wrapper
    return decorator


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0
):
    """
    Decorator für Retry mit Exponential Backoff.
    
    Usage:
        @with_retry(max_attempts=3)
        async def publish(topic, payload):
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=min_wait, max=max_wait),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


class ResilientPublisher:
    """
    MQTT Publisher mit Circuit Breaker und Retry.
    
    Kombiniert beide Patterns für maximale Robustheit.
    """
    
    def __init__(
        self,
        publish_callback: Callable,
        circuit_config: Optional[CircuitBreakerConfig] = None
    ):
        self._publish = publish_callback
        self._circuit = CircuitBreaker(
            name="mqtt_publish",
            config=circuit_config or CircuitBreakerConfig()
        )
    
    async def publish(
        self,
        topic: str,
        payload: dict,
        retry_on_failure: bool = True
    ) -> bool:
        """
        Publiziert mit Circuit Breaker und optionalem Retry.
        
        Returns:
            True wenn erfolgreich, False wenn Circuit offen oder Fehler
        """
        if not self._circuit.allow_request():
            logger.debug(f"Circuit open, skipping publish to {topic}")
            return False
        
        try:
            if retry_on_failure:
                await self._publish_with_retry(topic, payload)
            else:
                await self._do_publish(topic, payload)
            
            self._circuit.record_success()
            return True
            
        except Exception as e:
            self._circuit.record_failure()
            logger.error(f"Publish failed to {topic}: {e}")
            return False
    
    @with_retry(max_attempts=3, min_wait=0.5, max_wait=5.0)
    async def _publish_with_retry(self, topic: str, payload: dict) -> None:
        await self._do_publish(topic, payload)
    
    async def _do_publish(self, topic: str, payload: dict) -> None:
        result = self._publish(topic, payload)
        if asyncio.iscoroutine(result):
            await result
    
    @property
    def circuit_state(self) -> str:
        return self._circuit.state.value
    
    @property
    def failure_count(self) -> int:
        return self._circuit._failure_count
```

#### Schritt 3: SimulationScheduler mit Resilience erweitern

**In `src/services/simulation_scheduler.py`:**

```python
from src.utils.resilience import ResilientPublisher, CircuitBreakerConfig

class SimulationScheduler:
    def __init__(self, mqtt_publish_callback: Optional[Callable] = None):
        # ... bestehender Code ...
        
        # Resilient Publisher
        if mqtt_publish_callback:
            self._publisher = ResilientPublisher(
                publish_callback=mqtt_publish_callback,
                circuit_config=CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=30.0,
                    half_open_max_calls=3
                )
            )
        else:
            self._publisher = None
    
    async def _publish(self, topic: str, payload: dict) -> None:
        """Publiziert mit Resilience."""
        if self._publisher:
            await self._publisher.publish(topic, payload)
```

### 7.4 Verifikation

**Test für Circuit Breaker:**

```python
# tests/unit/test_resilience.py

import pytest
from src.utils.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitState

def test_circuit_breaker_opens_after_failures():
    circuit = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=3)
    )
    
    assert circuit.state == CircuitState.CLOSED
    
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.state == CircuitState.CLOSED
    
    circuit.record_failure()
    assert circuit.state == CircuitState.OPEN
    assert not circuit.allow_request()
```

---

## 8. Problem 5: Graceful Shutdown fehlt

### 8.1 Problem-Beschreibung

**IST-Zustand:**
- Server-Stop (Ctrl+C) → Tasks werden abrupt beendet
- Laufende DB-Transaktionen können korrupt werden
- Simulation-State in DB wird nicht aktualisiert

### 8.2 SOLL-Zustand

```
┌─────────────────────────────────────────────────────────────┐
│                    GRACEFUL SHUTDOWN                        │
│                                                             │
│   SIGTERM/SIGINT empfangen                                  │
│        │                                                    │
│        ▼                                                    │
│   1. Neue Requests ablehnen (503)                           │
│        │                                                    │
│        ▼                                                    │
│   2. Laufende Requests abarbeiten (30s Timeout)             │
│        │                                                    │
│        ▼                                                    │
│   3. Simulation-Jobs stoppen                                │
│        │                                                    │
│        ▼                                                    │
│   4. DB-Status aktualisieren (simulation_state='stopped')   │
│        │                                                    │
│        ▼                                                    │
│   5. Scheduler shutdown                                     │
│        │                                                    │
│        ▼                                                    │
│   6. MQTT disconnect                                        │
│        │                                                    │
│        ▼                                                    │
│   7. DB connections schließen                               │
│        │                                                    │
│        ▼                                                    │
│   Exit Code 0                                               │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 Entwickler-Anweisungen

#### Schritt 1: Lifespan in main.py vollständig implementieren

**Datei:** `src/main.py`

**Lifespan Context Manager überarbeiten:**

```python
import signal
import sys
from contextlib import asynccontextmanager

# Shutdown Event
shutdown_event = asyncio.Event()

def handle_shutdown_signal(signum, frame):
    """Signal Handler für graceful shutdown."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Manager.
    
    Handles startup and graceful shutdown.
    """
    # ================================================================
    # STARTUP
    # ================================================================
    logger.info("=" * 60)
    logger.info("Starting AutomationOne God-Kaiser Server")
    logger.info("=" * 60)
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    
    # ... bestehender Startup-Code ...
    
    # Step 0: Security Validation
    # Step 1: Database Initialization
    # Step 2: MQTT Client Setup
    # Step 3: MQTT Handler Registration
    # Step 4: WebSocket Manager
    # Step 5: Simulation Scheduler
    # Step 6: Recovery
    
    # Store references for shutdown
    app.state.mqtt_client = mqtt_client
    app.state.simulation_scheduler = simulation_scheduler
    app.state.websocket_manager = ws_manager
    
    logger.info("=" * 60)
    logger.info("Server startup complete")
    logger.info("=" * 60)
    
    try:
        yield
    finally:
        # ================================================================
        # SHUTDOWN
        # ================================================================
        logger.info("=" * 60)
        logger.info("Initiating graceful shutdown...")
        logger.info("=" * 60)
        
        # Step 1: Stop accepting new simulation starts
        logger.info("Step 1/5: Stopping simulation scheduler...")
        scheduler = getattr(app.state, 'simulation_scheduler', None)
        if scheduler:
            async with async_session_maker() as session:
                stopped_count = await scheduler.stop_all_simulations(session)
                logger.info(f"  Stopped {stopped_count} simulations")
            scheduler.shutdown(wait=True)
        
        # Step 2: Disconnect MQTT
        logger.info("Step 2/5: Disconnecting MQTT...")
        mqtt = getattr(app.state, 'mqtt_client', None)
        if mqtt:
            try:
                mqtt.disconnect()
            except Exception as e:
                logger.error(f"  MQTT disconnect error: {e}")
        
        # Step 3: Close WebSocket connections
        logger.info("Step 3/5: Closing WebSocket connections...")
        ws_mgr = getattr(app.state, 'websocket_manager', None)
        if ws_mgr:
            try:
                await ws_mgr.disconnect_all()
            except Exception as e:
                logger.error(f"  WebSocket disconnect error: {e}")
        
        # Step 4: Close database connections
        logger.info("Step 4/5: Closing database connections...")
        try:
            from src.db.session import engine
            await engine.dispose()
        except Exception as e:
            logger.error(f"  Database disconnect error: {e}")
        
        # Step 5: Final cleanup
        logger.info("Step 5/5: Final cleanup...")
        
        logger.info("=" * 60)
        logger.info("Graceful shutdown complete")
        logger.info("=" * 60)
```

#### Schritt 2: WebSocket Manager disconnect_all hinzufügen

**Datei:** `src/websocket/manager.py`

**Hinzufügen:**

```python
class WebSocketManager:
    # ... bestehender Code ...
    
    async def disconnect_all(self) -> int:
        """
        Schließt alle aktiven WebSocket-Verbindungen.
        
        Wird bei Server-Shutdown aufgerufen.
        
        Returns:
            Anzahl geschlossener Verbindungen
        """
        count = 0
        for client_id in list(self._connections.keys()):
            try:
                ws = self._connections[client_id]
                await ws.close(code=1001, reason="Server shutdown")
                del self._connections[client_id]
                count += 1
            except Exception as e:
                logger.error(f"Error closing WebSocket {client_id}: {e}")
        
        logger.info(f"Closed {count} WebSocket connections")
        return count
```

### 8.4 Verifikation

**Manueller Test:**

```bash
# 1. Server starten
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000

# 2. Mock-ESP erstellen (sollte Simulation starten)
curl -X POST http://localhost:8000/debug/mock-esp ...

# 3. Ctrl+C drücken

# 4. Logs prüfen - sollte zeigen:
# "Initiating graceful shutdown..."
# "Step 1/5: Stopping simulation scheduler..."
# "  Stopped 1 simulations"
# ...
# "Graceful shutdown complete"

# 5. Prüfen dass DB-Status korrekt ist
# simulation_state sollte 'stopped' sein
```

---

## 9. Implementierungs-Reihenfolge

```
Woche 1:
├── Tag 1-2: Problem 1 (Dual-Storage)
│   ├── DB Schema erweitern
│   ├── Repository erweitern
│   └── MockESPManager refactoren
│
├── Tag 3: Problem 2 (Scheduler)
│   ├── APScheduler installieren
│   └── SimulationScheduler implementieren
│
└── Tag 4: Problem 3 (Dependency Injection)
    ├── Singletons refactoren
    └── Test-Fixtures aktualisieren

Woche 2:
├── Tag 1: Problem 4 (Resilience)
│   ├── Circuit Breaker implementieren
│   └── In Scheduler integrieren
│
├── Tag 2: Problem 5 (Graceful Shutdown)
│   ├── Lifespan überarbeiten
│   └── WebSocket Manager erweitern
│
└── Tag 3-5: Testing & Integration
    ├── Unit Tests
    ├── Integration Tests
    └── Performance Tests
```

---

## 10. Verifikations-Checkliste

### Nach Problem 1 (Dual-Storage)

- [ ] Migration erfolgreich ausgeführt
- [ ] `simulation_state`, `simulation_config`, `heartbeat_interval` Spalten existieren
- [ ] Mock-ESP erstellen speichert Config in DB
- [ ] Server-Restart: Config wird aus DB geladen
- [ ] Kein In-Memory State außer Task-Referenzen

### Nach Problem 2 (Scheduler)

- [ ] APScheduler läuft (Log: "Simulation scheduler started")
- [ ] Jobs werden erstellt (überprüfbar via Debug-Endpoint)
- [ ] Heartbeat-Intervall konfigurierbar
- [ ] Sensor-Intervall pro Sensor konfigurierbar
- [ ] 100 Mocks: CPU-Auslastung < 5%

### Nach Problem 3 (Dependency Injection)

- [ ] Keine `get_instance()` Aufrufe mehr in Codebase
- [ ] Alle Manager via `Depends()` injected
- [ ] Tests können eigene Manager-Instanzen nutzen
- [ ] `app.dependency_overrides` funktioniert in Tests

### Nach Problem 4 (Resilience)

- [ ] Circuit Breaker öffnet nach 5 Fehlern
- [ ] Circuit Breaker schließt nach 30s Recovery
- [ ] Retry mit Exponential Backoff funktioniert
- [ ] Simulation läuft weiter bei temporären MQTT-Ausfällen

### Nach Problem 5 (Graceful Shutdown)

- [ ] Ctrl+C löst Graceful Shutdown aus
- [ ] Alle Simulations-States werden auf 'stopped' gesetzt
- [ ] WebSocket-Verbindungen werden sauber geschlossen
- [ ] Kein "Connection reset by peer" in Client-Logs
- [ ] Exit Code 0 bei normalem Shutdown

---

## Anhang A: Neue Dateien Übersicht

| Datei | Zweck |
|-------|-------|
| `src/schemas/simulation.py` | Pydantic Schemas für Simulation |
| `src/services/simulation_scheduler.py` | APScheduler-basierter Scheduler |
| `src/utils/resilience.py` | Circuit Breaker und Retry |
| `alembic/versions/xxx_add_simulation_fields.py` | DB Migration |

---

## Anhang B: Geänderte Dateien Übersicht

| Datei | Änderungen |
|-------|------------|
| `src/db/models/esp.py` | Neue Spalten für Simulation |
| `src/db/repositories/esp_repo.py` | Neue Methoden für Mock-ESPs |
| `src/services/mock_esp_manager.py` | Komplettes Refactoring |
| `src/main.py` | Scheduler Init, Graceful Shutdown |
| `src/websocket/manager.py` | `disconnect_all()` Methode |
| `src/api/v1/debug.py` | Neue Endpoints für Scheduler |
| `pyproject.toml` | APScheduler Dependency |

---

## Anhang C: API Endpoint Änderungen

### Neue Endpoints

| Endpoint | Method | Beschreibung |
|----------|--------|--------------|
| `/debug/scheduler/jobs` | GET | Alle geplanten Jobs |
| `/debug/scheduler/jobs/{esp_id}` | GET | Jobs für einen Mock-ESP |
| `/debug/mock-esp/{id}/simulation/sensors` | POST | Sensor zur laufenden Sim hinzufügen |
| `/debug/mock-esp/{id}/simulation/sensors/{gpio}` | DELETE | Sensor aus laufender Sim entfernen |
| `/debug/mock-esp/{id}/simulation/sensors/{gpio}/interval` | PATCH | Sensor-Intervall ändern |

### Geänderte Endpoints

| Endpoint | Änderung |
|----------|----------|
| `POST /debug/mock-esp` | Nutzt jetzt SimulationScheduler |
| `DELETE /debug/mock-esp/{id}` | Stoppt Scheduler-Jobs |
| `GET /debug/mock-esp/{id}/simulation/status` | Zeigt Scheduler-Jobs |

---

## 11. Verbesserungsvorschläge (Basierend auf Codebase-Analyse)

> **Analysiert am:** 2025-12-26
> **Prinzip:** Konsistenz mit bestehender Codebase wahren, minimale Änderungen

### 11.1 Sofort umsetzbar (Low-Hanging Fruit)

#### A. TopicBuilder in MockESP32Client verwenden
**Problem:** `mock_esp32_client.py` baut Topics manuell statt `TopicBuilder` zu verwenden.

**Aktuell (Zeile ~200):**
```python
def _build_sensor_topic(self, gpio: int) -> str:
    return f"kaiser/{self.kaiser_id}/esp/{self.esp_id}/sensor/{gpio}/data"
```

**Verbesserung:**
```python
# Am Anfang der Datei
from god_kaiser_server.src.mqtt.topics import TopicBuilder

def _build_sensor_topic(self, gpio: int) -> str:
    return TopicBuilder.build_sensor_data_topic(self.esp_id, gpio)
```

**Aufwand:** 30 Minuten | **Risiko:** Niedrig | **Benefit:** Konsistenz garantiert

---

#### B. Graceful Shutdown für MockESPManager in main.py
**Problem:** MockESPManager-Tasks werden bei Server-Shutdown nicht sauber beendet.

**Aktuell in `main.py` (Zeile 286-327):**
```python
# ===== SHUTDOWN =====
# ... kein Eintrag für MockESPManager!
```

**Verbesserung - Nach Zeile 303 einfügen:**
```python
# Step 3.5: Stop MockESPManager simulations
try:
    mock_esp_manager = await MockESPManager.get_instance()
    for esp_id in list(mock_esp_manager._heartbeat_tasks.keys()):
        mock_esp_manager._heartbeat_tasks[esp_id].cancel()
    logger.info("MockESPManager simulations stopped")
except Exception as e:
    logger.warning(f"MockESPManager shutdown failed: {e}")
```

**Aufwand:** 15 Minuten | **Risiko:** Niedrig | **Benefit:** Sauberer Shutdown

---

#### C. Bestehende Sync-Methoden nutzen statt neu bauen
**Erkenntnis:** `MockESPManager` hat BEREITS `get_sync_status()` und `get_orphaned_mock_ids()`.

**Empfehlung für Problem 1 (Dual-Storage):**
- Diese Methoden als Basis für die Migration nutzen
- Nicht komplett neu schreiben, sondern erweitern:

```python
# Bestehender Code in mock_esp_manager.py:634-676 nutzen
async def sync_from_database(self, session: AsyncSession) -> Dict[str, Any]:
    """Synchronisiert In-Memory Store mit Datenbank."""
    esp_repo = ESPRepository(session)
    db_mocks = await esp_repo.get_all_mock_devices()

    sync_status = self.get_sync_status([m.device_id for m in db_mocks])

    # Orphaned aus DB löschen oder in Memory rekonstruieren
    for orphan_id in sync_status["orphaned_ids"]:
        # Entscheidung: Rekonstruieren oder Löschen?
        ...

    return sync_status
```

**Aufwand:** 1 Stunde | **Risiko:** Niedrig | **Benefit:** Wiederverwendung existierenden Codes

---

### 11.2 Architektur-Verbesserungen (Mittelfristig)

#### D. Callback-Pattern beibehalten, aber erweitern
**Erkenntnis:** Das bestehende Callback-Pattern für MQTT Publishing ist gut.

**Aktuell in `mock_esp_manager.py:547-557`:**
```python
def _create_publish_callback(self, esp_id: str):
    def callback(topic: str, payload: Dict[str, Any], qos: int = 1):
        if self._mqtt_client and self._mqtt_client.is_connected():
            self._mqtt_client.publish(topic, json.dumps(payload), qos=qos)
    return callback
```

**Verbesserung - Circuit Breaker einbauen:**
```python
def _create_publish_callback(self, esp_id: str):
    circuit_breaker = CircuitBreaker(
        failure_threshold=5,
        recovery_timeout=30.0,
        expected_exceptions=(MQTTException,)
    )

    @circuit_breaker
    def callback(topic: str, payload: Dict[str, Any], qos: int = 1):
        if self._mqtt_client and self._mqtt_client.is_connected():
            self._mqtt_client.publish(topic, json.dumps(payload), qos=qos)
            return True
        raise MQTTException("MQTT not connected")

    return callback
```

**Aufwand:** 2 Stunden | **Risiko:** Mittel | **Benefit:** Resilience

---

#### E. WebSocket-Manager Pattern kopieren für MockESPManager
**Erkenntnis:** WebSocketManager hat bereits gutes Shutdown-Pattern.

**Aus `websocket/manager.py` lernen:**
```python
# WebSocketManager hat:
async def shutdown(self):
    """Graceful shutdown - disconnects all clients."""
    for connection in list(self._connections.values()):
        await connection.close()
    self._connections.clear()
```

**Für MockESPManager übernehmen:**
```python
async def shutdown(self) -> None:
    """Graceful shutdown - stops all simulations."""
    logger.info(f"Stopping {len(self._heartbeat_tasks)} mock simulations...")

    for esp_id, task in list(self._heartbeat_tasks.items()):
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    self._heartbeat_tasks.clear()
    self._mock_esps.clear()
    logger.info("MockESPManager shutdown complete")
```

**Aufwand:** 1 Stunde | **Risiko:** Niedrig | **Benefit:** Konsistentes Pattern

---

### 11.3 Alternative Lösungsansätze

#### F. Kompromiss für Problem 1: DB als Primary, Memory als Cache
Statt komplettes Refactoring, minimale Änderung:

```python
class MockESPManager:
    def __init__(self):
        self._mock_esps: Dict[str, MockESP32Client] = {}  # Bleibt als Cache
        self._db_is_primary: bool = True  # Flag für neues Verhalten

    async def get_mock_esp(self, esp_id: str, session: AsyncSession) -> Optional[MockESP32Client]:
        # 1. In-Memory Check (Cache-Hit)
        if esp_id in self._mock_esps:
            return self._mock_esps[esp_id]

        # 2. DB-Lookup (Cache-Miss)
        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(esp_id)

        if device and device.hardware_type == "MOCK_ESP32":
            # 3. Rekonstruieren und cachen
            mock = self._reconstruct_from_db(device)
            self._mock_esps[esp_id] = mock
            return mock

        return None
```

**Aufwand:** 2 Stunden | **Risiko:** Niedrig | **Benefit:** Inkrementelle Migration

---

#### G. Problem 2 Alternative: Task-Pool statt APScheduler
Einfacher als APScheduler, nutzt bestehende asyncio-Patterns:

```python
class TaskPoolSimulator:
    """Simpler Scheduler ohne externe Dependencies."""

    def __init__(self, max_concurrent: int = 100):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: Dict[str, asyncio.Task] = {}

    async def schedule_simulation(self, esp_id: str, coro):
        async with self._semaphore:
            self._tasks[esp_id] = asyncio.create_task(coro)

    async def cancel_simulation(self, esp_id: str):
        if esp_id in self._tasks:
            self._tasks[esp_id].cancel()
            del self._tasks[esp_id]
```

**Vorteile:**
- Keine neue Dependency
- Nutzt bestehende asyncio-Patterns
- Einfacher zu verstehen und debuggen

**Aufwand:** 3 Stunden | **Risiko:** Niedrig | **Benefit:** Keine neue Abhängigkeit

---

### 11.4 Priorisierte Umsetzungsreihenfolge

| Priorität | Verbesserung | Aufwand | Begründung |
|-----------|-------------|---------|------------|
| 1 | B. Graceful Shutdown in main.py | 15 Min | Kritisches Problem, einfache Lösung |
| 2 | A. TopicBuilder verwenden | 30 Min | Konsistenz-Risiko eliminieren |
| 3 | E. Shutdown-Pattern übernehmen | 1 Std | Vorbereitung für größere Änderungen |
| 4 | C. Sync-Methoden erweitern | 1 Std | Bestehenden Code nutzen |
| 5 | F. DB als Primary | 2 Std | Inkrementeller Ansatz für Problem 1 |
| 6 | G. Task-Pool statt APScheduler | 3 Std | Alternative zu Problem 2 |
| 7 | D. Circuit Breaker | 2 Std | Resilience für Problem 4 |

**Gesamt-Aufwand (minimale Lösung):** ~10 Stunden
**Gesamt-Aufwand (vollständige Lösung aus Plan):** ~5-7 Tage

---

### 11.5 Kritische Erkenntnisse aus der Codebase-Analyse

1. **Auto-Discovery ist DEAKTIVIERT:** ESPs MÜSSEN in DB registriert sein bevor Heartbeats akzeptiert werden. Das aktuelle Dual-Storage ist deshalb notwendig - aber die Lösung sollte das sauber konsolidieren.

2. **MockESP32Client ist test-fokussiert:** Die Datei liegt in `tests/esp32/mocks/` - sie wurde primär für Tests geschrieben, nicht für Production-Debug. Bei der Migration bedenken.

3. **get_sync_status() zeigt Problem-Awareness:** Der Code hat bereits Workarounds für das Dual-Storage-Problem. Die neue Lösung sollte diese eliminieren, nicht erweitern.

4. **Heartbeat-Handler ist streng:** Payload-Validierung erwartet spezifische Felder (`ts`, `uptime`, `heap_free`, `wifi_rssi`). MockESP32Client muss diese liefern.

5. **WebSocket-Broadcast ist konsistent:** Alle Handler nutzen dasselbe Pattern für Frontend-Updates. Mock-ESPs sollten das gleiche Ergebnis produzieren.

---

**Ende des Dokuments**

*Bei Fragen: Projekt-Dokumentation in `.claude/` konsultieren*