# 📊 Audit-Log - Vollständige UI-Dokumentation

## 🎯 AuditLogView (`/audit`) - Komplette Event-Tracking Dokumentation

Diese Dokumentation beschreibt die vollständige Implementierung eines Audit-Logging-Systems für Compliance, Security-Monitoring und Troubleshooting. Die AuditLogView ermöglicht es Administratoren und berechtigten Usern, alle System-Events in Echtzeit zu überwachen und zu analysieren.

---

## 📋 Sektion 1: Übersicht

### **Route & Zweck**
- **Route**: `/audit`
- **Zweck**: Vollständige Event-Historie für Compliance, Debugging und Security-Monitoring
- **Zugriffsrechte**: Nur Administratoren und berechtigte User
- **Event-Types**: User Actions, System Events, API Calls, Config Changes, Security Events

### **Kernfunktionen**
- **Event-Tracking**: Automatische Erfassung aller Systemaktivitäten
- **Filter & Suche**: Mehrdimensionale Filterung und Volltext-Suche
- **Compliance**: Audit-Trail für regulatorische Anforderungen (GDPR, SOX, etc.)
- **Troubleshooting**: User-Aktivitäten und Systemfehler nachverfolgen
- **Security Monitoring**: Verdächtige Aktivitäten erkennen und alerten

---

## 🎨 Sektion 2: UI-Komponenten detailliert

