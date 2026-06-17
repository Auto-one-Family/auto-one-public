# 📡 MQTT Live-Stream - Vollständige UI-Dokumentation

## 🎯 Übersicht

Die **MqttLogView** (`/mqtt-log`) ist eine Real-time Monitoring-Oberfläche für MQTT-Nachrichten, die Entwicklern und Administratoren ermöglicht, MQTT-Traffic live zu überwachen, zu debuggen und zu analysieren.

### **Zentrale Funktionen**
- **Real-time Streaming**: Live-Anzeige aller MQTT-Nachrichten
- **Erweiterte Filter**: Filtern nach Message-Type, ESP-ID und Topic
- **Performance-Monitoring**: Message-Rate und Connection-Status
- **Debugging-Tools**: Expandierbare Payloads für Detailanalyse
- **Pause/Resume**: Stream-Kontrolle für gezielte Analyse

### **Unterstützte Message-Types**
Die Anwendung unterstützt 9 verschiedene Message-Types:
- `sensor_data` - Sensordaten von ESP-Geräten
- `actuator_status` - Aktuator-Statusmeldungen
- `actuator_response` - Antworten auf Aktuator-Befehle
- `actuator_alert` - Aktuator-Warnungen/Alarme
- `esp_health` - ESP-Geräte-Health-Status
- `config_response` - Konfigurationsantworten
- `zone_assignment` - Zonen-Zuweisungen
- `logic_execution` - Logik-Engine-Ausführungen
- `system_event` - Systemweite Ereignisse

---

## 🔧 Technische Architektur

### **WebSocket Integration**
```typescript
// WebSocket URL Pattern
ws://localhost:8000/api/v1/ws/realtime/{client_id}?token={access_token}

// Message Format
interface WebSocketMessage {
  type: MessageType | string
  timestamp: number
  data: Record<string, unknown>
}

// Filter Interface
interface WebSocketFilters {
  types?: MessageType[]
  esp_ids?: string[]
  sensor_types?: string[]
  topicPattern?: string
}
```

### **Singleton Service Pattern**
Die Anwendung verwendet einen zentralen WebSocket-Service (Singleton), der:
- Verbindung automatisch verwaltet
- Mehrfach-Subscriptions unterstützt
- Rate-Limiting (10 Messages/Sekunde) implementiert
- Automatische Reconnection-Logic enthält

---

## 🎨 UI Layout & Design

### **Hauptlayout-Struktur**

```
┌─────────────────────────────────────────────────────────────┐
│ MQTT Message Log                           [● Connected]   │
│ Real-time message stream from WebSocket                    │
├─────────────────────────────────────────────────────────────┤
│ [▶️ Resume] [⏸️ Pause] [🔍 Filters] [🗑️ Clear]               │
├─────────────────────────────────────────────────────────────┤
│ ▼ Filters Panel (expandable)                               │
│ ├─ Message Types: [sensor_data ✓] [esp_health ✓] [...]     │
│ ├─ ESP ID: [ESP_12AB]                                      │
│ └─ Topic Contains: [kaiser/god]                            │
├─────────────────────────────────────────────────────────────┤
│ Showing 247 of 500 messages (max capacity)                 │
├─────────────────────────────────────────────────────────────┤
│ ▼ Message List (scrollable, max-height: 600px)            │
│ ├─ 14:32:15 │ ESP_01 │ sensor_data │ kaiser/god/esp/1     │
│ │   ▼ Payload: { "gpio": 12, "value": 23.5, "unit": "°C"} │
│ ├─ 14:32:16 │ ESP_02 │ actuator_status │ kaiser/god/esp/2 │
│ ├─ 14:32:17 │ SYSTEM │ system_event │ Connection lost     │
│ └─ 14:32:18 │ ESP_01 │ esp_health │ Online ✓              │
└─────────────────────────────────────────────────────────────┘
```

### **Responsive Design**
- **Desktop**: Vollständige Sidebar und Filter-Panel
- **Tablet**: Kompakte Filter-Darstellung
- **Mobile**: Vertikale Stapelung, reduzierte Controls

---

## 🎮 Interaktive Elemente

### **Control Panel**

