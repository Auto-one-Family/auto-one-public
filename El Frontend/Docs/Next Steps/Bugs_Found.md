# Bug Report: Multi-Value I2C Sensor + Wokwi Integration

> **Datum:** 2026-01-14
> **Status:** Offen - Erfordert tiefere Analyse
> **Betroffene Komponenten:** El Trabajante, El Servador, El Frontend, Wokwi

---

## Zusammenfassung

Bei der Konfiguration eines SHT31 (I2C Multi-Value Sensor) über das Frontend für den Wokwi-simulierten ESP werden die Pins 21/22 als belegt angezeigt, obwohl der Sensor nicht funktioniert. Der Sensor erscheint nicht auf der Orbital Card im Frontend.

---

## Kontext: Multi-Value Sensor Architektur

### Beabsichtigtes Design (KEIN Bug)

Ein SHT31 ist ein **Multi-Value Sensor** - er liefert zwei Messwerte:
- Temperatur (`sht31_temp`)
- Luftfeuchtigkeit (`sht31_humidity`)

Der ESP32 sendet deshalb **zwei separate MQTT-Nachrichten** - eine pro Wert. Das ist beabsichtigt und modular erweiterbar:
- BME280 sendet 3 Werte (temp, humidity, pressure)
- Zukünftige Sensoren können beliebig viele Werte senden

**Relevante Dateien (Multi-Value Logik):**
```
El Trabajante/src/models/sensor_registry.h      # SensorCapability Struct
El Trabajante/src/models/sensor_registry.cpp    # MULTI_VALUE_DEVICES Registry
El Frontend/src/utils/sensorDefaults.ts         # MULTI_VALUE_DEVICES Config (Frontend)
```

---

## Bug T: I2C Sensor GPIO-Zuordnung in Datenbank

### Problem

Die Datenbank speichert für einen SHT31 **zwei separate Sensor-Einträge** mit unterschiedlichen GPIOs:

| DB-Eintrag | GPIO | sensor_type | Bedeutung |
|------------|------|-------------|-----------|
| Eintrag 1 | **21** | `sht31_temp` | SDA Pin |
| Eintrag 2 | **22** | `sht31_humidity` | SCL Pin |

### Warum das problematisch ist

Ein I2C-Sensor nutzt **beide Pins gleichzeitig** als Bus:
- GPIO 21 = SDA (Daten)
- GPIO 22 = SCL (Clock)

Es ist **ein physisches Gerät** auf I2C-Adresse `0x44`, das über den Bus kommuniziert. Die aktuelle DB-Struktur impliziert fälschlich, dass Temperatur auf Pin 21 gemessen wird und Humidity auf Pin 22 - das ist technisch falsch.

### Erwartetes Verhalten

Ein I2C Multi-Value Sensor sollte als **ein logisches Device** gespeichert werden:
- Eine `sensor_config` mit I2C-Adresse `0x44`
- Mehrere `sensor_data` Einträge für die verschiedenen Werte
- ODER: Ein `gpio` Feld das "i2c" oder die Adresse referenziert

### Betroffene Dateien für Analyse

```
El Servador/god_kaiser_server/src/db/models/sensor.py           # SensorConfig Model
El Servador/god_kaiser_server/src/mqtt/handlers/sensor_handler.py # Wie werden Multi-Values verarbeitet?
El Frontend/src/views/DeviceDetailView.vue                      # Wie wird ein Sensor angelegt?
El Frontend/src/components/esp/ESPOrbitalLayout.vue             # Wie werden Sensoren angezeigt?
```

### Fragen für weitere Analyse

1. Wie soll das DB-Schema für I2C Multi-Value Sensoren aussehen?
2. Sendet der ESP32 beide Werte mit demselben GPIO oder verschiedenen?
3. Wie erkennt der Server, dass zwei Nachrichten zum selben physischen Device gehören?

---

## Bug U: NVS_WRITE_FAILED in Wokwi Simulation

### Problem

Bei der Sensor-Konfiguration schlägt das NVS-Schreiben fehl:

```
config_status: failed
config_error: NVS_WRITE_FAILED
```

### Ursache

**Wokwi hat keinen persistenten NVS-Speicher.** Die ESP32-Firmware versucht, die Sensor-Konfiguration im NVS zu speichern, aber Wokwi simuliert diese Hardware-Komponente nicht.

