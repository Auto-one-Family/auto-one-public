# ESP-AP PROVISIONING - DESIGN-SPEZIFIKATION

**Version:** 1.0  
**Datum:** 2025-01-22  
**System:** AutomationOne - El Trabajante  
**Fokus:** Zero-Touch ESP32 Provisioning via Access Point

---

## 🎯 DESIGN-PHILOSOPHIE

### Kern-Prinzipien

```
1. ZERO-TOUCH PROVISIONING
   → ESP auspacken → einschalten → automatisch im AP-Mode
   → Kein Button-Press nötig
   → Kein Serial-Monitor nötig

2. PLUG & PLAY
   → God-Kaiser scannt WiFi
   → Findet "AutoOne-ESP_XXXXXX" SSIDs
   → Verbindet → pushed Config → fertig

3. RUNTIME-FLEXIBEL
   → System läuft mit 50 ESPs
   → ESP #51 wird eingeschaltet
   → Automatisch provisioniert während System weiterläuft

4. SKALIERBAR
   → 1 ESP: 60 Sekunden Provisioning
   → 10 ESPs: 10 Minuten (sequentiell)
   → 100 ESPs: Initial-Setup über Nacht

5. INDUSTRIAL-GRADE
   → Vollständiges Error-Handling
   → Timeout-Protection
   → Factory-Reset-Optionen (3 Methoden)
   → Audit-Trail (Logging auf allen Ebenen)
```

---

## 🏗️ SYSTEM-ARCHITEKTUR

### High-Level Datenfluss

```
┌─────────────────────────────────────────────────────────────┐
│  ESP32 BOOT-SEQUENZ                                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Phase 1: Config laden │
              └───────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ NVS: Config vorhanden?│
              └───────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
         ✅ JA                       ❌ NEIN
            │                           │
            ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐
│ NORMAL FLOW           │   │ PROVISIONING FLOW     │
│ - WiFi Connect        │   │ - Start AP-Mode       │
│ - MQTT Connect        │   │ - Start HTTP-Server   │
│ - Operational         │   │ - Wait for Config     │
└───────────────────────┘   └───────────────────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │ God-Kaiser verbindet  │
                            │ zu ESP-AP             │
                            └───────────────────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │ POST /provision       │
                            │ {ssid, password, ...} │
                            └───────────────────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │ ESP: Validate Config  │
                            │ Save to NVS           │
                            │ HTTP 200 OK           │
                            └───────────────────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │ ESP.restart()         │
                            └───────────────────────┘
                                        │
                                        ▼
                            ┌───────────────────────┐
                            │ NORMAL FLOW           │
                            │ (Config vorhanden)    │
                            └───────────────────────┘
```

---

## 📡 AP-MODE SPEZIFIKATION

### WiFi Access Point

```cpp
// AP-Configuration
SSID: "AutoOne-{ESP_ID}"
  → Beispiel: "AutoOne-ESP_AB12CD"
  → ESP_ID wird aus MAC-Adresse generiert (letzte 3 Bytes)

Password: "provision"
  → Hard-coded (dokumentiert in User-Guide)
  → Balance zwischen Sicherheit und Einfachheit
  → Alternative: ESP_ID-basiert (z.B. letzten 8 Zeichen)

IP-Address: 192.168.4.1
  → Standard ESP32 AP IP

Channel: 1
  → Default-Channel (WiFi.softAP wählt automatisch)

Max Connections: 1
  → Nur God-Kaiser soll verbinden
  → Verhindert unerwünschte Connections

Hidden: false
  → SSID muss sichtbar sein (God-Kaiser scannt WiFi)
```

**Implementation:**

```cpp
bool ProvisionManager::startWiFiAP() {
  String ssid = "AutoOne-" + g_system_config.esp_id;
  String password = "provision";
  
  // Start AP
  bool success = WiFi.softAP(ssid.c_str(), password.c_str(), 1, 0, 1);
  
  if (success) {
    LOG_INFO("AP-Mode started:");
    LOG_INFO("  SSID: " + ssid);
    LOG_INFO("  Password: " + password);
    LOG_INFO("  IP: " + WiFi.softAPIP().toString());
  } else {
    LOG_ERROR("Failed to start AP-Mode");
  }
  
  return success;
}
```

