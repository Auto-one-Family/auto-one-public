# El Frontend – Debug Architecture & Flows

Ziel: Das Debug-Dashboard soll ohne echte ESP32‑Hardware die gleichen Flows wie das Produktions-Frontend fahren. Diese Doku fasst die für Entwickler relevanten Pfade, Zustände und Integrationspunkte zusammen, damit Änderungen minimal bleiben und Tests (inkl. Lastszenarien mit vielen ESPs/Sensoren/Aktoren) reproduzierbar sind.

---

## 0) KI-Agenten: Service-Management (Start/Stop/Logs)

> **WICHTIG:** Diese Section ist für KI-Agenten gedacht, die das System entwickeln oder debuggen.
> **Letzte Aktualisierung:** 2026-02-01

### 0.1) Quick-Reference: Services

| Service | Port | Prozess | Prüf-Befehl |
|---------|------|---------|-------------|
| **Server (uvicorn)** | 8000 | `python.exe` | `netstat -ano \| findstr "8000"` |
| **Frontend (Vite)** | 5173 | `node.exe` | `netstat -ano \| findstr "5173"` |
| **MQTT (Mosquitto)** | 1883 | `mosquitto.exe` | `netstat -ano \| findstr "1883"` |

### 0.2) Laufende Services finden

```bash
# Schritt 1: Prozesse nach Namen finden
tasklist | findstr "python"      # Server (uvicorn)
tasklist | findstr "node"        # Frontend (Vite)
tasklist | findstr "mosquitto"   # MQTT Broker

# Schritt 2: Ports prüfen (zeigt PIDs)
netstat -ano | findstr "8000"    # Server Port → PID in letzter Spalte
netstat -ano | findstr "5173"    # Frontend Port
netstat -ano | findstr "1883"    # MQTT Port

# Beispiel-Output:
# TCP    0.0.0.0:8000    0.0.0.0:0    ABHÖREN    63588
#                                              ↑ PID
```

**Service-Status interpretieren:**
- `ABHÖREN` / `LISTENING` = Service läuft und akzeptiert Verbindungen
- Keine Ausgabe = Service läuft NICHT auf diesem Port
- `WARTEND` / `TIME_WAIT` = Alte Verbindungen werden aufgeräumt

### 0.3) Services beenden

**WICHTIG für Git Bash:** Verwende `//` statt `/` für Windows-Befehle!

```bash
# Einzelnen Prozess nach PID beenden (Git Bash Syntax)
taskkill //PID 63588 //F //T

# Erklärung:
# //PID = Prozess-ID (aus netstat)
# //F   = Force (erzwingen)
# //T   = Tree (auch Child-Prozesse beenden)

# Mosquitto-Dienst stoppen (benötigt Admin-Rechte)
net stop mosquitto

# ALLE Python-Prozesse beenden (Vorsicht!)
taskkill //IM python.exe //F

# ALLE Node-Prozesse beenden (Vorsicht!)
taskkill //IM node.exe //F
```

**Vollständiger Neustart-Workflow:**
```bash
# 1. Finde PIDs
netstat -ano | findstr "8000"  # → z.B. PID 63588
netstat -ano | findstr "5173"  # → z.B. PID 17344

# 2. Beende Services
taskkill //PID 63588 //F //T   # Server
taskkill //PID 17344 //F //T   # Frontend

# 3. Warte kurz (optional)
sleep 2

# 4. Starte neu (siehe 0.4)
```

### 0.4) Services starten

**Server starten (Foreground):**
```bash
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Servador/god_kaiser_server"
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Server starten (Background - für KI-Agenten):**
```bash
# Mit Claude Code Bash Tool: run_in_background=true
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Servador/god_kaiser_server" && poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend starten (Foreground):**
```bash
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Frontend"
npm run dev
```

**Frontend starten (Background - für KI-Agenten):**
```bash
# Mit Claude Code Bash Tool: run_in_background=true
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Frontend" && npm run dev
```

**Erwartete Server-Ausgabe:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [63588] using WatchFiles
INFO:     Started server process [34872]
INFO:     Waiting for application startup.
SECURITY: Using default JWT secret key (OK for development only).
MQTT TLS is disabled.
INFO:     Application startup complete.
```

**Erwartete Frontend-Ausgabe:**
```
VITE v6.4.1  ready in 369 ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

### 0.5) Server-Logs prüfen

> **Vollständige Log-Dokumentation:** `.claude/reference/debugging/LOG_LOCATIONS.md`
> Enthält: Alle Log-Pfade, JSON-Format, grep-Patterns, Log-Rotation, Konfiguration

**Quick Commands:**
```bash
# Live-Logs
tail -f "El Servador/god_kaiser_server/logs/god_kaiser.log"

# Fehler suchen
grep -i "ERROR\|CRITICAL" "El Servador/god_kaiser_server/logs/god_kaiser.log"

# Letzte 50 Zeilen
tail -50 "El Servador/god_kaiser_server/logs/god_kaiser.log"
```

