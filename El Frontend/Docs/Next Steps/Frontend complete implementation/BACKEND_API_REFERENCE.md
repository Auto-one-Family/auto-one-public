# Backend API Referenz - God-Kaiser Server

> **Zielgruppe:** Frontend-Entwickler
> **Zweck:** Vollständige API-Dokumentation mit TypeScript-Interfaces
> **Version:** 1.0.0
> **Stand:** 2026-01-30

---

## Inhaltsverzeichnis

1. [Authentifizierung](#1-authentifizierung)
2. [Logic Engine API](#2-logic-engine-api)
3. [Sensor API](#3-sensor-api)
4. [Actuator API](#4-actuator-api)
5. [ESP-Geräte API](#5-esp-geräte-api)
6. [Zone API](#6-zone-api)
7. [WebSocket Verbindung](#7-websocket-verbindung)
8. [Fehlerbehandlung](#8-fehlerbehandlung)
9. [Konstanten & Enums](#9-konstanten--enums)
10. [Subzone API](#10-subzone-api) [ERGÄNZT]
11. [Health API](#11-health-api) [ERGÄNZT]
12. [Users API](#12-users-api) [ERGÄNZT]
13. [Audit API](#13-audit-api) [ERGÄNZT]
14. [Debug/Mock ESP API](#14-debugmock-esp-api) [ERGÄNZT]
15. [Sequences API](#15-sequences-api) [ERGÄNZT]
10. [Subzone API](#10-subzone-api) [ERGÄNZT]
11. [Health API](#11-health-api) [ERGÄNZT]
12. [Users API](#12-users-api) [ERGÄNZT]
13. [Audit API](#13-audit-api) [ERGÄNZT]
14. [Debug/Mock ESP API](#14-debugmock-esp-api) [ERGÄNZT]
15. [Sequences API](#15-sequences-api) [ERGÄNZT]

---

## 1. Authentifizierung

### 1.1 TypeScript Interfaces

```typescript
// ============================================================
// AUTH INTERFACES
// ============================================================

/** Login Request */
interface LoginRequest {
  username: string;  // min 3, max 50 chars
  password: string;  // min 8 chars
}

/** Login Response */
interface LoginResponse {
  success: boolean;
  message?: string;
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;  // seconds until access token expires
  user: UserResponse;
}

/** User Registration Request */
interface RegisterRequest {
  username: string;  // min 3, max 50 chars, alphanumeric + underscore
  email: string;     // valid email format
  password: string;  // min 8 chars, must contain: uppercase, lowercase, digit
  display_name?: string;  // max 100 chars
}

/** User Registration Response */
interface RegisterResponse {
  success: boolean;
  message?: string;
  user: UserResponse;
}

/** Token Refresh Request */
interface RefreshTokenRequest {
  refresh_token: string;
}

/** Token Refresh Response */
interface RefreshTokenResponse {
  success: boolean;
  message?: string;
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

/** Initial Setup Request (First Admin User) */
interface SetupRequest {
  username: string;
  email: string;
  password: string;
  display_name?: string;
}

/** Setup Response */
interface SetupResponse {
  success: boolean;
  message?: string;
  user: UserResponse;
  access_token: string;
  refresh_token: string;
}

/** User Info Response */
interface UserResponse {
  id: number;
  username: string;
  email: string;
  display_name?: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;  // ISO 8601 datetime
  last_login?: string; // ISO 8601 datetime
}

/** Setup Status Response */
interface SetupStatusResponse {
  success: boolean;
  needs_setup: boolean;
  user_count: number;
}

/** MQTT Auth Configuration Request */
interface MQTTConfigureRequest {
  username: string;
  password: string;
}

/** MQTT Status Response */
interface MQTTStatusResponse {
  success: boolean;
  password_file_exists: boolean;
  user_count: number;
}
```

### 1.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/auth/status` | - | Prüft ob Setup benötigt wird |
| `POST` | `/api/v1/auth/setup` | - | Erstellt ersten Admin-User |
| `POST` | `/api/v1/auth/login` | - | Login mit Username/Password |
| `POST` | `/api/v1/auth/register` | Admin | Registriert neuen User |
| `POST` | `/api/v1/auth/refresh` | - | Erneuert Access Token |
| `POST` | `/api/v1/auth/logout` | JWT | Invalidiert Tokens |
| `GET` | `/api/v1/auth/me` | JWT | Gibt aktuellen User zurück |
| `POST` | `/api/v1/auth/mqtt/configure` | Admin | Konfiguriert MQTT Auth |
| `GET` | `/api/v1/auth/mqtt/status` | Admin | MQTT Auth Status |

### 1.3 Beispiele

```typescript
// Login
const login = async (username: string, password: string): Promise<LoginResponse> => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  return response.json();
};

// Authenticated Request mit Access Token
const fetchWithAuth = async (url: string, token: string) => {
  return fetch(url, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
};

// Token Refresh
const refreshToken = async (refreshToken: string): Promise<RefreshTokenResponse> => {
  const response = await fetch('/api/v1/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  return response.json();
};
```

### 1.4 Validierungsregeln

| Feld | Regeln |
|------|--------|
| `username` | 3-50 Zeichen, nur alphanumerisch + Unterstrich |
| `email` | Valides E-Mail-Format |
| `password` | Min 8 Zeichen, muss enthalten: Großbuchstabe, Kleinbuchstabe, Ziffer |
| `display_name` | Max 100 Zeichen, optional |

---

## 2. Logic Engine API

### 2.1 TypeScript Interfaces

```typescript
// ============================================================
// LOGIC ENGINE INTERFACES
// ============================================================

/** Sensor-basierte Bedingung */
interface SensorCondition {
  type: "sensor_threshold" | "sensor";
  esp_id: string;
  gpio: number;           // 0-39
  sensor_type: SensorType;
  operator: ">" | "<" | ">=" | "<=" | "==" | "!=";
  value: number;
  hysteresis?: number;    // Optional: Hysterese-Wert (default: 0)
}

/** Zeit-basierte Bedingung */
interface TimeCondition {
  type: "time_window" | "time";
  start_time?: string;    // Format: "HH:MM" (z.B. "08:00")
  end_time?: string;      // Format: "HH:MM" (z.B. "18:00")
  start_hour?: number;    // Alternative: 0-23
  end_hour?: number;      // Alternative: 0-24
  days_of_week?: number[];  // 0=Montag, 6=Sonntag
}

/** Cooldown-Bedingung (verhindert zu häufige Ausführung) */
interface CooldownCondition {
  type: "cooldown";
  min_interval_seconds: number;  // Mindestabstand zwischen Ausführungen
}

/** Compound-Bedingung (AND/OR-Verknüpfung) */
interface CompoundCondition {
  logic: "AND" | "OR";
  conditions: (SensorCondition | TimeCondition | CooldownCondition)[];
}

/** Alle Bedingungstypen */
type Condition = SensorCondition | TimeCondition | CooldownCondition | CompoundCondition;

/** Aktor-Aktion */
interface ActuatorAction {
  type: "actuator";
  esp_id: string;
  gpio: number;           // 0-39
  actuator_type: ActuatorType;
  value: number;          // PWM: 0.0-1.0, Digital: 0 oder 1
  duration_seconds?: number;  // Optional: Auto-Abschaltung nach X Sekunden
}

/** Benachrichtigungs-Aktion */
interface NotificationAction {
  type: "notification";
  channel: "websocket" | "email" | "webhook";
  message: string;
  severity?: "info" | "warning" | "critical";
  recipients?: string[];  // E-Mail-Adressen oder Webhook-URLs
}

/** Verzögerungs-Aktion */
interface DelayAction {
  type: "delay";
  seconds: number;  // Wartezeit in Sekunden
}

/** Alle Aktionstypen */
type Action = ActuatorAction | NotificationAction | DelayAction;

/** Logic Rule erstellen */
interface LogicRuleCreate {
  name: string;              // 1-100 Zeichen
  description?: string;      // Max 500 Zeichen
  conditions: Condition | Condition[];  // Einzeln oder Array
  actions: Action[];         // Min 1 Aktion
  logic_operator?: "AND" | "OR";  // Default: "AND"
  enabled?: boolean;         // Default: true
  priority?: number;         // 0-100, höher = wichtiger (default: 50)
  cooldown_seconds?: number; // Min 0 (default: 60)
  max_executions_per_hour?: number;  // Min 1, Max 1000 (default: 100)
}

/** Logic Rule aktualisieren (alle Felder optional) */
interface LogicRuleUpdate {
  name?: string;
  description?: string;
  conditions?: Condition | Condition[];
  actions?: Action[];
  logic_operator?: "AND" | "OR";
  enabled?: boolean;
  priority?: number;
  cooldown_seconds?: number;
  max_executions_per_hour?: number;
}

/** Logic Rule Response */
interface LogicRuleResponse {
  id: string;               // UUID
  name: string;
  description?: string;
  conditions: Condition | Condition[];
  actions: Action[];
  logic_operator: "AND" | "OR";
  enabled: boolean;
  priority: number;
  cooldown_seconds: number;
  max_executions_per_hour: number;
  last_triggered?: string;  // ISO 8601 datetime
  execution_count: number;
  created_at: string;
  updated_at: string;
}

/** Rule Test Request */
interface RuleTestRequest {
  mock_sensor_values?: Record<string, number>;  // Format: "esp_id:gpio" -> value
  mock_time?: string;       // Format: "HH:MM"
  dry_run?: boolean;        // Default: true (keine echten Aktionen)
}

/** Einzelnes Condition-Ergebnis */
interface ConditionResult {
  condition_index: number;
  condition_type: string;
  result: boolean;
  details: string;
  actual_value?: number;
}

/** Rule Test Response */
interface RuleTestResponse {
  success: boolean;
  rule_id: string;
  rule_name: string;
  would_trigger: boolean;
  condition_results: ConditionResult[];
  action_results: string[];
  dry_run: boolean;
}

/** Execution History Entry */
interface ExecutionHistoryEntry {
  id: string;              // UUID
  rule_id: string;         // UUID
  rule_name: string;
  triggered_at: string;    // ISO 8601 datetime
  trigger_reason: string;
  conditions_met: Record<string, any>;
  actions_executed: Record<string, any>[];
  success: boolean;
  error_message?: string;
  execution_time_ms: number;
}

/** Rule Toggle Response */
interface RuleToggleResponse {
  success: boolean;
  message: string;
  rule_id: string;
  enabled: boolean;
}
```

### 2.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/logic/rules` | JWT | Alle Regeln abrufen |
| `POST` | `/api/v1/logic/rules` | JWT | Neue Regel erstellen |
| `GET` | `/api/v1/logic/rules/{rule_id}` | JWT | Einzelne Regel abrufen |
| `PUT` | `/api/v1/logic/rules/{rule_id}` | JWT | Regel aktualisieren |
| `DELETE` | `/api/v1/logic/rules/{rule_id}` | JWT | Regel löschen |
| `POST` | `/api/v1/logic/rules/{rule_id}/toggle` | JWT | Regel aktivieren/deaktivieren |
| `POST` | `/api/v1/logic/rules/{rule_id}/test` | JWT | Regel mit Mock-Daten testen |
| `GET` | `/api/v1/logic/execution_history` | JWT | Ausführungshistorie abrufen |

### 2.3 Beispiele

```typescript
// Einfache Regel: Pumpe an wenn Temperatur > 30°C
const createTemperatureRule: LogicRuleCreate = {
  name: "Kühlpumpe bei Hitze",
  description: "Aktiviert Kühlpumpe wenn Temperatur über 30°C steigt",
  conditions: {
    type: "sensor_threshold",
    esp_id: "ESP_12AB34CD",
    gpio: 32,
    sensor_type: "temperature",
    operator: ">",
    value: 30,
    hysteresis: 2  // Schaltet erst bei 28°C wieder ab
  },
  actions: [
    {
      type: "actuator",
      esp_id: "ESP_12AB34CD",
      gpio: 25,
      actuator_type: "pump",
      value: 1,
      duration_seconds: 300  // Max 5 Minuten
    },
    {
      type: "notification",
      channel: "websocket",
      message: "Kühlpumpe aktiviert wegen hoher Temperatur",
      severity: "warning"
    }
  ],
  priority: 80,
  cooldown_seconds: 120,
  max_executions_per_hour: 10
};

// Komplexe Regel mit Compound-Condition
const createComplexRule: LogicRuleCreate = {
  name: "Bewässerung im Zeitfenster",
  description: "Bewässert nur wenn trocken UND im Zeitfenster",
  conditions: {
    logic: "AND",
    conditions: [
      {
        type: "sensor_threshold",
        esp_id: "ESP_GARDEN01",
        gpio: 34,
        sensor_type: "moisture",
        operator: "<",
        value: 30
      },
      {
        type: "time_window",
        start_time: "06:00",
        end_time: "10:00",
        days_of_week: [0, 1, 2, 3, 4]  // Mo-Fr
      }
    ]
  },
  actions: [
    {
      type: "actuator",
      esp_id: "ESP_GARDEN01",
      gpio: 26,
      actuator_type: "valve",
      value: 1,
      duration_seconds: 600
    }
  ]
};

// Regel testen
const testRule = async (ruleId: string, token: string) => {
  const testRequest: RuleTestRequest = {
    mock_sensor_values: {
      "ESP_12AB34CD:32": 32.5  // Simuliere 32.5°C
    },
    mock_time: "14:30",
    dry_run: true
  };

  const response = await fetch(`/api/v1/logic/rules/${ruleId}/test`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(testRequest)
  });
  return response.json() as Promise<RuleTestResponse>;
};
```

### 2.4 Validierungsregeln

| Feld | Regeln |
|------|--------|
| `name` | 1-100 Zeichen, nicht leer |
| `description` | Max 500 Zeichen |
| `gpio` | 0-39 (ESP32 GPIO-Bereich) |
| `priority` | 0-100 |
| `cooldown_seconds` | >= 0 |
| `max_executions_per_hour` | 1-1000 |
| `value` (PWM) | 0.0-1.0 |
| `value` (Digital) | 0 oder 1 |
| `time` Format | "HH:MM" (24-Stunden) |
| `days_of_week` | Array von 0-6 (Mo=0, So=6) |

---

## 3. Sensor API

### 3.1 TypeScript Interfaces

```typescript
// ============================================================
// SENSOR INTERFACES
// ============================================================

/** Sensor-Konfiguration erstellen */
interface SensorConfigCreate {
  gpio: number;             // 0-39
  sensor_type: SensorType;
  name?: string;            // Max 100 Zeichen
  description?: string;     // Max 500 Zeichen
  interval_ms?: number;     // Min 100, Max 3600000 (1h), default: 5000
  enabled?: boolean;        // Default: true

  // Pi-Enhanced Processing
  pi_enhanced?: boolean;    // Server-seitige Verarbeitung
  calibration_offset?: number;
  calibration_scale?: number;

  // I2C-spezifisch
  i2c_address?: number;     // 0x00-0xFF
  i2c_bus?: number;         // Bus-Nummer (default: 0)

  // OneWire-spezifisch (DS18B20)
  onewire_address?: string; // 16-Zeichen Hex-String (z.B. "28FF1234567890AB")
  onewire_bus_gpio?: number; // GPIO für OneWire-Bus

  // Schwellwerte für Alerts
  alert_min?: number;
  alert_max?: number;
  alert_enabled?: boolean;
}

/** Sensor-Konfiguration aktualisieren */
interface SensorConfigUpdate {
  name?: string;
  description?: string;
  interval_ms?: number;
  enabled?: boolean;
  pi_enhanced?: boolean;
  calibration_offset?: number;
  calibration_scale?: number;
  alert_min?: number;
  alert_max?: number;
  alert_enabled?: boolean;
}

/** Sensor-Konfiguration Response */
interface SensorConfigResponse {
  id: number;
  esp_id: string;
  gpio: number;
  sensor_type: SensorType;
  name?: string;
  description?: string;
  interval_ms: number;
  enabled: boolean;
  pi_enhanced: boolean;
  calibration_offset: number;
  calibration_scale: number;
  i2c_address?: number;
  onewire_address?: string;
  onewire_bus_gpio?: number;
  alert_min?: number;
  alert_max?: number;
  alert_enabled: boolean;
  last_reading?: SensorReading;
  last_error?: string;
  error_count: number;
  created_at: string;
  updated_at: string;
}

/** Einzelner Sensor-Messwert */
interface SensorReading {
  timestamp: number;        // Unix Timestamp (Sekunden)
  value: number;            // Primärer Messwert
  secondary_value?: number; // Für Multi-Value-Sensoren (z.B. Humidity bei SHT31)
  raw_value?: number;       // Rohwert vor Kalibrierung
  unit: string;             // z.B. "°C", "%", "pH"
  quality?: "good" | "degraded" | "bad";
}

/** Sensor-Daten Abfrage */
interface SensorDataQuery {
  esp_id?: string;
  gpio?: number;
  sensor_type?: SensorType;
  start_time?: number;      // Unix Timestamp
  end_time?: number;        // Unix Timestamp
  limit?: number;           // Max Anzahl Ergebnisse (default: 100, max: 1000)
  aggregation?: "none" | "avg" | "min" | "max" | "sum";
  interval_seconds?: number; // Aggregations-Intervall
}

/** Sensor-Daten Response */
interface SensorDataResponse {
  success: boolean;
  data: SensorReading[];
  count: number;
  esp_id: string;
  gpio: number;
  sensor_type: SensorType;
  query_time_ms: number;
}

/** Sensor-Statistiken */
interface SensorStats {
  esp_id: string;
  gpio: number;
  sensor_type: SensorType;
  period_start: string;     // ISO 8601
  period_end: string;       // ISO 8601
  count: number;
  min: number;
  max: number;
  avg: number;
  std_dev: number;
  last_value: number;
  last_timestamp: string;
}

/** OneWire Device (gefunden beim Scan) */
interface OneWireDevice {
  address: string;          // 16-Zeichen Hex
  family_code: string;      // z.B. "28" für DS18B20
  device_type: string;      // z.B. "DS18B20"
  is_configured: boolean;   // Bereits in DB konfiguriert?
}

/** OneWire Scan Response */
interface OneWireScanResponse {
  success: boolean;
  message: string;
  esp_id: string;
  bus_gpio: number;
  devices: OneWireDevice[];
  scan_time_ms: number;
}

/** Trigger Measurement Response */
interface TriggerMeasurementResponse {
  success: boolean;
  message: string;
  esp_id: string;
  gpio: number;
  request_id: string;       // UUID für Tracking
}
```

### 3.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/sensors/` | JWT | Alle Sensor-Configs abrufen |
| `GET` | `/api/v1/sensors/{esp_id}/{gpio}` | JWT | Einzelne Sensor-Config |
| `POST` | `/api/v1/sensors/{esp_id}/{gpio}` | JWT | Sensor konfigurieren |
| `PATCH` | `/api/v1/sensors/{esp_id}/{gpio}` | JWT | Sensor aktualisieren |
| `DELETE` | `/api/v1/sensors/{esp_id}/{gpio}` | JWT | Sensor-Config löschen |
| `GET` | `/api/v1/sensors/data` | JWT | Sensor-Daten abfragen |
| `GET` | `/api/v1/sensors/{esp_id}/{gpio}/stats` | JWT | Statistiken abrufen |
| `POST` | `/api/v1/sensors/{esp_id}/{gpio}/measure` | JWT | On-Demand Messung triggern |
| `POST` | `/api/v1/sensors/esp/{esp_id}/onewire/scan` | JWT | OneWire-Bus scannen |

### 3.3 Beispiele

```typescript
// DS18B20 Temperatur-Sensor konfigurieren
const createDS18B20: SensorConfigCreate = {
  gpio: 4,  // OneWire Data-Pin
  sensor_type: "temperature",
  name: "Wassertemperatur Tank 1",
  description: "DS18B20 im Haupttank",
  interval_ms: 10000,  // Alle 10 Sekunden
  enabled: true,
  pi_enhanced: true,   // Server-seitige Kalibrierung
  calibration_offset: -0.5,  // Offset-Korrektur
  onewire_address: "28FF1234567890AB",
  onewire_bus_gpio: 4,
  alert_min: 15,
  alert_max: 35,
  alert_enabled: true
};

// SHT31 Temperatur+Humidity Sensor (I2C)
const createSHT31: SensorConfigCreate = {
  gpio: 21,  // I2C SDA
  sensor_type: "sht31",  // Multi-Value: temp + humidity
  name: "Raumklima Gewächshaus",
  interval_ms: 30000,
  i2c_address: 0x44,
  i2c_bus: 0,
  pi_enhanced: true
};

// Sensor-Daten der letzten Stunde abrufen
const fetchRecentData = async (espId: string, gpio: number, token: string) => {
  const oneHourAgo = Math.floor(Date.now() / 1000) - 3600;
  const query: SensorDataQuery = {
    esp_id: espId,
    gpio: gpio,
    start_time: oneHourAgo,
    limit: 500,
    aggregation: "none"
  };

  const params = new URLSearchParams(query as any);
  const response = await fetch(`/api/v1/sensors/data?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json() as Promise<SensorDataResponse>;
};

// OneWire-Bus scannen
const scanOneWire = async (espId: string, busGpio: number, token: string) => {
  const response = await fetch(`/api/v1/sensors/esp/${espId}/onewire/scan`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ bus_gpio: busGpio })
  });
  return response.json() as Promise<OneWireScanResponse>;
};
```

### 3.4 Sensor-Typen Referenz

| Type | Beschreibung | Einheit | Multi-Value |
|------|--------------|---------|-------------|
| `temperature` | Temperatur (DS18B20, etc.) | °C | Nein |
| `humidity` | Luftfeuchtigkeit | % | Nein |
| `sht31` | SHT31 Temp+Humidity | °C, % | Ja |
| `ph` | pH-Wert | pH | Nein |
| `ec` | Leitfähigkeit | mS/cm | Nein |
| `moisture` | Bodenfeuchtigkeit | % | Nein |
| `pressure` | Luftdruck | hPa | Nein |
| `co2` | CO2-Konzentration | ppm | Nein |
| `light` | Lichtstärke | lux | Nein |
| `flow` | Durchfluss | L/min | Nein |
| `analog` | Generischer Analog-Input | raw | Nein |
| `digital` | Digitaler Input | 0/1 | Nein |

---

## 4. Actuator API

### 4.1 TypeScript Interfaces

```typescript
// ============================================================
// ACTUATOR INTERFACES
// ============================================================

/** Actuator-Konfiguration erstellen */
interface ActuatorConfigCreate {
  gpio: number;             // 0-39
  actuator_type: ActuatorType;
  name?: string;            // Max 100 Zeichen
  description?: string;     // Max 500 Zeichen
  enabled?: boolean;        // Default: true

  // PWM-spezifisch
  pwm_frequency?: number;   // Hz, default: 5000
  pwm_resolution?: number;  // Bits, default: 8 (0-255)

  // Sicherheitseinstellungen
  max_runtime_seconds?: number;  // Auto-Abschaltung (default: 3600)
  safe_state?: number;      // Zustand bei Fehler (default: 0 = aus)
  requires_confirmation?: boolean;  // Bestätigung erforderlich

  // Invertierung
  inverted?: boolean;       // Logik invertieren
}

/** Actuator-Konfiguration aktualisieren */
interface ActuatorConfigUpdate {
  name?: string;
  description?: string;
  enabled?: boolean;
  pwm_frequency?: number;
  pwm_resolution?: number;
  max_runtime_seconds?: number;
  safe_state?: number;
  requires_confirmation?: boolean;
  inverted?: boolean;
}

/** Actuator-Konfiguration Response */
interface ActuatorConfigResponse {
  id: number;
  esp_id: string;
  gpio: number;
  actuator_type: ActuatorType;
  name?: string;
  description?: string;
  enabled: boolean;
  pwm_frequency: number;
  pwm_resolution: number;
  max_runtime_seconds: number;
  safe_state: number;
  requires_confirmation: boolean;
  inverted: boolean;
  current_state: ActuatorState;
  last_command?: string;
  last_command_time?: string;
  emergency_stopped: boolean;
  created_at: string;
  updated_at: string;
}

/** Aktueller Actuator-Zustand */
interface ActuatorState {
  value: number;            // 0.0-1.0 für PWM, 0/1 für Digital
  is_active: boolean;
  runtime_seconds: number;  // Aktuelle Laufzeit
  last_changed: string;     // ISO 8601
  source: "manual" | "logic" | "schedule" | "emergency";
}

/** Actuator-Befehl senden */
interface ActuatorCommand {
  value: number;            // 0.0-1.0 für PWM, 0/1 für Digital
  duration_seconds?: number; // Optional: Auto-Abschaltung
  source?: string;          // Quelle des Befehls (für Logging)
  priority?: number;        // Befehlspriorität (höher überschreibt niedriger)
}

/** Actuator-Befehl Response */
interface ActuatorCommandResponse {
  success: boolean;
  message: string;
  esp_id: string;
  gpio: number;
  command_id: string;       // UUID für Tracking
  value: number;
  previous_value: number;
  estimated_execution_time_ms: number;
}

/** Emergency Stop Request */
interface EmergencyStopRequest {
  esp_id?: string;          // Optional: Nur dieses ESP, sonst alle
  reason: string;           // Pflichtfeld: Grund für Emergency Stop
  notify?: boolean;         // WebSocket-Benachrichtigung senden
}

/** Emergency Stop Response */
interface EmergencyStopResponse {
  success: boolean;
  message: string;
  affected_actuators: number;
  affected_esps: string[];
  timestamp: string;
}

/** Actuator History Entry */
interface ActuatorHistoryEntry {
  id: number;
  esp_id: string;
  gpio: number;
  timestamp: string;        // ISO 8601
  action: "on" | "off" | "set" | "emergency_stop" | "timeout";
  value: number;
  previous_value: number;
  source: string;
  duration_seconds?: number;
  success: boolean;
  error_message?: string;
}

/** Actuator History Query Params */
interface ActuatorHistoryQuery {
  start_time?: string;      // ISO 8601
  end_time?: string;        // ISO 8601
  action?: string;          // Filter nach Action
  limit?: number;           // Max 1000, default 100
}
```

### 4.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/actuators/` | JWT | Alle Actuator-Configs |
| `GET` | `/api/v1/actuators/{esp_id}/{gpio}` | JWT | Einzelne Actuator-Config |
| `POST` | `/api/v1/actuators/{esp_id}/{gpio}` | JWT | Actuator konfigurieren |
| `PATCH` | `/api/v1/actuators/{esp_id}/{gpio}` | JWT | Actuator aktualisieren |
| `DELETE` | `/api/v1/actuators/{esp_id}/{gpio}` | JWT | Actuator-Config löschen |
| `POST` | `/api/v1/actuators/{esp_id}/{gpio}/command` | JWT | Befehl senden |
| `GET` | `/api/v1/actuators/{esp_id}/{gpio}/status` | JWT | Aktuellen Status abrufen |
| `POST` | `/api/v1/actuators/emergency_stop` | JWT | Emergency Stop |
| `GET` | `/api/v1/actuators/{esp_id}/{gpio}/history` | JWT | Historie abrufen |

### 4.3 Beispiele

```typescript
// Pumpe konfigurieren
const createPump: ActuatorConfigCreate = {
  gpio: 25,
  actuator_type: "pump",
  name: "Hauptpumpe Tank 1",
  description: "Umwälzpumpe für Nährstofflösung",
  enabled: true,
  max_runtime_seconds: 1800,  // Max 30 Minuten
  safe_state: 0,              // Bei Fehler: aus
  requires_confirmation: false
};

// PWM-gesteuerten Lüfter konfigurieren
const createFan: ActuatorConfigCreate = {
  gpio: 26,
  actuator_type: "pwm",
  name: "Abluft-Ventilator",
  pwm_frequency: 25000,       // 25kHz für leisen Betrieb
  pwm_resolution: 8,
  max_runtime_seconds: 0,     // Kein Limit
  inverted: false
};

// Actuator-Befehl senden
const sendCommand = async (
  espId: string,
  gpio: number,
  value: number,
  token: string
): Promise<ActuatorCommandResponse> => {
  const command: ActuatorCommand = {
    value: value,
    duration_seconds: 300,    // 5 Minuten
    source: "frontend_manual"
  };

  const response = await fetch(`/api/v1/actuators/${espId}/${gpio}/command`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(command)
  });
  return response.json();
};

// Emergency Stop für alle Geräte
const emergencyStopAll = async (reason: string, token: string) => {
  const request: EmergencyStopRequest = {
    reason: reason,
    notify: true
  };

  const response = await fetch('/api/v1/actuators/emergency_stop', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json() as Promise<EmergencyStopResponse>;
};

// PWM-Wert setzen (0-100% -> 0.0-1.0)
const setFanSpeed = async (espId: string, gpio: number, percent: number, token: string) => {
  const value = Math.max(0, Math.min(1, percent / 100));
  return sendCommand(espId, gpio, value, token);
};
```

### 4.4 Actuator-Typen Referenz

| Type | Beschreibung | Wertebereich | ESP32 Mapping |
|------|--------------|--------------|---------------|
| `digital` | Digitaler Output | 0 oder 1 | GPIO Output |
| `pwm` | PWM-gesteuerter Output | 0.0-1.0 | LEDC PWM |
| `servo` | Servo-Motor | 0.0-1.0 (0-180°) | LEDC PWM |
| `pump` | Pumpe (alias für digital) | 0 oder 1 | GPIO Output |
| `valve` | Ventil (alias für digital) | 0 oder 1 | GPIO Output |
| `relay` | Relais (alias für digital) | 0 oder 1 | GPIO Output |

### 4.5 Sicherheitsregeln

- **Emergency Stop** hat höchste Priorität und überschreibt alle anderen Befehle
- **max_runtime_seconds**: Automatische Abschaltung nach Ablauf
- **safe_state**: Wird bei Fehler/Timeout/Disconnect angenommen
- **PWM-Werte** werden auf 0.0-1.0 begrenzt (Server validiert)
- **GPIO-Konflikte** werden vom Server erkannt und verhindert

---

## 5. ESP-Geräte API

### 5.1 TypeScript Interfaces

```typescript
// ============================================================
// ESP DEVICE INTERFACES
// ============================================================

/** ESP-Gerät registrieren */
interface ESPDeviceCreate {
  esp_id: string;           // Format: "ESP_{6-8 hex chars}", z.B. "ESP_12AB34CD"
  name?: string;            // Max 100 Zeichen
  description?: string;     // Max 500 Zeichen
  location?: string;        // Max 200 Zeichen
  hardware_version?: string;
  firmware_version?: string;
}

/** ESP-Gerät aktualisieren */
interface ESPDeviceUpdate {
  name?: string;
  description?: string;
  location?: string;
  hardware_version?: string;
  firmware_version?: string;
  is_active?: boolean;
  master_zone_id?: string;  // Zone zuweisen
}

/** ESP-Gerät Response */
interface ESPDeviceResponse {
  id: number;
  esp_id: string;
  name?: string;
  description?: string;
  location?: string;
  hardware_version?: string;
  firmware_version?: string;
  is_active: boolean;
  is_online: boolean;
  is_mock: boolean;         // Simuliertes Gerät?
  master_zone_id?: string;
  last_seen?: string;       // ISO 8601
  last_heartbeat?: string;  // ISO 8601
  uptime_seconds?: number;
  ip_address?: string;
  mac_address?: string;
  wifi_rssi?: number;       // dBm
  created_at: string;
  updated_at: string;
  sensor_count: number;
  actuator_count: number;
}

/** GPIO Status Item */
interface GpioStatusItem {
  gpio: number;
  mode: "input" | "output" | "pwm" | "i2c" | "onewire" | "reserved" | "unused";
  component_type?: "sensor" | "actuator";
  component_name?: string;
  value?: number;
}

/** GPIO Status Response */
interface GpioStatusResponse {
  success: boolean;
  esp_id: string;
  gpio_pins: GpioStatusItem[];
  reserved_pins: number[];  // System-reservierte Pins (Flash, etc.)
}

/** ESP Health Metrics */
interface ESPHealthMetrics {
  heap_free: number;        // Bytes
  heap_fragmentation: number; // Prozent
  cpu_frequency: number;    // MHz
  flash_size: number;       // Bytes
  uptime_seconds: number;
  wifi_rssi: number;        // dBm
  mqtt_connected: boolean;
  sensor_error_count: number;
  actuator_error_count: number;
  last_error?: string;
}

/** ESP Health Response */
interface ESPHealthResponse {
  success: boolean;
  esp_id: string;
  is_online: boolean;
  last_seen?: string;
  metrics?: ESPHealthMetrics;
  health_status: "healthy" | "degraded" | "critical" | "offline";
}

/** Config Response Payload (von ESP empfangen) */
interface ConfigResponsePayload {
  esp_id: string;
  status: "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED";
  applied_count: number;
  failed_count: number;
  failures?: ConfigFailureItem[];
  timestamp: number;
}

/** Config Failure Item */
interface ConfigFailureItem {
  gpio: number;
  component_type: string;
  error_code: number;
  error_message: string;
}

/** Pending ESP Device (nicht genehmigt) */
interface PendingESPDevice {
  esp_id: string;
  first_seen: string;       // ISO 8601
  last_seen: string;
  ip_address?: string;
  mac_address?: string;
  firmware_version?: string;
  request_count: number;    // Anzahl Heartbeats
}

/** ESP Approval Request */
interface ESPApprovalRequest {
  name?: string;
  description?: string;
  location?: string;
  master_zone_id?: string;
}

/** ESP Approval Response */
interface ESPApprovalResponse {
  success: boolean;
  message: string;
  device: ESPDeviceResponse;
}
```

### 5.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/esp/devices` | JWT | Alle registrierten ESPs |
| `POST` | `/api/v1/esp/devices` | JWT | Neues ESP registrieren |
| `GET` | `/api/v1/esp/devices/{esp_id}` | JWT | Einzelnes ESP abrufen |
| `PATCH` | `/api/v1/esp/devices/{esp_id}` | JWT | ESP aktualisieren |
| `DELETE` | `/api/v1/esp/devices/{esp_id}` | JWT | ESP löschen |
| `POST` | `/api/v1/esp/devices/{esp_id}/config` | JWT | Config an ESP senden |
| `POST` | `/api/v1/esp/devices/{esp_id}/restart` | JWT | ESP neu starten |
| `POST` | `/api/v1/esp/devices/{esp_id}/reset` | JWT | ESP auf Werkseinstellungen |
| `GET` | `/api/v1/esp/devices/{esp_id}/health` | JWT | Health-Metrics abrufen |
| `GET` | `/api/v1/esp/devices/{esp_id}/gpio-status` | JWT | GPIO-Belegung abrufen |
| `GET` | `/api/v1/esp/devices/pending` | JWT | Nicht genehmigte ESPs |
| `POST` | `/api/v1/esp/devices/{esp_id}/approve` | JWT | ESP genehmigen |
| `POST` | `/api/v1/esp/devices/{esp_id}/reject` | JWT | ESP ablehnen |

### 5.3 Beispiele

```typescript
// Neues ESP registrieren
const registerESP = async (token: string): Promise<ESPDeviceResponse> => {
  const device: ESPDeviceCreate = {
    esp_id: "ESP_12AB34CD",
    name: "Gewächshaus Controller",
    description: "Hauptcontroller für Gewächshaus Nord",
    location: "Gewächshaus Nord, Rack 1",
    firmware_version: "2.1.0"
  };

  const response = await fetch('/api/v1/esp/devices', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(device)
  });
  return response.json();
};

// Alle Online-ESPs abrufen
const getOnlineDevices = async (token: string): Promise<ESPDeviceResponse[]> => {
  const response = await fetch('/api/v1/esp/devices?is_online=true', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const data = await response.json();
  return data.data;
};

// Config an ESP senden
const pushConfig = async (espId: string, token: string) => {
  const response = await fetch(`/api/v1/esp/devices/${espId}/config`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Pending ESP genehmigen
const approveDevice = async (espId: string, token: string) => {
  const approval: ESPApprovalRequest = {
    name: "Neuer Controller",
    location: "Zelt 2",
    master_zone_id: "zone_1"
  };

  const response = await fetch(`/api/v1/esp/devices/${espId}/approve`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(approval)
  });
  return response.json() as Promise<ESPApprovalResponse>;
};

// GPIO-Status prüfen
const getGpioStatus = async (espId: string, token: string): Promise<GpioStatusResponse> => {
  const response = await fetch(`/api/v1/esp/devices/${espId}/gpio-status`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### 5.4 ESP-ID Format

| Format | Beispiel | Beschreibung |
|--------|----------|--------------|
| `ESP_{6 hex}` | `ESP_D0B19C` | Standard-Format |
| `ESP_{8 hex}` | `ESP_12AB34CD` | Erweitertes Format |
| Mock-Geräte | `MOCK_001` | Test/Simulation |

### 5.5 Health Status

| Status | Bedingung |
|--------|-----------|
| `healthy` | Online, keine Fehler, RSSI > -70 dBm |
| `degraded` | Online, aber Fehler oder schwaches WLAN |
| `critical` | Online, aber kritische Fehler |
| `offline` | Kein Heartbeat seit > 5 Minuten |

---

## 6. Zone API

### 6.1 TypeScript Interfaces

```typescript
// ============================================================
// ZONE INTERFACES
// ============================================================

/** Zone-Zuweisung Request */
interface ZoneAssignRequest {
  zone_id: string;          // Technische ID: nur [a-z0-9_-]
  zone_name?: string;       // Menschenlesbarer Name
  kaiser_id?: string;       // Default: "god"
}

/** Zone-Zuweisung Response */
interface ZoneAssignResponse {
  success: boolean;
  message: string;
  esp_id: string;
  zone_id: string;
  zone_name?: string;
  previous_zone_id?: string;
  mqtt_topic_published: string;
}

/** Zone-Entfernung Response */
interface ZoneRemoveResponse {
  success: boolean;
  message: string;
  esp_id: string;
  removed_from_zone: string;
}

/** Zone ACK Payload (von ESP empfangen) */
interface ZoneAckPayload {
  esp_id: string;
  zone_id: string;
  kaiser_id: string;
  status: "SUCCESS" | "FAILED";
  error_code?: number;
  error_message?: string;
  timestamp: number;
}

/** Zone Info */
interface ZoneInfo {
  zone_id: string;
  zone_name?: string;
  kaiser_id: string;
  device_count: number;
  devices: ESPDeviceResponse[];
  created_at: string;
  updated_at: string;
}
```

### 6.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `POST` | `/api/v1/zone/devices/{esp_id}/assign` | JWT | ESP einer Zone zuweisen |
| `DELETE` | `/api/v1/zone/devices/{esp_id}/zone` | JWT | ESP aus Zone entfernen |
| `GET` | `/api/v1/zone/devices/{esp_id}` | JWT | Zone eines ESPs abrufen |
| `GET` | `/api/v1/zone/{zone_id}/devices` | JWT | Alle ESPs einer Zone |
| `GET` | `/api/v1/zone/unassigned` | JWT | ESPs ohne Zone |

### 6.3 Beispiele

```typescript
// ESP einer Zone zuweisen
const assignToZone = async (
  espId: string,
  zoneId: string,
  zoneName: string,
  token: string
): Promise<ZoneAssignResponse> => {
  const request: ZoneAssignRequest = {
    zone_id: zoneId,
    zone_name: zoneName,
    kaiser_id: "god"
  };

  const response = await fetch(`/api/v1/zone/devices/${espId}/assign`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json();
};

// Zone-ID aus Name generieren (Frontend-Logik)
const generateZoneId = (zoneName: string): string => {
  return zoneName
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_-]/g, '')
    .substring(0, 50);
};

// Beispiel: "Gewächshaus Nord" -> "gewaechshaus_nord"

// Alle ESPs einer Zone abrufen
const getZoneDevices = async (zoneId: string, token: string): Promise<ESPDeviceResponse[]> => {
  const response = await fetch(`/api/v1/zone/${zoneId}/devices`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const data = await response.json();
  return data.devices;
};

// Nicht zugewiesene ESPs abrufen
const getUnassignedDevices = async (token: string): Promise<ESPDeviceResponse[]> => {
  const response = await fetch('/api/v1/zone/unassigned', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const data = await response.json();
  return data.devices;
};
```

### 6.4 Zone-ID Validierung

| Regel | Beschreibung |
|-------|--------------|
| Zeichen | Nur `[a-z0-9_-]` erlaubt |
| Länge | 1-50 Zeichen |
| Groß/Klein | Nur Kleinbuchstaben |
| Leerzeichen | Nicht erlaubt (zu `_` konvertieren) |

---

## 7. WebSocket Verbindung

### 7.1 TypeScript Interfaces

```typescript
// ============================================================
// WEBSOCKET INTERFACES
// ============================================================

/** WebSocket Subscription Filters */
interface WebSocketFilters {
  types?: WebSocketEventType[];     // Event-Typen filtern
  esp_ids?: string[];               // Nur bestimmte ESPs
  sensor_types?: SensorType[];      // Nur bestimmte Sensor-Typen
  gpios?: number[];                 // Nur bestimmte GPIOs
}

/** WebSocket Event Types */
type WebSocketEventType =
  | "sensor_data"
  | "actuator_status"
  | "logic_execution"
  | "esp_health"
  | "system_event"
  | "config_response";

/** WebSocket Subscribe Message */
interface WebSocketSubscribeMessage {
  action: "subscribe";
  filters: WebSocketFilters;
}

/** WebSocket Unsubscribe Message */
interface WebSocketUnsubscribeMessage {
  action: "unsubscribe";
  filters?: WebSocketFilters;  // Leer = alle Subscriptions entfernen
}

/** WebSocket Event Base */
interface WebSocketEvent {
  type: WebSocketEventType;
  timestamp: number;          // Unix Timestamp
  data: any;
}

/** Sensor Data Event */
interface SensorDataEvent extends WebSocketEvent {
  type: "sensor_data";
  data: {
    esp_id: string;
    gpio: number;
    sensor_type: SensorType;
    value: number;
    secondary_value?: number;
    unit: string;
    raw_value?: number;
    quality?: "good" | "degraded" | "bad";
  };
}

/** Actuator Status Event */
interface ActuatorStatusEvent extends WebSocketEvent {
  type: "actuator_status";
  data: {
    esp_id: string;
    gpio: number;
    actuator_type: ActuatorType;
    value: number;
    is_active: boolean;
    source: string;
    runtime_seconds: number;
  };
}

/** Logic Execution Event */
interface LogicExecutionEvent extends WebSocketEvent {
  type: "logic_execution";
  data: {
    rule_id: string;
    rule_name: string;
    triggered: boolean;
    conditions_met: Record<string, boolean>;
    actions_executed: string[];
    execution_time_ms: number;
  };
}

/** ESP Health Event */
interface ESPHealthEvent extends WebSocketEvent {
  type: "esp_health";
  data: {
    esp_id: string;
    is_online: boolean;
    health_status: "healthy" | "degraded" | "critical" | "offline";
    heap_free?: number;
    wifi_rssi?: number;
    error_message?: string;
  };
}

/** System Event */
interface SystemEventEvent extends WebSocketEvent {
  type: "system_event";
  data: {
    event_type: "startup" | "shutdown" | "error" | "warning" | "info";
    source: string;
    message: string;
    details?: Record<string, any>;
  };
}

/** Config Response Event */
interface ConfigResponseEvent extends WebSocketEvent {
  type: "config_response";
  data: ConfigResponsePayload;
}
```

### 7.2 Verbindung

```typescript
// WebSocket URL
const WS_URL = "ws://localhost:8000/api/v1/ws/realtime/{client_id}?token={jwt_token}";

// Client-ID sollte eindeutig sein (z.B. UUID oder user_id + tab_id)
```

### 7.3 Beispiele

```typescript
class WebSocketService {
  private ws: WebSocket | null = null;
  private clientId: string;
  private token: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  constructor(clientId: string, token: string) {
    this.clientId = clientId;
    this.token = token;
  }

  connect(): void {
    const url = `ws://localhost:8000/api/v1/ws/realtime/${this.clientId}?token=${this.token}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;

      // Subscribe to all events
      this.subscribe({
        types: ['sensor_data', 'actuator_status', 'esp_health']
      });
    };

    this.ws.onmessage = (event) => {
      const message: WebSocketEvent = JSON.parse(event.data);
      this.handleEvent(message);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  subscribe(filters: WebSocketFilters): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const message: WebSocketSubscribeMessage = {
        action: 'subscribe',
        filters
      };
      this.ws.send(JSON.stringify(message));
    }
  }

  unsubscribe(filters?: WebSocketFilters): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const message: WebSocketUnsubscribeMessage = {
        action: 'unsubscribe',
        filters
      };
      this.ws.send(JSON.stringify(message));
    }
  }

  private handleEvent(event: WebSocketEvent): void {
    switch (event.type) {
      case 'sensor_data':
        this.onSensorData(event as SensorDataEvent);
        break;
      case 'actuator_status':
        this.onActuatorStatus(event as ActuatorStatusEvent);
        break;
      case 'esp_health':
        this.onESPHealth(event as ESPHealthEvent);
        break;
      case 'logic_execution':
        this.onLogicExecution(event as LogicExecutionEvent);
        break;
      case 'system_event':
        this.onSystemEvent(event as SystemEventEvent);
        break;
      case 'config_response':
        this.onConfigResponse(event as ConfigResponseEvent);
        break;
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
      setTimeout(() => this.connect(), delay);
    }
  }

  // Event handlers (override in subclass or set callbacks)
  onSensorData(event: SensorDataEvent): void {}
  onActuatorStatus(event: ActuatorStatusEvent): void {}
  onESPHealth(event: ESPHealthEvent): void {}
  onLogicExecution(event: LogicExecutionEvent): void {}
  onSystemEvent(event: SystemEventEvent): void {}
  onConfigResponse(event: ConfigResponseEvent): void {}

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Verwendung
const wsService = new WebSocketService('user_123_tab_1', accessToken);
wsService.onSensorData = (event) => {
  console.log(`Sensor ${event.data.esp_id}:${event.data.gpio} = ${event.data.value}`);
};
wsService.connect();

// Nur bestimmte ESPs abonnieren
wsService.subscribe({
  types: ['sensor_data'],
  esp_ids: ['ESP_12AB34CD', 'ESP_GARDEN01']
});
```

### 7.4 Rate Limiting

- **Limit:** 10 Nachrichten pro Sekunde pro Client
- **Überschreitung:** Nachricht wird gedroppt, Warning geloggt
- **Reconnect:** Bei Disconnect automatisch mit Exponential Backoff

### 7.5 Authentifizierung

- Token wird als Query-Parameter übergeben: `?token=<jwt_token>`
- Token wird bei Verbindung validiert
- Bei abgelaufenem Token: Verbindung wird mit Code 4001 geschlossen
- Bei Blacklist: Verbindung wird abgelehnt

---

## 8. Fehlerbehandlung

### 8.1 TypeScript Interfaces

```typescript
// ============================================================
// ERROR HANDLING INTERFACES
// ============================================================

/** Standard API Response */
interface BaseResponse {
  success: boolean;
  message?: string;
}

/** Error Response */
interface ErrorResponse {
  success: false;
  error: string;            // Error-Code (z.B. "NOT_FOUND", "VALIDATION_ERROR")
  detail: string;           // Menschenlesbare Beschreibung
  timestamp?: number;       // Unix Timestamp
  path?: string;            // Request-Pfad
  request_id?: string;      // Request-ID für Tracing
}

/** Validation Error Response (422) */
interface ValidationErrorResponse extends ErrorResponse {
  error: "VALIDATION_ERROR";
  errors: ValidationErrorItem[];
}

/** Validation Error Item */
interface ValidationErrorItem {
  loc: string[];            // Pfad zum Feld (z.B. ["body", "gpio"])
  msg: string;              // Fehlermeldung
  type: string;             // Fehlertyp (z.B. "value_error.number.not_le")
}

/** Paginated Response */
interface PaginatedResponse<T> {
  success: boolean;
  message?: string;
  data: T[];
  pagination: PaginationMeta;
}

/** Pagination Metadata */
interface PaginationMeta {
  page: number;             // Aktuelle Seite (1-indexed)
  page_size: number;        // Items pro Seite
  total_items: number;      // Gesamtanzahl
  total_pages: number;      // Gesamtseitenanzahl
  has_next: boolean;
  has_prev: boolean;
}

/** Pagination Query Params */
interface PaginationParams {
  page?: number;            // Default: 1, min: 1
  page_size?: number;       // Default: 20, min: 1, max: 100
}
```

### 8.2 HTTP Status Codes

| Code | Bedeutung | Wann verwendet |
|------|-----------|----------------|
| `200` | OK | Erfolgreiche Anfrage |
| `201` | Created | Ressource erstellt |
| `204` | No Content | Erfolgreich, keine Daten |
| `400` | Bad Request | Ungültige Anfrage |
| `401` | Unauthorized | Nicht authentifiziert |
| `403` | Forbidden | Keine Berechtigung |
| `404` | Not Found | Ressource nicht gefunden |
| `409` | Conflict | Konflikt (z.B. GPIO bereits belegt) |
| `422` | Validation Error | Validierungsfehler |
| `500` | Internal Error | Server-Fehler |
| `503` | Service Unavailable | ESP offline, MQTT nicht verbunden |

### 8.3 Error Codes

```typescript
// Error Code Kategorien
const ERROR_CODES = {
  // Authentication (1000-1099)
  AUTH_INVALID_CREDENTIALS: 1001,
  AUTH_TOKEN_EXPIRED: 1002,
  AUTH_TOKEN_INVALID: 1003,
  AUTH_TOKEN_BLACKLISTED: 1004,
  AUTH_INSUFFICIENT_PERMISSIONS: 1005,

  // Validation (1100-1199)
  VALIDATION_FAILED: 1100,
  VALIDATION_GPIO_INVALID: 1101,
  VALIDATION_GPIO_CONFLICT: 1102,
  VALIDATION_ESP_ID_INVALID: 1103,
  VALIDATION_ZONE_ID_INVALID: 1104,

  // Resources (1200-1299)
  RESOURCE_NOT_FOUND: 1200,
  RESOURCE_ALREADY_EXISTS: 1201,
  RESOURCE_CONFLICT: 1202,

  // ESP/Device (1300-1399)
  ESP_NOT_FOUND: 1300,
  ESP_OFFLINE: 1301,
  ESP_CONFIG_FAILED: 1302,
  ESP_COMMAND_TIMEOUT: 1303,

  // MQTT (1400-1499)
  MQTT_NOT_CONNECTED: 1400,
  MQTT_PUBLISH_FAILED: 1401,
  MQTT_SUBSCRIBE_FAILED: 1402,

  // Logic Engine (1500-1599)
  LOGIC_RULE_NOT_FOUND: 1500,
  LOGIC_VALIDATION_FAILED: 1501,
  LOGIC_EXECUTION_FAILED: 1502,

  // Sensor (1600-1699)
  SENSOR_NOT_FOUND: 1600,
  SENSOR_READ_FAILED: 1601,
  SENSOR_CONFIG_INVALID: 1602,

  // Actuator (1700-1799)
  ACTUATOR_NOT_FOUND: 1700,
  ACTUATOR_COMMAND_FAILED: 1701,
  ACTUATOR_EMERGENCY_STOPPED: 1702,
  ACTUATOR_SAFETY_CHECK_FAILED: 1703,

  // Zone (1800-1899)
  ZONE_NOT_FOUND: 1800,
  ZONE_ASSIGNMENT_FAILED: 1801,
} as const;
```

### 8.4 Beispiel Error Handling

```typescript
interface APIError {
  status: number;
  error: string;
  detail: string;
  errors?: ValidationErrorItem[];
}

async function apiRequest<T>(
  url: string,
  options: RequestInit,
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>)
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });
  const data = await response.json();

  if (!response.ok) {
    const error: APIError = {
      status: response.status,
      error: data.error || 'UNKNOWN_ERROR',
      detail: data.detail || 'An unknown error occurred',
      errors: data.errors
    };

    // Handle specific errors
    switch (response.status) {
      case 401:
        // Token expired - try refresh
        throw new AuthenticationError(error);
      case 403:
        throw new AuthorizationError(error);
      case 404:
        throw new NotFoundError(error);
      case 422:
        throw new ValidationError(error);
      case 503:
        throw new ServiceUnavailableError(error);
      default:
        throw new APIRequestError(error);
    }
  }

  return data as T;
}

// Custom Error Classes
class APIRequestError extends Error {
  constructor(public apiError: APIError) {
    super(apiError.detail);
    this.name = 'APIRequestError';
  }
}

class AuthenticationError extends APIRequestError {
  constructor(apiError: APIError) {
    super(apiError);
    this.name = 'AuthenticationError';
  }
}

class ValidationError extends APIRequestError {
  get validationErrors(): ValidationErrorItem[] {
    return this.apiError.errors || [];
  }
}

// Verwendung
try {
  const device = await apiRequest<ESPDeviceResponse>(
    '/api/v1/esp/devices/ESP_12AB34CD',
    { method: 'GET' },
    accessToken
  );
} catch (error) {
  if (error instanceof AuthenticationError) {
    // Redirect to login
  } else if (error instanceof ValidationError) {
    // Show validation errors
    error.validationErrors.forEach(e => {
      console.log(`Field ${e.loc.join('.')}: ${e.msg}`);
    });
  } else if (error instanceof NotFoundError) {
    // Show "not found" message
  }
}
```

---

## 9. Konstanten & Enums

### 9.1 Sensor Types

```typescript
type SensorType =
  | "temperature"
  | "humidity"
  | "sht31"       // Multi-value: temp + humidity
  | "ph"
  | "ec"
  | "moisture"
  | "pressure"
  | "co2"
  | "light"
  | "flow"
  | "analog"
  | "digital";

const SENSOR_TYPES: readonly SensorType[] = [
  "temperature", "humidity", "sht31", "ph", "ec",
  "moisture", "pressure", "co2", "light", "flow",
  "analog", "digital"
];

// Sensor Units
const SENSOR_UNITS: Record<SensorType, string> = {
  temperature: "°C",
  humidity: "%",
  sht31: "°C/%",
  ph: "pH",
  ec: "mS/cm",
  moisture: "%",
  pressure: "hPa",
  co2: "ppm",
  light: "lux",
  flow: "L/min",
  analog: "raw",
  digital: "0/1"
};
```

### 9.2 Actuator Types

```typescript
type ActuatorType =
  | "digital"
  | "pwm"
  | "servo"
  | "pump"       // Alias für digital
  | "valve"      // Alias für digital
  | "relay";     // Alias für digital

const ACTUATOR_TYPES: readonly ActuatorType[] = [
  "digital", "pwm", "servo", "pump", "valve", "relay"
];

// Actuator Value Ranges
const ACTUATOR_VALUE_RANGES: Record<ActuatorType, { min: number; max: number }> = {
  digital: { min: 0, max: 1 },
  pwm: { min: 0, max: 1 },
  servo: { min: 0, max: 1 },  // 0-180° mapped to 0-1
  pump: { min: 0, max: 1 },
  valve: { min: 0, max: 1 },
  relay: { min: 0, max: 1 }
};
```

### 9.3 ESP32 GPIO Constraints

```typescript
// Gültige GPIO-Pins für ESP32
const VALID_GPIO_PINS = [
  0, 1, 2, 3, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19,
  21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 39
];

// System-reservierte Pins (nicht verwendbar)
const RESERVED_GPIO_PINS = [
  6, 7, 8, 9, 10, 11  // Flash-Pins
];

// Input-Only Pins (nur für Sensoren)
const INPUT_ONLY_PINS = [34, 35, 36, 39];

// Validierung
const isValidGpio = (gpio: number): boolean => {
  return gpio >= 0 && gpio <= 39 && !RESERVED_GPIO_PINS.includes(gpio);
};

const canUseAsOutput = (gpio: number): boolean => {
  return isValidGpio(gpio) && !INPUT_ONLY_PINS.includes(gpio);
};
```

### 9.4 Logic Operators

```typescript
type LogicOperator = "AND" | "OR";
type ConditionOperator = ">" | "<" | ">=" | "<=" | "==" | "!=";
type ActionType = "actuator" | "notification" | "delay";
type ConditionType = "sensor_threshold" | "sensor" | "time_window" | "time" | "cooldown";
```

### 9.5 WebSocket Event Types

```typescript
type WebSocketEventType =
  | "sensor_data"
  | "actuator_status"
  | "logic_execution"
  | "esp_health"
  | "system_event"
  | "config_response";
```

---

## 10. Subzone API [ERGÄNZT]

> **GPIO-Level Zone-Gruppierung für Pin-basierte Isolation**

### 10.1 TypeScript Interfaces

```typescript
// ============================================================
// SUBZONE INTERFACES [ERGÄNZT]
// ============================================================

/** Subzone erstellen/zuweisen */
interface SubzoneAssignRequest {
  subzone_id: string;          // Technische ID (lowercase, alphanumeric + underscore)
  name?: string;               // Menschenlesbarer Name
  gpios: number[];             // GPIO-Pins die zur Subzone gehören (1-20 Pins)
  description?: string;        // Max 500 Zeichen
  parent_zone_id?: string;     // Optional: Übergeordnete Zone
}

/** Subzone-Zuweisung Response */
interface SubzoneAssignResponse {
  success: boolean;
  message: string;
  esp_id: string;
  subzone_id: string;
  name?: string;
  gpios: number[];
  parent_zone_id?: string;
  mqtt_topic_published: string;
  created_at: string;
}

/** Subzone entfernen Response */
interface SubzoneRemoveResponse {
  success: boolean;
  message: string;
  esp_id: string;
  subzone_id: string;
  gpios_released: number[];
}

/** Safe-Mode Anfrage */
interface SafeModeRequest {
  reason?: string;             // Grund für Safe-Mode Aktivierung
  notify_websocket?: boolean;  // WebSocket-Benachrichtigung senden (default: true)
}

/** Safe-Mode Response */
interface SafeModeResponse {
  success: boolean;
  message: string;
  esp_id: string;
  subzone_id: string;
  safe_mode_active: boolean;
  affected_gpios: number[];
  affected_actuators: number;
  timestamp: string;
}

/** Subzone ACK Payload (von ESP empfangen) */
interface SubzoneAckPayload {
  esp_id: string;
  subzone_id: string;
  status: "SUCCESS" | "FAILED";
  error_code?: number;
  error_message?: string;
  timestamp: number;
}

/** Subzone Info */
interface SubzoneInfo {
  subzone_id: string;
  name?: string;
  description?: string;
  esp_id: string;
  gpios: number[];
  parent_zone_id?: string;
  safe_mode_active: boolean;
  safe_mode_activated_at?: string;
  sensor_count: number;
  actuator_count: number;
  created_at: string;
  updated_at: string;
}

/** Subzone-Liste Response */
interface SubzoneListResponse {
  success: boolean;
  esp_id: string;
  subzones: SubzoneInfo[];
  total: number;
}
```

### 10.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `POST` | `/api/v1/subzone/{esp_id}/assign` | JWT | Subzone erstellen/zuweisen |
| `DELETE` | `/api/v1/subzone/{esp_id}/{subzone_id}` | JWT | Subzone entfernen |
| `GET` | `/api/v1/subzone/{esp_id}` | JWT | Alle Subzones eines ESP |
| `GET` | `/api/v1/subzone/{esp_id}/{subzone_id}` | JWT | Einzelne Subzone abrufen |
| `POST` | `/api/v1/subzone/{esp_id}/{subzone_id}/safe-mode` | JWT | Safe-Mode aktivieren |
| `DELETE` | `/api/v1/subzone/{esp_id}/{subzone_id}/safe-mode` | JWT | Safe-Mode deaktivieren |

### 10.3 Beispiele

```typescript
// Subzone für Bewässerung erstellen
const createIrrigationSubzone = async (
  espId: string,
  token: string
): Promise<SubzoneAssignResponse> => {
  const request: SubzoneAssignRequest = {
    subzone_id: "irrigation_zone_1",
    name: "Bewässerung Zone 1",
    gpios: [25, 26, 27],  // Pumpe, Ventil 1, Ventil 2
    description: "Hauptbewässerung Gewächshaus Nord",
    parent_zone_id: "greenhouse_north"
  };

  const response = await fetch(`/api/v1/subzone/${espId}/assign`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json();
};

// Safe-Mode bei Leckage aktivieren
const activateSafeMode = async (
  espId: string,
  subzoneId: string,
  token: string
): Promise<SafeModeResponse> => {
  const request: SafeModeRequest = {
    reason: "Wasserleckage erkannt",
    notify_websocket: true
  };

  const response = await fetch(`/api/v1/subzone/${espId}/${subzoneId}/safe-mode`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json();
};

// Alle Subzones eines ESP abrufen
const getSubzones = async (espId: string, token: string): Promise<SubzoneListResponse> => {
  const response = await fetch(`/api/v1/subzone/${espId}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### 10.4 Validierungsregeln

| Feld | Regeln |
|------|--------|
| `subzone_id` | 1-50 Zeichen, nur `[a-z0-9_]` |
| `gpios` | 1-20 Pins, jeder 0-39, keine Duplikate |
| `parent_zone_id` | Muss existieren wenn angegeben |
| GPIO-Konflikt | Pins dürfen nicht in anderer Subzone sein |

---

## 11. Health API [ERGÄNZT]

> **System-Monitoring und Kubernetes-Probes**

### 11.1 TypeScript Interfaces

```typescript
// ============================================================
// HEALTH CHECK INTERFACES [ERGÄNZT]
// ============================================================

/** Basis Health Response */
interface HealthResponse {
  success: boolean;
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;           // ISO 8601
  version: string;             // Server-Version
  uptime_seconds: number;
}

/** Detaillierter Health-Check */
interface DetailedHealthResponse extends HealthResponse {
  components: {
    database: DatabaseHealth;
    mqtt: MQTTHealth;
    websocket: WebSocketHealth;
    logic_engine: LogicEngineHealth;
    scheduler: SchedulerHealth;
  };
  system: SystemResourceHealth;
}

/** Datenbank Health */
interface DatabaseHealth {
  status: "healthy" | "degraded" | "unhealthy";
  connected: boolean;
  pool_size: number;
  active_connections: number;
  latency_ms: number;
  last_error?: string;
}

/** MQTT Health */
interface MQTTHealth {
  status: "healthy" | "degraded" | "unhealthy";
  connected: boolean;
  broker_host: string;
  subscriptions_active: number;
  messages_published_total: number;
  messages_received_total: number;
  last_message_received?: string;
  reconnect_count: number;
}

/** WebSocket Health */
interface WebSocketHealth {
  status: "healthy" | "degraded" | "unhealthy";
  active_connections: number;
  max_connections: number;
  messages_sent_total: number;
  rate_limit_hits: number;
}

/** Logic Engine Health */
interface LogicEngineHealth {
  status: "healthy" | "degraded" | "unhealthy";
  running: boolean;
  active_rules: number;
  rules_evaluated_total: number;
  actions_executed_total: number;
  last_evaluation?: string;
  average_evaluation_time_ms: number;
}

/** Scheduler Health */
interface SchedulerHealth {
  status: "healthy" | "degraded" | "unhealthy";
  running: boolean;
  jobs_scheduled: number;
  jobs_executed_total: number;
  next_job_run?: string;
}

/** System-Ressourcen */
interface SystemResourceHealth {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_available_mb: number;
  disk_percent: number;
  disk_free_gb: number;
}

/** ESP Health Summary */
interface ESPHealthSummaryResponse {
  success: boolean;
  total_devices: number;
  online_devices: number;
  offline_devices: number;
  degraded_devices: number;
  devices: ESPHealthItem[];
}

/** ESP Health Item */
interface ESPHealthItem {
  esp_id: string;
  name?: string;
  status: "healthy" | "degraded" | "critical" | "offline";
  is_online: boolean;
  last_seen?: string;
  wifi_rssi?: number;
  heap_free?: number;
  error_count: number;
  sensor_count: number;
  actuator_count: number;
}

/** Prometheus Metrics Response */
interface PrometheusMetrics {
  // Raw Prometheus text format
  // Content-Type: text/plain; version=0.0.4
}

/** Kubernetes Liveness Probe */
interface LivenessResponse {
  status: "ok" | "fail";
  timestamp: string;
}

/** Kubernetes Readiness Probe */
interface ReadinessResponse {
  status: "ready" | "not_ready";
  timestamp: string;
  checks: {
    database: boolean;
    mqtt: boolean;
    scheduler: boolean;
  };
}
```

### 11.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/health/` | - | Basis Health-Check |
| `GET` | `/api/v1/health/detailed` | JWT | Detaillierter Health-Check |
| `GET` | `/api/v1/health/esp` | JWT | ESP-Geräte Health Summary |
| `GET` | `/api/v1/health/metrics` | - | Prometheus Metrics |
| `GET` | `/api/v1/health/live` | - | Kubernetes Liveness Probe |
| `GET` | `/api/v1/health/ready` | - | Kubernetes Readiness Probe |

### 11.3 Beispiele

```typescript
// Basis Health-Check (ohne Auth)
const checkHealth = async (): Promise<HealthResponse> => {
  const response = await fetch('/api/v1/health/');
  return response.json();
};

// Detaillierter Health-Check
const getDetailedHealth = async (token: string): Promise<DetailedHealthResponse> => {
  const response = await fetch('/api/v1/health/detailed', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// ESP Health Summary
const getESPHealthSummary = async (token: string): Promise<ESPHealthSummaryResponse> => {
  const response = await fetch('/api/v1/health/esp', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Kubernetes Probes (für Container-Orchestrierung)
// Liveness: Ist der Server am Leben?
const livenessCheck = async (): Promise<boolean> => {
  try {
    const response = await fetch('/api/v1/health/live');
    const data: LivenessResponse = await response.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
};

// Readiness: Ist der Server bereit für Traffic?
const readinessCheck = async (): Promise<boolean> => {
  try {
    const response = await fetch('/api/v1/health/ready');
    const data: ReadinessResponse = await response.json();
    return data.status === 'ready';
  } catch {
    return false;
  }
};
```

### 11.4 Health Status Logik

| Status | Bedingung |
|--------|-----------|
| `healthy` | Alle Komponenten OK |
| `degraded` | Mindestens eine Komponente hat Probleme |
| `unhealthy` | Kritische Komponente ausgefallen |

---

## 12. Users API [ERGÄNZT]

> **Benutzerverwaltung (Admin-Only)**

### 12.1 TypeScript Interfaces

```typescript
// ============================================================
// USER MANAGEMENT INTERFACES [ERGÄNZT]
// ============================================================

/** User-Rollen */
type UserRole = "admin" | "operator" | "viewer";

/** User erstellen (Admin-Only) */
interface UserCreate {
  username: string;            // 3-50 Zeichen, alphanumerisch + Unterstrich
  email: string;               // Valide E-Mail
  password: string;            // Min 8 Zeichen, Komplexitätsregeln
  display_name?: string;       // Max 100 Zeichen
  role?: UserRole;             // Default: "viewer"
  is_active?: boolean;         // Default: true
}

/** User aktualisieren */
interface UserUpdate {
  email?: string;
  display_name?: string;
  role?: UserRole;
  is_active?: boolean;
}

/** User Response */
interface UserDetailResponse {
  id: number;
  username: string;
  email: string;
  display_name?: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;          // ISO 8601
  updated_at: string;
  last_login?: string;
  login_count: number;
}

/** User Liste Response */
interface UserListResponse {
  success: boolean;
  users: UserDetailResponse[];
  total: number;
  pagination: PaginationMeta;
}

/** Passwort Reset (Admin) */
interface PasswordReset {
  new_password: string;        // Min 8 Zeichen
  force_change_on_login?: boolean;  // Default: true
}

/** Passwort ändern (Self-Service) */
interface PasswordChange {
  current_password: string;
  new_password: string;
}

/** Message Response */
interface MessageResponse {
  success: boolean;
  message: string;
}
```

### 12.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/users/` | Admin | Alle User abrufen |
| `POST` | `/api/v1/users/` | Admin | Neuen User erstellen |
| `GET` | `/api/v1/users/{user_id}` | Admin | Einzelnen User abrufen |
| `PATCH` | `/api/v1/users/{user_id}` | Admin | User aktualisieren |
| `DELETE` | `/api/v1/users/{user_id}` | Admin | User löschen |
| `POST` | `/api/v1/users/{user_id}/reset-password` | Admin | Passwort zurücksetzen |
| `PATCH` | `/api/v1/users/me/password` | JWT | Eigenes Passwort ändern |

### 12.3 Beispiele

```typescript
// Neuen Operator erstellen
const createOperator = async (token: string): Promise<UserDetailResponse> => {
  const user: UserCreate = {
    username: "operator_anna",
    email: "anna@example.com",
    password: "SecurePass123!",
    display_name: "Anna Müller",
    role: "operator",
    is_active: true
  };

  const response = await fetch('/api/v1/users/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(user)
  });
  return response.json();
};

// Eigenes Passwort ändern
const changeMyPassword = async (
  currentPassword: string,
  newPassword: string,
  token: string
): Promise<MessageResponse> => {
  const request: PasswordChange = {
    current_password: currentPassword,
    new_password: newPassword
  };

  const response = await fetch('/api/v1/users/me/password', {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json();
};

// Alle User abrufen (paginiert)
const getUsers = async (page: number, token: string): Promise<UserListResponse> => {
  const response = await fetch(`/api/v1/users/?page=${page}&page_size=20`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### 12.4 Rollen-Berechtigungen

| Rolle | Beschreibung | Berechtigungen |
|-------|--------------|----------------|
| `admin` | Administrator | Voller Zugriff, Benutzerverwaltung |
| `operator` | Bediener | Gerätekontrolle, Regeln, keine Benutzerverwaltung |
| `viewer` | Betrachter | Nur Lesen, kein Schreibzugriff |

---

## 13. Audit API [ERGÄNZT]

> **Audit-Log-System mit Retention-Management**

### 13.1 TypeScript Interfaces

```typescript
// ============================================================
// AUDIT LOG INTERFACES [ERGÄNZT]
// ============================================================

/** Audit Event Types */
type AuditEventType =
  | "auth.login"
  | "auth.logout"
  | "auth.failed_login"
  | "user.created"
  | "user.updated"
  | "user.deleted"
  | "esp.registered"
  | "esp.updated"
  | "esp.deleted"
  | "esp.config_sent"
  | "sensor.created"
  | "sensor.updated"
  | "sensor.deleted"
  | "actuator.created"
  | "actuator.updated"
  | "actuator.deleted"
  | "actuator.command"
  | "actuator.emergency_stop"
  | "logic.rule_created"
  | "logic.rule_updated"
  | "logic.rule_deleted"
  | "logic.rule_executed"
  | "zone.assigned"
  | "zone.removed"
  | "subzone.created"
  | "subzone.removed"
  | "subzone.safe_mode"
  | "system.startup"
  | "system.shutdown"
  | "system.error";

/** Audit Log Entry */
interface AuditLogEntry {
  id: number;
  event_type: AuditEventType;
  timestamp: string;           // ISO 8601
  user_id?: number;
  username?: string;
  ip_address?: string;
  user_agent?: string;
  resource_type?: string;      // z.B. "esp", "sensor", "actuator"
  resource_id?: string;        // z.B. "ESP_12AB34CD"
  action: string;              // z.B. "CREATE", "UPDATE", "DELETE"
  details: Record<string, any>;
  success: boolean;
  error_message?: string;
}

/** Audit Log Query */
interface AuditLogQuery {
  event_type?: AuditEventType | AuditEventType[];
  user_id?: number;
  resource_type?: string;
  resource_id?: string;
  success?: boolean;
  start_time?: string;         // ISO 8601
  end_time?: string;           // ISO 8601
  page?: number;
  page_size?: number;          // Default: 50, Max: 500
}

/** Audit Log List Response */
interface AuditLogListResponse {
  success: boolean;
  logs: AuditLogEntry[];
  total: number;
  pagination: PaginationMeta;
  query_time_ms: number;
}

/** Aggregierte Events */
interface AggregatedEventsResponse {
  success: boolean;
  period_start: string;
  period_end: string;
  events_by_type: Record<AuditEventType, number>;
  events_by_hour: { hour: string; count: number }[];
  total_events: number;
}

/** Error-Log Response */
interface ErrorLogResponse {
  success: boolean;
  errors: AuditLogEntry[];
  total: number;
  pagination: PaginationMeta;
}

/** Audit Statistiken */
interface AuditStatisticsResponse {
  success: boolean;
  total_events: number;
  events_today: number;
  events_this_week: number;
  events_this_month: number;
  top_event_types: { event_type: string; count: number }[];
  top_users: { username: string; count: number }[];
  error_rate_percent: number;
  storage_used_mb: number;
}

/** Retention Config */
interface RetentionConfig {
  enabled: boolean;
  retention_days: number;      // 1-365
  backup_before_delete: boolean;
  auto_cleanup_enabled: boolean;
  cleanup_batch_size: number;  // 100-10000
}

/** Retention Config Update */
interface RetentionConfigUpdate {
  enabled?: boolean;
  retention_days?: number;
  backup_before_delete?: boolean;
  auto_cleanup_enabled?: boolean;
  cleanup_batch_size?: number;
}

/** Cleanup Response */
interface CleanupResponse {
  success: boolean;
  message: string;
  deleted_count: number;
  backup_created: boolean;
  backup_file?: string;
  duration_ms: number;
}

/** Backup Info */
interface BackupInfo {
  filename: string;
  created_at: string;
  size_bytes: number;
  record_count: number;
  retention_start: string;
  retention_end: string;
}

/** Backup List Response */
interface BackupListResponse {
  success: boolean;
  backups: BackupInfo[];
  total_size_mb: number;
}
```

### 13.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/audit/` | JWT | Audit-Logs abrufen (gefiltert) |
| `GET` | `/api/v1/audit/events/aggregated` | JWT | Aggregierte Events |
| `GET` | `/api/v1/audit/errors` | JWT | Nur Fehler-Logs |
| `GET` | `/api/v1/audit/statistics` | JWT | Statistiken |
| `GET` | `/api/v1/audit/retention` | Admin | Retention-Config abrufen |
| `PUT` | `/api/v1/audit/retention` | Admin | Retention-Config ändern |
| `POST` | `/api/v1/audit/cleanup` | Admin | Manuelles Cleanup |
| `GET` | `/api/v1/audit/backups` | Admin | Backups auflisten |
| `POST` | `/api/v1/audit/backups` | Admin | Backup erstellen |
| `DELETE` | `/api/v1/audit/backups/{filename}` | Admin | Backup löschen |

### 13.3 Beispiele

```typescript
// Audit-Logs abrufen mit Filtern
const getAuditLogs = async (
  query: AuditLogQuery,
  token: string
): Promise<AuditLogListResponse> => {
  const params = new URLSearchParams();
  if (query.event_type) {
    if (Array.isArray(query.event_type)) {
      query.event_type.forEach(t => params.append('event_type', t));
    } else {
      params.set('event_type', query.event_type);
    }
  }
  if (query.start_time) params.set('start_time', query.start_time);
  if (query.end_time) params.set('end_time', query.end_time);
  if (query.page) params.set('page', query.page.toString());
  if (query.page_size) params.set('page_size', query.page_size.toString());

  const response = await fetch(`/api/v1/audit/?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Statistiken abrufen
const getAuditStatistics = async (token: string): Promise<AuditStatisticsResponse> => {
  const response = await fetch('/api/v1/audit/statistics', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Retention-Config ändern (Admin)
const updateRetention = async (
  config: RetentionConfigUpdate,
  token: string
): Promise<RetentionConfig> => {
  const response = await fetch('/api/v1/audit/retention', {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(config)
  });
  return response.json();
};

// Manuelles Cleanup mit Dry-Run
const runCleanup = async (
  dryRun: boolean,
  token: string
): Promise<CleanupResponse> => {
  const response = await fetch(`/api/v1/audit/cleanup?dry_run=${dryRun}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### 13.4 Retention Best Practices

| Einstellung | Empfehlung |
|-------------|------------|
| `retention_days` | 90 Tage für Produktiv, 30 für Dev |
| `backup_before_delete` | Immer `true` für Compliance |
| `auto_cleanup_enabled` | `true` mit täglichem Schedule |
| `cleanup_batch_size` | 1000-5000 je nach Last |

---

## 14. Debug/Mock ESP API [ERGÄNZT]

> **Mock-ESP32-Simulation für Tests ohne Hardware**

### 14.1 TypeScript Interfaces

```typescript
// ============================================================
// MOCK ESP INTERFACES [ERGÄNZT]
// ============================================================

/** Mock ESP System States */
type MockSystemState =
  | "BOOT"
  | "WIFI_SETUP"
  | "WIFI_CONNECTED"
  | "MQTT_CONNECTING"
  | "MQTT_CONNECTED"
  | "AWAITING_USER_CONFIG"
  | "ZONE_CONFIGURED"
  | "SENSORS_CONFIGURED"
  | "OPERATIONAL"
  | "LIBRARY_DOWNLOADING"
  | "SAFE_MODE"
  | "ERROR";

/** Sensor Quality Level */
type QualityLevel = "excellent" | "good" | "fair" | "poor" | "bad" | "stale";

/** Variation Pattern für Simulation */
type VariationPattern = "constant" | "random" | "drift";

/** Mock Sensor Config */
interface MockSensorConfig {
  gpio: number;                // 0-39
  sensor_type: SensorType;
  name?: string;
  subzone_id?: string;
  raw_value: number;           // Basis-Wert
  unit: string;
  quality?: QualityLevel;      // Default: "good"
  raw_mode?: boolean;          // Default: true

  // Multi-Value Support (I2C/OneWire)
  interface_type?: "I2C" | "ONEWIRE" | "ANALOG" | "DIGITAL";
  onewire_address?: string;    // 16 hex chars für DS18B20
  i2c_address?: number;        // 0-127

  // Simulation Parameter
  interval_seconds?: number;   // 1-3600, default: 30
  variation_pattern?: VariationPattern;
  variation_range?: number;    // >= 0
  min_value?: number;
  max_value?: number;
}

/** Mock Actuator Config */
interface MockActuatorConfig {
  gpio: number;                // 0-39
  actuator_type: ActuatorType; // Default: "relay"
  name?: string;
  state?: boolean;             // Default: false
  pwm_value?: number;          // 0.0-1.0
  min_value?: number;
  max_value?: number;
}

/** Mock ESP erstellen */
interface MockESPCreate {
  esp_id: string;              // Format: ESP_XXXXXX oder MOCK_XXXXXX
  zone_id?: string;
  zone_name?: string;
  master_zone_id?: string;
  subzone_id?: string;
  sensors?: MockSensorConfig[];
  actuators?: MockActuatorConfig[];
  auto_heartbeat?: boolean;    // Default: false
  heartbeat_interval_seconds?: number;  // 5-300, default: 60
}

/** Mock ESP aktualisieren */
interface MockESPUpdate {
  zone_id?: string;
  master_zone_id?: string;
  subzone_id?: string;
  auto_heartbeat?: boolean;
  heartbeat_interval_seconds?: number;
}

/** Sensor-Wert setzen */
interface SetSensorValueRequest {
  raw_value: number;
  quality?: QualityLevel;
  publish?: boolean;           // MQTT publizieren (default: true)
}

/** Batch Sensor-Werte setzen */
interface BatchSensorValueRequest {
  values: Record<number, number>;  // GPIO -> Value
  publish?: boolean;
}

/** Actuator-Befehl (Simulation) */
interface ActuatorCommandRequest {
  command: "ON" | "OFF" | "PWM" | "TOGGLE";
  value?: number;              // 0.0-1.0 für PWM
  duration?: number;           // Auto-off in Sekunden (0 = unlimited)
}

/** State Transition Request */
interface StateTransitionRequest {
  state: MockSystemState;
  reason?: string;
}

/** Mock ESP Response */
interface MockESPResponse {
  esp_id: string;
  name?: string;
  zone_id?: string;
  zone_name?: string;
  master_zone_id?: string;
  subzone_id?: string;
  system_state: MockSystemState;
  sensors: MockSensorResponse[];
  actuators: MockActuatorResponse[];
  auto_heartbeat: boolean;
  heap_free: number;
  wifi_rssi: number;
  uptime: number;
  last_heartbeat?: string;
  created_at: string;
  connected: boolean;
  hardware_type: string;       // "MOCK_ESP32"
  status: "online" | "offline";
}

/** Mock Sensor Response */
interface MockSensorResponse {
  gpio: number;
  sensor_type: string;
  name?: string;
  subzone_id?: string;
  raw_value: number;
  unit: string;
  quality: string;
  raw_mode: boolean;
  last_read?: string;
}

/** Mock Actuator Response */
interface MockActuatorResponse {
  gpio: number;
  actuator_type: string;
  name?: string;
  state: boolean;
  pwm_value: number;
  emergency_stopped: boolean;
  last_command?: string;
}

/** Heartbeat Response */
interface HeartbeatResponse {
  success: boolean;
  esp_id: string;
  timestamp: string;
  message_published: boolean;
  payload?: Record<string, any>;
}

/** Mock ESP List Response */
interface MockESPListResponse {
  success: boolean;
  data: MockESPResponse[];
  total: number;
}

/** Actuator Command Response */
interface MockActuatorCommandResponse {
  success: boolean;
  esp_id: string;
  gpio: number;
  command: string;
  state: boolean;
  pwm_value: number;
  message: string;
}
```

### 14.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `POST` | `/api/v1/debug/mock-esp` | JWT | Mock ESP erstellen |
| `GET` | `/api/v1/debug/mock-esp` | JWT | Alle Mock ESPs auflisten |
| `GET` | `/api/v1/debug/mock-esp/{esp_id}` | JWT | Mock ESP Details |
| `PATCH` | `/api/v1/debug/mock-esp/{esp_id}` | JWT | Mock ESP aktualisieren |
| `DELETE` | `/api/v1/debug/mock-esp/{esp_id}` | JWT | Mock ESP löschen |
| `POST` | `/api/v1/debug/mock-esp/{esp_id}/heartbeat` | JWT | Heartbeat triggern |
| `POST` | `/api/v1/debug/mock-esp/{esp_id}/state` | JWT | State-Transition |
| `POST` | `/api/v1/debug/mock-esp/{esp_id}/sensor/{gpio}/value` | JWT | Sensor-Wert setzen |
| `POST` | `/api/v1/debug/mock-esp/{esp_id}/sensor/batch` | JWT | Batch Sensor-Werte |
| `POST` | `/api/v1/debug/mock-esp/{esp_id}/actuator/{gpio}/command` | JWT | Actuator-Befehl |

### 14.3 Beispiele

```typescript
// Mock ESP für Tests erstellen
const createMockESP = async (token: string): Promise<MockESPResponse> => {
  const mockEsp: MockESPCreate = {
    esp_id: "MOCK_TEST_001",
    zone_id: "test_zone",
    zone_name: "Test Zone",
    sensors: [
      {
        gpio: 4,
        sensor_type: "temperature",
        name: "Test Temp Sensor",
        raw_value: 22.5,
        unit: "°C",
        interval_seconds: 10,
        variation_pattern: "random",
        variation_range: 2.0
      },
      {
        gpio: 34,
        sensor_type: "ph",
        name: "Test pH Sensor",
        raw_value: 6.5,
        unit: "pH"
      }
    ],
    actuators: [
      {
        gpio: 25,
        actuator_type: "pump",
        name: "Test Pump"
      }
    ],
    auto_heartbeat: true,
    heartbeat_interval_seconds: 30
  };

  const response = await fetch('/api/v1/debug/mock-esp', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(mockEsp)
  });
  return response.json();
};

// Sensor-Wert für Tests setzen
const setMockSensorValue = async (
  espId: string,
  gpio: number,
  value: number,
  token: string
): Promise<void> => {
  const request: SetSensorValueRequest = {
    raw_value: value,
    quality: "good",
    publish: true  // MQTT-Nachricht senden
  };

  await fetch(`/api/v1/debug/mock-esp/${espId}/sensor/${gpio}/value`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
};

// State-Transition simulieren
const simulateESPState = async (
  espId: string,
  state: MockSystemState,
  token: string
): Promise<void> => {
  const request: StateTransitionRequest = {
    state: state,
    reason: "Test state transition"
  };

  await fetch(`/api/v1/debug/mock-esp/${espId}/state`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
};

// Actuator-Befehl über MQTT-Flow simulieren
const simulateActuatorCommand = async (
  espId: string,
  gpio: number,
  token: string
): Promise<MockActuatorCommandResponse> => {
  const request: ActuatorCommandRequest = {
    command: "ON",
    duration: 60  // Auto-off nach 60 Sekunden
  };

  const response = await fetch(`/api/v1/debug/mock-esp/${espId}/actuator/${gpio}/command`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request)
  });
  return response.json();
};
```

### 14.4 Mock ESP Architektur

- **DB-First:** Mock ESPs werden in PostgreSQL persistiert
- **SimulationScheduler:** APScheduler für automatische Heartbeats/Sensor-Updates
- **MQTT-Integration:** Volle MQTT-Nachrichtenflow-Simulation
- **Server-Restart-Recovery:** Mock ESPs bleiben nach Neustart erhalten

---

## 15. Sequences API [ERGÄNZT]

> **Sequenz-Monitoring und -Steuerung für Multi-Step Actions**

### 15.1 TypeScript Interfaces

```typescript
// ============================================================
// SEQUENCE INTERFACES [ERGÄNZT]
// ============================================================

/** Sequenz-Status */
type SequenceStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timeout";

/** Step Failure Behavior */
type StepFailureAction = "abort" | "continue" | "retry";

/** Sequenz-Step mit Action */
interface SequenceStepWithAction {
  name?: string;
  action: Record<string, any>;  // Actuator/Notification Action
  delay_before_seconds?: number;  // 0-3600
  delay_after_seconds?: number;   // 0-3600
  timeout_seconds?: number;       // 1-300, default: 30
  on_failure?: StepFailureAction; // Default: "abort"
  retry_count?: number;           // 0-3
  retry_delay_seconds?: number;   // 0-60
}

/** Reiner Delay-Step */
interface SequenceStepDelayOnly {
  name?: string;
  delay_seconds: number;          // 0.1-3600
}

type SequenceStep = SequenceStepWithAction | SequenceStepDelayOnly;

/** Sequenz-Action Schema (für Logic Rules) */
interface SequenceActionSchema {
  type: "sequence";
  sequence_id?: string;           // Auto-generiert wenn nicht angegeben
  description?: string;           // Max 500 Zeichen
  abort_on_failure?: boolean;     // Default: true
  max_duration_seconds?: number;  // 1-86400, default: 3600
  steps: SequenceStep[];          // 1-50 Steps
}

/** Step-Ergebnis */
interface StepResult {
  step_index: number;
  step_name?: string;
  success: boolean;
  message: string;
  error_code?: number;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  retries: number;
}

/** Sequenz-Progress */
interface SequenceProgressSchema {
  sequence_id: string;
  rule_id: string;
  rule_name?: string;
  status: SequenceStatus;
  description?: string;
  current_step: number;
  total_steps: number;
  progress_percent: number;
  started_at: string;
  completed_at?: string;
  estimated_completion?: string;
  step_results: StepResult[];
  current_step_name?: string;
  error?: string;
  error_code?: number;
}

/** Sequenz-Liste Response */
interface SequenceListResponse {
  success: boolean;
  sequences: SequenceProgressSchema[];
  total: number;
  running: number;
  completed: number;
  failed: number;
}

/** Sequenz-Statistiken */
interface SequenceStatsResponse {
  success: boolean;
  total_sequences: number;
  running: number;
  completed_last_hour: number;
  failed_last_hour: number;
  average_duration_seconds: number;
  longest_sequence_id?: string;
  most_common_failure_step?: string;
}

/** Cancel Response */
interface SequenceCancelResponse {
  success: boolean;
  message: string;
  reason: string;
}
```

### 15.2 Endpoints

| Method | Endpoint | Auth | Beschreibung |
|--------|----------|------|--------------|
| `GET` | `/api/v1/sequences` | JWT | Alle Sequenzen abrufen |
| `GET` | `/api/v1/sequences/stats` | JWT | Sequenz-Statistiken |
| `GET` | `/api/v1/sequences/{sequence_id}` | JWT | Einzelne Sequenz |
| `POST` | `/api/v1/sequences/{sequence_id}/cancel` | JWT | Sequenz abbrechen |

### 15.3 Beispiele

```typescript
// Laufende Sequenzen abrufen
const getRunningSequences = async (token: string): Promise<SequenceListResponse> => {
  const response = await fetch('/api/v1/sequences?running_only=true', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Sequenz-Statistiken
const getSequenceStats = async (token: string): Promise<SequenceStatsResponse> => {
  const response = await fetch('/api/v1/sequences/stats', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Einzelne Sequenz überwachen
const watchSequence = async (
  sequenceId: string,
  token: string
): Promise<SequenceProgressSchema> => {
  const response = await fetch(`/api/v1/sequences/${sequenceId}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Sequenz abbrechen
const cancelSequence = async (
  sequenceId: string,
  reason: string,
  token: string
): Promise<SequenceCancelResponse> => {
  const response = await fetch(
    `/api/v1/sequences/${sequenceId}/cancel?reason=${encodeURIComponent(reason)}`,
    {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    }
  );
  return response.json();
};

// Sequenz-Action in Logic Rule verwenden
const createSequenceRule: LogicRuleCreate = {
  name: "Bewässerungssequenz",
  description: "Sequentielle Bewässerung aller Zonen",
  conditions: {
    type: "time_window",
    start_time: "06:00",
    end_time: "06:30"
  },
  actions: [
    {
      type: "sequence",
      description: "3-Zonen Bewässerung",
      steps: [
        {
          name: "Zone 1 Bewässerung",
          action: {
            type: "actuator",
            esp_id: "ESP_GARDEN01",
            gpio: 25,
            actuator_type: "valve",
            value: 1
          },
          delay_after_seconds: 300  // 5 Min Bewässerung
        },
        {
          delay_seconds: 10  // Pause zwischen Zonen
        },
        {
          name: "Zone 2 Bewässerung",
          action: {
            type: "actuator",
            esp_id: "ESP_GARDEN01",
            gpio: 26,
            actuator_type: "valve",
            value: 1
          },
          delay_after_seconds: 300
        }
      ],
      max_duration_seconds: 1800  // Max 30 Min
    }
  ]
};
```

---

## 2.5 Logic Engine Erweiterungen [ERWEITERT]

### 2.5.1 Hysterese-Bedingungen

```typescript
// ============================================================
// HYSTERESIS CONDITION [ERWEITERT]
// ============================================================

/** Hysterese-Bedingung (Anti-Flatter-Logik) */
interface HysteresisCondition {
  type: "hysteresis";
  esp_id: string;
  gpio: number;
  sensor_type?: SensorType;

  // Modus A: Kühlung (Lüfter an wenn heiß)
  activate_above?: number;     // Aktivierung wenn value > threshold
  deactivate_below?: number;   // Deaktivierung wenn value < threshold

  // Modus B: Heizung (Heizung an wenn kalt)
  activate_below?: number;     // Aktivierung wenn value < threshold
  deactivate_above?: number;   // Deaktivierung wenn value > threshold
}

// Beispiel: Lüfter-Steuerung mit Hysterese
const coolingHysteresis: HysteresisCondition = {
  type: "hysteresis",
  esp_id: "ESP_GREENHOUSE_1",
  gpio: 4,
  sensor_type: "temperature",
  activate_above: 28.0,   // Lüfter AN wenn > 28°C
  deactivate_below: 24.0  // Lüfter AUS wenn < 24°C
};

// Beispiel: Heizungs-Steuerung mit Hysterese
const heatingHysteresis: HysteresisCondition = {
  type: "hysteresis",
  esp_id: "ESP_GREENHOUSE_1",
  gpio: 4,
  sensor_type: "temperature",
  activate_below: 18.0,   // Heizung AN wenn < 18°C
  deactivate_above: 22.0  // Heizung AUS wenn > 22°C
};
```

### 2.5.2 Sequenz-Aktionen

```typescript
/** Sequenz-Action für Multi-Step Automation */
interface SequenceAction {
  type: "sequence";
  sequence_id?: string;
  description?: string;
  abort_on_failure?: boolean;
  max_duration_seconds?: number;
  steps: SequenceStep[];
}
```

### 2.5.3 Safety Components

```typescript
// ============================================================
// SAFETY COMPONENTS [ERWEITERT]
// ============================================================

/** Conflict Manager - Priority-basiertes Actuator-Locking */
interface ConflictLock {
  actuator_key: string;        // Format: "esp_id:gpio"
  owner_rule_id: string;
  priority: number;            // Höher = wichtiger, SAFETY = -1000
  acquired_at: string;
  ttl_seconds: number;         // Default: 60
  is_safety_lock: boolean;
}

/** Rate Limiter - Hierarchische Rate-Limits */
interface RateLimitConfig {
  global_limit: number;        // Default: 100/sec
  per_esp_limit: number;       // Default: 20/sec
  per_rule_limit?: number;     // Aus DB: max_executions_per_hour
  burst_multiplier: number;    // Default: 1.5
}

/** Loop Detector - Zykluserkennung */
interface RuleDependency {
  source_rule_id: string;
  target_actuator: string;     // "esp_id:gpio"
  depends_on_sensor: string;   // "esp_id:gpio"
}

// Loop Detector prüft auf Zyklen:
// Rule A → Actuator X → beeinflusst Sensor Y → Rule B → Actuator Z → beeinflusst Sensor W → Rule A
// Max Chain Depth: 10
```

---

## 7.5 WebSocket Erweiterungen [ERWEITERT]

### 7.5.1 Zusätzliche Event-Typen

```typescript
// ============================================================
// ADDITIONAL WEBSOCKET EVENTS [ERWEITERT]
// ============================================================

/** Device Discovered Event (Mock ESP erstellt) */
interface DeviceDiscoveredEvent extends WebSocketEvent {
  type: "device_discovered";
  data: {
    esp_id: string;
    hardware_type: string;     // "MOCK_ESP32" oder "ESP32"
    zone_id?: string;
    is_mock: boolean;
    discovered_at: string;
  };
}

/** Subzone Safe Mode Event */
interface SubzoneSafeModeEvent extends WebSocketEvent {
  type: "subzone_safe_mode";
  data: {
    esp_id: string;
    subzone_id: string;
    safe_mode_active: boolean;
    reason?: string;
    affected_gpios: number[];
  };
}

/** Sequence Progress Event */
interface SequenceProgressEvent extends WebSocketEvent {
  type: "sequence_progress";
  data: {
    sequence_id: string;
    rule_id: string;
    status: SequenceStatus;
    current_step: number;
    total_steps: number;
    progress_percent: number;
    current_step_name?: string;
  };
}

/** Audit Event (für Admin-Dashboard) */
interface AuditWebSocketEvent extends WebSocketEvent {
  type: "audit_event";
  data: {
    event_type: AuditEventType;
    resource_type?: string;
    resource_id?: string;
    user?: string;
    success: boolean;
  };
}

// Erweiterte Event-Typen
type ExtendedWebSocketEventType =
  | WebSocketEventType
  | "device_discovered"
  | "subzone_safe_mode"
  | "sequence_progress"
  | "audit_event";
```

---

## Anhang A: Vollständige Type Definitions

```typescript
// ============================================================
// COMPLETE TYPE DEFINITIONS FILE
// Copy this to your frontend project as types/api.ts
// ============================================================

// Auth Types
export interface LoginRequest { username: string; password: string; }
export interface LoginResponse { success: boolean; message?: string; access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number; user: UserResponse; }
export interface RegisterRequest { username: string; email: string; password: string; display_name?: string; }
export interface RegisterResponse { success: boolean; message?: string; user: UserResponse; }
export interface RefreshTokenRequest { refresh_token: string; }
export interface RefreshTokenResponse { success: boolean; message?: string; access_token: string; token_type: "bearer"; expires_in: number; }
export interface SetupRequest { username: string; email: string; password: string; display_name?: string; }
export interface SetupResponse { success: boolean; message?: string; user: UserResponse; access_token: string; refresh_token: string; }
export interface UserResponse { id: number; username: string; email: string; display_name?: string; role: "admin" | "user"; is_active: boolean; created_at: string; last_login?: string; }
export interface SetupStatusResponse { success: boolean; needs_setup: boolean; user_count: number; }

// Sensor Types
export type SensorType = "temperature" | "humidity" | "sht31" | "ph" | "ec" | "moisture" | "pressure" | "co2" | "light" | "flow" | "analog" | "digital";
export interface SensorConfigCreate { gpio: number; sensor_type: SensorType; name?: string; description?: string; interval_ms?: number; enabled?: boolean; pi_enhanced?: boolean; calibration_offset?: number; calibration_scale?: number; i2c_address?: number; i2c_bus?: number; onewire_address?: string; onewire_bus_gpio?: number; alert_min?: number; alert_max?: number; alert_enabled?: boolean; }
export interface SensorConfigUpdate { name?: string; description?: string; interval_ms?: number; enabled?: boolean; pi_enhanced?: boolean; calibration_offset?: number; calibration_scale?: number; alert_min?: number; alert_max?: number; alert_enabled?: boolean; }
export interface SensorConfigResponse { id: number; esp_id: string; gpio: number; sensor_type: SensorType; name?: string; description?: string; interval_ms: number; enabled: boolean; pi_enhanced: boolean; calibration_offset: number; calibration_scale: number; i2c_address?: number; onewire_address?: string; onewire_bus_gpio?: number; alert_min?: number; alert_max?: number; alert_enabled: boolean; last_reading?: SensorReading; last_error?: string; error_count: number; created_at: string; updated_at: string; }
export interface SensorReading { timestamp: number; value: number; secondary_value?: number; raw_value?: number; unit: string; quality?: "good" | "degraded" | "bad"; }
export interface SensorDataQuery { esp_id?: string; gpio?: number; sensor_type?: SensorType; start_time?: number; end_time?: number; limit?: number; aggregation?: "none" | "avg" | "min" | "max" | "sum"; interval_seconds?: number; }
export interface SensorDataResponse { success: boolean; data: SensorReading[]; count: number; esp_id: string; gpio: number; sensor_type: SensorType; query_time_ms: number; }
export interface SensorStats { esp_id: string; gpio: number; sensor_type: SensorType; period_start: string; period_end: string; count: number; min: number; max: number; avg: number; std_dev: number; last_value: number; last_timestamp: string; }
export interface OneWireDevice { address: string; family_code: string; device_type: string; is_configured: boolean; }
export interface OneWireScanResponse { success: boolean; message: string; esp_id: string; bus_gpio: number; devices: OneWireDevice[]; scan_time_ms: number; }
export interface TriggerMeasurementResponse { success: boolean; message: string; esp_id: string; gpio: number; request_id: string; }

// Actuator Types
export type ActuatorType = "digital" | "pwm" | "servo" | "pump" | "valve" | "relay";
export interface ActuatorConfigCreate { gpio: number; actuator_type: ActuatorType; name?: string; description?: string; enabled?: boolean; pwm_frequency?: number; pwm_resolution?: number; max_runtime_seconds?: number; safe_state?: number; requires_confirmation?: boolean; inverted?: boolean; }
export interface ActuatorConfigUpdate { name?: string; description?: string; enabled?: boolean; pwm_frequency?: number; pwm_resolution?: number; max_runtime_seconds?: number; safe_state?: number; requires_confirmation?: boolean; inverted?: boolean; }
export interface ActuatorConfigResponse { id: number; esp_id: string; gpio: number; actuator_type: ActuatorType; name?: string; description?: string; enabled: boolean; pwm_frequency: number; pwm_resolution: number; max_runtime_seconds: number; safe_state: number; requires_confirmation: boolean; inverted: boolean; current_state: ActuatorState; last_command?: string; last_command_time?: string; emergency_stopped: boolean; created_at: string; updated_at: string; }
export interface ActuatorState { value: number; is_active: boolean; runtime_seconds: number; last_changed: string; source: "manual" | "logic" | "schedule" | "emergency"; }
export interface ActuatorCommand { value: number; duration_seconds?: number; source?: string; priority?: number; }
export interface ActuatorCommandResponse { success: boolean; message: string; esp_id: string; gpio: number; command_id: string; value: number; previous_value: number; estimated_execution_time_ms: number; }
export interface EmergencyStopRequest { esp_id?: string; reason: string; notify?: boolean; }
export interface EmergencyStopResponse { success: boolean; message: string; affected_actuators: number; affected_esps: string[]; timestamp: string; }
export interface ActuatorHistoryEntry { id: number; esp_id: string; gpio: number; timestamp: string; action: "on" | "off" | "set" | "emergency_stop" | "timeout"; value: number; previous_value: number; source: string; duration_seconds?: number; success: boolean; error_message?: string; }

// ESP Device Types
export interface ESPDeviceCreate { esp_id: string; name?: string; description?: string; location?: string; hardware_version?: string; firmware_version?: string; }
export interface ESPDeviceUpdate { name?: string; description?: string; location?: string; hardware_version?: string; firmware_version?: string; is_active?: boolean; master_zone_id?: string; }
export interface ESPDeviceResponse { id: number; esp_id: string; name?: string; description?: string; location?: string; hardware_version?: string; firmware_version?: string; is_active: boolean; is_online: boolean; is_mock: boolean; master_zone_id?: string; last_seen?: string; last_heartbeat?: string; uptime_seconds?: number; ip_address?: string; mac_address?: string; wifi_rssi?: number; created_at: string; updated_at: string; sensor_count: number; actuator_count: number; }
export interface GpioStatusItem { gpio: number; mode: "input" | "output" | "pwm" | "i2c" | "onewire" | "reserved" | "unused"; component_type?: "sensor" | "actuator"; component_name?: string; value?: number; }
export interface GpioStatusResponse { success: boolean; esp_id: string; gpio_pins: GpioStatusItem[]; reserved_pins: number[]; }
export interface ESPHealthMetrics { heap_free: number; heap_fragmentation: number; cpu_frequency: number; flash_size: number; uptime_seconds: number; wifi_rssi: number; mqtt_connected: boolean; sensor_error_count: number; actuator_error_count: number; last_error?: string; }
export interface ESPHealthResponse { success: boolean; esp_id: string; is_online: boolean; last_seen?: string; metrics?: ESPHealthMetrics; health_status: "healthy" | "degraded" | "critical" | "offline"; }
export interface ConfigResponsePayload { esp_id: string; status: "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED"; applied_count: number; failed_count: number; failures?: ConfigFailureItem[]; timestamp: number; }
export interface ConfigFailureItem { gpio: number; component_type: string; error_code: number; error_message: string; }
export interface PendingESPDevice { esp_id: string; first_seen: string; last_seen: string; ip_address?: string; mac_address?: string; firmware_version?: string; request_count: number; }
export interface ESPApprovalRequest { name?: string; description?: string; location?: string; master_zone_id?: string; }
export interface ESPApprovalResponse { success: boolean; message: string; device: ESPDeviceResponse; }

// Zone Types
export interface ZoneAssignRequest { zone_id: string; zone_name?: string; kaiser_id?: string; }
export interface ZoneAssignResponse { success: boolean; message: string; esp_id: string; zone_id: string; zone_name?: string; previous_zone_id?: string; mqtt_topic_published: string; }
export interface ZoneRemoveResponse { success: boolean; message: string; esp_id: string; removed_from_zone: string; }
export interface ZoneAckPayload { esp_id: string; zone_id: string; kaiser_id: string; status: "SUCCESS" | "FAILED"; error_code?: number; error_message?: string; timestamp: number; }
export interface ZoneInfo { zone_id: string; zone_name?: string; kaiser_id: string; device_count: number; devices: ESPDeviceResponse[]; created_at: string; updated_at: string; }

// Logic Engine Types
export interface SensorCondition { type: "sensor_threshold" | "sensor"; esp_id: string; gpio: number; sensor_type: SensorType; operator: ">" | "<" | ">=" | "<=" | "==" | "!="; value: number; hysteresis?: number; }
export interface TimeCondition { type: "time_window" | "time"; start_time?: string; end_time?: string; start_hour?: number; end_hour?: number; days_of_week?: number[]; }
export interface CooldownCondition { type: "cooldown"; min_interval_seconds: number; }
export interface CompoundCondition { logic: "AND" | "OR"; conditions: (SensorCondition | TimeCondition | CooldownCondition)[]; }
export type Condition = SensorCondition | TimeCondition | CooldownCondition | CompoundCondition;
export interface ActuatorAction { type: "actuator"; esp_id: string; gpio: number; actuator_type: ActuatorType; value: number; duration_seconds?: number; }
export interface NotificationAction { type: "notification"; channel: "websocket" | "email" | "webhook"; message: string; severity?: "info" | "warning" | "critical"; recipients?: string[]; }
export interface DelayAction { type: "delay"; seconds: number; }
export type Action = ActuatorAction | NotificationAction | DelayAction;
export interface LogicRuleCreate { name: string; description?: string; conditions: Condition | Condition[]; actions: Action[]; logic_operator?: "AND" | "OR"; enabled?: boolean; priority?: number; cooldown_seconds?: number; max_executions_per_hour?: number; }
export interface LogicRuleUpdate { name?: string; description?: string; conditions?: Condition | Condition[]; actions?: Action[]; logic_operator?: "AND" | "OR"; enabled?: boolean; priority?: number; cooldown_seconds?: number; max_executions_per_hour?: number; }
export interface LogicRuleResponse { id: string; name: string; description?: string; conditions: Condition | Condition[]; actions: Action[]; logic_operator: "AND" | "OR"; enabled: boolean; priority: number; cooldown_seconds: number; max_executions_per_hour: number; last_triggered?: string; execution_count: number; created_at: string; updated_at: string; }
export interface RuleTestRequest { mock_sensor_values?: Record<string, number>; mock_time?: string; dry_run?: boolean; }
export interface ConditionResult { condition_index: number; condition_type: string; result: boolean; details: string; actual_value?: number; }
export interface RuleTestResponse { success: boolean; rule_id: string; rule_name: string; would_trigger: boolean; condition_results: ConditionResult[]; action_results: string[]; dry_run: boolean; }
export interface ExecutionHistoryEntry { id: string; rule_id: string; rule_name: string; triggered_at: string; trigger_reason: string; conditions_met: Record<string, any>; actions_executed: Record<string, any>[]; success: boolean; error_message?: string; execution_time_ms: number; }
export interface RuleToggleResponse { success: boolean; message: string; rule_id: string; enabled: boolean; }

// WebSocket Types
export type WebSocketEventType = "sensor_data" | "actuator_status" | "logic_execution" | "esp_health" | "system_event" | "config_response";
export interface WebSocketFilters { types?: WebSocketEventType[]; esp_ids?: string[]; sensor_types?: SensorType[]; gpios?: number[]; }
export interface WebSocketSubscribeMessage { action: "subscribe"; filters: WebSocketFilters; }
export interface WebSocketUnsubscribeMessage { action: "unsubscribe"; filters?: WebSocketFilters; }
export interface WebSocketEvent { type: WebSocketEventType; timestamp: number; data: any; }
export interface SensorDataEvent extends WebSocketEvent { type: "sensor_data"; data: { esp_id: string; gpio: number; sensor_type: SensorType; value: number; secondary_value?: number; unit: string; raw_value?: number; quality?: "good" | "degraded" | "bad"; }; }
export interface ActuatorStatusEvent extends WebSocketEvent { type: "actuator_status"; data: { esp_id: string; gpio: number; actuator_type: ActuatorType; value: number; is_active: boolean; source: string; runtime_seconds: number; }; }
export interface LogicExecutionEvent extends WebSocketEvent { type: "logic_execution"; data: { rule_id: string; rule_name: string; triggered: boolean; conditions_met: Record<string, boolean>; actions_executed: string[]; execution_time_ms: number; }; }
export interface ESPHealthEvent extends WebSocketEvent { type: "esp_health"; data: { esp_id: string; is_online: boolean; health_status: "healthy" | "degraded" | "critical" | "offline"; heap_free?: number; wifi_rssi?: number; error_message?: string; }; }
export interface SystemEventEvent extends WebSocketEvent { type: "system_event"; data: { event_type: "startup" | "shutdown" | "error" | "warning" | "info"; source: string; message: string; details?: Record<string, any>; }; }
export interface ConfigResponseEvent extends WebSocketEvent { type: "config_response"; data: ConfigResponsePayload; }

// Common Types
export interface BaseResponse { success: boolean; message?: string; }
export interface ErrorResponse { success: false; error: string; detail: string; timestamp?: number; path?: string; request_id?: string; }
export interface ValidationErrorItem { loc: string[]; msg: string; type: string; }
export interface ValidationErrorResponse extends ErrorResponse { error: "VALIDATION_ERROR"; errors: ValidationErrorItem[]; }
export interface PaginationMeta { page: number; page_size: number; total_items: number; total_pages: number; has_next: boolean; has_prev: boolean; }
export interface PaginatedResponse<T> { success: boolean; message?: string; data: T[]; pagination: PaginationMeta; }
export interface PaginationParams { page?: number; page_size?: number; }

// ============================================================
// SUBZONE TYPES [ERGÄNZT]
// ============================================================
export interface SubzoneAssignRequest { subzone_id: string; name?: string; gpios: number[]; description?: string; parent_zone_id?: string; }
export interface SubzoneAssignResponse { success: boolean; message: string; esp_id: string; subzone_id: string; name?: string; gpios: number[]; parent_zone_id?: string; mqtt_topic_published: string; created_at: string; }
export interface SubzoneRemoveResponse { success: boolean; message: string; esp_id: string; subzone_id: string; gpios_released: number[]; }
export interface SafeModeRequest { reason?: string; notify_websocket?: boolean; }
export interface SafeModeResponse { success: boolean; message: string; esp_id: string; subzone_id: string; safe_mode_active: boolean; affected_gpios: number[]; affected_actuators: number; timestamp: string; }
export interface SubzoneAckPayload { esp_id: string; subzone_id: string; status: "SUCCESS" | "FAILED"; error_code?: number; error_message?: string; timestamp: number; }
export interface SubzoneInfo { subzone_id: string; name?: string; description?: string; esp_id: string; gpios: number[]; parent_zone_id?: string; safe_mode_active: boolean; safe_mode_activated_at?: string; sensor_count: number; actuator_count: number; created_at: string; updated_at: string; }
export interface SubzoneListResponse { success: boolean; esp_id: string; subzones: SubzoneInfo[]; total: number; }

// ============================================================
// HEALTH TYPES [ERGÄNZT]
// ============================================================
export interface HealthResponse { success: boolean; status: "healthy" | "degraded" | "unhealthy"; timestamp: string; version: string; uptime_seconds: number; }
export interface DatabaseHealth { status: "healthy" | "degraded" | "unhealthy"; connected: boolean; pool_size: number; active_connections: number; latency_ms: number; last_error?: string; }
export interface MQTTHealth { status: "healthy" | "degraded" | "unhealthy"; connected: boolean; broker_host: string; subscriptions_active: number; messages_published_total: number; messages_received_total: number; last_message_received?: string; reconnect_count: number; }
export interface WebSocketHealth { status: "healthy" | "degraded" | "unhealthy"; active_connections: number; max_connections: number; messages_sent_total: number; rate_limit_hits: number; }
export interface LogicEngineHealth { status: "healthy" | "degraded" | "unhealthy"; running: boolean; active_rules: number; rules_evaluated_total: number; actions_executed_total: number; last_evaluation?: string; average_evaluation_time_ms: number; }
export interface SchedulerHealth { status: "healthy" | "degraded" | "unhealthy"; running: boolean; jobs_scheduled: number; jobs_executed_total: number; next_job_run?: string; }
export interface SystemResourceHealth { cpu_percent: number; memory_percent: number; memory_used_mb: number; memory_available_mb: number; disk_percent: number; disk_free_gb: number; }
export interface DetailedHealthResponse extends HealthResponse { components: { database: DatabaseHealth; mqtt: MQTTHealth; websocket: WebSocketHealth; logic_engine: LogicEngineHealth; scheduler: SchedulerHealth; }; system: SystemResourceHealth; }
export interface ESPHealthItem { esp_id: string; name?: string; status: "healthy" | "degraded" | "critical" | "offline"; is_online: boolean; last_seen?: string; wifi_rssi?: number; heap_free?: number; error_count: number; sensor_count: number; actuator_count: number; }
export interface ESPHealthSummaryResponse { success: boolean; total_devices: number; online_devices: number; offline_devices: number; degraded_devices: number; devices: ESPHealthItem[]; }
export interface LivenessResponse { status: "ok" | "fail"; timestamp: string; }
export interface ReadinessResponse { status: "ready" | "not_ready"; timestamp: string; checks: { database: boolean; mqtt: boolean; scheduler: boolean; }; }

// ============================================================
// USER TYPES [ERGÄNZT]
// ============================================================
export type UserRole = "admin" | "operator" | "viewer";
export interface UserCreate { username: string; email: string; password: string; display_name?: string; role?: UserRole; is_active?: boolean; }
export interface UserUpdate { email?: string; display_name?: string; role?: UserRole; is_active?: boolean; }
export interface UserDetailResponse { id: number; username: string; email: string; display_name?: string; role: UserRole; is_active: boolean; created_at: string; updated_at: string; last_login?: string; login_count: number; }
export interface UserListResponse { success: boolean; users: UserDetailResponse[]; total: number; pagination: PaginationMeta; }
export interface PasswordReset { new_password: string; force_change_on_login?: boolean; }
export interface PasswordChange { current_password: string; new_password: string; }
export interface MessageResponse { success: boolean; message: string; }

// ============================================================
// AUDIT TYPES [ERGÄNZT]
// ============================================================
export type AuditEventType = "auth.login" | "auth.logout" | "auth.failed_login" | "user.created" | "user.updated" | "user.deleted" | "esp.registered" | "esp.updated" | "esp.deleted" | "esp.config_sent" | "sensor.created" | "sensor.updated" | "sensor.deleted" | "actuator.created" | "actuator.updated" | "actuator.deleted" | "actuator.command" | "actuator.emergency_stop" | "logic.rule_created" | "logic.rule_updated" | "logic.rule_deleted" | "logic.rule_executed" | "zone.assigned" | "zone.removed" | "subzone.created" | "subzone.removed" | "subzone.safe_mode" | "system.startup" | "system.shutdown" | "system.error";
export interface AuditLogEntry { id: number; event_type: AuditEventType; timestamp: string; user_id?: number; username?: string; ip_address?: string; user_agent?: string; resource_type?: string; resource_id?: string; action: string; details: Record<string, any>; success: boolean; error_message?: string; }
export interface AuditLogQuery { event_type?: AuditEventType | AuditEventType[]; user_id?: number; resource_type?: string; resource_id?: string; success?: boolean; start_time?: string; end_time?: string; page?: number; page_size?: number; }
export interface AuditLogListResponse { success: boolean; logs: AuditLogEntry[]; total: number; pagination: PaginationMeta; query_time_ms: number; }
export interface AggregatedEventsResponse { success: boolean; period_start: string; period_end: string; events_by_type: Record<AuditEventType, number>; events_by_hour: { hour: string; count: number }[]; total_events: number; }
export interface ErrorLogResponse { success: boolean; errors: AuditLogEntry[]; total: number; pagination: PaginationMeta; }
export interface AuditStatisticsResponse { success: boolean; total_events: number; events_today: number; events_this_week: number; events_this_month: number; top_event_types: { event_type: string; count: number }[]; top_users: { username: string; count: number }[]; error_rate_percent: number; storage_used_mb: number; }
export interface RetentionConfig { enabled: boolean; retention_days: number; backup_before_delete: boolean; auto_cleanup_enabled: boolean; cleanup_batch_size: number; }
export interface RetentionConfigUpdate { enabled?: boolean; retention_days?: number; backup_before_delete?: boolean; auto_cleanup_enabled?: boolean; cleanup_batch_size?: number; }
export interface CleanupResponse { success: boolean; message: string; deleted_count: number; backup_created: boolean; backup_file?: string; duration_ms: number; }
export interface BackupInfo { filename: string; created_at: string; size_bytes: number; record_count: number; retention_start: string; retention_end: string; }
export interface BackupListResponse { success: boolean; backups: BackupInfo[]; total_size_mb: number; }

// ============================================================
// MOCK ESP TYPES [ERGÄNZT]
// ============================================================
export type MockSystemState = "BOOT" | "WIFI_SETUP" | "WIFI_CONNECTED" | "MQTT_CONNECTING" | "MQTT_CONNECTED" | "AWAITING_USER_CONFIG" | "ZONE_CONFIGURED" | "SENSORS_CONFIGURED" | "OPERATIONAL" | "LIBRARY_DOWNLOADING" | "SAFE_MODE" | "ERROR";
export type QualityLevel = "excellent" | "good" | "fair" | "poor" | "bad" | "stale";
export type VariationPattern = "constant" | "random" | "drift";
export interface MockSensorConfig { gpio: number; sensor_type: SensorType; name?: string; subzone_id?: string; raw_value: number; unit: string; quality?: QualityLevel; raw_mode?: boolean; interface_type?: "I2C" | "ONEWIRE" | "ANALOG" | "DIGITAL"; onewire_address?: string; i2c_address?: number; interval_seconds?: number; variation_pattern?: VariationPattern; variation_range?: number; min_value?: number; max_value?: number; }
export interface MockActuatorConfig { gpio: number; actuator_type: ActuatorType; name?: string; state?: boolean; pwm_value?: number; min_value?: number; max_value?: number; }
export interface MockESPCreate { esp_id: string; zone_id?: string; zone_name?: string; master_zone_id?: string; subzone_id?: string; sensors?: MockSensorConfig[]; actuators?: MockActuatorConfig[]; auto_heartbeat?: boolean; heartbeat_interval_seconds?: number; }
export interface MockESPUpdate { zone_id?: string; master_zone_id?: string; subzone_id?: string; auto_heartbeat?: boolean; heartbeat_interval_seconds?: number; }
export interface SetSensorValueRequest { raw_value: number; quality?: QualityLevel; publish?: boolean; }
export interface BatchSensorValueRequest { values: Record<number, number>; publish?: boolean; }
export interface MockActuatorCommandRequest { command: "ON" | "OFF" | "PWM" | "TOGGLE"; value?: number; duration?: number; }
export interface StateTransitionRequest { state: MockSystemState; reason?: string; }
export interface MockSensorResponse { gpio: number; sensor_type: string; name?: string; subzone_id?: string; raw_value: number; unit: string; quality: string; raw_mode: boolean; last_read?: string; }
export interface MockActuatorResponse { gpio: number; actuator_type: string; name?: string; state: boolean; pwm_value: number; emergency_stopped: boolean; last_command?: string; }
export interface MockESPResponse { esp_id: string; name?: string; zone_id?: string; zone_name?: string; master_zone_id?: string; subzone_id?: string; system_state: MockSystemState; sensors: MockSensorResponse[]; actuators: MockActuatorResponse[]; auto_heartbeat: boolean; heap_free: number; wifi_rssi: number; uptime: number; last_heartbeat?: string; created_at: string; connected: boolean; hardware_type: string; status: "online" | "offline"; }
export interface HeartbeatResponse { success: boolean; esp_id: string; timestamp: string; message_published: boolean; payload?: Record<string, any>; }
export interface MockESPListResponse { success: boolean; data: MockESPResponse[]; total: number; }
export interface MockActuatorCommandResponse { success: boolean; esp_id: string; gpio: number; command: string; state: boolean; pwm_value: number; message: string; }

// ============================================================
// SEQUENCE TYPES [ERGÄNZT]
// ============================================================
export type SequenceStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "timeout";
export type StepFailureAction = "abort" | "continue" | "retry";
export interface SequenceStepWithAction { name?: string; action: Record<string, any>; delay_before_seconds?: number; delay_after_seconds?: number; timeout_seconds?: number; on_failure?: StepFailureAction; retry_count?: number; retry_delay_seconds?: number; }
export interface SequenceStepDelayOnly { name?: string; delay_seconds: number; }
export type SequenceStep = SequenceStepWithAction | SequenceStepDelayOnly;
export interface SequenceActionSchema { type: "sequence"; sequence_id?: string; description?: string; abort_on_failure?: boolean; max_duration_seconds?: number; steps: SequenceStep[]; }
export interface StepResult { step_index: number; step_name?: string; success: boolean; message: string; error_code?: number; started_at: string; completed_at: string; duration_ms: number; retries: number; }
export interface SequenceProgressSchema { sequence_id: string; rule_id: string; rule_name?: string; status: SequenceStatus; description?: string; current_step: number; total_steps: number; progress_percent: number; started_at: string; completed_at?: string; estimated_completion?: string; step_results: StepResult[]; current_step_name?: string; error?: string; error_code?: number; }
export interface SequenceListResponse { success: boolean; sequences: SequenceProgressSchema[]; total: number; running: number; completed: number; failed: number; }
export interface SequenceStatsResponse { success: boolean; total_sequences: number; running: number; completed_last_hour: number; failed_last_hour: number; average_duration_seconds: number; longest_sequence_id?: string; most_common_failure_step?: string; }
export interface SequenceCancelResponse { success: boolean; message: string; reason: string; }

// ============================================================
// HYSTERESIS CONDITION [ERWEITERT]
// ============================================================
export interface HysteresisCondition { type: "hysteresis"; esp_id: string; gpio: number; sensor_type?: SensorType; activate_above?: number; deactivate_below?: number; activate_below?: number; deactivate_above?: number; }

// ============================================================
// SAFETY COMPONENTS [ERWEITERT]
// ============================================================
export interface ConflictLock { actuator_key: string; owner_rule_id: string; priority: number; acquired_at: string; ttl_seconds: number; is_safety_lock: boolean; }
export interface RateLimitConfig { global_limit: number; per_esp_limit: number; per_rule_limit?: number; burst_multiplier: number; }
export interface RuleDependency { source_rule_id: string; target_actuator: string; depends_on_sensor: string; }

// ============================================================
// EXTENDED WEBSOCKET EVENTS [ERWEITERT]
// ============================================================
export type ExtendedWebSocketEventType = WebSocketEventType | "device_discovered" | "subzone_safe_mode" | "sequence_progress" | "audit_event";
export interface DeviceDiscoveredEvent extends WebSocketEvent { type: "device_discovered"; data: { esp_id: string; hardware_type: string; zone_id?: string; is_mock: boolean; discovered_at: string; }; }
export interface SubzoneSafeModeEvent extends WebSocketEvent { type: "subzone_safe_mode"; data: { esp_id: string; subzone_id: string; safe_mode_active: boolean; reason?: string; affected_gpios: number[]; }; }
export interface SequenceProgressEvent extends WebSocketEvent { type: "sequence_progress"; data: { sequence_id: string; rule_id: string; status: SequenceStatus; current_step: number; total_steps: number; progress_percent: number; current_step_name?: string; }; }
export interface AuditWebSocketEvent extends WebSocketEvent { type: "audit_event"; data: { event_type: AuditEventType; resource_type?: string; resource_id?: string; user?: string; success: boolean; }; }
```

---

**Dokument erstellt:** 2026-01-30
**Erweitert:** 2026-01-30 - 6 neue API-Sektionen, Logic Engine Safety, WebSocket Events [ERGÄNZT]
**Basiert auf:** God-Kaiser Server Codebase Analyse
**Für:** Frontend-Entwickler im AutomationOne Framework
