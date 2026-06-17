# ESP-AP PROVISIONING - INTEGRATION GUIDE

**AutomationOne - El Trabajante**  
**Version:** 1.0  
**Datum:** 2025-01-22  
**Zielgruppe:** Entwickler, System-Integratoren

---

## 🎯 ÜBERBLICK

Dieses Dokument beschreibt die **technische Integration** des ESP-AP Provisioning-Systems in El Trabajante. Es richtet sich an Entwickler, die:

- Das System verstehen wollen
- Code erweitern/anpassen
- Tests schreiben
- God-Kaiser-Server implementieren

---

## 📦 DATEIEN & STRUKTUR

### Neu erstellte Dateien

```
El Trabajante/src/services/provisioning/
├── provision_manager.h       # ProvisionManager Header (142 Zeilen)
└── provision_manager.cpp     # ProvisionManager Implementation (726 Zeilen)

docs/
├── ANALYSIS.md              # Code-Analyse (El Trabajante Architektur)
├── PROVISIONING_DESIGN.md   # Design-Spezifikation (State-Machine, API)
├── PROVISIONING.md          # User-Guide (diese Datei)
└── INTEGRATION_GUIDE.md     # Developer-Guide (diese Datei)
```

### Modifizierte Dateien

```
El Trabajante/src/main.cpp
  - Zeile 32: #include "services/provisioning/provision_manager.h"
  - Zeile 70-124: Boot-Button Factory-Reset (vor GPIO Safe-Mode)
  - Zeile 107-167: Provisioning-Check (nach Config-Load)
  - Zeile 368-405: MQTT Factory-Reset Command (im Callback)
```

---

## 🏗️ ARCHITEKTUR

### System-Komponenten

```
┌─────────────────────────────────────────────────────────────┐
│  PROVISION MANAGER                                          │
│  (Singleton, manages provisioning lifecycle)                │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ WiFi AP      │  │ HTTP Server  │  │ mDNS Service │
│ (192.168.4.1)│  │ (Port 80)    │  │ (Optional)   │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │
        │                 │
        ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│  HTTP ENDPOINTS                                             │
│  - GET  /          (Landing Page)                           │
│  - POST /provision (Config Submission)                      │
│  - GET  /status    (ESP Status)                             │
│  - POST /reset     (Factory Reset)                          │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  CONFIG MANAGER                                             │
│  (validates, saves to NVS)                                  │
└─────────────────────────────────────────────────────────────┘
```

### State-Machine

```cpp
enum ProvisionState {
  PROVISION_IDLE,                // Not in provisioning mode
  PROVISION_AP_MODE,             // AP started, waiting for connection
  PROVISION_WAITING_CONFIG,      // Connection established, waiting for POST
  PROVISION_CONFIG_RECEIVED,     // Config received, validating + saving
  PROVISION_COMPLETE,            // Config saved, ready to reboot
  PROVISION_TIMEOUT,             // Timeout reached
  PROVISION_ERROR                // Error occurred
};
```

**State Flow:**

```
IDLE → AP_MODE → WAITING_CONFIG → CONFIG_RECEIVED → COMPLETE → [ESP.restart()]
                       │
                       └─→ TIMEOUT → [Retry or Safe-Mode]
```

---

## 🔌 INTEGRATION IN MAIN.CPP

### Integration-Point 1: Include (Zeile 32)

```cpp
// Phase 5: Actuator System
#include "services/actuator/actuator_manager.h"
#include "services/actuator/safety_controller.h"

// Phase 6: Provisioning System  ← NEU
#include "services/provisioning/provision_manager.h"

// ============================================
// GLOBAL VARIABLES
// ============================================
```

**Zweck:** ProvisionManager-Klasse importieren

---

### Integration-Point 2: Boot-Button Factory-Reset (Zeile 70-124)

**Location:** **VOR** `gpioManager.initializeAllPinsToSafeMode()`

**Warum vor GPIO-Init?** GPIO 0 (Boot-Button) muss geprüft werden bevor GPIO-Manager alle Pins in Safe-Mode setzt.

