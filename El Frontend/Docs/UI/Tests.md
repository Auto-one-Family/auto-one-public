# 🧪 Load Testing Dashboard - Vollständige UI-Dokumentation

## 🎯 Übersicht

### Route & Zweck
- **Route**: `/load-test`
- **Zweck**: Performance-Testing des Gesamtsystems durch Simulation mehrerer ESP-Geräte mit realistischen Sensor- und Aktordaten
- **Zielgruppe**: Entwickler, DevOps, QA-Teams für Systemkapazitäts-Tests
- **Primäre Features**: Bulk-Erstellung von Mock-ESPs, Simulation von Echtzeit-Daten, Live-Performance-Monitoring

### Systemarchitektur
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend UI   │────│   REST API       │────│   Database      │
│   (Vue.js)      │    │   (FastAPI)      │    │   (PostgreSQL)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌──────────────────┐
                    │  WebSocket       │
                    │  Real-time Data  │
                    └──────────────────┘
```

## 🔧 Technische Architektur

### Vue.js Komponenten-Struktur
```
LoadTestView.vue
├── LoadTestControlPanel.vue     # Steuerungsbuttons
├── LoadTestConfiguration.vue    # Testparameter-Eingabe
├── LoadTestMetrics.vue          # Live-Metriken Dashboard
├── LoadTestScenarios.vue        # Vordefinierte Szenarien
├── LoadTestProgress.vue         # Fortschrittsanzeigen
└── LoadTestResults.vue          # Testergebnisse & Export
```

### State Management (Pinia Store)
```javascript
// stores/loadTest.js
export const useLoadTestStore = defineStore('loadTest', {
  state: () => ({
    testStatus: 'stopped', // 'stopped' | 'starting' | 'running' | 'stopping'
    configuration: {
      espCount: 50,
      sensorInterval: 5000, // ms
      actuatorRatio: 0.3,
      dataRate: 'normal' // 'low' | 'normal' | 'high'
    },
    metrics: {
      cpu: 0,
      memory: 0,
      espCount: 0,
      onlineEspCount: 0,
      apiResponseTimes: {},
      websocketLatency: 0
    },
    scenarios: [...],
    progress: {
      bulkCreate: { current: 0, total: 0, status: 'idle' },
      simulation: { status: 'idle' }
    }
  }),

  actions: {
    async bulkCreateESPs(count) { /* ... */ },
    async startSimulation() { /* ... */ },
    async stopSimulation() { /* ... */ },
    async getMetrics() { /* ... */ },
    async cleanup() { /* ... */ }
  }
})
```

## 🎨 UI-Komponenten detailliert

### Hauptlayout
```vue
<template>
  <div class="load-test-dashboard">
    <!-- Header mit Status-Indikator -->
    <div class="dashboard-header">
      <h1>🧪 Load Testing Dashboard</h1>
      <div class="status-indicator" :class="testStatus">
        <span class="status-dot" :class="testStatus"></span>
        {{ statusText }}
      </div>
    </div>

    <!-- Haupt-Grid Layout -->
    <div class="dashboard-grid">
      <!-- Linke Spalte: Controls -->
      <div class="control-column">
        <LoadTestControlPanel />
        <LoadTestConfiguration />
        <LoadTestScenarios />
      </div>

      <!-- Rechte Spalte: Monitoring -->
      <div class="monitoring-column">
        <LoadTestMetrics />
        <LoadTestProgress />
      </div>
    </div>

    <!-- Bottom: Results -->
    <LoadTestResults />
  </div>
