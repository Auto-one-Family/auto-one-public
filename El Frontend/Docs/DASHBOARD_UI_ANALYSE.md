# Entwickler-Briefing: Dashboard UI Feinschliff & Bug Fix

**Projekt:** AutomationOne Framework  
**Datum:** 2026-01-04  
**Priorität:** Hoch  
**Geschätzter Aufwand:** 8-12 Stunden

---

## Teil A: Systemeinführung

### A.1 Was ist AutomationOne?

AutomationOne ist ein industrielles IoT-Framework für Gewächshaus-Automatisierung mit einer **4-Layer-Architektur**:

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: God (KI-Layer) - OPTIONAL, noch nicht implementiert   │
└─────────────────────────────────────────────────────────────────┘
                              ↕ HTTP REST
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: God-Kaiser (Raspberry Pi 5)                            │
│ → Control Hub, MQTT Broker, PostgreSQL, Logic Engine            │
│ → Code: El Servador/god_kaiser_server/                          │
└─────────────────────────────────────────────────────────────────┘
                              ↕ MQTT (TLS)
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: Kaiser-Nodes (Pi Zero) - OPTIONAL für Skalierung       │
└─────────────────────────────────────────────────────────────────┘
                              ↕ MQTT
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 4: ESP32-Agenten ("El Trabajante")                        │
│ → Sensor-Auslesung, Aktor-Steuerung                             │
│ → Code: El Trabajante/ (Firmware, ~13.300 LOC)                  │
└─────────────────────────────────────────────────────────────────┘
```

**Kern-Prinzip:** Server-Centric Architecture
- ESP32 Geräte sind "dumm" - senden nur RAW-Daten
- Server (God-Kaiser) übernimmt alle Intelligenz
- Python-Libraries verarbeiten Sensor-Daten serverseitig

### A.2 Die drei Code-Repositories

| Repository | Sprache | Zweck |
|------------|---------|-------|
| **El Trabajante** | C++ (PlatformIO) | ESP32 Firmware |
| **El Servador** | Python (FastAPI) | Backend-Server |
| **El Frontend** | TypeScript (Vue 3) | Web-Interface |

**Für diesen Auftrag relevant:** `El Frontend` + `El Servador`

### A.3 Mock ESP System

Ein **Alleinstellungsmerkmal** von AutomationOne: Vollständige Hardware-Simulation ohne physische Geräte.

```
Mock ESP = Virtuelle ESP32-Simulation im Server
         → Sendet echte MQTT-Nachrichten
         → Durchläuft identische Processing-Pipeline wie echte Hardware
         → Ermöglicht vollständiges Testing ohne Hardware