```cpp
// STEP 2.5: BOOT-BUTTON FACTORY RESET CHECK
const uint8_t BOOT_BUTTON_PIN = 0;  // GPIO 0 on ESP32
const unsigned long HOLD_TIME_MS = 10000;  // 10 seconds

pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);

if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
  // Button pressed - wait 10 seconds
  // ...
  if (held_for_10s) {
    // Clear NVS
    configManager.resetWiFiConfig();
    // Reboot
    ESP.restart();
  }
}
```

**Flow:**

1. Check GPIO 0 (Boot-Button)
2. Wenn LOW (gedrückt) → warte 10 Sekunden
3. Wenn immer noch LOW → Factory-Reset
4. NVS löschen → Reboot
5. ESP startet im AP-Mode (keine Config)

**Serial-Output:**

```
╔════════════════════════════════════════╗
║  ⚠️  BOOT BUTTON PRESSED              ║
║  Hold for 10 seconds for Factory Reset║
╚════════════════════════════════════════╝
..........
╔════════════════════════════════════════╗
║  🔥 FACTORY RESET TRIGGERED           ║
╚════════════════════════════════════════╝
✅ WiFi configuration cleared
✅ Zone configuration cleared
Rebooting in 2 seconds...
```

---

### Integration-Point 3: Provisioning-Check (Zeile 107-167)

**Location:** Nach `configManager.printConfigurationStatus()`, vor `errorTracker.begin()`

```cpp
configManager.printConfigurationStatus();

// ═══════════════════════════════════════════════════
// STEP 6.5: PROVISIONING CHECK (Phase 6)
// ═══════════════════════════════════════════════════
if (!g_wifi_config.configured || g_wifi_config.ssid.length() == 0) {
  LOG_INFO("╔════════════════════════════════════════╗");
  LOG_INFO("║   NO CONFIG - STARTING PROVISIONING   ║");
  LOG_INFO("╚════════════════════════════════════════╝");
  
  // Initialize Provision Manager
  if (!provisionManager.begin()) {
    LOG_ERROR("ProvisionManager initialization failed!");
    return;  // Stop setup
  }
  
  // Start AP-Mode
  if (provisionManager.startAPMode()) {
    // Block until config received (timeout: 10 minutes)
    if (provisionManager.waitForConfig(600000)) {
      // SUCCESS: Config received
      LOG_INFO("✅ PROVISIONING SUCCESSFUL");
      delay(2000);
      ESP.restart();  // Reboot to apply config
    } else {
      // TIMEOUT: No config received
      LOG_ERROR("❌ PROVISIONING TIMEOUT");
      return;  // Stop setup - AP stays active (Safe-Mode)
    }
  }
}

// NORMAL FLOW: Config vorhanden
LOG_INFO("Configuration found - starting normal flow");
```

**Trigger-Conditions:**

```cpp
!g_wifi_config.configured           // Config-Flag nicht gesetzt
OR
g_wifi_config.ssid.length() == 0    // SSID leer
```

**Flow:**

1. **Check:** Config vorhanden?
2. **NEIN → Provisioning:**
   - `provisionManager.begin()` → Initialize
   - `provisionManager.startAPMode()` → Start AP + HTTP Server
   - `provisionManager.waitForConfig(600000)` → Block 10 Minuten
   - **Config empfangen:** Reboot → Normal Flow
   - **Timeout:** Safe-Mode → AP bleibt aktiv
3. **JA → Normal Flow:**
   - Continue mit Phase 2 (WiFi-Connect)

**Wichtig:** `waitForConfig()` **blockiert**! `setup()` läuft nicht weiter bis Config empfangen oder Timeout.

---

### Integration-Point 4: MQTT Factory-Reset (Zeile 368-405)

**Location:** Im MQTT-Callback (nach Emergency-Handling)

```cpp
// System commands (factory reset, etc.)
String system_command_topic = String(TopicBuilder::buildSystemCommandTopic());
if (topic == system_command_topic) {
  // Parse JSON payload
  DynamicJsonDocument doc(256);
  DeserializationError error = deserializeJson(doc, payload);
  
  if (!error) {
    String command = doc["command"].as<String>();
    bool confirm = doc["confirm"] | false;
    
    if (command == "factory_reset" && confirm) {
      LOG_WARNING("FACTORY RESET via MQTT");
      
      // Acknowledge command
      String response = "{\"status\":\"factory_reset_initiated\"}";
      mqttClient.publish(system_command_topic + "/response", response);
      
      // Clear configs
      configManager.resetWiFiConfig();
      
      // Reboot
      delay(3000);
      ESP.restart();
    }
  }
}
```

