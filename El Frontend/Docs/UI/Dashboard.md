# 🏠 Dashboard - Vollständige UI-Dokumentation

## 🎯 Übersicht: IoT-System Dashboard (`/`)

Das Dashboard ist die **zentrale Kommandozentrale** für das gesamte IoT-Management-System. Es bietet Usern eine umfassende, echtzeit-aktualisierte Übersicht über alle ESP32-Geräte, System-Health-Metriken und kritische Alerts. Als Root-Route (`/`) ist dies die erste View, die User sehen - sie muss perfekt funktionieren und sofort Klarheit über den Systemzustand geben.

### **Technische Architektur**
- **Frontend**: React/TypeScript mit Material-UI oder ähnlichem Design-System
- **State-Management**: Zustand oder Redux mit WebSocket-Integration
- **Real-time Kommunikation**: WebSocket für Live-Updates
- **API**: RESTful API für Datenaggregation + GraphQL für komplexe Queries
- **Performance-Ziel**: < 2 Sekunden Initial-Load-Time

### **Kernfunktionalitäten**
1. **System-Status Monitoring**: Live-Übersicht aller ESP-Geräte
2. **KPI-Dashboard**: Aggregierte Metriken und Health-Indikatoren
3. **Alert-Management**: Kritische Events mit Acknowledge-System
4. **Quick-Actions**: Schnellzugriff auf häufige Operationen
5. **Drill-Down Navigation**: Direkter Zugang zu Detail-Views

---

## 📋 Detaillierte Dokumentations-Struktur

## 📋 Detaillierte Dokumentations-Struktur

### **Sektion 1: Übersicht** ✅
- **Route**: `/` (Root-Route, wichtigste View)
- **Zweck**: Zentrale System-Übersicht für IoT-Management
- **Kritische Funktion**: Erstes was User sehen - muss perfekt sein!
- **Performance-Ziel**: < 2s Initial Load, < 100ms für Updates
- **Responsiveness**: Mobile-first Design mit Breakpoints

### **Sektion 2: UI-Komponenten detailliert**

#### **Layout-Struktur**
```
┌─────────────────────────────────────────────────────────┐
│ [System Status: 🟢 OPERATIONAL] [Letzte Update: 14:32] │
├─────────────────────────────────────────────────────────┤
│ KPI-Karten:                                             │
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐         │
│ │ 12  │ │ 3   │ │ 95% │ │ 2   │ │ 45°C│ │ 2.1A│         │
│ │ ESPs│ │Offline│ │Online│ │Alerts│ │Temp │ │Strom│         │
│ │ 🟢  │ │ 🔴   │ │ 📊  │ │ ⚠️  │ │ 📈  │ │ 📉  │         │
│ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘         │
├─────────────────────────────────────────────────────────┤
│ ESP-Übersicht (Mini-Karten):                           │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ │ ESP_01          │ │ ESP_02          │ │ ESP_03          │
│ │ 🟢 Online       │ │ 🔴 Offline      │ │ 🟡 Safe Mode    │
│ │ 23.5°C | 85%    │ │ Connection Lost │ │ Emergency Stop │
│ │ [Details →]     │ │ [Reconnect]     │ │ [Reset]        │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘
├─────────────────────────────────────────────────────────┤
│ Aktive Alerts:                                          │
│ ⚠️ ESP_02: Connection lost (5 min ago)                 │
│ ⚠️ Sensor_05: Value out of range (2 min ago)           │
│ ✅ ESP_01: Reconnected successfully                     │
└─────────────────────────────────────────────────────────┘
```

#### **2.1 Header-Bereich (SystemStatusBar)**
```typescript
interface SystemStatusBarProps {
  systemStatus: 'operational' | 'warning' | 'critical' | 'offline';
  lastUpdate: Date;
  onEmergencyStop: () => void;
  onRefresh: () => void;
}

// Implementierung mit auto-refresh jede 30 Sekunden
const SystemStatusBar: React.FC<SystemStatusBarProps> = ({
  systemStatus,
  lastUpdate,
  onEmergencyStop,
  onRefresh
}) => {
  // Status-Indikator mit Farbkodierung
  const getStatusColor = (status: string) => {
    switch(status) {
      case 'operational': return '#10B981'; // green
      case 'warning': return '#F59E0B';     // yellow
      case 'critical': return '#EF4444';    // red
      default: return '#6B7280';            // gray
    }
  };

  return (
    <div className="system-status-bar">
      <div className="status-indicator">
        <div
          className="status-dot"
          style={{ backgroundColor: getStatusColor(systemStatus) }}
        />
        <span>System Status: {systemStatus.toUpperCase()}</span>
      </div>
      <div className="last-update">
        Letzte Update: {lastUpdate.toLocaleTimeString()}
      </div>
      <div className="header-actions">
        <button onClick={onRefresh}>🔄 Refresh</button>
        <button onClick={onEmergencyStop} className="emergency-stop">
          🛑 Emergency Stop
        </button>
      </div>
    </div>
  );
};
```

#### **2.2 KPI-Karten (KPICardsGrid)**
```typescript
interface KPICard {
  id: string;
  title: string;
  value: number | string;
  unit?: string;
  status: 'normal' | 'warning' | 'critical';
  icon: string;
  trend?: 'up' | 'down' | 'stable';
  onClick?: () => void;
}

const KPICard: React.FC<KPICard> = ({
  title, value, unit, status, icon, trend, onClick
}) => (
  <Card
    className={`kpi-card kpi-card--${status}`}
    onClick={onClick}
    hoverable
  >
    <div className="kpi-header">
      <span className="kpi-icon">{icon}</span>
      <span className="kpi-title">{title}</span>
    </div>
    <div className="kpi-value">
      {value}{unit && <span className="kpi-unit">{unit}</span>}
    </div>
    {trend && (
      <div className="kpi-trend">
        {trend === 'up' && '📈'}
        {trend === 'down' && '📉'}
        {trend === 'stable' && '➡️'}
      </div>
    )}
  </Card>
);

// Standard-KPI-Karten Definition
const DEFAULT_KPIS: KPICard[] = [
  { id: 'active-esps', title: 'ESPs', value: 12, icon: '🟢', status: 'normal' },
  { id: 'offline-esps', title: 'Offline', value: 3, icon: '🔴', status: 'warning' },
  { id: 'system-health', title: 'Online', value: '95%', icon: '📊', status: 'normal' },
  { id: 'active-alerts', title: 'Alerts', value: 2, icon: '⚠️', status: 'warning' },
  { id: 'avg-temperature', title: 'Temp', value: 45, unit: '°C', icon: '📈', status: 'normal' },
  { id: 'power-consumption', title: 'Strom', value: 2.1, unit: 'A', icon: '📉', status: 'normal' }
];
```

#### **2.3 ESP-Mini-Karten (ESPOverviewGrid)**
```typescript
interface ESPDevice {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'safe_mode' | 'error';
  temperature?: number;
  humidity?: number;
  lastSeen: Date;
  location?: string;
  firmwareVersion: string;
}

const ESPMiniCard: React.FC<{ device: ESPDevice; onAction: (action: string) => void }> = ({
  device, onAction
}) => {
  const getStatusIcon = (status: string) => {
    switch(status) {
      case 'online': return '🟢';
      case 'offline': return '🔴';
      case 'safe_mode': return '🟡';
      case 'error': return '🔴';
      default: return '⚪';
    }
  };

  const getActionButton = (status: string) => {
    switch(status) {
      case 'offline': return { text: 'Reconnect', action: 'reconnect' };
      case 'safe_mode': return { text: 'Reset', action: 'reset' };
      default: return { text: 'Details →', action: 'details' };
    }
  };

  const action = getActionButton(device.status);

  return (
    <Card className={`esp-card esp-card--${device.status}`}>
      <div className="esp-header">
        <h4>{device.name}</h4>
        <span className="esp-status">{getStatusIcon(device.status)} {device.status.replace('_', ' ')}</span>
      </div>

      {device.status === 'online' && device.temperature && device.humidity && (
        <div className="esp-metrics">
          <span>{device.temperature}°C</span>
          <span>{device.humidity}%</span>
        </div>
      )}

      {device.status === 'offline' && (
        <div className="esp-error">Connection Lost</div>
      )}

      {device.status === 'safe_mode' && (
        <div className="esp-warning">Emergency Stop</div>
      )}

      <button
        className="esp-action-btn"
        onClick={() => onAction(action.action)}
      >
        {action.text}
      </button>
    </Card>
  );
};
```

#### **2.4 Alert-Panel (AlertPanel)**
```typescript
interface Alert {
  id: string;
  type: 'warning' | 'error' | 'info' | 'success';
  title: string;
  message: string;
  timestamp: Date;
  source: string; // ESP ID oder Sensor ID
  acknowledged: boolean;
  priority: 'low' | 'medium' | 'high' | 'critical';
}

const AlertItem: React.FC<{
  alert: Alert;
  onAcknowledge: (id: string) => void;
  onNavigate: (source: string) => void;
}> = ({ alert, onAcknowledge, onNavigate }) => {
  const getAlertIcon = (type: string) => {
    switch(type) {
      case 'error': return '🚨';
      case 'warning': return '⚠️';
      case 'success': return '✅';
      default: return 'ℹ️';
    }
  };

  return (
    <div className={`alert-item alert-item--${alert.type} alert-item--${alert.priority}`}>
      <div className="alert-icon">{getAlertIcon(alert.type)}</div>
      <div className="alert-content">
        <div className="alert-title">{alert.title}</div>
        <div className="alert-message">{alert.message}</div>
        <div className="alert-meta">
          {alert.source} • {alert.timestamp.toLocaleString()}
        </div>
      </div>
      <div className="alert-actions">
        {!alert.acknowledged && (
          <button onClick={() => onAcknowledge(alert.id)}>Acknowledge</button>
        )}
        <button onClick={() => onNavigate(alert.source)}>View Source</button>
      </div>
    </div>
  );
};
```

### **Sektion 3: Live-Monitoring Interaktionen**