### **Hauptlayout**
```
┌─────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard │ 📊 Analytics │ 📋 Audit │ ⚙️ Settings │ 👤 Profile │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ ┌─ Filter Panel ──────────────────────────────────────────────────┐ │
│ │ 🔍 [Search Input] [📅 Time Range ▼] [👤 User ▼] [📋 Type ▼] [💾 Export ▼] │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─ Event Timeline ─────────────────────────────────────────────────┐ │
│ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ │ │ 🕒 2024-01-15 14:32:15 │ 👤 admin │ 🔐 LOGIN_SUCCESS │ ✅ │ │ │
│ │ │ IP: 192.168.1.100     │ Session: abc123def456         │ │ │
│ │ │ Browser: Chrome/120.0 │ Location: Munich, DE          │ │ │
│ │ └─────────────────────────────────────────────────────────────┘ │ │
│ │                                                                 │ │
│ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ │ │ 🕒 2024-01-15 14:35:22 │ 👤 admin │ ⚙️ CONFIG_CHANGE │ ⚠️ │ │ │
│ │ │ Changed: MQTT.broker │ Old: localhost → New: prod-broker │ │ │
│ │ │ Module: System Config │ Impact: High                   │ │ │
│ │ └─────────────────────────────────────────────────────────────┘ │ │
│ │                                                                 │ │
│ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ │ │ 🕒 2024-01-15 14:40:10 │ 👤 user1 │ 📱 ESP_CREATE    │ ✅ │ │ │
│ │ │ ESP_ID: ESP_001        │ Type: MOCK_ESP32            │ │ │
│ │ │ Config: {name:"Test", ip:"192.168.1.50"}              │ │ │
│ │ └─────────────────────────────────────────────────────────────┘ │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─ Pagination & Stats ─────────────────────────────────────────────┐ │
│ │ Events: 1-50 of 2,847 │ [‹‹] [‹] [1] [2] [3] [›] [››] │ ⟲ Refresh │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ ┌─ Retention Settings ─────────────────────────────────────────────┐ │
│ │ 📅 Retention: 365 Tage │ 🗂️ Archive: 2 Jahre │ 🗑️ Delete: 5 Jahre │
│ │ ⚙️ Auto-Cleanup aktiviert │ 📊 Storage: 2.3 GB verwendet       │
│ └──────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### **Filter-Panel Komponenten**

#### **1. Search Input (🔍)**
- **Typ**: Volltext-Suche
- **Scope**: Event-Beschreibung, Payload, User, IP, Session-ID
- **Features**:
  - Live-Search (debounced 300ms)
  - Search-Highlighting in Results
  - Regex-Support für fortgeschrittene User
  - Suchverlauf speichern

#### **2. Time Range Picker (📅)**
- **Optionen**:
  - `Last 15 minutes` - Echtzeit-Monitoring
  - `Last hour` - Kurzzeit-Analyse
  - `Last 24 hours` - Tagesübersicht
  - `Last 7 days` - Wochenanalyse
  - `Last 30 days` - Monatsübersicht
  - `Custom Range` - Flexible Datumsbereiche
- **Features**:
  - Kalender-Widget mit Zeitangaben
  - Relative Zeitbereiche (rolling windows)
  - Quick-Select Buttons

#### **3. User Filter (👤)**
- **Typ**: Multi-Select Dropdown
- **Datenquelle**: `/api/v1/users/active`
- **Features**:
  - Alle User anzeigen
  - "System" für automatische Events
  - "Unknown" für nicht-authentifizierte Zugriffe

#### **4. Event Type Filter (📋)**
- **Kategorien**:
  - 🔐 **Security**: LOGIN, LOGOUT, FAILED_LOGIN, PASSWORD_CHANGE
  - ⚙️ **Configuration**: CONFIG_CHANGE, SETTINGS_UPDATE
  - 📱 **ESP Management**: ESP_CREATE, ESP_UPDATE, ESP_DELETE, ESP_COMMAND
  - 👤 **User Management**: USER_CREATE, USER_UPDATE, USER_DELETE
  - 🌐 **API Access**: API_CALL, API_ERROR
  - 🔧 **System**: BACKUP, RESTORE, MAINTENANCE, ERROR

#### **5. Export Dropdown (💾)**
- **Formate**:
  - 📄 **CSV**: Tabellarische Export für Excel
  - 📋 **JSON**: Vollständige Daten mit Payload
  - 📊 **PDF Report**: Formatierte Compliance-Reports
- **Optionen**:
  - Aktuelle Filter anwenden
  - Zeitbereich begrenzen
  - Komprimierung (ZIP für große Exports)

### **Event Timeline Komponenten**

#### **Event Entry Structure**
```typescript
interface AuditEvent {
  id: string;
  timestamp: Date;
  user: string;
  eventType: EventType;
  status: 'SUCCESS' | 'FAILED' | 'WARNING';
  description: string;
  metadata: {
    ip?: string;
    userAgent?: string;
    sessionId?: string;
    location?: string;
  };
  payload?: any; // Vollständige Event-Daten
  expandable: boolean;
}
```

#### **Event Display Modes**
- **Compact**: Zeitstempel + User + Event-Type + Status-Icon
- **Expanded**: Zusätzliche Metadaten und Payload-Preview
- **Full Detail**: Vollständige JSON-Payload mit Syntax-Highlighting

#### **Status Indicators**
- ✅ **Success**: Grüne Farbe, erfolgreiche Operationen
- ⚠️ **Warning**: Gelbe Farbe, Warnungen oder ungewöhnliche Aktivitäten
- ❌ **Failed**: Rote Farbe, fehlgeschlagene Operationen
- 🔄 **Pending**: Graue Farbe, noch nicht abgeschlossene Operationen

---

## 🔄 Sektion 3: Audit-Monitoring Interaktionen

### **Filter-Combination Logic**
```typescript
// Beispiel für kombinierte Filter-Anwendung
const appliedFilters = {
  searchQuery: "MQTT",
  timeRange: { start: "2024-01-01", end: "2024-01-31" },
  users: ["admin", "user1"],
  eventTypes: ["CONFIG_CHANGE", "ESP_CREATE"],
  status: ["SUCCESS", "WARNING"]
};

// API-Call mit kombinierten Filtern
GET /api/v1/audit?search=MQTT&start=2024-01-01&end=2024-01-31&users=admin,user1&types=CONFIG_CHANGE,ESP_CREATE&status=SUCCESS,WARNING
```

### **Event-Expansion Flow**
1. **Click auf Event-Entry** → Expand Animation (200ms)
2. **Payload Loading** → Lazy-Load für große JSON-Payloads
3. **Syntax Highlighting** → JSON/Code mit Prism.js
4. **Copy to Clipboard** → Vollständige Payload kopieren
5. **Raw View Toggle** → Zwischen formatiert/roh wechseln

### **Search-Highlighting Implementation**
```javascript
// Suchbegriffe in Results hervorheben
function highlightSearchTerms(text, searchQuery) {
  const regex = new RegExp(`(${searchQuery})`, 'gi');
  return text.replace(regex, '<mark class="search-highlight">$1</mark>');
}