**MQTT Topic:**

```
kaiser/god/esp/{esp_id}/system/command
```

**Payload:**

```json
{
  "command": "factory_reset",
  "confirm": true
}
```

**Wichtig:** `"confirm": true` ist **Pflicht** (Schutz vor versehentlichem Reset)

---

## 🌐 HTTP-API REFERENZ

### Endpoint 1: GET /

**Zweck:** Landing-Page (HTML)

**Response:** HTML-Seite mit ESP-Informationen

**Placeholders:** (werden ersetzt)

- `%ESP_ID%` → `g_system_config.esp_id`
- `%MAC_ADDRESS%` → `WiFi.macAddress()`
- `%CHIP_MODEL%` → `ESP.getChipModel()`
- `%UPTIME%` → `getUptimeSeconds()`
- `%HEAP_FREE%` → `ESP.getFreeHeap()`

**Code:**

```cpp
void ProvisionManager::handleRoot() {
  String html = String(HTML_LANDING_PAGE);
  
  // Replace placeholders
  html.replace("%ESP_ID%", esp_id_);
  html.replace("%MAC_ADDRESS%", WiFi.macAddress());
  // ...
  
  server_->send(200, "text/html", html);
  
  // Transition to WAITING_CONFIG
  if (state_ == PROVISION_AP_MODE) {
    transitionTo(PROVISION_WAITING_CONFIG);
  }
}
```

---

### Endpoint 2: POST /provision

**Zweck:** Config-Daten empfangen

**Request:**

```http
POST /provision HTTP/1.1
Host: 192.168.4.1
Content-Type: application/json

{
  "ssid": "ProductionWiFi",
  "password": "Secret123",
  "server_address": "192.168.0.100",
  "mqtt_port": 8883,
  "mqtt_username": "",
  "mqtt_password": "",
  "kaiser_id": "god_kaiser_01",
  "master_zone_id": "greenhouse_zone_1"
}
```

**Response (Success):**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "Configuration saved successfully. Rebooting in 2 seconds...",
  "esp_id": "ESP_AB12CD",
  "timestamp": 12345678
}
```

**Response (Error):**

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "success": false,
  "error": "VALIDATION_FAILED",
  "message": "WiFi SSID is empty"
}
```

**Validation-Rules:**

```cpp
String ProvisionManager::validateProvisionConfig(const WiFiConfig& config) const {
  // SSID
  if (config.ssid.length() == 0) return "WiFi SSID is empty";
  if (config.ssid.length() > 32) return "WiFi SSID too long (max 32 chars)";
  
  // Password
  if (config.password.length() > 63) return "WiFi password too long (max 63 chars)";
  
  // Server Address
  if (config.server_address.length() == 0) return "Server address is empty";
  if (!validateIPv4(config.server_address)) return "Invalid IPv4 address";
  
  // MQTT Port
  if (config.mqtt_port == 0 || config.mqtt_port > 65535) return "Port out of range";
  
  return "";  // No errors
}
```

**Flow:**

1. Parse JSON
2. Extract fields → `WiFiConfig`
3. Validate (`validateProvisionConfig()`)
4. Save to NVS (`configManager.saveWiFiConfig()`)
5. Save Zone-Config (optional)
6. Send HTTP 200
7. Set `config_received_ = true`
8. Delay 2 seconds
9. `ESP.restart()`

---

### Endpoint 3: GET /status