#### **3.1 Event-System Architektur**
```typescript
// Zentrales Event-System für Dashboard-Interaktionen
interface DashboardEvent {
  type: 'kpi_click' | 'esp_action' | 'alert_acknowledge' | 'system_control' | 'refresh';
  payload: any;
  timestamp: Date;
}

class DashboardEventHandler {
  private listeners: Map<string, Function[]> = new Map();

  on(eventType: string, callback: Function) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, []);
    }
    this.listeners.get(eventType)!.push(callback);
  }

  emit(event: DashboardEvent) {
    const listeners = this.listeners.get(event.type) || [];
    listeners.forEach(callback => callback(event));
  }
}

// Global Event Handler Instance
export const dashboardEvents = new DashboardEventHandler();
```

#### **3.2 KPI-Interaktionen (Drill-Down Navigation)**
```typescript
// KPI-Klick Handler mit Navigation-Logik
const handleKPIClick = (kpiId: string) => {
  const navigationMap = {
    'active-esps': '/devices',
    'offline-esps': '/devices?status=offline',
    'system-health': '/system/health',
    'active-alerts': '/alerts',
    'avg-temperature': '/sensors/temperature',
    'power-consumption': '/sensors/power'
  };

  const targetRoute = navigationMap[kpiId as keyof typeof navigationMap];
  if (targetRoute) {
    // Navigation mit Query-Parametern für Filter-Kontext
    navigate(targetRoute, {
      state: {
        from: 'dashboard',
        filter: getKPIFilterContext(kpiId)
      }
    });

    // Event für Analytics
    dashboardEvents.emit({
      type: 'kpi_click',
      payload: { kpiId, targetRoute },
      timestamp: new Date()
    });
  }
};

// KPI-spezifische Filter-Kontexte
const getKPIFilterContext = (kpiId: string) => {
  switch(kpiId) {
    case 'active-esps': return { status: 'online' };
    case 'offline-esps': return { status: 'offline' };
    case 'active-alerts': return { acknowledged: false };
    default: return {};
  }
};
```

#### **3.3 ESP-Karten Interaktionen**
```typescript
// ESP Action Handler mit Device-spezifischer Logik
const handleESPAction = async (espId: string, action: string) => {
  try {
    switch(action) {
      case 'details':
        navigate(`/devices/${espId}`, {
          state: { from: 'dashboard' }
        });
        break;

      case 'reconnect':
        await reconnectDevice(espId);
        showNotification('Reconnect initiated', 'info');
        // Auto-refresh triggern für Status-Update
        triggerDashboardRefresh();
        break;

      case 'reset':
        const confirmed = await confirmDialog(
          'Reset ESP Device',
          'Are you sure you want to reset this device? This will interrupt all active processes.'
        );
        if (confirmed) {
          await resetDevice(espId);
          showNotification('Device reset initiated', 'warning');
        }
        break;

      default:
        console.warn(`Unknown ESP action: ${action}`);
    }

    // Event logging
    dashboardEvents.emit({
      type: 'esp_action',
      payload: { espId, action },
      timestamp: new Date()
    });
  } catch (error) {
    showNotification(`Action failed: ${error.message}`, 'error');
  }
};
```

#### **3.4 Alert-Management Interaktionen**
```typescript
// Alert Acknowledge System
const handleAlertAcknowledge = async (alertId: string) => {
  try {
    await api.post(`/api/v1/alerts/${alertId}/acknowledge`);
    showNotification('Alert acknowledged', 'success');

    // Lokales State Update für sofortiges UI-Feedback
    updateAlertState(alertId, { acknowledged: true });

    dashboardEvents.emit({
      type: 'alert_acknowledge',
      payload: { alertId },
      timestamp: new Date()
    });
  } catch (error) {
    showNotification('Failed to acknowledge alert', 'error');
  }
};

// Alert Navigation (zum Alert-Source)
const navigateToAlertSource = (alertSource: string) => {
  // Parse alert source (Format: "ESP_01:sensor_05" oder "ESP_02")
  const [espId, sensorId] = alertSource.split(':');

  if (sensorId) {
    // Navigiere zu spezifischem Sensor
    navigate(`/devices/${espId}/sensors/${sensorId}`, {
      state: { highlight: true, from: 'alert' }
    });
  } else {
    // Navigiere zu ESP Device
    navigate(`/devices/${espId}`, {
      state: { from: 'alert' }
    });
  }
};
```

#### **3.5 Auto-Refresh & Live-Updates**
```typescript
// Auto-Refresh Manager mit konfigurierbaren Intervallen
class AutoRefreshManager {
  private intervalId: NodeJS.Timeout | null = null;
  private refreshInterval: number = 30000; // 30 Sekunden default
  private isActive: boolean = true;

  start() {
    if (this.intervalId) return;

    this.intervalId = setInterval(() => {
      if (this.isActive && document.visibilityState === 'visible') {
        this.performRefresh();
      }
    }, this.refreshInterval);
  }

  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  setInterval(intervalMs: number) {
    this.refreshInterval = intervalMs;
    this.restart();
  }

  pause() { this.isActive = false; }
  resume() { this.isActive = true; }

  private async performRefresh() {
    try {
      const data = await api.get('/api/v1/dashboard');
      updateDashboardData(data);

      dashboardEvents.emit({
        type: 'refresh',
        payload: { success: true },
        timestamp: new Date()
      });
    } catch (error) {
      console.error('Dashboard refresh failed:', error);
      dashboardEvents.emit({
        type: 'refresh',
        payload: { success: false, error: error.message },
        timestamp: new Date()
      });
    }
  }

  private restart() {
    this.stop();
    this.start();
  }
}

// Global Instance
export const autoRefreshManager = new AutoRefreshManager();

// React Hook für Component-Integration
export const useAutoRefresh = () => {
  useEffect(() => {
    autoRefreshManager.start();
    return () => autoRefreshManager.stop();
  }, []);

  return {
    refreshNow: () => autoRefreshManager.performRefresh(),
    setInterval: (ms: number) => autoRefreshManager.setInterval(ms),
    pause: () => autoRefreshManager.pause(),
    resume: () => autoRefreshManager.resume()
  };
};
```

#### **3.6 System-Control Interaktionen**
```typescript
// Emergency Stop für alle ESPs
const handleEmergencyStop = async () => {
  const confirmed = await confirmDialog(
    'Emergency Stop All Devices',
    'This will immediately stop all ESP devices. Are you sure?',
    'danger'
  );

  if (!confirmed) return;

  try {
    showLoadingSpinner('Initiating emergency stop...');
    await api.post('/api/v1/system/emergency-stop');

    showNotification('Emergency stop initiated for all devices', 'warning');

    // Force refresh nach Emergency Stop
    setTimeout(() => {
      triggerDashboardRefresh();
    }, 2000);

    dashboardEvents.emit({
      type: 'system_control',
      payload: { action: 'emergency_stop', target: 'all' },
      timestamp: new Date()
    });
  } catch (error) {
    showNotification('Emergency stop failed', 'error');
  } finally {
    hideLoadingSpinner();
  }
};

// Einzelnes Device Emergency Stop
const handleDeviceEmergencyStop = async (espId: string) => {
  try {
    await api.post(`/api/v1/devices/${espId}/emergency-stop`);
    showNotification(`Emergency stop initiated for ${espId}`, 'warning');

    dashboardEvents.emit({
      type: 'system_control',
      payload: { action: 'emergency_stop', target: espId },
      timestamp: new Date()
    });
  } catch (error) {
    showNotification(`Emergency stop failed for ${espId}`, 'error');
  }
};
```

#### **3.7 Touch & Gesture Support (Mobile)**
```typescript
// Swipe Gestures für Mobile Navigation
const useSwipeGestures = () => {
  const swipeThreshold = 50;

  const handleSwipe = (direction: 'left' | 'right') => {
    switch(direction) {
      case 'left':
        navigate('/devices'); // Swipe left -> Devices
        break;
      case 'right':
        navigate('/alerts'); // Swipe right -> Alerts
        break;
    }
  };

  return { handleSwipe };
};

// Long-Press für Quick-Actions
const useLongPress = (callback: Function, delay: number = 500) => {
  const [startLongPress, setStartLongPress] = useState(false);

  useEffect(() => {
    let timerId: NodeJS.Timeout;
    if (startLongPress) {
      timerId = setTimeout(callback, delay);
    } else {
      clearTimeout(timerId);
    }

    return () => clearTimeout(timerId);
  }, [callback, delay, startLongPress]);

  return {
    onMouseDown: () => setStartLongPress(true),
    onMouseUp: () => setStartLongPress(false),
    onMouseLeave: () => setStartLongPress(false),
    onTouchStart: () => setStartLongPress(true),
    onTouchEnd: () => setStartLongPress(false)
  };
};
```

### **Sektion 4: Server-API Integration**

#### **4.1 REST API Endpunkte**

##### **Dashboard Daten Aggregation**
```typescript
// GET /api/v1/dashboard
interface DashboardResponse {
  system_status: 'operational' | 'warning' | 'critical' | 'offline';
  last_update: string; // ISO 8601 timestamp
  kpis: {
    active_esps: number;
    offline_esps: number;
    system_health_percentage: number;
    active_alerts: number;
    avg_temperature: number;
    power_consumption: number;
  };
  devices: ESPDevice[];
  alerts: Alert[];
  system_metrics: {
    cpu_usage: number;
    memory_usage: number;
    network_status: 'online' | 'degraded' | 'offline';
    uptime_seconds: number;
  };
}

// Response Beispiel
{
  "system_status": "operational",
  "last_update": "2024-01-15T14:32:15.000Z",
  "kpis": {
    "active_esps": 12,
    "offline_esps": 3,
    "system_health_percentage": 95,
    "active_alerts": 2,
    "avg_temperature": 45.2,
    "power_consumption": 2.1
  },
  "devices": [...], // Array von ESPDevice Objekten
  "alerts": [...],  // Array von Alert Objekten
  "system_metrics": {
    "cpu_usage": 45.2,
    "memory_usage": 67.8,
    "network_status": "online",
    "uptime_seconds": 86400
  }
}
```

