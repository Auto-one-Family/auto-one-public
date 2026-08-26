# DEVELOPER BRIEFING: Logic Engine Integration in Test-Suite

**Version:** 2.0 (Code-Verifiziert)
**Datum:** 2026-01-30
**Autor:** Robin (Product Owner / System Architect)
**Code-Analyse:** Manager #2 (Analyse-Manager)
**Empfänger:** Test-Suite-Entwickler (Domain-Expert für Gewächshaus-Automatisierung)

---

## ÄNDERUNGSPROTOKOLL (Version 2.0)

| Section | Status | Änderung |
|---------|--------|----------|
| 3.2 | [ERGÄNZT] | Modular Evaluators/Executors + Safety-Komponenten hinzugefügt |
| 3.3 | [KORRIGIERT] | Rule-Struktur mit echtem DB-Model abgeglichen (UUID, rule_name, etc.) |
| 3.4 | [ERGÄNZT] | 12 neue Code-Locations für Logic Sub-Komponenten |
| 3.5 | [NEU] | Condition/Action Types aus echtem Code dokumentiert |
| 3.6 | [NEU] | Safety-Komponenten dokumentiert (ConflictManager, SequenceExecutor) |
| 5.1 | [KORRIGIERT] | MockESP32Client: 1678 Zeilen (nicht ~1433), vollständige Methodenliste |
| 5.2 | [KORRIGIERT] | 15 echte Fixtures mit Zeilennummern dokumentiert |
| 5.4 | [NEU] | Wichtige Importe für Tests (Mock, Logic, Schema, Safety) |
| 6.2 | [KORRIGIERT] | `ConditionCreate`/`ActionCreate` → raw dicts (wie echte API) |
| 6.2 | [KORRIGIERT] | `evaluate_rules()` → `evaluate_sensor_data()` (echte Methode) |
| 6.2 | [KORRIGIERT] | `get_actuator_state()` gibt `ActuatorState` zurück, nicht bool |
| 8.1 | [NEU] | Bereits existierende Methoden dokumentiert (NICHT implementieren!) |
| 8.2 | [KORRIGIERT] | Nur wirklich neue Methoden mit Hardware-Kontext |
| 8.3 | [NEU] | Implementierungs-Checkliste (existiert vs. implementieren) |
| 10.2 | [KORRIGIERT] | Deliverables: `add_sht31()` entfernt (nutze `set_multi_value_sensor()`) |

---

## 1. SYSTEM-KONTEXT: Was ist AutomationOne?

### 1.1 Überblick

AutomationOne ist ein **industrielles IoT-Framework für Gewächshaus-Automatisierung** mit folgender Architektur:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ El Frontend (Vue 3 + TypeScript)                                        │
│ Rolle: Web Dashboard, Monitoring, Konfiguration                         │
└─────────────────────────────────────────────────────────────────────────┘
                    ↕ HTTP REST API + WebSocket
┌─────────────────────────────────────────────────────────────────────────┐
│ God-Kaiser Server (FastAPI + PostgreSQL + MQTT)                         │
│ Rolle: Control Hub, Logic Engine, Sensor-Processing, Database           │
│ Code: El Servador/god_kaiser_server/                                    │
│ ⭐ FOKUS DIESER AUFGABE: Logic Engine Testing                           │
└─────────────────────────────────────────────────────────────────────────┘
                    ↕ MQTT (TLS)
┌─────────────────────────────────────────────────────────────────────────┐
│ ESP32-Agenten (C++ Firmware)                                            │
│ Rolle: Sensor-Auslesung, Aktor-Steuerung ("dumme" Agenten)              │
│ Code: El Trabajante/                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Server-Centric Architektur-Prinzip

**KRITISCH:** Der God-Kaiser Server ist die "Intelligenz" des Systems. ESPs sind "dumme" Agenten.

```
ESP32 sendet:     RAW-Daten (z.B. analogRead = 2048)
Server macht:     Umrechnung, Validierung, Business-Logic, Cross-ESP-Automation
ESP32 empfängt:   Befehle (z.B. "GPIO 5 = HIGH")
```

**Warum?**
- ESP32 hat begrenzte Ressourcen (RAM, CPU)
- Zentrale Logik = einfache Wartung
- Cross-ESP-Regeln nur auf Server möglich
- Python-Libraries für Sensor-Kalibrierung

---

## 2. DEINE ROLLE ALS ENTWICKLER

### 2.1 Aufgabe

Du bist ein **Test-Suite-Entwickler mit Greenhouse-Domain-Expertise**. Deine Aufgabe:

1. **Die existierende Test-Infrastruktur verstehen** (MockESP32Client, pytest)
2. **Hardware-realistische Testszenarien erstellen** (pH, DS18B20, SHT31, Relays, PWM)
3. **Logic Engine Integration testen** (Cross-ESP-Automation-Rules)
4. **MockESP32Client erweitern** (neue Hardware-Simulation)

### 2.2 Was du NICHT tust

- ❌ Tests **ausführen** (nur erstellen)
- ❌ Server oder Frontend Code ändern
- ❌ Hardware beschaffen oder anschließen
- ❌ Produktions-Code schreiben

### 2.3 Was du tust

- ✅ Tests **erstellen** (pytest, Python)
- ✅ MockESP32Client **erweitern** (Hardware-Simulation)
- ✅ Testszenarien **dokumentieren** (warum dieser Test wichtig ist)
- ✅ Hardware-Kontext **einbringen** (welche Sensoren verhalten sich wie)

---

## 3. FOKUSBEREICH: LOGIC ENGINE

### 3.1 Was ist die Logic Engine?

Die Logic Engine ermöglicht **Cross-ESP-Automation**: "Wenn Sensor auf ESP_A einen Wert erreicht, dann aktiviere Actuator auf ESP_B."

**Code-Location:** `El Servador/god_kaiser_server/src/services/logic_engine.py` [VERIFIZIERT]

### 3.2 Logic Engine Architektur [ERGÄNZT]

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LOGIC ENGINE FLOW                               │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. Sensor-Daten via MQTT → sensor_handler.handle_sensor_data()       │
│  2. Sensor-Daten in DB gespeichert                                    │
│  3. sensor_handler ruft logic_engine.evaluate_sensor_data()           │
│     (non-blocking via asyncio.create_task)                            │
│  4. LogicEngine lädt passende Rules aus DB (get_rules_by_trigger)     │
│  5. Für jede Rule: Conditions evaluieren via MODULAR EVALUATORS       │
│     - SensorConditionEvaluator (sensor_threshold, sensor)             │
│     - TimeConditionEvaluator (time_window, time)                      │
│     - HysteresisConditionEvaluator (hysteresis) ← NEU                 │
│     - CompoundConditionEvaluator (AND/OR logic)                       │
│  6. ConflictManager prüft Actuator-Locks (Priority-basiert)           │
│  7. RateLimiter prüft max_executions_per_hour                         │
│  8. Bei Match: Actions ausführen via MODULAR EXECUTORS                │
│     - ActuatorActionExecutor (actuator_command, actuator)             │
│     - DelayActionExecutor (delay)                                     │
│     - NotificationActionExecutor (notification)                       │
│     - SequenceActionExecutor (sequence) ← NEU                         │
│  9. Actuator-Command via ActuatorService.send_command()               │
│ 10. Safety-Checks VOR Command-Publishing (SafetyService)              │
│ 11. Command via MQTT Publisher (QoS 1)                                │
│ 12. Execution in DB geloggt (LogicExecutionHistory)                   │
│ 13. WebSocket Broadcast für Live-Updates                              │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Rule-Struktur (Database Model) [KORRIGIERT]

```python
# Echte DB-Model-Struktur aus src/db/models/logic.py
# CrossESPLogic Model

from uuid import UUID

# Beispiel-Rule in Database (KORRIGIERT)
{
    "id": UUID("..."),                    # UUID, nicht int!
    "rule_name": "Auto-Ventilation",      # NICHT "name" - das ist ein Alias
    "description": "Lüfter bei hoher Temp",
    "enabled": True,
    "priority": 100,                      # Default=100, niedriger=höhere Priorität
    "logic_operator": "AND",              # AND oder OR für multiple conditions

    # trigger_conditions ist dict ODER list (nicht nur dict)
    "trigger_conditions": {
        "type": "sensor_threshold",       # oder "sensor" (Shorthand)
        "esp_id": "ESP_SENSOR_01",
        "gpio": 4,
        "sensor_type": "DS18B20",
        "operator": ">",                  # >, <, >=, <=, ==, !=, between
        "value": 28.0
    },

    # actions ist list
    "actions": [
        {
            "type": "actuator_command",   # oder "actuator" (Shorthand)
            "esp_id": "ESP_ACTUATOR_01",
            "gpio": 25,
            "command": "ON",              # ON, OFF, PWM, TOGGLE
            "value": 1.0,
            "duration_seconds": 0         # oder "duration" - beide akzeptiert
        }
    ],

    "cooldown_seconds": 300,              # Optional
    "max_executions_per_hour": None,      # Optional Rate-Limit
    "last_triggered": None,               # Timestamp der letzten Ausführung
    "rule_metadata": {}                   # Zusätzliche Metadaten
}
```

### 3.4 Relevante Code-Locations [ERGÄNZT]

