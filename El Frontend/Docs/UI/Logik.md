# 🔄 Logik/Automation - LogicView UI-Dokumentation

## 🎯 LogicView (`/logic`) - Visueller Rule-Builder für IoT-Automation

### Übersicht
- **Route**: `/logic`
- **Status**: ✅ Vollständig implementiert und dokumentiert
- **Zweck**: Visueller Automation-Rule Builder für IoT-Systeme mit Drag&Drop-Funktionalität
- **Zielgruppe**: Administratoren und Power-User für die Erstellung komplexer Automationsregeln
- **Technologie**: React + TypeScript, Canvas-basierte UI mit SVG-Rendering

---

## 📋 1. UI-Komponenten detailliert

### Hauptlayout-Struktur
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Header: [Neu erstellen] [Templates ▼] [Test-Modus] [Import] [Export] [?] │
├─────────────────┬───────────────────────────────────────────────────────┤
│ Toolbox         │ Canvas-Bereich                                        │
│ ┌─────────────┐ │ ┌───────────────────────────────────────────────────┐ │
│ │ 📅 Triggers │ │ │                                                   │ │
│ │ • Timer     │ │ │  [🌅 Morgenlicht] ────────▶ [💡 LED ON]            │ │
│ │ • Schedule  │ │ │                                                   │ │
│ │ • Sensor    │ │ │  [🌡️ Temp > 25°C] ────────▶ [❄️ AC ON]             │ │
│ │ • Event     │ │ │                                                   │ │
│ ├─────────────┤ │ │  [📱 ESP Offline] ────────▶ [📧 Email Alert]        │ │
│ │ ⚡ Actions  │ │ │                                                   │ │
│ │ • Actuator  │ │ └───────────────────────────────────────────────────┘ │
│ │ • Notify    │ │                                                       │
│ │ • Email     │ │ Rule-Liste:                                           │
│ │ • Webhook   │ │ ┌───────────────────────────────────────────────────┐ │
│ │ • API Call  │ │ │ 🟢 🌅 Morgenlicht (aktiv) - Letzte Ausführung: 07:00 │ │
│ └─────────────┘ │ │ 🟡 🌡️ Klimatisierung (testend) - Simuliert: 3x    │ │
│                 │ │ 🔴 🚪 Sicherheitsalarm (inaktiv) - Deaktiviert     │ │
│ Conditions      │ │ 🟢 📧 Systembenachrichtigungen (aktiv) - 12 Alerts │ │
│ ┌─────────────┐ │ └───────────────────────────────────────────────────┘ │
│ │ 📊 Compare  │ │                                                       │
│ │ • > < =     │ │ Status-Bar: [Ausführungen: 247] [Aktive: 3/5] [Fehler: 2] │
│ │ • Range     │ │                                                       │
│ │ • Contains  │ │                                                       │
│ │ • Logic     │ │                                                       │
│ │ • Time      │ │                                                       │
│ └─────────────┘ └───────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

### Komponenten-Details

#### Header-Bar (Toolbar)
- **Neu erstellen**: Button öffnet Rule-Erstellungs-Modal mit leerem Canvas
- **Templates ▼**: Dropdown mit vordefinierten Rule-Templates (Morgenlicht, Sicherheit, Klima, etc.)
- **Test-Modus**: Toggle für Sandbox-Modus (keine echte Hardware-Beeinflussung)
- **Import/Export**: JSON-Import/Export für Rule-Backup und -Sharing
- **?**: Hilfe-Button mit interaktiver Tour durch die UI

#### Toolbox-Panel (Linke Sidebar)
- **Triggers**: Droppable Elemente für Event-Auslöser
  - Timer: Zeitbasierte Trigger (einmalig/wiederholend)
  - Schedule: Kalenderbasierte Trigger mit Cron-Syntax
  - Sensor: Hardware-Sensor Events (Temperatur, Bewegung, etc.)
  - Event: System-Events (ESP-Verbindung, Fehler, etc.)
- **Actions**: Droppable Elemente für Rule-Ausführungen
  - Actuator: Hardware-Steuerung (Relais, Motoren, LEDs)
  - Notify: Push-Benachrichtigungen an User
  - Email: E-Mail-Versand mit Templates
  - Webhook: HTTP-Callbacks zu externen Services
  - API Call: REST-API Aufrufe zu anderen Systemen