**Log-Pfad:** `El Servador/god_kaiser_server/logs/god_kaiser.log` (JSON-Format, rotierend)

**Für Details siehe:** `.claude/reference/debugging/LOG_LOCATIONS.md`

### 0.6) Health-Checks durchführen

```bash
# Server erreichbar?
curl -s http://localhost:8000/api/v1/auth/status

# Erwartete Antwort:
# {"setup_required":false,"users_exist":true,"mqtt_auth_enabled":false,"mqtt_tls_enabled":false}

# Frontend erreichbar?
curl -I http://localhost:5173
# Erwartete Antwort: HTTP/1.1 200 OK
```

### 0.7) System-Status-Tabelle

Nach erfolgreichem Start sollte die Tabelle so aussehen:

| Service | URL | Status-Check | Erwartung |
|---------|-----|--------------|-----------|
| Backend API | `http://localhost:8000` | `curl http://localhost:8000/api/v1/auth/status` | JSON Response |
| Frontend | `http://localhost:5173` | Browser öffnen | Vue App lädt |
| API Docs | `http://localhost:8000/docs` | Swagger UI | Interaktive Docs |
| MQTT Broker | `mqtt://localhost:1883` | `netstat -ano \| findstr "1883"` | LISTENING |

### 0.8) Häufige Startprobleme

| Problem | Ursache | Lösung |
|---------|---------|--------|
| `EADDRINUSE :8000` | Server läuft bereits | PID finden und beenden (siehe 0.3) |
| `EADDRINUSE :5173` | Frontend läuft bereits | PID finden und beenden (siehe 0.3) |
| `ModuleNotFoundError` | Dependencies fehlen | `poetry install` im Server-Ordner |
| `npm ERR!` | Node modules fehlen | `npm install` im Frontend-Ordner |
| `401 Unauthorized` (Loop) | Token korrupt | LocalStorage leeren, neu einloggen |
| `404 Not Found` auf API | Falscher Prefix | Prüfe ob `/api/v1/` im Pfad ist |
| `Queue bound to different event loop` | Python 3.14 Bug | Siehe `Bugs_and_Phases/Bugs_Found_2.md` Bug O |
| `Zugriff verweigert` bei Dienst | Keine Admin-Rechte | PowerShell als Admin öffnen |

### 0.9) Mosquitto MQTT Broker

Mosquitto läuft als **Windows-Dienst** und startet automatisch mit Windows.

```bash
# Dienst-Status prüfen
sc query mosquitto

# Erwartete Antwort:
# STATE: 4 RUNNING

# Dienst neu starten (benötigt Admin-Rechte)
net stop mosquitto && net start mosquitto

# Manuell starten (falls kein Dienst)
"C:\Program Files\mosquitto\mosquitto.exe" -v
```

**Konfigurationsdatei:** `C:\Program Files\mosquitto\mosquitto.conf`

**Standard-Ports:**
- 1883: MQTT (unverschlüsselt)
- 9001: WebSocket (falls konfiguriert)

### 0.10) Kompletter Neustart-Workflow (Copy-Paste Ready)

```bash
# 1. Aktuelle Prozesse finden
netstat -ano | findstr "8000"
netstat -ano | findstr "5173"

# 2. Services beenden (PIDs aus Schritt 1 einsetzen)
# taskkill //PID <SERVER_PID> //F //T
# taskkill //PID <FRONTEND_PID> //F //T

# 3. Server starten (Background)
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Servador/god_kaiser_server" && poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 4. Warten (5 Sekunden)
sleep 5

# 5. Frontend starten (Background)
cd "c:/Users/PCUser/Documents/PlatformIO/Projects/Auto-one/El Frontend" && npm run dev

# 6. Verifizieren
curl -s http://localhost:8000/api/v1/auth/status
```

### 0.11) Voraussetzungen prüfen

```bash
# Working Directory muss Auto-one sein
pwd
# → c:\Users\PCUser\Documents\PlatformIO\Projects\Auto-one

# Poetry muss installiert sein (für Server)
poetry --version

# Node.js muss installiert sein (für Frontend)
node --version
npm --version
```

---

## 1) Architektur-Überblick
- **Vue 3 + Pinia + Vite + TypeScript** – State in Pinia, Routing via `vue-router`.
- **Axios mit JWT-Interceptor** – Refresh bei 401, Retry des Original-Requests; Logout & Redirect bei fehlgeschlagenem Refresh.
- **REST**: Proxy `/api` → `http://localhost:8000/api/v1`. Vollständige API-Abdeckung (Auth, Debug, Database, Logs, Users, Config, LoadTest).
- **WebSocket**: Proxy `/ws` → `ws://localhost:8000`. MQTT-Log über `/ws/realtime/{client_id}?token=...`.
- **Styling**: Tailwind CSS Dark Theme, Utility-Klassen in `src/style.css`.