---

### mDNS Service Discovery

```cpp
// mDNS-Configuration
Hostname: "esp-{ESP_ID}"
  → Beispiel: "esp-AB12CD.local"
  → Erreichbar via: http://esp-AB12CD.local

Service: "_autoone._tcp"
  → Service-Type für AutomationOne ESPs
  → God-Kaiser kann via mDNS scannen

Port: 80
  → HTTP-Server Port
```

**Implementation:**

```cpp
bool ProvisionManager::startMDNS() {
  String hostname = "esp-" + g_system_config.esp_id.substring(4);  // "ESP_AB12CD" → "AB12CD"
  hostname.toLowerCase();
  
  if (!MDNS.begin(hostname.c_str())) {
    LOG_ERROR("Failed to start mDNS");
    return false;
  }
  
  // Advertise HTTP service
  MDNS.addService("_autoone", "_tcp", 80);
  
  LOG_INFO("mDNS started: " + hostname + ".local");
  return true;
}
```

---

## 🌐 HTTP-API SPEZIFIKATION

### Endpoint 1: POST /provision

**Zweck:** Config-Daten vom God-Kaiser empfangen

**Request:**

```http
POST /provision HTTP/1.1
Host: 192.168.4.1
Content-Type: application/json
Content-Length: 234

{
  "ssid": "ProductionWiFi",
  "password": "SecretPassword123",
  "server_address": "192.168.0.100",
  "mqtt_port": 8883,
  "mqtt_username": "",
  "mqtt_password": "",
  "kaiser_id": "god_kaiser_01",
  "master_zone_id": "greenhouse_zone_1",
  "subzone_id": "section_A"
}
```

**Request-Schema:**

```json
{
  // REQUIRED
  "ssid": "string",                  // Production WiFi SSID (1-32 chars)
  "password": "string",              // WiFi Password (0-63 chars, kann leer sein für offene Netzwerke)
  "server_address": "string",        // God-Kaiser IP (IPv4 format)
  
  // OPTIONAL (Default-Values)
  "mqtt_port": 8883,                 // MQTT Port (1-65535, default: 8883)
  "mqtt_username": "",               // MQTT Username (leer = Anonymous)
  "mqtt_password": "",               // MQTT Password (leer = Anonymous)
  
  // ZONE CONFIGURATION (OPTIONAL)
  "kaiser_id": "",                   // God-Kaiser ID (assigned by server)
  "master_zone_id": "",              // Master Zone ID (optional)
  "subzone_id": ""                   // Subzone ID (optional)
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

**Response (Validation Error):**

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "success": false,
  "error": "VALIDATION_FAILED",
  "message": "WiFi SSID is empty or too long (max 32 chars)",
  "field": "ssid"
}
```

**Response (Internal Error):**

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{
  "success": false,
  "error": "NVS_WRITE_FAILED",
  "message": "Failed to save configuration to NVS"
}
```

**Validation-Rules:**

```cpp
// SSID
- Länge: 1-32 Zeichen
- Nicht leer

// Password
- Länge: 0-63 Zeichen
- Leer erlaubt (offenes Netzwerk)

// Server Address
- IPv4 Format: xxx.xxx.xxx.xxx
- Nicht leer
- Regex: ^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$

// MQTT Port
- Range: 1-65535
- Default: 8883