#### **Pause/Resume Button**
```vue
<button @click="togglePause" class="btn-secondary">
  <Pause v-if="!isPaused" class="w-4 h-4 mr-2" />
  <Play v-else class="w-4 h-4 mr-2" />
  {{ isPaused ? 'Resume' : 'Pause' }}
</button>
```
- **Funktion**: Stoppt/Startet den Live-Stream
- **Use Case**: Analyse von Message-Patterns ohne Unterbrechung durch neue Nachrichten
- **State**: Persistiert während Session

#### **Clear Button**
```vue
<button @click="clearMessages" class="btn-secondary">
  <Trash2 class="w-4 h-4 mr-2" />
  Clear
</button>
```
- **Funktion**: Löscht alle Messages aus der Anzeige
- **Use Case**: Neue Analyse-Session starten
- **Warnung**: Unwiederuflich, keine Bestätigung erforderlich

#### **Filter Toggle**
```vue
<button @click="showFilters = !showFilters" class="btn-secondary">
  <Filter class="w-4 h-4 mr-2" />
  Filters
</button>
```
- **Funktion**: Zeigt/versteckt erweitertes Filter-Panel
- **Animation**: Smooth transition (200ms)
- **State**: Persistiert während Session

### **Filter Panel**

#### **Message Type Filter**
```vue
<div class="flex flex-wrap gap-2">
  <label v-for="type in messageTypes" class="flex items-center gap-2">
    <input v-model="filterTypes" :value="type" type="checkbox" />
    <span class="text-sm">{{ type }}</span>
  </label>
</div>
```
- **Multi-Select**: Mehrere Types gleichzeitig
- **Real-time**: Filter werden sofort angewendet
- **Default**: Alle Types aktiviert

#### **ESP ID Filter**
```vue
<input v-model="filterEspId" placeholder="e.g., ESP_12AB" class="input" />
```
- **Pattern**: Case-sensitive substring search
- **Real-time**: Filter wird während Eingabe angewendet
- **Clear**: Leeres Feld = kein ESP-Filter

#### **Topic Filter**
```vue
<input v-model="filterTopic" placeholder="e.g., sensor" class="input" />
```
- **Pattern**: Case-sensitive substring search
- **Scope**: Durchsucht komplette Topic-Strings
- **Performance**: Clientseitige Filterung für < 500 Messages

### **Message Interaction**

#### **Message Expansion**
```vue
<div @click="toggleExpand(msg.id)" class="cursor-pointer">
  <ChevronRight v-if="!expandedIds.has(msg.id)" />
  <ChevronDown v-else />
</div>
```
- **Toggle**: Einzelne Messages expandieren/collapsen
- **State**: Expansion-Zustand pro Message gespeichert
- **Animation**: Smooth chevron rotation

#### **Payload Display**
```vue
<pre class="text-xs font-mono bg-dark-950 p-3 rounded-lg overflow-x-auto">
  {{ formatJson(msg.payload) }}
</pre>
```
- **Format**: Pretty-printed JSON (2 spaces indentation)
- **Syntax**: Monospace font für bessere Lesbarkeit
- **Overflow**: Horizontal scroll für lange Zeilen

---

## 📊 Performance & Monitoring

### **Message Buffer Management**
```typescript
const maxMessages = 500
const messages = ref<MqttMessage[]>([])

// Buffer Management
if (messages.value.length > maxMessages) {
  messages.value = messages.value.slice(0, maxMessages)
}
```
- **Capacity**: Max. 500 Messages im Buffer
- **Strategy**: FIFO (First In, First Out)
- **Performance**: Clientseitige Filterung ohne Server-Roundtrip

### **Connection Status Monitoring**
```vue
<div class="flex items-center gap-2">
  <span :class="['status-dot', isConnected ? 'status-online' : 'status-offline']" />
  <span class="text-sm">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
</div>
```
- **Real-time**: Status-Updates jede Sekunde
- **Visual**: Grüne/Rote Status-Dot
- **Text**: Klarer Status-Text

