# AutomationOne

**Full-stack IoT automation framework for greenhouse and indoor grow monitoring.**

Built on a strict server-centric architecture: ESP32 firmware acts as dumb data collectors,
a FastAPI backend handles all intelligence, and a Vue 3 dashboard provides the control surface.

```
El Frontend (Vue 3)  ←── HTTP/WebSocket ──→  El Servador (FastAPI)  ←── MQTT ──→  El Trabajante (ESP32)
```

---

## Architecture

### Three-Layer Design

| Layer | Tech | Role |
|-------|------|------|
| **El Trabajante** (firmware) | C++ / PlatformIO / ESP32-S3 | Sensor data collection, actuator control |
| **El Servador** (backend) | Python / FastAPI / PostgreSQL | Business logic, MQTT broker, REST API, WebSocket |
| **El Frontend** (dashboard) | Vue 3 / TypeScript / Pinia / Tailwind | Hardware monitoring, sensor config, live data |

### Data Flow

```
ESP32 → MQTT publish → FastAPI handler → PostgreSQL
                                        ↓
                              WebSocket broadcast
                                        ↓
                              Vue 3 Dashboard (live update)
```

### Supported Hardware

- **Sensors (10 types):** pH, EC, Temperature, Humidity, Soil moisture, Pressure, CO₂, Light intensity, Flow rate, Liquid level
- **Actuators (4 types):** Pump, Valve, PWM (LED/fans), Relay
- **Boards:** ESP32 DevKit, ESP32-S3 DevKitC-1, Seeed XIAO ESP32C3

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Firmware | C++17, PlatformIO, FreeRTOS, ArduinoJson, PubSubClient |
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16, 41 tables |
| Message broker | MQTT (Mosquitto) |
| Frontend | Vue 3, TypeScript, Pinia, Vite, Tailwind CSS, Chart.js |
| Monitoring | Prometheus, Grafana, Loki |
| Testing | pytest, Playwright, Vitest, Wokwi (ESP32 simulation) |
| CI | GitHub Actions |
| Containerization | Docker Compose |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- (Optional) PlatformIO for firmware flashing

### 1. Clone and configure

```bash
git clone https://github.com/Auto-one-Family/auto-one-public.git
cd auto-one-public
cp .env.example .env
# Edit .env with your values
```

### 2. Start the stack

```bash
docker compose up -d
```

Services started:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Grafana: http://localhost:3000
- pgAdmin: http://localhost:5050

### 3. Flash ESP32 firmware (optional)

```bash
cd "El Trabajante"
# Configure NVS secrets first (see El Trabajante/secrets/README.md)
pio run -e esp32_dev --target upload
```

---

## Project Structure

```
auto-one-public/
├── El Trabajante/          # ESP32 firmware (C++ / PlatformIO)
│   ├── src/                # Source: managers, drivers, services
│   ├── secrets/            # NVS secrets (*.csv.example — fill in values)
│   ├── diagram.json        # Wokwi circuit simulation
│   └── platformio.ini      # Build config
├── El Servador/            # FastAPI backend
│   └── god_kaiser_server/
│       ├── src/            # API, MQTT handlers, services, models
│       ├── tests/          # pytest unit + integration + E2E tests
│       └── alembic/        # Database migrations
├── El Frontend/            # Vue 3 dashboard
│   └── src/
│       ├── components/     # UI components (hardware view, sensors, actuators)
│       ├── stores/         # Pinia state management
│       ├── composables/    # Reusable Vue composables
│       └── views/          # Route-level views
├── .github/workflows/      # CI: build, test, E2E, Playwright visual regression
├── docker-compose.yml      # Production stack
├── docker-compose.dev.yml  # Development overrides
└── docker-compose.ci.yml   # CI stack
```

---

## AI-Agent Architecture

AutomationOne is developed and operated using a fleet of **14 specialized Claude Code agents**. Each agent has a defined scope, explicit skill definitions, and mandatory build verification after every change.

| Agent type | Role |
|-----------|------|
| `esp32-dev` | ESP32 firmware — sensors, actuators, GPIO, NVS, MQTT |
| `server-dev` | FastAPI — handlers, repositories, services, schemas |
| `frontend-dev` | Vue 3 — components, composables, Pinia stores, WebSocket |
| `mqtt-dev` | MQTT protocol — topics, publishers, subscribers, QoS |
| `esp32-debug` | Serial log analysis, boot diagnostics, hardware faults |
| `server-debug` | FastAPI log analysis, error codes 5000–5699, circuit breaker |
| `frontend-debug` | TypeScript build errors, WebSocket events, auth flows |
| `mqtt-debug` | Topic hierarchy, payload validation, QoS behavior |
| `db-inspector` | PostgreSQL schema, migrations, data integrity |
| `meta-analyst` | Cross-layer code analysis, developer handoffs |
| `auto-debugger` | Incident orchestration, TASK-PACKAGES, verify-plan gate |
| `test-log-analyst` | pytest / Playwright / Vitest / Wokwi log analysis |
| `system-control` | Session briefing, Docker operations |
| `technical-manager` | Cross-layer coordination, Linear issue management |

**Key workflow:** Each agent runs after a dedicated skill loads context → implements changes → runs build verification → commits only on green. A `verify-plan` gate prevents any generated code from reaching production without a reality-check pass against the actual codebase.

---

## Development

### Build verification

```bash
# ESP32 firmware
cd "El Trabajante" && pio run -e esp32_dev

# Backend tests
cd "El Servador/god_kaiser_server" && pytest --tb=short -q

# Backend lint
cd "El Servador/god_kaiser_server" && ruff check .

# Frontend build
cd "El Frontend" && npm run build

# Frontend type check
cd "El Frontend" && npx vue-tsc --noEmit
```

### Environment setup

```bash
cp .env.example .env
cp "El Servador/god_kaiser_server/.env.example" "El Servador/god_kaiser_server/.env"
cp "El Trabajante/secrets/nvs_secrets.dev-local.csv.example" "El Trabajante/secrets/nvs_secrets.dev-local.csv"
# Fill in values in each file
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
