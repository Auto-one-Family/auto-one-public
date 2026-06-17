# NVS Storage Manager Tests

> **Erstellt:** 2026-01-28
> **Version:** 1.0
> **Kategorie:** 10-nvs
> **Prioritaet:** KRITISCH - Basis fuer alle Konfigurationspersistenz

---

## Uebersicht

Diese Test-Suite validiert den **Storage Manager** (`storage_manager.cpp`), die Abstraktionsschicht ueber dem ESP32 NVS (Non-Volatile Storage). Der Storage Manager ist kritisch fuer:

- **Persistenz nach Stromausfall:** Alle Konfigurationen muessen Neustarts ueberleben
- **Namespace-Isolation:** Daten duerfen nicht zwischen Modulen "lecken"
- **Datenintegritaet:** Gespeicherte Werte muessen korrekt wiederhergestellt werden
- **Kapazitaetsmanagement:** NVS-Limits muessen respektiert werden

**IEC 61508 Relevanz:** Verlorene Konfigurationsdaten koennen dazu fuehren, dass Sensoren/Aktoren nach einem Neustart nicht mehr funktionieren. Das System MUSS nach jedem Stromausfall identisch konfiguriert wieder hochfahren.

---

## Test-Dateien

| Datei | Test-IDs | Beschreibung | Prioritaet |
|-------|----------|--------------|-----------|
| `nvs_init_success.yaml` | NVS-INIT-001 | Erfolgreiche NVS-Initialisierung | Hoch |
| `nvs_init_double.yaml` | NVS-INIT-002 | Doppelte Initialisierung (idempotent) | Mittel |
| `nvs_init_order.yaml` | NVS-INIT-003 | Init vor anderen Modulen | Hoch |
| `nvs_init_status.yaml` | NVS-INIT-004 | Init-Status abrufbar | Mittel |
| `nvs_init_boot_count.yaml` | NVS-INIT-005 | Boot-Count inkrementiert | Hoch |
| `nvs_ns_open.yaml` | NVS-NS-001 | Namespace oeffnen | Hoch |
| `nvs_ns_close.yaml` | NVS-NS-002 | Namespace schliessen | Hoch |
| `nvs_ns_autoclose.yaml` | NVS-NS-003 | Auto-Close bei neuem Open | Mittel |
| `nvs_ns_readonly.yaml` | NVS-NS-004 | Read-Only Modus | Hoch |
| `nvs_ns_toolong.yaml` | NVS-NS-005 | Zu langer Namespace-Name | Mittel |
| `nvs_ns_empty.yaml` | NVS-NS-006 | Leerer Namespace-Name | Mittel |
| `nvs_ns_isolation.yaml` | NVS-NS-007 | Namespace-Isolation | Kritisch |
| `nvs_type_string.yaml` | NVS-TYPE-009 | String speichern/laden | Hoch |
| `nvs_type_bool.yaml` | NVS-TYPE-007/008 | Bool true/false speichern/laden | Hoch |
| `nvs_type_uint8.yaml` | NVS-TYPE-001 | UInt8 speichern/laden | Mittel |
| `nvs_type_uint16.yaml` | NVS-TYPE-002 | UInt16 speichern/laden | Mittel |
| `nvs_type_int.yaml` | NVS-TYPE-004/005 | Int speichern/laden | Mittel |
| `nvs_type_float.yaml` | NVS-TYPE-011/012 | Float speichern/laden | Hoch |
| `nvs_type_ulong.yaml` | NVS-TYPE-013/014 | Unsigned Long speichern/laden | Mittel |
| `nvs_def_missing.yaml` | NVS-DEF-001/002/003/004 | Default-Werte fuer fehlende Keys | Hoch |
| `nvs_key_valid.yaml` | NVS-KEY-001 | Gueltiger Key (15 Zeichen) | Mittel |
| `nvs_key_toolong.yaml` | NVS-KEY-002 | Zu langer Key (16+ Zeichen) | Hoch |
| `nvs_key_exists.yaml` | NVS-KEY-004/005 | Key-Existenz pruefen | Mittel |
| `nvs_del_key.yaml` | NVS-DEL-001 | Einzelnen Key loeschen | Hoch |
| `nvs_del_namespace.yaml` | NVS-DEL-003 | Namespace loeschen | Hoch |
| `nvs_del_factory.yaml` | NVS-DEL-004 | Factory Reset | Kritisch |
| `nvs_pers_reboot.yaml` | NVS-PERS-001 | Daten ueberleben Reboot | Kritisch |
| `nvs_pers_sensor.yaml` | NVS-PERS-002 | Sensor-Config ueberlebt Reboot | Kritisch |
| `nvs_pers_zone.yaml` | NVS-PERS-003 | Zone-Config ueberlebt Reboot | Kritisch |
| `nvs_pers_wifi.yaml` | NVS-PERS-004 | WiFi-Config ueberlebt Reboot | Kritisch |
| `nvs_pers_bootcount.yaml` | NVS-PERS-005 | Boot-Count inkrementiert | Hoch |
| `nvs_cap_many_keys.yaml` | NVS-CAP-001 | Viele Keys in einem Namespace | Hoch |
| `nvs_cap_string_limit.yaml` | NVS-CAP-002 | String-Laengen-Limit | Mittel |
| `nvs_cap_free_entries.yaml` | NVS-CAP-004/005 | Freie/Used Entries abrufbar | Mittel |
| `nvs_err_no_namespace.yaml` | NVS-ERR-001/002 | Schreiben/Lesen ohne Namespace | Hoch |
| `nvs_err_readonly.yaml` | NVS-ERR-003 | Schreiben in Read-Only | Hoch |
| `nvs_int_configmanager.yaml` | NVS-INT-001/002 | ConfigManager Integration | Hoch |
| `nvs_int_sensor_boot.yaml` | NVS-INT-002 | Sensor-Config bei Boot | Kritisch |
| `nvs_int_actuator_boot.yaml` | NVS-INT-003 | Actuator-Config bei Boot | Kritisch |
| `nvs_int_zone_boot.yaml` | NVS-INT-004 | Zone-Config bei Boot | Kritisch |

