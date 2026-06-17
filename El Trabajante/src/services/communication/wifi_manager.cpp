#include "wifi_manager.h"
#include "mqtt_client.h"
#include "../../models/error_codes.h"
#include "../../utils/time_manager.h"
#include "../../utils/watchdog_storage.h"
#ifdef ESP_PLATFORM
#include "esp_task_wdt.h"

// ESP-IDF TAG convention for structured logging
static const char* TAG = "WIFI";
#endif

// ============================================
// CONSTANTS
// ============================================
const unsigned long RECONNECT_INTERVAL_MS = 30000;  // 30 seconds
const uint16_t MAX_RECONNECT_ATTEMPTS = 10;
const unsigned long WIFI_TIMEOUT_MS = 20000;  // ✅ IMPROVEMENT #1: 20 seconds (erhöht von 10s)

// ============================================
// GLOBAL WIFI MANAGER INSTANCE
// ============================================
WiFiManager& wifiManager = WiFiManager::getInstance();

// ============================================
// SINGLETON IMPLEMENTATION
// ============================================
WiFiManager& WiFiManager::getInstance() {
    static WiFiManager instance;
    return instance;
}

// ============================================
// CONSTRUCTOR / DESTRUCTOR
// ============================================
WiFiManager::WiFiManager() 
    : last_reconnect_attempt_(0),
      reconnect_attempts_(0),
      initialized_(false),
      circuit_breaker_("WiFi", 10, 60000, 15000) {
  // Circuit Breaker configured:
  // - 10 failures → OPEN (WiFi needs more tolerance)
  // - 60s recovery timeout (WiFi takes longer)
  // - 15s half-open test timeout
}

WiFiManager::~WiFiManager() {
    disconnect();
}

// ============================================
// INITIALIZATION
// ============================================
bool WiFiManager::begin() {
    if (initialized_) {
        LOG_W(TAG, "WiFiManager already initialized");
        return true;
    }
    
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(false);  // We handle reconnection manually
    
    initialized_ = true;
    LOG_I(TAG, "WiFiManager initialized");
    return true;
}

// ============================================
// CONNECTION MANAGEMENT
// ============================================
bool WiFiManager::connect(const WiFiConfig& config) {
    if (!initialized_) {
        LOG_E(TAG, "WiFiManager not initialized");
        errorTracker.logCommunicationError(ERROR_WIFI_INIT_FAILED, 
                                           "WiFiManager not initialized");
        return false;
    }
    
    // Validate config
    if (config.ssid.length() == 0) {
        LOG_E(TAG, "WiFi SSID is empty");
        errorTracker.logCommunicationError(ERROR_WIFI_NO_SSID, 
                                           "WiFi SSID is empty");
        return false;
    }
    
    current_config_ = config;
    reconnect_attempts_ = 0;
    
    return connectToNetwork();
}