| Komponente | Pfad | Beschreibung |
|------------|------|--------------|
| **Logic Engine** | `src/services/logic_engine.py` | Background-Task, Rule-Evaluation (782 Zeilen) |
| Logic Service | `src/services/logic_service.py` | CRUD für Rules |
| Logic Scheduler | `src/services/logic_scheduler.py` | Timer-basierte Rule-Evaluation |
| **Logic Models** | `src/db/models/logic.py` | CrossESPLogic, LogicExecutionHistory (332 Zeilen) |
| Logic Validation | `src/db/models/logic_validation.py` | Pydantic-Validation für conditions/actions |
| Logic Repository | `src/db/repositories/logic_repo.py` | DB-Queries |
| **Logic Schemas** | `src/schemas/logic.py` | API-Schemas (670 Zeilen) |
| Logic API | `src/api/v1/logic.py` | REST Endpoints |
| Actuator Service | `src/services/actuator_service.py` | Command Execution |
| Safety Service | `src/services/safety_service.py` | Safety Validation |

**[NEU] Modular Condition Evaluators:**

| Evaluator | Pfad | Unterstützte Types |
|-----------|------|-------------------|
| SensorConditionEvaluator | `src/services/logic/conditions/sensor_evaluator.py` | `sensor_threshold`, `sensor` |
| TimeConditionEvaluator | `src/services/logic/conditions/time_evaluator.py` | `time_window`, `time` |
| HysteresisConditionEvaluator | `src/services/logic/conditions/hysteresis_evaluator.py` | `hysteresis` |
| CompoundConditionEvaluator | `src/services/logic/conditions/compound_evaluator.py` | AND/OR Logic |
| BaseConditionEvaluator | `src/services/logic/conditions/base.py` | Abstract Base Class |

**[NEU] Modular Action Executors:**

| Executor | Pfad | Unterstützte Types |
|----------|------|-------------------|
| ActuatorActionExecutor | `src/services/logic/actions/actuator_executor.py` | `actuator_command`, `actuator` |
| DelayActionExecutor | `src/services/logic/actions/delay_executor.py` | `delay` |
| NotificationActionExecutor | `src/services/logic/actions/notification_executor.py` | `notification` |
| SequenceActionExecutor | `src/services/logic/actions/sequence_executor.py` | `sequence` (908 Zeilen!) |
| BaseActionExecutor | `src/services/logic/actions/base.py` | Abstract Base Class |

**[NEU] Safety-Komponenten:**

| Komponente | Pfad | Beschreibung |
|------------|------|--------------|
| ConflictManager | `src/services/logic/safety/conflict_manager.py` | Actuator-Lock-Management, Priority-basiert |
| RateLimiter | `src/services/logic/safety/rate_limiter.py` | max_executions_per_hour |
| LoopDetector | `src/services/logic/safety/loop_detector.py` | Zirkuläre Dependencies erkennen |

### 3.5 Condition/Action Types (aus echtem Code) [NEU]

#### Condition Types

| Type | Beschreibung | Beispiel |
|------|--------------|----------|
| `sensor_threshold` / `sensor` | Sensor-Wert-Vergleich | `{"type": "sensor", "esp_id": "ESP_001", "gpio": 4, "operator": ">", "value": 25.0}` |
| `time_window` / `time` | Zeitfenster | `{"type": "time", "start_hour": 8, "end_hour": 18}` |
| `hysteresis` | Anti-Flattern | `{"type": "hysteresis", "esp_id": "ESP_001", "gpio": 4, "activate_above": 28.0, "deactivate_below": 24.0}` |
| Compound | AND/OR Logic | `{"logic": "AND", "conditions": [...]}` |

**Operatoren:** `>`, `<`, `>=`, `<=`, `==`, `!=`, `between`

**Hysteresis-Modi (aus hysteresis_evaluator.py:41-68):**
- **Kühlung:** `activate_above` + `deactivate_below` (z.B. Lüfter an bei >28°C, aus bei <24°C)
- **Heizung:** `activate_below` + `deactivate_above` (z.B. Heizung an bei <18°C, aus bei >22°C)

#### Action Types

| Type | Beschreibung | Beispiel |
|------|--------------|----------|
| `actuator_command` / `actuator` | Aktor-Steuerung | `{"type": "actuator", "esp_id": "ESP_001", "gpio": 5, "command": "ON", "value": 1.0}` |
| `delay` | Verzögerung (1-3600s) | `{"type": "delay", "seconds": 5}` |
| `notification` | Email/Webhook/WebSocket | `{"type": "notification", "channel": "websocket", "target": "dashboard", "message_template": "..."}` |
| `sequence` | Verkettete Actions | `{"type": "sequence", "steps": [...], "abort_on_failure": true}` |

**Actuator Commands:** `ON`, `OFF`, `PWM`, `TOGGLE`

**Notification Channels:** `email`, `webhook`, `websocket`

### 3.6 Safety-Komponenten (aus echtem Code) [NEU]

#### ConflictManager (conflict_manager.py)

Verhindert, dass mehrere Rules gleichzeitig denselben Actuator steuern.

```python
# Aus conflict_manager.py:92-206
async def acquire_actuator(
    self,
    esp_id: str,
    gpio: int,
    rule_id: str,
    priority: int,
    command: str,
    is_safety_critical: bool = False,
    lock_ttl_seconds: Optional[int] = None
) -> Tuple[bool, Optional[ConflictInfo]]:
    """
    Strategie:
    1. Höhere Priorität gewinnt (niedrigerer priority-Wert = höher)
    2. Bei gleicher Priorität: Erste Rule gewinnt (FIFO)
    3. Safety-kritische Commands haben IMMER Vorrang
    4. Locks haben TTL (default: 60 Sekunden)
    """
```

**ConflictResolution Enum:**
- `HIGHER_PRIORITY_WINS`
- `FIRST_WINS`
- `SAFETY_WINS`
- `BLOCKED`

#### SequenceActionExecutor (sequence_executor.py)

Führt verkettete Actions mit Delays, Timeouts und Error-Handling aus.

```python
# Limits aus sequence_executor.py:174-191
MAX_CONCURRENT_SEQUENCES = 20
MAX_STEPS_PER_SEQUENCE = 50
MAX_SEQUENCE_DURATION_SECONDS = 3600  # 1 Stunde
DEFAULT_STEP_TIMEOUT_SECONDS = 30
PROGRESS_RETENTION_SECONDS = 3600
```

**Sequence-Step-Format:**
```python
{
    "type": "sequence",
    "description": "Pump-Valve Interlock",
    "abort_on_failure": True,
    "steps": [
        {"name": "Open Valve", "action": {"type": "actuator", "esp_id": "ESP_001", "gpio": 6, "command": "ON"}},
        {"delay_seconds": 2},
        {"name": "Start Pump", "action": {"type": "actuator", "esp_id": "ESP_001", "gpio": 5, "command": "ON"}}
    ]
}

---

## 4. HARDWARE-RECHERCHE

Diese Sektion dokumentiert die **echten Hardware-Spezifikationen** der Sensoren und Aktoren, die in Gewächshäusern verwendet werden. Deine Tests müssen diese Realität abbilden.

### 4.1 pH Sensor: Haoshi H-101 (Industrial BNC Electrode)

#### Hardware-Charakteristik

| Eigenschaft | Wert |
|-------------|------|
| Typ | Analog (BNC-Connector) |
| Messbereich | pH 0-14 |
| Auflösung | 0.01 pH |
| Genauigkeit | ±0.05 pH |
| Interface Board | PH-4502C oder DFRobot Gravity erforderlich |
| Output | 0-5V → Interface Board → 0-3.3V für ESP32 |
| Antwortzeit | ~10 Sekunden nach Eintauchen |
| Drift | ≤0.02 pH/24h (bei kalibrierten Sensoren) |

#### ESP32 Integration

```
pH Electrode (BNC) → Interface Board (PH-4502C) → ESP32 ADC
                            │
                            ├── VCC: 5V (oder 3.3V je nach Board)
                            ├── GND: Ground
                            └── Po: Analog Output → GPIO34-39 (ADC1!)