---

## NVS-Architektur

### Namespaces

| Namespace | Keys (Worst-Case) | Beschreibung |
|-----------|-------------------|--------------|
| `wifi_config` | 7 | WiFi SSID, Password, MQTT Settings |
| `zone_config` | 8 | Zone-ID, Kaiser-ID, Zone-Name |
| `system_config` | 5 | ESP-ID, Device-Name, Boot-Count |
| `sensor_config` | 161 | Sensor-Array (20 Sensoren x 8 Keys + count) |
| `actuator_config` | 201 | Actuator-Array (20 Aktoren x 10 Keys + count) |
| `subzone_config` | 30 | Subzone-Konfigurationen |

### NVS Limits

| Limit | Wert | Beschreibung |
|-------|------|--------------|
| Max Namespace-Name | 15 Zeichen | ESP-IDF Limit |
| Max Key-Name | 15 Zeichen | ESP-IDF Limit |
| Max String-Wert | 4000 Zeichen | Preferences-Limit |
| NVS Partition | 20 KB | Standard ESP32 |
| Erwartete Nutzung | ~8 KB | Bei voller Auslastung |

### Log-Patterns (fuer Test-Verifikation)

| Operation | Log-Level | Pattern |
|-----------|-----------|---------|
| Init | INFO | `StorageManager: Initialized` |
| Namespace Open | DEBUG | `Opened namespace: {name}` |
| Namespace Close | DEBUG | `Closed namespace: {name}` |
| Auto-Close | WARNING | `Namespace already open, closing first` |
| Write Success | DEBUG | `Write {key} = {value}` |
| Write Fail | ERROR | `Failed to write` |
| No Namespace | ERROR | `No namespace open` |
| NVS Full | ERROR | `NVS FULL` |
| NVS Nearly Full | WARNING | `NVS NEARLY FULL` |

