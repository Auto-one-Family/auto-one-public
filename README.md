# AutomationOne

AutomationOne is a local stack for continuous environmental monitoring in
protected cropping and related spaces — climate, substrate, and nutrient
solution — plus the actuators on the same nodes. ESP32 firmware reads sensors
and drives pumps, valves, PWM, and relays. A FastAPI server stores UTC time
series and runs rules. A Vue interface shows live and historical data and lets
you assign pins and places without flashing.

This repository is a **public mirror** of a running system — not a frozen demo
dataset or a marketing one-pager without code.

---

## Why place matters

*A reading without a place is just a name.*

The same temperature in canopy air, at the bench edge, or in the slab is not the
same measurement. AutomationOne treats **place as part of the setup**:

| Level | Role |
|-------|------|
| **Zone** | House or climate context |
| **Subzone** | Air volume, substrate bed, or solution circuit |
| **Mount metadata** (when set) | Height, medium (`air` \| `canopy` \| `substrate` \| `solution`), angle |

**Place contract (canonical):**

- **Physical mounting** — height, medium, angle, subzone assignment — lives on
  the **sensor config**, not on individual time-series rows.
- **Crop context** — growth phase, variety, trial design — lives on the
  **zone** or **plant**, not on a GPIO pin.

Two houses can be compared later only when both *where* and *how* are
documented — not inferred from a sensor nickname.

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
runs rules, and applies a safety chain. The interface shows live and historical
data and lets an operator assign pins and places.

| Layer | Stack | Role |
|-------|--------|------|
| **El Trabajante** | C++ / PlatformIO / ESP32 | Read sensors; drive pumps, valves, PWM and relays; publish over MQTT |
| **El Servador** | Python / FastAPI / PostgreSQL / MQTT | Store UTC time series, distribute config, run rules and the safety chain |
| **El Frontend** | Vue 3 / TypeScript | Show live and history; assign pins and places without flashing |

Data path: ESP32 publishes over MQTT → FastAPI writes PostgreSQL → Vue updates
over HTTP and WebSocket.

Intelligence sits primarily on the server. ESP32 nodes capture and switch.
Sensor types, rules, and processing are configured centrally — after initial
setup, pin and place assignments do not require a firmware reflash.

### How a reading is stored

Readings are a PostgreSQL time series in UTC. Each row **snapshots zone and
subzone at write time**; later config changes do not rewrite older rows.

Mount fields (`mount_height_cm`, `mount_medium`, `mount_angle_deg`) live on the
sensor config. Charts join the current config for labels — for example
`Substrate (%) · Z1 / SZ-A · 30cm canopy` — but historical mount metadata is
not retroactively stamped onto past samples.

Per-sensor settings include:

- **`measurement_interval`** — interval on the sensor config, not a global tick
- **`operating_mode`** — e.g. `continuous` vs `on_demand` (spot reads for pH/EC)
- **`calibration_data`** — slope/offset coefficients from a two-point wizard;
  optional validity timestamp on the blob; `adc_source` (`internal` \| `ads1115`)
  for analog acquisition path

Raw values arrive from firmware; calibration and unit conversion run on the
server via type-specific processors.

---

## Hardware and sensors

Current deployments use **accessible ESP32 boards and low-cost IoT modules**
(DFRobot, Grove, Seeed, and similar). These are hobby- to prosumer-grade
instruments — not NIST-traceable laboratory reference devices. That trade-off is
deliberate: the stack is built to produce **continuous, place-annotated time
series** with a consistent metadata model, while leaving room to swap probes
without rewriting the architecture.

Sensor **types** and **calibration** are abstracted from vendor SKU. The same
`ph` type can be served by different probe hardware; comparability depends on
documented placement and calibration, not on the sensor nickname.

| Measurement | Typical physical module | Bus / path | Caveats |
|-------------|-------------------------|------------|---------|
| Air temp + RH | SHT31 (often on DFRobot/Grove I²C boards) | I²C | Good for zone climate; spatial variability is real |
| Temperature | DS18B20 | OneWire | Substrate or air probe depending on placement |
| CO₂ | SEN0220-class NDIR or similar | UART / I²C per driver | Warm-up and placement affect baseline |
| Substrate moisture | SEN0193-class capacitive | Analog (internal ADC or ADS1115) | Representative volume is cm-scale, not the whole bench |
| pH / EC | SEN0169 / DFR0300-class probes | Analog via **internal ESP32 ADC or ADS1115** — acquisition path, not a separate sensor type | Spot / on-demand immersion suits lab-style probes; continuous 24/7 immersion needs industrial-rated hardware |
| Pressure / ambient temp | BMP280 / BME280 | I²C | Environment reference |
| Light intensity | Typed server-side; firmware driver pending | I²C candidates (BH1750, VEML7700, …) | **Lux ≠ PPFD/PAR** — do not treat lux readings as photosynthetic flux without conversion |
| Flow, fill level | Pulse / analog generics | Digital or ADC | Application-specific |