```

**KRITISCH: ADC1 vs ADC2**
- **ADC1 (GPIO32-39):** Immer verfügbar, auch mit WiFi
- **ADC2 (GPIO0,2,4,12-15,25-27):** DEAKTIVIERT wenn WiFi aktiv!

**Empfohlene Pins:** GPIO34, GPIO35, GPIO36, GPIO39

#### Kalibrierung

**Zwei-Punkt-Kalibrierung erforderlich:**

1. **Neutral-Punkt (pH 7.0):**
   - Elektrode in pH 7.0 Pufferlösung
   - Warten bis Wert stabil (~1-2 Minuten)
   - Offset einstellen (sollte ~2.5V = Mitte des Bereichs)

2. **Acid-Punkt (pH 4.0):**
   - Elektrode in pH 4.0 Pufferlösung
   - Slope einstellen
   - Ergibt ~3V Output

**Formel nach Kalibrierung:**
```
pH = slope * voltage + offset
```

Wobei:
- `slope` = (pH_4 - pH_7) / (V_4 - V_7) ≈ -5.7 pH/V
- `offset` = pH bei 0V (extrapoliert)

#### Fehler-Szenarien für Tests

| RAW-Wert | ADC-Reading | Bedeutung | Test-Aktion |
|----------|-------------|-----------|-------------|
| pH < 0 | ADC ≈ 4095 | Sensor defekt/getrennt | Emergency + Alert |
| pH > 14 | ADC ≈ 0 | Sensor defekt | Emergency + Alert |
| pH = 7.0 ±0.1 | ADC ≈ 2048 | Neutral (Kurzschluss-Test) | Normal |
| pH driftet >0.5/24h | - | Kalibrierung nötig | Alert senden |

---

### 4.2 DS18B20 Temperature Sensor (OneWire Digital)

#### Hardware-Charakteristik

| Eigenschaft | Wert |
|-------------|------|
| Protokoll | OneWire (Dallas) |
| Messbereich | -55°C bis +125°C |
| Genauigkeit | ±0.5°C (-10°C bis +85°C) |
| Auflösung | 0.0625°C (12-bit Modus) |
| Unique ID | 64-bit ROM-Adresse pro Sensor |
| Conversion Time | 750ms (12-bit) |

#### Verkabelung

**Normal Mode (EMPFOHLEN):**
```
DS18B20 Pin 1 (GND) → ESP32 GND
DS18B20 Pin 2 (DQ)  → ESP32 GPIO4 + 4.7kΩ Pull-up zu 3.3V
DS18B20 Pin 3 (VDD) → ESP32 3.3V
```

**Mehrere Sensoren auf einem Bus:**
- Bis zu ~20 Sensoren auf einem GPIO möglich
- Jeder Sensor hat einzigartige 64-bit ROM-Adresse
- 4.7kΩ Pull-up reicht für kurze Kabel
- Für lange Kabel (>10m): 2.2kΩ Pull-up

**Empfohlene GPIO-Pins:** GPIO4, GPIO16, GPIO17 (keine Boot-Konflikte)

#### Spezielle Werte (KRITISCH für Tests)

| RAW-Wert | Temperatur | Bedeutung | Test-Aktion |
|----------|------------|-----------|-------------|
| -2032 | -127.0°C | Sensor-Fehler/CRC-Fehler/Getrennt | Error loggen, Skip |
| 1360 | +85.0°C | Power-On-Reset (Factory Default) | Ignorieren beim Boot |
| 1400-2000 | 87.5-125°C | Mögliche Überhitzung | Warning/Emergency |

**Test-Szenarien:**
```python
# Sensor-Fault Detection
async def test_ds18b20_reports_minus127_on_disconnect():
    """DS18B20 meldet -127°C wenn getrennt oder CRC-Fehler."""
    mock.set_sensor_value(gpio=4, raw=-2032)  # -127°C
    # Logic Rule sollte NICHT triggern, Error loggen

# Power-On-Reset Detection
async def test_ds18b20_ignores_85_on_boot():
    """DS18B20 meldet +85°C nach Power-On. Nicht als echte Temperatur werten."""
    mock.set_sensor_value(gpio=4, raw=1360)  # +85°C
    mock.is_first_reading_after_boot = True
    # Logic Rule sollte ignorieren, warten auf nächsten Wert
```

---

### 4.3 SHT31 Temperature & Humidity Sensor (I2C Digital)

#### Hardware-Charakteristik

| Eigenschaft | Wert |
|-------------|------|
| Protokoll | I2C |
| Temperatur | -40°C bis +125°C, ±0.2°C |
| Luftfeuchtigkeit | 0-100% RH, ±2% |
| Auflösung | 0.01°C, 0.01% RH |
| Built-in Heater | Ja (für Kondensation) |

#### I2C Adressierung

| ADR Pin | I2C Adresse |
|---------|-------------|
| LOW/Float | 0x44 (Default) |
| HIGH (VDD) | 0x45 |

**MAXIMUM 2 SHT31 pro I2C-Bus!** Für mehr: TCA9548A I2C Multiplexer nötig.

#### Verkabelung

```
SHT31 VCC → ESP32 3.3V
SHT31 GND → ESP32 GND
SHT31 SDA → ESP32 GPIO21 + 10kΩ Pull-up
SHT31 SCL → ESP32 GPIO22 + 10kΩ Pull-up
SHT31 ADR → GND (für 0x44) oder VDD (für 0x45)
```

**Standard I2C Pins ESP32:** GPIO21 (SDA), GPIO22 (SCL)

#### Heater-Funktion

Der SHT31 hat einen eingebauten Heater für Kondensations-Entfernung:
- Aktivieren bei >95% RH für >5 Minuten
- Heater läuft max 30 Sekunden
- Verhindert falsche Readings durch Wassertropfen

**Test-Szenario:**
```python
async def test_sht31_heater_activation_at_high_humidity():
    """Bei >95% RH für 5+ Minuten: Heater aktivieren."""
    mock.set_sht31_value(address=0x44, humidity=98.5, temp=22.0)
    mock.set_high_humidity_duration(minutes=6)
    # Logic Rule sollte Heater-Command senden
```

---

### 4.4 ESP32 GPIO-Referenz

#### ESP32-WROOM-32 (Classic)

**Sichere GPIO-Pins (keine Boot-Konflikte):**
```
GPIO13, GPIO14, GPIO16, GPIO17, GPIO18, GPIO19, GPIO21, GPIO22, GPIO23, 
GPIO25, GPIO26, GPIO27, GPIO32, GPIO33
```

**ADC1 (SICHER mit WiFi):**
```
GPIO32 (ADC1_CH4), GPIO33 (ADC1_CH5), GPIO34 (ADC1_CH6), 
GPIO35 (ADC1_CH7), GPIO36 (ADC1_CH0), GPIO39 (ADC1_CH3)
```

**Strapping Pins (VORSICHT):**
```
GPIO0  - Muss HIGH bei Boot (LOW = Flash-Modus)
GPIO2  - Muss LOW bei Boot
GPIO12 - Muss LOW bei Boot (Flash-Spannung)
GPIO15 - Muss LOW bei Boot
```

**NIEMALS NUTZEN:**
```
GPIO6-11 - SPI Flash (System crash!)
GPIO34-39 - Nur Input (kein Output/Pull-up)
```

#### ESP32-C3 (RISC-V)

**Strapping Pins:**
```
GPIO2, GPIO8, GPIO9 - Boot-Mode-Steuerung
```

**ADC (nur 5 Kanäle!):**
```
GPIO0-4 (ADC1)
```

**I2C Default:**
```
GPIO8 (SDA), GPIO9 (SCL) - ACHTUNG: Strapping Pins!
```

**Empfehlung:** I2C auf andere Pins mappen wenn möglich.

---

### 4.5 Relay Control

#### Relay-Modul-Typen

| Typ | Trigger | HIGH | LOW |
|-----|---------|------|-----|
| Active-LOW (häufig) | LOW aktiviert | Relay OFF | Relay ON |
| Active-HIGH | HIGH aktiviert | Relay ON | Relay OFF |

#### Sichere GPIO-Pins für Relays

**EMPFOHLEN:** GPIO16, GPIO17 (keine Boot-Konflikte, kein PWM-Glitch)

**VERMEIDEN:** GPIO0, GPIO2, GPIO12, GPIO15 (Strapping Pins → Relay "rattert" beim Boot)

#### Verkabelung

```
Relay Module VCC → 5V (von VIN oder extern)
Relay Module GND → ESP32 GND (gemeinsam!)
Relay Module IN1 → ESP32 GPIO16
Relay Module IN2 → ESP32 GPIO17
```

**WARNUNG:** Relay-Spule zieht ~70-90mA. ESP32 GPIO max ~40mA!
- Relay-Module haben eingebauten Treiber-Transistor
- NIEMALS Relay-Spule direkt an GPIO!

#### Test-Szenarien

```python
async def test_pump_valve_interlock():
    """Pumpe darf nicht starten wenn Ventil geschlossen."""
    # Rule: IF irrigation_scheduled THEN:
    # 1. Valve ON (GPIO17)
    # 2. Wait 2000ms
    # 3. Pump ON (GPIO16)
    
async def test_relay_boot_safety():
    """Relay auf sicherem Pin (GPIO16) sollte beim Boot nicht toggled werden."""
    mock.simulate_boot_sequence()
    assert mock.get_relay_state(gpio=16) == "unchanged"
```

---

### 4.6 PWM Actuators (Fans, Pumps, Servos)

#### ESP32 LEDC (PWM)

| Parameter | Wert |
|-----------|------|
| Kanäle | 16 unabhängige |
| Frequenz | Wenige Hz bis 40 MHz |
| Auflösung | Bis 16-bit |
| Typisch für Motoren | 1-25 kHz, 8-10 bit |

#### Sichere PWM-Pins

**EMPFOHLEN:** GPIO25, GPIO26, GPIO27 (haben auch DAC)

#### Servo-Steuerung

```
Frequenz: 50 Hz (20ms Periode)
Pulsbreite: 1ms (0°) bis 2ms (180°)
```

**Test-Szenario:**
```python
async def test_servo_valve_proportional_control():
    """Servo-Ventil öffnet proportional zum Flow-Demand."""
    # 0% demand → 0° (1.0ms pulse)
    # 50% demand → 90° (1.5ms pulse)
    # 100% demand → 180° (2.0ms pulse)
```

---

## 5. EXISTIERENDE TEST-INFRASTRUKTUR [KORRIGIERT]

### 5.1 MockESP32Client [VERIFIZIERT]

**Location:** `El Servador/god_kaiser_server/tests/esp32/mocks/mock_esp32_client.py`

**Aktuell 1678 Zeilen** (nicht ~1433) mit folgenden Kernmethoden:

```python
# Aus mock_esp32_client.py - ECHTE IMPORTS
from tests.esp32.mocks.mock_esp32_client import MockESP32Client, BrokerMode, SystemState