```

**Dual-Storage-Architektur:**
- **PostgreSQL:** Persistente Daten (Name, Zone, Metadata)
- **In-Memory (SimulationScheduler):** Live-Simulation (Heartbeats, Sensor-Werte)

---

## Teil B: Orientierung im Code

### B.1 Pflichtlektüre (in dieser Reihenfolge)

| Datei | Pfad | Inhalt | Lesezeit |
|-------|------|--------|----------|
| **1. CLAUDE.md** | `.claude/CLAUDE.md` | Gesamtübersicht, ESP32-Architektur, Quick Reference | 15 min |
| **2. Hierarchie.md** | `.claude/Hierarchie.md` | 4-Layer-Architektur, Zone-System, Code-Locations | 20 min |
| **3. CLAUDE_FRONTEND.md** | `.claude/CLAUDE_FRONTEND.md` | Frontend-Struktur, Stores, API-Layer | 10 min |
| **4. CLAUDE_SERVER.md** | `.claude/CLAUDE_SERVER.md` | Backend-API, MQTT-Handler, Database | 15 min |

### B.2 Relevante Flow-Dokumentation

| Dokument | Pfad | Relevanz für diesen Auftrag |
|----------|------|----------------------------|
| **14-satellite-cards-flow** | `.claude/14-satellite-cards-flow-server-frontend.md` | Satellite-Komponenten, Layout-System |
| **VIEW_ANALYSIS.md** | `.claude/VIEW_ANALYSIS.md` | View-Struktur, API-Endpoints |
| **API_PAYLOAD_EXAMPLES.md** | `.claude/API_PAYLOAD_EXAMPLES.md` | Request/Response Beispiele |

### B.3 Projekt-Struktur (Frontend)

```
El Frontend/
├── src/
│   ├── api/
│   │   ├── esp.ts          ← ESPDevice Interface, API-Calls
│   │   ├── debug.ts        ← Mock ESP API
│   │   └── index.ts        ← Axios-Wrapper
│   ├── stores/
│   │   └── esp.ts          ← Pinia Store für ESP-Geräte
│   ├── components/
│   │   ├── esp/
│   │   │   ├── ESPOrbitalLayout.vue   ← HAUPT-Dashboard-Komponente
│   │   │   ├── ESPCard.vue            ← Legacy Card
│   │   │   ├── ESPSettingsPopover.vue ← Geräte-Einstellungen
│   │   │   ├── SensorSatellite.vue    ← Sensor-Karte
│   │   │   └── ActuatorSatellite.vue  ← Aktor-Karte
│   │   └── modals/
│   │       └── CreateMockEspModal.vue ← Mock ESP erstellen
│   ├── views/
│   │   └── DashboardView.vue          ← Dashboard-Seite
│   └── style.css                       ← Design-Tokens, CSS Variables
```

### B.4 Projekt-Struktur (Backend - relevant)

```
El Servador/god_kaiser_server/
├── src/
│   ├── api/v1/
│   │   ├── debug.py        ← Mock ESP Endpoints
│   │   └── esp.py          ← ESP Device Endpoints
│   ├── schemas/
│   │   ├── debug.py        ← MockESPResponse Schema
│   │   └── esp.py          ← ESPDeviceResponse Schema
│   ├── services/
│   │   └── simulation_scheduler.py  ← Mock-Simulation Engine
│   └── db/
│       └── models/esp.py   ← ESPDevice DB Model
```

---

## Teil C: Auftragsübersicht

### C.1 Die drei Arbeitsbereiche

| # | Bereich | Typ | Priorität |
|---|---------|-----|-----------|
| **1** | Auto-Heartbeat UI-Sync Bug | 🔴 Bug Fix | KRITISCH |
| **2** | ESP Card & Satellite Design | 🎨 Design | HOCH |
| **3** | Geräte-Einstellungen Design | 🎨 Design | MITTEL |

### C.2 Identifizierter Bug (aus Codebase-Analyse)

**Problem:** `auto_heartbeat` Status geht nach Page-Reload verloren

**Root Cause:**
1. Beim Erstellen wird `auto_heartbeat: true` korrekt gespeichert
2. `fetchAll()` überschreibt den Store mit Daten von `GET /esp/devices`
3. `ESPDeviceResponse` (Backend-Schema) enthält **kein** `auto_heartbeat` Feld
4. → UI zeigt `false` obwohl Heartbeat aktiv ist

**Beweis:**
```python
# schemas/esp.py - ESPDeviceResponse
# → KEIN auto_heartbeat Feld vorhanden

# schemas/debug.py - MockESPResponse  
auto_heartbeat: bool  # ← Nur hier vorhanden
```

---

## Teil D: Implementierungsphasen

---

## Phase 1: Auto-Heartbeat Bug Fix

**Ziel:** `auto_heartbeat` Status bleibt nach Reload erhalten  
**Geschätzter Aufwand:** 2-3 Stunden

### Phase 1.1: Backend-Erweiterung

**Datei:** `El Servador/god_kaiser_server/src/schemas/esp.py`

**Aufgabe:** `ESPDeviceResponse` um Mock-spezifische Felder erweitern

```python
# VORHER (ca. Zeile 45-70):
class ESPDeviceResponse(BaseModel):
    id: int
    esp_id: str
    name: Optional[str]
    hardware_type: Optional[str]
    zone_id: Optional[str]
    zone_name: Optional[str]
    # ... weitere Felder

# NACHHER - Hinzufügen:
class ESPDeviceResponse(BaseModel):
    # ... bestehende Felder ...
    
    # Mock-spezifische Felder (nur für Mock ESPs relevant)
    auto_heartbeat: Optional[bool] = None
    heartbeat_interval_seconds: Optional[int] = None
