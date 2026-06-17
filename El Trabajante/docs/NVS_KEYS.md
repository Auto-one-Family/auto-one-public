# NVS-Keys - Migration von main.cpp

Diese Dokumentation listet alle NVS-Keys auf, die von StorageManager verwendet werden.

## WiFi Configuration

- **Namespace**: `wifi_config`

- **Keys**:

  - `ssid` (String) - WiFi SSID

  - `password` (String) - WiFi Password

  - `server_address` (String) - God-Kaiser Server IP

  - `mqtt_port` (uint16_t) - MQTT Port (default: 8883)

  - `mqtt_username` (String) - MQTT Username (required since AUT-747; provisioned via `flash_nvs.py`)

  - `mqtt_password` (String) - MQTT Password (required since AUT-747; provisioned via `flash_nvs.py`)

### Default-Values & Constraints

Diese Tabelle zeigt **Default-Werte**, die verwendet werden, wenn Keys **nicht in NVS** existieren (z.B. First-Boot).

#### WiFi Configuration (Namespace: `wifi_config`)

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `ssid` | String | `""` (empty) | Max 32 chars | WiFi Network Name |
| `password` | String | `""` (empty) | Max 64 chars | WiFi Network Password |
| `server_address` | String | `"192.168.0.198"` | IPv4 or Hostname | MQTT Broker IP/Hostname |
| `mqtt_port` | uint16_t | `8883` | 1-65535 | MQTT Broker Port (8883=TLS, 1883=Plain) |
| `mqtt_username` | String | `""` (empty) | Max 64 chars | MQTT Auth Username — required since AUT-747 (`allow_anonymous=false` auf allen Envs) |
| `mqtt_password` | String | `""` (empty) | Max 64 chars | MQTT Auth Password — required since AUT-747 |
| `configured` | bool | `false` | - | WiFi Configuration Status |

**Provisioning (AUT-764):** Credentials werden nie manuell getippt, sondern via NVS-Binary-Tool geflasht:
```bash
# Vorlage anlegen (einmalig)
cp El\ Trabajante/secrets/nvs_secrets.dev-local.csv.example El\ Trabajante/secrets/nvs_secrets.dev-local.csv
# Werte eintragen, dann:
python El\ Trabajante/scripts/esp/flash_nvs.py --env dev-local --port COM3
```
Pi-elbherb: Skript gibt manuelles `esptool`-Befehlsblock-Print statt autonomem Flash (STRICT-Risikostufe).

#### Zone Configuration (Namespace: `zone_config`)

**File:** `src/services/config/config_manager.cpp` (lines 170-244)

**Phase 7 Keys (Hierarchical Zone Info):**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `zone_id` | String | `""` (empty) | Max 64 chars | Primary zone identifier (Phase 7) |
| `master_zone_id` | String | `""` (empty) | Max 64 chars | Parent master zone ID (Phase 7) |
| `zone_name` | String | `""` (empty) | Max 64 chars | Human-readable zone name (Phase 7) |
| `zone_assigned` | bool | `false` | - | Zone assignment status flag (Phase 7) |

**Existing Keys (Kaiser Communication):**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `kaiser_id` | String | `""` (empty) | Max 64 chars | Kaiser instance identifier |
| `kaiser_name` | String | `""` (empty) | Max 64 chars | Human-readable Kaiser name |
| `connected` | bool | `false` | - | MQTT connection status |
| `id_generated` | bool | `false` | - | Kaiser ID generation flag |

**Legacy Keys (Backward Compatibility):**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `legacy_master_zone_id` | String | `""` (empty) | Max 64 chars | Legacy master zone ID |
| `legacy_master_zone_name` | String | `""` (empty) | Max 64 chars | Legacy master zone name |
| `is_master_esp` | bool | `false` | - | Legacy master ESP flag |

**Implementation:**