// CSS für Hervorhebung
.search-highlight {
  background-color: #fff3cd;
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: bold;
}
```

### **Time-Navigation Features**
- **Timeline Scroll**: Vertikales Scrollen durch Events
- **Jump to Date**: Direkte Navigation zu spezifischen Zeitpunkten
- **Real-time Updates**: Neue Events werden oben hinzugefügt (ohne Scroll-Reset)
- **Time Markers**: Visuelle Markierungen für wichtige Zeitpunkte

### **Export-Selection Workflow**
1. **Filter anwenden** → Gewünschte Events filtern
2. **Selection bestätigen** → Export-Dialog öffnen
3. **Format wählen** → CSV/JSON/PDF
4. **Optionen setzen** → Komprimierung, Metadaten
5. **Download starten** → Progress-Bar anzeigen

---

## 🔌 Sektion 4: Server-API Integration

### **Audit Events API**

#### **GET /api/v1/audit**
**Zweck**: Events mit Filter und Pagination laden

**Query Parameters**:
```typescript
interface AuditQueryParams {
  // Pagination
  page?: number;        // Default: 1
  limit?: number;       // Default: 50, Max: 200

  // Filter
  search?: string;      // Volltext-Suche
  start?: string;       // ISO Date (2024-01-01T00:00:00Z)
  end?: string;         // ISO Date
  users?: string[];     // Komma-separiert
  types?: string[];     // Event-Types
  status?: string[];    // SUCCESS, FAILED, WARNING

