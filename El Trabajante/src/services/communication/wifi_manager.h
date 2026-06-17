#ifndef SERVICES_COMMUNICATION_WIFI_MANAGER_H
#define SERVICES_COMMUNICATION_WIFI_MANAGER_H

#include <WiFi.h>
#include <Arduino.h>
#include "../../models/system_types.h"
#include "../../utils/logger.h"
#include "../../error_handling/error_tracker.h"
#include "../../error_handling/circuit_breaker.h"

// ============================================
// WIFI MANAGER CLASS (Phase 2 - Communication Layer)
// ============================================
class WiFiManager {
public:
    // Singleton Pattern
    static WiFiManager& getInstance();
    
    // Initialization
    bool begin();
    
    // Connection Management
    bool connect(const WiFiConfig& config);
    bool disconnect();
    bool isConnected() const;
    void reconnect();
    
    // Status
    String getConnectionStatus() const;
    int8_t getRSSI() const;
    IPAddress getLocalIP() const;
    String getSSID() const;
    
    // Monitoring
    void loop();  // Call in main loop for reconnection
    
    // Circuit Breaker Access (for Watchdog integration)
    CircuitState getCircuitBreakerState() const;
    
private:
    WiFiManager();
    ~WiFiManager();
    
    // Prevent copy
    WiFiManager(const WiFiManager&) = delete;
    WiFiManager& operator=(const WiFiManager&) = delete;
    
    // Private members
    WiFiConfig current_config_;
    unsigned long last_reconnect_attempt_;
    uint16_t reconnect_attempts_;
    bool initialized_;
    
    // Circuit Breaker (Phase 6+)
    CircuitBreaker circuit_breaker_;
    
    // Helper methods
    bool connectToNetwork();
    void handleDisconnection();
    bool shouldAttemptReconnect() const;
    String getWiFiStatusMessage(wl_status_t status);  // ✅ IMPROVEMENT #2: WiFi error translation
};

// ============================================
// GLOBAL WIFI MANAGER INSTANCE
// ============================================
extern WiFiManager& wifiManager;

#endif // SERVICES_COMMUNICATION_WIFI_MANAGER_H

