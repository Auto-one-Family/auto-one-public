# Vision - UI-Ziele und Roadmap

> **Dokument-Typ:** Strategische Roadmap & Implementierungsübersicht  
> **Letzte Aktualisierung:** 20. Dezember 2025 (Code-verifiziert)  
> **Verknüpfte System Flows:** [Alle Flows](../System%20Flows/)

---

## 🎯 Quick Status Overview

> ⚠️ **HINWEIS:** Diese Übersicht wurde am 20.12.2025 gegen den aktuellen Code verifiziert.
> Status-Angaben sind mit `[IST]` für implementiert und `[SOLL]` für geplant markiert.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTOMATIONONE - IMPLEMENTIERUNGSSTAND                     │
│                        (Code-verifiziert: 20.12.2025)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  KERN-SYSTEM           ████████████████████░░░░  85%  ✅ Production-Ready   │
│  ├─ Boot & Discovery   ██████████████████████████  100%  ✅ [IST]           │
│  ├─ Sensor Reading     ██████████████████████████  100%  ✅ [IST]           │
│  ├─ Actuator Control   ██████████████████████████  100%  ✅ [IST]           │
│  ├─ Zone Management    ██████████████████████████  100%  ✅ [IST]           │
│  └─ Error Recovery     ████████████████████░░░░░░  80%   ✅ [IST]           │
│                                                                             │
│  FRONTEND-UI           ████████████████░░░░░░░░░░  65%  🔄 In Progress      │
│  ├─ Views (15/16)      ██████████████████████████  94%   ✅ [IST]           │
│  ├─ Unified Device View██████████████████████████  100%  ✅ [IST]           │
│  ├─ Satellite Kompon.  ██████████████████████████  100%  ✅ [IST]           │
│  ├─ Satellite Layout   ░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    📋 [SOLL]         │
│  ├─ Connection Lines   ██████████████░░░░░░░░░░░░  50%   🔄 [IST: SVG]     │
│  ├─ Zone Drag & Drop   ░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    📋 [SOLL]         │
│  └─ Logic Builder UI   ░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    📋 [SOLL: Placeholder] │
│                                                                             │
│  SICHERHEIT            ██████████████████████████  100%  ✅ Production-Ready │
│  ├─ Authentication     ██████████████████████████  100%  ✅ [IST]           │
│  ├─ Authorization      ██████████████████████████  100%  ✅ [IST]           │
│  └─ User Management    ██████████████████████████  100%  ✅ [IST]           │
│                                                                             │
│  AUTOMATION            ██████████████████░░░░░░░░  70%  🔄 In Progress      │
│  ├─ Logic Engine (BE)  ████████████████████░░░░░░  80%   ✅ [IST: Backend]  │
│  ├─ Logic Engine (FE)  ░░░░░░░░░░░░░░░░░░░░░░░░░░  0%    📋 [SOLL]         │
│  └─ Cross-ESP Rules    ████████████░░░░░░░░░░░░░░  45%   🔄 [IST: Backend] │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📑 Inhaltsverzeichnis