```cpp
// Loading (config_manager.cpp:170-204)
kaiser.zone_id = storageManager.getStringObj("zone_id", "");
kaiser.master_zone_id = storageManager.getStringObj("master_zone_id", "");
kaiser.zone_name = storageManager.getStringObj("zone_name", "");
kaiser.zone_assigned = storageManager.getBool("zone_assigned", false);
kaiser.kaiser_id = storageManager.getStringObj("kaiser_id", "");
kaiser.kaiser_name = storageManager.getStringObj("kaiser_name", "");
kaiser.connected = storageManager.getBool("connected", false);
kaiser.id_generated = storageManager.getBool("id_generated", false);

// Saving (config_manager.cpp:206-244)
storageManager.putString("zone_id", kaiser.zone_id);
storageManager.putString("master_zone_id", kaiser.master_zone_id);
storageManager.putString("zone_name", kaiser.zone_name);
storageManager.putBool("zone_assigned", kaiser.zone_assigned);
storageManager.putString("kaiser_id", kaiser.kaiser_id);
storageManager.putString("kaiser_name", kaiser.kaiser_name);
storageManager.putBool("connected", kaiser.connected);
storageManager.putBool("id_generated", kaiser.id_generated);
```

#### Subzone Configuration (Namespace: `subzone_config`)

**Phase 9 Keys:**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `subzone_ids` | String | `""` | Comma-separated | **Master list** of all subzone IDs (e.g., "irr_A,irr_B,clim_1") |
| `subzone_{subzone_id}_id` | String | `""` | Max 32 chars | Subzone identifier |
| `subzone_{subzone_id}_name` | String | `""` | Max 64 chars | Human-readable name |
| `subzone_{subzone_id}_parent` | String | `""` | Max 64 chars | Parent zone ID |
| `subzone_{subzone_id}_gpios` | String | `""` | Comma-separated | GPIO list (e.g., "4,5,6") |
| `subzone_{subzone_id}_safe_mode` | bool | `true` | - | Safe-mode status |
| `subzone_{subzone_id}_timestamp` | uint32 | `0` | - | Creation timestamp |

**Hinweis:** Der `subzone_ids` Key ist der Master-Index für alle konfigurierten Subzones. Er wird automatisch bei `saveSubzoneConfig()` und `removeSubzoneConfig()` aktualisiert.

**Indexed Pattern (aktuell, Namespace `subzone_config`, `config_manager.cpp`):**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `sz_%d_sen` | uint8 | `0` | 0-255 | Gespeicherte Sensor-Anzahl pro Subzone (`%d` = Index 0–99) |
| `sz_%d_act` | uint8 | `0` | 0-255 | Gespeicherte Aktor-Anzahl pro Subzone (`%d` = Index 0–99) |

**Implementation:**

```cpp
// Saving (config_manager.cpp:450-484)
storageManager.putString("subzone_" + subzone_id + "_id", config.subzone_id);
storageManager.putString("subzone_" + subzone_id + "_name", config.subzone_name);
storageManager.putString("subzone_" + subzone_id + "_parent", config.parent_zone_id);
storageManager.putBool("subzone_" + subzone_id + "_safe_mode", config.safe_mode_active);
storageManager.putULong("subzone_" + subzone_id + "_timestamp", config.created_timestamp);
// GPIO-Array als komma-separierte String
String gpio_string = "4,5,6";  // Beispiel
storageManager.putString("subzone_" + subzone_id + "_gpios", gpio_string);

// Loading (config_manager.cpp:486-520)
config.subzone_id = storageManager.getStringObj("subzone_" + subzone_id + "_id", "");
config.subzone_name = storageManager.getStringObj("subzone_" + subzone_id + "_name", "");
config.parent_zone_id = storageManager.getStringObj("subzone_" + subzone_id + "_parent", "");
config.safe_mode_active = storageManager.getBool("subzone_" + subzone_id + "_safe_mode", true);
config.created_timestamp = storageManager.getULong("subzone_" + subzone_id + "_timestamp", 0);
// GPIO-Array aus komma-separiertem String laden
String gpio_string = storageManager.getStringObj("subzone_" + subzone_id + "_gpios", "");
// Parse comma-separated string to vector
```

#### System Configuration (Namespace: `system_config`)

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `esp_id` | String | `""` → **Generated** | Format: `ESP_XXXXXX` | Generated from MAC if missing |
| `device_name` | String | `"ESP32"` | Max 32 chars | Human-Readable Device Name |
| `current_state` | uint8_t | `0` (STATE_BOOT) | 0-11 | State Machine Current State |
| `safe_mode_reason` | String | `""` (empty) | Max 128 chars | Reason for Safe-Mode Entry |
| `boot_count` | uint16_t | `0` | 0-65535 | Number of Reboots |
| `log_level` | uint8_t | `1` (LOG_INFO) | 0-4 | Persisted log level (0=DEBUG, 1=INFO, 2=WARNING, 3=ERROR, 4=CRITICAL) |
| `emergency_auth` | String | `""` (empty) | Max 64 chars | ESP emergency-stop auth token (fail-open: empty = accept all) |
| `broadcast_em_tok` | String | `""` (empty) | Max 64 chars | Broadcast emergency-stop auth token (fail-open: empty = accept all) |

