# ESP-Devices Tabelle - Spalten-Analyse

**Tabelle:** `esp_devices`
**Label:** ESP32-Geräte
**Datum:** 2026-01-23

---

## Operator-Perspektive

> **"Wenn ich um 3 Uhr morgens angerufen werde weil ein Gerät offline ist - hilft mir diese Spalte SOFORT?"**

| Spalte | Operator braucht das? | Begründung |
|--------|----------------------|------------|
| `device_id` | ✅ **JA!** | "WELCHES Gerät?" (ESP_12AB34CD) |
| `name` | ✅ **JA!** | Menschenlesbarer Name |
| `status` | ✅ **JA!** | "Online oder Offline?" |
| `last_seen` | ✅ **JA!** | "WANN war es zuletzt aktiv?" - KRITISCH! |
| `zone_name` | ✅ **JA!** | "WO steht das Gerät?" |
| `firmware_version` | ✅ JA | Für Troubleshooting wichtig |
| `id` | ❌ NEIN | UUID - technisch |
| `zone_id` | ❌ NEIN | UUID - technisch (nutze `zone_name`!) |
| `is_zone_master` | ❌ NEIN | Technisches Detail |
| `hardware_type` | ❌ NEIN | Technisches Detail |
| `ip_address` | ❌ NEIN | Für Details |
| `mac_address` | ❌ NEIN | Für Details |
| `health_status` | ❌ NEIN | Duplikat von `status` |
| `discovered_at` | ❌ NEIN | Metadaten |
| `approved_at` | ❌ NEIN | Metadaten |
| `approved_by` | ❌ NEIN | Metadaten |
| `capabilities` | ❌ NEIN | JSON - technisch |
| `created_at` | ❌ NEIN | Metadaten |
| `updated_at` | ❌ NEIN | Metadaten |

---

## Änderungen

| Spalte | Von | Zu | Begründung |
|--------|-----|-----|-----------|
| `is_zone_master` | `defaultVisible: true` | `defaultVisible: false` | Technisches Detail |
| `hardware_type` | `defaultVisible: true` | `defaultVisible: false` | Technisches Detail |
| `last_seen` | Position 11 | Position 4 | Timestamp prominenter |

---

## Resultat

### Haupttabelle zeigt (7 Spalten):
1. **Geräte-ID** (device_id) - ESP_12AB34CD
2. **Name** (name) - Menschenlesbarer Name
3. **Status** (status) - Online/Offline
4. **Zuletzt gesehen** (last_seen) - vor 5 Min.
5. **Zone** (zone_name) - Gewächshaus 1
6. **Firmware** (firmware_version) - v1.2.3

### Details-Modal zeigt zusätzlich:
- Datensatz-ID (id)
- Zonen-ID (zone_id)
- Zonen-Master (is_zone_master)
- Hardware-Typ (hardware_type)
- IP-Adresse (ip_address)
- MAC-Adresse (mac_address)
- Gesundheit (health_status)
- Entdeckt am (discovered_at)
- Freigegeben am (approved_at)
- Freigegeben von (approved_by)
- Fähigkeiten (capabilities)
- Registriert am (created_at)
- Aktualisiert am (updated_at)

---

## Robin's Prinzipien - Verifizierung

- ✅ **Timestamp IMMER sichtbar:** `last_seen` → `true`, Position 4
- ✅ **IDs NIEMALS sichtbar:** `id` → `false`, `zone_id` → `false`
- ✅ **Namen statt IDs:** `zone_name` (true) statt `zone_id` (false)