</template>
```

### Control Panel Komponente
```vue
<!-- LoadTestControlPanel.vue -->
<template>
  <div class="control-panel">
    <h3>🎛️ Test Steuerung</h3>

    <!-- Hauptsteuerung -->
    <div class="control-buttons">
      <button
        class="btn btn-primary"
        @click="bulkCreateESPs"
        :disabled="testStatus !== 'stopped'"
      >
        <i class="fas fa-cubes"></i>
        Bulk Create ESPs
      </button>

      <button
        class="btn btn-success"
        @click="startSimulation"
        :disabled="testStatus !== 'stopped' || espCount === 0"
      >
        <i class="fas fa-play"></i>
        Start Simulation
      </button>

      <button
        class="btn btn-danger"
        @click="stopSimulation"
        :disabled="testStatus === 'stopped'"
      >
        <i class="fas fa-stop"></i>
        Stop Simulation
      </button>
    </div>

    <!-- Sekundäre Aktionen -->
    <div class="secondary-buttons">
      <button class="btn btn-warning" @click="cleanup">
        <i class="fas fa-broom"></i>
        Cleanup Test Data
      </button>

      <button class="btn btn-info" @click="exportResults">
        <i class="fas fa-download"></i>
        Export Results
      </button>
    </div>

    <!-- Schnellkonfiguration -->
    <div class="quick-config">
      <label>Quick ESP Count:</label>
      <div class="quick-buttons">
        <button @click="setEspCount(10)">10</button>
        <button @click="setEspCount(50)">50</button>
        <button @click="setEspCount(100)">100</button>
        <button @click="setEspCount(500)">500</button>
      </div>
    </div>
  </div>
</template>
```

### Configuration Panel
```vue
<!-- LoadTestConfiguration.vue -->
<template>
  <div class="configuration-panel">
    <h3>⚙️ Test Konfiguration</h3>

    <!-- ESP Anzahl -->
    <div class="config-item">
      <label for="espCount">Anzahl ESPs:</label>
      <div class="input-group">
        <input
          id="espCount"
          type="number"
          v-model.number="configuration.espCount"
          min="1"
          max="1000"
          :disabled="testStatus === 'running'"
        />
        <input
          type="range"
          min="1"
          max="1000"
          step="10"
          v-model="configuration.espCount"
          :disabled="testStatus === 'running'"
        />
      </div>
      <span class="range-hint">1 - 1000 ESPs</span>
    </div>

    <!-- Sensor Interval -->
    <div class="config-item">
      <label for="sensorInterval">Sensor-Intervall:</label>
      <select
        id="sensorInterval"
        v-model="configuration.sensorInterval"
        :disabled="testStatus === 'running'"
      >
        <option :value="1000">1 Sekunde</option>
        <option :value="5000">5 Sekunden</option>
        <option :value="30000">30 Sekunden</option>
        <option :value="60000">1 Minute</option>
        <option :value="300000">5 Minuten</option>
      </select>
    </div>

    <!-- Aktoren Ratio -->
    <div class="config-item">
      <label for="actuatorRatio">Aktoren-Verhältnis:</label>
      <div class="input-group">
        <input
          id="actuatorRatio"
          type="range"
          min="0"
          max="1"
          step="0.1"
          v-model="configuration.actuatorRatio"
          :disabled="testStatus === 'running'"
        />
        <span class="percentage">{{ Math.round(configuration.actuatorRatio * 100) }}%</span>
      </div>
      <span class="range-hint">0% - 100% aktive Aktoren</span>
    </div>

    <!-- Daten-Rate -->
    <div class="config-item">
      <label for="dataRate">Daten-Rate:</label>
      <select
        id="dataRate"
        v-model="configuration.dataRate"
        :disabled="testStatus === 'running'"
      >
        <option value="low">🟢 Niedrig (Realistisch)</option>
        <option value="normal">🟡 Normal (Standard)</option>
        <option value="high">🔴 Hoch (Stress-Test)</option>
        <option value="extreme">💀 Extrem (Break-Test)</option>
      </select>
    </div>

    <!-- Sensor-Typen Auswahl -->
    <div class="config-item">
      <label>Sensor-Typen aktivieren:</label>
      <div class="checkbox-group">
        <label v-for="sensor in availableSensors" :key="sensor.id">
          <input
            type="checkbox"
            v-model="configuration.activeSensors"
            :value="sensor.id"
            :disabled="testStatus === 'running'"
          />
          {{ sensor.name }}
        </label>
      </div>
    </div>
  </div>
