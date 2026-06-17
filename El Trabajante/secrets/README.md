# NVS Secrets

Per-environment MQTT credential files for the ESP32 NVS partition.

**WARNING: Flashing this binary replaces the ENTIRE NVS partition (0x9000, 32KB).
All previously provisioned configs (zone, sensors, actuators) will be erased.
Use only for fresh ESPs or after intentional full-reset.**

## NVS keys (namespace: wifi_config)

| Key | Type | Description |
|-----|------|-------------|
| `ssid` | string | WiFi network name |
| `password` | string | WiFi password |
| `server_address` | string | MQTT broker host |
| `mqtt_port` | u16 | MQTT broker port (default 1883) |
| `mqtt_username` | string | MQTT username (from broker password_file) |
| `mqtt_password` | string | MQTT password |
| `configured` | u8 | Must be 1 — marks config as provisioned |

Keys verified from `config_manager.cpp:236-237` (AUT-764 Phase A).

## Setup

1. Copy the example for your environment:
   ```
   cp nvs_secrets.dev-local.csv.example nvs_secrets.dev-local.csv
   ```

2. Open the `.csv` and replace all `PLACEHOLDER_*` values with real credentials.
   Match the MQTT user/password from your Mosquitto `password_file`.

3. Install the NVS generator (once):
   ```
   pip install esp-idf-nvs-partition-gen
   ```

4. Flash credentials (ESP32 already has firmware):
   ```
   python scripts/esp/flash_nvs.py --env dev-local --port COM5
   ```

   Or complete flash — bootloader + partitions + firmware + NVS in one step (first flash / after factory reset):
   ```
   # Requires: pio run -e esp32_dev first
   python scripts/esp/flash_full.py --env dev-local --port COM5
   ```

   Or generate binary only (no ESP connected):
   ```
   python scripts/esp/flash_nvs.py --env dev-local --generate-only
   ```

## Environments

| Environment | Broker host | Risk | Who flashes |
|-------------|-------------|------|-------------|
| dev-local | localhost | FREE | dev-local-Session, autonomous |
| pi-home | 192.168.0.2 | MEDIUM | Robin via chat block / pi-2-Session |
| pi-elbherb | 192.168.178.67 | STRICT | Robin via chat block (DEFERRED until ESP access) |

## Security

- `.csv` and `.bin` files are gitignored — verify with `git status` before committing
- Only `*.csv.example` files (with placeholders) are tracked
- Credentials must match the `password_file` configured on the MQTT broker (AUT-747)

---

## Pi-home Example (pi-home, Robin — USB attached to Pi)

```bash
# Credentials only (firmware already on device):
python scripts/esp/flash_nvs.py --env pi-home --port /dev/ttyUSB0

# Complete flash — bootloader + partitions + firmware + NVS (first flash / factory reset):
# Requires: pio run -e esp32_dev first (build binaries in .pio/build/esp32_dev/)
python scripts/esp/flash_full.py --env pi-home --port /dev/ttyUSB0

# Via PlatformIO (from El Trabajante/):
NVS_ENV=pi-home UPLOAD_PORT=/dev/ttyUSB0 pio run -e flash_nvs -t flash_nvs

# Generate binary only (no ESP connected), then scp to Pi and flash there:
python scripts/esp/flash_nvs.py --env pi-home --generate-only
scp secrets/nvs_secrets.pi-home.bin robin@192.168.0.2:/tmp/
# On Pi: esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash 0x9000 /tmp/nvs_secrets.pi-home.bin
```

---

## Lessons-Learned Fallstricke (AUT-764/AUT-769)

**1. Namespace-Syntax in CSV**

The namespace row must have empty `encoding` and `value` columns:
```
wifi_config,namespace,,          ← CORRECT (empty encoding + value)
wifi_config,namespace,string,""  ← WRONG (nvs_partition_gen rejects this)
```
The namespace row itself does not store a value — it just declares which namespace the following keys belong to.

**2. SCons-Signatur in PlatformIO extra_scripts**

`Import("env")` MUST be the first executable line in any `pre:` or `post:` script. Linters flag it as undefined (`F821`) because it's a SCons-injected global — suppress with `# noqa: F821`. Without `Import("env")`, `env.AddCustomTarget` fails silently or raises `NameError`.

**3. `framework = arduino` (not `espidf`) for `[env:flash_nvs]`**

The custom flash_nvs PlatformIO environment uses SCons via `env.AddCustomTarget`. This requires `framework = arduino`. With `framework = espidf`, the SCons environment exposes different variables and `env.subst("$UPLOAD_PORT")` may not resolve correctly. The `esp-idf-nvs-partition-gen` Python tool is framework-independent, but the PlatformIO build scaffolding is not.

**4. gitignore-Layering**

Two gitignore layers apply to this directory:
- Root `.gitignore` — contains `El Trabajante/secrets/*.csv` and `El Trabajante/secrets/*.bin` glob patterns
- `secrets/.gitignore` — contains local `*.csv` / `*.bin` with `!*.csv.example` exception

The `!*.csv.example` exception **must** appear in the closer-scoped `secrets/.gitignore`, not only in the root. Git applies gitignore rules from the closest enclosing `.gitignore` first; if the root ignores `*.csv` and no local exception exists, `*.csv.example` gets ignored too. Always run `git status` after adding new example files to verify they are tracked.
