# Sensor-Configs Tabelle - Spalten-Analyse

**Tabelle:** `sensor_configs`
**Label:** Sensorkonfigurationen
**Datum:** 2026-01-23

---

## Operator-Perspektive

> **"Wenn ich einen Sensor konfigurieren muss - welche Info brauche ich SOFORT?"**

| Spalte | Operator braucht das? | Begründung |
|--------|----------------------|------------|
| `sensor_name` | ✅ **JA!** | "WIE heißt der Sensor?" |
| `sensor_type` | ✅ **JA!** | "WAS misst er?" (Temperatur, pH) |
| `gpio` | ✅ **JA!** | "AN WELCHEM Pin?" |
| `interface_type` | ✅ JA | "WIE kommuniziert er?" (I2C, OneWire) |
| `enabled` | ✅ **JA!** | "IST er aktiv?" |
| `sample_interval_ms` | ✅ JA | "WIE oft misst er?" |
| `id` | ❌ NEIN | UUID - technisch |
| `esp_id` | ❌ NEIN | UUID - technisch |
| `i2c_address` | ❌ NEIN | Technisches Detail |
| `onewire_address` | ❌ NEIN | Technisches Detail |
| `pi_enhanced` | ❌ NEIN | Technisches Detail |
| `calibration_data` | ❌ NEIN | JSON - komplex |
| `thresholds` | ❌ NEIN | JSON - komplex |
| `created_at` | ❌ NEIN | Metadaten |
| `updated_at` | ❌ NEIN | Metadaten |

---

## Änderungen

| Spalte | Von | Zu | Begründung |
|--------|-----|-----|-----------|
| - | - | - | Keine Änderungen nötig - bereits gut konfiguriert |

---

## Resultat

### Haupttabelle zeigt (6 Spalten):
1. **Name** (sensor_name) - Menschenlesbarer Name
2. **Typ** (sensor_type) - Temperatur, pH, etc.
3. **GPIO** (gpio) - GPIO 34
4. **Schnittstelle** (interface_type) - I2C, OneWire, Analog
5. **Aktiv** (enabled) - Ja/Nein
6. **Messintervall** (sample_interval_ms) - 30 s

### Details-Modal zeigt zusätzlich:
- Datensatz-ID (id)
- Gerät (esp_id)
- I2C-Adresse (i2c_address)
- OneWire-Adresse (onewire_address)
- Pi-Enhanced (pi_enhanced)
- Kalibrierung (calibration_data)
- Schwellwerte (thresholds)
- Erstellt am (created_at)
- Aktualisiert am (updated_at)

---

## Robin's Prinzipien - Verifizierung

- ✅ **IDs NIEMALS sichtbar:** `id` → `false`, `esp_id` → `false`
- ✅ **Technische Details in Modal:** JSON-Felder, Adressen
- ✅ **Operator-relevante Info prominent:** Name, Typ, GPIO, Aktiv