</template>
```

### Live Metrics Dashboard
```vue
<!-- LoadTestMetrics.vue -->
<template>
  <div class="metrics-dashboard">
    <h3>📊 Live Metriken</h3>

    <!-- System-Metriken Grid -->
    <div class="metrics-grid">
      <!-- CPU Usage -->
      <div class="metric-card">
        <div class="metric-header">
          <i class="fas fa-microchip"></i>
          <span>CPU</span>
        </div>
        <div class="metric-value">
          <span class="value">{{ metrics.cpu }}%</span>
          <span class="trend" :class="cpuTrend">
            <i :class="cpuTrendIcon"></i>
            {{ cpuChange }}%
          </span>
        </div>
        <div class="mini-chart">
          <canvas ref="cpuChart" width="100" height="30"></canvas>
        </div>
      </div>

      <!-- Memory Usage -->
      <div class="metric-card">
        <div class="metric-header">
          <i class="fas fa-memory"></i>
          <span>Memory</span>
        </div>
        <div class="metric-value">
          <span class="value">{{ formatBytes(metrics.memory) }}</span>
          <span class="trend" :class="memoryTrend">
            <i :class="memoryTrendIcon"></i>
            {{ formatBytes(memoryChange) }}
          </span>
        </div>
        <div class="mini-chart">
          <canvas ref="memoryChart" width="100" height="30"></canvas>
        </div>
      </div>

      <!-- ESP Count -->
      <div class="metric-card">
        <div class="metric-header">
          <i class="fas fa-router"></i>
          <span>ESPs</span>
        </div>
        <div class="metric-value">
          <span class="value">{{ metrics.espCount }}</span>
          <span class="sub-value">Online: {{ metrics.onlineEspCount }}</span>
        </div>
        <div class="connection-status">
          <div class="status-bar">
            <div
              class="status-fill"
              :style="{ width: connectionPercentage + '%' }"
              :class="connectionStatus"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- API Response Times -->
    <div class="api-metrics">
      <h4>API Response Times</h4>
      <div class="api-list">
        <div
          v-for="api in metrics.apiResponseTimes"
          :key="api.endpoint"
          class="api-item"
          :class="getApiStatusClass(api.responseTime)"
        >
          <span class="method">{{ api.method }}</span>
          <span class="endpoint">{{ api.endpoint }}</span>
          <span class="response-time">{{ api.responseTime }}ms</span>
          <div class="response-trend">
            <i :class="getTrendIcon(api.trend)"></i>
          </div>
        </div>
      </div>
    </div>

    <!-- WebSocket Latency -->
    <div class="websocket-metrics">
      <h4>WebSocket Verbindung</h4>
      <div class="ws-status">
        <span class="status">Latency: {{ metrics.websocketLatency }}ms</span>
        <span class="status" :class="websocketStatus">
          {{ websocketStatusText }}
        </span>
      </div>
    </div>
  </div>
</template>
```

## 🔌 Server-API Integration

### REST API Endpunkte

#### Bulk ESP Creation
```javascript
// POST /api/v1/debug/bulk-create-esps
{
  "count": 50,
  "configuration": {
    "sensor_types": ["temperature", "humidity", "pressure"],
    "actuator_ratio": 0.3,
    "location_pattern": "random", // "grid" | "random" | "clustered"
    "naming_pattern": "MOCK_ESP_{index}"
  }
}

// Response
{
  "success": true,
  "created_count": 50,
  "esp_ids": ["mock_esp_001", "mock_esp_002", ...],
  "processing_time": 2450 // ms
}
```

#### Simulation Control
```javascript
// POST /api/v1/debug/start-simulation
{
  "esp_ids": ["mock_esp_001", "mock_esp_002", ...],
  "configuration": {
    "sensor_interval": 5000,      // ms
    "data_rate": "normal",        // "low" | "normal" | "high" | "extreme"
    "realistic_data": true,       // Use realistic sensor ranges
    "actuator_simulation": true,  // Simulate actuator commands
    "error_rate": 0.02            // 2% error rate for realism
  }
}