## 2) Auth Flow (Frontend ↔ Server)
- Initial: `authStore.checkAuthStatus()` prüft `/auth/status` → entscheidet `/setup` vs. `/login`.
- Login/Setup: `authApi.login/setup` speichern `access_token` + `refresh_token` in `localStorage`, anschließend `authApi.me` für User-Daten.
- Axios-Interceptor: hängt `Authorization: Bearer <access>` an; bei 401 → `refreshTokens()` → wiederholt Request; sonst Logout + Redirect `/login`.
- Router-Guards: `requiresAuth` und `requiresAdmin` setzen Navigation durch; Setup-Zwang vor Login.

## 3) Debug REST Flows (Mock ESP)
Alle Aufrufe sind in `src/api/debug.ts` typisiert; State in `src/stores/mockEsp.ts` wird nach jeder Mutation per `getMockEsp` aktualisiert (Single Source of Truth = Server).

- **Mock ESP CRUD**: `createMockEsp`, `listMockEsps`, `getMockEsp`, `deleteMockEsp`.
- **Heartbeat & State**: `triggerHeartbeat`, `setState`, `setAutoHeartbeat`.
- **Sensoren**: `addSensor`, `setSensorValue`, `setBatchSensorValues`.
- **Aktoren**: `addActuator`, `setActuatorState`.
- **Safety**: `emergencyStop`, `clearEmergency`.
- **History**: `getMessages`, `clearMessages` (MQTT-Verlauf pro ESP).

UI-Abbildung:
- **MockEspView**: Create/Refresh/Delete/State-Toggle/Heartbeat, Grid-Übersicht, Admin-only Route.
- **MockEspDetailView**: Herzstück für Einzel-ESP – Safe Mode Toggle, Emergency Stop/Clear, Sensorwerte editieren, Aktoren toggeln, Sensor/Aktor hinzufügen.
- **SensorsView / ActuatorsView**: Aggregierte Listen über alle ESPs; ActuatorsView bietet globalen Emergency Stop über alle Geräte.

## 4) MQTT Live Log (WebSocket)
- Einstieg: `src/views/MqttLogView.vue` öffnet WS gegen `/ws/realtime/{client_id}?token=<jwt>`.
- Nach `onopen`: `subscribe`-Message mit allen `MessageType`-Filtern.
- Eingehende Nachrichten werden gepuffert (max 500, neu oben), Pausen-Toggle stoppt nur UI-Verarbeitung.
- **Token-Robustheit**: Vor Connect wird `ensureAuthToken()` aufgerufen → nutzt frischen Access-Token oder `refreshTokens()`; bei Fehlschlag Logout+Redirect. Reconnect nach Close (3s) holt erneut ein gültiges Token.

## 5) Typen & States (Kanonisch)
- Zentral in `src/types/index.ts`: `MockSystemState`, `MockSensor`, `MockActuator`, `MqttMessage`, `LogicRule` (für spätere Logic-Engine), Qualitätsstufen, API-Response-Typen.
- Frontend nutzt diese Typen in API-Layern und Stores, um Server-Schema 1:1 abzubilden.

## 6) Last- & Cross-Device-Tests
- Viele ESPs/Sensoren/Aktoren können über `MockEspView` erzeugt werden; Batch-Sensor-Set (`setBatchSensorValues`) erlaubt schnelle Simulation hoher Frequenz.
- MQTT-Log skaliert in der UI bis 500 Einträge; für längere Sessions ggf. filterbasiert einschränken (MessageType/ESP/Topic).
- Notfall: Globaler E-Stop über ActuatorsView (`emergencyStopAll` via Store-Schleife) hält Konsistenz mit Backend-Safety-Pfaden.

## 7) Logic Engine (Stand & TODO)
- `LogicView.vue` ist bewusst ein Placeholder; bereit für Anbindung an künftige `/v1/logic` Endpunkte.
- Typen (`LogicRule`, `LogicCondition`, `LogicAction`, `LogicExecution`) sind vorbereitet, damit spätere REST/WS-Integration minimalen Umbau erfordert.

## 8) Bekannte Grenzen / nächste sinnvolle Schritte
- WS: Aktuell kein gestaffelter Backoff oder Topic-basierte Re-Subscriptions nach Filterwechsel (wird clientseitig initial gesetzt). Bei Bedarf Re-Subscribe-UI hinzufügen.
- LogicView: Kein CRUD/UI; sobald Server-API stabil, Routen/Store/API-Module ergänzen und gleiche Auth/Refresh-Mechanik wiederverwenden.
- Charts: `chart.js`/`vue-chartjs` sind installiert, aber ungenutzt. Eignen sich für KPI/Trend-Visualisierung (z. B. Sensorverläufe).

## 9) Verknüpfte Referenzen
- Server API & MQTT: `.claude/skills/server/CLAUDE_SERVER.md`
- ESP32 Firmware: `.claude/skills/esp32/CLAUDE_Esp32.md`
- Frontend Skill: `.claude/skills/Frontend/CLAUDE_FRONTEND.md`
- Log-System: `.claude/reference/debugging/LOG_LOCATIONS.md`
- MQTT Protokoll: `El Trabajante/docs/Mqtt_Protocoll.md`


