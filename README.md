# AutomationOne

AutomationOne is a local stack for horticultural climate, substrate and
nutrient measurements — and for the devices that sit on the same nodes.
Firmware on ESP32 reads sensors and drives pumps, valves, PWM and relays.
A FastAPI server stores UTC time series and runs rules. A Vue interface
shows live and history and lets you assign pins and places without flashing.

A reading without a place is just a name. The same temperature in canopy
air, at the bench edge, or in the slab is not the same measurement. This
system therefore treats place as part of the setup: a zone (the house or
climate context), a subzone (air volume, substrate or solution circuit),
and, when you set them, mount height, medium and angle. The number stays
attached to how and where it was taken, so two houses can be compared
later without guessing the probe position from a sensor nickname.

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

Three layers. Firmware measures and switches. The server stores readings,
runs rules, and applies a safety chain. The interface shows live and
history and lets an operator assign pins and places.

| Layer | Stack | Role |
|-------|--------|------|
| **El Trabajante** | C++ / PlatformIO / ESP32 | Read sensors; drive pumps, valves, PWM and relays; publish over MQTT |
| **El Servador** | Python / FastAPI / PostgreSQL / MQTT | Store UTC time series, distribute config, run rules and the safety chain |
| **El Frontend** | Vue 3 / TypeScript | Show live and history; assign pins and places without flashing |

Data path: ESP32 publishes over MQTT, FastAPI writes PostgreSQL, the Vue
interface updates over HTTP and WebSocket.

### How a reading is stored

Readings are a PostgreSQL time series in UTC. Each row snapshots zone and
subzone at write time. The measurement interval lives on the sensor
config, not as a global tick. Calibration is slope/offset coefficients
and a two-point wizard; a nullable validity timestamp can sit on that
blob. Mount height, medium (`air` | `canopy` | `substrate` | `solution`)
and angle live on the sensor config. Charts join the config for labels.
Changing the config later does not rewrite the mount history of older
rows.

---

## Operator surface

An operator assigns sensors and actuators to GPIO and subzone in the
same hardware view — zone → device → pin — without flashing firmware for
that assignment.

Actuator types in this tree: pump, valve, PWM, relay. They sit on the
same nodes that measure.

Rules can fire across ESP boundaries: if sensor X crosses a threshold,
actuator Y runs. Offline rules stay on the ESP when the link is down.
A new ESP is discovered from its heartbeat and waits for approval
before it is trusted.

Actuator commands go through a server safety chain. The checks in this
tree are emergency stop, GPIO conflict, loop detection, and rate limit.
The ESP applies local checks as well.

Live and historical charts are grouped by zone and subzone. A dataset
label carries name, unit, and zone/subzone. When mount fields are set
on the config, the label appends them — for example
`Substrate (%) · Z1 / SZ-A · 30cm canopy`.

---

## Measured quantities

1. **Air:** temperature, humidity, CO₂, air pressure
2. **Substrate:** moisture, temperature
3. **Nutrient solution:** pH, EC (internal ADC or ADS1115 is the
   acquisition path, not a separate sensor type)
4. **Also in this tree:** flow, light intensity, fill level, generic
   analog/digital

VPD is derived on the server from an SHT31 temperature/humidity pair
and appears like a sensor.

Light intensity is typed on the server and in the interface. The next
step is a firmware driver so the type is end-to-end.

---

## What this repo does not claim

This is a public mirror of a running system, not a frozen trial dataset.

It does not record a first-class calibration event with a reference
standard, an operator name, and a validity window as its own row.
It does not flag individual samples for quality.
It has no site identifier for house A versus house B — zone is inside
one installation.
It does not export a scientific schema.

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