### Datenbank-Evidenz

```sql
-- Wokwi ESP: ESP_00000001 (device_id: d8e2436fdec9414bb2e1adf560b6318d)
SELECT gpio, sensor_type, config_status, config_error FROM sensor_configs
WHERE esp_id = 'd8e2436fdec9414bb2e1adf560b6318d';

-- Ergebnis:
-- gpio=21, type=sht31_temp,     status=failed, error=NVS_WRITE_FAILED
-- gpio=22, type=sht31_humidity, status=failed, error=NVS_WRITE_FAILED
-- gpio=4,  type=ds18b20,        status=failed, error=GPIO_CONFLICT
```

### Betroffene Dateien

```
El Trabajante/src/services/config/storage_manager.cpp   # NVS Write Logic
El Trabajante/src/services/config/config_manager.cpp    # Config Persistence
El Trabajante/docs/NVS_KEYS.md                          # NVS Key Reference
```

### Mögliche Lösungen (zu evaluieren)

1. **Wokwi-Mode Flag:** ESP32 erkennt Wokwi und überspringt NVS-Writes
2. **Graceful Degradation:** NVS-Fehler sollten nicht die gesamte Konfiguration blockieren
3. **In-Memory Fallback:** Konfiguration im RAM halten wenn NVS nicht verfügbar

---

## Bug V: Fehlgeschlagene Sensoren blockieren GPIO-Auswahl im Frontend

### Problem

Im Frontend werden GPIO 21 und 22 als "belegt" angezeigt, obwohl die Sensor-Konfiguration fehlgeschlagen ist (`config_status=failed`). Der User kann diese Pins nicht mehr auswählen.

### Ursache

Das Frontend/die GPIO-Status-Logik filtert nicht nach `config_status`. Es prüft nur, ob ein Sensor-Eintrag für den GPIO existiert - unabhängig davon, ob die Konfiguration erfolgreich war.

### Erwartetes Verhalten

Pins mit `config_status=failed` sollten:
- Entweder automatisch bereinigt werden
- Oder als "verfügbar (Fehler)" angezeigt werden
- Oder einen "Retry/Delete" Button haben

### Betroffene Dateien

```
El Frontend/src/composables/useGpioStatus.ts            # GPIO Status Logic
El Frontend/src/components/esp/GpioPicker.vue           # GPIO Selection UI
El Servador/god_kaiser_server/src/api/v1/sensors.py     # GET /gpio-status Endpoint
```

---

## Bug W: GPIO_CONFLICT auf Pin 4

### Problem

```
gpio=4, type=ds18b20, status=failed, error=GPIO_CONFLICT
```

### Ursache

Die Wokwi-Konfiguration (`El Trabajante/diagram.json`) hat bereits einen DS18B20 auf GPIO 4. Der User hat versucht, einen zweiten Sensor auf demselben Pin zu konfigurieren.

### Warum das ein Problem ist

Der GPIO-Manager hat korrekt den Konflikt erkannt - **das ist erwartetes Verhalten**. Das Problem ist, dass dieser fehlgeschlagene Eintrag in der DB verbleibt und den Pin blockiert (siehe Bug V).

### Wokwi Konfiguration

```json
// El Trabajante/diagram.json (Lines 14-21)
{
  "type": "wokwi-ds18b20",
  "id": "temp1",
  "attrs": { "temperature": "22.5" }
}
// Connection: esp:D4 -> temp1:DQ (Line 56)
```

---

## Bug X: SHT31 nicht in Wokwi Simulation vorhanden

### Problem

Der User hat versucht, einen SHT31 zu konfigurieren, aber Wokwi simuliert keinen SHT31.

### Wokwi diagram.json Inhalt

```
Vorhandene Parts:
- wokwi-esp32-devkit-v1
- wokwi-ds18b20 (GPIO 4)
- wokwi-led (GPIO 5)
- 2x wokwi-resistor

NICHT vorhanden:
- Kein SHT31 / SHT3x
- Kein I2C Sensor
```

### Konsequenz

Selbst wenn die DB-Konfiguration korrekt wäre, kann Wokwi den SHT31 nicht simulieren - es gibt keine Hardware zum Auslesen.