bool WiFiManager::connectToNetwork() {
    // Planned network handover must tear down MQTT first so the broker does not
    // keep a stale TCP session alive while WiFi switches to a different AP.
    if (WiFi.status() == WL_CONNECTED) {
        String current_ssid = WiFi.SSID();
        if (current_ssid != current_config_.ssid) {
            LOG_I(TAG, "WiFi handover: " + current_ssid + " -> " + current_config_.ssid);
        } else {
            LOG_I(TAG, "WiFi reconnect requested on current SSID: " + current_ssid);
        }
        if (mqttClient.isConnected()) {
            mqttClient.disconnect();
            LOG_I(TAG, "MQTT disconnected before WiFi handover");
        }
        WiFi.disconnect(true);
        delay(100);
    }

    LOG_I(TAG, "Connecting to WiFi: " + current_config_.ssid);

    WiFi.begin(current_config_.ssid.c_str(),
               current_config_.password.c_str());

    // Wait for connection with timeout
    unsigned long start_time = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start_time > WIFI_TIMEOUT_MS) {
            // ❌ CONNECTION FAILED
            // ✅ IMPROVEMENT #2: Detailed WiFi error messages
            wl_status_t status = WiFi.status();
            String error_message = getWiFiStatusMessage(status);

            LOG_E(TAG, "╔════════════════════════════════════════╗");
            LOG_E(TAG, "║  ❌ WIFI CONNECTION FAILED            ║");
            LOG_E(TAG, "╚════════════════════════════════════════╝");
            LOG_E(TAG, "SSID: " + current_config_.ssid);
            LOG_E(TAG, "Status Code: " + String(status));
            LOG_E(TAG, "Reason: " + error_message);
            LOG_E(TAG, "");
            LOG_E(TAG, "Possible solutions:");

            // Status-specific recommendations
            if (status == WL_NO_SSID_AVAIL) {
                LOG_E(TAG, "  1. Check SSID spelling (case-sensitive!)");
                LOG_E(TAG, "  2. Ensure router is powered on and broadcasting");
                LOG_E(TAG, "  3. Check if ESP is within WiFi range");
            } else if (status == WL_CONNECT_FAILED) {
                LOG_E(TAG, "  1. Verify WiFi password is correct");
                LOG_E(TAG, "  2. Check WiFi security mode (WPA2 recommended)");
                LOG_E(TAG, "  3. Restart router if issues persist");
            } else if (status == WL_IDLE_STATUS || status == WL_DISCONNECTED) {
                LOG_E(TAG, "  1. WiFi signal too weak - move ESP closer to router");
                LOG_E(TAG, "  2. Router may be overloaded - restart router");
                LOG_E(TAG, "  3. Check for WiFi interference (2.4GHz congestion)");
            }

            errorTracker.logCommunicationError(ERROR_WIFI_CONNECT_TIMEOUT,
                                               error_message.c_str());
            circuit_breaker_.recordFailure();  // Phase 6+

            // Check if Circuit Breaker opened
            if (circuit_breaker_.isOpen()) {
                LOG_W(TAG, "WiFi Circuit Breaker OPENED after failure threshold");
                LOG_W(TAG, "  Will retry in 60 seconds");
            }

            return false;
        }
        // FIX #2: Non-blocking wait with watchdog feed
        // WiFi connect can take up to 20s - feed watchdog to prevent reset
        yield();
        #ifdef ESP_PLATFORM
        esp_task_wdt_reset();
        #endif
        delay(100);
    }

    // ✅ CONNECTION SUCCESS
    LOG_I(TAG, "WiFi connected! IP: " + WiFi.localIP().toString());
    LOG_I(TAG, "WiFi RSSI: " + String(WiFi.RSSI()) + " dBm");

    reconnect_attempts_ = 0;
    circuit_breaker_.recordSuccess();  // Phase 6+

    // ============================================
    // NTP TIME SYNCHRONIZATION (Phase 8)
    // ============================================
    // Initialize TimeManager after WiFi connection for accurate timestamps
    LOG_I(TAG, "Initializing NTP time synchronization...");
    if (timeManager.begin()) {
        LOG_I(TAG, "NTP sync successful - Unix timestamp: " + 
                 String((unsigned long)timeManager.getUnixTimestamp()));
        watchdogStorageTryFinalizeBootRecord();
    } else {
        LOG_W(TAG, "NTP sync failed - timestamps may be inaccurate");
        LOG_W(TAG, "TimeManager will retry in background");
    }

    return true;
}

// ✅ IMPROVEMENT #2: Helper function to translate WiFi status codes
String WiFiManager::getWiFiStatusMessage(wl_status_t status) {
    switch (status) {
        case WL_IDLE_STATUS:
            return "WiFi is idle (not attempting connection)";
        case WL_NO_SSID_AVAIL:
            return "SSID not found (network not in range or SSID incorrect)";
        case WL_SCAN_COMPLETED:
            return "WiFi scan completed";
        case WL_CONNECTED:
            return "WiFi connected";
        case WL_CONNECT_FAILED:
            return "Connection failed (wrong password or security mode mismatch)";
        case WL_CONNECTION_LOST:
            return "Connection lost (signal dropped or router disconnected)";
        case WL_DISCONNECTED:
            return "WiFi disconnected (timeout or signal issue)";
        default:
            return "Unknown WiFi status (code: " + String(status) + ")";
    }
}

bool WiFiManager::disconnect() {
    if (mqttClient.isConnected()) {
        mqttClient.disconnect();
        LOG_I(TAG, "MQTT disconnected before WiFi disconnect");
    }
    if (WiFi.status() == WL_CONNECTED) {
        WiFi.disconnect(true);
        LOG_I(TAG, "WiFi disconnected");
    }
    return true;
}