// MQTT Username/Password
- Optional (leer = Anonymous Mode)
```

**Implementation:**

```cpp
void ProvisionManager::handleProvision() {
  // Read request body
  String body = server_->arg("plain");
  
  // Parse JSON
  DynamicJsonDocument doc(1024);
  DeserializationError error = deserializeJson(doc, body);
  
  if (error) {
    sendJsonError(400, "JSON_PARSE_ERROR", "Invalid JSON format");
    return;
  }
  
  // Extract fields
  WiFiConfig config;
  config.ssid = doc["ssid"].as<String>();
  config.password = doc["password"] | "";  // Default: leer
  config.server_address = doc["server_address"].as<String>();
  config.mqtt_port = doc["mqtt_port"] | 8883;
  config.mqtt_username = doc["mqtt_username"] | "";
  config.mqtt_password = doc["mqtt_password"] | "";
  config.configured = true;  // Mark as configured
  
  // Validate
  String validation_error = validateProvisionConfig(config);
  if (validation_error.length() > 0) {
    sendJsonError(400, "VALIDATION_FAILED", validation_error);
    return;
  }
  
  // Save to NVS
  if (!configManager.saveWiFiConfig(config)) {
    sendJsonError(500, "NVS_WRITE_FAILED", "Failed to save configuration");
    return;
  }
  
  // Save zone config (optional)
  KaiserZone kaiser;
  MasterZone master;
  if (doc.containsKey("kaiser_id")) {
    kaiser.kaiser_id = doc["kaiser_id"].as<String>();
  }
  if (doc.containsKey("master_zone_id")) {
    master.master_zone_id = doc["master_zone_id"].as<String>();
  }
  configManager.saveZoneConfig(kaiser, master);
  
  // Success response
  DynamicJsonDocument response(256);
  response["success"] = true;
  response["message"] = "Configuration saved successfully. Rebooting in 2 seconds...";
  response["esp_id"] = g_system_config.esp_id;
  response["timestamp"] = millis();
  
  String response_str;
  serializeJson(response, response_str);
  
  server_->send(200, "application/json", response_str);
  
  // Set state
  state_ = PROVISION_CONFIG_RECEIVED;
  config_received_ = true;
  
  LOG_INFO("✅ Provisioning successful!");
}
```

---

### Endpoint 2: GET /status

**Zweck:** ESP-Status abfragen (für Debugging)

**Request:**

```http
GET /status HTTP/1.1
Host: 192.168.4.1
```

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
  "provisioned": false,
  "waiting_since": 12345678
}
```

**Implementation:**

```cpp
void ProvisionManager::handleStatus() {
  DynamicJsonDocument doc(512);
  
  doc["esp_id"] = g_system_config.esp_id;
  doc["chip_model"] = ESP.getChipModel();
  doc["mac_address"] = WiFi.macAddress();
  doc["firmware_version"] = "4.0.0";  // TODO: aus Config lesen
  doc["state"] = getStateString(state_);
  doc["uptime_seconds"] = millis() / 1000;
  doc["heap_free"] = ESP.getFreeHeap();
  doc["heap_min_free"] = ESP.getMinFreeHeap();
  doc["provisioned"] = config_received_;
  doc["waiting_since"] = ap_start_time_;
  
  String response;
  serializeJson(doc, response);
  
  server_->send(200, "application/json", response);
}
```

---

### Endpoint 3: POST /reset

**Zweck:** Factory-Reset (Config löschen)

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

**Implementation:**

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
  
  LOG_WARNING("Factory Reset requested via HTTP");
  
  // Clear WiFi config
  configManager.resetWiFiConfig();
  
  // Clear zone config
  KaiserZone kaiser;
  MasterZone master;
  configManager.saveZoneConfig(kaiser, master);
  
  // Optional: Clear sensor/actuator configs
  // ...
  
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

### Endpoint 4: GET /

**Zweck:** Captive Portal Landing-Page (optional)

**Request:**

```http
GET / HTTP/1.1
Host: 192.168.4.1
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html>
<head>
  <title>AutomationOne - Provisioning</title>
  <style>
    body { font-family: Arial; max-width: 600px; margin: 50px auto; }
    .info { background: #e3f2fd; padding: 15px; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>AutomationOne ESP32</h1>
  <div class="info">
    <p><strong>ESP ID:</strong> ESP_AB12CD</p>
    <p><strong>Status:</strong> Waiting for configuration</p>
    <p><strong>API Endpoint:</strong> POST /provision</p>
  </div>
  <p>This ESP is waiting for provisioning by the God-Kaiser server.</p>
  <p>Use the God-Kaiser web interface to configure this device.</p>
</body>
</html>
```