# Instanziierung (mock_esp32_client.py:175-192)
mock = MockESP32Client(
    esp_id="MOCK_GREENHOUSE_01",
    kaiser_id="god",
    auto_heartbeat=False,
    broker_mode=BrokerMode.DIRECT,  # oder BrokerMode.MQTT für echten Broker
    mqtt_config=None  # Optional: {"host": "localhost", "port": 1883}
)

# Zone konfigurieren - PFLICHT vor Actuator-Control! (mock_esp32_client.py:388-412)
mock.configure_zone(
    zone_id="greenhouse",
    master_zone_id="main-greenhouse",
    subzone_id="zone-a",       # Optional
    zone_name="Greenhouse",    # Optional
    subzone_name="Zone A"      # Optional
)

# Sensor konfigurieren - VOLLSTÄNDIGE Signatur (mock_esp32_client.py:1511-1563)
mock.set_sensor_value(
    gpio=4,
    raw_value=23.5,           # Float, nicht int!
    sensor_type="DS18B20",
    name="Soil Temperature",
    unit="°C",
    quality="good",           # excellent, good, fair, poor, bad, stale
    library_name="",          # Optional
    subzone_id=None,          # Optional
    calibration=None,         # Optional: {"offset": 0.0, "multiplier": 1.0}
    processed_value=None,     # Optional: Server-berechneter Wert
    is_multi_value=False,     # True für SHT31 etc.
    secondary_values=None,    # Optional: {"humidity": 65.2}
    raw_mode=False           # True wenn Server processing macht
)

# Multi-Value-Sensor (SHT31) - EXISTIERT! (mock_esp32_client.py:1565-1593)
mock.set_multi_value_sensor(
    gpio=21,
    sensor_type="SHT31",
    primary_value=23.5,       # Temperature
    secondary_values={"humidity": 65.2},
    name="SHT31 Temp/Humidity",
    quality="good"
)

# Actuator konfigurieren - VOLLSTÄNDIGE Signatur (mock_esp32_client.py:1595-1616)
mock.configure_actuator(
    gpio=16,
    actuator_type="relay",    # relay, pump, valve, fan, pwm_motor
    name="Irrigation Pump",
    min_value=0.0,            # PWM-Minimum
    max_value=1.0,            # PWM-Maximum
    safety_timeout_ms=0,      # 0 = unbegrenzt
    inverted=False            # Active-LOW Relay
)

# Command ausführen (mock_esp32_client.py:466-521)
response = mock.handle_command("actuator_set", {
    "gpio": 16,
    "value": 1,
    "mode": "digital"         # oder "pwm"
})

# Actuator-Status prüfen - gibt ActuatorState zurück! (mock_esp32_client.py:1503-1505)
state = mock.get_actuator_state(gpio=16)
assert state.state == True    # ActuatorState Objekt, nicht bool!
assert state.emergency_stopped == False

# Published Messages prüfen (mock_esp32_client.py:1622-1628)
messages = mock.get_published_messages()
messages_filtered = mock.get_messages_by_topic_pattern("sensor")

# System State Machine (mock_esp32_client.py:67-80)
# SystemState: BOOT, WIFI_SETUP, WIFI_CONNECTED, MQTT_CONNECTING, MQTT_CONNECTED,
#              AWAITING_USER_CONFIG, ZONE_CONFIGURED, SENSORS_CONFIGURED,
#              OPERATIONAL, LIBRARY_DOWNLOADING, SAFE_MODE, ERROR
assert mock.get_system_state() == SystemState.OPERATIONAL
```

**Wichtige existierende Methoden:**

| Methode | Zeile | Beschreibung |
|---------|-------|--------------|
| `configure_zone()` | 388 | Zone/Subzone konfigurieren |
| `set_sensor_value()` | 1511 | Sensor-Wert setzen (vollständig) |
| `set_multi_value_sensor()` | 1565 | Multi-Value Sensor (SHT31) |
| `configure_actuator()` | 1595 | Actuator konfigurieren |
| `handle_command()` | 466 | Command-Handler (zentral) |
| `get_actuator_state()` | 1503 | ActuatorState abrufen |
| `get_sensor_state()` | 1507 | SensorState abrufen |
| `get_published_messages()` | 1622 | Alle MQTT-Messages |
| `get_messages_by_topic_pattern()` | 1626 | Messages nach Topic filtern |
| `enter_safe_mode()` | 442 | SAFE_MODE aktivieren |
| `exit_safe_mode()` | 454 | SAFE_MODE verlassen |
| `reset()` | 1634 | Mock zurücksetzen |
| `disconnect()` | 1642 | Verbindung trennen |
| `reconnect()` | 1647 | Verbindung wiederherstellen |

### 5.2 Test-Fixtures (conftest.py) [KORRIGIERT]

**Location:** `El Servador/god_kaiser_server/tests/esp32/conftest.py` (790 Zeilen)

```python
# tests/esp32/conftest.py - ECHTE FIXTURES

# === BASIC FIXTURES ===

@pytest.fixture
def mock_esp32():
    """Standard Mock ESP mit Zone-Config (conftest.py:27-48)"""
    mock = MockESP32Client(esp_id="test-esp-001", kaiser_id="god")
    mock.configure_zone("test-zone", "test-master", "test-subzone")
    yield mock
    mock.reset()

@pytest.fixture
def mock_esp32_unconfigured():
    """Mock OHNE Zone - für Provisioning-Tests (conftest.py:51-59)"""
    mock = MockESP32Client(esp_id="ESP_UNPROVISIONED", kaiser_id="god")
    yield mock
    mock.reset()

# === PRE-CONFIGURED FIXTURES ===

@pytest.fixture
def mock_esp32_with_actuators():
    """3 Aktoren vorkonfiguriert (conftest.py:63-88)
    - GPIO 5: Pump (digital)
    - GPIO 6: Valve (digital)
    - GPIO 7: PWM Motor
    """

@pytest.fixture
def mock_esp32_with_sensors():
    """3 Sensoren vorkonfiguriert (conftest.py:91-136)
    - GPIO 34: Analog (moisture)
    - GPIO 35: Analog (temperature)
    - GPIO 36: Digital (flow)
    """

@pytest.fixture
def mock_esp32_with_zones():
    """Mit Zone-Config + Sensor + Actuator (conftest.py:140-182)"""

@pytest.fixture
def mock_esp32_with_sht31():
    """Multi-Value SHT31 Sensor (conftest.py:185-220)
    - GPIO 21: SHT31 (temp=23.5, humidity=65.2)
    - GPIO 4: DS18B20 Backup
    """

@pytest.fixture
def mock_esp32_greenhouse():
    """⭐ KOMPLETTES GREENHOUSE SETUP (conftest.py:223-323)
    Zone: greenhouse / main-greenhouse / zone-a
    Sensors:
        - GPIO 4: DS18B20 Temperature (calibriert)
        - GPIO 21: SHT31 Temp+Humidity (multi-value)
        - GPIO 34: Soil Moisture (analog)
    Actuators:
        - GPIO 5: Irrigation Pump (safety_timeout_ms=300000)
        - GPIO 6: Ventilation Valve
        - GPIO 7: Fan (PWM, min=0.2, max=1.0)
    Libraries: dallas_temp, sht31_combined
    """

# === CROSS-ESP FIXTURES ===

@pytest.fixture
def multiple_mock_esp32():
    """3 ESPs für Cross-ESP-Tests (conftest.py:326-381)
    - esp1: Actuator Controller (GPIO 5 Pump, GPIO 6 Valve)
    - esp2: Sensor Station (GPIO 34 moisture, 35 temp, 36 flow)
    - esp3: Mixed (1 Actuator, 2 Sensors)

    Usage:
        esps = multiple_mock_esp32
        esps["esp1"].handle_command(...)
        esps["esp2"].set_sensor_value(...)
    """

@pytest.fixture
def multiple_mock_esp32_with_zones():
    """4 ESPs mit Zone-Struktur (conftest.py:384-435)
    Master Zone: greenhouse-complex
    Subzones:
        - zone-a: ESP_ZA_SENS (sensors) + ESP_ZA_ACT (actuators)
        - zone-b: ESP_ZB_SENS (sensors) + ESP_ZB_ACT (actuators)
    """

# === SAFE MODE FIXTURE ===

@pytest.fixture
def mock_esp32_safe_mode():
    """Für SAFE_MODE Tests (conftest.py:438-456)
    - GPIO 5: Test Pump
    - GPIO 6: Test Valve
    """

# === MQTT BROKER FIXTURES ===

@pytest.fixture
def mock_esp32_with_broker(mqtt_test_config):
    """Mit echtem MQTT Broker (conftest.py:567-610)
    Skipped wenn Broker nicht erreichbar.
    """

@pytest.fixture
def mock_esp32_broker_fallback(mqtt_test_config):
    """Broker wenn verfügbar, sonst DIRECT (conftest.py:613-659)"""
