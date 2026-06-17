# El Frontend - AutomationOne Control Panel

> **Vue 3 + TypeScript + Tailwind CSS Control Panel**
> **Status:** Ready for Development

## Features

- **Authentication**: Login, Setup, JWT Token Auto-Refresh
- **Mock ESP Management**: Virtuelle ESP32-Geräte erstellen und steuern
- **Sensor Simulation**: Sensor-Werte simulieren und MQTT-Messages triggern
- **Actuator Control**: Aktoren steuern mit Emergency Stop
- **MQTT Live Log**: Echtzeit-Anzeige aller MQTT-Messages via WebSocket
- **Logic Engine**: Automation-Rules testen

## Technologie-Stack

- **Vue 3** (Composition API + `<script setup>`)
- **TypeScript** (Type Safety)
- **Tailwind CSS** (Dark Theme)
- **Pinia** (State Management)
- **Vite** (Build Tool)
- **Axios** (REST API mit JWT Interceptors)
- **Lucide Vue** (Icons)

## Setup

```bash
# 1. Node.js installieren (falls nicht vorhanden)
# https://nodejs.org/ (LTS Version empfohlen)

# 2. Dependencies installieren
cd "El Frontend"
npm install

# 3. Development-Server starten
npm run dev

# 4. Browser öffnen: http://localhost:5173
```

## Server Requirements

Der God-Kaiser Server muss laufen:

```bash
cd "El Servador/god_kaiser_server"
poetry run uvicorn src.main:app --reload
```

**Endpoints:**
- REST API: `http://localhost:8000/api/v1/`
- WebSocket: `ws://localhost:8000/ws/realtime/{client_id}`
- Debug API: `http://localhost:8000/api/v1/debug/mock-esp/`

## Views

| Route | Beschreibung |
|-------|-------------|
| `/login` | Login-Seite |
| `/setup` | Initial Admin Setup |
| `/` | Dashboard |
| `/mock-esp` | Mock ESP Manager |
| `/mock-esp/:id` | Mock ESP Details |
| `/sensors` | Komponenten-Tab (Inventar/Wissensdatenbank); volle Konfiguration in `/hardware` |
| `/hardware` | Übersicht: Zone/ESP-Topologie; SensorConfigPanel/ActuatorConfigPanel nur hier |
| `/actuators` | Actuator Control |
| `/mqtt-log` | MQTT Live Log |
| `/logic` | Logic Rules |
| `/settings` | Settings |

## Dokumentation

- **Server API:** `../.claude/CLAUDE_SERVER.md`
- **ESP32 Firmware:** `../.claude/CLAUDE.md`
- **MQTT Protocol:** `../El Trabajante/docs/Mqtt_Protocoll.md`
- **Frontend Debug Architektur & Flows:** `./Docs/DEBUG_ARCHITECTURE.md` (Auth, REST/WS-Flows, Mock-ESP-Pfade, Lasttests, Logic-Placeholder)