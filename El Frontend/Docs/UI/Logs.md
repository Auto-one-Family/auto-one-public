# 📋 Server Logs - Vollständige UI-Dokumentation

## 🎯 LogViewerView (`/logs`) - Komplettes Log-Monitoring System

Diese Dokumentation beschreibt das vollständige Log-Monitoring-System, das es Benutzern ermöglicht, Server-Logs in Echtzeit zu überwachen, zu filtern, zu durchsuchen und für Troubleshooting zu analysieren.

---

## 📋 Sektion 1: Übersicht

### Route & Navigation
- **URL**: `/logs`
- **Zugriff**: Verfügbar für alle authentifizierten Benutzer mit Leseberechtigung
- **Breadcrumb**: Dashboard > Monitoring > Server Logs

### Zweck & Funktionalität
Das Log-Monitoring-System dient der **Echtzeit-Überwachung** von Server-Logs mit folgenden Hauptfunktionen:
- **Live-Streaming**: Kontinuierliche Anzeige neuer Log-Einträge
- **Historische Analyse**: Zugriff auf vergangene Logs mit Zeitfiltern
- **Troubleshooting**: Detaillierte Fehleranalyse mit Stack-Traces
- **System-Monitoring**: Überwachung der Systemgesundheit durch Log-Patterns
- **Audit-Trail**: Nachverfolgung wichtiger Systemereignisse

### Unterstützte Log-Types
Das System verarbeitet fünf Log-Level mit unterschiedlichen Prioritäten:

| Level | Priorität | Beschreibung | Verwendung |
|-------|-----------|-------------|------------|
| **ERROR** | 1 (Höchste) | Kritische Fehler, Systemausfälle | Sofortige Aufmerksamkeit erforderlich |
| **WARN** | 2 | Warnungen, potenzielle Probleme | Überwachung empfohlen |
| **INFO** | 3 | Allgemeine Informationen | Normale Betriebsmeldungen |
| **DEBUG** | 4 | Detaillierte Debug-Informationen | Entwicklung und Fehlerbehebung |
| **TRACE** | 5 (Niedrigste) | Sehr detaillierte Tracing-Infos | Nur bei spezifischen Analysen |

### Log-Quellen
- **ESP Devices**: ESP_01, ESP_02, ESP_03, etc.
- **SYSTEM**: Server-interne Prozesse
- **API**: REST-API Aufrufe und Responses
- **MQTT**: Message Queue Kommunikation
- **DATABASE**: Datenbankoperationen
- **AUTH**: Authentifizierungsereignisse

---

## 📋 Sektion 2: UI-Komponenten detailliert

### Hauptlayout-Struktur