```

### 5.3 Test-Kategorien [AKTUALISIERT]

| Verzeichnis | Tests | Status |
|-------------|-------|--------|
| `tests/esp32/` | ~100+ | ✅ Produktionsreif |
| `tests/unit/` | ~30+ | ✅ Produktionsreif |
| `tests/integration/` | ~50+ | ✅ Produktionsreif |
| `tests/e2e/` | ~10 | ⏳ In Entwicklung |

### 5.4 Wichtige Importe für Tests [NEU]

```python
# === MOCK IMPORTS ===
from tests.esp32.mocks.mock_esp32_client import (
    MockESP32Client,
    BrokerMode,
    SystemState,
    ActuatorState,
    SensorState,
    QualityLevel,
    ZoneConfig
)

# === LOGIC ENGINE IMPORTS ===
from src.services.logic_engine import LogicEngine, get_logic_engine, set_logic_engine
from src.services.logic_service import LogicService
from src.db.repositories.logic_repo import LogicRepository
from src.db.models.logic import CrossESPLogic, LogicExecutionHistory

# === SCHEMA IMPORTS (API-Modelle) ===
from src.schemas.logic import (
    LogicRuleCreate,
    LogicRuleUpdate,
    LogicRuleResponse,
    RuleTestRequest,
    RuleTestResponse,
    ExecutionHistoryEntry,
    SensorCondition,
    TimeCondition,
    ActuatorAction,
    DelayAction,
    NotificationAction
)

# === SERVICE IMPORTS ===
from src.services.actuator_service import ActuatorService
from src.services.safety_service import SafetyService
from src.websocket.manager import WebSocketManager

# === SAFETY COMPONENT IMPORTS ===
from src.services.logic.safety.conflict_manager import ConflictManager, ConflictInfo
from src.services.logic.safety.rate_limiter import RateLimiter
```

---

## 6. NEUE TEST-DATEIEN (DEINE DELIVERABLES)

### 6.1 Übersicht

Du erstellst **6 neue Test-Dateien**:

| Datei | Fokus | Tests (ca.) |
|-------|-------|-------------|
| `test_ph_sensor_logic.py` | pH-Sensor + Logic Engine | ~10 |
| `test_ds18b20_cross_esp_logic.py` | DS18B20 Multi-Sensor + Logic | ~12 |
| `test_sht31_i2c_logic.py` | SHT31 I2C Adressierung + Logic | ~8 |
| `test_relay_logic_chains.py` | Relay Interlock + Safety | ~10 |
| `test_pwm_logic.py` | PWM/Servo Proportional Control | ~6 |
| `test_logic_engine_real_server.py` | E2E mit echtem Server | ~8 |

**Total: ~54 neue Tests**

### 6.2 Test-Datei Template [KORRIGIERT]

```python
"""
Test-Modul: [MODUL_NAME]

Fokus: [BESCHREIBUNG]

Hardware-Kontext:
- [SENSOR/AKTOR TYP]
- [INTERFACE: I2C/OneWire/Analog/Digital]
- [GPIO-PINS]
- [SPEZIELLE ANFORDERUNGEN]

Dependencies:
- MockESP32Client
- LogicService
- LogicRepository
- ActuatorService (für Action-Execution)
- SafetyService (für Safety-Validation)
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

# === MOCK IMPORTS (aus Section 5.4) ===
from tests.esp32.mocks.mock_esp32_client import (
    MockESP32Client,
    BrokerMode,
    SystemState,
    ActuatorState,
    SensorState,
)

# === LOGIC ENGINE IMPORTS ===
from src.services.logic_engine import LogicEngine, get_logic_engine
from src.services.logic_service import LogicService
from src.db.repositories.logic_repo import LogicRepository
from src.db.models.logic import CrossESPLogic, LogicExecutionHistory

# === SCHEMA IMPORTS (ECHTE Klassen aus src/schemas/logic.py) ===
# WICHTIG: LogicRuleCreate akzeptiert conditions/actions als List[Dict]!
# Die Condition/Action-Klassen sind Dokumentation, nicht Pflicht.
from src.schemas.logic import (
    LogicRuleCreate,
    LogicRuleUpdate,
    LogicRuleResponse,
    SensorCondition,     # Dokumentations-Klasse für Sensor-Conditions
    TimeCondition,       # Dokumentations-Klasse für Time-Conditions
    ActuatorAction,      # Dokumentations-Klasse für Actuator-Actions
    DelayAction,         # Dokumentations-Klasse für Delay-Actions
    NotificationAction,  # Dokumentations-Klasse für Notifications
)


class TestModulName:
    """[BESCHREIBUNG DER TEST-KLASSE]"""

    @pytest_asyncio.fixture
    async def logic_setup(self, db_session):
        """Setup Logic Engine mit Repository."""
        logic_repo = LogicRepository(db_session)
        logic_service = LogicService(logic_repo)
        logic_engine = LogicEngine(logic_repo)

        return {
            "repo": logic_repo,
            "service": logic_service,
            "engine": logic_engine,
            "session": db_session
        }

    @pytest.mark.asyncio
    async def test_example_scenario(self, logic_setup, mock_esp32_greenhouse):
        """
        SZENARIO: [BESCHREIBUNG]

        HARDWARE-KONTEXT:
        - [WELCHER SENSOR/AKTOR]
        - [GPIO-PIN]
        - [INTERFACE-DETAILS]

        GIVEN: [VORBEDINGUNG]
        WHEN: [AKTION]
        THEN: [ERWARTETES ERGEBNIS]

        LOGIC RULE:
        - Condition: [BEDINGUNG]
        - Action: [AKTION]
        """
        # === SETUP ===
        mock = mock_esp32_greenhouse
        logic = logic_setup["service"]

        # Rule erstellen - KORRIGIERT: conditions/actions sind List[Dict]!
        # Die API akzeptiert raw dicts, NICHT typisierte Klassen.
        rule = await logic.create_rule(LogicRuleCreate(
            name="Test Rule",
            description="Test Description",
            conditions=[
                {
                    "type": "sensor",           # oder "sensor_threshold"
                    "esp_id": "MOCK_GREENHOUSE_001",
                    "gpio": 4,
                    "sensor_type": "DS18B20",
                    "operator": ">",
                    "value": 28.0,              # Float, nicht RAW!
                }
            ],
            actions=[
                {
                    "type": "actuator",         # oder "actuator_command"
                    "esp_id": "MOCK_GREENHOUSE_001",
                    "gpio": 25,
                    "command": "ON",
                    "value": 1.0,
                    "duration": 0,              # 0 = bis expliziter Stop
                }
            ],
            logic_operator="AND",
            enabled=True,
            priority=50,                        # 1-100, Default=50
            cooldown_seconds=60,                # Minimum zwischen Executions
        ))

        # === TRIGGER ===
        # WICHTIG: set_sensor_value erwartet raw_value als Float!
        mock.set_sensor_value(gpio=4, raw_value=29.5, sensor_type="DS18B20")

        # Logic Engine evaluieren via evaluate_sensor_data (echte Methode!)
        await logic_setup["engine"].evaluate_sensor_data(
            esp_id="MOCK_GREENHOUSE_001",
            gpio=4,
            sensor_type="DS18B20",
            value=29.5,
        )

        # === VERIFY ===
        # WICHTIG: get_actuator_state() gibt ActuatorState zurück, nicht bool!
        actuator_state = mock.get_actuator_state(gpio=25)
        assert actuator_state.state == True
        assert actuator_state.emergency_stopped == False

        # Execution History prüfen
        history = await logic_setup["repo"].get_execution_history(
            rule_id=rule.id,
            limit=1
        )
        assert len(history) == 1
        assert history[0].success == True
```

---

## 7. DETAILLIERTE TEST-SZENARIEN

### 7.1 pH Sensor Tests (`test_ph_sensor_logic.py`)

```python
"""
Test-Modul: pH Sensor Logic Integration

Hardware-Kontext:
- Haoshi H-101 Industrial pH Electrode
- Interface Board: PH-4502C
- GPIO34 (ADC1_CH6) - SICHER mit WiFi
- 2-Punkt-Kalibrierung erforderlich (pH 4.0, pH 7.0)
- Drift: ≤0.02 pH/24h (kalibriert)
"""

class TestPHSensorLogic:
    """pH Sensor + Logic Engine Integration Tests."""

    @pytest.mark.asyncio
    async def test_ph_low_triggers_dosing_pump(self, logic_setup, mock_esp32_ph):
        """
        SZENARIO: pH zu niedrig → Dosing Pump aktivieren
        
        HARDWARE-KONTEXT:
        - pH Sensor auf GPIO34 (ADC1)
        - Dosing Pump (Base) auf GPIO16 (Relay)
        - Hydroponik: Ziel-pH = 6.0-6.5
        
        GIVEN: pH Sensor auf ESP_A, Dosing Pump auf ESP_B
        WHEN: pH sinkt unter 5.5
        THEN: Dosing Pump für Base-Lösung aktivieren
        
        LOGIC RULE:
        - Condition: ph_value < 5.5
        - Action: actuator_command(ESP_B, gpio=16, command="ON")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ph_extreme_triggers_emergency_stop(self, logic_setup, mock_esp32_ph):
        """
        SZENARIO: Extremer pH-Wert → Emergency Stop
        
        HARDWARE-KONTEXT:
        - pH <0 oder >14 = Sensor defekt/getrennt
        - ADC ~0 oder ~4095 = Kabelbruch oder Kurzschluss
        
        GIVEN: pH Sensor auf ESP_A
        WHEN: pH meldet -0.5 (ADC ~0, Sensor-Fault)
        THEN: Emergency Stop für Irrigation + Alert
        
        LOGIC RULE:
        - Condition: ph_value < 0 OR ph_value > 14
        - Action: emergency_stop(esp_id="ESP_IRRIGATION")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ph_drift_triggers_calibration_alert(self, logic_setup, mock_esp32_ph):
        """
        SZENARIO: pH driftet über 24h → Kalibrierungs-Alert
        
        HARDWARE-KONTEXT:
        - pH Elektroden driften natürlich (±0.5 pH/Tag)
        - Drift >0.5 pH = Rekalibrierung nötig
        
        GIVEN: pH Sensor, stabile Bedingungen
        WHEN: pH driftet von 6.5 auf 7.2 in 24h (>0.5)
        THEN: Notification "pH Calibration Required"
        
        LOGIC RULE:
        - Condition: ph_drift_24h > 0.5
        - Action: notification("pH calibration required")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ph_stabilization_time(self, logic_setup, mock_esp32_ph):
        """
        SZENARIO: pH Stabilisierungszeit berücksichtigen
        
        HARDWARE-KONTEXT:
        - pH Elektrode braucht ~10 Sekunden zum Stabilisieren
        - Erste Readings nach Eintauchen sind unzuverlässig
        
        GIVEN: pH Sensor gerade eingetaucht
        WHEN: Readings in ersten 10 Sekunden
        THEN: Logic Rule ignoriert diese Readings
        """
        pass  # Implementierung