**ADS1115:** Optional 16-bit I²C ADC for pH, EC, and other analog channels —
selectable per sensor config instead of the ESP32 internal ADC. The
`adc_source` value comes from the calibration/config blob, not a standalone
time-series column.

**VPD:** Derived on the server from an SHT31 temperature/humidity pair in the
same zone; stored and displayed like a sensor reading.

Firmware drivers today cover SHT31, BMP280, BME280, DS18B20, analog pH/EC/moisture
(with internal ADC or ADS1115), UART CO₂, pulse flow, and digital fill level.
Light intensity is registered on the server and in the UI; an end-to-end firmware
driver is the next step.

---

## Operator surface

An operator assigns sensors and actuators to GPIO and subzone in one hardware
view — zone → device → pin — without flashing firmware for that assignment.

**Actuator types:** pump, valve, PWM, relay — on the same nodes that measure.

**Rules** can fire across ESP boundaries: if sensor X crosses a threshold,
actuator Y runs. Offline rules stay on the ESP when the MQTT link is down.
A new ESP is discovered from its heartbeat and waits for approval before it is
trusted.

**Actuator commands** pass through a server safety chain: emergency stop, GPIO
conflict detection, loop detection, and rate limiting. The ESP applies local
checks as well.

**Charts** group live and historical data by zone and subzone. Dataset labels
carry name, unit, zone/subzone, and mount fields when set.

Authentication uses JWT after first-run setup; role-based guards restrict admin
and zone-scoped operations. There is no multi-tenant site registry in this
mirror — one installation, many zones.

---

## Crop and plant context

AutomationOne is moving from room monitoring toward **crop-aware monitoring**:
continuous environmental time series anchored to **where** (zone, subzone,
mount) and increasingly to **what** (plant and crop context), so growth response
can be compared across positions and, eventually, sites.

**In the codebase today:**

- Zone / subzone hierarchy for all time series
- **`zone_contexts`** — zone-level crop metadata (plant count, variety, substrate,
  growth phase, cycle history) maintained by the operator
- **`plants`** — individual plant records under a subzone (identity, phase,
  optional QR code, lifecycle events); REST API and UI views present
- **`operating_mode`** and per-sensor **`measurement_interval`** — continuous
  vs on-demand reads (e.g. pH/EC spot measurements)
- **`plan_segments`** — planned setpoints (EC, pH, temperature, humidity) stored
  as a separate layer from measured time series; rules can opt in to follow plans
- Rules, actuators, and safety chain as described above

**Direction (not fully productized):**

- **Observations** — a unified ledger for manual notes and instrument snapshots
  tied to plant or zone
- **Plant-derived zone KPIs** — aggregating zone context from individual plants
  instead of manual zone-only fields
- **Multi-rate fusion** — air, substrate, solution, and plant-linked signals at
  different intervals, joined by time and place metadata

---

## Measured quantities

Grouped by domain; sensor **type** in config maps to firmware driver and server
processor (see hardware table above).

1. **Air:** temperature, humidity, CO₂, air pressure, derived VPD
2. **Substrate:** moisture, temperature
3. **Nutrient solution:** pH, EC
4. **Also supported:** flow, light intensity (server/UI; firmware driver pending),
   fill level, generic analog/digital

---

## Engineering direction

Long term, the system must keep measurement series **comparable over months to
years**, support **multiple sites** without guessing from nicknames, and make
data **accessible** (export, APIs) while **securing** who can read and write what.

Current priorities, in order:

1. **Operator UX** — place metadata, hardware tree, charts, plant views, honest
   live / stale / on-demand states; making the data model legible without flashing
2. **Data access and security** — permissions across zones and installations
3. **Scientific comparability metadata** — calibration events, QC flags, site
   identity, schema-bearing export

These are known gaps within the existing architecture — not reasons to rebuild
from scratch, and not solved yet.

Raw CSV export (`/api/v1/sensors/export`) and component JSON export
(`/api/v1/export/*`) exist today. They are operational exports, not a
standardized scientific interchange format.

---

## What this repo does not claim (yet)

Gaps are **design constraints**, not apologies. The foundation — place-aware
time series, flexible config, server-side processing — is in place; metadata
depth and operator UX are the next levers.

- No first-class **calibration event** row (reference standard, operator, validity
  window) — only coefficients in a config blob plus a wizard
- No per-sample **QC flag** (offline, range, missing) on time-series rows
- No **site / facility identifier** for comparing house A vs house B — zone lives
  within one installation
- No **scientific export schema** (MIAPPE, QUDT, JSON-LD) — PostgreSQL is the
  source of truth; CSV and component JSON are available
- Light intensity type exists server-side; **end-to-end firmware driver** still
  pending
- **Observation workflows** and plant analytics across sites — direction, not
  a finished product surface in this mirror
- Does not assert laboratory accuracy from low-cost modules — **metadata and
  placement** are the comparability lever

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