```ascii
┌─────────────────────────────────────────────────────────┐
│                    LogViewerView                        │
├─────────────────────────────────────────────────────────┤
│ [🔄 Auto-Scroll] [⏸️ Pause] [🗑️ Clear] [💾 Export] [🔍] │ ← Toolbar
├─────────────────────────────────────────────────────────┤
│ Filter: [ERROR ✓] [WARN ✓] [Time: Last 1h] [Search: ""] │ ← Filter Panel
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 🕒 14:32:15 │ ERROR │ ESP_01 │ Connection timeout      │
│             │       │        │ ▼ Stack trace expand    │ ← Log Entry (Expandable)
│             │       │        │   at connect() line 45   │
│             │       │        │   at ESPComm.send()      │
│             │       │        │   Error: Timeout 5s      │
│                                                         │
│ 🕒 14:32:16 │ WARN  │ SYSTEM │ High memory usage       │
│ 🕒 14:32:17 │ INFO  │ API    │ User login: admin       │
│ 🕒 14:32:18 │ DEBUG │ MQTT   │ Message received: {...} │
│                                                         │
│ 🕒 14:32:19 │ INFO  │ API    │ GET /api/v1/sensors     │
│ 🕒 14:32:20 │ ERROR │ ESP_02 │ Sensor read failure     │
│             │       │        │ ▼ Stack trace expand    │
│             │       │        │   at readSensor()        │
│             │       │        │   TypeError: null ref    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.1 Toolbar-Komponenten

#### Auto-Scroll Toggle (`🔄`)
- **Status**: Ein/Aus (Default: Ein)
- **Funktion**: Automatisches Scrollen zu neuen Log-Einträgen
- **Visual Feedback**:
  - Aktiv: Grüne Farbe, animiertes Icon
  - Inaktiv: Graue Farbe, statisches Icon
- **Verhalten**: Bei Deaktivierung zeigt ein "New Logs" Badge die Anzahl ungelesener Einträge

#### Pause Button (`⏸️`)
- **Status**: Live/Pause (Default: Live)
- **Funktion**: Anhalten des Live-Streams für detaillierte Analyse
- **Visual Feedback**: Rote Farbe wenn aktiv
- **Verhalten**: Buffer hält bis zu 1000 Einträge während Pause

#### Clear Button (`🗑️`)
- **Funktion**: Leeren des aktuellen Log-Displays
- **Bestätigung**: Modal-Dialog: "Alle angezeigten Logs löschen?"
- **Scope**: Nur lokale Anzeige, historische Daten bleiben erhalten

#### Export Button (`💾`)
- **Funktion**: Export der gefilterten Logs
- **Formate**: TXT, JSON, CSV
- **Scope**: Nur aktuell gefilterte und angezeigte Logs
- **Dateiname**: `logs_export_YYYY-MM-DD_HH-MM-SS.format`

#### Search Toggle (`🔍`)
- **Funktion**: Ein-/Ausblenden der erweiterten Suchleiste
- **Zusätzliche Filter**: Regex-Suche, Case-Sensitive, Whole Word

### 2.2 Filter Panel

#### Log-Level Filter
- **Typ**: Multi-Select Checkboxen
- **Optionen**: ERROR, WARN, INFO, DEBUG, TRACE
- **Default**: ERROR, WARN, INFO (DEBUG/TRACE ausgeblendet)
- **Verhalten**: Sofortige Anwendung ohne zusätzlichen "Apply" Button

#### Time-Range Picker
- **Typ**: Preset + Custom Range
- **Presets**:
  - Last 5 minutes
  - Last 15 minutes
  - Last 1 hour
  - Last 6 hours
  - Last 24 hours
  - Last 7 days
  - Custom Range (Date Picker)
- **Format**: ISO 8601 (`2024-01-15T14:30:00Z`)
- **Verhalten**: Bei Änderung werden historische Logs nachgeladen

#### Search Field
- **Typ**: Debounced Input (300ms delay)
- **Features**:
  - Volltext-Suche in allen Log-Feldern
  - Real-time Highlighting (gelbe Markierung)
  - Case-insensitive (Default)
  - Regex-Unterstützung (erweitert)
- **Placeholder**: "Search logs... (supports regex: /error.*/i)"

### 2.3 Log Entry Display

#### Log Entry Format
```
[TIMESTAMP] [LEVEL] [SOURCE] [MESSAGE]
    [EXPANDABLE DETAILS]