##### **ESP Device Management**
```typescript
// GET /api/v1/devices
interface DevicesResponse {
  devices: ESPDevice[];
  total: number;
  online: number;
  offline: number;
}

// GET /api/v1/devices/{id}
interface DeviceDetailResponse extends ESPDevice {
  sensors: Sensor[];
  logs: DeviceLog[];
  configuration: DeviceConfig;
}

// POST /api/v1/devices/{id}/reconnect
interface ReconnectRequest {
  force?: boolean; // Force reconnection even if device appears online
}

// POST /api/v1/devices/{id}/reset
interface ResetRequest {
  type: 'soft' | 'hard'; // Soft reset vs complete power cycle
  reason?: string; // Optional reason for logging
}
```

##### **Alert Management**
```typescript
// GET /api/v1/alerts
interface AlertsResponse {
  alerts: Alert[];
  total: number;
  unacknowledged: number;
  by_priority: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
}

// POST /api/v1/alerts/{id}/acknowledge
interface AcknowledgeRequest {
  user_id?: string; // Optional for audit logging
  comment?: string; // Optional comment
}

// GET /api/v1/alerts/history
interface AlertHistoryResponse {
  alerts: Alert[];
  pagination: {
    page: number;
    limit: number;
    total: number;
  };
}
```

##### **System Controls**
```typescript
// POST /api/v1/system/emergency-stop
interface EmergencyStopRequest {
  reason: string; // Required reason for emergency stop
  affected_devices?: string[]; // Optional: specific devices, empty = all
}

// GET /api/v1/system/health
interface SystemHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  services: {
    database: 'up' | 'down' | 'degraded';
    websocket: 'up' | 'down' | 'degraded';
    api: 'up' | 'down' | 'degraded';
    mqtt_broker: 'up' | 'down' | 'degraded';
  };
  metrics: {
    response_time_ms: number;
    error_rate: number;
    uptime_percentage: number;
  };
}
```

#### **4.2 WebSocket Real-time Updates**

##### **Connection Setup**
```typescript
// WebSocket URL: ws://api.example.com/v1/dashboard/live
// Authentifizierung via JWT Token im Query Parameter
const wsUrl = `ws://api.example.com/v1/dashboard/live?token=${jwtToken}`;

const ws = new WebSocket(wsUrl);

// Connection Event Handler
ws.onopen = () => {
  console.log('Dashboard WebSocket connected');
  // Subscribe to specific event types
  ws.send(JSON.stringify({
    type: 'subscribe',
    events: ['system_health', 'esp_status', 'alerts', 'kpi_updates']
  }));
};
```

##### **Event Types & Payloads**
```typescript
// System Health Updates
interface SystemHealthEvent {
  type: 'system_health';
  data: {
    status: 'operational' | 'warning' | 'critical' | 'offline';
    timestamp: string;
    changes: {
      cpu_usage?: number;
      memory_usage?: number;
      network_status?: string;
    };
  };
}

// ESP Status Updates
interface ESPStatusEvent {
  type: 'esp_status';
  data: {
    esp_id: string;
    status: 'online' | 'offline' | 'safe_mode' | 'error';
    timestamp: string;
    previous_status?: string;
    metadata?: {
      reason?: string; // e.g., "connection_lost", "power_failure"
      reconnect_attempts?: number;
    };
  };
}

// Alert Events
interface AlertEvent {
  type: 'alert';
  action: 'created' | 'acknowledged' | 'resolved';
  data: Alert;
}

// KPI Updates (periodische Updates alle 30s)
interface KPIUpdateEvent {
  type: 'kpi_update';
  data: {
    timestamp: string;
    kpis: DashboardResponse['kpis'];
    changes: {
      active_esps?: { old: number; new: number };
      offline_esps?: { old: number; new: number };
      // ... weitere KPI-Änderungen
    };
  };
}

// Device Sensor Updates
interface SensorUpdateEvent {
  type: 'sensor_update';
  data: {
    esp_id: string;
    sensor_id: string;
    readings: {
      temperature?: number;
      humidity?: number;
      pressure?: number;
      // ... weitere Sensor-Daten
    };
    timestamp: string;
  };
}
```

##### **WebSocket Client Implementation**
```typescript
class DashboardWebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1s, exponential backoff

  constructor(private url: string, private eventHandlers: Map<string, Function[]>) {}

  connect() {
    try {
      this.ws = new WebSocket(this.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      this.scheduleReconnect();
    }
  }

  private setupEventHandlers() {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.subscribeToEvents();
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      if (!event.wasClean) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  private subscribeToEvents() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const subscription = {
      type: 'subscribe',
      events: ['system_health', 'esp_status', 'alerts', 'kpi_updates', 'sensor_updates']
    };

    this.ws.send(JSON.stringify(subscription));
  }

  private handleMessage(message: any) {
    const handlers = this.eventHandlers.get(message.type) || [];
    handlers.forEach(handler => {
      try {
        handler(message.data);
      } catch (error) {
        console.error(`Error in ${message.type} handler:`, error);
      }
    });
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    setTimeout(() => {
      console.log(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
      this.connect();
    }, delay);
  }

  disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
  }
}
```

#### **4.3 Data Models & TypeScript Interfaces**
```typescript
// Core Data Models
export interface ESPDevice {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'safe_mode' | 'error';
  ip_address?: string;
  mac_address: string;
  firmware_version: string;
  hardware_version: string;
  location?: {
    zone: string;
    position: string;
  };
  last_seen: string; // ISO timestamp
  uptime_seconds?: number;
  config: DeviceConfig;
}

export interface DeviceConfig {
  update_interval_seconds: number;
  emergency_stop_enabled: boolean;
  sensors_enabled: string[]; // Array von Sensor-IDs
  wifi_ssid?: string;
  mqtt_broker?: string;
}

export interface Sensor {
  id: string;
  type: 'temperature' | 'humidity' | 'pressure' | 'motion' | 'power' | 'custom';
  unit: string;
  current_value?: number;
  min_value?: number;
  max_value?: number;
  threshold_warning?: number;
  threshold_critical?: number;
  last_reading: string;
  status: 'normal' | 'warning' | 'critical' | 'offline';
}

export interface Alert {
  id: string;
  type: 'device_offline' | 'sensor_failure' | 'value_out_of_range' | 'system_error' | 'custom';
  priority: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  source: string; // "ESP_01:sensor_temp" oder "ESP_02"
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  created_at: string;
  resolved_at?: string;
  metadata?: Record<string, any>; // Zusätzliche Alert-Daten
}

export interface DeviceLog {
  id: string;
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical';
  message: string;
  timestamp: string;
  source: string; // "system", "sensor", "network", etc.
  metadata?: Record<string, any>;
}
```

#### **4.4 Error Handling & API Resilience**
```typescript
// API Error Response Format
interface APIError {
  error: {
    code: string; // e.g., "DEVICE_NOT_FOUND", "VALIDATION_ERROR"
    message: string;
    details?: any;
    timestamp: string;
  };
}

// HTTP Status Code Mapping
const API_ERROR_CODES = {
  400: 'VALIDATION_ERROR',
  401: 'UNAUTHORIZED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'UNPROCESSABLE_ENTITY',
  429: 'RATE_LIMITED',
  500: 'INTERNAL_SERVER_ERROR',
  503: 'SERVICE_UNAVAILABLE'
} as const;

// Client-side Error Handler
class APIErrorHandler {
  static handle(error: any): APIError {
    if (error.response) {
      // Server responded with error status
      const { status, data } = error.response;
      return {
        error: {
          code: API_ERROR_CODES[status as keyof typeof API_ERROR_CODES] || 'UNKNOWN_ERROR',
          message: data?.message || 'An error occurred',
          details: data?.details,
          timestamp: new Date().toISOString()
        }
      };
    } else if (error.request) {
      // Network error
      return {
        error: {
          code: 'NETWORK_ERROR',
          message: 'Network request failed',
          timestamp: new Date().toISOString()
        }
      };
    } else {
      // Client error
      return {
        error: {
          code: 'CLIENT_ERROR',
          message: error.message || 'Unknown client error',
          timestamp: new Date().toISOString()
        }
      };
    }
  }
}

// Retry Logic für kritische API Calls
const withRetry = async <T>(
  apiCall: () => Promise<T>,
  maxRetries: number = 3,
  delayMs: number = 1000
): Promise<T> => {
  let lastError: any;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await apiCall();
    } catch (error) {
      lastError = error;

      if (attempt === maxRetries) break;

      // Exponential backoff
      const delay = delayMs * Math.pow(2, attempt - 1);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError;
};
```

#### **4.5 Caching Strategy**
```typescript
// Smart Caching für Performance
interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number; // Time to live in milliseconds
}

class APICache {
  private cache = new Map<string, CacheEntry<any>>();

  set<T>(key: string, data: T, ttlMs: number = 30000) { // 30s default
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl: ttlMs
    });
  }

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    if (Date.now() - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      return null;
    }

    return entry.data;
  }

  invalidate(pattern: string) {
    // Lösche alle Keys die dem Pattern entsprechen
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }

  clear() {
    this.cache.clear();
  }
}

// Cache Keys für Dashboard
const CACHE_KEYS = {
  DASHBOARD_DATA: 'dashboard:main',
  DEVICES_LIST: 'devices:list',
  ALERTS_LIST: 'alerts:list',
  DEVICE_DETAIL: (id: string) => `devices:${id}:detail`,
  SYSTEM_HEALTH: 'system:health'
} as const;

// Cached API Service
class CachedAPIService {
  constructor(private api: AxiosInstance, private cache: APICache) {}

  async getDashboardData(): Promise<DashboardResponse> {
    const cacheKey = CACHE_KEYS.DASHBOARD_DATA;
    const cached = this.cache.get<DashboardResponse>(cacheKey);

    if (cached) return cached;

    const data = await this.api.get('/api/v1/dashboard');
    this.cache.set(cacheKey, data, 10000); // 10s TTL für Dashboard
    return data;
  }