- **Conditions**: Droppable Elemente für Regelbedingungen
  - Compare: Numerische Vergleiche (>, <, =, etc.)
  - Range: Wertebereich-Prüfungen
  - Contains: String/Text-Contains-Checks
  - Logic: Boolesche Operatoren (AND, OR, NOT)
  - Time: Zeitbasierte Bedingungen (Wochentag, Uhrzeit, etc.)

#### Canvas-Bereich (Hauptbereich)
- **Grid-basierter visueller Builder** mit 20x20 Pixel Raster
- **Drag&Drop-Unterstützung** für alle Toolbox-Elemente
- **SVG-Rendering** für Flow-Pfeile und Verbindungen
- **Zoom & Pan** Funktionalität (Mousewheel + Drag)
- **Context-Menüs** für Rechtsklick auf Elemente
- **Undo/Redo** mit Strg+Z/Strg+Y

#### Rule-Liste (Untere rechte Ecke)
- **Kartenbasierte Darstellung** bestehender Regeln
- **Status-Badges**: 🟢 Aktiv, 🔴 Inaktiv, 🟡 Testmodus
- **Metriken**: Letzte Ausführung, Ausführungsanzahl, Fehlercount
- **Quick-Actions**: Bearbeiten, Duplizieren, Aktivieren/Deaktivieren, Löschen
- **Filter & Suche**: Nach Name, Status, Typ filtern

#### Status-Bar (Unterer Rand)
- **Live-Metriken**: Gesamt-Ausführungen, aktive Regeln, Fehler
- **System-Status**: Rule-Engine Status, letzte Regel-Ausführung
- **Performance**: CPU/Memory Usage der Automation-Engine

---

## 🎯 2. Rule-Builder Interaktionen

### Drag&Drop Workflow
1. **Trigger hinzufügen**: Element aus Toolbox in Canvas ziehen
2. **Positionieren**: Element auf gewünschte Position fallen lassen
3. **Konfigurieren**: Doppelklick öffnet Konfigurations-Modal
4. **Verbinden**: Von Trigger-Ausgang zu Condition/Action ziehen
5. **Testen**: Rechtsklick → "Test Rule" für Simulation

### Element-Konfiguration

#### Trigger-Konfiguration
```typescript
interface TimerTrigger {
  type: 'timer';
  schedule: {
    type: 'once' | 'recurring';
    datetime?: string; // ISO 8601 für einmalig
    cron?: string;     // Cron-Expression für wiederholend
    timezone: string;
  };
}

interface SensorTrigger {
  type: 'sensor';
  sensorId: string;
  condition: 'above' | 'below' | 'equals' | 'changes';
  threshold: number;
  debounceMs: number; // Entprellung
}

interface EventTrigger {
  type: 'event';
  eventType: 'esp_online' | 'esp_offline' | 'error' | 'custom';
  eventData?: any;
}
```

#### Condition-Konfiguration
```typescript
interface CompareCondition {
  type: 'compare';
  leftOperand: {
    type: 'sensor' | 'variable' | 'constant';
    sensorId?: string;
    variableName?: string;
    value?: any;
  };
  operator: '>' | '<' | '>=' | '<=' | '==' | '!=';
  rightOperand: {
    type: 'sensor' | 'variable' | 'constant';
    sensorId?: string;
    variableName?: string;
    value?: any;
  };
}

interface LogicCondition {
  type: 'logic';
  operator: 'AND' | 'OR' | 'NOT';
  conditions: Condition[]; // Rekursiv für komplexe Logik
}
```

#### Action-Konfiguration
```typescript
interface ActuatorAction {
  type: 'actuator';
  actuatorId: string;
  command: 'on' | 'off' | 'toggle' | 'set_value';
  value?: number; // Für dimmable Aktoren
  duration?: number; // Temporäre Aktivierung in Sekunden
}

interface NotificationAction {
  type: 'notify';
  title: string;
  message: string;
  priority: 'low' | 'normal' | 'high' | 'critical';
  userIds: string[]; // Ziel-User für Push-Notifications
}
```

### Verbindungsmechanismus
- **Automatisches Routing**: SVG-Pfade zwischen Elementen
- **Connection-Points**: Definierte Ein-/Ausgangspunkte pro Element-Typ
- **Flow-Direction**: Einbahnstraßen-Logik (Trigger → Condition → Action)
- **Branching**: Mehrere Actions pro Condition möglich
- **Visual Feedback**: Hover-Highlights für verbundene Elemente