---

## Test-Ausfuehrung

### Einzeltest ausfuehren

```bash
cd "El Trabajante"
wokwi-cli . --timeout 90000 --scenario tests/wokwi/scenarios/10-nvs/nvs_init_success.yaml
```

### Alle NVS-Tests

```bash
cd "El Trabajante"
for f in tests/wokwi/scenarios/10-nvs/*.yaml; do
    echo "Running: $f"
    wokwi-cli . --timeout 90000 --scenario "$f" || echo "FAILED: $f"
done
```

---

## Kritische Erkenntnisse

### 1. String-Buffer-Gefahr

**KRITISCH:** Die `getString()` Methode verwendet einen **statischen 256-Byte Buffer**:
```cpp
static char string_buffer_[256];
```
- Mehrfache `getString()` Aufrufe ueberschreiben vorherige Werte
- IMMER `getStringObj()` verwenden wenn mehrere Strings benoetigt werden

### 2. Namespace-State-Machine

- `beginNamespace()` schliesst automatisch vorherigen Namespace (mit WARNING)
- `endNamespace()` ist safe bei wiederholtem Aufruf (no-op)
- Read/Write ohne offenen Namespace gibt ERROR zurueck

### 3. Thread-Safety

- Bei `CONFIG_ENABLE_THREAD_SAFETY` wird FreeRTOS Mutex verwendet
- Timeout ist `portMAX_DELAY` (blockiert unbegrenzt)
- Kein Deadlock-Risiko (Single Mutex, kein Nesting)

### 4. NVS-Quota-Warnung

- Bei < 10 freien Entries: WARNING aber Schreiben erlaubt
- Bei 0 freien Entries: ERROR und Schreiben abgelehnt

---

## Test-ID Mapping