  async getDeviceDetail(id: string): Promise<DeviceDetailResponse> {
    const cacheKey = CACHE_KEYS.DEVICE_DETAIL(id);
    const cached = this.cache.get<DeviceDetailResponse>(cacheKey);

    if (cached) return cached;

    const data = await this.api.get(`/api/v1/devices/${id}`);
    this.cache.set(cacheKey, data, 30000); // 30s TTL für Device Details
    return data;
  }
}
```

### **Sektion 5: Kritische Dashboard-Features**

#### **5.1 System-Health Monitoring**
```typescript
// System Health Dashboard Component
interface SystemHealthMetrics {
  cpu: {
    usage: number; // Percentage 0-100
    temperature: number; // Celsius
    cores: number;
  };
  memory: {
    used: number; // MB
    total: number; // MB
    percentage: number;
  };
  network: {
    status: 'online' | 'degraded' | 'offline';
    latency_ms: number;
    bandwidth_up: number; // Mbps
    bandwidth_down: number; // Mbps
  };
  storage: {
    used: number; // GB
    total: number; // GB
    percentage: number;
  };
  uptime: {
    seconds: number;
    formatted: string; // "2d 14h 32m"
  };
}

const SystemHealthIndicator: React.FC<{ metrics: SystemHealthMetrics }> = ({ metrics }) => {
  const getHealthScore = (): number => {
    // Weighted health score calculation
    const weights = {
      cpu: 0.3,
      memory: 0.3,
      network: 0.2,
      storage: 0.2
    };

    const cpuScore = Math.max(0, 100 - metrics.cpu.usage);
    const memoryScore = Math.max(0, 100 - metrics.memory.percentage);
    const networkScore = metrics.network.status === 'online' ? 100 :
                        metrics.network.status === 'degraded' ? 50 : 0;
    const storageScore = Math.max(0, 100 - metrics.storage.percentage);

    return Math.round(
      cpuScore * weights.cpu +
      memoryScore * weights.memory +
      networkScore * weights.network +
      storageScore * weights.storage
    );
  };

  const healthScore = getHealthScore();
  const healthStatus = healthScore >= 90 ? 'excellent' :
                      healthScore >= 70 ? 'good' :
                      healthScore >= 50 ? 'warning' : 'critical';

  return (
    <Card className={`system-health health--${healthStatus}`}>
      <div className="health-header">
        <h3>System Health</h3>
        <div className="health-score">
          <CircularProgress value={healthScore} />
          <span className="score-text">{healthScore}%</span>
        </div>
      </div>

      <div className="health-metrics">
        <MetricItem
          label="CPU"
          value={`${metrics.cpu.usage}%`}
          status={metrics.cpu.usage > 80 ? 'warning' : 'normal'}
          icon="🖥️"
        />
        <MetricItem
          label="Memory"
          value={`${metrics.memory.percentage}%`}
          status={metrics.memory.percentage > 85 ? 'warning' : 'normal'}
          icon="💾"
        />
        <MetricItem
          label="Network"
          value={metrics.network.status}
          status={metrics.network.status === 'online' ? 'normal' : 'critical'}
          icon="🌐"
        />
        <MetricItem
          label="Storage"
          value={`${metrics.storage.percentage}%`}
          status={metrics.storage.percentage > 90 ? 'warning' : 'normal'}
          icon="💿"
        />
      </div>

      <div className="uptime-display">
        <span>Uptime: {metrics.uptime.formatted}</span>
      </div>
    </Card>
  );
};
```

#### **5.2 ESP-Monitoring & Device Management**
```typescript
// Advanced ESP Monitoring mit Health Scores
interface ESPHealthMetrics {
  device: ESPDevice;
  health_score: number; // 0-100
  connectivity: {
    signal_strength: number; // -100 to 0 (dBm)
    ping_time: number; // ms
    reconnect_count: number;
  };
  performance: {
    cpu_usage: number;
    memory_usage: number;
    uptime_percentage: number;
  };
  sensors: {
    active: number;
    failing: number;
    offline: number;
  };
  alerts: {
    active: number;
    acknowledged: number;
  };
}

const ESPHealthCard: React.FC<{ metrics: ESPHealthMetrics }> = ({ metrics }) => {
  const getHealthColor = (score: number) => {
    if (score >= 90) return '#10B981';
    if (score >= 70) return '#F59E0B';
    if (score >= 50) return '#F97316';
    return '#EF4444';
  };

  const getConnectivityIcon = (signal: number) => {
    if (signal > -50) return '📶'; // Excellent
    if (signal > -70) return '📶'; // Good
    if (signal > -85) return '📶'; // Fair
    return '📶'; // Poor
  };

  return (
    <Card className="esp-health-card">
      <div className="esp-header">
        <div className="esp-info">
          <h4>{metrics.device.name}</h4>
          <div className="esp-status">
            <span className={`status-dot status--${metrics.device.status}`}></span>
            {metrics.device.status}
          </div>
        </div>
        <div className="health-score">
          <CircularProgress
            value={metrics.health_score}
            color={getHealthColor(metrics.health_score)}
            size={40}
          />
        </div>
      </div>

      <div className="esp-metrics-grid">
        <div className="metric connectivity">
          <span className="metric-icon">{getConnectivityIcon(metrics.connectivity.signal_strength)}</span>
          <div className="metric-data">
            <span className="metric-value">{metrics.connectivity.ping_time}ms</span>
            <span className="metric-label">Ping</span>
          </div>
        </div>

        <div className="metric performance">
          <span className="metric-icon">⚡</span>
          <div className="metric-data">
            <span className="metric-value">{metrics.performance.cpu_usage}%</span>
            <span className="metric-label">CPU</span>
          </div>
        </div>

        <div className="metric sensors">
          <span className="metric-icon">📡</span>
          <div className="metric-data">
            <span className="metric-value">{metrics.sensors.active}</span>
            <span className="metric-label">Sensors</span>
          </div>
        </div>

        <div className="metric alerts">
          <span className="metric-icon">🚨</span>
          <div className="metric-data">
            <span className="metric-value">{metrics.alerts.active}</span>
            <span className="metric-label">Alerts</span>
          </div>
        </div>
      </div>

      <div className="esp-actions">
        <button onClick={() => navigate(`/devices/${metrics.device.id}`)}>
          Details
        </button>
        {metrics.device.status === 'offline' && (
          <button onClick={() => handleReconnect(metrics.device.id)}>
            Reconnect
          </button>
        )}
      </div>
    </Card>
  );
};
```

#### **5.3 Advanced Alert-Management System**
```typescript
// Alert Priorisierung und intelligente Gruppierung
interface AlertGroup {
  id: string;
  type: 'device_cluster' | 'sensor_type' | 'system_wide' | 'custom';
  title: string;
  description: string;
  alerts: Alert[];
  priority: 'low' | 'medium' | 'high' | 'critical';
  impact_score: number; // 1-100, wie viele Devices/Systeme betroffen
  suggested_actions: AlertAction[];
}

interface AlertAction {
  id: string;
  type: 'acknowledge' | 'reconnect' | 'reset' | 'escalate' | 'ignore';
  label: string;
  description: string;
  automated?: boolean; // Kann automatisch ausgeführt werden
  requires_confirmation: boolean;
}

class AlertManager {
  private alerts: Alert[] = [];

  // Intelligente Alert-Gruppierung
  groupAlerts(alerts: Alert[]): AlertGroup[] {
    const groups: AlertGroup[] = [];

    // Gruppiere nach ESP-ID für Device-bezogene Alerts
    const deviceGroups = this.groupByDevice(alerts);
    groups.push(...deviceGroups);

    // Gruppiere nach Alert-Typ für systemweite Issues
    const typeGroups = this.groupByType(alerts);
    groups.push(...typeGroups);

    // Sortiere nach Impact und Priority
    return groups.sort((a, b) => {
      if (a.priority !== b.priority) {
        const priorityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
        return priorityOrder[b.priority] - priorityOrder[a.priority];
      }
      return b.impact_score - a.impact_score;
    });
  }

  private groupByDevice(alerts: Alert[]): AlertGroup[] {
    const deviceMap = new Map<string, Alert[]>();

    alerts.forEach(alert => {
      const deviceId = alert.source.split(':')[0]; // ESP_01:sensor_05 -> ESP_01
      if (!deviceMap.has(deviceId)) {
        deviceMap.set(deviceId, []);
      }
      deviceMap.get(deviceId)!.push(alert);
    });

    return Array.from(deviceMap.entries()).map(([deviceId, deviceAlerts]) => ({
      id: `device_${deviceId}`,
      type: 'device_cluster',
      title: `Issues with ${deviceId}`,
      description: `${deviceAlerts.length} alerts for device ${deviceId}`,
      alerts: deviceAlerts,
      priority: this.calculateGroupPriority(deviceAlerts),
      impact_score: deviceAlerts.length,
      suggested_actions: this.getDeviceActions(deviceId, deviceAlerts)
    }));
  }

  private calculateGroupPriority(alerts: Alert[]): Alert['priority'] {
    const priorities = alerts.map(a => a.priority);
    if (priorities.includes('critical')) return 'critical';
    if (priorities.includes('high')) return 'high';
    if (priorities.includes('medium')) return 'medium';
    return 'low';
  }

  private getDeviceActions(deviceId: string, alerts: Alert[]): AlertAction[] {
    const hasOfflineAlerts = alerts.some(a => a.type === 'device_offline');
    const hasSensorAlerts = alerts.some(a => a.type === 'sensor_failure');

    const actions: AlertAction[] = [
      {
        id: 'acknowledge_all',
        type: 'acknowledge',
        label: 'Acknowledge All',
        description: 'Mark all alerts in this group as acknowledged',
        requires_confirmation: false
      }
    ];

    if (hasOfflineAlerts) {
      actions.push({
        id: 'reconnect_device',
        type: 'reconnect',
        label: 'Reconnect Device',
        description: 'Attempt to reconnect the offline device',
        automated: true,
        requires_confirmation: true
      });
    }

    if (hasSensorAlerts) {
      actions.push({
        id: 'reset_sensors',
        type: 'reset',
        label: 'Reset Sensors',
        description: 'Reset all sensors on this device',
        requires_confirmation: true
      });
    }

    return actions;
  }
}

