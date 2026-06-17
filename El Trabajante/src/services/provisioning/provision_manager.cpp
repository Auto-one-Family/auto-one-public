#include "provision_manager.h"
#ifdef XIAO_ESP32C3
    #include "../../config/hardware/xiao_esp32c3.h"
#elif defined(ESP32_S3_DEVKIT_MODE)
    #include "../../config/hardware/esp32_s3_devkit.h"
#else
    #include "../../config/hardware/esp32_dev.h"
#endif
#include "../../config/firmware_version.h"
#include "../../services/config/config_manager.h"
#include "../../services/config/storage_manager.h"
#include "../../models/error_codes.h"
#include "../../models/watchdog_types.h"
#include "../../drivers/gpio_manager.h"
#include <ArduinoJson.h>

// ESP-IDF TAG convention for structured logging
static const char* TAG = "PROV";

// ============================================
// HTML LANDING PAGE (Captive Portal with Form)
// ============================================
const char* ProvisionManager::HTML_LANDING_PAGE = R"rawliteral(
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AutomationOne - ESP32 Setup</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 16px;
      line-height: 1.5;
    }
    .container {
      max-width: 480px;
      margin: 0 auto;
    }
    .card {
      background: rgba(255,255,255,0.95);
      backdrop-filter: blur(10px);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.2);
    }
    h1 {
      font-size: 1.5rem;
      color: #1976d2;
      margin-bottom: 4px;
      text-align: center;
    }
    .subtitle {
      color: #666;
      font-size: 0.85rem;
      text-align: center;
      margin-bottom: 20px;
    }
    .section {
      margin-bottom: 20px;
    }
    .section-title {
      font-size: 0.8rem;
      font-weight: 600;
      color: #1976d2;
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .field { margin-bottom: 14px; }
    label {
      display: block;
      font-size: 0.85rem;
      color: #333;
      margin-bottom: 4px;
      font-weight: 500;
    }
    .required::after { content: " *"; color: #d32f2f; }
    input[type="text"], input[type="password"], input[type="number"] {
      width: 100%;
      padding: 12px 14px;
      border: 2px solid #e0e0e0;
      border-radius: 8px;
      font-size: 1rem;
      transition: border-color 0.2s, box-shadow 0.2s;
      background: #fff;
    }
    input:focus {
      outline: none;
      border-color: #1976d2;
      box-shadow: 0 0 0 3px rgba(25,118,210,0.1);
    }
    .hint {
      font-size: 0.75rem;
      color: #888;
      margin-top: 4px;
    }
    .password-wrapper { position: relative; }
    .toggle-pwd {
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      cursor: pointer;
      font-size: 1.1rem;
      color: #666;
      padding: 4px;
    }
    .toggle-pwd:hover { color: #1976d2; }
    .error-box {
      background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
      border: 1px solid #ef9a9a;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 20px;
      color: #c62828;
    }
    .error-box strong {
      display: block;
      margin-bottom: 4px;
      font-size: 0.9rem;
    }
    .error-box span { font-size: 0.85rem; }
    .submit-btn {
      width: 100%;
      padding: 14px;
      background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.1s, box-shadow 0.2s;
      margin-top: 8px;
    }
    .submit-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(25,118,210,0.4);
    }
    .submit-btn:active { transform: translateY(0); }
    .submit-btn:disabled {
      background: #bdbdbd;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    .footer {
      text-align: center;
      font-size: 0.7rem;
      color: rgba(255,255,255,0.8);
      padding-top: 16px;
      margin-top: 16px;
    }
    .footer p { margin: 2px 0; }
    .divider {
      height: 1px;
      background: #e0e0e0;
      margin: 16px 0;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>AutomationOne Setup</h1>
      <p class="subtitle">ESP-ID: %ESP_ID%</p>

      %ERROR_BOX%

      <form id="provisionForm">
        <div class="section">
          <div class="section-title">WiFi-Verbindung</div>
          <div class="field">
            <label class="required">WiFi-Netzwerk (SSID)</label>
            <input type="text" name="ssid" id="ssid" maxlength="32"
                   value="%WIFI_SSID%" placeholder="Netzwerkname eingeben" required>
          </div>
          <div class="field">
            <label class="required">WiFi-Passwort</label>
            <div class="password-wrapper">
              <input type="password" name="password" id="password" maxlength="63"
                     placeholder="Passwort eingeben">
              <button type="button" class="toggle-pwd" onclick="togglePwd()">&#128065;</button>
            </div>
            <p class="hint">Leer lassen fuer offene Netzwerke</p>
          </div>
        </div>

        <div class="divider"></div>

        <div class="section">
          <div class="section-title">Server-Verbindung</div>
          <div class="field">
            <label class="required">Server-IP</label>
            <input type="text" name="server_address" id="server_address"
                   value="%SERVER_IP%" placeholder="192.168.0.198" required
                   pattern="^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$">
          </div>
          <div class="field">
            <label>MQTT-Port</label>
            <input type="number" name="mqtt_port" id="mqtt_port"
                   value="%MQTT_PORT%" min="1" max="65535" placeholder="8883">
            <p class="hint">Standard: 8883 (TLS) oder 1883 (unverschluesselt)</p>
          </div>
        </div>

        <div class="divider"></div>

        <div class="section">
          <div class="section-title">Zone (Optional)</div>
          <div class="field">
            <label>Zone-Name</label>
            <input type="text" name="zone_name" id="zone_name"
                   value="%ZONE_NAME%" maxlength="64" placeholder="z.B. Gewaechshaus Nord">
            <p class="hint">Wenn leer: ESP erscheint als "Nicht zugewiesen"</p>
          </div>
        </div>

        <button type="submit" class="submit-btn" id="submitBtn">
          Speichern &amp; Verbinden
        </button>
      </form>
    </div>

    <div class="footer">
      <p>%ESP_ID% | Firmware v%FIRMWARE_VERSION%</p>
      <p>Heap: %HEAP_FREE% bytes | Uptime: %UPTIME%s</p>
    </div>
  </div>

  <script>
    function togglePwd() {
      var p = document.getElementById('password');
      p.type = p.type === 'password' ? 'text' : 'password';
    }

    document.getElementById('provisionForm').addEventListener('submit', function(e) {
      e.preventDefault();
      var btn = document.getElementById('submitBtn');
      btn.disabled = true;
      btn.textContent = 'Verbinde...';

      var data = {
        ssid: document.getElementById('ssid').value,
        password: document.getElementById('password').value,
        server_address: document.getElementById('server_address').value,
        mqtt_port: parseInt(document.getElementById('mqtt_port').value) || 8883,
        kaiser_id: "god"
      };

      var zoneName = document.getElementById('zone_name').value;
      if (zoneName && zoneName.trim().length > 0) {
        data.zone_name = zoneName.trim();
      }

      fetch('/provision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      .then(function(r) { return r.json(); })
      .then(function(res) {
        if (res.success) {
          btn.textContent = 'Neustart...';
          btn.style.background = 'linear-gradient(135deg, #43a047 0%, #2e7d32 100%)';
        } else {
          btn.disabled = false;
          btn.textContent = 'Speichern & Verbinden';
          alert('Fehler: ' + res.message);
        }
      })
      .catch(function(err) {
        btn.disabled = false;
        btn.textContent = 'Speichern & Verbinden';
        alert('Verbindungsfehler: ' + err.message);
      });
    });
  </script>
</body>
</html>
)rawliteral";

// ============================================
// GLOBAL PROVISION MANAGER INSTANCE
// ============================================
ProvisionManager& provisionManager = ProvisionManager::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
ProvisionManager& ProvisionManager::getInstance() {
  static ProvisionManager instance;
  return instance;
}

ProvisionManager::ProvisionManager()
  : state_(PROVISION_IDLE),
    server_(nullptr),
    esp_id_(""),
    config_received_(false),
    ap_start_time_(0),
    state_start_time_(0),
    retry_count_(0),
    initialized_(false) {
}

ProvisionManager::~ProvisionManager() {
  if (server_) {
    delete server_;
    server_ = nullptr;
  }
}

// ============================================
// INITIALIZATION & LIFECYCLE
// ============================================
bool ProvisionManager::begin() {
  if (initialized_) {
    LOG_W(TAG, "ProvisionManager already initialized");
    return true;
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  PROVISION MANAGER INITIALIZATION     ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  // Get ESP ID from global system config
  esp_id_ = configManager.getESPId();

  if (esp_id_.length() == 0) {
    LOG_E(TAG, "ProvisionManager: ESP ID not available");
    errorTracker.trackError(ERROR_SYSTEM_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "ESP ID not available for provisioning");
    return false;
  }

  LOG_I(TAG, "ESP ID: " + esp_id_);

  // Check if last connection failed (config exists but provisioning was triggered)
  // This happens when WiFi connection fails after 3 attempts
  WiFiConfig wifi_config = configManager.getWiFiConfig();
  if (wifi_config.configured && wifi_config.ssid.length() > 0) {
    // Config exists, but provisioning was triggered
    // → Last connection attempt must have failed
    last_connection_failed_ = true;
    last_error_message_ = "Verbindung zum Netzwerk '" + wifi_config.ssid +
                          "' fehlgeschlagen. Bitte Zugangsdaten pruefen.";
    LOG_W(TAG, "Previous connection failed - showing error in form");
  } else {
    last_connection_failed_ = false;
    last_error_message_ = "";
  }

  initialized_ = true;
  state_ = PROVISION_IDLE;

  LOG_I(TAG, "ProvisionManager initialized successfully");
  return true;
}

bool ProvisionManager::needsProvisioning() const {
  WiFiConfig config = configManager.getWiFiConfig();

  // Check if config is marked as configured
  if (!config.configured) {
    LOG_I(TAG, "ProvisionManager: Config not marked as configured");
    return true;
  }

  // Check if SSID is empty
  if (config.ssid.length() == 0) {
    LOG_I(TAG, "ProvisionManager: WiFi SSID is empty");
    return true;
  }

  // Config seems valid
  return false;
}

bool ProvisionManager::startAPMode() {
  if (!initialized_) {
    LOG_E(TAG, "ProvisionManager not initialized");
    return false;
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  STARTING ACCESS POINT MODE           ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  ap_start_time_ = millis();
  retry_count_ = 0;
  config_received_ = false;

  // Start WiFi AP
  if (!startWiFiAP()) {
    LOG_E(TAG, "Failed to start WiFi AP");
    transitionTo(PROVISION_ERROR);
    return false;
  }

  // Start HTTP Server
  if (!startHTTPServer()) {
    LOG_E(TAG, "Failed to start HTTP Server");
    transitionTo(PROVISION_ERROR);
    return false;
  }

  // Start mDNS (optional - non-critical)
  if (!startMDNS()) {
    LOG_W(TAG, "Failed to start mDNS (optional feature)");
    // Continue anyway
  }

  // Transition to AP_MODE state
  transitionTo(PROVISION_AP_MODE);

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  ACCESS POINT MODE ACTIVE             ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Please connect to this ESP and configure:");
  LOG_I(TAG, "  1. Connect to WiFi SSID: AutoOne-" + esp_id_);
  LOG_I(TAG, "  2. Password: provision");
  LOG_I(TAG, "  3. Open browser: http://192.168.4.1");
  LOG_I(TAG, "  4. Or use API: POST http://192.168.4.1/provision");
  LOG_I(TAG, "Timeout: " + String(AP_MODE_TIMEOUT_MS / 60000) + " minutes");

  return true;
}

bool ProvisionManager::startAPModeForReconfig() {
  if (!initialized_) {
    LOG_E(TAG, "ProvisionManager not initialized");
    return false;
  }

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  AP+STA MODE (Reconfig, Reconnect)     ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  ap_start_time_ = millis();
  retry_count_ = 0;
  config_received_ = false;

  // Start WiFi AP in AP+STA mode (STA bleibt fuer parallelen Reconnect)
  if (!startWiFiAP(true)) {
    LOG_E(TAG, "Failed to start WiFi AP (AP+STA)");
    transitionTo(PROVISION_ERROR);
    return false;
  }

  // Start HTTP Server
  if (!startHTTPServer()) {
    LOG_E(TAG, "Failed to start HTTP Server");
    transitionTo(PROVISION_ERROR);
    return false;
  }

  // Start mDNS (optional - non-critical)
  if (!startMDNS()) {
    LOG_W(TAG, "Failed to start mDNS (optional feature)");
  }

  transitionTo(PROVISION_AP_MODE);

  LOG_I(TAG, "Config-Portal geoeffnet (Server getrennt), Reconnect laeuft im Hintergrund");
  LOG_I(TAG, "Connect: AutoOne-" + esp_id_ + " | http://192.168.4.1");

  return true;
}

bool ProvisionManager::waitForConfig(uint32_t timeout_ms) {
  if (state_ != PROVISION_AP_MODE && state_ != PROVISION_WAITING_CONFIG) {
    LOG_E(TAG, "ProvisionManager: Not in AP-Mode or Waiting state");
    return false;
  }

  LOG_I(TAG, "Waiting for configuration (timeout: " + String(timeout_ms / 1000) + " seconds)");

  unsigned long start_time = millis();
  unsigned long last_feed_time = millis();

  // ─────────────────────────────────────────────────────
  // INDUSTRIAL-GRADE THROTTLED LOGGING (Siemens-Style)
  // ─────────────────────────────────────────────────────
  unsigned long last_feed_log_time = millis();
  const unsigned long LOG_THROTTLE_MS = 300000;  // Log every 5 minutes (not every feed)
  uint32_t feed_count = 0;
  uint32_t feed_failures = 0;
#ifdef ESP32_S3_DEVKIT_MODE
  unsigned long last_serial_heartbeat = millis();
  const unsigned long SERIAL_HEARTBEAT_MS = 15000;
#endif

  while (millis() - start_time < timeout_ms) {
#ifdef ESP32_S3_DEVKIT_MODE
    if (millis() - last_serial_heartbeat >= SERIAL_HEARTBEAT_MS) {
      Serial.println("[PROVISION] AP aktiv — WLAN: AutoOne-" + esp_id_ +
                     " Passwort: provision — http://192.168.4.1");
      Serial.flush();
      last_serial_heartbeat = millis();
    }
#endif
    // ─────────────────────────────────────────────────────
    // WATCHDOG FEED (every 60s in Provisioning Mode)
    // ─────────────────────────────────────────────────────
    if (millis() - last_feed_time >= 60000) {  // 60s interval
      if (feedWatchdog("PROVISIONING")) {
        last_feed_time = millis();
        feed_count++;

        // ─────────────────────────────────────────────────
        // THROTTLED LOGGING (every 5 minutes, not every feed)
        // Pattern: Siemens S7-1500 Lifecycle Logging
        // ─────────────────────────────────────────────────
        if (millis() - last_feed_log_time >= LOG_THROTTLE_MS) {
          unsigned long uptime_sec = (millis() - start_time) / 1000;
          LOG_I(TAG, "🔄 Provisioning alive: " + String(uptime_sec) +
                   "s uptime, " + String(feed_count) + " watchdog feeds");
          last_feed_log_time = millis();
        }
      } else {
        feed_failures++;
        LOG_W(TAG, "⚠️ Watchdog feed blocked (failure #" + String(feed_failures) + ")");
        // Continue anyway - user can manually reset
      }
    }

    // Process HTTP requests
    loop();

    // Check if config received
    if (config_received_) {
      unsigned long elapsed_sec = (millis() - start_time) / 1000;
      LOG_I(TAG, "✅ Configuration received successfully");
      LOG_I(TAG, "📊 Provisioning summary: " + String(feed_count) + " feeds, " +
               String(feed_failures) + " failures over " + String(elapsed_sec) + "s");
      transitionTo(PROVISION_COMPLETE);
      return true;
    }

    // Check for timeout
    if (checkTimeouts()) {
      // Timeout occurred
      LOG_E(TAG, "❌ Provisioning timeout");
      return false;
    }

    // Small delay
    delay(10);
  }

  // ─────────────────────────────────────────────────────
  // FINAL SUMMARY (Industrial Diagnostics)
  // ─────────────────────────────────────────────────────
  unsigned long total_time_sec = (millis() - start_time) / 1000;
  LOG_I(TAG, "📊 Provisioning summary: " + String(feed_count) + " feeds, " +
           String(feed_failures) + " failures over " + String(total_time_sec) + "s");

  // Timeout reached
  LOG_E(TAG, "❌ Wait timeout reached");
  transitionTo(PROVISION_TIMEOUT);
  return false;
}

void ProvisionManager::stop() {
  LOG_I(TAG, "Stopping Provision Manager");

  // Stop DNS Server (Captive Portal)
  dns_server_.stop();
  LOG_I(TAG, "DNS Server stopped");

  // Stop HTTP Server
  if (server_) {
    server_->stop();
    delete server_;
    server_ = nullptr;
  }

  // Stop mDNS
  MDNS.end();

  // Stop AP
  WiFi.softAPdisconnect(true);

  transitionTo(PROVISION_IDLE);

  LOG_I(TAG, "Provision Manager stopped");
}

// ============================================
// STATE MANAGEMENT
// ============================================
String ProvisionManager::getStateString() const {
  return getStateString(state_);
}

String ProvisionManager::getStateString(ProvisionState state) const {
  switch (state) {
    case PROVISION_IDLE:
      return "IDLE";
    case PROVISION_AP_MODE:
      return "AP_MODE";
    case PROVISION_WAITING_CONFIG:
      return "WAITING_CONFIG";
    case PROVISION_CONFIG_RECEIVED:
      return "CONFIG_RECEIVED";
    case PROVISION_COMPLETE:
      return "COMPLETE";
    case PROVISION_TIMEOUT:
      return "TIMEOUT";
    case PROVISION_ERROR:
      return "ERROR";
    default:
      return "UNKNOWN";
  }
}

bool ProvisionManager::transitionTo(ProvisionState new_state) {
  if (state_ == new_state) {
    return true;  // Already in this state
  }

  LOG_I(TAG, "Provision State Transition: " + getStateString(state_) + " → " + getStateString(new_state));

  state_ = new_state;
  state_start_time_ = millis();

  return true;
}

bool ProvisionManager::checkTimeouts() {
  unsigned long current_time = millis();
  unsigned long elapsed = current_time - state_start_time_;

  switch (state_) {
    case PROVISION_AP_MODE:
    case PROVISION_WAITING_CONFIG:
      if (elapsed > AP_MODE_TIMEOUT_MS) {
        LOG_W(TAG, "⏰ AP-Mode timeout reached (" + String(AP_MODE_TIMEOUT_MS / 60000) + " minutes)");
        transitionTo(PROVISION_TIMEOUT);

        // Check retry count
        if (retry_count_ < MAX_RETRY_COUNT) {
          retry_count_++;
          LOG_I(TAG, "Retrying provisioning (attempt " + String(retry_count_ + 1) + "/" + String(MAX_RETRY_COUNT + 1) + ")");

          // Restart provisioning
          stop();
          delay(1000);
          startAPMode();

          return false;  // Continue waiting
        } else {
          LOG_C(TAG, "❌ Max provisioning retries reached (" + String(MAX_RETRY_COUNT) + ")");
          enterSafeMode();
          return true;  // Timeout
        }
      }
      break;

    default:
      break;
  }

  return false;  // No timeout
}

void ProvisionManager::enterSafeMode() {
  LOG_C(TAG, "╔════════════════════════════════════════╗");
  LOG_C(TAG, "║  ENTERING SAFE-MODE (PROVISIONING)    ║");
  LOG_C(TAG, "║  AP-Mode remains active indefinitely  ║");
  LOG_C(TAG, "╚════════════════════════════════════════╝");

  // Update system state
  SystemConfig sys_config = configManager.getSystemConfig();
  sys_config.current_state = STATE_SAFE_MODE_PROVISIONING;  // ✅ FIX #1: Neuer State!
  sys_config.safe_mode_reason = "Provisioning timeout after " + String(MAX_RETRY_COUNT) + " retries";
  configManager.saveSystemConfig(sys_config);

  // Track error
  errorTracker.trackError(ERROR_SYSTEM_SAFE_MODE,
                         ERROR_SEVERITY_CRITICAL,
                         "Provisioning timeout - Safe-Mode active with AP");

  // User-Instructions (ERWEITERT)
  LOG_I(TAG, "");
  LOG_I(TAG, "╔═══════════════════════════════════════════════════════════╗");
  LOG_I(TAG, "║  MANUAL PROVISIONING REQUIRED                             ║");
  LOG_I(TAG, "╠═══════════════════════════════════════════════════════════╣");

  // ESP-ID-abhängige SSID-Anzeige
  String ssid_lower = esp_id_;
  ssid_lower.toLowerCase();

  LOG_I(TAG, "║  1. Connect to WiFi: AutoOne-" + esp_id_ + "                  ");
  LOG_I(TAG, "║  2. Password: provision                                   ║");
  LOG_I(TAG, "║  3. Open: http://192.168.4.1                              ║");
  LOG_I(TAG, "║     OR:   http://" + ssid_lower + ".local                    ");
  LOG_I(TAG, "║  4. Use POST /provision endpoint                          ║");
  LOG_I(TAG, "║                                                           ║");
  LOG_I(TAG, "║  Alternative: Factory-Reset (Boot-Button 10s)             ║");
  LOG_I(TAG, "╚═══════════════════════════════════════════════════════════╝");
  LOG_I(TAG, "");

  // Visual feedback (LED-Blink-Pattern)
  const uint8_t led_pin = HardwareConfig::LED_PIN;
  gpioManager.requestPin(led_pin, "system", "provision_led");
  gpioManager.configurePinMode(led_pin, OUTPUT);

  // Pattern: 10× kurzes Blinken (200ms on/off)
  LOG_I(TAG, "LED Pattern: 10× blink (GPIO " + String(led_pin) + ")");
  for (int i = 0; i < 10; i++) {
    digitalWrite(led_pin, HIGH);
    delay(200);
    digitalWrite(led_pin, LOW);
    delay(200);
  }
  gpioManager.releasePin(led_pin);

  // Transition to WAITING state (AP bleibt aktiv)
  transitionTo(PROVISION_WAITING_CONFIG);
}

// ============================================
// LOOP (Call regularly during provisioning)
// ============================================
void ProvisionManager::loop() {
  if (!initialized_) return;  // Safety-Guard: DNS-Server nie gestartet → kein Poll

  // Process DNS requests for Captive Portal
  // This is non-blocking and must be called frequently
  // Handles Windows/macOS captive portal detection queries
  dns_server_.processNextRequest();

  // Process HTTP requests
  if (server_ && (state_ == PROVISION_AP_MODE || state_ == PROVISION_WAITING_CONFIG)) {
    server_->handleClient();
  }
}

// ============================================
// WIFI & SERVER SETUP
// ============================================
bool ProvisionManager::startWiFiAP(bool ap_sta_mode) {
  LOG_I(TAG, "Starting WiFi Access Point...");

  String ssid = "AutoOne-" + esp_id_;
  String password = "provision";

  // AP-only or AP+STA (STA bleibt fuer parallelen Reconnect bei Disconnect)
  WiFi.mode(ap_sta_mode ? WIFI_AP_STA : WIFI_AP);

  // Configure AP
  // softAP(ssid, password, channel, hidden, max_connections)
  bool success = WiFi.softAP(ssid.c_str(), password.c_str(), 1, 0, MAX_CLIENTS);

  if (!success) {
    LOG_E(TAG, "Failed to start WiFi AP");
    errorTracker.trackError(ERROR_WIFI_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "WiFi.softAP() failed");
    return false;
  }

  // Get AP IP
  IPAddress ip = WiFi.softAPIP();

  LOG_I(TAG, "✅ WiFi AP started:");
  LOG_I(TAG, "  SSID: " + ssid);
  LOG_I(TAG, "  Password: " + password);
  LOG_I(TAG, "  IP Address: " + ip.toString());
  LOG_I(TAG, "  Channel: 1");
  LOG_I(TAG, "  Max Connections: " + String(MAX_CLIENTS));

  // ============================================
  // DNS SERVER FOR CAPTIVE PORTAL DETECTION
  // ============================================
  // Windows/macOS perform DNS lookups to detect captive portals
  // Without DNS response, OS rejects connection with "No internet" error
  // Solution: Redirect all DNS queries to AP IP → Client opens browser automatically

  LOG_I(TAG, "Starting DNS Server for Captive Portal...");

  bool dns_started = dns_server_.start(DNS_PORT, "*", ip);

  if (!dns_started) {
    LOG_W(TAG, "Failed to start DNS Server - Captive Portal may not work");
    LOG_W(TAG, "  Windows/macOS might reject connection");
    // Continue without DNS - AP still works, just less convenient
  } else {
    LOG_I(TAG, "✅ DNS Server started:");
    LOG_I(TAG, "  Port: 53");
    LOG_I(TAG, "  Redirect: All DNS queries -> " + ip.toString());
  }

  return true;
}

bool ProvisionManager::startHTTPServer() {
  LOG_I(TAG, "Starting HTTP Server...");

  // Create WebServer instance
  server_ = new WebServer(80);

  if (!server_) {
    LOG_E(TAG, "Failed to allocate WebServer");
    errorTracker.trackError(ERROR_SYSTEM_INIT_FAILED,
                           ERROR_SEVERITY_CRITICAL,
                           "WebServer allocation failed");
    return false;
  }

  // Register HTTP handlers
  server_->on("/", HTTP_GET, [this]() { this->handleRoot(); });
  server_->on("/provision", HTTP_POST, [this]() { this->handleProvision(); });
  server_->on("/status", HTTP_GET, [this]() { this->handleStatus(); });
  server_->on("/reset", HTTP_POST, [this]() { this->handleReset(); });
  server_->onNotFound([this]() { this->handleNotFound(); });

  // Start server
  server_->begin();

  LOG_I(TAG, "✅ HTTP Server started on port 80");
  LOG_I(TAG, "  Endpoints:");
  LOG_I(TAG, "    GET  / (Landing page)");
  LOG_I(TAG, "    POST /provision (Config submission)");
  LOG_I(TAG, "    GET  /status (ESP status)");
  LOG_I(TAG, "    POST /reset (Factory reset)");

  return true;
}

bool ProvisionManager::startMDNS() {
  LOG_I(TAG, "Starting mDNS...");

  // Extract short ID (e.g., "ESP_AB12CD" → "ab12cd")
  String hostname = esp_id_;
  hostname.replace("ESP_", "");
  hostname.toLowerCase();

  // Start mDNS
  if (!MDNS.begin(hostname.c_str())) {
    LOG_W(TAG, "Failed to start mDNS");
    return false;
  }

  // Advertise HTTP service
  MDNS.addService("http", "tcp", 80);
  MDNS.addService("autoone", "tcp", 80);

  LOG_I(TAG, "✅ mDNS started:");
  LOG_I(TAG, "  Hostname: " + hostname + ".local");
  LOG_I(TAG, "  Services: http, autoone");

  return true;
}

// ============================================
// HTTP HANDLERS
// ============================================
void ProvisionManager::handleRoot() {
  LOG_D(TAG, "HTTP GET /");

  // Load stored configuration for form pre-fill
  WiFiConfig wifi_config = configManager.getWiFiConfig();
  KaiserZone kaiser = configManager.getKaiser();

  String html = String(HTML_LANDING_PAGE);

  // Basic placeholders
  html.replace("%ESP_ID%", esp_id_);
  html.replace("%FIRMWARE_VERSION%", String(KAISER_FIRMWARE_VERSION_STRING));
  html.replace("%UPTIME%", String(getUptimeSeconds()));
  html.replace("%HEAP_FREE%", String(ESP.getFreeHeap()));

  // Form pre-fill placeholders (with HTML escaping for security)
  html.replace("%WIFI_SSID%", htmlEscape(wifi_config.ssid));
  // NOTE: Password is NEVER pre-filled for security reasons

  // Server IP: Use stored value, Wokwi defaults, or fallback
  String server_ip = wifi_config.server_address;
  #ifdef WOKWI_SIMULATION
  if (server_ip.length() == 0) {
    server_ip = "host.wokwi.internal";  // Wokwi host access
  }
  #else
  if (server_ip.length() == 0) {
    server_ip = "192.168.0.198";  // Default server IP
  }
  #endif
  html.replace("%SERVER_IP%", htmlEscape(server_ip));

  // MQTT Port: Use stored value or default
  uint16_t mqtt_port = wifi_config.mqtt_port > 0 ? wifi_config.mqtt_port : 8883;
  #ifdef WOKWI_SIMULATION
  mqtt_port = wifi_config.mqtt_port > 0 ? wifi_config.mqtt_port : 1883;  // Wokwi uses non-TLS
  #endif
  html.replace("%MQTT_PORT%", String(mqtt_port));

  // Zone Name pre-fill
  html.replace("%ZONE_NAME%", htmlEscape(kaiser.zone_name));

  // Error box: Show if last connection failed
  String errorBox = "";
  if (last_connection_failed_) {
    errorBox = "<div class=\"error-box\"><strong>Verbindung fehlgeschlagen</strong><span>";
    errorBox += htmlEscape(last_error_message_);
    errorBox += "</span></div>";
  }
  html.replace("%ERROR_BOX%", errorBox);

  server_->send(200, "text/html", html);

  // Transition to WAITING_CONFIG if not already
  if (state_ == PROVISION_AP_MODE) {
    transitionTo(PROVISION_WAITING_CONFIG);
  }
}

void ProvisionManager::handleProvision() {
  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  HTTP POST /provision                 ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");

  // Check state
  if (state_ != PROVISION_AP_MODE && state_ != PROVISION_WAITING_CONFIG) {
    sendJsonError(400, "INVALID_STATE", "Not in provisioning mode");
    return;
  }

  // Read request body
  String body = server_->arg("plain");

  if (body.length() == 0) {
    sendJsonError(400, "EMPTY_BODY", "Request body is empty");
    return;
  }

  LOG_D(TAG, "Request body length: " + String(body.length()) + " bytes");

  // Parse JSON
  DynamicJsonDocument doc(1024);
  DeserializationError error = deserializeJson(doc, body);

  if (error) {
    String error_msg = "JSON parse error: " + String(error.c_str());
    LOG_E(TAG, error_msg);
    sendJsonError(400, "JSON_PARSE_ERROR", error_msg);
    return;
  }

  // Extract WiFi Config
  WiFiConfig config;
  config.ssid = doc["ssid"] | "";
  config.password = doc["password"] | "";
  config.server_address = doc["server_address"] | "";
  config.mqtt_port = doc["mqtt_port"] | 8883;
  config.mqtt_username = doc["mqtt_username"] | "";
  config.mqtt_password = doc["mqtt_password"] | "";
  config.configured = true;  // Mark as configured

  LOG_I(TAG, "Received configuration:");
  LOG_I(TAG, "  SSID: " + config.ssid);
  LOG_I(TAG, "  Password: " + String(config.password.length() > 0 ? "***" : "(empty)"));
  LOG_I(TAG, "  Server: " + config.server_address);
  LOG_I(TAG, "  MQTT Port: " + String(config.mqtt_port));
  LOG_I(TAG, "  MQTT Username: " + (config.mqtt_username.length() > 0 ? config.mqtt_username : "(anonymous)"));

  // Validate config
  String validation_error = validateProvisionConfig(config);
  if (validation_error.length() > 0) {
    LOG_E(TAG, "Validation failed: " + validation_error);
    sendJsonError(400, "VALIDATION_FAILED", validation_error);
    return;
  }

  // Save WiFi Config to NVS
  if (!configManager.saveWiFiConfig(config)) {
    LOG_E(TAG, "Failed to save WiFi config to NVS");
    sendJsonError(500, "NVS_WRITE_FAILED", "Failed to save configuration to NVS");
    return;
  }

  LOG_I(TAG, "✅ WiFi configuration saved to NVS");

  // Extract and save Zone Config (optional)
  if (doc.containsKey("kaiser_id") || doc.containsKey("master_zone_id") || doc.containsKey("zone_name")) {
    KaiserZone kaiser = configManager.getKaiser();
    MasterZone master = configManager.getMasterZone();

    if (doc.containsKey("kaiser_id")) {
      kaiser.kaiser_id = doc["kaiser_id"].as<String>();
      LOG_I(TAG, "  Kaiser ID: " + kaiser.kaiser_id);
    }

    if (doc.containsKey("master_zone_id")) {
      master.master_zone_id = doc["master_zone_id"].as<String>();
      LOG_I(TAG, "  Master Zone ID: " + master.master_zone_id);
    }

    // NEW: zone_name processing (Server generates zone_id automatically)
    if (doc.containsKey("zone_name")) {
      kaiser.zone_name = doc["zone_name"].as<String>();
      LOG_I(TAG, "  Zone Name: " + kaiser.zone_name);
    }

    if (configManager.saveZoneConfig(kaiser, master)) {
      LOG_I(TAG, "✅ Zone configuration saved to NVS");
    } else {
      LOG_W(TAG, "⚠️ Failed to save zone configuration (non-critical)");
    }
  }

  // Reset error state on successful config save
  last_connection_failed_ = false;
  last_error_message_ = "";

  // ═══════════════════════════════════════════════════════════════════════════
  // CRITICAL FIX: Reset system state BEFORE reboot
  // ═══════════════════════════════════════════════════════════════════════════
  // Problem: STATE_SAFE_MODE_PROVISIONING was persisted in NVS but never cleared
  // after successful provisioning. This caused an infinite reboot loop:
  //   Boot → load config (valid) → STATE_SAFE_MODE_PROVISIONING (persisted)
  //   → skip WiFi → loop() sees valid config → "KONFIGURATION EMPFANGEN!" → reboot
  //
  // Solution: Reset state to STATE_BOOT before reboot so normal boot flow
  // proceeds with WiFi connection attempt on next boot.
  // ═══════════════════════════════════════════════════════════════════════════
  SystemConfig sys_config = configManager.getSystemConfig();
  if (sys_config.current_state == STATE_SAFE_MODE_PROVISIONING ||
      sys_config.current_state == STATE_SAFE_MODE) {
    LOG_I(TAG, "Resetting system state from " + String(sys_config.current_state) +
             " to STATE_BOOT");
    sys_config.current_state = STATE_BOOT;
    sys_config.safe_mode_reason = "";  // Clear safe mode reason
    sys_config.boot_count = 0;         // Reset boot counter (stable config now)
    if (!configManager.saveSystemConfig(sys_config)) {
      LOG_E(TAG, "Failed to save system config - state reset may not persist!");
      // Continue anyway - better to try than to stay in broken state
    }
  }

  // Success response
  DynamicJsonDocument response(256);
  response["success"] = true;
  response["message"] = "Configuration saved successfully. Rebooting in " + String(REBOOT_DELAY_MS / 1000) + " seconds...";
  response["esp_id"] = esp_id_;
  response["timestamp"] = millis();

  String response_str;
  serializeJson(response, response_str);

  server_->send(200, "application/json", response_str);

  // Update state
  config_received_ = true;
  transitionTo(PROVISION_CONFIG_RECEIVED);

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  ✅ PROVISIONING SUCCESSFUL           ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Rebooting in " + String(REBOOT_DELAY_MS / 1000) + " seconds...");

  // Delay before reboot (allow HTTP response to be sent)
  delay(REBOOT_DELAY_MS);

  // Reboot ESP
  ESP.restart();
}

void ProvisionManager::handleStatus() {
  LOG_D(TAG, "HTTP GET /status");

  DynamicJsonDocument doc(512);

  doc["esp_id"] = esp_id_;
  doc["chip_model"] = ESP.getChipModel();
  doc["mac_address"] = WiFi.macAddress();
  doc["firmware_version"] = KAISER_FIRMWARE_VERSION_STRING;
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

void ProvisionManager::handleReset() {
  LOG_W(TAG, "╔════════════════════════════════════════╗");
  LOG_W(TAG, "║  HTTP POST /reset                     ║");
  LOG_W(TAG, "║  FACTORY RESET REQUESTED              ║");
  LOG_W(TAG, "╚════════════════════════════════════════╝");

  // Parse request
  String body = server_->arg("plain");
  DynamicJsonDocument doc(256);
  deserializeJson(doc, body);

  // Check confirmation
  bool confirm = doc["confirm"] | false;
  if (!confirm) {
    sendJsonError(400, "CONFIRM_REQUIRED", "Set 'confirm':true to proceed with factory reset");
    return;
  }

  LOG_W(TAG, "Confirmation received - proceeding with factory reset");

  // Clear WiFi config
  configManager.resetWiFiConfig();
  LOG_I(TAG, "✅ WiFi configuration cleared");

  // Clear zone config
  KaiserZone kaiser;
  MasterZone master;
  configManager.saveZoneConfig(kaiser, master);
  LOG_I(TAG, "✅ Zone configuration cleared");

  // Success response
  DynamicJsonDocument response(256);
  response["success"] = true;
  response["message"] = "Factory reset completed. Rebooting in 3 seconds...";

  String response_str;
  serializeJson(response, response_str);

  server_->send(200, "application/json", response_str);

  LOG_I(TAG, "╔════════════════════════════════════════╗");
  LOG_I(TAG, "║  ✅ FACTORY RESET COMPLETE            ║");
  LOG_I(TAG, "╚════════════════════════════════════════╝");
  LOG_I(TAG, "Rebooting in 3 seconds...");

  // Delay before reboot
  delay(3000);

  // Reboot ESP
  ESP.restart();
}

void ProvisionManager::handleNotFound() {
  LOG_D(TAG, "HTTP 404: " + server_->uri());

  DynamicJsonDocument doc(256);
  doc["success"] = false;
  doc["error"] = "NOT_FOUND";
  doc["message"] = "Endpoint not found: " + server_->uri();
  doc["available_endpoints"] = "GET /, POST /provision, GET /status, POST /reset";

  String response;
  serializeJson(doc, response);

  server_->send(404, "application/json", response);
}

// ============================================
// HELPER FUNCTIONS
// ============================================
String ProvisionManager::validateProvisionConfig(const WiFiConfig& config) const {
  // SSID Validation
  if (config.ssid.length() == 0) {
    return "WiFi SSID is empty";
  }
  if (config.ssid.length() > 32) {
    return "WiFi SSID too long (max 32 characters)";
  }

  // Password Validation
  if (config.password.length() > 63) {
    return "WiFi password too long (max 63 characters)";
  }

  // Server Address Validation
  if (config.server_address.length() == 0) {
    return "Server address is empty";
  }
  if (!validateIPv4(config.server_address)) {
    return "Server address is not a valid IPv4 address";
  }

  // MQTT Port Validation
  if (config.mqtt_port == 0 || config.mqtt_port > 65535) {
    return "MQTT port out of range (1-65535)";
  }

  return "";  // No errors
}

bool ProvisionManager::validateIPv4(const String& ip) const {
  int parts[4];
  int part_count = 0;
  int current_part = 0;

  for (size_t i = 0; i < ip.length(); i++) {
    char c = ip[i];
    if (c >= '0' && c <= '9') {
      current_part = current_part * 10 + (c - '0');
      if (current_part > 255) {
        return false;
      }
    } else if (c == '.') {
      if (part_count >= 4) {
        return false;
      }
      parts[part_count++] = current_part;
      current_part = 0;
    } else {
      return false;  // Invalid character
    }
  }

  // Add last part
  if (part_count >= 4) {
    return false;
  }
  parts[part_count++] = current_part;

  // Must have exactly 4 parts
  return part_count == 4;
}

void ProvisionManager::sendJsonError(int status_code, const String& error_code, const String& message) {
  LOG_E(TAG, "HTTP Error " + String(status_code) + ": " + error_code + " - " + message);

  DynamicJsonDocument doc(256);
  doc["success"] = false;
  doc["error"] = error_code;
  doc["message"] = message;

  String response;
  serializeJson(doc, response);

  server_->send(status_code, "application/json", response);
}

void ProvisionManager::sendJsonSuccess(const String& message) {
  DynamicJsonDocument doc(256);
  doc["success"] = true;
  doc["message"] = message;

  String response;
  serializeJson(doc, response);

  server_->send(200, "application/json", response);
}

unsigned long ProvisionManager::getUptimeSeconds() const {
  return millis() / 1000;
}

String ProvisionManager::htmlEscape(const String& input) {
  String output = input;
  output.replace("&", "&amp;");
  output.replace("<", "&lt;");
  output.replace(">", "&gt;");
  output.replace("\"", "&quot;");
  output.replace("'", "&#39;");
  return output;
}