#### Sensor Configuration (Namespace: `sensor_config`)

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `sensor_count` | uint8_t | `0` | 0-20 | Number of Configured Sensors |
| `sensor_{i}_gpio` | uint8_t | N/A | 0-39 | GPIO Pin for Sensor i |
| `sensor_{i}_type` | String | N/A | Max 32 chars | Sensor Type (e.g. "ph_sensor") |
| `sensor_{i}_name` | String | N/A | Max 64 chars | Human-Readable Sensor Name |
| `sensor_{i}_subzone` | String | N/A | Max 32 chars | Subzone Identifier |
| `sensor_{i}_active` | bool | N/A | - | Is Sensor Active? |
| `sensor_{i}_raw_mode` | bool | `true` | - | Raw ADC Mode (true) or Calibrated (false) |
| `sensor_{i}_mode` | String | `"continuous"` | Max 16 chars | **✅ Phase 2C** Operating Mode (continuous, on_demand, paused, scheduled) |
| `sensor_{i}_interval` | uint32_t | `30000` | 1000-300000 | **✅ Phase 2C** Measurement Interval in Milliseconds |
| `sen_%d_if` | String | `""` | Max 16 chars | Interface type (`UART`, leer = legacy) — **Implementierung:** `config_manager.cpp` |
| `sen_%d_urx` | uint8_t | `255` | 0-39 or 255 | UART RX pin (255 = unset; 0 = invalid) |
| `sen_%d_utx` | uint8_t | `255` | 0-39 or 255 | UART TX pin (255 = unset; 0 = invalid) |
| `sen_%d_ubd` | uint32_t | `9600` | 9600-115200 | UART baud rate (MH-Z19/SEN0220 default 9600) |
| `sen_%d_adcsrc` | uint8_t | `0` | 0/1 | **ADS1115** ADC-Quelle für pH/EC: 0 = internal (ESP32 12-bit), 1 = ads1115 (extern 16-bit I2C) |
| `sen_%d_adcch` | uint8_t | `255` | 0-3 or 255 | **ADS1115** Single-ended Kanal (AIN0-AIN3; 255 = unset/internal) |
| `sen_%d_pga` | uint8_t | `1` | 0-5 | **ADS1115** PGA-Bits (Config-Register [11:9]); 1 = ±4.096V default. Mapping: 0=±6.144V,1=±4.096V,2=±2.048V,3=±1.024V,4=±0.512V,5=±0.256V |

**Note:** Sensor-Array-Elemente haben **keine Default-Values**. Keys werden nur geschrieben, wenn ein Sensor konfiguriert wird.

**Phase 2C Operating Modes:**
- `continuous`: Sensor misst automatisch im konfigurierten Intervall
- `on_demand`: Sensor misst nur auf MQTT-Command (via `/sensor/{gpio}/command`)
- `paused`: Sensor misst nicht (GPIO bleibt reserviert)
- `scheduled`: Sensor misst auf Server-getriggerte Commands (Phase 2D)

#### Offline Rules Configuration (Namespace: `offline`)

**File:** `src/services/safety/offline_mode_manager.cpp`

**SAFETY-P4 + LE-01 — Blob-Format v1 (aktuell):**

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `ofr_ver` | uint8_t | `0` → `1` | 0/1 | Schema-Version (0 = legacy Individual-Keys, 1 = Blob-Format) |
| `ofr_count` | uint8_t | `0` | 0-8 | Anzahl gespeicherter Offline-Regeln |
| `ofr_blob` | Blob | — | `(count × sizeof(OfflineRule)) + 1` Bytes | Packed `OfflineRule[]` Array + CRC8/SMBUS Trailer |

**OfflineRule Struct Layout (Blob-Inhalt, v1, 56 Bytes):**