// Alert Dashboard Component
const AlertDashboard: React.FC = () => {
  const [alertGroups, setAlertGroups] = useState<AlertGroup[]>([]);
  const [filter, setFilter] = useState<AlertFilter>('all');

  useEffect(() => {
    const loadAlerts = async () => {
      const alerts = await api.get('/api/v1/alerts');
      const manager = new AlertManager();
      const groups = manager.groupAlerts(alerts);
      setAlertGroups(groups);
    };

    loadAlerts();
  }, []);

  const filteredGroups = alertGroups.filter(group => {
    if (filter === 'all') return true;
    return group.priority === filter;
  });

  return (
    <div className="alert-dashboard">
      <div className="alert-filters">
        <button onClick={() => setFilter('all')}>All ({alertGroups.length})</button>
        <button onClick={() => setFilter('critical')}>Critical</button>
        <button onClick={() => setFilter('high')}>High</button>
        <button onClick={() => setFilter('medium')}>Medium</button>
        <button onClick={() => setFilter('low')}>Low</button>
      </div>

      <div className="alert-groups">
        {filteredGroups.map(group => (
          <AlertGroupCard key={group.id} group={group} />
        ))}
      </div>
    </div>
  );
};
```

#### **5.4 Performance-Metriken & Analytics**
```typescript
// Performance Monitoring Dashboard
interface PerformanceMetrics {
  api: {
    response_times: {
      avg: number; // ms
      p95: number; // 95th percentile
      p99: number; // 99th percentile
    };
    error_rate: number; // percentage
    throughput: number; // requests per second
  };
  websocket: {
    connections: number;
    message_rate: number; // messages per second
    latency: number; // ms
  };
  ui: {
    load_time: number; // ms
    render_time: number; // ms
    memory_usage: number; // MB
  };
  devices: {
    avg_response_time: number; // ms
    success_rate: number; // percentage
    data_rate: number; // KB/s
  };
}

const PerformanceDashboard: React.FC<{ metrics: PerformanceMetrics }> = ({ metrics }) => {
  const getStatusColor = (value: number, thresholds: { good: number; warning: number }) => {
    if (value <= thresholds.good) return '#10B981';
    if (value <= thresholds.warning) return '#F59E0B';
    return '#EF4444';
  };

  return (
    <div className="performance-dashboard">
      <div className="metric-section">
        <h3>API Performance</h3>
        <div className="metrics-grid">
          <MetricCard
            title="Avg Response Time"
            value={`${metrics.api.response_times.avg}ms`}
            status={getStatusColor(metrics.api.response_times.avg, { good: 200, warning: 500 })}
            trend="stable"
          />
          <MetricCard
            title="Error Rate"
            value={`${metrics.api.error_rate}%`}
            status={getStatusColor(metrics.api.error_rate, { good: 1, warning: 5 })}
            trend="down"
          />
          <MetricCard
            title="Throughput"
            value={`${metrics.api.throughput} req/s`}
            status="normal"
            trend="up"
          />
        </div>
      </div>

      <div className="metric-section">
        <h3>Real-time Performance</h3>
        <div className="metrics-grid">
          <MetricCard
            title="WebSocket Connections"
            value={metrics.websocket.connections.toString()}
            status="normal"
            trend="up"
          />
          <MetricCard
            title="Message Rate"
            value={`${metrics.websocket.message_rate} msg/s`}
            status="normal"
            trend="stable"
          />
        </div>
      </div>

      <div className="metric-section">
        <h3>Device Performance</h3>
        <div className="metrics-grid">
          <MetricCard
            title="Device Response Time"
            value={`${metrics.devices.avg_response_time}ms`}
            status={getStatusColor(metrics.devices.avg_response_time, { good: 100, warning: 300 })}
            trend="stable"
          />
          <MetricCard
            title="Device Success Rate"
            value={`${metrics.devices.success_rate}%`}
            status={getStatusColor(100 - metrics.devices.success_rate, { good: 1, warning: 5 })}
            trend="up"
          />
        </div>
      </div>
    </div>
  );
};
```

#### **5.5 Trend-Analysis & Predictive Monitoring**
```typescript
// Trend Analysis mit historischen Daten
interface TrendData {
  metric: string;
  timeframe: '1h' | '24h' | '7d' | '30d';
  data: {
    timestamp: string;
    value: number;
  }[];
  trend: 'up' | 'down' | 'stable';
  change_percentage: number;
  prediction?: {
    next_hour: number;
    confidence: number; // 0-100
  };
}

class TrendAnalyzer {
  analyzeTrend(data: { timestamp: string; value: number }[]): TrendAnalysis {
    if (data.length < 2) return { trend: 'stable', change_percentage: 0 };

    const firstHalf = data.slice(0, Math.floor(data.length / 2));
    const secondHalf = data.slice(Math.floor(data.length / 2));

    const firstAvg = firstHalf.reduce((sum, d) => sum + d.value, 0) / firstHalf.length;
    const secondAvg = secondHalf.reduce((sum, d) => sum + d.value, 0) / secondHalf.length;

    const change = ((secondAvg - firstAvg) / firstAvg) * 100;
    const trend = Math.abs(change) < 5 ? 'stable' :
                 change > 0 ? 'up' : 'down';

    return {
      trend,
      change_percentage: Math.abs(change)
    };
  }

  predictNextValue(data: { timestamp: string; value: number }[]): Prediction | null {
    if (data.length < 10) return null;

    // Simple linear regression für Trend-Vorhersage
    const n = data.length;
    const sumX = data.reduce((sum, d, i) => sum + i, 0);
    const sumY = data.reduce((sum, d) => sum + d.value, 0);
    const sumXY = data.reduce((sum, d, i) => sum + i * d.value, 0);
    const sumXX = data.reduce((sum, d, i) => sum + i * i, 0);

    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;

    const nextValue = intercept + slope * n;

    // Confidence basierend auf Datenkonsistenz
    const variance = data.reduce((sum, d, i) => {
      const predicted = intercept + slope * i;
      return sum + Math.pow(d.value - predicted, 2);
    }, 0) / n;
    const confidence = Math.max(0, Math.min(100, 100 - variance));

    return {
      next_hour: nextValue,
      confidence: Math.round(confidence)
    };
  }
}

// Trend Visualization Component
const TrendChart: React.FC<{ data: TrendData }> = ({ data }) => {
  const analyzer = new TrendAnalyzer();
  const trend = analyzer.analyzeTrend(data.data);
  const prediction = analyzer.predictNextValue(data.data);

  return (
    <div className="trend-chart">
      <div className="trend-header">
        <h4>{data.metric}</h4>
        <div className="trend-info">
          <span className={`trend-indicator trend--${trend.trend}`}>
            {trend.trend === 'up' && '↗️'}
            {trend.trend === 'down' && '↘️'}
            {trend.trend === 'stable' && '➡️'}
            {trend.change_percentage.toFixed(1)}%
          </span>
        </div>
      </div>

      <div className="chart-container">
        {/* Line Chart mit Trend-Linie */}
        <LineChart data={data.data} />

        {prediction && (
          <div className="prediction-overlay">
            <div className="prediction-line" style={{ left: '100%' }} />
            <div className="prediction-label">
              Prediction: {prediction.next_hour.toFixed(1)}
              <br />
              Confidence: {prediction.confidence}%
            </div>
          </div>
        )}
      </div>

      <div className="trend-actions">
        <select value={data.timeframe} onChange={(e) => setTimeframe(e.target.value)}>
          <option value="1h">Last Hour</option>
          <option value="24h">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      </div>
    </div>
  );
};
```

---

## 🔄 **Sektion 6: State-Management Architektur**

#### **6.1 Zentraler Dashboard-Store**
```typescript
// Zustand Store für Dashboard State Management
interface DashboardState {
  // Core Data
  systemStatus: 'operational' | 'warning' | 'critical' | 'offline';
  lastUpdate: Date;
  kpis: KPICard[];
  devices: ESPDevice[];
  alerts: Alert[];

  // UI State
  loading: boolean;
  error: string | null;
  selectedTimeframe: '1h' | '24h' | '7d' | '30d';
  filters: {
    deviceStatus: string[];
    alertPriority: string[];
    zones: string[];
  };

  // Connection State
  websocketConnected: boolean;
  autoRefreshEnabled: boolean;
  refreshInterval: number;

  // User Preferences
  layout: 'grid' | 'list' | 'compact';
  theme: 'light' | 'dark' | 'auto';
  notifications: {
    sound: boolean;
    desktop: boolean;
    criticalOnly: boolean;
  };
}

class DashboardStore {
  private state: DashboardState;
  private listeners: Set<Function> = new Set();

  constructor(initialState: Partial<DashboardState>) {
    this.state = {
      systemStatus: 'offline',
      lastUpdate: new Date(),
      kpis: [],
      devices: [],
      alerts: [],
      loading: false,
      error: null,
      selectedTimeframe: '24h',
      filters: {
        deviceStatus: [],
        alertPriority: [],
        zones: []
      },
      websocketConnected: false,
      autoRefreshEnabled: true,
      refreshInterval: 30000,
      layout: 'grid',
      theme: 'auto',
      notifications: {
        sound: true,
        desktop: true,
        criticalOnly: false
      },
      ...initialState
    };
  }

  // State Updates
  setSystemStatus(status: DashboardState['systemStatus']) {
    this.updateState({ systemStatus: status });
  }

  setKPIs(kpis: KPICard[]) {
    this.updateState({ kpis });
  }

  updateDevice(deviceId: string, updates: Partial<ESPDevice>) {
    const devices = this.state.devices.map(device =>
      device.id === deviceId ? { ...device, ...updates } : device
    );
    this.updateState({ devices });
  }

  addAlert(alert: Alert) {
    this.updateState({
      alerts: [...this.state.alerts, alert]
    });
  }

