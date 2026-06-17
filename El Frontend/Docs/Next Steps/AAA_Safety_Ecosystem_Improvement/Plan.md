Ich denke das gründlich durch, bevor ich die Phasen aufstelle.

---

## VORÜBERLEGUNG: WiFi-Loss vs MQTT-Loss

| Szenario | WiFi | MQTT | Server-Zugriff | Lokaler Zugriff | ESP kann... |
|----------|------|------|----------------|-----------------|-------------|
| **Normal** | ✅ | ✅ | ✅ | Via lokale IP | Alles |
| **MQTT-Loss** | ✅ | ❌ | ❌ (kein MQTT) | Via lokale IP | Sensoren lesen, lokal puffern, WiFi-Portal erreichbar |
| **WiFi-Loss** | ❌ | ❌ | ❌ | Nur via AP-Mode | Sensoren lesen, lokal puffern, AP-Portal nötig |

**Meine Schlussfolgerung:**

1. **WiFi-Loss und MQTT-Loss sind VERSCHIEDENE Szenarien** – nicht gleich behandeln
2. **MQTT-Loss:** WiFi funktioniert noch → ESP ist über normale IP erreichbar → KEIN AP-Mode nötig
3. **WiFi-Loss:** Nichts geht mehr → AP-Mode MUSS aktiviert werden für User-Zugriff
4. **Gemeinsam:** Beide brauchen lokales Buffering und Actuator-Safe-State

**Das Webportal:**
- Sollte IMMER verfügbar sein (über lokale IP oder AP)
- Muss SCHLANK bleiben (kein Full-Dashboard, nur Diagnostics + Config)
- Zeigt: WiFi-Status, MQTT-Status, Buffered-Messages-Count, Basis-Configs

**Server-Centric Prinzip bleibt:**
- Normal: Server hat 100% Kontrolle
- Disconnected: ESP puffert nur, führt KEINE eigene Logik aus
- Reconnected: ESP sendet Buffer, Server entscheidet was damit passiert

---

# 🔧 PHASENPLAN: SAFETY-PATTERN-VERBESSERUNGEN

---

## PHASE 1: Window Watchdog Implementation

**Ziel:** Diagnostic Coverage von ~70% auf ~95% erhöhen (IEC 61508 SIL 2)

### 1.1 IST-ZUSTAND

**Datei:** `main.cpp:1639-1650`

```cpp
// AKTUELL: Simple Timeout-basierter Feed
if (g_watchdog_config.mode != WatchdogMode::WDT_DISABLED) {
  if (millis() - last_feed_time >= g_watchdog_config.feed_interval_ms) {
    if (feedWatchdog("MAIN_LOOP")) {
      last_feed_time = millis();
    }
  }
}
```

**Problem:** 
- Erkennt nur "zu spät gefüttert" (Timeout)
- Erkennt NICHT "zu früh gefüttert" (Code-Pfad übersprungen, Loop zu schnell)

### 1.2 SOLL-ZUSTAND

**Neues Struct in `watchdog_types.h`:**

```cpp
struct WatchdogConfig {
    WatchdogMode mode;
    unsigned long timeout_ms;
    unsigned long feed_interval_ms;
    unsigned long min_feed_window_ms;  // NEU: Minimum Zeit zwischen Feeds
    bool panic_enabled;
};
```

**Neue Konfiguration:**

| Mode | MIN_WINDOW | MAX_WINDOW (Timeout) | Ratio |
|------|------------|----------------------|-------|
| PRODUCTION | 5.000ms (5s) | 60.000ms (60s) | 1:12 |
| PROVISIONING | 30.000ms (30s) | 300.000ms (5min) | 1:10 |

**Neue Logik in `feedWatchdog()`:**

```
feedWatchdog() aufgerufen
    │
    ├─> Berechne: elapsed = millis() - last_feed_time
    │
    ├─> elapsed < min_feed_window_ms?
    │       │
    │       └─> JA: ERROR_WATCHDOG_FEED_TOO_EARLY (4073)
    │                Log Warning, return false (NICHT füttern!)
    │
    ├─> [Bestehende CB-Checks...]
    │
    └─> esp_task_wdt_reset(), Update Diagnostics, return true
```

**Neuer Error Code in `error_codes.h`:**