| Feld | Offset | Typ | Beschreibung |
|------|--------|-----|--------------|
| `enabled` | 0 | bool | Regel aktiv? |
| `actuator_gpio` | 1 | uint8_t | Aktor GPIO-Pin |
| `sensor_gpio` | 2 | uint8_t | Sensor GPIO-Pin (0 = I2C-Konvention) |
| `sensor_value_type` | 3 | char[24] | Kanonischer Sensortyp (z.B. "sht31_temperature") |
| `activate_below` | 28 | float | Heating-Modus: AN wenn < Schwelle |
| `deactivate_above` | 32 | float | Heating-Modus: AUS wenn > Schwelle |
| `activate_above` | 36 | float | Cooling-Modus: AN wenn > Schwelle |
| `deactivate_below` | 40 | float | Cooling-Modus: AUS wenn < Schwelle |
| `is_active` | 44 | bool | Aktueller Aktor-Zustand |
| `server_override` | 45 | bool | Server hat manuell geschaltet → Regel pausiert |
| `time_filter_enabled` | 46 | bool | Hat diese Regel ein Zeitfenster? |
| `start_hour` | 47 | uint8_t | UTC Stunde Start (0–23) |
| `start_minute` | 48 | uint8_t | UTC Minute Start (0–59) |
| `end_hour` | 49 | uint8_t | UTC Stunde Ende (0–24, 24 = Mitternacht exklusiv) |
| `end_minute` | 50 | uint8_t | UTC Minute Ende (0–59) |
| `_reserved` | 51 | uint8_t | Alignment-Padding (future: days_of_week Bitfield) |

**Migration (ver=0 → ver=1):** Beim ersten Load mit neuer Firmware werden alte Individual-Keys (`ofr_{i}_en`, `ofr_{i}_agpio`, usw.) gelesen, ins Blob-Format geschrieben und die alten Keys gelöscht (`_deleteOldIndividualKeys()`).

**Change-Detection:** `saveOfflineRulesToNVS()` nutzt `memcmp` gegen Shadow-Copy — NVS wird nur beschrieben wenn sich Regeln geändert haben.

**Boot-Load:** `loadOfflineRulesFromNVS()` in `setup()` nach `actuatorManager.begin()`, vor MQTT-Connect.

#### Watchdog Diagnostics (Namespace: `wdt_diag`)

**File:** `src/utils/watchdog_storage.cpp`

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `hist` | String | `""` | Comma-separated UNIX epochs | Watchdog-Timeouts im rollierenden 24h-Fenster (Einträge nach gültiger Systemzeit / NTP) |
| `snap` | String | `""` | JSON (ArduinoJson) | Letzter Diagnose-Snapshot vor Timeout (`handleWatchdogTimeout`) |

#### Intent Outcome Outbox (Namespace: `io_outbox`)

**File:** `src/tasks/intent_contract.cpp`

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `head` | uint8_t | `0` | 0-7 | Ringbuffer-Head für Pending-Outcomes |
| `count` | uint8_t | `0` | 0-8 | Anzahl belegter Outbox-Slots |
| `retry_total` | uint32_t | `0` | - | Kumulierte Replay-Retry-Versuche |
| `recovered_total` | uint32_t | `0` | - | Erfolgreich wiederhergestellte Outcomes (Replay) |
| `drop_total` | uint32_t | `0` | - | Gedroppte kritische Outcomes bei Outbox-Overflow/Retry-Limit |
| `fin_ok_total` | uint32_t | `0` | Key <= 15 chars | Kumuliert final bestätigte Outcomes (Direkt-Publish + Replay) |
| `s{idx}_flow` | String | `""` | `idx` 0-7 | Flow je Slot (`command`, `publish`, ...) |
| `s{idx}_intent` | String | `""` | `idx` 0-7 | Intent-ID je Slot |
| `s{idx}_corr` | String | `""` | `idx` 0-7 | Correlation-ID je Slot |
| `s{idx}_gen` | uint32_t | `0` | `idx` 0-7 | Generation je Slot |
| `s{idx}_created` | uint32_t | `0` | `idx` 0-7 | created_at_ms je Slot |
| `s{idx}_ttl` | uint32_t | `0` | `idx` 0-7 | ttl_ms je Slot |
| `s{idx}_epoch` | uint32_t | `0` | `idx` 0-7 | epoch_at_accept je Slot |
| `s{idx}_outcome` | String | `"failed"` | `idx` 0-7 | Outcome je Slot |
| `s{idx}_code` | String | `"EXECUTE_FAIL"` | `idx` 0-7 | Fehler-/Statuscode je Slot |
| `s{idx}_reason` | String | `"Pending outcome replay"` | `idx` 0-7 | Reason je Slot |
| `s{idx}_retryable` | bool | `true` | `idx` 0-7 | Retry-Flag je Slot |
| `s{idx}_attempt` | uint8_t | `1` | `idx` 0-7 | Aktueller Attempt je Slot |