### **Message Rate Display**
```vue
<span class="text-sm text-dark-400">
  Showing {{ filteredMessages.length }} of {{ messages.length }} messages
  <span v-if="isPaused" class="text-yellow-400 ml-2">(Paused)</span>
</span>
```
- **Metrics**: Gefilterte vs. Gesamtanzahl
- **Status**: Pause-Indikator
- **Update**: Bei jeder neuen Message

---

## 🔌 Server-Kommunikation

### **WebSocket Connection Flow**

1. **Initial Connection**
   ```typescript
   // Auto-connect on component mount
   const { subscribe, unsubscribe, isConnected } = useWebSocket({
     autoConnect: true,
     autoReconnect: true,
   })
   ```

2. **Subscription Setup**
   ```typescript
   // Subscribe to all message types
   subscribe({
     types: messageTypes, // All 9 types
   }, handleWebSocketMessage)
   ```

3. **Message Processing**
   ```typescript
   function handleWebSocketMessage(message: WebSocketMessage) {
     if (isPaused.value) return

     const msg: MqttMessage = {
       id: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
       timestamp: new Date().toISOString(),
       type: message.type as MessageType,
       topic: message.data.topic as string,
       payload: message.data.payload || message.data,
       esp_id: message.data.esp_id as string,
     }

     messages.value.unshift(msg) // Add to beginning
   }
   ```

### **Error Handling & Reconnection**

#### **Automatic Reconnection**
- **Max Attempts**: 10 Versuche
- **Delay**: Progressiver Delay (3s Basis)
- **Trigger**: Unerwartete Disconnects (nicht Code 1000)

#### **Rate Limiting**
- **Limit**: 10 Messages/Sekunde
- **Scope**: Pro Client-ID
- **Handling**: Serverseitiges Buffering bei Überschreitung

---

## 🎨 Design System

### **Message Type Color Coding**
```typescript
function getTypeColor(type: MessageType): string {
  switch (type) {
    case 'sensor_data': return 'badge-info'      // Blue
    case 'actuator_status': return 'badge-success' // Green
    case 'actuator_response': return 'badge-success' // Green
    case 'actuator_alert': return 'badge-danger'   // Red
    case 'esp_health': return 'badge-gray'       // Gray
    case 'config_response': return 'badge-warning' // Yellow
    case 'zone_assignment': return 'badge-info'    // Blue
    case 'logic_execution': return 'badge-warning' // Yellow
    case 'system_event': return 'badge-danger'    // Red
    default: return 'badge-gray'
  }
}
```

### **Timestamp Format**
```typescript
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString() // HH:MM:SS format
}
```

### **Status Indicators**
- **🟢 Connected**: Grüne Dot + "Connected"
- **🔴 Disconnected**: Rote Dot + "Disconnected"
- **🟡 Connecting**: Gelbe Dot + "Connecting"

---

## 🔍 User Flows & Use Cases

### **Debugging Workflow**
1. **Problem Isolation**
   - Filter auf spezifischen ESP-ID
   - Message-Type auf `esp_health` beschränken
   - Stream pausieren für Detailanalyse

2. **Traffic Analysis**
   - Alle Message-Types aktivieren
   - Topic-Filter für bestimmte Topics
   - Payloads expandieren für Daten-Validierung

3. **Performance Monitoring**
   - Message-Rate über Zeit beobachten
   - Connection-Status überwachen
   - Buffer-Auslastung prüfen

### **System Health Monitoring**
1. **ESP Status Check**
   - `esp_health` Messages filtern
   - Offline-Geräte identifizieren
   - Health-Patterns analysieren

2. **Logic Engine Monitoring**
   - `logic_execution` Messages verfolgen
   - Error-Patterns erkennen
   - Performance-Bottlenecks identifizieren

3. **Alert Management**
   - `actuator_alert` Messages priorisieren
   - Alarm-Patterns analysieren
   - System-Response überwachen

---

## 🛠️ Technische Implementierung

### **Vue 3 Composition API**
```typescript
// Reactive State Management
const messages = ref<MqttMessage[]>([])
const isPaused = ref(false)
const maxMessages = 500

// Computed Properties
const filteredMessages = computed(() => {
  return messages.value.filter(msg => {
    // Real-time filtering logic
  })
})
```

