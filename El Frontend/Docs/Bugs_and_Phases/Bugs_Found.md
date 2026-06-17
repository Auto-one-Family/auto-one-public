# Bugs Found

> **Letzte Aktualisierung:** 2026-01-05
> **Status:** 🟡 2 NON-CRITICAL BUGS (Bug R - Windows Console, Bug S - Test Cleanup)

---

## Zusammenfassung

| Kategorie | Status |
|-----------|--------|
| **Windows Console Unicode** | 🟡 OPEN (Bug R - Windows CP1252 encoding, non-critical) |
| **Test asyncio Task Cleanup** | 🟡 OPEN (Bug S - SequenceActionExecutor cleanup, non-critical) |
| **Wokwi Zero Serial Output** | ✅ FIXED (Bug Q - Serial Monitor + Timing, Workflow verifiziert) |
| **Wokwi GPIO 0 Boot-Loop** | ✅ FIXED (Bug P - committed, Workaround aktiv) |
| **AsyncIO Event-Loop Bug** | ✅ FIXED (Bug O - committed, pending 48h verification) |
| Deprecation Warnings | 🟡 Non-Critical |
| Sicherheitshinweise | 🔵 Dev Only |

---

## Aktive Bugs (Non-Critical)

### Bug R: Windows Console UnicodeEncodeError

**Status:** 🟡 OPEN (Non-Critical, nur Windows)

**Entdeckt:** 2026-01-05 (Server-Startup-Logs)

**Symptom:** Server startet und funktioniert, aber in der Windows-Konsole erscheinen `UnicodeEncodeError`-Meldungen:
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2192' in position 123
UnicodeEncodeError: 'charmap' codec can't encode characters in position 93-94
```

**Root Cause:**
- Windows-Terminal verwendet standardmäßig CP1252-Encoding
- Server-Logs enthalten Unicode-Zeichen: `→` (\u2192), `⚠️` (\u26a0\ufe0f)
- Diese Zeichen können von CP1252 nicht dargestellt werden
- **Nur betrifft Console-Output**, nicht die JSON-Log-Datei

**Betroffene Dateien:**
- `src/core/resilience/circuit_breaker.py:338` - Verwendet `→` in Log-Nachricht
- `src/services/maintenance/jobs/cleanup.py:468` - Verwendet `⚠️` in Warning

**Workarounds:**
1. **Terminal auf UTF-8 setzen:** `chcp 65001` vor Server-Start
2. **PowerShell:** `$OutputEncoding = [System.Text.Encoding]::UTF8`
3. **Log-Datei lesen statt Console:** `god_kaiser.log` ist JSON-formatiert und UTF-8

**Mögliche Fixes:**
```python
# Option 1: Unicode-Zeichen durch ASCII ersetzen
"closed → closed"  # →  "closed -> closed"
"⚠️ Orphaned"       # →  "[WARN] Orphaned"

# Option 2: Console-Handler mit UTF-8 forcieren (logging_config.py)
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

**Priorität:** Low - Logs funktionieren korrekt, nur Console-Anzeige betroffen

---

### Bug S: asyncio Task-Warnings bei Test-Cleanup

**Status:** 🟡 OPEN (Non-Critical, nur Tests)

**Entdeckt:** 2026-01-05 (pytest-Ausführung)

**Symptom:** Nach pytest-Durchlauf erscheinen mehrere Warnings:
```
ERROR - Task was destroyed but it is pending!
task: <Task pending name='Task-8877' coro=<SequenceActionExecutor._cleanup_loop() running at .../sequence_executor.py:864>>
```

**Root Cause:**
- `SequenceActionExecutor` startet Background-Tasks (`_cleanup_loop`)
- Diese Tasks werden bei Test-Teardown nicht sauber beendet
- asyncio meldet "destroyed but pending" für nicht-abgeschlossene Tasks
- **Nur bei Tests**, nicht in Production

