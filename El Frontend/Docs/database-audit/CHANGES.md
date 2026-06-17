# Database Column UX Improvements - Changelog

**Datum:** 2026-01-23
**Sprint:** Sprint 3 - UX-Verbesserungen
**Autor:** KI-Agent

---

## Problem (Robin's Feedback)

Robin's Screenshot zeigte kritische UX-Probleme in der Datenbank-Tabelle:

```
VORHER (FALSCH):
┌────────────────────────────────┬──────────────┬─────────────┬────────┬──────────────┬────────┐
│ ID (32-stelliger Hash!)        │ EREIGNIS     │ SCHWEREGRAD │ QUELLE │ QUELL-ID     │ STATUS │
└────────────────────────────────┴──────────────┴─────────────┴────────┴──────────────┴────────┘
```

**Kritikpunkte:**
1. UUID in erster Spalte - nutzlos für Operator
2. Kein Timestamp sichtbar - "Wann ist das passiert?" fehlt
3. Technische Informationen statt menschenlesbarer Daten

---

## Lösung

### Robin's Prinzipien implementiert:

| Prinzip | Umsetzung |
|---------|-----------|
| **Timestamps IMMER sichtbar** | `created_at`, `last_seen` → `defaultVisible: true` |
| **IDs NIEMALS sichtbar** | `id`, `zone_id`, `user_id`, `esp_id` → `defaultVisible: false` |
| **Namen statt IDs** | `zone_name` (true) statt `zone_id` (false) |
| **Operator-Perspektive** | Nur Infos die um 3 Uhr morgens helfen |

---

## Geänderte Dateien

### 1. `src/utils/databaseColumnTranslator.ts`

**Alle 4 Tabellen optimiert:**

#### audit_logs (Robin's Screenshot!)

| Spalte | Vorher | Nachher | Begründung |
|--------|--------|---------|------------|
| `id` | `true` (erste Spalte!) | `false` | UUID nutzlos |
| `created_at` | `true` (letzte Spalte) | `true` (ERSTE Spalte!) | Timestamp kritisch |
| `source_type` | `true` | `false` | "esp32" sagt wenig |
| `source_id` | Label: "Quell-ID" | Label: "Gerät" | Menschenlesbarer |

**Neue Spalten-Reihenfolge:**
```
Zeitpunkt → Ereignis → Schweregrad → Gerät → Status
```

#### esp_devices

| Spalte | Vorher | Nachher | Begründung |
|--------|--------|---------|------------|
| `id` | `false` | `false` | OK |
| `is_zone_master` | `true` | `false` | Technisches Detail |
| `hardware_type` | `true` | `false` | Technisches Detail |
| `last_seen` | `true` | `true` (4. Position) | Timestamp prominent |

**Neue Spalten-Reihenfolge:**
```
Geräte-ID → Name → Status → Zuletzt gesehen → Zone → Firmware
```

#### sensor_configs

| Spalte | Vorher | Nachher | Begründung |
|--------|--------|---------|------------|
| `id` | `false` | `false` | OK |
| `esp_id` | `false` | `false` | UUID in Details |

**Spalten-Reihenfolge:**
```
Name → Typ → GPIO → Schnittstelle → Aktiv → Messintervall
```

#### actuator_configs

| Spalte | Vorher | Nachher | Begründung |
|--------|--------|---------|------------|
| `id` | `false` | `false` | OK |
| `max_runtime_seconds` | `false` | `true` | Sicherheits-Info! |

**Spalten-Reihenfolge:**
```
Name → Typ → GPIO → Aktiv → Max. Laufzeit
```

---

### 2. `src/components/system-monitor/DatabaseTab.vue`

**Problem:** Nutzte alle Backend-Spalten ohne Filterung

**Lösung:**
```typescript
// Vorher: Alle Spalten vom Backend
const translatedColumns = computed(() => {
  return store.currentColumns.map(col => ({...}))
})

// Nachher: Gefiltert nach defaultVisible
const translatedColumns = computed(() => {
  const visibleKeys = getPrimaryColumnKeys(store.currentTable)
  // Filter und ordne nach Translator-Konfiguration
})
```

**Imports hinzugefügt:**
- `getPrimaryColumnKeys`
- `getTableConfig`

---

### 3. `src/components/database/DataTable.vue`

**Problem:** Sortierte Spalten mit Primary Key (id) ZUERST

```typescript
// Vorher (FALSCH):
const visibleColumns = computed(() => {
  const sorted = [...props.columns].sort((a, b) => {
    if (a.primary_key) return -1  // ← ID zuerst!
    ...
  })
})

// Nachher (RICHTIG):
const visibleColumns = computed(() => {
  // Parent hat bereits gefiltert/sortiert
  return props.columns.slice(0, 8)
})
```

---

## Ergebnis

```
NACHHER (RICHTIG):
┌──────────────┬──────────────┬─────────────┬──────────────┬────────┐
│ ZEITPUNKT    │ EREIGNIS     │ SCHWEREGRAD │ GERÄT        │ STATUS │
├──────────────┼──────────────┼─────────────┼──────────────┼────────┤
│ 14:32:15     │ Konfig-Antw. │ Fehler      │ ESP_00000001 │ Fehler │
└──────────────┴──────────────┴─────────────┴──────────────┴────────┘
```

**Verbesserungen:**
- ✅ Timestamp in erster Spalte (für audit_logs)
- ✅ Keine UUIDs mehr sichtbar
- ✅ Menschenlesbare Labels ("Gerät" statt "Quell-ID")
- ✅ Operator-relevante Informationen priorisiert
- ✅ Technische Details nur im Detail-Modal

---

## Verifizierung

```bash
# Build erfolgreich
cd "El Frontend" && npm run build
# ✓ built in 16.21s
```

---

## Zusammenfassung der sichtbaren Spalten

### audit_logs (5 Spalten)
1. Zeitpunkt (created_at)
2. Ereignis (event_type)
3. Schweregrad (severity)
4. Gerät (source_id)
5. Status (status)

### esp_devices (7 Spalten)
1. Geräte-ID (device_id)
2. Name (name)
3. Status (status)
4. Zuletzt gesehen (last_seen)
5. Zone (zone_name)
6. Firmware (firmware_version)

### sensor_configs (6 Spalten)
1. Name (sensor_name)
2. Typ (sensor_type)
3. GPIO (gpio)
4. Schnittstelle (interface_type)
5. Aktiv (enabled)
6. Messintervall (sample_interval_ms)

### actuator_configs (5 Spalten)
1. Name (actuator_name)
2. Typ (actuator_type)
3. GPIO (gpio)
4. Aktiv (enabled)
5. Max. Laufzeit (max_runtime_seconds)
