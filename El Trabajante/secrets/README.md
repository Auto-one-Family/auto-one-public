# NVS Secrets

Per-environment MQTT credential files for the ESP32 NVS partition.

**WARNING: Flashing this binary replaces the ENTIRE NVS partition (0x9000, 32KB).
All previously provisioned configs will be erased.
Use only for a fresh ESP or after an intentional full reset.**

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

## Setup

1. Copy the generic example:

   ```
   cp nvs_secrets.dev-local.csv.example nvs_secrets.dev-local.csv
   ```

2. Open the `.csv` and replace every `PLACEHOLDER_*` value.
   Keep `server_address` as `localhost` for a machine-local broker, or set
   it to the broker hostname you actually use. Match MQTT user/password
   to your Mosquitto `password_file`.

3. Install the NVS generator (once):

   ```
   pip install esp-idf-nvs-partition-gen
   ```

4. Flash credentials (ESP32 already has firmware):

   ```
   python scripts/esp/flash_nvs.py --env dev-local --port COM5
   ```

   Or complete flash — bootloader + partitions + firmware + NVS in one step
   (first flash / after factory reset):

   ```
   # Requires: pio run -e esp32_dev first
   python scripts/esp/flash_full.py --env dev-local --port COM5
   ```

   Or generate a binary only (no ESP connected):

   ```
   python scripts/esp/flash_nvs.py --env dev-local --generate-only
   ```

Flash environments: `dev-local` (machine-local broker), `lab` (LAN),
`field` (strict — confirmation required before flashing).
The tracked example is `dev-local`. Copy it to `nvs_secrets.lab.csv` or
`nvs_secrets.field.csv` when targeting those environments.

The tracked example uses `localhost` and `PLACEHOLDER_*` values only.

## Security

- `.csv` and `.bin` files are gitignored — check `git status` before committing
- Only `*.csv.example` files (with placeholders) are tracked
- Credentials must match the `password_file` configured on the MQTT broker

---

## CSV pitfalls

**1. Namespace syntax**

The namespace row must have empty `encoding` and `value` columns:

```
wifi_config,namespace,,          ← CORRECT (empty encoding + value)
wifi_config,namespace,string,""  ← WRONG (nvs_partition_gen rejects this)
```

The namespace row does not store a value — it declares which namespace the
following keys belong to.

**2. SCons signature in PlatformIO extra_scripts**

`Import("env")` MUST be the first executable line in any `pre:` or `post:`
script. Linters flag it as undefined (`F821`) because it is a SCons-injected
global — suppress with `# noqa: F821`. Without `Import("env")`,
`env.AddCustomTarget` fails silently or raises `NameError`.

**3. `framework = arduino` (not `espidf`) for `[env:flash_nvs]`**

The custom flash_nvs PlatformIO environment uses SCons via
`env.AddCustomTarget`. This requires `framework = arduino`. The
`esp-idf-nvs-partition-gen` Python tool is framework-independent, but the
PlatformIO build scaffolding is not.

**4. gitignore layering**

Two gitignore layers apply to this directory:

- Root `.gitignore` — contains `El Trabajante/secrets/*.csv` and
  `El Trabajante/secrets/*.bin`
- `secrets/.gitignore` — local `*.csv` / `*.bin` with `!*.csv.example`

The `!*.csv.example` exception **must** appear in the closer-scoped
`secrets/.gitignore`, not only in the root. Always run `git status` after
adding new example files to verify they are tracked.
