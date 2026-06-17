# Debug Scripts

> **Zweck:** Helper-Scripts für Debug-Sessions
> **Version:** 4.1 | **Aktualisiert:** 2026-02-25

## start_session.sh (v4.0)

Primary debug session script using Docker-based workflow.

### Usage

```bash
./scripts/debug/start_session.sh [session-name] [--with-server] [--mode MODE]
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `session-name` | Name for the session | `debug` |
| `--with-server` | Start server if not running | - |
| `--mode MODE` | Test mode: `boot`, `config`, `sensor`, `actuator`, `e2e` | `boot` |

### Features (v4.0)

- **Docker-Stack Health-Check:** Verifies Docker containers instead of local services
- **MQTT-Capture with Timestamps:** `mosquitto_sub` via Docker exec with ISO timestamps
- **Log-Archivierung:** Archives previous session logs to `logs/archive/`
- **Extended STATUS.md:** Includes Docker container details for agents

### Output Files

| File | Description |
|------|-------------|
| `logs/current/mqtt_traffic.log` | MQTT traffic with timestamps |
| `logs/current/STATUS.md` | Agent context file |
| `logs/current/god_kaiser.log` | Symlink to server log |

### Examples

```bash
# Basic boot test
./scripts/debug/start_session.sh boot-test

# Sensor test session
./scripts/debug/start_session.sh sensor-test --mode sensor

# Full E2E test with server start
./scripts/debug/start_session.sh e2e-test --mode e2e --with-server
```

## stop_session.sh

Stops the debug session and archives all logs.

```bash
./scripts/debug/stop_session.sh
```

### Actions

1. Stops MQTT capture process
2. Stops server (if started with `--with-server`)
3. Archives logs → `logs/archive/{session_id}/`
4. Archives reports → `.claude/reports/archive/{session_id}/`
5. Clears `logs/current/` and `reports/current/`

## debug-status.ps1

Aggregated system health check. Returns JSON with status of all core services.

### Usage

```powershell
powershell -ExecutionPolicy Bypass -File scripts/debug/debug-status.ps1
```

### Checks

| Service | What | Endpoint |
|---------|------|----------|
| Docker | Container running | `docker compose ps` |
| Server | HTTP reachable | `http://localhost:8000/api/v1/health/live` |
| MQTT | Broker port open | `localhost:1883` |
| PostgreSQL | Accepts connections | `docker exec pg_isready` |
| Loki | Ready state | `http://localhost:3100/ready` |
| Grafana | API health | `http://localhost:3000/api/health` (Basic auth) |

### Output

```json
{
  "timestamp": "2026-02-25T10:00:00",
  "overall": "ok",
  "services": { "docker": {...}, "server": {...}, ... },
  "issues": []
}
```

`overall` is `"ok"` when all services are green, `"degraded"` or `"critical"` otherwise.

### Notes

- Uses `System.Net.WebClient` fallback for localhost HTTP (bypasses WinHTTP proxy issues)
- Grafana check includes Basic auth (`admin:admin`)
- Recommended as first step in any debug session

## loki-query (Loki API Wrapper)

Loki-Logs abfragen. **Voraussetzung:** `make monitor-up` (Loki auf localhost:3100).

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/loki-query.ps1 errors 5
powershell -ExecutionPolicy Bypass -File scripts/loki-query.ps1 trace <correlation-id>
powershell -ExecutionPolicy Bypass -File scripts/loki-query.ps1 esp <esp-id>
powershell -ExecutionPolicy Bypass -File scripts/loki-query.ps1 health
```

### Linux/Mac (Bash)

```bash
bash scripts/loki-query.sh errors 5
bash scripts/loki-query.sh trace <correlation-id>
bash scripts/loki-query.sh esp <esp-id>
bash scripts/loki-query.sh health
```

### Mit Make (wählt automatisch passendes Script)

```bash
make loki-errors
make loki-trace CID=<id>
make loki-esp ESP=<id>
make loki-health
```

## Log Directories

| Directory | Content |
|-----------|---------|
| `logs/server/` | Server JSON-Logs (Docker bind-mount) |
| `logs/mqtt/` | Deaktiviert (stdout-only); Broker-Logs via Loki `compose_service=mqtt-broker` |
| (kein Bind-Mount) | PostgreSQL: `docker compose logs postgres` oder Loki `{compose_service="postgres"}` |
| `logs/esp32/` | ESP32 Serial-Logs (manual) |
| `logs/current/` | Session-Logs (via start_session.sh) |
| `logs/archive/` | Archived session logs |