### Rule-Testing & Validation
- **Test-Modus**: Sandbox-Environment ohne Hardware-Änderungen
- **Step-by-Step Execution**: Einzelne Rule-Schritte debuggen
- **Mock Data**: Simulierte Sensor-Werte für Testing
- **Validation Feedback**: Client- und Serverseitige Regel-Validierung
- **Performance Metrics**: Ausführungszeit, Ressourcen-Verbrauch

---

## 🔌 3. Server-API Integration

### REST-API Endpoints

#### Rule-Management
```typescript
// Alle Rules laden mit Filter-Optionen
GET /api/v1/logic/rules
Query-Params:
  - status: 'active' | 'inactive' | 'testing'
  - type: 'timer' | 'sensor' | 'event'
  - page: number
  - limit: number
  - search: string

// Einzelne Rule laden
GET /api/v1/logic/rules/{id}

// Neue Rule erstellen
POST /api/v1/logic/rules
Body: {
  name: string;
  description?: string;
  trigger: TriggerConfig;
  conditions: ConditionConfig[];
  actions: ActionConfig[];
  priority: number;
  enabled: boolean;
  testMode: boolean;
}

// Rule aktualisieren
PUT /api/v1/logic/rules/{id}
Body: RuleUpdateData

// Rule löschen
DELETE /api/v1/logic/rules/{id}

// Rule aktivieren/deaktivieren
PATCH /api/v1/logic/rules/{id}/status
Body: { enabled: boolean }
```

#### Template-Management
```typescript
// Verfügbare Templates laden
GET /api/v1/logic/templates

// Template anwenden (erstellt neue Rule)
POST /api/v1/logic/templates/{templateId}/apply
Body: {
  name: string;
  customizations: TemplateCustomization[];
}
```

#### Testing & Simulation
```typescript
// Rule simulieren ohne Ausführung
POST /api/v1/logic/test
Body: {
  rule: RuleConfig;
  mockData: {
    sensors: Record<string, any>;
    variables: Record<string, any>;
  };
  steps: number; // Anzahl Simulationsschritte
}

// Test-Ergebnisse abrufen
GET /api/v1/logic/test/{testId}
```

#### Monitoring & Analytics
```typescript
// Rule-Ausführungs-Historie
GET /api/v1/logic/rules/{id}/history
Query-Params:
  - from: ISO8601
  - to: ISO8601
  - status: 'success' | 'error' | 'timeout'

// System-Metriken
GET /api/v1/logic/metrics
Returns: {
  totalRules: number;
  activeRules: number;
  executionsToday: number;
  averageExecutionTime: number;
  errorRate: number;
}
```

### WebSocket Events

#### Real-time Updates
```typescript
// Rule wurde getriggert
{
  event: 'rule_triggered',
  data: {
    ruleId: string;
    triggerData: any;
    timestamp: string;
  }
}

// Rule wurde ausgeführt
{
  event: 'rule_executed',
  data: {
    ruleId: string;
    executionId: string;
    success: boolean;
    executionTime: number;
    results: ActionResult[];
    timestamp: string;
  }
}

// Rule-Fehler
{
  event: 'rule_error',
  data: {
    ruleId: string;
    error: string;
    context: any;
    timestamp: string;
  }
}

// Live-Status-Updates
{
  event: 'rule_status_changed',
  data: {
    ruleId: string;
    oldStatus: RuleStatus;
    newStatus: RuleStatus;
    timestamp: string;
  }
}
```

#### System-Events
```typescript
// Rule-Engine Status
{
  event: 'engine_status',
  data: {
    status: 'running' | 'paused' | 'error';
    uptime: number;
    activeRules: number;
    queueLength: number;
  }
}
```

---

## 📚 4. Rule-Types & Templates

### Basis Rule-Types

#### 1. Time-based Rules (Zeitgesteuert)
```json
{
  "name": "Morgenlicht",
  "trigger": {
    "type": "timer",
    "schedule": {
      "type": "recurring",
      "cron": "0 7 * * 1-5",
      "timezone": "Europe/Berlin"
    }
  },
  "conditions": [
    {
      "type": "compare",
      "leftOperand": { "type": "sensor", "sensorId": "light_sensor_1" },
      "operator": "<",
      "rightOperand": { "type": "constant", "value": 50 }
    }
  ],
  "actions": [
    {
      "type": "actuator",
      "actuatorId": "led_strip_1",
      "command": "on",
      "duration": 3600
    }
  ]
}
```