**Betroffene Datei:**
- `src/services/logic/actions/sequence_executor.py:864` - `_cleanup_loop()` Coroutine

**Impact:**
- Tests laufen erfolgreich durch (908 passed)
- Warnings sind nur informativ, kein funktionaler Bug
- In Production läuft der Cleanup-Loop kontinuierlich

**Möglicher Fix:**
```python
# In conftest.py - explizites Cleanup nach jedem Test
@pytest.fixture(autouse=True)
async def cleanup_tasks():
    yield
    # Cancel all pending tasks
    for task in asyncio.all_tasks():
        if '_cleanup_loop' in str(task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
```

**Priorität:** Low - Nur kosmetisch, Tests funktionieren

---

## Verbleibende Tasks (Nicht-kritisch)

### 1. Pydantic `class Config` zu `ConfigDict` migrieren

**Status:** 🟡 Non-Critical (wird in Pydantic v3 entfernt)
**Dateien:**
- `El Servador/god_kaiser_server/src/api/schemas.py:15, 98, 156, 204, 277`
- `El Servador/god_kaiser_server/src/api/v1/audit.py:37`

```python
# Von:
class MyModel(BaseModel):
    class Config:
        from_attributes = True

# Nach:
from pydantic import ConfigDict

class MyModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

---

### 2. `datetime.utcnow()` zu `datetime.now(UTC)` migrieren

**Status:** 🟡 Non-Critical (deprecated in Python 3.12+)
**Dateien:**
- `src/db/repositories/actuator_repo.py:212`
- `src/db/repositories/sensor_repo.py:214`
- `src/db/repositories/system_config_repo.py:200`
- `tests/unit/test_repositories_actuator.py:115`
- `tests/unit/test_repositories_sensor.py:230, 260`

```python
# Von:
from datetime import datetime
timestamp = datetime.utcnow()