1. [Implementierungsstand-Matrix](#implementierungsstand-matrix)
2. [Sidebar-Navigation](#sidebar-navigation)
3. [Dashboard - Zielzustand](#dashboard---zielzustand)
4. [Geräte-Ansicht](#geräte-ansicht---alle-esps)
5. [Sensoren-Ansicht](#sensoren-ansicht)
6. [Aktoren-Ansicht](#aktoren-ansicht)
7. [Relevante Code-Dateien](#relevante-code-dateien)
8. [Roadmap & Prioritäten](#roadmap--prioritäten)

---

## Implementierungsstand-Matrix

### Legende

| Symbol | Bedeutung | Industrie-Standard |
|--------|-----------|-------------------|
| ✅ | **Implementiert** - Getestet & Production-Ready | MVP+ |
| 🔄 | **In Arbeit** - Teilweise implementiert | Development |
| 📋 | **Geplant** - Design vorhanden, nicht implementiert | Roadmap |
| ❌ | **Fehlt** - Nicht geplant oder blockiert | - |

### Kern-Features mit System Flow Verlinkung

| Feature | IST | SOLL | System Flow | Priorität |
|---------|-----|------|-------------|-----------|
| **ESP Boot & Discovery** | ✅ 100% | ✅ | [01-boot-sequence](../System%20Flows/01-boot-sequence-server-frontend.md) | 🔴 Kritisch |
| **Sensor Daten Erfassung** | ✅ 100% | ✅ | [02-sensor-reading](../System%20Flows/02-sensor-reading-flow-server-frontend.md) | 🔴 Kritisch |
| **Aktor Steuerung** | ✅ 100% | ✅ | [03-actuator-command](../System%20Flows/03-actuator-command-flow-server-frontend.md) | 🔴 Kritisch |
| **Runtime Config** | ✅ 100% | ✅ | [04-05-runtime-config](../System%20Flows/04-05-runtime-config-flow-server-frontend.md) | 🔴 Kritisch |
| **MQTT Routing** | ✅ 100% | ✅ | [06-mqtt-message-routing](../System%20Flows/06-mqtt-message-routing-flow-server-frontend.md) | 🔴 Kritisch |
| **Error Recovery** | ✅ 80% | ✅ | [07-error-recovery](../System%20Flows/07-error-recovery-flow-server-frontend.md) | 🔴 Kritisch |
| **Zone Assignment** | ✅ 100% | ✅ | [08-zone-assignment](../System%20Flows/08-zone-assignment-flow-server-frontend.md) | 🟡 Wichtig |
| **Sensor Libraries** | ✅ 80% | ✅ | [09-sensor-library](../System%20Flows/09-sensor-library-flow-server-frontend.md) | 🟡 Wichtig |
| **Subzone & Safe-Mode** | ✅ 100% | ✅ | [10-subzone-safemode](../System%20Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md) | 🟡 Wichtig |
| **Authentication** | ✅ 100% | ✅ | [11-authentication](../System%20Flows/11-authentication-authorization-flow-server-frontend.md) | 🔴 Kritisch |
| **User Management** | ✅ 100% | ✅ | [12-user-management](../System%20Flows/12-user-management-flow-server-frontend.md) | 🟡 Wichtig |
| **Logic Engine** | 🔄 70% (nur Backend) | ✅ | [13-logic-engine](../System%20Flows/13-logic-engine-flow-server-frontend.md) | 🟡 Wichtig |
| **Satellite Cards** | 🔄 50% (Komp.✅ Layout❌) | ✅ | [14-satellite-cards](../System%20Flows/14-satellite-cards-flow-server-frontend.md) | 🟡 Wichtig |

### Frontend UI-Features

> ⚠️ **Code-Verifiziert am 20.12.2025** - Jeder Status wurde gegen den tatsächlichen Code geprüft.

| Feature | IST-Zustand | SOLL-Zustand | Gap | Aufwand | Code-Quelle |
|---------|-------------|--------------|-----|---------|-------------|
| **Unified Device View** | ✅ Mock+Real kombiniert | ✅ | - | - | `DevicesView.vue` |
| **ESP Card Design** | ✅ Basis-Cards (ohne Satelliten) | ✅ Mit Satelliten-Layout | ⚠️ **Layout fehlt** | 3d | `ESPCard.vue` |
| **Sensor Satellite** | ✅ Komponente fertig | ✅ | - | - | `SensorSatellite.vue` |
| **Actuator Satellite** | ✅ Komponente fertig | ✅ | - | - | `ActuatorSatellite.vue` |
| **Satelliten-Integration** | ❌ **0% - Nicht integriert** | ✅ In ESPCard | ⚠️ **Komplett** | 2d | fehlt in `ESPCard.vue` |
| **Connection Lines** | 🔄 SVG-Basis fertig | ✅ + Logic-Parsing | ⚠️ Logic fehlt | 2d | `ConnectionLines.vue` |
| **WebSocket Sensor-Live** | ❌ Nur esp_health/status | ✅ + sensor_data | ⚠️ **Fehlt** | 1d | `esp.ts` Store |
| **Zone Drag & Drop** | 📋 Nicht implementiert | ✅ | ❌ Komplett | 5d | - |
| **Mock→ESP Transfer** | 📋 Nicht implementiert | ✅ | ❌ Komplett | 3d | - |
| **Sanfte Übergänge** | 📋 Nicht implementiert | ✅ | ❌ Komplett | 2d | - |
| **Logic Builder UI** | ⚠️ **Nur Placeholder** | ✅ Visueller Builder | ❌ **Komplett** | 8d | `LogicView.vue` |
| **Custom Sensor Libraries** | 📋 Nicht implementiert | ✅ Phase 7 | ❌ | 5d | - |

---

## Sidebar-Navigation

> **Status:** ✅ Implementiert | **System Flow:** [11-authentication](../System%20Flows/11-authentication-authorization-flow-server-frontend.md) (RBAC)

Die Seitenleiste (`AppSidebar.vue`) ist in kollabierbare Gruppen organisiert.

### IST-Zustand vs. SOLL-Zustand

| Gruppe | Tabs | IST | SOLL | Sichtbarkeit |
|--------|------|-----|------|--------------|
| Dashboard | Dashboard | ✅ | ✅ | Alle |
| Geräte | Alle ESPs | ✅ Unified View | ✅ | Alle |
| Geräte | Sensoren | ✅ Liste | ✅ + Mini-Charts | Alle |
| Geräte | Aktoren | ✅ Liste | ✅ + Quick-Control | Alle |
| Automation | Regeln | 🔄 Basis-Liste | ✅ + Builder | Alle |
| Monitoring | MQTT Live | ✅ | ✅ | Alle |
| Monitoring | Server Logs | ✅ | ✅ | Alle |
| Administration | Benutzer | ✅ | ✅ | Nur Admins |
| Administration | System | ✅ | ✅ | Nur Admins |

**Quelle:** `El Frontend/src/components/layout/AppSidebar.vue`

### User Experience

| User-Rolle | Sieht | Kann |
|------------|-------|------|
| **Admin** | Alle Tabs | Alles konfigurieren, User verwalten |
| **Operator** | Geräte, Automation, Monitoring | ESPs steuern, Regeln erstellen |
| **Viewer** | Dashboard, Geräte (readonly) | Nur ansehen |

---

## Dashboard - Zielzustand

> **Status:** 🔄 70% Implementiert | **Quell-Dateien:** `src/views/DashboardView.vue`, `src/views/DevicesView.vue`

### Grundprinzipien

| Prinzip | Beschreibung | IST | SOLL |
|---------|--------------|-----|------|
| **User-friendly** | Alle Informationen auf einen Blick | ✅ | ✅ |
| **Zielgerichtet** | Klare Handlungsoptionen für den User | 🔄 | ✅ Quick-Actions |
| **Konsistent** | Einheitliche Design-Patterns (Iridescent Theme) | ✅ | ✅ |
| **Responsiv** | Mobile-first, funktioniert auf allen Bildschirmgrößen | ✅ | ✅ |
| **Real-time** | Live-Updates ohne Reload | ✅ WebSocket | ✅ |

### Was der User heute sieht vs. Vision

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ IST-ZUSTAND (Heute)                    │ SOLL-ZUSTAND (Vision)              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                        │                                     │
│  ┌──────────┐ ┌──────────┐             │  ┌──────────────────────────────┐  │
│  │ESP_12AB  │ │ESP_34CD  │             │  │      ZONEN-ÜBERSICHT         │  │
│  │─────────│ │─────────│             │  │  ┌─────────┐  ┌─────────┐    │  │
│  │ Status  │ │ Status  │             │  │  │Gewächs- │  │Anzucht- │    │  │
│  │ Zone    │ │ Zone    │             │  │  │  haus   │  │ bereich │    │  │
│  │ S:3 A:2 │ │ S:2 A:1 │             │  │  │[ESP][ESP]│  │ [ESP]   │    │  │
│  └──────────┘ └──────────┘             │  │  └─────────┘  └─────────┘    │  │
│                                        │  └──────────────────────────────┘  │
│  → Karten nebeneinander               │                                     │
│  → Keine Satelliten                    │  → Drag & Drop Zonen               │
│  → Keine Connection Lines              │  → Satelliten um ESPs               │
│                                        │  → Connection Lines aktiv           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 1. Geräte-Übersicht (ESP Cards)

> **System Flow:** [14-satellite-cards](../System%20Flows/14-satellite-cards-flow-server-frontend.md)

#### Zwei Card-Typen

> **Status:** ✅ Implementiert | **Code:** `src/components/esp/ESPCard.vue`

| Aspekt | Mock-ESP Card | ESP Card (Echte Hardware) | IST |
|--------|---------------|---------------------------|-----|
| **Badge** | `MOCK` (lila) | `REAL` (cyan) | ✅ |
| **Herkunft** | Manuell erstellt über UI | Auto-Discovery via MQTT Heartbeat | ✅ |
| **Zweck** | Entwicklung, Tests, Simulation | Produktivbetrieb | ✅ |
| **Status-Bar** | Lila linker Rand | Cyan linker Rand | ✅ |
| **Mock→Real Transfer** | — | Kann Mock-Voreinstellungen übernehmen | 📋 |

#### Card-Struktur (Schwebende Satelliten-Cards)

> **Status:** ✅ Komponenten fertig, 🔄 Layout-Integration ausstehend  
> **System Flow:** [14-satellite-cards](../System%20Flows/14-satellite-cards-flow-server-frontend.md)  
> **Komponenten:** `SensorSatellite.vue`, `ActuatorSatellite.vue`, `ConnectionLines.vue`

```
                    ┌─────────────┐
                    │  🌡️ Temp    │ ← SensorSatellite.vue ✅
                    │    23.4°C   │
                    └──────┬──────┘
                           │
    ┌─────────────┐   ┌────┴────────────────┐   ┌─────────────┐
    │  💧 Moisture│───│                     │───│  💡 Licht   │
    │     67%     │   │   ESP_AB12CD34      │   │    420 lux  │
    └─────────────┘   │   ───────────────   │   └─────────────┘
                      │   Zone: Gewächshaus │     ESPCard.vue ✅
         ┌───────────│   Status: ● Online  │───────────┐
         │            │   Sensoren: 4       │           │
         │            │   Aktoren: 2        │           │
         │            └────────────────────┘           │
         │                     │                        │
    ┌────┴────────┐      ┌─────┴─────┐           ┌─────┴─────┐
    │  🔴 Pumpe   │      │  🟢 Ventil│           │  ⚡ Relais │
    │   [AN]      │      │   [AUS]   │           │   [AUS]    │
    └─────────────┘      └───────────┘           └────────────┘
          ↑                   ↑                        ↑
     ActuatorSatellite.vue ✅ ─────── ConnectionLines.vue 🔄
```

### Implementierungsstand Satelliten-System

> ⚠️ **Code-Verifiziert am 20.12.2025**

| Komponente | Status | Code-Location | LOC | Features |
|------------|--------|---------------|-----|----------|
| **SensorSatellite** | ✅ 100% | `src/components/esp/SensorSatellite.vue` | 271 | Live-Werte, Quality-Badge, Icons |
| **ActuatorSatellite** | ✅ 100% | `src/components/esp/ActuatorSatellite.vue` | 289 | AN/AUS, PWM%, E-STOP |
| **ConnectionLines** | 🔄 50% | `src/components/esp/ConnectionLines.vue` | 268 | SVG-Linien, Hover, **Logic-Parsing fehlt** |
| **ESPCard Integration** | ❌ **0%** | `src/components/esp/ESPCard.vue` | 413 | **Keine Satelliten-Imports!** |
| **Position Tracking** | 📋 0% | — | - | Dynamische Positionierung |
| **WebSocket sensor_data** | ❌ **0%** | `src/stores/esp.ts` | - | **Nicht subscribed!** |

### Verhalten (Vision vs. Code-Realität)

| Aktion | IST (Code-verifiziert) | SOLL | Gap |
|--------|------------------------|------|-----|
| Satelliten-Cards schweben um ESP-Card | ❌ **Nicht implementiert** | ✅ Orbital-Layout | ❌ **Komplett** |
| Live-Werte der Sensoren | ❌ **Nur via API-Refresh** | ✅ WebSocket sensor_data | ⚠️ WebSocket fehlt |
| ESP Health/Status | ✅ WebSocket esp_health | ✅ | - |
| Aktor-Status Live | ❌ **Nicht subscribed** | ✅ WebSocket actuator_status | ⚠️ Subscription fehlt |
| **Klick auf Satellit** | ❌ Nicht möglich (keine Satellites) | ✅ Connection Lines | ❌ |
| Grüne Linien = Logic-Verbindung | ❌ | ✅ | 🔄 Logic-Parsing |
| Gestrichelte Linien = Intern | ❌ | ✅ | 🔄 |
| Cross-ESP Linien | ❌ | ✅ | 🔄 |

---

### 2. Zonen-Management (Drag & Drop)

> **Status:** 📋 Geplant (0%) | **System Flow:** [08-zone-assignment](../System%20Flows/08-zone-assignment-flow-server-frontend.md)  
> **Backend:** ✅ Zone-Assignment API vollständig implementiert

#### IST vs. SOLL Vergleich

| Feature | IST | SOLL | Aufwand |
|---------|-----|------|---------|
| Zone-Zuweisung | ✅ Via Panel | ✅ | - |
| Zone-Übersicht | 🔄 Liste | ✅ Visuell gruppiert | 2d |
| Drag & Drop | ❌ | ✅ | 3d |
| "Ohne Zone" Bereich | ❌ | ✅ Pulsierend | 1d |
| Mock→ESP Transfer | ❌ | ✅ | 3d |

#### Zone-Layout (Vision)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ZONEN-ÜBERSICHT                                    📋 GEPLANT      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────┐│
│  │ 🏠 Gewächshaus      │  │ 🌱 Anzuchtbereich   │  │ ❓ Ohne Zone ││
│  │ ─────────────────── │  │ ─────────────────── │  │ ──────────── ││
│  │                     │  │                     │  │              ││
│  │  [ESP_A1]  [ESP_A2] │  │  [ESP_B1]          │  │  [ESP_NEW]   ││
│  │                     │  │                     │  │    ↑         ││
│  │  [MOCK_01]          │  │  [MOCK_02]          │  │  Neu!        ││
│  │                     │  │                     │  │  Einrichten→ ││
│  └─────────────────────┘  └─────────────────────┘  └──────────────┘│
│                                                                     │
│  [────────────────── DRAG & DROP ZONE ──────────────────]          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Funktionen (Vision)

| Funktion | Status | Beschreibung |
|----------|--------|--------------|
| **Drag & Drop** | 📋 | ESPs zwischen Zonen verschieben |
| **Neue ESPs ohne Zone** | 📋 | Pulsierender Rand, Quick-Setup Button |
| **Mock → ESP Transfer** | 📋 | Config übernehmen beim Einrichten |

**Mock → ESP Transfer Details (Geplant):**
- [ ] Sensor-Konfigurationen übertragen
- [ ] Aktor-Konfigurationen übertragen
- [ ] Zone-Zuweisungen kopieren
- [ ] Logik-Regeln übernehmen (nach Funktionstest)

> **Technische Basis vorhanden:** Die Zone-Assignment API (`POST /v1/esp/devices/{id}/zone`) ist vollständig implementiert. Nur das Drag & Drop Frontend fehlt.

---

### 3. Verlinkungen (Sanfte Übergänge)

**Problem (Aktuell):** Klick auf ESP → Direkter Sprung zur Detailseite wirkt abrupt.

**Lösung:**
1. **Hover-Preview:** Bei Hover auf ESP-Card erscheint kleines Popup mit Kurzinfo
2. **Expand-Animation:** Card expandiert sanft zur Vollansicht (innerhalb Dashboard)
3. **Breadcrumb:** Klarer Pfad zurück: `Dashboard > ESP_AB12CD34`
4. **Slide-Transition:** Seiten-Übergang mit horizontaler Slide-Animation

---

### 4. Statistik-Karten (Bestehend, erweitert)

| Karte | Wert | Subtitle |
|-------|------|----------|
| ESP-Geräte | Gesamt (Mock + Real) | X online |
| Sensoren | Anzahl aktiver Sensoren | "Aktive Messungen" |
| Aktoren | Anzahl Aktoren | X eingeschaltet |
| Automation | Anzahl aktiver Regeln | "Aktive Regeln" |
| Zonen | Anzahl Zonen | X ESPs zugewiesen |

---

## Geräte-Ansicht - Alle ESPs

> **Status:** ✅ Implementiert | **Route:** `/devices`  
> **Code:** `src/views/DevicesView.vue`, `src/views/DeviceDetailView.vue`

### Ziel: Unified Device View ✅ ERREICHT

Mock-ESPs und echte ESPs werden in **einer** Ansicht kombiniert angezeigt.

### IST vs. SOLL Vergleich

| Feature | IST | SOLL | Status |
|---------|-----|------|--------|
| Mock + Real kombiniert | ✅ | ✅ | ✅ |
| Filter nach Typ | ✅ | ✅ | ✅ |
| Filter nach Status | ✅ | ✅ | ✅ |
| Filter nach Zone | 🔄 | ✅ | 🔄 |
| Sortierung | ✅ | ✅ | ✅ |
| Suchfunktion | ✅ | ✅ | ✅ |

### Filter-Optionen

| Filter | Optionen | IST |
|--------|----------|-----|
| Typ | Alle, Mock, Real | ✅ |
| Status | Online, Offline, Error, Safe-Mode | ✅ |
| Zone | Alle Zonen, Ohne Zone | 🔄 |
| Hardware | ESP32_WROOM, XIAO_ESP32_C3, MOCK_* | ✅ |

### Detailansicht (ESP-Detail)

> **Status:** ✅ Implementiert | **Route:** `/devices/{esp_id}`  
> **Code:** `src/views/DeviceDetailView.vue` (864 Zeilen)

#### Verfügbare Aktionen

| Aktion | Beschreibung | API | IST |
|--------|--------------|-----|-----|
| **Löschen** | ESP aus System entfernen | `DELETE /debug/mock-esp/{id}` (Mock) | ✅ |
| **Config ändern** | Hardware-Einstellungen | `POST /v1/esp/devices/{id}/config` | ✅ |
| **Heartbeat triggern** | Manueller Heartbeat (Mock) | `POST /debug/mock-esp/{id}/heartbeat` | ✅ |
| **Safe-Mode Toggle** | Sicherheitsmodus (Mock) | `POST /debug/mock-esp/{id}/state` | ✅ |
| **Emergency Stop** | Notfall-Stopp (Mock) | `POST /debug/mock-esp/emergency-stop` | ✅ |
| **Zone ändern** | Zone zuweisen/entfernen | via `ZoneAssignmentPanel` | ✅ |
| **Restart** | ESP neustarten | `POST /v1/esp/devices/{id}/restart` | 📋 |
| **Factory Reset** | Auf Werkseinstellungen | `POST /v1/esp/devices/{id}/reset` | 📋 |

#### Sensor-Management

> **System Flow:** [02-sensor-reading](../System%20Flows/02-sensor-reading-flow-server-frontend.md), [04-05-runtime-config](../System%20Flows/04-05-runtime-config-flow-server-frontend.md)

| Aktion | Beschreibung | IST | SOLL |
|--------|--------------|-----|------|
| **Sensor hinzufügen** | GPIO-Pin + Sensor-Typ auswählen | ✅ Mock | ✅ |
| **Sensor konfigurieren** | Kalibrierung, Intervalle, Thresholds | 🔄 | ✅ |
| **Sensor entfernen** | Sensor von ESP entfernen | ✅ Mock | ✅ |
| **Live-Werte** | Echtzeit-Anzeige der Messwerte | ✅ WebSocket | ✅ |
| **Quality Badge** | Datenqualität anzeigen | ✅ | ✅ |
| **Batch Update** | Mehrere Werte gleichzeitig (Mock) | ✅ | ✅ |

#### Aktor-Management

> **System Flow:** [03-actuator-command](../System%20Flows/03-actuator-command-flow-server-frontend.md)

| Aktion | Beschreibung | IST | SOLL |
|--------|--------------|-----|------|
| **Aktor hinzufügen** | GPIO-Pin + Aktor-Typ auswählen | ✅ Mock | ✅ |
| **Aktor konfigurieren** | Min/Max-Werte, Timeout, Safety | 🔄 | ✅ |
| **Aktor steuern** | AN/AUS Toggle | ✅ | ✅ |
| **PWM-Wert setzen** | 0-255 Wert | ✅ Mock | ✅ |
| **Emergency Stop** | Notfall-Stopp (einzeln oder alle) | ✅ | ✅ |

#### Subzone-Management

> **System Flow:** [10-subzone-safemode](../System%20Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md)

| Aktion | Beschreibung | IST | SOLL |
|--------|--------------|-----|------|
| **Subzone erstellen** | Logische Untergruppe innerhalb ESP | ✅ API | ✅ |
| **GPIOs zuweisen** | Sensoren/Aktoren zu Subzone | ✅ API | ✅ |
| **Safe-Mode** | Subzone in sicheren Zustand versetzen | ✅ API | ✅ |
| **Subzone UI** | Grafische Verwaltung | 🔄 | ✅ |

---

## Sensoren-Ansicht

> **Status:** ✅ Basis implementiert | **Route:** `/sensors`  
> **System Flow:** [02-sensor-reading](../System%20Flows/02-sensor-reading-flow-server-frontend.md), [09-sensor-library](../System%20Flows/09-sensor-library-flow-server-frontend.md)

### IST vs. SOLL Vergleich

| Feature | IST | SOLL | Status |
|---------|-----|------|--------|
| Sensor-Liste | ✅ | ✅ | ✅ |
| Live-Werte | ✅ WebSocket | ✅ | ✅ |
| Quality-Anzeige | ✅ | ✅ | ✅ |
| Mini-Charts | ❌ | ✅ Trend-Anzeige | 📋 |
| Kalibrierung UI | 🔄 | ✅ | 🔄 |
| Custom Libraries | ❌ | ✅ Phase 7 | 📋 |

### Sensor-Libraries (Server-Side Processing)

AutomationOne verwendet **Pi-Enhanced Mode**: ESPs senden Rohdaten, der Server verarbeitet sie mit Sensor-Libraries.

> **Code-Location:** `El Servador/god_kaiser_server/src/sensors/sensor_libraries/active/`

#### Verfügbare Libraries

| Library | Datei | Beschreibung |
|---------|-------|--------------|
| **Temperature** | `temperature.py` | Temperatur-Sensoren (DS18B20, DHT22, etc.) |
| **Humidity** | `humidity.py` | Luftfeuchtigkeit |
| **pH** | `ph_sensor.py` | pH-Wert-Messung mit Kalibrierung |
| **EC** | `ec_sensor.py` | Elektrische Leitfähigkeit |
| **Moisture** | `moisture.py` | Bodenfeuchtigkeit |
| **Light** | `light.py` | Lichtstärke (Lux) |
| **Pressure** | `pressure.py` | Druck-Sensoren |
| **Flow** | `flow.py` | Durchfluss-Sensoren |
| **CO2** | `co2.py` | CO2-Konzentration |

**Speicherort:** `El Servador/god_kaiser_server/src/sensors/sensor_libraries/active/`

#### Custom Libraries (Geplant)

```
┌─────────────────────────────────────────────────────────────┐
│  🧪 CUSTOM SENSOR LIBRARY                          [Beta]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Name:        [__________________________]                  │
│                                                             │
│  Basis:       [Rohwert → Verarbeitung → Kalibrierter Wert] │
│                                                             │
│  Formel:      [calibrated = raw * factor + offset]         │
│                                                             │
│  Einheit:     [__________]   Dezimalstellen: [2]           │
│                                                             │
│  Min/Max:     [0.0] - [100.0]                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  def process(raw_value, calibration):               │   │
│  │      factor = calibration.get('factor', 1.0)        │   │
│  │      offset = calibration.get('offset', 0.0)        │   │
│  │      return raw_value * factor + offset             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [Testen]  [Speichern]  [Abbrechen]                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Status:** 🔴 Noch nicht implementiert - Geplant für Phase 7

### Sensor-Übersicht

| Spalte | Beschreibung |
|--------|--------------|
| ESP | Zugehöriger ESP (mit Link) |
| GPIO | Pin-Nummer |
| Typ | Sensor-Typ (temperature, ph, etc.) |
| Aktueller Wert | Live-Wert mit Einheit |
| Qualität | Signal-Qualität (good, degraded, poor) |
| Letztes Update | Zeitstempel |
| Aktionen | Details, Kalibrieren, Entfernen |

---

## Aktoren-Ansicht

> **Status:** ✅ Basis implementiert | **Route:** `/actuators`  
> **System Flow:** [03-actuator-command](../System%20Flows/03-actuator-command-flow-server-frontend.md)

### IST vs. SOLL Vergleich

| Feature | IST | SOLL | Status |
|---------|-----|------|--------|
| Aktor-Liste | ✅ | ✅ | ✅ |
| Status-Anzeige | ✅ | ✅ | ✅ |
| Quick-Toggle | 🔄 | ✅ | 🔄 |
| PWM-Slider | ❌ | ✅ | 📋 |
| Laufzeit-Anzeige | 🔄 | ✅ | 🔄 |
| Custom Libraries | ❌ | ✅ Phase 7 | 📋 |

### Aktor-Typen

| Typ | Server-Typ | Beschreibung | Wertbereich |
|-----|------------|--------------|-------------|
| **Pumpe** | `digital` | Ein/Aus-Steuerung | 0.0 / 1.0 |
| **Ventil** | `digital` | Ein/Aus-Steuerung | 0.0 / 1.0 |
| **Relais** | `digital` | Ein/Aus-Steuerung | 0.0 / 1.0 |
| **PWM** | `pwm` | Stufenlose Regelung | 0.0 - 1.0 |
| **Servo** | `servo` | Positionssteuerung | 0.0 - 1.0 |

**Mapping ESP32 → Server:**
- `pump` → `digital`
- `valve` → `digital`
- `relay` → `digital`
- `pwm` → `pwm`
- `servo` → `servo`

### Aktor-Libraries (Geplant)

Analog zu Sensor-Libraries: Custom Aktor-Verhalten definieren.

**Status:** 🔴 Noch nicht implementiert - Geplant für Phase 7

### Aktor-Übersicht

| Spalte | Beschreibung |
|--------|--------------|
| ESP | Zugehöriger ESP (mit Link) |
| GPIO | Pin-Nummer |
| Typ | Aktor-Typ |
| Status | AN/AUS/PWM-Wert |
| Zustand | idle, active, error, emergency_stop |
| Laufzeit | Aktuelle Laufzeit |
| Aktionen | Steuern, Details, Emergency Stop |

### Sicherheits-Features

| Feature | Beschreibung |
|---------|--------------|
| **Timeout** | Auto-Abschaltung nach X Sekunden |
| **Min/Max-Werte** | Begrenzte Wertbereiche |
| **Cooldown** | Pause zwischen Aktivierungen |
| **Emergency Stop** | Sofortige Abschaltung aller Aktoren |

---

## Relevante Code-Dateien

### Frontend - Views

| Datei | Beschreibung | Status | Zeilen |
|-------|--------------|--------|--------|
| `src/views/DashboardView.vue` | Dashboard-Hauptansicht | ✅ | ~300 |
| `src/views/DevicesView.vue` | **Unified ESP-Liste** | ✅ | 590 |
| `src/views/DeviceDetailView.vue` | **Unified ESP-Detail** | ✅ | 864 |
| `src/views/SensorsView.vue` | Sensoren-Übersicht | ✅ | ~400 |
| `src/views/ActuatorsView.vue` | Aktoren-Übersicht | ✅ | ~350 |

### Frontend - Komponenten (Satelliten-System)

| Datei | Beschreibung | Status | System Flow |
|-------|--------------|--------|-------------|
| `src/components/esp/ESPCard.vue` | ESP-Hauptkarte | ✅ | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| `src/components/esp/SensorSatellite.vue` | Sensor-Satellit | ✅ | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| `src/components/esp/ActuatorSatellite.vue` | Aktor-Satellit | ✅ | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| `src/components/esp/ConnectionLines.vue` | SVG-Verbindungen | 🔄 | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| `src/components/esp/SensorValueCard.vue` | Sensor-Detail | ✅ | [Flow 02](../System%20Flows/02-sensor-reading-flow-server-frontend.md) |

### Frontend - Infrastruktur

| Datei | Beschreibung | Status |
|-------|--------------|--------|
| `src/components/layout/AppSidebar.vue` | Sidebar-Navigation | ✅ |
| `src/components/common/Badge.vue` | Status-Badges | ✅ |
| `src/components/zones/ZoneAssignmentPanel.vue` | Zonen-Zuweisung | ✅ |
| `src/stores/esp.ts` | **Unified ESP Store** | ✅ |
| `src/api/esp.ts` | **Unified ESP API** | ✅ |
| `src/composables/useRealTimeData.ts` | WebSocket Real-time | ✅ |
| `src/router/index.ts` | Router-Konfiguration | ✅ |

### Frontend - Utilities (Verifiziert)

| Datei | Beschreibung | Referenz |
|-------|--------------|----------|
| `src/utils/sensorDefaults.ts` | Sensor-Typ Konfigurationen | [Flow 14 §7.2](../System%20Flows/14-satellite-cards-flow-server-frontend.md#72-utility-functions) |
| `src/utils/labels.ts` | Labels (German) | [Flow 14 §7.2](../System%20Flows/14-satellite-cards-flow-server-frontend.md#72-utility-functions) |
| `src/utils/formatters.ts` | Formatierung | [Flow 14 §7.2](../System%20Flows/14-satellite-cards-flow-server-frontend.md#72-utility-functions) |
| `src/types/index.ts` | TypeScript Types | [Flow 14 §7.3](../System%20Flows/14-satellite-cards-flow-server-frontend.md#73-types) |

### Backend - ESP Management

| Datei | Beschreibung |
|-------|--------------|
| `src/api/v1/esp.py` | ESP Device API Endpoints |
| `src/api/v1/debug.py` | Mock-ESP Debug Endpoints |
| `src/services/esp_service.py` | ESP Business Logic |
| `src/db/models/esp.py` | ESPDevice Model |
| `src/db/repositories/esp_repo.py` | ESP Repository |
| `src/mqtt/handlers/heartbeat_handler.py` | Auto-Discovery via Heartbeat |
| `src/mqtt/handlers/discovery_handler.py` | Legacy Discovery (deprecated) |

### Backend - Sensoren

| Datei | Beschreibung |
|-------|--------------|
| `src/api/v1/sensors.py` | Sensor API Endpoints |
| `src/db/models/sensor.py` | SensorConfig, SensorData Models |
| `src/db/repositories/sensor_repo.py` | Sensor Repository |
| `src/sensors/library_loader.py` | Dynamischer Library Loader |
| `src/sensors/base_processor.py` | Basis-Klasse für Sensor-Prozessoren |
| `src/sensors/sensor_libraries/active/*.py` | Sensor-Libraries |

### Backend - Aktoren

| Datei | Beschreibung |
|-------|--------------|
| `src/api/v1/actuators.py` | Actuator API Endpoints |
| `src/db/models/actuator.py` | ActuatorConfig, ActuatorState, ActuatorHistory |
| `src/db/repositories/actuator_repo.py` | Actuator Repository |
| `src/services/actuator_service.py` | Actuator Business Logic |
| `src/mqtt/handlers/actuator_handler.py` | MQTT Actuator Handler |
| `src/schemas/actuator.py` | Actuator Pydantic Schemas |

### Backend - Zonen & Subzones

| Datei | Beschreibung |
|-------|--------------|
| `src/api/v1/subzone.py` | Subzone API Endpoints |
| `src/db/models/subzone.py` | SubzoneConfig Model |
| `src/db/repositories/subzone_repo.py` | Subzone Repository |
| `src/services/subzone_service.py` | Subzone Business Logic |

---

## API-Übersicht

### Mock-ESP APIs (Debug)

| Methode | Endpoint | Beschreibung |
|---------|----------|--------------|
| GET | `/debug/mock-esp` | Liste aller Mock-ESPs |
| POST | `/debug/mock-esp` | Mock-ESP erstellen |
| GET | `/debug/mock-esp/{id}` | Mock-ESP Details |
| DELETE | `/debug/mock-esp/{id}` | Mock-ESP löschen |
| POST | `/debug/mock-esp/{id}/heartbeat` | Heartbeat triggern |
| POST | `/debug/mock-esp/{id}/state` | System-State setzen |
| POST | `/debug/mock-esp/{id}/sensors` | Sensor hinzufügen |
| POST | `/debug/mock-esp/{id}/actuators` | Aktor hinzufügen |
| POST | `/debug/mock-esp/emergency-stop` | Globaler Emergency Stop |

### Echte ESP APIs

| Methode | Endpoint | Beschreibung |
|---------|----------|--------------|
| GET | `/v1/esp/devices` | Liste aller ESPs |
| POST | `/v1/esp/devices` | ESP manuell registrieren |
| GET | `/v1/esp/devices/{id}` | ESP Details |
| PATCH | `/v1/esp/devices/{id}` | ESP aktualisieren |
| POST | `/v1/esp/devices/{id}/config` | Config via MQTT senden |
| POST | `/v1/esp/devices/{id}/restart` | Restart-Befehl |
| POST | `/v1/esp/devices/{id}/reset` | Factory Reset |
| GET | `/v1/esp/devices/{id}/health` | Health Metrics |
| GET | `/v1/esp/discovery` | Network Discovery |

---

## Implementierungs-Priorität

### Übersicht nach Priorität

| Priorität | Feature | Status | System Flow | ETA |
|-----------|---------|--------|-------------|-----|
| 🔴 **KRITISCH** | Authentication & Authorization | ✅ **FERTIG** | [Flow 11](../System%20Flows/11-authentication-authorization-flow-server-frontend.md) | - |
| 🔴 **KRITISCH** | User Management | ✅ **FERTIG** | [Flow 12](../System%20Flows/12-user-management-flow-server-frontend.md) | - |
| 🔴 **KRITISCH** | Unified Device View (Mock + Real) | ✅ **FERTIG** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) | - |
| 🔴 **KRITISCH** | Satelliten-Cards Komponenten | ✅ **FERTIG** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) | - |
| 🟡 **WICHTIG** | ESPCard Satelliten-Layout | 🔄 **IN ARBEIT** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) | 2d |
| 🟡 **WICHTIG** | Logik-Verbindungslinien | 🔄 **IN ARBEIT** | [Flow 13](../System%20Flows/13-logic-engine-flow-server-frontend.md) | 2d |
| 🟡 **WICHTIG** | Logic Engine Backend | 🔄 **70%** | [Flow 13](../System%20Flows/13-logic-engine-flow-server-frontend.md) | 3d |
| 🟢 **NORMAL** | Zonen-Drag & Drop | 📋 **Geplant** | [Flow 08](../System%20Flows/08-zone-assignment-flow-server-frontend.md) | 5d |
| 🟢 **NORMAL** | Mock → ESP Config-Transfer | 📋 **Geplant** | - | 3d |
| 🟢 **NORMAL** | Sanfte Seiten-Übergänge | 📋 **Geplant** | - | 2d |
| ⚪ **BACKLOG** | Custom Sensor Libraries UI | 📋 **Phase 7** | [Flow 09](../System%20Flows/09-sensor-library-flow-server-frontend.md) | 5d |
| ⚪ **BACKLOG** | Custom Actuator Libraries | 📋 **Phase 7** | - | 5d |

### Fortschritts-Übersicht

```
FERTIG (✅)           ████████████████████████████████░░░░░░░░  65%
IN ARBEIT (🔄)        ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  20%
GEPLANT (📋)          ░░░░░░░░░░░░░░░░░░░░░░░░████████░░░░░░░░  15%
```

---

## 📋 Detaillierter Umsetzungsplan: Satelliten-Cards System

### Architektur-Übersicht

Das Satelliten-Cards System besteht aus mehreren Komponenten, die zusammenarbeiten, um Live-Sensor- und Aktor-Daten visuell um ESP-Cards anzuzeigen:

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │  ESPCard     │      │  ESPCard     │                    │
│  │  (Hauptcard) │      │  (Hauptcard) │                    │
│  └──────┬───────┘      └──────┬───────┘                    │
│         │                     │                             │
│    ┌────┴─────┐         ┌────┴─────┐                      │
│    │ Sensor    │         │ Sensor    │                      │
│    │ Satellite │         │ Satellite │                      │
│    └───────────┘         └───────────┘                      │
│         │                     │                             │
│    ┌────┴─────┐         ┌────┴─────┐                      │
│    │ Actuator │         │ Actuator  │                      │
│    │ Satellite│         │ Satellite │                       │
│    └──────────┘         └───────────┘                      │
│         │                     │                             │
│    ┌────┴─────────────────────┴─────┐                    │
│    │   ConnectionLines (SVG)          │                    │
│    │   (Verbindungslinien)            │                    │
│    └──────────────────────────────────┘                    │
│                                                             │
│  ┌──────────────────────────────────────┐                 │
│  │  useWebSocket Composable              │                 │
│  │  (WebSocket Subscription)             │                 │
│  └──────────────┬───────────────────────┘                 │
│                 │                                           │
│  ┌──────────────┴───────────────────────┐                 │
│  │  websocketService (Singleton)        │                 │
│  │  - Auto-Reconnect                    │                 │
│  │  - Rate Limiting                     │                 │
│  └──────────────┬───────────────────────┘                 │
└─────────────────┼─────────────────────────────────────────┘
                  │
                  │ WebSocket (ws://host/ws/realtime/{client_id})
                  │
┌─────────────────┼─────────────────────────────────────────┐
│                 │                                           │
│  ┌──────────────┴───────────────────────┐                 │
│  │  Backend (FastAPI)                    │                 │
│  │  WebSocketManager (Singleton)         │                 │
│  │  - Connection Management              │                 │
│  │  - Subscription Filtering             │                 │
│  │  - Rate Limiting (10 msg/sec)        │                 │
│  └──────────────┬───────────────────────┘                 │
│                 │                                           │
│  ┌──────────────┴───────────────────────┐                 │
│  │  MQTT Subscriber                     │                 │
│  │  - sensor_data Events                │                 │
│  │  - actuator_status Events             │                 │
│  │  - esp_health Events                 │                 │
│  └───────────────────────────────────────┘                 │
│                                                             │
│  ┌──────────────────────────────────────┐                 │
│  │  Logic Engine                        │                 │
│  │  - Rule Evaluation                   │                 │
│  │  - logic_execution Events            │                 │
│  └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### Komponenten-Details

#### 1. SensorSatellite Komponente (`El Frontend/src/components/esp/SensorSatellite.vue`)

**Zweck:** Zeigt einen Sensor als "Satelliten"-Card um die Haupt-ESP-Card.

**Props:**
- `espId`: ESP ID, zu dem der Sensor gehört
- `gpio`: GPIO-Pin-Nummer
- `sensorType`: Sensor-Typ (z.B. 'DS18B20', 'pH', 'EC')
- `name`: Optionaler Sensor-Name
- `value`: Aktueller Sensor-Wert
- `quality`: Quality-Level ('excellent', 'good', 'fair', 'poor', 'bad', 'stale')
- `unit`: Einheit (optional, wird aus Sensor-Typ abgeleitet)
- `selected`: Ob der Sensor ausgewählt/highlighted ist
- `showConnections`: Ob Verbindungslinien angezeigt werden sollen

**Features:**
- Live-Wert-Anzeige mit Einheit
- Quality-Indikator (Badge mit Farbe: grün=gut, gelb=akzeptabel, rot=schlecht)
- Icon basierend auf Sensor-Typ (Thermometer, Droplet, Zap, etc.)
- Klick-Handler für Verbindungslinien-Anzeige

**Datenquelle:**
- WebSocket Event: `sensor_data`
- Format: `{ type: 'sensor_data', timestamp: number, data: { esp_id, gpio, value, quality, sensor_type, unit } }`

**Styling:**
- Position: Absolut positioniert um ESP-Card
- Icon-Farbe basierend auf Quality-Level
- Hover-Effekt mit Border-Highlight
- Connection-Indicator (grüner Punkt) wenn Verbindungen vorhanden

#### 2. ActuatorSatellite Komponente (`El Frontend/src/components/esp/ActuatorSatellite.vue`)

**Zweck:** Zeigt einen Aktor als "Satelliten"-Card um die Haupt-ESP-Card.

**Props:**
- `espId`: ESP ID, zu dem der Aktor gehört
- `gpio`: GPIO-Pin-Nummer
- `actuatorType`: Aktor-Typ (z.B. 'relay', 'pump', 'valve', 'fan')
- `name`: Optionaler Aktor-Name
- `state`: Aktueller Status (AN/AUS)
- `pwmValue`: PWM-Wert (0-255, optional)
- `emergencyStopped`: Ob Emergency-Stop aktiv ist
- `selected`: Ob der Aktor ausgewählt/highlighted ist
- `showConnections`: Ob Verbindungslinien angezeigt werden sollen

**Features:**
- Status-Anzeige (AN/AUS oder PWM-Prozent)
- Icon basierend auf Aktor-Typ (Power, Waves, GitBranch, Fan, etc.)
- Emergency-Stop-Indikator (roter Badge)
- Pulse-Animation wenn aktiv

**Datenquelle:**
- WebSocket Event: `actuator_status`
- Format: `{ type: 'actuator_status', timestamp: number, data: { esp_id, gpio, state, pwm_value, emergency_stopped } }`

**Styling:**
- Position: Absolut positioniert um ESP-Card
- Icon-Farbe: Grün wenn aktiv, Grau wenn inaktiv, Rot bei Emergency-Stop
- Pulse-Animation für aktive Aktoren

#### 3. ConnectionLines Komponente (`El Frontend/src/components/esp/ConnectionLines.vue`)

**Zweck:** Zeigt SVG-basierte Verbindungslinien zwischen Sensoren und Aktoren.

**Props:**
- `connections`: Array von Connection-Objekten
- `positions`: Positions-Map für Komponenten (`{ espId_gpio: { x, y } }`)
- `showTooltips`: Ob Tooltips angezeigt werden sollen
- `hoveredConnection`: Aktuell gehoverte Verbindung

**Connection-Typen:**
1. **Logic Connections** (Grüne durchgezogene Linien):
   - Kommen von Logic Rules
   - Zeigen aktive Sensor → Aktor Verbindungen
   - Können Cross-ESP sein (Sensor auf ESP1 → Aktor auf ESP2)
   - Tooltip zeigt Rule-Name und Details

2. **Internal Connections** (Gestrichelte graue Linien):
   - Sensor → Aktor auf demselben ESP
   - Zeigen interne Verknüpfungen

3. **Cross-ESP Connections** (Durchgezogene iridescent Linien):
   - Sensor auf einem ESP → Aktor auf anderem ESP
   - Zeigen Cross-ESP Verbindungen

**Datenquelle:**
- Logic Rules API: `GET /v1/logic/rules`
- Parsing von `conditions` und `actions` Arrays
- Mapping: `sensor_esp_id` + `sensor_gpio` → `actuator_esp_id` + `actuator_gpio`

**Rendering:**
- SVG-Pfade mit quadratischen Kurven für sanfte Linien
- Dynamische Positionierung basierend auf Komponenten-Positionen
- Hover-Effekt: Linie wird dicker und erhält Glow-Effekt
- Tooltip bei Hover zeigt Rule-Informationen

### Datenfluss

#### 1. Initiales Laden

```
User öffnet Dashboard
  ↓
ESP Store: fetchAll()
  ↓
API: GET /v1/esp/devices (Real ESPs)
API: GET /debug/mock-esp (Mock ESPs)
  ↓
ESP Store: devices[] wird gefüllt
  ↓
Dashboard: Rendert ESPCards
  ↓
ESPCard: Lädt Sensoren/Aktoren aus device.sensors/actuators
  ↓
ESPCard: Rendert SensorSatellite und ActuatorSatellite Komponenten
```

#### 2. WebSocket-Verbindung

```
App startet
  ↓
useWebSocket Composable: autoConnect = true
  ↓
websocketService.connect()
  ↓
WebSocket: ws://host/ws/realtime/{client_id}?token={jwt_token}
  ↓
Backend: WebSocketManager.connect()
  ↓
Backend: Token-Validierung
  ↓
Backend: Connection akzeptiert
  ↓
Frontend: websocketService.onopen
  ↓
Frontend: Resubscribe aller aktiven Subscriptions
```

#### 3. Live-Updates (Sensor-Daten)

```
ESP32/Mock-ESP: Sensor-Wert ändert sich
  ↓
MQTT: Publish sensor_data Topic
  ↓
Backend: MQTT Subscriber empfängt Message
  ↓
Backend: Sensor-Repository speichert Wert in DB
  ↓
Backend: WebSocketManager.broadcast('sensor_data', data)
  ↓
Backend: Filtert Clients basierend auf Subscriptions
  ↓
Backend: Sendet Message an abonnierte Clients
  ↓
Frontend: websocketService.onmessage
  ↓
Frontend: Route Message zu Subscriptions
  ↓
ESP Store: handleEspHealth() oder handleSensorData()
  ↓
ESP Store: Update device.sensors[gpio].value
  ↓
ESPCard: Re-rendert SensorSatellite mit neuem Wert
```

#### 4. Logic-Verbindungen

```
User klickt auf SensorSatellite
  ↓
ESPCard: setzt showConnections = true
  ↓
ESPCard: Lädt Logic Rules: GET /v1/logic/rules
  ↓
ESPCard: Parst Rules für Verbindungen:
  - Findet Rules mit condition.sensor_esp_id === espId
  - Findet Rules mit condition.sensor_gpio === gpio
  - Extrahiert action.actuator_esp_id und action.actuator_gpio
  ↓
ESPCard: Erstellt Connection-Objekte
  ↓
ESPCard: Berechnet Positionen für alle Komponenten
  ↓
ESPCard: Rendert ConnectionLines Komponente
  ↓
ConnectionLines: Zeichnet SVG-Linien zwischen Komponenten
```

### Server-Integration

#### WebSocket Endpoint

**URL:** `ws://localhost:8000/ws/realtime/{client_id}?token={jwt_token}`

**Authentifizierung:**
- JWT Token als Query-Parameter
- Backend validiert Token vor Connection-Accept
- User muss aktiv sein

**Subscription-Format:**
```json
{
  "action": "subscribe",
  "filters": {
    "types": ["sensor_data", "actuator_status", "esp_health"],
    "esp_ids": ["ESP_12AB34CD", "ESP_MOCK_123456"],
    "sensor_types": ["temperature", "humidity"]
  }
}
```

**Message-Format (vom Server):**
```json
{
  "type": "sensor_data",
  "timestamp": 1735818000,
  "data": {
    "esp_id": "ESP_12AB34CD",
    "gpio": 4,
    "value": 23.5,
    "quality": "good",
    "sensor_type": "DS18B20",
    "unit": "°C"
  }
}
```

#### Rate Limiting

**Backend:**
- Max 10 Nachrichten pro Sekunde pro Client
- Window: 1 Sekunde
- Überschreitung: Warnung im Log, keine Blockierung

**Frontend:**
- Erkennt Rate-Limit-Überschreitungen
- Zeigt Warnung in Console
- Keine Blockierung, aber Monitoring

### Dateien-Struktur

```
El Frontend/src/
├── components/
│   └── esp/
│       ├── ESPCard.vue              # Hauptcard (erweitert um Satelliten)
│       ├── SensorSatellite.vue      # Sensor-Satelliten-Komponente ✅
│       ├── ActuatorSatellite.vue    # Aktor-Satelliten-Komponente ✅
│       └── ConnectionLines.vue      # Verbindungslinien-Komponente ✅
├── composables/
│   └── useWebSocket.ts              # WebSocket Composable ✅
├── services/
│   └── websocket.ts                 # WebSocket Service (Singleton) ✅
├── stores/
│   └── esp.ts                       # ESP Store (mit WebSocket-Integration) ✅
└── api/
    └── esp.ts                       # Unified ESP API Client ✅
```

### Implementierungs-Status (Aktualisiert Dezember 2025)

| Phase | Feature | Status | System Flow |
|-------|---------|--------|-------------|
| **Phase 1** | Unified Device View | ✅ **FERTIG** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| **Phase 2** | Satelliten-Komponenten | ✅ **FERTIG** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| **Phase 2.5** | ESPCard Layout-Integration | 🔄 **IN ARBEIT** | [Flow 14](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |
| **Phase 2.5** | Logic-Verbindungs-Ermittlung | 🔄 **IN ARBEIT** | [Flow 13](../System%20Flows/13-logic-engine-flow-server-frontend.md) |
| **Phase 4** | WebSocket Integration | ✅ **FERTIG** | [Flow 14 §5.1](../System%20Flows/14-satellite-cards-flow-server-frontend.md#51-real-time-updates-flow) |
| **Phase 5** | Logic Builder UI | 📋 **Geplant** | [Flow 13](../System%20Flows/13-logic-engine-flow-server-frontend.md) |

### Nächste Schritte (Priorisiert)

#### 🔴 Priorität 1: Satelliten-Layout Fertigstellung (2-3 Tage)

| Task | Status | Dateien | Details |
|------|--------|---------|---------|
| ESPCard Satelliten-Container | 📋 | `ESPCard.vue` | Flex/Grid Layout um Haupt-Card |
| Positionierung der Satelliten | 📋 | `ESPCard.vue` | CSS Orbital-Positionierung |
| ConnectionLines Integration | 🔄 | `ConnectionLines.vue` | In ESPCard einbinden |

**Abhängigkeiten:** Keine - kann sofort beginnen

#### 🟡 Priorität 2: Logic-Verbindungen (2-3 Tage)

| Task | Status | Dateien | Details |
|------|--------|---------|---------|
| Logic Store | 📋 | `src/stores/logic.ts` | Rules API Integration |
| Connection-Parsing | 🔄 | `ConnectionLines.vue` | Aus Rules extrahieren |
| Cross-ESP Linien | 📋 | `ConnectionLines.vue` | ESP-übergreifende Verbindungen |

**Abhängigkeiten:** Logic Engine API (🔄 70% fertig)

#### 🟢 Priorität 3: Testing & Polish (1-2 Tage)

| Task | Status | Details |
|------|--------|---------|
| WebSocket-Verbindung testen | 🔄 | Reconnect, Rate-Limiting |
| Live-Updates verifizieren | 🔄 | Alle Sensor/Aktor-Typen |
| Verbindungslinien testen | 📋 | Hover, Click, Tooltip |
| Mobile Responsiveness | 📋 | Satelliten auf kleinen Screens |

---

## 📊 System Flows Konsistenz & Dokumentation

### Status der Flow-Dokumentationen (Aktualisiert Dezember 2025)

| # | Flow | Frontend Docs | Code | Status | Link |
|---|------|---------------|------|--------|------|
| 01 | Boot Sequence | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/01-boot-sequence-server-frontend.md) |
| 02 | Sensor Reading | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/02-sensor-reading-flow-server-frontend.md) |
| 03 | Actuator Command | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/03-actuator-command-flow-server-frontend.md) |
| 04-05 | Runtime Config | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/04-05-runtime-config-flow-server-frontend.md) |
| 06 | MQTT Routing | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/06-mqtt-message-routing-flow-server-frontend.md) |
| 07 | Error Recovery | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/07-error-recovery-flow-server-frontend.md) |
| 08 | Zone Assignment | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/08-zone-assignment-flow-server-frontend.md) |
| 09 | Sensor Library | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/09-sensor-library-flow-server-frontend.md) |
| 10 | Subzone & Safe-Mode | ✅ | ✅ | ✅ Vollständig | [→ Flow](../System%20Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md) |
| 11 | Authentication | ✅ | ✅ | ✅ **NEU** | [→ Flow](../System%20Flows/11-authentication-authorization-flow-server-frontend.md) |
| 12 | User Management | ✅ | ✅ | ✅ **NEU** | [→ Flow](../System%20Flows/12-user-management-flow-server-frontend.md) |
| 13 | Logic Engine | ✅ | 🔄 | ✅ **NEU** | [→ Flow](../System%20Flows/13-logic-engine-flow-server-frontend.md) |
| 14 | Satellite Cards | ✅ | 🔄 | ✅ **NEU** | [→ Flow](../System%20Flows/14-satellite-cards-flow-server-frontend.md) |

**Dokumentations-Abdeckung:** 14/14 Flows dokumentiert (100%) ✅

### Vision → System Flow Mapping

| Vision Feature | Dokumentiert | Implementiert | Nächste Schritte |
|----------------|--------------|---------------|------------------|
| Satelliten-Cards | ✅ Flow 14 | 🔄 85% | ESPCard Layout-Integration |
| Zone Drag & Drop | ✅ Flow 08 (API) | 📋 0% | Frontend DnD Library |
| Logic Builder | ✅ Flow 13 | 🔄 70% | UI Builder Komponente |
| Mock → ESP Transfer | 📋 In Vision | 📋 0% | API + Frontend |
| Custom Libraries | ✅ Flow 09 | 📋 30% | Admin UI |

**Siehe:** `El Frontend/Docs/System_Flows_Analysis_Report.md` für detaillierte Analyse

---

## Roadmap & Prioritäten

### Phase 2.5: Satelliten-Cards Fertigstellung (Aktuell)

| Task | Status | Aufwand | Abhängigkeiten |
|------|--------|---------|----------------|
| ESPCard Satelliten-Layout | 🔄 | 2d | - |
| ConnectionLines Logic-Parsing | 🔄 | 2d | Logic Engine API |
| Position Tracking | 📋 | 1d | Layout |
| **Gesamt Phase 2.5** | | **5d** | |

### Phase 3: Zone Drag & Drop

| Task | Status | Aufwand | Abhängigkeiten |
|------|--------|---------|----------------|
| DnD Library Integration | 📋 | 1d | - |
| Zone-Übersicht Refactoring | 📋 | 2d | - |
| "Ohne Zone" Bereich | 📋 | 1d | - |
| Drop-Zone Validierung | 📋 | 1d | - |
| **Gesamt Phase 3** | | **5d** | |

### Phase 4: Mock → ESP Transfer

| Task | Status | Aufwand | Abhängigkeiten |
|------|--------|---------|----------------|
| Transfer API Backend | 📋 | 2d | - |
| Config-Diff UI | 📋 | 1d | - |
| Transfer-Wizard | 📋 | 2d | - |
| **Gesamt Phase 4** | | **5d** | |

### Phase 5: Logic Builder UI

| Task | Status | Aufwand | Abhängigkeiten |
|------|--------|---------|----------------|
| Visual Rule Builder | 🔄 | 5d | Logic Engine |
| Condition Editor | 📋 | 2d | - |
| Action Editor | 📋 | 2d | - |
| Rule Testing | 📋 | 2d | - |
| **Gesamt Phase 5** | | **11d** | |

---

### Industrie-Standards Checkliste

| Standard | Beschreibung | Status |
|----------|--------------|--------|
| **Availability** | 99.9% Uptime für Kern-System | ✅ Error Recovery |
| **Security** | JWT Auth, RBAC, HTTPS | ✅ Implementiert |
| **Scalability** | Kaiser-Node Architektur | ✅ Vorbereitet |
| **Observability** | Logs, Metrics, Tracing | 🔄 Basis vorhanden |
| **Resilience** | Circuit Breaker, Retry | ✅ MQTT/WiFi |
| **Auditability** | User-Action Logging | 🔄 Basis |
| **Backup/Recovery** | DB Backup, Config Export | 📋 Geplant |

---

*Letzte Aktualisierung: Dezember 2025*  
*Verifiziert gegen: System Flows 01-14*