```cpp
// Watchdog Errors (4070-4079)
constexpr uint16_t ERROR_WATCHDOG_TIMEOUT = 4070;
constexpr uint16_t ERROR_WATCHDOG_FEED_BLOCKED = 4071;
constexpr uint16_t ERROR_WATCHDOG_FEED_BLOCKED_CRITICAL = 4072;
constexpr uint16_t ERROR_WATCHDOG_FEED_TOO_EARLY = 4073;  // NEU
```

### 1.3 WARUM DAS WICHTIG IST

**Was Window Watchdog erkennt:**

| Fehler | Simple WD | Window WD |
|--------|-----------|-----------|
| Infinite Loop (Code hängt) | ✅ | ✅ |
| Code-Pfad übersprungen | ❌ | ✅ |
| Loop läuft zu schnell (Sensor-Fehler?) | ❌ | ✅ |
| Task starved aber nicht tot | ❌ | ✅ |

### 1.4 BETROFFENE DATEIEN

| Datei | Änderung |
|-------|----------|
| `src/models/watchdog_types.h` | `min_feed_window_ms` zu WatchdogConfig hinzufügen |
| `src/models/error_codes.h` | `ERROR_WATCHDOG_FEED_TOO_EARLY` hinzufügen |
| `src/main.cpp` | feedWatchdog() erweitern, Initialisierung anpassen |
| `src/error_handling/health_monitor.cpp` | Optional: Window-Status in Diagnostics |

### 1.5 QUALITY GATES

- [ ] Feed innerhalb Window → Success
- [ ] Feed zu früh → Error 4073, kein Reset des Hardware-WDT
- [ ] Feed zu spät → Hardware-WDT Timeout (unverändert)
- [ ] Diagnostics enthalten `min_feed_window_ms` und `time_since_last_feed`

---

## PHASE 2: Degraded Mode bei Connectivity-Loss

**Ziel:** System bleibt operabel und erreichbar bei WiFi-Loss oder MQTT-Loss

### 2.1 IST-ZUSTAND

**WiFi CB OPEN (wifi_manager.cpp, main.cpp):**
```
WiFi CB → OPEN
    │
    └─> feedWatchdog() prüft CB-State
            │
            └─> WiFi CB OPEN in PRODUCTION?
                    │
                    └─> JA: return false (Feed blockiert)
                            │
                            └─> Nach 60s: Hardware-WDT Timeout → ESP Reboot
```

**Probleme:**
1. ESP resettet bei WiFi-Ausfall → Daten gehen verloren
2. User hat keinen Zugriff auf ESP bei WiFi-Problemen
3. Kein lokales Webportal für Diagnostics/Config

**MQTT CB OPEN (mqtt_client.cpp):**
- Bereits korrekt: Warning only, Feed wird NICHT blockiert
- Offline-Buffer existiert (100 Messages)
- Exponential Backoff für Reconnect existiert

### 2.2 SOLL-ZUSTAND

**Neuer SystemState in `system_config.h` oder `system_types.h`:**

```cpp
enum class SystemState : uint8_t {
    STATE_BOOT = 0,
    STATE_PROVISIONING,
    STATE_CONNECTING,
    STATE_OPERATIONAL,
    STATE_DEGRADED_WIFI,    // NEU: WiFi verloren, AP aktiv
    STATE_DEGRADED_MQTT,    // NEU: MQTT verloren, WiFi OK
    STATE_ERROR,
    STATE_SAFE_MODE
};
```

### 2.3 DEGRADED_WIFI MODE

**Trigger:** WiFi CB wechselt zu OPEN

**Aktionen bei Eintritt:**

| Aktion | Beschreibung |
|--------|--------------|
| **1. State setzen** | `g_system_config.current_state = STATE_DEGRADED_WIFI` |
| **2. AP-Mode aktivieren** | WiFi AP+STA Mode (versucht weiter zu reconnecten) |
| **3. Webportal starten** | Minimales Portal auf 192.168.4.1 |
| **4. Actuator Safe-State** | Alle Aktoren in definierten Safe-State (NICHT abschalten, sondern sicherer Zustand) |
| **5. Sensor-Buffering** | Lokal puffern (NVS oder RAM-Ring-Buffer) |
| **6. Watchdog-Feed ERLAUBEN** | System ist stabil, nur disconnected → KEIN Reboot |

**Webportal-Inhalt (SCHLANK):**