# Nach:
from datetime import datetime, UTC
timestamp = datetime.now(UTC)
```

---

### 3. Coverage-Konfiguration

**Status:** 🔵 Low Priority

```bash
poetry run pytest tests/ --cov=src --cov-report=term-missing
```

---

## Sicherheitshinweise (Development Only)

**Status:** ℹ️ INFO (nur Development)

### A) Default JWT Secret Key
```
SECURITY: Using default JWT secret key (OK for development only).
```
**Aktion für Production:** `.env` mit `JWT_SECRET_KEY=<secure-random-key>` erstellen

### B) MQTT TLS deaktiviert
```
MQTT TLS is disabled.
```
**Aktion für Production:** `MQTT_USE_TLS=true` in `.env` setzen

---

## Übersprungene Tests (6 Tests)

**Status:** ℹ️ INFO (erwartet)

| Test | Grund |
|------|-------|
| `test_communication.py` (4x) | Real ESP32 / `ESP32_TEST_DEVICE_ID` not set |
| `test_mqtt_auth_service.py` (2x) | Unix permissions not supported on Windows |

---

## Abgeschlossene Bugs (Archiv)

Alle kritischen Bugs wurden behoben. Siehe Git-History für Details:

### Server/Backend Bugs (2025-12)
- ✅ Bug I: Circular Import (2025-12-27)
- ✅ Bug J: Test Import Bugs (2025-12-27)
- ✅ Bug K: Test Implementation Bugs (2025-12-27)
- ✅ Bug G: Database Schema (2025-12-27)
- ✅ Bug H: Alembic Multiple Heads (2025-12-27)
- ✅ Bug E: Graceful Shutdown (bereits korrekt)
- ✅ Bug F: MQTT Connection Leak (bereits korrekt)
- ✅ Bug D: MQTT Reconnect (2025-12-27)
- ✅ Bug A: Token Blacklist (2025-12-26)
- ✅ Bug B: ThreadPoolExecutor (2025-12-26)
- ✅ Bug C: MQTT Log-Spam (2025-12-26)
- ✅ Bug L: Maintenance Import (verifiziert 2025-12-30)
- ✅ Bug M: SimulationSchedulerDep (verifiziert 2025-12-30)
- ✅ Zone-ACK WebSocket Bug (2025-12-30)

### Mock ESP Bugs (2025-12-30) - ehemals Bugs_Found_2.md
- ✅ Bug 1: Mock ESP Name nicht persistent (2025-12-30)
- ✅ Bug 2: Freshness-Anzeige nach Name-Update (2025-12-30)
- ✅ Bug 3: Heartbeat nach Server-Neustart (2025-12-30)
- ✅ Bug 4: Freshness-Indikator bei Name-Änderung (2025-12-30)

### Drag & Drop Bugs (2026-01-03) - ehemals Bugs_Found_3.md
- ✅ BUG-001: AnalysisDropZone triggert ESP-Card-Drag
- ✅ BUG-002: ESP-Card nicht sofort draggbar
- ✅ BUG-003: Inkonsistentes Cursor-Styling
- ✅ BUG-004: Sensor-Satellite Timing-Konflikt
- ✅ BUG-005: Native Drag-Events brechen VueDraggable ab (Root Cause)

### Wokwi/CI Bugs (2026-01-05)
- ✅ Bug P: GPIO 0 Boot-Loop (committed, gefixt)
- ✅ Bug Q: Zero Serial Output (committed - Serial Timing + Watchdog Skip)

---

## Behobener Bug: Wokwi GPIO 0 Boot-Loop (Bug P)

**Status:** ✅ COMMITTED (2026-01-05) - Verifizierung blockiert durch Bug Q

**Entdeckt:** 2026-01-05 (Workflow Run 20705170819)

**Symptom:** GPIO 0 Factory Reset Check verursacht potentielle Boot-Loop in Wokwi.

**Root Cause:** Boot-Button Factory Reset Check auf GPIO 0 verursachte **Boot-Loop**.

**Technische Analyse:**
1. In `main.cpp:120-179` wird GPIO 0 (Boot Button) für Factory Reset geprüft
2. GPIO 0 ist in `diagram.json` **nicht angeschlossen** (kein physischer Button)
3. In Wokwi-Simulation kann GPIO 0 floaten oder LOW sein (kein Pull-Up aktiv)
4. Wenn `digitalRead(GPIO 0) == LOW` → 10s warten → `ESP.restart()`
5. **Endlose Boot-Loop** → keine Serial-Ausgabe sichtbar

**Lösung:**
- `#ifndef WOKWI_SIMULATION` Guard um Boot-Button-Check in `main.cpp:126-189`
- In Wokwi wird stattdessen `[WOKWI] Boot button check skipped` geloggt
- Konsistent mit existierendem Pattern in `config_manager.cpp:65-105`

**Geänderte Dateien:**
- `El Trabajante/src/main.cpp` (Zeilen 116-189)

**Verifizierung:**
```bash
# Build erfolgreich:
cd "El Trabajante" && pio run -e wokwi_simulation
# → SUCCESS in 24.16 seconds

# Commit:
git commit -m "fix(wokwi): Skip boot button check in simulation (Bug P)"
# → 3f3a12e (2026-01-05)
```

**Nächster Schritt:** Workflow-Run verifizieren nach Bug Q Fix.

---

## Behobener Bug: Wokwi Zero Serial Output (Bug Q)

**Status:** ✅ FIXED & VERIFIZIERT (2026-01-05, Workflow Run 20706888212)

**Entdeckt:** 2026-01-05 (Workflow Run 20705951050)

**Symptom:** Wokwi ESP32 Simulation startet, läuft 90 Sekunden, aber produziert **ZERO Serial-Ausgabe** - nicht einmal den Boot-Banner.

**Root Cause (FINAL - nach 2 Iterationen):**