#### Actuator Configuration (Namespace: `actuator_config`)

| Key | Type | Default | Constraint | Description |
|-----|------|---------|------------|-------------|
| `actuator_count` | uint8_t | `0` | 0-20 | Number of Configured Actuators |
| `actuator_{i}_gpio` | uint8_t | N/A | 0-39 | Primary GPIO Pin |
| `actuator_{i}_aux_gpio` | uint8_t | N/A | 0-39 or 255 | Auxiliary GPIO (255=unused) |
| `actuator_{i}_type` | String | N/A | Max 32 chars | Actuator Type ("pump","pwm","valve","relay") |
| `actuator_{i}_name` | String | N/A | Max 64 chars | Human-Readable Actuator Name |
| `actuator_{i}_subzone` | String | N/A | Max 32 chars | Subzone Identifier |
| `actuator_{i}_active` | bool | N/A | - | Is Actuator Active? |
| `actuator_{i}_critical` | bool | N/A | - | Critical Actuator (true) or Optional (false) |
| `actuator_{i}_inverted` | bool | N/A | - | Inverted Logic (LOW=ON if true) |
| `actuator_{i}_default_state` | bool | N/A | - | Default State (ON/OFF) at Boot |
| `actuator_{i}_default_pwm` | uint8_t | N/A | 0-255 | Default PWM Duty Cycle (0-255) |

**Note:** Actuator-Array-Elemente haben **keine Default-Values**. Keys werden nur geschrieben, wenn ein Aktor konfiguriert wird.
Since R20-P11: NVS writes are skipped for identical config pushes (0 writes) and reduced to 1 write for soft-only changes (name, subzone, etc.). Full 2-write cycle (remove + add) only on structural changes (type, aux_gpio).

## Kaiser/Zone Configuration

- **Namespace**: `zone_config`

- **Keys**:

  - `kaiser_id` (String) - Kaiser ID (UUID)

  - `kaiser_name` (String) - Kaiser Name

  - `master_zone_id` (String) - Master Zone ID

  - `master_zone_name` (String) - Master Zone Name

  - `is_master_esp` (bool) - Ist dieses ESP Master?

## Sensor Configuration

- **Namespace**: `sensor_config`

- **Keys** (pro Sensor: 6 Keys × max 20 Sensoren = 120 Keys):

  - `sensor_count` (uint8_t) - Anzahl konfigurierter Sensoren (0-20)

  - `sensor_{i}_gpio` (uint8_t) - GPIO-Pin (i = 0-19)

  - `sensor_{i}_type` (String) - Sensor-Typ (z.B. "ph_sensor", "temperature_ds18b20", "soil_moisture")

  - `sensor_{i}_name` (String) - Sensor-Name für UI

  - `sensor_{i}_subzone` (String) - Subzone-Zuordnung (z.B. "zone_1", "zone_2") (entspricht `subzone_id` im SensorConfig)

  - `sensor_{i}_active` (bool) - Aktiv?

  - `sensor_{i}_raw_mode` (bool) - Raw-Mode aktiv? (immer `true` für Server-Centric Architecture)

  - `sensor_{i}_mode` (String) - **✅ Phase 2C** Operating Mode ("continuous", "on_demand", "paused", "scheduled")

  - `sensor_{i}_interval` (uint32_t) - **✅ Phase 2C** Mess-Intervall in Millisekunden (1000-300000, default: 30000)

  - `sen_{i}_if` (String) - Interface-Typ (z.B. `"UART"` für MH-Z19/SEN0220 CO2)

  - `sen_{i}_urx` (uint8_t) - UART RX-Pin (255 = unset)

  - `sen_{i}_utx` (uint8_t) - UART TX-Pin (255 = unset)

  - `sen_{i}_ubd` (uint32_t) - UART Baudrate (default: 9600)

  - `sen_{i}_adcsrc` (uint8_t) - **ADS1115** ADC-Quelle für pH/EC (0 = internal, 1 = ads1115; default: 0)

  - `sen_{i}_adcch` (uint8_t) - **ADS1115** Single-ended Kanal AIN0-AIN3 (default: 255 = unset)

  - `sen_{i}_pga` (uint8_t) - **ADS1115** PGA-Bits 0-5 (default: 1 = ±4.096V)

  **UART CO2 (AUT-527):** Ein logischer NVS-Slot (`sensor_{i}_gpio`) reserviert **beide** UART-Pins (typ. 17+18). Nach UI-Löschen können Geister auf dem Komplement-GPIO bleiben — Server sendet dual Tombstone; Firmware entfernt Fallback GPIO 17/18.

  **ADS1115 (Externer ADC):** pH/EC können wahlweise über einen externen 16-bit-I2C-ADC (ADS1115) statt des internen ESP32-ADC erfasst werden. `gpio` bleibt die logische Slot-/Topic-ID, `i2c_address` trägt die Modul-Adresse (0x48-0x4B). Die Erfassung wechselt die Quelle, alles danach (RAW → MQTT → Server-Conversion → Kalibrierung) bleibt identisch.