**Implementation:**

```cpp
const char* HTML_LANDING_PAGE = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutomationOne - Provisioning</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
    h1 { color: #1976d2; }
    .info { background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }
    .info p { margin: 5px 0; }
    .status { color: #ff9800; font-weight: bold; }
  </style>
</head>
<body>
  <h1>🤖 AutomationOne ESP32</h1>
  <div class="info">
    <p><strong>ESP ID:</strong> %ESP_ID%</p>
    <p><strong>MAC Address:</strong> %MAC_ADDRESS%</p>
    <p><strong>Status:</strong> <span class="status">Waiting for configuration</span></p>
    <p><strong>Uptime:</strong> %UPTIME% seconds</p>
  </div>
  <h2>Provisioning Instructions</h2>
  <ol>
    <li>Open the God-Kaiser web interface</li>
    <li>Navigate to "ESP Provisioning"</li>
    <li>Select this device from the list</li>
    <li>Configure WiFi and Zone settings</li>
    <li>Click "Provision"</li>
  </ol>
  <h2>API Information</h2>
  <p><strong>Endpoint:</strong> <code>POST http://192.168.4.1/provision</code></p>
  <p><strong>Status:</strong> <code>GET http://192.168.4.1/status</code></p>
</body>
</html>
)rawliteral";

void ProvisionManager::handleRoot() {
  String html = String(HTML_LANDING_PAGE);
  
  // Replace placeholders
  html.replace("%ESP_ID%", g_system_config.esp_id);
  html.replace("%MAC_ADDRESS%", WiFi.macAddress());
  html.replace("%UPTIME%", String(millis() / 1000));
  
  server_->send(200, "text/html", html);
}
```

---

## 🎛️ STATE-MACHINE DESIGN

### Provisioning States

```cpp
enum ProvisionState {
  PROVISION_IDLE,                // Not in provisioning mode
  PROVISION_AP_MODE,             // AP started, waiting for connection
  PROVISION_WAITING_CONFIG,      // Connection established, waiting for POST /provision
  PROVISION_CONFIG_RECEIVED,     // Config received, validating + saving
  PROVISION_COMPLETE,            // Config saved, ready to reboot
  PROVISION_TIMEOUT,             // Timeout reached
  PROVISION_ERROR                // Error occurred
};
```

### State Transitions

```
                    ┌─────────────┐
                    │  IDLE       │
                    └─────────────┘
                           │
                           │ begin() called
                           ▼
                    ┌─────────────┐
                    │  AP_MODE    │ ← AP started, HTTP-Server listening
                    └─────────────┘
                           │
                           │ Client connected
                           ▼
                    ┌─────────────┐
                    │ WAITING     │ ← Waiting for POST /provision
                    │ CONFIG      │
                    └─────────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
          POST /provision         Timeout (10 min)
                │                     │
                ▼                     ▼
        ┌─────────────┐       ┌─────────────┐
        │ CONFIG      │       │  TIMEOUT    │
        │ RECEIVED    │       └─────────────┘
        └─────────────┘               │
                │                     │
         Validation OK         Retry or Error
                │                     │
                ▼                     ▼
        ┌─────────────┐       ┌─────────────┐
        │ COMPLETE    │       │  ERROR      │
        └─────────────┘       └─────────────┘
                │                     │
           ESP.restart()         Safe-Mode
```

### State Methods

```cpp
class ProvisionManager {
public:
  // State Query
  ProvisionState getState() const { return state_; }
  String getStateString(ProvisionState state) const;
  
  // State Transitions
  bool transitionTo(ProvisionState new_state);
  
private:
  ProvisionState state_;
  unsigned long state_start_time_;
  
  // State-specific timeouts
  static const unsigned long AP_MODE_TIMEOUT_MS = 600000;  // 10 minutes
  static const unsigned long WAITING_TIMEOUT_MS = 300000;   // 5 minutes
};
```

---

## ⏱️ TIMEOUT & ERROR-HANDLING