1. **HAUPTURSACHE: Fehlende Serial Monitor Verbindung in diagram.json**
   - Die `diagram.json` hatte KEINE Verbindung zwischen ESP32 TX0/RX0 und `$serialMonitor`
   - Ohne diese Verbindungen wird die Serial-Ausgabe nicht zum Wokwi CLI geleitet
   - Dokumentation: https://docs.wokwi.com/guides/serial-monitor

2. **Sekundär: Wokwi Serial Timing**
   - Wokwi's virtuelle UART braucht mehr Zeit zur Initialisierung (500ms statt 100ms)

3. **Sekundär: esp_task_wdt Problem**
   - Die Low-Level ESP-IDF Watchdog-Funktionen werden in Wokwi nicht unterstützt

**Lösung (3 Teile):**

1. **diagram.json: Serial Monitor Verbindung hinzufügen (KRITISCH!)**
   ```json
   "connections": [
     ["esp:TX0", "$serialMonitor:RX", "", []],
     ["esp:RX0", "$serialMonitor:TX", "", []],
     // ... andere Verbindungen
   ]
   ```

2. **main.cpp: Längere Serial-Delay für Wokwi**
   ```cpp
   #ifdef WOKWI_SIMULATION
   delay(500);  // Wokwi needs more time for UART
   Serial.println("[WOKWI] Serial initialized");
   Serial.flush();
   #else
   delay(100);
   #endif
   ```

3. **main.cpp: Watchdog überspringen in Wokwi**
   ```cpp
   #ifndef WOKWI_SIMULATION
   esp_task_wdt_init(30, false);
   esp_task_wdt_add(NULL);
   #endif
   ```

**Geänderte Dateien:**
- `El Trabajante/diagram.json` (Serial Monitor Verbindung)
- `El Trabajante/src/main.cpp` (Zeilen 91-133)

**Verifizierung:**
```bash
# Build:
cd "El Trabajante" && pio run -e wokwi_simulation

# Lokaler Test (benötigt WOKWI_CLI_TOKEN):
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/01-boot/boot_full.yaml
```

**Erfolgskriterium:** ✅ ERFÜLLT - Workflow-Run 20706888212 zeigt:
- Phase 1 OK
- Phase 2 OK
- Phase 3 OK
- Phase 4 OK
- Phase 5 OK

---

## Behobener Bug: Event-Loop-Konflikt (Bug O)

**Status:** ✅ FIXED (2026-01-05) - Verifizierung: Server 48h+ laufen lassen

**Symptom:** Server läuft normal, aber nach längerer Laufzeit erscheint sporadisch:
```
RuntimeError: Queue bound to different event loop
```

**Root Cause:** Python 3.12+ ist strenger bei Event-Loop-Binding:
1. `asyncio.get_event_loop()` ist deprecated und kann falsche/neue Loops zurückgeben
2. MQTT-Handler werden in ThreadPool-Threads ausgeführt, brauchen aber den Main-Loop
3. SQLAlchemy AsyncEngine ist an den Main-Loop gebunden

**Lösung (3 Teile):**

1. **websocket/manager.py:61** - `get_event_loop()` → `get_running_loop()`
   ```python
   self._loop = asyncio.get_running_loop()
   ```

2. **network_helpers.py:45** - `get_event_loop()` → `get_running_loop()`
   ```python
   loop = asyncio.get_running_loop()
   ```

3. **main.py + subscriber.py** - Explizite Loop-Zuweisung beim Startup
   ```python
   # main.py (nach Subscriber-Erstellung)
   _subscriber_instance.set_main_loop(asyncio.get_running_loop())
   ```

**Geänderte Dateien:**
- `El Servador/god_kaiser_server/src/websocket/manager.py`
- `El Servador/god_kaiser_server/src/utils/network_helpers.py`
- `El Servador/god_kaiser_server/src/mqtt/subscriber.py`
- `El Servador/god_kaiser_server/src/main.py`

**Erfolgskriterium:** Server läuft 48+ Stunden ohne Event-Loop-Fehler