```

### Phase 1.2: Repository-Erweiterung

**Datei:** `El Servador/god_kaiser_server/src/db/repositories/esp_repository.py`

**Aufgabe:** `get_all_devices()` und `get_device()` um Simulation-Status erweitern

**Recherche-Schritte:**
1. Finde `get_all_devices()` Methode
2. Prüfe ob `simulation_config` aus der DB geladen wird
3. Falls ja: Mapping zu Response hinzufügen
4. Falls nein: Join mit `simulation_scheduler` Status

**Hinweis:** Mock ESPs haben `simulation_config` als JSON-Feld in der DB:
```python
# Erwartete Struktur:
simulation_config = {
    "auto_heartbeat": True,
    "heartbeat_interval_seconds": 60
}
```

### Phase 1.3: API-Endpoint Anpassung

**Datei:** `El Servador/god_kaiser_server/src/api/v1/esp.py`

**Aufgabe:** `get_devices()` Endpoint nutzt erweiterte Response

**Prüfpunkte:**
- [ ] Response-Schema verwendet `ESPDeviceResponse`
- [ ] `auto_heartbeat` wird aus DB/Simulation geladen
- [ ] Nur für Mock ESPs gefüllt (Real ESPs: `null`)

### Phase 1.4: Frontend Type-Update

**Datei:** `El Frontend/src/api/esp.ts`

**Aufgabe:** `ESPDevice` Interface aktualisieren (falls nötig)

```typescript
// Zeile ~62 - Prüfen ob bereits vorhanden:
export interface ESPDevice {
  // ... bestehende Felder ...
  auto_heartbeat?: boolean        // ← Sicherstellen
  heartbeat_interval_seconds?: number  // ← Sicherstellen
}
```

### Phase 1.5: Verifizierung

**Test-Szenario:**
1. Mock ESP erstellen mit `auto_heartbeat: true`
2. Seite neu laden (F5)
3. Geräte-Einstellungen öffnen
4. **Erwartung:** Toggle zeigt "aktiv"

**Debug-Logging (temporär hinzufügen):**
```typescript
// esp.ts Store - fetchAll()
console.log('Fetched devices:', devices.value.map(d => ({
  id: d.esp_id,
  auto_heartbeat: d.auto_heartbeat
})))
```

---

## Phase 2: ESP Card & Satellite Design

**Ziel:** Luxuriöseres Design, bessere Lesbarkeit, visueller Zusammenhalt  
**Geschätzter Aufwand:** 3-4 Stunden

### Phase 2.1: Mock/Real Unterscheidung verbessern

**Dateien:**
- `El Frontend/src/components/esp/ESPOrbitalLayout.vue`
- `El Frontend/src/style.css`

**Aktuelle Unterscheidung:**
- Badge in Einstellungen (klein, kaum sichtbar)

**Gewünschte Unterscheidung:**

| Element | Mock | Real |
|---------|------|------|
| **Card Border** | Subtiler violetter Schimmer | Subtiler cyan Schimmer |
| **Type Badge** | Oben rechts auf Card | Oben rechts auf Card |
| **Badge Farbe** | `--color-mock` (#a78bfa) | `--color-real` (#22d3ee) |

**Implementierung:**

```vue
<!-- ESPOrbitalLayout.vue - esp-info-compact Section -->
<div 
  class="esp-info-compact"
  :class="{
    'esp-info-compact--mock': isMock,
    'esp-info-compact--real': !isMock
  }"
>
  <!-- Type Badge (NEU) -->
  <div class="esp-type-badge" :class="isMock ? 'badge--mock' : 'badge--real'">
    {{ isMock ? 'MOCK' : 'REAL' }}
  </div>
  
  <!-- ... bestehender Content ... -->
</div>
```

```css
/* style.css - Neue Styles */

/* Card-Varianten */
.esp-info-compact--mock {
  border-color: rgba(167, 139, 250, 0.2);
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.15),
    0 0 20px rgba(167, 139, 250, 0.05);
}

.esp-info-compact--real {
  border-color: rgba(34, 211, 238, 0.2);
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.15),
    0 0 20px rgba(34, 211, 238, 0.05);
}

