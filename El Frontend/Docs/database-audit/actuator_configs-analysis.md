# Actuator-Configs Tabelle - Spalten-Analyse

**Tabelle:** `actuator_configs`
**Label:** Aktorkonfigurationen
**Datum:** 2026-01-23

---

## Operator-Perspektive

> **"Wenn ein Aktor nicht funktioniert - welche Info brauche ich SOFORT?"**

| Spalte | Operator braucht das? | Begründung |
|--------|----------------------|------------|
| `actuator_name` | ✅ **JA!** | "WIE heißt der Aktor?" |
| `actuator_type` | ✅ **JA!** | "WAS ist er?" (Pumpe, Relais) |
| `gpio` | ✅ **JA!** | "AN WELCHEM Pin?" |
| `enabled` | ✅ **JA!** | "IST er aktiv?" |
| `max_runtime_seconds` | ✅ **JA!** | "WIE LANGE darf er laufen?" - SICHERHEIT! |
| `id` | ❌ NEIN | UUID - technisch |
| `esp_id` | ❌ NEIN | UUID - technisch |
| `default_state` | ❌ NEIN | Technisches Detail |
| `inverted` | ❌ NEIN | Technisches Detail |
| `pwm_frequency` | ❌ NEIN | Technisches Detail |
| `created_at` | ❌ NEIN | Metadaten |
| `updated_at` | ❌ NEIN | Metadaten |

---

## Änderungen

| Spalte | Von | Zu | Begründung |
|--------|-----|-----|-----------|
| `max_runtime_seconds` | `defaultVisible: false` | `defaultVisible: true` | **SICHERHEITS-INFO!** Operator muss wissen ob Timeout konfiguriert ist |

---

## Resultat

### Haupttabelle zeigt (5 Spalten):
1. **Name** (actuator_name) - Menschenlesbarer Name
2. **Typ** (actuator_type) - Pumpe, Relais, PWM
3. **GPIO** (gpio) - GPIO 25
4. **Aktiv** (enabled) - Ja/Nein
5. **Max. Laufzeit** (max_runtime_seconds) - 60 s oder "Unbegrenzt"

### Details-Modal zeigt zusätzlich:
- Datensatz-ID (id)
- Gerät (esp_id)
- Standardzustand (default_state)
- Invertiert (inverted)
- PWM-Frequenz (pwm_frequency)
- Erstellt am (created_at)
- Aktualisiert am (updated_at)

---

## Robin's Prinzipien - Verifizierung

- ✅ **IDs NIEMALS sichtbar:** `id` → `false`, `esp_id` → `false`
- ✅ **Sicherheits-Info prominent:** `max_runtime_seconds` → `true`
- ✅ **Operator-relevante Info:** Name, Typ, GPIO, Aktiv, Timeout