```

#### Expandable Details
- **Stack Traces**: Bei ERROR/WARN automatisch verfügbar
- **JSON Payloads**: Bei API/MQTT Messages formatierte Anzeige
- **Performance Data**: Memory, CPU, Network Stats
- **Context Information**: User ID, Session ID, Request ID

#### Virtual Scrolling
- **Performance**: Unterstützt 100.000+ Einträge
- **Buffer Size**: 100 Einträge über/under viewport
- **Memory Management**: Alte Einträge werden bei Überschreitung entfernt

---

## 📋 Sektion 3: Log-Monitoring Interaktionen

### 3.1 Live-Streaming Workflows

#### Normaler Live-Modus
1. **WebSocket Connection**: Automatische Verbindung beim Laden der Seite
2. **Auto-Scroll**: Neue Einträge erscheinen am Ende, View scrollt automatisch
3. **Filter Application**: Alle Filter werden in Echtzeit auf neue Einträge angewendet
4. **Buffer Management**: Bei hoher Frequenz werden Einträge gepuffert

#### Pause-Modus
1. **Stream Stop**: WebSocket-Daten werden gepuffert
2. **Visual Indicator**: "⏸️ PAUSED - X new logs" Badge
3. **Resume**: Klick auf Badge lädt alle gepufferten Einträge
4. **Filter Reset**: Bei Resume werden aktuelle Filter angewendet

### 3.2 Filter-Interaktionen

#### Log-Level Filtering
```javascript
// Sofortige Filter-Anwendung
const activeLevels = ['ERROR', 'WARN', 'INFO'];
const filteredLogs = logs.filter(log => activeLevels.includes(log.level));
```

- **Performance**: Clientseitige Filterung für Live-Stream
- **Server Sync**: Filter-State wird an Server gesendet für optimierte Streams
- **Persistence**: Filter-Einstellungen werden in localStorage gespeichert

#### Time-Range Selection
1. **Preset Selection**: Sofortige Anwendung
2. **Custom Range**: Date-Picker Dialog
3. **Historical Load**: REST-API Call für vergangene Logs
4. **Pagination**: Automatisches Nachladen bei Scroll nach oben

#### Search Interactions
- **Debounced Input**: 300ms Verzögerung für optimale Performance
- **Highlighting**: `<mark class="search-highlight">` für Suchtreffer
- **Regex Support**: Vollständige JavaScript Regex-Syntax
- **Search History**: Letzte 10 Suchbegriffe gespeichert

### 3.3 Detail-Analyse Features

#### Stack-Trace Expansion
- **Trigger**: Klick auf Chevron-Down Icon
- **Animation**: Smooth expand/collapse (200ms)
- **Syntax Highlighting**: Verschiedene Sprachen unterstützt
- **Copy to Clipboard**: Ein-Klick Kopieren der kompletten Trace

#### Log Entry Context Menu
- **Right-Click Options**:
  - Copy Log Entry
  - Copy Timestamp
  - Copy Message Only
  - Filter by this Source
  - Filter by this Level
  - Search for similar errors

#### Export Workflows
1. **Format Selection**: Dropdown mit verfügbaren Formaten
2. **Scope Confirmation**: "Export X logs?" Dialog
3. **Progress Indicator**: Bei großen Exports
4. **Download**: Automatischer Download mit timestamped filename

---

## 📋 Sektion 4: Server-Integration

### 4.1 WebSocket Live-Streaming

#### Connection Details
```javascript
// WebSocket Endpoint
const wsUrl = `ws://${server}/ws/logs`;