/* Type Badge */
.esp-type-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
}

.badge--mock {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
  border: 1px solid rgba(167, 139, 250, 0.3);
}

.badge--real {
  background: rgba(34, 211, 238, 0.15);
  color: #22d3ee;
  border: 1px solid rgba(34, 211, 238, 0.3);
}
```

### Phase 2.2: Satellites "schwebender" machen

**Datei:** `El Frontend/src/components/esp/ESPOrbitalLayout.vue`

**Aktuell:** Satellites direkt an ESP Card anliegend  
**Gewünscht:** Mehr visuelle Trennung, "schwebender" Effekt

**CSS-Anpassungen:**

```css
/* Satellite Cards - Schwebender Effekt */
.sensor-satellite,
.actuator-satellite {
  /* Bestehende Styles... */
  
  /* NEU: Schwebender Effekt */
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.2),
    0 4px 16px rgba(0, 0, 0, 0.1);
  
  /* Subtiler Glow basierend auf Status */
  transition: all 0.2s ease;
}

.sensor-satellite:hover,
.actuator-satellite:hover {
  transform: translateY(-2px);
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.25),
    0 8px 24px rgba(0, 0, 0, 0.15);
}

/* Abstand zwischen Satellites und ESP Card */
.esp-horizontal-layout__column {
  gap: 0.5rem;  /* Erhöht von 0.375rem */
}

.esp-horizontal-layout {
  gap: 1rem;    /* Erhöht von 0.75rem */
}
```

### Phase 2.3: Lesbarkeit verbessern

**Datei:** `El Frontend/src/style.css`

**Anpassungen:**

```css
/* Kontrast erhöhen */
:root {
  /* VORHER: --color-text-secondary: #a0a0b0 */
  --color-text-secondary: #b0b0c0;  /* Heller */
  
  /* VORHER: --color-text-muted: #606070 */
  --color-text-muted: #707080;      /* Heller */
}

/* Sensor-Werte prominenter */
.sensor-satellite__value {
  font-size: 0.875rem;    /* Erhöht von 0.8125rem */
  font-weight: 700;       /* Erhöht von 600 */
}

/* Labels klarer */
.sensor-satellite__name,
.actuator-satellite__name {
  font-size: 0.75rem;     /* Erhöht von 0.6875rem */
  color: var(--color-text-secondary);
}
```

### Phase 2.4: ESPs ohne Sensoren/Aktoren

**Datei:** `El Frontend/src/components/esp/ESPOrbitalLayout.vue`

**Aktuell:** Leere Spalten werden ausgeblendet  
**Gewünscht:** Valider Zustand, keine visuellen Artefakte

**Prüfpunkte:**
- [ ] ESP ohne Sensoren: Linke Spalte leer oder mit Placeholder
- [ ] ESP ohne Aktoren: Rechte Spalte leer oder mit Placeholder
- [ ] ESP ohne beides: Nur zentrale Card, keine leeren Bereiche

**Implementierung (optional - nur wenn gewünscht):**

```vue
<!-- Placeholder für leere Sensor-Spalte -->
<div v-if="sensors.length === 0" class="satellite-placeholder">
  <span class="satellite-placeholder__text">Keine Sensoren</span>
</div>
```

```css
.satellite-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60px;
  border: 1px dashed var(--glass-border);
  border-radius: 0.5rem;
  opacity: 0.5;
}

.satellite-placeholder__text {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}
```

---

## Phase 3: Geräte-Einstellungen Design

**Ziel:** Konsistentes Spacing, bessere visuelle Hierarchie  
**Geschätzter Aufwand:** 2-3 Stunden

### Phase 3.1: Spacing-Konsistenz

**Datei:** `El Frontend/src/components/esp/ESPSettingsPopover.vue`

**Design-Tokens definieren (am Anfang der `<style>` Section):**

```css
.esp-settings-popover {
  /* Spacing-Tokens */
  --popover-padding: 1.25rem;
  --section-gap: 1rem;
  --section-padding: 0.875rem;
  --item-gap: 0.625rem;
  --label-gap: 0.375rem;
}
```

**Einheitlich anwenden:**

```css
.popover-section {
  padding: var(--section-padding);
  margin-bottom: var(--section-gap);
}

