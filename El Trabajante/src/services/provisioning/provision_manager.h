#ifndef SERVICES_PROVISIONING_PROVISION_MANAGER_H
#define SERVICES_PROVISIONING_PROVISION_MANAGER_H

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <DNSServer.h>  // Captive Portal DNS
#include "../../models/system_types.h"
#include "../../services/config/config_manager.h"
#include "../../utils/logger.h"
#include "../../error_handling/error_tracker.h"

// ============================================
// PROVISIONING STATES
// ============================================
enum ProvisionState {
  PROVISION_IDLE = 0,                // Not in provisioning mode
  PROVISION_AP_MODE,                 // AP started, waiting for connection
  PROVISION_WAITING_CONFIG,          // Connection established, waiting for POST /provision
  PROVISION_CONFIG_RECEIVED,         // Config received, validating + saving
  PROVISION_COMPLETE,                // Config saved, ready to reboot
  PROVISION_TIMEOUT,                 // Timeout reached
  PROVISION_ERROR                    // Error occurred
};

// ============================================
// PROVISION MANAGER CLASS (Phase 6 - Provisioning Layer)
// ============================================
/**
 * ProvisionManager - ESP-AP-basiertes Zero-Touch Provisioning
 * 
 * Verantwortlichkeiten:
 * - AP-Mode starten wenn Config fehlt
 * - HTTP-Server für Config-Empfang
 * - Config-Validation & NVS-Speicherung
 * - Timeout & Error-Handling
 * - Factory-Reset-Support
 * 
 * Flow:
 * 1. needsProvisioning() prüft ob Config vorhanden
 * 2. begin() initialisiert Manager
 * 3. startAPMode() startet WiFi-AP + HTTP-Server
 * 4. waitForConfig() blockiert bis Config empfangen
 * 5. Nach Success: ESP.restart() → Production-Mode
 */
class ProvisionManager {
public:
  // Singleton Pattern
  static ProvisionManager& getInstance();
  
  // ============================================
  // INITIALIZATION & LIFECYCLE
  // ============================================
  
  /**
   * Initialisiert ProvisionManager
   * @return true wenn erfolgreich
   */
  bool begin();
  
  /**
   * Prüft ob Provisioning nötig ist
   * @return true wenn Config fehlt oder ungültig
   */
  bool needsProvisioning() const;
  
  /**
   * Startet AP-Mode + HTTP-Server
   * SSID: "AutoOne-{ESP_ID}"
   * Password: "provision"
   * IP: 192.168.4.1
   * @return true wenn erfolgreich
   */
  bool startAPMode();

  /**
   * Startet AP+STA-Mode (paralleler Reconnect) + HTTP-Server
   * Nutzt WIFI_AP_STA — Portal (AP) und Reconnect-Versuche (STA) laufen parallel.
   * Formular wird aus bestehender Config vorausgefuellt (handleRoot).
   * @return true wenn erfolgreich
   */
  bool startAPModeForReconfig();
  
  /**
   * Blockiert bis Config empfangen oder Timeout
   * @param timeout_ms Timeout in Millisekunden
   * @return true wenn Config empfangen, false bei Timeout
   */
  bool waitForConfig(uint32_t timeout_ms);
  
  /**
   * Stoppt AP-Mode + HTTP-Server
   */
  void stop();
  
  // ============================================
  // STATE MANAGEMENT
  // ============================================
  
  ProvisionState getState() const { return state_; }
  String getStateString() const;
  String getStateString(ProvisionState state) const;
  
  // ============================================
  // STATUS GETTERS
  // ============================================
  
  bool isInitialized() const { return initialized_; }
  bool isConfigReceived() const { return config_received_; }
  unsigned long getAPStartTime() const { return ap_start_time_; }
  unsigned long getUptimeSeconds() const;
  uint8_t getRetryCount() const { return retry_count_; }
  String getAPSSID() const { return ap_ssid_; }
  String getAPPassword() const { return ap_password_; }
  IPAddress getAPIP() const;
  
  // ============================================
  // LOOP (Call in main loop during provisioning)
  // ============================================
  
  /**
   * Muss während Provisioning in loop() aufgerufen werden
   * - Verarbeitet HTTP-Requests
   * - Prüft Timeouts
   * - Updated State-Machine
   */
  void loop();

  // AUT-744: RTOS-safe timeout query; checkTimeouts() has blocking delay()/retry (boot path only).
  bool isAPModeTimedOut() const {
      return (state_ == PROVISION_AP_MODE || state_ == PROVISION_WAITING_CONFIG) &&
             ((millis() - state_start_time_) > AP_MODE_TIMEOUT_MS);
  }

private:
  // ============================================
  // PRIVATE CONSTRUCTOR (SINGLETON)
  // ============================================
  
  ProvisionManager();
  ~ProvisionManager();
  
  // Prevent copy
  ProvisionManager(const ProvisionManager&) = delete;
  ProvisionManager& operator=(const ProvisionManager&) = delete;
  
  // ============================================
  // PRIVATE MEMBERS
  // ============================================
  
