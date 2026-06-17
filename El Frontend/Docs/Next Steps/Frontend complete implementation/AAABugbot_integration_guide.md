# Bugbot-Integration: Manager-Guide

**Für:** Technische Manager, die Entwickleranweisungen erstellen  
**Zweck:** Bugbot optimal in jeder Backend-Phase nutzen

---

## Was ist Bugbot?

Bugbot ist ein **statischer Code-Analyzer**, der PR-Diffs automatisch auf Bugs prüft und Kommentare direkt in GitHub hinterlässt.

### Was Bugbot MACHT:
- Prüft **nur geänderte Code-Zeilen** (PR-Diff)
- Erkennt Logik-Fehler, Security-Issues, Inkonsistenzen
- Befolgt projekt-spezifische Regeln aus `BUGBOT.md`
- Schreibt Inline-Kommentare mit Severity (Low/Medium/High)

### Was Bugbot NICHT MACHT:
- ❌ Führt keine Tests aus (kein pytest, kein Wokwi)
- ❌ Analysiert keine unveränderten Dateien
- ❌ Erstellt keine Reports oder Dateien
- ❌ Kann nicht auf bestimmte Ordner eingeschränkt werden

---

## BUGBOT.md - Die Steuerungs-Datei

Die Datei `BUGBOT.md` im Repo-Root steuert **wie** Bugbot den Diff interpretiert:

| Abschnitt | Zweck |
|-----------|-------|
| **Architektur** | Bugbot versteht Zusammenhänge |
| **Invarianten** | Was IMMER gelten muss → wird aktiv geprüft |
| **Kein Bug** | False-Positive-Unterdrückung für Tests/Mocks |
| **Domain-Checks** | Projekt-spezifische Regeln |
| **Fokus-Prioritäten** | Bei Änderungen in X → besonders auf Y achten |

---

## Integration pro Backend-Phase

### Phase 1: Hardware Foundation

**Aktuelle Fokus-Bereiche in BUGBOT.md:**

```markdown
### Phase 1: Hardware Foundation
- sensor_handler.py: Quality-Feld, Error-Code-Mapping
- i2c_bus.cpp/h: Recovery-Logik, Bus-Stuck-Detection
- onewire_bus.cpp/h: DS18B20 Fehlerwert-Erkennung
- error_codes.h: Neue Codes in Range 1015-1018, 1060-1063
```

**Bugbot prüft bei Phase-1-PRs:**
- Werden `-127°C` und `85°C` als Error erkannt?
- Ist `quality: "error"` bei ungültigen Werten gesetzt?
- Sind neue Error-Codes in korrekter Range (1015-1018, 1060-1063)?
- Wird I2C-Recovery korrekt implementiert?

### Zukünftige Phasen

Bei neuer Phase → BUGBOT.md erweitern:

```markdown
### Phase N: [Name]
- [datei1.py]: Was prüfen
- [datei2.cpp]: Was prüfen
- Neue Invarianten: ...
```

---

## Workflow: BUGBOT.md aktuell halten

### Bei neuer Entwicklungsphase:

1. **Fokus-Abschnitt hinzufügen**
   ```markdown
   ### Phase N: [Name]
   - Relevante Dateien und was zu prüfen ist
   ```

2. **Neue Invarianten definieren**
   - Was muss IMMER gelten?
   - Welche Wertebereiche?
   - Welche Abhängigkeiten?

3. **False-Positives vorwegnehmen**
   - Neue Test-Patterns in "Kein Bug" aufnehmen
   - Neue Mock-Typen dokumentieren

### Bei wiederkehrenden False-Positives:

```markdown
## 3. Kein Bug

### 3.X [Neues Pattern]
- `[pattern]` in `[pfad]` ist beabsichtigt weil [grund]
```

### Bei neuen Komponenten:

```markdown
## 4. Domain-spezifische Checks

### 4.X [Neue Komponente]
Bei Änderungen in `[pfad]` prüfen:
- [check 1]
- [check 2]
```

---

## Bugbot-Output interpretieren

### Severity-Stufen

| Severity | Bedeutung | Aktion |
|----------|-----------|--------|
| **High** | Safety-Verletzung, Daten-Korruption | Sofort beheben |
| **Medium** | API-Bruch, fehlendes Error-Handling | Vor Merge beheben |
| **Low** | Style, fehlende Doku | Optional beheben |

### Typische Findings

**High:**
- "PWM value 1.5 exceeds maximum of 1.0"
- "Emergency-Stop check missing before actuator command"
- "Error code 1060 outside valid range"

**Medium:**
- "Missing quality field in sensor payload"
- "Topic pattern inconsistent with constants.py"
- "No error handling for MQTT publish failure"

**Low:**
- "Type hint missing for parameter"
- "Logging statement missing for error case"

---

## Zusammenspiel: CI Pipeline + Bugbot

```
┌─────────────────────────────────────────────────────────────┐
│ Pull Request erstellt                                        │
└─────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  CI Pipeline    │  │    Bugbot       │  │  Code Review    │
│  (pytest, etc.) │  │  (BUGBOT.md)    │  │  (Manuell)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Tests bestanden │  │ Inline-Comments │  │ Approve/Request │
│ oder gefailed   │  │ auf GitHub      │  │ Changes         │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Arbeitsteilung:**
- **CI Pipeline:** Führt Tests aus, prüft ob Code funktioniert
- **Bugbot:** Prüft Logik/Invarianten im Diff, findet potenzielle Bugs
- **Code Review:** Architektur-Entscheidungen, Best Practices

---

## Checkliste: BUGBOT.md pflegen

### Wöchentlich:
- [ ] Wiederkehrende False-Positives als "Kein Bug" aufnehmen
- [ ] Neue Test-Patterns dokumentieren

### Bei Phase-Wechsel:
- [ ] Fokus-Abschnitt für neue Phase hinzufügen
- [ ] Alte Phase kann bleiben (Regression-Schutz)
- [ ] Neue Invarianten formulieren

### Bei neuen Komponenten:
- [ ] Domain-Check hinzufügen
- [ ] Pfade in Architektur aktualisieren
- [ ] Relevante Patterns dokumentieren

---

## Quick Reference: BUGBOT.md Struktur

```markdown
# BUGBOT.md

## 1. Architektur-Überblick
[Komponenten, Pfade, Zusammenhänge]

## 2. Kritische Invarianten
[Was IMMER gelten muss - wird aktiv geprüft]

## 3. Kein Bug
[False-Positive-Unterdrückung]

## 4. Domain-spezifische Checks
[Bei Änderungen in X → prüfe Y]

## 5. Fokus-Prioritäten nach Phase
[Aktuelle Phase hervorheben]

## 6. Code-Konventionen
[Sprach-spezifische Regeln]

## 7. Severity-Hinweise
[Wann High/Medium/Low]

## 8. Bekannte Patterns
[Patterns die kein Bug sind]
```

---

**Fazit:** Bugbot ist ein Invarianten-Prüfer für PR-Diffs. Die Qualität seiner Findings hängt direkt von der Qualität der BUGBOT.md ab. Halte sie aktuell, formuliere klare Regeln, und dokumentiere False-Positives.