.popover-section:last-child {
  margin-bottom: 0;
}

.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--item-gap);
}

.section-label {
  font-size: 0.6875rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: var(--label-gap);
}
```

### Phase 3.2: Section-Titel verbessern

**Aktuell:** Kleine, unauffällige Titel  
**Gewünscht:** Größer, mit Icons

```vue
<!-- Section Header Template -->
<div class="section-header">
  <component :is="sectionIcon" class="section-header__icon" />
  <span class="section-header__title">{{ title }}</span>
</div>
```

```css
.section-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.section-header__icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
}

.section-header__title {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
}
```

**Icons pro Section:**

| Section | Icon (Lucide) |
|---------|---------------|
| IDENTIFIKATION | `Tag` |
| STATUS | `Activity` |
| ZONE | `MapPin` |
| MOCK-STEUERUNG | `Settings2` |
| GEFAHRENZONE | `AlertTriangle` |

### Phase 3.3: Status-Grid Layout

**Datei:** `El Frontend/src/components/esp/ESPSettingsPopover.vue`

**Aktuell:** Status-Werte lose angeordnet  
**Gewünscht:** Strukturiertes Grid

```vue
<div class="status-grid">
  <div class="status-item">
    <span class="status-label">Verbindung</span>
    <span class="status-value">
      <Badge :variant="isOnline ? 'success' : 'error'">
        {{ isOnline ? 'Online' : 'Offline' }}
      </Badge>
    </span>
  </div>
  
  <div class="status-item">
    <span class="status-label">WiFi</span>
    <span class="status-value">
      <WifiDisplay :rssi="wifiRssi" />
    </span>
  </div>
  
  <!-- ... weitere Items ... -->