// Connection Parameters
const params = {
  levels: ['ERROR', 'WARN', 'INFO'],
  source_filter: null,
  search_filter: null
};
```

#### Message Format
```json
{
  "type": "log_entry",
  "timestamp": "2024-01-15T14:32:15.123Z",
  "level": "ERROR",
  "source": "ESP_01",
  "message": "Connection timeout after 5000ms",
  "details": {
    "stack_trace": "...",
    "context": {
      "user_id": "admin",
      "request_id": "req_123"
    }
  }
}
```

#### Connection Management
- **Auto-Reconnect**: Bei Verbindungsverlust alle 5 Sekunden retry
- **Heartbeat**: Ping/Pong alle 30 Sekunden
- **Buffer Size**: Serverseitige Queue von 1000 Einträgen
- **Rate Limiting**: Max 100 Einträge/Sekunde pro Client

### 4.2 REST API für historische Daten

#### Endpoint: `GET /api/v1/debug/logs`
```http
GET /api/v1/debug/logs?start=2024-01-15T10:00:00Z&end=2024-01-15T14:00:00Z&levels=ERROR,WARN&search=timeout&limit=1000&offset=0
```

#### Query Parameters
| Parameter | Typ | Beschreibung | Beispiel |
|-----------|-----|-------------|----------|
| `start` | ISO8601 | Start-Zeitpunkt | `2024-01-15T10:00:00Z` |
| `end` | ISO8601 | End-Zeitpunkt | `2024-01-15T14:00:00Z` |
| `levels` | CSV | Log-Level Filter | `ERROR,WARN,INFO` |
| `source` | String | Source Filter | `ESP_01` |
| `search` | String | Volltext-Suche | `connection timeout` |
| `limit` | Number | Max Einträge | `1000` |
| `offset` | Number | Pagination Offset | `0` |

#### Response Format
```json
{
  "logs": [
    {
      "id": "log_12345",
      "timestamp": "2024-01-15T14:32:15.123Z",
      "level": "ERROR",
      "source": "ESP_01",
      "message": "Connection timeout after 5000ms",
      "details": { ... }
    }
  ],
  "pagination": {
    "total": 15432,
    "limit": 1000,
    "offset": 0,
    "has_more": true
  },
  "filters_applied": {
    "levels": ["ERROR", "WARN"],
    "time_range": "2024-01-15T10:00:00Z - 2024-01-15T14:00:00Z"
  }
}
```

### 4.3 Filter-Parameter Synchronisation

#### Client → Server Filter Updates
```javascript
// Bei Filter-Änderung
websocket.send(JSON.stringify({
  type: 'update_filters',
  filters: {
    levels: activeLevels,
    search: searchQuery,
    source_filter: selectedSource
  }
}));
```

#### Server → Client Filter Confirmation
```json
{
  "type": "filters_updated",
  "active_filters": {
    "levels": ["ERROR", "WARN", "INFO"],
    "search": "connection",
    "source_filter": null
  },
  "affected_log_count": 1234
}
```

### 4.4 Buffering & Performance

#### Serverseitiges Buffering
- **Ring Buffer**: 10.000 Einträge für jeden Log-Level
- **Memory Management**: LRU-Eviction bei Überschreitung
- **Persistence**: Wichtige Logs (ERROR) werden dauerhaft gespeichert
- **Compression**: Automatische Kompression alter Einträge

#### Clientseitiges Buffering
- **Live Buffer**: 500 Einträge für sofortige Anzeige
- **History Buffer**: 5000 Einträge für Scrolling
- **Virtual Scrolling**: Nur sichtbare + Buffer-Elemente im DOM
- **Memory Cleanup**: Automatische Garbage Collection

---

## 📋 Sektion 5: Advanced Features

### 5.1 Log-Analysis & Pattern-Erkennung

#### Häufige Issues Pattern
```javascript
const patterns = {
  connection_timeout: /Connection timeout after \d+ms/,
  memory_warning: /High memory usage: \d+%/,
  auth_failure: /Authentication failed for user/,
  sensor_error: /Sensor read failure on \w+/
};
```

#### Real-time Analytics
- **Error Rate Monitoring**: Fehler pro Minute/Stunde
- **Source Health Score**: Prozentuale Erfolgsrate pro ESP
- **Performance Trends**: Memory/CPU Trends über Zeit
- **Anomaly Detection**: Abweichungen von Normalverhalten

#### Alert Conditions
- **Threshold Alerts**: "Mehr als 10 ERROR in 5 Minuten"
- **Pattern Alerts**: "Connection timeout detected"
- **Source Alerts**: "ESP_01 nicht erreichbar seit 5 Minuten"

### 5.2 Alert-Setup & Notifications

#### Alert-Konfiguration
```json
{
  "alert_id": "connection_timeout_alert",
  "name": "Connection Timeouts",
  "condition": {
    "pattern": "Connection timeout after",
    "threshold": 5,
    "time_window": "300000" // 5 minutes in ms
  },
  "notification": {
    "channels": ["email", "websocket"],
    "recipients": ["admin@example.com"],
    "message": "Mehrere Connection Timeouts detected"
  },
  "cooldown": "600000" // 10 minutes
}
```

#### Notification Types
- **Browser Notifications**: System-native Notifications API
- **Email Alerts**: SMTP-basierte Benachrichtigungen
- **WebSocket Push**: Real-time Alerts im Browser
- **SMS**: Über externe SMS-Gateway (Premium Feature)

### 5.3 Log-Rotation & Archivierung

#### Rotation Strategy
- **Size-based**: Neue Datei bei 100MB
- **Time-based**: Tägliche Rotation um 00:00 UTC
- **Level-based**: ERROR Logs werden länger aufbewahrt

#### Archivierung
- **Compression**: gzip-Kompression für alte Logs
- **Retention Policy**:
  - ERROR/WARN: 90 Tage
  - INFO: 30 Tage
  - DEBUG/TRACE: 7 Tage
- **Cloud Storage**: Automatische Archivierung in S3/Azure Blob

### 5.4 Performance & Monitoring

#### Throughput Metrics
- **Ingestion Rate**: Logs/Sekunde (Max: 1000)
- **Query Performance**: <100ms für typische Queries
- **Memory Usage**: <200MB für 100k Logs
- **Network Usage**: <50KB/s pro Client bei Live-Stream

#### System Health Checks
```json
{
  "websocket_connections": 15,
  "active_clients": 8,
  "buffer_usage_percent": 45,
  "error_rate_per_minute": 2.3,
  "average_query_time_ms": 87,
  "memory_usage_mb": 156
}
```

---

## 🎨 Design-Spezifikationen

### Color Scheme & Visual Hierarchy

#### Log-Level Colors
```css
.log-entry {
  &.error { background: #fee; border-left: 4px solid #e74c3c; color: #c0392b; }
  &.warn  { background: #fff8e1; border-left: 4px solid #f39c12; color: #e67e22; }
  &.info  { background: #e8f4fd; border-left: 4px solid #3498db; color: #2980b9; }
  &.debug { background: #f8f9fa; border-left: 4px solid #95a5a6; color: #7f8c8d; }
  &.trace { background: #fafafa; border-left: 4px solid #bdc3c7; color: #34495e; }
}
```

#### UI Element Colors
- **Primary Actions**: `#007bff` (Bootstrap Primary)
- **Danger Actions**: `#dc3545` (Error Red)
- **Success States**: `#28a745` (Green)
- **Warning States**: `#ffc107` (Amber)
- **Neutral/Disabled**: `#6c757d` (Gray)

### Typography & Spacing

#### Font Hierarchy
```css
.log-timestamp { font-family: 'Monaco', monospace; font-size: 12px; font-weight: 500; }
.log-level     { font-family: 'Monaco', monospace; font-size: 11px; font-weight: bold; }
.log-source    { font-family: 'Monaco', monospace; font-size: 12px; font-weight: 600; }
.log-message   { font-family: 'Inter', sans-serif; font-size: 14px; line-height: 1.4; }
```

#### Spacing System
- **Log Entry Padding**: 12px vertical, 16px horizontal
- **Toolbar Spacing**: 8px between elements
- **Filter Panel**: 16px padding, 12px element spacing
- **Expandable Details**: 24px left margin, 8px line spacing

### Timestamps & Formatting

#### ISO-Format mit Millisekunden
```javascript
// Format: 2024-01-15T14:32:15.123Z
const timestamp = new Date().toISOString();

// Display Format für UI
const displayFormat = {
  short: '14:32:15',     // Innerhalb gleicher Stunde
  medium: 'Jan 15 14:32', // Innerhalb gleichen Tages
  long: '2024-01-15 14:32:15.123' // Andere Tage
};
```

#### Search Highlighting
```css
.search-highlight {
  background-color: #fff3cd;
  border-radius: 2px;
  padding: 1px 2px;
  font-weight: 600;
  box-shadow: 0 0 0 1px #ffeaa7;
}
```

### Auto-Scroll Indicator

#### Visual Feedback
```css
.auto-scroll-indicator {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: #007bff;
  color: white;
  padding: 8px 16px;
  border-radius: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  animation: pulse 2s infinite;
}

.auto-scroll-indicator::before {
  content: "⬇";
  margin-right: 8px;
}

@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}
```

---

## 🔧 Technische Details

### Frontend Architecture

#### Vue.js Component Structure
```
LogViewerView.vue
├── components/
│   ├── LogToolbar.vue
│   ├── LogFilters.vue
│   ├── LogEntry.vue
│   ├── LogDetails.vue
│   └── VirtualScroll.vue
├── composables/
│   ├── useWebSocket.js
│   ├── useLogFilters.js
│   └── useVirtualScroll.js
└── stores/
    └── logStore.js
```

#### State Management
```javascript
// Pinia Store für Logs
export const useLogStore = defineStore('logs', {
  state: () => ({
    logs: [],
    filters: {
      levels: ['ERROR', 'WARN', 'INFO'],
      timeRange: 'last_1h',
      search: '',
      source: null
    },
    connection: {
      status: 'connecting', // 'connected', 'disconnected', 'error'
      reconnectAttempts: 0
    }
  }),

  actions: {
    addLogEntry(entry) {
      this.logs.push(entry);
      this.applyFilters();
    },

    updateFilters(newFilters) {
      this.filters = { ...this.filters, ...newFilters };
      this.syncFiltersToServer();
    }
  }
});
```

### Log Parser & Processing

#### Structured Log Format
```javascript
class LogParser {
  static parse(rawLog) {
    const pattern = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s+(\w+)\s+(\w+)\s+(.+)$/;

    const match = rawLog.match(pattern);
    if (!match) return null;

    return {
      timestamp: new Date(match[1]),
      level: match[2].toUpperCase(),
      source: match[3],
      message: match[4],
      id: generateId(),
      expanded: false
    };
  }
}
```

#### JSON Payload Handling
```javascript
class JsonPayloadHandler {
  static extractJson(message) {
    const jsonMatch = message.match(/\{.*\}/s);
    if (jsonMatch) {
      try {
        return JSON.parse(jsonMatch[0]);
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  static formatJson(obj) {
    return JSON.stringify(obj, null, 2);
  }
}
```

### WebSocket Manager

#### Connection Lifecycle
```javascript
class WebSocketManager {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.reconnectDelay = 5000;
    this.maxReconnectAttempts = 10;
  }

  connect() {
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log('WebSocket connected');
      this.sendFilters();
      this.startHeartbeat();
    };

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };

    this.socket.onclose = () => {
      this.scheduleReconnect();
    };

    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  sendFilters() {
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'update_filters',
        filters: this.getCurrentFilters()
      }));
    }
  }
}
```

### Search Engine Implementation

#### Clientseitige Volltext-Suche
```javascript
class LogSearchEngine {
  constructor(logs) {
    this.logs = logs;
    this.index = this.buildIndex();
  }

  buildIndex() {
    return this.logs.map((log, index) => ({
      id: log.id,
      text: `${log.message} ${log.source} ${log.level}`,
      index: index
    }));
  }

  search(query, options = {}) {
    const { caseSensitive = false, regex = false } = options;

    let pattern;
    if (regex) {
      pattern = new RegExp(query, caseSensitive ? 'g' : 'gi');
    } else {
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      pattern = new RegExp(escaped, caseSensitive ? 'g' : 'gi');
    }

    return this.logs.filter(log => {
      const searchText = `${log.message} ${log.source}`;
      const matches = searchText.match(pattern);
      if (matches) {
        // Highlight matches
        log.highlightedMessage = this.highlightMatches(log.message, pattern);
        return true;
      }
      return false;
    });
  }

  highlightMatches(text, pattern) {
    return text.replace(pattern, '<mark class="search-highlight">$&</mark>');
  }
}
```

### Export Handler

#### Mehrere Export-Formate
```javascript
class LogExporter {
  static exportAsText(logs, filters) {
    const header = `Log Export - ${new Date().toISOString()}\nFilters: ${JSON.stringify(filters)}\n\n`;
    const content = logs.map(log =>
      `[${log.timestamp}] ${log.level} ${log.source} ${log.message}`
    ).join('\n');

    return header + content;
  }

  static exportAsJson(logs, filters) {
    return JSON.stringify({
      export_info: {
        timestamp: new Date().toISOString(),
        filters: filters,
        count: logs.length
      },
      logs: logs
    }, null, 2);
  }

  static exportAsCsv(logs, filters) {
    const headers = ['Timestamp', 'Level', 'Source', 'Message'];
    const rows = logs.map(log => [
      log.timestamp,
      log.level,
      log.source,
      log.message.replace(/"/g, '""') // Escape quotes
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(field => `"${field}"`).join(','))
      .join('\n');

    return csvContent;
  }
}
```

### Performance Optimizations

#### Virtual Scrolling Implementation
```javascript
class VirtualScroller {
  constructor(container, itemHeight = 40) {
    this.container = container;
    this.itemHeight = itemHeight;
    this.totalItems = 0;
    this.visibleItems = 50;
    this.bufferSize = 10;

    this.scrollTop = 0;
    this.container.addEventListener('scroll', this.onScroll.bind(this));
  }

  onScroll() {
    const scrollTop = this.container.scrollTop;
    const startIndex = Math.floor(scrollTop / this.itemHeight) - this.bufferSize;
    const endIndex = startIndex + this.visibleItems + (this.bufferSize * 2);

    this.renderItems(Math.max(0, startIndex), Math.min(this.totalItems, endIndex));
  }

  renderItems(start, end) {
    const items = this.getItems(start, end);
    this.container.innerHTML = items.map(item =>
      `<div style="height: ${this.itemHeight}px">${item.content}</div>`
    ).join('');
  }
}
```

#### Memory Management
```javascript
class LogMemoryManager {
  static MAX_LOGS = 100000;
  static CLEANUP_THRESHOLD = 80000;

  static manageMemory(logs) {
    if (logs.length > this.CLEANUP_THRESHOLD) {
      // Keep recent logs and important ones (ERROR)
      const recentLogs = logs.slice(-50000);
      const errorLogs = logs.filter(log => log.level === 'ERROR').slice(-10000);
      const uniqueErrors = [...new Set([...recentLogs, ...errorLogs])];

      return uniqueErrors.sort((a, b) => a.timestamp - b.timestamp);
    }

    return logs;
  }
}
```

---

**Diese Dokumentation ermöglicht es einem Entwickler, das komplette Log-Monitoring-System von Grund auf neu zu implementieren. Alle UI-Komponenten, Server-APIs, Datenformate und Performance-Aspekte sind detailliert spezifiziert.**