**Zweck:** ESP-Status abfragen (für Debugging)

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "esp_id": "ESP_AB12CD",
  "chip_model": "ESP32-C3",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "firmware_version": "4.0.0",
  "state": "PROVISION_WAITING_CONFIG",
  "uptime_seconds": 45,
  "heap_free": 245632,
  "heap_min_free": 220000,
  "heap_size": 327680,
  "provisioned": false,
  "ap_start_time": 12345678,
  "retry_count": 0
}
```

**Code:**

```cpp
void ProvisionManager::handleStatus() {
  DynamicJsonDocument doc(512);
  
  doc["esp_id"] = esp_id_;
  doc["chip_model"] = ESP.getChipModel();
  doc["mac_address"] = WiFi.macAddress();
  doc["firmware_version"] = "4.0.0";
  doc["state"] = getStateString();
  doc["uptime_seconds"] = getUptimeSeconds();
  doc["heap_free"] = ESP.getFreeHeap();
  doc["heap_min_free"] = ESP.getMinFreeHeap();
  doc["heap_size"] = ESP.getHeapSize();
  doc["provisioned"] = config_received_;
  doc["ap_start_time"] = ap_start_time_;
  doc["retry_count"] = retry_count_;
  
  String response;
  serializeJson(doc, response);
  
  server_->send(200, "application/json", response);
}
```

---

### Endpoint 4: POST /reset

**Zweck:** Factory-Reset (während Provisioning)

**Request:**

```http
POST /reset HTTP/1.1
Host: 192.168.4.1
Content-Type: application/json

{
  "confirm": true
}
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "Factory reset completed. Rebooting in 3 seconds..."
}
```

**Code:**

```cpp
void ProvisionManager::handleReset() {
  // Parse request
  String body = server_->arg("plain");
  DynamicJsonDocument doc(256);
  deserializeJson(doc, body);
  
  // Check confirmation
  bool confirm = doc["confirm"] | false;
  if (!confirm) {
    sendJsonError(400, "CONFIRM_REQUIRED", "Set 'confirm':true to proceed");
    return;
  }
  
  // Clear configs
  configManager.resetWiFiConfig();
  
  // Success response
  DynamicJsonDocument response(256);
  response["success"] = true;
  response["message"] = "Factory reset completed. Rebooting in 3 seconds...";
  
  String response_str;
  serializeJson(response, response_str);
  
  server_->send(200, "application/json", response_str);
  
  // Reboot
  delay(3000);
  ESP.restart();
}
```

---

## 🧪 TESTING

### Unit-Tests (Konzept)

```cpp
// Test 1: IPv4 Validation
TEST(ProvisionManager, ValidateIPv4) {
  ProvisionManager pm;
  
  EXPECT_TRUE(pm.validateIPv4("192.168.0.1"));
  EXPECT_TRUE(pm.validateIPv4("10.0.0.1"));
  EXPECT_TRUE(pm.validateIPv4("255.255.255.255"));
  
  EXPECT_FALSE(pm.validateIPv4("256.1.1.1"));
  EXPECT_FALSE(pm.validateIPv4("abc.def.ghi.jkl"));
  EXPECT_FALSE(pm.validateIPv4("192.168.0"));
  EXPECT_FALSE(pm.validateIPv4("192.168.0.1.1"));
}

// Test 2: Config Validation
TEST(ProvisionManager, ValidateConfig) {
  ProvisionManager pm;
  WiFiConfig config;
  
  // Empty SSID
  config.ssid = "";
  EXPECT_NE(pm.validateProvisionConfig(config), "");
  
  // SSID too long
  config.ssid = String('a', 33);  // 33 chars
  EXPECT_NE(pm.validateProvisionConfig(config), "");
  
  // Valid config
  config.ssid = "TestWiFi";
  config.password = "test123";
  config.server_address = "192.168.0.1";
  config.mqtt_port = 8883;
  EXPECT_EQ(pm.validateProvisionConfig(config), "");
}
```

### Integration-Tests

```cpp
// Test 3: Full Provisioning Flow
TEST(ProvisionManager, FullFlow) {
  // 1. Start Provisioning
  EXPECT_TRUE(provisionManager.begin());
  EXPECT_TRUE(provisionManager.startAPMode());
  EXPECT_EQ(provisionManager.getState(), PROVISION_AP_MODE);
  
  // 2. Simulate HTTP POST /provision
  String json = R"({
    "ssid": "TestWiFi",
    "password": "test123",
    "server_address": "192.168.0.100",
    "mqtt_port": 8883
  })";
  
  // ... HTTP-Request simulieren (Mock WebServer)
  
  // 3. Check Config saved
  WiFiConfig loaded_config = configManager.getWiFiConfig();
  EXPECT_EQ(loaded_config.ssid, "TestWiFi");
  EXPECT_TRUE(loaded_config.configured);
  EXPECT_EQ(provisionManager.getState(), PROVISION_CONFIG_RECEIVED);
}
```

### Manual-Tests

#### Test 1: Zero-Touch Provisioning

```
1. ESP flashen (ohne Config in NVS)
2. ESP einschalten
3. Check: AP-Mode startet automatisch
   → WiFi: "AutoOne-ESP_XXXXXX" sichtbar