### Betroffene Datei

```
El Trabajante/diagram.json    # Wokwi Hardware Definition
```

---

## Datenbank-Bereinigung (Quick Fix)

Um die blockierten Pins freizugeben:

```sql
-- Alle fehlgeschlagenen Sensoren für Wokwi-ESP löschen
DELETE FROM sensor_configs
WHERE esp_id = 'd8e2436fdec9414bb2e1adf560b6318d';
```

**Achtung:** Das löst nicht die Root-Cause-Probleme (Bug T, U, V).

---

## Zusammenfassung der offenen Fragen

| Bug | Frage | Wer sollte analysieren |
|-----|-------|----------------------|
| **T** | Wie soll das DB-Schema für I2C Multi-Value Sensoren aussehen? | Backend + DB Design |
| **U** | Soll Wokwi-Mode NVS überspringen? Graceful Degradation? | El Trabajante Firmware |
| **V** | Sollen failed Configs automatisch gelöscht werden? | Frontend + Backend API |
| **W/X** | Soll Wokwi einen SHT31 bekommen oder nur DS18B20 testen? | Test-Strategie |

---

## Relevante Code-Locations (Gesamtübersicht)

### El Trabajante (ESP32 Firmware)
```
src/models/sensor_registry.h/.cpp       # Multi-Value Sensor Definitionen
src/services/config/storage_manager.*   # NVS Persistence
src/services/config/config_manager.*    # Config Loading
src/drivers/i2c_bus.*                   # I2C Bus Management
src/drivers/gpio_manager.*              # GPIO Reservation (Safe-Mode)
diagram.json                            # Wokwi Hardware Definition
```

### El Servador (Python Server)
```
src/db/models/sensor.py                 # SensorConfig Model
src/mqtt/handlers/sensor_handler.py     # MQTT Message Processing
src/api/v1/sensors.py                   # REST API (GPIO Status)
```

### El Frontend (Vue.js)
```
src/utils/sensorDefaults.ts             # Multi-Value Device Config
src/utils/gpioConfig.ts                 # GPIO Pin Definitions
src/composables/useGpioStatus.ts        # GPIO Status Composable
src/components/esp/GpioPicker.vue       # GPIO Selection UI
src/components/esp/ESPOrbitalLayout.vue # Sensor Display
src/views/DeviceDetailView.vue          # Device Configuration
```

---

**Nächster Schritt:** Ein Entwickler sollte die Multi-Value Sensor Logik von El Trabajante bis Frontend durchgehen und ein konsistentes Datenmodell für I2C-Sensoren definieren.

---

# Wokwi Szenario-Tests: Bug Report (2026-01-28)

> **Datum:** 2026-01-28
> **Getestet:** 9 neue Wokwi-Szenarien (E2E Sensor/Actuator/Emergency/Combined Flows)
> **Ergebnis:** Alle 9 Szenarien FAIL — MQTT-Verbindung blockiert
> **Firmware-Build:** SUCCESS (wokwi_simulation, 87.1% Flash)

---

## Bug A: MQTT "Connection reset by peer" in Wokwi-Simulation (BLOCKER)

**Betrifft:** Alle 9 Szenarien
**Schweregrad:** BLOCKER — kein einziges Szenario kann MQTT-basierte Steps erreichen

**Erwarteter Output:**
```
MQTT connected
```

**Tatsächlicher Output:**
```
[  6318][E][WiFiClient.cpp:275] connect(): socket error on fd 48, errno: 104, "Connection reset by peer"
[      6372] [ERROR   ] MQTT connection failed, rc=-2
[      7162] [WARNING ] CircuitBreaker [MQTT]: Failure recorded (count: 1/5)
...
[     37578] [ERROR   ] CircuitBreaker [MQTT]: Failure threshold reached → OPEN
Timeout: simulation did not finish in 90000ms
```

**Ablauf:**
1. ESP32 bootet korrekt (alle 5 Phasen READY)
2. WiFi verbindet erfolgreich (`WiFi connected! IP: 10.13.37.2`)
3. MQTT-Verbindung zu `host.wokwi.internal:1883` schlägt fehl mit `errno: 104` (Connection reset by peer)
4. 6 Reconnect-Versuche, alle fehlgeschlagen
5. CircuitBreaker öffnet nach 5 Failures → keine weiteren Reconnects
6. Szenario timeout

