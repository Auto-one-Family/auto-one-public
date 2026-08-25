# ESP32 Serial Logger

**Purpose:** Bridges ESP32 serial output (via TCP) into AutomationOne's Docker monitoring stack (Promtail → Loki → Grafana).

---

## Architecture

```
ESP32 (USB) --> Windows Host (COM3)
                    |
         [usbipd-win: USB-IP Bridge]
                    |
            WSL2 (/dev/ttyUSB0)
                    |
      [socat/ser2net: Serial-to-TCP]
           TCP Port 3333
                    |
    [Docker: esp32-serial-logger]
       Connects to host.docker.internal:3333
       Parses serial output → JSON
                    |
              stdout (JSON)
                    |
       [Promtail: Docker Socket SD]
                    |
                 [Loki]
                    |
               [Grafana]
```

---

## Prerequisites

### 1. USB-IP Bridge (usbipd-win)

**Installation:**
```powershell
# In PowerShell (Admin)
winget install dorssel.usbipd-win
```

**Bind USB device** (one-time, requires Admin):
```powershell
# List devices
usbipd list

# Bind ESP32 device (example BUSID: 1-4)
usbipd bind --busid 1-4
```

**Attach to WSL2** (per session):
```powershell
# Manual attach
usbipd attach --wsl --busid 1-4

# Auto-attach (persistent across reboots)
usbipd attach --wsl --auto-attach --hardware-id <VID:PID>
```

**Find VID:PID:**
- ESP32 WROOM-32 with CP2102: `10c4:ea60`
- ESP32 WROOM-32 with CH340: `1a86:7523`
- XIAO ESP32-C3 (native USB): `303a:1001`

**Verify in WSL2:**
```bash
# In WSL2 terminal
ls -la /dev/ttyUSB* /dev/ttyACM*

# Should show: /dev/ttyUSB0 (CP2102/CH340) or /dev/ttyACM0 (XIAO native USB)
```