// Response
{
  "success": true,
  "simulation_id": "sim_20241227_143022",
  "active_esps": 50,
  "estimated_load": "medium"
}
```

#### Live Metrics
```javascript
// GET /api/v1/debug/metrics
// Response
{
  "timestamp": "2024-12-27T14:30:22Z",
  "system": {
    "cpu_percent": 45.2,
    "memory_used": 2147483648,  // bytes
    "memory_total": 8589934592,  // bytes
    "disk_usage": 0.23
  },
  "application": {
    "active_connections": 1250,
    "esp_count": 50,
    "online_esps": 48,
    "sensor_updates_per_second": 245,
    "actuator_commands_per_second": 15
  },
  "api_performance": [
    {
      "endpoint": "/api/v1/esps",
      "method": "GET",
      "avg_response_time": 45,
      "p95_response_time": 120,
      "error_rate": 0.001,
      "requests_per_minute": 1200
    },
    {
      "endpoint": "/api/v1/sensor-data",
      "method": "POST",
      "avg_response_time": 8,
      "p95_response_time": 25,
      "error_rate": 0.0005,
      "requests_per_minute": 2400
    }
  ],
  "websocket": {
    "connected_clients": 1250,
    "latency_ms": 12,
    "messages_per_second": 500
  }
}
```

### WebSocket Real-time Updates
```javascript
// WebSocket: /ws/debug/metrics
{
  "type": "metrics_update",
  "data": {
    "timestamp": "2024-12-27T14:30:22Z",
    "cpu": 45.2,
    "memory": 2147483648,
    "esp_count": 50,
    "online_esps": 48,
    "api_response_times": {
      "/api/v1/esps": 45,
      "/api/v1/sensor-data": 8
    }
  }
}

{
  "type": "simulation_event",
  "data": {
    "event": "esp_connected",
    "esp_id": "mock_esp_015",
    "timestamp": "2024-12-27T14:30:25Z"
  }
}
```

## 🎯 Test-Szenarien & Monitoring

### Vordefinierte Szenarien
```javascript
const testScenarios = [
  {
    id: 'light_load',
    name: 'Light Load',
    description: 'Grundlegende Funktionalität mit minimaler Last',
    config: {
      espCount: 10,
      sensorInterval: 30000,  // 30s
      actuatorRatio: 0.1,
      dataRate: 'low',
      activeSensors: ['temperature', 'humidity']
    },
    expected: {
      cpuUsage: '< 20%',
      memoryUsage: '< 1GB',
      responseTime: '< 50ms'
    }
  },

  {
    id: 'medium_load',
    name: 'Medium Load',
    description: 'Normale Betriebslast für typische Anwendungsfälle',
    config: {
      espCount: 50,
      sensorInterval: 5000,   // 5s
      actuatorRatio: 0.3,
      dataRate: 'normal',
      activeSensors: ['temperature', 'humidity', 'pressure', 'light']
    },
    expected: {
      cpuUsage: '20-50%',
      memoryUsage: '1-3GB',
      responseTime: '< 100ms'
    }
  },

  {
    id: 'heavy_load',
    name: 'Heavy Load',
    description: 'Hohe Last für Kapazitätsgrenzen-Tests',
    config: {
      espCount: 200,
      sensorInterval: 1000,   // 1s
      actuatorRatio: 0.5,
      dataRate: 'high',
      activeSensors: ['temperature', 'humidity', 'pressure', 'light', 'motion', 'sound']
    },
    expected: {
      cpuUsage: '50-80%',
      memoryUsage: '3-6GB',
      responseTime: '< 200ms'
    }
  },

  {
    id: 'stress_test',
    name: 'Stress Test',
    description: 'Maximale Kapazität und Systemgrenzen austesten',
    config: {
      espCount: 500,
      sensorInterval: 500,    // 0.5s
      actuatorRatio: 0.8,
      dataRate: 'extreme',
      activeSensors: ['all'],
      errorSimulation: true
    },
    expected: {
      cpuUsage: '80-100%',
      memoryUsage: '6-8GB',
      responseTime: 'Variable (mit Degradation)'
    }
  }
]
```

### Monitoring & Alerting
```javascript
const monitoringThresholds = {
  cpu: {
    warning: 70,    // %
    critical: 90    // %
  },
  memory: {
    warning: 0.8,   // 80%
    critical: 0.95  // 95%
  },
  responseTime: {
    warning: 200,   // ms
    critical: 500   // ms
  },
  espConnection: {
    warning: 0.9,   // 90%
    critical: 0.75  // 75%
  }
}