### Timeout-Konfiguration

```cpp
// Provisioning-Timeouts
const unsigned long AP_MODE_TIMEOUT = 600000;      // 10 Minuten
const unsigned long WAITING_TIMEOUT = 300000;      // 5 Minuten
const unsigned long REBOOT_DELAY = 2000;           // 2 Sekunden

// HTTP-Server-Timeouts
const unsigned long HTTP_REQUEST_TIMEOUT = 10000;  // 10 Sekunden
const unsigned long HTTP_RESPONSE_TIMEOUT = 5000;  // 5 Sekunden
```

### Timeout-Handling

```cpp
bool ProvisionManager::checkTimeouts() {
  unsigned long current_time = millis();
  unsigned long elapsed = current_time - state_start_time_;
  
  switch (state_) {
    case PROVISION_AP_MODE:
      if (elapsed > AP_MODE_TIMEOUT) {
        LOG_WARNING("AP-Mode timeout reached (10 minutes)");
        transitionTo(PROVISION_TIMEOUT);
        return false;
      }
      break;
      
    case PROVISION_WAITING_CONFIG:
      if (elapsed > WAITING_TIMEOUT) {
        LOG_WARNING("Config wait timeout (5 minutes)");
        transitionTo(PROVISION_TIMEOUT);
        return false;
      }
      break;
      
    default:
      break;
  }
  
  return true;
}
```

### Error-Recovery-Strategien

```cpp
// Option 1: Retry Provisioning
if (state_ == PROVISION_TIMEOUT) {
  LOG_INFO("Retrying provisioning (attempt 2/3)");
  retry_count_++;
  if (retry_count_ < 3) {
    transitionTo(PROVISION_IDLE);
    startAPMode();  // Restart provisioning
  } else {
    LOG_CRITICAL("Max provisioning retries reached");
    enterSafeMode();
  }
}

// Option 2: Enter Safe-Mode
void ProvisionManager::enterSafeMode() {
  LOG_CRITICAL("Entering Safe-Mode due to provisioning failure");
  
  // Blink LED (GPIO 2)
  pinMode(2, OUTPUT);
  for (int i = 0; i < 10; i++) {
    digitalWrite(2, HIGH);
    delay(200);
    digitalWrite(2, LOW);
    delay(200);
  }
  
  // Update system state
  g_system_config.current_state = STATE_SAFE_MODE;
  g_system_config.safe_mode_reason = "Provisioning timeout";
  configManager.saveSystemConfig(g_system_config);
  
  // Stay in AP-Mode (unlimited timeout)
  state_ = PROVISION_AP_MODE;
  LOG_INFO("Safe-Mode: AP-Mode stays active until manual intervention");
}

// Option 3: Serial Fallback (optional)
void ProvisionManager::serialFallback() {
  LOG_INFO("╔════════════════════════════════════════╗");
  LOG_INFO("║  SERIAL FALLBACK MODE                 ║");
  LOG_INFO("╚════════════════════════════════════════╝");
  LOG_INFO("Enter config via Serial Monitor:");
  LOG_INFO("Format: SSID,PASSWORD,SERVER_IP,MQTT_PORT");
  
  // Wait for Serial input
  // ...
}
```

---

## 🏭 FACTORY-RESET METHODEN

### Methode 1: Boot-Button (Hardware)