  acknowledgeAlert(alertId: string, userId: string) {
    const alerts = this.state.alerts.map(alert =>
      alert.id === alertId
        ? { ...alert, acknowledged: true, acknowledged_by: userId, acknowledged_at: new Date().toISOString() }
        : alert
    );
    this.updateState({ alerts });
  }

  // Filter Management
  setFilters(filters: Partial<DashboardState['filters']>) {
    this.updateState({
      filters: { ...this.state.filters, ...filters }
    });
  }

  // Computed Properties
  get filteredDevices(): ESPDevice[] {
    return this.state.devices.filter(device => {
      if (this.state.filters.deviceStatus.length > 0 &&
          !this.state.filters.deviceStatus.includes(device.status)) {
        return false;
      }
      if (this.state.filters.zones.length > 0 &&
          !this.state.filters.zones.includes(device.location?.zone || '')) {
        return false;
      }
      return true;
    });
  }

  get filteredAlerts(): Alert[] {
    return this.state.alerts.filter(alert => {
      if (this.state.filters.alertPriority.length > 0 &&
          !this.state.filters.alertPriority.includes(alert.priority)) {
        return false;
      }
      return true;
    });
  }

  get criticalAlertsCount(): number {
    return this.state.alerts.filter(alert =>
      alert.priority === 'critical' && !alert.acknowledged
    ).length;
  }

  get offlineDevicesCount(): number {
    return this.state.devices.filter(device => device.status === 'offline').length;
  }

  // Persistence
  async saveToStorage() {
    const preferences = {
      layout: this.state.layout,
      theme: this.state.theme,
      notifications: this.state.notifications,
      refreshInterval: this.state.refreshInterval,
      autoRefreshEnabled: this.state.autoRefreshEnabled
    };

    localStorage.setItem('dashboard-preferences', JSON.stringify(preferences));
  }

  async loadFromStorage() {
    try {
      const stored = localStorage.getItem('dashboard-preferences');
      if (stored) {
        const preferences = JSON.parse(stored);
        this.updateState(preferences);
      }
    } catch (error) {
      console.warn('Failed to load dashboard preferences:', error);
    }
  }

  // Subscriber Pattern
  subscribe(listener: Function) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private updateState(updates: Partial<DashboardState>) {
    this.state = { ...this.state, ...updates, lastUpdate: new Date() };
    this.notifyListeners();
  }

  private notifyListeners() {
    this.listeners.forEach(listener => listener(this.state));
  }
}

// Global Store Instance
export const dashboardStore = new DashboardStore({});
```

#### **6.2 WebSocket State Integration**
```typescript
// WebSocket State Manager
class WebSocketStateManager {
  constructor(private store: DashboardStore) {}

  handleConnectionEvent(connected: boolean) {
    this.store.updateState({ websocketConnected: connected });
  }

  handleSystemHealthEvent(event: SystemHealthEvent) {
    this.store.setSystemStatus(event.data.status);
  }

  handleESPStatusEvent(event: ESPStatusEvent) {
    this.store.updateDevice(event.data.esp_id, {
      status: event.data.status,
      last_seen: event.data.timestamp
    });
  }

  handleAlertEvent(event: AlertEvent) {
    if (event.action === 'created') {
      this.store.addAlert(event.data);
      this.handleAlertNotification(event.data);
    }
  }

  handleKPIUpdateEvent(event: KPIUpdateEvent) {
    this.store.setKPIs(event.data.kpis);
  }

  private handleAlertNotification(alert: Alert) {
    if (this.store.state.notifications.desktop &&
        (alert.priority === 'critical' || !this.store.state.notifications.criticalOnly)) {
      this.showDesktopNotification(alert);
    }

    if (this.store.state.notifications.sound) {
      this.playAlertSound(alert.priority);
    }
  }

  private showDesktopNotification(alert: Alert) {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(`IoT Alert: ${alert.title}`, {
        body: alert.message,
        icon: '/alert-icon.png',
        tag: alert.id
      });
    }
  }

  private playAlertSound(priority: Alert['priority']) {
    const audio = new Audio(`/sounds/alert-${priority}.mp3`);
    audio.volume = 0.3;
    audio.play().catch(() => {
      // Ignore audio play errors (user interaction required)
    });
  }
}
```

#### **6.3 React Integration mit Custom Hooks**
```typescript
// Custom Hook für Dashboard State
export const useDashboard = () => {
  const [state, setState] = useState<DashboardState>(dashboardStore.state);

  useEffect(() => {
    const unsubscribe = dashboardStore.subscribe(setState);
    return unsubscribe;
  }, []);

  return {
    ...state,
    // Computed values
    filteredDevices: dashboardStore.filteredDevices,
    filteredAlerts: dashboardStore.filteredAlerts,
    criticalAlertsCount: dashboardStore.criticalAlertsCount,
    offlineDevicesCount: dashboardStore.offlineDevicesCount,

    // Actions
    setFilters: (filters: Partial<DashboardState['filters']>) =>
      dashboardStore.setFilters(filters),
    acknowledgeAlert: (alertId: string) =>
      dashboardStore.acknowledgeAlert(alertId, 'current-user'),
    updateDevice: (deviceId: string, updates: Partial<ESPDevice>) =>
      dashboardStore.updateDevice(deviceId, updates),
    savePreferences: () => dashboardStore.saveToStorage(),
    loadPreferences: () => dashboardStore.loadFromStorage()
  };
};

// Hook für WebSocket Connection
export const useWebSocket = () => {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<Date | null>(null);

  useEffect(() => {
    const wsManager = new WebSocketStateManager(dashboardStore);

    const connect = () => {
      // WebSocket connection logic here
      setConnected(true);
    };

    connect();

    // Heartbeat to track connection
    const heartbeat = setInterval(() => {
      setLastMessage(new Date());
    }, 30000);

    return () => {
      clearInterval(heartbeat);
      // Cleanup WebSocket connection
    };
  }, []);

  return { connected, lastMessage };
};

// Hook für Auto-Refresh
export const useAutoRefresh = (enabled: boolean = true) => {
  const refresh = useCallback(async () => {
    try {
      const data = await api.get('/api/v1/dashboard');
      dashboardStore.setState(data);
    } catch (error) {
      console.error('Auto-refresh failed:', error);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const interval = setInterval(refresh, dashboardStore.state.refreshInterval);
    return () => clearInterval(interval);
  }, [enabled, refresh]);

  return { refresh, manualRefresh: refresh };
};
```

---

## 📊 **Sektion 7: Data-Models & TypeScript Interfaces**

#### **7.1 Core Data Models**
```typescript
// Base Types
export type DeviceStatus = 'online' | 'offline' | 'safe_mode' | 'error';
export type AlertPriority = 'low' | 'medium' | 'high' | 'critical';
export type SystemStatus = 'operational' | 'warning' | 'critical' | 'offline';
export type Timeframe = '1h' | '24h' | '7d' | '30d';

// ESP Device Model
export interface ESPDevice {
  readonly id: string;
  name: string;
  status: DeviceStatus;
  ip_address?: string;
  mac_address: string;
  firmware_version: string;
  hardware_version: string;
  location?: {
    zone: string;
    position: string;
    coordinates?: {
      lat: number;
      lng: number;
    };
  };
  last_seen: string; // ISO 8601 timestamp
  uptime_seconds?: number;
  config: DeviceConfig;
  metadata: {
    first_seen: string;
    last_config_update: string;
    restart_count: number;
    power_cycles: number;
  };
}

// Device Configuration
export interface DeviceConfig {
  update_interval_seconds: number;
  emergency_stop_enabled: boolean;
  sensors_enabled: string[]; // Array von Sensor-IDs
  wifi_ssid?: string;
  wifi_password?: string; // Nur bei Updates, nie in Responses
  mqtt_broker?: string;
  mqtt_port?: number;
  mqtt_topic_prefix?: string;
  log_level: 'debug' | 'info' | 'warning' | 'error';
  auto_reconnect: boolean;
  watchdog_enabled: boolean;
}

// Sensor Model
export interface Sensor {
  readonly id: string;
  type: 'temperature' | 'humidity' | 'pressure' | 'motion' | 'power' | 'voltage' | 'current' | 'custom';
  name: string;
  unit: string;
  description?: string;

  // Value Ranges
  min_value?: number;
  max_value?: number;
  precision?: number; // Dezimalstellen

  // Thresholds
  threshold_warning?: number;
  threshold_critical?: number;
  threshold_direction?: 'above' | 'below' | 'range'; // Richtung für Threshold-Verletzung

  // Current Readings
  current_value?: number;
  last_reading: string;
  status: 'normal' | 'warning' | 'critical' | 'offline' | 'error';

  // Metadata
  metadata: {
    manufacturer?: string;
    model?: string;
    calibration_date?: string;
    accuracy?: string;
  };
}

// Alert Model
export interface Alert {
  readonly id: string;
  type: 'device_offline' | 'sensor_failure' | 'value_out_of_range' | 'system_error' | 'network_issue' | 'power_failure' | 'custom';
  priority: AlertPriority;
  title: string;
  message: string;
  description?: string; // Detaillierte Beschreibung

  source: string; // "ESP_01:sensor_temp" oder "ESP_02" oder "system:database"
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  resolved_at?: string;

  created_at: string;
  updated_at: string;

  metadata?: Record<string, any>; // Zusätzliche Alert-Daten
  tags?: string[]; // Für Filterung und Suche
}

// System Metrics
export interface SystemMetrics {
  timestamp: string;

  // Server Metrics
  cpu: {
    usage: number; // Percentage
    temperature: number; // Celsius
    cores: number;
    load_average: [number, number, number]; // 1min, 5min, 15min
  };

  memory: {
    used: number; // MB
    total: number; // MB
    percentage: number;
    swap_used?: number;
    swap_total?: number;
  };

  storage: {
    used: number; // GB
    total: number; // GB
    percentage: number;
    filesystems: Array<{
      mount: string;
      used: number;
      total: number;
    }>;
  };

  network: {
    status: 'online' | 'degraded' | 'offline';
    latency_ms: number;
    bandwidth_up: number; // Mbps
    bandwidth_down: number; // Mbps
    interfaces: Array<{
      name: string;
      ip: string;
      status: 'up' | 'down';
    }>;
  };

  services: {
    database: 'up' | 'down' | 'degraded';
    websocket: 'up' | 'down' | 'degraded';
    api: 'up' | 'down' | 'degraded';
    mqtt_broker: 'up' | 'down' | 'degraded';
    redis?: 'up' | 'down' | 'degraded';
  };

  uptime: {
    seconds: number;
    formatted: string;
  };
}

// KPI Model
export interface KPICard {
  readonly id: string;
  title: string;
  value: number | string;
  unit?: string;
  status: 'normal' | 'warning' | 'critical';
  icon: string;
  trend?: 'up' | 'down' | 'stable';
  change_percentage?: number;
  description?: string;
  onClick?: () => void;
  metadata?: {
    calculation_method?: string;
    last_updated: string;
    data_points?: number;
  };
}

// Dashboard Response
export interface DashboardResponse {
  system_status: SystemStatus;
  last_update: string;
  kpis: KPICard[];
  devices: ESPDevice[];
  alerts: Alert[];
  system_metrics: SystemMetrics;

  // Optional: Performance Data
  performance?: {
    api_response_time: number;
    websocket_connections: number;
    cache_hit_rate: number;
  };

  // Optional: Trend Data
  trends?: {
    device_count: TrendData;
    alert_rate: TrendData;
    system_load: TrendData;
  };
}

// Trend Data Model
export interface TrendData {
  metric: string;
  timeframe: Timeframe;
  data: Array<{
    timestamp: string;
    value: number;
  }>;
  trend: 'up' | 'down' | 'stable';
  change_percentage: number;
  statistics: {
    min: number;
    max: number;
    avg: number;
    std_dev: number;
  };
  prediction?: {
    next_value: number;
    confidence: number;
    based_on_hours: number;
  };
}
```

#### **7.2 API Request/Response Models**
```typescript
// API Request Models
export interface CreateDeviceRequest {
  name: string;
  mac_address: string;
  location?: {
    zone: string;
    position?: string;
  };
  config?: Partial<DeviceConfig>;
}

export interface UpdateDeviceRequest {
  name?: string;
  location?: {
    zone?: string;
    position?: string;
  };
  config?: Partial<DeviceConfig>;
}

export interface CreateAlertRequest {
  type: Alert['type'];
  priority: AlertPriority;
  title: string;
  message: string;
  source: string;
  metadata?: Record<string, any>;
  tags?: string[];
}

export interface AcknowledgeAlertRequest {
  user_id?: string;
  comment?: string;
  resolution?: string;
}

export interface SystemControlRequest {
  action: 'emergency_stop' | 'restart' | 'maintenance_mode';
  reason: string;
  affected_devices?: string[];
  duration_minutes?: number; // Für maintenance mode
}

// API Response Models
export interface APIResponse<T = any> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  meta?: {
    timestamp: string;
    request_id: string;
    processing_time_ms?: number;
  };
}

