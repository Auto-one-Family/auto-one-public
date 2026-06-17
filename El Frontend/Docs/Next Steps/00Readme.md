# AutomationOne - Entwickler-Briefings Übersicht

> **Stand:** 2026-01-05  
> **Erstellt von:** Claude (Manager-Modus)  
> **Basierend auf:** Chat-Historie und Projekt-Dokumentation

---

## 📋 Zusammenfassung der Aufgabenbereiche

Basierend auf deiner Priorisierung (1, 2, 4, 5) wurden **4 detaillierte Entwicklerdokumente** erstellt:

| # | Briefing | Priorität | Aufwand | Status |
|---|----------|-----------|---------|--------|
| 01 | **Wokwi ESP-Virtualisierung** | 🔴 KRITISCH | 3-5 Tage | Neu |
| 02 | **Logging-Infrastruktur** | 🟠 HOCH | 2-3 Tage | Teilweise implementiert |
| 03 | **Logic Engine Visual Builder** | 🔴 KRITISCH | 5-8 Tage | Placeholder vorhanden |
| 04 | **CI Pipeline Enhancement** | 🟠 HOCH | 2-3 Tage | Basis vorhanden |

**Gesamtaufwand geschätzt:** 12-19 Entwicklertage

---

## 📁 Dokumente

### DEV-BRIEFING_01_Wokwi-ESP-Virtualisierung.md

**Ziel:** Echte ESP32-Firmware in Wokwi simulieren mit MQTT-Broker-Anbindung

**Kernpunkte:**
- Wokwi-Environment in `platformio.ini`
- `wokwi.toml` und `diagram.json` erstellen
- Compile-Time Credentials für Simulation
- GitHub Actions Integration mit Wokwi CLI
- Test-Szenarien für Boot, MQTT, Sensor, Actuator

**Unterschied zu Mock-ESPs:**
- Mock-ESP = Python-Simulation (Server-seitig)
- Wokwi-ESP = Echte C++ Firmware (Hardware-simuliert)

---

### DEV-BRIEFING_02_Logging-Infrastruktur.md

**Ziel:** Zentrale Log-Ansicht im Frontend mit ESP-Logs, Server-Logs, MQTT, Error-Codes

**Kernpunkte:**
- ESP-Log-Handler implementieren (MQTT → DB → WebSocket)
- `esp_logs` Database-Tabelle erstellen
- Error-Code-Referenz-API (`/v1/debug/error-codes`)
- `LogCenterView.vue` mit Tabs und Filtern
- Menschenlesbare Error-Code-Beschreibungen

**Bereits vorhanden:**
- MqttLogView (WebSocket-Events)
- LogViewerView (Server-Logs)
- ESP32 Logger (sendet via MQTT)

---

### DEV-BRIEFING_03_Logic-Engine-Visual-Builder.md

**Ziel:** Node-Red-ähnlicher Visual Rule Editor für Cross-ESP-Automation

**Kernpunkte:**
- SVG-Canvas für Verbindungslinien
- Drag-and-Drop: Sensor → Actuator
- Rule-Editor-Modal öffnet automatisch
- Bezier-Kurven für elegante Verbindungen
- Live-Execution-Visualisierung (pulsierend)
- Menschenlesbare Darstellung auf Linien

**Backend bereits implementiert:**
- Logic Engine (Evaluation, Execution)
- REST API für Rules CRUD
- WebSocket für `logic_execution` Events

---

### DEV-BRIEFING_04_CI-Pipeline-Enhancement.md

**Ziel:** KI-lesbares Test-Output für VS Code Integration

**Kernpunkte:**
- JSON-Output mit `pytest-json-report`
- Coverage-Analyse mit Gap-Identifikation
- System-Flow-Test-Matrix
- Konsolidierter KI-Report (`ki-ci-report.json`)
- Testabdeckungs-Checkliste für alle Flows

**Bereits vorhanden:**
- `server-tests.yml`, `esp32-tests.yml`, `pr-checks.yml`
- pytest mit pytest-cov

---

## 🔄 Abhängigkeiten

```
                    ┌───────────────────┐
                    │ 01: Wokwi Setup   │
                    │ (unabhängig)      │
                    └───────────────────┘
                    
┌───────────────────┐     ┌───────────────────┐
│ 02: Logging       │────▶│ 04: CI Pipeline   │
│ (Backend zuerst)  │     │ (nutzt neue Logs) │
└───────────────────┘     └───────────────────┘
        │
        ▼
┌───────────────────┐
│ 03: Logic Builder │
│ (nutzt Log-System)│
└───────────────────┘
```

**Empfohlene Reihenfolge:**
1. **Briefing 01** (Wokwi) - Unabhängig, kann parallel laufen
2. **Briefing 02** (Logging) - Backend-Grundlage
3. **Briefing 04** (CI) - Nutzt Logging-Verbesserungen
4. **Briefing 03** (Logic Builder) - Größtes Feature, am Ende

---

## 📖 Pflichtlektüre für Entwickler

Jedes Briefing verweist auf diese Kern-Dokumentation:

| Dokument | Pfad | Inhalt |
|----------|------|--------|
| **CLAUDE.md** | `.claude/CLAUDE.md` | ESP32-Architektur, Build-Commands |
| **CLAUDE_SERVER.md** | `.claude/CLAUDE_SERVER.md` | Server-Architektur, MQTT, API |
| **Hierarchie.md** | `Hierarchie.md` | 4-Layer-System, Kommunikation |

---

## ⚠️ Wichtige Hinweise

### Mock-ESP vs. Real-ESP vs. Wokwi-ESP

| Typ | Implementierung | MQTT | Firmware | Zweck |
|-----|----------------|------|----------|-------|
| **Mock-ESP** | Python (Server) | Simuliert | Keine | Server-Tests, Load-Tests |
| **Real-ESP** | C++ (Hardware) | Echt | Echt | Produktion |
| **Wokwi-ESP** | C++ (Simulator) | Echt | Echt | Firmware-Tests ohne Hardware |

### Konsistenz mit Codebase

Alle Briefings betonen:
- **Bestehende Patterns verwenden** (Repository, Service, Handler)
- **TopicBuilder für MQTT-Topics**
- **WebSocketManager für Broadcasts**
- **Pydantic für Validation**
- **Alembic für Migrationen**

---

## 🚀 Nächste Schritte

1. **Briefings mit Entwicklern teilen**
2. **Phase 1 jedes Briefings:** Codebase-Analyse durchführen
3. **Priorität setzen:** Wokwi + Logging parallel starten
4. **Regelmäßige Reviews** nach jeder Phase

---

**Fragen?** Die Briefings enthalten detaillierte Checklisten und Code-Templates. Bei Unklarheiten: Codebase analysieren und mit bestehenden Patterns abgleichen.