const alertRules = [
  {
    condition: (metrics) => metrics.cpu > monitoringThresholds.cpu.critical,
    message: 'CPU usage critical! System may become unresponsive.',
    level: 'critical',
    action: 'auto_scale'
  },
  {
    condition: (metrics) => metrics.apiResponseTimes['/api/v1/sensor-data'] > 500,
    message: 'Sensor data API response time degraded significantly.',
    level: 'warning',
    action: 'log_detailed_metrics'
  }
]
```

## 🎨 Design-System & Styling

### CSS Custom Properties
```css
:root {
  /* Status Colors */
  --color-status-stopped: #6c757d;
  --color-status-starting: #ffc107;
  --color-status-running: #28a745;
  --color-status-error: #dc3545;

  /* Alert Colors */
  --color-alert-normal: #28a745;
  --color-alert-warning: #ffc107;
  --color-alert-critical: #dc3545;

  /* Metrics */
  --metric-card-bg: #f8f9fa;
  --metric-card-border: #dee2e6;
  --metric-value-color: #212529;
  --metric-trend-up: #28a745;
  --metric-trend-down: #dc3545;
  --metric-trend-neutral: #6c757d;
}
```

### Responsive Layout
```css
.load-test-dashboard {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
  padding: 1.5rem;
  min-height: 100vh;
}

@media (min-width: 768px) {
  .load-test-dashboard {
    grid-template-columns: 350px 1fr;
  }
}

@media (min-width: 1200px) {
  .load-test-dashboard {
    grid-template-columns: 400px 1fr;
  }
}

/* Metric Cards Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

/* Control Panel Layout */
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.control-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