```
┌─────────────────────────────────────────┐
│ ESP32 Diagnostics - DEGRADED MODE       │
├─────────────────────────────────────────┤
│ WiFi: ❌ Disconnected (reconnecting...) │
│ MQTT: ❌ N/A (no WiFi)                  │
│ Buffered: 47 sensor readings            │
│ Uptime: 4h 23m                          │
├─────────────────────────────────────────┤
│ [WiFi Settings]                         │
│ SSID: _________ Password: _________     │
│ [Save & Reconnect]                      │
├─────────────────────────────────────────┤
│ Stored Config:                          │
│ - Kaiser ID: GOD                        │
│ - ESP ID: ESP_12AB34                    │
│ - MQTT Broker: 192.168.1.100:1883       │
│ [Edit MQTT Settings]                    │
└─────────────────────────────────────────┘
```

**Exit-Bedingung:** WiFi CB wechselt zu CLOSED → zurück zu STATE_OPERATIONAL

### 2.4 DEGRADED_MQTT MODE

**Trigger:** MQTT CB wechselt zu OPEN (WiFi ist noch CLOSED)

**Aktionen bei Eintritt:**

| Aktion | Beschreibung |
|--------|--------------|
| **1. State setzen** | `g_system_config.current_state = STATE_DEGRADED_MQTT` |
| **2. Kein AP-Mode** | WiFi funktioniert, ESP über lokale IP erreichbar |
| **3. Webportal verfügbar** | Auf normaler lokaler IP (z.B. 192.168.1.42) |
| **4. Erhöhtes Buffering** | Offline-Buffer nutzen (existiert bereits) |
| **5. Watchdog-Feed normal** | Bereits so implementiert |

**Webportal bei MQTT-Loss:**

```
┌─────────────────────────────────────────┐
│ ESP32 Diagnostics - MQTT DISCONNECTED   │
├─────────────────────────────────────────┤
│ WiFi: ✅ Connected (192.168.1.42)       │
│ MQTT: ❌ Disconnected (CB: OPEN)        │
│ Buffered: 89 messages (100 max)         │
│ Next retry: 45s                         │
├─────────────────────────────────────────┤
│ MQTT Settings:                          │
│ Broker: 192.168.1.100:1883              │
│ [Edit MQTT Settings]                    │
└─────────────────────────────────────────┘
```

**Exit-Bedingung:** MQTT CB wechselt zu CLOSED → zurück zu STATE_OPERATIONAL

### 2.5 ACTUATOR SAFE-STATE DEFINITION

**Neue Struktur in `actuator_types.h`:**

```cpp
struct ActuatorSafeState {
    uint8_t gpio;
    SafeStateAction action;  // HOLD_LAST, SET_LOW, SET_HIGH, SET_PWM
    uint16_t pwm_value;      // Nur wenn action == SET_PWM
};

enum class SafeStateAction : uint8_t {
    HOLD_LAST = 0,  // Letzten Wert beibehalten
    SET_LOW,        // Auf LOW setzen
    SET_HIGH,       // Auf HIGH setzen
    SET_PWM         // Auf spezifischen PWM-Wert setzen
};
```

**Default Safe-States (konfigurierbar vom Server):**

| Actuator-Typ | Safe-State | Begründung |
|--------------|------------|------------|
| Heizung | SET_LOW (aus) | Überhitzung verhindern |
| Lüftung | HOLD_LAST | Letzte Belüftung beibehalten |
| Bewässerung | SET_LOW (aus) | Überschwemmung verhindern |
| Beleuchtung | HOLD_LAST | Pflanzen-Rhythmus beibehalten |

### 2.6 LOKALES BUFFERING

**Erweitern des bestehenden Systems:**

| Komponente | Aktuell | Erweiterung |
|------------|---------|-------------|
| MQTT Offline Buffer | 100 Messages (RAM) | Beibehalten |
| Sensor Data Buffer | Keiner | NEU: NVS oder RAM Ring-Buffer |
| Buffer-Persistenz | Nein | NEU: Optional NVS für kritische Daten |

**Neuer SensorDataBuffer:**

```cpp
struct BufferedSensorReading {
    uint32_t timestamp;      // millis() bei Erfassung
    uint8_t sensor_gpio;
    float value;
    SensorType type;
};

// Ring-Buffer für ~100-200 Readings
// Bei Reconnect: Server entscheidet über Verarbeitung
```

### 2.7 BETROFFENE DATEIEN