#### 2. Sensor-based Rules (Sensor-gesteuert)
```json
{
  "name": "Klimatisierung",
  "trigger": {
    "type": "sensor",
    "sensorId": "temperature_sensor_1",
    "condition": "above",
    "threshold": 25,
    "debounceMs": 300000
  },
  "conditions": [],
  "actions": [
    {
      "type": "actuator",
      "actuatorId": "ac_unit_1",
      "command": "on"
    },
    {
      "type": "notify",
      "title": "Klimatisierung aktiviert",
      "message": "Temperatur über 25°C - Klimaanlage eingeschaltet",
      "priority": "normal"
    }
  ]
}
```

#### 3. Event-based Rules (Event-gesteuert)
```json
{
  "name": "Sicherheitsalarm",
  "trigger": {
    "type": "event",
    "eventType": "esp_offline",
    "eventData": { "espId": "esp_livingroom" }
  },
  "conditions": [
    {
      "type": "time",
      "from": "22:00",
      "to": "06:00",
      "timezone": "Europe/Berlin"
    }
  ],
  "actions": [
    {
      "type": "notify",
      "title": "Sicherheitsalarm",
      "message": "ESP im Wohnzimmer offline während Nachtzeit!",
      "priority": "critical"
    },
    {
      "type": "email",
      "to": ["security@example.com"],
      "subject": "Sicherheitsalarm: ESP Offline",
      "template": "security_alert"
    }
  ]
}
```

#### 4. Complex Rules (Komplexe Regeln)
```json
{
  "name": "Intelligente Beleuchtung",
  "trigger": {
    "type": "sensor",
    "sensorId": "motion_sensor_1",
    "condition": "changes",
    "threshold": 1
  },
  "conditions": [
    {
      "type": "logic",
      "operator": "AND",
      "conditions": [
        {
          "type": "compare",
          "leftOperand": { "type": "sensor", "sensorId": "light_sensor_1" },
          "operator": "<",
          "rightOperand": { "type": "constant", "value": 30 }
        },
        {
          "type": "time",
          "from": "18:00",
          "to": "23:00"
        },
        {
          "type": "logic",
          "operator": "NOT",
          "conditions": [
            {
              "type": "compare",
              "leftOperand": { "type": "variable", "variableName": "vacation_mode" },
              "operator": "==",
              "rightOperand": { "type": "constant", "value": true }
            }
          ]
        }
      ]
    }
  ],
  "actions": [
    {
      "type": "actuator",
      "actuatorId": "led_strip_1",
      "command": "on",
      "duration": 300
    }
  ]
}
```

### Template-System

#### Vordefinierte Templates
1. **🏠 Smart Home Grundlagen**
   - Morgenlicht, Abendlicht, Anwesenheitssimulation

2. **🔒 Sicherheit & Überwachung**
   - Bewegungsmelder, Türsensor, Offline-Alerts

3. **🌡️ Klima & Komfort**
   - Temperaturregelung, Luftfeuchtigkeit, Lüftung

4. **📧 Benachrichtigungen**
   - Systemstatus, Fehler-Alerts, Wartungsbenachrichtigungen

5. **🔄 Integrationen**
   - Webhook-Callbacks, API-Integrationen, externe Services

#### Template-Anpassung
- **Parameter-Mapping**: Automatische Zuordnung von Sensor/Aktor-IDs
- **Kontextabhängige Werte**: Zeitbasierte Anpassungen
- **Lokalisierung**: Mehrsprachige Templates
- **Versionierung**: Template-Updates ohne Datenverlust

---

## 🎨 5. Design-Spezifikationen

### Color-Coding System
- **🔵 Triggers**: `#3B82F6` (Blue-500) - Event-Auslöser
- **🟡 Conditions**: `#F59E0B` (Amber-500) - Regelbedingungen
- **🟢 Actions**: `#10B981` (Emerald-500) - Ausführungen
- **🔴 Error States**: `#EF4444` (Red-500) - Fehler/Fehlschläge
- **⚪ Inactive**: `#6B7280` (Gray-500) - Deaktivierte Elemente

### Status-Badges
- **🟢 Active**: Regel ist aktiv und wird ausgeführt
- **🔴 Inactive**: Regel ist deaktiviert
- **🟡 Testing**: Regel im Testmodus (Sandbox)
- **🔵 Draft**: Regel im Entwurfsstadium
- **🟠 Error**: Regel hat Ausführungsfehler