```cpp
// Location: main.cpp setup() - BEFORE gpioManager.initializeAllPinsToSafeMode()

void checkBootButtonFactoryReset() {
  const uint8_t BOOT_BUTTON_PIN = 0;  // GPIO 0 on ESP32
  const unsigned long HOLD_TIME_MS = 10000;  // 10 seconds
  
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  
  if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
    Serial.println("╔════════════════════════════════════════╗");
    Serial.println("║  BOOT BUTTON PRESSED                  ║");
    Serial.println("║  Hold for 10 seconds to Factory Reset║");
    Serial.println("╚════════════════════════════════════════╝");
    
    unsigned long start_time = millis();
    bool held_for_10s = true;
    
    while (millis() - start_time < HOLD_TIME_MS) {
      if (digitalRead(BOOT_BUTTON_PIN) == HIGH) {
        held_for_10s = false;
        Serial.println("Button released - Factory Reset cancelled");
        break;
      }
      
      // Progress indicator
      if ((millis() - start_time) % 1000 == 0) {
        Serial.print(".");
      }
      
      delay(100);
    }
    
    if (held_for_10s) {
      Serial.println("\n╔════════════════════════════════════════╗");
      Serial.println("║  FACTORY RESET TRIGGERED              ║");
      Serial.println("╚════════════════════════════════════════╝");
      
      // Clear NVS
      storageManager.begin();
      configManager.resetWiFiConfig();
      
      Serial.println("Config cleared. Rebooting in 2 seconds...");
      delay(2000);
      ESP.restart();
    }
  }
}
```

**Verwendung:**

```cpp
void setup() {
  Serial.begin(115200);
  delay(100);
  
  // Check Boot-Button FIRST (before any initialization)
  checkBootButtonFactoryReset();
  
  // Continue with normal setup...
  gpioManager.initializeAllPinsToSafeMode();
  // ...
}
```

---

### Methode 2: HTTP-Endpoint (während Provisioning)

```cpp
// POST /reset
// Siehe Endpoint 3 oben
```

**Verwendung:**

```bash
# God-Kaiser sendet Factory-Reset
curl -X POST http://192.168.4.1/reset \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

---

### Methode 3: MQTT-Command (nach Provisioning)

```cpp
// MQTT Topic: kaiser/god/esp/{esp_id}/system/command
// Payload: {"command":"factory_reset","confirm":true}

void handleSystemCommand(const String& topic, const String& payload) {
  DynamicJsonDocument doc(256);
  deserializeJson(doc, payload);
  
  String command = doc["command"].as<String>();
  bool confirm = doc["confirm"] | false;
  
  if (command == "factory_reset" && confirm) {
    LOG_WARNING("Factory Reset requested via MQTT");
    
    // Acknowledge command
    String response = "{\"status\":\"factory_reset_initiated\"}";
    mqttClient.publish(TopicBuilder::buildSystemResponseTopic(), response);
    
    // Clear configs
    configManager.resetWiFiConfig();
    
    // Reboot
    LOG_INFO("Factory Reset complete. Rebooting in 3 seconds...");
    delay(3000);
    ESP.restart();
  }
}
```

**Verwendung:**

```bash
# God-Kaiser sendet MQTT-Command
mosquitto_pub -t "kaiser/god/esp/ESP_AB12CD/system/command" \
  -m '{"command":"factory_reset","confirm":true}'
```

---

## 🔒 SICHERHEITS-ÜBERLEGUNGEN

### Current Implementation (Phase 1)

```
✅ VORHANDEN:
- AP-Password ("provision")
- Config-Validation (SSID-Länge, IP-Format)
- NVS-Persistenz (Config bleibt nach Reboot)
- Timeout-Protection (10 Minuten AP-Mode)

❌ FEHLT (später erweitern):
- TLS/HTTPS (HTTP-Server ist unencrypted)
- Auth-Token für /provision Endpoint
- Rate-Limiting (verhindert Brute-Force)
- IP-Whitelist (nur God-Kaiser erlaubt)
```

### Security-Roadmap (Phase 6+)

```
PHASE 6: BASIC SECURITY
- HTTPS-Server (selbst-signiertes Zertifikat)
- One-Time-Token (generiert beim Boot, nur 1x verwendbar)
- IP-Whitelist (nur God-Kaiser IP erlaubt)

PHASE 7: ADVANCED SECURITY
- mTLS (Mutual TLS Authentication)
- Certificate-based Authentication
- Encrypted NVS (Config wird verschlüsselt gespeichert)

PHASE 8: INDUSTRIAL SECURITY
- HSM-Integration (Hardware Security Module)
- Secure Boot (nur signierte Firmware)
- OTA-Update-Signing
```

---

## 🎯 IMPLEMENTIERUNGS-PRIORITÄTEN

### MVP (Minimum Viable Product)

```
1. ProvisionManager-Klasse
   - begin() / startAPMode()
   - HTTP-Server (POST /provision, GET /status)
   - Config-Validation
   - NVS-Speicherung
   - Reboot-Logic