| Datei | Änderung |
|-------|----------|
| `src/models/system_types.h` | STATE_DEGRADED_WIFI, STATE_DEGRADED_MQTT |
| `src/models/actuator_types.h` | SafeStateAction, ActuatorSafeState |
| `src/services/communication/wifi_manager.h/.cpp` | Degraded-Mode Trigger, AP-Mode Aktivierung |
| `src/services/communication/mqtt_client.h/.cpp` | Degraded-Mode Trigger |
| `src/services/actuator/safety_controller.h/.cpp` | enterSafeState() Methode |
| `src/main.cpp` | feedWatchdog() Logik anpassen (DEGRADED → Feed erlauben) |
| **NEU:** `src/services/web/diagnostic_portal.h/.cpp` | Minimales Webportal |
| **NEU:** `src/services/storage/sensor_buffer.h/.cpp` | Lokaler Sensor-Buffer |

### 2.8 FLOW-DIAGRAMM: WIFI-LOSS

```
WiFi Connection Lost
    │
    ├─> WiFiManager erkennt Disconnect
    │
    ├─> Nach X Reconnect-Versuchen: WiFi CB → OPEN
    │
    ├─> g_system_config.current_state = STATE_DEGRADED_WIFI
    │
    ├─> safetyController.enterSafeState(REASON_WIFI_LOSS)
    │       │
    │       └─> Alle Aktoren → Konfigurierter Safe-State
    │
    ├─> wifiManager.enableAPMode() (AP + STA parallel)
    │
    ├─> diagnosticPortal.start()
    │
    └─> Main Loop:
            │
            ├─> Sensoren weiter lesen
            ├─> Daten in lokalen Buffer
            ├─> Watchdog-Feed ERLAUBT (System stabil)
            ├─> WiFi-Reconnect-Versuche (Backoff)
            │
            └─> WiFi CB → CLOSED?
                    │
                    └─> JA: STATE_OPERATIONAL
                            AP-Mode deaktivieren
                            Buffer an Server senden
                            Aktoren: Server-Kontrolle
```

### 2.9 QUALITY GATES

- [ ] WiFi-Loss → STATE_DEGRADED_WIFI, Watchdog läuft weiter
- [ ] MQTT-Loss → STATE_DEGRADED_MQTT, Watchdog läuft weiter
- [ ] AP-Mode aktiviert bei WiFi-Loss, Portal erreichbar auf 192.168.4.1
- [ ] Portal zeigt korrekten Status (WiFi, MQTT, Buffer-Count)
- [ ] WiFi-Credentials können geändert werden
- [ ] MQTT-Settings können geändert werden
- [ ] Reconnect funktioniert automatisch (mit Backoff)
- [ ] Nach Reconnect: Buffer wird an Server gesendet
- [ ] Aktoren in Safe-State während Degraded-Mode

---

## PHASE 3: Server-Status-Broadcast

**Ziel:** ESP kann auf Server-Probleme reagieren (Koordinierte Degradation)

### 3.1 IST-ZUSTAND

- Server und ESP haben unabhängige Circuit Breakers
- Keine Kommunikation über CB-States
- ESP sendet blind Daten, auch wenn Server-DB down ist

### 3.2 SOLL-ZUSTAND

**Server publiziert Status auf MQTT:**

**Topic:** `kaiser/{kaiser_id}/system/status`

**Payload:**
```json
{
    "db_circuit": "closed",       // closed, open, half_open
    "mqtt_load_pct": 23,          // MQTT-Handler Auslastung
    "buffer_pct": 12,             // Server-seitiger Buffer
    "recommended_interval_ms": 60000,  // Empfohlenes Telemetrie-Intervall
    "timestamp": 1738245600
}
```

**Publishing-Frequenz:**
- Normal: Alle 60 Sekunden
- Bei State-Change: Sofort

### 3.3 ESP-REAKTION

**Neuer Handler in MQTTClient:**

```cpp
void handleServerStatus(const JsonDocument& payload) {
    ServerStatus status;
    status.db_circuit = parseCircuitState(payload["db_circuit"]);
    status.buffer_pct = payload["buffer_pct"];
    status.recommended_interval_ms = payload["recommended_interval_ms"];
    
    // Telemetrie-Intervall anpassen
    if (status.recommended_interval_ms > 0) {
        healthMonitor.setPublishInterval(status.recommended_interval_ms);
    }
    
    // Bei hoher Server-Last: Nicht-kritische Telemetrie reduzieren
    if (status.buffer_pct > 80 || status.db_circuit == CircuitState::OPEN) {
        setTelemetryMode(TELEMETRY_CRITICAL_ONLY);
    } else {
        setTelemetryMode(TELEMETRY_FULL);
    }
}
```