</div>
```

```css
.status-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.status-label {
  font-size: 0.625rem;
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.status-value {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}
```

### Phase 3.4: Auto-Heartbeat Toggle verbessern

**Aktuell:** Kleiner Toggle, schwer zu treffen  
**Gewünscht:** Größerer Hit-Bereich, klare Labels

```vue
<div class="auto-heartbeat-control">
  <div class="auto-heartbeat-info">
    <span class="auto-heartbeat-label">Automatische Heartbeats</span>
    <span class="auto-heartbeat-description">
      {{ autoHeartbeatEnabled ? `Alle ${heartbeatInterval}s` : 'Deaktiviert' }}
    </span>
  </div>
  
  <button 
    class="toggle-switch"
    :class="{ 'toggle-switch--active': autoHeartbeatEnabled }"
    @click="handleAutoHeartbeatToggle"
    role="switch"
    :aria-checked="autoHeartbeatEnabled"
  >
    <span class="toggle-switch__knob" />
  </button>
</div>
```

```css
.auto-heartbeat-control {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.625rem;
  background: var(--color-bg-tertiary);
  border-radius: 0.5rem;
  cursor: pointer;
}

.auto-heartbeat-control:hover {
  background: var(--color-bg-hover);
}

.auto-heartbeat-info {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.auto-heartbeat-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.auto-heartbeat-description {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

/* Toggle Switch - Größer */
.toggle-switch {
  width: 48px;
  height: 26px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: 13px;
  position: relative;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-switch--active {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.4), rgba(139, 92, 246, 0.3));
  border-color: rgba(167, 139, 250, 0.5);
}

.toggle-switch__knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background: var(--color-text-secondary);
  border-radius: 50%;
  transition: all 0.2s;
}

.toggle-switch--active .toggle-switch__knob {
  left: 25px;
  background: #a78bfa;
  box-shadow: 0 0 8px rgba(167, 139, 250, 0.6);
}
```

---

## Teil E: Qualitätskriterien

### E.1 Code-Standards

- [ ] TypeScript strict mode - keine `any` Types
- [ ] Vue 3 Composition API mit `<script setup>`
- [ ] CSS Custom Properties für alle Farben/Spacing
- [ ] Responsive Design (Mobile, Tablet, Desktop)
- [ ] Accessibility (ARIA Labels, Keyboard Navigation)

### E.2 Naming Conventions

```
Dateien:     PascalCase.vue, camelCase.ts
Komponenten: PascalCase
CSS-Klassen: kebab-case mit BEM (.block__element--modifier)
Variables:   camelCase
Constants:   UPPER_SNAKE_CASE
```

### E.3 Commit-Format

```
feat(frontend): add mock/real type badge to ESP cards
fix(backend): include auto_heartbeat in ESPDeviceResponse
style(frontend): improve satellite card shadows and spacing
```

---

## Teil F: Verifizierung

### F.1 Test-Checkliste Phase 1 (Bug Fix)

- [ ] Mock ESP erstellen mit `auto_heartbeat: true`
- [ ] Seite neu laden
- [ ] Einstellungen öffnen → Toggle zeigt "aktiv"
- [ ] Toggle deaktivieren → Speichert korrekt
- [ ] Seite neu laden → Toggle zeigt "inaktiv"
- [ ] Real ESP hat kein Auto-Heartbeat Feld

### F.2 Test-Checkliste Phase 2 (Card Design)

- [ ] Mock ESP hat violetten Border-Schimmer
- [ ] Real ESP hat cyan Border-Schimmer
- [ ] Type Badge oben rechts sichtbar
- [ ] Satellites haben Schatten und Hover-Effekt
- [ ] Text ist gut lesbar (Kontrast prüfen)
- [ ] ESP ohne Sensoren zeigt keine leeren Bereiche

### F.3 Test-Checkliste Phase 3 (Settings Design)

- [ ] Einheitliches Spacing in allen Sections
- [ ] Section-Titel haben Icons
- [ ] Status-Grid ist übersichtlich
- [ ] Auto-Heartbeat Toggle ist größer und klickbar
- [ ] Alle Hover-States funktionieren

---

## Teil G: Ansprechpartner & Ressourcen

### G.1 Bei Fragen

- **Architektur-Fragen:** CLAUDE.md, Hierarchie.md konsultieren
- **API-Fragen:** API_PAYLOAD_EXAMPLES.md, CLAUDE_SERVER.md
- **Design-Fragen:** style.css (Design-Tokens), 14-satellite-cards-flow

### G.2 Hilfreiche Commands

```bash
# Frontend starten
cd "El Frontend"
npm run dev

# Backend starten
cd "El Servador"
poetry run uvicorn god_kaiser_server.src.main:app --reload

# Tests ausführen (Backend)
cd "El Servador"
poetry run pytest god_kaiser_server/tests/ -v
```

### G.3 Browser DevTools

- **Vue DevTools:** Komponenten-Hierarchie, Store-Inspection
- **Network Tab:** API-Responses prüfen (`auto_heartbeat` Feld)
- **Console:** Debug-Logs für Store-Updates

---

## Zusammenfassung der Phasen

| Phase | Aufgabe | Dateien | Aufwand |
|-------|---------|---------|---------|
| **1.1** | Backend Schema erweitern | `schemas/esp.py` | 30 min |
| **1.2** | Repository erweitern | `repositories/esp_repository.py` | 45 min |
| **1.3** | API Endpoint anpassen | `api/v1/esp.py` | 30 min |
| **1.4** | Frontend Type Update | `api/esp.ts` | 15 min |
| **1.5** | Verifizierung | - | 30 min |
| **2.1** | Mock/Real Badge | `ESPOrbitalLayout.vue`, `style.css` | 1h |
| **2.2** | Satellite Shadows | `style.css` | 30 min |
| **2.3** | Lesbarkeit | `style.css` | 30 min |
| **2.4** | Leere Zustände | `ESPOrbitalLayout.vue` | 30 min |
| **3.1** | Spacing-Konsistenz | `ESPSettingsPopover.vue` | 45 min |
| **3.2** | Section-Titel | `ESPSettingsPopover.vue` | 30 min |
| **3.3** | Status-Grid | `ESPSettingsPopover.vue` | 45 min |
| **3.4** | Toggle verbessern | `ESPSettingsPopover.vue` | 30 min |

**Gesamtaufwand:** ~8-10 Stunden

---

*Briefing erstellt am 2026-01-04*  
*Basierend auf Codebase-Analyse vom gleichen Tag*