```

### 7.2 DS18B20 Tests (`test_ds18b20_cross_esp_logic.py`)

```python
"""
Test-Modul: DS18B20 Multi-Sensor Cross-ESP Logic

Hardware-Kontext:
- DS18B20 OneWire Digital Sensoren
- GPIO4 für OneWire-Bus
- Mehrere Sensoren auf einem Bus (unique ROM)
- RAW-Wert = Temperatur * 16 (12-bit Auflösung)
- Special Values: -127°C (Fault), +85°C (Power-On-Reset)
"""

class TestDS18B20CrossESPLogic:
    """DS18B20 Multi-Sensor + Cross-ESP Logic Tests."""

    @pytest.mark.asyncio
    async def test_multi_zone_temperature_averaging(self, logic_setup):
        """
        SZENARIO: Durchschnittstemperatur aus 3 Sensoren
        
        HARDWARE-KONTEXT:
        - 3 DS18B20 auf einem OneWire-Bus (GPIO4)
        - Jeder hat einzigartige 64-bit ROM-Adresse
        - Durchschnitt reduziert Einzelsensor-Fehler
        
        GIVEN: 3 DS18B20 auf ESP_A
               Sensor_1: 22.5°C, Sensor_2: 23.0°C, Sensor_3: 22.8°C
        WHEN: Average = 22.77°C > 22.5°C Threshold
        THEN: Ventilation auf ESP_B aktivieren
        
        LOGIC RULE:
        - Condition: avg(temp_1, temp_2, temp_3) > 22.5
        - Action: actuator_command(ESP_B, gpio=25, command="ON")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ds18b20_power_on_reset_ignored(self, logic_setup):
        """
        SZENARIO: Power-On-Reset Value ignorieren
        
        HARDWARE-KONTEXT:
        - DS18B20 meldet +85°C (RAW 1360) nach Power-On
        - Das ist KEINE echte Temperatur!
        - Muss erkannt und ignoriert werden
        
        GIVEN: DS18B20 gerade eingeschaltet
        WHEN: Sensor meldet 85.0°C (RAW 1360)
        THEN: Logic Rule ignoriert, wartet auf nächsten Wert
        
        LOGIC RULE:
        - Condition: temp == 85.0 AND first_reading_after_boot
        - Action: skip_execution, log_warning
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ds18b20_sensor_fault_failover(self, logic_setup):
        """
        SZENARIO: Primärsensor fällt aus → Backup übernimmt
        
        HARDWARE-KONTEXT:
        - DS18B20 meldet -127°C (RAW -2032) bei Fault
        - CRC-Fehler, getrennt, oder beschädigt
        
        GIVEN: 2 DS18B20 (Primary + Backup) auf ESP_A
        WHEN: Primary meldet -127°C (Sensor-Fault)
        THEN: Logic schaltet auf Backup-Sensor
        
        LOGIC RULE:
        - Condition: primary_temp == -127 OR primary_crc_error
        - Action: switch_to_backup_sensor, alert_maintenance
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_ds18b20_gradient_detection(self, logic_setup):
        """
        SZENARIO: Temperatur-Gradient (schnelle Änderung) erkennen
        
        HARDWARE-KONTEXT:
        - Schnelle Temperaturänderung kann auf Problem hindeuten
        - >5°C/Minute = abnormal
        
        GIVEN: DS18B20 meldet normale Temperaturen
        WHEN: Temperatur springt von 22°C auf 30°C in 1 Minute
        THEN: Alert "Abnormal temperature gradient"
        """
        pass  # Implementierung
```

### 7.3 SHT31 Tests (`test_sht31_i2c_logic.py`)

```python
"""
Test-Modul: SHT31 I2C Multi-Sensor Logic

Hardware-Kontext:
- SHT31 I2C Sensoren (Temp + Humidity)
- I2C Adressen: 0x44 (ADR=LOW), 0x45 (ADR=HIGH)
- Max 2 pro I2C-Bus ohne Multiplexer
- Built-in Heater für Kondensation
"""

class TestSHT31I2CLogic:
    """SHT31 I2C Adressierung + Logic Tests."""

    @pytest.mark.asyncio
    async def test_dual_sht31_zone_comparison(self, logic_setup):
        """
        SZENARIO: Vergleich zwischen zwei Zonen
        
        HARDWARE-KONTEXT:
        - SHT31_A at 0x44 (ADR LOW)
        - SHT31_B at 0x45 (ADR HIGH)
        - Beide auf I2C-Bus (GPIO21/22)
        
        GIVEN: SHT31_A (Zone A): 75% RH
               SHT31_B (Zone B): 55% RH
        WHEN: Zone A humidity > Zone B + 15%
        THEN: Ventilation in Zone A aktivieren
        
        LOGIC RULE:
        - Condition: humidity_A > humidity_B + 15
        - Action: actuator_command(ESP_A, gpio=26, command="ON")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_sht31_heater_activation_on_condensation(self, logic_setup):
        """
        SZENARIO: Kondensation → Heater aktivieren
        
        HARDWARE-KONTEXT:
        - SHT31 hat eingebauten Heater
        - Heater entfernt Kondensation von Sensor
        - Aktivieren via I2C-Kommando
        
        GIVEN: SHT31 meldet 98% RH
        WHEN: Humidity >95% für >5 Minuten
        THEN: SHT31 Heater für 30 Sekunden aktivieren
        
        LOGIC RULE:
        - Condition: humidity > 95 AND duration > 300s
        - Action: sht31_heater_command(address=0x44, duration=30)
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_sht31_dew_point_calculation(self, logic_setup):
        """
        SZENARIO: Taupunkt-Berechnung für Kondensations-Warnung
        
        HARDWARE-KONTEXT:
        - Taupunkt = f(Temperatur, Luftfeuchtigkeit)
        - Wenn Oberflächentemp < Taupunkt → Kondensation
        
        GIVEN: SHT31 meldet 22°C, 80% RH
        WHEN: Berechneter Taupunkt = 18.4°C
               UND Pflanzenoberfläche < 18.4°C
        THEN: Warning "Condensation risk"
        """
        pass  # Implementierung
```

### 7.4 Relay Tests (`test_relay_logic_chains.py`)

```python
"""
Test-Modul: Relay Logic Chains + Safety

Hardware-Kontext:
- Relay-Module (Active-LOW typisch)
- GPIO16, GPIO17 = sichere Pins (keine Boot-Konflikte)
- Interlock-Logik für Pump/Valve
"""

class TestRelayLogicChains:
    """Relay Interlock + Safety Tests."""

    @pytest.mark.asyncio
    async def test_pump_valve_interlock_sequence(self, logic_setup):
        """
        SZENARIO: Pumpe darf erst nach Ventil starten
        
        HARDWARE-KONTEXT:
        - Pump Relay auf ESP_A GPIO16
        - Valve Relay auf ESP_B GPIO17
        - Active-LOW Relays (HIGH=OFF, LOW=ON)
        
        GIVEN: Irrigation scheduled
        WHEN: Logic versucht Pumpe zu starten
        THEN: Ventil öffnet zuerst, 2s warten, dann Pumpe
        
        LOGIC RULE:
        - Condition: irrigation_schedule_active
        - Action sequence:
          1. actuator_command(ESP_B, gpio=17, "ON")  # Valve
          2. delay(2000ms)
          3. actuator_command(ESP_A, gpio=16, "ON")  # Pump
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_pump_stops_when_valve_closes(self, logic_setup):
        """
        SZENARIO: Pumpe muss sofort stoppen wenn Ventil schließt
        
        HARDWARE-KONTEXT:
        - Pumpe gegen geschlossenes Ventil = Druckaufbau
        - Kann Schläuche/Verbindungen beschädigen
        
        GIVEN: Pumpe und Ventil laufen
        WHEN: Ventil schließt (manuell oder Fehler)
        THEN: Pumpe stoppt sofort
        
        LOGIC RULE:
        - Condition: valve_state == "OFF" AND pump_state == "ON"
        - Action: actuator_command(ESP_A, gpio=16, "OFF")
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_relay_boot_glitch_protection(self, logic_setup):
        """
        SZENARIO: Relay auf sicherem Pin glitcht nicht beim Boot
        
        HARDWARE-KONTEXT:
        - Strapping Pins (GPIO0,2,12,15) toggled beim Boot
        - Kann "Machine-Gun" Relay-Klicken verursachen
        - GPIO16, GPIO17 haben dieses Problem nicht
        
        GIVEN: Relay auf GPIO16 (safe pin)
        WHEN: ESP32 bootet
        THEN: Relay bleibt in letztem bekannten Zustand
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_emergency_stop_all_relays(self, logic_setup):
        """
        SZENARIO: Emergency Stop schaltet alle Relays ab
        
        HARDWARE-KONTEXT:
        - Emergency Stop = alle Aktoren AUS
        - Muss unabhängig von Logic Rules funktionieren
        
        GIVEN: Mehrere Relays aktiv
        WHEN: Emergency Stop ausgelöst
        THEN: Alle Relays sofort AUS
        """
        pass  # Implementierung