**References:**
- [usbipd-win GitHub](https://github.com/dorssel/usbipd-win)
- [Microsoft: Connect USB devices to WSL](https://devblogs.microsoft.com/commandline/connecting-usb-devices-to-wsl/)

---

### 2. Serial-to-TCP Bridge (socat in WSL2)

**Install socat:**
```bash
# In WSL2
sudo apt update && sudo apt install -y socat
```

**Run TCP bridge** (bind to all interfaces so Docker can connect):
```bash
# For CP2102/CH340 boards (ttyUSB0)
socat TCP-LISTEN:3333,fork,reuseaddr,bind=0.0.0.0 /dev/ttyUSB0,raw,echo=0,b115200

# For XIAO ESP32-C3 (ttyACM0)
socat TCP-LISTEN:3333,fork,reuseaddr,bind=0.0.0.0 /dev/ttyACM0,raw,echo=0,b115200
```

**Options explained:**
- `TCP-LISTEN:3333`: Listen on TCP port 3333
- `fork`: Spawn new process per connection (multiple clients allowed)
- `reuseaddr`: Allow rapid restart without "address already in use"
- `bind=0.0.0.0`: Listen on all interfaces (Docker needs this)
- `raw,echo=0`: Raw mode, no echo
- `b115200`: Baud rate 115200 (must match ESP32 `platformio.ini` setting)

**Verify:**
```bash
# In another WSL2 terminal
telnet localhost 3333

# Should see ESP32 serial output
```

**Auto-start socat** (optional, via systemd or cron):
```bash
# Create systemd service: /etc/systemd/system/esp32-serial-bridge.service
[Unit]
Description=ESP32 Serial-to-TCP Bridge
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:3333,fork,reuseaddr,bind=0.0.0.0 /dev/ttyUSB0,raw,echo=0,b115200
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable esp32-serial-bridge
sudo systemctl start esp32-serial-bridge
```

---

## Usage

### Start with Docker Compose

**Profile:** `hardware` (independent from `monitoring` and `devtools`)

```bash
# Start full stack including hardware profile
docker-compose --profile monitoring --profile hardware up -d

# Start only hardware profile (assumes core services running)
docker-compose --profile hardware up -d

# View logs
docker-compose logs -f esp32-serial-logger

# Stop hardware profile
docker-compose --profile hardware down
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_HOST` | `host.docker.internal` | TCP host (ser2net/socat) |
| `SERIAL_PORT` | `3333` | TCP port |
| `DEVICE_ID` | `esp32-unknown` | ESP32 device identifier |
| `LOG_FORMAT` | `structured` | `structured` (JSON) or `passthrough` (raw) |
| `RECONNECT_DELAY` | `5` | Seconds between reconnect attempts |

### Multi-Device Configuration

To monitor multiple ESP32 devices simultaneously:

1. **Run multiple socat instances** (one per device, different ports):
```bash
# Device 1 (ttyUSB0 -> TCP 3333)
socat TCP-LISTEN:3333,fork,reuseaddr,bind=0.0.0.0 /dev/ttyUSB0,raw,echo=0,b115200 &

# Device 2 (ttyUSB1 -> TCP 3334)
socat TCP-LISTEN:3334,fork,reuseaddr,bind=0.0.0.0 /dev/ttyUSB1,raw,echo=0,b115200 &
```

2. **Add additional services** in `docker-compose.yml`:
```yaml
  esp32-serial-logger-01:
    build: ./docker/esp32-serial-logger
    container_name: automationone-esp32-serial-01
    profiles: ["hardware"]
    environment:
      SERIAL_HOST: host.docker.internal
      SERIAL_PORT: "3333"
      DEVICE_ID: "esp32-xiao-01"
    # ... rest of config ...

  esp32-serial-logger-02:
    build: ./docker/esp32-serial-logger
    container_name: automationone-esp32-serial-02
    profiles: ["hardware"]
    environment:
      SERIAL_HOST: host.docker.internal
      SERIAL_PORT: "3334"
      DEVICE_ID: "esp32-wroom-01"
    # ... rest of config ...
```

3. **Promtail automatically discovers** both containers and labels logs with `device` label for filtering in Grafana.

---

## ESP32 Log Formats

The logger parses **4 different ESP32 log formats**:

### Format 1: Custom Logger with TAG (dominant, 1324+ occurrences)
```
[      1234] [INFO    ] [BOOT    ] Logger system initialized
[      5678] [WARNING ] [SENSOR  ] Sensor timeout on GPIO 4
[     12345] [ERROR   ] [MQTT    ] MQTTClient initialization failed!
```
**Pattern:** `[millis] [LEVEL] [TAG] message`

TAGs identify the source module (ESP-IDF convention):
`BOOT`, `SENSOR`, `ACTUATOR`, `MQTT`, `WIFI`, `GPIO`, `CONFIG`, `NVS`, `SAFETY`, `I2C`, `ONEWIRE`, `PWM`, etc.

**JSON Output:**
```json
{
  "timestamp": "2026-02-10T12:00:00Z",
  "level": "info",
  "device_id": "esp32-xiao-01",
  "component": "logger",
  "message": "Logger system initialized",
  "format": "custom_logger",
  "millis": 1234
}
```

### Format 2: Boot Banner (plaintext, unstructured)
```
+========================================+
|  ESP32 Sensor Network v4.0 (Phase 2)  |
+========================================+
Chip Model: ESP32
CPU Frequency: 240 MHz
```
**JSON Output:**
```json
{
  "timestamp": "2026-02-10T12:00:00Z",
  "level": "info",
  "device_id": "esp32-xiao-01",
  "component": "serial",
  "message": "+========================================+",
  "format": "plaintext"
}
```

### Format 3: MQTT Debug JSON (temporary, 127 occurrences)
```
[DEBUG]{"id":"mqtt_connect_entry","timestamp":1234,"message":"MQTT connect() called"}
```
**JSON Output:**
```json
{
  "timestamp": "2026-02-10T12:00:00Z",
  "level": "debug",
  "device_id": "esp32-xiao-01",
  "component": "mqtt",
  "message": "MQTT connect() called",
  "format": "mqtt_debug_json",
  "debug_data": {...}
}
```

### Format 4: ESP-IDF SDK Logs
```
E (1234) wifi: connect failed
W (5678) mqtt: buffer full
```
**JSON Output:**
```json
{
  "timestamp": "2026-02-10T12:00:00Z",
  "level": "error",
  "device_id": "esp32-xiao-01",
  "component": "wifi",
  "message": "connect failed",
  "format": "esp_idf",
  "millis": 1234
}
```

---

## Promtail Integration

**Promtail Stage** (automatically applied via Docker Socket SD):

```yaml
# In docker/promtail/config.yml
- match:
    selector: '{compose_service="esp32-serial-logger"}'
    stages:
      - json:
          expressions:
            level: level
            device: device_id
            component: component
      - labels:
          level:
          device:
          component:
```

**Grafana Query Examples:**
```logql
# All ESP32 logs for a specific device
{compose_service="esp32-serial-logger", device="esp32-xiao-01"}

# Only errors from any device
{compose_service="esp32-serial-logger", level="error"}

# MQTT component logs
{compose_service="esp32-serial-logger", component="mqtt"}

# Search for specific message content
{compose_service="esp32-serial-logger"} |= "MQTT connect"

# Count error rate per device
rate({compose_service="esp32-serial-logger", level="error"}[5m])
```

---

## Troubleshooting

### Container doesn't start
```bash
# Check logs
docker-compose logs esp32-serial-logger

# Common issues:
# - SERIAL_HOST unreachable: Verify socat is running in WSL2
# - SERIAL_PORT closed: Check firewall, socat bind=0.0.0.0
```

### No logs in Grafana
```bash
# 1. Verify container is outputting JSON
docker-compose logs esp32-serial-logger | head -20

# 2. Check Promtail is scraping the service
curl -s http://localhost:9080/targets | jq '.activeTargets[] | select(.labels.compose_service=="esp32-serial-logger")'

# 3. Query Loki directly
curl -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={compose_service="esp32-serial-logger"}' | jq
```

### ESP32 resets when serial connects
**Cause:** DTR/RTS signals trigger bootloader mode on some boards.

**Fix:** Use `local` option in socat (already included in examples above):
```bash
socat TCP-LISTEN:3333,fork,reuseaddr,bind=0.0.0.0 /dev/ttyUSB0,raw,echo=0,b115200,local
```
The `local` flag ignores DTR/RTS signals.

### High log volume overwhelms Loki
**Cause:** ESP32 `main.cpp` produces ~1400-2000 lines/second in DEBUG mode.

**Fix (Option 1):** Set ESP32 log level to WARNING via MQTT command:
```bash
# Via God-Kaiser Server API (when implemented)
curl -X POST http://localhost:8000/api/v1/esp/{esp_id}/command \
  -H "Content-Type: application/json" \
  -d '{"command": "set_log_level", "params": {"level": "WARNING"}}'
```

**Fix (Option 2):** Use Promtail drop stage to filter verbose logs:
```yaml
# Add to promtail config before json stage
- drop:
    source: ""
    expression: '.*LOOP\[\d+\].*'  # Drop LOOP trace messages
```

### USB device disappears in WSL2
**Cause:** USB-IP connection lost or usbipd service stopped.

**Fix:**
```powershell
# Re-attach device
usbipd attach --wsl --busid 1-4

# Or setup auto-attach (persistent)
usbipd attach --wsl --auto-attach --hardware-id 10c4:ea60
```

---

## Performance Considerations

- **CPU:** Negligible (~1% on 4-core system)
- **Memory:** ~20 MB per container
- **Network:** Serial output at 115200 baud ≈ 11.5 KB/s theoretical max
- **Loki Storage:** ~1 MB/hour per device at INFO level, ~50 MB/hour at DEBUG level (before firmware fixes)

---

## Security Notes

- Container runs as **non-root user** (UID 1000)
- No privileged mode required (TCP-based, not USB passthrough)
- No sensitive data in logs (ESP32 only logs operational data)
- Promtail connects to Loki internally (no external exposure)

---

## References

- **ser2net Analysis Report:** `.technical-manager/inbox/agent-reports/ser2net-analysis-2026-02-10.md`
- **MQTT Topics:** `.claude/reference/api/MQTT_TOPICS.md`
- **ESP32 Firmware Logger:** `El Trabajante/src/utils/logger.h` and `logger.cpp`
- **Promtail Docs:** https://grafana.com/docs/loki/latest/send-data/promtail/
