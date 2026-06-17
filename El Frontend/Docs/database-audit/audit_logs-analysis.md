# Audit-Logs Tabelle - Spalten-Analyse

**Tabelle:** `audit_logs`
**Label:** Ereignisprotokoll
**Datum:** 2026-01-23

---

## Problem (Robin's Screenshot)

```
┌────────────────────────────────┬──────────────┬─────────────┬────────┬──────────────┬────────┐
│ ID ↕                           │ EREIGNIS ↕   │ SCHWEREGRAD │ QUELLE │ QUELL-ID ↕   │ STATUS │
├────────────────────────────────┼──────────────┼─────────────┼────────┼──────────────┼────────┤
│ d85c7aa9fe54451db68ded26f8dec0 │config_respon │ error       │ esp32  │ ESP_00000001 │ error  │
└────────────────────────────────┴──────────────┴─────────────┴────────┴──────────────┴────────┘
```

**Robin's Kritik:**
1. ID-Spalte (32-stelliger Hash) - NUTZLOS für Operator!
2. Keine Uhrzeit sichtbar - "Wann ist das passiert?" FEHLT!
3. "error" zweimal - SCHWEREGRAD und STATUS sind redundant

---

## Operator-Perspektive

> **"Wenn ich um 3 Uhr morgens angerufen werde weil ein Fehler ist - hilft mir diese Spalte SOFORT?"**

| Spalte | Operator braucht das? | Begründung |
|--------|----------------------|------------|
| `created_at` | ✅ **JA!** | "WANN ist der Fehler aufgetreten?" - KRITISCH! |
| `event_type` | ✅ JA | "WAS ist passiert?" |
| `severity` | ✅ JA | "WIE kritisch ist es?" |
| `source_id` | ✅ JA | "WELCHES Gerät hat das Problem?" |
| `status` | ✅ JA | "Ist es gelöst oder noch offen?" |
| `id` | ❌ NEIN | UUID - nutzlos für Operator |
| `source_type` | ❌ NEIN | "esp32" sagt wenig aus |
| `user_id` | ❌ NEIN | UUID - technisch |
| `details` | ❌ NEIN | JSON - zu komplex für Tabelle |
| `error_code` | ❌ NEIN | Technisch - für Details |
| `correlation_id` | ❌ NEIN | UUID - technisch |
| `ip_address` | ❌ NEIN | Für Debugging, nicht Monitoring |

---

## Änderungen

| Spalte | Von | Zu | Begründung |
|--------|-----|-----|-----------|
| `id` | Position 1, sichtbar | `defaultVisible: false` | UUID nutzlos für Operator |
| `created_at` | Position 12 (letzte!) | Position 1 (ERSTE!) | **KRITISCH:** Zeitpunkt muss sofort sichtbar sein |
| `source_type` | `defaultVisible: true` | `defaultVisible: false` | "esp32" sagt wenig aus |
| `source_id` | Label: "Quell-ID" | Label: "Gerät" | Menschenlesbarer |

---

## Resultat

### Haupttabelle zeigt (5 Spalten):
1. **Zeitpunkt** (created_at) - WANN?
2. **Ereignis** (event_type) - WAS?
3. **Schweregrad** (severity) - WIE KRITISCH?
4. **Gerät** (source_id) - WO?
5. **Status** (status) - GELÖST?

### Details-Modal zeigt zusätzlich:
- Datensatz-ID (id) - für Support-Tickets
- Quelltyp (source_type) - esp32, system, api
- Fehlercode (error_code) - für Entwickler
- Fehlerbeschreibung (error_description)
- Details-JSON (details) - vollständige technische Infos
- Korrelations-ID (correlation_id) - für zusammenhängende Events
- IP-Adresse (ip_address) - für Security-Audit

---

## Vorher/Nachher

**VORHER:**
```
ID (32-stellig) | EREIGNIS | SCHWEREGRAD | QUELLE | QUELL-ID | STATUS
```

**NACHHER:**
```
ZEITPUNKT | EREIGNIS | SCHWEREGRAD | GERÄT | STATUS
14:32:15  | Konfig-  | Fehler      | ESP_... | Fehler
```

---

## Robin's Prinzipien - Verifizierung

- ✅ **Timestamp IMMER sichtbar:** `created_at` → `true`, Position 1
- ✅ **IDs NIEMALS sichtbar:** `id` → `false`
- ✅ **Namen statt IDs:** Label "Gerät" statt "Quell-ID"
- ✅ **Redundanz geprüft:** `severity` und `status` behalten (unterschiedliche Bedeutung)