```

### 7.5 PWM Tests (`test_pwm_logic.py`)

```python
"""
Test-Modul: PWM/Servo Proportional Control

Hardware-Kontext:
- ESP32 LEDC für PWM
- GPIO25, GPIO26, GPIO27 empfohlen
- Fans: 1-25kHz, 8-bit Resolution
- Servos: 50Hz, 1-2ms Pulse
"""

class TestPWMLogic:
    """PWM/Servo Proportional Control Tests."""

    @pytest.mark.asyncio
    async def test_fan_speed_proportional_to_temperature(self, logic_setup):
        """
        SZENARIO: Fan-Geschwindigkeit steigt mit Temperatur
        
        HARDWARE-KONTEXT:
        - PWM Fan auf GPIO25
        - Frequenz: 25kHz
        - Duty Cycle: 0-255 (8-bit)
        
        GIVEN: Temperatur steigt von 24°C auf 30°C
        WHEN: Temperatur kreuzt Thresholds
        THEN: Fan-Geschwindigkeit steigt stufenweise
        
        LOGIC RULES:
        - 24-26°C: 30% PWM (duty=77)
        - 26-28°C: 60% PWM (duty=153)
        - 28-30°C: 100% PWM (duty=255)
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_servo_valve_proportional_opening(self, logic_setup):
        """
        SZENARIO: Servo-Ventil öffnet proportional
        
        HARDWARE-KONTEXT:
        - Servo auf GPIO26
        - 50Hz PWM (20ms Periode)
        - Pulsbreite: 1ms (0°) bis 2ms (180°)
        
        GIVEN: Flow demand = 50%
        WHEN: Logic berechnet Ventilposition
        THEN: Servo bewegt auf 90° (1.5ms pulse)
        
        LOGIC RULE:
        - Condition: flow_demand_percent
        - Action: servo_position(gpio=26, angle=demand*1.8)
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_pwm_ramp_up_gradual(self, logic_setup):
        """
        SZENARIO: PWM Rampe (nicht sprunghaft)
        
        HARDWARE-KONTEXT:
        - Plötzliche PWM-Änderung kann Motoren beschädigen
        - Sanftes Hochfahren über 2-3 Sekunden
        
        GIVEN: Fan bei 0%
        WHEN: Target = 100%
        THEN: Rampe über 3 Sekunden (nicht sofort 100%)
        """
        pass  # Implementierung