## Actuator Configuration

- **Namespace**: `actuator_config`

- **Keys** (pro Aktor: **10 Keys** × max 20 Aktoren = **200 Keys**):

  - `actuator_count` (uint8_t) - Anzahl konfigurierter Aktoren (0-20)

  - `actuator_{i}_gpio` (uint8_t) - GPIO-Pin (i = 0-19)

  - `actuator_{i}_aux_gpio` (uint8_t) - **✅ NEU (Phase 5)** Auxiliary GPIO (z.B. Ventil-Richtungspin, H-Bridge) (255 = unused)

  - `actuator_{i}_type` (String) - Aktor-Typ ("pump", "pwm", "valve", "relay")

  - `actuator_{i}_name` (String) - Aktor-Name für UI

  - `actuator_{i}_subzone` (String) - Subzone-Zuordnung (entspricht `subzone_id` im ActuatorConfig)

  - `actuator_{i}_active` (bool) - Aktiv?

  - `actuator_{i}_critical` (bool) - **✅ NEU (Phase 5)** Kritisches System (z.B. Bewässerungspumpe) - Safety-Priorität

  - `actuator_{i}_inverted` (bool) - Invertierte Logik? (LOW = ON)

  - `actuator_{i}_default_state` (bool) - Standard-Zustand (false=OFF, true=ON)

  - `actuator_{i}_default_pwm` (uint8_t) - **✅ NEU (Phase 5)** Standard-PWM-Wert (0-255) für PWM-Aktoren

> **Phase-Status:** ✅ **AKTUALISIERT (Phase 5)** - Die NVS-Speicher-Funktionalität ist vollständig implementiert (`ConfigManager::saveActuatorConfig()` / `loadActuatorConfig()`), wird aber in Phase 5 bewusst **NICHT verwendet** (Server-Centric Option 2). Stattdessen erfolgt Actuator-Konfiguration **ausschließlich via MQTT** (`/config` Topic mit `actuators[]` Array). Die NVS-Keys dienen als **Fallback-Mechanismus** für Phase 6 (Hybrid/Persistenz-Mode) und als **Defense-in-Depth** gegen Server-Fehlkonfigurationen (GPIO-Konflikt-Check bleibt aktiv).
>
> **Architektur-Hinweis:** Siehe `docs/ZZZ.md` - "Server-Centric Pragmatic Deviations" für Details zur bewussten Nicht-Nutzung von NVS-Persistenz in Phase 5.

## System Configuration

- **Namespace**: `system_config`