bool WiFiManager::isConnected() const {
    return WiFi.status() == WL_CONNECTED;
}

void WiFiManager::reconnect() {
    if (isConnected()) {
        LOG_D(TAG, "WiFi already connected");
        circuit_breaker_.recordSuccess();  // Reset on successful connection
        return;
    }
    
    // ============================================
    // CIRCUIT BREAKER CHECK (Phase 6+)
    // ============================================
    if (!circuit_breaker_.allowRequest()) {
        LOG_D(TAG, "WiFi reconnect blocked by Circuit Breaker (waiting for recovery)");
        return;  // Skip reconnect attempt
    }
    
    if (!shouldAttemptReconnect()) {
        return;
    }
    
    reconnect_attempts_++;
    last_reconnect_attempt_ = millis();
    
    LOG_I(TAG, "Attempting WiFi reconnection (attempt " +
             String(reconnect_attempts_) + ")");

    if (!connectToNetwork()) {
        // connectToNetwork already calls circuit_breaker_.recordFailure()
        // FIX #1: MAX_RECONNECT_ATTEMPTS check entfernt - Circuit Breaker regelt dies
    } else {
        // ✅ RECONNECT SUCCESS
        // connectToNetwork already calls circuit_breaker_.recordSuccess()
        // Ensure TimeManager resumes SNTP after a prior disconnect stop.
        timeManager.onWiFiConnected();
    }
}

// ============================================
// MONITORING
// ============================================
void WiFiManager::loop() {
    if (!initialized_) {
        return;
    }
    
    // Check connection status
    if (!isConnected()) {
        handleDisconnection();
    }
}

void WiFiManager::handleDisconnection() {
    static bool disconnection_logged = false;

    if (!disconnection_logged) {
        LOG_W(TAG, "WiFi disconnected");
        errorTracker.logCommunicationError(ERROR_WIFI_DISCONNECT,
                                           "WiFi connection lost");
        // Stop SNTP daemon to prevent log flood while WiFi is down
        timeManager.onWiFiDisconnected();
        disconnection_logged = true;
    }

    reconnect();

    if (isConnected()) {
        disconnection_logged = false;
    }
}

bool WiFiManager::shouldAttemptReconnect() const {
    // FIX #1: MAX_RECONNECT_ATTEMPTS entfernt (wie MQTT-Client, Zeile 730-734)
    // Circuit Breaker regelt Retry-Limit: 10 Failures → OPEN → 60s Pause → Recovery
    // MAX_RECONNECT_ATTEMPTS war redundant und verhinderte Recovery.

    // FIX #5: HALF_OPEN bypasses reconnect interval (wie MQTT-Client, Zeile 742-744)
    // Bei HALF_OPEN sofort Reconnect versuchen - das ist der Sinn von HALF_OPEN!
    if (circuit_breaker_.getState() == CircuitState::HALF_OPEN) {
        return true;
    }

    // Circuit Breaker Check
    if (circuit_breaker_.isOpen()) {
        return false;
    }

    // Wait for reconnect interval
    unsigned long current_time = millis();
    if (current_time - last_reconnect_attempt_ < RECONNECT_INTERVAL_MS) {
        return false;
    }

    return true;
}

// ============================================
// STATUS GETTERS
// ============================================
String WiFiManager::getConnectionStatus() const {
    switch (WiFi.status()) {
        case WL_CONNECTED:
            return "Connected";
        case WL_NO_SSID_AVAIL:
            return "SSID not available";
        case WL_CONNECT_FAILED:
            return "Connection failed";
        case WL_CONNECTION_LOST:
            return "Connection lost";
        case WL_DISCONNECTED:
            return "Disconnected";
        case WL_IDLE_STATUS:
            return "Idle";
        default:
            return "Unknown";
    }
}

int8_t WiFiManager::getRSSI() const {
    return WiFi.RSSI();
}

IPAddress WiFiManager::getLocalIP() const {
    return WiFi.localIP();
}

String WiFiManager::getSSID() const {
    return WiFi.SSID();
}


CircuitState WiFiManager::getCircuitBreakerState() const {
    return circuit_breaker_.getState();
}