4. Verbinden (Password: "provision")
5. Browser: http://192.168.4.1
6. POST /provision mit gültiger Config
7. Check: ESP rebootet, verbindet Production-WiFi
8. Check: ESP sendet Heartbeat an God-Kaiser
```

**Expected Result:** ✅ ESP operational nach ~60 Sekunden

#### Test 2: Timeout-Handling

```
1. ESP flashen (ohne Config)
2. ESP einschalten → AP-Mode
3. NICHTS TUN (keine Config senden)
4. Warte 10 Minuten
5. Check: ESP geht in Safe-Mode
   → Serial: "PROVISIONING TIMEOUT"
   → AP bleibt aktiv (unbegrenzt)
6. POST /provision jetzt
7. Check: ESP rebootet, funktioniert
```

**Expected Result:** ✅ Safe-Mode ermöglicht spätes Provisioning

#### Test 3: Boot-Button Factory-Reset

```
1. ESP mit Config (operational)
2. Reset-Button drücken (oder Power-Cycle)
3. SOFORT Boot-Button gedrückt halten
4. 10 Sekunden warten (Serial zeigt Progress)
5. Check: ESP rebootet
6. Check: ESP startet AP-Mode (Config gelöscht)
```

**Expected Result:** ✅ Factory-Reset erfolgreich

#### Test 4: MQTT Factory-Reset

```
1. ESP operational (verbunden mit God-Kaiser)
2. God-Kaiser sendet MQTT:
   Topic: kaiser/god/esp/ESP_XXXXXX/system/command
   Payload: {"command":"factory_reset","confirm":true}
3. Check: ESP empfängt Command
4. Check: ESP sendet Response
5. Check: ESP rebootet nach 3 Sekunden
6. Check: ESP startet AP-Mode
```

**Expected Result:** ✅ Remote Factory-Reset funktioniert

---

## 🔧 ANPASSUNGEN & ERWEITERUNGEN

### Custom AP-Password

**Location:** `provision_manager.cpp:startWiFiAP()`

```cpp
// AKTUELL:
String password = "provision";

// CUSTOM:
String password = "MyCustomPassword123";
// Oder aus Config:
String password = configManager.getSystemConfig().ap_password;
```

### Custom Timeout

**Location:** `provision_manager.h`

```cpp
// AKTUELL:
static const unsigned long AP_MODE_TIMEOUT_MS = 600000;  // 10 minutes

// CUSTOM:
static const unsigned long AP_MODE_TIMEOUT_MS = 1800000;  // 30 minutes
```

### Custom Retry-Count

```cpp
// AKTUELL:
static const uint8_t MAX_RETRY_COUNT = 3;

// CUSTOM:
static const uint8_t MAX_RETRY_COUNT = 5;
```

### Zusätzliche Config-Felder

**Beispiel:** Timezone hinzufügen

**1. `system_types.h` erweitern:**

```cpp
struct WiFiConfig {
  String ssid;
  String password;
  String server_address;
  uint16_t mqtt_port;
  String mqtt_username;
  String mqtt_password;
  bool configured;
  
  // NEU:
  String timezone;  // z.B. "Europe/Berlin"
};
```

**2. `provision_manager.cpp` erweitern:**

```cpp
void ProvisionManager::handleProvision() {
  // ...
  config.timezone = doc["timezone"] | "UTC";
  // ...
}
```

**3. `config_manager.cpp` erweitern:**

```cpp
bool ConfigManager::saveWiFiConfig(const WiFiConfig& config) {
  // ...
  success &= storageManager.putString("timezone", config.timezone);
  // ...
}