export interface PaginatedResponse<T> extends APIResponse<T[]> {
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

export interface DevicesResponse extends PaginatedResponse<ESPDevice> {
  summary: {
    total: number;
    online: number;
    offline: number;
    safe_mode: number;
    error: number;
  };
}

export interface AlertsResponse extends PaginatedResponse<Alert> {
  summary: {
    total: number;
    unacknowledged: number;
    by_priority: Record<AlertPriority, number>;
    by_type: Record<string, number>;
  };
}

// WebSocket Message Models
export interface WebSocketMessage {
  type: string;
  data: any;
  timestamp: string;
  sequence_id?: number;
}

export interface SystemHealthEvent extends WebSocketMessage {
  type: 'system_health';
  data: {
    status: SystemStatus;
    timestamp: string;
    changes: Partial<SystemMetrics>;
  };
}

export interface ESPStatusEvent extends WebSocketMessage {
  type: 'esp_status';
  data: {
    esp_id: string;
    status: DeviceStatus;
    timestamp: string;
    previous_status?: DeviceStatus;
    metadata?: {
      reason?: string;
      reconnect_attempts?: number;
    };
  };
}

export interface AlertEvent extends WebSocketMessage {
  type: 'alert';
  action: 'created' | 'acknowledged' | 'resolved' | 'updated';
  data: Alert;
}

export interface KPIUpdateEvent extends WebSocketMessage {
  type: 'kpi_update';
  data: {
    timestamp: string;
    kpis: KPICard[];
    changes: Record<string, { old: any; new: any }>;
  };
}

export interface SensorUpdateEvent extends WebSocketMessage {
  type: 'sensor_update';
  data: {
    esp_id: string;
    sensor_id: string;
    readings: Record<string, number>; // key: sensor_type, value: reading
    timestamp: string;
  };
}
```

#### **7.3 Validation Schemas**
```typescript
// Runtime Validation mit Zod oder ähnlichem
import { z } from 'zod';

// Device Validation
export const DeviceSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1).max(50),
  status: z.enum(['online', 'offline', 'safe_mode', 'error']),
  ip_address: z.string().ip().optional(),
  mac_address: z.string().regex(/^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/),
  firmware_version: z.string().min(1),
  hardware_version: z.string().min(1),
  location: z.object({
    zone: z.string().min(1),
    position: z.string().optional(),
    coordinates: z.object({
      lat: z.number().min(-90).max(90),
      lng: z.number().min(-180).max(180)
    }).optional()
  }).optional(),
  last_seen: z.string().datetime(),
  uptime_seconds: z.number().positive().optional(),
  config: DeviceConfigSchema
});

// Alert Validation
export const AlertSchema = z.object({
  id: z.string().uuid(),
  type: z.enum(['device_offline', 'sensor_failure', 'value_out_of_range', 'system_error', 'network_issue', 'power_failure', 'custom']),
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  title: z.string().min(1).max(100),
  message: z.string().min(1).max(500),
  source: z.string().min(1),
  acknowledged: z.boolean(),
  acknowledged_by: z.string().optional(),
  acknowledged_at: z.string().datetime().optional(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  tags: z.array(z.string()).optional()
});

// KPI Validation
export const KPISchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1).max(50),
  value: z.union([z.number(), z.string()]),
  unit: z.string().optional(),
  status: z.enum(['normal', 'warning', 'critical']),
  icon: z.string().min(1),
  trend: z.enum(['up', 'down', 'stable']).optional(),
  change_percentage: z.number().optional()
});

// Type Guards für Runtime Type Checking
export const isESPDevice = (obj: any): obj is ESPDevice => {
  return DeviceSchema.safeParse(obj).success;
};

export const isAlert = (obj: any): obj is Alert => {
  return AlertSchema.safeParse(obj).success;
};

export const isKPICard = (obj: any): obj is KPICard => {
  return KPISchema.safeParse(obj).success;
};
```

---

## ⚠️ **Sektion 8: Error-Handling & Resilience**

#### **8.1 Fehler-Klassifikation**
```typescript
// Error Types Hierarchy
export class IoTError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500,
    public details?: any
  ) {
    super(message);
    this.name = 'IoTError';
  }
}

export class NetworkError extends IoTError {
  constructor(message: string, details?: any) {
    super(message, 'NETWORK_ERROR', 0, details);
    this.name = 'NetworkError';
  }
}

export class DeviceError extends IoTError {
  constructor(message: string, public deviceId: string, details?: any) {
    super(message, 'DEVICE_ERROR', 502, details);
    this.name = 'DeviceError';
  }
}

export class ValidationError extends IoTError {
  constructor(message: string, public field: string, details?: any) {
    super(message, 'VALIDATION_ERROR', 400, details);
    this.name = 'ValidationError';
  }
}

export class AuthenticationError extends IoTError {
  constructor(message: string = 'Authentication required') {
    super(message, 'AUTHENTICATION_ERROR', 401);
    this.name = 'AuthenticationError';
  }
}

export class AuthorizationError extends IoTError {
  constructor(message: string = 'Insufficient permissions') {
    super(message, 'AUTHORIZATION_ERROR', 403);
    this.name = 'AuthorizationError';
  }
}

export class NotFoundError extends IoTError {
  constructor(resource: string, id: string) {
    super(`${resource} with id ${id} not found`, 'NOT_FOUND', 404, { resource, id });
    this.name = 'NotFoundError';
  }
}

export class RateLimitError extends IoTError {
  constructor(message: string = 'Rate limit exceeded', public retryAfter?: number) {
    super(message, 'RATE_LIMIT_ERROR', 429, { retryAfter });
    this.name = 'RateLimitError';
  }
}
```

#### **8.2 Error Boundary Component**
```typescript
// React Error Boundary für Dashboard
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: any;
}

class DashboardErrorBoundary extends Component<{}, ErrorBoundaryState> {
  constructor(props: {}) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    this.setState({ errorInfo });

    // Log error to monitoring service
    errorReporting.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo.componentStack
        }
      },
      tags: {
        component: 'DashboardErrorBoundary'
      }
    });

    // Send error to dashboard analytics
    dashboardEvents.emit({
      type: 'error',
      payload: {
        error: error.message,
        component: 'Dashboard',
        stack: error.stack
      },
      timestamp: new Date()
    });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    // Force dashboard refresh
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-boundary__content">
            <div className="error-boundary__icon">⚠️</div>
            <h2>Something went wrong</h2>
            <p>The dashboard encountered an unexpected error.</p>

            {process.env.NODE_ENV === 'development' && (
              <details className="error-boundary__details">
                <summary>Error Details</summary>
                <pre>{this.state.error?.stack}</pre>
              </details>
            )}

            <div className="error-boundary__actions">
              <button onClick={this.handleRetry} className="retry-button">
                Reload Dashboard
              </button>
              <button onClick={() => window.location.href = '/'} className="home-button">
                Go to Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