**Umgebung:**
- Wokwi CLI v0.19.1, `gateway = true` in `wokwi.toml`
- Mosquitto läuft als Windows-Service auf `0.0.0.0:1883` (verifiziert via `netstat`)
- `mosquitto_pub` von localhost funktioniert einwandfrei
- Windows 10/11

**Vermutete Ursache:**
Windows Firewall blockiert eingehende TCP-Verbindungen von der Wokwi-Simulation-Netzwerkschicht (10.13.37.x) auf Port 1883. Mosquitto hört auf allen Interfaces, aber die Wokwi-Gateway-Bridge wird von der Firewall als externe Verbindung behandelt.

**Mögliche Fixes (nicht getestet):**
1. Windows Firewall Regel für Port 1883 eingehend (von allen Quellen) erlauben
2. Windows Firewall komplett deaktivieren (nur zum Testen)
3. Mosquitto-Konfiguration prüfen (`allow_anonymous true` + `listener 1883 0.0.0.0`)

**Hinweis:** In GitHub Actions CI funktioniert dieser Flow, da Docker-Container im gleichen Netzwerk laufen und keine Firewall-Regeln greifen.

---

## Szenario-Ergebnisse im Detail

| # | Szenario | Ergebnis | Fehlgeschlagener Step |
|---|----------|----------|----------------------|
| 1 | `02-sensor/sensor_ds18b20_full_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 3/6) |
| 2 | `02-sensor/sensor_dht22_full_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/4) |
| 3 | `02-sensor/sensor_analog_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/4) |
| 4 | `03-actuator/actuator_binary_full_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/4) |
| 5 | `03-actuator/actuator_pwm_full_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/4) |
| 6 | `03-actuator/actuator_timeout_e2e.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/4) |
| 7 | `05-emergency/emergency_stop_full_flow.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/5) |
| 8 | `07-combined/combined_sensor_actuator.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/5) |
| 9 | `07-combined/multi_device_parallel.yaml` | FAIL | `wait-serial: "MQTT connected"` (Step 1/6) |

**Alle Szenarien scheitern am identischen Punkt:** Die MQTT-Verbindung zu `host.wokwi.internal:1883` wird mit `errno: 104` ("Connection reset by peer") abgelehnt.

---

## Was funktioniert (verifiziert aus Serial Output)

Trotz MQTT-Failure konnte aus dem Serial Output bestätigt werden:

| Komponente | Status | Beweis |
|-----------|--------|--------|
| Boot-Sequenz | OK | Alle 5 Phasen READY |
| GPIO Safe-Mode | OK | "All pins successfully set to Safe-Mode" |
| WiFi-Verbindung | OK | "WiFi connected! IP: 10.13.37.2, RSSI: -77 dBm" |
| ConfigManager | OK | "All Phase 1 configurations loaded successfully" |
| ESP ID | OK | "Using Wokwi ESP ID: ESP_00000001" |
| I2C Reservation | OK | "I2C pins auto-reserved (SDA: GPIO 21, SCL: GPIO 22)" |
| OneWire Bus | OK | Initialisiert (Phase 3) |
| Sensor Manager | OK | "Phase 4: Sensor System READY" |
| Actuator Manager | OK | "Phase 5: Actuator System READY" |
| Circuit Breaker | OK | Öffnet korrekt nach 5 Failures |

---

## Bug B: Phase 2 meldet "READY" trotz MQTT-Failure

**Szenario:** Alle (beobachtet in DS18B20 Full Flow)
**Erwartetes Verhalten:** Phase 2 sollte als FAILED oder WARNING gemeldet werden wenn MQTT nicht verbunden ist
**Tatsächliches Verhalten:**
```
[      6372] [ERROR   ] MQTT connection failed, rc=-2
[      6385] [WARNING ] System will continue but MQTT features unavailable
[      6407] [INFO    ] ║   Phase 2: Communication Layer READY
```

**Vermutete Ursache:** Das Design erlaubt explizit das Weiterlaufen ohne MQTT (graceful degradation). Ob "READY" hier korrekt ist oder "DEGRADED" besser wäre, ist eine Design-Entscheidung.