```

### 7.6 E2E Tests (`test_logic_engine_real_server.py`)

```python
"""
Test-Modul: Logic Engine E2E mit echtem Server

ACHTUNG: Diese Tests benötigen einen laufenden Server!
Markiert mit @pytest.mark.e2e und @pytest.mark.requires_server
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.requires_server]


class TestLogicEngineE2E:
    """End-to-End Tests mit echtem Server."""

    @pytest.mark.asyncio
    async def test_cross_esp_rule_execution_latency(self):
        """
        E2E: Messe echte Logic-Execution-Zeit
        
        GIVEN: Server läuft, 2 ESP32 verbunden
        WHEN: Temp-Sensor auf ESP_A überschreitet Threshold
        THEN: Fan auf ESP_B aktiviert innerhalb 5 Sekunden
        
        MEASURES:
        - MQTT Publish Latenz
        - Logic Engine Evaluation Zeit
        - Cross-ESP Command Propagation
        - Total End-to-End Latenz
        
        ACCEPTANCE: <5 Sekunden total
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_logic_rule_survives_server_restart(self):
        """
        E2E: Logic Rules persistieren über Server-Restart
        
        GIVEN: Logic Rule erstellt und aktiv
        WHEN: Server startet neu
        THEN: Rule noch aktiv, führt korrekt aus
        
        VERIFIES:
        - Database Persistence
        - Rule Re-Loading bei Startup
        - Execution History Kontinuität
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_safety_service_blocks_unsafe_logic(self):
        """
        E2E: SafetyService validiert Logic-Actions
        
        GIVEN: Logic Rule versucht unsafe Action
               (z.B. Pump ON ohne Pressure Sensor OK)
        WHEN: Rule triggered
        THEN: SafetyService blockt, loggt Rejection
        
        VERIFIES:
        - Logic Engine → SafetyService Integration
        - Rejection in LogicExecutionHistory
        - WebSocket Alert Broadcast
        """
        pass  # Implementierung

    @pytest.mark.asyncio
    async def test_concurrent_rules_do_not_conflict(self):
        """
        E2E: Gleichzeitige Rules verursachen keine Konflikte
        
        GIVEN: 2 Rules mit gleichem Target-Actuator
        WHEN: Beide Rules gleichzeitig triggern
        THEN: Höhere Priority gewinnt, keine Race Condition
        """
        pass  # Implementierung
```

---

## 8. MOCKESPCLIENT ERWEITERUNGEN [KORRIGIERT]

Du musst den MockESP32Client erweitern um die neuen Hardware-Typen zu unterstützen.

### 8.1 Bereits existierende Methoden (NICHT implementieren!) [NEU]

Diese Methoden existieren bereits in `mock_esp32_client.py` und können direkt verwendet werden:

| Methode | Zeile | Beschreibung |
|---------|-------|--------------|
| `set_sensor_value()` | 1511 | Einzelsensor setzen (vollständige Signatur) |
| `set_multi_value_sensor()` | 1565 | Multi-Value-Sensor (z.B. SHT31) |
| `configure_actuator()` | 1595 | Actuator konfigurieren |
| `get_actuator_state()` | 1503 | ActuatorState abrufen |
| `get_sensor_state()` | 1507 | SensorState abrufen |
| `simulate_wifi_rssi_change()` | 1657 | RSSI-Änderung simulieren |
| `simulate_heap_change()` | 1661 | Heap-Änderung simulieren |
| `enter_safe_mode()` | 442 | SAFE_MODE aktivieren |
| `exit_safe_mode()` | 454 | SAFE_MODE verlassen |

**WICHTIG für SHT31:** Verwende `set_multi_value_sensor()` - es existiert bereits!

```python
# EXISTIERT BEREITS (mock_esp32_client.py:1565-1593)
mock.set_multi_value_sensor(
    gpio=21,
    sensor_type="SHT31",
    primary_value=23.5,       # Temperature
    secondary_values={"humidity": 65.2},
    name="SHT31 Temp/Humidity",
    quality="good"
)
```

### 8.2 Neue Methoden (IMPLEMENTIEREN!)

Diese Methoden existieren NICHT und müssen neu implementiert werden:

```python
# In tests/esp32/mocks/mock_esp32_client.py
# ALLE diese Methoden sind NEU zu implementieren!

def add_ph_sensor(
    self,
    gpio: int,
    initial_ph: float = 7.0,
    calibrated: bool = False,
    drift_rate: float = 0.0  # pH/hour
):
    """
    Add pH sensor with calibration state.

    HARDWARE-KONTEXT:
    - pH Elektrode + Interface Board (PH-4502C)
    - ADC1 Pins erforderlich (32-39) wegen WiFi!
    - Wert 0-14 pH, Genauigkeit ±0.05

    Args:
        gpio: ADC1 pin (32-39 empfohlen)
        initial_ph: Starting pH value
        calibrated: Whether sensor is calibrated
        drift_rate: Simulated drift per hour

    Implementation Notes:
    - Speichere calibration state in self._sensor_states
    - Berechne drift über Zeit wenn drift_rate > 0
    - Return Error-Wert (pH < 0 oder > 14) bei defektem Sensor
    """
    pass

def add_ds18b20_multi(
    self,
    gpio: int,
    count: int = 3,
    initial_temps: list[float] = None,
    rom_addresses: list[str] = None
):
    """
    Add multiple DS18B20 on same OneWire bus.

    HARDWARE-KONTEXT:
    - OneWire-Bus: Mehrere Sensoren auf einem GPIO
    - Jeder Sensor hat einzigartige 64-bit ROM-Adresse
    - Spezielle Werte: -127°C (Fault), +85°C (Power-On-Reset)

    Args:
        gpio: OneWire data pin (4, 16, 17 empfohlen)
        count: Number of sensors
        initial_temps: Starting temperatures for each
        rom_addresses: Unique 64-bit ROM addresses

    Implementation Notes:
    - Generiere ROM-Adressen wenn nicht angegeben (z.B. "28-000000000001")
    - Speichere jeden Sensor separat in self._sensor_states
    - Ermögliche individuelles Setzen via ROM-Adresse
    """
    pass

def set_relay_state(
    self,
    gpio: int,
    state: bool,
    trigger_type: str = "active_low"
):
    """
    Set relay state accounting for trigger type.

    HARDWARE-KONTEXT:
    - Active-LOW Relays (häufig): LOW=ON, HIGH=OFF
    - Active-HIGH Relays: HIGH=ON, LOW=OFF
    - GPIO-Level ≠ Relay-State bei Active-LOW!

    Args:
        gpio: Relay control pin
        state: Desired relay state (True=ON, False=OFF)
        trigger_type: "active_low" or "active_high"

    Implementation Notes:
    - Konvertiere state zu GPIO-Level basierend auf trigger_type
    - Speichere sowohl relay_state als auch gpio_level
    """
    pass

def set_pwm_duty(
    self,
    gpio: int,
    duty_cycle: int,
    frequency: int = 25000
):
    """
    Set PWM duty cycle.

    HARDWARE-KONTEXT:
    - ESP32 LEDC: 16 Kanäle, bis 40MHz
    - Fans: 1-25kHz, 8-bit (0-255)
    - Servos: 50Hz, Pulse 1-2ms

    Args:
        gpio: PWM pin
        duty_cycle: 0-255 (8-bit)
        frequency: Hz (default 25kHz for fans)

    Implementation Notes:
    - Speichere duty_cycle UND frequency
    - Berechne Prozent: duty_cycle / 255 * 100
    """
    pass

def simulate_boot_sequence(self):
    """
    Simulate ESP32 boot with strapping pin behavior.

    HARDWARE-KONTEXT:
    - Strapping Pins (GPIO0,2,12,15) können beim Boot toggled werden
    - Safe Pins (GPIO16,17) bleiben stabil
    - Relays auf Strapping Pins "rattern" beim Boot

    Implementation Notes:
    - Setze SystemState auf BOOT
    - Toggle Strapping Pins kurzzeitig
    - Prüfe Relay-States auf Safe Pins (sollten unverändert sein)
    - Transition zu WIFI_SETUP → OPERATIONAL
    """
    pass

def simulate_sensor_fault(self, gpio: int, fault_type: str):
    """
    Simulate sensor fault conditions.

    HARDWARE-KONTEXT:
    - DS18B20 Fault: -127°C (-2032 RAW), +85°C bei Power-On
    - pH Fault: ADC=0 oder ADC=4095 (Kurzschluss/Kabelbruch)
    - SHT31 Fault: I2C NACK, ungültige Checksumme

    Args:
        gpio: Sensor pin
        fault_type:
            - "disconnect" → -127°C for DS18B20, ADC=4095 for pH
            - "power_on_reset" → +85°C for DS18B20
            - "crc_error" → Invalid checksum
            - "i2c_nack" → I2C device not responding

    Implementation Notes:
    - Setze sensor quality auf "bad" oder "stale"
    - Setze entsprechenden Error-Wert
    - Trigger ggf. Error-Logging
    """
    pass
```

### 8.3 Implementierungs-Checkliste [NEU]

| Methode | Existiert? | Aktion |
|---------|------------|--------|
| `set_sensor_value()` | ✅ JA | Nutzen |
| `set_multi_value_sensor()` | ✅ JA | Nutzen für SHT31 |
| `configure_actuator()` | ✅ JA | Nutzen |
| `add_ph_sensor()` | ❌ NEIN | **IMPLEMENTIEREN** |
| `add_ds18b20_multi()` | ❌ NEIN | **IMPLEMENTIEREN** |
| `set_relay_state()` | ❌ NEIN | **IMPLEMENTIEREN** |
| `set_pwm_duty()` | ❌ NEIN | **IMPLEMENTIEREN** |
| `simulate_boot_sequence()` | ❌ NEIN | **IMPLEMENTIEREN** |
| `simulate_sensor_fault()` | ❌ NEIN | **IMPLEMENTIEREN** |

---

## 9. QUALITY CRITERIA

### 9.1 Hardware-Realismus

- ✅ Korrekte GPIO-Pins (ADC1 für Analog, Safe Pins für Relays)
- ✅ Korrekte I2C-Adressen (0x44/0x45 für SHT31)
- ✅ Realistische Sensor-Werte (RAW für DS18B20, Voltage für pH)
- ✅ Fehler-Szenarien aus echten Hardware-Problemen

### 9.2 Logic Engine Integration

- ✅ Jeder Test erstellt echte LogicRule via LogicService
- ✅ Execution wird in LogicExecutionHistory verifiziert
- ✅ Sowohl Success als auch Failure Paths getestet

### 9.3 Safety Validation

- ✅ Tests wo SafetyService Actions blockt
- ✅ Rejection-Logging verifiziert
- ✅ Emergency Stop Propagation getestet

### 9.4 Cross-ESP Coordination

- ✅ Sensor auf ESP_A triggert Actuator auf ESP_B
- ✅ MQTT Message Routing verifiziert
- ✅ Cascade Failures getestet (ESP_A offline → ESP_B verhält sich korrekt)

### 9.5 Dokumentation

- ✅ HARDWARE CONTEXT in jedem Docstring
- ✅ Erklärt WARUM dieses Szenario für Greenhouse wichtig ist
- ✅ Erwartete Latenzen für E2E Tests dokumentiert

---

## 10. DELIVERABLES CHECKLIST

### 10.1 Neue Test-Dateien

- [ ] `tests/integration/test_ph_sensor_logic.py` (~10 Tests)
- [ ] `tests/integration/test_ds18b20_cross_esp_logic.py` (~12 Tests)
- [ ] `tests/integration/test_sht31_i2c_logic.py` (~8 Tests)
- [ ] `tests/integration/test_relay_logic_chains.py` (~10 Tests)
- [ ] `tests/integration/test_pwm_logic.py` (~6 Tests)
- [ ] `tests/e2e/test_logic_engine_real_server.py` (~8 Tests)

### 10.2 MockESP32Client Erweiterungen [KORRIGIERT]

**Bereits verfügbar (keine Implementierung nötig):**
- [x] `set_multi_value_sensor()` - für SHT31 (existiert: Zeile 1565)
- [x] `set_sensor_value()` - für Einzelsensoren (existiert: Zeile 1511)
- [x] `configure_actuator()` - für alle Aktoren (existiert: Zeile 1595)

**Neue Methoden (IMPLEMENTIEREN!):**
- [ ] `add_ph_sensor()` Methode - pH mit Kalibrierung & Drift
- [ ] `add_ds18b20_multi()` Methode - Multi-Sensor OneWire Bus
- [ ] `set_relay_state()` mit trigger_type (active_low/active_high)
- [ ] `set_pwm_duty()` Methode - PWM mit Frequenz
- [ ] `simulate_boot_sequence()` Methode - Strapping Pin Verhalten
- [ ] `simulate_sensor_fault()` Methode - Fault-Szenarien

**HINWEIS:** `add_sht31()` ist NICHT nötig! Verwende stattdessen `set_multi_value_sensor()`.

### 10.3 Dokumentation

- [ ] Jeder Test hat HARDWARE CONTEXT Docstring
- [ ] GIVEN/WHEN/THEN Format in jedem Test
- [ ] LOGIC RULE Beschreibung in jedem Test

---

## 11. EXECUTION PLAN

### Phase 1: MockESP32Client Erweiterungen (Tag 1)

1. pH-Sensor Methode implementieren
2. Multi-DS18B20 Methode implementieren
3. SHT31 mit I2C-Adressierung implementieren
4. Relay trigger_type Support
5. PWM duty cycle control
6. Boot-Sequence Simulation

### Phase 2: Integration Tests (Tag 2-4)

1. pH Sensor Tests (Tag 2)
2. DS18B20 Tests (Tag 2)
3. SHT31 Tests (Tag 3)
4. Relay Tests (Tag 3)
5. PWM Tests (Tag 4)

### Phase 3: E2E Tests (Tag 5)

1. Setup E2E Test Infrastructure
2. Latency Tests
3. Persistence Tests
4. Safety Integration Tests

### Phase 4: Review & Dokumentation (Tag 6)

1. Code Review vorbereiten
2. Test-Dokumentation finalisieren
3. Coverage Report erstellen

---

## 12. REFERENZEN

### Code-Locations

| Komponente | Pfad |
|------------|------|
| MockESP32Client | `tests/esp32/mocks/mock_esp32_client.py` |
| Test Fixtures | `tests/esp32/conftest.py` |
| Logic Engine | `src/services/logic_engine.py` |
| Logic Service | `src/services/logic_service.py` |
| Logic Models | `src/db/models/logic.py` |
| Logic Repository | `src/db/repositories/logic_repo.py` |
| Actuator Service | `src/services/actuator_service.py` |
| Safety Service | `src/services/safety_service.py` |

### Dokumentation

| Dokument | Pfad |
|----------|------|
| Server-Doku | `.claude/CLAUDE_SERVER.md` |
| ESP32-Doku | `.claude/CLAUDE.md` |
| Test-Workflow | `.claude/TEST_WORKFLOW.md` |
| System-Hierarchie | `.claude/Hierarchie.md` |

---

**Ende des Developer Briefings**

**Erstellt:** 2026-01-30  
**Autor:** Robin (Product Owner / System Architect)  
**Für:** Test-Suite-Entwickler mit Greenhouse-Domain-Expertise