#### **8.3 API Error Handler mit Retry Logic**
```typescript
// Enhanced API Error Handler
class APIErrorHandler {
  static async handle<T>(
    apiCall: () => Promise<T>,
    options: {
      maxRetries?: number;
      retryDelay?: number;
      exponentialBackoff?: boolean;
      retryCondition?: (error: any) => boolean;
      fallbackValue?: T;
    } = {}
  ): Promise<T> {
    const {
      maxRetries = 3,
      retryDelay = 1000,
      exponentialBackoff = true,
      retryCondition = (error) => error.status >= 500 || error.code === 'NETWORK_ERROR',
      fallbackValue
    } = options;

    let lastError: any;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        return await apiCall();
      } catch (error) {
        lastError = error;

        // Don't retry if it's not a retryable error
        if (!retryCondition(error)) {
          break;
        }

        // Don't retry on last attempt
        if (attempt === maxRetries) {
          break;
        }

        // Calculate delay
        const delay = exponentialBackoff
          ? retryDelay * Math.pow(2, attempt - 1) + Math.random() * 1000 // Jitter
          : retryDelay;

        console.warn(`API call failed (attempt ${attempt}/${maxRetries}), retrying in ${delay}ms:`, error.message);

        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }

    // If we have a fallback value, return it
    if (fallbackValue !== undefined) {
      console.warn('Using fallback value due to API error:', lastError.message);
      return fallbackValue;
    }

    // Transform error to IoTError
    throw this.transformError(lastError);
  }

  private static transformError(error: any): IoTError {
    if (error.response) {
      const { status, data } = error.response;

      switch (status) {
        case 400:
          return new ValidationError(data.message || 'Validation error', data.field, data.details);
        case 401:
          return new AuthenticationError(data.message);
        case 403:
          return new AuthorizationError(data.message);
        case 404:
          return new NotFoundError(data.resource || 'Resource', data.id || 'unknown');
        case 429:
          return new RateLimitError(data.message, data.retryAfter);
        case 502:
        case 503:
        case 504:
          return new DeviceError(data.message || 'Device communication error', data.deviceId, data.details);
        default:
          return new IoTError(data.message || 'API error', 'API_ERROR', status, data.details);
      }
    } else if (error.request) {
      return new NetworkError('Network request failed', {
        url: error.config?.url,
        method: error.config?.method,
        timeout: error.config?.timeout
      });
    } else {
      return new IoTError(error.message || 'Unknown error', 'UNKNOWN_ERROR', 500);
    }
  }
}

// Usage Examples
const loadDashboardData = async () => {
  return APIErrorHandler.handle(
    () => api.get('/api/v1/dashboard'),
    {
      maxRetries: 3,
      retryCondition: (error) => error.status >= 500,
      fallbackValue: {
        system_status: 'offline',
        kpis: [],
        devices: [],
        alerts: []
      }
    }
  );
};

const reconnectDevice = async (deviceId: string) => {
  return APIErrorHandler.handle(
    () => api.post(`/api/v1/devices/${deviceId}/reconnect`),
    {
      maxRetries: 2,
      retryCondition: (error) => error.code === 'NETWORK_ERROR' || error.status === 502
    }
  );
};
```

#### **8.4 Fallback UI Patterns**
```typescript
// Fallback Components für verschiedene Error-Szenarien
const OfflineIndicator: React.FC<{ message?: string }> = ({
  message = "You're currently offline"
}) => (
  <div className="offline-indicator">
    <div className="offline-icon">📶</div>
    <div className="offline-message">{message}</div>
    <button onClick={() => window.location.reload()}>
      Retry Connection
    </button>
  </div>
);

const LoadingFallback: React.FC<{ message?: string }> = ({
  message = "Loading dashboard..."
}) => (
  <div className="loading-fallback">
    <div className="loading-spinner"></div>
    <div className="loading-message">{message}</div>
  </div>
);

const ErrorFallback: React.FC<{
  error: Error;
  retry?: () => void;
  showDetails?: boolean;
}> = ({ error, retry, showDetails = false }) => (
  <div className="error-fallback">
    <div className="error-icon">⚠️</div>
    <div className="error-title">Something went wrong</div>
    <div className="error-message">{error.message}</div>

    {showDetails && (
      <details className="error-details">
        <summary>Technical Details</summary>
        <pre>{error.stack}</pre>
      </details>
    )}

    {retry && (
      <button onClick={retry} className="retry-button">
        Try Again
      </button>
    )}
  </div>
);

// Device Card Fallback für einzelne fehlgeschlagene Devices
const DeviceCardError: React.FC<{ deviceId: string; error: string }> = ({
  deviceId, error
}) => (
  <div className="device-card device-card--error">
    <div className="device-header">
      <span className="device-name">Device {deviceId}</span>
      <span className="device-status status--error">⚠️ Error</span>
    </div>
    <div className="device-error-message">{error}</div>
    <button className="device-retry-btn" onClick={() => retryDeviceLoad(deviceId)}>
      Retry
    </button>
  </div>
);

// Hook für graceful error handling
export const useErrorHandler = () => {
  const [errors, setErrors] = useState<Map<string, Error>>(new Map());

  const handleError = useCallback((key: string, error: Error) => {
    setErrors(prev => new Map(prev.set(key, error)));

    // Auto-clear error after 10 seconds
    setTimeout(() => {
      setErrors(prev => {
        const newErrors = new Map(prev);
        newErrors.delete(key);
        return newErrors;
      });
    }, 10000);
  }, []);

  const clearError = useCallback((key: string) => {
    setErrors(prev => {
      const newErrors = new Map(prev);
      newErrors.delete(key);
      return newErrors;
    });
  }, []);

  return {
    errors,
    handleError,
    clearError,
    hasError: (key: string) => errors.has(key),
    getError: (key: string) => errors.get(key)
  };
};
```

#### **8.5 Monitoring & Alerting für Errors**
```typescript
// Error Monitoring Service
class ErrorMonitoring {
  private static instance: ErrorMonitoring;
  private errorQueue: any[] = [];
  private flushInterval: NodeJS.Timeout | null = null;

  static getInstance(): ErrorMonitoring {
    if (!ErrorMonitoring.instance) {
      ErrorMonitoring.instance = new ErrorMonitoring();
    }
    return ErrorMonitoring.instance;
  }

  trackError(error: Error, context?: any) {
    const errorData = {
      message: error.message,
      stack: error.stack,
      name: error.name,
      timestamp: new Date().toISOString(),
      userAgent: navigator.userAgent,
      url: window.location.href,
      context: context || {},
      sessionId: this.getSessionId(),
      userId: this.getUserId()
    };

    this.errorQueue.push(errorData);

    // Flush immediately for critical errors
    if (this.isCriticalError(error)) {
      this.flush();
    } else {
      this.scheduleFlush();
    }
  }

  private isCriticalError(error: Error): boolean {
    return error.name === 'IoTError' &&
           (error as IoTError).statusCode >= 500;
  }

  private scheduleFlush() {
    if (this.flushInterval) return;

    this.flushInterval = setTimeout(() => {
      this.flush();
    }, 5000); // Flush every 5 seconds
  }

  private async flush() {
    if (this.errorQueue.length === 0) return;

    const errorsToSend = [...this.errorQueue];
    this.errorQueue = [];

    if (this.flushInterval) {
      clearTimeout(this.flushInterval);
      this.flushInterval = null;
    }

    try {
      await api.post('/api/v1/errors', { errors: errorsToSend });
    } catch (error) {
      console.error('Failed to send error reports:', error);
      // Re-queue errors for next attempt
      this.errorQueue.unshift(...errorsToSend);
    }
  }

  private getSessionId(): string {
    let sessionId = sessionStorage.getItem('sessionId');
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      sessionStorage.setItem('sessionId', sessionId);
    }
    return sessionId;
  }

  private getUserId(): string | undefined {
    return localStorage.getItem('userId') || undefined;
  }
}

// Global error handler
window.addEventListener('error', (event) => {
  ErrorMonitoring.getInstance().trackError(event.error, {
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno
  });
});

window.addEventListener('unhandledrejection', (event) => {
  const error = new Error(event.reason?.message || 'Unhandled promise rejection');
  ErrorMonitoring.getInstance().trackError(error, {
    reason: event.reason,
    promise: event.promise
  });
});
```

---

## 🎨 Design-Spezifikationen:
- **Status-Farben**: 🟢 Normal, 🟡 Warning, 🔴 Critical
- **KPI-Karten**: Hover-Effekte mit zusätzlichen Details
- **ESP-Status**: Farbkodierte Badges (Online/Offline/Error)
- **Alert-Prioritäten**: Verschiedene Icons für verschiedene Alert-Typen
- **Responsive Layout**: Verschiedene Layouts für Mobile/Desktop

## 🔧 Technische Details:
- **State-Management**: Zentraler Dashboard-Store mit WebSocket-Integration
- **Data-Aggregation**: Serverseitige Berechnung von KPIs
- **Caching-Strategy**: Optimierte Ladezeiten mit Smart-Caching
- **Alert-System**: Real-time Push-Benachrichtigungen

## 🚨 **KRITISCHE ANFORDERUNGEN:**

1. **Performance**: Dashboard muss <2s laden - ist die erste View!
2. **Real-time**: Alle Daten müssen live aktualisiert werden
3. **Reliability**: Darf nie "kaputt" aussehen - Fallbacks für alle Fehler
4. **Actionable**: Jeder KPI muss zu einer Aktion führen
5. **Mobile-First**: Muss auf allen Geräten perfekt funktionieren

## 🎯 **User-Experience Ziele:**

- **Sofortige Übersicht**: User versteht System-Status in 3 Sekunden
- **Intuitive Navigation**: Klicks führen logisch zu Detail-Views
- **Zero-Confusion**: Klare Status-Indikatoren und aussagekräftige Labels
- **Proactive Alerts**: Probleme werden bevor sie kritisch werden angezeigt
- **Personalization**: User kann Layout und angezeigte KPIs anpassen

---

**DIES IST DIE WICHTIGSTE VIEW! Erstelle eine Dokumentation, die so detailliert ist, dass ein Entwickler das perfekte Dashboard-System nachbauen kann - das Erste was User sehen und das Zentrum der gesamten Anwendung! 🏠✨**