  // Sorting
  sortBy?: 'timestamp' | 'user' | 'type';  // Default: timestamp
  sortOrder?: 'asc' | 'desc';              // Default: desc
}
```

**Response**:
```json
{
  "events": [
    {
      "id": "evt_123456",
      "timestamp": "2024-01-15T14:32:15Z",
      "user": "admin",
      "eventType": "LOGIN_SUCCESS",
      "status": "SUCCESS",
      "description": "User logged in successfully",
      "metadata": {
        "ip": "192.168.1.100",
        "userAgent": "Chrome/120.0",
        "sessionId": "abc123def456",
        "location": "Munich, DE"
      },
      "payload": {
        "method": "POST",
        "endpoint": "/api/v1/auth/login",
        "duration": 245
      }
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 2847,
    "pages": 57
  },
  "filters": {
    "applied": ["search", "timeRange"],
    "availableUsers": ["admin", "user1", "system"],
    "availableTypes": ["LOGIN", "CONFIG_CHANGE", "ESP_CREATE"]
  }
}
```

#### **POST /api/v1/audit/search**
**Zweck**: Erweiterte Volltext-Suche mit Facetten

**Request Body**:
```json
{
  "query": "MQTT broker",
  "filters": {
    "timeRange": {
      "start": "2024-01-01T00:00:00Z",
      "end": "2024-01-31T23:59:59Z"
    },
    "users": ["admin"],
    "eventTypes": ["CONFIG_CHANGE"]
  },
  "facets": ["user", "eventType", "status"],
  "highlight": true
}
```

**Response mit Facetten**:
```json
{
  "results": [...],
  "facets": {
    "user": [
      {"value": "admin", "count": 1250},
      {"value": "user1", "count": 543},
      {"value": "system", "count": 210}
    ],
    "eventType": [
      {"value": "CONFIG_CHANGE", "count": 892},
      {"value": "LOGIN_SUCCESS", "count": 654}
    ],
    "status": [
      {"value": "SUCCESS", "count": 1800},
      {"value": "WARNING", "count": 203}
    ]
  },
  "highlighted": true
}
```

### **Export API**

#### **GET /api/v1/audit/export**
**Zweck**: Gefilterte Events als Datei exportieren

**Query Parameters**:
```typescript
interface ExportParams extends AuditQueryParams {
  format: 'csv' | 'json' | 'pdf';
  includePayload?: boolean;    // Default: false (nur für JSON)
  compress?: boolean;          // ZIP-Komprimierung
  filename?: string;           // Custom Dateiname
}
```

**CSV Format Beispiel**:
```csv
timestamp,user,event_type,status,description,ip,user_agent
2024-01-15T14:32:15Z,admin,LOGIN_SUCCESS,SUCCESS,"User logged in successfully",192.168.1.100,"Chrome/120.0"
2024-01-15T14:35:22Z,admin,CONFIG_CHANGE,WARNING,"MQTT broker changed",192.168.1.100,"Chrome/120.0"
```

### **Retention Management API**

#### **GET /api/v1/audit/retention**
**Zweck**: Aktuelle Retention-Einstellungen abrufen

**Response**:
```json
{
  "retentionDays": 365,
  "archiveDays": 730,
  "deleteDays": 1825,
  "autoCleanup": true,
  "storageUsed": "2.3GB",
  "storageLimit": "10GB",
  "lastCleanup": "2024-01-10T03:00:00Z"
}
```

#### **PUT /api/v1/audit/retention**
**Zweck**: Retention-Policies aktualisieren

**Request Body**:
```json
{
  "retentionDays": 365,
  "archiveDays": 730,
  "deleteDays": 1825,
  "autoCleanup": true
}
```

### **Event Categories & Types**

```typescript
enum EventCategory {
  SECURITY = 'SECURITY',
  CONFIGURATION = 'CONFIGURATION',
  ESP_MANAGEMENT = 'ESP_MANAGEMENT',
  USER_MANAGEMENT = 'USER_MANAGEMENT',
  API_ACCESS = 'API_ACCESS',
  SYSTEM = 'SYSTEM'
}

const EVENT_TYPES = {
  // Security Events
  LOGIN_SUCCESS: { category: 'SECURITY', icon: '🔐', severity: 'INFO' },
  LOGIN_FAILED: { category: 'SECURITY', icon: '🔒', severity: 'WARNING' },
  LOGOUT: { category: 'SECURITY', icon: '🚪', severity: 'INFO' },
  PASSWORD_CHANGE: { category: 'SECURITY', icon: '🔑', severity: 'INFO' },

  // Configuration Events
  CONFIG_CHANGE: { category: 'CONFIGURATION', icon: '⚙️', severity: 'WARNING' },
  SETTINGS_UPDATE: { category: 'CONFIGURATION', icon: '🔧', severity: 'INFO' },

  // ESP Management Events
  ESP_CREATE: { category: 'ESP_MANAGEMENT', icon: '📱', severity: 'INFO' },
  ESP_UPDATE: { category: 'ESP_MANAGEMENT', icon: '📱', severity: 'INFO' },
  ESP_DELETE: { category: 'ESP_MANAGEMENT', icon: '📱', severity: 'WARNING' },
  ESP_COMMAND: { category: 'ESP_MANAGEMENT', icon: '📡', severity: 'INFO' },

  // User Management Events
  USER_CREATE: { category: 'USER_MANAGEMENT', icon: '👤', severity: 'INFO' },
  USER_UPDATE: { category: 'USER_MANAGEMENT', icon: '👤', severity: 'INFO' },
  USER_DELETE: { category: 'USER_MANAGEMENT', icon: '👤', severity: 'WARNING' },

  // API Access Events
  API_CALL: { category: 'API_ACCESS', icon: '🌐', severity: 'INFO' },
  API_ERROR: { category: 'API_ACCESS', icon: '❌', severity: 'ERROR' },

  // System Events
  BACKUP_STARTED: { category: 'SYSTEM', icon: '💾', severity: 'INFO' },
  BACKUP_COMPLETED: { category: 'SYSTEM', icon: '✅', severity: 'INFO' },
  MAINTENANCE_MODE: { category: 'SYSTEM', icon: '🔧', severity: 'WARNING' },
  SYSTEM_ERROR: { category: 'SYSTEM', icon: '🚨', severity: 'ERROR' }
};
```

---

## 🛡️ Sektion 5: Compliance & Monitoring

### **Compliance Features**

#### **Audit Trail Standards**
- **SOX Compliance**: Finanzielle Transaktionen nachverfolgen
- **GDPR Compliance**: User-Daten-Zugriffe loggen
- **ISO 27001**: Security-Events dokumentieren
- **Data Retention**: Konfigurierbare Aufbewahrungsfristen

#### **Event Categories für Compliance**
- **Security Events**: Alle Authentifizierungs-Versuche
- **Data Access**: Lese-/Schreib-Zugriffe auf sensible Daten
- **Configuration Changes**: System-Änderungen mit Impact-Assessment
- **User Management**: Account-Änderungen und Berechtigungen

### **Security Monitoring**

#### **Automated Alerts**
```typescript
interface AlertRule {
  id: string;
  name: string;
  condition: {
    eventType?: string[];
    user?: string[];
    status?: string[];
    threshold?: number;  // Events pro Zeitfenster
    timeWindow?: number; // Minuten
  };
  actions: {
    email?: string[];
    webhook?: string;
    severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  };
  enabled: boolean;
}

// Beispiel Alert Rules
const alertRules = [
  {
    name: "Failed Login Attempts",
    condition: {
      eventType: ["LOGIN_FAILED"],
      threshold: 5,
      timeWindow: 15
    },
    actions: {
      severity: "HIGH",
      email: ["security@company.com"]
    }
  },
  {
    name: "Configuration Changes",
    condition: {
      eventType: ["CONFIG_CHANGE"],
      status: ["WARNING"]
    },
    actions: {
      severity: "MEDIUM",
      webhook: "https://slack-webhook.com/alerts"
    }
  }
];
```

#### **Real-time Monitoring Dashboard**
- **Live Event Stream**: WebSocket-Verbindung für Echtzeit-Updates
- **Alert Panel**: Aktive Warnungen und deren Status
- **Metrics Dashboard**: Event-Statistiken und Trends
- **User Activity Map**: Geografische Verteilung der Zugriffe

### **Data Retention & Archiving**

#### **Retention Policies**
```typescript
interface RetentionPolicy {
  activeRetentionDays: number;    // Aktive Events (Default: 365)
  archiveRetentionDays: number;   // Archivierte Events (Default: 730)
  compressionEnabled: boolean;    // Archiv-Komprimierung
  encryptionEnabled: boolean;     // Archiv-Verschlüsselung
  backupEnabled: boolean;         // Regelmäßige Backups
}
```

#### **Auto-Cleanup Process**
1. **Daily Check**: Events älter als `activeRetentionDays` identifizieren
2. **Archiving**: Events in Archiv-Storage verschieben
3. **Compression**: Archiv-Dateien komprimieren
4. **Encryption**: Sensible Daten verschlüsseln
5. **Cleanup**: Events älter als `deleteRetentionDays` löschen
6. **Logging**: Cleanup-Aktivitäten selbst audit-loggen

### **Reporting & Analytics**

#### **Compliance Reports**
- **User Access Report**: Alle Zugriffe eines Users
- **Security Incident Report**: Verdächtige Aktivitäten
- **Configuration Change Report**: System-Änderungen
- **Data Access Report**: Zugriffe auf sensible Daten

#### **Analytics Features**
- **Event Trends**: Zeitliche Entwicklung der Event-Types
- **User Behavior**: Häufigste Aktivitäten pro User
- **System Health**: Error-Rates und Performance-Metriken
- **Compliance Metrics**: Abdeckung der Audit-Anforderungen

---

## 🎨 Design-Spezifikationen

### **Color Scheme**
```css
/* Status Colors */
.audit-success { color: #28a745; }    /* Grün für Success */
.audit-warning { color: #ffc107; }    /* Gelb für Warning */
.audit-error { color: #dc3545; }      /* Rot für Error */
.audit-info { color: #17a2b8; }       /* Blau für Info */

/* Event Type Colors */
.security-event { border-left: 4px solid #dc3545; }
.config-event { border-left: 4px solid #ffc107; }
.esp-event { border-left: 4px solid #28a745; }
.user-event { border-left: 4px solid #17a2b8; }
.api-event { border-left: 4px solid #6c757d; }
.system-event { border-left: 4px solid #343a40; }
```

### **Icons & Visual Elements**
- **Event-Type Icons**: 🔐 Security, ⚙️ Config, 📱 ESP, 👤 User, 🌐 API, 🔧 System
- **Status Icons**: ✅ Success, ⚠️ Warning, ❌ Failed, 🔄 Pending
- **Action Icons**: 🔍 Search, 📅 Calendar, 💾 Export, ⟲ Refresh
- **Navigation Icons**: ‹‹ First, ‹ Previous, › Next, ›› Last

### **Timeline Design**
```css
.audit-timeline {
  position: relative;
  padding-left: 30px;
}

.audit-timeline::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #dee2e6;
}

.audit-event {
  position: relative;
  margin-bottom: 20px;
}

.audit-event::before {
  content: '';
  position: absolute;
  left: -22px;
  top: 8px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #007bff;
  border: 2px solid #fff;
}
```

### **Search Highlighting**
```css
.search-highlight {
  background-color: #fff3cd;
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: 600;
  animation: highlight-pulse 2s ease-in-out;
}

@keyframes highlight-pulse {
  0% { background-color: #fff3cd; }
  50% { background-color: #ffeaa7; }
  100% { background-color: #fff3cd; }
}
```

---

## 🔧 Technische Details

### **Frontend Architecture**

#### **React Components Structure**
```
src/components/audit/
├── AuditLogView.tsx          # Haupt-Container
├── AuditFilters.tsx          # Filter-Panel
├── AuditTimeline.tsx         # Event-Liste
├── AuditEvent.tsx            # Einzelnes Event
├── AuditPagination.tsx       # Paginierung
├── AuditExport.tsx           # Export-Funktionalität
└── AuditRetention.tsx        # Retention-Einstellungen
```

#### **State Management**
```typescript
interface AuditState {
  events: AuditEvent[];
  filters: AuditFilters;
  pagination: PaginationState;
  loading: boolean;
  searchQuery: string;
  selectedEvent?: AuditEvent;
  exportProgress?: number;
}

// Redux Slice oder Context für globale State-Verwaltung
const auditSlice = createSlice({
  name: 'audit',
  initialState,
  reducers: {
    setFilters: (state, action) => { /* ... */ },
    setEvents: (state, action) => { /* ... */ },
    setLoading: (state, action) => { /* ... */ },
    // ...
  }
});
```

### **Backend Services**

#### **Audit Service**
```typescript
class AuditService {
  async logEvent(event: AuditEventInput): Promise<void> {
    // Event in Datenbank speichern
    // Index für Suche aktualisieren
    // Real-time Notifications senden
  }

  async queryEvents(query: AuditQuery): Promise<AuditResult> {
    // Filter anwenden
    // Pagination implementieren
    // Such-Index verwenden
  }

  async exportEvents(query: AuditQuery, format: ExportFormat): Promise<Blob> {
    // Events formatieren
    // Datei generieren
    // Komprimierung anwenden
  }
}
```

#### **Search Engine Integration**
- **Elasticsearch/OpenSearch**: Für Volltext-Suche und Facetten
- **Index-Struktur**: Events mit Metadaten und Payload
- **Query-Optimierung**: Filter vor Suche anwenden
- **Performance**: Cached Queries für häufige Suchen

#### **Retention Manager**
```typescript
class RetentionManager {
  async cleanupOldEvents(): Promise<void> {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - this.retentionDays);

    // Events identifizieren
    const oldEvents = await this.findOldEvents(cutoffDate);

    // Archivieren
    await this.archiveEvents(oldEvents);

    // Löschen
    await this.deleteEvents(oldEvents);
  }

  private async archiveEvents(events: AuditEvent[]): Promise<void> {
    // Komprimierung
    // Verschlüsselung
    // Archiv-Storage
  }
}
```

#### **Export Handler**
```typescript
class ExportHandler {
  async generateCSV(events: AuditEvent[]): Promise<string> {
    const headers = ['timestamp', 'user', 'event_type', 'status', 'description'];
    const rows = events.map(event => [
      event.timestamp.toISOString(),
      event.user,
      event.eventType,
      event.status,
      event.description
    ]);

    return [headers, ...rows]
      .map(row => row.map(field => `"${field}"`).join(','))
      .join('\n');
  }

  async generatePDF(events: AuditEvent[]): Promise<Buffer> {
    // PDF-Dokument erstellen
    // Tabellen formatieren
    // Compliance-Header hinzufügen
  }
}
```

### **Performance Optimierungen**

#### **Frontend Optimizations**
- **Virtual Scrolling**: Für große Event-Listen (>1000 Events)
- **Lazy Loading**: Event-Details nur bei Bedarf laden
- **Debounced Search**: 300ms Delay für Such-Queries
- **Pagination Caching**: Bereits geladene Seiten cachen

#### **Backend Optimizations**
- **Database Indexing**: Composite Indizes für häufige Filter-Kombinationen
- **Query Caching**: Redis für häufige Such-Queries
- **Async Processing**: Export-Jobs in Background verarbeiten
- **Rate Limiting**: API-Calls limitieren (100/min pro User)

#### **Real-time Features**
- **WebSocket Connection**: Für Live-Updates
- **Server-Sent Events**: Als Fallback für WebSockets
- **Polling**: Als letzter Fallback (alle 30 Sekunden)

---

## 📊 Monitoring & Analytics

### **System Health Metrics**
- **Event Ingestion Rate**: Events pro Sekunde
- **Search Performance**: Query-Response-Zeiten
- **Storage Usage**: Datenbank-Größe und Wachstum
- **API Response Times**: Durchschnittliche Antwortzeiten

### **User Analytics**
- **Most Active Users**: Top-User nach Event-Count
- **Common Event Types**: Häufigste Aktivitäten
- **Peak Usage Times**: Zeitliche Verteilung der Aktivitäten
- **Geographic Distribution**: Zugriffe nach Standort

### **Compliance Metrics**
- **Audit Coverage**: Prozentsatz abgedeckter Compliance-Anforderungen
- **Retention Compliance**: Einhaltung der Aufbewahrungsfristen
- **Security Incidents**: Anzahl erkannter Sicherheitsvorfälle
- **Report Generation**: Häufigkeit der Compliance-Reports

---

## 🚀 Implementierungs-Guide

### **Phase 1: Core Infrastructure**
1. **Audit Service Setup**: Event-Erfassung implementieren
2. **Database Schema**: Audit-Event-Tabelle erstellen
3. **Basic API**: CRUD-Operationen für Events
4. **Frontend Shell**: Grundlegende UI-Struktur

### **Phase 2: Core Features**
1. **Event Timeline**: Basis-Event-Anzeige
2. **Basic Filters**: User, Type, Time-Range Filter
3. **Search Functionality**: Volltext-Suche implementieren
4. **Pagination**: Serverseitige Paginierung

### **Phase 3: Advanced Features**
1. **Real-time Updates**: WebSocket-Integration
2. **Export Functionality**: CSV/JSON/PDF Export
3. **Advanced Search**: Facetten und Filter-Kombinationen
4. **Retention Management**: Cleanup-Policies

### **Phase 4: Compliance & Security**
1. **Security Monitoring**: Alert-System implementieren
2. **Compliance Reports**: PDF-Report-Generierung
3. **Data Encryption**: Sensible Daten verschlüsseln
4. **Access Controls**: Rollenbasierte Zugriffsrechte

### **Phase 5: Optimization & Monitoring**
1. **Performance Tuning**: Caching und Indizes optimieren
2. **Monitoring Dashboard**: System-Metriken hinzufügen
3. **Analytics**: User-Behavior-Analytics
4. **Documentation**: Vollständige API-Dokumentation

---

**Diese Dokumentation bietet alle notwendigen Informationen, um ein vollständiges, skalierbares Audit-Logging-System zu implementieren. Der Fokus liegt auf Compliance, Security und Benutzerfreundlichkeit.**
