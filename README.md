# AutomationOne

Own acquisition system for environmental time series in protected horticulture
(greenhouse, polytunnel, and indoor horticulture climate).

Firmware measures, the server stores, the interface shows readings and lets
an operator configure devices in space.

A reading is bound to a **zone** (the house or climate context) and a
**subzone** (the place inside that zone — air volume, substrate, or
solution circuit).

```
El Trabajante (ESP32)
        │ MQTT
        ▼
El Servador (FastAPI + PostgreSQL)
        │ HTTP / WebSocket
        ▼
El Frontend (Vue)
```

---

## Architecture

Three layers. The device collects readings, the server persists them, the
interface shows them and lets an operator assign devices to places.

| Layer | Stack | Role |
|-------|--------|------|
| **El Trabajante** | C++ / PlatformIO / ESP32 | Measure and publish environmental readings |
| **El Servador** | Python / FastAPI / PostgreSQL / MQTT | Store UTC time series and serve them |
| **El Frontend** | Vue 3 / TypeScript | Show live and history; configure devices in space |

Data path: ESP32 publishes over MQTT, FastAPI writes PostgreSQL, the Vue
interface updates over HTTP and WebSocket.

Readings are a PostgreSQL time series in UTC. Each row carries zone and
subzone. The measurement interval is configurable per sensor. Calibration
uses slope/offset coefficients and a two-point wizard.

---

## Operator surface

An operator assigns sensors and actuators to GPIO and subzone in the
interface — zone → device → pin — without flashing firmware for that
assignment. Live and historical readings are shown by zone and subzone.

Actuator types in this tree: pump, valve, PWM, relay. They are
configurable nodes on the same hardware view.

---

## Measured quantities

1. **Air:** temperature, humidity, CO₂, air pressure
2. **Substrate:** moisture, temperature
3. **Nutrient solution:** pH, EC
4. **Also in this tree:** flow, light intensity, fill level

Light intensity is typed on the server and in the interface. The next
step is a firmware driver so the type is end-to-end.

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) PlatformIO to flash firmware

### 1. Clone and configure

```bash
git clone https://github.com/Auto-one-Family/auto-one-public.git
cd auto-one-public
cp .env.example .env
```

Replace every `CHANGE_ME_USE_STRONG_PASSWORD` with the same strong password in `POSTGRES_PASSWORD`, `DB_BACKUP_PG_PASSWORD`, and `DATABASE_URL`. Replace `CHANGE_ME_GENERATE_SECURE_KEY` with a JWT secret.

The shipped `docker/mosquitto/passwd` matches the example `MQTT_*` placeholders. If you change `MQTT_*`, regenerate `docker/mosquitto/passwd`.

Leave `COMPOSE_PROFILES` empty so `docker compose up -d` starts the core stack. Monitoring is optional:

```bash
COMPOSE_PROFILES=monitoring docker compose up -d
```

On Docker Desktop Windows, that profile pulls node-exporter with rslave and compose exits 1.

### 2. Start the stack

```bash
docker compose up -d
docker compose ps
```

`docker compose ps` should show el-frontend, el-servador, postgres, and mqtt healthy or running.

Then open:

- Frontend: http://127.0.0.1:5173
- Backend API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Live health: http://127.0.0.1:8000/api/v1/health/live

Those URLs answered HTTP 200. `localhost` on the same ports timed out on a Windows IPv6 stack — if `localhost` hangs, use `127.0.0.1`.

The first visit to the UI goes to `/setup` to create the first admin.

### 3. Flash ESP32 firmware (optional)

```bash
cd "El Trabajante"
# Copy the generic NVS example and fill PLACEHOLDER_* values
# (see El Trabajante/secrets/README.md)
pio run -e esp32_dev --target upload
```

---

## Project Structure

```
auto-one-public/
├── El Trabajante/          # ESP32 firmware (C++ / PlatformIO)
│   ├── src/
│   └── secrets/            # NVS examples (localhost + PLACEHOLDER_*)
├── El Servador/            # FastAPI backend
│   └── god_kaiser_server/
│       ├── src/
│       ├── tests/
│       └── alembic/
├── El Frontend/            # Vue 3 interface
├── docker/                 # compose bind-mounts (mosquitto, postgres, ...)
├── docker-compose.yml
├── docker-compose.dev.yml
└── docker-compose.ci.yml
```

---

## License

MIT License — see [LICENSE](LICENSE).
Copyright (c) 2026 Robin Herbig.