2. main.cpp Integration
   - Config-Check nach loadWiFiConfig()
   - IF Config leer → provisionManager.begin()
   - waitForConfig() mit Timeout

3. Basic Testing
   - 1 ESP provisionieren
   - Config-Validation testen
   - Reboot → OPERATIONAL
```

### Phase 2: Production-Ready

```
1. Error-Handling
   - Timeout-Logic (10 Minuten)
   - Retry-Mechanismus (3 Versuche)
   - Safe-Mode bei Failure

2. Factory-Reset
   - Boot-Button (10s hold)
   - HTTP /reset Endpoint
   - MQTT Command

3. mDNS-Integration
   - Service-Discovery
   - Landing-Page (GET /)

4. Logging & Debugging
   - Vollständige Error-Logs
   - Status-Endpoint (GET /status)
   - Serial-Output
```

### Phase 3: Industrial-Grade

```
1. Skalierung
   - 10+ ESPs parallel provisionieren
   - Queue-basiertes Processing (God-Kaiser)

2. Zonierung
   - Zone-Assignment beim Provisioning
   - Heartbeat enthält zone_id

3. Security
   - HTTPS-Server
   - One-Time-Token
   - IP-Whitelist

4. Monitoring
   - Provisioning-Audit-Log
   - Fehler-Statistiken
   - Performance-Metriken
```

---

## 📝 CONFIG-VALIDATION REGELN

### Validation-Function

```cpp
String ProvisionManager::validateProvisionConfig(const WiFiConfig& config) {
  // SSID Validation
  if (config.ssid.length() == 0) {
    return "WiFi SSID is empty";
  }
  if (config.ssid.length() > 32) {
    return "WiFi SSID too long (max 32 chars)";
  }
  
  // Password Validation
  if (config.password.length() > 63) {
    return "WiFi password too long (max 63 chars)";
  }
  
  // Server Address Validation (IPv4)
  if (config.server_address.length() == 0) {
    return "Server address is empty";
  }
  if (!validateIPv4(config.server_address)) {
    return "Server address is not a valid IPv4";
  }
  
  // MQTT Port Validation
  if (config.mqtt_port == 0 || config.mqtt_port > 65535) {
    return "MQTT port out of range (1-65535)";
  }
  
  return "";  // No errors
}

bool ProvisionManager::validateIPv4(const String& ip) {
  int parts[4];
  int part_count = 0;
  int current_part = 0;
  
  for (size_t i = 0; i < ip.length(); i++) {
    char c = ip[i];
    if (c >= '0' && c <= '9') {
      current_part = current_part * 10 + (c - '0');
      if (current_part > 255) return false;
    } else if (c == '.') {
      parts[part_count++] = current_part;
      current_part = 0;
      if (part_count > 4) return false;
    } else {
      return false;  // Invalid character
    }
  }
  parts[part_count++] = current_part;
  
  return part_count == 4;
}
```

---

## 🧪 TESTING-STRATEGIE

### Unit-Tests

```cpp
// Test 1: Config-Validation
TEST(ProvisionManager, ValidateConfig_EmptySSID) {
  WiFiConfig config;
  config.ssid = "";
  
  String error = provisionManager.validateProvisionConfig(config);
  EXPECT_EQ(error, "WiFi SSID is empty");
}

// Test 2: IPv4-Validation
TEST(ProvisionManager, ValidateIPv4_Valid) {
  EXPECT_TRUE(provisionManager.validateIPv4("192.168.0.1"));
  EXPECT_TRUE(provisionManager.validateIPv4("10.0.0.1"));
}