- **Keys**:

  - `esp_id` (String) - ESP-ID (MAC-basiert, z.B. "ESP_AABBCC")

  - `device_name` (String) - User-definierter Name

  - `current_state` (uint8_t) - SystemState (0-11, siehe Mqtt_Protocoll.md State-Values)
    - 0: BOOT
    - 1: WIFI_SETUP
    - 2: WIFI_CONNECTED
    - 3: MQTT_CONNECTING
    - 4: MQTT_CONNECTED
    - 5: AWAITING_USER_CONFIG
    - 6: ZONE_CONFIGURED
    - 7: SENSORS_CONFIGURED
    - 8: OPERATIONAL
    - 9: LIBRARY_DOWNLOADING
    - 10: SAFE_MODE
    - 11: ERROR

  - `safe_mode_reason` (String) - Grund für Safe-Mode

  - `boot_count` (uint16_t) - Anzahl der Boots (für Diagnostik)

  - `log_level` (uint8_t) - Persistiertes Log-Level (0=DEBUG, 1=INFO, 2=WARNING, 3=ERROR, 4=CRITICAL). Gesetzt via MQTT `set_log_level` Command, geladen bei Boot (STEP 5.1)

  - `emergency_auth` (String) - ESP emergency-stop auth token (max 64 chars, fail-open: empty = accept all). Gesetzt via MQTT `set_emergency_token` Command

  - `broadcast_em_tok` (String) - Broadcast emergency-stop auth token (max 64 chars, fail-open: empty = accept all). Gesetzt via MQTT `set_emergency_token` Command (token_type="broadcast")

  - `last_error` (String) - Letzte Fehlermeldung

## Zone Configuration - Subzonen Details

- **Namespace**: `zone_config`

- **Subzone Keys** (pro Subzone: 3 Keys × max 10 Subzonen = 30 Keys):

  - `subzone_count` (uint8_t) - Anzahl der Subzonen (0-10)

  - `subzone_{i}_id` (String) - Subzone ID (i = 0-9)

  - `subzone_{i}_name` (String) - Subzone Name

  - `subzone_{i}_active` (bool) - Ist diese Subzone aktiv?

## MQTT Topics - Zusätzliche Topics

Das System unterstützt **18 MQTT Topic-Patterns** (nicht nur 13):

**Zusätzliche Topics über die Standard-13 hinaus:**

- `kaiser/{kaiser_id}/zone/{master_zone_id}/status` - Zone-Status
- `kaiser/{kaiser_id}/zone/{master_zone_id}/subzone/{subzone_id}/status` - Subzone-Status
- `kaiser/{kaiser_id}/esp/{esp_id}/will` - Last Will Topic
- `kaiser/{kaiser_id}/esp/{esp_id}/config/request` - Konfig-Anfrage
- `kaiser/{kaiser_id}/esp/{esp_id}/config/response` - Konfig-Antwort

### Memory-Usage Summary

**Total Keys (Worst-Case):**
- WiFi: 7 Keys
- Zone: 6 Keys
- System: 6 Keys
- Sensors: 1 + (8 × 20) = 161 Keys (bei 20 Sensoren, **+2 Keys Phase 2C: mode, interval**; UART-CO2 optional +4 Keys pro Sensor: `sen_%d_if`, `sen_%d_urx`, `sen_%d_utx`, `sen_%d_ubd`; ADS1115 optional +3 Keys pro Sensor: `sen_%d_adcsrc`, `sen_%d_adcch`, `sen_%d_pga`)
- Actuators: 1 + (10 × 20) = 201 Keys (bei 20 Aktoren)
- Offline Rules: 3 Keys (ofr_ver, ofr_count, ofr_blob = Blob v1, **SAFETY-P4 + LE-01**)
- **TOTAL: ~385 Keys** (bei voller Auslastung)

**Estimated NVS-Usage:**
- Strings (avg 30 bytes): ~200 Keys × 30 = 6.0 KB
- Integers (4 bytes): ~100 Keys × 4 = 400 bytes
- Offline Rules Blob: 8 × 56 Bytes + 1 CRC + Overhead ≈ 0.5 KB
- **TOTAL: ~7 KB** (bei voller Auslastung)

**NVS-Partition:** 20 KB (Standard ESP32)
**Usage:** ~45% (bei 20 Sensoren + 20 Aktoren + 8 Offline-Regeln)
**Safe-Margin:** ✅ 55% frei

## Notes

- Alle String-Keys haben Max-Länge 255
- Bool-Keys werden als uint8_t gespeichert (0/1)
- Float-Keys nutzen Preferences putFloat/getFloat (4 Bytes)
- Namespaces sind isoliert (kein Key-Konflikt zwischen Namespaces)
- **WICHTIG:** Sensor/Actuator Configs sind Arrays mit dynamischer Länge (sensor_count/actuator_count)
- **Watchdog:** Zusätzlich Namespace `wdt_diag` (`hist`, `snap`) — siehe Abschnitt Watchdog Diagnostics