| Test-ID | Beschreibung | Datei | Status |
|---------|--------------|-------|--------|
| NVS-INIT-001 | Erfolgreiche Initialisierung | nvs_init_success.yaml | Implementiert |
| NVS-INIT-002 | Doppelte Initialisierung | nvs_init_double.yaml | Implementiert |
| NVS-INIT-003 | Init vor anderen Modulen | nvs_init_order.yaml | Implementiert |
| NVS-INIT-004 | Init-Status abrufbar | nvs_init_status.yaml | Implementiert |
| NVS-INIT-005 | Boot-Count inkrementiert | nvs_init_boot_count.yaml | Implementiert |
| NVS-NS-001 | Namespace oeffnen | nvs_ns_open.yaml | Implementiert |
| NVS-NS-002 | Namespace schliessen | nvs_ns_close.yaml | Implementiert |
| NVS-NS-003 | Auto-Close bei neuem Open | nvs_ns_autoclose.yaml | Implementiert |
| NVS-NS-004 | Read-Only Modus | nvs_ns_readonly.yaml | Implementiert |
| NVS-NS-005 | Zu langer Namespace-Name | nvs_ns_toolong.yaml | Implementiert |
| NVS-NS-006 | Leerer Namespace-Name | nvs_ns_empty.yaml | Implementiert |
| NVS-NS-007 | Namespace-Isolation | nvs_ns_isolation.yaml | Implementiert |
| NVS-TYPE-001 | UInt8 speichern/laden | nvs_type_uint8.yaml | Implementiert |
| NVS-TYPE-002 | UInt16 speichern/laden | nvs_type_uint16.yaml | Implementiert |
| NVS-TYPE-004 | Int8 speichern/laden | nvs_type_int.yaml | Implementiert |
| NVS-TYPE-005 | Int32 speichern/laden | nvs_type_int.yaml | Implementiert |
| NVS-TYPE-007 | Bool true speichern/laden | nvs_type_bool.yaml | Implementiert |
| NVS-TYPE-008 | Bool false speichern/laden | nvs_type_bool.yaml | Implementiert |
| NVS-TYPE-009 | String speichern/laden | nvs_type_string.yaml | Implementiert |
| NVS-TYPE-010 | Leerer String | nvs_type_string.yaml | Implementiert |
| NVS-TYPE-011 | Float speichern/laden | nvs_type_float.yaml | Implementiert |
| NVS-TYPE-012 | Float negativ/Default | nvs_type_float.yaml | Implementiert |
| NVS-TYPE-013 | ULong speichern/laden | nvs_type_ulong.yaml | Implementiert |
| NVS-TYPE-014 | ULong Timestamps | nvs_type_ulong.yaml | Implementiert |
| NVS-DEF-001 | Default UInt | nvs_def_missing.yaml | Implementiert |
| NVS-DEF-002 | Default String | nvs_def_missing.yaml | Implementiert |
| NVS-DEF-003 | Default Bool | nvs_def_missing.yaml | Implementiert |
| NVS-DEF-004 | Default Float | nvs_def_missing.yaml | Implementiert |
| NVS-KEY-001 | Gueltiger Key 15 Zeichen | nvs_key_valid.yaml | Implementiert |
| NVS-KEY-002 | Zu langer Key | nvs_key_toolong.yaml | Implementiert |
| NVS-KEY-004 | Key existiert | nvs_key_exists.yaml | Implementiert |
| NVS-KEY-005 | Key existiert nicht | nvs_key_exists.yaml | Implementiert |
| NVS-DEL-001 | Einzelnen Key loeschen | nvs_del_key.yaml | Implementiert |
| NVS-DEL-003 | Namespace loeschen | nvs_del_namespace.yaml | Implementiert |
| NVS-DEL-004 | Factory Reset | nvs_del_factory.yaml | Implementiert |
| NVS-PERS-001 | Daten ueberleben Reboot | nvs_pers_reboot.yaml | Implementiert |
| NVS-PERS-002 | Sensor-Config Reboot | nvs_pers_sensor.yaml | Implementiert |
| NVS-PERS-003 | Zone-Config Reboot | nvs_pers_zone.yaml | Implementiert |
| NVS-PERS-004 | WiFi-Config Reboot | nvs_pers_wifi.yaml | Implementiert |
| NVS-PERS-005 | Boot-Count Reboot | nvs_pers_bootcount.yaml | Implementiert |
| NVS-CAP-001 | Viele Keys | nvs_cap_many_keys.yaml | Implementiert |
| NVS-CAP-002 | String zu lang | nvs_cap_string_limit.yaml | Implementiert |
| NVS-CAP-004 | Free Entries | nvs_cap_free_entries.yaml | Implementiert |
| NVS-CAP-005 | Used Entries | nvs_cap_free_entries.yaml | Implementiert |
| NVS-ERR-001 | Schreiben ohne Namespace | nvs_err_no_namespace.yaml | Implementiert |
| NVS-ERR-002 | Lesen ohne Namespace | nvs_err_no_namespace.yaml | Implementiert |
| NVS-ERR-003 | Schreiben in Read-Only | nvs_err_readonly.yaml | Implementiert |
| NVS-INT-001 | ConfigManager Integration | nvs_int_configmanager.yaml | Implementiert |
| NVS-INT-002 | Sensor-Config Boot | nvs_int_sensor_boot.yaml | Implementiert |
| NVS-INT-003 | Actuator-Config Boot | nvs_int_actuator_boot.yaml | Implementiert |
| NVS-INT-004 | Zone-Config Boot | nvs_int_zone_boot.yaml | Implementiert |

---

## Referenzen

- `El Trabajante/src/services/config/storage_manager.h` - Interface
- `El Trabajante/src/services/config/storage_manager.cpp` - Implementierung
- `El Trabajante/docs/NVS_KEYS.md` - Vollstaendige NVS-Schluessel-Referenz
- `El Trabajante/src/services/config/config_manager.cpp` - ConfigManager Integration

---

*Erstellt gemaess IEC 61508 Best Practices fuer funktionale Sicherheit.*