**Schweregrad:** LOW — funktionales Verhalten, keine Fehlfunktion. Möglicherweise beabsichtigt.

---

## Bug C: Szenarien erfordern MQTT-Injection, aber kein automatischer Mechanismus

**Betrifft:** Szenarien 4-9 (actuator, emergency, combined)
**Beschreibung:** Die Szenarien `actuator_binary_full_flow.yaml`, `actuator_pwm_full_flow.yaml`, `actuator_timeout_e2e.yaml`, `emergency_stop_full_flow.yaml`, `combined_sensor_actuator.yaml`, `multi_device_parallel.yaml` erwarten `wait-serial: "Actuator"` nach MQTT-Injection-Commands, aber die YAML-Szenarien selbst haben **keinen Mechanismus für MQTT-Injection**. Die Injection muss extern (parallel in einem separaten Prozess) ausgeführt werden.

**Konsequenz:** Diese Szenarien können nur in der CI-Umgebung (GitHub Actions) korrekt laufen, wo der Workflow Wokwi im Hintergrund startet und dann `mosquitto_pub` für die Injection aufruft. Lokal müsste man manuell parallel `mosquitto_pub` ausführen.

**Schweregrad:** MEDIUM — Design-Limitation, kein Bug. Die CI-Workflow-Datei (`wokwi-tests.yml`) implementiert dies korrekt.

---

**Zusammenfassung:** Der einzige echte Blocker ist **Bug A** (Firewall/Netzwerk). Sobald MQTT-Verbindung funktioniert, können die 3 passiven Sensor-Szenarien (1-3) sofort durchlaufen. Die 6 aktiven Szenarien (4-9) benötigen zusätzlich externe MQTT-Injection.

---

# Test-Run 2 (2026-01-28, nach Firewall-Fix)

## Ergebnis: Firewall-Fix hat Problem NICHT behoben

| # | Szenario | Ergebnis | Fehlgeschlagener Step |
|---|----------|----------|-----------------------|
| 1 | sensor_ds18b20_full_flow | **FAIL** | `wait-serial: "MQTT connected"` (Step 3) |
| 2 | sensor_dht22_full_flow | **FAIL** | `wait-serial: "MQTT connected"` (Step 1) |
| 3 | sensor_analog_flow | **FAIL** | `wait-serial: "MQTT connected"` (Step 1) |
| 4-9 | actuator/emergency/combined | **FAIL** | Nicht separat getestet — identischer Blocker (MQTT) |

### Beobachtungen

- **WiFi verbindet erfolgreich:** `WiFi connected! IP: 10.13.37.2` (OK)
- **MQTT schlägt fehl:** `MQTT connect attempt 1 failed, rc=-1 (errno: 104, "Connection reset by peer")` (identisch zu Test-Run 1)
- **Mosquitto läuft:** Service aktiv, Port 1883 gebunden, `mosquitto_pub` von localhost funktioniert
- **Circuit Breaker:** Öffnet nach 6 Fehlversuchen, blockiert dann alle weiteren Reconnect-Versuche

### Analyse

Die Windows-Firewall-Regel (Port 1883 eingehend erlauben) hat das Problem nicht gelöst. Die Ursache liegt tiefer:

1. **Wokwi Gateway-Bridge:** `host.wokwi.internal` wird zu einer IP aufgelöst, die über die Wokwi Cloud-Simulation zum Host-Rechner zurücktunnelt. Die Firewall-Regel greift möglicherweise nicht für diesen Tunnel-Traffic.
2. **Mosquitto Binding:** Mosquitto bindet auf `0.0.0.0:1883`, sollte also alle Interfaces akzeptieren. Aber der Wokwi-Traffic kommt ggf. über einen unerwarteten Netzwerkpfad.
3. **Mögliche nächste Schritte:**
   - Prüfen ob `host.wokwi.internal` korrekt aufgelöst wird (DNS innerhalb Wokwi-Simulation)
   - Mosquitto-Logs auf eingehende Verbindungsversuche prüfen (`$SYS/broker/log/#`)
   - Wokwi-Support kontaktieren: Gateway-Networking unter Windows 11 möglicherweise anders als unter Linux/macOS
   - Alternative: Nur in CI (GitHub Actions/Linux) testen — dort funktioniert der Gateway nachweislich