**Telemetrie-Modi:**

| Modus | Sensor-Data | Heartbeat | Diagnostics | Error-Reports |
|-------|-------------|-----------|-------------|---------------|
| TELEMETRY_FULL | ✅ Normal | ✅ 60s | ✅ 60s | ✅ Sofort |
| TELEMETRY_CRITICAL_ONLY | ⚠️ Nur Anomalien | ✅ 120s | ❌ | ✅ Sofort |

### 3.4 BETROFFENE DATEIEN

**Server-Seite:**

| Datei | Änderung |
|-------|----------|
| `src/mqtt/publishers/server_status_publisher.py` | NEU: Status-Publisher |
| `src/core/resilience/registry.py` | Status-Aggregation für Publishing |
| `src/main.py` | Status-Publisher starten |

**ESP-Seite:**

| Datei | Änderung |
|-------|----------|
| `src/services/communication/mqtt_client.h/.cpp` | Server-Status-Handler, Telemetrie-Modi |
| `src/error_handling/health_monitor.h/.cpp` | Dynamisches Publish-Intervall |
| `src/models/server_types.h` | NEU: ServerStatus Struct |

### 3.5 QUALITY GATES

- [ ] Server publiziert Status alle 60s und bei State-Changes
- [ ] ESP empfängt und parst Server-Status
- [ ] ESP passt Telemetrie-Intervall basierend auf Server-Empfehlung an
- [ ] Bei Server-DB-CB OPEN: ESP reduziert auf CRITICAL_ONLY
- [ ] Bei Server-Buffer > 80%: ESP reduziert auf CRITICAL_ONLY
- [ ] Nach Server-Recovery: ESP kehrt zu TELEMETRY_FULL zurück

---

## PHASE 4: SafetyController bei Watchdog-Timeout

**Ziel:** Definierter Actuator-State vor ESP-Reset

### 4.1 IST-ZUSTAND

**Datei:** `main.cpp:1560-1617` (handleWatchdogTimeout)

```cpp
void handleWatchdogTimeout() {
    // 1. Track Critical Error
    // 2. Collect Diagnostics
    // 3. Persist to NVS (TODO)
    // 4. Publish Emergency MQTT (wenn möglich)
    // 5. Mode-spezifische Aktion:
    //    - PRODUCTION: Panic → ESP Reset
    //    - PROVISIONING: Kein Panic, Safe-Mode Entry
    
    // PROBLEM: Aktoren werden NICHT explizit in Safe-State gesetzt!
}
```

**Problem:**
- Bei Watchdog-Timeout werden Aktoren in undefiniertem Zustand belassen
- Nach Reboot könnten Aktoren in vorherigem (potenziell gefährlichem) State starten
- Beispiel: Heizung war AN, Watchdog-Timeout, Reboot, Boot dauert 10s → Heizung läuft unkontrolliert

### 4.2 SOLL-ZUSTAND

**Erweiterung von handleWatchdogTimeout():**

```cpp
void handleWatchdogTimeout() {
    // 1. ZUERST: Aktoren sicher abschalten
    safetyController.emergencyStopAll("Watchdog Timeout - controlled shutdown");
    
    // 2. Track Critical Error
    errorTracker.trackError(ERROR_WATCHDOG_TIMEOUT, ERROR_SEVERITY_CRITICAL, ...);
    
    // 3. Collect Diagnostics (inkl. Actuator-States vor Stop)
    // 4. Persist to NVS
    // 5. Publish Emergency MQTT (wenn möglich)
    // 6. Mode-spezifische Aktion
}
```

**Reihenfolge ist KRITISCH:**
1. **Aktoren sichern** (Hardware-Zustand)
2. **Diagnostics sammeln** (Software-State)
3. **Persistieren** (für Post-Mortem)
4. **Reset**

### 4.3 ACTUATOR-STATE PERSISTENZ

**Problem:** Nach Reboot weiß ESP nicht, warum er neugestartet hat.

**Lösung:** Watchdog-Reason und letzte Actuator-States in NVS speichern:

```cpp
struct WatchdogRecoveryData {
    uint32_t magic;              // Validierungs-Magic
    uint32_t timestamp;          // Zeitpunkt des Timeouts
    ResetReason reason;          // WATCHDOG_TIMEOUT, CRITICAL_ERROR, etc.
    uint8_t actuator_states[16]; // Letzte States vor Shutdown
    uint8_t error_count;         // Anzahl Errors vor Timeout
    CircuitState wifi_cb;
    CircuitState mqtt_cb;
};
```

**Nach Reboot:**

```cpp
void setup() {
    // ...
    if (esp_reset_reason() == ESP_RST_TASK_WDT) {
        WatchdogRecoveryData recovery;
        if (storageManager.loadWatchdogRecovery(&recovery)) {
            LOG_WARNING("Recovered from Watchdog Timeout");
            LOG_WARNING("  Reason: %s", reasonToString(recovery.reason));
            LOG_WARNING("  WiFi CB was: %s", stateToString(recovery.wifi_cb));
            // Diagnostics an Server senden bei Reconnect
        }
    }
}
```

### 4.4 BETROFFENE DATEIEN

| Datei | Änderung |
|-------|----------|
| `src/main.cpp` | handleWatchdogTimeout() erweitern |
| `src/services/actuator/safety_controller.h/.cpp` | emergencyStopAll() für WD-Timeout optimieren |
| `src/services/config/storage_manager.h/.cpp` | saveWatchdogRecovery(), loadWatchdogRecovery() |
| `src/models/watchdog_types.h` | WatchdogRecoveryData Struct |

### 4.5 TIMING-ÜBERLEGUNG

**Problem:** Nach Watchdog-Timeout hat ESP nur begrenzte Zeit für Cleanup.

**ESP32 Task WDT Verhalten:**
- Timeout erreicht → panic=true → Hardware-Reset nach wenigen Zyklen
- Wir haben KEINE Zeit für lange Cleanup-Operationen

**Lösung:** "Software Watchdog" mit GRÖSSEREM Timeout als Hardware-WDT:

```
┌─────────────────────────────────────────────────────────┐
│ Zeit: 0s                    50s        55s         60s  │
│       │                      │          │           │   │
│       │   Feed-Interval (10s)│          │           │   │
│       │   ─────────────────►│          │           │   │
│       │                      │          │           │   │
│       │              Software-WDT      Hardware-WDT │   │
│       │              Warnung (55s)     Timeout (60s)│   │
│       │                      │          │           │   │
│       │                      │   ┌──────┴───────┐   │   │
│       │                      │   │ 5s Cleanup:  │   │   │
│       │                      │   │ - EmergStop  │   │   │
│       │                      │   │ - NVS Save   │   │   │
│       │                      │   │ - MQTT Pub   │   │   │
│       │                      │   └──────────────┘   │   │
└─────────────────────────────────────────────────────────┘
```

**Implementation:**
- Software-Timer bei 55s (5s vor Hardware-WDT)
- Im Timer-ISR: Cleanup starten
- Hardware-WDT bei 60s: Reset (falls Cleanup hängt)

### 4.6 QUALITY GATES

- [ ] Bei Watchdog-Timeout: Aktoren werden in Safe-State gesetzt VOR Reset
- [ ] WatchdogRecoveryData wird in NVS gespeichert
- [ ] Nach Reboot: Recovery-Daten werden gelesen und geloggt
- [ ] Recovery-Daten werden an Server gesendet bei Reconnect
- [ ] Software-WDT (55s) gibt 5s Cleanup-Zeit vor Hardware-WDT (60s)

---

## ZUSAMMENFASSUNG: PHASEN-ÜBERSICHT

| Phase | Aufwand | Abhängigkeiten | Impact |
|-------|---------|----------------|--------|
| **1. Window Watchdog** | 2-3h | Keine | Diagnostic Coverage ↑ |
| **2. Degraded Mode** | 8-12h | Keine | Verfügbarkeit ↑↑ |
| **3. Server-Status-Broadcast** | 4-6h | Phase 2 (optional) | Koordination ↑ |
| **4. SafetyController @ WDT** | 2-3h | Keine | Safety ↑ |

**Empfohlene Reihenfolge:**

1. **Phase 1** (Window Watchdog) – Einfach, hoher Value
2. **Phase 4** (SafetyController @ WDT) – Einfach, wichtig für Safety
3. **Phase 2** (Degraded Mode) – Komplex, höchster Value
4. **Phase 3** (Server-Status) – Nice-to-have, verbessert Koordination