bool ConfigManager::loadWiFiConfig(WiFiConfig& config) {
  // ...
  config.timezone = storageManager.getStringObj("timezone", "UTC");
  // ...
}
```

### Captive Portal (Auto-Redirect)

**Location:** `provision_manager.cpp` - DNSServer hinzufügen

```cpp
#include <DNSServer.h>

DNSServer* dns_server_;
const byte DNS_PORT = 53;

bool ProvisionManager::startAPMode() {
  // ... existing code ...
  
  // Start DNS Server (Captive Portal)
  dns_server_ = new DNSServer();
  dns_server_->start(DNS_PORT, "*", WiFi.softAPIP());
  
  LOG_INFO("Captive Portal enabled");
}

void ProvisionManager::loop() {
  if (server_) {
    server_->handleClient();
  }
  if (dns_server_) {
    dns_server_->processNextRequest();
  }
}
```

**Effekt:** User wird automatisch zu Landing-Page geleitet (http://192.168.4.1)

---

## 📊 MEMORY & PERFORMANCE

### Heap-Usage

```
ProvisionManager Footprint:
- Class Instance: ~100 Bytes
- WebServer: ~20 KB
- HTTP Request Buffer: ~2 KB
- HTML Landing Page: ~1 KB (statisch)
TOTAL: ~23 KB

ESP32 (Standard):
- Total Heap: ~320 KB
- After Phase 1-5: ~200 KB free
- After Provisioning: ~177 KB free
✅ Ausreichend Reserve

ESP32-C3 (Xiao):
- Total Heap: ~256 KB
- After Phase 1-5: ~150 KB free
- After Provisioning: ~127 KB free
✅ Akzeptabel (Reserve >100 KB)
```

### Performance-Metriken

```
AP-Mode Start: ~1 Sekunde
HTTP-Server Start: <100 ms
HTTP POST Verarbeitung: ~50 ms
NVS Write: ~100 ms
ESP Reboot: ~2 Sekunden

TOTAL (Config empfangen → Operational): ~30-40 Sekunden
```

---

## 🔒 SICHERHEIT

### Threat Model

**Bedrohungen:**

1. **Man-in-the-Middle:**
   - Angreifer scannt WiFi, findet ESP-AP
   - Verbindet und pushed böswillige Config
   - **Mitigation:** AP-Password, später: TLS/HTTPS

2. **Config-Injection:**
   - Angreifer sendet manipulierte JSON
   - SQL-Injection-artige Attacks
   - **Mitigation:** Config-Validation, Längen-Checks

3. **Denial-of-Service:**
   - Angreifer sendet viele Requests
   - ESP überlastet
   - **Mitigation:** Rate-Limiting (zukünftig)

4. **Physical Access:**
   - Angreifer hat physischen Zugriff
   - Boot-Button-Reset → Factory-Reset
   - **Mitigation:** Gehäuse, physische Sicherheit

### Security-Roadmap

**Phase 7: Basic Security**
- ✅ HTTPS-Server (selbst-signiertes Zertifikat)
- ✅ One-Time-Token (generiert beim Boot)
- ✅ IP-Whitelist

**Phase 8: Advanced Security**
- ✅ mTLS (Mutual TLS)
- ✅ Certificate-based Auth
- ✅ Encrypted NVS

**Phase 9: Industrial Security**
- ✅ HSM-Integration
- ✅ Secure Boot
- ✅ OTA-Update-Signing

---

## 🐛 DEBUGGING

### Serial-Output Levels

```cpp
// main.cpp
logger.setLogLevel(LOG_DEBUG);  // Alle Details

// Oder: Nur Provisioning
#define PROVISIONING_DEBUG 1
```

### Serial-Output Beispiel

```
╔════════════════════════════════════════╗
║  ESP32 Sensor Network v4.0 (Phase 2)  ║
╚════════════════════════════════════════╝
Chip Model: ESP32-C3
CPU Frequency: 160 MHz
Free Heap: 256432 bytes