  // State Management
  ProvisionState state_;
  unsigned long state_start_time_;
  unsigned long ap_start_time_;
  uint8_t retry_count_;
  bool initialized_;
  bool config_received_;

  // Error Tracking for Retry Display
  bool last_connection_failed_ = false;
  String last_error_message_ = "";
  
  // WiFi & Server
  WebServer* server_;
  String ap_ssid_;
  String ap_password_;
  String esp_id_;
  
  // DNS Server for Captive Portal Detection
  // Windows/macOS perform DNS lookups to detect captive portals
  // Without DNS response, OS rejects connection with "No internet" error
  DNSServer dns_server_;
  static const uint8_t DNS_PORT = 53;
  
  // Timeouts (const für Memory-Effizienz)
  static const unsigned long AP_MODE_TIMEOUT_MS = 600000;      // 10 minutes
  static const unsigned long WAITING_TIMEOUT_MS = 300000;      // 5 minutes
  static const unsigned long REBOOT_DELAY_MS = 2000;           // 2 seconds
  static const unsigned long HTTP_TIMEOUT_MS = 10000;          // 10 seconds
  static const uint8_t MAX_RETRY_COUNT = 3;
  static const uint8_t MAX_CLIENTS = 2;                        // God-Kaiser + 1 Admin-Client
  
  // ============================================
  // PRIVATE METHODS - SETUP
  // ============================================
  
  /**
   * Startet WiFi Access Point
   * @param ap_sta_mode true = WIFI_AP_STA (STA bleibt fuer parallelen Reconnect)
   * @return true wenn erfolgreich
   */
  bool startWiFiAP(bool ap_sta_mode = false);
  
  /**
   * Startet HTTP-Server auf Port 80
   * Registriert alle Endpoints
   * @return true wenn erfolgreich
   */
  bool startHTTPServer();
  
  /**
   * Startet mDNS Service-Advertisement
   * Hostname: "esp-{ESP_ID}.local"
   * @return true wenn erfolgreich
   */
  bool startMDNS();
  
  // ============================================
  // PRIVATE METHODS - HTTP HANDLERS
  // ============================================
  
  /**
   * GET / - Landing-Page (Captive Portal)
   */
  void handleRoot();
  
  /**
   * POST /provision - Config empfangen
   * Body: JSON mit WiFiConfig + ZoneConfig
   */
  void handleProvision();
  
  /**
   * GET /status - ESP-Status abfragen
   * Response: JSON mit esp_id, state, uptime, etc.
   */
  void handleStatus();
  
  /**
   * POST /reset - Factory-Reset
   * Body: {"confirm":true}
   */
  void handleReset();
  
  /**
   * 404 - Not Found
   */
  void handleNotFound();
  
  // ============================================
  // PRIVATE METHODS - VALIDATION
  // ============================================
  
  /**
   * Validiert WiFiConfig vor Speicherung
   * Prüft: SSID-Länge, IP-Format, Port-Range
   * @param config Config-Struktur
   * @return Leer-String wenn valid, sonst Fehler-Message
   */
  String validateProvisionConfig(const WiFiConfig& config) const;
  
  /**
   * Validiert IPv4-Adresse
   * Format: xxx.xxx.xxx.xxx (0-255 pro Segment)
   * @param ip IP-String
   * @return true wenn valid
   */
  bool validateIPv4(const String& ip) const;
  
  // ============================================
  // PRIVATE METHODS - HTTP HELPERS
  // ============================================
  
  /**
   * Sendet JSON-Error-Response
   * @param status_code HTTP-Status (400, 500, etc.)
   * @param error_code Error-Code (z.B. "VALIDATION_FAILED")
   * @param message Human-readable Fehler
   */
  void sendJsonError(int status_code, const String& error_code, const String& message);
  
  /**
   * Sendet JSON-Success-Response
   * @param message Success-Message
   */
  void sendJsonSuccess(const String& message);

  /**
   * Escapes HTML special characters for safe output
   * Prevents XSS when displaying user-provided data
   * @param input Raw string to escape
   * @return HTML-safe string
   */
  String htmlEscape(const String& input);
  
  // ============================================
  // PRIVATE METHODS - STATE MACHINE
  // ============================================
  
  /**
   * Wechselt State mit Logging
   * @param new_state Neuer State
   * @return true wenn Transition erlaubt
   */
  bool transitionTo(ProvisionState new_state);
  
  /**
   * Prüft Timeouts für aktuellen State
   * @return true wenn OK, false wenn Timeout
   */
  bool checkTimeouts();
  
  /**
   * Triggered bei Timeout → Safe-Mode
   */
  void enterSafeMode();
  
  // ============================================
  // HTML LANDING PAGE (CAPTIVE PORTAL)
  // ============================================
  
  static const char* HTML_LANDING_PAGE;
};

// ============================================
// GLOBAL PROVISION MANAGER INSTANCE
// ============================================
extern ProvisionManager& provisionManager;

#endif // SERVICES_PROVISIONING_PROVISION_MANAGER_H