### **WebSocket Service Integration**
```typescript
// Singleton Pattern Usage
const { subscribe, unsubscribe, isConnected } = useWebSocket({
  autoConnect: true,
  autoReconnect: true,
})

// Lifecycle Management
onMounted(() => {
  subscribe({ types: messageTypes }, handleWebSocketMessage)
})

onUnmounted(() => {
  unsubscribe()
})
```

### **Performance Optimizations**
- **Virtual Scrolling**: Für > 500 Messages
- **Debounced Filtering**: 100ms Delay bei Eingabe
- **Memory Management**: Automatisches Cleanup alter Messages
- **Lazy Loading**: Payload nur bei Expansion parsen

---

## 🚀 Erweiterte Features (zukünftig)

### **Export Funktionalität**
```typescript
// JSON Export
function exportToJson() {
  const data = {
    timestamp: new Date().toISOString(),
    filters: activeFilters.value,
    messages: filteredMessages.value,
  }
  downloadJson(data, `mqtt-log-${Date.now()}.json`)
}

// CSV Export
function exportToCsv() {
  const csv = convertToCsv(filteredMessages.value)
  downloadCsv(csv, `mqtt-log-${Date.now()}.csv`)
}
```

### **Search & Highlight**
```typescript
// Real-time Search
const searchTerm = ref('')
const highlightedMessages = computed(() => {
  return filteredMessages.value.map(msg => ({
    ...msg,
    highlighted: highlightMatches(msg, searchTerm.value)
  }))
})
```

### **Advanced Filtering**
- **Time Range**: Messages nach Zeit filtern
- **Payload Search**: In JSON-Payloads suchen
- **Regex Support**: Erweiterte Pattern-Matching
- **Saved Filters**: Filter-Presets speichern

---

## 📈 Monitoring & Analytics

### **Message Statistics**
- **Rate Monitoring**: Messages/Sekunde
- **Type Distribution**: Prozentuale Verteilung pro Type
- **ESP Activity**: Aktivste Geräte
- **Error Patterns**: Häufigste Fehler

### **Connection Analytics**
- **Uptime**: Connection-Verfügbarkeit
- **Reconnect Frequency**: Verbindungsschwierigkeiten
- **Message Loss**: Geschätzter Message-Verlust

---

## 🔐 Sicherheit & Authentifizierung

### **WebSocket Authentication**
```typescript
// Token-based Authentication
const token = authStore.accessToken
const wsUrl = `${protocol}//${host}/api/v1/ws/realtime/${clientId}?token=${encodeURIComponent(token)}`
```

### **Rate Limiting**
- **Client Limits**: 10 Messages/Sekunde
- **Server Protection**: DDoS-Schutz
- **Fair Usage**: Gleichmäßige Ressourcen-Verteilung

---

## 🐛 Troubleshooting

### **Häufige Probleme**

#### **WebSocket Connection Failed**
- **Ursache**: Token expired, Server down
- **Lösung**: Re-Authentifizierung, Server-Status prüfen
- **Fallback**: Polling-Modus aktivieren

#### **Messages nicht angezeigt**
- **Ursache**: Filter zu restriktiv, Buffer voll
- **Lösung**: Filter zurücksetzen, Clear ausführen
- **Debug**: Console für WebSocket-Events prüfen

#### **Performance Issues**
- **Ursache**: Zu viele Messages, Browser-Limit
- **Lösung**: Filter anwenden, Buffer reduzieren
- **Optimierung**: Virtual Scrolling aktivieren

---

## 📚 API Referenz

### **MqttLogView Props**
```typescript
interface MqttLogViewProps {
  maxMessages?: number    // Default: 500
  autoConnect?: boolean   // Default: true
  showFilters?: boolean   // Default: false
}
```

### **WebSocket Events**
```typescript
// Emitted Events
'message-received'  // Neue Message eingetroffen
'connection-status' // Status-Änderung
'filter-changed'    // Filter aktualisiert
'buffer-full'       // Max capacity erreicht
```

---

Diese Dokumentation ermöglicht es Entwicklern, das komplette MQTT-Monitoring-System zu verstehen und zu erweitern. Die modulare Architektur erlaubt einfache Integration zusätzlicher Features wie Export, erweiterte Suche oder Analytics.