[INFO] Logger system initialized
[INFO] StorageManager: NVS initialized
[INFO] ConfigManager: Loading Phase 1 configurations...
[INFO] ConfigManager: WiFi config loaded - SSID: , Server: 192.168.0.198
[INFO] ConfigManager: Zone config loaded - Kaiser: , Master: 
[INFO] ConfigManager: System config loaded - ESP ID: ESP_AB12CD
[INFO] === Configuration Status (Phase 1) ===
[INFO] WiFi Config: ✅ Loaded
[INFO] Zone Config: ✅ Loaded
[INFO] System Config: ✅ Loaded
[INFO] Configuration Complete: ❌ NO

╔════════════════════════════════════════╗
║   NO CONFIG - STARTING PROVISIONING   ║
╚════════════════════════════════════════╝
[INFO] ProvisionManager: ESP ID: ESP_AB12CD
[INFO] ProvisionManager initialized successfully
[INFO] ╔════════════════════════════════════════╗
[INFO] ║  STARTING ACCESS POINT MODE           ║
[INFO] ╚════════════════════════════════════════╝
[INFO] Starting WiFi Access Point...
[INFO] ✅ WiFi AP started:
[INFO]   SSID: AutoOne-ESP_AB12CD
[INFO]   Password: provision
[INFO]   IP Address: 192.168.4.1
[INFO]   Channel: 1
[INFO]   Max Connections: 1
[INFO] Starting HTTP Server...
[INFO] ✅ HTTP Server started on port 80
[INFO]   Endpoints:
[INFO]     GET  / (Landing page)
[INFO]     POST /provision (Config submission)
[INFO]     GET  /status (ESP status)
[INFO]     POST /reset (Factory reset)
[INFO] Starting mDNS...
[INFO] ✅ mDNS started:
[INFO]   Hostname: ab12cd.local
[INFO]   Services: http, autoone
[INFO] Provision State Transition: IDLE → AP_MODE
[INFO] ╔════════════════════════════════════════╗
[INFO] ║  ACCESS POINT MODE ACTIVE             ║
[INFO] ╚════════════════════════════════════════╝
[INFO] Please connect to this ESP and configure:
[INFO]   1. Connect to WiFi SSID: AutoOne-ESP_AB12CD
[INFO]   2. Password: provision
[INFO]   3. Open browser: http://192.168.4.1
[INFO]   4. Or use API: POST http://192.168.4.1/provision
[INFO] Timeout: 10 minutes
[INFO] Waiting for configuration (timeout: 600 seconds)

// ... Warten auf Config ...

[DEBUG] HTTP GET /
[INFO] Provision State Transition: AP_MODE → WAITING_CONFIG

[INFO] ╔════════════════════════════════════════╗
[INFO] ║  HTTP POST /provision                 ║
[INFO] ╚════════════════════════════════════════╝
[DEBUG] Request body length: 234 bytes
[INFO] Received configuration:
[INFO]   SSID: ProductionWiFi
[INFO]   Password: ***
[INFO]   Server: 192.168.0.100
[INFO]   MQTT Port: 8883
[INFO]   MQTT Username: (anonymous)
[INFO] ✅ WiFi configuration saved to NVS
[INFO] ╔════════════════════════════════════════╗
[INFO] ║  ✅ PROVISIONING SUCCESSFUL           ║
[INFO] ╚════════════════════════════════════════╝
[INFO] Rebooting in 2 seconds...

// ESP reboots...

[INFO] Configuration found - starting normal flow
[INFO] WiFi connected! IP: 192.168.0.123
[INFO] MQTT connected!
```

---

## 📞 SUPPORT & CONTRIBUTION

**Fragen? Bugs? Feature-Requests?**

1. **GitHub Issues:** [github.com/AutomationOne/issues](https://github.com)
2. **Discord:** #el-trabajante Channel
3. **Email:** dev@automationone.io

**Pull Requests Welcome!**

- Fork Repository
- Feature-Branch erstellen
- Tests schreiben
- Pull-Request stellen

**Coding-Standards:**
- PascalCase für Klassen
- snake_case für Member-Variablen (mit trailing `_`)
- UPPER_CASE für Konstanten
- Ausführliche LOG-Messages
- Error-Tracking Integration
- Memory-Safety (keine Leaks!)

---

**Version 1.0 - Januar 2025**  
**AutomationOne - Industrial IoT Made Simple**


