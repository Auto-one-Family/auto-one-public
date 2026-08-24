# AutomationOne

An environmental time-series acquisition system for protected horticulture
(greenhouse, polytunnel, and indoor horticulture climate).

Firmware measures, the server stores, the interface displays.

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
interface shows them.

| Layer | Stack | Role |
|-------|--------|------|
| **El Trabajante** | C++ / PlatformIO / ESP32 | Measure and publish environmental readings |
| **El Servador** | Python / FastAPI / PostgreSQL / MQTT | Store UTC time series and serve them |
| **El Frontend** | Vue 3 / TypeScript | Display live and historical readings |

Data path: ESP32 publishes over MQTT, FastAPI writes PostgreSQL, the Vue
dashboard updates over HTTP and WebSocket.

---

## Measured quantities

Types present in this tree — not a site log and not a running campaign:

1. **Air:** temperature, humidity, CO₂, air pressure
2. **Substrate:** moisture, temperature
3. **Nutrient solution:** pH, EC
4. **Also named in this snapshot:** flow, light intensity, fill level

---

## What this snapshot is

This tree is a snapshot from **2026-06-17**. It documents architecture and
quantity types. It does not document a current experiment series.

- **Calibration.** Slope/offset coefficients and a two-point wizard exist.
  This tree does not record a calibration event against a reference standard,
  with date, validity window, or operator.
- **Sample interval.** The measurement interval is configurable. This
  description does not fix a period.
- **Storage.** Readings are stored as a PostgreSQL time series in UTC.
- **Actuators.** Actuator code exists in the tree. It is not part of this
  public description. This README makes no control or automation promise.

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