TEST(ProvisionManager, ValidateIPv4_Invalid) {
  EXPECT_FALSE(provisionManager.validateIPv4("256.1.1.1"));
  EXPECT_FALSE(provisionManager.validateIPv4("abc.def.ghi.jkl"));
}
```

### Integration-Tests

```cpp
// Test 3: Full Provisioning Flow
TEST(ProvisionManager, FullFlow_Success) {
  // 1. Start Provisioning
  EXPECT_TRUE(provisionManager.begin());
  EXPECT_TRUE(provisionManager.startAPMode());
  
  // 2. Simulate POST /provision
  String json = "{\"ssid\":\"TestWiFi\",\"password\":\"test123\",\"server_address\":\"192.168.0.100\"}";
  // ... HTTP-Request simulieren
  
  // 3. Check Config saved
  WiFiConfig loaded_config;
  configManager.loadWiFiConfig(loaded_config);
  EXPECT_EQ(loaded_config.ssid, "TestWiFi");
  EXPECT_TRUE(loaded_config.configured);
}
```

### Manual-Tests

```
1. ZERO-TOUCH TEST
   - ESP flashen (ohne Config)
   - Einschalten → AP-Mode startet automatisch
   - WiFi-Scan: "AutoOne-ESP_XXXXXX" sichtbar
   - Verbinden mit Password "provision"
   - POST /provision → Config speichern
   - ESP rebootet → Production-WiFi

2. TIMEOUT TEST
   - ESP flashen (ohne Config)
   - AP-Mode startet
   - Warte 10 Minuten (keine Config gesendet)
   - ESP geht in Safe-Mode

3. FACTORY-RESET TEST
   - ESP mit Config
   - Boot-Button 10s halten
   - Config gelöscht
   - ESP rebootet → AP-Mode

4. RUNTIME-ADD TEST
   - System läuft mit 5 ESPs
   - ESP #6 einschalten
   - ESP #6 startet AP-Mode
   - God-Kaiser provisioniert ESP #6
   - ESP #6 verbindet Production-WiFi
   - System weiter operational
```

---

## 📊 MEMORY-IMPACT ANALYSE

### Zusätzlicher Speicherbedarf

```
ProvisionManager:
- Class Instance: ~100 Bytes
- WebServer Instance: ~20 KB
- HTTP-Request-Buffer: ~2 KB
- State-Variables: ~100 Bytes
TOTAL: ~22 KB

Landing-Page HTML:
- HTML-String (compressed): ~1 KB

GESAMT: ~23 KB zusätzlicher RAM-Verbrauch während Provisioning
```

### Heap-Analyse

```
ESP32 (Standard):
- Total Heap: ~320 KB
- After Phase 1-5: ~200 KB free
- After Provisioning: ~177 KB free
- Reserve: ~150 KB (Safety-Buffer)

ESP32-C3 (Xiao):
- Total Heap: ~256 KB
- After Phase 1-5: ~150 KB free
- After Provisioning: ~127 KB free
- Reserve: ~100 KB (Safety-Buffer)

✅ FAZIT: Provisioning passt in beide ESP32-Varianten
```

---

## 🚀 ZUSAMMENFASSUNG

### Kern-Entscheidungen

```
1. TRIGGER: Automatisch bei leerem Config (g_wifi_config.configured == false)
2. AP-PASSWORD: "provision" (hard-coded, dokumentiert)
3. HTTP-ENDPOINTS: POST /provision, GET /status, POST /reset, GET /
4. TIMEOUT: 10 Minuten AP-Mode
5. ERROR-HANDLING: Retry (3x) → Safe-Mode
6. FACTORY-RESET: 3 Methoden (Boot-Button, HTTP, MQTT)
```

### Integration-Points

```
1. main.cpp: Nach loadWiFiConfig() (Zeile 98-102)
2. main.cpp: MQTT-Callback für factory_reset
3. main.cpp: Boot-Button-Check vor gpioManager.initializeAllPinsToSafeMode()
```

### Nächste Schritte

```
1. ProvisionManager Header erstellen (provision_manager.h)
2. ProvisionManager Implementation (provision_manager.cpp)
3. main.cpp Integration
4. Testing (Unit + Integration)
5. Dokumentation (User-Guide + Dev-Guide)
```

---

**Ende des Design-Dokuments**