@media (max-width: 480px) {
  .control-buttons {
    grid-template-columns: 1fr;
  }
}
```

### Animationen & Transitions
```css
/* Status Indicator Animation */
.status-indicator.running .status-dot {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

/* Progress Bar Animation */
.progress-bar {
  transition: width 0.3s ease-in-out;
}

/* Metric Value Updates */
.metric-value .value {
  transition: color 0.3s ease;
}

.metric-value.updating {
  animation: highlight 0.5s ease;
}

@keyframes highlight {
  0% { background-color: rgba(255, 193, 7, 0.1); }
  100% { background-color: transparent; }
}

/* Button Hover Effects */
.btn {
  transition: all 0.2s ease;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.btn:active {
  transform: translateY(0);
}
```

## 🔧 Technische Implementierung

### Mock ESP Generator
```javascript
class MockESPGenerator {
  constructor(config) {
    this.config = config;
    this.espTemplates = {
      temperature: {
        min: -20,
        max: 50,
        unit: '°C',
        precision: 1
      },
      humidity: {
        min: 0,
        max: 100,
        unit: '%',
        precision: 0
      },
      pressure: {
        min: 950,
        max: 1050,
        unit: 'hPa',
        precision: 1
      },
      light: {
        min: 0,
        max: 100000,
        unit: 'lux',
        precision: 0
      }
    };
  }

  generateESP(index) {
    const espId = `mock_esp_${String(index).padStart(3, '0')}`;
    const location = this.generateLocation();

    return {
      id: espId,
      name: `Mock ESP ${index}`,
      location,
      sensors: this.generateSensors(),
      actuators: this.generateActuators(),
      status: 'offline',
      created_at: new Date().toISOString()
    };
  }

  generateLocation() {
    const patterns = {
      random: () => ({
        lat: (Math.random() - 0.5) * 180,
        lng: (Math.random() - 0.5) * 360
      }),
      grid: (index) => ({
        lat: 50 + (index % 10) * 0.1,
        lng: 10 + Math.floor(index / 10) * 0.1
      }),
      clustered: () => {
        const centerLat = 50 + (Math.random() - 0.5) * 2;
        const centerLng = 10 + (Math.random() - 0.5) * 2;
        return {
          lat: centerLat + (Math.random() - 0.5) * 0.1,
          lng: centerLng + (Math.random() - 0.5) * 0.1
        };
      }
    };

    return patterns[this.config.locationPattern || 'random'](this.index);
  }

  generateSensors() {
    return this.config.activeSensors.map(sensorType => ({
      id: `${sensorType}_sensor`,
      type: sensorType,
      template: this.espTemplates[sensorType],
      enabled: true
    }));
  }

  generateActuators() {
    const actuatorCount = Math.round(this.config.actuatorRatio * 3); // Max 3 actuators per ESP
    const actuatorTypes = ['relay', 'led', 'servo'];

    return Array.from({ length: actuatorCount }, (_, i) => ({
      id: `actuator_${i + 1}`,
      type: actuatorTypes[i % actuatorTypes.length],
      enabled: Math.random() > 0.3 // 70% chance of being enabled
    }));
  }
}
```

### Simulation Scheduler
```javascript
class SimulationScheduler {
  constructor(espManager, metricsCollector) {
    this.espManager = espManager;
    this.metricsCollector = metricsCollector;
    this.intervals = new Map();
    this.isRunning = false;
  }

  startSimulation(esps, config) {
    this.isRunning = true;

    esps.forEach(esp => {
      const interval = setInterval(() => {
        this.simulateESPStep(esp, config);
      }, config.sensorInterval);

      this.intervals.set(esp.id, interval);
    });

    this.metricsCollector.startCollection();
  }

  stopSimulation() {
    this.isRunning = false;

    for (const [espId, interval] of this.intervals) {
      clearInterval(interval);
    }

    this.intervals.clear();
    this.metricsCollector.stopCollection();
  }

  simulateESPStep(esp, config) {
    if (!this.isRunning) return;

    // Generate sensor data
    const sensorData = this.generateSensorData(esp.sensors, config);

    // Simulate actuator activity
    const actuatorCommands = this.generateActuatorCommands(esp.actuators, config);

    // Send data to server
    this.sendDataToServer(esp.id, sensorData, actuatorCommands);

    // Update ESP status
    this.updateESPStatus(esp);
  }

  generateSensorData(sensors, config) {
    const dataRateMultiplier = {
      low: 0.5,
      normal: 1,
      high: 2,
      extreme: 5
    }[config.dataRate];

    return sensors.map(sensor => {
      const template = sensor.template;
      const baseValue = this.generateRealisticValue(template);
      const noise = (Math.random() - 0.5) * template.max * 0.1 * dataRateMultiplier;

      return {
        sensor_id: sensor.id,
        value: Math.max(template.min, Math.min(template.max,
          baseValue + noise)),
        unit: template.unit,
        timestamp: new Date().toISOString(),
        quality: this.generateQuality(config.errorRate)
      };
    });
  }

  generateRealisticValue(template) {
    // Use normal distribution for more realistic values
    const mean = (template.min + template.max) / 2;
    const stdDev = (template.max - template.min) / 6; // 99.7% within range

    let value;
    do {
      value = mean + stdDev * (Math.random() + Math.random() + Math.random() + Math.random() + Math.random() + Math.random() - 3);
    } while (value < template.min || value > template.max);

    return Math.round(value * Math.pow(10, template.precision)) / Math.pow(10, template.precision);
  }

  generateQuality(errorRate) {
    return Math.random() > errorRate ? 'good' : 'error';
  }
}
```

### Metrics Collector
```javascript
class MetricsCollector {
  constructor(apiClient, websocketClient) {
    this.apiClient = apiClient;
    this.websocketClient = websocketClient;
    this.collectionInterval = null;
    this.history = {
      cpu: [],
      memory: [],
      apiResponseTimes: new Map(),
      espConnections: []
    };
    this.maxHistorySize = 100;
  }

  startCollection() {
    this.collectionInterval = setInterval(async () => {
      await this.collectMetrics();
    }, 1000); // Collect every second
  }

  stopCollection() {
    if (this.collectionInterval) {
      clearInterval(this.collectionInterval);
      this.collectionInterval = null;
    }
  }

  async collectMetrics() {
    try {
      const metrics = await this.apiClient.get('/api/v1/debug/metrics');

      // Update history
      this.updateHistory(metrics);

      // Calculate trends
      const trends = this.calculateTrends();

      // Send to UI via WebSocket
      this.websocketClient.send('metrics_update', {
        ...metrics,
        trends
      });

      // Check thresholds and trigger alerts
      this.checkThresholds(metrics);

    } catch (error) {
      console.error('Metrics collection failed:', error);
      this.websocketClient.send('metrics_error', { error: error.message });
    }
  }

  updateHistory(metrics) {
    this.history.cpu.push({
      value: metrics.system.cpu_percent,
      timestamp: metrics.timestamp
    });

    this.history.memory.push({
      value: metrics.system.memory_used,
      timestamp: metrics.timestamp
    });

    // Keep only recent history
    if (this.history.cpu.length > this.maxHistorySize) {
      this.history.cpu.shift();
      this.history.memory.shift();
    }

    // Update API response times history
    metrics.api_performance.forEach(api => {
      if (!this.history.apiResponseTimes.has(api.endpoint)) {
        this.history.apiResponseTimes.set(api.endpoint, []);
      }

      const history = this.history.apiResponseTimes.get(api.endpoint);
      history.push({
        value: api.avg_response_time,
        timestamp: metrics.timestamp
      });

      if (history.length > this.maxHistorySize) {
        history.shift();
      }
    });
  }

  calculateTrends() {
    return {
      cpu: this.calculateTrend(this.history.cpu),
      memory: this.calculateTrend(this.history.memory),
      apiResponseTimes: Object.fromEntries(
        Array.from(this.history.apiResponseTimes.entries()).map(([endpoint, history]) => [
          endpoint,
          this.calculateTrend(history)
        ])
      )
    };
  }

  calculateTrend(data) {
    if (data.length < 2) return 0;

    const recent = data.slice(-5); // Last 5 data points
    const older = data.slice(-10, -5); // Previous 5 data points

    if (older.length === 0) return 0;

    const recentAvg = recent.reduce((sum, item) => sum + item.value, 0) / recent.length;
    const olderAvg = older.reduce((sum, item) => sum + item.value, 0) / older.length;

    return ((recentAvg - olderAvg) / olderAvg) * 100; // Percentage change
  }

  checkThresholds(metrics) {
    const alerts = [];

    // CPU threshold
    if (metrics.system.cpu_percent > 90) {
      alerts.push({
        type: 'cpu_critical',
        message: 'CPU usage above 90%',
        level: 'critical'
      });
    } else if (metrics.system.cpu_percent > 70) {
      alerts.push({
        type: 'cpu_warning',
        message: 'CPU usage above 70%',
        level: 'warning'
      });
    }

    // Memory threshold
    const memoryUsage = metrics.system.memory_used / metrics.system.memory_total;
    if (memoryUsage > 0.95) {
      alerts.push({
        type: 'memory_critical',
        message: 'Memory usage above 95%',
        level: 'critical'
      });
    }

    // Send alerts
    if (alerts.length > 0) {
      this.websocketClient.send('alerts', alerts);
    }
  }
}
```

## 🧹 Cleanup Handler
```javascript
class CleanupHandler {
  constructor(apiClient, confirmationRequired = true) {
    this.apiClient = apiClient;
    this.confirmationRequired = confirmationRequired;
  }

  async cleanup(confirm = false) {
    if (this.confirmationRequired && !confirm) {
      throw new Error('Cleanup requires explicit confirmation');
    }

    try {
      // Stop any running simulations first
      await this.stopAllSimulations();

      // Delete all mock ESPs
      const response = await this.apiClient.delete('/api/v1/debug/cleanup');

      // Clear local state
      this.clearLocalState();

      return response;

    } catch (error) {
      console.error('Cleanup failed:', error);
      throw error;
    }
  }

  async stopAllSimulations() {
    try {
      await this.apiClient.post('/api/v1/debug/stop-simulation');
    } catch (error) {
      console.warn('Failed to stop simulations:', error);
    }
  }

  clearLocalState() {
    // Clear any local storage or cached data
    localStorage.removeItem('loadTest_config');
    localStorage.removeItem('loadTest_metrics');

    // Reset Pinia store if available
    if (this.store) {
      this.store.$reset();
    }
  }

  async getCleanupStatus() {
    // Get information about what will be cleaned up
    const response = await this.apiClient.get('/api/v1/debug/cleanup-status');

    return {
      mockEsps: response.mock_esp_count,
      testData: response.test_data_size,
      simulations: response.active_simulations,
      estimatedCleanupTime: response.estimated_cleanup_time
    };
  }
}
```

## 📊 Test-Ergebnisse & Export

### Ergebnis-Format
```javascript
const testResults = {
  testId: 'load_test_20241227_143022',
  duration: 300000, // ms
  configuration: { /* test config */ },
  metrics: {
    peak: {
      cpu: 78.5,
      memory: 4294967296, // bytes
      espCount: 200,
      responseTime: 145 // ms
    },
    average: {
      cpu: 45.2,
      memory: 2684354560,
      espCount: 195,
      responseTime: 89
    },
    timeline: [ /* time-series data */ ]
  },
  alerts: [ /* triggered alerts */ ],
  summary: {
    status: 'completed', // 'completed' | 'failed' | 'aborted'
    recommendations: [
      'Consider increasing server CPU cores for >100 ESPs',
      'Memory usage remains stable under load',
      'API response times degrade linearly with ESP count'
    ],
    score: 85 // 0-100 performance score
  }
}
```

### Export-Formate
```javascript
// JSON Export
function exportResultsJSON(results) {
  const blob = new Blob([JSON.stringify(results, null, 2)], {
    type: 'application/json'
  });

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `load-test-results-${results.testId}.json`;
  a.click();
}

// CSV Export für Metriken
function exportMetricsCSV(metrics) {
  const headers = ['timestamp', 'cpu', 'memory', 'esp_count', 'response_time'];
  const rows = metrics.timeline.map(point => [
    point.timestamp,
    point.cpu,
    point.memory,
    point.espCount,
    point.responseTime
  ]);

  const csv = [headers, ...rows]
    .map(row => row.join(','))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `load-test-metrics-${Date.now()}.csv`;
  a.click();
}
```

## 🔒 Sicherheit & Validierung

### Input-Validierung
```javascript
const validationRules = {
  espCount: {
    min: 1,
    max: 1000,
    type: 'number'
  },
  sensorInterval: {
    min: 500,    // 0.5s minimum
    max: 300000, // 5min maximum
    type: 'number'
  },
  actuatorRatio: {
    min: 0,
    max: 1,
    type: 'number'
  }
};

function validateConfiguration(config) {
  const errors = [];

  Object.entries(validationRules).forEach(([field, rules]) => {
    const value = config[field];

    if (typeof value !== rules.type) {
      errors.push(`${field} must be of type ${rules.type}`);
    }

    if (value < rules.min || value > rules.max) {
      errors.push(`${field} must be between ${rules.min} and ${rules.max}`);
    }
  });

  // Business logic validation
  if (config.espCount > 500 && config.sensorInterval < 1000) {
    errors.push('High ESP count with low interval may cause system overload');
  }

  return errors;
}
```

### Rate Limiting & Schutz
```javascript
const rateLimits = {
  bulkCreate: {
    maxRequests: 5,
    windowMs: 60000, // 1 minute
    blockDurationMs: 300000 // 5 minutes
  },
  metrics: {
    maxRequests: 60, // 1 per second
    windowMs: 60000
  }
};

class RateLimiter {
  constructor() {
    this.requests = new Map();
  }

  checkLimit(endpoint, clientId) {
    const key = `${endpoint}_${clientId}`;
    const now = Date.now();
    const windowStart = now - rateLimits[endpoint].windowMs;

    if (!this.requests.has(key)) {
      this.requests.set(key, []);
    }

    const requestTimes = this.requests.get(key);

    // Remove old requests outside the window
    const validRequests = requestTimes.filter(time => time > windowStart);

    if (validRequests.length >= rateLimits[endpoint].maxRequests) {
      return {
        allowed: false,
        retryAfter: Math.ceil((validRequests[0] + rateLimits[endpoint].windowMs - now) / 1000)
      };
    }

    validRequests.push(now);
    this.requests.set(key, validRequests);

    return { allowed: true };
  }
}
```

---

**Diese Dokumentation ermöglicht es einem Entwickler, das komplette Load-Testing-System von Grund auf neu zu implementieren. Alle UI-Komponenten, API-Integrationen, Business-Logik und technischen Details sind detailliert spezifiziert.**
