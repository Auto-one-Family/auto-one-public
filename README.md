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
# Fill in values. Keep CHANGE_ME keys and empty optional keys until you set them.
```

### 2. Start the stack

```bash
docker compose up -d
```

Typical local ports after compose (from the compose files in this tree):

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

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
├── docker-compose.yml
├── docker-compose.dev.yml
└── docker-compose.ci.yml
```

---

## License

MIT License — see [LICENSE](LICENSE).
Copyright (c) 2026 Robin Herbig.