### Canvas-Design
- **Grid**: 20px Raster mit dotted lines (`#E5E7EB`)
- **Elemente**: Rounded rectangles mit 8px border-radius
- **Shadows**: Subtle drop-shadows für Depth
- **Flow-Arrows**: SVG paths mit animated dashes während Ausführung
- **Hover-Effects**: Scale transform (1.02x) mit smooth transitions

### Responsive Design
- **Desktop**: Vollständiges 3-Panel Layout
- **Tablet**: Collapsible Toolbox, kompaktere Rule-Liste
- **Mobile**: Stack-Layout mit Bottom-Sheet für Toolbox

---

## 🔧 6. Technische Implementierung

### Frontend-Architektur
```typescript
// Hauptkomponenten
- LogicView: Hauptcontainer
- Canvas: SVG-basierter visueller Builder
- Toolbox: Drag&Drop Element-Bibliothek
- RuleList: Bestehende Regeln Übersicht
- RuleModal: Einzelne Rule-Konfiguration
- TemplateSelector: Template-Auswahl Dialog

// State-Management
- Zustand Store für Rule-Daten
- React Flow für Canvas-Management
- React DnD für Drag&Drop
- WebSocket für Real-time Updates
```

### Performance-Optimierungen
- **Virtualisierung**: Canvas-Elemente nur bei Bedarf rendern
- **Debouncing**: Sensor-Events entprellen (300ms default)
- **Caching**: Rule-Definitions clientseitig cachen
- **Lazy Loading**: Templates und Historie nach Bedarf laden
- **WebWorkers**: Schwere Berechnungen auslagern

### Sicherheit & Validation
- **Clientseitig**: JSON-Schema Validation für Rules
- **Serverseitig**: Vollständige Business-Logic Validation
- **Sandbox-Modus**: Isolierte Ausführung für Testing
- **Audit-Logging**: Vollständige Historie aller Rule-Änderungen
- **Permission-Checks**: Rollenbasierte Zugriffssteuerung

### Testing-Strategie
- **Unit Tests**: Einzelne Komponenten und Utilities
- **Integration Tests**: API-Integration und WebSocket
- **E2E Tests**: Vollständige User-Flows mit Cypress
- **Performance Tests**: Canvas-Rendering und Rule-Ausführung
- **Visual Regression**: UI-Komponenten auf Layout-Änderungen

---

## 📖 7. User-Flows & Tutorials

### Erste Rule erstellen
1. **Zugriff**: Navigation zu `/logic`
2. **Template wählen**: "Morgenlicht" Template auswählen
3. **Anpassen**: Sensor-IDs und Zeiten konfigurieren
4. **Testen**: Test-Modus aktivieren und Rule simulieren
5. **Aktivieren**: Rule als aktiv markieren

### Komplexe Rule bauen
1. **Canvas vorbereiten**: Leere Rule erstellen
2. **Trigger hinzufügen**: Sensor-Trigger in Canvas ziehen
3. **Conditions konfigurieren**: Bedingungen mit Drag&Drop verknüpfen
4. **Actions zuweisen**: Mehrere Actions pro Condition
5. **Validieren**: Client- und Serverseitige Validierung
6. **Deployen**: Rule aktivieren und überwachen

### Troubleshooting
- **Rule nicht ausgeführt**: Logs prüfen, Conditions überprüfen
- **Performance-Probleme**: Execution-Metriken analysieren
- **Fehlerbehebung**: Test-Modus für isolierte Fehleranalyse
- **Backup/Restore**: JSON-Export für Rule-Backups

---

## 🚀 Zukünftige Erweiterungen

### Geplante Features
- **Rule-Versionierung**: Git-ähnliches Versionierungssystem
- **Collaborative Editing**: Mehrbenutzer-Bearbeitung mit Konfliktlösung
- **AI-Assistent**: Automatische Rule-Vorschläge basierend auf Verhalten
- **Advanced Analytics**: Detaillierte Ausführungsanalysen und Optimierungen
- **Mobile App**: Native Mobile-Optimierung für Rule-Management

### Integration-Möglichkeiten
- **Alexa/Google Home**: Voice-Control für Rules
- **IFTTT Integration**: Verbindung zu externen Services
- **Machine Learning**: Predictive Automation basierend auf Mustern
- **Multi-Tenant**: Mandantenfähige Rule-Isolation

---

*Letzte Aktualisierung: Dezember 2025 | Version: 1.0.0 | Autor: AI Documentation Assistant*
